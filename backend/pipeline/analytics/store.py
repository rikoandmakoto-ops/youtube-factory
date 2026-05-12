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

                -- Phase E: Trend detections (Google Trends / News / etc.)
                CREATE TABLE IF NOT EXISTS trend_detections (
                    id TEXT PRIMARY KEY,           -- short hex id
                    channel_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    source TEXT NOT NULL,          -- google_trends | news_api | youtube_trending
                    trend_score REAL NOT NULL DEFAULT 0,     -- 0..1 source-supplied or rank-derived
                    relevance_score REAL NOT NULL DEFAULT 0, -- 0..1 channel fit (Claude judged)
                    combined_score REAL NOT NULL DEFAULT 0,  -- weighted (trend * relevance)
                    suggested_title TEXT,
                    suggested_angle TEXT,
                    rationale TEXT,                -- why this fits the channel
                    raw TEXT,                      -- JSON: original payload
                    detected_at INTEGER NOT NULL,
                    queued_at INTEGER,             -- timestamp when added to theme_queue
                    auto_queued INTEGER NOT NULL DEFAULT 0,  -- 1 if auto-injected
                    queue_theme_id TEXT,
                    status TEXT NOT NULL DEFAULT 'detected' -- detected | queued | dismissed
                );
                CREATE INDEX IF NOT EXISTS idx_trend_detections_channel
                    ON trend_detections(channel_id, detected_at DESC);
                CREATE INDEX IF NOT EXISTS idx_trend_detections_status
                    ON trend_detections(channel_id, status, combined_score DESC);

                -- Phase E: Trend scan history
                CREATE TABLE IF NOT EXISTS trend_scan_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    started_at INTEGER NOT NULL,
                    finished_at INTEGER,
                    sources TEXT,                  -- JSON
                    detected INTEGER NOT NULL DEFAULT 0,
                    auto_queued INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_trend_scan_history_channel
                    ON trend_scan_history(channel_id, started_at DESC);

                -- Phase E: Series suggestions (continuations of viral videos)
                CREATE TABLE IF NOT EXISTS series_suggestions (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    original_video_id TEXT NOT NULL,
                    original_title TEXT,
                    original_views INTEGER NOT NULL DEFAULT 0,
                    channel_avg_views INTEGER NOT NULL DEFAULT 0,
                    viral_ratio REAL NOT NULL DEFAULT 1.0,   -- views / avg
                    series_type TEXT,              -- deep_dive | contrast | application
                    suggested_title TEXT NOT NULL,
                    suggested_angle TEXT,
                    rationale TEXT,
                    created_at INTEGER NOT NULL,
                    decided_at INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
                    queue_theme_id TEXT,
                    queued_video_id TEXT           -- set when the spinoff is actually published
                );
                CREATE INDEX IF NOT EXISTS idx_series_channel
                    ON series_suggestions(channel_id, status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_series_original
                    ON series_suggestions(channel_id, original_video_id);
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

                -- AI-model compete: one row per generated candidate (both gpt + claude
                -- are recorded for each dual-gen run). selected=1 marks the one that
                -- proceeded to production. video_id is filled at archive/match time.
                CREATE TABLE IF NOT EXISTS model_scenario_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,            -- gpt | claude
                    run_id TEXT NOT NULL,                -- groups gpt+claude from same dual-gen
                    title TEXT,                          -- candidate title (slug-match against video later)
                    selected INTEGER NOT NULL DEFAULT 0, -- 1 if this candidate was chosen
                    selected_by TEXT,                    -- blind_eval | performance | only_one (filled on winner)
                    won_blind_eval INTEGER NOT NULL DEFAULT 0, -- 1 if blind compare ranked this side as A>B/B>A winner
                    blind_overall REAL,                  -- this candidate's overall score from blind eval
                    blind_scores TEXT,                   -- JSON: 6 axes per candidate
                    video_id TEXT,                       -- filled later when matched to a published video
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_model_records_channel
                    ON model_scenario_records(channel_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_model_records_run
                    ON model_scenario_records(run_id);
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


# ---------------------------------------------------------------------
# Model compete (gpt vs claude scenario competition)
# ---------------------------------------------------------------------


def insert_model_scenario_record(
    *,
    channel_id: str,
    model_name: str,
    run_id: str,
    title: Optional[str],
    selected: bool,
    selected_by: Optional[str],
    won_blind_eval: bool,
    blind_overall: Optional[float],
    blind_scores: Optional[Dict[str, Any]],
) -> int:
    """1 候補分のレコードを書き込む。同じ run_id で gpt/claude 双方分を挿入する想定。"""
    now = int(time.time())
    payload_scores = json.dumps(blind_scores or {}, ensure_ascii=False)
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                """
                INSERT INTO model_scenario_records
                (channel_id, model_name, run_id, title, selected, selected_by,
                 won_blind_eval, blind_overall, blind_scores, video_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    channel_id, model_name, run_id, title,
                    1 if selected else 0, selected_by,
                    1 if won_blind_eval else 0,
                    float(blind_overall) if blind_overall is not None else None,
                    payload_scores,
                    now,
                ),
            )
            c.commit()
            return int(cur.lastrowid or 0)
        finally:
            c.close()


def list_model_scenario_records(
    channel_id: str,
    *,
    limit: int = 500,
    selected_only: bool = False,
) -> List[Dict[str, Any]]:
    where = ["channel_id = ?"]
    args: List[Any] = [channel_id]
    if selected_only:
        where.append("selected = 1")
    sql = (
        "SELECT * FROM model_scenario_records WHERE "
        + " AND ".join(where)
        + " ORDER BY created_at DESC LIMIT ?"
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
            d["blind_scores"] = json.loads(d.get("blind_scores") or "{}")
        except Exception:
            d["blind_scores"] = {}
        d["selected"] = bool(d.get("selected"))
        d["won_blind_eval"] = bool(d.get("won_blind_eval"))
        out.append(d)
    return out


def update_model_record_video_id(record_id: int, video_id: str) -> bool:
    """生成後に動画と紐づいたタイミングで video_id を埋める。"""
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                "UPDATE model_scenario_records SET video_id = ? WHERE id = ?",
                (video_id, int(record_id)),
            )
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()


def link_model_record_by_title(channel_id: str, title: str, video_id: str) -> int:
    """selected かつ video_id 未設定の最新 1 レコードを title 完全一致で video_id 紐づけ。"""
    if not title or not video_id:
        return 0
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                """
                UPDATE model_scenario_records
                SET video_id = ?
                WHERE id = (
                    SELECT id FROM model_scenario_records
                    WHERE channel_id = ? AND title = ? AND selected = 1
                          AND video_id IS NULL
                    ORDER BY created_at DESC LIMIT 1
                )
                """,
                (video_id, channel_id, title),
            )
            c.commit()
            return cur.rowcount
        finally:
            c.close()


# ---------------------------------------------------------------------
# Phase E: Trend detections
# ---------------------------------------------------------------------

def upsert_trend_detection(
    *,
    detection_id: str,
    channel_id: str,
    keyword: str,
    source: str,
    trend_score: float,
    relevance_score: float,
    combined_score: float,
    suggested_title: Optional[str],
    suggested_angle: Optional[str],
    rationale: Optional[str],
    raw: Optional[Dict[str, Any]] = None,
    auto_queued: bool = False,
    status: str = "detected",
    queue_theme_id: Optional[str] = None,
) -> None:
    now = int(time.time())
    raw_json = json.dumps(raw or {}, ensure_ascii=False)
    with _db_lock:
        c = _conn()
        try:
            existing = c.execute(
                "SELECT detected_at FROM trend_detections WHERE id = ?",
                (detection_id,),
            ).fetchone()
            detected_at = existing["detected_at"] if existing else now
            queued_at = now if auto_queued else None
            c.execute(
                """
                INSERT OR REPLACE INTO trend_detections
                (id, channel_id, keyword, source, trend_score, relevance_score,
                 combined_score, suggested_title, suggested_angle, rationale,
                 raw, detected_at, queued_at, auto_queued, queue_theme_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    detection_id, channel_id, keyword, source,
                    float(trend_score), float(relevance_score),
                    float(combined_score), suggested_title, suggested_angle,
                    rationale, raw_json, detected_at, queued_at,
                    1 if auto_queued else 0, queue_theme_id, status,
                ),
            )
            c.commit()
        finally:
            c.close()


def find_recent_trend_by_keyword(
    channel_id: str, keyword: str, *, within_seconds: int = 7 * 24 * 3600
) -> Optional[Dict[str, Any]]:
    """同チャンネルで同じキーワードの直近検出を返す（重複検出回避用）。"""
    threshold = int(time.time()) - int(within_seconds)
    with _db_lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM trend_detections WHERE channel_id = ? "
                "AND keyword = ? AND detected_at >= ? "
                "ORDER BY detected_at DESC LIMIT 1",
                (channel_id, keyword, threshold),
            ).fetchone()
        finally:
            c.close()
    return dict(row) if row else None


def list_trend_detections(
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
        "SELECT * FROM trend_detections WHERE "
        + " AND ".join(where)
        + " ORDER BY combined_score DESC, detected_at DESC LIMIT ?"
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
            d["raw"] = json.loads(d.get("raw") or "{}")
        except Exception:
            d["raw"] = {}
        d["auto_queued"] = bool(d.get("auto_queued"))
        out.append(d)
    return out


def get_trend_detection(detection_id: str) -> Optional[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM trend_detections WHERE id = ?", (detection_id,)
            ).fetchone()
        finally:
            c.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["raw"] = json.loads(d.get("raw") or "{}")
    except Exception:
        d["raw"] = {}
    d["auto_queued"] = bool(d.get("auto_queued"))
    return d


def update_trend_status(
    detection_id: str,
    status: str,
    *,
    queue_theme_id: Optional[str] = None,
    queued: bool = False,
) -> bool:
    now = int(time.time())
    fields = ["status = ?"]
    args: List[Any] = [status]
    if queue_theme_id is not None:
        fields.append("queue_theme_id = ?")
        args.append(queue_theme_id)
    if queued:
        fields.append("queued_at = ?")
        args.append(now)
    args.append(detection_id)
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                f"UPDATE trend_detections SET {', '.join(fields)} WHERE id = ?",
                args,
            )
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()


def insert_trend_scan_history(
    channel_id: str,
    *,
    sources: List[str],
    detected: int,
    auto_queued: int,
    error: Optional[str] = None,
    started_at: Optional[int] = None,
) -> int:
    now = int(time.time())
    started_at = int(started_at or now)
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                """
                INSERT INTO trend_scan_history
                (channel_id, started_at, finished_at, sources, detected,
                 auto_queued, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel_id, started_at, now,
                    json.dumps(sources, ensure_ascii=False),
                    int(detected), int(auto_queued), error,
                ),
            )
            c.commit()
            return cur.lastrowid
        finally:
            c.close()


def list_trend_scan_history(channel_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT * FROM trend_scan_history WHERE channel_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (channel_id, int(limit)),
            ).fetchall()
        finally:
            c.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["sources"] = json.loads(d.get("sources") or "[]")
        except Exception:
            d["sources"] = []
        out.append(d)
    return out


# ---------------------------------------------------------------------
# Phase E: Series suggestions
# ---------------------------------------------------------------------

def upsert_series_suggestion(
    *,
    suggestion_id: str,
    channel_id: str,
    original_video_id: str,
    original_title: Optional[str],
    original_views: int,
    channel_avg_views: int,
    viral_ratio: float,
    series_type: Optional[str],
    suggested_title: str,
    suggested_angle: Optional[str],
    rationale: Optional[str],
    status: str = "pending",
) -> None:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            existing = c.execute(
                "SELECT created_at FROM series_suggestions WHERE id = ?",
                (suggestion_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            c.execute(
                """
                INSERT OR REPLACE INTO series_suggestions
                (id, channel_id, original_video_id, original_title,
                 original_views, channel_avg_views, viral_ratio,
                 series_type, suggested_title, suggested_angle, rationale,
                 created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion_id, channel_id, original_video_id, original_title,
                    int(original_views), int(channel_avg_views),
                    float(viral_ratio), series_type, suggested_title,
                    suggested_angle, rationale, created_at, status,
                ),
            )
            c.commit()
        finally:
            c.close()


def list_series_suggestions(
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
        "SELECT * FROM series_suggestions WHERE "
        + " AND ".join(where)
        + " ORDER BY created_at DESC, viral_ratio DESC LIMIT ?"
    )
    args.append(int(limit))
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(sql, args).fetchall()
        finally:
            c.close()
    return [dict(r) for r in rows]


def get_series_suggestion(suggestion_id: str) -> Optional[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM series_suggestions WHERE id = ?", (suggestion_id,)
            ).fetchone()
        finally:
            c.close()
    return dict(row) if row else None


def list_series_for_original(
    channel_id: str, original_video_id: str
) -> List[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT * FROM series_suggestions WHERE channel_id = ? "
                "AND original_video_id = ? ORDER BY created_at DESC",
                (channel_id, original_video_id),
            ).fetchall()
        finally:
            c.close()
    return [dict(r) for r in rows]


def update_series_status(
    suggestion_id: str,
    status: str,
    *,
    queue_theme_id: Optional[str] = None,
    queued_video_id: Optional[str] = None,
) -> bool:
    now = int(time.time())
    fields = ["status = ?", "decided_at = ?"]
    args: List[Any] = [status, now]
    if queue_theme_id is not None:
        fields.append("queue_theme_id = ?")
        args.append(queue_theme_id)
    if queued_video_id is not None:
        fields.append("queued_video_id = ?")
        args.append(queued_video_id)
    args.append(suggestion_id)
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                f"UPDATE series_suggestions SET {', '.join(fields)} WHERE id = ?",
                args,
            )
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()


# ---------------------------------------------------------------------
# Phase F-1: Competitor analyses
# ---------------------------------------------------------------------

def _ensure_phase_f_tables() -> None:
    with _db_lock:
        c = _conn()
        try:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS competitor_analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    competitor_id TEXT NOT NULL,        -- YouTube channel ID (UC...)
                    competitor_title TEXT,
                    subscriber_count INTEGER,
                    video_count INTEGER,
                    view_count INTEGER,
                    analysis_date TEXT NOT NULL,        -- YYYY-MM-DD
                    insights_json TEXT,                 -- Claude analysis output
                    top_videos_json TEXT,               -- raw video samples
                    posting_frequency_per_week REAL,
                    avg_views INTEGER,
                    fetched_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_competitor_analyses_channel
                    ON competitor_analyses(channel_id, analysis_date DESC);
                CREATE INDEX IF NOT EXISTS idx_competitor_analyses_competitor
                    ON competitor_analyses(channel_id, competitor_id, analysis_date DESC);

                CREATE TABLE IF NOT EXISTS comment_demands (
                    id TEXT PRIMARY KEY,                -- short hex id
                    channel_id TEXT NOT NULL,
                    video_id TEXT,                      -- source video (optional, aggregation may span videos)
                    comment_ids TEXT,                   -- JSON array of source comment_ids
                    demand_text TEXT NOT NULL,          -- canonical phrasing of the demand
                    demand_type TEXT NOT NULL,          -- request | question
                    frequency INTEGER NOT NULL DEFAULT 1,
                    total_likes INTEGER NOT NULL DEFAULT 0,
                    relevance_score REAL NOT NULL DEFAULT 0,  -- 0..1 channel fit
                    score REAL NOT NULL DEFAULT 0,            -- combined frequency*likes*relevance
                    suggested_title TEXT,
                    suggested_angle TEXT,
                    rationale TEXT,
                    status TEXT NOT NULL DEFAULT 'pending', -- pending | queued | dismissed | auto_queued
                    queue_theme_id TEXT,
                    auto_queued INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_comment_demands_channel
                    ON comment_demands(channel_id, status, score DESC);
                CREATE INDEX IF NOT EXISTS idx_comment_demands_text
                    ON comment_demands(channel_id, demand_text);
                """
            )
            c.commit()
        finally:
            c.close()


_ensure_phase_f_tables()


def insert_competitor_analysis(
    *,
    channel_id: str,
    competitor_id: str,
    competitor_title: Optional[str],
    subscriber_count: Optional[int],
    video_count: Optional[int],
    view_count: Optional[int],
    analysis_date: str,
    insights: Optional[Dict[str, Any]],
    top_videos: Optional[List[Dict[str, Any]]],
    posting_frequency_per_week: Optional[float],
    avg_views: Optional[int],
) -> int:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                """
                INSERT INTO competitor_analyses
                (channel_id, competitor_id, competitor_title, subscriber_count,
                 video_count, view_count, analysis_date, insights_json,
                 top_videos_json, posting_frequency_per_week, avg_views, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel_id, competitor_id, competitor_title,
                    int(subscriber_count) if subscriber_count is not None else None,
                    int(video_count) if video_count is not None else None,
                    int(view_count) if view_count is not None else None,
                    analysis_date,
                    json.dumps(insights or {}, ensure_ascii=False),
                    json.dumps(top_videos or [], ensure_ascii=False),
                    float(posting_frequency_per_week) if posting_frequency_per_week is not None else None,
                    int(avg_views) if avg_views is not None else None,
                    now,
                ),
            )
            c.commit()
            return int(cur.lastrowid or 0)
        finally:
            c.close()


def _competitor_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["insights_json"] = json.loads(d.get("insights_json") or "{}")
    except Exception:
        d["insights_json"] = {}
    try:
        d["top_videos_json"] = json.loads(d.get("top_videos_json") or "[]")
    except Exception:
        d["top_videos_json"] = []
    return d


def list_competitor_analyses(
    channel_id: str,
    *,
    competitor_id: Optional[str] = None,
    latest_per_competitor: bool = True,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            if competitor_id:
                rows = c.execute(
                    "SELECT * FROM competitor_analyses WHERE channel_id = ? "
                    "AND competitor_id = ? ORDER BY analysis_date DESC, fetched_at DESC LIMIT ?",
                    (channel_id, competitor_id, int(limit)),
                ).fetchall()
            elif latest_per_competitor:
                rows = c.execute(
                    """
                    SELECT ca.* FROM competitor_analyses ca
                    INNER JOIN (
                        SELECT competitor_id, MAX(fetched_at) AS max_fetched
                        FROM competitor_analyses WHERE channel_id = ?
                        GROUP BY competitor_id
                    ) latest
                    ON ca.competitor_id = latest.competitor_id AND ca.fetched_at = latest.max_fetched
                    WHERE ca.channel_id = ?
                    ORDER BY ca.fetched_at DESC
                    LIMIT ?
                    """,
                    (channel_id, channel_id, int(limit)),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM competitor_analyses WHERE channel_id = ? "
                    "ORDER BY fetched_at DESC LIMIT ?",
                    (channel_id, int(limit)),
                ).fetchall()
        finally:
            c.close()
    return [_competitor_row_to_dict(r) for r in rows]


def delete_competitor_analyses(channel_id: str, competitor_id: str) -> int:
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                "DELETE FROM competitor_analyses WHERE channel_id = ? AND competitor_id = ?",
                (channel_id, competitor_id),
            )
            c.commit()
            return cur.rowcount
        finally:
            c.close()


# ---------------------------------------------------------------------
# Phase F-2: Comment demands
# ---------------------------------------------------------------------

def upsert_comment_demand(
    *,
    demand_id: str,
    channel_id: str,
    video_id: Optional[str],
    comment_ids: Optional[List[str]],
    demand_text: str,
    demand_type: str,
    frequency: int,
    total_likes: int,
    relevance_score: float,
    score: float,
    suggested_title: Optional[str] = None,
    suggested_angle: Optional[str] = None,
    rationale: Optional[str] = None,
    status: str = "pending",
    queue_theme_id: Optional[str] = None,
    auto_queued: bool = False,
) -> None:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            existing = c.execute(
                "SELECT created_at FROM comment_demands WHERE id = ?",
                (demand_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            c.execute(
                """
                INSERT OR REPLACE INTO comment_demands
                (id, channel_id, video_id, comment_ids, demand_text, demand_type,
                 frequency, total_likes, relevance_score, score, suggested_title,
                 suggested_angle, rationale, status, queue_theme_id, auto_queued,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    demand_id, channel_id, video_id,
                    json.dumps(comment_ids or [], ensure_ascii=False),
                    demand_text, demand_type,
                    int(frequency), int(total_likes),
                    float(relevance_score), float(score),
                    suggested_title, suggested_angle, rationale,
                    status, queue_theme_id, 1 if auto_queued else 0,
                    created_at, now,
                ),
            )
            c.commit()
        finally:
            c.close()


def find_existing_demand(channel_id: str, demand_text: str) -> Optional[Dict[str, Any]]:
    """既に登録されている同義リクエストを返す（status != dismissed）。"""
    with _db_lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM comment_demands WHERE channel_id = ? AND demand_text = ? "
                "AND status != 'dismissed' ORDER BY updated_at DESC LIMIT 1",
                (channel_id, demand_text),
            ).fetchone()
        finally:
            c.close()
    return _demand_row_to_dict(row) if row else None


def _demand_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["comment_ids"] = json.loads(d.get("comment_ids") or "[]")
    except Exception:
        d["comment_ids"] = []
    d["auto_queued"] = bool(d.get("auto_queued"))
    return d


def list_comment_demands(
    channel_id: str,
    *,
    status: Optional[str] = None,
    demand_type: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    where = ["channel_id = ?"]
    args: List[Any] = [channel_id]
    if status:
        where.append("status = ?")
        args.append(status)
    if demand_type:
        where.append("demand_type = ?")
        args.append(demand_type)
    sql = (
        "SELECT * FROM comment_demands WHERE "
        + " AND ".join(where)
        + " ORDER BY score DESC, updated_at DESC LIMIT ?"
    )
    args.append(int(limit))
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(sql, args).fetchall()
        finally:
            c.close()
    return [_demand_row_to_dict(r) for r in rows]


def get_comment_demand(demand_id: str) -> Optional[Dict[str, Any]]:
    with _db_lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM comment_demands WHERE id = ?", (demand_id,)
            ).fetchone()
        finally:
            c.close()
    return _demand_row_to_dict(row) if row else None


def update_comment_demand_status(
    demand_id: str,
    status: str,
    *,
    queue_theme_id: Optional[str] = None,
) -> bool:
    now = int(time.time())
    fields = ["status = ?", "updated_at = ?"]
    args: List[Any] = [status, now]
    if queue_theme_id is not None:
        fields.append("queue_theme_id = ?")
        args.append(queue_theme_id)
    args.append(demand_id)
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                f"UPDATE comment_demands SET {', '.join(fields)} WHERE id = ?",
                args,
            )
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()


def list_request_comments(
    channel_id: str,
    *,
    since_ts: Optional[int] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """is_request=1 のコメントを返す（comment_demand の入力に使う）。"""
    where = ["channel_id = ?", "(is_request = 1 OR sentiment = 'request')"]
    args: List[Any] = [channel_id]
    if since_ts is not None:
        where.append("created_at >= ?")
        args.append(int(since_ts))
    sql = (
        "SELECT * FROM comment_analysis WHERE "
        + " AND ".join(where)
        + " ORDER BY like_count DESC, published_at DESC LIMIT ?"
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
        out.append(d)
    return out
