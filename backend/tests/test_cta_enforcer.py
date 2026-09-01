"""cta_enforcer のテスト（2026-09-01 新設）。

実際に 08-29〜08-31 に生成され公開された台本の最終行を回帰ケースとして使う。
当時 高評価CTA 50% / 登録CTA 38% しか無く、62%のショートが登録を求めていなかった。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import cta_enforcer as ce  # noqa: E402


def _last(scenario):
    return scenario[-1]["text"]


def _visible_len(text: str) -> int:
    return len(re.sub(r"\s", "", text))


# 実際に公開された最終行（data/scenarios の ショートシナリオ節より）
REAL_LAST_LINES = [
    ("company-facts", "気になったらプロフィールから、話題の企業の実態シリーズもチェックしてね。"),
    ("company-facts", "気になったら、話題の企業の実態シリーズもプロフィールからチェックしてね。…これが最初の疑問の答えだ"),
    ("daily-science", "睡眠と夢シリーズシリーズ、面白かったら高評価で教えてね！次の科学ネタの参考にする！…って、冒頭の話に戻るんだけど"),
    ("yokai-watch", "元ネタが怖い最恐の妖怪シリーズシリーズ、次に調べてほしい妖怪をコメントで教えてくれ。…これが最初の違和感の正体だった"),
    ("pokemon-lab", "裏設定ファイルシリーズシリーズ、推しヤバすぎるポケモンの闇設定も知りたい人はコメントで！…あれ、以外って最初に言ってた…"),
    ("2ch-matome", "お前らの期待もコメントで頼むわw 毎日投稿中、1万人目標の〜あげてけシリーズ応援よろしくやで。…あれ、最初のレスもう一回読んでみ？"),
    ("scp-lab", "財団の裏側シリーズシリーズ、次に解説してほしいSCPをコメントで教えてくれ。…待て、最初の報告と矛盾してないか？"),
]


class TestEnforceFinalCta:
    @pytest.mark.parametrize("channel_id,last_line", REAL_LAST_LINES)
    def test_real_lines_gain_both_ctas(self, channel_id, last_line):
        """実公開された非準拠の最終行が、高評価と登録の両方を含むようになる。"""
        scenario = [{"text": "本文"}, {"text": last_line}]
        ce.enforce_final_cta(channel_id, scenario)
        result = _last(scenario)
        assert ce.has_like(result), f"高評価が無い: {result}"
        assert ce.has_subscribe(result), f"登録が無い: {result}"

    @pytest.mark.parametrize("channel_id,last_line", REAL_LAST_LINES)
    def test_stays_within_budget(self, channel_id, last_line):
        """CTA付与で最終行が間延びしない（字数は維持率を直接規定するため）。"""
        scenario = [{"text": "本文"}, {"text": last_line}]
        ce.enforce_final_cta(channel_id, scenario)
        assert _visible_len(_last(scenario)) <= ce._LAST_LINE_BUDGET + 5

    def test_compliant_line_is_untouched(self):
        """既に高評価+登録がある行は書き換えない。"""
        good = "高評価を残せ。収容違反ファイルシリーズにも空白はある。毎日投稿中、1万人目標の登録で応援よろしく。"
        scenario = [{"text": "本文"}, {"text": good}]
        result = ce.enforce_final_cta("scp-lab", scenario)
        assert result["applied"] is False
        assert _last(scenario) == good

    def test_idempotent(self):
        """2回適用しても増殖しない。"""
        scenario = [{"text": "本文"}, {"text": "気になったらチェックしてね。"}]
        ce.enforce_final_cta("company-facts", scenario)
        once = _last(scenario)
        second = ce.enforce_final_cta("company-facts", scenario)
        assert second["applied"] is False
        assert _last(scenario) == once

    def test_like_comes_before_subscribe(self):
        """高評価は登録より先に置く（実測 6.3倍の観測レバーを先頭に）。"""
        scenario = [{"text": "本文"}, {"text": "気になったらチェックしてね。"}]
        ce.enforce_final_cta("daily-science", scenario)
        text = _last(scenario)
        assert text.index("高評価") < text.index("登録")

    def test_only_last_line_is_modified(self):
        """本文行には触れない。"""
        body = {"text": "なんでSCP-1987だけ、映像にいないのに隔離されるのか。"}
        scenario = [body, {"text": "コメントで教えてくれ。"}]
        ce.enforce_final_cta("scp-lab", scenario)
        assert scenario[0]["text"] == "なんでSCP-1987だけ、映像にいないのに隔離されるのか。"

    def test_empty_scenario_is_safe(self):
        assert ce.enforce_final_cta("scp-lab", [])["applied"] is False


class TestStripLoopTrailer:
    @pytest.mark.parametrize(
        "trailer",
        [
            "…って、冒頭の話に戻るんだけど",
            "…待て、最初の報告と矛盾してないか？",
            "…これが最初の違和感の正体だった",
            "…あれ、最初のレスもう一回読んでみ？",
            "…つまり最初に言った通り、全部繋がっている",
            "…待って、財団に戻って",
            "…あれ、水分補給って最初に言ってた…",
        ],
    )
    def test_removes_every_loop_trigger_shape(self, trailer):
        """replay_loop_seeder のトリガーは全て … で始まる suffix なので確実に落ちる。"""
        base = "高評価を残せ。登録すれば次のファイルが届く。"
        assert ce.strip_loop_trailer(base + trailer) == base

    def test_keeps_line_without_trailer(self):
        base = "高評価を残せ。登録すれば次のファイルが届く。"
        assert ce.strip_loop_trailer(base) == base


class TestDoesNotDestroyContent:
    """2026-09-01 のレビューで見つかった破壊的挙動の回帰テスト。"""

    @pytest.mark.parametrize(
        "line",
        [
            "答えは…実は3年前から決まっていた。",
            "つまり、この会社の正体は……ただの下請けだったんだ。",
            "でも本当に怖いのは…その次に起きたことだ。コメントで教えてくれ。",
            "そして誰も…戻ってこなかった。",
        ],
    )
    def test_mid_sentence_ellipsis_is_preserved(self, line):
        """溜めの「…」を含む普通の文を切り詰めない。

        「… 以降を全部落とす」実装では「答えは」まで削られ、
        TTS が破片を読み上げていた。
        """
        assert ce.strip_loop_trailer(line) == line

    @pytest.mark.parametrize(
        "line",
        [
            "答えは…実は3年前から決まっていた。",
            "でも本当に怖いのは…その次に起きたことだ。コメントで教えてくれ。",
        ],
    )
    def test_enforcement_keeps_original_sentence(self, line):
        """CTA付与後も元の文がそのまま残っている。"""
        scenario = [{"text": "本文"}, {"text": line}]
        ce.enforce_final_cta("company-facts", scenario)
        assert line in _last(scenario)

    def test_authored_content_survives_for_real_lines(self):
        """実台本の特徴語（シリーズ名等）が定型文で潰されない。

        当初 budget=70 では 7件中6件が畳まれ、そのチャンネルの
        全ショートが同一の最終行で終わる状態だった。
        """
        kept = 0
        for channel_id, line in REAL_LAST_LINES:
            scenario = [{"text": "本文"}, {"text": line}]
            result = ce.enforce_final_cta(channel_id, scenario)
            if not result["collapsed"]:
                kept += 1
        assert kept >= 6, f"台本の文言が残ったのは {kept}/7 件だけ"

    def test_single_line_scenario_is_not_replaced_wholesale(self):
        """1行しかない台本を丸ごと定型文に差し替えない。"""
        only = "なんでSCP-1987だけ、映像にいないのに隔離されるのか。"
        scenario = [{"text": only}]
        ce.enforce_final_cta("scp-lab", scenario)
        assert only in scenario[0]["text"]

    @pytest.mark.parametrize(
        "line",
        [
            "登録者数100万人の裏側。",
            "商標登録された社名がヤバい。",
            "この会社は登録免許税の抜け道を使っている。",
        ],
    )
    def test_general_vocabulary_is_not_mistaken_for_cta(self, line):
        """「登録者数」「商標登録」等を登録CTAと誤認して補正を止めない。"""
        assert not ce.has_subscribe(line)
        scenario = [{"text": "本文"}, {"text": line}]
        ce.enforce_final_cta("company-facts", scenario)
        assert ce.has_subscribe(_last(scenario))

    def test_aizuchi_iine_is_not_mistaken_for_like_cta(self):
        line = "それいいねって思った人はコメントで。"
        assert not ce.has_like(line)
        scenario = [{"text": "本文"}, {"text": line}]
        ce.enforce_final_cta("daily-science", scenario)
        assert ce.has_like(_last(scenario))

    @pytest.mark.parametrize("bad", [123, ["x"], {"a": 1}, None])
    def test_non_string_text_does_not_raise(self, bad):
        scenario = [{"text": "本文"}, {"text": bad}]
        result = ce.enforce_final_cta("scp-lab", scenario)
        assert result["applied"] is False

    def test_overlong_fallback_is_capped(self):
        """cta_fallback が長すぎても予算内に収まる。"""
        channel_dict = {
            "short_format": {
                "cta_fallback": {
                    "like": "高評価を" + "とても" * 30 + "お願いします。",
                    "subscribe": "チャンネル登録を" + "ぜひ" * 30 + "お願いします。",
                }
            }
        }
        scenario = [{"text": "本文"}, {"text": "コメントで教えてね。"}]
        ce.enforce_final_cta("scp-lab", scenario, channel_dict=channel_dict)
        text = _last(scenario)
        assert _visible_len(text) <= ce._LAST_LINE_BUDGET
        assert ce.has_like(text) and ce.has_subscribe(text)


class TestCtaPhrases:
    def test_channel_json_override_wins(self):
        channel_dict = {
            "short_format": {
                "cta_fallback": {"like": "カスタム高評価。", "subscribe": "カスタム登録。"}
            }
        }
        phrases = ce.cta_phrases("scp-lab", channel_dict)
        assert phrases["like"] == "カスタム高評価。"
        assert phrases["subscribe"] == "カスタム登録。"

    def test_unknown_channel_falls_back_to_generic(self):
        phrases = ce.cta_phrases("does-not-exist")
        assert ce.has_like(phrases["like"])
        assert ce.has_subscribe(phrases["subscribe"])

    @pytest.mark.parametrize("channel_id", list(ce._DEFAULT_CTA))
    def test_every_default_contains_its_token(self, channel_id):
        phrases = ce.cta_phrases(channel_id)
        assert ce.has_like(phrases["like"])
        assert ce.has_subscribe(phrases["subscribe"])


class TestSeriesDedup:
    """「シリーズシリーズ」重複（LLMが series_lineup の値に更にシリーズを足す）。"""

    @pytest.mark.parametrize(
        "before,after",
        [
            ("睡眠と夢シリーズシリーズ、面白かったら高評価。", "睡眠と夢シリーズ、面白かったら高評価。"),
            ("裏設定ファイルシリーズシリーズも見てね。", "裏設定ファイルシリーズも見てね。"),
            ("元ネタが怖い最恐の妖怪シリーズ シリーズ、次回も。", "元ネタが怖い最恐の妖怪シリーズ、次回も。"),
        ],
    )
    def test_dedup(self, before, after):
        scenario = [{"text": "本文"}, {"text": before}]
        ce.enforce_final_cta("daily-science", scenario)
        assert after.rstrip("。") in _last(scenario)

    def test_single_series_untouched(self):
        line = "収容違反ファイルシリーズにも空白はある。高評価を残せ。登録して待て。"
        scenario = [{"text": "本文"}, {"text": line}]
        ce.enforce_final_cta("scp-lab", scenario)
        assert _last(scenario) == line
