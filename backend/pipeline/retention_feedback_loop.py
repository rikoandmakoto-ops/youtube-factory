"""Retention Feedback Loop — リテンション分析→シナリオ生成フィードバック（Round 7）。

狙い:
    retention_analyzer と success_analyzer が収集したデータは
    data/analytics/ に蓄積されているが、シナリオ生成に直接フィードバック
    されていない（identified gap）。

    本モジュールは:
    1. retention_insights.json から離脱ポイントパターンを読み取り
    2. success_patterns.json から成功パターンを読み取り
    3. チャンネル別の「やるべき/避けるべき」ルールを生成
    4. シナリオのpost-process で具体的な修正を適用

    修正の種類:
    - 離脱ポイントパターンに該当する構造を検出→警告or修正
    - 成功パターンの構造要素が欠けている場合→追加推奨
    - チャンネル別の「勝ちパターン」を強制適用

既存モジュールとの違い:
    - retention_analyzer: データを"収集・蓄積"する → 生成には介入しない
    - success_analyzer: 成功パターンを"分類"する → 生成には介入しない
    - improvement_queue: CTR不足時に再生成を"キュー"する → 構造修正はしない
    - 本モジュール: 蓄積データを"シナリオ修正"に直接適用 → フィードバックループ完成
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# =====================================================================
# データ読み込み
# =====================================================================

ANALYTICS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "analytics"


def _load_retention_insights() -> Dict[str, Any]:
    """retention_insights.json を読み込む。"""
    path = ANALYTICS_DIR / "retention_insights.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _load_success_patterns() -> Dict[str, Any]:
    """success_patterns.json を読み込む。"""
    path = ANALYTICS_DIR / "success_patterns.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# =====================================================================
# 離脱パターンルール
# =====================================================================

# 離脱ポイントの一般的な原因パターン（retention_insightsがない場合のフォールバック）
_FALLBACK_DROP_PATTERNS: List[Dict[str, Any]] = [
    {
        "name": "mid_explanation_drop",
        "description": "中盤の長い説明で離脱",
        "pattern": r"(つまり|要するに|簡単に言うと).{30,}",
        "position": "middle",  # 全体の30-70%位置
        "fix": "説明を短くし、具体例や驚きの事実で分割",
    },
    {
        "name": "slow_transition",
        "description": "展開の遅い転換部分で離脱",
        "pattern": r"^(さて|では|ということで|話を戻すと)",
        "position": "any",
        "fix": "転換語を驚き表現に置換（例: 「さて」→「ここでヤバい事実」）",
    },
    {
        "name": "predictable_ending",
        "description": "予測可能な結末で離脱",
        "pattern": r"(というわけで|まとめると|結論として)",
        "position": "last_quarter",
        "fix": "結論を意外な角度から再提示",
    },
]

# 転換語の置換マップ
_TRANSITION_REPLACEMENTS: Dict[str, List[str]] = {
    "さて": ["ここで衝撃の事実", "ところが", "でもここからが本番"],
    "では": ["実はここで", "ここで驚くべきことに"],
    "ということで": ["でもちょっと待ってほしい", "と思うじゃん？"],
    "話を戻すと": ["ここで一気に話が変わる", "ここで爆弾投下"],
    "続いて": ["さらにヤバいことに", "追い打ちをかけるように"],
    "次に": ["しかもここで", "そしてとどめに"],
}


# =====================================================================
# 成功パターンルール
# =====================================================================

# 成功パターンの構造要素（success_patternsがない場合のフォールバック）
_FALLBACK_SUCCESS_ELEMENTS: Dict[str, List[Dict[str, Any]]] = {
    "daily-science": [
        {"element": "number_hook", "pattern": r"\d+[%万億]", "position": "first_quarter",
         "description": "冒頭に具体的な数字"},
        {"element": "counter_intuitive", "pattern": r"(実は|逆に|常識と真逆)",
         "position": "any", "description": "反直感的な事実"},
    ],
    "scp-lab": [
        {"element": "classification", "pattern": r"(Keter|Euclid|Safe|Thaumiel)",
         "position": "first_quarter", "description": "冒頭でオブジェクトクラス言及"},
        {"element": "incident", "pattern": r"(事案|インシデント|実験記録)",
         "position": "middle", "description": "中盤に具体的な事案"},
    ],
    "2ch-matome": [
        {"element": "reaction", "pattern": r"(草|ワロタ|w{2,}|面白)",
         "position": "any", "description": "リアクションワード散在"},
        {"element": "anchor", "pattern": r">>?\d+",
         "position": "any", "description": "アンカー形式の使用"},
        {"element": "ero_element", "pattern": r"(エロ|下ネタ|セクシー|おっぱい|巨乳|パンツ)",
         "position": "any", "description": "軽いエロ要素"},
    ],
    "company-facts": [
        {"element": "revenue", "pattern": r"(売上|利益|時価総額|年商)",
         "position": "first_quarter", "description": "冒頭に財務数字"},
        {"element": "scandal", "pattern": r"(闇|不正|隠蔽|炎上|スキャンダル)",
         "position": "any", "description": "企業の闇要素"},
    ],
    "pokemon-lab": [
        {"element": "specific_pokemon", "pattern": r"[ァ-ヶー]{3,}",
         "position": "first_quarter", "description": "冒頭で具体的なポケモン名"},
        {"element": "dark_lore", "pattern": r"(闇設定|裏設定|都市伝説|図鑑説明)",
         "position": "any", "description": "闇設定・裏設定要素"},
    ],
    "yokai-watch": [
        {"element": "folklore", "pattern": r"(伝承|伝説|言い伝え|昔話)",
         "position": "first_quarter", "description": "伝承要素"},
        {"element": "horror", "pattern": r"(怖|恐|不気味|ゾッと|背筋)",
         "position": "last_quarter", "description": "後半のホラー演出"},
    ],
}


# =====================================================================
# フィードバック適用
# =====================================================================

def _apply_drop_pattern_fixes(
    short_scenario: List[Dict[str, Any]],
    drop_patterns: List[Dict[str, Any]],
    channel_id: str,
) -> List[str]:
    """離脱パターンに該当する箇所を修正。"""
    fixes_applied = []
    n = len(short_scenario)

    for i, entry in enumerate(short_scenario):
        text_key = "text" if "text" in entry else "line"
        text = entry.get(text_key, "")
        if not text:
            continue

        position_ratio = i / max(n - 1, 1)

        for dp in drop_patterns:
            pat = dp.get("pattern", "")
            pos = dp.get("position", "any")

            # 位置フィルタ
            if pos == "middle" and not (0.3 <= position_ratio <= 0.7):
                continue
            if pos == "first_quarter" and position_ratio > 0.25:
                continue
            if pos == "last_quarter" and position_ratio < 0.75:
                continue

            if pat and re.search(pat, text):
                # 転換語の修正
                for old, replacements in _TRANSITION_REPLACEMENTS.items():
                    if old in text:
                        import random
                        new = random.choice(replacements)
                        text = text.replace(old, new, 1)
                        entry[text_key] = text
                        fixes_applied.append(
                            f"行{i+1}: 「{old}」→「{new}」（{dp['name']}）"
                        )
                        break

    return fixes_applied


def _check_success_elements(
    short_scenario: List[Dict[str, Any]],
    channel_id: str,
    success_elements: List[Dict[str, Any]],
) -> List[str]:
    """成功パターンの構造要素が含まれているかチェック。"""
    missing = []
    n = len(short_scenario)

    # テキスト全体を結合
    full_text = ""
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        full_text += text + "\n"

    for elem in success_elements:
        pat = elem.get("pattern", "")
        if pat and not re.search(pat, full_text):
            missing.append(elem.get("description", elem.get("element", "不明")))

    return missing


# =====================================================================
# メインエントリポイント
# =====================================================================

def apply_retention_feedback(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """リテンション分析データに基づいてシナリオを最適化する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。

    Returns:
        {
            "data_available": bool,
            "drop_fixes": [...],         # 適用した離脱パターン修正
            "missing_elements": [...],   # 欠けている成功パターン要素
            "insights_used": int,        # 使用したインサイト数
        }
    """
    if not short_scenario:
        return {"data_available": False, "drop_fixes": [],
                "missing_elements": [], "insights_used": 0}

    # データ読み込み
    retention_data = _load_retention_insights()
    success_data = _load_success_patterns()
    data_available = bool(retention_data or success_data)

    # 離脱パターン取得
    # retention_data からチャンネル固有のパターンを探す
    channel_drops = []
    if retention_data:
        for channel_key, insights in retention_data.items():
            if channel_id in channel_key:
                drops = insights if isinstance(insights, list) else []
                channel_drops.extend(drops)

    # フォールバック
    if not channel_drops:
        channel_drops = _FALLBACK_DROP_PATTERNS

    # 成功パターン要素取得
    channel_success = []
    if success_data:
        for channel_key, patterns in success_data.items():
            if channel_id in channel_key:
                elems = patterns if isinstance(patterns, list) else []
                channel_success.extend(elems)

    # フォールバック
    if not channel_success:
        channel_success = _FALLBACK_SUCCESS_ELEMENTS.get(channel_id, [])

    # 離脱パターン修正
    drop_fixes = _apply_drop_pattern_fixes(
        short_scenario, channel_drops, channel_id
    )

    # 成功要素チェック
    missing_elements = _check_success_elements(
        short_scenario, channel_id, channel_success
    )

    insights_used = len(channel_drops) + len(channel_success)

    # ログ
    fix_count = len(drop_fixes)
    miss_count = len(missing_elements)
    if fix_count or miss_count:
        print(
            f"  📊 RetentionFeedback [{channel_id}]: "
            f"修正{fix_count}件, 不足要素{miss_count}件"
            f" (data={'live' if data_available else 'fallback'})"
        )
        for fix in drop_fixes[:2]:
            print(f"     🔧 {fix}")
        for miss in missing_elements[:2]:
            print(f"     💡 不足: {miss}")
    else:
        print(
            f"  ✅ RetentionFeedback [{channel_id}]: "
            f"パターン適合OK (data={'live' if data_available else 'fallback'})"
        )

    return {
        "data_available": data_available,
        "drop_fixes": drop_fixes,
        "missing_elements": missing_elements,
        "insights_used": insights_used,
    }
