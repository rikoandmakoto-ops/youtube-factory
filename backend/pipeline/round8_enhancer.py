"""Round 8 Post-Generation Enhancer — エンゲージメント & 登録者最大化パイプライン。

generate() から1回だけ呼ばれ、以下の6モジュールを順番に実行する:

    1. Curiosity Gap Enforcer      — 冒頭の情報ギャップ強制構築
    2. Comment Bait Injector       — 視聴者コメント誘発ポイント注入
    3. Emotional Polarity Alternator — 感情極性の交互切替で注意維持
    4. Pattern Interrupt Injector    — 話法パターン中断で飽き防止
    5. Subscribe Trigger Optimizer   — 有機的な登録トリガー注入
    6. Contrast Amplifier            — 常識vs真実 コントラスト増幅

実行順序の意図:
    1 は冒頭を変更（後続は冒頭以外を主に変更）
    2-4 はシナリオ中盤〜後半の異なる側面を最適化（独立）
    5 は登録トリガー配置（他の最適化後に配置位置を決める）
    6 は対比構造の仕上げ（全体を俯瞰して適用）

各モジュールは独立しており、1つが失敗しても他に影響しない。
結果はすべて round8 キーにまとめて返す。
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
    """Round 8 の全最適化を実行する。

    Args:
        short_scenario: 生成済みシナリオの行リスト（in-place で変更される）。
        title: 動画タイトル。
        channel_id: チャンネルID。
        channel_dict: チャンネル設定辞書。

    Returns:
        {
            "curiosity_gap": {...},
            "comment_bait": {...},
            "emotional_polarity": {...},
            "pattern_interrupt": {...},
            "subscribe_trigger": {...},
            "contrast": {...},
        }
    """
    results: Dict[str, Any] = {}

    # ── 1. Curiosity Gap Enforcer ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "curiosity_gap_enforcer"):
            results["curiosity_gap"] = enhancer_gate.skipped("curiosity_gap_enforcer", channel_id)
        else:
            from pipeline.curiosity_gap_enforcer import enforce_curiosity_gap
            results["curiosity_gap"] = enforce_curiosity_gap(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["curiosity_gap"] = {"error": str(e)}
        print(f"  ⚠️ Round8 CuriosityGap failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 2. Comment Bait Injector ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "comment_bait_injector"):
            results["comment_bait"] = enhancer_gate.skipped("comment_bait_injector", channel_id)
        else:
            from pipeline.comment_bait_injector import inject_comment_bait
            results["comment_bait"] = inject_comment_bait(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["comment_bait"] = {"error": str(e)}
        print(f"  ⚠️ Round8 CommentBait failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 3. Emotional Polarity Alternator ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "emotional_polarity_alternator"):
            results["emotional_polarity"] = enhancer_gate.skipped("emotional_polarity_alternator", channel_id)
        else:
            from pipeline.emotional_polarity_alternator import alternate_emotional_polarity
            # 2ch-matome は感情の振れ幅を大きく許容（連続3→4）
            max_consec = 4 if channel_id == "2ch-matome" else 3
            results["emotional_polarity"] = alternate_emotional_polarity(
                short_scenario,
                channel_id=channel_id,
                max_consecutive=max_consec,
            )
    except Exception as e:
        results["emotional_polarity"] = {"error": str(e)}
        print(f"  ⚠️ Round8 EmotionalPolarity failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 4. Pattern Interrupt Injector ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "pattern_interrupt_injector"):
            results["pattern_interrupt"] = enhancer_gate.skipped("pattern_interrupt_injector", channel_id)
        else:
            from pipeline.pattern_interrupt_injector import inject_pattern_interrupts
            # 2ch-matome は多め（3回まで中断許容）
            max_int = 3 if channel_id == "2ch-matome" else 2
            results["pattern_interrupt"] = inject_pattern_interrupts(
                short_scenario,
                channel_id=channel_id,
                max_interrupts=max_int,
            )
    except Exception as e:
        results["pattern_interrupt"] = {"error": str(e)}
        print(f"  ⚠️ Round8 PatternInterrupt failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 5. Subscribe Trigger Optimizer ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "subscribe_trigger_optimizer"):
            results["subscribe_trigger"] = enhancer_gate.skipped("subscribe_trigger_optimizer", channel_id)
        else:
            from pipeline.subscribe_trigger_optimizer import optimize_subscribe_triggers
            results["subscribe_trigger"] = optimize_subscribe_triggers(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["subscribe_trigger"] = {"error": str(e)}
        print(f"  ⚠️ Round8 SubTrigger failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 6. Contrast Amplifier ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "contrast_amplifier"):
            results["contrast"] = enhancer_gate.skipped("contrast_amplifier", channel_id)
        else:
            from pipeline.contrast_amplifier import amplify_contrast
            results["contrast"] = amplify_contrast(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["contrast"] = {"error": str(e)}
        print(f"  ⚠️ Round8 Contrast failed [{channel_id}]: {e}")
        traceback.print_exc()

    return results
