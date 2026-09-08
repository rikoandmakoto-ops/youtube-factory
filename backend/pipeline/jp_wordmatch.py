"""jp_wordmatch — 日本語の「語として当たったか」を判定する共通ルール。

背景（2026-09-09）:
    語彙表との照合を素の部分一致（`keyword in text`）でやっていたため、
    無関係な語の内側に当たる事故が繰り返し起きていた。実測例:

        「ロケット団の言葉選びを追う」
            → 『ロケット』アイコン（ロケット**団**）と『植物』アイコン（言**葉**）
        「月額いくら払えば」            → 『月』アイコン
        「影響」                        → 『人影』シルエット
        「注目 / 駄目 / 3回目」          → 『視覚』アイコン
        「意味 / 興味」                  → 『味覚』アイコン
        「能力 / 魅力 / 協力」            → 『エネルギー』アイコン
        「本音」                        → 『波』アイコン

    これをチャンネル単位のフラグ（`thumbnail_card: false`）で潰すと、当たっている
    チャンネルまで機能を失う上に、新しいチャンネルが増えるたびに同じ事故が出る。
    照合規則そのものを直す。

方針:
    形態素解析器は入れない（Python 3.9・本番常駐・追加依存を増やしたくない）。
    代わりに **文字種の切れ目**を語境界の近似として使う。日本語は語境界に
    空白が無い代わりに、漢字↔ひらがな↔カタカナの切り替わりが語の切れ目と
    かなり高い確率で一致する。そのうえで、実測で出た誤爆の型だけを潰す:

      規則1  1文字の漢字キーワードは、前後に漢字が続いていたら不採用。
             （月額の月／言葉の葉／注目の目／影響の影／意味の味／能力の力）
             2文字以上の漢字キーワードは複合語の中でも意味が保たれるので許す
             （筋肉痛の筋肉／睡眠不足の睡眠／電気代の電気）。

      規則2  カタカナのキーワードはカタカナの連なり全体と一致すること。
             さらに直後が漢字なら不採用（ロケット団／アニメ版／ゲーム機 の型）。
             カタカナ＋漢字は複合名詞・固有名詞になり、元の語の意味では無くなる。

      規則3  ラテン文字のキーワードはラテン文字の連なり全体と一致すること
             （DNAが SDNA の内側に当たらない）。直後の漢字は許す
             （「DNA鑑定」「PCR検査」は元の語がそのまま主題なので）。

      ひらがなの側は境界を見ない。活用語尾があるので「見え」＋「ない」の
      ような切れ目を「語の途中」と誤判定してしまうため。

    偽陰性（本当は当たっているのに落とす）側に倒してある。呼び出し側は
    「確度が足りなければ描かない」判断に使うので、迷ったら描かない方が安全。

公開 API:
    contains_word(text, keyword) -> bool
    find_words(text, keywords)   -> [matched keyword, ...]
"""

from __future__ import annotations

from typing import Iterable, List, Sequence

__all__ = ["contains_word", "find_words", "char_class"]

# 文字種。'other' は記号・空白・句読点で、常に語境界として扱う。
_KANJI = "kanji"
_KATAKANA = "katakana"
_HIRAGANA = "hiragana"
_LATIN = "latin"
_DIGIT = "digit"
_OTHER = "other"


def char_class(ch: str) -> str:
    """1文字の文字種を返す。"""
    if not ch:
        return _OTHER
    o = ord(ch)
    # 々（繰り返し記号）と ヶ は漢字の一部として振る舞う（「人々」「一ヶ月」）。
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or ch in "々〆ヶ":
        return _KANJI
    # 長音符とカタカナ中黒はカタカナ語の一部（「コーヒー」）。中黒は語の切れ目
    # でもあるが、切れ目として扱うと「ロケット・団」のような表記で緩くなるので
    # ここではカタカナ側に寄せる。
    if 0x30A1 <= o <= 0x30FA or ch in "ーヽヾ":
        return _KATAKANA
    if 0x3041 <= o <= 0x309F:
        return _HIRAGANA
    if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("ａ" <= ch <= "ｚ") or ("Ａ" <= ch <= "Ｚ"):
        return _LATIN
    if ch.isdigit():
        return _DIGIT
    return _OTHER


def _occurrence_is_word(text: str, start: int, keyword: str) -> bool:
    """text[start:start+len(keyword)] を「語として」認めてよいか。"""
    end = start + len(keyword)
    left = text[start - 1] if start > 0 else ""
    right = text[end] if end < len(text) else ""
    lc = char_class(left) if left else _OTHER
    rc = char_class(right) if right else _OTHER
    first = char_class(keyword[0])
    last = char_class(keyword[-1])

    # 規則1: 1文字の漢字は、漢字に挟まれていたら複合語の内側なので不採用。
    if len(keyword) == 1 and first == _KANJI:
        if lc == _KANJI or rc == _KANJI:
            return False

    # 規則2: カタカナ語はカタカナの連なり全体と一致し、直後に漢字が来ない。
    if first == _KATAKANA or last == _KATAKANA:
        if lc == _KATAKANA or rc == _KATAKANA:
            return False
        if last == _KATAKANA and rc == _KANJI:
            return False

    # 規則3: ラテン文字語はラテン文字の連なり全体と一致する。
    if first == _LATIN and lc == _LATIN:
        return False
    if last == _LATIN and rc == _LATIN:
        return False

    return True


def contains_word(text: str, keyword: str) -> bool:
    """`keyword` が `text` に**語として**現れるか。"""
    t = text or ""
    k = keyword or ""
    if not t or not k:
        return False
    pos = t.find(k)
    while pos != -1:
        if _occurrence_is_word(t, pos, k):
            return True
        pos = t.find(k, pos + 1)
    return False


def find_words(text: str, keywords: Iterable[str]) -> List[str]:
    """`keywords` のうち `text` に語として現れるものを、渡された順で返す。"""
    return [k for k in keywords if contains_word(text, k)]


def any_word(text: str, keywords: Sequence[str]) -> bool:
    return any(contains_word(text, k) for k in keywords)
