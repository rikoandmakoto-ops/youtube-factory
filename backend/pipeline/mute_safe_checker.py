"""Mute-Safe Checker — ミュート視聴対応チェッカー（Round 6）。

狙い:
    2026年の調査で「ショート視聴者の70%がミュート（音なし）で視聴」
    していることが判明。字幕（テロップ）だけで内容が伝わらないと
    冒頭2秒で離脱する。

    このモジュールは:
    1. 音声依存フレーズ（「この音聞いて」「BGMが」等）を検出
    2. 視覚情報なしでは意味が通じない表現を検出
    3. 指示語（「これ」「あれ」）の過剰使用を検出（テロップだけだと何を指すか不明）

    検出結果は警告ログとして出力し、将来的にはスコアに組み込む。

既存モジュールとの違い:
    - scenario_validator: 構造ルール → 音声/視覚依存は検出しない
    - 本モジュール: テキストのみで伝わるか → ミュート視聴者対策
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# =====================================================================
# 音声依存パターン
# =====================================================================

AUDIO_DEPENDENT_PATTERNS: List[Tuple[str, str]] = [
    (r"この音", "「この音」はミュートでは聞こえない"),
    (r"聞いて[みてくれ]", "「聞いて」はミュートでは無意味"),
    (r"BGM[がをは]", "BGMへの言及はミュートでは伝わらない"),
    (r"声[がをは]", "「声が」はミュートでは確認できない"),
    (r"叫[ぶび声]", "叫びの描写は視覚的な代替が必要"),
    (r"音[がをは]鳴", "音の描写はミュートでは伝わらない"),
    (r"静か[にだ]", "「静かに」はミュートでは区別できない"),
    (r"耳[をに]", "耳への言及はミュートでは無意味"),
    (r"歌[っうい]", "歌の描写はミュートでは伝わらない"),
    (r"(SE|効果音)", "効果音への言及はミュートでは伝わらない"),
]

# =====================================================================
# 視覚依存パターン（テロップだけでは不十分）
# =====================================================================

VISUAL_DEPENDENT_PATTERNS: List[Tuple[str, str]] = [
    (r"この画像[をが見]", "「この画像」はテロップだけでは指示が不明"),
    (r"見て[みてくれ]", "「見て」だけでは何を見るか不明（テロップでは）"),
    (r"画面[のを上下左右]", "「画面の〜」はテロップ視聴者には分かりにくい"),
    (r"ここ[にがを]注目", "「ここ」の指示はテロップだけでは不明"),
    (r"(赤|青|緑|黄|白|黒)い(部分|ところ|箇所)", "色の指示はモノクロテロップでは伝わりにくい"),
]

# =====================================================================
# 指示語の過剰使用
# =====================================================================

DEMONSTRATIVE_PATTERNS = [
    r"^これ[はがを]",    # 行頭の「これは」
    r"^あれ[はがを]",
    r"^それ[はがを]",
    r"^この(?!SCP|ポケモン|妖怪|企業|スレ|会社|動画|チャンネル)",  # 固有名詞への指示語は除外
]

# 行頭の指示語が全体の何%を超えたら警告
DEMONSTRATIVE_THRESHOLD = 0.3


# =====================================================================
# チェック関数
# =====================================================================

def _check_audio_dependency(lines: List[str]) -> List[Dict[str, Any]]:
    """音声依存フレーズを検出。"""
    issues = []
    for i, line in enumerate(lines):
        for pattern, reason in AUDIO_DEPENDENT_PATTERNS:
            if re.search(pattern, line):
                issues.append({
                    "type": "audio_dependent",
                    "line": i + 1,
                    "text": line[:40],
                    "pattern": pattern,
                    "reason": reason,
                })
    return issues


def _check_visual_dependency(lines: List[str]) -> List[Dict[str, Any]]:
    """視覚依存フレーズを検出。"""
    issues = []
    for i, line in enumerate(lines):
        for pattern, reason in VISUAL_DEPENDENT_PATTERNS:
            if re.search(pattern, line):
                issues.append({
                    "type": "visual_dependent",
                    "line": i + 1,
                    "text": line[:40],
                    "pattern": pattern,
                    "reason": reason,
                })
    return issues


def _check_demonstratives(lines: List[str]) -> List[Dict[str, Any]]:
    """指示語の過剰使用を検出。"""
    if not lines:
        return []

    demonstrative_count = 0
    for line in lines:
        for pattern in DEMONSTRATIVE_PATTERNS:
            if re.search(pattern, line):
                demonstrative_count += 1
                break

    ratio = demonstrative_count / len(lines)
    if ratio > DEMONSTRATIVE_THRESHOLD:
        return [{
            "type": "demonstrative_overuse",
            "line": 0,
            "text": f"{demonstrative_count}/{len(lines)}行が指示語で開始",
            "reason": (
                f"指示語の使用率が{ratio:.0%}（閾値{DEMONSTRATIVE_THRESHOLD:.0%}）。"
                "ミュート視聴者はテロップしか見ないため、「これ」「あれ」が何を指すか不明になる"
            ),
        }]
    return []


def _check_caption_readability(lines: List[str]) -> List[Dict[str, Any]]:
    """テロップとしての読みやすさをチェック。"""
    issues = []
    for i, line in enumerate(lines):
        # 1行が長すぎる（テロップとして読めない）
        if len(line) > 50:
            issues.append({
                "type": "caption_too_long",
                "line": i + 1,
                "text": line[:40],
                "reason": f"1行{len(line)}字はテロップとして長すぎる（推奨: 40字以内）",
            })

        # 括弧や記号が多すぎる（テロップで読みにくい）
        symbol_count = len(re.findall(r"[（）()「」『』【】{}《》〈〉]", line))
        if symbol_count > 4:
            issues.append({
                "type": "too_many_symbols",
                "line": i + 1,
                "text": line[:40],
                "reason": f"括弧・記号が{symbol_count}個 — テロップで視認性が低下",
            })

    return issues


# =====================================================================
# メインエントリポイント
# =====================================================================

def check_mute_safe(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """ミュート視聴安全性をチェックする。

    Args:
        short_scenario: シナリオ行リスト。
        channel_id: チャンネルID。

    Returns:
        {
            "safe": bool,          # 全チェックパス
            "score": int,          # 0-100 (100 = 完全にミュート安全)
            "issues": [...],       # 検出された問題
            "warnings": int,       # 警告数
        }
    """
    if not short_scenario:
        return {"safe": True, "score": 100, "issues": [], "warnings": 0}

    # テキスト行を抽出
    lines = []
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        if text:
            lines.append(text)

    if not lines:
        return {"safe": True, "score": 100, "issues": [], "warnings": 0}

    # 各チェック実行
    all_issues: List[Dict[str, Any]] = []
    all_issues.extend(_check_audio_dependency(lines))
    all_issues.extend(_check_visual_dependency(lines))
    all_issues.extend(_check_demonstratives(lines))
    all_issues.extend(_check_caption_readability(lines))

    # スコア計算
    penalty_map = {
        "audio_dependent": 15,
        "visual_dependent": 10,
        "demonstrative_overuse": 10,
        "caption_too_long": 5,
        "too_many_symbols": 3,
    }
    total_penalty = sum(penalty_map.get(i["type"], 5) for i in all_issues)
    score = max(0, 100 - total_penalty)
    safe = score >= 70

    if all_issues:
        n = len(all_issues)
        print(
            f"  {'⚠️' if not safe else '💡'} MuteSafe [{channel_id}]: "
            f"score={score} — {n}件の問題検出"
        )
        for issue in all_issues[:3]:
            line_info = f"行{issue['line']}" if issue["line"] > 0 else ""
            print(f"     {line_info}: {issue['reason']}")
    else:
        print(f"  ✅ MuteSafe [{channel_id}]: score={score} — ミュート安全")

    return {
        "safe": safe,
        "score": score,
        "issues": all_issues,
        "warnings": len(all_issues),
    }
