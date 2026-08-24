"""Originality Guard — コンテンツ独自性チェック（Round 7）。

狙い:
    2025年7月のYouTubeポリシー更新で、スクリプト類似度70%超のチャンネルは
    「再利用コンテンツ」として収益化停止。特に2chまとめ・ゆっくり解説系が
    大量にBANされた。

    本モジュールは:
    1. 過去N本のシナリオとの類似度をチェック
    2. テンプレ構造の繰り返し検出（毎回同じ導入パターン等）
    3. チャンネル固有の独自性ルール適用
    4. 70%超で警告、85%超でブロック推奨

    2ch-matome は特に厳しく:
    - スレタイのコピペ率チェック
    - レス引用のオリジナル編集度チェック
    - 導入パターンの多様性チェック

既存モジュールとの違い:
    - scenario_validator: 構造ルール（フック有無等）→ 独自性は対象外
    - title_quality: タイトル品質 → スクリプト内容は対象外
    - theme_dedup: テーマの重複排除 → スクリプト文面の類似度は見ない
    - 本モジュール: スクリプト全体の類似度 → YouTube収益化保護
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# =====================================================================
# 設定
# =====================================================================

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "originality"
MAX_HISTORY = 50  # 過去何本と比較するか
WARN_THRESHOLD = 0.70  # 70%以上で警告
BLOCK_THRESHOLD = 0.85  # 85%以上でブロック推奨

# 2ch-matome は特に厳格
CHANNEL_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "2ch-matome": (0.60, 0.75),  # 警告60%、ブロック75%
}


# =====================================================================
# テキスト正規化
# =====================================================================

def _normalize_for_comparison(text: str) -> str:
    """比較用にテキストを正規化。"""
    # 空白・改行統一
    text = re.sub(r"\s+", " ", text).strip()
    # 句読点・記号を除去
    text = re.sub(r"[、。！？!?…「」『』【】（）()・]", "", text)
    # 数字を統一（具体的な数字の違いは独自性とみなさない）
    text = re.sub(r"\d+", "NUM", text)
    return text


def _extract_scenario_text(short_scenario: List[Dict[str, Any]]) -> str:
    """シナリオリストからプレーンテキストを抽出。"""
    lines = []
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


# =====================================================================
# 類似度計算
# =====================================================================

def _text_similarity(a: str, b: str) -> float:
    """2つのテキスト間の類似度を0.0〜1.0で返す。"""
    if not a or not b:
        return 0.0
    norm_a = _normalize_for_comparison(a)
    norm_b = _normalize_for_comparison(b)
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _structural_similarity(
    scenario_a: List[str],
    scenario_b: List[str],
) -> float:
    """構造的な類似度（行数、行長パターン）。"""
    if not scenario_a or not scenario_b:
        return 0.0

    # 行数差
    len_ratio = min(len(scenario_a), len(scenario_b)) / max(len(scenario_a), len(scenario_b))

    # 行長パターンの相関
    lens_a = [len(line) for line in scenario_a]
    lens_b = [len(line) for line in scenario_b]
    # 短い方に合わせる
    min_len = min(len(lens_a), len(lens_b))
    lens_a = lens_a[:min_len]
    lens_b = lens_b[:min_len]

    if min_len == 0:
        return 0.0

    # 行長パターンの類似度
    diffs = [abs(a - b) for a, b in zip(lens_a, lens_b)]
    avg_diff = sum(diffs) / min_len
    pattern_sim = max(0.0, 1.0 - avg_diff / 30.0)  # 30文字差で0

    return (len_ratio + pattern_sim) / 2


# =====================================================================
# テンプレートパターン検出
# =====================================================================

# よくあるテンプレ導入パターン
_TEMPLATE_OPENERS = [
    r"^(今回は|今日は|本日は|さて今回は)",
    r"^(皆さん|みなさん|みんな)[、,]?(知って|こんにちは)",
    r"^(突然ですが|ところで|さて)",
    r"^(この|あの)(ポケモン|妖怪|SCP|企業|会社)[はがを]",
]

# テンプレ締め
_TEMPLATE_CLOSERS = [
    r"(以上|いかがでしたか|参考になれば)",
    r"(チャンネル登録|高評価|コメント)(を?お[願ねが]い|してね)",
    r"(それでは|ではまた|またね|バイバイ)",
]


def _check_template_patterns(
    scenario_lines: List[str],
    history_lines_list: List[List[str]],
) -> Dict[str, Any]:
    """テンプレパターンの繰り返しを検出。"""
    if not scenario_lines or not history_lines_list:
        return {"template_score": 0, "issues": []}

    issues = []
    opener = scenario_lines[0] if scenario_lines else ""
    closer = scenario_lines[-1] if scenario_lines else ""

    # 過去のオープナーとの重複チェック
    opener_matches = 0
    for hist_lines in history_lines_list[-10:]:  # 直近10本
        if hist_lines:
            hist_opener = hist_lines[0]
            if _text_similarity(opener, hist_opener) > 0.6:
                opener_matches += 1

    if opener_matches >= 3:
        issues.append(
            f"直近10本中{opener_matches}本で似た導入パターン使用 — "
            "テンプレ感が強く独自性低下"
        )

    # テンプレ語チェック
    for pattern in _TEMPLATE_OPENERS:
        if re.search(pattern, opener):
            issues.append(f"導入がテンプレパターン「{opener[:15]}…」")
            break

    for pattern in _TEMPLATE_CLOSERS:
        if re.search(pattern, closer):
            issues.append(f"締めがテンプレパターン「{closer[:15]}…」")
            break

    template_score = min(100, len(issues) * 25)
    return {"template_score": template_score, "issues": issues}


# =====================================================================
# 履歴管理
# =====================================================================

def _get_history_path(channel_id: str) -> Path:
    """チャンネルの履歴ファイルパスを返す。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{channel_id}.json"


def _load_history(channel_id: str) -> List[Dict[str, Any]]:
    """過去シナリオ履歴を読み込む。"""
    path = _get_history_path(channel_id)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_to_history(
    channel_id: str,
    text: str,
    text_hash: str,
    title: str = "",
) -> None:
    """現在のシナリオを履歴に追加。"""
    history = _load_history(channel_id)
    history.append({
        "hash": text_hash,
        "title": title,
        "text_preview": text[:200],
        "lines": text.split("\n"),
    })
    # 上限超えたら古いものから削除
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    path = _get_history_path(channel_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"  ⚠️ OriginalityGuard: 履歴保存失敗: {e}")


# =====================================================================
# メインエントリポイント
# =====================================================================

def check_originality(
    short_scenario: List[Dict[str, Any]],
    *,
    title: str = "",
    channel_id: str = "",
) -> Dict[str, Any]:
    """シナリオの独自性をチェックする。

    Args:
        short_scenario: シナリオ行リスト。
        title: 動画タイトル。
        channel_id: チャンネルID。

    Returns:
        {
            "original": bool,            # 独自性OK
            "max_similarity": float,     # 最も類似した過去作との類似度
            "similar_to": str | None,    # 最も類似した過去作のタイトル
            "template_issues": [...],    # テンプレパターン問題
            "blocked": bool,             # ブロック推奨
            "history_count": int,        # 比較した履歴数
        }
    """
    if not short_scenario:
        return {"original": True, "max_similarity": 0.0,
                "similar_to": None, "template_issues": [],
                "blocked": False, "history_count": 0}

    text = _extract_scenario_text(short_scenario)
    if not text:
        return {"original": True, "max_similarity": 0.0,
                "similar_to": None, "template_issues": [],
                "blocked": False, "history_count": 0}

    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

    # チャンネル固有の閾値
    warn_th, block_th = CHANNEL_THRESHOLDS.get(
        channel_id, (WARN_THRESHOLD, BLOCK_THRESHOLD)
    )

    # 履歴読み込み
    history = _load_history(channel_id)

    # 類似度チェック
    max_sim = 0.0
    most_similar_title: Optional[str] = None
    scenario_lines = text.split("\n")

    history_lines_list: List[List[str]] = []
    for entry in history:
        hist_text = "\n".join(entry.get("lines", []))
        hist_lines = entry.get("lines", [])
        history_lines_list.append(hist_lines)

        # テキスト類似度
        sim = _text_similarity(text, hist_text)

        # 構造類似度（補助）
        struct_sim = _structural_similarity(scenario_lines, hist_lines)

        # 総合類似度 (テキスト80% + 構造20%)
        combined = sim * 0.8 + struct_sim * 0.2

        if combined > max_sim:
            max_sim = combined
            most_similar_title = entry.get("title", "不明")

    # テンプレパターンチェック
    template_result = _check_template_patterns(
        scenario_lines, history_lines_list
    )

    # 判定
    blocked = max_sim >= block_th
    warned = max_sim >= warn_th
    original = not warned

    # 履歴に保存
    _save_to_history(channel_id, text, text_hash, title)

    # ログ
    if blocked:
        print(
            f"  🚫 OriginalityGuard [{channel_id}]: "
            f"類似度{max_sim:.0%} — ブロック推奨！"
            f" (類似: {most_similar_title})"
        )
    elif warned:
        print(
            f"  ⚠️ OriginalityGuard [{channel_id}]: "
            f"類似度{max_sim:.0%} — 警告"
            f" (類似: {most_similar_title})"
        )
    else:
        print(
            f"  ✅ OriginalityGuard [{channel_id}]: "
            f"類似度{max_sim:.0%} — OK (履歴{len(history)}本)"
        )

    if template_result["issues"]:
        for issue in template_result["issues"][:2]:
            print(f"     💡 {issue}")

    return {
        "original": original,
        "max_similarity": round(max_sim, 3),
        "similar_to": most_similar_title,
        "template_issues": template_result["issues"],
        "template_score": template_result["template_score"],
        "blocked": blocked,
        "history_count": len(history),
        "warn_threshold": warn_th,
        "block_threshold": block_th,
    }
