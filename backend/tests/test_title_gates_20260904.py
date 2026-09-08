"""2026-09-04 に入れた機械ゲートのテスト。

  1. title_constraints  — 自然文では守られなかったタイトル規約の決定論的な検査/修復
  2. cross_channel_gate — 同日・全ch横断で同一キーワードは既定2本まで
  3. 実チャンネル設定   — yokai-watch / pokemon-lab / fake-paper のキューが規約を満たすこと
"""
import json
import unittest
from pathlib import Path

from pipeline import title_constraints as tc
from pipeline.auto_scenario import cross_channel_gate as ccg

CHANNELS = Path(__file__).resolve().parent.parent.parent / "data" / "channels"

YOKAI = {"title_rules": {"hard_constraints": {"forbid_digits": True, "max_chars": 30}}}
POKE = {"title_rules": {"hard_constraints": {
    "max_digit_groups": 1,
    "forbid_prefixes": ["なぜ", "何故", "なんで", "どうして"],
    "max_chars": 30,
}}}


class TitleConstraintTest(unittest.TestCase):
    def test_no_constraints_means_no_gate(self):
        self.assertTrue(tc.check("なぜ3つの正体？", {})["ok"])
        self.assertFalse(tc.is_enforced({}))

    def test_forbid_digits_detects_halfwidth_and_fullwidth(self):
        self.assertFalse(tc.check("妖怪ファイル #12 の話", YOKAI)["ok"])
        self.assertFalse(tc.check("妖怪ファイル ＃１２ の話", YOKAI)["ok"])
        self.assertTrue(tc.check("座敷童子が去った家の言い伝え", YOKAI)["ok"])

    def test_forbid_digits_repair_produces_a_passing_title(self):
        bad = "1分妖怪ファイル #12：座敷童子の3つの秘密"
        fixed = tc.repair(bad, YOKAI)
        self.assertTrue(tc.check(fixed, YOKAI)["ok"], fixed)
        self.assertNotIn("#", fixed)
        self.assertIn("座敷童子", fixed)

    def test_max_digit_groups_allows_exactly_one(self):
        self.assertTrue(tc.check("イーブイが8方向に進化する設定", POKE)["ok"])
        self.assertFalse(tc.check("特防190と種族値48の関係", POKE)["ok"])
        fixed = tc.repair("ピカチュウの3つの技と127の謎と5匹", POKE)
        self.assertTrue(tc.check(fixed, POKE)["ok"], fixed)

    def test_forbid_prefix_rewrites_why_titles(self):
        for bad in ["なぜピカチュウは電気を出すのか？",
                    "どうしてイーブイは進化先が多いの？",
                    "なぜカビゴンは眠り続けるのだろうか"]:
            self.assertFalse(tc.check(bad, POKE)["ok"])
            fixed = tc.repair(bad, POKE)
            self.assertTrue(tc.check(fixed, POKE)["ok"], fixed)
            self.assertFalse(fixed.startswith("なぜ"))
            self.assertGreaterEqual(len(fixed), 8)

    def test_banned_words(self):
        ch = {"title_rules": {"hard_constraints": {"banned_words": ["iPhone", "マック"]}}}
        self.assertFalse(tc.check("iPhoneの充電器は無限エネルギー", ch)["ok"])
        self.assertTrue(tc.check("充電器は無限エネルギー", ch)["ok"])

    def test_repair_never_returns_a_degenerate_title(self):
        # 全部が数字のタイトルは削ると空になる。元のまま返す（違反は残るが空よりまし）。
        self.assertEqual(tc.repair("12345", YOKAI), "12345")


class CrossChannelGateTest(unittest.TestCase):
    def setUp(self):
        self._orig = ccg._STATE_PATH
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        ccg._STATE_PATH = Path(self._tmp.name) / "cross.json"

    def tearDown(self):
        ccg._STATE_PATH = self._orig
        self._tmp.cleanup()

    def test_third_use_of_a_topic_keyword_is_blocked(self):
        self.assertEqual(ccg.check_and_reserve("scp-lab", "ファミマの収容記録")[0], True)
        self.assertEqual(ccg.check_and_reserve("yokai-watch", "ファミマの言い伝え")[0], True)
        ok, hit = ccg.check_and_reserve("pokemon-lab", "ファミマの限定グッズ")
        self.assertFalse(ok)
        self.assertEqual(hit[0], "ファミマ")

    def test_answer_markers_get_a_larger_daily_budget(self):
        """答え提示語は話題語より上限が高い（→ ANSWER_MARKER_DAILY_LIMIT）。

        6ch × 3枠 = 18本/日 に対し 9語 × 上限2 = 18 では余裕がゼロで、
        少しでも偏ると必ずブロックが出る。共食いするのは題材であって
        「正体」のような煽り語ではないので、語の枠だけ広げてある。
        """
        self.assertGreater(ccg.ANSWER_MARKER_DAILY_LIMIT, ccg.KEYWORD_DAILY_LIMIT)
        self.assertEqual(ccg.check_and_reserve("scp-lab", "収容違反の正体")[0], True)
        self.assertEqual(ccg.check_and_reserve("yokai-watch", "河童の正体")[0], True)
        # 3本目までは通る
        self.assertEqual(ccg.check_and_reserve("pokemon-lab", "ミュウツーの正体")[0], True)
        ok, hit = ccg.check_and_reserve("daily-science", "しゃっくりの正体")
        self.assertFalse(ok)
        self.assertEqual(hit[0], "正体")

    def test_one_generation_consumes_only_one_slot(self):
        """1本の生成は、題名が書き換わっても枠を1つしか使わない。

        テーマ取り出し時（キューの題名）と最終タイトル確定時（LLM が書き直した
        題名）で予約が2回走る。key が無いと別物として積まれ、1本で枠を2つ食う。
        09-07 に横断ゲートが114回発動した主因。
        """
        key = ccg.reservation_key("daily-science", "喉が鉄の味になる正体")
        ccg.reserve("daily-science", "喉が鉄の味になる正体", key=key)
        ccg.reserve("daily-science", "走った後の鉄味、その正体", key=key)
        entries = (ccg._load().get("used") or {}).get("正体") or []
        self.assertEqual(len(entries), 1)

    def test_rewriting_a_title_releases_the_dropped_keyword(self):
        """書き直しで語が消えたら、その語の枠は返る。"""
        key = ccg.reservation_key("scp-lab", "収容違反の正体")
        ccg.reserve("scp-lab", "収容違反の正体", key=key)
        ccg.reserve("scp-lab", "収容違反で何が起きたか", key=key)
        self.assertEqual((ccg._load().get("used") or {}).get("正体"), None)

    def test_unrelated_titles_are_not_blocked(self):
        for cid, t in [("a", "河童の正体"), ("b", "天狗の正体")]:
            ccg.check_and_reserve(cid, t)
        self.assertTrue(ccg.check_and_reserve("c", "ミュウツーが人を信じない経緯")[0])

    def test_same_channel_same_title_retry_is_not_self_blocking(self):
        ccg.check_and_reserve("scp-lab", "収容違反の記録")
        ccg.check_and_reserve("scp-lab", "収容違反の記録")
        self.assertIsNone(ccg.blocking_keyword("scp-lab", "収容違反の記録"))

    def test_boilerplate_words_are_not_counted(self):
        # チャンネル定型語（妖怪 / 財団 …）で埋まらないこと
        self.assertNotIn("妖怪", ccg.extract_keywords("妖怪の言い伝え"))
        self.assertNotIn("scp", ccg.extract_keywords("SCPの記録"))


class RealChannelConfigTest(unittest.TestCase):
    """実際のチャンネル設定が、自分で宣言した機械ゲートを満たしていること。"""

    def _load(self, cid):
        return json.loads((CHANNELS / f"{cid}.json").read_text(encoding="utf-8"))

    def test_enforced_channels_have_clean_queues_and_seeds(self):
        """テーマ（題材）が**禁止系**の制約に触れていないこと。

        2026-09-09: `require_any_of`（答え提示語を必ず含む）は対象外にする。
        キューに入っているのは題材であって最終タイトルではなく、答え提示語は
        generator がタイトルを組み立てる段で入れる。題材にまで必須化すると
        「〜の理由」を全題材の語尾に貼るだけになり、意味が無い。
        （2ch-matome だけは施策として題材レベルで結論型に揃えてあり、そちらは
        tests/test_fixes_20260909.py::TestNichanThemeSeeds が見ている。）
        """
        for cid in ("yokai-watch", "pokemon-lab", "fake-paper"):
            d = self._load(cid)
            self.assertTrue(tc.is_enforced(d), cid)
            titles = [t.get("title", "") for t in
                      (d.get("autopilot") or {}).get("theme_queue") or []]
            titles += [(s.get("title") if isinstance(s, dict) else s)
                       for s in (d.get("theme_seeds") or [])]
            bad = [t for t in titles if t and any(
                v["rule"] != "require_any_of" for v in tc.check(t, d)["violations"])]
            self.assertEqual(bad, [], f"{cid} に規約違反のテーマが残っている: {bad}")

    def test_every_channel_declares_the_single_decision_metric(self):
        from pipeline import optimization_policy as op
        for path in sorted(CHANNELS.glob("*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(op.primary_metric(d), "subs_per_1000_views", path.name)
            self.assertFalse(op.is_decision_metric(d, "retention"), path.name)

    def test_autopilot_slots_respect_the_burst_guard(self):
        """同一チャンネル内の枠は 90 分以上あけること（連投ガードに落ちるため）。"""
        from collections import defaultdict
        for path in sorted(CHANNELS.glob("*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            times = ((d.get("autopilot") or {}).get("schedule") or {}).get("times") or []
            by_day = defaultdict(list)
            for t in times:
                for dow in t.get("days_of_week", list(range(7))):
                    by_day[dow].append(t["hour"] * 60 + t.get("minute", 0))
            for dow, mins in by_day.items():
                mins.sort()
                for a, b in zip(mins, mins[1:]):
                    self.assertGreaterEqual(
                        b - a, 90,
                        f"{path.name} dow={dow}: 枠が {b - a} 分しか離れていない")


if __name__ == "__main__":
    unittest.main()
