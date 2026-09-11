"""title_lexicon — タイトルの「型語」を1箇所で持つ。

背景（2026-09-12）:
    「型語」（なぜ／正体／本当の理由／隠された秘密／だけ／ショート／元ネタ …）は
    **題材を区別しない**のに、これまで3つのモジュールが別々のリストで持っていた:

      - theme_dedup._FILLER_WORDS / _BOILERPLATE_TOKENS   … 重複判定で落とす語
      - cross_channel_gate.ANSWER_MARKER_KEYWORDS / STOP_KEYWORDS … 横断ゲートの語
      - title_constraints._REASON_WORDS                    … 修復で足す語

    指揮者が「全タイトルに◯◯を入れる」と方針を変えるたびに、片方に足して片方に
    足し忘れ、重複ゲートが型語に反応して無関係な題材を落とす事故が3回再発した
    （08-23「ショート」/ 09-06 ハッシュタグ / 09-08「正体」/ 09-11「なぜ」「だけ」）。
    リストを1つにして、全モジュールがここから読む。

    ただし静的リストは本質的に**後追い**なので、theme_dedup 側は別途
    「比較対象の中で高頻度な語は型語とみなす」（文書頻度による自動判定）を持つ。
    こちらは新しい型語が生まれた瞬間から効く（→ theme_dedup.corpus_stopwords）。

公開:
    ANSWER_MARKERS      … 答え提示語（横断ゲートで別枠の上限を持つ語）
    FORMAT_PHRASES      … 正規化で消す型フレーズ（長い順）。重複判定用
    FORMAT_TOKENS       … 話題語抽出で捨てる定型トークン（媒体語・ジャンル語）
    channel_format_words(channel_dict) … チャンネル設定が必須化/禁止している語
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

# 答え提示語。「型」であって題材ではない。横断ゲートでは話題語より緩い上限で数える。
# 09-08 の実測: この語を含むタイトルは 登録/千再生 0.57、含まないもの 0.31。
ANSWER_MARKERS: frozenset = frozenset({
    "理由", "正体", "本当の", "実は", "わけ", "なぜ", "真相", "裏側", "実態",
    "真実", "からくり", "仕組み", "元ネタ", "秘密",
})

# 正規化で消す型フレーズ。**長い語から順に**消すこと（replace を順に掛けるため、
# 「本当の理由」を消す前に「理由」を消すと「本当の」が残る）。
_FORMAT_PHRASES_RAW: List[str] = [
    # 疑問・説明の定型
    "本当の理由", "という現象", "について", "とは何か", "とは", "の科学", "の謎",
    "の秘密", "隠された秘密", "隠された", "を解説", "を深掘り", "深掘り",
    "メカニズム", "仕組み", "理由", "なぜか", "なぜ", "どうして", "実は", "まとめ",
    "入門", "現象", "のだろうか", "のだろう", "のか", "こと", "もの", "ある",
    "する", "なる",
    # 煽りの定型
    "今すぐ", "衝撃", "驚愕", "閲覧注意", "禁断", "ヤバい", "やばい", "ヤバすぎ",
    "怖すぎる", "怖すぎ",
    # 「◯◯だけ」「◯◯しか」型（09-11 に重複誤検出の主語になった）
    "だけが", "だけの", "だけ", "しか",
    # 答え提示語の型（09-08 に全chへ必須化。話題を一切区別しない）
    "の正体が怖すぎる", "の元ネタが怖すぎる", "が怖すぎる",
    "の元ネタ", "元ネタ", "の正体", "正体",
    "の真相", "真相", "の実態", "実態", "の裏側", "裏側", "本当の", "わけ",
    "の真実", "真実", "からくり", "秘密",
    # 媒体語（08-23 に「ショート」共有だけで 0.76 に跳ねた）
    "ショート", "shorts", "short",
]


def _longest_first(words: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for w in sorted((w for w in words if w), key=lambda s: (-len(s), s)):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


FORMAT_PHRASES: List[str] = _longest_first(_FORMAT_PHRASES_RAW)

# 話題語抽出（漢字連・カタカナ連・英数連）で捨てる定型トークン。
# チャンネル名・シリーズ名・媒体語・ジャンル語。話題を区別しない。
FORMAT_TOKENS: frozenset = frozenset({
    # 媒体・体裁
    "ショート", "shorts", "short", "ゆっくり", "解説", "考察", "研究", "動画",
    "今回", "紹介", "雑学", "豆知識", "一口", "分科学", "ファイル", "まとめ",
    "切り抜き",
    # 各chの定型
    "scp", "goc", "gow", "anomaly", "item", "財団", "異常", "収容",   # scp-lab
    "妖怪", "伝承", "民話",                                          # yokai-watch
    "ポケモン", "ポケ", "図鑑",                                      # pokemon-lab
    "企業", "会社", "社員",                                          # company-facts
    "論文", "実験",                                                  # fake-paper
    "科学", "日常",                                                  # daily-science
    "スレ",                                                          # 2ch-matome
    "司書", "書庫",                                                  # akashic-librarian
})


def channel_format_words(channel_dict: Optional[Dict[str, Any]]) -> Set[str]:
    """チャンネル設定が「必ず入れる」「この語で始めない」と指定している語。

    設定で全タイトルに入ると決めた語は、そのチャンネルでは定義上「型語」である。
    `title_rules.hard_constraints.require_any_of.words` と `forbid_prefixes` を
    自動で拾うので、指揮者が必須語を増やしても手でリストを直す必要がない。
    """
    out: Set[str] = set()
    hc = (((channel_dict or {}).get("title_rules") or {}).get("hard_constraints")) or {}
    if not isinstance(hc, dict):
        return out
    spec = hc.get("require_any_of")
    words: Iterable[Any] = ()
    if isinstance(spec, dict):
        words = spec.get("words") or ()
    elif isinstance(spec, (list, tuple)):
        words = spec
    for w in words:
        w = str(w or "").strip()
        if w:
            out.add(w)
    for p in (hc.get("forbid_prefixes") or ()):
        p = str(p or "").strip()
        if p:
            out.add(p)
    return out


def is_format_word(word: str) -> bool:
    """語が型語（題材を区別しない語）か。"""
    w = (word or "").strip().lower()
    return bool(w) and (w in ANSWER_MARKERS or w in FORMAT_TOKENS or w in FORMAT_PHRASES)
