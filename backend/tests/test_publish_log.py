"""video_status への公開記録の単体テスト。

pytest 未導入の環境でも動くよう標準ライブラリ unittest で記述。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_publish_log -v

守りたい回帰:
  - 単体ショート公開・手動アップロードが video_status に行を残すこと
    （この記録が無いと pdca_report は期間内動画0件になり、登録者ソース分析が
     全部 "unknown" に落ちる。実際 2026-06-07 から 8月末まで死んでいた）
  - 同じ動画を2回記録しても行が増えないこと（バックフィルの再実行に耐える）
  - 予約公開が status="scheduled" で published_at を埋めないこと
  - is_short / title カラムが無い旧DBでも接続時に足されること
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# backend/ を import パスに追加（tests/ の1つ上）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import publish_log  # noqa: E402


class PublishLogTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_db = publish_log.PUBLISH_DB
        publish_log.PUBLISH_DB = Path(self._tmp.name) / "video_publish.db"

    def tearDown(self):
        publish_log.PUBLISH_DB = self._orig_db
        self._tmp.cleanup()

    def _rows(self):
        conn = sqlite3.connect(str(publish_log.PUBLISH_DB))
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM video_status")]
        finally:
            conn.close()

    def test_records_published_short(self):
        key = publish_log.record_publish(
            channel_id="fake-paper",
            video_id="abc123",
            url="https://youtube.com/watch?v=abc123",
            job_id="job-1",
            is_short=True,
            title="架空論文ファイル #6",
        )
        self.assertEqual(key, "job-1")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["channel_id"], "fake-paper")
        self.assertEqual(rows[0]["status"], "published")
        self.assertEqual(rows[0]["is_short"], 1)
        self.assertIsNotNone(rows[0]["published_at"])
        self.assertIsNone(rows[0]["scheduled_at"])

    def test_scheduled_publish_is_not_marked_published(self):
        publish_log.record_publish(
            channel_id="scp-lab",
            video_id="sched1",
            job_id="job-2",
            scheduled_at="2026-09-02T19:00:00Z",
        )
        row = self._rows()[0]
        self.assertEqual(row["status"], "scheduled")
        self.assertIsNone(row["published_at"])
        self.assertEqual(row["scheduled_at"], "2026-09-02T19:00:00Z")

    def test_manual_upload_without_job_id_is_idempotent(self):
        # 手動スクリプト経路は job を持たないので video_id からキーを作る。
        # 同じ動画を再記録しても行が増えてはいけない（重複すると
        # pdca_report が同じ動画を2回集計する）。
        for _ in range(3):
            key = publish_log.record_publish(
                channel_id="daily-science", video_id="vid9"
            )
        self.assertEqual(key, "upload:vid9")
        self.assertEqual(len(self._rows()), 1)

    def test_missing_video_id_records_nothing(self):
        # video_id が無いなら DB を作りにすら行かない（アップロード失敗時に
        # 空行を残さないため）。
        self.assertIsNone(
            publish_log.record_publish(channel_id="scp-lab", video_id="")
        )
        self.assertIsNone(
            publish_log.record_publish(channel_id="", video_id="vid1")
        )
        self.assertFalse(publish_log.PUBLISH_DB.exists())

    def test_legacy_db_gets_new_columns(self):
        # publish_log 導入前のスキーマ（is_short / title 無し）を作ってから接続。
        conn = sqlite3.connect(str(publish_log.PUBLISH_DB))
        conn.execute(
            "CREATE TABLE video_status ("
            " job_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL,"
            " status TEXT NOT NULL DEFAULT 'draft', video_id TEXT, url TEXT,"
            " scheduled_at TEXT, published_at TEXT, updated_at INTEGER NOT NULL)"
        )
        conn.commit()
        conn.close()

        publish_log.record_publish(
            channel_id="yokai-watch", video_id="legacy1", is_short=True
        )
        row = self._rows()[0]
        self.assertEqual(row["is_short"], 1)
        self.assertEqual(row["video_id"], "legacy1")


if __name__ == "__main__":
    unittest.main()
