"""Emotional Polarity Alternator — 感情極性の交互切替で注意維持（Round 8）。

狙い:
    同じ感情トーンが3行以上続くと脳が「慣れ」を起こし離脱する。
    ポジティブ→ネガティブ→驚き→… の極性を交互に切り替えることで
    常に新鮮な刺激を与え、完走率とリプレイ率を向上させる。

既存モジュールとの違い:
    - completion_rate_optimizer: 情報「密度」の均等化 & ペーシング
    - power_word_amplifier: 個別の弱い単語を強い単語に置換
    - 本モジュール: 行ごとの感情「極性」（+/-/surprise）を分析し、
      同一極性の連続を検出して感情転換語を注入
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Tuple

# =====================================================================
# 感情極性分類
# =====================================================================

_POSITIVE_PATTERNS = [
    (r"(すごい|すげー|やばい|ヤバい|最強|天才|神)", "positive"),
    (r"(面白い|おもしろい|楽しい|嬉しい|幸せ)", "positive"),
    (r"(成功|勝利|達成|実現|突破)", "positive"),
    (r"(美しい|素晴らしい|最高|感動)", "positive"),
    (r"[ｗw]{2,}", "positive"),  # 草
]

_NEGATIVE_PATTERNS = [
    (r"(怖い|恐ろしい|ヤバい|危険|闇)", "negative"),
    (r"(失敗|破滅|崩壊|消滅|死)", "negative"),
    (r"(悲しい|辛い|苦しい|絶望)", "negative"),
    (r"(問題|犯罪|被害|損害|損失)", "negative"),
    (r"(禁止|違法|逮捕|罰)", "negative"),
]

_SURPRISE_PATTERNS = [
    (r"[！!]{1,}", "surprise"),
    (r"(実は|じつは|なんと|まさか|衝撃)", "surprise"),
    (r"(え[？?！!]|マジ[？?！!]|嘘[！!])", "surprise"),
    (r"(信じられない|ありえない|想像を超える)", "surprise"),
]


def _classify_polarity(text: str) -> str:
    """テキストの感情極性を分類。positive/negative/surprise/neutral。"""
    scores = {"positive": 0, "negative": 0, "surprise": 0}

    for pattern, polarity in _POSITIVE_PATTERNS:
        if re.search(pattern, text):
            scores[polarity] += 1

    for pattern, polarity in _NEGATIVE_PATTERNS:
        if re.search(pattern, text):
            scores[polarity] += 1

    for pattern, polarity in _SURPRISE_PATTERNS:
        if re.search(pattern, text):
            scores[polarity] += 1

    max_score = max(scores.values())
    if max_score == 0:
        return "neutral"

    # 最大スコアの極性を返す（同点はsurprise優先）
    for p in ["surprise", "negative", "positive"]:
        if scores[p] == max_score:
            return p
    return "neutral"


# =====================================================================
# 感情転換語（同一極性が続いた時に注入）
# =====================================================================

# 極性 → 転換先の注入フレーズ
_POLARITY_BREAKERS: Dict[str, Dict[str, List[str]]] = {
    "positive": {
        # ポジティブ連続 → ネガティブ転換
        "default": [
            "…ところが、ここで問題が発生する",
            "…しかし裏を返せば、恐ろしい事実でもある",
            "…だが、話はそう単純じゃない",
        ],
        "2ch-matome": [
            "…と思ったら地獄の始まりだったｗｗ",
            "…からの急転直下ｗｗｗ",
            "…はい、ここからが本番です",
        ],
    },
    "negative": {
        # ネガティブ連続 → ポジティブ/驚き転換
        "default": [
            "…でも、ここで奇跡が起こる",
            "…と思いきや、意外な展開が待っていた",
            "…しかし！ここから逆転が始まる",
        ],
        "2ch-matome": [
            "…からの大逆転ｗｗｗ",
            "…ここで神展開きたｗｗｗ",
            "…と思ったらまさかの結末",
        ],
    },
    "surprise": {
        # 驚き連続 → 冷静な事実で緩急
        "default": [
            "…落ち着いて聞いてほしいんだけど",
            "…ここで冷静に考えてみると",
            "…一旦整理すると、こういうことだ",
        ],
        "2ch-matome": [
            "…ちょっと落ち着けｗｗ",
            "…まあ冷静に考えるとさ",
            "…ここで一回整理するわ",
        ],
    },
}


def _get_breaker(polarity: str, channel_id: str) -> str:
    """極性に応じた転換フレーズを取得。"""
    breakers = _POLARITY_BREAKERS.get(polarity, {})
    channel_breakers = breakers.get(channel_id, breakers.get("default", []))
    if not channel_breakers:
        return ""
    return random.choice(channel_breakers)


# =====================================================================
# メインエントリポイント
# =====================================================================

def alternate_emotional_polarity(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
    max_consecutive: int = 3,
) -> Dict[str, Any]:
    """感情極性の連続を検出し、転換語を注入する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。
        max_consecutive: 同一極性の許容連続数（デフォルト3）。

    Returns:
        {
            "polarities": List[str],     # 各行の極性
            "streaks_found": int,        # 検出した連続数
            "breakers_injected": int,    # 注入した転換数
            "polarity_diversity": float, # 極性の多様性 (0-1)
        }
    """
    if len(short_scenario) < 4:
        return {"polarities": [], "streaks_found": 0,
                "breakers_injected": 0, "polarity_diversity": 0.0}

    # 全行の極性を分類
    polarities: List[str] = []
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        polarities.append(_classify_polarity(text))

    # 連続同一極性を検出
    streaks = 0
    injected = 0

    i = 0
    while i < len(polarities) - max_consecutive:
        # max_consecutive行連続で同じ非neutral極性かチェック
        window = polarities[i:i + max_consecutive]
        if (len(set(window)) == 1 and window[0] != "neutral"):
            streaks += 1

            # 連続の最後の行に転換語を注入
            break_pos = i + max_consecutive - 1
            if break_pos < len(short_scenario):
                breaker = _get_breaker(window[0], channel_id)
                if breaker:
                    entry = short_scenario[break_pos]
                    text_key = "text" if "text" in entry else "line"
                    current = entry.get(text_key, "").rstrip()
                    if current and not current.endswith(("。", "！", "？", "…")):
                        current += "。"
                    entry[text_key] = f"{current}{breaker}"
                    injected += 1

            # 連続区間を飛ばす
            i += max_consecutive
        else:
            i += 1

    # 極性多様性（非neutralの種類数 / 3）
    non_neutral = [p for p in polarities if p != "neutral"]
    diversity = len(set(non_neutral)) / 3.0 if non_neutral else 0.0

    print(
        f"  🎭 EmotionPol [{channel_id}]: "
        f"streaks={streaks}, injected={injected}, "
        f"diversity={diversity:.0%}"
    )

    return {
        "polarities": polarities,
        "streaks_found": streaks,
        "breakers_injected": injected,
        "polarity_diversity": round(diversity, 2),
    }
