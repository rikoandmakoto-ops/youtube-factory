"""Round 6 Post-Generation Enhancer — 生成後の6段階最適化パイプライン。

generate() から1回だけ呼ばれ、以下の6モジュールを順番に実行する:

    1. Hook A/B Selector    — 冒頭フックの最適化（GPT-light採点）
    2. Swipe-Stop Injector  — 離脱防止パターンの多点注入
    3. CTA Rotator          — CTAスタイルのローテーション
    4. Cross-Channel Bridge — チャンネル間コンテンツ連携
    5. Mute-Safe Checker    — ミュート視聴安全性チェック
    6. Viral Score Gate     — バイラルポテンシャル事前スコアリング

各モジュールは独立しており、1つが失敗しても他に影響しない。
結果はすべて round6 キーにまとめて返す。
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
    series_name: str = "",
    api_key: str = "",
) -> Dict[str, Any]:
    """Round 6 の全最適化を実行する。

    Args:
        short_scenario: 生成済みシナリオの行リスト（in-place で変更される）。
        title: 動画タイトル。
        channel_id: チャンネルID。
        channel_dict: チャンネル設定辞書。
        series_name: シリーズ名（あれば）。
        api_key: OpenAI API キー（Hook A/B用）。

    Returns:
        {
            "hook_ab": {...},
            "swipe_stop": {...},
            "cta_rotation": {...},
            "cross_bridge": {...},
            "mute_safe": {...},
            "viral_score": {...},
        }
    """
    results: Dict[str, Any] = {}

    # ── 1. Hook A/B Selector ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "hook_ab_selector"):
            results["hook_ab"] = enhancer_gate.skipped("hook_ab_selector", channel_id)
        else:
            from pipeline import hook_ab_selector
            results["hook_ab"] = hook_ab_selector.select_best_hook(
                short_scenario,
                theme_title=title,
                channel_id=channel_id,
                api_key=api_key,
            )
    except Exception as e:
        results["hook_ab"] = {"error": str(e)}
        print(f"  ⚠️ Round6 HookAB failed [{channel_id}]: {e}")
        traceback.print_exc()

    # ── 2. Swipe-Stop Injector ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "swipe_stop_injector"):
            results["swipe_stop"] = enhancer_gate.skipped("swipe_stop_injector", channel_id)
        else:
            from pipeline import swipe_stop_injector
            results["swipe_stop"] = swipe_stop_injector.inject_rehooks(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["swipe_stop"] = {"error": str(e)}
        print(f"  ⚠️ Round6 SwipeStop failed [{channel_id}]: {e}")

    # ── 3. CTA Rotator ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "cta_rotator"):
            results["cta_rotation"] = enhancer_gate.skipped("cta_rotator", channel_id)
        else:
            from pipeline import cta_rotator
            results["cta_rotation"] = cta_rotator.rotate_cta(
                short_scenario,
                channel_id=channel_id,
                series_name=series_name,
            )
    except Exception as e:
        results["cta_rotation"] = {"error": str(e)}
        print(f"  ⚠️ Round6 CTARotator failed [{channel_id}]: {e}")

    # ── 4. Cross-Channel Bridge ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "cross_channel_bridge"):
            results["cross_bridge"] = enhancer_gate.skipped("cross_channel_bridge", channel_id)
        else:
            from pipeline import cross_channel_bridge
            results["cross_bridge"] = cross_channel_bridge.inject_bridge(
                short_scenario,
                title=title,
                channel_id=channel_id,
            )
    except Exception as e:
        results["cross_bridge"] = {"error": str(e)}
        print(f"  ⚠️ Round6 CrossBridge failed [{channel_id}]: {e}")

    # ── 5. Mute-Safe Checker ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "mute_safe_checker"):
            results["mute_safe"] = enhancer_gate.skipped("mute_safe_checker", channel_id)
        else:
            from pipeline import mute_safe_checker
            results["mute_safe"] = mute_safe_checker.check_mute_safe(
                short_scenario,
                channel_id=channel_id,
            )
    except Exception as e:
        results["mute_safe"] = {"error": str(e)}
        print(f"  ⚠️ Round6 MuteSafe failed [{channel_id}]: {e}")

    # ── 6. Viral Score Gate ──
    try:
        if not enhancer_gate.is_enabled(channel_dict, "viral_score_gate"):
            results["viral_score"] = enhancer_gate.skipped("viral_score_gate", channel_id)
        else:
            from pipeline import viral_score_gate
            results["viral_score"] = viral_score_gate.score_viral_potential(
                short_scenario,
                title=title,
                channel_id=channel_id,
            )
    except Exception as e:
        results["viral_score"] = {"error": str(e)}
        print(f"  ⚠️ Round6 ViralScore failed [{channel_id}]: {e}")

    return results
