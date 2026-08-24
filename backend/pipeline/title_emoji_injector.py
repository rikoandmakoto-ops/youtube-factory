"""Title Emoji Injector — タイトル絵文字CTR最適化（Round 7）。

狙い:
    2026年のYouTubeショートにおいて、タイトルへの戦略的な絵文字配置が
    CTRを平均12-18%向上させることが複数の調査で報告されている。

    本モジュールは:
    1. チャンネルのトーンに合った絵文字パレットを管理
    2. タイトルのテーマを解析して最適な絵文字を選択
    3. 配置位置を最適化（先頭 vs 末尾 vs 挟み込み）
    4. 過剰使用を防止（最大2個）
    5. 2ch-matome用に軽い下ネタ絵文字を優先

既存モジュールとの違い:
    - title_quality: タイトルのCTRをスコアリング（絵文字は対象外）
    - hashtag_optimizer: ハッシュタグ（#xxx）の最適化 → 絵文字は非対象
    - 本モジュール: 絵文字の戦略的な配置 → CTR向上の別軸
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

# =====================================================================
# チャンネル別絵文字パレット
# =====================================================================

CHANNEL_EMOJI_PALETTES: Dict[str, Dict[str, List[str]]] = {
    "daily-science": {
        "default": ["🔬", "🧪", "⚡", "🌍", "💡", "🧬"],
        "shock":   ["😱", "🤯", "⚠️"],
        "number":  ["📊", "📈", "💯"],
        "mystery": ["🔍", "❓", "👀"],
    },
    "scp-lab": {
        "default": ["🔒", "⚠️", "☠️", "🏚️", "👁️"],
        "shock":   ["😱", "💀", "🫣"],
        "danger":  ["☢️", "🚫", "⛔"],
        "mystery": ["❓", "🔍", "📁"],
    },
    "2ch-matome": {
        "default": ["😂", "🤣", "💦", "🍑", "😏"],
        "ero":     ["🍑", "💦", "😏", "🫦", "♨️", "🔞"],
        "shock":   ["😱", "🤯", "😨"],
        "funny":   ["🤣", "😂", "💀", "草"],
        "fight":   ["⚔️", "💢", "🔥"],
    },
    "company-facts": {
        "default": ["🏢", "💰", "📊", "🔍"],
        "shock":   ["😱", "🤯", "⚠️"],
        "money":   ["💰", "💸", "📈", "📉"],
        "dark":    ["🌑", "🕳️", "💀"],
    },
    "pokemon-lab": {
        "default": ["⚡", "🎮", "🔥", "💧", "🌿"],
        "shock":   ["😱", "🤯", "😨"],
        "mystery": ["🔍", "❓", "👀", "🕵️"],
        "dark":    ["💀", "👻", "🌑"],
    },
    "yokai-watch": {
        "default": ["👻", "🏚️", "🌙", "⛩️"],
        "shock":   ["😱", "😰", "🫣"],
        "scary":   ["💀", "☠️", "👹", "😈"],
        "mystery": ["🔍", "❓", "👁️"],
    },
    "akashic-librarian": {
        "default": ["📖", "🔮", "✨", "🌌"],
        "mystery": ["🔍", "❓", "👁️"],
        "cosmic":  ["🌌", "⭐", "🌀"],
    },
}

# =====================================================================
# テーマ→絵文字カテゴリ マッピング
# =====================================================================

_THEME_CATEGORY_MAP: List[Tuple[str, str]] = [
    # パターン, カテゴリ（チャンネル固有カテゴリを先にチェック）
    (r"エロ|セクシー|下ネタ|おっぱい|巨乳|胸|パンツ|裸|ムラ|興奮", "ero"),
    (r"闇|ヤバ|衝撃|恐|怖|やべえ|マジ", "shock"),
    (r"草|w{2,}|ワロタ|面白|笑|ウケる", "funny"),
    (r"\d+万|\d+億|\d+兆|年収|売上|利益|倒産|赤字", "money"),
    (r"死|殺|消[えされ]|危険|致死|毒", "danger"),
    (r"怪談|呪|霊|心霊|怨|祟", "scary"),
    (r"謎|秘密|隠|封印|未解明|不思議", "mystery"),
    (r"\d+[%％]|統計|データ|調査|研究", "number"),
    (r"宇宙|銀河|次元|時空|量子", "cosmic"),
    (r"喧嘩|対決|vs|バトル|炎上", "fight"),
]


def _detect_theme_category(title: str, channel_id: str) -> str:
    """タイトルからテーマカテゴリを推定。"""
    for pattern, category in _THEME_CATEGORY_MAP:
        if re.search(pattern, title, re.IGNORECASE):
            # このチャンネルにそのカテゴリがあるか確認
            palette = CHANNEL_EMOJI_PALETTES.get(channel_id, {})
            if category in palette:
                return category
    return "default"


# =====================================================================
# 絵文字配置ロジック
# =====================================================================

def _select_emoji(
    title: str,
    channel_id: str,
    category: str,
) -> Optional[str]:
    """タイトルとカテゴリから最適な絵文字を1つ選択。"""
    palette = CHANNEL_EMOJI_PALETTES.get(channel_id, {})
    emojis = palette.get(category, palette.get("default", []))
    if not emojis:
        return None

    # タイトル中に既に絵文字がある場合はスキップ
    existing_emoji_count = len(re.findall(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FEFF]",
        title,
    ))
    if existing_emoji_count >= 2:
        return None

    return random.choice(emojis)


def _place_emoji(title: str, emoji: str, channel_id: str) -> str:
    """タイトル内の最適位置に絵文字を配置。"""
    # 既存の絵文字数チェック
    existing = len(re.findall(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FEFF]",
        title,
    ))

    if existing >= 2:
        return title

    # 2ch-matome: 末尾配置が多い（2chっぽさ）
    if channel_id == "2ch-matome":
        return f"{title}{emoji}"

    # SCP / yokai-watch: 先頭配置（恐怖感演出）
    if channel_id in ("scp-lab", "yokai-watch"):
        return f"{emoji}{title}"

    # それ以外: 先頭に置くパターンが最もCTR高い（視認性）
    # ただし「#」タグ付きタイトルは末尾
    if title.startswith("#"):
        return f"{title}{emoji}"
    return f"{emoji}{title}"


# =====================================================================
# セカンド絵文字（オプション）
# =====================================================================

def _maybe_add_second_emoji(
    title: str,
    channel_id: str,
    category: str,
) -> str:
    """40%の確率で2個目の絵文字を追加（過剰にならないよう制御）。"""
    if random.random() > 0.4:
        return title

    existing = len(re.findall(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FEFF]",
        title,
    ))
    if existing >= 2:
        return title

    palette = CHANNEL_EMOJI_PALETTES.get(channel_id, {})
    emojis = palette.get(category, palette.get("default", []))
    if not emojis:
        return title

    second = random.choice(emojis)

    # 先頭に既にあれば末尾に、末尾にあれば先頭に
    if re.match(r"^[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", title):
        return f"{title}{second}"
    else:
        return f"{second}{title}"


# =====================================================================
# メインエントリポイント
# =====================================================================

def inject_title_emoji(
    title: str,
    *,
    channel_id: str = "",
    short_scenario: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """タイトルに戦略的な絵文字を注入する。

    Args:
        title: 元のタイトル。
        channel_id: チャンネルID。
        short_scenario: シナリオ行リスト（テーマ推定用、省略可）。

    Returns:
        {
            "original_title": str,
            "enhanced_title": str,
            "emoji_added": str | None,
            "category": str,
            "modified": bool,
        }
    """
    if not title:
        return {"original_title": "", "enhanced_title": "",
                "emoji_added": None, "category": "none", "modified": False}

    # チャンネルパレットがなければスキップ
    if channel_id not in CHANNEL_EMOJI_PALETTES:
        return {"original_title": title, "enhanced_title": title,
                "emoji_added": None, "category": "unknown_channel",
                "modified": False}

    # テーマカテゴリ検出
    category = _detect_theme_category(title, channel_id)

    # 絵文字選択
    emoji = _select_emoji(title, channel_id, category)
    if not emoji:
        return {"original_title": title, "enhanced_title": title,
                "emoji_added": None, "category": category, "modified": False}

    # 配置
    enhanced = _place_emoji(title, emoji, channel_id)

    # 2個目チャレンジ
    enhanced = _maybe_add_second_emoji(enhanced, channel_id, category)

    modified = enhanced != title
    print(
        f"  {'🎨' if modified else '➡️'} TitleEmoji [{channel_id}]: "
        f"category={category}"
        f"{f' | {title[:20]}→{enhanced[:25]}' if modified else ' | no change'}"
    )

    return {
        "original_title": title,
        "enhanced_title": enhanced,
        "emoji_added": emoji if modified else None,
        "category": category,
        "modified": modified,
    }
