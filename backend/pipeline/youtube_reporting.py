"""
YouTube Reporting API v1 連携 — サムネ impressions / CTR のバルクレポート取り込み。

なぜ Analytics API v2 ではないのか:
    サムネ表示回数（impressions）とサムネ CTR は **YouTube Analytics API v2 には
    存在しない**。`metrics=impressions` を投げると 400 "Unknown identifier
    (impressions) given in field parameters.metrics." で拒否される。
    （`cardImpressions` / `cardClickRate` は情報カードの指標であって
    サムネのそれではない。カードを貼っていないショートでは常に 0 になる。）

    サムネ指標を API で取れる唯一の経路が Reporting API のバルクレポート
    `channel_reach_basic_a1`:
        dimensions: date, channel_id, video_id
        metrics:    video_thumbnail_impressions, video_thumbnail_impressions_ctr

運用上の性質（Analytics API と違うところ）:
  - **ジョブを作らないとデータが1バイトも存在しない。** レポートは
    「ジョブ作成後に YouTube が日次生成する」方式で、作成前に遡って
    問い合わせることはできない。ensure_job() を先に通す必要がある。
  - ジョブ作成から最初のレポートが出るまで **最大 48 時間**かかる。
  - ジョブ作成時点で **過去 30 日分がバックフィル**される（それより古い期間は
    永久に取得不能）。
  - レポートは日次 CSV。同じ日のレポートが再発行されることがあるので
    report_id 単位で冪等に取り込む。

公開関数:
  - ensure_job(channel_id)            ジョブが無ければ作る
  - list_jobs(channel_id)             ジョブ一覧
  - ingest_reports(channel_id, ...)   未取り込みレポートを DL して日次テーブルへ
  - writeback_reach(channel_id, ...)  日次テーブルを合算して video_metrics へ反映
  - sync_reach(channel_id, days=30)   取り込み＋書き戻し
  - sync_reach_all(...)               全チャンネルの取り込み（analytics.enabled 非依存）
"""

from __future__ import annotations

import csv
import io
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import youtube_oauth as yt_oauth
from .analytics import store as analytics_store


REPORT_TYPE_ID = "channel_reach_basic_a1"
JOB_NAME = "youtube-factory reach (thumbnail impressions/CTR)"

# reports.list はサーバ側の一時障害で 500 / 503 / 429 を返すことがある。
# 1回でも落ちるとそのチャンネルの取り込みが丸ごと 0 件になるので再試行する。
RETRYABLE_STATUS = (429, 500, 502, 503, 504)
LIST_MAX_ATTEMPTS = 4
LIST_BACKOFF_SEC = 1.5

# レポートの列名（channel_reach_basic_a1）
COL_DATE = "date"
COL_VIDEO = "video_id"
COL_IMPRESSIONS = "video_thumbnail_impressions"
COL_CTR = "video_thumbnail_impressions_ctr"


# ---------------------------------------------------------------------
# service
# ---------------------------------------------------------------------

def _build_reporting_service(channel_id: str):
    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception:
        return None
    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return None
    try:
        return build("youtubereporting", "v1", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def _authorized_session(channel_id: str):
    """レポート本体（downloadUrl）を取りに行くための認証済みセッション。"""
    try:
        from google.auth.transport.requests import AuthorizedSession  # type: ignore
    except Exception:
        return None
    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return None
    try:
        return AuthorizedSession(creds)
    except Exception:
        return None


# ---------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------

def list_jobs(channel_id: str) -> Dict[str, Any]:
    svc = _build_reporting_service(channel_id)
    if not svc:
        return {"ok": False, "error": "OAuth 未連携または googleapiclient 未導入"}
    try:
        resp = svc.jobs().list().execute()
    except Exception as e:
        return {"ok": False, "error": f"jobs.list failed: {e}"}
    return {"ok": True, "jobs": resp.get("jobs", []) or []}


def ensure_job(channel_id: str, *, report_type_id: str = REPORT_TYPE_ID) -> Dict[str, Any]:
    """reach レポートのジョブが無ければ作る。既にあれば何もしない。

    ジョブを作った直後は当然まだレポートが無い（最大 48h 待ち）。
    created=True のときはその旨を呼び出し側に返す。
    """
    svc = _build_reporting_service(channel_id)
    if not svc:
        return {"ok": False, "error": "OAuth 未連携または googleapiclient 未導入"}
    try:
        existing = svc.jobs().list().execute().get("jobs", []) or []
    except Exception as e:
        return {"ok": False, "error": f"jobs.list failed: {e}"}

    for j in existing:
        if j.get("reportTypeId") == report_type_id:
            return {
                "ok": True,
                "created": False,
                "job_id": j.get("id"),
                "create_time": j.get("createTime"),
            }

    try:
        job = svc.jobs().create(
            body={"reportTypeId": report_type_id, "name": JOB_NAME}
        ).execute()
    except Exception as e:
        return {"ok": False, "error": f"jobs.create failed: {e}"}

    return {
        "ok": True,
        "created": True,
        "job_id": job.get("id"),
        "create_time": job.get("createTime"),
        "note": "初回レポート生成まで最大48時間。作成時点で過去30日分がバックフィルされる。",
    }


def _reach_job_id(svc, report_type_id: str = REPORT_TYPE_ID) -> Optional[str]:
    try:
        jobs = svc.jobs().list().execute().get("jobs", []) or []
    except Exception:
        return None
    for j in jobs:
        if j.get("reportTypeId") == report_type_id:
            return j.get("id")
    return None


# ---------------------------------------------------------------------
# report ingest
# ---------------------------------------------------------------------

def _normalize_date(raw: str) -> Optional[str]:
    """Reporting API の日付は YYYYMMDD。ISO(YYYY-MM-DD) に揃える。"""
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    return None


def _normalize_ctr(raw: Any) -> float:
    """CTR を 0..1 に正規化する。

    video_metrics.ctr は 0..1 で持つ規約。レポート側が百分率（4.2 = 4.2%）で
    返してくる場合に備えて、1 を超える値は百分率とみなして 100 で割る。
    率として 1.0 を超えることは定義上ありえないので、この判定は安全。
    """
    try:
        v = float(raw or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if v <= 0:
        return 0.0
    return v / 100.0 if v > 1.0 else v


def _parse_report_csv(text: str, channel_id: str) -> List[Dict[str, Any]]:
    """CSV を [{video_id, date, impressions, clicks}] に変換する。"""
    out: List[Dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        vid = (row.get(COL_VIDEO) or "").strip()
        d = _normalize_date(row.get(COL_DATE) or "")
        if not vid or not d:
            continue
        try:
            impressions = int(float(row.get(COL_IMPRESSIONS) or 0))
        except (TypeError, ValueError):
            impressions = 0
        ctr = _normalize_ctr(row.get(COL_CTR))
        out.append({
            "video_id": vid,
            "channel_id": channel_id,
            "date": d,
            "impressions": impressions,
            "clicks": impressions * ctr,
        })
    return out


def _http_status(exc: Exception) -> Optional[int]:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _list_reports(
    svc, job_id: str, created_after: str
) -> Dict[str, Any]:
    """ジョブのレポート一覧を全ページ取得する。

    一時障害（500/503/429）は指数バックオフで再試行する。ここで諦めると
    そのチャンネルはその日のレポートを1件も取り込まないまま「取得0件」に
    なり、翌日以降も createdAfter の窓から落ちれば永久に欠落する。
    """
    reports: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while True:
        last_err: Optional[Exception] = None
        resp: Optional[Dict[str, Any]] = None
        for attempt in range(LIST_MAX_ATTEMPTS):
            try:
                resp = (
                    svc.jobs()
                    .reports()
                    .list(jobId=job_id, createdAfter=created_after, pageToken=page_token)
                    .execute()
                )
                last_err = None
                break
            except Exception as e:  # noqa: BLE001 — 再試行可否は status で判定
                last_err = e
                status = _http_status(e)
                if status is not None and status not in RETRYABLE_STATUS:
                    break
                if attempt < LIST_MAX_ATTEMPTS - 1:
                    time.sleep(LIST_BACKOFF_SEC * (2 ** attempt))
        if last_err is not None or resp is None:
            return {"ok": False, "error": f"reports.list failed: {last_err}"}
        reports.extend(resp.get("reports", []) or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return {"ok": True, "reports": reports}


def ingest_reports(
    channel_id: str,
    *,
    days: int = 30,
    max_reports: int = 200,
    ensure: bool = True,
) -> Dict[str, Any]:
    """未取り込みの reach レポートを DL して video_reach_daily に流し込む。

    ensure=True ならジョブが無いときに作る。ジョブ作成時点で過去30日分が
    バックフィルされるので、作り忘れたチャンネルはここで自動的に復旧する。
    """
    svc = _build_reporting_service(channel_id)
    if not svc:
        return {"ok": False, "error": "OAuth 未連携または googleapiclient 未導入"}
    job_id = _reach_job_id(svc)
    job_created = False
    if not job_id and ensure:
        created = ensure_job(channel_id)
        if created.get("ok"):
            job_id = created.get("job_id")
            job_created = bool(created.get("created"))
    if not job_id:
        return {
            "ok": False,
            "error": "reach レポートジョブが未作成",
            "hint": "ensure_job(channel_id) を先に実行する",
        }

    created_after = (
        datetime.now(timezone.utc) - timedelta(days=days + 2)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    listed = _list_reports(svc, job_id, created_after)
    if not listed.get("ok"):
        return {"ok": False, "error": listed.get("error"), "job_id": job_id}
    reports: List[Dict[str, Any]] = listed.get("reports") or []

    if not reports:
        return {
            "ok": True,
            "job_id": job_id,
            "job_created": job_created,
            "reports_found": 0,
            "reports_ingested": 0,
            "rows": 0,
            "note": "レポートがまだ1件も生成されていない（ジョブ作成から最大48時間かかる）",
        }

    session = _authorized_session(channel_id)
    if not session:
        return {"ok": False, "error": "認証済みセッションを作れない", "job_id": job_id}

    # 同じ日を含むレポートが再発行されることがある。新しいものが後勝ちに
    # なるよう createTime 昇順で処理する。
    reports.sort(key=lambda r: r.get("createTime") or "")

    ingested = 0
    total_rows = 0
    errors: List[str] = []
    for rep in reports:
        # max_reports は「1回で新規取り込みする上限」。取り込み済みを数えて
        # しまうと、既存が上限に達した時点で新しいレポートに永久に届かない。
        if ingested >= max_reports:
            break
        rid = rep.get("id")
        url = rep.get("downloadUrl")
        if not rid or not url:
            continue
        if analytics_store.is_report_ingested(rid):
            continue
        try:
            r = session.get(url)
            r.raise_for_status()
            text = r.text
        except Exception as e:
            errors.append(f"{rid}: download failed: {e}")
            continue

        try:
            rows = _parse_report_csv(text, channel_id)
        except Exception as e:
            errors.append(f"{rid}: parse failed: {e}")
            continue

        for row in rows:
            analytics_store.upsert_video_reach_daily(**row)
        analytics_store.mark_report_ingested(
            report_id=rid,
            channel_id=channel_id,
            job_id=job_id,
            start_time=rep.get("startTime"),
            end_time=rep.get("endTime"),
            rows_ingested=len(rows),
        )
        ingested += 1
        total_rows += len(rows)
        time.sleep(0.05)

    latest_start = max((r.get("startTime") or "" for r in reports), default="")
    return {
        "ok": True,
        "job_id": job_id,
        "job_created": job_created,
        "reports_found": len(reports),
        "reports_ingested": ingested,
        "reports_pending": sum(
            1 for r in reports
            if r.get("id") and not analytics_store.is_report_ingested(r["id"])
        ),
        "latest_report_start": latest_start,
        "rows": total_rows,
        "errors": errors,
    }


# ---------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------

def writeback_reach(
    channel_id: str,
    *,
    days: int = 30,
    snapshot_date: Optional[str] = None,
) -> Dict[str, Any]:
    """日次テーブルを期間集計して video_metrics.impressions/ctr を更新する。

    video_metrics は「snapshot_date 時点で直近 days 日の値」という規約なので、
    reach 側も同じ窓で合算する。update_video_metric_reach は既存行しか
    更新しないので、**必ず fetch_video_metrics がその日の行を作った後**に
    呼ぶこと。先に呼ぶと毎回 metrics_updated=0 / no_snapshot_row=N になる。
    """
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    snap = snapshot_date or end.isoformat()

    agg = analytics_store.aggregate_video_reach(
        channel_id, start_date=start.isoformat(), end_date=end.isoformat()
    )

    updated = 0
    missing_row = 0
    for vid, v in agg.items():
        ok = analytics_store.update_video_metric_reach(
            video_id=vid,
            date=snap,
            impressions=int(v["impressions"]),
            ctr=float(v["ctr"]),
        )
        if ok:
            updated += 1
        else:
            missing_row += 1

    return {
        "channel_id": channel_id,
        "ok": True,
        "videos_with_reach": len(agg),
        "metrics_updated": updated,
        "no_snapshot_row": missing_row,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "snapshot_date": snap,
    }


def sync_reach(
    channel_id: str,
    *,
    days: int = 30,
    snapshot_date: Optional[str] = None,
) -> Dict[str, Any]:
    """レポート取り込み → 期間集計 → video_metrics.impressions/ctr を更新。"""
    ing = ingest_reports(channel_id, days=days)
    if not ing.get("ok"):
        return {"channel_id": channel_id, "ok": False, "ingest": ing}

    back = writeback_reach(channel_id, days=days, snapshot_date=snapshot_date)
    return {**back, "ok": True, "ingest": ing}


def sync_reach_all(
    channel_ids: Optional[List[str]] = None,
    *,
    days: int = 30,
    writeback: bool = False,
) -> Dict[str, Any]:
    """全チャンネルのレポートを取り込む。

    なぜ独立した入口が要るか:
        取り込みは `sync_channel` の中でしか走っておらず、その `sync_channel`
        は PDCA が `video_format.analytics.enabled=true` のチャンネルにしか
        投げない。結果、ジョブは作ってあるのにレポートを1件も取り込んで
        いないチャンネル（akashic-librarian / clip-lab / company-facts）が
        できていた。レポートは createdAfter の窓から落ちると二度と取れない
        ので、取り込みだけは analytics.enabled と切り離して全チャンネル回す。

    writeback=False（既定）は日次テーブルに貯めるだけ。video_metrics への
    反映は sync_channel が fetch_video_metrics の後段でやる。
    """
    if channel_ids is None:
        channel_ids = _all_channel_ids()

    results: Dict[str, Any] = {}
    total_rows = 0
    for cid in channel_ids:
        try:
            res = ingest_reports(cid, days=days)
        except Exception as e:  # noqa: BLE001 — 1chの失敗で全体を止めない
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        if res.get("ok") and writeback:
            res["writeback"] = writeback_reach(cid, days=days)
        total_rows += int(res.get("rows") or 0)
        results[cid] = res

    return {
        "ok": True,
        "channels": len(channel_ids),
        "rows": total_rows,
        "results": results,
    }


def _all_channel_ids() -> List[str]:
    from pathlib import Path

    d = Path(__file__).resolve().parent.parent.parent / "data" / "channels"
    try:
        return sorted(p.stem for p in d.glob("*.json"))
    except Exception:
        return []
