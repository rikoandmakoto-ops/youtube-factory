"""ショート最終行の CTA を決定論的に保証する（2026-09-01 新設）。

【なぜ必要か】
至上目標はチャンネル登録者数の増加だが、08-29〜08-31 に生成された
ショート台本 32本の **実際にレンダリングされる最終行** を実測したところ：

    高評価CTAあり  16/32 (50%)
    登録CTAあり    12/32 (38%)   ← 62%のショートが登録を一度も求めていない

チャンネル別（08/29-31, ショートシナリオ節の最終行）:
    company-facts  高評価 0/4  登録 0/4   ← CTAが一切ない
    daily-science  高評価 3/4  登録 0/4
    yokai-watch    高評価 1/3  登録 0/3
    pokemon-lab    高評価 3/4  登録 1/4
    2ch-matome     高評価 3/4  登録 1/4
    scp-lab        高評価 5/7  登録 5/7

【なぜ CTA が消えるか】
`cta_rotator` / `replay_loop_seeder` は 13ch中12ch で
`script_enhancers.disabled` により無効化されている（enhancer_gate.py:31-48）。
そのため CTA 文言は channel JSON の `short_format.structure` に
「6行目=高評価CTA+登録CTA」と書いてあるだけの **LLM任せ** であり、
強制力がない。`scenario_validator._check_cta()` は
CTA_PATTERNS に高評価の語を持たず、かつ strict=False で呼ばれるため
違反しても警告すら止まらない（generator.py:2470）。

【なぜ高評価を先に置くか（実測）】
成熟動画 n=322 のチャンネル内統制比較。高評価率の4分位と登録転換：

    高評価率 0-0.2%   n= 72  登録/1000再生 0.17
    高評価率 0.2-0.4% n=102  登録/1000再生 0.32
    高評価率 0.4-0.8% n=119  登録/1000再生 0.53
    高評価率 0.8%+    n= 29  登録/1000再生 1.07   ← 最下位群の 6.3倍

単調増加であり、途中に反転がない。一方で **終盤維持率（90-100%区間）は
登録転換と無相関**（<15%:0.41 / 15-25%:0.26 / 25-40%:0.42 / 40%+:0.30）。
つまり「最後まで見せれば登録される」は本データでは否定されており、
登録を増やす観測レバーは終盤維持率ではなく高評価率である。

【この関数がすること】
最終行に対してのみ、決定論的に：
  1. CTA の後ろに付いたループ誘導句（「…待って、Xに戻って」等）を除去する。
     これは replay_loop_seeder が Round7 で CTA の**後**に足すため、
     登録導線が最後の1〜2秒で埋もれる。
  2. 高評価の語が無ければ、チャンネルの語り口に合わせた高評価句を**先頭**に挿す。
  3. 登録の語が無ければ、登録句を**末尾**に足す。

再生成ではなく文字列修復なのは、無人実行で生成本数がゼロになるのを避けるため
（shorts_length_guard と同じ方針）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 高評価を求めているとみなす語。
# 「いいね」単独だと「それいいねって思った人はコメントで」のような
# 相槌に誤反応するため、ボタンを押す文脈を伴う形だけを採る。
LIKE_PATTERNS: List[str] = [
    r"高評価",
    r"いいね(?:ボタン|を|も|だけ|押)",
    r"グッドボタン",
]

# チャンネル登録を求めているとみなす語。
# 裸の「登録」は company-facts の「商標登録」「登録免許税」、
# daily-science の「登録者数」等の一般語に誤反応し、
# 「CTAは既にある」と誤判定して補正を抑止してしまう。
# そのため *依頼している形* のみを採る。
SUBSCRIBE_PATTERNS: List[str] = [
    r"チャンネル登録",
    r"登録(?:して|すれば|しと|を|も|で|よろしく|お願い|頼む|待|は済)",
    r"フォロー(?:して|よろしく|を|も|お願い|頼む)",
]

# 「登録」を含むが CTA ではない一般語（誤検知の確認用・テストが参照する）
NON_CTA_SUBSCRIBE_WORDS: List[str] = [
    "登録者数",
    "商標登録",
    "登録免許税",
    "登録商標",
]

# replay_loop_seeder が CTA の後ろに足すループ誘導句。
#
# トリガーは `f"{text}{trigger}"` (replay_loop_seeder.py:199) で
# 「…」始まりの suffix として連結される。ここでは
# replay_loop_seeder が実際に足す文言だけを対象にする。
#
# 「行末の … 以降を全部落とす」だと、日本語台本が溜めに多用する
# 「答えは…実は3年前から決まっていた。」のような文を
# 「答えは」まで削ってしまい、TTS が破片を読み上げる。
# そこで replay_loop_seeder.py の LOOP_TRIGGERS / _DEFAULT_TRIGGERS と
# custom_triggers の *形* に一致するものだけを除去する。
_LOOP_TRIGGER_BODIES = [
    # custom_triggers（キーワード埋め込み・replay_loop_seeder.py:179-193）
    r"あれ、.{1,10}って最初に言ってた",
    r"待って、.{1,10}に戻って",
    # チャンネル別 LOOP_TRIGGERS + _DEFAULT_TRIGGERS（同 44-86）
    r"って、冒頭の話に戻るんだけど",
    r"実はこれ、最初に言ったことと繋がってる",
    r"あれ？これってさっきの",
    r"待て、最初の報告と矛盾してないか",
    r"まさか、冒頭の.{0,8}がこれを意味していたのか",
    r"この収容手順、最初から見直す必要がある",
    r"あれ、最初のレスもう一回読んでみ",
    r"ちょ待て、>>1に戻ってみろ",
    r"草、最初から伏線だったのかよ",
    r"この数字、冒頭のデータと照合すると",
    r"つまり最初に言った通り、全部繋がっている",
    r"これが最初の疑問の答えだ",
    r"あれ、最初に言ったやつもう一回見て",
    r"ここでさっきの伏線回収なんだけど",
    r"つまり最初のアレ、全部ここに繋がってた",
    r"そういえば、最初の話を思い出してほしい",
    r"冒頭の怪異、実はここに繋がっていた",
    r"これが最初の違和感の正体だった",
    r"そしてこの記録は、冒頭に戻る",
    r"最初の一節が、ここで意味を持つ",
    r"記録は繰り返される",
    r"あれ、最初のあの話",
    r"ちょっと待って、最初に戻ってみて",
    r"つまりこれ、最初から繋がってた",
]
_LOOP_TRAILER = re.compile(
    r"(?:…|\.\.\.)\s*(?:" + "|".join(_LOOP_TRIGGER_BODIES) + r")[^。]*$"
)

# 最終行の上限。実測 CTA（scp-lab の良例）が 48字前後。
# ここを超えても *まずは台本の文言を残す*。台本を定型文へ畳むのは
# 100字を超えた場合のみで、毎日同じ最終行が並ぶ副作用を避ける。
_LAST_LINE_BUDGET = 100

# チャンネル別の既定CTA句。channel JSON の
# short_format.cta_fallback = {"like": ..., "subscribe": ...} があればそちらを優先。
_DEFAULT_CTA: Dict[str, Dict[str, str]] = {
    # 報告役シロは抑揚を殺した常体。感嘆符は使わない。
    "scp-lab": {
        "like": "この報告書が届いたなら高評価を残せ。",
        "subscribe": "登録すれば、次の収容違反ファイルが届く。",
    },
    # 理子は丁寧語。真だけがタメ口。
    "daily-science": {
        "like": "今日のこれ、面白かったら高評価を押してね。",
        "subscribe": "チャンネル登録すれば、毎日ひとつ雑学が増えるよ。",
    },
    # ゴロー/ユイは一人称ワイ・語尾やろ/やが/草/w。
    "2ch-matome": {
        "like": "共感したやつは高評価だけ置いてけw",
        "subscribe": "チャンネル登録も頼むわ、毎日投稿しとるで。",
    },
    # ヒカリ研究員はテンション高めのタメ口。
    "pokemon-lab": {
        "like": "え、マジで？ってなったら高評価を押してね。",
        "subscribe": "チャンネル登録すれば、毎日ひとつポケモンの秘密が届くよ。",
    },
    # ミナモ調査員は丁寧語だが怪談の語り口。
    "yokai-watch": {
        "like": "ゾッとしたら高評価を押してね。",
        "subscribe": "チャンネル登録すれば、次の妖怪の原典も調べて持ってくるよ。",
    },
    # 企業紹介。断定を避けた丁寧語。
    "company-facts": {
        "like": "面白かったら高評価を押してね。",
        "subscribe": "チャンネル登録すれば、毎日1社の実態が届くよ。",
    },
    "fake-paper": {
        "like": "面白かったら高評価をお願いします。",
        "subscribe": "チャンネル登録で、存在しない次の論文をお届けします。",
    },
}

_GENERIC_CTA: Dict[str, str] = {
    "like": "面白かったら高評価を押してね。",
    "subscribe": "チャンネル登録もよろしくね。",
}


def _has(patterns: List[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def _visible_len(text: str) -> int:
    """空白を除いた実文字数（読み上げ尺の目安）。"""
    return len(re.sub(r"\s", "", text))


def has_like(text: str) -> bool:
    """高評価を求める語が含まれるか。"""
    return _has(LIKE_PATTERNS, text)


def has_subscribe(text: str) -> bool:
    """チャンネル登録を求める語が含まれるか。"""
    return _has(SUBSCRIBE_PATTERNS, text)


def cta_phrases(
    channel_id: str,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """チャンネルの語り口に合わせた CTA 句を返す。

    channel JSON の short_format.cta_fallback を最優先し、次に
    _DEFAULT_CTA、最後に汎用句にフォールバックする。
    """
    phrases = dict(_DEFAULT_CTA.get(channel_id or "", _GENERIC_CTA))
    if channel_dict:
        override = (channel_dict.get("short_format") or {}).get("cta_fallback")
        if isinstance(override, dict):
            for key in ("like", "subscribe"):
                value = override.get(key)
                if isinstance(value, str) and value.strip():
                    phrases[key] = value.strip()
    return phrases


def strip_loop_trailer(text: str) -> str:
    """CTA の後ろに付いた replay_loop_seeder のループ誘導句を除去する。

    replay_loop_seeder が実際に生成する文言と一致した場合のみ削る。
    「…」を見たら全部落とす、という実装にすると
    「答えは…実は3年前から決まっていた。」が「答えは」まで削られ、
    TTS が破片を読み上げてしまうため。

    切り落とす側に高評価/登録の語が含まれる場合は CTA 本体を巻き込む
    恐れがあるので何もしない。
    """
    match = _LOOP_TRAILER.search(text)
    if not match:
        return text
    head = text[: match.start()].rstrip()
    tail = text[match.start():]
    if not head:
        return text
    if has_like(tail) or has_subscribe(tail):
        return text
    return head


def enforce_final_cta(
    channel_id: str,
    scenario: List[Dict[str, Any]],
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """最終行に高評価CTA→登録CTAの順で存在を保証する（in-place）。

    Args:
        scenario: 行 dict のリスト（"text" キー）。**破壊的に変更される**。
        channel_dict: channel JSON。short_format.cta_fallback を読む。

    Returns:
        {"applied": bool, "added_like": bool, "added_subscribe": bool,
         "stripped_loop": bool, "before": str, "after": str}
    """
    result: Dict[str, Any] = {
        "applied": False,
        "added_like": False,
        "added_subscribe": False,
        "stripped_loop": False,
        "collapsed": False,
        "deduped_series": False,
        "before": "",
        "after": "",
    }
    if not scenario:
        return result

    last = scenario[-1]
    if not isinstance(last, dict):
        return result
    raw = last.get("text")
    # text が str でない台本（数値・リスト等）が来ても落とさない。
    # ここで例外を投げると呼び出し側の except に飲まれ、補正が
    # 黙って飛ばされるだけになるため、型で門前払いする。
    if not isinstance(raw, str):
        return result
    original = raw.strip()
    if not original:
        return result
    result["before"] = original

    text = original

    # 0. 「シリーズシリーズ」重複の解消。
    #    theme_priority.series_lineup の値が既に「〜シリーズ」で終わっているのに
    #    generator.py の指示で LLM が「〜シリーズ、」と書くため、
    #    「睡眠と夢シリーズシリーズ」「裏設定ファイルシリーズシリーズ」が
    #    そのまま読み上げられていた。cta_rotator 側の同等の修正は
    #    13ch中12ch で enhancer が無効なため効かない。
    deduped = re.sub(r"(シリーズ)(?:\s*シリーズ)+", r"\1", text)
    if deduped != text:
        result["deduped_series"] = True
        text = deduped

    # 1. CTA の後ろのループ誘導句を落とす（登録導線が末尾で埋もれるのを防ぐ）
    stripped = strip_loop_trailer(text)
    if stripped != text:
        result["stripped_loop"] = True
        text = stripped

    phrases = cta_phrases(channel_id, channel_dict)
    need_like = not has_like(text)
    need_sub = not has_subscribe(text)

    # 2. 高評価を先頭に（実測 6.3倍の観測レバーを最優先で置く）
    if need_like:
        text = f"{phrases['like']} {text}".strip()
        result["added_like"] = True

    # 3. 登録を末尾に
    if need_sub:
        if text and not text.endswith(("。", "！", "？", "!", "?", "w", "草")):
            text += "。"
        text = f"{text} {phrases['subscribe']}".strip()
        result["added_subscribe"] = True

    # 4. 極端に伸びた場合の最終手段。
    #
    #    台本字数は維持率を直接規定する（維持率 = 92.6 - 0.1720×字数, r=-0.414, n=214）ため
    #    最終行を無制限に伸ばすことはできない。一方で、少し超えた程度で定型文へ畳むと
    #    台本が書いたシリーズ名・コメント誘導・キャラの語り口が毎回消え、
    #    そのチャンネルの全ショートが同一の最終行で終わってしまう。
    #    そこで既定 100字までは台本の文言を残し、それを超えた時だけ畳む。
    if (need_like or need_sub) and _visible_len(text) > _LAST_LINE_BUDGET:
        text = f"{phrases['like']} {phrases['subscribe']}".strip()
        result["collapsed"] = True
        # フォールバック自体が長い（channel JSON の cta_fallback 上書き等）場合に
        # 予算を超えたまま返さないよう、汎用句まで落とす。
        if _visible_len(text) > _LAST_LINE_BUDGET:
            text = f"{_GENERIC_CTA['like']} {_GENERIC_CTA['subscribe']}".strip()

    if text != original:
        last["text"] = text
        result["applied"] = True
    result["after"] = text
    return result
