"""季節カレンダー — 月ごとの視聴トレンドに合わせてテーマ生成の優先度を調整する。

狙い:
    競合分析で確認された季節性:
    - 7〜8月: ホラー・怖い話の検索量が年間ピーク（SCP/妖怪/ラグナロク系に追い風）
    - 12月〜1月: 年末年始の暇な時間帯に再生数が全体的に伸びる
    - ゲームリリース前後: ポケモン新作発売の前後1ヶ月は検索量2〜3倍
    - 季節の変わり目: 体の不思議（花粉症・冷え・眠気）が検索される

    テーマ生成時にこの季節ブーストを注入し、タイムリーなテーマが優先生成されるようにする。
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple


# 月別のチャンネルブースト定義
# boost_factor: テーマ生成時の優先度倍率（1.0 = 通常、2.0 = 2倍優先）
# suggested_angles: この時期に追加で提案すべきテーマの切り口
SEASONAL_RULES: Dict[str, List[Dict[str, Any]]] = {
    "daily-science": [
        {"months": [3, 4], "boost_factor": 1.5, "label": "春の体の変化",
         "suggested_angles": ["花粉症の仕組み", "春眠の科学", "新生活のストレスと体"]},
        {"months": [6, 7, 8], "boost_factor": 1.3, "label": "夏の体の不思議",
         "suggested_angles": ["熱中症の仕組み", "なぜ汗をかくと涼しくなるのか", "蚊に刺されやすい人の特徴"]},
        {"months": [11, 12, 1], "boost_factor": 1.3, "label": "冬の体の不思議",
         "suggested_angles": ["なぜ冬は眠いのか", "しもやけの仕組み", "乾燥肌の科学"]},
    ],
    "scp-lab": [
        {"months": [7, 8], "boost_factor": 2.0, "label": "夏のホラーシーズン",
         "suggested_angles": ["最恐SCP特集", "認識災害SCP", "実は身近なSCP"]},
        {"months": [10], "boost_factor": 1.8, "label": "ハロウィンシーズン",
         "suggested_angles": ["ハロウィン級のSCP特集", "変身・変容系SCP"]},
        {"months": [12, 1], "boost_factor": 1.3, "label": "年末年始の暇視聴",
         "suggested_angles": ["SCP総まとめ", "最も再生された回の続編"]},
    ],
    "2ch-matome": [
        {"months": [4], "boost_factor": 1.5, "label": "新生活シーズン",
         "suggested_angles": ["新社会人あるある", "引っ越し先でやらかした話", "新しい上司がヤバい"]},
        {"months": [8], "boost_factor": 1.3, "label": "お盆・夏休み",
         "suggested_angles": ["帰省あるある", "夏休みの暇つぶし", "お盆の親戚トラブル"]},
        {"months": [12], "boost_factor": 1.5, "label": "忘年会シーズン",
         "suggested_angles": ["忘年会でやらかした話", "年末の大掃除で出てきた物", "今年一番の失敗談"]},
    ],
    "company-facts": [
        {"months": [3, 4], "boost_factor": 1.8, "label": "就活・転職シーズン",
         "suggested_angles": ["新卒が知るべき企業の裏側", "転職先として人気の企業", "ブラック企業の見分け方"]},
        {"months": [6], "boost_factor": 1.3, "label": "ボーナスシーズン",
         "suggested_angles": ["ボーナスが高い企業ランキング", "賞与の裏事情"]},
        {"months": [9, 10], "boost_factor": 1.5, "label": "秋の転職シーズン",
         "suggested_angles": ["中途採用に強い企業", "年収アップ転職の実態"]},
    ],
    "pokemon-lab": [
        {"months": [2, 11], "boost_factor": 2.0, "label": "ポケモン新作シーズン",
         "suggested_angles": ["新ポケモンの種族値予想", "歴代御三家比較", "新作で変わった仕様"]},
        {"months": [7, 8], "boost_factor": 1.5, "label": "夏休みポケモン映画",
         "suggested_angles": ["映画のポケモン裏設定", "伝説ポケモンの知られざる事実"]},
        {"months": [12, 1], "boost_factor": 1.3, "label": "年末年始ポケモン",
         "suggested_angles": ["今年のポケモン総まとめ", "歴代最強ランキング"]},
    ],
    "yokai-watch": [
        {"months": [7, 8], "boost_factor": 2.0, "label": "夏の怪談シーズン",
         "suggested_angles": ["最も怖い元ネタを持つ妖怪", "夏に出る妖怪の伝承", "お盆と妖怪の関係"]},
        {"months": [10], "boost_factor": 1.5, "label": "ハロウィン",
         "suggested_angles": ["洋妖怪vs和妖怪", "ハロウィンに出そうな妖怪"]},
    ],
    "akashic-librarian": [
        {"months": [7, 8], "boost_factor": 1.8, "label": "夏のオカルトシーズン",
         "suggested_angles": ["心霊・超常現象", "古代文明の謎", "予言の記録"]},
        {"months": [12], "boost_factor": 1.5, "label": "年末の予言",
         "suggested_angles": ["来年の予言", "ノストラダムスの未解読預言"]},
    ],
}


def get_seasonal_boost(
    channel_id: str,
    *,
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    """指定チャンネルの現在の季節ブースト情報を返す。

    Returns:
        {
            "boost_factor": float,     # 1.0 = 通常
            "label": str,              # ブーストの名前（空文字 = 通常期）
            "suggested_angles": [...], # 追加で提案すべきテーマ切り口
            "is_boosted": bool,        # ブースト中かどうか
        }
    """
    d = target_date or date.today()
    month = d.month

    rules = SEASONAL_RULES.get(channel_id, [])
    for rule in rules:
        if month in rule.get("months", []):
            return {
                "boost_factor": rule.get("boost_factor", 1.0),
                "label": rule.get("label", ""),
                "suggested_angles": rule.get("suggested_angles", []),
                "is_boosted": True,
            }

    return {
        "boost_factor": 1.0,
        "label": "",
        "suggested_angles": [],
        "is_boosted": False,
    }


def get_seasonal_prompt_addendum(
    channel_id: str,
    *,
    target_date: Optional[date] = None,
) -> str:
    """テーマ生成プロンプトに追加する季節情報ブロックを返す。

    theme_queue.py の replenish() やシナリオ生成プロンプトから呼ばれる。
    ブースト対象外の月は空文字列を返す。
    """
    boost = get_seasonal_boost(channel_id, target_date=target_date)
    if not boost["is_boosted"]:
        return ""

    lines = [
        f"\n# 季節ブースト: {boost['label']}（現在 {boost['boost_factor']}倍優先）",
        "現在この時期はこのジャンルの検索量・視聴数が通常より高いため、",
        "以下の切り口を優先的に取り入れてください:",
    ]
    for angle in boost["suggested_angles"]:
        lines.append(f"  - {angle}")

    return "\n".join(lines)


def get_all_boosts(
    *,
    target_date: Optional[date] = None,
) -> Dict[str, Dict[str, Any]]:
    """全チャンネルのブースト状況を一覧で返す。"""
    return {
        cid: get_seasonal_boost(cid, target_date=target_date)
        for cid in SEASONAL_RULES
    }
