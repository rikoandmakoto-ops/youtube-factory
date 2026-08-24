"""Growth V3 features テスト — hashtag_optimizer / shorts_length_guard / theme_queue prioritize."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# =====================================================================
# hashtag_optimizer
# =====================================================================

class TestHashtagOptimizer(unittest.TestCase):

    def setUp(self):
        from pipeline import hashtag_optimizer as ho
        self.ho = ho

    def test_optimize_hashtags_daily_science(self):
        result = self.ho.optimize_hashtags("daily-science", "なぜ朝起きると目ヤニがついているのか")
        self.assertIn("#ゆっくり解説", result)
        self.assertIn("#雑学", result)
        tags = result.split()
        self.assertLessEqual(len(tags), 5)
        self.assertGreaterEqual(len(tags), 2)

    def test_optimize_hashtags_scp(self):
        result = self.ho.optimize_hashtags("scp-lab", "SCP-5000「人類滅亡」— 財団が殲滅する側に回った日")
        self.assertIn("#SCP", result)
        tags = result.split()
        self.assertLessEqual(len(tags), 5)

    def test_optimize_hashtags_2ch(self):
        result = self.ho.optimize_hashtags("2ch-matome", "上司「残業代はやる気で払う」→結果www")
        self.assertIn("#2ch", result)
        self.assertIn("#2chまとめ", result)

    def test_optimize_hashtags_with_trends(self):
        result = self.ho.optimize_hashtags(
            "daily-science",
            "なぜ猫は箱に入りたがるのか",
            trend_keywords=["猫", "ペット", "動物行動学"],
        )
        self.assertIn("#猫", result)

    def test_optimize_hashtags_with_theme_info(self):
        result = self.ho.optimize_hashtags(
            "daily-science",
            "睡眠の科学",
            theme_info={"is_trending": True, "trend_match": "睡眠障害"},
        )
        self.assertIn("#睡眠障害", result)

    def test_optimize_short_title_hashtags(self):
        result = self.ho.optimize_short_title_hashtags("daily-science", "なぜあくびは伝染するのか")
        self.assertTrue(result.startswith("#shorts"))
        tags = result.split()
        self.assertLessEqual(len(tags), 4)  # max_tags=3 + shorts

    def test_optimize_upload_tags(self):
        tags = self.ho.optimize_upload_tags(
            "scp-lab",
            "SCP-096「シャイガイ」",
            is_short=True,
        )
        self.assertIsInstance(tags, list)
        self.assertIn("Shorts", tags)
        total_len = sum(len(t) + 1 for t in tags)
        self.assertLessEqual(total_len, 450)

    def test_unknown_channel_fallback(self):
        result = self.ho.optimize_hashtags("unknown-channel", "テスト動画")
        self.assertIn("#ゆっくり解説", result)

    def test_no_duplicate_tags(self):
        result = self.ho.optimize_hashtags(
            "daily-science",
            "雑学クイズ：科学の豆知識",  # title contains 雑学 and 豆知識 which are also core
        )
        tags = result.split()
        normalized = [t.lower() for t in tags]
        self.assertEqual(len(normalized), len(set(normalized)), f"Duplicate tags: {tags}")

    def test_extract_title_keywords(self):
        kws = self.ho._extract_title_keywords("SCP-5000「人類滅亡」— 生存者は1名")
        self.assertIsInstance(kws, list)
        self.assertTrue(len(kws) >= 1)
        # ストップワードが含まれないことを確認
        for kw in kws:
            self.assertNotIn(kw, self.ho._STOP_WORDS)


# =====================================================================
# shorts_length_guard
# =====================================================================

class TestShortsLengthGuard(unittest.TestCase):

    def setUp(self):
        from pipeline import shorts_length_guard as slg
        self.slg = slg

    def _make_scenario(self, n_lines: int, chars_per_line: int) -> list:
        return [{"text": "あ" * chars_per_line, "speaker": "テスト"} for _ in range(n_lines)]

    def test_estimate_duration(self):
        scenario = self._make_scenario(8, 36)  # 288 chars
        dur = self.slg.estimate_duration(scenario)
        # 288 / 8.9 ≒ 32.4 + 8*0.3=2.4 + 1.6 ≒ 36.4
        self.assertGreater(dur, 30)
        self.assertLess(dur, 45)

    def test_check_scenario_ok(self):
        # 8 lines * 36 chars = 288 chars ≒ 36 seconds — within daily-science range (30-50)
        scenario = self._make_scenario(8, 36)
        result = self.slg.check_scenario("daily-science", scenario)
        self.assertTrue(result["ok"])

    def test_check_scenario_too_short(self):
        # 5 lines * 20 chars = 100 chars ≒ 14 seconds
        scenario = self._make_scenario(5, 20)
        result = self.slg.check_scenario("daily-science", scenario)
        self.assertFalse(result["ok"])
        self.assertIn("下回る", result["warning"])

    def test_check_scenario_too_long(self):
        # 10 lines * 50 chars = 500 chars ≒ 60 seconds
        scenario = self._make_scenario(10, 50)
        result = self.slg.check_scenario("daily-science", scenario)
        self.assertFalse(result["ok"])
        self.assertIn("超過", result["warning"])

    def test_guard_strict_raises(self):
        scenario = self._make_scenario(10, 50)  # too long
        with self.assertRaises(ValueError):
            self.slg.guard("daily-science", scenario, strict=True)

    def test_guard_non_strict_passes(self):
        scenario = self._make_scenario(10, 50)  # too long
        result = self.slg.guard("daily-science", scenario, strict=False)
        self.assertFalse(result["ok"])
        # Should not raise

    def test_estimate_completion_rate(self):
        self.assertGreater(self.slg.estimate_completion_rate(20), 0.8)
        self.assertLess(self.slg.estimate_completion_rate(55), 0.55)

    def test_channel_specific_ranges(self):
        # scp-lab allows longer (35-55) vs pokemon-lab (30-45)
        scenario = self._make_scenario(8, 45)  # ~46 seconds
        scp_result = self.slg.check_scenario("scp-lab", scenario)
        poke_result = self.slg.check_scenario("pokemon-lab", scenario)
        # Should be OK for scp but potentially over for pokemon
        self.assertTrue(scp_result["ok"])


# =====================================================================
# theme_queue prioritize_trending
# =====================================================================

class TestThemeQueuePrioritize(unittest.TestCase):

    def setUp(self):
        from pipeline.auto_scenario import theme_queue as tq
        self.tq = tq
        self.tmpdir = tempfile.mkdtemp()
        self._orig_data_root = tq._data_root

    def tearDown(self):
        self.tq._data_root = self._orig_data_root
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_prioritize_trending_moves_to_front(self):
        channel_id = "test-channel"
        channel_dir = Path(self.tmpdir) / channel_id
        channel_dir.mkdir(parents=True, exist_ok=True)

        # Override data root
        self.tq._data_root = lambda: Path(self.tmpdir)

        # Build a queue with mixed trending/non-trending items
        queue = self.tq._empty_queue(channel_id)
        queue["items"] = [
            {"id": "a", "title": "Non-trending 1", "is_trending": False, "trend_score": None},
            {"id": "b", "title": "Non-trending 2", "is_trending": False, "trend_score": None},
            {"id": "c", "title": "Trending low", "is_trending": True, "trend_score": 0.5},
            {"id": "d", "title": "Non-trending 3", "is_trending": False, "trend_score": None},
            {"id": "e", "title": "Trending high", "is_trending": True, "trend_score": 0.9},
        ]
        self.tq.save_queue(channel_id, queue)

        # Prioritize
        result = self.tq.prioritize_trending(channel_id)

        # Trending items should be first, sorted by score descending
        items = result["items"]
        self.assertEqual(items[0]["id"], "e")  # highest trend_score
        self.assertEqual(items[1]["id"], "c")  # lower trend_score
        # Non-trending maintain original order
        self.assertEqual(items[2]["id"], "a")
        self.assertEqual(items[3]["id"], "b")
        self.assertEqual(items[4]["id"], "d")

    def test_prioritize_no_trending(self):
        channel_id = "test-no-trend"
        channel_dir = Path(self.tmpdir) / channel_id
        channel_dir.mkdir(parents=True, exist_ok=True)
        self.tq._data_root = lambda: Path(self.tmpdir)

        queue = self.tq._empty_queue(channel_id)
        queue["items"] = [
            {"id": "a", "title": "Item 1", "is_trending": False},
            {"id": "b", "title": "Item 2", "is_trending": False},
        ]
        self.tq.save_queue(channel_id, queue)

        result = self.tq.prioritize_trending(channel_id)
        self.assertEqual(result["items"][0]["id"], "a")
        self.assertEqual(result["items"][1]["id"], "b")


# =====================================================================
# Channel config validation
# =====================================================================

class TestChannelConfigs(unittest.TestCase):
    """チャンネル設定の改善が正しく適用されているか検証。"""

    CHANNELS_DIR = Path(__file__).parent.parent.parent / "data" / "channels"
    TARGET_CHANNELS = [
        "daily-science", "scp-lab", "2ch-matome", "company-facts",
        "pokemon-lab", "yokai-watch", "akashic-librarian", "fake-paper",
    ]

    def _load(self, channel_id: str) -> dict:
        p = self.CHANNELS_DIR / f"{channel_id}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def test_all_channels_have_short_title_hashtags(self):
        for ch in self.TARGET_CHANNELS:
            cfg = self._load(ch)
            defaults = cfg.get("defaults") or {}
            val = defaults.get("short_title_hashtags")
            self.assertIsNotNone(
                val, f"{ch} missing defaults.short_title_hashtags"
            )
            self.assertIn("#shorts", val.lower(), f"{ch} short_title_hashtags missing #shorts")

    def test_all_channels_have_auto_optimize_schedule(self):
        for ch in self.TARGET_CHANNELS:
            cfg = self._load(ch)
            ap = cfg.get("autopilot") or {}
            self.assertIn(
                "auto_optimize_schedule", ap,
                f"{ch} missing autopilot.auto_optimize_schedule"
            )
            self.assertTrue(
                ap["auto_optimize_schedule"],
                f"{ch} autopilot.auto_optimize_schedule should be true"
            )


if __name__ == "__main__":
    unittest.main()
