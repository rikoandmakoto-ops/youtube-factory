"""Round 8 features テスト — Engagement & Subscriber Maximizer Suite.

テスト対象:
    1. curiosity_gap_enforcer     — 冒頭情報ギャップ強制
    2. comment_bait_injector      — コメント誘発注入
    3. emotional_polarity_alternator — 感情極性交互化
    4. pattern_interrupt_injector  — 話法パターン中断
    5. subscribe_trigger_optimizer — 登録トリガー最適化
    6. contrast_amplifier          — コントラスト増幅
    7. round8_enhancer             — 統合オーケストレーター
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# =====================================================================
# Helper: テスト用シナリオ生成
# =====================================================================

def _make_scenario(lines, speaker="理子"):
    """テスト用のシナリオ行リストを生成。"""
    return [{"speaker": speaker, "text": line} for line in lines]


# 情報ギャップなし（平叙文のみ）
SCENARIO_NO_GAP = _make_scenario([
    "今日は面白い話をします",
    "ある科学者が実験をした",
    "その結果がこちらだ",
    "驚くべき数値が出た",
    "つまりこういうことだった",
    "この発見は重要だ",
    "以上です",
])

# 情報ギャップあり
SCENARIO_WITH_GAP = _make_scenario([
    "なぜ人間は宇宙で生きられないのか？",
    "その理由は意外なものだった",
    "まず気圧の問題がある",
    "次に放射線の問題だ",
    "しかし最も致命的なのは別の要因だ",
    "それは温度変化だ",
])

# 単調シナリオ（全部平叙文）
SCENARIO_MONOTONE = _make_scenario([
    "この会社は1950年に設立された",
    "創業者は田中太郎という人物だった",
    "最初の製品は小さなラジオだった",
    "その後テレビ事業に参入した",
    "1980年に海外展開を始めた",
    "現在は売上1兆円の大企業になった",
    "従業員数は10万人を超えている",
])

# 感情ポジティブ連続
SCENARIO_ALL_POSITIVE = _make_scenario([
    "すごい発見があった！",
    "これは最高の成果だ！",
    "天才的なアイデアだった！",
    "面白すぎる結果になった！",
    "素晴らしい展開だ！",
    "最強の理論が完成した！",
])

# 2chシナリオ
SCENARIO_2CH = _make_scenario([
    "上司「お前の仕事、AIで代替できるぞ」",
    "ワイ「マジすか」",
    "上司「だからリストラな」",
    "ワイ「ちょ待てよ」",
    "友達に相談した結果ｗｗｗ",
    "まさかの展開にｗｗｗ",
    "結局ワイが社長になった話",
], speaker="ユイ")

# 対比構造あり
SCENARIO_WITH_CONTRAST = _make_scenario([
    "みんなはこう思っている",
    "しかし実はそうじゃなかった",
    "データを見ると全く逆の結果が出た",
    "つまり常識は間違いだった",
    "これが真実だ",
])


# =====================================================================
# 1. Curiosity Gap Enforcer
# =====================================================================

class TestCuriosityGapEnforcer(unittest.TestCase):

    def setUp(self):
        from pipeline.curiosity_gap_enforcer import (
            enforce_curiosity_gap,
            _has_gap,
            _has_answer,
        )
        self.enforce = enforce_curiosity_gap
        self.has_gap = _has_gap
        self.has_answer = _has_answer

    def test_detect_gap_question(self):
        self.assertTrue(self.has_gap("なぜ空は青いの？"))

    def test_detect_gap_reveal(self):
        self.assertTrue(self.has_gap("実はこれ、とんでもない秘密がある"))

    def test_no_gap_plain(self):
        self.assertFalse(self.has_gap("今日は天気がいい"))

    def test_detect_answer(self):
        self.assertTrue(self.has_answer("答えはこれだ"))

    def test_inject_gap_when_missing(self):
        scenario = _make_scenario([
            "今日は面白い話をします",
            "ある科学者が実験をした",
            "結果が出た",
            "以上",
        ])
        result = self.enforce(scenario, channel_id="daily-science")
        self.assertTrue(result["gap_injected"])
        # 冒頭にギャップが注入されていること
        first_text = scenario[0]["text"]
        self.assertTrue(self.has_gap(first_text) or "…" in first_text)

    def test_no_inject_when_gap_exists(self):
        scenario = _make_scenario([
            "なぜこれが起きたのか？",
            "その理由を解説する",
            "答えはここにある",
        ])
        result = self.enforce(scenario, channel_id="daily-science")
        self.assertTrue(result["gap_found"])
        self.assertFalse(result["gap_injected"])

    def test_early_answer_detection(self):
        scenario = _make_scenario([
            "なぜ空は青い？",
            "答えは光の散乱だ",
            "レイリー散乱という現象",
            "以上",
        ])
        result = self.enforce(scenario, channel_id="daily-science")
        self.assertTrue(result["early_answer"])
        self.assertEqual(result["early_answer_line"], 1)

    def test_too_short_scenario(self):
        scenario = _make_scenario(["短い", "テスト"])
        result = self.enforce(scenario, channel_id="daily-science")
        self.assertFalse(result["gap_injected"])

    def test_all_channels(self):
        channels = ["daily-science", "scp-lab", "2ch-matome",
                     "company-facts", "pokemon-lab", "yokai-watch", "akashic"]
        for ch in channels:
            scenario = _make_scenario([
                "普通の文章です",
                "何もないよ",
                "特に面白くもない",
                "おしまい",
            ])
            result = self.enforce(scenario, channel_id=ch)
            self.assertTrue(result["gap_injected"], f"Gap not injected for {ch}")


# =====================================================================
# 2. Comment Bait Injector
# =====================================================================

class TestCommentBaitInjector(unittest.TestCase):

    def setUp(self):
        from pipeline.comment_bait_injector import (
            inject_comment_bait,
            _has_existing_bait,
        )
        self.inject = inject_comment_bait
        self.has_bait = _has_existing_bait

    def test_inject_bait(self):
        scenario = list(SCENARIO_MONOTONE)  # copy
        scenario = [dict(e) for e in scenario]
        result = self.inject(scenario, channel_id="daily-science")
        self.assertTrue(result["bait_injected"])
        self.assertGreater(result["position"], 0)

    def test_skip_when_bait_exists(self):
        scenario = _make_scenario([
            "これは面白い話",
            "みんなはどう思う？コメントで教えて",
            "意見分かれると思う",
            "以上",
        ])
        result = self.inject(scenario, channel_id="daily-science")
        self.assertTrue(result["existing_bait"])
        self.assertFalse(result["bait_injected"])

    def test_bait_position_in_range(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.inject(scenario, channel_id="company-facts")
        if result["bait_injected"]:
            n = len(scenario)
            self.assertGreaterEqual(result["position"], int(n * 0.5))
            self.assertLessEqual(result["position"], n - 1)

    def test_2ch_bait(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.inject(scenario, channel_id="2ch-matome")
        self.assertTrue(result["bait_injected"])


# =====================================================================
# 3. Emotional Polarity Alternator
# =====================================================================

class TestEmotionalPolarityAlternator(unittest.TestCase):

    def setUp(self):
        from pipeline.emotional_polarity_alternator import (
            alternate_emotional_polarity,
            _classify_polarity,
        )
        self.alternate = alternate_emotional_polarity
        self.classify = _classify_polarity

    def test_classify_positive(self):
        self.assertEqual(self.classify("すごい発見だ。面白すぎる"), "positive")

    def test_classify_negative(self):
        self.assertEqual(self.classify("恐ろしい事件が起きた"), "negative")

    def test_classify_surprise(self):
        self.assertEqual(self.classify("実はこれ衝撃の事実！"), "surprise")

    def test_classify_neutral(self):
        self.assertEqual(self.classify("今日は水曜日です"), "neutral")

    def test_detect_positive_streak(self):
        scenario = [dict(e) for e in SCENARIO_ALL_POSITIVE]
        result = self.alternate(scenario, channel_id="daily-science")
        self.assertGreater(result["streaks_found"], 0)

    def test_inject_breaker(self):
        scenario = [dict(e) for e in SCENARIO_ALL_POSITIVE]
        result = self.alternate(scenario, channel_id="daily-science")
        self.assertGreater(result["breakers_injected"], 0)

    def test_neutral_no_action(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.alternate(scenario, channel_id="daily-science")
        # neutral連続はstreakとしてカウントしない
        self.assertEqual(result["streaks_found"], 0)


# =====================================================================
# 4. Pattern Interrupt Injector
# =====================================================================

class TestPatternInterruptInjector(unittest.TestCase):

    def setUp(self):
        from pipeline.pattern_interrupt_injector import (
            inject_pattern_interrupts,
            _classify_ending,
        )
        self.inject = inject_pattern_interrupts
        self.classify = _classify_ending

    def test_classify_question(self):
        self.assertEqual(self.classify("本当にそうなの？"), "question")

    def test_classify_exclaim(self):
        self.assertEqual(self.classify("ヤバい！"), "exclaim")

    def test_classify_statement(self):
        self.assertEqual(self.classify("これは事実だ。"), "statement")

    def test_classify_ellipsis(self):
        self.assertEqual(self.classify("ところが…"), "ellipsis")

    def test_detect_monotone_statements(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.inject(scenario, channel_id="company-facts")
        self.assertGreater(result["monotone_runs"], 0)

    def test_inject_interrupts(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.inject(scenario, channel_id="company-facts")
        self.assertGreater(result["interrupts_injected"], 0)

    def test_variety_score(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.inject(scenario, channel_id="daily-science")
        self.assertGreater(result["variety_score"], 0.0)

    def test_2ch_more_interrupts(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.inject(scenario, channel_id="2ch-matome", max_interrupts=3)
        # max_interrupts=3 なので最大3個まで注入可能
        self.assertLessEqual(result["interrupts_injected"], 3)


# =====================================================================
# 5. Subscribe Trigger Optimizer
# =====================================================================

class TestSubscribeTriggerOptimizer(unittest.TestCase):

    def setUp(self):
        from pipeline.subscribe_trigger_optimizer import (
            optimize_subscribe_triggers,
        )
        self.optimize = optimize_subscribe_triggers

    def test_inject_trigger(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.optimize(scenario, channel_id="daily-science")
        self.assertTrue(result["injected"])
        self.assertIn(result["trigger_type"],
                       ["series_hint", "expertise_proof", "community_belong"])

    def test_position_by_type(self):
        # 複数回実行してポジション範囲をチェック
        for _ in range(10):
            scenario = [dict(e) for e in SCENARIO_MONOTONE]
            result = self.optimize(scenario, channel_id="scp-lab")
            if result["trigger_type"] == "series_hint":
                self.assertGreaterEqual(result["position"], len(scenario) - 3)

    def test_all_channels(self):
        channels = ["daily-science", "scp-lab", "2ch-matome",
                     "company-facts", "pokemon-lab", "yokai-watch", "akashic"]
        for ch in channels:
            scenario = [dict(e) for e in SCENARIO_MONOTONE]
            result = self.optimize(scenario, channel_id=ch)
            self.assertTrue(result["injected"], f"Trigger not injected for {ch}")

    def test_too_short(self):
        scenario = _make_scenario(["短い", "テスト"])
        result = self.optimize(scenario, channel_id="daily-science")
        self.assertFalse(result["injected"])


# =====================================================================
# 6. Contrast Amplifier
# =====================================================================

class TestContrastAmplifier(unittest.TestCase):

    def setUp(self):
        from pipeline.contrast_amplifier import (
            amplify_contrast,
            _has_contrast,
            _is_setup_line,
        )
        self.amplify = amplify_contrast
        self.has_contrast = _has_contrast
        self.is_setup = _is_setup_line

    def test_detect_contrast(self):
        self.assertTrue(self.has_contrast("しかし実は違っていた"))

    def test_detect_setup(self):
        self.assertTrue(self.is_setup("一般的にはこう思われている"))

    def test_no_contrast_plain(self):
        self.assertFalse(self.has_contrast("今日は天気がいい"))

    def test_amplify_existing_contrast(self):
        scenario = [dict(e) for e in SCENARIO_WITH_CONTRAST]
        result = self.amplify(scenario, channel_id="daily-science")
        self.assertGreater(result["contrasts_found"], 0)

    def test_inject_frame_when_no_contrast(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.amplify(scenario, channel_id="company-facts")
        self.assertTrue(result["frame_injected"])

    def test_contrast_score_range(self):
        scenario = [dict(e) for e in SCENARIO_WITH_CONTRAST]
        result = self.amplify(scenario, channel_id="daily-science")
        self.assertGreaterEqual(result["contrast_score"], 0.0)
        self.assertLessEqual(result["contrast_score"], 1.0)

    def test_all_channels(self):
        channels = ["daily-science", "scp-lab", "2ch-matome",
                     "company-facts", "pokemon-lab", "yokai-watch", "akashic"]
        for ch in channels:
            scenario = [dict(e) for e in SCENARIO_MONOTONE]
            result = self.amplify(scenario, channel_id=ch)
            self.assertTrue(result["frame_injected"], f"Frame not injected for {ch}")


# =====================================================================
# 7. Round 8 Enhancer (統合オーケストレーター)
# =====================================================================

class TestRound8Enhancer(unittest.TestCase):

    def setUp(self):
        from pipeline.round8_enhancer import enhance
        self.enhance = enhance

    def test_all_modules_run(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        result = self.enhance(
            scenario,
            title="テスト動画",
            channel_id="daily-science",
        )
        expected_keys = [
            "curiosity_gap", "comment_bait", "emotional_polarity",
            "pattern_interrupt", "subscribe_trigger", "contrast",
        ]
        for key in expected_keys:
            self.assertIn(key, result, f"Missing key: {key}")
            # error キーがないことを確認（成功している）
            self.assertNotIn("error", result[key],
                             f"{key} failed: {result[key].get('error')}")

    def test_all_channels_integration(self):
        channels = ["daily-science", "scp-lab", "2ch-matome",
                     "company-facts", "pokemon-lab", "yokai-watch", "akashic"]
        for ch in channels:
            scenario = [dict(e) for e in SCENARIO_MONOTONE]
            result = self.enhance(
                scenario,
                title=f"テスト_{ch}",
                channel_id=ch,
            )
            for key in result:
                self.assertNotIn("error", result[key] if isinstance(result[key], dict) else {},
                                 f"{key} failed for {ch}")

    def test_2ch_special_settings(self):
        scenario = [dict(e) for e in SCENARIO_2CH]
        result = self.enhance(
            scenario,
            title="2chテスト",
            channel_id="2ch-matome",
        )
        # エラーなく全モジュール実行されること
        for key, val in result.items():
            if isinstance(val, dict):
                self.assertNotIn("error", val, f"{key} failed for 2ch")

    def test_scenario_modified_in_place(self):
        scenario = [dict(e) for e in SCENARIO_MONOTONE]
        original_first = scenario[0]["text"]
        self.enhance(scenario, title="テスト", channel_id="daily-science")
        # 冒頭行はcuriosity_gapで変更されているはず
        self.assertNotEqual(scenario[0]["text"], original_first)


if __name__ == "__main__":
    unittest.main()
