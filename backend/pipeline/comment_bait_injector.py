"""Comment Bait Injector — 視聴者コメントを誘発する議論ポイント注入（Round 8）。

狙い:
    YouTubeアルゴリズムはコメント数をエンゲージメント指標として重視。
    シナリオ内に「つい意見を言いたくなる」ポイントを戦略的に配置し、
    視聴者の自発的コメントを誘発する。

既存モジュールとの違い:
    - auto_comment (R1): チャンネル自身のコメントを自動投稿
    - comment_question_variations (R3): チャンネルの質問コメントのバリエーション
    - 本モジュール: 動画コンテンツ自体にコメント誘発文を埋め込む
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List

# =====================================================================
# コメントベイトパターン
# =====================================================================

# チャンネル別ベイト（シナリオ内に埋め込む議論誘発文）
BAIT_TEMPLATES: Dict[str, List[str]] = {
    "daily-science": [
        "…これ、賛否分かれると思うんだけど、みんなはどう思う？",
        "ちなみにこの説、科学者の間でもまだ議論中なんだよね",
        "コメント欄で正解率チェックしてみて",
    ],
    "scp-lab": [
        "…この分類、Euclid派とKeter派で意見割れてるんだが",
        "お前らならどう収容する？",
        "これ、一番怖いSCPランキング何位だと思う？",
    ],
    "2ch-matome": [
        "…これ、ワイが悪いんか？コメ欄で判定してくれ",
        "お前らならどうする？正直に答えてみ？ｗ",
        "これ男が悪い派と女が悪い派でコメ欄割れそうｗｗｗ",
    ],
    "company-facts": [
        "…この戦略、天才だと思う？それとも狂気？",
        "この会社に投資する？しない？理由もコメントで教えて",
        "ここまで聞いて、あなたならどの企業を選ぶ？",
    ],
    "pokemon-lab": [
        "…このポケモン、パーティに入れる派？入れない派？",
        "コメント欄でお前らの最強パーティ教えて",
        "この設定知ってた人、正直にコメントしてみて",
    ],
    "yokai-watch": [
        "…この妖怪、実際に見たことある人いる？コメントで教えて",
        "一番遭遇したくない妖怪、コメント欄で決めよう",
        "この怪談、信じる？信じない？",
    ],
    "akashic-librarian": [
        "…この記録、真実だと思う？コメント欄で議論しよう",
        "あなたならこの選択、どちらを選ぶ？",
        "この予言、的中すると思う人はコメントで教えて",
    ],
}

_DEFAULT_BAITS = [
    "…みんなはどう思う？コメントで教えて",
    "これ、意見分かれると思うんだけど",
    "コメント欄で答え合わせしよう",
]

# ベイト挿入に最適な位置 = シナリオの60-80%地点（終盤手前）
_BAIT_POSITION_RATIO = (0.6, 0.8)


# =====================================================================
# 既存ベイトチェック
# =====================================================================

_EXISTING_BAIT_PATTERNS = [
    r"コメント(欄|で)",
    r"(みんな|お前ら|あなた)(は|なら)",
    r"(教えて|聞かせて|書いて)",
    r"どう(思う|する|考える)",
    r"[？?]$",  # 最後が疑問形で終わる行（視聴者への問いかけ）
]


def _has_existing_bait(short_scenario: List[Dict[str, Any]]) -> bool:
    """シナリオ内に既存のコメントベイトがあるか。"""
    for entry in short_scenario:
        text = (entry.get("text") or entry.get("line") or "").strip()
        matches = sum(1 for p in _EXISTING_BAIT_PATTERNS if re.search(p, text))
        if matches >= 2:  # 2パターン以上マッチ = 明確なベイト
            return True
    return False


# =====================================================================
# メインエントリポイント
# =====================================================================

def inject_comment_bait(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """シナリオにコメント誘発文を注入する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。

    Returns:
        {
            "bait_injected": bool,
            "existing_bait": bool,
            "position": int,          # 注入行インデックス（-1 = 未注入）
            "bait_text": str,         # 注入したベイト文
        }
    """
    if len(short_scenario) < 4:
        return {"bait_injected": False, "existing_bait": False,
                "position": -1, "bait_text": ""}

    # 既存ベイトチェック
    has_bait = _has_existing_bait(short_scenario)
    if has_bait:
        print(f"  💬 CommentBait [{channel_id}]: 既存ベイト検出 → スキップ")
        return {"bait_injected": False, "existing_bait": True,
                "position": -1, "bait_text": ""}

    # 注入位置を算出（60-80%地点）
    n = len(short_scenario)
    start = int(n * _BAIT_POSITION_RATIO[0])
    end = int(n * _BAIT_POSITION_RATIO[1])
    pos = random.randint(max(start, 1), min(end, n - 2))

    # ベイト選択
    baits = BAIT_TEMPLATES.get(channel_id, _DEFAULT_BAITS)
    bait = random.choice(baits)

    # 対象行のテキスト末尾にベイトを追記
    entry = short_scenario[pos]
    text_key = "text" if "text" in entry else "line"
    current = entry.get(text_key, "").rstrip()

    # 句点で終わってなければ追加
    if current and not current.endswith(("。", "！", "？", "!", "?", "…")):
        current += "。"

    entry[text_key] = f"{current}{bait}"

    print(f"  💬 CommentBait [{channel_id}]: L{pos}に注入 → {bait[:25]}...")

    return {
        "bait_injected": True,
        "existing_bait": False,
        "position": pos,
        "bait_text": bait,
    }
