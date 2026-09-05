"""2026-09-06 の修正の回帰テスト。

対象:
  1. 画像ブリッジ — スレッド URL の旧置き場（トップレベル）を読めること /
     既存 pending の宛先を貼り直せること
  2. dup_check の偽陽性 — ハッシュタグが類似度を支配しないこと。
     ただし `#21：` のような連番見出しは消さないこと
  3. theme_blacklist — `SCP-173` が `SCP-1730`〜`1739` を巻き添えにしないこと
  4. fact_ledger — 同じ会社の同じ指標の食い違いを検出できること
"""

import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# 1. 画像ブリッジ
# ---------------------------------------------------------------------------
class TestImageBridgeThreadResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["IMAGE_BRIDGE_DIR"] = str(self.tmp / "q")
        os.environ["IMAGE_BRIDGE_CHANNELS_DIR"] = str(self.tmp / "channels")
        (self.tmp / "channels").mkdir(parents=True)
        from pipeline import chatgpt_image_bridge
        # モジュールは import 時にディレクトリを定数へ焼くので reload が要る。
        self.bridge = importlib.reload(chatgpt_image_bridge)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("IMAGE_BRIDGE_DIR", None)
        os.environ.pop("IMAGE_BRIDGE_CHANNELS_DIR", None)
        from pipeline import chatgpt_image_bridge
        importlib.reload(chatgpt_image_bridge)

    def _write(self, channel_id, cfg):
        path = self.tmp / "channels" / f"{channel_id}.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def test_reads_legacy_top_level_thread_url(self):
        """09-05 の事故: URL がトップレベルに書かれていて誰も読めなかった。"""
        self._write("scp-lab", {"id": "scp-lab",
                                "chatgpt_thread_url": "https://chatgpt.com/c/legacy"})
        self.assertEqual(self.bridge.thread_url_for("scp-lab"),
                         "https://chatgpt.com/c/legacy")
        self.assertEqual(self.bridge.channels_missing_thread(), [])

    def test_canonical_block_wins_over_legacy(self):
        self._write("scp-lab", {
            "id": "scp-lab",
            "chatgpt_thread_url": "https://chatgpt.com/c/old",
            "image_generation": {"chatgpt_thread_url": "https://chatgpt.com/c/new"},
        })
        self.assertEqual(self.bridge.thread_url_for("scp-lab"),
                         "https://chatgpt.com/c/new")

    def test_set_thread_url_folds_away_legacy_key(self):
        self._write("scp-lab", {"id": "scp-lab",
                                "chatgpt_thread_url": "https://chatgpt.com/c/old"})
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/new")
        cfg = json.loads((self.tmp / "channels" / "scp-lab.json").read_text())
        self.assertNotIn("chatgpt_thread_url", cfg)
        self.assertEqual(cfg["image_generation"]["chatgpt_thread_url"],
                         "https://chatgpt.com/c/new")

    def test_backfill_fills_thread_url_on_existing_pending(self):
        """スレッド登録前に積まれた依頼は thread_url が空のまま残る。"""
        self._write("scp-lab", {"id": "scp-lab"})
        req = self.bridge.enqueue("a prompt", channel_id="scp-lab")
        self.assertEqual(req["thread_url"], "")
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/x")
        res = self.bridge.backfill_pending()
        self.assertEqual(res["thread_url_updated"], 1)
        self.assertEqual(res["still_without_thread"], [])
        self.assertEqual(self.bridge.pending_requests()[0]["thread_url"],
                         "https://chatgpt.com/c/x")

    def test_backfill_infers_channel_from_art_style(self):
        """channel_id が空の依頼を、プロンプト先頭の art_style から復元する。"""
        art = ("bright colorful pop illustration in a game-guidebook style — vivid "
               "saturated palette, confident clean outlines, flat cel shading")
        self._write("pokemon-lab", {
            "id": "pokemon-lab",
            "image_generation": {"chatgpt_thread_url": "https://chatgpt.com/c/pk"},
            "video_format": {"illustration_style": {"art_style": art}},
        })
        self.bridge.enqueue(f"{art}. Subject: a diagram.", channel_id=None)
        res = self.bridge.backfill_pending()
        self.assertEqual(res["channel_id_filled"], 1)
        req = self.bridge.pending_requests()[0]
        self.assertEqual(req["channel_id"], "pokemon-lab")
        self.assertEqual(req["thread_url"], "https://chatgpt.com/c/pk")


# ---------------------------------------------------------------------------
# 2. dup_check の偽陽性（ハッシュタグ）
# ---------------------------------------------------------------------------
from pipeline.auto_scenario import theme_dedup as td  # noqa: E402


class TestHashtagNormalization(unittest.TestCase):
    def test_hashtags_are_stripped(self):
        self.assertEqual(td.normalize_title("金魚の帰宅時刻 #shorts #架空論文"),
                         td.normalize_title("金魚の帰宅時刻"))

    def test_fullwidth_hash_is_stripped(self):
        self.assertEqual(td.normalize_title("金魚の帰宅時刻 ＃架空論文"),
                         td.normalize_title("金魚の帰宅時刻"))

    def test_shared_hashtags_no_longer_drive_similarity(self):
        """全動画に付く定型タグだけを共有する無関係な2本は重複ではない。"""
        a = "なぜ友達の風呂で3回もやらかしたのか？ｗ #shorts #2ch #面白い"
        b = "正体を大人が知る3秒の言葉あげてけw😂 #shorts #2ch #面白い"
        self.assertLess(td.similarity(a, b), 0.62)

    def test_series_number_is_not_treated_as_hashtag(self):
        """`#21：` は連番見出し。消すと別回同士が丸ごと一致してしまう。"""
        a = "1分ポケモン研究 #21：カビゴンが道を塞ぐ理由に隠された1日の秘密"
        b = "1分ポケモン研究 #13：グリーンに隠された3つの秘密、あなたは本当に"
        self.assertIn("21", td.normalize_title(a))
        self.assertLess(td.similarity(a, b), 0.62)

    def test_real_duplicates_still_caught(self):
        a = "止めようとすると余計ひどくなる…横隔膜が『暴走』する理由とは？ #shorts"
        b = "なぜ止まらない？横隔膜の暴走 #shorts"
        self.assertGreaterEqual(td.similarity(a, b), 0.62)


# ---------------------------------------------------------------------------
# 3. theme_blacklist の部分一致
# ---------------------------------------------------------------------------
class TestBlacklistMatching(unittest.TestCase):
    BL = ["SCP-173", "視線を外", "かまいたち"]

    def test_exact_object_number_matches(self):
        self.assertEqual(
            td.blacklist_match("一口SCP：SCP-173「彫刻」の記録", self.BL), "SCP-173")

    def test_longer_object_numbers_are_not_collateral(self):
        """SCP-1730〜1739 の10体が SCP-173 の部分一致で巻き添えになっていた。"""
        for n in range(1730, 1740):
            self.assertIsNone(
                td.blacklist_match(f"SCP-{n} の収容記録", self.BL),
                f"SCP-{n} が誤ってブロックされた")

    def test_shorter_number_does_not_match(self):
        self.assertIsNone(td.blacklist_match("SCP-17 の記録", self.BL))

    def test_non_numeric_terms_keep_substring_behaviour(self):
        self.assertEqual(td.blacklist_match("かまいたちの正体とは", self.BL), "かまいたち")

    def test_regex_prefix(self):
        self.assertIsNotNone(td.blacklist_match("SCP-173の記録", [r"re:SCP-?173(?![0-9])"]))
        self.assertIsNone(td.blacklist_match("SCP-1730の記録", [r"re:SCP-?173(?![0-9])"]))

    def test_invalid_regex_is_ignored_not_fatal(self):
        self.assertIsNone(td.blacklist_match("なんでもいい", ["re:[unclosed"]))

    def test_exact_prefix(self):
        self.assertIsNotNone(td.blacklist_match("大谷翔平", ["=大谷翔平"]))
        self.assertIsNone(td.blacklist_match("大谷翔平の年収", ["=大谷翔平"]))


# ---------------------------------------------------------------------------
# 4. fact_ledger
# ---------------------------------------------------------------------------
class TestFactLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["FACT_LEDGER_DIR"] = str(self.tmp)
        from pipeline import fact_ledger
        fl = importlib.reload(fact_ledger)
        self.fl = fl
        fl.record("company-facts", self._scenario("マック 年収576万円",
                                                  "2023年有価証券報告書",
                                                  "日本マクドナルド株式会社 店舗 外観"),
                  title="576万円の回")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("FACT_LEDGER_DIR", None)
        from pipeline import fact_ledger
        importlib.reload(fact_ledger)

    @staticmethod
    def _scenario(main, sub, bg):
        return {"short_scenario": [{"fact_main": main, "fact_sub": sub, "bg_query": bg}]}

    def test_holdings_and_operating_company_are_the_same_entity(self):
        """576万円 と 670万円 は表記違いの同一社。別会社扱いだと検出できない。"""
        claims = self.fl.extract_claims(
            self._scenario("マクド 年収670万円", "2024年12月期",
                           "日本マクドナルドホールディングス株式会社 本社"))
        self.assertEqual(claims[0]["entity"], "日本マクドナルド")

    def test_same_period_different_value_is_a_conflict(self):
        issues = self.fl.check("company-facts", self._scenario(
            "マック 年収610万円", "2023年有価証券報告書", "日本マクドナルド株式会社 店舗"))
        self.assertEqual([i["kind"] for i in issues], ["conflict"])

    def test_different_period_is_restated_with_the_period(self):
        s = self._scenario("マクド 年収670万円", "2024年12月期",
                           "日本マクドナルドホールディングス株式会社 本社")
        issues = self.fl.check("company-facts", s)
        self.assertEqual([i["kind"] for i in issues], ["restate"])
        self.assertEqual(self.fl.disclose_period(s, issues), 1)
        self.assertIn("2024年12月期", s["short_scenario"][0]["fact_main"])

    def test_same_period_same_value_is_silent(self):
        self.assertEqual(self.fl.check("company-facts", self._scenario(
            "マック 年収576万円", "2023年有価証券報告書", "日本マクドナルド株式会社 店舗")), [])

    def test_unknown_entity_is_silent(self):
        self.assertEqual(self.fl.check("company-facts", self._scenario(
            "ほげ社 年収500万円", "2023年", "ほげ株式会社 本社")), [])

    def test_multi_company_video_keeps_entities_separate(self):
        """1本で3社を比較する回。行ごとに会社を採らないと数字が混ざる。"""
        claims = self.fl.extract_claims({"short_scenario": [
            {"fact_main": "年収982万円", "fact_sub": "2024年3月期",
             "bg_query": "トヨタ自動車株式会社 本社"},
            {"fact_main": "年収1118万円", "fact_sub": "2024年3月期",
             "bg_query": "ソニーグループ株式会社 本社"},
        ]})
        self.assertEqual([c["entity"] for c in claims], ["トヨタ自動車", "ソニー"])

    def test_gate_is_off_unless_configured(self):
        self.assertFalse(self.fl.is_enforced({}))
        self.assertFalse(self.fl.is_enforced({"fact_consistency": {"enabled": False}}))
        self.assertTrue(self.fl.is_enforced({"fact_consistency": {"enabled": True}}))


if __name__ == "__main__":
    unittest.main()
