"""
サムネイル AB テスト自動化 — 投稿後 CTR を監視し低ければ次の候補に自動差し替え。

ライフサイクル:
  1. register_test(...) — 動画投稿直後にオリジナルサムネ + 2 バリエーションを登録
  2. APScheduler が 1h ごとに `check_pending(...)` を呼ぶ
  3. 投稿から 48h 経過した動画 → YouTube Analytics で CTR を取得
  4. CTR < チャンネル平均 × 0.8 なら次の候補にサムネを差し替え (`thumbnails().set`)
  5. 差し替え後さらに 48h 監視 → 改善しなければ 3 つ目、それでもダメなら exhausted
  6. 差し替え履歴と都度の CTR を DB に保存

データソース:
  - 動画別 CTR: `video_metrics.ctr`（既存 sync で更新済み）
  - YouTube サムネ差し替え: `youtube.thumbnails().set(...)`
  - 候補生成: `thumbnail_generator.generate_thumbnail` を feedback 違いで 2 回呼ぶ
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "analytics" / "analytics.db"
THUMB_DIR = PROJECT_ROOT / "data" / "thumbnail_ab"


_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_table() -> None:
    with _lock:
        c = _conn()
        try:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS thumbnail_ab_tests (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    video_title TEXT,
                    variants_json TEXT NOT NULL,   -- list of {index, path, feedback, generated_at}
                    current_variant_index INTEGER NOT NULL DEFAULT 0,
                    channel_avg_ctr REAL DEFAULT 0,
                    threshold_ratio REAL NOT NULL DEFAULT 0.8,
                    last_check_ctr REAL,
                    last_checked_at INTEGER,
                    last_switched_at INTEGER,
                    status TEXT NOT NULL DEFAULT 'monitoring',  -- monitoring | exhausted | stopped
                    history_json TEXT NOT NULL DEFAULT '[]',    -- list of {variant_index, ctr_at_check, switched_at, channel_avg_at_check}
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    next_check_at INTEGER NOT NULL              -- unix sec when next CTR check is due
                );
                CREATE INDEX IF NOT EXISTS idx_thumb_ab_channel
                    ON thumbnail_ab_tests(channel_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_thumb_ab_due
                    ON thumbnail_ab_tests(status, next_check_at);
                """
            )
            c.commit()
        finally:
            c.close()


_init_table()


def _now() -> int:
    return int(time.time())


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["variants"] = json.loads(d.pop("variants_json") or "[]")
    except Exception:
        d["variants"] = []
    try:
        d["history"] = json.loads(d.pop("history_json") or "[]")
    except Exception:
        d["history"] = []
    return d


def list_tests(channel_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    with _lock:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT * FROM thumbnail_ab_tests WHERE channel_id = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (channel_id, int(limit)),
            ).fetchall()
        finally:
            c.close()
    return [_row_to_dict(r) for r in rows]


def get_test(video_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM thumbnail_ab_tests WHERE video_id = ?",
                (video_id,),
            ).fetchone()
        finally:
            c.close()
    return _row_to_dict(row) if row else None


# ---------------------------------------------------------------------
# 候補サムネ生成
# ---------------------------------------------------------------------

def _generate_variants(
    *,
    channel_id: str,
    video_id: str,
    title: str,
    original_path: Optional[str],
    count: int = 2,
) -> List[Dict[str, Any]]:
    """オリジナル + 2 バリエーションを返す。生成に失敗した分はスキップ。"""
    out: List[Dict[str, Any]] = []
    if original_path and Path(original_path).exists():
        out.append({
            "index": 0,
            "path": original_path,
            "feedback": "original",
            "generated_at": _now(),
        })
    else:
        out.append({
            "index": 0,
            "path": original_path or "",
            "feedback": "original",
            "generated_at": _now(),
        })

    # チャンネル設定を読む
    ch_path = PROJECT_ROOT / "data" / "channels" / f"{channel_id}.json"
    if not ch_path.exists():
        return out
    try:
        ch_cfg = json.loads(ch_path.read_text(encoding="utf-8"))
    except Exception:
        return out

    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    base_dir = THUMB_DIR / channel_id / video_id
    base_dir.mkdir(parents=True, exist_ok=True)

    feedback_variants = [
        ["より大胆なキャッチコピーで、感情訴求を強める"],
        ["疑問形・対比強化で、好奇心ギャップを最大化"],
    ]

    try:
        from pipeline.thumbnail_generator import generate_thumbnail  # type: ignore
    except Exception as e:
        print(f"⚠️ thumbnail_ab_test: generate_thumbnail import failed: {e}")
        return out

    for i in range(count):
        idx = i + 1
        feedback = feedback_variants[i % len(feedback_variants)]
        out_path = base_dir / f"variant_{idx}.png"
        try:
            generate_thumbnail(
                title=title,
                channel_config=ch_cfg,
                output_path=out_path,
                feedback=feedback,
            )
            out.append({
                "index": idx,
                "path": str(out_path),
                "feedback": feedback[0],
                "generated_at": _now(),
            })
        except Exception as e:
            print(f"⚠️ thumbnail_ab_test: variant {idx} generation failed for {video_id}: {e}")
            # placeholder で残しておく（手動再生成可能）
            out.append({
                "index": idx,
                "path": "",
                "feedback": feedback[0],
                "generated_at": _now(),
                "error": str(e),
            })

    return out


# ---------------------------------------------------------------------
# 登録 & 状態遷移
# ---------------------------------------------------------------------

CHECK_WINDOW_HOURS = 48
DEFAULT_THRESHOLD_RATIO = 0.8


def register_test(
    *,
    video_id: str,
    channel_id: str,
    video_title: str,
    original_thumbnail_path: Optional[str] = None,
    threshold_ratio: float = DEFAULT_THRESHOLD_RATIO,
    generate_variants: bool = True,
) -> Dict[str, Any]:
    """投稿直後に呼ぶ：オリジナル + 2 バリエーションを登録し、48h 後に CTR チェック予約。"""
    existing = get_test(video_id)
    if existing:
        return existing

    if generate_variants:
        variants = _generate_variants(
            channel_id=channel_id,
            video_id=video_id,
            title=video_title,
            original_path=original_thumbnail_path,
            count=2,
        )
    else:
        variants = [{
            "index": 0,
            "path": original_thumbnail_path or "",
            "feedback": "original",
            "generated_at": _now(),
        }]

    now = _now()
    next_check = now + CHECK_WINDOW_HOURS * 3600

    with _lock:
        c = _conn()
        try:
            c.execute(
                """
                INSERT INTO thumbnail_ab_tests
                (video_id, channel_id, video_title, variants_json,
                 current_variant_index, threshold_ratio,
                 status, history_json, created_at, updated_at, next_check_at)
                VALUES (?, ?, ?, ?, 0, ?, 'monitoring', '[]', ?, ?, ?)
                """,
                (
                    video_id, channel_id, video_title,
                    json.dumps(variants, ensure_ascii=False),
                    float(threshold_ratio),
                    now, now, next_check,
                ),
            )
            c.commit()
        finally:
            c.close()

    return get_test(video_id) or {}


def _update_row(video_id: str, fields: Dict[str, Any]) -> None:
    if not fields:
        return
    fields = dict(fields)
    fields["updated_at"] = _now()
    keys = ", ".join(f"{k} = ?" for k in fields.keys())
    args = list(fields.values()) + [video_id]
    with _lock:
        c = _conn()
        try:
            c.execute(
                f"UPDATE thumbnail_ab_tests SET {keys} WHERE video_id = ?",
                args,
            )
            c.commit()
        finally:
            c.close()


def _channel_avg_ctr(channel_id: str) -> float:
    """直近の動画の CTR 中央値〜平均を返す。 improvement_queue とロジックを揃える。"""
    with _lock:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT ctr FROM video_metrics WHERE channel_id = ? "
                "AND ctr IS NOT NULL ORDER BY date DESC LIMIT 50",
                (channel_id,),
            ).fetchall()
        finally:
            c.close()
    vals = [float(r["ctr"] or 0) for r in rows if r["ctr"] is not None and float(r["ctr"]) > 0]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _view_velocity(row: Any) -> Optional[float]:
    """1動画の「1日あたり再生数」を返す。published_at が無ければ None。

    サムネ impressions / CTR は YouTube Analytics API v2 では取得できない
    （metrics=impressions は "Unknown identifier" で 400。Studio と
    Reporting API のバルクレポートにしか無い）。そのため CTR を判定材料に
    できないケースでは、実際に効果として見たい「伸び方」を代理指標に使う。
    """
    try:
        views = float(row["views"] or 0)
    except Exception:
        return None
    pub = row["published_at"] if "published_at" in row.keys() else None
    if not pub:
        return None
    try:
        published = datetime.strptime(str(pub)[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except Exception:
        return None
    age_days = (datetime.now(timezone.utc) - published).total_seconds() / 86400.0
    if age_days < 0.5:
        return None  # 公開直後は分母が小さすぎて暴れる
    return views / age_days


def _latest_rows_per_video(channel_id: str, limit: int = 60) -> List[Any]:
    """チャンネルの動画ごとに最新スナップショットを1行ずつ返す。"""
    with _lock:
        c = _conn()
        try:
            return c.execute(
                "SELECT video_id, views, published_at, MAX(date) AS date "
                "FROM video_metrics WHERE channel_id = ? "
                "GROUP BY video_id ORDER BY date DESC LIMIT ?",
                (channel_id, limit),
            ).fetchall()
        finally:
            c.close()


def _channel_median_velocity(channel_id: str) -> float:
    """チャンネルの「1日あたり再生数」の中央値。平均だと1本のバズで歪む。

    判定対象側と同じ足切り（MIN_VIEWS_FOR_JUDGEMENT）を基準側にも掛ける。
    露出がほぼ無い動画を基準に混ぜると中央値が不当に下がり、
    実際は不調なサムネまで「基準を超えている」と判定されてしまう。
    """
    vals = []
    for row in _latest_rows_per_video(channel_id):
        try:
            if float(row["views"] or 0) < MIN_VIEWS_FOR_JUDGEMENT:
                continue
        except Exception:
            continue
        v = _view_velocity(row)
        if v is not None and v > 0:
            vals.append(v)
    if not vals:
        return 0.0
    vals.sort()
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


# 代理指標で「不調」と断じるのに最低限必要な再生数。
# これ未満は「サムネが悪い」のか「そもそも露出されていない / 同期が失敗している」のか
# 区別できない。区別できないまま切り替えると、公開中の動画のサムネを
# 根拠なく差し替えることになるので、判定を見送って no_data として扱う。
MIN_VIEWS_FOR_JUDGEMENT = 20


def _fetch_current_velocity(channel_id: str, video_id: str) -> Optional[float]:
    with _lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT video_id, views, published_at FROM video_metrics "
                "WHERE video_id = ? ORDER BY date DESC LIMIT 1",
                (video_id,),
            ).fetchone()
        finally:
            c.close()
    if not row:
        return None
    try:
        if float(row["views"] or 0) < MIN_VIEWS_FOR_JUDGEMENT:
            return None
    except Exception:
        return None
    return _view_velocity(row)


def _fetch_current_ctr(channel_id: str, video_id: str) -> Optional[float]:
    """直近スナップショットから video の CTR を取得。無ければ analytics sync を試す。"""
    with _lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT ctr FROM video_metrics WHERE video_id = ? "
                "ORDER BY date DESC LIMIT 1",
                (video_id,),
            ).fetchone()
        finally:
            c.close()
    if row and row["ctr"] is not None:
        try:
            return float(row["ctr"])
        except Exception:
            pass
    # CTR データが無ければ analytics API から最新を取得しに行く（best-effort）
    try:
        from pipeline import youtube_analytics as ya  # type: ignore
        ya.fetch_video_metrics(channel_id, video_ids=[video_id], days=30)
    except Exception:
        return None
    with _lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT ctr FROM video_metrics WHERE video_id = ? "
                "ORDER BY date DESC LIMIT 1",
                (video_id,),
            ).fetchone()
        finally:
            c.close()
    if row and row["ctr"] is not None:
        try:
            return float(row["ctr"])
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------
# YouTube サムネ差し替え
# ---------------------------------------------------------------------

def _set_youtube_thumbnail(channel_id: str, video_id: str, thumbnail_path: str) -> Dict[str, Any]:
    if not thumbnail_path or not Path(thumbnail_path).exists():
        return {"ok": False, "error": f"thumbnail_path not found: {thumbnail_path}"}
    try:
        from pipeline import youtube_oauth as yt_oauth  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.http import MediaFileUpload  # type: ignore
    except Exception as e:
        return {"ok": False, "error": f"google api libs not available: {e}"}

    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return {"ok": False, "error": "channel not OAuth-linked"}
    try:
        service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        service.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
        ).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------
# 切替ロジック
# ---------------------------------------------------------------------

def switch_to_next_variant(video_id: str, *, force: bool = False) -> Dict[str, Any]:
    """次のバリエーションに進める（手動 or 自動共通）。"""
    t = get_test(video_id)
    if not t:
        return {"ok": False, "error": "test not found"}
    if t.get("status") == "exhausted" and not force:
        return {"ok": False, "error": "all variants exhausted"}
    variants = t.get("variants") or []
    cur = int(t.get("current_variant_index") or 0)
    nxt = cur + 1
    if nxt >= len(variants):
        _update_row(video_id, {"status": "exhausted"})
        return {"ok": False, "error": "no further variants", "test": get_test(video_id)}
    next_variant = variants[nxt]
    path = next_variant.get("path") or ""
    upload = _set_youtube_thumbnail(t["channel_id"], video_id, path) if path else {"ok": False, "error": "variant has no path"}
    now = _now()
    history = t.get("history") or []
    history.append({
        "variant_index": cur,
        "ctr_at_check": t.get("last_check_ctr"),
        "channel_avg_at_check": t.get("channel_avg_ctr"),
        "switched_at": now,
        "switched_to": nxt,
        "youtube_update_ok": bool(upload.get("ok")),
        "youtube_update_error": upload.get("error"),
    })
    new_status = "monitoring"
    if nxt >= len(variants) - 1 and not force:
        # 最後のバリエーションに切替 — それでも改善しないと exhausted
        pass
    _update_row(video_id, {
        "current_variant_index": nxt,
        "last_switched_at": now,
        "history_json": json.dumps(history, ensure_ascii=False),
        "next_check_at": now + CHECK_WINDOW_HOURS * 3600,
        "status": new_status,
    })
    return {"ok": upload.get("ok", False), "switched_to": nxt, "upload": upload, "test": get_test(video_id)}


def check_one(video_id: str) -> Dict[str, Any]:
    """1 テストを評価し、必要なら切替。"""
    t = get_test(video_id)
    if not t:
        return {"ok": False, "error": "not found"}
    if t.get("status") != "monitoring":
        return {"ok": True, "noop": True, "status": t.get("status")}

    channel_id = t["channel_id"]
    threshold = float(t.get("threshold_ratio") or DEFAULT_THRESHOLD_RATIO)
    now = _now()

    # 第一候補は CTR。ただしサムネ impressions/CTR は YouTube Analytics API v2 に
    # 存在せず（metrics=impressions は 400 "Unknown identifier"）、実運用では
    # 常に 0 になる。CTR が取れないときは「1日あたり再生数」を代理指標にする。
    # これを入れるまで、全テストが no_data のまま無期限に monitoring に留まり、
    # 18 件が2か月以上ぶら下がったままだった。
    metric = "ctr"
    current = _fetch_current_ctr(channel_id, video_id)
    baseline = _channel_avg_ctr(channel_id)

    if current is None or current <= 0 or baseline <= 0:
        metric = "view_velocity"
        current = _fetch_current_velocity(channel_id, video_id)
        baseline = _channel_median_velocity(channel_id)

    _update_row(video_id, {
        "last_check_ctr": current if current is not None else 0.0,
        "channel_avg_ctr": baseline,
        "last_checked_at": now,
    })

    if current is None or baseline <= 0:
        # 判定材料が足りない → 24h 後に再チェック
        _update_row(video_id, {"next_check_at": now + 24 * 3600})
        return {
            "ok": True,
            "status": "no_data",
            "metric": metric,
            "next_check_at": now + 24 * 3600,
        }

    floor = baseline * threshold
    if current >= floor:
        # OK: 監視継続だが間隔は広げる（72h 後に再確認）
        _update_row(video_id, {
            "next_check_at": now + 72 * 3600,
            "status": "monitoring",
        })
        return {
            "ok": True,
            "status": "passing",
            "metric": metric,
            "current_ctr": current,
            "channel_avg_ctr": baseline,
            "threshold": floor,
        }

    # 不調 → 次バリエーションへ
    sw = switch_to_next_variant(video_id)
    return {
        "ok": sw.get("ok"),
        "status": "switched" if sw.get("ok") else "switch_failed",
        "metric": metric,
        "current_ctr": current,
        "channel_avg_ctr": baseline,
        "threshold": floor,
        "switch": sw,
    }


def check_pending(*, channel_id: Optional[str] = None) -> Dict[str, Any]:
    """期限超過の monitoring テストを一斉チェック。スケジューラから呼ぶ用。"""
    now = _now()
    with _lock:
        c = _conn()
        try:
            if channel_id:
                rows = c.execute(
                    "SELECT video_id FROM thumbnail_ab_tests "
                    "WHERE status = 'monitoring' AND next_check_at <= ? AND channel_id = ?",
                    (now, channel_id),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT video_id FROM thumbnail_ab_tests "
                    "WHERE status = 'monitoring' AND next_check_at <= ?",
                    (now,),
                ).fetchall()
        finally:
            c.close()

    results: List[Dict[str, Any]] = []
    for r in rows:
        vid = r["video_id"]
        try:
            res = check_one(vid)
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        results.append({"video_id": vid, **res})
    return {"checked": len(results), "results": results, "now": now}


# ---------------------------------------------------------------------
# 手動操作
# ---------------------------------------------------------------------

def force_switch(video_id: str) -> Dict[str, Any]:
    return switch_to_next_variant(video_id, force=True)


def stop_test(video_id: str) -> Dict[str, Any]:
    _update_row(video_id, {"status": "stopped"})
    return {"ok": True, "test": get_test(video_id)}


def restart_test(video_id: str) -> Dict[str, Any]:
    _update_row(video_id, {
        "status": "monitoring",
        "next_check_at": _now() + CHECK_WINDOW_HOURS * 3600,
    })
    return {"ok": True, "test": get_test(video_id)}


def summary(channel_id: str) -> Dict[str, Any]:
    items = list_tests(channel_id, limit=500)
    counts = {"monitoring": 0, "exhausted": 0, "stopped": 0}
    switched = 0
    for it in items:
        counts[it.get("status", "monitoring")] = counts.get(it.get("status", "monitoring"), 0) + 1
        if (it.get("history") or []):
            switched += 1
    return {
        "channel_id": channel_id,
        "total_tests": len(items),
        "by_status": counts,
        "switched_tests": switched,
        "channel_avg_ctr": _channel_avg_ctr(channel_id),
    }
