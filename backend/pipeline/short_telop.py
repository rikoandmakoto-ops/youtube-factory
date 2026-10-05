"""ショートの読み上げテロップ（字幕）描画。

2026-10-03 visual r1 で新設。比較対象（化け学のふしぎ 848万・ぽへ 155万 など
上位ショート8本）と原寸コマで並べたときの差は次の3点だった:

  1. 上位は「いま読んでいる一句」だけを 2 行以内・極太で出す。こちらは
     1 行ぶん（最大 61 字）を 62px で 3〜4 行まとめて出していた。
  2. 上位はキーワード（数字・固有名詞）だけ赤や黄に塗り分ける。こちらは単色。
  3. こちらは行頭に「、」が来たり「。」だけの行ができたりしていた（禁則なし）。

このモジュールはその 3 点だけを受け持つ。
  - split_chunks:   1 セリフを読み上げ順の「句」に分ける（。！？ と 、 で区切る）
  - wrap_balanced:  句を 2 行以内・左右の長さが揃う位置で改行（行頭禁則つき）
  - find_highlights: 数字＋単位 / 「」の中身 / 3 字以上のカタカナ語 を強調対象に
  - render_telop:   上記を PIL の stroke で描いて全画面 RGBA レイヤで返す

描画は PIL の draw.text(stroke_width=...) を使う（video_generator の
draw_composite_text は 1 文字ずつ r² 回描くので太い縁取りだと遅い）。
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

# 極太の和文ゴシック（上位ショートのテロップは W8〜W9 相当）。無ければ順に落とす。
_HEAVY_FONTS = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)
_BOLD_FONTS = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)


def _first_existing(paths: Sequence[str]) -> Optional[str]:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


HEAVY_FONT_PATH = _first_existing(_HEAVY_FONTS)
BOLD_FONT_PATH = _first_existing(_BOLD_FONTS) or HEAVY_FONT_PATH


@lru_cache(maxsize=64)
def font(size: int, weight: str = "heavy"):
    path = HEAVY_FONT_PATH if weight == "heavy" else BOLD_FONT_PATH
    if path:
        try:
            return ImageFont.truetype(path, int(size))
        except Exception:
            pass
    return ImageFont.load_default()


def text_width(text: str, size: int, weight: str = "heavy") -> int:
    if not text:
        return 0
    f = font(size, weight)
    try:
        return int(round(f.getlength(text)))
    except Exception:
        return len(text) * size


# ---------------------------------------------------------------------
# 句に分ける
# ---------------------------------------------------------------------
_SENT_END = "。！？!?"
_CLAUSE = "、，,"
# 句の末尾から落とす記号（上位ショートのテロップは句点・読点を出さない）
_TRAIL_STRIP = "。、，,．."


def _visible_len(s: str) -> int:
    return len(s.strip())


def split_chunks(text: str, max_chars: int = 18, min_chars: int = 5) -> List[Tuple[str, int]]:
    """1 セリフを読み上げ順の句に分ける。

    戻り値は (表示文字列, 重み) のリスト。重みは元の文字数（句読点込み）で、
    呼び出し側は読み上げ時間をこの比で句に配る。

    規則:
      - 。！？ では必ず切る（！？ は表示に残す）
      - 1 句が max_chars を超えるときは 、 で切る（貪欲に詰める）
      - 、 が無いのに長いときは長さで等分する（数字・英字・カタカナの途中では切らない）
      - min_chars 未満の句は直前（無ければ直後）とつなぐ（つないで max_chars を
        大きく超える場合はつながない）
    """
    text = (text or "").replace("\n", "").strip()
    if not text:
        return []

    # 1) 文に分ける
    sentences, cur = [], ""
    for i, ch in enumerate(text):
        cur += ch
        if ch in _SENT_END:
            # 「！？」「？！」の連続は同じ文
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt and nxt in _SENT_END:
                continue
            # 閉じ括弧が続くなら括弧まで含める
            sentences.append(cur)
            cur = ""
    if cur.strip():
        sentences.append(cur)

    # 2) 長い文を 、 で詰め直す
    pieces: List[str] = []
    for s in sentences:
        if _visible_len(s) <= max_chars:
            pieces.append(s)
            continue
        clauses, c = [], ""
        for ch in s:
            c += ch
            if ch in _CLAUSE:
                clauses.append(c)
                c = ""
        if c:
            clauses.append(c)
        buf = ""
        for cl in clauses:
            if buf and _visible_len(buf + cl) > max_chars:
                pieces.append(buf)
                buf = cl
            else:
                buf += cl
        if buf:
            pieces.append(buf)

    # 3) まだ長い句は等分
    out: List[str] = []
    for p in pieces:
        if _visible_len(p) <= max_chars:
            out.append(p)
            continue
        n = -(-_visible_len(p) // max_chars)  # ceil
        out.extend(_split_even(p, n))

    # 4) 短すぎる句をつなぐ
    merged: List[str] = []
    for p in out:
        if merged and (_visible_len(p.strip(_TRAIL_STRIP)) < min_chars
                       or _visible_len(merged[-1].strip(_TRAIL_STRIP)) < min_chars) \
                and _visible_len(merged[-1] + p) <= max_chars + 4:
            merged[-1] = merged[-1] + p
        else:
            merged.append(p)

    result = []
    for p in merged:
        disp = p.strip()
        while disp and disp[-1] in _TRAIL_STRIP:
            disp = disp[:-1]
        if not disp:
            continue
        result.append((disp, max(1, len(p))))
    return result


def _is_word_char(ch: str) -> bool:
    return bool(re.match(r"[0-9A-Za-z０-９Ａ-Ｚａ-ｚァ-ヴー・.\-%％]", ch))


def _split_even(s: str, n: int) -> List[str]:
    """s を n 個に長さでほぼ等分する（切れ目の自然さを優先して ±4 字まで動かす）。"""
    if n <= 1:
        return [s]
    res, start = [], 0
    L = len(s)
    for k in range(1, n):
        target = round(L * k / n)
        best, best_score = None, None
        for cand in range(max(start + 2, target - 4), min(L - 1, target + 4) + 1):
            if not _ok_break(s, cand):
                continue
            score = abs(cand - target) * 2 - break_quality(s, cand)
            if best_score is None or score < best_score:
                best, best_score = cand, score
        if best is None:
            best = target
        res.append(s[start:best])
        start = best
    res.append(s[start:])
    return [r for r in res if r]


# ---------------------------------------------------------------------
# 改行（2 行以内・行頭禁則）
# ---------------------------------------------------------------------
_NO_LINE_START = set("、。，．,.！？!?」』）)】〉》ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ…‥・ 　")
_NO_LINE_END = set("「『（(【〈《")


def _ok_break(s: str, i: int) -> bool:
    """s[:i] / s[i:] で改行してよいか。"""
    if i <= 0 or i >= len(s):
        return False
    a, b = s[i - 1], s[i]
    if b in _NO_LINE_START or a in _NO_LINE_END:
        return False
    if _is_word_char(a) and _is_word_char(b):
        return False
    return True


def _cls(ch: str) -> str:
    if re.match(r"[0-9A-Za-z０-９Ａ-Ｚａ-ｚ]", ch):
        return "N"
    if "ぁ" <= ch <= "ゖ":
        return "H"
    if "ァ" <= ch <= "ヺ" or ch == "ー":
        return "T"
    if "一" <= ch <= "鿿" or ch in "々〆ヶ":
        return "K"
    return "P"


# 文節の切れ目になりやすい「後ろに付く」ひらがな（助詞・活用語尾の末尾）
_PARTICLES = ("なら", "たら", "れば", "ても", "では", "には", "とは", "から", "まで", "より", "って", "けど", "ので", "のに", "だけ", "ほど",
              "は", "が", "を", "に", "で", "と", "も", "へ", "の", "や", "ね", "よ")


def break_quality(s: str, i: int) -> int:
    """s[:i] / s[i:] の切れ目の自然さ（大きいほど自然）。おおよそ 0〜10。"""
    if i <= 0 or i >= len(s):
        return -10
    a, b = s[i - 1], s[i]
    ca, cb = _cls(a), _cls(b)
    if a in "、，,":
        return 10
    if a in "！？!?」』）)…‥":
        return 9
    if b in "「『（(":
        return 8
    if ca == "N" and (cb == "N" or b in "%％倍人回年日時分秒個匹体万億兆割度種歳件位号番本枚ヶか頭羽歩段階"):
        return -8  # 数字と単位を割らない（20|回）
    head = s[:i]
    if ca == "H" and any(head.endswith(p) for p in _PARTICLES) and cb in ("K", "T", "N"):
        return 8
    if ca == "H" and cb in ("K", "T", "N"):
        return 6
    if ca == "H" and any(head.endswith(p) for p in _PARTICLES) and cb == "H":
        return 3
    if ca in ("K", "T", "N") and cb == "H":
        return 1   # 漢字→送り仮名（例: 消|えた）は切りたくない
    if ca != cb:
        return 4
    if ca == "K":
        return 0   # 漢字の途中（熟語を割る）
    if ca == "H":
        return -2  # ひらがなの途中（知っ|て）
    return -6      # カタカナ・英数の途中


def wrap_balanced(text: str, size: int, max_w: int, max_lines: int = 2,
                  weight: str = "heavy") -> List[str]:
    """text を max_lines 行以内で、各行が max_w に収まるよう改行する。

    収まらない場合は収まらないまま返す（呼び出し側がサイズを落として再試行する）。
    2 行の場合は「左右の幅差が小さい」かつ「助詞の後ろ」で切れる位置を選ぶ。
    """
    text = text.strip()
    if not text:
        return []
    if text_width(text, size, weight) <= max_w or max_lines <= 1 or len(text) < 2:
        return [text]
    best, best_score = None, None
    for i in range(1, len(text)):
        if not _ok_break(text, i):
            continue
        l, r = text[:i], text[i:]
        wl, wr = text_width(l, size, weight), text_width(r, size, weight)
        over = max(0, wl - max_w) + max(0, wr - max_w)
        # 意味の切れ目を幅の釣り合いより優先する（r2）。r1 は幅差 1 字 = 3 点で、
        # 「えっ、靴がきつ / いのに違うの？」「足が急に太ったか / らではないんです」の
        # ように文節の途中で割れていた（批評: 1 枚だけ見ると意味が取れない）。
        # 幅差 1 字 = 1.2 点、自然さ 1 点 = 2.5 点。2 字以下の行は作らない。
        short_pen = 12 if min(len(l.strip()), len(r.strip())) <= 2 else 0
        score = over * 10 + abs(wl - wr) / max(1, size) * 1.2 - break_quality(text, i) * 2.5 + short_pen
        if best_score is None or score < best_score:
            best, best_score = i, score
    if best is None:
        best = len(text) // 2
    lines = [text[:best], text[best:]]
    if max_lines >= 3 and text_width(lines[1], size, weight) > max_w:
        lines = [lines[0]] + wrap_balanced(lines[1], size, max_w, max_lines - 1, weight)
    return lines


def fit_lines(text: str, max_w: int, size_max: int, size_min: int,
              max_lines: int = 2, step: int = 4, weight: str = "heavy") -> Tuple[List[str], int]:
    """size_max から下げていき、max_lines 行以内・max_w 以内に収まる最大サイズを返す。"""
    # 1 行で収まるなら（多少小さくなっても）1 行を優先する。短い句を 2 行に割ると
    # 「これ知っ / てました？」のような割れ方になる。
    one_line_min = max(size_min, int(size_max * 0.8))
    size = size_max
    while size >= one_line_min:
        if text_width(text, size, weight) <= max_w:
            return [text], size
        size -= step
    # 2 段目: 文節の切れ目（自然さ 3 以上）で割れる最大サイズを探す。大きいサイズで
    # 無理に収めると「体の謎シリーズも毎 / 日投稿中で」のような割れ方になるので、
    # 字を少し小さくしてでも切れ目の良い方を取る。見つからなければ従来どおり。
    size = size_max
    fallback = None
    while size >= size_min:
        lines = wrap_balanced(text, size, max_w, max_lines, weight)
        if len(lines) <= max_lines and all(text_width(l, size, weight) <= max_w for l in lines):
            if len(lines) < 2 or break_quality(text, len(lines[0])) >= 3:
                return lines, size
            if fallback is None:
                fallback = (lines, size)
        size -= step
    if fallback is not None:
        return fallback
    # 最小サイズでも収まらなければ 1 行増やして最小サイズで
    lines = wrap_balanced(text, size_min, max_w, max_lines + 1, weight)
    return lines, size_min


# ---------------------------------------------------------------------
# 強調語
# ---------------------------------------------------------------------
_NUM_RE = re.compile(
    r"(?:SCP-?\d+|[0-9０-９][0-9０-９.,，．]*"
    r"(?:%|％|倍|人|回|年|日|時間|分|秒|個|匹|体|kg|km|cm|mm|m|万|億|兆|割|度|℃|種|歳|件|位|号|番|つ|本|枚|ヶ月|か月|カ月|ターン|頭|羽|歩|段|階|kcal|g)?)"
)
_QUOTE_RE = re.compile(r"[「『]([^」』]{1,12})[」』]")
_KATA_RE = re.compile(r"[ァ-ヴ][ァ-ヴー]{2,}")
_KATA_STOP = {
    "チャンネル", "シリーズ", "コメント", "ショート", "ポイント", "テーマ", "ゲーム",
    "イメージ", "パターン", "タイプ", "レベル", "ケース", "スピード", "パワー",
}


def find_highlights(text: str, extra_terms: Iterable[str] = (), limit: int = 2) -> List[Tuple[int, int]]:
    """強調する区間 [(start, end), ...] を返す（重なりなし・先頭から順）。

    優先順: 数字＋単位 → 「」の中身 → extra_terms（題名の固有名詞など）→ 3字以上のカタカナ語。
    1 句あたり limit 個まで（上位ショートは 1 テロップに 1〜2 語だけ色を変える）。
    """
    spans: List[Tuple[int, int, int]] = []  # (priority, start, end)
    for m in _NUM_RE.finditer(text):
        if any(c.isdigit() for c in m.group(0)):
            spans.append((0, m.start(), m.end()))
    for m in _QUOTE_RE.finditer(text):
        spans.append((1, m.start(1), m.end(1)))
    for term in extra_terms or ():
        term = (term or "").strip()
        if len(term) < 2:
            continue
        start = 0
        while True:
            k = text.find(term, start)
            if k < 0:
                break
            spans.append((2, k, k + len(term)))
            start = k + len(term)
    for m in _KATA_RE.finditer(text):
        if m.group(0) not in _KATA_STOP:
            spans.append((3, m.start(), m.end()))
    spans.sort(key=lambda s: (s[0], s[1]))
    chosen: List[Tuple[int, int]] = []
    for _, a, b in spans:
        if any(not (b <= x or a >= y) for x, y in chosen):
            continue
        chosen.append((a, b))
        if len(chosen) >= limit:
            break
    return sorted(chosen)


def title_terms(title: str) -> List[str]:
    """題名から強調語の候補（SCP番号・カタカナ語・「」の中身）を拾う。"""
    t = title or ""
    terms = [m.group(0) for m in re.finditer(r"SCP-?\d+", t)]
    terms += [m.group(1) for m in _QUOTE_RE.finditer(t)]
    terms += [m.group(0) for m in _KATA_RE.finditer(t) if m.group(0) not in _KATA_STOP]
    # 漢字 2〜4 字の固有名詞らしき語（妖怪名など）は誤爆が多いので拾わない
    seen, out = set(), []
    for x in terms:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------------------------------------------------------------------
# 描画
# ---------------------------------------------------------------------
def draw_line(draw: ImageDraw.ImageDraw, x: int, y: int, line: str, size: int,
              fill, stroke_fill, stroke_width: int,
              spans: Sequence[Tuple[int, int]] = (), hi_fill=None,
              glow_fill=None, glow_extra: int = 0, weight: str = "heavy") -> None:
    """1 行を描く。spans の区間だけ hi_fill で塗る。"""
    f = font(size, weight)
    segs: List[Tuple[str, bool]] = []
    pos = 0
    for a, b in spans:
        if a > pos:
            segs.append((line[pos:a], False))
        segs.append((line[a:b], True))
        pos = b
    if pos < len(line):
        segs.append((line[pos:], False))

    # 1) グロー（色付きの外側縁取り）→ 2) 黒縁 → 3) 文字、を層ごとに全区間へ。
    #    区間ごとに縁→文字を描くと、次の区間の縁が前の文字に被る。
    passes = []
    if glow_fill is not None and glow_extra > 0:
        passes.append(("stroke", glow_fill, stroke_width + glow_extra))
    passes.append(("stroke", stroke_fill, stroke_width))
    passes.append(("fill", None, 0))
    for kind, col, sw in passes:
        cx = x
        for seg, hi in segs:
            if not seg:
                continue
            if kind == "stroke":
                draw.text((cx, y), seg, font=f, fill=col, stroke_width=sw, stroke_fill=col)
            else:
                draw.text((cx, y), seg, font=f, fill=(hi_fill if (hi and hi_fill) else fill))
            cx += int(round(f.getlength(seg)))


def render_telop(width: int, height: int, text: str, *, center_y: int,
                 max_w: int, size_max: int = 104, size_min: int = 72,
                 fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width: int = 10,
                 hi_fill=(255, 220, 40), glow_fill=None, glow_extra: int = 0,
                 extra_terms: Iterable[str] = (), line_gap_ratio: float = 1.22,
                 plate_alpha: int = 0, max_lines: int = 2,
                 weight: str = "heavy") -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    """全画面 RGBA レイヤに句を描いて (layer, bbox) を返す。"""
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text:
        return layer, (0, center_y, 0, center_y)
    lines, size = fit_lines(text, max_w, size_max, size_min, max_lines=max_lines, weight=weight)
    # 強調区間は「句全体」で探してから各行へ割り振る（行をまたぐ語も拾える）
    spans_all = find_highlights(text, extra_terms)
    line_h = int(size * line_gap_ratio)
    total_h = line_h * (len(lines) - 1) + size
    top = int(center_y - total_h / 2)
    draw = ImageDraw.Draw(layer)
    widths = [text_width(l, size, weight) for l in lines]

    if plate_alpha > 0:
        pad_x, pad_y = int(size * 0.35), int(size * 0.28)
        mw = max(widths)
        draw.rounded_rectangle(
            [(width - mw) // 2 - pad_x, top - pad_y, (width + mw) // 2 + pad_x, top + total_h + pad_y],
            radius=int(size * 0.25), fill=(0, 0, 0, plate_alpha))

    offset = 0
    # 実際の行の並びは text を連結したものと一致する（wrap は文字を落とさない）
    y = top
    for line, w in zip(lines, widths):
        a0, a1 = offset, offset + len(line)
        spans = [(max(a, a0) - a0, min(b, a1) - a0) for a, b in spans_all if a < a1 and b > a0]
        x = (width - w) // 2
        # PIL の text は y を ascent 基準で置くので、字面の上端を揃えるため少し上げる
        draw_line(draw, x, y - int(size * 0.08), line, size, fill, stroke_fill, stroke_width,
                  spans=spans, hi_fill=hi_fill, glow_fill=glow_fill, glow_extra=glow_extra,
                  weight=weight)
        y += line_h
        offset = a1
    x0 = (width - max(widths)) // 2 - stroke_width - glow_extra
    x1 = (width + max(widths)) // 2 + stroke_width + glow_extra
    return layer, (x0, top - stroke_width, x1, top + total_h + stroke_width)
