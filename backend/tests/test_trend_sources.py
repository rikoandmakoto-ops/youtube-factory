"""トレンド検出のソース疎通に関する単体テスト（ネットワークは叩かない）。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_trend_sources -v

守りたい回帰:
  - trend_scanner が fetch_youtube_trending の返り値を正しいキーで読むこと。
    "items" を読んでいたため取得成功でも常に0件と判定され、984回のスキャンで
    trend_detections が1件も入らないまま機能が死んでいた。
  - Google Trends RSS のパースがフィード名（Daily Search Trends）を
    トレンドとして拾わないこと。
  - relevance 採点が Claude 不通時に GPT へフォールバックすること。
    Claude だけに依存していた頃は ANTHROPIC_API_KEY が失効した時点で
    語彙一致フォールバック（上限0.35前後）に落ち、自動キュー投入の
    しきい値 0.7 に永久に届かなくなっていた。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import trend_fetcher  # noqa: E402
from pipeline.analytics import trend_scanner as ts  # noqa: E402


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <title>Daily Search Trends</title>
    <description>Recent searches</description>
    <item>
      <title>袋麺</title>
      <ht:approx_traffic>2000+</ht:approx_traffic>
    </item>
    <item>
      <title>人工島</title>
    </item>
    <item>
      <title>袋麺</title>
    </item>
  </channel>
</rss>
"""


class TestTrendsRssParsing(unittest.TestCase):
    def test_feed_title_is_not_a_trend(self):
        out = trend_fetcher.parse_trends_rss(SAMPLE_RSS)
        self.assertNotIn("Daily Search Trends", out)

    def test_extracts_item_titles_in_order(self):
        out = trend_fetcher.parse_trends_rss(SAMPLE_RSS)
        self.assertEqual(out[:2], ["袋麺", "人工島"])

    def test_deduplicates(self):
        out = trend_fetcher.parse_trends_rss(SAMPLE_RSS)
        self.assertEqual(len(out), 2)

    def test_limit_respected(self):
        self.assertEqual(len(trend_fetcher.parse_trends_rss(SAMPLE_RSS, limit=1)), 1)

    def test_empty_feed(self):
        empty = '<?xml version="1.0"?><rss version="2.0"><channel/></rss>'
        self.assertEqual(trend_fetcher.parse_trends_rss(empty), [])


class TestYoutubeTrendingKey(unittest.TestCase):
    """fetch_youtube_trending は "videos" を返す。"items" ではない。"""

    def setUp(self):
        self._orig = trend_fetcher.fetch_youtube_trending

    def tearDown(self):
        trend_fetcher.fetch_youtube_trending = self._orig

    def _patch(self, payload):
        trend_fetcher.fetch_youtube_trending = lambda *a, **k: payload

    def test_reads_videos_key(self):
        self._patch({
            "ok": True,
            "error": None,
            "videos": [
                {"video_id": "a1", "title": "実験", "views": 100, "tags": []},
                {"video_id": "a2", "title": "検証", "views": 50, "tags": []},
            ],
        })
        out, err = ts._fetch_youtube_trending()
        self.assertIsNone(err)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["keyword"], "実験")
        self.assertEqual(out[0]["source"], "youtube_trending")

    def test_items_key_is_not_used(self):
        """旧バグの再発防止: "items" しか入っていない返り値は0件扱いでよい。"""
        self._patch({"ok": True, "error": None, "items": [{"title": "x"}]})
        out, _ = ts._fetch_youtube_trending()
        self.assertEqual(out, [])

    def test_ranks_descend(self):
        self._patch({
            "ok": True,
            "error": None,
            "videos": [{"video_id": str(i), "title": f"t{i}", "views": 0, "tags": []}
                       for i in range(4)],
        })
        out, _ = ts._fetch_youtube_trending()
        scores = [o["trend_score"] for o in out]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_empty_videos_returns_error_field(self):
        self._patch({"ok": False, "error": "YOUTUBE_API_KEY not set", "videos": []})
        out, err = ts._fetch_youtube_trending()
        self.assertEqual(out, [])
        self.assertEqual(err, "YOUTUBE_API_KEY not set")


class TestRelevanceScoringFallback(unittest.TestCase):
    """Claude が落ちても GPT で採点が続くこと。"""

    def setUp(self):
        self._claude = ts._score_via_claude
        self._gpt = ts._score_via_gpt

    def tearDown(self):
        ts._score_via_claude = self._claude
        ts._score_via_gpt = self._gpt

    def _candidates(self):
        return [{"keyword": "袋麺", "source": "google_trends", "trend_score": 1.0}]

    def _run(self):
        return ts._score_with_llm(
            self._candidates(),
            channel_name="ch", channel_concept="concept",
            seeds=["睡眠"], channel_id="daily-science",
        )

    def test_falls_back_to_gpt_when_claude_unavailable(self):
        ts._score_via_claude = lambda *a, **k: None
        ts._score_via_gpt = lambda *a, **k: {
            "scores": [{"index": 0, "relevance": 0.82, "title": "T", "angle": "A", "reason": "R"}]
        }
        out = self._run()
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["relevance_score"], 0.82)
        self.assertEqual(out[0]["suggested_title"], "T")

    def test_claude_result_wins_when_available(self):
        ts._score_via_claude = lambda *a, **k: {
            "scores": [{"index": 0, "relevance": 0.5, "title": "claude", "angle": "", "reason": ""}]
        }

        def _boom(*a, **k):
            raise AssertionError("Claude が使えるのに GPT を呼んではいけない")

        ts._score_via_gpt = _boom
        self.assertEqual(self._run()[0]["suggested_title"], "claude")

    def test_returns_none_when_both_backends_fail(self):
        ts._score_via_claude = lambda *a, **k: None
        ts._score_via_gpt = lambda *a, **k: None
        self.assertIsNone(self._run())

    def test_relevance_is_clamped(self):
        ts._score_via_claude = lambda *a, **k: None
        ts._score_via_gpt = lambda *a, **k: {
            "scores": [{"index": 0, "relevance": 9.9, "title": "", "angle": "", "reason": ""}]
        }
        self.assertLessEqual(self._run()[0]["relevance_score"], 1.0)

    def test_empty_candidates_short_circuits(self):
        self.assertEqual(
            ts._score_with_llm([], channel_name="c", channel_concept="c",
                               seeds=[], channel_id="x"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
