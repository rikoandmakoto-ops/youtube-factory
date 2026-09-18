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
        # 2026-09-18 再校正: 288 / 6.95 ≒ 41.4 + 8*0.3=2.4 + 1.6 ≒ 45.4
        # （旧 8.9字/秒 前提では 36.4 と見積もっていたが、実尺と 1.28 倍ずれていた）
        self.assertGreater(dur, 30)
        self.assertLess(dur, 50)

    def test_check_scenario_ok(self):
        # 6 lines * 30 chars = 180 chars — daily-science の short_format
        # (2026-09-18 再校正後: 165〜195字 ≒ 29秒) のど真ん中。
        scenario = self._make_scenario(6, 30)
        result = self.slg.check_scenario("daily-science", scenario)
        self.assertTrue(result["ok"], result["warning"])

    def test_check_scenario_too_short(self):
        # 5 lines * 20 chars = 100 chars
        scenario = self._make_scenario(5, 20)
        result = self.slg.check_scenario("daily-science", scenario)
        self.assertFalse(result["ok"])
        self.assertIn("下回る", result["warning"])

    def test_check_scenario_too_long(self):
        # 10 lines * 50 chars = 500 chars
        scenario = self._make_scenario(10, 50)
        result = self.slg.check_scenario("daily-science", scenario)
        self.assertFalse(result["ok"])
        self.assertIn("超過", result["warning"])

    def test_band_follows_channel_short_format(self):
        """帯は channel JSON の short_format から引く（二重管理しない）。

        以前このモジュールは 30〜55秒 という独自の帯を持っており、08-25 に
        short_format 側が短尺へ差し戻された後もそこだけ旧仮説のまま残った。
        結果、規約どおりの 6行200字 の台本が毎回「下限を下回る」と警告され、
        suggestion が実測で否定された「加筆」を勧め続けていた。
        """
        import json
        from pathlib import Path

        channels_dir = Path(self.slg.CHANNELS_DIR)
        for path in sorted(channels_dir.glob("*.json")):
            conf = json.loads(path.read_text(encoding="utf-8"))
            sf = conf.get("short_format") or {}
            lo, hi = sf.get("total_chars_min"), sf.get("total_chars_max")
            if not (isinstance(lo, int) and isinstance(hi, int)):
                continue
            self.assertEqual(
                (lo, hi), self.slg.char_band_for(path.stem),
                f"{path.stem}: guard の帯が short_format とズレている",
            )

    def test_short_format_scenario_passes_for_every_channel(self):
        """各チャンネルの規約どおりに書いた台本がガードを通ること。"""
        import json
        from pathlib import Path

        channels_dir = Path(self.slg.CHANNELS_DIR)
        for path in sorted(channels_dir.glob("*.json")):
            conf = json.loads(path.read_text(encoding="utf-8"))
            sf = conf.get("short_format") or {}
            lo, hi = sf.get("total_chars_min"), sf.get("total_chars_max")
            n = sf.get("line_count")
            if not (isinstance(lo, int) and isinstance(hi, int) and isinstance(n, int)):
                continue
            mid = (lo + hi) // 2
            scenario = self._make_scenario(n, mid // n)
            result = self.slg.check_scenario(path.stem, scenario)
            self.assertTrue(result["ok"], f"{path.stem}: {result['warning']}")

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
        # 08-25 実測の回帰 維持率(%) = 89.0 - 0.1612 × 字数 に一致すること。
        # 旧テーブル（20秒→90%）は実測より大幅に楽観的だった。
        self.assertGreater(self.slg.estimate_completion_rate(20), 0.55)
        self.assertLess(self.slg.estimate_completion_rate(55), 0.35)
        # 実測の再現: 180字→60.0%（実測60.2〜72.2%）、370字→29.4%（実測29.3〜29.8%）
        self.assertAlmostEqual(
            self.slg.estimate_completion_rate_from_chars(180), 0.600, places=2)
        self.assertAlmostEqual(
            self.slg.estimate_completion_rate_from_chars(370), 0.294, places=2)

    def test_channel_specific_ranges(self):
        # 帯はチャンネルごとに違う。daily-science（長め 175〜225）では通る字数が
        # scp-lab（短め 165〜210）では超過になること。字数は config から引く。
        # 2026-09-01: 長い側は fake-paper だったが、維持率27.6%（全ch最下位）の
        # 是正で 190〜235 → 170〜210 に詰めたため scp-lab と上限が並んだ。
        # このテストが見たいのは「帯がチャンネルごとに違うこと」なので、
        # 現に帯の広いチャンネルに差し替える。
        # 2026-09-18: daily-science を 165〜195 に詰めて scp-lab と上限が並んだため、
        # 長い側を company-facts（165〜210）に差し替えた。company-facts だけ帯が広いのは
        # facts_overlay 形式で読み上げ速度が 5.44字/秒 と遅く、同じ字数でも尺が長いため。
        long_lo, long_hi = self.slg.char_band_for("company-facts")
        short_lo, short_hi = self.slg.char_band_for("scp-lab")
        self.assertGreater(long_hi, short_hi, "前提: company-facts のほうが長い帯")
        target = max(long_lo, short_hi + 10)
        self.assertLessEqual(target, long_hi, "前提: 2チャンネルの帯が重なりすぎ")
        scenario = self._make_scenario(7, target // 7)
        self.assertTrue(self.slg.check_scenario("company-facts", scenario)["ok"])
        scp_result = self.slg.check_scenario("scp-lab", scenario)
        self.assertFalse(scp_result["ok"])
        self.assertIn("超過", scp_result["warning"])


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

    # 2026-08-22 の PDCA で実測ブーストに基づいて投稿時刻を固定した5ch。
    # 自動再最適化を有効のままにすると、この実測ベースの時刻が上書きされる。
    #   scp-lab 09:00(+20.0%) / daily-science 17:00(+26.2%)
    #   pokemon-lab 18:00(+30.3%) / yokai-watch 19:00(+48.9%) / 2ch-matome 18:00(+26.3%)
    MEASURED_SCHEDULE_CHANNELS = [
        "daily-science", "scp-lab", "2ch-matome", "pokemon-lab", "yokai-watch",
    ]

    def test_all_channels_have_auto_optimize_schedule(self):
        for ch in self.TARGET_CHANNELS:
            cfg = self._load(ch)
            ap = cfg.get("autopilot") or {}
            self.assertIn(
                "auto_optimize_schedule", ap,
                f"{ch} missing autopilot.auto_optimize_schedule"
            )

    def test_measured_schedule_channels_are_pinned(self):
        """実測で投稿時刻を決めた5chは自動再最適化を切ったままにする。

        2026-09-01: pokemon-lab だけ data/channels 側で true に戻っており
        （data/channels_orchestrator 側は false）、08-22 の決定と食い違っていた。
        設定ディレクトリの二重管理をやめたうえで false に戻した。
        """
        for ch in self.MEASURED_SCHEDULE_CHANNELS:
            ap = self._load(ch).get("autopilot") or {}
            self.assertFalse(
                ap.get("auto_optimize_schedule"),
                f"{ch} autopilot.auto_optimize_schedule は false のままにすること"
                "（08-22 の実測ベース投稿時刻が上書きされる）",
            )


if __name__ == "__main__":
    unittest.main()
