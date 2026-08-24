"""Cross-Channel Content Bridge — チャンネル間コンテンツ連携（Round 6）。

狙い:
    description_blocks のクロスプロモーション（説明文にリンクを載せる）とは異なり、
    **シナリオ本文**に姉妹チャンネルのトピックを自然に織り込む。

    例: SCP-labのシナリオで「この現象、実は妖怪の伝承にも似た話があるんだ」
    → 妖怪ラボへの興味を喚起 → チャンネル回遊 → 登録

    これにより:
    - チャンネルポートフォリオ全体の登録者を最大化
    - 「この人の他のチャンネルも面白そう」という認知を形成
    - 1つのバズが他チャンネルにも波及する

既存モジュールとの違い:
    - description_blocks.build_cross_promo_block: 説明文のリンク → 折りたたまれて読まれない
    - auto_comment: コメント欄 → シナリオ本文の話題連携は対象外
    - 本モジュール: シナリオ本文に自然な「話題のブリッジ」を1行追加
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

# =====================================================================
# チャンネル間トピック連携マップ
# =====================================================================
# (source, target): ブリッジが自然に成立するトピック領域と、
# 注入するブリッジ行のテンプレート

BRIDGE_MAP: Dict[Tuple[str, str], Dict[str, Any]] = {
    # SCP ↔ 妖怪
    ("scp-lab", "yokai-watch"): {
        "topics": ["超自然", "異常現象", "民間伝承", "怪異", "霊", "呪"],
        "templates": [
            "ちなみにこの現象、日本の妖怪伝承にも似た話が残ってるんだ。",
            "実はこのSCP、元ネタが日本の妖怪だって説もあるんだよ。",
        ],
    },
    ("yokai-watch", "scp-lab"): {
        "topics": ["収容", "怪異", "異常", "SCP", "財団", "超自然"],
        "templates": [
            "この妖怪、もしSCP財団が知ったら間違いなく収容対象だな。",
            "こういう伝承を記録してるのがSCP財団って組織なんだ。",
        ],
    },
    # SCP ↔ ラグナロク
    ("scp-lab", "akashic-librarian"): {
        "topics": ["記録", "文書", "報告書", "オカルト", "未解明"],
        "templates": [
            "こういう記録って、他にも世界中に残ってるんだ。",
            "この手の報告書、実は他にも未公開のものが山ほどある。",
        ],
    },
    ("akashic-librarian", "scp-lab"): {
        "topics": ["異常", "収容", "財団", "実験", "SCP"],
        "templates": [
            "ある組織は、こういった記録を『報告書』として体系化しているらしい。",
            "この種の記録を収集している財団が、実在するという噂もある。",
        ],
    },
    # 日常科学 ↔ ポケモン
    ("daily-science", "pokemon-lab"): {
        "topics": ["生物", "進化", "脳", "体", "DNA", "遺伝"],
        "templates": [
            "ちなみにこの仕組み、ポケモンの設定にも使われてるんだよ。",
            "実はこの科学的事実、ポケモンの裏設定の元ネタなんだ。",
        ],
    },
    ("pokemon-lab", "daily-science"): {
        "topics": ["科学", "理論", "実験", "研究", "DNA", "進化"],
        "templates": [
            "この設定、実は本当の科学がベースになってるんだよ。",
            "ゲームフリークはこの科学的事実を元にこの設定を作ったんだ。",
        ],
    },
    # 妖怪 ↔ ラグナロク
    ("yokai-watch", "akashic-librarian"): {
        "topics": ["伝承", "民話", "古文書", "記録", "オカルト"],
        "templates": [
            "この伝承、実はもっと深い記録が残ってるんだ。",
            "古い文書には、この妖怪についてもっと恐ろしい記述がある。",
        ],
    },
    ("akashic-librarian", "yokai-watch"): {
        "topics": ["妖怪", "伝承", "怪異", "民話", "地方"],
        "templates": [
            "この記録に登場する存在は、日本では古くから妖怪として知られている。",
            "実はこの話、ある妖怪の伝承と驚くほど一致している。",
        ],
    },
    # 2chまとめ ↔ 企業ホンネ
    ("2ch-matome", "company-facts"): {
        "topics": ["会社", "企業", "年収", "ブラック", "社畜", "仕事", "転職", "上司"],
        "templates": [
            "ちなみにこの企業のホンネ、もっとヤバいんだけどねw",
            "この会社の裏事情、マジでやべーんだわw",
        ],
    },
    ("company-facts", "2ch-matome"): {
        "topics": ["2ch", "スレ", "ネット", "匿名", "暴露"],
        "templates": [
            "この企業の話、2chのスレでもかなり盛り上がってましたね。",
            "元社員が匿名掲示板に書いた暴露がまた衝撃的なんです。",
        ],
    },
    # 日常科学 ↔ ラグナロク
    ("daily-science", "akashic-librarian"): {
        "topics": ["謎", "未解明", "宇宙", "量子", "意識"],
        "templates": [
            "この現象、科学では説明がつかない部分があるんだ。",
            "実はこの科学的事実の裏に、もっと深い謎が隠されてる。",
        ],
    },
    ("akashic-librarian", "daily-science"): {
        "topics": ["科学", "物理", "宇宙", "量子", "実験"],
        "templates": [
            "この記録には、ある科学的な裏付けが存在する。",
            "現代科学の観点から見ると、この記録は別の意味を持つ。",
        ],
    },
    # ポケモン ↔ 妖怪
    ("pokemon-lab", "yokai-watch"): {
        "topics": ["妖怪", "伝承", "民話", "元ネタ", "モチーフ"],
        "templates": [
            "このポケモンの元ネタ、実は日本の妖怪なんだよ。",
            "この設定、日本の妖怪伝承がモチーフになってるんだ。",
        ],
    },
    ("yokai-watch", "pokemon-lab"): {
        "topics": ["ポケモン", "ゲーム", "モチーフ", "元ネタ"],
        "templates": [
            "この妖怪、実はあるポケモンのモチーフになってるんだ。",
            "ゲーフリはこの妖怪を元にポケモンをデザインしたらしい。",
        ],
    },
}

# クロスチャンネルプロモ先（チャンネルごとの優先順位）
PROMO_PRIORITY: Dict[str, List[str]] = {
    "daily-science": ["pokemon-lab", "akashic-librarian"],
    "scp-lab": ["yokai-watch", "akashic-librarian"],
    "akashic-librarian": ["scp-lab", "yokai-watch"],
    "yokai-watch": ["scp-lab", "pokemon-lab"],
    "pokemon-lab": ["daily-science", "yokai-watch"],
    "2ch-matome": ["company-facts"],
    "company-facts": ["2ch-matome"],
}


# =====================================================================
# トピック照合
# =====================================================================

def _check_topic_match(text: str, topics: List[str]) -> bool:
    """テキストがトピックリストのいずれかに合致するか。"""
    text_lower = text.lower()
    for topic in topics:
        if topic in text_lower:
            return True
    return False


def find_bridge_opportunity(
    short_scenario: List[Dict[str, Any]],
    *,
    title: str = "",
    channel_id: str = "",
) -> Optional[Dict[str, Any]]:
    """シナリオとタイトルからブリッジ機会を探す。

    Returns:
        None（機会なし）or {
            "target_channel": str,
            "bridge_line": str,
            "matched_topic": str,
        }
    """
    targets = PROMO_PRIORITY.get(channel_id, [])
    if not targets:
        return None

    # シナリオ全文を結合
    full_text = title + " "
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        full_text += text + " "

    # 各ターゲットチャンネルとのブリッジ機会を探す
    for target in targets:
        key = (channel_id, target)
        bridge_def = BRIDGE_MAP.get(key)
        if not bridge_def:
            continue

        topics = bridge_def.get("topics", [])
        if _check_topic_match(full_text, topics):
            templates = bridge_def.get("templates", [])
            if templates:
                bridge_line = random.choice(templates)
                matched = [t for t in topics if t in full_text.lower()]
                return {
                    "target_channel": target,
                    "bridge_line": bridge_line,
                    "matched_topic": matched[0] if matched else "",
                }

    return None


# =====================================================================
# メインエントリポイント
# =====================================================================

def inject_bridge(
    short_scenario: List[Dict[str, Any]],
    *,
    title: str = "",
    channel_id: str = "",
    probability: float = 0.4,
) -> Dict[str, Any]:
    """シナリオにクロスチャンネルブリッジを注入する。

    毎回ではなく、probability の確率でのみ注入する（やりすぎると宣伝臭くなる）。

    Args:
        short_scenario: シナリオ行リスト。
        title: 動画タイトル。
        channel_id: チャンネルID。
        probability: 注入確率（0.0-1.0）。

    Returns:
        {
            "modified": bool,
            "target_channel": str,
            "bridge_line": str,
        }
    """
    if not short_scenario or len(short_scenario) < 4:
        return {"modified": False, "reason": "too_short"}

    # 確率チェック
    if random.random() > probability:
        return {"modified": False, "reason": "probability_skip"}

    # ブリッジ機会を探す
    opportunity = find_bridge_opportunity(
        short_scenario, title=title, channel_id=channel_id,
    )
    if not opportunity:
        return {"modified": False, "reason": "no_topic_match"}

    bridge_line = opportunity["bridge_line"]
    target = opportunity["target_channel"]

    # CTA行（最終行）の1つ前にブリッジ行を挿入
    # 挿入する際は、既存のspeaker構造を維持する
    insert_idx = len(short_scenario) - 1  # CTA行の前

    # speaker情報を推測（直前の行のspeakerを使う）
    prev_entry = short_scenario[insert_idx - 1] if insert_idx > 0 else {}
    speaker = prev_entry.get("speaker", "")

    # ブリッジ行を構築
    bridge_entry: Dict[str, Any] = {}
    if "text" in (short_scenario[0] if short_scenario else {}):
        bridge_entry = {"speaker": speaker, "text": bridge_line}
    else:
        bridge_entry = {"line": bridge_line}

    short_scenario.insert(insert_idx, bridge_entry)

    print(
        f"  🌉 CrossBridge [{channel_id}→{target}]: "
        f"{bridge_line[:40]}…"
    )

    return {
        "modified": True,
        "target_channel": target,
        "bridge_line": bridge_line,
        "matched_topic": opportunity.get("matched_topic", ""),
    }
