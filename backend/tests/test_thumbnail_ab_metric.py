"""サムネABテストの判定指標に関する単体テスト。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_thumbnail_ab_metric -v

背景と守りたい回帰:
  サムネ impressions / CTR は YouTube Analytics API v2 では取得できない
  （metrics=impressions は 400 "Unknown identifier"。Studio と Reporting API の
  バルクレポートにしか無い）。そのため video_metrics.ctr は4673行すべて0で、
  判定が常に no_data になり、18件のテストが2か月以上 monitoring のまま
  ぶら下がっていた。代理指標として「1日あたり再生数」を使う。

  ただし再生数が極端に少ない動画では「サムネが悪い」のか「そもそも露出が
  無い/同期が失敗している」のか区別できない。区別できないまま切り替えると
  公開中の動画のサムネを根拠なく差し替えることになるので、
  MIN_VIEWS_FOR_JUDGEMENT 未満は判定を見送る。
"""

import os
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.analytics import thumbnail_ab_test as tab  # noqa: E402


def _iso(days_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(views, published_at):
    """sqlite3.Row 互換の軽量スタブ（views / published_at のみ）。"""
    return {"views": views, "published_at": published_at}


class TestViewVelocity(unittest.TestCase):
    def test_views_per_day(self):
        v = tab._view_velocity(_row(100, _iso(10)))
        self.assertIsNotNone(v)
        self.assertAlmostEqual(v, 10.0, delta=0.5)

    def test_too_fresh_returns_none(self):
        """公開直後は分母が小さすぎて指標が暴れるので判定しない。"""
        self.assertIsNone(tab._view_velocity(_row(5, _iso(0.1))))

    def test_missing_published_at(self):
        self.assertIsNone(tab._view_velocity(_row(100, None)))

    def test_malformed_published_at(self):
        self.assertIsNone(tab._view_velocity(_row(100, "not-a-date")))

    def test_zero_views_is_zero_not_none(self):
        """0再生は「指標が取れない」ではなく「0」。足切りは呼び出し側の責務。"""
        self.assertEqual(tab._view_velocity(_row(0, _iso(30))), 0.0)


class TestVelocityQueries(unittest.TestCase):
    """DB を一時ファイルに差し替えて実クエリを検証する。"""

    def setUp(self):
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self._orig_db = tab.DB_PATH
        tab.DB_PATH = Path(self._tmp.name) / "analytics.db"
        conn = sqlite3.connect(str(tab.DB_PATH))
        conn.executescript(
            """
            CREATE TABLE video_metrics (
              video_id TEXT, channel_id TEXT, date TEXT, views INTEGER,
              published_at TEXT, ctr REAL
            );
            """
        )
        rows = [
            # 十分な再生数がある動画（判定対象）
            ("v_big", "ch", "2026-08-18", 400, _iso(10), 0.0),
            ("v_mid", "ch", "2026-08-18", 200, _iso(10), 0.0),
            ("v_small", "ch", "2026-08-18", 100, _iso(10), 0.0),
            # 足切り未満（判定見送り）
            ("v_tiny", "ch", "2026-08-18", 3, _iso(30), 0.0),
            ("v_zero", "ch", "2026-08-18", 0, _iso(60), 0.0),
        ]
        conn.executemany("INSERT INTO video_metrics VALUES (?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

    def tearDown(self):
        tab.DB_PATH = self._orig_db
        self._tmp.cleanup()

    def test_below_min_views_is_not_judged(self):
        """再生数が足りない動画は None を返し、切替判定に進ませない。"""
        self.assertIsNone(tab._fetch_current_velocity("ch", "v_tiny"))
        self.assertIsNone(tab._fetch_current_velocity("ch", "v_zero"))

    def test_sufficient_views_is_judged(self):
        v = tab._fetch_current_velocity("ch", "v_big")
        self.assertIsNotNone(v)
        self.assertAlmostEqual(v, 40.0, delta=2.0)

    def test_unknown_video(self):
        self.assertIsNone(tab._fetch_current_velocity("ch", "nope"))

    def test_median_uses_middle_not_mean(self):
        """1本のバズで基準が歪まないよう中央値を使う。"""
        med = tab._channel_median_velocity("ch")
        # 40 / 20 / 10 (views/day) の中央値 = 20
        self.assertAlmostEqual(med, 20.0, delta=1.5)

    def test_median_is_zero_when_no_data(self):
        self.assertEqual(tab._channel_median_velocity("other-ch"), 0.0)


class TestMinViewsConstant(unittest.TestCase):
    def test_threshold_is_positive(self):
        """0 にすると再生0の動画で無根拠なサムネ切替が走る。"""
        self.assertGreater(tab.MIN_VIEWS_FOR_JUDGEMENT, 0)


if __name__ == "__main__":
    unittest.main()
