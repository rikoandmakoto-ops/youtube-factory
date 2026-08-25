"""サムネ impressions / CTR の取り込み（YouTube Reporting API reach レポート）テスト。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_reach_reporting -v

守りたい回帰:
  video_metrics.impressions / ctr が 4,850 行すべて 0 だった原因は、
  Analytics API v2 に存在しない metrics=impressions を叩いて 400 を
  握り潰していたこと。サムネ指標は Reporting API の
  channel_reach_basic_a1（video_thumbnail_impressions /
  video_thumbnail_impressions_ctr）からしか取れない。

  ここでは API を叩かずに、CSV パース・CTR 正規化・期間集計・
  video_metrics への反映を検証する。
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import youtube_reporting as yr  # noqa: E402
from pipeline.analytics import store  # noqa: E402


class TestReportParsing(unittest.TestCase):
    def test_parses_reach_csv(self):
        csv_text = (
            "date,channel_id,video_id,"
            "video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
            "20260820,UCxxx,vid1,1000,0.045\n"
            "20260821,UCxxx,vid1,500,0.06\n"
        )
        rows = yr._parse_report_csv(csv_text, "daily-science")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["video_id"], "vid1")
        self.assertEqual(rows[0]["date"], "2026-08-20")
        self.assertEqual(rows[0]["impressions"], 1000)
        self.assertAlmostEqual(rows[0]["clicks"], 45.0)

    def test_skips_rows_without_video_or_date(self):
        csv_text = (
            "date,channel_id,video_id,"
            "video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
            ",UCxxx,vid1,10,0.1\n"
            "20260820,UCxxx,,10,0.1\n"
            "20260820,UCxxx,vid2,10,0.1\n"
        )
        rows = yr._parse_report_csv(csv_text, "daily-science")
        self.assertEqual([r["video_id"] for r in rows], ["vid2"])

    def test_date_normalization(self):
        self.assertEqual(yr._normalize_date("20260820"), "2026-08-20")
        self.assertEqual(yr._normalize_date("2026-08-20"), "2026-08-20")
        self.assertIsNone(yr._normalize_date(""))
        self.assertIsNone(yr._normalize_date("garbage"))


class TestCtrNormalization(unittest.TestCase):
    """video_metrics.ctr は 0..1 の規約。百分率で来ても揃える。"""

    def test_fraction_passes_through(self):
        self.assertAlmostEqual(yr._normalize_ctr(0.045), 0.045)

    def test_percentage_is_divided(self):
        self.assertAlmostEqual(yr._normalize_ctr(4.5), 0.045)

    def test_zero_and_garbage(self):
        self.assertEqual(yr._normalize_ctr(0), 0.0)
        self.assertEqual(yr._normalize_ctr(""), 0.0)
        self.assertEqual(yr._normalize_ctr(None), 0.0)
        self.assertEqual(yr._normalize_ctr("abc"), 0.0)

    def test_boundary_one_stays_fraction(self):
        # 100% はありうる（分数として 1.0）。100 で割ってはいけない。
        self.assertAlmostEqual(yr._normalize_ctr(1.0), 1.0)


class _FakeResp:
    def __init__(self, status):
        self.status = status


class _FakeHttpError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.resp = _FakeResp(status)


class _FakeReports:
    """jobs().reports().list(...).execute() を模す。

    `script` は execute() 呼び出しごとの結果。例外インスタンスなら raise。
    """

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._script.pop(0)

        class _Req:
            def execute(_self):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        return _Req()


class _FakeJobs:
    def __init__(self, reports):
        self._reports = reports

    def reports(self):
        return self._reports


class _FakeSvc:
    def __init__(self, reports):
        self._jobs = _FakeJobs(reports)

    def jobs(self):
        return self._jobs


class TestListReportsResilience(unittest.TestCase):
    """reports.list の一時 500 で丸ごと取り込み 0 件になるのを防ぐ。

    守りたい回帰: 2026-08-25 に yokai-watch の reports.list が 500 を返し、
    再試行が無かったためそのチャンネルの取り込みが 0 件で終わっていた。
    """

    def setUp(self):
        self._orig_sleep = yr.time.sleep
        yr.time.sleep = lambda *_a, **_k: None

    def tearDown(self):
        yr.time.sleep = self._orig_sleep

    def test_retries_transient_500_then_succeeds(self):
        reports = _FakeReports([
            _FakeHttpError(500),
            _FakeHttpError(503),
            {"reports": [{"id": "r1"}]},
        ])
        res = yr._list_reports(_FakeSvc(reports), "job1", "2026-07-24T00:00:00Z")
        self.assertTrue(res["ok"])
        self.assertEqual([r["id"] for r in res["reports"]], ["r1"])
        self.assertEqual(len(reports.calls), 3)

    def test_does_not_retry_permanent_error(self):
        reports = _FakeReports([_FakeHttpError(403)])
        res = yr._list_reports(_FakeSvc(reports), "job1", "2026-07-24T00:00:00Z")
        self.assertFalse(res["ok"])
        self.assertEqual(len(reports.calls), 1)  # 403 は再試行しない

    def test_gives_up_after_max_attempts(self):
        reports = _FakeReports([_FakeHttpError(500)] * yr.LIST_MAX_ATTEMPTS)
        res = yr._list_reports(_FakeSvc(reports), "job1", "2026-07-24T00:00:00Z")
        self.assertFalse(res["ok"])
        self.assertEqual(len(reports.calls), yr.LIST_MAX_ATTEMPTS)

    def test_follows_all_pages(self):
        """ページを打ち切ると新しいレポートが取り込まれず日次が欠ける。"""
        reports = _FakeReports([
            {"reports": [{"id": "a"}], "nextPageToken": "t1"},
            {"reports": [{"id": "b"}], "nextPageToken": "t2"},
            {"reports": [{"id": "c"}]},
        ])
        res = yr._list_reports(_FakeSvc(reports), "job1", "2026-07-24T00:00:00Z")
        self.assertEqual([r["id"] for r in res["reports"]], ["a", "b", "c"])
        self.assertEqual(
            [c.get("pageToken") for c in reports.calls], [None, "t1", "t2"]
        )


class TestAggregationAndUpdate(unittest.TestCase):
    """集計と video_metrics への反映を一時DBで検証する。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_path = store.DB_PATH
        store.DB_PATH = Path(self._tmp.name) / "analytics.db"
        store.init_db()

    def tearDown(self):
        store.DB_PATH = self._orig_path
        self._tmp.cleanup()

    def test_ctr_is_impression_weighted_not_simple_mean(self):
        """impressions 1 の日と 10,000 の日を同じ重みにしてはいけない。"""
        store.upsert_video_reach_daily(
            video_id="vid1", channel_id="ch", date="2026-08-20",
            impressions=10000, clicks=400.0,   # 4%
        )
        store.upsert_video_reach_daily(
            video_id="vid1", channel_id="ch", date="2026-08-21",
            impressions=1, clicks=1.0,          # 100%
        )
        agg = store.aggregate_video_reach(
            "ch", start_date="2026-08-01", end_date="2026-08-31"
        )
        self.assertEqual(agg["vid1"]["impressions"], 10001)
        # 単純平均なら 0.52。重み付きなら ~0.0401
        self.assertAlmostEqual(agg["vid1"]["ctr"], 401.0 / 10001, places=6)

    def test_window_filters_out_of_range_days(self):
        store.upsert_video_reach_daily(
            video_id="vid1", channel_id="ch", date="2026-07-01",
            impressions=999, clicks=99.0,
        )
        store.upsert_video_reach_daily(
            video_id="vid1", channel_id="ch", date="2026-08-20",
            impressions=100, clicks=5.0,
        )
        agg = store.aggregate_video_reach(
            "ch", start_date="2026-08-01", end_date="2026-08-31"
        )
        self.assertEqual(agg["vid1"]["impressions"], 100)

    def test_reingesting_same_day_replaces_not_doubles(self):
        """レポートは再発行されうる。二重計上したら CTR が壊れる。"""
        for _ in range(3):
            store.upsert_video_reach_daily(
                video_id="vid1", channel_id="ch", date="2026-08-20",
                impressions=100, clicks=5.0,
            )
        agg = store.aggregate_video_reach(
            "ch", start_date="2026-08-01", end_date="2026-08-31"
        )
        self.assertEqual(agg["vid1"]["impressions"], 100)

    def test_update_video_metric_reach_preserves_other_columns(self):
        store.upsert_video_metric(
            video_id="vid1", channel_id="ch", date="2026-08-21",
            title="タイトル", published_at="2026-08-01T00:00:00Z",
            views=1234, avg_view_percentage=53.2, likes=10,
        )
        ok = store.update_video_metric_reach(
            video_id="vid1", date="2026-08-21", impressions=5000, ctr=0.042
        )
        self.assertTrue(ok)
        rows = store.list_video_metrics("ch", limit=10)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["impressions"], 5000)
        self.assertAlmostEqual(r["ctr"], 0.042)
        # 他の列を壊していないこと
        self.assertEqual(r["views"], 1234)
        self.assertEqual(r["title"], "タイトル")
        self.assertEqual(r["likes"], 10)

    def test_update_returns_false_when_no_snapshot_row(self):
        ok = store.update_video_metric_reach(
            video_id="missing", date="2026-08-21", impressions=1, ctr=0.1
        )
        self.assertFalse(ok)

    def test_report_ingest_is_idempotent(self):
        self.assertFalse(store.is_report_ingested("r1"))
        store.mark_report_ingested(
            report_id="r1", channel_id="ch", job_id="j1",
            start_time="2026-08-20T00:00:00Z", end_time="2026-08-21T00:00:00Z",
            rows_ingested=42,
        )
        self.assertTrue(store.is_report_ingested("r1"))


if __name__ == "__main__":
    unittest.main()
