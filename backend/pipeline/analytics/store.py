"""
Analytics データストア — YouTube Analytics メトリクスとコメント分析を SQLite に保存。

DB: data/analytics/analytics.db

テーブル:
  - video_metrics: 動画ごとの直近スナップショット（同 video_id + date は UPSERT）
  - retention_curve: video_id ごとの視聴維持率カーブ（最新のみ保持）
  - comment_analysis: コメント本体 + GPT-4o の感情/トピック分析

シンプルさを優先。集計や時系列が必要になったら後で正規化する。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "analytics" / "analytics.db"

_db_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db_lock:
        c = _conn()
        try:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS video_metrics (
                    video_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    date TEXT NOT NULL,             -- ISO YYYY-MM-DD (snapshot date)
                    title TEXT,
                    published_at TEXT,
                    views INTEGER NOT NULL DEFAULT 0,
                    watch_time_minutes REAL NOT NULL DEFAULT 0,
                    avg_view_duration REAL NOT NULL DEFAULT 0,
                    avg_view_percentage REAL NOT NULL DEFAULT 0,
                    impressions INTEGER NOT NULL DEFAULT 0,
                    ctr REAL NOT NULL DEFAULT 0,    -- 0..1
                    likes INTEGER NOT NULL DEFAULT 0,
                    comments INTEGER NOT NULL DEFAULT 0,
                    shares INTEGER NOT NULL DEFAULT 0,
                    subscribers_gained INTEGER NOT NULL DEFAULT 0,
                    fetched_at INTEGER NOT NULL,
                    PRIMARY KEY (video_id, date)
                );
                CREATE INDEX IF NOT EXISTS idx_metrics_channel
                    ON video_metrics(channel_id, date DESC);

                CREATE TABLE IF NOT EXISTS retention_curve (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    curve TEXT NOT NULL,            -- JSON: [{ratio, audience_watch_ratio, relative_retention}]
                    fetched_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS channel_metrics (
                    channel_id TEXT NOT NULL,
                    date TEXT NOT NULL,             -- ISO YYYY-MM-DD
                    views INTEGER NOT NULL DEFAULT 0,
                    watch_time_minutes REAL NOT NULL DEFAULT 0,
                    subscribers_gained INTEGER NOT NULL DEFAULT 0,
                    subscribers_lost INTEGER NOT NULL DEFAULT 0,
                    fetched_at INTEGER NOT NULL,
                    PRIMARY KEY (channel_id, date)
                );

                CREATE TABLE IF NOT EXISTS comment_analysis (
                    comment_id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    channel_id TEXT,
                    author TEXT,
                    text TEXT NOT NULL,
                    like_count INTEGER NOT NULL DEFAULT 0,
                    published_at TEXT,
                    sentiment TEXT,                 -- positive | negative | request | neutral
                    topics TEXT,                    -- JSON array
                    is_request INTEGER NOT NULL DEFAULT 0,
                    analyzed_at INTEGER,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_comments_video
                    ON comment_analysis(video_id, published_at DESC);

                -- Phase D: scenario evaluation (A2/A3)
                CREATE TABLE IF NOT EXISTS scenario_evaluations (
                    video_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    evaluated_at INTEGER NOT NULL,
                    hook_strength REAL NOT NULL DEFAULT 0,
                    specificity REAL NOT NULL DEFAULT 0,
                    pacing REAL NOT NULL DEFAULT 0,
                    cta_effectiveness REAL NOT NULL DEFAULT 0,
                    wording_quality REAL NOT NULL DEFAULT 0,
                    overall REAL NOT NULL DEFAULT 0,
                    weak_sections TEXT,             -- JSON array
                    improvement_suggestions TEXT,    -- JSON array
                    comment_feedback TEXT,           -- JSON array
                    scenario_path TEXT,
                    video_title TEXT,
                    PRIMARY KEY (video_id)
                );
                CREATE INDEX IF NOT EXISTS idx_eval_channel
                    ON scenario_evaluations(channel_id, evaluated_at DESC);

                -- Phase D: AB test reconciliation (B)
                CREATE TABLE IF NOT EXISTS ab_test_reconciliation (
                    test_id TEXT NOT NULL,
                    variant_index INTEGER NOT NULL,
                    channel_id TEXT,
                    video_id TEXT,
                    pattern_type TEXT,
                    predicted_score REAL,
                    actual_ctr REAL,
                    actual_impressions INTEGER,
                    actual_views INTEGER,
                    reconciled_at INTEGER NOT NULL,
                    PRIMARY KEY (test_id, variant_index)
                );
                CREATE INDEX IF NOT EXISTS idx_ab_reco_channel
                    ON ab_test_reconciliation(channel_id, reconciled_at DESC);

                -- Phase D: improvement queue (C)
                CREATE TABLE IF NOT EXISTS improvement_queue (
                    video_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', -- pending | applied | dismissed
                    current_title TEXT,
                    current_ctr REAL,
                    channel_avg_ctr REAL,
                    suggested_titles TEXT,       -- JSON array
                    suggested_catchcopies TEXT,  -- JSON array of {pattern, title, thumb_copy, score}
                    predicted_improvement REAL,  -- % delta vs current
                    PRIMARY KEY (video_id)
                );
                CREATE INDEX IF NOT EXISTS idx_imp_queue_channel
                    ON improvement_queue(channel_id, status, updated_at DESC);
                """
            )
            c.commit()
        finally:
            c.close()


init_db()


# ---------------------------------------------------------------------
# Video metrics
# ---------------------------------------------------------------------

def upsert_video_metric(
    *,
    video_id: str,
    channel_id: str,
    date: str,
    title: Optional[str] = None,
    published_at: Optional[str] = None,
    views: int = 0,
    watch_time_minutes: float = 0.0,
    avg_view_duration: float = 0.0,
    avg_view_percentage: float = 0.0,
    impressions: int = 0,
    ctr: float = 0.0,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    subscribers_gained: int = 0,
) -> None:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            c.execute(
                """
                INSERT OR REPLACE INTO video_metrics
                (video_id, channel_id, date, title, published_at, views,
                 watch_time_minutes, avg_view_duration, avg_view_percentage,
                 impressions, ctr, likes, comments, shares, subscribers_gained,
                 fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id, channel_id, date, title, published_at, int(views),
                    float(watch_time_minutes), float(avg_view_duration),
                    float(avg_view_percentage), int(impressions), float(ctr),
                    int(likes), int(comments), int(shares),
                    int(subscribers_gained), now,
                ),
            )
            c.commit()
        finally:
            c.close()


def list_video_metrics(
    channel_id: str,
    *,
    limit: int = 100,
    latest_per_video: bool = True,
) -> List[Dict[str, Any]]:
    """チャンネルの動画別メトリクスを返す。latest_per_video=True なら
    各 video_id の最新スナップショット1件のみ。"""
    with _db_lock:
        c = _conn()
        try:
            if latest_per_video:
                rows = c.execute(
                    """
                    SELECT m.* FROM video_metrics m
                    INNER JOIN (
                        SELECT video_id, MAX(date) AS max_date
                        FROM video_metrics WHERE channel_id = ?
                        GROUP BY video_id
                    ) latest
                    ON m.video_id = latest.video_id AND m.date = latest.max_date
                    WHERE m.channel_id = ?
                    ORDER BY m.published_at DESC NULLS LAST, m.views DESC
                    LIMIT ?
                    """,
                    (channel_id, channel_id, int(limit)),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM video_metrics WHERE channel_id = ? "
                    "ORDER BY date DESC, views DESC LIMIT ?",
                    (channel_id, int(limit)),
                ).fetchall()
        finally:
            c.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------

def save_retention(video_id: str, channel_id: str, curve: List[Dict[str, float]]) -> None:
    payload = json.dumps(curve, ensure_ascii=False)
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            c.execute(
                "INSERT OR REPLACE INTO retention_curve "
                "(video_id, channel_id, curve, fetched_at) VALUES (?, ?, ?, ?)",
                (video_id, channel_id, payload, now),
            )
            c.commit()
        finally:
            c.close()


def get_retention(video_id: str) -> Optional[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM retention_curve WHERE video_id = ?", (video_id,)
            ).fetchone()
        finally:
            c.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["curve"] = json.loads(d["curve"])
    except Exception:
        d["curve"] = []
    return d


# ---------------------------------------------------------------------
# Channel metrics
# ---------------------------------------------------------------------

def upsert_channel_metric(
    *,
    channel_id: str,
    date: str,
    views: int = 0,
    watch_time_minutes: float = 0.0,
    subscribers_gained: int = 0,
    subscribers_lost: int = 0,
) -> None:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            c.execute(
                """
                INSERT OR REPLACE INTO channel_metrics
                (channel_id, date, views, watch_time_minutes,
                 subscribers_gained, subscribers_lost, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel_id, date, int(views), float(watch_time_minutes),
                    int(subscribers_gained), int(subscribers_lost), now,
                ),
            )
            c.commit()
        finally:
            c.close()


def list_channel_metrics(channel_id: str, *, days: int = 30) -> List[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT * FROM channel_metrics WHERE channel_id = ? "
                "ORDER BY date DESC LIMIT ?",
                (channel_id, int(days)),
            ).fetchall()
        finally:
            c.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------

def upsert_comment(
    *,
    comment_id: str,
    video_id: str,
    text: str,
    channel_id: Optional[str] = None,
    author: Optional[str] = None,
    like_count: int = 0,
    published_at: Optional[str] = None,
    sentiment: Optional[str] = None,
    topics: Optional[List[str]] = None,
    is_request: bool = False,
    analyzed: bool = False,
) -> None:
    now = int(time.time())
    topics_json = json.dumps(topics or [], ensure_ascii=False)
    analyzed_at = now if analyzed else None
    with _db_lock:
        c = _conn()
        try:
            existing = c.execute(
                "SELECT created_at FROM comment_analysis WHERE comment_id = ?",
                (comment_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            c.execute(
                """
                INSERT OR REPLACE INTO comment_analysis
                (comment_id, video_id, channel_id, author, text, like_count,
                 published_at, sentiment, topics, is_request, analyzed_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comment_id, video_id, channel_id, author, text, int(like_count),
                    published_at, sentiment, topics_json,
                    1 if is_request else 0, analyzed_at, created_at,
                ),
            )
            c.commit()
        finally:
            c.close()


def list_comments_for_video(
    video_id: str,
    *,
    limit: int = 200,
    analyzed_only: bool = False,
) -> List[Dict[str, Any]]:
    where = ["video_id = ?"]
    args: List[Any] = [video_id]
    if analyzed_only:
        where.append("analyzed_at IS NOT NULL")
    sql = (
        "SELECT * FROM comment_analysis WHERE "
        + " AND ".join(where)
        + " ORDER BY published_at DESC NULLS LAST LIMIT ?"
    )
    args.append(int(limit))
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(sql, args).fetchall()
        finally:
            c.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["topics"] = json.loads(d.get("topics") or "[]")
        except Exception:
            d["topics"] = []
        d["is_request"] = bool(d.get("is_request"))
        out.append(d)
    return out


def comment_summary_for_video(video_id: str) -> Dict[str, Any]:
    """video_id 単位の集計（感情分布・トピック頻度・リクエスト件数）。"""
    items = list_comments_for_video(video_id, limit=1000, analyzed_only=True)
    sentiment_count: Dict[str, int] = {}
    topic_count: Dict[str, int] = {}
    requests: List[Dict[str, Any]] = []
    for it in items:
        s = it.get("sentiment") or "neutral"
        sentiment_count[s] = sentiment_count.get(s, 0) + 1
        for t in it.get("topics") or []:
            topic_count[t] = topic_count.get(t, 0) + 1
        if it.get("is_request"):
            requests.append(
                {
                    "comment_id": it["comment_id"],
                    "text": it["text"],
                    "topics": it.get("topics") or [],
                }
            )
    top_topics = sorted(
        topic_count.items(), key=lambda kv: kv[1], reverse=True
    )[:20]
    return {
        "video_id": video_id,
        "total": len(items),
        "sentiment": sentiment_count,
        "top_topics": [{"topic": k, "count": v} for k, v in top_topics],
        "requests": requests[:50],
    }


# ---------------------------------------------------------------------
# Scenario evaluations (Phase D — A2/A3)
# ---------------------------------------------------------------------

# These CREATE TABLE statements run on import too — for existing DBs that
# pre-date the bigger schema string above, ensure the new tables exist.
def _ensure_phase_d_tables() -> None:
    with _db_lock:
        c = _conn()
        try:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS scenario_evaluations (
                    video_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    evaluated_at INTEGER NOT NULL,
                    hook_strength REAL NOT NULL DEFAULT 0,
                    specificity REAL NOT NULL DEFAULT 0,
                    pacing REAL NOT NULL DEFAULT 0,
                    cta_effectiveness REAL NOT NULL DEFAULT 0,
                    wording_quality REAL NOT NULL DEFAULT 0,
                    overall REAL NOT NULL DEFAULT 0,
                    weak_sections TEXT,
                    improvement_suggestions TEXT,
                    comment_feedback TEXT,
                    scenario_path TEXT,
                    video_title TEXT,
                    PRIMARY KEY (video_id)
                );
                CREATE INDEX IF NOT EXISTS idx_eval_channel
                    ON scenario_evaluations(channel_id, evaluated_at DESC);

                CREATE TABLE IF NOT EXISTS ab_test_reconciliation (
                    test_id TEXT NOT NULL,
                    variant_index INTEGER NOT NULL,
                    channel_id TEXT,
                    video_id TEXT,
                    pattern_type TEXT,
                    predicted_score REAL,
                    actual_ctr REAL,
                    actual_impressions INTEGER,
                    actual_views INTEGER,
                    reconciled_at INTEGER NOT NULL,
                    PRIMARY KEY (test_id, variant_index)
                );
                CREATE INDEX IF NOT EXISTS idx_ab_reco_channel
                    ON ab_test_reconciliation(channel_id, reconciled_at DESC);

                CREATE TABLE IF NOT EXISTS improvement_queue (
                    video_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    current_title TEXT,
                    current_ctr REAL,
                    channel_avg_ctr REAL,
                    suggested_titles TEXT,
                    suggested_catchcopies TEXT,
                    predicted_improvement REAL,
                    PRIMARY KEY (video_id)
                );
                CREATE INDEX IF NOT EXISTS idx_imp_queue_channel
                    ON improvement_queue(channel_id, status, updated_at DESC);
                """
            )
            c.commit()
        finally:
            c.close()


_ensure_phase_d_tables()


def upsert_scenario_evaluation(
    *,
    video_id: str,
    channel_id: str,
    hook_strength: float,
    specificity: float,
    pacing: float,
    cta_effectiveness: float,
    wording_quality: float,
    overall: float,
    weak_sections: Optional[List[Dict[str, Any]]] = None,
    improvement_suggestions: Optional[List[Any]] = None,
    comment_feedback: Optional[List[Any]] = None,
    scenario_path: Optional[str] = None,
    video_title: Optional[str] = None,
) -> Dict[str, Any]:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            c.execute(
                """
                INSERT OR REPLACE INTO scenario_evaluations
                (video_id, channel_id, evaluated_at, hook_strength, specificity,
                 pacing, cta_effectiveness, wording_quality, overall,
                 weak_sections, improvement_suggestions, comment_feedback,
                 scenario_path, video_title)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id, channel_id, now,
                    float(hook_strength), float(specificity), float(pacing),
                    float(cta_effectiveness), float(wording_quality), float(overall),
                    json.dumps(weak_sections or [], ensure_ascii=False),
                    json.dumps(improvement_suggestions or [], ensure_ascii=False),
                    json.dumps(comment_feedback or [], ensure_ascii=False),
                    scenario_path, video_title,
                ),
            )
            c.commit()
            row = c.execute(
                "SELECT * FROM scenario_evaluations WHERE video_id = ?",
                (video_id,),
            ).fetchone()
        finally:
            c.close()
    return _scenario_eval_row_to_dict(row) if row else {}


def _scenario_eval_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for k in ("weak_sections", "improvement_suggestions", "comment_feedback"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except Exception:
            d[k] = []
    return d


def list_scenario_evaluations(channel_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT * FROM scenario_evaluations WHERE channel_id = ? "
                "ORDER BY evaluated_at DESC LIMIT ?",
                (channel_id, int(limit)),
            ).fetchall()
        finally:
            c.close()
    return [_scenario_eval_row_to_dict(r) for r in rows]


def get_scenario_evaluation(video_id: str) -> Optional[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM scenario_evaluations WHERE video_id = ?",
                (video_id,),
            ).fetchone()
        finally:
            c.close()
    return _scenario_eval_row_to_dict(row) if row else None


# ---------------------------------------------------------------------
# AB test reconciliation (Phase D — B)
# ---------------------------------------------------------------------

def upsert_ab_reconciliation(
    *,
    test_id: str,
    variant_index: int,
    channel_id: Optional[str],
    video_id: Optional[str],
    pattern_type: Optional[str],
    predicted_score: Optional[float],
    actual_ctr: Optional[float],
    actual_impressions: Optional[int],
    actual_views: Optional[int],
) -> Dict[str, Any]:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            c.execute(
                """
                INSERT OR REPLACE INTO ab_test_reconciliation
                (test_id, variant_index, channel_id, video_id, pattern_type,
                 predicted_score, actual_ctr, actual_impressions, actual_views,
                 reconciled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_id, int(variant_index), channel_id, video_id, pattern_type,
                    float(predicted_score) if predicted_score is not None else None,
                    float(actual_ctr) if actual_ctr is not None else None,
                    int(actual_impressions) if actual_impressions is not None else None,
                    int(actual_views) if actual_views is not None else None,
                    now,
                ),
            )
            c.commit()
            row = c.execute(
                "SELECT * FROM ab_test_reconciliation WHERE test_id = ? AND variant_index = ?",
                (test_id, int(variant_index)),
            ).fetchone()
        finally:
            c.close()
    return dict(row) if row else {}


def list_ab_reconciliations(channel_id: Optional[str] = None, *, limit: int = 200) -> List[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            if channel_id:
                rows = c.execute(
                    "SELECT * FROM ab_test_reconciliation WHERE channel_id = ? "
                    "ORDER BY reconciled_at DESC LIMIT ?",
                    (channel_id, int(limit)),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM ab_test_reconciliation "
                    "ORDER BY reconciled_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        finally:
            c.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------
# Improvement queue (Phase D — C)
# ---------------------------------------------------------------------

def upsert_improvement_entry(
    *,
    video_id: str,
    channel_id: str,
    current_title: Optional[str],
    current_ctr: Optional[float],
    channel_avg_ctr: Optional[float],
    suggested_titles: Optional[List[Any]] = None,
    suggested_catchcopies: Optional[List[Any]] = None,
    predicted_improvement: Optional[float] = None,
    status: str = "pending",
) -> Dict[str, Any]:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            existing = c.execute(
                "SELECT created_at FROM improvement_queue WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            c.execute(
                """
                INSERT OR REPLACE INTO improvement_queue
                (video_id, channel_id, created_at, updated_at, status,
                 current_title, current_ctr, channel_avg_ctr,
                 suggested_titles, suggested_catchcopies, predicted_improvement)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id, channel_id, created_at, now, status,
                    current_title,
                    float(current_ctr) if current_ctr is not None else None,
                    float(channel_avg_ctr) if channel_avg_ctr is not None else None,
                    json.dumps(suggested_titles or [], ensure_ascii=False),
                    json.dumps(suggested_catchcopies or [], ensure_ascii=False),
                    float(predicted_improvement) if predicted_improvement is not None else None,
                ),
            )
            c.commit()
            row = c.execute(
                "SELECT * FROM improvement_queue WHERE video_id = ?",
                (video_id,),
            ).fetchone()
        finally:
            c.close()
    return _improvement_row_to_dict(row) if row else {}


def _improvement_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for k in ("suggested_titles", "suggested_catchcopies"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except Exception:
            d[k] = []
    return d


def list_improvement_entries(
    channel_id: str,
    *,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    where = ["channel_id = ?"]
    args: List[Any] = [channel_id]
    if status:
        where.append("status = ?")
        args.append(status)
    sql = (
        "SELECT * FROM improvement_queue WHERE "
        + " AND ".join(where)
        + " ORDER BY updated_at DESC LIMIT ?"
    )
    args.append(int(limit))
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(sql, args).fetchall()
        finally:
            c.close()
    return [_improvement_row_to_dict(r) for r in rows]


def update_improvement_status(video_id: str, status: str) -> bool:
    if status not in ("pending", "applied", "dismissed"):
        raise ValueError(f"invalid status: {status}")
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                "UPDATE improvement_queue SET status = ?, updated_at = ? WHERE video_id = ?",
                (status, now, video_id),
            )
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()
