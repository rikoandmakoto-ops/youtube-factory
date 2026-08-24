"""Swipe-Stop Pattern Injector — 離脱防止パターンの多点注入（Round 6）。

狙い:
    2026年のYouTubeショートアルゴリズムは、1時間以内のスワイプ離脱率が
    40%を超えると配信を止める。同じ画面が4秒以上続くと離脱が発生する。

    既存の scenario_validator は 20% 地点に1つの中盤フック（転換ワード）が
    あるか検証するだけ。このモジュールは:

    1. 全行のテンションカーブを分析
    2. テンションが2行連続で低い「デッドゾーン」を検出
    3. チャンネル別のリフックパターンを注入（行の先頭に転換語を追加）

    これにより完視聴率70%+を目指す。

既存モジュールとの違い:
    - scenario_validator._check_mid_hook: 20%地点1箇所の転換ワード有無 → pass/fail
    - 本モジュール: 全行を分析し、複数のデッドゾーンにリフックを注入 → 実際に修正する
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# テンション検出パターン（各行に含まれていればテンション+）
TENSION_PATTERNS: List[Tuple[str, int]] = [
    # 疑問・問いかけ (高テンション)
    (r"[？?]", 3),
    (r"なぜ|なんで|どうして|どういう", 3),
    # 驚き・衝撃 (高テンション)
    (r"実は|じつは", 3),
    (r"ヤバ|やばい|とんでも|信じられ|衝撃|まさか", 3),
    # 転換・逆説 (中テンション)
    (r"しかも|ところが|さらに|でも実は|ヤバいのが", 2),
    (r"ところで|だが|けど|意外な|驚くべき", 2),
    (r"逆に|反対に|真逆|一方で", 2),
    # 数字・具体性 (中テンション)
    (r"\d+[%％倍万億兆人匹体件]", 2),
    (r"\d{2,}", 1),
    # 感情・共感 (低-中テンション)
    (r"怖|恐|闇|死|禁|危|草|笑|エロ|下ネタ", 2),
    (r"あなた|君|お前|ワイ|みんな", 1),
    # 比喩・例え (低テンション)
    (r"たとえば|例えば|いわば|つまり", 1),
]

# デッドゾーン閾値: この値以下のテンションが連続するとリフック注入
DEAD_ZONE_THRESHOLD = 1

# チャンネル別のリフック転換語テンプレート
# 行の先頭に挿入して、テンションを上げる
REHOOK_TEMPLATES: Dict[str, List[str]] = {
    "daily-science": [
        "しかもこれ、もっとヤバいことに…",
        "ここからが本題なんだけど、",
        "でも実はこれ、まだ序の口で…",
        "ちょっと待って、ここからが驚きなんだけど、",
    ],
    "scp-lab": [
        "ここからが本当に怖いんだけど…",
        "報告書にはこう書かれている。",
        "しかし、異常はここで終わらなかった。",
        "次の記録が、すべてを変えた。",
    ],
    "2ch-matome": [
        "ここからが草なんだけどさw",
        "でもこっからが本番でさw",
        "待って、まだ続きがあるんだわw",
        "しかもこの>>1、さらにとんでもないこと言い出してw",
    ],
    "company-facts": [
        "しかもこの企業、さらに驚くことに…",
        "ここからが本当のホンネなんだけど、",
        "でも本当にヤバいのはこっちで…",
        "元社員の証言がさらに衝撃的で、",
    ],
    "pokemon-lab": [
        "しかもこのポケモン、さらにヤバい設定があって…",
        "でも図鑑をよく見ると、もっと怖いことが書いてあって…",
        "ここからが闇設定なんだけど、",
        "実はこれ、ゲーム内にヒントが隠されてて…",
    ],
    "yokai-watch": [
        "しかもこの妖怪、さらに恐ろしい伝承があって…",
        "だがここからが本当の怪異なんだ。",
        "地元の古老はこう語っている。",
        "次の目撃報告が、すべてを覆した。",
    ],
    "akashic-librarian": [
        "だが、記録はここで途切れていない。",
        "次のページには、こう記されていた。",
        "しかし、この記録にはまだ続きがある。",
        "ここからが、閲覧注意の領域だ。",
    ],
}

# デフォルトのリフックテンプレート
DEFAULT_REHOOK_TEMPLATES = [
    "しかもここからがヤバいんだけど…",
    "でも実はこれ、まだ序の口で…",
    "ところがここからが本題で、",
]


# =====================================================================
# テンション分析
# =====================================================================

def _score_tension(text: str) -> int:
    """1行のテンションスコアを計算する（0〜最大値は青天井）。"""
    score = 0
    for pattern, weight in TENSION_PATTERNS:
        if re.search(pattern, text):
            score += weight
    return score


def analyze_tension_curve(lines: List[str]) -> List[Dict[str, Any]]:
    """全行のテンションカーブを分析する。

    Returns:
        [{"index": 0, "text": "...", "tension": 5, "is_dead": False}, ...]
    """
    result = []
    for i, line in enumerate(lines):
        tension = _score_tension(line)
        result.append({
            "index": i,
            "text": line[:50],
            "tension": tension,
            "is_dead": tension <= DEAD_ZONE_THRESHOLD,
        })
    return result


def _find_dead_zones(curve: List[Dict[str, Any]]) -> List[int]:
    """2行以上連続するデッドゾーンの開始インデックスを返す。

    冒頭（index 0）と最終行は対象外（フックとCTAなので）。
    """
    dead_starts: List[int] = []
    n = len(curve)

    for i in range(1, n - 1):  # 冒頭と最終行を除く
        if curve[i]["is_dead"] and i > 0 and i < n - 1:
            # 前の行もデッドか、次の行もデッドなら注入対象
            prev_dead = i > 1 and curve[i - 1]["is_dead"]
            next_dead = i < n - 2 and curve[i + 1]["is_dead"]
            if prev_dead or next_dead:
                # 連続デッドゾーンの最初の行だけ記録
                if i not in dead_starts and (i - 1) not in dead_starts:
                    dead_starts.append(i)

    return dead_starts


# =====================================================================
# リフック注入
# =====================================================================

def _pick_rehook(channel_id: str, used: set) -> str:
    """使用済みを避けてリフックテンプレートを選択。"""
    import random
    pool = REHOOK_TEMPLATES.get(channel_id, DEFAULT_REHOOK_TEMPLATES)
    available = [t for t in pool if t not in used]
    if not available:
        available = pool
    choice = random.choice(available)
    used.add(choice)
    return choice


def inject_rehooks(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """デッドゾーンにリフックパターンを注入する。

    Args:
        short_scenario: シナリオ行リスト（各行は {"speaker": ..., "text": ...}）。
        channel_id: チャンネルID。

    Returns:
        {
            "modified": bool,
            "injections": int,      # 注入した箇所数
            "dead_zones": [...],    # 検出されたデッドゾーン
            "tension_curve": [...], # テンションカーブ
        }
    """
    if not short_scenario or len(short_scenario) < 4:
        return {"modified": False, "injections": 0, "reason": "too_short"}

    # テキスト行を抽出
    texts = []
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        texts.append(text)

    # テンションカーブ分析
    curve = analyze_tension_curve(texts)
    dead_zones = _find_dead_zones(curve)

    if not dead_zones:
        print(f"  ✅ SwipeStop [{channel_id}]: デッドゾーンなし — テンション維持OK")
        return {
            "modified": False,
            "injections": 0,
            "dead_zones": [],
            "tension_curve": curve,
        }

    # リフック注入（行の先頭に転換語を追加）
    used_rehooks: set = set()
    injected = 0

    for idx in dead_zones:
        if idx >= len(short_scenario):
            continue

        entry = short_scenario[idx]
        text_key = "text" if "text" in entry else "line"
        original_text = (entry.get(text_key) or "").strip()

        if not original_text:
            continue

        rehook = _pick_rehook(channel_id, used_rehooks)

        # 転換語がすでに行頭にあるなら追加注入しない
        already_has_transition = any(
            original_text.startswith(m) for m in
            ["しかも", "ところが", "さらに", "でも", "だが", "けど", "ところで",
             "待って", "ここから", "次の", "報告書"]
        )
        if already_has_transition:
            continue

        # 行の先頭を転換語に差し替え（元のテキストの最初の句読点まで）
        # ただし行が短い場合は先頭に追加するだけ
        if len(original_text) > 40:
            # 長い行: 先頭部分を転換語に置換
            # 最初の読点か句点で区切る
            cut = -1
            for sep in ["、", "。", "…", "が、", "けど、"]:
                pos = original_text.find(sep)
                if 0 < pos < 20:
                    cut = pos + len(sep)
                    break
            if cut > 0:
                entry[text_key] = rehook + original_text[cut:]
            else:
                entry[text_key] = rehook + original_text
        else:
            # 短い行: 先頭に転換語を追加
            entry[text_key] = rehook + original_text

        injected += 1

    if injected > 0:
        print(
            f"  🔧 SwipeStop [{channel_id}]: {injected}箇所にリフック注入 "
            f"(デッドゾーン {len(dead_zones)}箇所検出)"
        )

    return {
        "modified": injected > 0,
        "injections": injected,
        "dead_zones": dead_zones,
        "tension_curve": curve,
    }
