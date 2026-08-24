"""Viral Score Gate — バイラルポテンシャルの事前スコアリング（Round 6）。

狙い:
    scenario_validator が「構造的に正しいか」をチェックするのに対し、
    このモジュールは「バズるか」をルールベースでスコアリングする。

    5軸 × 20点 = 100点満点:
    1. 好奇心ギャップ (Curiosity Gap)    — 答えを知りたくさせるか
    2. 感情インパクト (Emotional Impact) — 驚き・恐怖・笑いを引くか
    3. 共感性 (Relatability)             — 「あるある」「自分ごと」と感じるか
    4. シェアラビリティ (Shareability)    — 友達に話したくなるか
    5. 議論性 (Debate Potential)          — 「自分はこう思う」と言いたくなるか

    60点未満はログ警告（将来的にリジェクト閾値に使える）。

既存モジュールとの違い:
    - scenario_validator: 構造ルール（フック有無・CTA有無・行数）→ 品質軸
    - title_quality: タイトルだけのCTRスコア → シナリオ本文は対象外
    - 本モジュール: シナリオ全体の「バズり度」→ バイラル軸
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# =====================================================================
# 好奇心ギャップ (0-20)
# =====================================================================

_CURIOSITY_PATTERNS: List[Tuple[str, int]] = [
    (r"[？?]", 3),                          # 疑問形
    (r"実は|じつは", 4),                     # 常識覆し
    (r"知って(た|る|ました)", 3),             # 知識チェック
    (r"なぜ|なんで|どうして", 3),             # Why型
    (r"\d+%|[0-9]+割", 3),                   # 具体的な数字
    (r"禁止|封印|隠され|秘密|非公開", 4),     # 禁忌感
    (r"した結果|してみた", 3),                # 結果型
    (r"まだ[^。]*ない|まだ続[くき]", 2),      # 未解決感
]


def _score_curiosity(lines: List[str]) -> int:
    score = 0
    # 冒頭3行が最重要（ここで好奇心を引けなければ離脱）
    first_third = lines[:max(1, len(lines) // 3)]
    for text in first_third:
        for pattern, weight in _CURIOSITY_PATTERNS:
            if re.search(pattern, text):
                score += weight
    return min(20, score)


# =====================================================================
# 感情インパクト (0-20)
# =====================================================================

_EMOTION_PATTERNS: List[Tuple[str, int]] = [
    (r"ヤバ|やばい|やべえ", 3),
    (r"怖|恐|恐ろしい|震え", 3),
    (r"草|ワロタ|笑|w{2,}", 3),
    (r"エロ|下ネタ|セクシー|ムラ", 3),
    (r"衝撃|驚|びっくり|マジ[？?!！]", 3),
    (r"泣|感動|涙|切な", 2),
    (r"闇|ブラック|狂|異常", 3),
    (r"死|殺|消[えされ]", 2),
    (r"かわい|萌え|推し", 2),
]


def _score_emotion(lines: List[str]) -> int:
    score = 0
    full = "\n".join(lines)
    for pattern, weight in _EMOTION_PATTERNS:
        matches = len(re.findall(pattern, full))
        score += min(weight, matches * weight)
    return min(20, score)


# =====================================================================
# 共感性 (0-20)
# =====================================================================

_RELATABILITY_PATTERNS: List[Tuple[str, int]] = [
    (r"あなた|君|お前|ワイ|自分", 3),          # 直接呼びかけ
    (r"みんな|誰もが|誰でも|多くの人", 2),      # 普遍性
    (r"経験|体験|やったこと", 2),               # 体験の共有
    (r"日常|毎日|普段|いつも", 2),              # 日常性
    (r"学校|会社|職場|仕事|バイト", 2),         # 共通のコンテキスト
    (r"子供の頃|昔|小さい時", 2),               # 共通の記憶
    (r"友達|親|家族|恋人|彼女|彼氏", 2),        # 人間関係
    (r"食べ|飲[むみ]|寝[るてた]|起き", 1),     # 生理的欲求
]


def _score_relatability(lines: List[str]) -> int:
    score = 0
    full = "\n".join(lines)
    for pattern, weight in _RELATABILITY_PATTERNS:
        if re.search(pattern, full):
            score += weight
    return min(20, score)


# =====================================================================
# シェアラビリティ (0-20)
# =====================================================================

def _score_shareability(lines: List[str], title: str = "") -> int:
    """「友達に話したくなるか」を判定。"""
    score = 0
    full = "\n".join(lines) + "\n" + title

    # 「えっマジ？」リアクションを引く事実 → シェアしたくなる
    if re.search(r"実は.*だった|って知ってた", full):
        score += 5

    # 数字のインパクト（大きい数字 or 意外な比率）
    if re.search(r"\d{4,}|99%|100%|0%|\d+万|\d+億", full):
        score += 4

    # ランキング・比較 → 議論のきっかけ → シェア
    if re.search(r"一番|最も|トップ|ワースト|vs|対決", full):
        score += 3

    # 具体的な固有名詞（シェア時に「〇〇の話なんだけど」と言える）
    proper_nouns = len(re.findall(r"[一-鿿]{3,}", full))
    if proper_nouns >= 3:
        score += 3

    # 短いタイトル（シェアしやすい）
    if title and len(title) <= 25:
        score += 3

    # 下ネタ・面白系 → SNSシェア向き
    if re.search(r"エロ|下ネタ|草|ワロタ|面白|笑える", full):
        score += 4

    return min(20, score)


# =====================================================================
# 議論性 (0-20)
# =====================================================================

_DEBATE_PATTERNS: List[Tuple[str, int]] = [
    (r"どっち|どちら|AかBか|vs", 4),           # 二択
    (r"賛否|意見が分かれ|議論", 3),             # 議論ワード
    (r"あなたはどう思|みんなはどう|お前らは", 4),# 意見募集
    (r"正しい|間違い|嘘|本当", 3),              # 正誤判断
    (r"良い|悪い|アリ|ナシ", 2),                # 価値判断
    (r"許せ|ありえない|最悪|最高", 3),          # 感情的な判断
]


def _score_debate(lines: List[str]) -> int:
    score = 0
    full = "\n".join(lines)
    for pattern, weight in _DEBATE_PATTERNS:
        if re.search(pattern, full):
            score += weight
    return min(20, score)


# =====================================================================
# チャンネル別ボーナス
# =====================================================================

CHANNEL_BONUS_PATTERNS: Dict[str, List[Tuple[str, int]]] = {
    "2ch-matome": [
        (r"草|w{3,}|ワロタ|面白", 3),
        (r"エロ|下ネタ|セクシー|おっぱい", 3),
        (r">>?\d+", 2),  # アンカー形式
    ],
    "scp-lab": [
        (r"SCP-\d+|オブジェクトクラス|Keter|Euclid|Safe", 3),
        (r"収容|実験|Dクラス|財団", 2),
    ],
    "pokemon-lab": [
        (r"ポケモン|種族値|図鑑|進化", 2),
        (r"闇設定|裏設定|都市伝説", 3),
    ],
}


def _channel_bonus(lines: List[str], channel_id: str) -> int:
    """チャンネルの強みを活かしているかのボーナス。"""
    patterns = CHANNEL_BONUS_PATTERNS.get(channel_id, [])
    if not patterns:
        return 0
    score = 0
    full = "\n".join(lines)
    for pattern, weight in patterns:
        if re.search(pattern, full):
            score += weight
    return min(10, score)  # ボーナスは最大10点


# =====================================================================
# メインエントリポイント
# =====================================================================

def score_viral_potential(
    short_scenario: List[Dict[str, Any]],
    *,
    title: str = "",
    channel_id: str = "",
    threshold: int = 45,
) -> Dict[str, Any]:
    """バイラルポテンシャルをスコアリングする。

    Args:
        short_scenario: シナリオ行リスト。
        title: 動画タイトル。
        channel_id: チャンネルID。
        threshold: 警告閾値（この値未満で警告）。

    Returns:
        {
            "score": int,            # 0-100 (+ボーナス)
            "passed": bool,
            "dimensions": {...},     # 各軸のスコア
            "channel_bonus": int,
            "suggestions": [...],    # 改善提案
        }
    """
    # テキスト行を抽出
    lines = []
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        if text:
            lines.append(text)

    if not lines:
        return {"score": 0, "passed": False, "reason": "empty_scenario"}

    # 5軸スコアリング
    dimensions = {
        "curiosity_gap": _score_curiosity(lines),
        "emotional_impact": _score_emotion(lines),
        "relatability": _score_relatability(lines),
        "shareability": _score_shareability(lines, title),
        "debate_potential": _score_debate(lines),
    }

    base_score = sum(dimensions.values())
    bonus = _channel_bonus(lines, channel_id)
    total = base_score + bonus
    passed = total >= threshold

    # 改善提案
    suggestions: List[str] = []
    if dimensions["curiosity_gap"] < 8:
        suggestions.append("冒頭に疑問形や「実は」を入れて好奇心ギャップを強化")
    if dimensions["emotional_impact"] < 8:
        suggestions.append("驚き・恐怖・笑いの感情トリガーを追加")
    if dimensions["relatability"] < 6:
        suggestions.append("「あなた」「みんな」等の直接呼びかけで共感性UP")
    if dimensions["shareability"] < 6:
        suggestions.append("具体的な数字や固有名詞を入れてシェアしやすく")
    if dimensions["debate_potential"] < 6:
        suggestions.append("「どっち派？」型の問いかけで議論性UP")

    status = "PASSED" if passed else "LOW"
    print(
        f"  {'✅' if passed else '⚠️'} ViralScore [{channel_id}]: "
        f"{total}pt ({status}) — "
        f"好奇心{dimensions['curiosity_gap']} "
        f"感情{dimensions['emotional_impact']} "
        f"共感{dimensions['relatability']} "
        f"シェア{dimensions['shareability']} "
        f"議論{dimensions['debate_potential']}"
        f"{f' +bonus{bonus}' if bonus else ''}"
    )

    if suggestions and not passed:
        for s in suggestions[:3]:
            print(f"     💡 {s}")

    return {
        "score": total,
        "passed": passed,
        "dimensions": dimensions,
        "channel_bonus": bonus,
        "suggestions": suggestions,
    }
