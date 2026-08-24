"""Pattern Interrupt Injector — 話法パターン中断で飽き防止（Round 8）。

狙い:
    人間は「パターン」を検知すると予測可能と判断して注意を緩める。
    同じ話法パターン（平叙文→平叙文→平叙文…）が続くと、
    視聴者は次の展開を予測でき、離脱リスクが上がる。

    本モジュールは:
    1. 文末パターン（平叙/疑問/感嘆/省略）の連続を検出
    2. 単調な連続に「パターン中断」を注入
    3. チャンネルに合った中断スタイルを使用

既存モジュールとの違い:
    - swipe_stop_injector: 低テンション地点にrehookフレーズを"追加"
    - completion_rate_optimizer: 情報密度のバランス調整
    - 本モジュール: 文末パターンの単調さを検出し、文体を変化させる
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Tuple

# =====================================================================
# 文末パターン分類
# =====================================================================

def _classify_ending(text: str) -> str:
    """文末パターンを分類。"""
    text = text.rstrip()
    if not text:
        return "empty"

    if text.endswith(("？", "?")):
        return "question"
    elif text.endswith(("！", "!")):
        return "exclaim"
    elif text.endswith("…"):
        return "ellipsis"
    elif text.endswith(("。", "だ", "です", "ます", "た", "った", "んだ")):
        return "statement"
    elif re.search(r"[ｗw]{2,}$", text):
        return "laugh"
    else:
        return "statement"


# =====================================================================
# パターン中断テンプレート
# =====================================================================

# statement → 他パターンへの変換
_INTERRUPTS: Dict[str, Dict[str, List[Tuple[str, str]]]] = {
    # (追記フレーズ, 変換後パターン)
    "default": {
        "to_question": [
            ("…って、これ冷静に考えるとおかしくない？", "question"),
            ("…え、待って。本当にそうなの？", "question"),
            ("…なぜだと思う？", "question"),
        ],
        "to_exclaim": [
            ("…これ、ヤバすぎる！", "exclaim"),
            ("…衝撃の事実！", "exclaim"),
            ("…マジか！", "exclaim"),
        ],
        "to_ellipsis": [
            ("…と思うじゃん？", "ellipsis"),
            ("…ところが…", "ellipsis"),
            ("…実はこれ…", "ellipsis"),
        ],
    },
    "2ch-matome": {
        "to_question": [
            ("…これ草じゃね？ｗ", "question"),
            ("…いやおかしくね？ｗｗ", "question"),
            ("…お前らならどうするよ？", "question"),
        ],
        "to_exclaim": [
            ("…ファーーーーｗｗｗ！", "exclaim"),
            ("…これはアカンｗｗｗ！", "exclaim"),
            ("…草ァ！ｗｗｗ", "exclaim"),
        ],
        "to_ellipsis": [
            ("…と思うやん？ｗ", "ellipsis"),
            ("…からの…ｗ", "ellipsis"),
            ("…まさかの…ｗｗ", "ellipsis"),
        ],
    },
    # 司書は煽らない。中断は「声量」ではなく『間』と静かな断定で作る
    # （既定テンプレの「…マジか！」「…ヤバすぎる！」は voice_style.forbidden 違反）。
    "akashic-librarian": {
        "to_question": [
            ("…この頁だけ、なぜ残された？", "question"),
            ("…あなたは、どう読む？", "question"),
        ],
        "to_exclaim": [
            ("…記録は、そこで途切れている。", "statement"),
            ("…理由は、書かれていない。", "statement"),
        ],
        "to_ellipsis": [
            ("…だが、続きがある…", "ellipsis"),
            ("…そして、誰も戻らなかった…", "ellipsis"),
        ],
    },
    "scp-lab": {
        "to_question": [
            ("…これ、本当にEuclid分類で合っているのか？", "question"),
            ("…なぜ財団はこれを隠したのか？", "question"),
        ],
        "to_exclaim": [
            ("…これは[データ削除]レベルだ！", "exclaim"),
            ("…Keterに再分類すべきだ！", "exclaim"),
        ],
        "to_ellipsis": [
            ("…報告書はここで途切れている…", "ellipsis"),
            ("…続きは████…", "ellipsis"),
        ],
    },
}

# 許容する同一パターンの最大連続数
_MAX_SAME_ENDING = 3


# =====================================================================
# メインエントリポイント
# =====================================================================

def inject_pattern_interrupts(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
    max_interrupts: int = 2,
) -> Dict[str, Any]:
    """話法パターンの単調な連続を検出し、中断を注入する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。
        max_interrupts: 最大注入数（デフォルト2）。

    Returns:
        {
            "endings": List[str],          # 各行の文末パターン
            "monotone_runs": int,          # 検出した単調区間数
            "interrupts_injected": int,    # 注入した中断数
            "variety_score": float,        # 文末パターン多様性 (0-1)
        }
    """
    if len(short_scenario) < 4:
        return {"endings": [], "monotone_runs": 0,
                "interrupts_injected": 0, "variety_score": 0.0}

    # 全行の文末パターンを分類
    endings: List[str] = []
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        endings.append(_classify_ending(text))

    # 単調連続を検出
    monotone_runs = 0
    interrupts_done = 0
    interrupt_templates = _INTERRUPTS.get(channel_id, _INTERRUPTS["default"])

    i = 0
    while i < len(endings) - _MAX_SAME_ENDING and interrupts_done < max_interrupts:
        window = endings[i:i + _MAX_SAME_ENDING]

        if len(set(window)) == 1 and window[0] == "statement":
            monotone_runs += 1

            # 連続の中間点に中断を注入
            break_pos = i + _MAX_SAME_ENDING // 2
            if break_pos < len(short_scenario):
                # 現在のパターンと異なる中断タイプをランダム選択
                interrupt_types = [k for k in interrupt_templates.keys()]
                if interrupt_types:
                    chosen_type = random.choice(interrupt_types)
                    options = interrupt_templates[chosen_type]
                    if options:
                        phrase, _ = random.choice(options)

                        entry = short_scenario[break_pos]
                        text_key = "text" if "text" in entry else "line"
                        current = entry.get(text_key, "").rstrip()

                        # 文末の句点を除去してから中断フレーズを追記
                        if current.endswith("。"):
                            current = current[:-1]

                        entry[text_key] = f"{current}{phrase}"
                        interrupts_done += 1
                        # 分類を更新
                        endings[break_pos] = _classify_ending(entry[text_key])

            i += _MAX_SAME_ENDING
        else:
            i += 1

    # 文末多様性スコア
    non_empty = [e for e in endings if e != "empty"]
    unique_types = len(set(non_empty))
    variety = unique_types / 5.0 if non_empty else 0.0  # 5種類が最大

    print(
        f"  ⚡ PatternInt [{channel_id}]: "
        f"runs={monotone_runs}, injected={interrupts_done}, "
        f"variety={variety:.0%}"
    )

    return {
        "endings": endings,
        "monotone_runs": monotone_runs,
        "interrupts_injected": interrupts_done,
        "variety_score": round(min(1.0, variety), 2),
    }
