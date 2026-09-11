"""title_gate — タイトルの衛生検査を**1箇所**に集める。

背景（2026-09-11 → 12）:
    company-facts で『個人向け国債、年0.05%でも元本割れしにくい仕組み、】【の実態』
    という題が LLM の作り直しで生まれ、出力フォルダ名・サムネ・説明文・mp4 まで
    `】【` を含んだまま貫通した（job 1a6e3105）。作り直し後は `.strip("「」")`
    しか通っておらず、しかもタイトルが確定する経路は

        LLM 本生成 → Round7 絵文字注入 → 通し番号 → AB テスト → 重複作り直し
        → CTR 作り直し → 規約作り直し/機械修復 → 横断語作り直し

    と 8 段あって、それぞれが自分の直後の値しか見ていない。1段直しても別の段が
    壊れた値を持ち込める構造なので、**最後に必ず通る 1 箇所**で機械的に検査する。

設計:
    - `sanitize(title)`  … 決定論的な掃除。例外を投げない。空になりうる。
        * 前後の引用符・空白・「タイトル：」のような LLM の前置きを剥がす
        * 対になっていない括弧の破片（`】【`・閉じ忘れ）を除去、空の括弧を畳む
        * 制御文字・YouTube が拒否する `<` `>` を除去、空白と句読点の連続を畳む
        * `【ショート】` の二重付与を1つにする
        * 末尾に取り残された区切り記号を除去
    - `validate(title, channel_dict)` … 通せない理由の一覧。空なら OK。
        * 空・短すぎ・長すぎ（YouTube 上限 100）・括弧不整合・禁止文字
        * channel_dict があれば `title_constraints.check` の違反も含める
    - `finalize(title, channel_dict, fallback)` … 生成側の最終出口。
        sanitize → 長すぎれば区切りで詰める → 空なら fallback を同じ処理で使う。
        それでも使い物にならなければ `TitleGateError`（壊れたまま公開するより止める）。
    - `for_upload(title)` … 投稿側の最終出口（YouTube / TikTok）。
        sanitize + 100 字に詰める。空なら `TitleGateError`。
    - `safe_dirname(title)` … 出力フォルダ名。パス区切りと OS 禁止文字を落とす。

    通す場所（すべての経路がどれかを必ず通る）:
        generator.generate()   … result["title"] を finalize
        各 _regenerate_*      … LLM の作り直しは llm_title() で受ける
        job_queue.submit()     … ジョブ名 = finalize
        video_generator.generate_all() … フォルダ名 = safe_dirname、内部 title = sanitize
        youtube_uploader.upload_video() / tiktok_uploader.upload_video() … for_upload

    ここは**規約**（数字禁止・必須語など、チャンネルごとに違うルール）を判定する
    場所ではない。それは `title_constraints` の仕事で、finalize はそれを呼ぶだけ。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

# YouTube のタイトル上限。超えると videos.insert が 400 で落ちる。
YOUTUBE_TITLE_MAX = 100
# これより短いタイトルは「壊れている」とみなす（『】【』の掃除で残骸だけになった等）。
MIN_TITLE_CHARS = 8

# 対で扱う括弧。順序が逆の破片（`】【`）も検出できるよう走査で処理する。
_BRACKET_PAIRS = (("【", "】"), ("「", "」"), ("『", "』"), ("（", "）"), ("(", ")"),
                  ("［", "］"), ("[", "]"), ("〈", "〉"), ("《", "》"))
_EMPTY_BRACKETS = tuple(o + c for o, c in _BRACKET_PAIRS)

# LLM が付けがちな前置き。「タイトル: 」「Title: 」「案1: 」
_LLM_PREAMBLE_RE = re.compile(
    r"^\s*(?:タイトル|title|案\s*\d+|候補\s*\d+)\s*[:：．.、)）]\s*", re.IGNORECASE)
# 先頭の箇条書き記号・番号（「1. 」「1) 」）。数字＋読点は本文でありうるので触らない。
_LIST_MARK_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)．）])\s*")
# 前後に付く引用符（ASCII・カーリー）。「」『』は**全体を包んでいるときだけ**剥がす
# （「〜」上司の末路 のように本文の一部として使う題を壊さない）。
_QUOTE_CHARS = "\"'“”‘’`　 "
_WRAP_PAIRS = (("「", "」"), ("『", "』"))
# 制御文字（改行・タブ含む）と、YouTube が title に許さない山括弧
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f<>]")
# 空白の連続
_WS_RE = re.compile(r"[ \t　]+")
# 句読点・区切りの連続（「、、」「、】、」）
_PUNCT_DUP_RE = re.compile(r"([、，,。．・])[、，,。．・]+")
# 末尾に取り残される区切り記号
_TRAILING_SEP = " 　、。,．.・-—ー–~〜|｜/／:："
# 先頭に取り残される区切り記号（ハッシュタグの # は残す）
_LEADING_SEP = " 　、。,．.・-—–~〜|｜/／:："

SHORT_MARKER = "【ショート】"

# ファイル名に使えない文字（macOS / Linux / Windows の和集合）
_FS_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
# macOS の名前上限は 255 バイト。日本語は 3 バイトなので安全側で 80 字。
DIRNAME_MAX_CHARS = 80

# 長すぎるときに「ここで切ると自然」な区切り（後ろから探す）
_BREAK_CHARS = ("——", "—", "…", "。", "！", "？", "」", "』", "）", "】", "、", " ")


class TitleGateError(ValueError):
    """掃除しても使い物にならないタイトル。壊れたまま公開するより止める。"""


# ---------------------------------------------------------------------
# 掃除
# ---------------------------------------------------------------------

def _drop_unpaired_brackets(s: str) -> str:
    """対になっていない括弧の破片を落とす。

    個数だけでは `】【` のような**順序が逆**の破片を見逃す（実例がこれ）ので、
    左から走査して「開く前に閉じた」「閉じられないまま終わった」を両方落とす。
    """
    for open_c, close_c in _BRACKET_PAIRS:
        if open_c not in s and close_c not in s:
            continue
        kept: List[str] = []
        open_positions: List[int] = []
        for ch in s:
            if ch == open_c:
                open_positions.append(len(kept))
                kept.append(ch)
            elif ch == close_c:
                if not open_positions:
                    continue  # 開く前に閉じた → 破片
                open_positions.pop()
                kept.append(ch)
            else:
                kept.append(ch)
        for pos in sorted(open_positions, reverse=True):  # 閉じられなかった開き括弧
            kept.pop(pos)
        s = "".join(kept)
    return s


def _collapse_empty_brackets(s: str) -> str:
    changed = True
    while changed:
        changed = False
        for pair in _EMPTY_BRACKETS:
            if pair in s:
                s = s.replace(pair, "")
                changed = True
    return s


def _unwrap_quotes(s: str) -> str:
    """全体が「〜」『〜』で包まれているときだけ外す（本文中の鉤括弧は残す）。"""
    changed = True
    while changed and len(s) >= 2:
        changed = False
        for open_c, close_c in _WRAP_PAIRS:
            if (s.startswith(open_c) and s.endswith(close_c)
                    and open_c not in s[1:-1] and close_c not in s[1:-1]):
                s = s[1:-1].strip(_QUOTE_CHARS)
                changed = True
    return s


def _dedupe_short_marker(s: str) -> str:
    """`【ショート】` が2つ以上あれば末尾の1つだけ残す。"""
    if s.count(SHORT_MARKER) <= 1:
        return s
    body = s.replace(SHORT_MARKER, "")
    return body.rstrip(_TRAILING_SEP) + SHORT_MARKER


def sanitize(title: Optional[str]) -> str:
    """決定論的な掃除。例外を投げない。掃除の結果が空なら空文字を返す。"""
    s = "" if title is None else str(title)
    s = unicodedata.normalize("NFC", s)
    # 複数行なら最初の非空行だけ（LLM が説明文を続けてくることがある）
    lines = [ln for ln in re.split(r"[\r\n]+", s) if ln.strip()]
    s = lines[0] if lines else ""
    s = _CONTROL_RE.sub("", s)
    # markdown 強調
    s = s.replace("**", "").replace("__", "")
    s = _LLM_PREAMBLE_RE.sub("", s)
    s = _LIST_MARK_RE.sub("", s)
    s = s.strip(_QUOTE_CHARS)
    s = _unwrap_quotes(s)
    s = _drop_unpaired_brackets(s)
    s = _collapse_empty_brackets(s)
    s = _dedupe_short_marker(s)
    s = _WS_RE.sub(" ", s)
    s = _PUNCT_DUP_RE.sub(r"\1", s)
    s = s.strip()
    s = s.lstrip(_LEADING_SEP).rstrip(_TRAILING_SEP)
    # 括弧の直前に読点が残る（「仕組み、【ショート】」）→ 落とす
    s = re.sub(r"[、，,・]\s*(?=[【「『（(])", "", s)
    # 破片を抜いた跡で読点の直後に助詞が来る（「仕組み、の実態」）→ 読点を落とす
    s = re.sub(r"[、，,]\s*(?=[のがはをにでとへも])", "", s)
    # 閉じ括弧の直後に句点・読点が来て終わる（「〜】、」）→ 落とす
    s = s.rstrip(_TRAILING_SEP)
    return s.strip()


def trim_to(title: str, limit: int) -> str:
    """`limit` 文字に詰める。ハッシュタグの途中・語の途中で切らない。"""
    s = (title or "").strip()
    if limit <= 0:
        return ""
    if len(s) <= limit:
        return s
    head = s[:limit]
    # 切れ目の直後が空白なら、語の境界で切れている（末尾のタグも完全）。
    if not s[limit].isspace():
        for sep in _BREAK_CHARS:
            idx = head.rfind(sep)
            if idx >= limit // 2:
                head = head[: idx + (len(sep) if sep in ("」", "』", "）", "】") else 0)]
                break
        else:
            head = head[: limit - 1] + "…"
        # 途中で切れたハッシュタグ（「#shor」）は丸ごと落とす
        head = re.sub(r"\s*[#＃][^\s#＃]*$", "", head)
    return sanitize(head)


# ---------------------------------------------------------------------
# 検査
# ---------------------------------------------------------------------

def _bracket_problems(s: str) -> List[str]:
    out: List[str] = []
    for open_c, close_c in _BRACKET_PAIRS:
        depth = 0
        for ch in s:
            if ch == open_c:
                depth += 1
            elif ch == close_c:
                depth -= 1
                if depth < 0:
                    out.append(f"括弧の破片 {close_c}")
                    break
        else:
            if depth > 0:
                out.append(f"閉じていない括弧 {open_c}")
    return out


def validate(title: Optional[str], channel_dict: Optional[Dict[str, Any]] = None,
             *, max_chars: int = YOUTUBE_TITLE_MAX) -> List[str]:
    """通せない理由の一覧。空なら OK。

    channel_dict を渡すと `title_rules.hard_constraints` の違反も含める
    （数字禁止・必須語など。判定は title_constraints に委ねる）。
    """
    s = "" if title is None else str(title)
    problems: List[str] = []
    if not s.strip():
        return ["空"]
    if s != s.strip():
        problems.append("前後の空白")
    if _CONTROL_RE.search(s):
        problems.append("制御文字または < >")
    if len(s) < MIN_TITLE_CHARS:
        problems.append(f"短すぎ({len(s)}字)")
    if len(s) > max_chars:
        problems.append(f"長すぎ({len(s)}字>{max_chars})")
    problems.extend(_bracket_problems(s))
    for pair in _EMPTY_BRACKETS:
        if pair in s:
            problems.append(f"空の括弧 {pair}")
            break
    if s.count(SHORT_MARKER) > 1:
        problems.append("【ショート】の二重付与")
    if s.rstrip() and s.rstrip()[-1] in "、，,・-—ー–~〜|｜/／:：":
        problems.append("末尾の区切り記号")
    if channel_dict:
        try:
            from pipeline import title_constraints as _tc
            if _tc.is_enforced(channel_dict):
                v = _tc.check(s, channel_dict)
                if not v["ok"]:
                    problems.append("規約: " + _tc.violation_summary(v))
        except Exception as e:  # 規約モジュールの不調で衛生検査まで止めない
            problems.append(f"規約検査不能: {e}")
    return problems


def is_clean(title: Optional[str]) -> bool:
    """衛生面（括弧・長さ・禁止文字）だけを見て通るか。規約は見ない。"""
    return not validate(title)


# ---------------------------------------------------------------------
# 出口
# ---------------------------------------------------------------------

def llm_title(raw: Optional[str]) -> Optional[str]:
    """LLM が返したタイトル文字列を受ける。使えなければ None（呼び出し側は元題を維持）。"""
    s = sanitize(raw)
    if not s or len(s) < MIN_TITLE_CHARS:
        return None
    if validate(s, max_chars=YOUTUBE_TITLE_MAX):
        return None
    return s


def finalize(title: Optional[str], channel_dict: Optional[Dict[str, Any]] = None,
             *, fallback: Optional[str] = None,
             max_chars: int = YOUTUBE_TITLE_MAX) -> str:
    """生成側の最終出口。掃除して、長ければ詰めて、駄目なら fallback、それでも駄目なら例外。

    規約違反（title_constraints）はここでは**直さない**（直すのは生成側のゲートの
    仕事で、ここに来る時点で終わっている）。衛生面だけを保証する。
    """
    short_ok: Optional[str] = None
    for cand in (title, fallback):
        s = sanitize(cand)
        if len(s) > max_chars:
            s = trim_to(s, max_chars)
        if not s:
            continue
        problems = validate(s, max_chars=max_chars)
        if not problems:
            return s
        # 「短い」だけなら壊れてはいない（手動ジョブの短い題名など）。掃除済みの
        # 候補が他に無ければ採る。
        if short_ok is None and all(p.startswith("短すぎ") for p in problems):
            short_ok = s
    if short_ok is not None:
        return short_ok
    raise TitleGateError(
        f"タイトルが壊れていて掃除しても使えません: {title!r}"
        + (f" / fallback={fallback!r}" if fallback is not None else ""))


def for_upload(title: Optional[str]) -> str:
    """投稿側の最終出口。YouTube / TikTok に渡す直前に必ず通す。"""
    s = sanitize(title)
    if len(s) > YOUTUBE_TITLE_MAX:
        s = trim_to(s, YOUTUBE_TITLE_MAX)
    if not s:
        raise TitleGateError(f"投稿タイトルが空です: {title!r}")
    return s


def safe_dirname(title: Optional[str], *, fallback: str = "untitled") -> str:
    """出力フォルダ名。パス区切り・OS 禁止文字・制御文字を落とし、長さを抑える。"""
    s = sanitize(title)
    s = _FS_FORBIDDEN_RE.sub("", s)
    s = s.strip(" .")  # 先頭/末尾のドット・空白は OS によって不可
    if len(s) > DIRNAME_MAX_CHARS:
        s = s[:DIRNAME_MAX_CHARS].rstrip(" .")
    return s or fallback
