#!/usr/bin/env python3
"""video_status の欠損を analytics.db から埋め戻す。

背景:
    data/video_publish.db の `video_status` は 2026-06-07 を最後に更新が
    止まっていた（単体ショート公開の経路が書いていなかった。詳細は
    backend/pipeline/publish_log.py の冒頭）。前向きの記録は publish_log で
    直したが、6月〜8月末に公開した約450本は記録が無いままなので、
    PDCA レポートは過去分を一切見られない。

    analytics.db の `video_metrics` には YouTube から取得した
    (video_id, channel_id, title, published_at) が日次スナップショットで
    残っている。これを唯一の情報源として video_status を埋め戻す。
    YouTube API を叩かないのでクォータを消費しない。

冪等性:
    キーは publish_log.make_job_id() と同じ "upload:<video_id>"。すでに
    同じ video_id を持つ行がある（ペア公開や手動公開で記録済み）ものは
    触らない。何度実行しても行は増えない。

使い方:
    python3 backend/backfill_video_status.py            # 全チャンネル
    python3 backend/backfill_video_status.py scp-lab    # 指定チャンネルのみ
    python3 backend/backfill_video_status.py --dry-run  # 書き込まず件数だけ
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from pipeline import publish_log  # noqa: E402

ANALYTICS_DB = REPO_ROOT / "data" / "analytics" / "analytics.db"


def _latest_videos(channel_ids):
    """video_metrics から動画ごとの最新スナップショットを取る。"""
    if not ANALYTICS_DB.exists():
        raise SystemExit(f"analytics.db がありません: {ANALYTICS_DB}")
    conn = sqlite3.connect(str(ANALYTICS_DB))
    try:
        sql = (
            "SELECT video_id, channel_id, title, published_at FROM ("
            "  SELECT video_id, channel_id, title, published_at,"
            "         ROW_NUMBER() OVER ("
            "             PARTITION BY video_id ORDER BY date DESC) rn"
            "  FROM video_metrics"
            ") WHERE rn = 1 AND published_at IS NOT NULL AND published_at != ''"
        )
        params: tuple = ()
        if channel_ids:
            marks = ",".join("?" * len(channel_ids))
            sql += f" AND channel_id IN ({marks})"
            params = tuple(channel_ids)
        return conn.execute(sql + " ORDER BY channel_id, published_at", params).fetchall()
    finally:
        conn.close()


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry_run = "--dry-run" in sys.argv

    rows = _latest_videos(args)
    conn = publish_log.connect()
    try:
        known = {
            r[0]
            for r in conn.execute(
                "SELECT video_id FROM video_status WHERE video_id IS NOT NULL"
            )
        }
        inserted = 0
        skipped = 0
        per_channel: dict = {}
        for video_id, channel_id, title, published_at in rows:
            if video_id in known:
                skipped += 1
                continue
            per_channel[channel_id] = per_channel.get(channel_id, 0) + 1
            inserted += 1
            if dry_run:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO video_status "
                "(job_id, channel_id, status, video_id, url, scheduled_at, "
                " published_at, updated_at, is_short, title) "
                "VALUES (?, ?, 'published', ?, ?, NULL, ?, ?, NULL, ?)",
                (
                    publish_log.make_job_id(None, video_id, is_short=True),
                    channel_id,
                    video_id,
                    f"https://youtube.com/watch?v={video_id}",
                    published_at,
                    int(time.time()),
                    title,
                ),
            )
            known.add(video_id)
        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    label = "（dry-run。書き込みなし）" if dry_run else ""
    print(f"video_status 埋め戻し{label}")
    print(f"  対象 video_metrics 行: {len(rows)}")
    print(f"  既に記録済みでスキップ: {skipped}")
    print(f"  追加: {inserted}")
    for cid, n in sorted(per_channel.items()):
        print(f"    {cid:20s} {n}")
    # is_short は NULL のまま入れる。ここには尺の情報が無く、推測で埋めると
    # pdca_report のショート/メイン振り分けを誤らせる。NULL なら
    # pdca_report が YouTube 側の contentDetails.duration から判定する。
    print("  ※ is_short は NULL（YouTube 側の尺から判定させる）")


if __name__ == "__main__":
    main()
