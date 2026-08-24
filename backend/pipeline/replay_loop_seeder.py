"""Replay Loop Seeder — リプレイループ誘導のためのシームレス接続（Round 7）。

狙い:
    2026年のアルゴリズムでは「リプレイ率」が完走率と並ぶ独立シグナル。
    30秒ショートが2回視聴されると、60秒ショートの1回視聴を上回る。

    本モジュールは:
    1. 最終行を「終わった感」のない形に変換
    2. 最終行→冒頭行のシームレスな感情/トピック接続を強化
    3. 「え、もう1回？」となるループトリガーを最終行に仕込む

既存モジュールとの違い:
    - scenario_validator._check_loop_structure: 冒頭/末尾の文字重複を
      "パッシブに検出"するだけ。スコアに加算するのみで変更しない
    - 本モジュール: 最終行を"アクティブに書き換え"てシームレスループを実現
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional

# =====================================================================
# 終わった感パターン（除去対象）
# =====================================================================

_ENDING_FEEL_PATTERNS = [
    (r"以上[、。！]?$", ""),                          # 「以上。」
    (r"でした[。！]?$", "なんだけど…"),                 # 「〜でした。」→余韻
    (r"ということ(です|だ)[。！]?$", "って話"),         # 結論感→カジュアル化
    (r"(終わり|おわり|おしまい)[。！]?$", ""),           # 明示的な終了
    (r"(いかがでしたか|どうでしたか)[？?。]?$", ""),     # YouTube定型
    (r"ご視聴ありがとう[^。]*$", ""),                    # 視聴感謝
    (r"チャンネル登録[^。]*$", ""),                      # 登録促進（CTAで対応済）
    (r"それでは[、。！]?$", ""),                         # 締め
    (r"またね[。！]?$", ""),                             # 別れ
]

# =====================================================================
# ループトリガー（最終行の末尾に追加）
# =====================================================================

LOOP_TRIGGERS: Dict[str, List[str]] = {
    "daily-science": [
        "…って、冒頭の話に戻るんだけど",
        "…実はこれ、最初に言ったことと繋がってる",
        "…あれ？これってさっきの…",
    ],
    "scp-lab": [
        "…待て、最初の報告と矛盾してないか？",
        "…まさか、冒頭の[編集済]がこれを意味していたのか",
        "…この収容手順、最初から見直す必要がある",
    ],
    "2ch-matome": [
        "…あれ、最初のレスもう一回読んでみ？",
        "…ちょ待て、>>1に戻ってみろ",
        "…草、最初から伏線だったのかよ",
    ],
    "company-facts": [
        "…この数字、冒頭のデータと照合すると…",
        "…つまり最初に言った通り、全部繋がっている",
        "…これが最初の疑問の答えだ",
    ],
    "pokemon-lab": [
        "…あれ、最初に言ったやつもう一回見て",
        "…ここでさっきの伏線回収なんだけど",
        "…つまり最初のアレ、全部ここに繋がってた",
    ],
    "yokai-watch": [
        "…そういえば、最初の話を思い出してほしい",
        "…冒頭の怪異、実はここに繋がっていた",
        "…これが最初の違和感の正体だった",
    ],
    "akashic-librarian": [
        "…そしてこの記録は、冒頭に戻る",
        "…最初の一節が、ここで意味を持つ",
        "…記録は繰り返される",
    ],
}

_DEFAULT_TRIGGERS = [
    "…あれ、最初のあの話…",
    "…ちょっと待って、最初に戻ってみて",
    "…つまりこれ、最初から繋がってた？",
]


# =====================================================================
# キーワード接続チェック
# =====================================================================

def _extract_topic_keywords(text: str) -> set:
    """テキストからトピックキーワードを抽出。"""
    # カタカナ語・漢字複合語を抽出
    katakana = set(re.findall(r"[ァ-ヶー]{2,}", text))
    kanji = set(re.findall(r"[一-鿿]{2,}", text))
    # 数字付きキーワード (SCP-173 等)
    coded = set(re.findall(r"[A-Za-z]+-\d+", text))
    return katakana | kanji | coded


def _keyword_overlap(first_line: str, last_line: str) -> float:
    """冒頭と末尾のキーワード重複率。"""
    first_kw = _extract_topic_keywords(first_line)
    last_kw = _extract_topic_keywords(last_line)
    if not first_kw or not last_kw:
        return 0.0
    overlap = first_kw & last_kw
    return len(overlap) / max(len(first_kw), 1)


# =====================================================================
# ループシーディング
# =====================================================================

def _remove_ending_feel(text: str) -> str:
    """終わった感のある末尾表現を除去・変換。"""
    for pattern, replacement in _ENDING_FEEL_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text.strip()


def _add_loop_trigger(
    text: str,
    channel_id: str,
    first_line: str,
) -> str:
    """最終行にループトリガーを追加。"""
    triggers = LOOP_TRIGGERS.get(channel_id, _DEFAULT_TRIGGERS)

    # 冒頭のキーワードを参照するトリガーを優先
    first_kw = _extract_topic_keywords(first_line)
    if first_kw:
        # キーワードを含むカスタムトリガーを試行
        kw = random.choice(list(first_kw))
        custom_triggers = [
            f"…あれ、{kw}って最初に言ってた…",
            f"…待って、{kw}に戻って",
        ]
        # 50%の確率でカスタム vs チャンネル定型
        if random.random() < 0.5 and len(kw) <= 8:
            trigger = random.choice(custom_triggers)
        else:
            trigger = random.choice(triggers)
    else:
        trigger = random.choice(triggers)

    # 末尾に接続
    if text and not text.endswith(("…", "。", "！", "？")):
        text += "。"

    return f"{text}{trigger}"


def _enhance_first_line_callback(
    short_scenario: List[Dict[str, Any]],
) -> bool:
    """冒頭行が最終行からのループ受け入れに適しているか確認し、
    不十分なら冒頭を微調整。"""

    if len(short_scenario) < 2:
        return False

    first = short_scenario[0]
    text_key = "text" if "text" in first else "line"
    first_text = first.get(text_key, "")

    # 冒頭が疑問形や驚きで始まっていればOK（ループ受けに最適）
    if re.match(r"^(え[？?！!]|なんと|衝撃|ヤバ|マジ|実は|知って)", first_text):
        return True

    # 冒頭が淡々とした説明文の場合、ループ接続が弱い
    # → 軽い驚き表現を冒頭に追加
    if re.match(r"^(今日は|本日は|こんにちは|皆さん)", first_text):
        # 挨拶系はループ接続に不向き — ただしフック最適化で既に処理されている
        # 可能性があるので、ここでは触らない
        return False

    return True


# =====================================================================
# メインエントリポイント
# =====================================================================

def seed_replay_loop(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
) -> Dict[str, Any]:
    """リプレイループを誘導するシームレスな接続を構築する。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。

    Returns:
        {
            "loop_seeded": bool,
            "ending_feel_removed": bool,
            "trigger_added": str,
            "keyword_overlap_before": float,
            "keyword_overlap_after": float,
        }
    """
    if len(short_scenario) < 3:
        return {"loop_seeded": False, "reason": "too_short"}

    # テキストキーを特定
    first_entry = short_scenario[0]
    last_entry = short_scenario[-1]
    first_key = "text" if "text" in first_entry else "line"
    last_key = "text" if "text" in last_entry else "line"

    first_text = first_entry.get(first_key, "")
    last_text = last_entry.get(last_key, "")

    if not first_text or not last_text:
        return {"loop_seeded": False, "reason": "empty_lines"}

    # 最適化前のキーワード重複率
    overlap_before = _keyword_overlap(first_text, last_text)

    # Step 1: 終わった感の除去
    cleaned_last = _remove_ending_feel(last_text)
    ending_removed = cleaned_last != last_text

    # Step 2: ループトリガー追加
    if cleaned_last:
        triggered_last = _add_loop_trigger(cleaned_last, channel_id, first_text)
    else:
        # 全部除去されてしまった場合（稀）、トリガーだけ
        triggers = LOOP_TRIGGERS.get(channel_id, _DEFAULT_TRIGGERS)
        triggered_last = random.choice(triggers)

    # 適用
    last_entry[last_key] = triggered_last

    # Step 3: 冒頭のループ受け入れ確認
    _enhance_first_line_callback(short_scenario)

    # 最適化後の重複率
    overlap_after = _keyword_overlap(first_text, triggered_last)

    print(
        f"  🔄 ReplayLoop [{channel_id}]: "
        f"keyword_overlap {overlap_before:.0%}→{overlap_after:.0%}"
        f"{' | ending_feel除去' if ending_removed else ''}"
    )

    return {
        "loop_seeded": True,
        "ending_feel_removed": ending_removed,
        "trigger_added": triggered_last[-30:],
        "keyword_overlap_before": round(overlap_before, 2),
        "keyword_overlap_after": round(overlap_after, 2),
    }
