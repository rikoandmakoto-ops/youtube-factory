"""ショート動画の完視聴率最適化ガード。

競合分析の結果:
- 完視聴率 70%+ で初動リーチが倍増、80%+ で最大化
- 15〜30秒 = ループ最適化向き（7〜15秒のコンテンツが2周される）
- 30〜45秒 = 解説ショートの最適帯（completion rate が最も安定）
- 45〜55秒 = 情報密度が高い場合のみ許容
- 55秒超 = completion rate が急落、リーチ激減

このモジュールは:
1. 生成されたシナリオの文字数から推定尺を算出
2. チャンネル別の最適帯に収まっているか検証
3. 収まっていなければ警告を出し、修正ヒントを返す
4. video_generator から呼ばれ、尺が許容範囲外なら再生成を促す
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# VOICEVOX 1.3x の実効読み上げ速度（字/秒）
VOICEVOX_CHARS_PER_SEC = 8.9

# 話速・話者が既定（1.3x のゆっくり系）と違うチャンネルの実効読み上げ速度。
# ここを外すと推定尺が実尺の 6 割になり、ガードが逆方向の加筆を勧めてくる。
# akashic-librarian: 離途(101) speed=1.15 を実測して 5.43 字/秒。
CHANNEL_CHARS_PER_SEC: Dict[str, float] = {
    "akashic-librarian": 5.43,
}


def chars_per_sec_for(channel_id: str) -> float:
    """チャンネルの実効読み上げ速度（字/秒）。未登録なら既定値。"""
    return CHANNEL_CHARS_PER_SEC.get(channel_id, VOICEVOX_CHARS_PER_SEC)

# エンドカードの秒数
ENDCARD_SECONDS = 1.6

# チャンネル別の最適尺範囲（秒）
# 競合分析に基づく推奨値。各チャンネルのコンテンツ密度に合わせて調整。
CHANNEL_DURATION_RANGE: Dict[str, Tuple[int, int]] = {
    "daily-science": (30, 50),      # 解説系: 30〜50秒
    "scp-lab": (35, 55),            # 情報密度高い: 35〜55秒
    "2ch-matome": (30, 50),         # テンポ重視: 30〜50秒
    "company-facts": (30, 50),      # ファクト系: 30〜50秒
    "pokemon-lab": (30, 45),        # トリビア系: 30〜45秒
    "yokai-watch": (35, 50),        # 怪談系: 35〜50秒
    "akashic-librarian": (35, 55),  # モノローグ: 35〜55秒
    "fake-paper": (28, 40),         # 架空論文: 30秒前後（オチ一撃型・ループ狙い）
}

# デフォルトの許容範囲
DEFAULT_RANGE = (30, 55)

# 完視聴率の目安テーブル（秒 → 推定 completion rate）
# ショートは短いほど completion rate が高い傾向。
_COMPLETION_RATE_ESTIMATE = [
    (15, 0.90),
    (25, 0.82),
    (30, 0.78),
    (35, 0.74),
    (40, 0.70),
    (45, 0.65),
    (50, 0.58),
    (55, 0.50),
    (60, 0.42),
]


def estimate_duration(
    scenario: List[Dict[str, Any]],
    *,
    endcard_seconds: float = ENDCARD_SECONDS,
    chars_per_sec: float = VOICEVOX_CHARS_PER_SEC,
) -> float:
    """シナリオの推定再生時間（秒）を返す。"""
    total_chars = sum(len(line.get("text", "")) for line in scenario)
    speech_seconds = total_chars / chars_per_sec
    # 行間のポーズ（約0.3秒/行）
    pause_seconds = len(scenario) * 0.3
    return speech_seconds + pause_seconds + endcard_seconds


def estimate_completion_rate(duration_seconds: float) -> float:
    """推定完視聴率を返す（0.0〜1.0）。"""
    for threshold, rate in _COMPLETION_RATE_ESTIMATE:
        if duration_seconds <= threshold:
            return rate
    return 0.35  # 60秒超


def check_scenario(
    channel_id: str,
    scenario: List[Dict[str, Any]],
    *,
    endcard_seconds: float = ENDCARD_SECONDS,
) -> Dict[str, Any]:
    """シナリオの尺を検証し、結果を返す。

    Returns:
        {
            "ok": bool,
            "estimated_seconds": float,
            "estimated_completion_rate": float,
            "total_chars": int,
            "line_count": int,
            "range_min": int,
            "range_max": int,
            "warning": Optional[str],
            "suggestion": Optional[str],
        }
    """
    range_min, range_max = CHANNEL_DURATION_RANGE.get(channel_id, DEFAULT_RANGE)
    cps = chars_per_sec_for(channel_id)
    est_seconds = estimate_duration(
        scenario, endcard_seconds=endcard_seconds, chars_per_sec=cps,
    )
    est_cr = estimate_completion_rate(est_seconds)
    total_chars = sum(len(line.get("text", "")) for line in scenario)

    result: Dict[str, Any] = {
        "ok": True,
        "estimated_seconds": round(est_seconds, 1),
        "estimated_completion_rate": round(est_cr, 2),
        "total_chars": total_chars,
        "line_count": len(scenario),
        "range_min": range_min,
        "range_max": range_max,
        "warning": None,
        "suggestion": None,
    }

    if est_seconds < range_min:
        deficit = range_min - est_seconds
        chars_needed = int(deficit * cps)
        result["ok"] = False
        result["warning"] = (
            f"推定 {est_seconds:.0f}秒 — 最適帯の下限 {range_min}秒 を下回る "
            f"(completion rate は高いがリーチが減る)"
        )
        result["suggestion"] = (
            f"総文字数を約 {chars_needed} 字増やして {range_min}秒以上にする。"
            f"1行あたり {chars_needed // max(1, len(scenario))} 字程度の加筆で達成可能。"
        )
    elif est_seconds > range_max:
        excess = est_seconds - range_max
        chars_over = int(excess * cps)
        result["ok"] = False
        result["warning"] = (
            f"推定 {est_seconds:.0f}秒 — 最適帯の上限 {range_max}秒 を超過 "
            f"(completion rate {est_cr:.0%} に低下)"
        )
        result["suggestion"] = (
            f"総文字数を約 {chars_over} 字削って {range_max}秒以下にする。"
            f"1行あたり {chars_over // max(1, len(scenario))} 字程度の削減で達成可能。"
        )
    elif est_seconds > range_max - 5:
        # 上限に近い場合は注意喚起
        result["warning"] = (
            f"推定 {est_seconds:.0f}秒 — 上限 {range_max}秒 に近い。"
            f"あと {range_max - est_seconds:.0f}秒 余裕。"
        )

    return result


def guard(
    channel_id: str,
    scenario: List[Dict[str, Any]],
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    """パイプライン統合用エントリポイント。

    strict=True の場合、範囲外なら例外を送出する（再生成のトリガー用）。
    strict=False（デフォルト）の場合、警告をログに出すだけで通す。
    """
    result = check_scenario(channel_id, scenario)

    if result["warning"]:
        print(
            f"  ⏱️ ShortsLengthGuard [{channel_id}]: {result['warning']}"
        )
    if result["suggestion"]:
        print(
            f"     💡 {result['suggestion']}"
        )

    if not result["ok"] and strict:
        raise ValueError(
            f"ShortsLengthGuard: {channel_id} の推定尺 {result['estimated_seconds']:.0f}秒 が "
            f"最適帯 {result['range_min']}〜{result['range_max']}秒 の範囲外。"
            f"{result.get('suggestion', '')}"
        )

    print(
        f"  ⏱️ ShortsLengthGuard [{channel_id}]: "
        f"{result['estimated_seconds']:.0f}秒 / {result['total_chars']}字 / "
        f"推定CR {result['estimated_completion_rate']:.0%} — "
        f"{'✅ OK' if result['ok'] else '⚠️ 範囲外'}"
    )

    return result
