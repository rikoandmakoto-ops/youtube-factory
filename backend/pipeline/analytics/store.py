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
