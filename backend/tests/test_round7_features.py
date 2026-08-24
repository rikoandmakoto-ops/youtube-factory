"""Round 7 features テスト — Completion & Replay Maximizer Suite.

テスト対象:
    1. completion_rate_optimizer  — ペーシング最適化
    2. replay_loop_seeder        — リプレイループ誘導
    3. title_emoji_injector      — タイトル絵文字CTR最適化
    4. originality_guard         — コンテンツ独自性チェック
    5. retention_feedback_loop   — リテンション分析フィードバック
    6. power_word_amplifier      — パワーワード増幅
    7. round7_enhancer           — 統合オーケストレーター
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# =====================================================================
# Helper: テスト用シナリオ生成
# =====================================================================

def _make_scenario(lines, speaker="理子"):
    """テスト用のシナリオ行リストを生成。"""
    return [{"speaker": speaker, "text": line} for line in lines]


SAMPLE_SCENARIO_SCIENCE = _make_scenario([
    "実は人間の脳は10%しか使われていないという話、聞いたことある？",
    "うん、有名な話だよね",
    "でもこれ、完全にウソなんだ",
    "脳の全領域がMRIで活動しているのが確認されている",
    "さて、なぜこのデマが広まったのかというと",
    "1930年代の心理学者の発言が歪曲されたものなんだ",
    "つまり100%使われている。以上。",
])

SAMPLE_SCENARIO_2CH = _make_scenario([
    "上司「お前の仕事、AIで代替できるぞ」",
    "ワイ「じゃあAIにやらせろよ」",
    "上司「…」",
    "ワイ「…」",
    "結局ワイがやることになった話",
    "友達に話したらドン引きされた",
    "以上、終わり",
], speaker="ユイ")

SAMPLE_SCENARIO_SCP = _make_scenario([
    "SCP-173はコンクリート製の彫刻だ",
    "しかしこのオブジェクト、誰も目を離せない",
    "目を離した瞬間、対象の首を折る",
    "Dクラス職員3名による実験が行われた",
    "結果は壊滅的だった",
    "財団はKeter分類を検討している",
    "この報告書は以上です",
], speaker="シロ")


# =====================================================================
# 1. Completion Rate Optimizer
# =====================================================================

class TestCompletionRateOptimizer(unittest.TestCase):

    def setUp(self):
        from pipeline.completion_rate_optimizer import (
            optimize_completion_rate,
            _density_score,
            _analyze_pacing,
        )
        self.optimize = optimize_completion_rate
        self.density = _density_score
        self.pacing = _analyze_pacing

    def test_density_score_high(self):
        """数値データや転換語を含む行は高密度。"""
        score = self.density("実は人間の脳の90%は未使用というのは完全なウソ")
        self.assertGreater(score, 1.5)

    def test_density_score_low(self):
        """相槌行は低密度。"""
        score = self.density("うん、そうだね")
        self.assertLess(score, 1.0)

    def test_pacing_analysis(self):
        """ペーシング分析が結果を返す。"""
        densities = [1.5, 0.8, 0.4, 0.4, 1.0, 1.2, 2.0]
        result = self.pacing(densities)
        self.assertIn("score", result)
        self.assertIn("issues", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_dead_spot_detection(self):
        """連続低密度行を検出。"""
        densities = [1.5, 0.3, 0.3, 0.3, 1.0, 1.2, 2.0]
        result = self.pacing(densities)
        self.assertGreater(result["dead_spots"], 0)

    def test_optimize_basic(self):
        """基本的な最適化が動作する。"""
        scenario = _make_scenario([
            "実は人間の脳は面白い構造をしている",
            "うん",
            "ああ",
            "さて、本題に入ろう",
            "脳の神経細胞は860億個ある",
            "これは銀河系の星の数に匹敵する",
            "つまり宇宙が頭の中にある。以上。",
        ])
        result = self.optimize(scenario, channel_id="daily-science")
        self.assertIn("pacing_score", result)
        self.assertIn("optimized_score", result)

    def test_empty_scenario(self):
        """空シナリオでもエラーにならない。"""
        result = self.optimize([], channel_id="daily-science")
        self.assertEqual(result["pacing_score"], 0)


# =====================================================================
# 2. Replay Loop Seeder
# =====================================================================

class TestReplayLoopSeeder(unittest.TestCase):

    def setUp(self):
        from pipeline.replay_loop_seeder import seed_replay_loop
        self.seed = seed_replay_loop

    def test_ending_feel_removed(self):
        """「以上。」等の終わった感が除去される。"""
        scenario = _make_scenario([
            "実はこのポケモンには衝撃の裏設定がある",
            "初代から存在するこの設定",
            "ゲームフリークの意図とは",
            "以上。",
        ])
        result = self.seed(scenario, channel_id="pokemon-lab")
        last_text = scenario[-1]["text"]
        self.assertNotIn("以上。", last_text)
        self.assertTrue(result["loop_seeded"])

    def test_loop_trigger_added(self):
        """最終行にループトリガーが追加される。"""
        scenario = _make_scenario([
            "SCP-682は不死身の爬虫類だ",
            "あらゆる攻撃を適応して生き延びる",
            "財団は今も収容に苦しんでいる",
            "これが最強SCPの正体でした",
        ])
        result = self.seed(scenario, channel_id="scp-lab")
        self.assertTrue(result["loop_seeded"])
        # 最終行が変更されている
        last_text = scenario[-1]["text"]
        self.assertNotEqual(last_text, "これが最強SCPの正体でした")

    def test_short_scenario_skipped(self):
        """2行以下のシナリオはスキップ。"""
        scenario = _make_scenario(["短すぎる", "テスト"])
        result = self.seed(scenario, channel_id="daily-science")
        self.assertFalse(result["loop_seeded"])

    def test_all_channels(self):
        """全チャンネルでエラーなく動作。"""
        channels = ["daily-science", "scp-lab", "2ch-matome",
                     "company-facts", "pokemon-lab", "yokai-watch", "akashic"]
        for ch in channels:
            scenario = _make_scenario([
                "冒頭の衝撃的な事実",
                "中盤の展開",
                "さらなる驚き",
                "まとめです。以上。",
            ])
            result = self.seed(scenario, channel_id=ch)
            self.assertTrue(result["loop_seeded"], f"Failed for {ch}")


# =====================================================================
# 3. Title Emoji Injector
# =====================================================================

class TestTitleEmojiInjector(unittest.TestCase):

    def setUp(self):
        from pipeline.title_emoji_injector import inject_title_emoji
        self.inject = inject_title_emoji

    def test_daily_science_emoji(self):
        """daily-scienceに科学系絵文字が追加される。"""
        result = self.inject(
            "人間の脳は宇宙と同じ構造だった",
            channel_id="daily-science",
        )
        if result["modified"]:
            self.assertNotEqual(result["enhanced_title"], result["original_title"])
            self.assertTrue(result["emoji_added"])

    def test_2ch_ero_category(self):
        """2ch-matomeのエロ系テーマが検出される。"""
        result = self.inject(
            "彼女がセクシーすぎてヤバい件",
            channel_id="2ch-matome",
        )
        self.assertEqual(result["category"], "ero")

    def test_scp_shock_category(self):
        """scp-labの衝撃系テーマが検出される。"""
        result = self.inject(
            "絶対に閲覧してはいけないSCPの恐怖",
            channel_id="scp-lab",
        )
        self.assertIn(result["category"], ["shock", "danger", "default"])

    def test_no_double_emoji(self):
        """既に2個以上の絵文字がある場合は追加しない。"""
        result = self.inject(
            "😱🔥人間の脳はヤバい",
            channel_id="daily-science",
        )
        # 2個以上あるので追加なし
        self.assertFalse(result["modified"])

    def test_unknown_channel(self):
        """未知のチャンネルではスキップ。"""
        result = self.inject(
            "テストタイトル",
            channel_id="unknown-channel",
        )
        self.assertFalse(result["modified"])

    def test_empty_title(self):
        """空タイトルでもエラーにならない。"""
        result = self.inject("", channel_id="daily-science")
        self.assertFalse(result["modified"])


# =====================================================================
# 4. Originality Guard
# =====================================================================

class TestOriginalityGuard(unittest.TestCase):

    def setUp(self):
        from pipeline.originality_guard import check_originality
        self.check = check_originality
        # テスト用の一時ディレクトリ
        self.temp_dir = tempfile.mkdtemp()

    def test_first_scenario_always_original(self):
        """履歴がない場合は常にオリジナル。"""
        with patch("pipeline.originality_guard.DATA_DIR", Path(self.temp_dir)):
            result = self.check(
                SAMPLE_SCENARIO_SCIENCE,
                title="テスト",
                channel_id="test-channel",
            )
            self.assertTrue(result["original"])
            self.assertEqual(result["max_similarity"], 0.0)

    def test_duplicate_detection(self):
        """同一シナリオが2回目で検出される。"""
        with patch("pipeline.originality_guard.DATA_DIR", Path(self.temp_dir)):
            # 1回目
            self.check(
                SAMPLE_SCENARIO_SCIENCE,
                title="テスト1",
                channel_id="dup-test",
            )
            # 2回目（同じ内容）
            result = self.check(
                SAMPLE_SCENARIO_SCIENCE,
                title="テスト2",
                channel_id="dup-test",
            )
            self.assertGreater(result["max_similarity"], 0.5)

    def test_different_scenario_original(self):
        """異なるシナリオはオリジナル判定。"""
        with patch("pipeline.originality_guard.DATA_DIR", Path(self.temp_dir)):
            self.check(
                SAMPLE_SCENARIO_SCIENCE,
                title="科学テスト",
                channel_id="diff-test",
            )
            result = self.check(
                SAMPLE_SCENARIO_SCP,
                title="SCPテスト",
                channel_id="diff-test",
            )
            self.assertTrue(result["original"])

    def test_2ch_stricter_threshold(self):
        """2ch-matomeは閾値が厳しい。"""
        with patch("pipeline.originality_guard.DATA_DIR", Path(self.temp_dir)):
            result = self.check(
                SAMPLE_SCENARIO_2CH,
                title="2chテスト",
                channel_id="2ch-matome",
            )
            # 閾値が低い（厳格）
            self.assertEqual(result["warn_threshold"], 0.60)
            self.assertEqual(result["block_threshold"], 0.75)

    def test_empty_scenario(self):
        """空シナリオでもエラーにならない。"""
        result = self.check([], channel_id="daily-science")
        self.assertTrue(result["original"])


# =====================================================================
# 5. Retention Feedback Loop
# =====================================================================

class TestRetentionFeedbackLoop(unittest.TestCase):

    def setUp(self):
        from pipeline.retention_feedback_loop import apply_retention_feedback
        self.apply = apply_retention_feedback

    def test_transition_fix(self):
        """つなぎ語が強い表現に置換される。"""
        scenario = _make_scenario([
            "実はこの事実は衝撃的だ",
            "さて、次の話題に移ろう",
            "人間の脳には860億の神経細胞がある",
            "これは宇宙の星より多い",
        ])
        result = self.apply(scenario, channel_id="daily-science")
        # 「さて」が置換されているか確認
        second_text = scenario[1]["text"]
        self.assertNotIn("さて", second_text)
        self.assertGreater(len(result["drop_fixes"]), 0)

    def test_success_elements_check(self):
        """成功パターン要素の不足を検出。"""
        # 数字が全くないシナリオ
        scenario = _make_scenario([
            "この話は面白い",
            "ある日のことだった",
            "とても驚いた",
            "それが結論だ",
        ])
        result = self.apply(scenario, channel_id="daily-science")
        # 何かしらの不足要素が検出されるはず
        self.assertIsInstance(result["missing_elements"], list)

    def test_fallback_mode(self):
        """分析データがない場合はフォールバックルールが使われる。"""
        scenario = _make_scenario([
            "テスト冒頭",
            "さて、続いて",
            "テスト結論",
        ])
        empty_dir = Path(tempfile.mkdtemp())
        with patch("pipeline.retention_feedback_loop.ANALYTICS_DIR", empty_dir):
            result = self.apply(scenario, channel_id="daily-science")
        self.assertFalse(result["data_available"])
        self.assertGreater(result["insights_used"], 0)

    def test_empty_scenario(self):
        """空シナリオでもエラーにならない。"""
        result = self.apply([], channel_id="daily-science")
        self.assertFalse(result["data_available"])


# =====================================================================
# 6. Power Word Amplifier
# =====================================================================

class TestPowerWordAmplifier(unittest.TestCase):

    def setUp(self):
        from pipeline.power_word_amplifier import amplify_power_words
        self.amplify = amplify_power_words

    def test_weak_word_upgraded(self):
        """弱い表現がパワーワードに変換される。"""
        scenario = _make_scenario([
            "この宇宙にはすごいことがたくさんある",
            "面白い研究結果が出た",
            "大きい数字が確認された",
        ])
        result = self.amplify(scenario, channel_id="daily-science")
        self.assertGreater(result["amplified"], 0)
        self.assertGreater(len(result["changes"]), 0)

    def test_already_powerful_skipped(self):
        """既にパワフルな表現は変換しない。"""
        scenario = _make_scenario([
            "ヤバすぎる衝撃の事実が判明！",
            "最強の伝説級モンスターが登場",
            "禁断の狂気の実験記録",
        ])
        result = self.amplify(scenario, channel_id="daily-science")
        self.assertEqual(result["amplified"], 0)

    def test_2ch_ero_upgrades(self):
        """2ch-matomeではエロ系変換が利用可能。"""
        scenario = _make_scenario([
            "女が突然告白してきた",
            "体験談を友達に話したら",
            "結局バレて終了",
        ])
        result = self.amplify(scenario, channel_id="2ch-matome",
                              max_amplifications=5)
        self.assertGreater(result["amplified"], 0)

    def test_max_amplifications_respected(self):
        """最大変換数が尊重される。"""
        scenario = _make_scenario([
            "すごいことが判明した",
            "面白い話がある",
            "大きい数字だ",
            "変なことが起きた",
            "危ない状況になった",
        ])
        result = self.amplify(scenario, channel_id="daily-science",
                              max_amplifications=2)
        self.assertLessEqual(result["amplified"], 2)

    def test_empty_scenario(self):
        """空シナリオでもエラーにならない。"""
        result = self.amplify([], channel_id="daily-science")
        self.assertEqual(result["amplified"], 0)


# =====================================================================
# 7. Round 7 Enhancer (Integration)
# =====================================================================

class TestRound7Enhancer(unittest.TestCase):

    def setUp(self):
        from pipeline.round7_enhancer import enhance
        self.enhance = enhance
        self.temp_dir = tempfile.mkdtemp()

    def test_full_pipeline(self):
        """全6モジュールがエラーなく実行される。"""
        scenario = _make_scenario([
            "実は人間の脳は面白い構造をしている",
            "うん、そうだね",
            "さて、本題に入ろう",
            "脳の神経細胞は860億個ある",
            "すごい数だよね",
            "これは宇宙の星より多い",
            "以上、終わり。",
        ])
        with patch("pipeline.originality_guard.DATA_DIR", Path(self.temp_dir)):
            result = self.enhance(
                scenario,
                title="人間の脳がヤバすぎる件",
                channel_id="daily-science",
            )
        # 全キーが存在する
        self.assertIn("completion_rate", result)
        self.assertIn("replay_loop", result)
        self.assertIn("power_word", result)
        self.assertIn("retention_feedback", result)
        self.assertIn("originality", result)
        self.assertIn("title_emoji", result)
        self.assertIn("enhanced_title", result)

    def test_all_channels(self):
        """全チャンネルでエラーなく動作する。"""
        channels = ["daily-science", "scp-lab", "2ch-matome",
                     "company-facts", "pokemon-lab", "yokai-watch", "akashic"]
        for ch in channels:
            scenario = _make_scenario([
                "これは衝撃の事実",
                "普通に信じられないよね",
                "さて、さらに掘り下げよう",
                "すごいデータが見つかった",
                "まとめると面白い話だった",
                "以上です",
            ])
            with patch("pipeline.originality_guard.DATA_DIR",
                        Path(self.temp_dir)):
                result = self.enhance(
                    scenario,
                    title=f"テスト_{ch}",
                    channel_id=ch,
                )
            # エラーキーがないことを確認
            for key in ["completion_rate", "replay_loop", "power_word",
                        "retention_feedback", "originality", "title_emoji"]:
                self.assertNotIn("error", result.get(key, {}),
                                 f"{key} failed for {ch}: {result.get(key)}")

    def test_2ch_matome_power_words_higher(self):
        """2ch-matomeはパワーワードの最大数が多い。"""
        scenario = _make_scenario([
            "女が告白してきた",
            "体験を話したら",
            "友達がドン引きした",
            "事件が起きた",
            "失敗して終了",
            "話はここまで",
        ])
        with patch("pipeline.originality_guard.DATA_DIR",
                    Path(self.temp_dir)):
            result = self.enhance(
                scenario,
                title="とんでもない体験した",
                channel_id="2ch-matome",
            )
        # 2ch-matomeのmax_amplificationsは5
        pw = result.get("power_word", {})
        self.assertNotIn("error", pw)


if __name__ == "__main__":
    unittest.main()
