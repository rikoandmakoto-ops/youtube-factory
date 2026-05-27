"""
PDCA レポート生成 — ショート vs メイン動画のパフォーマンス比較。

YouTube Data API v3 で各動画の statistics + contentDetails を取得し、
duration <= 60s or タイトルに「ショート」/「#Shorts」を含む動画を short として分類。
api_usage.jsonl からチャンネル別の API コストを集計して、
ショート1本あたり / メイン1本あたりの推定コストを返す。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import store as analytics_store


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PUBLISH_DB = PROJECT_ROOT / "data" / "video_publish.db"
API_USAGE_FILE = PROJECT_ROOT / "data" / "api_usage.jsonl"


# ---------------------------------------------------------------------
# OAuth-backed YouTube Data API v3 service
# ---------------------------------------------------------------------

def _build_data_service(channel_id: str):
    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception:
        return None
    try:
        from pipeline import youtube_oauth as yt_oauth
    except Exception:
        return None
    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return None
    try:
        return build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def _build_analytics_service(channel_id: str):
    """YouTube Analytics API v2 サービス。subscribersGained を video ディメンション
    で取りたいときに使う。未連携 / 依存欠落で None。"""
    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception:
        return None
    try:
        from pipeline import youtube_oauth as yt_oauth
    except Exception:
        return None
    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return None
    try:
        return build(
            "youtubeAnalytics", "v2", credentials=creds, cache_discovery=False
        )
    except Exception:
        return None


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

_ISO_DURATION_RE = re.compile(
    r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$"
)


def _parse_iso_duration(value: str) -> float:
    """ISO 8601 duration (`PT1M30S`) → seconds. 解析できなければ 0.0。"""
    if not value:
        return 0.0
    m = _ISO_DURATION_RE.match(value.strip())
    if not m:
        return 0.0
    h = float(m.group(1) or 0)
    mn = float(m.group(2) or 0)
    s = float(m.group(3) or 0)
    return h * 3600 + mn * 60 + s


def _is_short(*, duration_seconds: float, title: str) -> bool:
    """short 判定: 60秒以下 OR タイトルに「ショート」/「#Shorts」を含む。"""
    if duration_seconds > 0 and duration_seconds <= 60:
        return True
    t = (title or "").lower()
    if "ショート" in (title or ""):
        return True
    if "#shorts" in t or " shorts " in t or t.endswith(" shorts"):
        return True
    return False


def _chunked(seq: List[str], n: int = 50):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _parse_iso_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ---------------------------------------------------------------------
# DB / file readers
# ---------------------------------------------------------------------

def _published_video_ids(channel_id: str) -> List[Dict[str, Any]]:
    """video_publish.db から「公開済み」相当の video_id を抜き出す。"""
    if not PUBLISH_DB.exists():
        return []
    conn = sqlite3.connect(str(PUBLISH_DB))
    try:
        rows = conn.execute(
            "SELECT job_id, video_id, status, published_at "
            "FROM video_status WHERE channel_id = ? AND video_id IS NOT NULL "
            "AND video_id != ''",
            (channel_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "job_id": r[0],
            "video_id": r[1],
            "status": r[2],
            "published_at": r[3],
        }
        for r in rows
    ]


def _aggregate_api_cost(
    channel_id: str, *, since: Optional[datetime]
) -> Dict[str, Any]:
    """api_usage.jsonl をストリームで読みつつ channel_id でフィルタして合計。"""
    total_cost = 0.0
    by_purpose: Dict[str, float] = {}
    by_model: Dict[str, float] = {}
    event_count = 0
    if not API_USAGE_FILE.exists():
        return {
            "total_cost_usd": 0.0,
            "events": 0,
            "by_purpose": {},
            "by_model": {},
        }
    cutoff = since
    with API_USAGE_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("channel_id") != channel_id:
                continue
            if cutoff is not None:
                ts = _parse_iso_dt(ev.get("ts") or "")
                if ts is None:
                    continue
                # api_usage の ts は local naive → 比較用に naive 同士で扱う
                cmp_cutoff = (
                    cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
                )
                cmp_ts = ts.replace(tzinfo=None) if ts.tzinfo else ts
                if cmp_ts < cmp_cutoff:
                    continue
            cost = float(ev.get("cost_usd") or 0.0)
            total_cost += cost
            purpose = ev.get("purpose") or "unknown"
            model = ev.get("model") or "unknown"
            by_purpose[purpose] = by_purpose.get(purpose, 0.0) + cost
            by_model[model] = by_model.get(model, 0.0) + cost
            event_count += 1
    return {
        "total_cost_usd": round(total_cost, 4),
        "events": event_count,
        "by_purpose": {k: round(v, 4) for k, v in by_purpose.items()},
        "by_model": {k: round(v, 4) for k, v in by_model.items()},
    }


# ---------------------------------------------------------------------
# YouTube Data API fetchers
# ---------------------------------------------------------------------

def _fetch_video_details(
    channel_id: str, video_ids: List[str]
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """videos.list(part=snippet,statistics,contentDetails)。最大50/req。"""
    svc = _build_data_service(channel_id)
    if not svc:
        return [], "youtube oauth 未連携 or googleapiclient 未導入"
    out: List[Dict[str, Any]] = []
    last_err: Optional[str] = None
    for batch in _chunked(video_ids, 50):
        try:
            resp = (
                svc.videos()
                .list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(batch),
                )
                .execute()
            )
        except Exception as e:
            last_err = f"videos.list failed: {e}"
            continue
        for item in resp.get("items", []):
            sn = item.get("snippet", {}) or {}
            st = item.get("statistics", {}) or {}
            cd = item.get("contentDetails", {}) or {}
            dur = _parse_iso_duration(cd.get("duration") or "")
            title = sn.get("title") or ""
            views = int(st.get("viewCount", 0) or 0)
            likes = int(st.get("likeCount", 0) or 0)
            comments = int(st.get("commentCount", 0) or 0)
            out.append(
                {
                    "video_id": item.get("id"),
                    "title": title,
                    "published_at": sn.get("publishedAt"),
                    "duration_seconds": dur,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "like_rate": (likes / views) if views > 0 else 0.0,
                    "is_short": _is_short(duration_seconds=dur, title=title),
                }
            )
    return out, last_err


def _fetch_channel_stats(channel_id: str) -> Dict[str, Any]:
    """channels.list(part=statistics, mine=True) で現在の subscriber/view を取得。"""
    svc = _build_data_service(channel_id)
    if not svc:
        return {}
    try:
        resp = (
            svc.channels()
            .list(part="snippet,statistics", mine=True)
            .execute()
        )
    except Exception as e:
        return {"error": f"channels.list failed: {e}"}
    items = resp.get("items", [])
    if not items:
        return {}
    it = items[0]
    sn = it.get("snippet", {}) or {}
    st = it.get("statistics", {}) or {}
    return {
        "youtube_channel_id": it.get("id"),
        "youtube_title": sn.get("title"),
        "subscriber_count": int(st.get("subscriberCount", 0) or 0),
        "view_count": int(st.get("viewCount", 0) or 0),
        "video_count": int(st.get("videoCount", 0) or 0),
        "subscriber_hidden": st.get("hiddenSubscriberCount", False),
    }


# ---------------------------------------------------------------------
# Subscriber source (YouTube Analytics API v2, dimensions=video)
# ---------------------------------------------------------------------

def _fetch_subscriber_sources_by_video(
    channel_id: str, *, start: date, end: date
) -> Tuple[Dict[str, Dict[str, int]], Optional[str]]:
    """各動画ごとの subscribersGained / subscribersLost を取得。

    Returns ({video_id: {"gained": int, "lost": int}}, error_message_or_None)。
    YouTube Analytics API は OAuth + yt-analytics.readonly スコープが必須。
    """
    analytics = _build_analytics_service(channel_id)
    if not analytics:
        return {}, "youtube analytics 未連携 or googleapiclient 未導入"
    try:
        resp = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                metrics="subscribersGained,subscribersLost",
                dimensions="video",
                sort="-subscribersGained",
                maxResults=200,
            )
            .execute()
        )
    except Exception as e:
        msg = str(e)
        # Google の長い HttpError ダンプから本質だけ抜く
        if "accessNotConfigured" in msg or "has not been used" in msg:
            return (
                {},
                "YouTube Analytics API がこの Google プロジェクトで未有効化です。"
                " Cloud Console でこのチャンネルの OAuth クライアントが属するプロジェクトに対して"
                " YouTube Analytics API を有効化してください。",
            )
        if "insufficientPermissions" in msg or "insufficient" in msg.lower():
            return (
                {},
                "OAuth スコープ不足。yt-analytics.readonly を含めて再連携してください。",
            )
        return {}, f"analytics.reports.query failed: {e}"

    headers = [h.get("name") for h in resp.get("columnHeaders", [])]
    idx = {h: i for i, h in enumerate(headers)}
    rows = resp.get("rows", []) or []
    out: Dict[str, Dict[str, int]] = {}
    for r in rows:
        vid = r[idx["video"]] if "video" in idx else None
        if not vid:
            continue
        gained = int(r[idx["subscribersGained"]] or 0) if "subscribersGained" in idx else 0
        lost = int(r[idx["subscribersLost"]] or 0) if "subscribersLost" in idx else 0
        out[vid] = {"gained": gained, "lost": lost}
    return out, None


def _bucket_subscriber_sources(
    videos: List[Dict[str, Any]],
    by_video: Dict[str, Dict[str, int]],
) -> Dict[str, Any]:
    """video_id → 登録獲得/解除 を short/main に振り分けて集計。

    videos は build_report が組んだ in_window リスト（is_short 付き）。
    by_video に出現するが videos に無い ID は "unknown" バケットへ。
    """
    short_g = 0
    short_l = 0
    main_g = 0
    main_l = 0
    unknown_g = 0
    unknown_l = 0
    short_views = 0
    main_views = 0
    classification = {v["video_id"]: v for v in videos}

    for vid, sub in by_video.items():
        g = int(sub.get("gained", 0) or 0)
        l = int(sub.get("lost", 0) or 0)
        v = classification.get(vid)
        if v is None:
            unknown_g += g
            unknown_l += l
            continue
        if v["is_short"]:
            short_g += g
            short_l += l
            short_views += int(v.get("views", 0) or 0)
        else:
            main_g += g
            main_l += l
            main_views += int(v.get("views", 0) or 0)

    total_g = short_g + main_g
    total_l = short_l + main_l

    def _pct(part: int, whole: int) -> float:
        if whole <= 0:
            return 0.0
        return round(part / whole, 4)

    def _per_1000(subs: int, views: int) -> float:
        if views <= 0:
            return 0.0
        return round(subs / views * 1000.0, 4)

    return {
        "total_gained": total_g,
        "total_lost": total_l,
        "total_net": total_g - total_l,
        "shorts": {
            "gained": short_g,
            "lost": short_l,
            "net": short_g - short_l,
            "share_of_gained": _pct(short_g, total_g),
            "subs_per_1000_views": _per_1000(short_g, short_views),
        },
        "main": {
            "gained": main_g,
            "lost": main_l,
            "net": main_g - main_l,
            "share_of_gained": _pct(main_g, total_g),
            "subs_per_1000_views": _per_1000(main_g, main_views),
        },
        "unknown": {
            "gained": unknown_g,
            "lost": unknown_l,
            "note": (
                "期間外/別チャンネル/取得失敗の動画分。share には含めない。"
                if (unknown_g or unknown_l)
                else None
            ),
        },
    }


# ---------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------

def _build_recommendation(
    *,
    shorts_summary: Dict[str, Any],
    mains_summary: Dict[str, Any],
    sub_sources: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """登録者獲得元を最重要指標として運用判断を返す。

    決定キー (`decision`):
      - keep_main: メインからの登録が支配的 → メイン頻度を落とすな
      - reduce_main_ok: ショートからの登録が支配的 → メイン頻度↓でコスト削減可
      - balanced: どちらもバランス良く貢献
      - more_data_needed: サンプル不足 or データ取得不可
    """
    warnings: List[str] = []
    metrics_used: Dict[str, Any] = {}

    if not sub_sources:
        return {
            "decision": "more_data_needed",
            "primary_subscriber_source": None,
            "headline": "登録者ソースが取得できないため判断保留",
            "reasoning": (
                "YouTube Analytics API から subscribersGained を取得できませんでした。"
                " OAuth 連携と yt-analytics.readonly スコープを確認してください。"
            ),
            "warnings": ["登録者ソースデータなし — 再生数ベースの判断は危険"],
            "metrics_used": {},
        }

    total_g = int(sub_sources.get("total_gained", 0) or 0)
    short_g = int(sub_sources.get("shorts", {}).get("gained", 0) or 0)
    main_g = int(sub_sources.get("main", {}).get("gained", 0) or 0)
    short_share = float(sub_sources.get("shorts", {}).get("share_of_gained", 0.0) or 0.0)
    main_share = float(sub_sources.get("main", {}).get("share_of_gained", 0.0) or 0.0)
    short_views = int(shorts_summary.get("total_views", 0) or 0)
    main_views = int(mains_summary.get("total_views", 0) or 0)
    total_views = short_views + main_views

    short_view_share = round(short_views / total_views, 4) if total_views else 0.0
    main_view_share = round(main_views / total_views, 4) if total_views else 0.0

    metrics_used = {
        "total_subs_gained": total_g,
        "short_subs_gained": short_g,
        "main_subs_gained": main_g,
        "short_subs_share": short_share,
        "main_subs_share": main_share,
        "short_view_share": short_view_share,
        "main_view_share": main_view_share,
        "short_subs_per_1000_views": float(
            sub_sources.get("shorts", {}).get("subs_per_1000_views", 0.0) or 0.0
        ),
        "main_subs_per_1000_views": float(
            sub_sources.get("main", {}).get("subs_per_1000_views", 0.0) or 0.0
        ),
    }

    if total_g < 5:
        warnings.append(
            f"期間内の登録獲得が {total_g} 人と少なく判断はノイズが大きい — もう少し期間を伸ばすか様子見"
        )
        return {
            "decision": "more_data_needed",
            "primary_subscriber_source": None,
            "headline": "サンプル不足 — もう少し様子見",
            "reasoning": (
                f"期間内の登録獲得が {total_g} 人で、ショート vs メインの優劣を統計的に判断するには"
                f" サンプルが不足しています。"
            ),
            "warnings": warnings,
            "metrics_used": metrics_used,
        }

    if shorts_summary["count"] == 0:
        primary = "main"
    elif mains_summary["count"] == 0:
        primary = "shorts"
    elif short_share >= 0.65:
        primary = "shorts"
    elif main_share >= 0.55:
        primary = "main"
    else:
        primary = "balanced"

    # 注意フラグ: 「ショートで再生回ってるけどメインから登録」パターンを最重要視
    short_views_dominate = short_view_share >= 0.7
    main_subs_dominate = main_share >= 0.55

    if short_views_dominate and main_subs_dominate:
        decision = "keep_main"
        headline = "⚠️ ショート再生数 ≠ 登録 — メインを絶対に減らさないこと"
        reasoning = (
            f"期間内の再生はショートが {int(short_view_share*100)}% を占めますが、"
            f"登録者獲得はメインが {int(main_share*100)}% です。"
            f" ショートは認知拡大・新規流入のフックとして機能していますが、"
            f"実際にチャンネル登録に変換しているのはメイン動画。"
            f" メイン頻度を落とすと登録者獲得経路を直接削ることになります。"
        )
        warnings.append(
            "再生数ベースで「メイン本数を減らす」と判断するのは危険 — 登録は別経路から来ている"
        )
    elif primary == "main":
        decision = "keep_main"
        headline = "メインが登録獲得の主力 — 頻度維持"
        reasoning = (
            f"登録者の {int(main_share*100)}% がメイン動画経由。"
            f" メイン頻度を維持・強化する方向で。"
        )
    elif primary == "shorts":
        if main_views > 0 and main_share >= 0.2:
            decision = "balanced"
            headline = "ショートが主力だがメインも一定貢献 — バランス維持"
            reasoning = (
                f"登録者の {int(short_share*100)}% がショート、{int(main_share*100)}% がメイン経由。"
                f" 主力はショートですが、メインの寄与もゼロではないので極端な削減は避ける。"
            )
        else:
            decision = "reduce_main_ok"
            headline = "ショートが圧倒的に登録元 — メイン頻度↓でコスト削減可"
            reasoning = (
                f"登録者の {int(short_share*100)}% がショート経由で、メインの寄与は {int(main_share*100)}%。"
                f" メイン1本あたり {mains_summary.get('avg_views', 0):.0f} 再生・"
                f"登録貢献も限定的なので、頻度を落としてコスト削減を検討できます。"
            )
            warnings.append(
                "メインの登録貢献が低いといってもブランド維持・SEO の側面はあるためゼロにするのは非推奨"
            )
    else:
        decision = "balanced"
        headline = "ショート/メイン双方が貢献 — 現状維持"
        reasoning = (
            f"登録者の {int(short_share*100)}% がショート、{int(main_share*100)}% がメイン経由で、"
            f" どちらも一定の寄与をしています。今の比率を維持。"
        )

    if total_views > 0 and short_view_share >= 0.5:
        short_eff = metrics_used["short_subs_per_1000_views"]
        main_eff = metrics_used["main_subs_per_1000_views"]
        if main_eff > 0 and short_eff > 0 and main_eff >= short_eff * 3:
            warnings.append(
                f"メインの登録効率 ({main_eff:.2f}/千再生) はショート ({short_eff:.2f}) の {main_eff/max(short_eff,1e-9):.1f} 倍"
                " — 再生効率より登録効率が圧倒的に高い"
            )

    return {
        "decision": decision,
        "primary_subscriber_source": primary,
        "headline": headline,
        "reasoning": reasoning,
        "warnings": warnings,
        "metrics_used": metrics_used,
    }


# ---------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------

def _zero_bucket() -> Dict[str, Any]:
    return {
        "count": 0,
        "total_views": 0,
        "total_likes": 0,
        "total_comments": 0,
        "avg_views": 0.0,
        "avg_likes": 0.0,
        "avg_comments": 0.0,
        "avg_like_rate": 0.0,
        "median_views": 0,
        "top_videos": [],
    }


def _summarize(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    bucket = _zero_bucket()
    if not videos:
        return bucket
    bucket["count"] = len(videos)
    bucket["total_views"] = sum(v["views"] for v in videos)
    bucket["total_likes"] = sum(v["likes"] for v in videos)
    bucket["total_comments"] = sum(v["comments"] for v in videos)
    bucket["avg_views"] = round(bucket["total_views"] / len(videos), 1)
    bucket["avg_likes"] = round(bucket["total_likes"] / len(videos), 1)
    bucket["avg_comments"] = round(bucket["total_comments"] / len(videos), 1)
    like_rates = [v["like_rate"] for v in videos if v["views"] > 0]
    bucket["avg_like_rate"] = (
        round(sum(like_rates) / len(like_rates), 4) if like_rates else 0.0
    )
    sorted_views = sorted(v["views"] for v in videos)
    n = len(sorted_views)
    if n % 2 == 1:
        bucket["median_views"] = sorted_views[n // 2]
    else:
        bucket["median_views"] = (sorted_views[n // 2 - 1] + sorted_views[n // 2]) // 2
    bucket["top_videos"] = sorted(videos, key=lambda v: v["views"], reverse=True)[:5]
    return bucket


def build_report(
    channel_id: str, *, days: int = 30
) -> Dict[str, Any]:
    """PDCA レポートを組み立てる。"""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)

    # 1. 公開済み video_id を DB から
    published = _published_video_ids(channel_id)
    all_ids = [p["video_id"] for p in published]

    # 2. YouTube Data API で詳細取得
    videos, fetch_err = _fetch_video_details(channel_id, all_ids)

    # 3. 期間でフィルタ（published_at >= cutoff）
    in_window: List[Dict[str, Any]] = []
    for v in videos:
        pub = _parse_iso_dt(v.get("published_at") or "")
        if pub is None:
            continue
        cmp_pub = pub.replace(tzinfo=None) if pub.tzinfo else pub
        if cmp_pub >= cutoff:
            in_window.append(v)

    shorts = [v for v in in_window if v["is_short"]]
    mains = [v for v in in_window if not v["is_short"]]

    shorts_summary = _summarize(shorts)
    mains_summary = _summarize(mains)

    # 4. チャンネル現在値
    channel_stats = _fetch_channel_stats(channel_id)

    # 5. サブ推移（SQLite キャッシュ）
    daily = analytics_store.list_channel_metrics(channel_id, days=days)
    daily_sorted = sorted(daily, key=lambda d: d.get("date", ""))
    subs_trend: List[Dict[str, Any]] = []
    running_net = 0
    for d in daily_sorted:
        gained = int(d.get("subscribers_gained", 0) or 0)
        lost = int(d.get("subscribers_lost", 0) or 0)
        running_net += gained - lost
        subs_trend.append(
            {
                "date": d.get("date"),
                "gained": gained,
                "lost": lost,
                "net": gained - lost,
                "cumulative_net": running_net,
            }
        )
    subs_summary = {
        "current_total": channel_stats.get("subscriber_count"),
        "gained_in_window": sum(s["gained"] for s in subs_trend),
        "lost_in_window": sum(s["lost"] for s in subs_trend),
        "net_in_window": running_net,
        "daily": subs_trend,
        "source": "analytics_cache (要 /api/analytics/sync)" if subs_trend else "none",
    }

    # 6. API コスト集計
    cost = _aggregate_api_cost(channel_id, since=cutoff)
    total_count = shorts_summary["count"] + mains_summary["count"]
    if total_count > 0:
        per_video = cost["total_cost_usd"] / total_count
    else:
        per_video = 0.0
    cost_summary = {
        **cost,
        "videos_in_window": total_count,
        "cost_per_video_usd": round(per_video, 4),
        "cost_per_short_usd": round(per_video, 4) if shorts_summary["count"] else 0.0,
        "cost_per_main_usd": round(per_video, 4) if mains_summary["count"] else 0.0,
        "note": (
            "ショート/メインは同一パイプライン由来で個別計上はないため、"
            "総コスト ÷ 期間内本数で均等按分しています。"
        ),
    }

    # 7. 比較メトリクス
    def _ratio(a: float, b: float) -> Optional[float]:
        if not b:
            return None
        return round(a / b, 3)

    comparison = {
        "avg_views_short_vs_main": _ratio(
            shorts_summary["avg_views"], mains_summary["avg_views"]
        ),
        "avg_likes_short_vs_main": _ratio(
            shorts_summary["avg_likes"], mains_summary["avg_likes"]
        ),
        "avg_like_rate_short_vs_main": _ratio(
            shorts_summary["avg_like_rate"], mains_summary["avg_like_rate"]
        ),
    }

    # 8. 登録者ソース分析 (YouTube Analytics API v2, dimensions=video)
    sub_by_video, sub_err = _fetch_subscriber_sources_by_video(
        channel_id, start=cutoff.date(), end=now.date()
    )
    if sub_by_video:
        subscriber_sources = _bucket_subscriber_sources(in_window, sub_by_video)
        subscriber_sources["source"] = "youtube_analytics_api"
        subscriber_sources["error"] = None
    else:
        subscriber_sources = {
            "total_gained": 0,
            "total_lost": 0,
            "total_net": 0,
            "shorts": {
                "gained": 0, "lost": 0, "net": 0,
                "share_of_gained": 0.0, "subs_per_1000_views": 0.0,
            },
            "main": {
                "gained": 0, "lost": 0, "net": 0,
                "share_of_gained": 0.0, "subs_per_1000_views": 0.0,
            },
            "unknown": {"gained": 0, "lost": 0, "note": None},
            "source": "none",
            "error": sub_err,
        }

    # 9. 判断ロジック (登録者ソースを最優先)
    recommendation = _build_recommendation(
        shorts_summary=shorts_summary,
        mains_summary=mains_summary,
        sub_sources=subscriber_sources if sub_by_video else None,
    )

    return {
        "channel_id": channel_id,
        "days": days,
        "generated_at": now.isoformat() + "Z",
        "window": {
            "start": cutoff.isoformat() + "Z",
            "end": now.isoformat() + "Z",
        },
        "channel_stats": channel_stats,
        "subscribers": subs_summary,
        "subscriber_sources": subscriber_sources,
        "recommendation": recommendation,
        "shorts": shorts_summary,
        "main": mains_summary,
        "comparison": comparison,
        "cost": cost_summary,
        "totals": {
            "published_in_db": len(all_ids),
            "fetched_from_youtube": len(videos),
            "in_window": len(in_window),
        },
        "errors": {
            "youtube_fetch": fetch_err,
            "subscriber_sources": sub_err,
        },
    }
