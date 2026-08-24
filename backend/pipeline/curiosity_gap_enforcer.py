"""Curiosity Gap Enforcer — 冒頭の情報ギャップ強制構築（Round 8）。

狙い:
    人間の脳は「知らない」状態に耐えられない。冒頭1-2行で
    「答えが気になる問い」を提示し、最後まで見ないと解決しない
    構造を強制する。

    Hook A/B（R6）はフック文言のバリエーションテスト。
    本モジュールは「情報ギャップ構造」そのものを保証する:
    1. 冒頭に未解決の問い/謎/矛盾を検出
    2. 不足している場合、チャンネルに合ったギャップを注入
    3. 回答が早すぎる場合（3行目以内に答え）を検出し警告

既存モジュールとの違い:
    - hook_ab_selector: フック文言をA/Bテスト → バリエーション選択
    - swipe_stop_injector: 低テンション行間にrehook追加
    - 本モジュール: 冒頭の「情報ギャップ構造」を検証・強制注入
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List

# =====================================================================
# ギャップパターン検出
# =====================================================================

# 冒頭にギャップが存在するパターン（問い・謎・矛盾）
_GAP_PATTERNS = [
    r"[？?]",                          # 疑問形
    r"なぜ|どうして|どうやって",          # Why/How疑問
    r"知って(る|いる|た|いた)?[？?]?",    # 「知ってる？」系
    r"(実は|じつは).*[。！]?$",          # 「実は〜」（隠された情報の示唆）
    r"(ヤバ|やば)(い|すぎ)",             # 衝撃示唆
    r"(信じ|しんじ)(られない|がたい)",     # 信じがたい事実
    r"(秘密|謎|闇|真相|裏側)",           # ミステリー語彙
    r"\d+[%％万億]",                    # 衝撃的数値
    r"(禁止|禁断|タブー|封印)",           # 禁忌系
    r"(誰も|絶対に).*ない",              # 否定の強調
]

# 回答を示すパターン（ギャップの早期解消）
_ANSWER_PATTERNS = [
    r"(答え|理由|原因|正体|真実)は",
    r"つまり|要するに|結論",
    r"(だから|なので|そのため).*[。]$",
]


def _has_gap(text: str) -> bool:
    """テキストに情報ギャップが含まれるかチェック。"""
    for pattern in _GAP_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def _has_answer(text: str) -> bool:
    """テキストが回答/結論を含むかチェック。"""
    for pattern in _ANSWER_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


# =====================================================================
# チャンネル別ギャップテンプレート
# =====================================================================

GAP_TEMPLATES: Dict[str, List[str]] = {
    "daily-science": [
        "これ、科学的にはありえないはずなんだけど…",
        "99%の人が間違って覚えてる科学の常識がある",
        "NASAが隠してた事実、知ってる？",
    ],
    "scp-lab": [
        "この収容記録、最後まで読んだ職員は全員[データ削除]された",
        "財団が最も恐れるオブジェクト…それは意外なものだった",
        "なぜこのSCPだけ、収容手順が████なのか",
    ],
    "2ch-matome": [
        "このスレ、途中からガチでヤバい展開になるんだが",
        ">>1の正体が判明した時のスレの反応がこちらｗｗｗ",
        "嫁に内緒で○○した結果ｗｗｗｗ",
    ],
    "company-facts": [
        "この企業の売上、実は○○で成り立っている",
        "社員すら知らない、あの大企業の裏の顔",
        "なぜこの会社だけ不況でも潰れないのか",
    ],
    "pokemon-lab": [
        "この設定、ゲームでは絶対に見れないんだけど…",
        "ポケモンの中で1体だけ、ヤバい裏設定があるやつがいる",
        "図鑑説明が怖すぎて海外で規制されたポケモンがいる",
    ],
    "yokai-watch": [
        "この妖怪に遭遇したら、絶対に○○してはいけない",
        "日本で最も目撃報告が多い妖怪…その正体は",
        "あの有名な怪談、実話だった可能性が出てきた",
    ],
    "akashic-librarian": [
        "書庫ラグナロクが記録していた、人類最大の転換点",
        "この記録だけ、なぜか途中で途切れている",
        "未来の記録に、ありえない日付が刻まれていた",
    ],
}

_DEFAULT_GAP_TEMPLATES = [
    "これ、最後まで見ないと意味がわからないんだけど…",
    "99%の人が知らない事実がある",
    "この話、途中で衝撃の展開がある",
]


# =====================================================================
# メインエントリポイント
# =====================================================================

def enforce_curiosity_gap(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """冒頭の情報ギャップ構造を検証し、不足なら注入する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。

    Returns:
        {
            "gap_found": bool,        # 既存ギャップの有無
            "gap_injected": bool,     # ギャップを注入したか
            "early_answer": bool,     # 早期回答が検出されたか
            "early_answer_line": int, # 早期回答の行番号（-1なら無し）
        }
    """
    if len(short_scenario) < 3:
        return {"gap_found": False, "gap_injected": False,
                "early_answer": False, "early_answer_line": -1}

    # ── 冒頭2行でギャップ検出 ──
    first_two_texts = []
    for entry in short_scenario[:2]:
        text = (entry.get("text") or entry.get("line") or "").strip()
        first_two_texts.append(text)

    gap_exists = any(_has_gap(t) for t in first_two_texts)

    # ── 早期回答チェック（3行目以内に答え） ──
    early_answer = False
    early_answer_line = -1
    for i, entry in enumerate(short_scenario[:3]):
        text = (entry.get("text") or entry.get("line") or "").strip()
        if _has_answer(text):
            early_answer = True
            early_answer_line = i
            break

    # ── ギャップ注入（不足の場合） ──
    injected = False
    if not gap_exists:
        templates = GAP_TEMPLATES.get(channel_id, _DEFAULT_GAP_TEMPLATES)
        gap_text = random.choice(templates)

        # 冒頭行のテキストの前にギャップを追加
        first_entry = short_scenario[0]
        text_key = "text" if "text" in first_entry else "line"
        original = first_entry.get(text_key, "")

        # ギャップ → 改行なしで元のテキストに接続
        first_entry[text_key] = f"{gap_text}…{original}"
        injected = True

    action = "注入" if injected else ("検出済" if gap_exists else "不要")
    early_warn = f" | ⚠️早期回答L{early_answer_line}" if early_answer else ""
    print(
        f"  🕳️ CuriosityGap [{channel_id}]: {action}{early_warn}"
    )

    return {
        "gap_found": gap_exists,
        "gap_injected": injected,
        "early_answer": early_answer,
        "early_answer_line": early_answer_line,
    }
