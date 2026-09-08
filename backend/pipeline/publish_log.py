"""公開実績の記録 — data/video_publish.db の `video_status` へ1行残す。

なぜ独立モジュールにしてあるか:
    `video_status` テーブルは元々 api_phase3（PublishDialog の手動公開）と
    api_phase3._record_pair_status_to_db（メイン+ショートのペア公開）だけが
    書いていた。ところが運用は 2026-06 以降 **全チャンネル gen_type="short"
    の単体公開** に移っており、その経路（api_phase4._start_single_short_publish）
    と手動スクリプト経路（youtube_uploader.upload_video）はどちらもこの
    テーブルに書いていなかった。

    結果、`video_status` の最終行が 2026-06-07 で止まり、そこを起点にしている

        - pipeline/analytics/pdca_report.build_report()  → 期間内の動画が0件
          になり、ショート/メインの振り分けも登録者ソース分析も全部 "unknown"
        - api_improvement._published_videos_for_channel() → いいね率改善ループが
          「公開済みの動画がまだありません」で毎回空振り

    が静かに死んでいた。アップロード経路が増えるたびに書き忘れるのが根本原因
    なので、記録を1箇所に集約して各経路から呼ぶ形にする。

    api_phase3 側の既存2経路は job_id の採番規約（メイン=job_id /
    ショート=f"{job_id}:short"）を持っているのでそのまま残してある。
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PUBLISH_DB = PROJECT_ROOT / "data" / "video_publish.db"

JST = timezone(timedelta(hours=9))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS video_status (
    job_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    video_id TEXT,
    url TEXT,
    scheduled_at TEXT,
    published_at TEXT,
    updated_at INTEGER NOT NULL
)
"""


def connect() -> sqlite3.Connection:
    """video_status を持つ接続を返す（テーブル・追加カラムを冪等に用意する）。"""
    PUBLISH_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(PUBLISH_DB), timeout=30.0)
    conn.execute(_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(video_status)")}
    # is_short: ショート/メインの判定を YouTube 側の尺・タイトル推定に頼らず、
    # 投稿時に分かっている事実として残す（NULL = 旧行 or 不明）。
    if "is_short" not in cols:
        conn.execute("ALTER TABLE video_status ADD COLUMN is_short INTEGER")
    if "title" not in cols:
        conn.execute("ALTER TABLE video_status ADD COLUMN title TEXT")
    conn.commit()
    return conn


def make_job_id(job_id: Optional[str], video_id: str, *, is_short: bool) -> str:
    """PRIMARY KEY に使うキーを決める。

    ジョブ由来の公開は job_id をそのまま使い、既存の PublishDialog / ペア公開と
    キー空間を共有する。ジョブを持たない手動スクリプト経路は video_id で一意に
    なるので "upload:<video_id>" を使う（再実行しても行が増えない）。
    """
    if job_id:
        return job_id
    return f"upload:{video_id}"


def record_publish(
    *,
    channel_id: str,
    video_id: str,
    url: str = "",
    job_id: Optional[str] = None,
    is_short: bool = True,
    scheduled_at: Optional[str] = None,
    title: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[str]:
    """公開（または予約公開）1本を video_status に記録する。

    Args:
        channel_id: **内部**チャンネルID（"daily-science" など）。YouTube の
            UC... ではない。分析側はこの値でチャンネルを引く。
        scheduled_at: 予約公開の場合の公開予定時刻（ISO）。指定があれば
            status="scheduled"、無ければ "published"。

    Returns:
        書き込んだ job_id。video_id が無い等で記録しなかった場合は None。

    この関数は投稿処理から呼ばれるので、失敗しても投稿を巻き込まないように
    例外を外へ出さない。
    """
    if not video_id or not channel_id:
        return None
    key = make_job_id(job_id, video_id, is_short=is_short)
    status = "scheduled" if scheduled_at else "published"
    published_at = None if scheduled_at else datetime.now().isoformat()
    own_conn = conn is None
    try:
        c = conn or connect()
        try:
            c.execute(
                "INSERT OR REPLACE INTO video_status "
                "(job_id, channel_id, status, video_id, url, scheduled_at, "
                " published_at, updated_at, is_short, title) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    channel_id,
                    status,
                    video_id,
                    url or f"https://youtube.com/watch?v={video_id}",
                    scheduled_at,
                    published_at,
                    int(time.time()),
                    1 if is_short else 0,
                    title,
                ),
            )
            c.commit()
        finally:
            if own_conn:
                c.close()
        return key
    except Exception as e:  # pragma: no cover - 記録失敗で投稿を止めない
        print(f"⚠️ publish_log: video_status への記録に失敗 ({video_id}): {e}", flush=True)
        return None


# ---------------------------------------------------------------------
# 予約公開の後始末
# ---------------------------------------------------------------------

def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """ISO 文字列を aware な datetime にする。

    `scheduled_at` は経路によって書式が揺れる（実データに `...Z` 付きと
    タイムゾーンなしの両方がある）。tz が無いものは **JST** として読む。
    投稿枠の時刻は全て JST で運用しているので、UTC と解釈すると9時間ぶん
    「まだ未来」に見えて永久に published にならない。
    """
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=JST)


def reconcile_scheduled(*, now: Optional[str] = None,
                        conn: Optional[sqlite3.Connection] = None) -> int:
    """公開時刻を過ぎた `scheduled` 行を `published` に遷移させる。

    なぜ要るか（2026-09-09）:
        `record_publish` は予約公開を `status='scheduled'` /
        `published_at=NULL` で書くが、**予定時刻が来たことを誰も書き戻して
        いなかった**。YouTube 側では毎日公開されているのに DB 上は
        ゆっくり系8chが `scheduled` のまま溜まり続け（09-08 時点で136行）、
        `published_at` で集計する経路（pdca_report / 公開本数の集計 /
        api_improvement の「公開済み動画」）から丸ごと落ちていた。

        遷移の根拠は YouTube API ではなく**予約時刻**にしている。予約公開は
        API が受理した時点で確定しており、`video_id` も既に採番済み
        （＝行に入っている）。追加の API 呼び出しは quota を使ううえ、
        OAuth 失効中のチャンネルで丸ごと失敗して復旧が遅れる。
        取り消し・削除された動画までは追えないが、その頻度と
        「毎日全ch欠測」を比べれば時刻ベースで足りる。

    Args:
        now: 基準時刻（ISO）。省略時は現在時刻。テスト用。

    Returns:
        遷移させた行数。
    """
    ref = _parse_ts(now) or datetime.now(JST)
    own_conn = conn is None
    c = conn or connect()
    try:
        rows = list(c.execute(
            "SELECT job_id, scheduled_at FROM video_status "
            "WHERE status = 'scheduled' AND video_id IS NOT NULL AND video_id != ''"))
        due = []
        for job_id, scheduled_at in rows:
            dt = _parse_ts(scheduled_at)
            if dt is not None and dt <= ref:
                due.append((scheduled_at, int(time.time()), job_id))
        if due:
            c.executemany(
                "UPDATE video_status SET status='published', published_at=?, "
                "updated_at=? WHERE job_id=?", due)
            c.commit()
        return len(due)
    finally:
        if own_conn:
            c.close()
