"""
改善フィードバック ストア — いいね率が閾値を下回った動画への次回改善提案を保存。

DB: data/improvement_feedback.db
- video_feedback: 動画ごとのフィードバック1行（video_id を主キーに UPSERT）
- improvement_settings: チャンネル別 / グローバル設定（閾値、最小視聴数など）

フィードバックの「suggestions」は構造化された改善案（タイトル/サムネ/構成）。
ScenarioGenerator が次回シナリオ生成時にこれを参照してプロンプトに織り込む。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "improvement_feedback.db"

_db_lock = threading.Lock()


# 既定の改善ループ閾値（％）。channel.video_format.analytics.performance_threshold で
# `min_like_rate` を指定すれば override される。
DEFAULT_LIKE_RATE_THRESHOLD_PERCENT = 3.0
DEFAULT_MIN_VIEWS = 100  # この再生数未満はサンプル不足扱い


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
                CREATE TABLE IF NOT EXISTS video_feedback (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    job_id TEXT,
                    video_title TEXT,
                    views INTEGER NOT NULL DEFAULT 0,
                    likes INTEGER NOT NULL DEFAULT 0,
                    like_rate REAL NOT NULL DEFAULT 0,
                    threshold REAL NOT NULL,
                    suggestions TEXT NOT NULL,            -- JSON
                    is_consumed INTEGER NOT NULL DEFAULT 0,
                    consumed_by_job_id TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    consumed_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_channel
                    ON video_feedback(channel_id, is_consumed);

                CREATE TABLE IF NOT EXISTS improvement_settings (
                    -- channel_id='*' をグローバル設定として扱う
                    channel_id TEXT PRIMARY KEY,
                    like_rate_threshold_percent REAL NOT NULL,
                    min_views INTEGER NOT NULL,
                    auto_check_enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            c.commit()
        finally:
            c.close()


# 起動時にテーブルを用意
init_db()


# ---------------------------------------------------------------------
# Suggestions builder
# ---------------------------------------------------------------------

def build_suggestions(
    *,
    video_title: Optional[str],
    like_rate: float,
    threshold: float,
    views: int,
    likes: int,
) -> Dict[str, Any]:
    """
    いいね率が閾値を下回ったときの改善提案を生成。
    （ルールベース＝GPTを呼ばない。GPT に渡す材料として使う。）

    like_rate / threshold は 0..1 の比率（%表示は呼び出し側で）。
    """
    rate_pct = like_rate * 100.0
    thr_pct = threshold * 100.0
    title_str = video_title or "(タイトル不明)"

    # 比率が小さければ大きいほど強い改善メッセージにする
    severity = "mild"
    if like_rate < threshold * 0.5:
        severity = "high"
    elif like_rate < threshold * 0.75:
        severity = "medium"

    title_tips = [
        "数字を入れる（例: 「3つの理由」「99%が知らない」）",
        "疑問形 + ベネフィットを冒頭に置く（例: 「なぜ◯◯なのか？知らないと損する△△」）",
        "ターゲット視聴者を明示（例: 「30代必見」「主婦が驚いた」）",
        "曖昧な抽象語（例: 「すごい」「面白い」）を具体名詞に置き換える",
    ]
    thumb_tips = [
        "サムネ文字は2行・各8文字以内に収め、最重要ワードのみ赤＋黄で強調",
        "キャラの表情を「驚き」「困惑」「目を見開く」のいずれかに変える",
        "背景色とテキスト色のコントラストを強める（例: 紺背景＋黄文字）",
        "数字や比較記号（VS / →）をサムネに大きく入れる",
    ]
    scenario_tips = [
        "冒頭5秒で結論または衝撃の事実を先出し（フック強化）",
        "視聴者へ問いかけ→共感→意外な答え、の3段構成を導入の3行以内に圧縮",
        "中盤に「ここで一度まとめると…」のリキャップを1回挿入",
        "終盤に「あなたならどうする？」とコメント誘発を1行追加",
        "数字データ・研究例を最低3箇所、具体名詞で言い切る",
    ]

    return {
        "severity": severity,
        "summary": (
            f"前回『{title_str}』は再生{views}回 / いいね{likes} = いいね率 {rate_pct:.2f}%。"
            f"目標 {thr_pct:.1f}% を下回った。次回はタイトル・サムネ・構成を強化する。"
        ),
        "title_improvements": title_tips,
        "thumbnail_improvements": thumb_tips,
        "scenario_improvements": scenario_tips,
        "metrics": {
            "views": views,
            "likes": likes,
            "like_rate": like_rate,
            "like_rate_percent": rate_pct,
            "threshold_percent": thr_pct,
        },
        "previous_title": video_title,
    }


# ---------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------

def save_feedback(
    *,
    video_id: str,
    channel_id: str,
    video_title: Optional[str],
    views: int,
    likes: int,
    like_rate: float,
    threshold: float,
    job_id: Optional[str] = None,
    suggestions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """フィードバックを UPSERT。同 video_id があれば metrics と is_consumed=0 にリセットする
    (再評価で改善が必要と判断された＝改めて反映してほしい)。"""
    if suggestions is None:
        suggestions = build_suggestions(
            video_title=video_title,
            like_rate=like_rate,
            threshold=threshold,
            views=views,
            likes=likes,
        )
    now = int(time.time())
    payload_json = json.dumps(suggestions, ensure_ascii=False)
    with _db_lock:
        c = _conn()
        try:
            existing = c.execute(
                "SELECT created_at FROM video_feedback WHERE video_id = ?", (video_id,)
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            c.execute(
                """
                INSERT OR REPLACE INTO video_feedback
                (video_id, channel_id, job_id, video_title, views, likes, like_rate,
                 threshold, suggestions, is_consumed, consumed_by_job_id,
                 created_at, updated_at, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, NULL)
                """,
                (
                    video_id,
                    channel_id,
                    job_id,
                    video_title,
                    int(views),
                    int(likes),
                    float(like_rate),
                    float(threshold),
                    payload_json,
                    created_at,
                    now,
                ),
            )
            c.commit()
            row = c.execute(
                "SELECT * FROM video_feedback WHERE video_id = ?", (video_id,)
            ).fetchone()
        finally:
            c.close()
    return _row_to_dict(row) if row else {}


def list_feedback(
    channel_id: Optional[str] = None,
    *,
    pending_only: bool = False,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    where = []
    args: List[Any] = []
    if channel_id:
        where.append("channel_id = ?")
        args.append(channel_id)
    if pending_only:
        where.append("is_consumed = 0")
    sql = "SELECT * FROM video_feedback"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    args.append(int(limit))
    with _db_lock:
        c = _conn()
        try:
            rows = c.execute(sql, args).fetchall()
        finally:
            c.close()
    return [_row_to_dict(r) for r in rows]


def get_pending_for_channel(channel_id: str) -> List[Dict[str, Any]]:
    return list_feedback(channel_id=channel_id, pending_only=True)


def mark_consumed(video_ids: List[str], consumed_by_job_id: Optional[str]) -> int:
    if not video_ids:
        return 0
    placeholders = ",".join("?" * len(video_ids))
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                f"UPDATE video_feedback SET is_consumed = 1, consumed_by_job_id = ?, "
                f"consumed_at = ?, updated_at = ? WHERE video_id IN ({placeholders})",
                [consumed_by_job_id, now, now, *video_ids],
            )
            c.commit()
            return cur.rowcount
        finally:
            c.close()


def delete_feedback(video_id: str) -> bool:
    with _db_lock:
        c = _conn()
        try:
            cur = c.execute(
                "DELETE FROM video_feedback WHERE video_id = ?", (video_id,)
            )
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["suggestions"] = json.loads(d.get("suggestions") or "{}")
    except Exception:
        d["suggestions"] = {}
    d["is_consumed"] = bool(d.get("is_consumed"))
    return d


# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------

def get_settings(channel_id: str = "*") -> Dict[str, Any]:
    """設定を取得。channel_id 個別 → '*' グローバル → 既定 の順で解決。"""
    with _db_lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM improvement_settings WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            if not row and channel_id != "*":
                row = c.execute(
                    "SELECT * FROM improvement_settings WHERE channel_id = '*'"
                ).fetchone()
        finally:
            c.close()
    if row:
        return {
            "channel_id": channel_id,
            "like_rate_threshold_percent": float(row["like_rate_threshold_percent"]),
            "min_views": int(row["min_views"]),
            "auto_check_enabled": bool(row["auto_check_enabled"]),
            "updated_at": int(row["updated_at"]) if row["updated_at"] else None,
            "source": "channel" if row["channel_id"] == channel_id else "global",
        }
    return {
        "channel_id": channel_id,
        "like_rate_threshold_percent": DEFAULT_LIKE_RATE_THRESHOLD_PERCENT,
        "min_views": DEFAULT_MIN_VIEWS,
        "auto_check_enabled": True,
        "updated_at": None,
        "source": "default",
    }


def save_settings(
    *,
    channel_id: str = "*",
    like_rate_threshold_percent: float,
    min_views: int,
    auto_check_enabled: bool,
) -> Dict[str, Any]:
    now = int(time.time())
    with _db_lock:
        c = _conn()
        try:
            c.execute(
                """
                INSERT OR REPLACE INTO improvement_settings
                (channel_id, like_rate_threshold_percent, min_views, auto_check_enabled, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    channel_id,
                    float(like_rate_threshold_percent),
                    int(min_views),
                    1 if auto_check_enabled else 0,
                    now,
                ),
            )
            c.commit()
        finally:
            c.close()
    return get_settings(channel_id)


def resolve_threshold_for_channel(channel) -> float:
    """
    Channel オブジェクト + DB 設定 + 既定 から、適用すべきいいね率閾値（0..1）を解決。

    優先順位:
      1. improvement_settings の channel_id 個別レコード
      2. channel.video_format.analytics.performance_threshold.min_like_rate (％)
      3. improvement_settings の '*' グローバル
      4. DEFAULT_LIKE_RATE_THRESHOLD_PERCENT (3.0%)
    """
    s = get_settings(channel.id) if channel else None
    if s and s["source"] == "channel":
        return s["like_rate_threshold_percent"] / 100.0
    # チャンネル定義側
    try:
        thr_pct = float(
            channel.video_format.analytics.performance_threshold.get("min_like_rate")
        )
        if thr_pct > 0:
            return thr_pct / 100.0
    except Exception:
        pass
    if s:
        return s["like_rate_threshold_percent"] / 100.0
    return DEFAULT_LIKE_RATE_THRESHOLD_PERCENT / 100.0


def resolve_min_views_for_channel(channel) -> int:
    s = get_settings(channel.id) if channel else None
    if s:
        return s["min_views"]
    return DEFAULT_MIN_VIEWS


# ---------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------

def build_prompt_addendum(feedback_items: List[Dict[str, Any]]) -> str:
    """ScenarioGenerator が GPT に渡す追加指示を組み立てる。
    pending な feedback が無い場合は空文字。"""
    if not feedback_items:
        return ""

    # 直近 3 件だけ反映（多すぎるとプロンプトがブレる）
    recent = feedback_items[:3]
    lines: List[str] = []
    lines.append("## 直近の改善フィードバック（前回までの低パフォーマンス動画）")
    for fb in recent:
        sug = fb.get("suggestions") or {}
        rate_pct = (fb.get("like_rate") or 0.0) * 100
        thr_pct = (fb.get("threshold") or 0.0) * 100
        prev_title = fb.get("video_title") or "(unknown)"
        lines.append(
            f"- 前回『{prev_title}』いいね率 {rate_pct:.2f}% (目標 {thr_pct:.1f}%) — "
            f"重要度: {sug.get('severity', '?')}"
        )

    # 改善の方向性（最新1件分の suggestions を使う）
    primary = recent[0].get("suggestions") or {}

    def _bullets(key: str) -> str:
        items = primary.get(key) or []
        return "\n".join(f"  - {x}" for x in items[:4])

    lines.append("\n### 次回シナリオで強化すること（必ず反映）")
    lines.append("**タイトル方針**:")
    lines.append(_bullets("title_improvements"))
    lines.append("**サムネ方針 (thumb_info で反映)**:")
    lines.append(_bullets("thumbnail_improvements"))
    lines.append("**シナリオ構成方針**:")
    lines.append(_bullets("scenario_improvements"))
    lines.append(
        "\n上記を必ず取り込んだ上で、title・thumb_info.hook_lines・full_scenario の冒頭5行に変化が出るようにすること。"
    )
    return "\n".join(lines)
