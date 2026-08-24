"""シナリオ構造バリデータ — 生成後のショートシナリオが構造ルールを守っているか検証する。

狙い:
    プロンプトでフック・CTA・ループ構造を要求しても、LLMが守らないケースが
    20〜30%ある（特にCTAの欠落と冒頭フックの弱さ）。生成後にルールベースで
    検証し、不合格なら再生成トリガーを出す。

検証項目:
    1. 冒頭フック: 1行目が疑問形/驚き形で始まっているか
    2. 中盤フック: 全体の20%付近に転換ワードがあるか
    3. CTA: 最終行にチャンネル登録の誘導が含まれるか
    4. 禁止語: チャンネルのforbiddenリストに触れていないか
    5. 行数: short_formatのline_countと一致するか
    6. ループ構造: 最終行の内容が冒頭に接続する構造か（オプション）
    7. 行あたり文字数: 各行が適正文字数範囲に収まっているか
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# --- Hook detection ---
# 冒頭フックとして有効な型のパターン
HOOK_PATTERNS: List[str] = [
    r"知って(た|ました|る)",      # これ知ってた？型
    r"実は",                       # 実は〇〇型
    r"なんで.*だけ",               # なんで〇〇だけ型
    r"した結果",                   # 〇〇した結果型
    r"なぜ",                       # なぜ型
    r"？$",                        # 疑問形
    r"ヤバ",                       # ヤバい系
    r"(ワイ|お前ら)",             # 2ch系
    r"この(SCP|報告書|妖怪|ポケモン|会社)",  # 対象指定型
    r"という(論文|研究|報告)",     # 架空論文: 「〜という論文があります」型
    r"(論文|研究|報告)が(ある|あり)",  # 架空論文: 結論を断定してから出典を示す型
    r"証明され",                   # 架空論文: 「〇〇が証明された」型
]

# 中盤フック（転換）のマーカー
MID_HOOK_MARKERS: List[str] = [
    "しかも", "ところが", "さらに", "でも実は", "ヤバいのが",
    "ところで", "だが", "けど", "意外なことに", "驚くべきことに",
]

# CTA検出パターン
CTA_PATTERNS: List[str] = [
    r"チャンネル登録",
    r"登録.*よろしく",
    r"登録.*待",
    r"フォロー",
    r"チャンネル.*見逃さない",
]

# デフォルトの行数
DEFAULT_LINE_COUNT = 8

# 1行あたりの文字数範囲（デフォルト）
DEFAULT_LINE_MIN_CHARS = 10
DEFAULT_LINE_MAX_CHARS = 60


# ---------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------

def _extract_content_words(text: str) -> set:
    """テキストからコンテンツワード（2文字以上の漢字/カタカナ塊）を抽出。"""
    return set(re.findall(r"[一-鿿゠-ヿ]{2,}", text))


# ---------------------------------------------------------------------
# 個別チェック関数
# ---------------------------------------------------------------------

def _check_opening_hook(lines: List[str]) -> Tuple[int, List[str], List[str]]:
    """冒頭フックの検証。

    Returns:
        (score_delta, issues, warnings)
    """
    if not lines:
        return -20, ["冒頭フック: シナリオが空"], []

    first_line = lines[0]
    for pattern in HOOK_PATTERNS:
        if re.search(pattern, first_line):
            return +20, [], []

    return -20, [f"冒頭フック: 1行目がフック型に該当しない（{first_line[:30]}…）"], []


def _check_mid_hook(lines: List[str]) -> Tuple[int, List[str], List[str]]:
    """中盤フック（転換ワード）の検証。

    全体の20%付近（8行なら行1〜2あたり）に転換ワードがあるか。
    """
    if len(lines) < 3:
        return 0, [], ["中盤フック: 行数が少なすぎて検証スキップ"]

    # 20%付近のインデックス範囲を計算（前後1行の余裕を持たせる）
    target_idx = max(1, int(len(lines) * 0.2))
    check_start = max(1, target_idx - 1)
    check_end = min(len(lines) - 1, target_idx + 1)

    for i in range(check_start, check_end + 1):
        for marker in MID_HOOK_MARKERS:
            if marker in lines[i]:
                return +15, [], []

    return -10, ["中盤フック: 転換ワードが見つからない"], []


def _check_cta(lines: List[str]) -> Tuple[int, List[str], List[str]]:
    """CTA（チャンネル登録誘導）の検証。最終行にCTAパターンがあるか。"""
    if not lines:
        return -25, ["CTA: シナリオが空"], []

    last_line = lines[-1]
    for pattern in CTA_PATTERNS:
        if re.search(pattern, last_line):
            return +20, [], []

    return -25, ["CTA: 最終行にチャンネル登録の誘導がない"], []


def _check_forbidden_words(
    lines: List[str],
    channel_dict: Optional[Dict[str, Any]],
) -> Tuple[int, List[str], List[str]]:
    """禁止語の検証。channel_dict.voice_style.forbidden に含まれる語が使われていないか。"""
    if not channel_dict:
        return 0, [], []

    voice_style = channel_dict.get("voice_style") or {}
    forbidden = voice_style.get("forbidden")
    if not isinstance(forbidden, list) or not forbidden:
        return 0, [], []

    score_delta = 0
    issues: List[str] = []
    full_text = "\n".join(lines)

    for word in forbidden:
        word_str = str(word).strip()
        if not word_str:
            continue
        if word_str in full_text:
            score_delta -= 30
            issues.append(f"禁止語: 「{word_str}」が使用されている")

    return score_delta, issues, []


def _check_line_count(
    lines: List[str],
    channel_dict: Optional[Dict[str, Any]],
) -> Tuple[int, List[str], List[str]]:
    """行数の検証。short_format.line_count と一致するか。"""
    expected = DEFAULT_LINE_COUNT
    if channel_dict:
        short_format = channel_dict.get("short_format") or {}
        raw_count = short_format.get("line_count")
        if isinstance(raw_count, int) and raw_count > 0:
            expected = raw_count

    actual = len(lines)
    if actual == expected:
        return +10, [], []

    diff = abs(actual - expected)
    warnings: List[str] = []
    issues: List[str] = []

    msg = f"行数: {actual}行（期待値 {expected}行、差分 {diff}行）"
    if diff <= 1:
        warnings.append(msg)
        return -5, [], warnings
    else:
        issues.append(msg)
        return -15, issues, []


def _check_loop_structure(lines: List[str]) -> Tuple[int, List[str], List[str]]:
    """ループ構造の検証（オプション・ボーナス）。

    最終コンテンツ行（CTA の手前）と1行目でキーワードが重複していれば、
    ループ再生を促す構造と判定する。ペナルティなし、検出時のみ加点。
    """
    if len(lines) < 3:
        return 0, [], []

    first_line = lines[0]

    # CTA行を除いた最終コンテンツ行を探す
    last_content_idx = len(lines) - 1
    last_line = lines[last_content_idx]
    for pattern in CTA_PATTERNS:
        if re.search(pattern, last_line):
            last_content_idx = len(lines) - 2
            break

    if last_content_idx < 1:
        return 0, [], []

    last_content = lines[last_content_idx]
    first_words = _extract_content_words(first_line)
    last_words = _extract_content_words(last_content)
    overlap = first_words & last_words

    if overlap:
        return +10, [], []

    return 0, [], []


def _check_line_lengths(
    lines: List[str],
    channel_dict: Optional[Dict[str, Any]],
) -> Tuple[int, List[str], List[str]]:
    """各行の文字数が適正範囲に収まっているか検証。"""
    min_chars = DEFAULT_LINE_MIN_CHARS
    max_chars = DEFAULT_LINE_MAX_CHARS
    if channel_dict:
        short_format = channel_dict.get("short_format") or {}
        raw_min = short_format.get("line_min_chars")
        raw_max = short_format.get("line_max_chars")
        if isinstance(raw_min, int) and raw_min > 0:
            min_chars = raw_min
        if isinstance(raw_max, int) and raw_max > 0:
            max_chars = raw_max

    score_delta = 0
    warnings: List[str] = []

    for i, line in enumerate(lines):
        length = len(line)
        if length < min_chars:
            score_delta -= 5
            warnings.append(
                f"行{i + 1}: {length}字 — 下限{min_chars}字を下回る"
            )
        elif length > max_chars:
            score_delta -= 5
            warnings.append(
                f"行{i + 1}: {length}字 — 上限{max_chars}字を超過"
            )

    return score_delta, [], warnings


# ---------------------------------------------------------------------
# メインバリデーション
# ---------------------------------------------------------------------

def validate_scenario(
    lines: List[str],
    *,
    channel_id: str = "",
    channel_dict: Optional[Dict[str, Any]] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """生成済みシナリオの構造を検証する。

    Args:
        lines: シナリオの各行テキスト。
        channel_id: チャンネルID（ログ用）。
        channel_dict: チャンネル設定辞書。voice_style.forbidden や
                      short_format.line_count などを参照する。
        strict: True の場合、guard() が不合格時に例外を投げる（ここでは使わない）。

    Returns:
        {
            "passed": bool,
            "score": int,          # 0-100
            "issues": [...],       # 不合格項目のリスト
            "warnings": [...],     # 注意項目のリスト
            "details": {...},      # 各チェックの詳細
        }
    """
    if not lines:
        return {
            "passed": False,
            "score": 0,
            "issues": ["シナリオが空"],
            "warnings": [],
            "details": {},
        }

    score = 50  # ベーススコア
    all_issues: List[str] = []
    all_warnings: List[str] = []
    details: Dict[str, Any] = {}

    # 各チェックを実行
    checks = [
        ("opening_hook", _check_opening_hook(lines)),
        ("mid_hook", _check_mid_hook(lines)),
        ("cta", _check_cta(lines)),
        ("forbidden_words", _check_forbidden_words(lines, channel_dict)),
        ("line_count", _check_line_count(lines, channel_dict)),
        ("loop_structure", _check_loop_structure(lines)),
        ("line_lengths", _check_line_lengths(lines, channel_dict)),
    ]

    for name, (delta, issues, warnings) in checks:
        score += delta
        all_issues.extend(issues)
        all_warnings.extend(warnings)
        details[name] = {
            "score_delta": delta,
            "issues": issues,
            "warnings": warnings,
        }

    score = max(0, min(100, score))
    passed = score >= 60

    return {
        "passed": passed,
        "score": score,
        "issues": all_issues,
        "warnings": all_warnings,
        "details": details,
    }


# ---------------------------------------------------------------------
# パイプライン統合用ガード
# ---------------------------------------------------------------------

def guard(
    lines: List[str],
    *,
    channel_id: str = "",
    channel_dict: Optional[Dict[str, Any]] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """パイプライン統合用エントリポイント。

    strict=True の場合、不合格なら ValueError を送出する（再生成トリガー用）。
    strict=False（デフォルト）の場合、警告をログに出すだけで通す。
    """
    result = validate_scenario(
        lines,
        channel_id=channel_id,
        channel_dict=channel_dict,
        strict=strict,
    )

    label = channel_id or "unknown"

    if not result["passed"]:
        msg = (
            f"Scenario validation failed (score={result['score']}): "
            f"{', '.join(result['issues'])}"
        )
        if strict:
            raise ValueError(msg)
        print(f"  ⚠️ ScenarioValidator [{label}]: {msg}")
    else:
        print(
            f"  ✅ ScenarioValidator [{label}]: "
            f"score={result['score']} — PASSED"
        )

    if result["warnings"]:
        for w in result["warnings"]:
            print(f"     💡 {w}")

    return result
