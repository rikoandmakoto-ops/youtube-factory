"""Contrast Amplifier — 常識vs真実 / before/after コントラスト増幅（Round 8）。

狙い:
    「え、常識と違うの？」「こんなに変わるの？」という
    コントラスト（対比）は、ショートで最もシェアされやすい構造。
    TikTokの「POV: expectation vs reality」形式がバイラルする理由。

    本モジュールは:
    1. シナリオ内の対比構造を検出（常識→実はX / before→after）
    2. 対比が弱い場合、コントラスト強調語を注入
    3. 対比が存在しない場合、チャンネルに合った対比フレームを追加

既存モジュールとの違い:
    - power_word_amplifier: 個別の弱い単語を強い単語に置換
    - emotional_polarity_alternator: 感情極性の連続を分断
    - 本モジュール: 対比構造そのものを検出・強化
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Tuple

# =====================================================================
# 対比構造検出パターン
# =====================================================================

# 対比を示す接続表現
_CONTRAST_CONNECTORS = [
    r"(でも|しかし|ところが|だが|けど|けれど)",
    r"(実は|じつは|実際は|本当は|真実は)",
    r"(と思いきや|かと思ったら|意外にも)",
    r"(逆に|反対に|一方で|その反面)",
    r"(なのに|にもかかわらず|それなのに)",
    r"(嘘|ウソ|間違い|デマ|誤解|勘違い)",
]

# 対比の「前フリ」パターン（常識・期待を提示する行）
_SETUP_PATTERNS = [
    r"(一般的|普通|常識|当たり前|みんな|誰もが)",
    r"(思って|思われて|信じ|考え)(いる|られて|る|た)",
    r"(〜と言われ|有名な|知られて)",
]


def _has_contrast(text: str) -> bool:
    """1行内に対比構造があるかチェック。"""
    for pattern in _CONTRAST_CONNECTORS:
        if re.search(pattern, text):
            return True
    return False


def _is_setup_line(text: str) -> bool:
    """常識・期待を提示する「前フリ」行かチェック。"""
    for pattern in _SETUP_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


# =====================================================================
# コントラスト強調語
# =====================================================================

# 既存の対比を強化するフレーズ
_AMPLIFY_PREFIXES = [
    "驚くべきことに、",
    "信じがたいが、",
    "常識を覆すが、",
    "衝撃の事実として、",
]

# チャンネル別コントラストフレーム（対比構造が無い場合に注入）
CONTRAST_FRAMES: Dict[str, List[Tuple[str, str]]] = {
    # (前フリ, 真実) のペア — 前フリ行の後に真実行を追記
    "daily-science": [
        ("一般的にはこう思われている", "しかし科学的な事実は真逆だった"),
        ("教科書にはこう書いてある", "だが最新の研究で完全に覆された"),
    ],
    "scp-lab": [
        ("当初、安全なオブジェクトだと分類された", "しかし真の特性は想像を絶するものだった"),
        ("財団はこれを無害だと判断した", "だがその判断は致命的な誤りだった"),
    ],
    "2ch-matome": [
        ("ワイ、余裕だと思ってた", "現実は非情だったｗｗｗ"),
        ("みんな勝ち組だと思ってるけど", "裏では地獄だったってオチｗ"),
    ],
    "company-facts": [
        ("表向きは優良企業として知られている", "だが財務の裏側は全く違う姿だった"),
        ("業界では常識とされている戦略だが", "データが示す真実は正反対だった"),
    ],
    "pokemon-lab": [
        ("ゲームではかわいいポケモンとして人気だが", "設定上は恐ろしい存在だった"),
        ("弱いポケモンだと思われているけど", "実は使い方次第で最強クラスになる"),
    ],
    "yokai-watch": [
        ("有名な怪談としてみんな知っている", "だが原典の話はもっと恐ろしい"),
        ("子供向けの妖怪だと思われているが", "本来の伝承はかなり残酷だ"),
    ],
    "akashic-librarian": [
        ("歴史はこう記録している", "だが書庫ラグナロクの記述は全く異なる"),
        ("人類はこう信じてきた", "しかし記録が示す真実は想像を超えていた"),
    ],
}

_DEFAULT_FRAMES = [
    ("一般的にはこう思われている", "しかし真実は全く違っていた"),
]


# =====================================================================
# メインエントリポイント
# =====================================================================

def amplify_contrast(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """対比構造を検出・強化する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。

    Returns:
        {
            "contrasts_found": int,      # 検出した対比数
            "amplified": int,            # 強化した対比数
            "frame_injected": bool,      # 対比フレームを注入したか
            "contrast_score": float,     # 対比スコア (0-1)
        }
    """
    if len(short_scenario) < 4:
        return {"contrasts_found": 0, "amplified": 0,
                "frame_injected": False, "contrast_score": 0.0}

    n = len(short_scenario)

    # ── 対比構造の検出 ──
    contrasts_found = 0
    contrast_positions: List[int] = []

    for i, entry in enumerate(short_scenario):
        text = (entry.get("text") or entry.get("line") or "").strip()
        if _has_contrast(text):
            contrasts_found += 1
            contrast_positions.append(i)

    # ── 既存対比の強化 ──
    amplified = 0
    for pos in contrast_positions[:1]:  # 最初の1つだけ強化（やりすぎ防止）
        entry = short_scenario[pos]
        text_key = "text" if "text" in entry else "line"
        text = entry.get(text_key, "")

        # 対比接続語の前に強調プレフィックスを挿入
        for conn_pattern in _CONTRAST_CONNECTORS:
            match = re.search(conn_pattern, text)
            if match:
                prefix = random.choice(_AMPLIFY_PREFIXES)
                # 接続語が行頭近くにある場合のみ（行中の場合は自然な流れ）
                if match.start() <= 10:
                    text = prefix + text
                    entry[text_key] = text
                    amplified += 1
                break

    # ── 対比フレーム注入（対比が無い場合） ──
    frame_injected = False
    if contrasts_found == 0:
        frames = CONTRAST_FRAMES.get(channel_id, _DEFAULT_FRAMES)
        setup, reveal = random.choice(frames)

        # 前半（20-40%地点）にsetup、直後にrevealを追記
        setup_pos = max(1, int(n * random.uniform(0.2, 0.4)))
        setup_pos = min(setup_pos, n - 2)

        entry = short_scenario[setup_pos]
        text_key = "text" if "text" in entry else "line"
        current = entry.get(text_key, "").rstrip()
        if current and not current.endswith(("。", "！", "？", "…")):
            current += "。"
        entry[text_key] = f"{current}{setup}"

        # 次の行にrevealを追記
        next_pos = setup_pos + 1
        if next_pos < n:
            next_entry = short_scenario[next_pos]
            next_key = "text" if "text" in next_entry else "line"
            next_current = next_entry.get(next_key, "").rstrip()
            if next_current and not next_current.endswith(("。", "！", "？", "…")):
                next_current += "。"
            next_entry[next_key] = f"{reveal}。{next_current}"
            frame_injected = True

    # コントラストスコア (0-1)
    # 理想: シナリオ中に1-2個の対比構造
    score = min(1.0, (contrasts_found + (1 if frame_injected else 0)) / 2.0)

    print(
        f"  🔀 Contrast [{channel_id}]: "
        f"found={contrasts_found}, amp={amplified}, "
        f"frame={'注入' if frame_injected else 'なし'}, "
        f"score={score:.0%}"
    )

    return {
        "contrasts_found": contrasts_found,
        "amplified": amplified,
        "frame_injected": frame_injected,
        "contrast_score": round(score, 2),
    }
