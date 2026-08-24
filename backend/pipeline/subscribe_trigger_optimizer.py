"""Subscribe Trigger Optimizer — 有機的な登録トリガー最適化（Round 8）。

狙い:
    登録者数を最大化するには、明示的なCTA（「チャンネル登録してね」）
    だけでなく、視聴者が自発的に「このチャンネルフォローしたい」と
    思う瞬間を動画内に作る必要がある。

    本モジュールは以下の「登録衝動トリガー」を戦略的に配置する:
    1. シリーズ性の示唆（「次回はもっとヤバい話をする」）
    2. 専門性の証明（「このチャンネルでしか聞けない話」）
    3. コミュニティ帰属（「登録者の間では有名な話だけど」）

既存モジュールとの違い:
    - cta_rotator (R6): 明示的なCTA文言をローテーション
    - 本モジュール: コンテンツ内に「自然な登録衝動」を埋め込む
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List

# =====================================================================
# 登録トリガーテンプレート
# =====================================================================

# 3タイプ: series_hint, expertise_proof, community_belong

TRIGGERS: Dict[str, Dict[str, List[str]]] = {
    "daily-science": {
        "series_hint": [
            "次回はこれよりさらにヤバい実験の話をする",
            "この続き、次の動画でもっと深掘りするよ",
        ],
        "expertise_proof": [
            "これ、このチャンネルでしか解説してないんだけど",
            "論文を直接読んで解説してるチャンネル、意外と少ないんだよね",
        ],
        "community_belong": [
            "前回の動画を見た人ならピンとくると思うけど",
            "うちの視聴者なら知ってると思うけど",
        ],
    },
    "scp-lab": {
        "series_hint": [
            "次回、これより上位のオブジェクトを紹介する",
            "この財団シリーズ、次がいよいよ核心だ",
        ],
        "expertise_proof": [
            "原文の報告書を精査した上での解説だ",
            "このレベルの分析は他では見れないぞ",
        ],
        "community_belong": [
            "財団職員ならこの収容手順の異常さに気づくはずだ",
            "前回のSCPを覚えている奴なら、この関連性がわかるだろう",
        ],
    },
    "2ch-matome": {
        "series_hint": [
            "次回のスレ、これの100倍ヤバいからなｗ",
            "この話の続き、次の動画でまとめるわ",
        ],
        "expertise_proof": [
            "このスレ、他のまとめじゃカットされてる部分まで拾ってる",
            "この手の良スレ見つけてくるの得意なんよｗ",
        ],
        "community_belong": [
            "常連ニキならこのノリわかるよなｗ",
            "前回のスレ見た奴は察してるだろうけど",
        ],
    },
    "company-facts": {
        "series_hint": [
            "次回はこの企業のライバルの闇に迫る",
            "次の動画でさらに衝撃的な事実を紹介する",
        ],
        "expertise_proof": [
            "決算書を直接読み込んで分析しているから、精度が違う",
            "この視点での企業分析は、ここでしか見れない",
        ],
        "community_belong": [
            "うちの視聴者はビジネスリテラシーが高いから言うけど",
            "前回の動画を見た人なら、この数字の異常さがわかるはず",
        ],
    },
    "pokemon-lab": {
        "series_hint": [
            "次回は伝説ポケモンの闇設定を暴く",
            "このシリーズ、次がいよいよ本命のポケモンだ",
        ],
        "expertise_proof": [
            "内部データまで調べてるからこそわかる設定なんだけど",
            "ここまで掘り下げてるポケモン解説、他にある？",
        ],
        "community_belong": [
            "前回の動画の考察を見てくれた人ならわかると思うけど",
            "うちのポケモン勢なら知ってるよね",
        ],
    },
    "yokai-watch": {
        "series_hint": [
            "次回はこの妖怪より格上の存在を紹介する",
            "この怪談シリーズ、次回が一番怖い",
        ],
        "expertise_proof": [
            "古文献を直接あたってるからこその情報だよ",
            "この妖怪の本当の話は、ここでしか聞けない",
        ],
        "community_belong": [
            "前回の妖怪を覚えている人なら、この繋がりに気づくはず",
            "うちの視聴者は怪談の質にうるさいから",
        ],
    },
    "akashic-librarian": {
        "series_hint": [
            "次の記録はこれよりさらに深層に迫る",
            "このシリーズ、次回が禁断の記録だ",
        ],
        "expertise_proof": [
            "この解読は独自の分析に基づいている",
            "書庫ラグナロクの記録をここまで体系的に扱うのは、ここだけだ",
        ],
        "community_belong": [
            "前回の記録を読み解いた探索者なら、この符号に気づくはずだ",
            "このチャンネルの探索者たちは、すでに核心に近づいている",
        ],
    },
}

_DEFAULT_TRIGGERS = {
    "series_hint": ["次回はもっとすごい話をする"],
    "expertise_proof": ["ここでしか聞けない話だよ"],
    "community_belong": ["前回見た人ならわかると思うけど"],
}


# =====================================================================
# メインエントリポイント
# =====================================================================

def optimize_subscribe_triggers(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """シナリオに有機的な登録トリガーを注入する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。

    Returns:
        {
            "trigger_type": str,       # 注入したトリガータイプ
            "trigger_text": str,       # 注入テキスト
            "position": int,           # 注入位置
            "injected": bool,
        }
    """
    if len(short_scenario) < 4:
        return {"trigger_type": "", "trigger_text": "",
                "position": -1, "injected": False}

    n = len(short_scenario)
    ch_triggers = TRIGGERS.get(channel_id, _DEFAULT_TRIGGERS)

    # トリガータイプをランダム選択（均等確率）
    trigger_type = random.choice(list(ch_triggers.keys()))
    options = ch_triggers[trigger_type]
    trigger_text = random.choice(options)

    # 注入位置の決定
    # - series_hint: 最後から2番目の行（次回予告感）
    # - expertise_proof: 中盤（40-60%）の専門情報付近
    # - community_belong: 序盤（20-30%）で仲間意識を形成
    if trigger_type == "series_hint":
        pos = max(1, n - 2)
    elif trigger_type == "expertise_proof":
        pos = max(1, int(n * random.uniform(0.4, 0.6)))
    else:  # community_belong
        pos = max(1, int(n * random.uniform(0.2, 0.3)))

    pos = min(pos, n - 1)

    # 注入
    entry = short_scenario[pos]
    text_key = "text" if "text" in entry else "line"
    current = entry.get(text_key, "").rstrip()

    if current and not current.endswith(("。", "！", "？", "…", "!", "?")):
        current += "。"

    entry[text_key] = f"{current}{trigger_text}"

    print(
        f"  🔔 SubTrigger [{channel_id}]: "
        f"type={trigger_type} @ L{pos}"
    )

    return {
        "trigger_type": trigger_type,
        "trigger_text": trigger_text,
        "position": pos,
        "injected": True,
    }
