"""Round 7 Post-Generation Enhancer — 完走率 & リプレイ最大化パイプライン。

generate() から1回だけ呼ばれ、以下の6モジュールを順番に実行する:

    1. Completion Rate Optimizer  — ペーシング最適化で完走率UP
    2. Replay Loop Seeder         — シームレスループ構造でリプレイ誘導
    3. Power Word Amplifier       — パワーワード注入でエンゲージメントUP
    4. Retention Feedback Loop    — 蓄積分析データのシナリオ直接反映
    5. Originality Guard          — 独自性チェック（収益化保護）
    6. Title Emoji Injector       — タイトル絵文字でCTR UP

実行順序の意図:
    1-4 はシナリオ本文を変更する（前段から順に適用）
    5 は変更後のシナリオで独自性を検証（変更前に検証すると意味がない）
    6 はタイトルのみ変更（シナリオ非依存）

各モジュールは独立しており、1つが失敗しても他に影響しない。
結果はすべて round7 キーにまとめて返す。
"""

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

from pipeline import enhancer_gate


def enhance(
    short_scenario: List[Dict[str, Any]],
    *,
    title: str = "",
    channel_id: str = "",
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Round 7 の全最適化を実行する。

    Args:
        short_scenario: 生成済みシナリオの行リスト（in-place で変更される）。
        title: 動画タイトル。
        channel_id: チャンネルID。
        channel_dict: チャンネル設定辞書。

    Returns:
        {
            "completion_rate": {...},
            "replay_loop": {...},
            "power_word": {...},
            "retention_feedback": {...},
            "originality": {...},
            "title_emoji": {...},
            "enhanced_title": str,   # 絵文字注入後のタイトル
        }
    """
    results: Dict[str, Any] = {}

    # ── 1. Completion Rate Optimizer ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "completion_rate_optimizer"):
            results["completion_rate"] = enhancer_gate.skipped("completion_rate_optimizer", channel_id)
        else:
            from pipeline.completion_rate_optimizer import optimize_completion_rate
            results["completion_rate"] = optimize_completion_rate(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["completion_rate"] = {"error": str(e)}
        print(f"  ⚠️ Round7 CompletionOpt failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 2. Replay Loop Seeder ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "replay_loop_seeder"):
            results["replay_loop"] = enhancer_gate.skipped("replay_loop_seeder", channel_id)
        else:
            from pipeline.replay_loop_seeder import seed_replay_loop
            results["replay_loop"] = seed_replay_loop(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["replay_loop"] = {"error": str(e)}
        print(f"  ⚠️ Round7 ReplayLoop failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 3. Power Word Amplifier ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "power_word_amplifier"):
            results["power_word"] = enhancer_gate.skipped("power_word_amplifier", channel_id)
        else:
            from pipeline.power_word_amplifier import amplify_power_words
            # 2ch-matome は多め（下ネタ・エロ面白系強化）
            max_amp = 5 if channel_id == "2ch-matome" else 3
            results["power_word"] = amplify_power_words(
                short_scenario,
                channel_id=channel_id,
                max_amplifications=max_amp,
            )
    except Exception as e:
        results["power_word"] = {"error": str(e)}
        print(f"  ⚠️ Round7 PowerWord failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 4. Retention Feedback Loop ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "retention_feedback_loop"):
            results["retention_feedback"] = enhancer_gate.skipped("retention_feedback_loop", channel_id)
        else:
            from pipeline.retention_feedback_loop import apply_retention_feedback
            results["retention_feedback"] = apply_retention_feedback(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["retention_feedback"] = {"error": str(e)}
        print(f"  ⚠️ Round7 RetentionFeedback failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 5. Originality Guard ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "originality_guard"):
            results["originality"] = enhancer_gate.skipped("originality_guard", channel_id)
        else:
            from pipeline.originality_guard import check_originality
            results["originality"] = check_originality(
                short_scenario,
                title=title,
                channel_id=channel_id,
            )
    except Exception as e:
        results["originality"] = {"error": str(e)}
        print(f"  ⚠️ Round7 OriginalityGuard failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 6. Title Emoji Injector ──
    enhanced_title = title
    try:
        if not enhancer_gate.is_enabled(channel_dict, "title_emoji_injector"):
            results["title_emoji"] = enhancer_gate.skipped("title_emoji_injector", channel_id)
        else:
            from pipeline.title_emoji_injector import inject_title_emoji
            emoji_result = inject_title_emoji(
                title,
                channel_id=channel_id,
                short_scenario=short_scenario,
            )
            results["title_emoji"] = emoji_result
            if emoji_result.get("modified"):
                enhanced_title = emoji_result["enhanced_title"]
    except Exception as e:
        results["title_emoji"] = {"error": str(e)}
        print(f"  ⚠️ Round7 TitleEmoji failed [{channel_id}]: {e}")
        traceback.print_exc()

    results["enhanced_title"] = enhanced_title
    return results
