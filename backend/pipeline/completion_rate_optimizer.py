"""Completion Rate Optimizer — 完走率最大化のためのペーシング最適化（Round 7）。

狙い:
    2026年のYouTubeショートアルゴリズムは完走率（watch-through rate）を
    最重要シグナルとして使用。閾値は:
    - 30秒以下: 65%以上で拡散ブースト
    - 30-60秒: 50%以上で拡散ブースト
    - 80%以上でバイラル圏突入

    本モジュールは「ペーシング曲線」を分析し、以下を実現する:
    1. 情報密度の均等化 — 密度が偏ると離脱ポイントが生まれる
    2. クレッシェンド構造 — 後半に向けて盛り上がる（前半で出し切らない）
    3. マイクロリビール注入 — 25%/50%/75%地点に小さな新情報を配置
    4. デッドスポット検出 — 2行以上の「つなぎ」を排除

既存モジュールとの違い:
    - swipe_stop_injector: 低テンション行間に rehook フレーズを"追加"
    - scenario_validator: 構造ルール違反の"検出"
    - 本モジュール: ペーシング曲線そのものを"最適化"（行の並び替え＋密度調整）
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# =====================================================================
# 情報密度スコアリング
# =====================================================================

# 高密度ワード — 具体的な情報を含む行は密度が高い
_HIGH_DENSITY_PATTERNS: List[Tuple[str, float]] = [
    (r"\d+[%％万億兆]", 1.5),            # 数値データ
    (r"[A-Z]{2,}", 0.8),                  # 略語・専門用語
    (r"「[^」]{2,}」", 0.6),              # 引用
    (r"実は|じつは|ところが|しかし", 1.0),  # 転換
    (r"つまり|要するに|結論", 1.2),        # 結論
    (r"例えば|たとえば", 0.7),             # 具体例
    (r"[？?！!]", 0.5),                   # 感情的反応
]

# 低密度ワード — つなぎ的な表現
_LOW_DENSITY_PATTERNS: List[Tuple[str, float]] = [
    (r"^(さて|では|そして|それでは|ということで)", -0.8),  # つなぎ語
    (r"^(まず|次に|続いて|最後に)", -0.5),                # 列挙つなぎ
    (r"(だよね|ですよね|よね|だね)", -0.3),               # 相槌
    (r"^(うん|ああ|へー|ほー|なるほど)", -0.6),           # 相槌行
]


def _density_score(line: str) -> float:
    """1行の情報密度を0.0〜3.0でスコアリング。"""
    score = 1.0  # ベースライン

    for pattern, weight in _HIGH_DENSITY_PATTERNS:
        if re.search(pattern, line):
            score += weight

    for pattern, weight in _LOW_DENSITY_PATTERNS:
        if re.search(pattern, line):
            score += weight  # weight is negative

    # 文字数ボーナス（短すぎず長すぎず）
    length = len(line)
    if length < 8:
        score -= 0.3  # 短すぎ
    elif 15 <= length <= 35:
        score += 0.2  # ちょうど良い

    return max(0.0, min(3.0, score))


# =====================================================================
# ペーシング曲線分析
# =====================================================================

def _analyze_pacing(densities: List[float]) -> Dict[str, Any]:
    """密度リストからペーシング品質を分析。"""
    n = len(densities)
    if n < 3:
        return {"quality": "too_short", "score": 50, "issues": []}

    avg = sum(densities) / n
    issues: List[str] = []

    # 1. クレッシェンドチェック — 後半の密度が前半以上であるべき
    mid = n // 2
    first_half_avg = sum(densities[:mid]) / mid if mid > 0 else 0
    second_half_avg = sum(densities[mid:]) / (n - mid) if n > mid else 0

    crescendo_ratio = second_half_avg / first_half_avg if first_half_avg > 0 else 1.0
    if crescendo_ratio < 0.85:
        issues.append("前半に情報が偏り後半が弱い（クレッシェンド不足）")

    # 2. デッドスポット検出 — 連続する低密度行
    dead_spots = 0
    for i in range(n - 1):
        if densities[i] < 0.6 and densities[i + 1] < 0.6:
            dead_spots += 1
    if dead_spots > 0:
        issues.append(f"連続する低密度行が{dead_spots}箇所（離脱ポイント）")

    # 3. マイクロリビールチェック — 25%/50%/75%地点に山があるか
    checkpoints = [n // 4, n // 2, n * 3 // 4]
    weak_checkpoints = []
    for cp in checkpoints:
        if 0 <= cp < n and densities[cp] < avg:
            weak_checkpoints.append(f"{int(cp / n * 100)}%")
    if weak_checkpoints:
        issues.append(f"{'・'.join(weak_checkpoints)}地点の密度が低い")

    # 4. 最終行チェック — 最後の行は必ず高密度であるべき
    if densities[-1] < avg:
        issues.append("最終行の密度が低い（ループ接続弱化）")

    # 総合スコア (0-100)
    score = 70  # ベース
    score += min(15, int(crescendo_ratio * 10))  # クレッシェンドボーナス
    score -= dead_spots * 8                       # デッドスポットペナルティ
    score -= len(weak_checkpoints) * 5            # チェックポイントペナルティ
    score = max(0, min(100, score))

    return {
        "quality": "good" if score >= 65 else "needs_work",
        "score": score,
        "crescendo_ratio": round(crescendo_ratio, 2),
        "dead_spots": dead_spots,
        "avg_density": round(avg, 2),
        "issues": issues,
    }


# =====================================================================
# ペーシング最適化（行の修正）
# =====================================================================

# チャンネル別マイクロリビール挿入テンプレート
MICRO_REVEALS: Dict[str, List[str]] = {
    "daily-science": [
        "…でも、この話にはまだ続きがある",
        "しかもこれ、ほんの序章にすぎない",
        "ここからがさらにヤバい",
    ],
    "scp-lab": [
        "…だが、報告書には続きがあった",
        "しかし、これで終わりではなかった",
        "さらに恐ろしい事実が判明する",
    ],
    "2ch-matome": [
        "…でもここで衝撃の展開",
        "と思ったら話はここからだった",
        "草、まだ終わらんのよ",
    ],
    "company-facts": [
        "…だが、数字の裏にはさらに驚きの事実がある",
        "しかし話はこれだけではない",
        "ここからが本当の闇だ",
    ],
    "pokemon-lab": [
        "…でもこのポケモンの本当の秘密はここから",
        "しかしこれ、さらにヤバい設定がある",
        "ここで衝撃の裏事実が判明",
    ],
    "yokai-watch": [
        "…でも、この妖怪の本当に怖いのはここから",
        "しかしこの伝承にはまだ続きがある",
        "ここからが本当のゾッとする話",
    ],
    "akashic-librarian": [
        "…だが、この記録はまだ完全ではない",
        "しかし書庫ラグナロクは更なる真実を記す",
        "ここから先が本当の核心だ",
    ],
}

# 汎用フォールバック
_DEFAULT_MICRO_REVEALS = [
    "…でも、話はここからが本番",
    "しかしこれだけでは終わらない",
    "ここからがさらに面白い",
]


def _inject_micro_reveals(
    short_scenario: List[Dict[str, Any]],
    densities: List[float],
    channel_id: str,
) -> int:
    """密度の谷にマイクロリビールを注入。in-place で変更。"""
    import random

    n = len(short_scenario)
    if n < 5:
        return 0

    reveals = MICRO_REVEALS.get(channel_id, _DEFAULT_MICRO_REVEALS)
    avg = sum(densities) / n
    injected = 0

    # 25%/50%/75%チェックポイントで密度が低い場合のみ注入
    checkpoints = [n // 4, n // 2, n * 3 // 4]
    for cp in checkpoints:
        if 0 <= cp < n and densities[cp] < avg * 0.8:
            reveal = random.choice(reveals)
            entry = short_scenario[cp]

            # 既存テキストの後ろにリビールを追記
            text_key = "text" if "text" in entry else "line"
            current = entry.get(text_key, "")
            if not current.endswith(("。", "！", "？", "!", "?")):
                current += "。"

            # 行内にリビールを追記（新行追加ではなく密度を上げる）
            entry[text_key] = f"{current}{reveal}"
            injected += 1

    return injected


# =====================================================================
# デッドスポット圧縮
# =====================================================================

def _compress_dead_spots(
    short_scenario: List[Dict[str, Any]],
    densities: List[float],
) -> int:
    """連続する低密度行のうち、相槌・つなぎ行を短縮。"""
    compressed = 0
    n = len(densities)

    for i in range(n - 1):
        if densities[i] < 0.5 and densities[i + 1] < 0.5:
            entry = short_scenario[i]
            text_key = "text" if "text" in entry else "line"
            text = entry.get(text_key, "")

            # 純粋な相槌行は短縮
            if re.match(r"^(うん|ああ|へー|ほー|なるほど|そうだね|そうなんだ)", text):
                # 短縮せず、次の行と結合
                if i + 1 < n:
                    next_entry = short_scenario[i + 1]
                    next_key = "text" if "text" in next_entry else "line"
                    next_text = next_entry.get(next_key, "")
                    # 相槌を短くして次の行に吸収
                    short_form = text[:6] + "…" if len(text) > 6 else text
                    next_entry[next_key] = f"{short_form}{next_text}"
                    entry[text_key] = ""  # 空にする（レンダラーがスキップ）
                    compressed += 1

    return compressed


# =====================================================================
# メインエントリポイント
# =====================================================================

def optimize_completion_rate(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """完走率を最大化するようにペーシングを最適化する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。

    Returns:
        {
            "pacing_score": int,      # 最適化前のペーシングスコア
            "optimized_score": int,   # 最適化後のスコア
            "micro_reveals": int,     # 注入したマイクロリビール数
            "dead_spots_fixed": int,  # 修正したデッドスポット数
            "issues": [...],
        }
    """
    if not short_scenario:
        return {"pacing_score": 0, "optimized_score": 0, "micro_reveals": 0,
                "dead_spots_fixed": 0, "issues": ["empty_scenario"]}

    # テキスト行を抽出して密度計算
    lines: List[str] = []
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        lines.append(text)

    densities = [_density_score(line) for line in lines]

    # ペーシング分析（最適化前）
    before = _analyze_pacing(densities)
    pacing_before = before["score"]

    # 最適化1: マイクロリビール注入
    reveals_injected = _inject_micro_reveals(
        short_scenario, densities, channel_id
    )

    # 最適化2: デッドスポット圧縮
    dead_fixed = _compress_dead_spots(short_scenario, densities)

    # 再計算
    lines_after = []
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        lines_after.append(text)
    densities_after = [_density_score(line) for line in lines_after]
    after = _analyze_pacing(densities_after)
    pacing_after = after["score"]

    improved = pacing_after > pacing_before
    print(
        f"  {'✅' if improved else '➡️'} CompletionOpt [{channel_id}]: "
        f"{pacing_before}→{pacing_after}pt "
        f"(reveals+{reveals_injected}, dead_fix={dead_fixed})"
    )

    if before["issues"]:
        for issue in before["issues"][:2]:
            print(f"     💡 {issue}")

    return {
        "pacing_score": pacing_before,
        "optimized_score": pacing_after,
        "micro_reveals": reveals_injected,
        "dead_spots_fixed": dead_fixed,
        "crescendo_ratio": after.get("crescendo_ratio", 0),
        "issues": before["issues"],
    }
