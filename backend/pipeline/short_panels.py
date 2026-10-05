"""ショートの「素材枠」— 文（句）ごとに差し替える題材の画（2026-10-03 visual r2）。

背景:
    r1 の批評（品質バー 8 本と原寸で比較）で一番大きかった差は「題材そのものの画が
    1 枚も出ない」ことだった。バーは毎コマ、物・生き物・証拠・図解のどれかを画面の
    主役に置き、文の切れ目ごとに差し替えている（01: 17 カット・平均 2.8 秒）。

    こちらは画像の入手経路が無い（ChatGPT ブリッジは未納品、OpenAI 画像 API は
    方針で廃止、Pexels はセリフ文で検索するだけで題材と無関係な写真を拾う）。
    そこで、Pillow だけで「その句が言っていること」を描いた図を毎句作る。

    - 句の語（足・靴・薬・名簿・門・骨・素早さ 125 …）から図の種類を選ぶ。
      同じ種類が続くときは寄り（拡大）に切り替えて、必ず画を変える。
    - ジャンルごとの見た目の約束を枠に持たせる:
        science  … 方眼の実験ノート
        scp      … 黄黒の危険テープ枠＋番号と記録名の札（バー 03 の型）
        yokai    … 和紙の原典札＋夜景（朱の落款）
        pokemon  … 対戦画面風（名前札・HP バー・種族値バー）
    - 数字（47人・6時間・20回・攻撃147）は数字そのものを図にする（人型の格子、
      時計、回数の矢印、棒グラフ）。

    公式絵・実在の画像は使わない（権利）。図に出す文字はシナリオ（題名・セリフ・
    thumb_info）にあるものだけで、こちらで事実を足さない。

公開 API:
    PanelContext / make_context(...)
    plan_panels(chunks, line_text, ctx, prev) -> [(kind, variant), ...]
    render_panel(kind, text, ctx, w, h, variant=0) -> RGBA Image
"""

from __future__ import annotations

import math
import os
import random
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    from pipeline import jp_wordmatch as _jw  # type: ignore
except Exception:  # pragma: no cover
    try:
        from . import jp_wordmatch as _jw  # type: ignore
    except Exception:
        import jp_wordmatch as _jw  # type: ignore

try:
    from pipeline import short_telop as _st  # type: ignore
except Exception:  # pragma: no cover
    try:
        from . import short_telop as _st  # type: ignore
    except Exception:
        import short_telop as _st  # type: ignore

SS = 2  # 2 倍で描いて縮小（線のギザギザを消す）

_MINCHO = (
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
)


@lru_cache(maxsize=64)
def _font(size: int, weight: str = "heavy"):
    if weight == "mincho":
        for p in _MINCHO:
            if os.path.exists(p):
                for idx in (1, 0):
                    try:
                        return ImageFont.truetype(p, int(size), index=idx)
                    except Exception:
                        continue
        weight = "heavy"
    return _st.font(int(size), weight)


def _tw(text, size, weight="heavy"):
    try:
        return int(_font(size, weight).getlength(text))
    except Exception:
        return len(text) * size


def _text(d, xy, text, size, fill, weight="heavy", anchor="mm", stroke=0, stroke_fill=(0, 0, 0)):
    d.text(xy, text, font=_font(size, weight), fill=fill, anchor=anchor,
           stroke_width=stroke, stroke_fill=stroke_fill)


def _fit_size(text, max_w, size, min_size=20, weight="heavy"):
    while size > min_size and _tw(text, size, weight) > max_w:
        size -= 2
    return size


# ---------------------------------------------------------------------
# 文脈
# ---------------------------------------------------------------------
@dataclass
class PanelContext:
    genre: str = "science"            # science / scp / yokai / pokemon
    title: str = ""
    subject: str = ""                 # 題材の名前（骨女・SCP-500・マニューラ）
    names: List[str] = field(default_factory=list)   # 対決もの: 2 体の名前
    subtitle: str = ""                # thumb_info.subtitle（記録名・副題）
    label: str = ""                   # 枠の札の文字
    accent: Tuple[int, int, int] = (74, 108, 212)
    title_text: str = ""              # 冒頭の題材図を決めるための題名＋1行目
    shown: List[str] = field(default_factory=list)   # これまでに出した図（締めの振り返り用）
    shown_src: dict = field(default_factory=dict)     # 図 → 最初に描いたときの句（振り返りで同じ絵を出す）
    recap_i: int = 0
    # r3: 同じ図を同じ状態で二度出さないための記録（種類 → 出した状態の集合）
    used: dict = field(default_factory=dict)
    hook_lines: List[str] = field(default_factory=list)   # thumb_info.hook_lines
    hook_caption: str = ""
    state: int = 0                    # 描画中の図の状態（render_panel が入れる）
    pre: bool = False                 # 冒頭の「変化の前」
    script_text: str = ""             # 台本全文（数値の持ち主を探すため）
    line_kinds_all: List[List[str]] = field(default_factory=list)   # 行ごとの語の図（先取り防止）
    line_i: int = 0


_SCP_RE = re.compile(r"SCP-?\s?(\d{2,4})", re.I)
_KATA_RUN = re.compile(r"[ァ-ヴ][ァ-ヴー]{2,}")
_KANJI_RUN = re.compile(r"[一-龥々]{2,4}")
_KATA_STOP = {"シリーズ", "チャンネル", "ゲーム", "アニメ", "ランキング", "ポケモン", "タイプ",
              "ターン", "バトル", "パーティ", "ガチ", "マジ", "データ", "ニュース", "ショート"}
_KANJI_STOP = {"正体", "真相", "理由", "原典", "伝承", "元ネタ", "記録", "同じ", "毎晩", "本当",
               "実は", "最強", "最弱", "意外", "秘密", "治療", "服用者", "患者", "夕方", "足首",
               "水分", "妖怪", "日本", "世界", "全員", "可能", "時間"}


def detect_genre(channel_id: str = "", title: str = "", card_style: str = "") -> str:
    cid = (channel_id or "").lower()
    if "scp" in cid or _SCP_RE.search(title or "") or card_style == "leaked-document":
        return "scp"
    if "pokemon" in cid or "poke" in cid:
        return "pokemon"
    if "yokai" in cid:
        return "yokai"
    return "science"


def _subject_from(title: str, lines: Sequence[str], genre: str) -> Tuple[str, List[str]]:
    t = title or ""
    body = " ".join(lines or [])
    if genre == "scp":
        m = _SCP_RE.search(t) or _SCP_RE.search(body)
        return ((f"SCP-{m.group(1)}" if m else "SCP"), [])
    katas = [k for k in _KATA_RUN.findall(t) if k not in _KATA_STOP]
    if genre == "pokemon":
        names = []
        for k in katas + [k for k in _KATA_RUN.findall(body) if k not in _KATA_STOP]:
            if k not in names:
                names.append(k)
        names = names[:2]
        return (names[0] if names else "", names)
    # yokai / science: 題名にあってセリフで最も多く繰り返される語
    cands = []
    for run in re.findall(r"[一-龥々ァ-ヴー]+", t):
        if 2 <= len(run) <= 5 and run not in _KANJI_STOP and run not in _KATA_STOP:
            cands.append(run)
    best, best_n = "", 0
    for c in cands:
        n = body.count(c)
        if n > best_n:
            best, best_n = c, n
    if not best and katas:
        best = katas[0]
    return best, []


def make_context(*, channel_id: str = "", title: str = "", lines: Sequence[str] = (),
                 card_style: str = "", subtitle: str = "", accent=None,
                 label: str = "", hook_lines: Sequence[str] = (), hook_caption: str = ""
                 ) -> PanelContext:
    genre = detect_genre(channel_id, title, card_style)
    subject, names = _subject_from(title, lines, genre)
    acc = tuple(int(c) for c in (accent or (74, 108, 212))[:3])
    if genre == "scp":
        lab = subject or "SCP"
    elif genre == "yokai":
        lab = subject or "原典"
    elif genre == "pokemon":
        lab = " × ".join(names) if len(names) == 2 else (subject or "")
    else:
        lab = label or ""
    ctx = PanelContext(genre=genre, title=title or "", subject=subject, names=names,
                       subtitle=(subtitle or "").strip(), label=lab, accent=acc,
                       title_text=(title or "") + " " + (lines[0] if lines else ""),
                       hook_lines=[str(h) for h in (hook_lines or []) if h],
                       hook_caption=str(hook_caption or ""))
    ctx.script_text = " ".join(lines or [])
    ctx.line_kinds_all = [[] if is_cta(ln) else _kinds_for(ln, genre) for ln in (lines or [])]
    return ctx


# ---------------------------------------------------------------------
# 種類の選び方
# ---------------------------------------------------------------------
_STAT_RE = re.compile(r"(素早さ|すばやさ|攻撃|こうげき|防御|特攻|特防|HP|種族値)\s*(\d{2,3})")
_NUM_RE = re.compile(r"(?<![A-Za-z\-ー])(\d{1,4}(?:\.\d+)?)\s*(人|回|時間|秒|分|日|年|倍|%|％|kg|cm|ターン|体|件|名)?")

_KINDS = {
    "science": [
        ("hose", ("ホース", "水道")),
        ("foot", ("靴", "足首", "むくみ", "足", "ふくらはぎ", "脚", "くつ")),
        ("water", ("水分", "水", "体液", "血液", "下がり", "下が", "たまる", "溜ま", "集まる")),
        ("pump", ("動かす", "動かし", "筋肉", "ポンプ", "戻す", "戻る", "ストレッチ")),
        ("clock", ("夕方", "時間", "朝", "夜", "一日", "毎日")),
    ],
    "scp": [
        ("note", ("処方箋", "一言", "言葉", "メッセージ", "手紙", "遺言", "メモ")),
        ("pill", ("万能薬", "薬", "錠剤", "服用", "処方", "治療", "投与", "カプセル", "飲んだ")),
        ("ward", ("翌朝", "病棟", "病室", "ベッド", "回復", "助か", "入院")),
        ("classroom", ("一クラス", "クラス", "教室", "出席")),
        ("roster", ("名簿", "出席簿", "リスト", "記録", "報告", "患者", "被験者", "職員", "カルテ")),
        ("expunged", ("空白", "消え", "消さ", "消える", "抹消", "不明", "削除", "正体", "改竄")),
        ("door", ("収容", "扉", "部屋", "施設", "収容室", "窓")),
        ("eye", ("視線", "見る", "見た", "目撃", "瞬き")),
    ],
    "yokai": [
        ("lovers", ("恋人", "夫", "妻", "会い", "想い")),
        ("gate", ("門", "戸", "家", "扉", "玄関")),
        ("knock", ("叩", "ノック", "コンコン")),
        ("shoji", ("外から", "家の外", "逃げ場", "障子", "通知", "部屋の中", "閉じこも")),
        ("pull", ("引かれ", "引き込", "連れて", "連れ去", "引きず", "引か")),
        ("skull", ("骨", "死者", "亡者", "骸", "遺体", "死", "幽霊")),
        ("moon", ("夜", "夜ごと", "毎晩", "月", "闇", "真夜中")),
        ("lantern", ("提灯", "灯り", "祭り", "祭", "盆")),
        ("contrast", ("ゲーム", "アニメ", "切ない", "かわいい", "可愛い")),
        ("scroll", ("伝承", "原典", "元ネタ", "昔", "江戸", "絵巻", "書物", "言い伝え")),
    ],
    "pokemon": [
        ("stat", ("素早さ", "すばやさ", "攻撃", "こうげき", "防御", "特攻", "特防", "種族値", "HP")),
        ("flip", ("逆に", "逆転", "読まれ", "裏をかく", "立場")),
        ("priority", ("先制技", "先制", "先に動", "ターン", "速い", "速さ", "先に")),
        ("wall", ("壁", "止める", "耐え", "受け", "防ぐ")),
        ("versus", ("対", "勝", "負け", "勝敗", "バトル")),
    ],
}

_FALLBACK = {"science": "subject", "scp": "dossier", "yokai": "scroll", "pokemon": "versus"}

# 図ごとの「別の状態」の数（中身の描き分け）と、寄り先（中身の箱に対する中心 x, y と倍率）。
# 同じ種類を二度目に出すときは、まだ出していない状態か寄り先を使う。寄りには丸印を付ける。
# r2 の批評: 4 本とも 3〜4 種の図を約 30 秒で使い回し、12 コマ中 4 回同じ図が出ていた。
_NSEM = {"foot": 2, "clock": 2, "roster": 2, "priority": 2, "number": 1}
_FOCUS = {
    "foot": [(0.36, 0.66, 1.9)],
    "water": [(0.36, 0.78, 1.9)],
    "hose": [(0.5, 0.78, 1.8)],
    "pump": [(0.3, 0.36, 1.8)],
    "pill": [(0.72, 0.6, 1.7)],
    "note": [(0.5, 0.66, 1.9)],
    "roster": [(0.5, 0.5, 1.6)],
    "ward": [(0.5, 0.62, 1.7)],
    "classroom": [(0.5, 0.6, 1.7)],
    "gate": [(0.24, 0.3, 2.2), (0.68, 0.55, 1.6)],
    "skull": [(0.5, 0.18, 2.4)],
    "moon": [(0.5, 0.75, 1.8)],
    "lovers": [(0.82, 0.45, 1.9)],
    "versus": [(0.22, 0.66, 1.9), (0.78, 0.26, 1.9)],
    "priority": [(0.75, 0.36, 1.7)],
    "number": [(0.62, 0.5, 1.7)],
}

_DENY_RE = re.compile(r"(.{2,14}?)(?:とは限らない|わけではな|ではない|ではなく|じゃない|じゃなく)")
_DENY_TRIM = re.compile(r"^(?:実は|でも|しかも|ただし|それは|これは|つまり|、|。|…)+")


def deny_label(text: str) -> str:
    """「Aではない／Aとは限らない」の A（画で ✕ を付ける誤解）。無ければ空。"""
    m = _DENY_RE.search(text or "")
    if not m:
        return ""
    lab = m.group(1)
    lab = lab.split("、")[-1].split("。")[-1]
    lab = _DENY_TRIM.sub("", lab)
    lab = re.sub(r"(から|ので|って|のが|のは|は|が|を|に|で)$", "", lab)
    return lab if len(lab) >= 2 else ""


def _number_in(text: str):
    for m in _NUM_RE.finditer(text or ""):
        val, unit = m.group(1), m.group(2) or ""
        # SCP 番号・素早さ等のステータス値はそれぞれの図で扱う
        pre = (text or "")[max(0, m.start() - 4):m.start()]
        if "SCP" in pre.upper():
            continue
        if unit or len(val) >= 2:
            return val, unit
    return None


def _kinds_for(text: str, genre: str) -> List[str]:
    t = text or ""
    found = []
    for kind, keys in _KINDS.get(genre, []):
        if _jw.any_word(t, keys) or any(len(k) >= 2 and k in t for k in keys):
            pos = min([t.find(k) for k in keys if k in t] or [len(t)])
            found.append((pos, kind))
    num = _number_in(t)
    if num:
        val, unit = num
        if genre == "pokemon" and (any(k[1] == "stat" for k in found) or unit in ("ターン", "分")):
            pass
        elif unit:
            found.append((t.find(val), "number"))
    found.sort()
    kinds = [k for _, k in found]
    # 「攻撃147を止める壁」は壁の図（攻撃の数値も入る）を優先。種族値の棒は直前に出ている。
    if genre == "pokemon" and "wall" in kinds and "stat" in kinds:
        kinds.remove("wall")
        kinds.insert(0, "wall")
    # 誤解の否定（「〜ではない」）は、その誤解に ✕ を付けた図を最優先
    if deny_label(t):
        kinds.insert(0, "deny")
    return kinds


_CTA_WORDS = ("高評価", "チャンネル登録", "毎日投稿", "シリーズ", "フォロー", "登録", "1万人", "応援")


def is_cta(text: str) -> bool:
    return any(w in (text or "") for w in _CTA_WORDS)


def subject_kind(ctx: PanelContext) -> str:
    """題材そのものを見せる図（冒頭と、締めの登録のお願いの区間で使う）。"""
    if ctx.genre == "pokemon" and len(ctx.names) == 2:
        return "versus"
    found = set(_kinds_for(ctx.title, ctx.genre)) or set(_kinds_for(ctx.title_text, ctx.genre))
    for kind, _ in _KINDS.get(ctx.genre, []):   # 表の順＝題材らしさの優先順
        if kind in found:
            return kind
    return _FALLBACK[ctx.genre]


def max_states(kind: str) -> int:
    return _NSEM.get(kind, 1) + len(_FOCUS.get(kind, []))


def use_key(kind: str, text: str) -> str:
    """出した記録のキー。数字・否定・種族値は中身（値・語）ごとに別の絵として数える。"""
    if kind == "number":
        n = _number_in(text)
        return f"number:{n[0]}{n[1]}" if n else "number"
    if kind == "deny":
        return "deny:" + deny_label(text)
    if kind == "stat":
        return "stat:" + ",".join(m.group(0) for m in _STAT_RE.finditer(text or ""))
    return kind


def _free_state(ctx: PanelContext, kind: str, text: str):
    used = ctx.used.get(use_key(kind, text), set())
    for v in range(max_states(kind)):
        if v not in used:
            return v
    return None


def _mark(ctx: PanelContext, kind: str, text: str, v: int) -> None:
    ctx.used.setdefault(use_key(kind, text), set()).add(v)


def plan_panels(chunks: Sequence[str], line_text: str, ctx: PanelContext,
                prev: Optional[Tuple[str, int]] = None, opening: bool = False
                ) -> List[Tuple[str, int]]:
    """句ごとの (種類, 状態) を返す（r3）。

    約束:
      1. 同じ (図, 状態) は二度出さない。句の語に合う図がすでに出ていれば、その図の
         まだ出していない状態（描き分け／寄り先＋丸印）を使う。
      2. 句の語に合う図が使い切りなら、まだ出していない別の図（題材→行→ジャンル全体の順）。
         後ろの句が自分の語で使う図は先取りしない。
      3. 直前の句と同じ種類は、語がそれを指すときだけ（状態は必ず変わる）。
      4. 登録・高評価のお願いの句は ("loop", 0)。描画側で冒頭の 1 コマ（題名の問い＋題材の図）に
         戻す。最後の画が最初の画と同じなので、ループで先頭に戻っても継ぎ目に見えない。
    """
    out: List[Tuple[str, int]] = []
    subj = subject_kind(ctx)
    pool = [k for k, _ in _KINDS.get(ctx.genre, [])] + [_FALLBACK[ctx.genre]]
    line_kinds = _kinds_for(line_text, ctx.genre)
    owns = [_kinds_for(ch, ctx.genre) for ch in chunks]
    for i, ch in enumerate(chunks):
        if (is_cta(ch) or (is_cta(line_text) and not owns[i])) and not (opening and i == 0):
            out.append(("loop", 0))
            continue
        last = out[-1] if out else prev
        later = {k for o in owns[i + 1:] for k in o}
        pick = None
        if opening and i == 0:
            pick = (subj, 0)
        else:
            own = owns[i]
            # (a) 句の語に合う図で、まだ一度も出していないもの
            for k in own:
                if use_key(k, ch) not in ctx.used and (last is None or k != last[0] or k in ("number", "stat", "deny")):
                    pick = (k, 0)
                    break
            # (b) 句の語に合う図の、まだ出していない状態
            if pick is None:
                for k in own:
                    v = _free_state(ctx, k, ch)
                    if v is not None:
                        pick = (k, v)
                        break
            # (c) 語に無くても、まだ出していない図。後ろの句・後ろの行が自分の語で使う図は
            #     先取りしない（その行で初めて出す方が、語と画が揃う）。
            if pick is None:
                future = {k for ks in ctx.line_kinds_all[ctx.line_i + 1:] for k in ks}
                skip = set(own) | later | {"number", "deny", "stat"}
                if last:
                    skip.add(last[0])
                near = [k for k in dict.fromkeys([subj] + line_kinds) if k not in skip]
                far = [k for k in dict.fromkeys(pool) if k not in skip and k not in near]
                # 題材・この行の図（未使用→別の状態）→ ジャンルの他の図（未使用→別の状態）
                for group in (near, far):
                    for k in group:
                        if k not in ctx.used and k not in future:
                            pick = (k, 0)
                            break
                    if pick is None:
                        for k in group:
                            if k in ctx.used:
                                v = _free_state(ctx, k, ch)
                                if v is not None:
                                    pick = (k, v)
                                    break
                    if pick is not None:
                        break
                if pick is None:
                    for k in near + far:
                        if k not in ctx.used:
                            pick = (k, 0)
                            break
            if pick is None:
                k = (own or [subj])[0]
                n = max(1, max_states(k))
                v = ((last[1] + 1) if last and last[0] == k else 0) % n
                pick = (k, v)
        _mark(ctx, pick[0], ch if not (opening and i == 0) else ctx.title_text, pick[1])
        out.append(pick)
        if pick[0] not in ctx.shown and pick[0] not in ("number", "deny", "loop"):
            ctx.shown.append(pick[0])
    ctx.line_i += 1
    return out


# ---------------------------------------------------------------------
# 枠（ジャンルの見た目の約束）
# ---------------------------------------------------------------------
def _stripes(d, box, a=(250, 205, 30), b=(20, 20, 20), step=36):
    x0, y0, x1, y1 = box
    h = y1 - y0
    d.rectangle(box, fill=b)
    x = x0 - h
    while x < x1:
        d.polygon([(x, y1), (x + h, y0), (x + h + step, y0), (x + step, y1)], fill=a)
        x += step * 2


def _paper_noise(img, box, seed=1, strength=10):
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = box
    for _ in range(int((x1 - x0) * (y1 - y0) / 2600)):
        x = rnd.randint(x0, x1)
        y = rnd.randint(y0, y1)
        ln = rnd.randint(6, 30) * SS
        a = rnd.randint(4, strength)
        ang = rnd.random() * math.pi
        d.line([(x, y), (x + ln * math.cos(ang), y + ln * math.sin(ang))], fill=(90, 60, 30, a), width=SS)


def _frame(ctx: PanelContext, W: int, H: int, night: bool = False):
    """枠と地を描き、(img, draw, 中身の箱) を返す。座標は SS 倍。"""
    g = ctx.genre
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    r = 30 * SS
    if g == "scp":
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=14 * SS, fill=(26, 25, 24, 255))
        t = 30 * SS
        _stripes(d, (0, 0, W, t))
        _stripes(d, (0, H - 62 * SS, W, H))
        # 札: 番号 ｜ 記録名（バー 03 の「黄黒テープ枠の分類」）
        plate = ctx.subject + (f"  ｜  {ctx.subtitle}" if ctx.subtitle else "")
        size = _fit_size(plate, W - 120 * SS, 40 * SS, 22 * SS)
        pw = _tw(plate, size) + 48 * SS
        cy = H - 31 * SS
        d.rectangle([(W - pw) // 2, cy - 25 * SS, (W + pw) // 2, cy + 25 * SS], fill=(12, 12, 12, 255))
        _text(d, (W // 2, cy), plate, size, (255, 255, 255))
        box = (24 * SS, t + 18 * SS, W - 24 * SS, H - 62 * SS - 18 * SS)
        return img, d, box
    if g == "yokai":
        base = (24, 26, 52) if night else (236, 226, 204)
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=10 * SS, fill=(*base, 255))
        if not night:
            _paper_noise(img, (0, 0, W, H), seed=W + H)
        else:
            # 夜: 上から下へ藍→黒のグラデーション
            for y in range(0, H, 4):
                k = y / H
                col = (int(30 - 18 * k), int(34 - 22 * k), int(70 - 44 * k), 255)
                d.rectangle([0, y, W, y + 4], fill=col)
        edge = (110, 30, 30) if not night else (190, 160, 110)
        d.rounded_rectangle([6 * SS, 6 * SS, W - 6 * SS, H - 6 * SS], radius=8 * SS,
                            outline=(*edge, 255), width=4 * SS)
        d.rounded_rectangle([16 * SS, 16 * SS, W - 16 * SS, H - 16 * SS], radius=6 * SS,
                            outline=(*edge, 140), width=2 * SS)
        # 札: 原典 ｜ 骨女（明朝）
        if ctx.subject:
            lab = f"伝承  {ctx.subject}"
            size = 34 * SS
            pw = _tw(lab, size, "mincho") + 40 * SS
            d.rectangle([28 * SS, H - 74 * SS, 28 * SS + pw, H - 26 * SS], fill=(150, 24, 24, 235))
            _text(d, (28 * SS + pw // 2, H - 50 * SS), lab, size, (255, 244, 225), "mincho")
        box = (30 * SS, 30 * SS, W - 30 * SS, H - 84 * SS)
        return img, d, box
    if g == "pokemon":
        for y in range(0, H, 4):
            k = y / H
            col = (int(250 - 30 * k), int(252 - 18 * k), 255, 255)
            d.rectangle([0, y, W, y + 4], fill=col)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=r, fill=255)
        img.putalpha(mask)
        d = ImageDraw.Draw(img, "RGBA")
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=r, outline=(22, 34, 84, 255), width=8 * SS)
        if ctx.label:
            size = _fit_size(ctx.label, W - 160 * SS, 38 * SS, 22 * SS)
            pw = _tw(ctx.label, size) + 56 * SS
            d.rounded_rectangle([(W - pw) // 2, H - 66 * SS, (W + pw) // 2, H - 18 * SS],
                                radius=24 * SS, fill=(22, 34, 84, 255))
            _text(d, (W // 2, H - 42 * SS), ctx.label, size, (255, 222, 60))
        box = (30 * SS, 26 * SS, W - 30 * SS, H - 80 * SS)
        return img, d, box
    # science: 方眼の実験ノート
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=r, fill=(252, 252, 248, 255))
    step = 40 * SS
    for x in range(step, W, step):
        d.line([(x, 0), (x, H)], fill=(205, 222, 242, 255), width=SS)
    for y in range(step, H, step):
        d.line([(0, y), (W, y)], fill=(205, 222, 242, 255), width=SS)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=r, fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=r, outline=(*ctx.accent, 255), width=8 * SS)
    box = (30 * SS, 30 * SS, W - 30 * SS, H - 30 * SS)
    return img, d, box


# ---------------------------------------------------------------------
# 部品
# ---------------------------------------------------------------------
def _chip(d, cx, cy, text, size, bg, fg=(255, 255, 255), weight="heavy"):
    w = _tw(text, size, weight) + size
    h = int(size * 1.5)
    d.rounded_rectangle([cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2], radius=h // 2, fill=bg)
    _text(d, (cx, cy), text, size, fg, weight)


def _arrow(d, p0, p1, col, w, head):
    d.line([p0, p1], fill=col, width=w)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    a1 = ang + math.radians(150)
    a2 = ang - math.radians(150)
    d.polygon([p1, (p1[0] + head * math.cos(a1), p1[1] + head * math.sin(a1)),
               (p1[0] + head * math.cos(a2), p1[1] + head * math.sin(a2))], fill=col)


def _person(d, cx, cy, s, fill):
    d.ellipse([cx - s * 0.28, cy - s * 0.62, cx + s * 0.28, cy - s * 0.06], fill=fill)
    d.rounded_rectangle([cx - s * 0.42, cy, cx + s * 0.42, cy + s * 0.7], radius=int(s * 0.3), fill=fill)


def _human(d, cx, foot_y, h, fill):
    """立っている人の影（頭・肩・胴・脚）。"""
    hr = h * 0.075
    hy = foot_y - h + hr
    d.ellipse([cx - hr, hy - hr, cx + hr, hy + hr], fill=fill)
    d.rounded_rectangle([cx - h * 0.13, hy + hr * 1.3, cx + h * 0.13, foot_y - h * 0.42],
                        radius=int(h * 0.06), fill=fill)
    d.rectangle([cx - h * 0.1, foot_y - h * 0.46, cx - h * 0.02, foot_y], fill=fill)
    d.rectangle([cx + h * 0.02, foot_y - h * 0.46, cx + h * 0.1, foot_y], fill=fill)


def _num_unit(text):
    n = _number_in(text)
    return n if n else (None, "")


# ---------------------------------------------------------------------
# science
# ---------------------------------------------------------------------
SKIN = (246, 205, 172)
SKIN_D = (214, 160, 124)


def _leg(d, x, y_top, y_floor, s, swollen=False):
    """横から見た下腿と足（つま先は右）。x=すねの前側, y_floor=床。戻り値: 足首の座標。"""
    leg_w = s * 0.42
    ankle_y = y_floor - s * 0.42
    L = y_floor - y_top
    # すね（前側はほぼまっすぐ）とふくらはぎ（後ろ側がふくらむ）
    back = []
    for k in range(13):
        t = k / 12
        y = y_top + (ankle_y - y_top) * t
        bulge = math.sin(math.pi * min(1.0, t * 1.35)) * s * 0.16 if t < 0.74 else 0
        back.append((x - leg_w * (1.0 - 0.28 * t) - bulge, y))
    poly = [(x, y_top)] + [(x - s * 0.02, ankle_y)] + [(x + s * 0.95, y_floor - s * 0.18),
            (x + s * 0.98, y_floor), (x - leg_w * 0.95, y_floor), (x - leg_w * 0.98, ankle_y + s * 0.05)] \
        + list(reversed(back))
    d.polygon(poly, fill=SKIN, outline=SKIN_D)
    d.line(poly + [poly[0]], fill=SKIN_D, width=3 * SS, joint="curve")
    if swollen:
        cx, cy = x - leg_w * 0.42, ankle_y + s * 0.02
        rr = s * 0.34
        d.ellipse([cx - rr, cy - rr * 0.8, cx + rr, cy + rr * 0.8], fill=(250, 178, 170),
                  outline=(225, 110, 100), width=4 * SS)
    return (x - leg_w * 0.45, ankle_y)


def _shoe(d, x, y_floor, s, leg_w, tight=False):
    col = (44, 72, 150)
    top = y_floor - s * 0.36
    d.rounded_rectangle([x - leg_w - s * 0.12, top, x + s * 1.05, y_floor + s * 0.06],
                        radius=int(s * 0.18), fill=col, outline=(20, 34, 80), width=4 * SS)
    d.rectangle([x - leg_w - s * 0.14, y_floor - s * 0.02, x + s * 1.07, y_floor + s * 0.1], fill=(240, 240, 240),
                outline=(150, 150, 150), width=3 * SS)
    for k in range(3):
        lx = x + s * (0.1 + 0.22 * k)
        d.line([(lx, top + s * 0.06), (lx + s * 0.12, top + s * 0.18)], fill=(255, 255, 255), width=5 * SS)
    if tight:
        for k, (dx, dy) in enumerate(((-1, -1), (1, -1), (-1.2, 0.2))):
            px = x - leg_w * 0.5 + dx * s * 0.55
            py = top - s * 0.1 + dy * s * 0.35
            _arrow(d, (x - leg_w * 0.5 + dx * s * 0.28, top - s * 0.05 + dy * s * 0.15), (px, py),
                   (225, 60, 60), 7 * SS, 22 * SS)


def _sci_foot(d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    if ctx.state == 1:
        return _sci_foot_compare(d, box, ctx, text, opening)
    s = min(W * 0.36, H * 0.5)
    floor = y1 - H * 0.14
    x = x0 + W * 0.42
    swollen = any(k in (text + ctx.title_text) for k in ("きつ", "むくみ", "パンパン", "太", "集ま", "下が"))
    if ctx.pre:
        swollen = False
    ankle = _leg(d, x, y0 + H * 0.04, floor, s, swollen=swollen)
    _shoe(d, x, floor, s, s * 0.42, tight=swollen)
    d.line([(x0, floor + s * 0.1), (x1, floor + s * 0.1)], fill=(150, 160, 180), width=4 * SS)
    if ctx.pre:
        return
    lab = "足首" if "足首" in text or not ("靴" in text) else "靴"
    lab = "パンパン" if ("きつ" in text and opening) else lab
    _chip(d, int(x + s * 1.02), int(ankle[1] - s * 0.45), lab, int(58 * SS), (225, 60, 60))
    if any(k in (text + ctx.title_text) for k in ("夕方",)):
        _mini_sun(d, x1 - W * 0.16, y0 + H * 0.14, H * 0.07)


def _sci_foot_compare(d, box, ctx, text, opening):
    """同じ足の 2 時点: 左=朝（靴にすき間）/ 右=夕方（むくんで靴がきつい）。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    s = min(W * 0.2, H * 0.36)
    floor = y1 - H * 0.16
    d.line([(x0 + W * 0.5, y0 + H * 0.06), (x0 + W * 0.5, y1 - H * 0.04)], fill=(170, 180, 200), width=4 * SS)
    for k, (lab, sw, col) in enumerate((("朝", False, (60, 120, 220)), ("夕方", True, (225, 60, 60)))):
        x = x0 + W * (0.2 + 0.5 * k)
        _leg(d, x, y0 + H * 0.24, floor, s, swollen=sw)
        _shoe(d, x, floor, s, s * 0.42, tight=sw)
        _chip(d, int(x0 + W * (0.25 + 0.5 * k)), int(y0 + H * 0.1), lab, int(60 * SS), col)
    _text(d, (int(x0 + W * 0.75), int(y1 - H * 0.05)), "きつい", int(56 * SS), (225, 60, 60))
    _text(d, (int(x0 + W * 0.25), int(y1 - H * 0.05)), "すき間", int(56 * SS), (60, 120, 220))


def _mini_sun(d, cx, cy, r):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 150, 40))
    for k in range(8):
        a = k * math.pi / 4
        d.line([(cx + r * 1.3 * math.cos(a), cy + r * 1.3 * math.sin(a)),
                (cx + r * 1.7 * math.cos(a), cy + r * 1.7 * math.sin(a))], fill=(255, 150, 40), width=5 * SS)


def _drop(d, cx, cy, r, col=(60, 150, 235)):
    d.polygon([(cx, cy - r * 1.6), (cx - r * 0.9, cy - r * 0.2), (cx + r * 0.9, cy - r * 0.2)], fill=col)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    d.ellipse([cx - r * 0.45, cy - r * 0.5, cx - r * 0.1, cy - r * 0.15], fill=(220, 240, 255))


def _sci_water(d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    s = min(W * 0.34, H * 0.6)
    floor = y1 - H * 0.08
    x = x0 + W * 0.40
    ankle = _leg(d, x, y0 + H * 0.02, floor, s, swollen=True)
    lw = s * 0.42
    rnd = random.Random(3)
    for k in range(9):
        cy = y0 + H * 0.12 + k * (ankle[1] - y0 - H * 0.12) / 9
        _drop(d, x - lw * 0.5 + rnd.uniform(-lw * 0.2, lw * 0.2), cy, s * (0.035 + 0.006 * k))
    for k in range(5):
        _drop(d, ankle[0] + (k - 2) * s * 0.12, ankle[1] + s * 0.02, s * 0.06)
    ax = x0 + W * 0.78
    _arrow(d, (ax, y0 + H * 0.08), (ax, y1 - H * 0.2), (60, 150, 235), 18 * SS, 50 * SS)
    _chip(d, int(ax), int(y0 + H * 0.5), "水分", int(44 * SS), (40, 120, 220))
    _text(d, (int(ax), int(y1 - H * 0.08)), "重力", int(38 * SS), (60, 70, 90))


def _sci_hose(d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    pts = []
    for k in range(41):
        t = k / 40
        px = x0 + W * (0.08 + 0.84 * t)
        py = y0 + H * 0.18 + (H * 0.62) * math.sin(math.pi * t) ** 1.3
        pts.append((px, py))
    d.line(pts, fill=(70, 160, 90), width=int(54 * SS), joint="curve")
    d.line(pts, fill=(120, 200, 130), width=int(30 * SS), joint="curve")
    lo = pts[20]
    for k in range(-6, 7):
        p = pts[20 + k]
        _drop(d, p[0], p[1] + 2 * SS, 12 * SS)
    _chip(d, int(lo[0]), int(lo[1] - H * 0.2), "低い所にたまる", int(42 * SS), (40, 120, 220))
    _text(d, (int(x0 + W * 0.12), int(y0 + H * 0.08)), "高", int(48 * SS), (90, 100, 120))
    _text(d, (int(x0 + W * 0.5), int(y1 - H * 0.04)), "低", int(48 * SS), (90, 100, 120))


def _sci_pump(d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    s = min(W * 0.34, H * 0.6)
    floor = y1 - H * 0.08
    x = x0 + W * 0.36
    _leg(d, x, y0 + H * 0.02, floor, s)
    lw = s * 0.42
    # ふくらはぎの筋肉
    d.ellipse([x - lw * 1.15, y0 + H * 0.12, x - lw * 0.15, y0 + H * 0.5], fill=(230, 110, 100),
              outline=(190, 70, 60), width=4 * SS)
    for k in range(3):
        ay = y0 + H * (0.62 - 0.18 * k)
        _arrow(d, (x - lw * 0.5 - 30 * SS * (k - 1), ay + 40 * SS), (x - lw * 0.5 - 30 * SS * (k - 1), ay - 30 * SS),
               (40, 120, 220), 10 * SS, 26 * SS)
    val, unit = _num_unit(text)
    lab = f"{val}{unit}" if val else "ポンプ"
    cx, cy = x0 + W * 0.76, y0 + H * 0.42
    rr = H * 0.22
    d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 200, 520, fill=(40, 120, 220), width=12 * SS)
    _arrow(d, (cx + rr * math.cos(math.radians(150)), cy + rr * math.sin(math.radians(150))),
           (cx + rr * math.cos(math.radians(170)), cy + rr * math.sin(math.radians(170))),
           (40, 120, 220), 12 * SS, 34 * SS)
    _text(d, (int(cx), int(cy)), lab, _fit_size(lab, rr * 1.7, int(72 * SS)), (225, 60, 60))
    _chip(d, int(cx), int(cy + rr + 50 * SS), "足首を動かす", int(38 * SS), (40, 120, 220))


def _sci_clock(d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    if ctx.state == 1:
        return _sci_timeline(d, box, ctx, text, opening)
    cx, cy = x0 + W * 0.32, y0 + H * 0.5
    r = min(W * 0.26, H * 0.44)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255), outline=(50, 60, 90), width=10 * SS)
    for k in range(12):
        a = k * math.pi / 6
        d.line([(cx + r * 0.82 * math.sin(a), cy - r * 0.82 * math.cos(a)),
                (cx + r * 0.93 * math.sin(a), cy - r * 0.93 * math.cos(a))], fill=(50, 60, 90), width=6 * SS)
    # 夕方 6 時
    d.line([(cx, cy), (cx, cy + r * 0.5)], fill=(50, 60, 90), width=12 * SS)
    d.line([(cx, cy), (cx, cy - r * 0.72)], fill=(50, 60, 90), width=8 * SS)
    d.ellipse([cx - 12 * SS, cy - 12 * SS, cx + 12 * SS, cy + 12 * SS], fill=(225, 60, 60))
    # 右: 夕日
    hx, hy = x0 + W * 0.76, y0 + H * 0.62
    rr = H * 0.18
    d.pieslice([hx - rr, hy - rr, hx + rr, hy + rr], 180, 360, fill=(255, 140, 40))
    d.line([(hx - rr * 1.6, hy), (hx + rr * 1.6, hy)], fill=(120, 90, 70), width=6 * SS)
    val, unit = _num_unit(text)
    lab = f"{val}{unit}" if (val and unit in ("時間", "分", "秒", "日")) else ("夕方" if "夕方" in (text + ctx.title_text) else "時間")
    _text(d, (int(hx), int(y0 + H * 0.24)), lab, _fit_size(lab, W * 0.4, int(96 * SS)), (225, 60, 60),
          stroke=6 * SS, stroke_fill=(255, 255, 255))


def _sci_timeline(d, box, ctx, text, opening):
    """時間を追った経過: 朝→昼→夕方で、足首にたまる水が増えていく（量は模式）。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    labs = ("朝", "昼", "夕方")
    _arrow(d, (x0 + W * 0.06, y1 - H * 0.08), (x1 - W * 0.04, y1 - H * 0.08), (60, 70, 100), 10 * SS, 40 * SS)
    for k, lab in enumerate(labs):
        cx = x0 + W * (0.2 + 0.31 * k)
        s = min(W * 0.15, H * 0.3)
        floor = y1 - H * 0.2
        _leg(d, cx, y0 + H * 0.22, floor, s, swollen=(k == 2))
        # 足首の水（たまり具合を 3 段階で）
        for j in range(2 + 3 * k):
            _drop(d, cx - s * 0.2 + (j % 3 - 1) * s * 0.16, floor - s * 0.3 - (j // 3) * s * 0.2, s * 0.06)
        _chip(d, int(cx), int(y0 + H * 0.12), lab, int(54 * SS), (225, 60, 60) if k == 2 else (60, 120, 220))
    _text(d, (int(x0 + W * 0.5), int(y1 - H * 0.03)), "時間がたつほど下へ", int(42 * SS), (60, 70, 100))


def _sci_subject(d, box, ctx, text, opening):
    """理科の汎用: 語に合うアイコン（既存の教科書アイコン）＋大きな「？」。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    try:
        from pipeline import pillow_illustration as _pi  # type: ignore
    except Exception:  # pragma: no cover
        _pi = None
    found = _pi._match_textbook(text or ctx.title_text) if _pi else []
    if found:
        icon, lab = found[0]
        _pi._TEXTBOOK_ICONS[icon](d, int(x0 + W * 0.33), int(y0 + H * 0.48), int(min(W, H) * 0.3), ctx.accent)
        _chip(d, int(x0 + W * 0.33), int(y1 - H * 0.08), lab, int(44 * SS), ctx.accent)
    _text(d, (int(x0 + W * 0.74), int(y0 + H * 0.5)), "？", int(H * 0.7), (225, 60, 60),
          stroke=8 * SS, stroke_fill=(255, 255, 255))


# ---------------------------------------------------------------------
# 数字（全ジャンル共通。色はジャンルで変える）
# ---------------------------------------------------------------------
def _number(d, box, ctx, text, opening, dark=False):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    val, unit = _num_unit(text)
    if not val:
        val, unit = "?", ""
    fg = (240, 240, 235) if dark else (40, 46, 70)
    hi = (230, 40, 40) if ctx.genre != "pokemon" else (230, 60, 50)
    if unit in ("人", "名", "体") and val.isdigit() and 1 < int(val) <= 120 and H > W * 0.9:
        # 縦長の枠: 上に「47人」、下に人数ぶんの人型を枠いっぱいに
        n = int(val)
        lab = val + unit
        _text(d, (int(x0 + W / 2), int(y0 + H * 0.15)), lab, _fit_size(lab, W * 0.8, int(H * 0.2)), hi,
              stroke=6 * SS, stroke_fill=(0, 0, 0) if dark else (255, 255, 255))
        cols = min(10, max(4, math.ceil(math.sqrt(n * 0.8))))
        rows = math.ceil(n / cols)
        gx0, gx1 = x0 + W * 0.05, x1 - W * 0.05
        gy0, gy1 = y0 + H * 0.32, y1 - H * 0.03
        cell = min((gx1 - gx0) / cols, (gy1 - gy0) / rows)
        ox = gx0 + ((gx1 - gx0) - cell * cols) / 2
        col = (210, 210, 205) if dark else (70, 90, 140)
        for k in range(n):
            r_, c_ = divmod(k, cols)
            _person(d, ox + cell * (c_ + 0.5), gy0 + cell * (r_ + 0.42), cell * 0.62, col)
        return
    if unit in ("人", "名", "体") and val.isdigit() and 1 < int(val) <= 120:
        n = int(val)
        cols = min(12, max(4, math.ceil(math.sqrt(n * 2.2))))
        rows = math.ceil(n / cols)
        gx0, gx1 = x0 + W * 0.36, x1 - W * 0.02
        cell = min((gx1 - gx0) / cols, (H * 0.92) / rows)
        gy0 = y0 + (H - cell * rows) / 2
        col = (210, 210, 205) if dark else (70, 90, 140)
        for k in range(n):
            r_, c_ = divmod(k, cols)
            _person(d, gx0 + cell * (c_ + 0.5), gy0 + cell * (r_ + 0.42), cell * 0.62, col)
        _text(d, (int(x0 + W * 0.18), int(y0 + H * 0.46)), val, _fit_size(val, W * 0.32, int(H * 0.5)), hi,
              stroke=6 * SS, stroke_fill=(0, 0, 0) if dark else (255, 255, 255))
        _text(d, (int(x0 + W * 0.18), int(y0 + H * 0.8)), unit, int(H * 0.16), fg)
        return
    if unit == "回":
        cx, cy = x0 + W * 0.5, y0 + H * 0.5
        rr = H * 0.4
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 210, 510, fill=hi, width=16 * SS)
        _arrow(d, (cx + rr * math.cos(math.radians(140)), cy + rr * math.sin(math.radians(140))),
               (cx + rr * math.cos(math.radians(158)), cy + rr * math.sin(math.radians(158))), hi, 16 * SS, 46 * SS)
        lab = val + unit
        _text(d, (int(cx), int(cy)), lab, _fit_size(lab, rr * 1.6, int(H * 0.36)), fg)
        return
    lab = val + unit
    _text(d, (int(x0 + W / 2), int(y0 + H * 0.5)), lab, _fit_size(lab, W * 0.9, int(H * 0.62)), hi,
          stroke=8 * SS, stroke_fill=(0, 0, 0) if dark else (255, 255, 255))


# ---------------------------------------------------------------------
# scp
# ---------------------------------------------------------------------
PAPER = (226, 220, 204)
INK = (40, 38, 36)


def _redact_rows(d, x0, y0, x1, rows, gap, seed=7, strike_from=None):
    rnd = random.Random(seed)
    for k in range(rows):
        y = y0 + k * gap
        _text(d, (int(x0), int(y)), f"No.{k + 1:02d}", int(gap * 0.42), INK, "bold", anchor="lm")
        bw = (x1 - x0 - gap * 2.2) * rnd.uniform(0.45, 0.95)
        d.rectangle([x0 + gap * 1.9, y - gap * 0.2, x0 + gap * 1.9 + bw, y + gap * 0.2], fill=(18, 18, 18))
        if strike_from is not None and k >= strike_from:
            d.line([(x0 - 6 * SS, y), (x1, y)], fill=(200, 30, 30), width=5 * SS)


def _stamp(img, cx, cy, text, size, col=(200, 30, 30), angle=-14):
    w = _tw(text, size) + size
    h = int(size * 1.6)
    st = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    sd = ImageDraw.Draw(st)
    sd.rounded_rectangle([10, 10, w + 10, h + 10], radius=10 * SS, outline=(*col, 235), width=7 * SS)
    _text(sd, ((w + 20) // 2, (h + 20) // 2), text, size, (*col, 235))
    st = st.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(st, (int(cx - st.width / 2), int(cy - st.height / 2)))


def _scp_paper(d, box, tilt=0):
    x0, y0, x1, y1 = box
    d.rectangle([x0, y0, x1, y1], fill=PAPER)
    d.rectangle([x0, y0, x1, y0 + (y1 - y0) * 0.12], fill=(200, 194, 178))


def _scp_roster(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    if ctx.state == 1:
        return _scp_roster_torn(img, d, box, ctx, text, opening)
    px0, px1 = x0 + W * 0.1, x1 - W * 0.1
    _scp_paper(d, (px0, y0 + 8 * SS, px1, y1))
    d.rounded_rectangle([x0 + W * 0.42, y0 - 6 * SS, x0 + W * 0.58, y0 + 30 * SS], radius=8 * SS, fill=(120, 120, 125))
    val, unit = _num_unit(text + " " + ctx.title_text)
    head = "患者名簿" if "患者" in (text + ctx.title_text) else ("出席簿" if "出席簿" in text else "記録")
    if val and unit in ("人", "名"):
        head += f"（{val}{unit}）"
    _text(d, (int((px0 + px1) / 2), int(y0 + H * 0.08)), head, int(46 * SS), INK)
    rows = 7
    _redact_rows(d, px0 + 30 * SS, y0 + H * 0.24, px1 - 30 * SS, rows, H * 0.1, seed=len(text),
                 strike_from=0 if any(k in text for k in ("消", "空白", "抹消")) else None)
    if any(k in text for k in ("消", "空白", "抹消", "途切れ")):
        _stamp(img, (px0 + px1) / 2, y0 + H * 0.6, "記録抹消", int(64 * SS))


def _scp_roster_torn(img, d, box, ctx, text, opening):
    """途切れた記録: 3 行目で紙が破れ、その下は白紙（「以下、記録なし」）。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    px0, px1 = x0 + W * 0.1, x1 - W * 0.1
    tear = y0 + H * 0.5
    _scp_paper(d, (px0, y0 + 8 * SS, px1, tear))
    head = "患者名簿" if "患者" in (text + ctx.title_text) else "記録"
    _text(d, (int((px0 + px1) / 2), int(y0 + H * 0.08)), head, int(46 * SS), INK)
    _redact_rows(d, px0 + 30 * SS, y0 + H * 0.24, px1 - 30 * SS, 3, H * 0.09, seed=11)
    # 破れ目（ぎざぎざ）
    rnd = random.Random(4)
    pts = []
    n = 18
    for k in range(n + 1):
        pts.append((px0 + (px1 - px0) * k / n, tear + rnd.uniform(-1, 1) * 18 * SS))
    d.polygon([(px0, tear - 30 * SS)] + pts + [(px1, tear - 30 * SS)], fill=PAPER)
    d.polygon(pts + [(px1, y1), (px0, y1)], fill=(18, 18, 18))
    lower = [(x, y + H * 0.08) for x, y in pts]
    d.polygon(lower + [(px1, y1), (px0, y1)], fill=(236, 232, 220))
    _text(d, (int((px0 + px1) / 2), int(y0 + H * 0.76)), "以下、記録なし", int(64 * SS), (200, 30, 30))


def _scp_expunged(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    px0, px1 = x0 + W * 0.08, x1 - W * 0.08
    _scp_paper(d, (px0, y0, px1, y1))
    _text(d, (int(px0 + 30 * SS), int(y0 + H * 0.06)), f"{ctx.subject}  補遺", int(36 * SS), INK, anchor="lm")
    for k in range(3):
        y = y0 + H * (0.2 + k * 0.08)
        d.rectangle([px0 + 30 * SS, y, px1 - 30 * SS - k * 60 * SS, y + 10 * SS], fill=(150, 145, 135))
    bx0, by0, bx1, by1 = px0 + 40 * SS, y0 + H * 0.46, px1 - 40 * SS, y0 + H * 0.78
    d.rectangle([bx0, by0, bx1, by1], outline=(200, 30, 30), width=6 * SS)
    lab = "［データ削除済］"
    _text(d, (int((bx0 + bx1) / 2), int((by0 + by1) / 2)), lab, _fit_size(lab, bx1 - bx0 - 40 * SS, int(64 * SS)),
          (200, 30, 30))
    for k in range(2):
        y = y0 + H * (0.84 + k * 0.07)
        d.rectangle([px0 + 30 * SS, y, px1 - 120 * SS + k * 80 * SS, y + 10 * SS], fill=(150, 145, 135))


def _scp_pill(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    bw, bh = W * 0.3, H * 0.78
    bx, by = x0 + W * 0.12, y0 + H * 0.16
    d.rounded_rectangle([bx + bw * 0.12, by - H * 0.12, bx + bw * 0.88, by + H * 0.02], radius=8 * SS,
                        fill=(235, 235, 235), outline=(90, 90, 90), width=4 * SS)
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=26 * SS, fill=(170, 96, 30), outline=(90, 50, 15), width=5 * SS)
    d.rectangle([bx + 14 * SS, by + bh * 0.28, bx + bw - 14 * SS, by + bh * 0.72], fill=(245, 242, 232))
    lab = ctx.subject or "SCP"
    _text(d, (int(bx + bw / 2), int(by + bh * 0.42)), lab, _fit_size(lab, bw - 40 * SS, int(44 * SS)), INK)
    _text(d, (int(bx + bw / 2), int(by + bh * 0.58)), "経口投与", int(30 * SS), (120, 30, 30), "bold")
    # 錠剤（カプセル）
    for k, (cx, cy, ang) in enumerate(((0.62, 0.42, -25), (0.8, 0.62, 20), (0.66, 0.78, -5))):
        cap = Image.new("RGBA", (int(220 * SS), int(90 * SS)), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cap)
        cd.rounded_rectangle([0, 0, cap.width - 1, cap.height - 1], radius=cap.height // 2, fill=(205, 40, 40),
                             outline=(110, 20, 20), width=4 * SS)
        cd.rounded_rectangle([cap.width // 2, 0, cap.width - 1, cap.height - 1], radius=cap.height // 2,
                             fill=(240, 240, 235), outline=(110, 20, 20), width=4 * SS)
        cd.rectangle([cap.width // 2, 4 * SS, cap.width // 2 + 40 * SS, cap.height - 4 * SS], fill=(240, 240, 235))
        cap = cap.rotate(ang, expand=True, resample=Image.BICUBIC)
        img.alpha_composite(cap, (int(x0 + W * cx - cap.width / 2), int(y0 + H * cy - cap.height / 2)))
    if "万能薬" in (text + ctx.title_text):
        _chip(d, int(x0 + W * 0.7), int(y0 + H * 0.14), "万能薬", int(56 * SS), (200, 30, 30))
    if opening and not ctx.pre and "消" in ctx.title:
        _stamp(img, x0 + W * 0.5, y0 + H * 0.62, "記録抹消", int(96 * SS))


def _scp_note(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    slip = Image.new("RGBA", (int(W * 0.66), int(H * 0.92)), (0, 0, 0, 0))
    sd = ImageDraw.Draw(slip)
    sw, sh = slip.size
    sd.rectangle([0, 0, sw - 1, sh - 1], fill=(244, 240, 228), outline=(120, 110, 90), width=4 * SS)
    head = "処方箋" if "処方" in (text + ctx.title_text) else "残された言葉"
    _text(sd, (sw // 2, int(sh * 0.12)), head, int(54 * SS), INK)
    sd.line([(30 * SS, sh * 0.22), (sw - 30 * SS, sh * 0.22)], fill=(120, 110, 90), width=3 * SS)
    for k, lab in enumerate(("氏名", "薬剤", "備考")):
        y = sh * (0.34 + k * 0.17)
        _text(sd, (int(40 * SS), int(y)), lab, int(34 * SS), (90, 80, 70), "bold", anchor="lm")
        if k < 2:
            sd.rectangle([150 * SS, y - 16 * SS, sw - 40 * SS, y + 16 * SS], fill=(18, 18, 18))
    # 備考欄: 手書き風の一言（読めない）＋赤丸
    y = sh * 0.68
    pts = [(150 * SS + t * 14 * SS, y + 8 * SS * math.sin(t * 1.3)) for t in range(int((sw - 200 * SS) / (14 * SS)))]
    if len(pts) > 1:
        sd.line(pts, fill=(30, 30, 90), width=5 * SS, joint="curve")
    sd.ellipse([130 * SS, y - 50 * SS, sw - 30 * SS, y + 50 * SS], outline=(200, 30, 30), width=6 * SS)
    _text(sd, (sw // 2, int(sh * 0.88)), "全員が同じ一言", int(36 * SS), (200, 30, 30)) if "同じ" in (text + ctx.title_text) else None
    slip = slip.rotate(-4, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(slip, (int(x0 + (W - slip.width) / 2), int(y0 + (H - slip.height) / 2)))


def _scp_door(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    dx0, dx1 = x0 + W * 0.28, x1 - W * 0.28
    d.rectangle([dx0 - 20 * SS, y0, dx1 + 20 * SS, y1], fill=(70, 72, 76))
    d.rectangle([dx0, y0 + 20 * SS, dx1, y1], fill=(120, 124, 130), outline=(40, 40, 44), width=6 * SS)
    _stripes(d, (int(dx0), int(y1 - 60 * SS), int(dx1), int(y1)))
    d.rectangle([dx0 + 40 * SS, y0 + H * 0.12, dx1 - 40 * SS, y0 + H * 0.3], fill=(20, 20, 22))
    _text(d, (int((dx0 + dx1) / 2), int(y0 + H * 0.21)), ctx.subject or "収容室", int(46 * SS), (230, 60, 60))
    d.ellipse([dx1 - 90 * SS, y0 + H * 0.5, dx1 - 40 * SS, y0 + H * 0.5 + 50 * SS], fill=(40, 40, 44))


def _scp_eye(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    cx, cy = x0 + W / 2, y0 + H / 2
    rw, rh = W * 0.36, H * 0.3
    d.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=(230, 226, 214), outline=(20, 20, 20), width=8 * SS)
    d.ellipse([cx - rh * 0.8, cy - rh * 0.8, cx + rh * 0.8, cy + rh * 0.8], fill=(150, 20, 20))
    d.ellipse([cx - rh * 0.3, cy - rh * 0.3, cx + rh * 0.3, cy + rh * 0.3], fill=(10, 10, 10))


def _scp_dossier(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    px0, px1 = x0 + W * 0.06, x1 - W * 0.06
    _scp_paper(d, (px0, y0, px1, y1))
    lab = ctx.subject or "SCP"
    _text(d, (int((px0 + px1) / 2), int(y0 + H * 0.3)), lab, _fit_size(lab, (px1 - px0) * 0.8, int(150 * SS)), INK)
    sub = ctx.subtitle or "特別収容プロトコル"
    _text(d, (int((px0 + px1) / 2), int(y0 + H * 0.56)), sub, _fit_size(sub, (px1 - px0) * 0.86, int(54 * SS)),
          (90, 80, 70))
    for k in range(2):
        y = y0 + H * (0.7 + k * 0.1)
        d.rectangle([px0 + 40 * SS, y, px1 - 40 * SS - k * 150 * SS, y + 14 * SS], fill=(18, 18, 18))
    _stamp(img, px1 - W * 0.18, y0 + H * 0.14, "機密", int(56 * SS))


# ---------------------------------------------------------------------
# yokai
# ---------------------------------------------------------------------
BONE = (232, 228, 214)


def _moon(d, cx, cy, r):
    glow = (255, 240, 200)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=glow)
    d.ellipse([cx - r * 0.4, cy - r * 0.3, cx - r * 0.1, cy], fill=(235, 220, 180))


def _bone_hand(d, wx, wy, ang, L, col=(232, 228, 214, 255), joint=(150, 140, 125, 255)):
    """骨の手（手首 wx,wy から角度 ang の向き、指の長さ L）。指は 4 本＋親指、関節に節。"""
    w = max(2, int(L * 0.09))
    for k, off in enumerate((-0.42, -0.14, 0.14, 0.42)):
        a = ang + off * 0.55
        # 中手骨
        mx, my = wx + L * 0.55 * math.cos(a), wy + L * 0.55 * math.sin(a)
        d.line([(wx, wy), (mx, my)], fill=col, width=w)
        px, py = mx, my
        seg = L * (0.42 if k in (1, 2) else 0.34)
        bend = 0.35
        for j in range(3):
            a2 = a + bend * (j + 1) * 0.5
            nx, ny = px + seg * math.cos(a2), py + seg * math.sin(a2)
            d.line([(px, py), (nx, ny)], fill=col, width=max(2, w - j))
            d.ellipse([px - w * 0.7, py - w * 0.7, px + w * 0.7, py + w * 0.7], fill=joint)
            px, py = nx, ny
            seg *= 0.8
    a = ang - 1.25
    tx, ty = wx + L * 0.45 * math.cos(a), wy + L * 0.45 * math.sin(a)
    d.line([(wx, wy), (tx, ty)], fill=col, width=w)
    d.line([(tx, ty), (tx + L * 0.3 * math.cos(a + 0.6), ty + L * 0.3 * math.sin(a + 0.6))], fill=col, width=w)
    d.ellipse([wx - w * 1.4, wy - w * 1.1, wx + w * 1.4, wy + w * 1.1], fill=col)


def _bone_arm(d, sx, sy, ex, ey, h, col=(232, 228, 214, 255)):
    """前腕の 2 本の骨（橈骨・尺骨）。"""
    w = max(3, int(h * 0.011))
    nx, ny = -(ey - sy), (ex - sx)
    ln = math.hypot(nx, ny) or 1
    nx, ny = nx / ln * h * 0.009, ny / ln * h * 0.009
    d.line([(sx + nx, sy + ny), (ex + nx * 0.5, ey + ny * 0.5)], fill=col, width=w)
    d.line([(sx - nx, sy - ny), (ex - nx * 0.5, ey - ny * 0.5)], fill=col, width=w)


def _skull_face(d, cx, cy, r, glint=True):
    """髑髏の顔（正面）。r=頭の半径。"""
    bone = (*BONE, 255)
    dark = (20, 16, 20, 255)
    shade = (170, 162, 146, 255)
    d.ellipse([cx - r * 0.82, cy - r * 0.95, cx + r * 0.82, cy + r * 0.55], fill=bone)
    # 頬骨と顎（顎は細く）
    d.polygon([(cx - r * 0.8, cy + r * 0.05), (cx - r * 0.55, cy + r * 0.95), (cx + r * 0.55, cy + r * 0.95),
               (cx + r * 0.8, cy + r * 0.05)], fill=bone)
    d.polygon([(cx - r * 0.8, cy + r * 0.15), (cx - r * 0.66, cy + r * 0.45), (cx - r * 0.5, cy + r * 0.3)], fill=shade)
    d.polygon([(cx + r * 0.8, cy + r * 0.15), (cx + r * 0.66, cy + r * 0.45), (cx + r * 0.5, cy + r * 0.3)], fill=shade)
    # 眼窩（深い）
    for sgn in (-1, 1):
        ex = cx + sgn * r * 0.36
        d.polygon([(ex - r * 0.3, cy - r * 0.18), (ex - r * 0.1 * sgn * -1 - r * 0.02, cy - r * 0.36),
                   (ex + r * 0.3, cy - r * 0.16), (ex + r * 0.24, cy + r * 0.14), (ex - r * 0.24, cy + r * 0.16)],
                  fill=dark)
        if glint:
            d.ellipse([ex - r * 0.06, cy - r * 0.06, ex + r * 0.06, cy + r * 0.06], fill=(210, 40, 40, 255))
    # 鼻腔
    d.polygon([(cx, cy + r * 0.16), (cx - r * 0.12, cy + r * 0.42), (cx, cy + r * 0.36), (cx + r * 0.12, cy + r * 0.42)],
              fill=dark)
    # 歯
    ty0, ty1 = cy + r * 0.56, cy + r * 0.8
    d.rectangle([cx - r * 0.42, ty0, cx + r * 0.42, ty1], fill=(210, 204, 188, 255))
    for k in range(-4, 5):
        x = cx + k * r * 0.095
        d.line([(x, ty0), (x, ty1)], fill=(60, 54, 56, 255), width=max(1, int(r * 0.03)))
    d.line([(cx - r * 0.42, (ty0 + ty1) / 2), (cx + r * 0.42, (ty0 + ty1) / 2)], fill=(60, 54, 56, 255),
           width=max(1, int(r * 0.035)))
    # ひび
    d.line([(cx + r * 0.1, cy - r * 0.92), (cx + r * 0.22, cy - r * 0.6), (cx + r * 0.12, cy - r * 0.42)],
           fill=(120, 112, 100, 255), width=max(1, int(r * 0.03)))


def _ghost_woman(img, cx, foot_y, h, raise_hand=False, reach=False):
    """骨女（r3 で描き直し）: 腰まで垂れた黒髪、髑髏の顔（眼窩に赤い光）、
    左前の白装束の胸元からのぞく肋骨、裾はぼろぼろで足は無く透ける、袖から骨の腕と手。
    raise_hand=門を叩く手を前へ / reach=両手をこちらへ伸ばす。"""
    W_, H_ = img.size
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    hr = h * 0.078
    hy = foot_y - h + hr * 1.3
    hair = (10, 8, 14, 252)
    strand = (44, 40, 52, 255)
    rnd = random.Random(int(cx) * 7 + int(h))
    # 後ろ髪: 腰まで、毛先はぎざぎざ
    tip_y = hy + h * 0.52
    back = [(cx - hr * 1.15, hy - hr * 0.4)]
    n = 11
    for k in range(n + 1):
        t = k / n
        x = cx - hr * 1.85 + hr * 3.7 * t
        y = tip_y + (h * 0.05 if k % 2 else 0) + rnd.uniform(-h * 0.015, h * 0.015)
        back.append((x, y))
    back.append((cx + hr * 1.15, hy - hr * 0.4))
    d.polygon(back, fill=hair)
    d.ellipse([cx - hr * 1.25, hy - hr * 1.35, cx + hr * 1.25, hy + hr * 0.9], fill=hair)
    # 髪の毛筋（後ろ髪の上だけ。衣の前には出さない）
    for k in range(18):
        x = cx - hr * 1.75 + k * hr * 0.205
        bot = tip_y - rnd.uniform(0, h * 0.05)
        d.line([(x * 0.85 + cx * 0.15, hy - hr * 0.8), (x + rnd.uniform(-hr * 0.1, hr * 0.1), bot)],
               fill=strand, width=max(1, int(h * 0.0035)))
    # 白装束（袖を含む）。裾は透けて消えるので、別の層に描いて下へ向けて薄くする
    robe = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(robe)
    sh_y = hy + hr * 1.35
    hem = []
    m = 14
    for k in range(m + 1):
        t = k / m
        x = cx - h * 0.2 + h * 0.4 * t
        y = foot_y - (h * 0.04 if k % 2 else 0) - rnd.uniform(0, h * 0.03)
        hem.append((x, y))
    rd.polygon([(cx - h * 0.1, sh_y), (cx + h * 0.1, sh_y)] + list(reversed(hem)), fill=(*BONE, 245))
    # 垂れた袖
    for sgn in (-1, 1):
        rd.polygon([(cx + sgn * h * 0.09, sh_y), (cx + sgn * h * 0.2, sh_y + h * 0.08),
                    (cx + sgn * h * 0.22, sh_y + h * 0.34), (cx + sgn * h * 0.13, sh_y + h * 0.38),
                    (cx + sgn * h * 0.1, sh_y + h * 0.12)], fill=(*BONE, 245))
        rd.line([(cx + sgn * h * 0.2, sh_y + h * 0.1), (cx + sgn * h * 0.205, sh_y + h * 0.33)],
                fill=(170, 164, 150, 255), width=max(2, int(h * 0.005)))
    # 衣のしわ
    for k in range(5):
        x = cx - h * 0.07 + k * h * 0.035
        rd.line([(x, sh_y + h * 0.36), (x + (k - 2) * h * 0.02, foot_y - h * 0.06)], fill=(176, 170, 156, 255),
                width=max(2, int(h * 0.005)))
    # 胸元（左前の合わせ）と肋骨
    nk_y = sh_y + h * 0.005
    v_bot = (cx + h * 0.012, sh_y + h * 0.17)
    rd.polygon([(cx - h * 0.05, nk_y), (cx + h * 0.05, nk_y), v_bot], fill=(36, 30, 34, 255))
    for k in range(4):
        y = nk_y + h * (0.03 + 0.024 * k)
        wv = h * (0.026 - 0.005 * k)
        rd.arc([cx - wv, y - h * 0.008, cx + wv, y + h * 0.012], 200, 340, fill=(*BONE, 255), width=max(2, int(h * 0.005)))
    rd.line([(cx - h * 0.05, nk_y), v_bot], fill=(150, 144, 130, 255), width=max(2, int(h * 0.008)))
    rd.line([(cx + h * 0.05, nk_y), (cx - h * 0.02, sh_y + h * 0.2)], fill=(150, 144, 130, 255), width=max(2, int(h * 0.008)))
    # 帯（くすんだ朱）
    rd.rectangle([cx - h * 0.105, sh_y + h * 0.21, cx + h * 0.115, sh_y + h * 0.25], fill=(110, 28, 30, 255))
    # 下へ向けて透ける
    fade = Image.new("L", img.size, 0)
    fd = ImageDraw.Draw(fade)
    top_f, bot_f = foot_y - h * 0.38, foot_y
    for y in range(int(max(0, sh_y - 4)), int(min(H_, foot_y + 4)), 4):
        a = 255 if y < top_f else int(255 * max(0.0, 1 - (y - top_f) / max(1, bot_f - top_f)) ** 1.4)
        fd.rectangle([0, y, W_, y + 4], fill=a)
    robe.putalpha(Image.composite(robe.split()[3], Image.new("L", img.size, 0), fade).point(lambda v: v))
    lay.alpha_composite(robe)
    d = ImageDraw.Draw(lay)
    # 腕と手
    if reach:
        for sgn in (-1, 1):
            sx, sy = cx + sgn * h * 0.16, sh_y + h * 0.3
            ex, ey = cx + sgn * h * 0.27, sh_y + h * 0.4
            _bone_arm(d, sx, sy, ex, ey, h)
            _bone_hand(d, ex, ey, math.atan2(ey - sy, ex - sx), h * 0.07)
    elif raise_hand:
        sx, sy = cx + h * 0.15, sh_y + h * 0.12
        ex, ey = cx + h * 0.3, sh_y + h * 0.05
        _bone_arm(d, sx, sy, ex, ey, h)
        _bone_hand(d, ex, ey, math.atan2(ey - sy, ex - sx) - 0.5, h * 0.07)
        sx2, sy2 = cx - h * 0.17, sh_y + h * 0.36
        _bone_arm(d, sx2, sy2, sx2 + h * 0.01, sy2 + h * 0.08, h)
        _bone_hand(d, sx2 + h * 0.01, sy2 + h * 0.08, math.pi / 2, h * 0.06)
    else:
        for sgn in (-1, 1):
            sx, sy = cx + sgn * h * 0.17, sh_y + h * 0.36
            ex, ey = sx + sgn * h * 0.01, sy + h * 0.09
            _bone_arm(d, sx, sy, ex, ey, h)
            _bone_hand(d, ex, ey, math.pi / 2 - sgn * 0.15, h * 0.065)
    # 顔
    _skull_face(d, cx, hy, hr * 0.92)
    # 前髪と、顔の左右に垂れる髪（顔に少しかかる）
    d.chord([cx - hr * 1.2, hy - hr * 1.38, cx + hr * 1.2, hy + hr * 0.1], 180, 360, fill=hair)
    for sgn in (-1, 1):
        d.polygon([(cx + sgn * hr * 1.22, hy - hr * 0.7), (cx + sgn * hr * 0.55, hy - hr * 0.95),
                   (cx + sgn * hr * 0.62, hy + hr * 0.2), (cx + sgn * hr * 0.8, hy + hr * 2.2),
                   (cx + sgn * hr * 1.0, hy + h * 0.3), (cx + sgn * hr * 1.45, hy + h * 0.26)], fill=hair)
    # 前に一房、顔を横切る乱れ髪
    d.line([(cx - hr * 0.3, hy - hr * 1.0), (cx - hr * 0.12, hy - hr * 0.3), (cx - hr * 0.3, hy + hr * 0.5)],
           fill=hair, width=max(3, int(hr * 0.1)), joint="curve")
    # 青白い光（ぼかした写し）を後ろに
    glow = lay.copy()
    glow.putalpha(glow.split()[3].point(lambda v: int(v * 0.55)))
    tint = Image.new("RGBA", img.size, (150, 200, 225, 0))
    tint.putalpha(glow.split()[3])
    img.alpha_composite(tint.filter(ImageFilter.GaussianBlur(max(4, int(h * 0.03)))))
    img.alpha_composite(lay)


def _gate(d, x0, y0, x1, y1):
    W = x1 - x0
    roof = (40, 34, 40)
    wood = (92, 62, 44)
    d.polygon([(x0 - W * 0.06, y0 + (y1 - y0) * 0.16), (x0 + W * 0.5, y0), (x1 + W * 0.06, y0 + (y1 - y0) * 0.16)],
              fill=roof)
    d.rectangle([x0 - W * 0.04, y0 + (y1 - y0) * 0.14, x1 + W * 0.04, y0 + (y1 - y0) * 0.2], fill=roof)
    d.rectangle([x0, y0 + (y1 - y0) * 0.2, x0 + W * 0.08, y1], fill=wood)
    d.rectangle([x1 - W * 0.08, y0 + (y1 - y0) * 0.2, x1, y1], fill=wood)
    d.rectangle([x0 + W * 0.08, y0 + (y1 - y0) * 0.24, x1 - W * 0.08, y1], fill=(120, 84, 58),
                outline=(60, 40, 28), width=4 * SS)
    d.line([(x0 + W * 0.5, y0 + (y1 - y0) * 0.24), (x0 + W * 0.5, y1)], fill=(60, 40, 28), width=6 * SS)
    for k in range(4):
        yy = y0 + (y1 - y0) * (0.34 + 0.16 * k)
        d.line([(x0 + W * 0.1, yy), (x1 - W * 0.1, yy)], fill=(90, 62, 42), width=4 * SS)


def _yk_gate(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    _moon(d, x1 - W * 0.12, y0 + H * 0.16, H * 0.1)
    ground = y1 - H * 0.04
    d.rectangle([x0, ground, x1, y1], fill=(14, 14, 26))
    _gate(d, x0 + W * 0.40, y0 + H * 0.12, x1 - W * 0.08, ground)
    _ghost_woman(img, x0 + W * 0.24, ground, H * 0.86, raise_hand=True)
    d = ImageDraw.Draw(img, "RGBA")
    if not ctx.pre and any(k in (text + ctx.title_text) for k in ("叩", "門")):
        _text(d, (int(x0 + W * 0.56), int(y0 + H * 0.12)), "コン…", int(84 * SS), (255, 236, 200), "mincho",
              stroke=3 * SS, stroke_fill=(10, 8, 20))
        _text(d, (int(x0 + W * 0.64), int(y0 + H * 0.24)), "コン…", int(66 * SS), (255, 236, 200, 210), "mincho",
              stroke=3 * SS, stroke_fill=(10, 8, 20))


def _yk_skull(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    _moon(d, x0 + W * 0.14, y0 + H * 0.18, H * 0.1)
    _ghost_woman(img, x0 + W * 0.5, y1 - H * 0.02, H * 0.98)
    d = ImageDraw.Draw(img, "RGBA")
    if "死者" in text or "死" in text:
        _chip(d, int(x1 - W * 0.16), int(y0 + H * 0.2), "死者", int(46 * SS), (150, 24, 24), weight="heavy")


def _yk_moon(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    _moon(d, x0 + W * 0.66, y0 + H * 0.34, H * 0.24)
    ground = y1 - H * 0.16
    # 家並みのシルエット
    xs = [x0 + W * k / 5 for k in range(6)]
    for k in range(5):
        hx0, hx1 = xs[k] + 6 * SS, xs[k + 1] - 6 * SS
        top = ground - H * (0.2 + 0.06 * (k % 2))
        d.polygon([(hx0 - 10 * SS, top + 30 * SS), ((hx0 + hx1) / 2, top - 20 * SS), (hx1 + 10 * SS, top + 30 * SS)],
                  fill=(8, 8, 16))
        d.rectangle([hx0, top + 28 * SS, hx1, ground], fill=(8, 8, 16))
        if k == 2:
            d.rectangle([hx0 + 40 * SS, top + 70 * SS, hx0 + 80 * SS, top + 110 * SS], fill=(255, 200, 110))
    d.rectangle([x0, ground, x1, y1], fill=(8, 8, 16))
    lab = "毎晩" if ("毎晩" in text or "夜ごと" in text) else "夜"
    _text(d, (int(x0 + W * 0.22), int(y0 + H * 0.3)), lab, int(110 * SS), (255, 236, 200), "mincho")


def _yk_lovers(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    ground = y1 - H * 0.04
    _gate(d, x0 + W * 0.38, y0 + H * 0.1, x0 + W * 0.62, ground)
    _ghost_woman(img, x0 + W * 0.2, ground, H * 0.8)
    d = ImageDraw.Draw(img, "RGBA")
    # 生者（暗い人影）
    cx = x0 + W * 0.82
    _human(d, cx, ground, H * 0.72, (70, 60, 84))
    _text(d, (int(x0 + W * 0.2), int(y0 + H * 0.12)), "死者", int(46 * SS), (255, 236, 200), "mincho")
    _text(d, (int(cx), int(y0 + H * 0.12)), "生者", int(46 * SS), (255, 236, 200), "mincho")


def _yk_lantern(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    cx, cy = x0 + W / 2, y0 + H * 0.52
    rw, rh = W * 0.16, H * 0.36
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - rw * 1.8, cy - rh * 1.4, cx + rw * 1.8, cy + rh * 1.4], fill=(255, 140, 60, 90))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40 * SS)))
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=(230, 70, 40))
    for k in range(1, 6):
        yy = cy - rh + 2 * rh * k / 6
        ww = rw * math.sqrt(max(0.0, 1 - ((yy - cy) / rh) ** 2))
        d.line([(cx - ww, yy), (cx + ww, yy)], fill=(160, 40, 20), width=3 * SS)
    d.rectangle([cx - rw * 0.6, cy - rh - 24 * SS, cx + rw * 0.6, cy - rh + 6 * SS], fill=(30, 26, 26))
    d.rectangle([cx - rw * 0.6, cy + rh - 6 * SS, cx + rw * 0.6, cy + rh + 24 * SS], fill=(30, 26, 26))


def _yk_scroll(img, d, box, ctx, text, opening):
    """原典札: 縦書きの名前（明朝）と朱の落款。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    name = ctx.subject or "妖怪"
    size = int(min(H * 0.8 / max(1, len(name)), W * 0.3))
    cx = x0 + W * 0.66
    total = size * len(name)
    ty = y0 + (H - total) / 2 + size / 2
    for k, ch in enumerate(name):
        _text(d, (int(cx), int(ty + k * size)), ch, size, (30, 22, 20), "mincho")
    # 落款
    sx, sy = cx - size * 1.0, y1 - H * 0.16
    d.rectangle([sx - 40 * SS, sy - 40 * SS, sx + 40 * SS, sy + 40 * SS], fill=(190, 30, 30))
    _text(d, (int(sx), int(sy)), (name[:1] or "妖"), int(50 * SS), (250, 230, 210), "mincho")
    # 左: 小さな縦書き「伝承」と骨女の白い影
    for k, ch in enumerate("元の伝承"):
        _text(d, (int(x0 + W * 0.12), int(y0 + H * 0.16 + k * 64 * SS)), ch, int(56 * SS), (110, 30, 30), "mincho")
    if "骨" in name or "女" in name:
        _ghost_woman(img, x0 + W * 0.34, y1 - H * 0.02, H * 0.8)


# ---------------------------------------------------------------------
# pokemon
# ---------------------------------------------------------------------
NAVY = (22, 34, 84)
P1 = (60, 120, 230)
P2 = (225, 70, 60)



def _plate(d, x0, y0, x1, y1, name, col, hp=1.0, active=True):
    a = 255 if active else 150
    d.rounded_rectangle([x0, y0, x1, y1], radius=18 * SS, fill=(255, 255, 255, a), outline=(*NAVY, a), width=6 * SS)
    d.rectangle([x0 + 6 * SS, y0 + 6 * SS, x0 + 22 * SS, y1 - 6 * SS], fill=(*col, a))
    size = _fit_size(name, (x1 - x0) - 70 * SS, int(56 * SS))
    _text(d, (int(x0 + 40 * SS), int(y0 + (y1 - y0) * 0.36)), name, size, (*NAVY, a), anchor="lm")
    bx0, bx1 = x0 + 40 * SS, x1 - 26 * SS
    by = y0 + (y1 - y0) * 0.74
    _text(d, (int(bx0), int(by)), "HP", int(26 * SS), (230, 150, 30, a), anchor="lm")
    bx0 += 50 * SS
    d.rounded_rectangle([bx0, by - 10 * SS, bx1, by + 10 * SS], radius=10 * SS, fill=(60, 60, 60, a))
    d.rounded_rectangle([bx0 + 3 * SS, by - 7 * SS, bx0 + 3 * SS + (bx1 - bx0 - 6 * SS) * hp, by + 7 * SS],
                        radius=7 * SS, fill=(80, 210, 90, a))


def _silhouette(d, cx, cy, r, col, name=""):
    """名前の頭文字のコマ（公式絵は使えないので、色と頭文字で 2 体を見分ける）。"""
    d.ellipse([cx - r, cy - r * 0.32, cx + r, cy + r * 0.32 + r * 0.6], fill=(*col, 50))  # 足元の影
    d.ellipse([cx - r * 0.8, cy - r * 0.8, cx + r * 0.8, cy + r * 0.8], fill=(*col, 255),
              outline=(*NAVY, 255), width=6 * SS)
    ch = (name[:1] if name and name != "？" else "?")
    _text(d, (int(cx), int(cy)), ch, int(r * 0.95), (255, 255, 255), stroke=4 * SS, stroke_fill=NAVY)


def _quiz_line(ctx) -> str:
    """冒頭の二択の問い。thumb_info.hook_lines の「〜？」を使う（台本側の言葉だけ）。"""
    for h in ctx.hook_lines:
        h = h.strip()
        if h.endswith(("？", "?")):
            core = h.rstrip("？?")
            for nm in ctx.names:
                core = core.replace(nm, "")
            core = core.strip("、 ").lstrip("はが")
            if len(core) >= 2:
                return core if core.startswith("どっち") else f"どっちが{core}？"
    return "どっちが勝つ？"


def _pk_versus(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    names = ctx.names + ["？", "？"]
    n1, n2 = names[0], names[1]
    act1 = (n1 in text) or not (n2 in text)
    act2 = (n2 in text) or not (n1 in text)
    quiz = opening and len(ctx.names) == 2
    # 対戦画面の定位置: 相手=右上の影＋左上の名前札 / 自分=左下の影＋右下の名前札
    cs = H * (0.34 if quiz else 0.4)
    for cx, foot, nm, col, act, fl in ((x1 - W * 0.24, y0 + H * (0.42 if quiz else 0.46), n2, P2, act2, True),
                                       (x0 + W * 0.24, y0 + H * 0.96, n1, P1, act1, False)):
        d.ellipse([cx - W * 0.2, foot - H * 0.035, cx + W * 0.2, foot + H * 0.035], fill=(200, 214, 240))
        _creature(img, cx, foot, cs, nm, col, flip=fl, dim=not act and not quiz)
    d = ImageDraw.Draw(img, "RGBA")
    _plate(d, x0 + W * 0.02, y0 + H * 0.04, x0 + W * 0.5, y0 + H * 0.2, n2, P2, active=act2 or quiz)
    _plate(d, x1 - W * 0.5, y0 + H * 0.72, x1 - W * 0.02, y0 + H * 0.88, n1, P1, active=act1 or quiz)
    if quiz:
        q = _quiz_line(ctx)
        _text(d, (int(x0 + W * 0.5), int(y0 + H * 0.52)), q, _fit_size(q, W * 0.94, int(H * 0.085)),
              (230, 50, 40), stroke=9 * SS, stroke_fill=(255, 255, 255))
        for cx, cy, lab, col in ((x1 - W * 0.47, y0 + H * 0.32, "B", P2), (x0 + W * 0.06, y0 + H * 0.62, "A", P1)):
            r = H * 0.05
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*col, 255), outline=(255, 255, 255, 255), width=6 * SS)
            _text(d, (int(cx), int(cy)), lab, int(r * 1.3), (255, 255, 255))
    else:
        _text(d, (int(x0 + W * 0.5), int(y0 + H * 0.56)), "VS", int(H * 0.14), (255, 210, 40),
              stroke=9 * SS, stroke_fill=NAVY)


def _pk_stat(img, d, box, ctx, text, opening):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    rows = []
    for m in _STAT_RE.finditer(text):
        stat = {"すばやさ": "素早さ", "こうげき": "攻撃"}.get(m.group(1), m.group(1))
        # どのポケモンの値か: 数字の前後で一番近い名前
        who = ""
        best = 10 ** 6
        for nm in ctx.names:
            for mm in re.finditer(re.escape(nm), text):
                dist = abs(mm.start() - m.start())
                if dist < best:
                    best, who = dist, nm
        rows.append((who, stat, int(m.group(2))))
    if not rows:
        return _pk_versus(img, d, box, ctx, text, opening)
    rows = rows[:3]
    n = len(rows)
    if n == 1:
        who, stat, val = rows[0]
        col = P1 if (not ctx.names or who == ctx.names[0]) else P2
        lab = f"{who}の{stat}" if who else stat
        _text(d, (int(x0 + W * 0.5), int(y0 + H * 0.08)), lab, _fit_size(lab, W * 0.9, int(64 * SS)), NAVY)
        bx0, bx1 = x0 + W * 0.06, x1 - W * 0.06
        by0, by1 = y0 + H * 0.15, y0 + H * 0.23
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=20 * SS, fill=(220, 226, 240))
        frac = max(0.05, min(1.0, val / 200.0))
        d.rounded_rectangle([bx0, by0, bx0 + (bx1 - bx0) * frac, by1], radius=20 * SS, fill=col)
        for t in (0.25, 0.5, 0.75):
            d.line([(bx0 + (bx1 - bx0) * t, by1 + 6 * SS), (bx0 + (bx1 - bx0) * t, by1 + 22 * SS)], fill=(150, 160, 190), width=3 * SS)
        _text(d, (int(bx1 - 10 * SS), int(by1 + 40 * SS)), "種族値（最大200で表示）", int(26 * SS), (110, 120, 150), "bold", anchor="rm")
        d.ellipse([x0 + W * 0.1, y1 - H * 0.08, x0 + W * 0.6, y1 - H * 0.02], fill=(200, 214, 240))
        _creature(img, x0 + W * 0.35, y1 - H * 0.05, H * 0.6, who or (ctx.names[:1] or ["？"])[0], col)
        d = ImageDraw.Draw(img, "RGBA")
        _text(d, (int(x0 + W * 0.78), int(y0 + H * 0.55)), str(val), int(H * 0.2), col, stroke=10 * SS,
              stroke_fill=(255, 255, 255))
        _text(d, (int(x0 + W * 0.78), int(y0 + H * 0.7)), stat, int(H * 0.06), NAVY)
        return
    gap = H / (n + 0.6)
    for k, (who, stat, val) in enumerate(rows):
        cy = y0 + gap * (k + 0.8)
        col = P1 if (not ctx.names or who == ctx.names[0]) else P2
        lab = f"{who}" if who else ""
        _text(d, (int(x0 + W * 0.08), int(cy - gap * 0.28)), f"{lab}  {stat}", int(44 * SS), NAVY, anchor="lm")
        bx0, bx1 = x0 + W * 0.08, x1 - W * 0.22
        d.rounded_rectangle([bx0, cy, bx1, cy + gap * 0.3], radius=12 * SS, fill=(220, 226, 240))
        frac = max(0.05, min(1.0, val / 200.0))
        d.rounded_rectangle([bx0, cy, bx0 + (bx1 - bx0) * frac, cy + gap * 0.3], radius=12 * SS, fill=col)
        _text(d, (int(x1 - W * 0.1), int(cy + gap * 0.15)), str(val),
              _fit_size(str(val), W * 0.18, int(min(gap * 0.62, 120 * SS))), col,
              stroke=6 * SS, stroke_fill=(255, 255, 255))
    _text(d, (int(x1 - 10 * SS), int(y1 - 8 * SS)), "種族値（最大200で表示）", int(24 * SS), (110, 120, 150), "bold",
          anchor="rd")


def _pk_priority(img, d, box, ctx, text, opening):
    """先制技の仕組み: 通常は素早さ順、先制技はそれより先に動く（ゲームの一般則のみ）。
    状態 0 は句に「先制」があれば先制技の図、無ければ素早さ順の図。状態 1 はその逆。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    lanes_first = "先制" in text
    if (ctx.state == 0) != lanes_first:
        return _pk_race(img, d, box, ctx, text, opening)
    _text(d, (int(x0 + W * 0.5), int(y0 + H * 0.08)), "行動の順番", int(48 * SS), NAVY)
    lanes = [("先制技", (230, 60, 50), 0.9), ("通常の技", (60, 120, 230), 0.55)]
    for k, (lab, col, frac) in enumerate(lanes):
        cy = y0 + H * (0.34 + 0.32 * k)
        _chip(d, int(x0 + W * 0.15), int(cy), lab, int(42 * SS), col)
        _arrow(d, (x0 + W * 0.3, cy), (x0 + W * (0.3 + 0.62 * frac), cy), col, 22 * SS, 54 * SS)
    _text(d, (int(x0 + W * 0.76), int(y0 + H * 0.46)), "先に動く", int(42 * SS), (230, 60, 50), anchor="mm")
    _text(d, (int(x0 + W * 0.55), int(y0 + H * 0.8)), "素早さ順", int(38 * SS), (60, 120, 230), anchor="mm")


def _pk_wall(img, d, box, ctx, text, opening):
    """攻撃を止める壁: 左から攻撃の矢印（台本に「攻撃N」があれば値）、壁、壁の後ろに守られる側。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    m = re.search(r"(攻撃|こうげき)\s*(\d{2,3})", text)
    lab = f"攻撃{m.group(2)}" if m else "攻撃"
    # 攻撃の値の持ち主（台本の前の行で「名前…攻撃N」と言った側）
    atk = ""
    for nm in ctx.names:
        if re.search(re.escape(nm) + r".{0,8}(攻撃|こうげき)\s*" + (m.group(2) if m else r"\d"), ctx.script_text):
            atk = nm
    other = next((nm for nm in ctx.names if nm != atk), "")
    gy = y0 + H * 0.9
    if atk:
        _creature(img, x0 + W * 0.2, gy, H * 0.5, atk, P2 if atk != ctx.names[0] else P1)
    if other:
        _creature(img, x0 + W * 0.84, gy, H * 0.42, other, P1 if other == ctx.names[0] else P2, flip=True)
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = x0 + W * 0.6, y0 + H * 0.5
    sw, sh = W * 0.16, H * 0.74
    shield = [(cx - sw / 2, cy - sh / 2), (cx + sw / 2, cy - sh / 2), (cx + sw / 2, cy + sh * 0.2),
              (cx, cy + sh / 2), (cx - sw / 2, cy + sh * 0.2)]
    d.polygon(shield, fill=(80, 150, 240, 235))
    d.polygon(shield, outline=NAVY, width=8 * SS)
    d.line([(cx - sw * 0.25, cy - sh * 0.4), (cx - sw * 0.25, cy + sh * 0.2)], fill=(200, 230, 255), width=8 * SS)
    ay = y0 + H * 0.42
    _arrow(d, (x0 + W * 0.3, ay), (cx - sw / 2 - 20 * SS, ay), (230, 60, 50), 34 * SS, 80 * SS)
    _text(d, (int(x0 + W * 0.3), int(y0 + H * 0.3)), lab, int(80 * SS), (230, 60, 50), stroke=8 * SS,
          stroke_fill=(255, 255, 255))
    for k in range(3):
        a = math.radians(-50 + 50 * k)
        p = (cx - sw / 2 - 30 * SS, ay)
        d.line([p, (p[0] - 70 * SS * math.cos(a), p[1] + 70 * SS * math.sin(a))], fill=(255, 200, 40), width=10 * SS)
    _text(d, (int(x0 + W * 0.6), int(y0 + H * 0.06)), "壁", int(H * 0.1), NAVY, stroke=6 * SS, stroke_fill=(255, 255, 255))


# ---------------------------------------------------------------------
# r3: 追加の図（否定・病棟・教室・ノック・障子の影・引き込む手・ゲームと原典・逆転）
# ---------------------------------------------------------------------
def _deny(img, d, box, ctx, text, opening):
    """誤解に ✕: 「A ではない」の A を大きく出し、赤い ✕ で消す。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    lab = deny_label(text) or "？"
    g = ctx.genre
    dark = g in ("scp", "yokai")
    fg = (240, 236, 226) if dark else (40, 46, 70)
    weight = "mincho" if g == "yokai" else "heavy"
    # よくある思い込み（小見出し）
    _chip(d, int(x0 + W / 2), int(y0 + H * 0.14), "よくある思い込み", int(44 * SS),
          (150, 24, 24) if dark else (60, 70, 100), weight="heavy")
    # 2 行まで折り返して大きく（読める大きさのまま、赤い取り消し線と ✕ 印）
    n = len(lab)
    lines = [lab] if n <= 7 else [lab[: (n + 1) // 2], lab[(n + 1) // 2:]]
    size = min(int(H * 0.16), int(W * 0.86 / max(len(l) for l in lines)))
    cy = y0 + H * 0.4
    lh = size * 1.25
    top = cy - lh * (len(lines) - 1) / 2
    for k, ln in enumerate(lines):
        ly = top + k * lh
        _text(d, (int(x0 + W / 2), int(ly)), ln, size, fg, weight,
              stroke=(5 * SS if not dark else 0), stroke_fill=(255, 255, 255))
        lw = _tw(ln, size, weight)
        d.line([(x0 + W / 2 - lw / 2 - 20 * SS, ly + size * 0.06), (x0 + W / 2 + lw / 2 + 20 * SS, ly - size * 0.06)],
               fill=(225, 40, 40, 235), width=int(size * 0.13))
    # ✕ 印（赤丸に白の ✕）
    r = min(W, H) * 0.17
    cx, cyx = x0 + W / 2, y0 + H * 0.76
    d.ellipse([cx - r, cyx - r, cx + r, cyx + r], fill=(225, 40, 40, 255), outline=(255, 255, 255, 255), width=8 * SS)
    k = r * 0.5
    for sx in (-1, 1):
        d.line([(cx - k, cyx - k * sx), (cx + k, cyx + k * sx)], fill=(255, 255, 255, 255), width=int(r * 0.22))
    if g == "pokemon":
        pass


def _scp_ward(img, d, box, ctx, text, opening):
    """病棟: 奥へ並ぶ空のベッド、吊り下げ灯の光の円錐、床の反射。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    vx, vy = x0 + W * 0.5, y0 + H * 0.36      # 消失点
    d.rectangle([x0, y0, x1, y1], fill=(16, 18, 20))
    # 床と壁
    d.polygon([(x0, y1), (x1, y1), (vx + W * 0.12, vy + H * 0.04), (vx - W * 0.12, vy + H * 0.04)], fill=(42, 46, 44))
    d.polygon([(x0, y0), (vx - W * 0.12, vy - H * 0.16), (vx - W * 0.12, vy + H * 0.04), (x0, y1)], fill=(30, 34, 34))
    d.polygon([(x1, y0), (vx + W * 0.12, vy - H * 0.16), (vx + W * 0.12, vy + H * 0.04), (x1, y1)], fill=(26, 30, 30))
    d.rectangle([vx - W * 0.12, vy - H * 0.16, vx + W * 0.12, vy + H * 0.04], fill=(12, 12, 14))
    # 床の目地
    for k in range(1, 9):
        t = k / 9
        d.line([(x0 + W * t, y1), (vx - W * 0.12 + W * 0.24 * t, vy + H * 0.04)], fill=(52, 56, 54), width=SS)
    # ベッド（左右に 4 台ずつ、奥ほど小さく）
    for side in (-1, 1):
        for k in range(4):
            t = 0.18 + k * 0.2
            sc = 1 - t * 0.85
            by = vy + H * 0.04 + (y1 - vy - H * 0.04) * (1 - t) * 0.92
            bx = vx + side * (W * 0.5 * (1 - t) * 0.92 + W * 0.05)
            bw, bh = W * 0.34 * sc, H * 0.09 * sc
            leg = H * 0.06 * sc
            fx0 = bx - bw / 2
            d.rectangle([fx0, by - bh, fx0 + bw, by - bh * 0.45], fill=(214, 214, 206))      # 敷布
            d.rectangle([fx0, by - bh * 0.45, fx0 + bw, by - bh * 0.25], fill=(120, 124, 126))  # 枠
            d.ellipse([fx0 + bw * (0.05 if side > 0 else 0.72), by - bh * 1.15,
                       fx0 + bw * (0.28 if side > 0 else 0.95), by - bh * 0.7], fill=(236, 236, 230))  # 枕
            for lx in (fx0 + bw * 0.06, fx0 + bw * 0.94):
                d.line([(lx, by - bh * 0.25), (lx, by - bh * 0.25 + leg)], fill=(90, 94, 96), width=max(2, int(5 * SS * sc)))
            # 点滴台
            if k % 2 == 0:
                px = fx0 + (bw * 1.04 if side < 0 else -bw * 0.04)
                d.line([(px, by - bh * 0.25 + leg), (px, by - bh * 2.6)], fill=(110, 114, 116), width=max(2, int(4 * SS * sc)))
                d.rounded_rectangle([px - bw * 0.05, by - bh * 2.6, px + bw * 0.05, by - bh * 2.0], radius=4,
                                    fill=(170, 200, 210))
    # 吊り下げ灯の光
    lx, ly = vx, y0 + H * 0.05
    cone = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(cone).polygon([(lx - W * 0.03, ly), (lx + W * 0.03, ly), (lx + W * 0.34, y1), (lx - W * 0.34, y1)],
                                 fill=(230, 240, 220, 46))
    img.alpha_composite(cone.filter(ImageFilter.GaussianBlur(18 * SS)))
    d.line([(lx, y0), (lx, ly)], fill=(60, 60, 60), width=3 * SS)
    d.polygon([(lx - W * 0.05, ly + H * 0.04), (lx + W * 0.05, ly + H * 0.04), (lx + W * 0.02, ly), (lx - W * 0.02, ly)],
              fill=(80, 84, 80))
    d.ellipse([lx - W * 0.02, ly + H * 0.03, lx + W * 0.02, ly + H * 0.055], fill=(250, 250, 225))
    if "翌朝" in text:
        _chip(d, int(x0 + W * 0.2), int(y0 + H * 0.12), "翌朝", int(52 * SS), (170, 24, 24))
    elif any(k in text for k in ("回復", "助か")):
        _chip(d, int(x0 + W * 0.22), int(y0 + H * 0.12), "全員 退院？", int(44 * SS), (170, 24, 24))


def _scp_classroom(img, d, box, ctx, text, opening):
    """空の教室: 黒板と、奥へ並ぶ誰もいない机と椅子。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    d.rectangle([x0, y0, x1, y1], fill=(34, 32, 30))
    d.rectangle([x0, y0 + H * 0.42, x1, y1], fill=(58, 46, 36))   # 床
    for k in range(10):
        yy = y0 + H * 0.42 + (H * 0.58) * (k / 10) ** 1.6
        d.line([(x0, yy), (x1, yy)], fill=(48, 38, 30), width=SS)
    # 黒板
    bx0, by0, bx1, by1 = x0 + W * 0.12, y0 + H * 0.06, x1 - W * 0.12, y0 + H * 0.3
    d.rectangle([bx0 - 10 * SS, by0 - 10 * SS, bx1 + 10 * SS, by1 + 16 * SS], fill=(92, 70, 48))
    d.rectangle([bx0, by0, bx1, by1], fill=(30, 58, 46))
    for k in range(5):  # 消し跡
        d.arc([bx0 + W * 0.08 * k, by0 + H * 0.04, bx0 + W * 0.08 * k + W * 0.2, by1 - H * 0.02], 200, 330,
              fill=(60, 88, 76), width=6 * SS)
    lab = "出席" if "出席" in text else "1クラス"
    _text(d, (int(bx1 - W * 0.12), int(by0 + H * 0.06)), lab, int(40 * SS), (220, 220, 210), "bold")
    # 机（4 列 × 4 行、手前ほど大きい）
    for r in range(4):
        t = r / 3
        sc = 0.45 + 0.55 * t
        yy = y0 + H * (0.46 + 0.42 * t)
        for c in range(4):
            cx = x0 + W * (0.5 + (c - 1.5) * (0.17 + 0.07 * t))
            dw, dh = W * 0.13 * sc, H * 0.035 * sc
            d.rectangle([cx - dw / 2, yy - dh, cx + dw / 2, yy], fill=(150, 112, 70))
            d.rectangle([cx - dw / 2, yy, cx + dw / 2, yy + dh * 0.5], fill=(110, 82, 52))
            for lx in (cx - dw * 0.42, cx + dw * 0.42):
                d.line([(lx, yy + dh * 0.5), (lx, yy + dh * 2.4)], fill=(90, 90, 92), width=max(2, int(4 * SS * sc)))
            # 椅子（引かれたまま）
            d.rectangle([cx - dw * 0.3, yy + dh * 1.4, cx + dw * 0.3, yy + dh * 1.8], fill=(120, 90, 60))
    # 窓の光（左から斜めに）
    win = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(win).polygon([(x0, y0 + H * 0.3), (x0 + W * 0.18, y0 + H * 0.3), (x0 + W * 0.7, y1), (x0, y1)],
                                fill=(200, 210, 230, 26))
    img.alpha_composite(win.filter(ImageFilter.GaussianBlur(10 * SS)))


def _wood(d, x0, y0, x1, y1, seed=5):
    rnd = random.Random(seed)
    d.rectangle([x0, y0, x1, y1], fill=(92, 62, 42))
    n = 5
    pw = (x1 - x0) / n
    for k in range(n):
        px0 = x0 + k * pw
        d.rectangle([px0 + 3 * SS, y0, px0 + pw - 3 * SS, y1], fill=(108 + rnd.randint(-8, 8), 74, 50))
        for j in range(7):
            gx = px0 + pw * rnd.uniform(0.1, 0.9)
            d.line([(gx, y0), (gx + rnd.uniform(-20, 20) * SS, y1)], fill=(84, 56, 38), width=2 * SS)
        d.line([(px0, y0), (px0, y1)], fill=(40, 26, 18), width=4 * SS)


def _yk_knock(img, d, box, ctx, text, opening):
    """門を叩く骨の手の寄り（木戸の板目いっぱい）。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    _wood(d, x0, y0, x1, y1)
    # 月明かりの斜光
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon([(x0, y0), (x1, y0), (x1, y0 + H * 0.25), (x0, y0 + H * 0.7)], fill=(10, 14, 40, 120))
    img.alpha_composite(sh)
    d = ImageDraw.Draw(img, "RGBA")
    # 腕（袖から）と拳
    sx, sy = x0 - W * 0.02, y0 + H * 0.78
    hx, hy = x0 + W * 0.56, y0 + H * 0.5
    d.polygon([(x0 - W * 0.05, y0 + H * 0.66), (x0 + W * 0.22, y0 + H * 0.6), (x0 + W * 0.26, y0 + H * 0.82),
               (x0 - W * 0.05, y0 + H * 0.98)], fill=(*BONE, 255))
    d.line([(x0 + W * 0.0, y0 + H * 0.7), (x0 + W * 0.22, y0 + H * 0.66)], fill=(170, 164, 150), width=4 * SS)
    _bone_arm(d, x0 + W * 0.22, y0 + H * 0.7, hx, hy, H * 2.4)
    # 拳（握った指の節）
    for k in range(4):
        kx = hx + W * 0.03 + k * W * 0.0
        ky = hy - H * 0.06 + k * H * 0.045
        d.rounded_rectangle([kx, ky, kx + W * 0.1, ky + H * 0.036], radius=int(H * 0.016), fill=(*BONE, 255),
                            outline=(140, 132, 118), width=2 * SS)
        d.ellipse([kx + W * 0.085, ky + H * 0.004, kx + W * 0.115, ky + H * 0.032], fill=(196, 188, 172))
    d.ellipse([hx - W * 0.03, hy - H * 0.05, hx + W * 0.06, hy + H * 0.08], fill=(*BONE, 255))
    # 衝撃線と擬音
    ix = hx + W * 0.16
    for k in range(5):
        a = math.radians(-60 + k * 30)
        d.line([(ix + W * 0.03 * math.cos(a), hy + W * 0.03 * math.sin(a)),
                (ix + W * 0.1 * math.cos(a), hy + W * 0.1 * math.sin(a))], fill=(255, 236, 200), width=5 * SS)
    _text(d, (int(x0 + W * 0.72), int(y0 + H * 0.2)), "コン…", int(120 * SS), (255, 236, 200), "mincho",
          stroke=4 * SS, stroke_fill=(20, 14, 10))
    _text(d, (int(x0 + W * 0.76), int(y0 + H * 0.8)), "コン…", int(90 * SS), (255, 236, 200, 210), "mincho",
          stroke=4 * SS, stroke_fill=(20, 14, 10))


def _yk_shoji(img, d, box, ctx, text, opening):
    """家の中から見た障子に、外に立つ骨女の影が映る（月明かりの逆光）。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    d.rectangle([x0, y0, x1, y1], fill=(10, 10, 16))
    sx0, sy0, sx1, sy1 = x0 + W * 0.06, y0 + H * 0.05, x1 - W * 0.06, y0 + H * 0.8
    # 障子紙（月明かりで青白い、中央ほど明るい）
    paper = Image.new("RGBA", img.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(paper)
    pd.rectangle([sx0, sy0, sx1, sy1], fill=(120, 140, 170, 255))
    pd.ellipse([sx0 + W * 0.1, sy0 + H * 0.05, sx1 - W * 0.1, sy1 - H * 0.05], fill=(190, 205, 225, 255))
    img.alpha_composite(paper.filter(ImageFilter.GaussianBlur(30 * SS)))
    # 影（髪の長い女の輪郭、片手を上げる）: 影絵として黒でぼかす
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    _ghost_woman(sh, x0 + W * 0.5, sy1 + H * 0.06, H * 0.82, raise_hand=True)
    a = sh.split()[3]
    shadow = Image.new("RGBA", img.size, (14, 12, 22, 0))
    shadow.putalpha(a.point(lambda v: int(min(255, v * 1.2) * 0.9)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(5 * SS))
    clip = Image.new("L", img.size, 0)
    ImageDraw.Draw(clip).rectangle([sx0, sy0, sx1, sy1], fill=255)
    shadow.putalpha(Image.composite(shadow.split()[3], Image.new("L", img.size, 0), clip))
    img.alpha_composite(shadow)
    d = ImageDraw.Draw(img, "RGBA")
    # 桟（格子）
    for k in range(1, 4):
        x = sx0 + (sx1 - sx0) * k / 4
        d.line([(x, sy0), (x, sy1)], fill=(40, 30, 24), width=7 * SS)
    for k in range(1, 6):
        y = sy0 + (sy1 - sy0) * k / 6
        d.line([(sx0, y), (sx1, y)], fill=(40, 30, 24), width=6 * SS)
    d.rectangle([sx0, sy0, sx1, sy1], outline=(46, 34, 26), width=16 * SS)
    # 手前の畳と、部屋の暗がり
    d.polygon([(x0, y1), (x1, y1), (x1 - W * 0.06, sy1 + 16 * SS), (x0 + W * 0.06, sy1 + 16 * SS)], fill=(46, 48, 30))
    for k in range(1, 4):
        d.line([(x0 + W * k / 4, y1), (x0 + W * 0.06 + (W * 0.88) * k / 4, sy1 + 16 * SS)], fill=(30, 32, 20), width=3 * SS)
    lab = "外から" if "外" in text else ("逃げ場なし" if "逃げ" in text else "")
    if lab:
        _chip(d, int(x0 + W * 0.2), int(y0 + H * 0.1), lab, int(46 * SS), (150, 24, 24))


def _yk_pull(img, d, box, ctx, text, opening):
    """開いた門の向こうの闇から、骨の手が何本も伸びて生者の袖を引く。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    ground = y1 - H * 0.04
    # 門の中の闇（奥が見えない）
    gx0, gx1 = x0 + W * 0.2, x1 - W * 0.2
    _gate(d, gx0, y0 + H * 0.05, gx1, ground)
    d.rectangle([gx0 + (gx1 - gx0) * 0.12, y0 + H * 0.05 + (ground - y0 - H * 0.05) * 0.26,
                 gx1 - (gx1 - gx0) * 0.12, ground], fill=(4, 2, 6))
    # 開いた扉（手前に開く）
    d.polygon([(gx0 + (gx1 - gx0) * 0.12, y0 + H * 0.3), (gx0 - W * 0.06, y0 + H * 0.26),
               (gx0 - W * 0.06, ground + H * 0.02), (gx0 + (gx1 - gx0) * 0.12, ground)], fill=(110, 76, 52))
    d.polygon([(gx1 - (gx1 - gx0) * 0.12, y0 + H * 0.3), (gx1 + W * 0.06, y0 + H * 0.26),
               (gx1 + W * 0.06, ground + H * 0.02), (gx1 - (gx1 - gx0) * 0.12, ground)], fill=(100, 70, 48))
    # 生者（手前、背中を向けて引かれる）
    mx = x0 + W * 0.5
    _human(d, mx, y1 + H * 0.02, H * 0.62, (64, 56, 76))
    # 闇から伸びる骨の手
    hands = [(0.36, 0.52, 0.35), (0.62, 0.48, 2.6), (0.44, 0.7, 0.6), (0.6, 0.72, 2.4), (0.52, 0.4, 1.4)]
    for k, (hx, hy, ang) in enumerate(hands):
        ex, ey = x0 + W * hx, y0 + H * hy
        sx = x0 + W * 0.5 + (ex - x0 - W * 0.5) * 0.3
        sy = ey - H * 0.12
        _bone_arm(d, sx, sy, ex, ey, H * 1.4)
        _bone_hand(d, ex, ey, math.atan2(ey - sy, ex - sx) + (0.3 if k % 2 else -0.3), H * 0.06)
    _text(d, (int(x0 + W * 0.5), int(y0 + H * 0.14)), "死者の側へ", int(64 * SS), (255, 236, 200), "mincho",
          stroke=4 * SS, stroke_fill=(10, 6, 10)) if "死者" in text else None


def _yk_contrast(img, d, box, ctx, text, opening):
    """左=ゲームでの印象（やさしい色）/ 右=原典（暗い夜の骨女）。斜めに割る。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    d.rectangle([x0, y0, x1, y1], fill=(250, 214, 226))
    right = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(right)
    poly = [(x0 + W * 0.58, y0), (x1, y0), (x1, y1), (x0 + W * 0.42, y1)]
    rd.polygon(poly, fill=(16, 16, 34, 255))
    img.alpha_composite(right)
    d = ImageDraw.Draw(img, "RGBA")
    # 左: 丸いハートと花びら（やさしい印象）
    for k in range(9):
        rnd = random.Random(k)
        px, py = x0 + W * rnd.uniform(0.05, 0.42), y0 + H * rnd.uniform(0.1, 0.9)
        d.ellipse([px - 12 * SS, py - 8 * SS, px + 12 * SS, py + 8 * SS], fill=(255, 170, 196))
    hx, hy, hs = x0 + W * 0.25, y0 + H * 0.46, W * 0.13
    d.ellipse([hx - hs, hy - hs * 0.8, hx, hy + hs * 0.2], fill=(240, 90, 130))
    d.ellipse([hx, hy - hs * 0.8, hx + hs, hy + hs * 0.2], fill=(240, 90, 130))
    d.polygon([(hx - hs * 0.98, hy - hs * 0.15), (hx + hs * 0.98, hy - hs * 0.15), (hx, hy + hs * 1.1)], fill=(240, 90, 130))
    _text(d, (int(hx), int(y0 + H * 0.16)), "ゲーム", int(64 * SS), (150, 50, 90))
    lab = "切ない" if "切ない" in text else ("好き" if "好き" in text else "")
    if lab:
        _text(d, (int(hx), int(y0 + H * 0.78)), lab, int(80 * SS), (200, 60, 110), stroke=4 * SS,
              stroke_fill=(255, 255, 255))
    # 右: 原典の骨女
    _moon(d, x1 - W * 0.12, y0 + H * 0.14, H * 0.06)
    _ghost_woman(img, x0 + W * 0.74, y1 - H * 0.02, H * 0.8)
    d = ImageDraw.Draw(img, "RGBA")
    _text(d, (int(x0 + W * 0.78), int(y0 + H * 0.06)), "原典", int(64 * SS), (255, 236, 200), "mincho")
    d.line([(x0 + W * 0.58, y0), (x0 + W * 0.42, y1)], fill=(255, 255, 255), width=8 * SS)


# --- pokemon: 種族の特徴だけを描いた影（公式絵は使わない） ---
_CREATURE = {
    # 名前: (形, 体色, 差し色)
    "マニューラ": ("claw", (36, 40, 84), (220, 40, 64)),
    "ニューラ": ("claw", (30, 50, 70), (220, 40, 64)),
    "オノノクス": ("tusk", (176, 160, 56), (200, 40, 40)),
    "オノンド": ("tusk", (120, 140, 70), (200, 40, 40)),
}


def _creature(img, cx, foot_y, h, name, col_default, flip=False, dim=False):
    """名前に応じた種族の特徴（爪と羽飾り／斧の牙）を持つ影。知らない名前は丸い影に「？」。"""
    shape, body, acc = _CREATURE.get(name, ("blob", col_default, (255, 210, 40)))
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    s = h
    out = (12, 14, 30, 255)
    ow = max(3, int(s * 0.012))
    def leaf(p0, p1, wdt, col, bend=0.25):
        """p0→p1 の曲がった葉形（羽・刃）。"""
        (ax, ay), (bx, by) = p0, p1
        nx, ny = -(by - ay), (bx - ax)
        ln = math.hypot(nx, ny) or 1
        nx, ny = nx / ln, ny / ln
        pts_a, pts_b = [], []
        for k in range(13):
            t = k / 12
            mx, my = ax + (bx - ax) * t, ay + (by - ay) * t
            off = math.sin(math.pi * t) * wdt * (1 - 0.3 * t)
            cb = math.sin(math.pi * t) * bend * ln
            pts_a.append((mx + nx * (off + cb), my + ny * (off + cb)))
            pts_b.append((mx - nx * (off - cb), my - ny * (off - cb)))
        d.polygon(pts_a + list(reversed(pts_b)), fill=col, outline=out, width=ow)

    if shape == "claw":
        # 細身の二足。頭に後ろへ流れる赤い長い羽、首の赤い襟羽、両手の長い白い爪
        hx, hy = cx, foot_y - s * 0.7
        for sgn in (-1, 1):  # 脚
            d.ellipse([cx + sgn * s * 0.09 - s * 0.06, foot_y - s * 0.24, cx + sgn * s * 0.09 + s * 0.06, foot_y],
                      fill=(*body, 255), outline=out, width=ow)
        d.ellipse([cx - s * 0.15, foot_y - s * 0.56, cx + s * 0.15, foot_y - s * 0.14], fill=(*body, 255), outline=out, width=ow)
        d.ellipse([cx - s * 0.08, foot_y - s * 0.44, cx + s * 0.08, foot_y - s * 0.22], fill=(min(255, body[0] + 40), min(255, body[1] + 40), min(255, body[2] + 50), 255))
        for sgn in (-1, 1):  # 腕と爪
            ax, ay = cx + sgn * s * 0.12, foot_y - s * 0.46
            ex, ey = cx + sgn * s * 0.3, foot_y - s * 0.36
            d.line([(ax, ay), (ex, ey)], fill=out, width=int(s * 0.075))
            d.line([(ax, ay), (ex, ey)], fill=(*body, 255), width=int(s * 0.05))
            base = math.atan2(ey - ay, ex - ax)
            for k in range(3):
                a2 = base + (k - 1) * 0.32
                leaf((ex, ey), (ex + s * 0.17 * math.cos(a2), ey + s * 0.17 * math.sin(a2)), s * 0.012, (245, 245, 250, 255), 0.08)
        for k in range(6):  # 襟羽
            a = math.radians(205 + k * 26)
            leaf((cx, foot_y - s * 0.53), (cx + s * 0.2 * math.cos(a), foot_y - s * 0.5 + s * 0.1 * math.sin(a) + s * 0.05),
                 s * 0.03, (*acc, 255), 0.05)
        leaf((hx + s * 0.02, hy - s * 0.08), (hx + s * 0.26, hy - s * 0.4), s * 0.05, (*acc, 255), -0.18)
        leaf((hx + s * 0.06, hy - s * 0.04), (hx + s * 0.3, hy - s * 0.26), s * 0.035, (*acc, 255), -0.12)
        d.ellipse([hx - s * 0.14, hy - s * 0.12, hx + s * 0.14, hy + s * 0.12], fill=(*body, 255), outline=out, width=ow)
        for sgn in (-1, 1):  # 耳
            leaf((hx + sgn * s * 0.08, hy - s * 0.06), (hx + sgn * s * 0.2, hy - s * 0.26), s * 0.035, (*body, 255), 0.0)
        for sgn in (-1, 1):  # 鋭い目
            d.polygon([(hx + sgn * s * 0.015, hy + s * 0.005), (hx + sgn * s * 0.105, hy - s * 0.035), (hx + sgn * s * 0.09, hy + s * 0.03)],
                      fill=(255, 220, 60, 255))
            d.ellipse([hx + sgn * s * 0.06 - s * 0.012, hy - s * 0.01, hx + sgn * s * 0.06 + s * 0.012, hy + s * 0.014], fill=out)
        d.ellipse([hx - s * 0.025, hy - s * 0.1, hx + s * 0.025, hy - s * 0.05], fill=(250, 200, 40, 255), outline=out, width=max(1, ow // 2))
    elif shape == "tusk":
        # 大柄な竜。顎の両側の斧の刃のような牙、胸から腹の黒い鎧、太い脚
        hx, hy = cx, foot_y - s * 0.74
        for sgn in (-1, 1):
            d.ellipse([cx + sgn * s * 0.13 - s * 0.09, foot_y - s * 0.22, cx + sgn * s * 0.13 + s * 0.09, foot_y],
                      fill=(*body, 255), outline=out, width=ow)
        d.ellipse([cx - s * 0.22, foot_y - s * 0.62, cx + s * 0.22, foot_y - s * 0.1], fill=(*body, 255), outline=out, width=ow)
        d.ellipse([cx - s * 0.12, foot_y - s * 0.52, cx + s * 0.12, foot_y - s * 0.16], fill=(40, 44, 36, 255))
        for k in range(3):
            yy = foot_y - s * (0.45 - k * 0.1)
            d.line([(cx - s * 0.1, yy), (cx + s * 0.1, yy)], fill=(70, 74, 60, 255), width=max(2, ow // 2))
        for sgn in (-1, 1):  # 腕
            d.line([(cx + sgn * s * 0.2, foot_y - s * 0.5), (cx + sgn * s * 0.3, foot_y - s * 0.32)], fill=out, width=int(s * 0.09))
            d.line([(cx + sgn * s * 0.2, foot_y - s * 0.5), (cx + sgn * s * 0.3, foot_y - s * 0.32)], fill=(*body, 255), width=int(s * 0.065))
        for sgn in (-1, 1):  # 斧の牙（黒い柄＋赤い刃）
            bx, by = hx + sgn * s * 0.1, hy + s * 0.1
            tip = (bx + sgn * s * 0.25, by - s * 0.1)
            leaf((bx, by), tip, s * 0.055, (30, 30, 30, 255), -0.1 * sgn)
            leaf((tip[0] - sgn * s * 0.06, tip[1] + s * 0.03), (tip[0] + sgn * s * 0.04, tip[1] + s * 0.16), s * 0.045, (*acc, 255), 0.0)
        d.ellipse([hx - s * 0.15, hy - s * 0.16, hx + s * 0.15, hy + s * 0.15], fill=(*body, 255), outline=out, width=ow)
        d.ellipse([hx - s * 0.09, hy + s * 0.02, hx + s * 0.09, hy + s * 0.13], fill=(150, 136, 46, 255))
        for sgn in (-1, 1):
            d.polygon([(hx + sgn * s * 0.03, hy - s * 0.05), (hx + sgn * s * 0.12, hy - s * 0.09), (hx + sgn * s * 0.1, hy - s * 0.01)],
                      fill=(220, 30, 30, 255))
        leaf((hx, hy - s * 0.13), (hx, hy - s * 0.32), s * 0.04, (*body, 255), 0.0)
    else:
        hx, hy = cx, foot_y - s * 0.45
        d.ellipse([cx - s * 0.26, foot_y - s * 0.6, cx + s * 0.26, foot_y], fill=(*body, 255), outline=out, width=ow)
        for sgn in (-1, 1):
            d.polygon([(cx + sgn * s * 0.08, foot_y - s * 0.56), (cx + sgn * s * 0.22, foot_y - s * 0.8),
                       (cx + sgn * s * 0.22, foot_y - s * 0.5)], fill=(*body, 255), outline=out, width=ow)
        _text(d, (int(cx), int(foot_y - s * 0.3)), "？", int(s * 0.3), (255, 255, 255), stroke=ow, stroke_fill=out[:3])
    if flip:
        lay = lay.transpose(Image.FLIP_LEFT_RIGHT)
        # 反転は画像全体なので、中心を戻す
        shift = int(2 * cx - img.size[0])
        moved = Image.new("RGBA", img.size, (0, 0, 0, 0))
        moved.alpha_composite(lay, (shift, 0)) if shift >= 0 else moved.alpha_composite(lay.crop((-shift, 0, img.size[0], img.size[1])), (0, 0))
        lay = moved
    if dim:
        lay.putalpha(lay.split()[3].point(lambda v: int(v * 0.55)))
    # 足元の影
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx - s * 0.3, foot_y - s * 0.04, cx + s * 0.3, foot_y + s * 0.05], fill=(20, 30, 70, 70))
    img.alpha_composite(sh)
    img.alpha_composite(lay)


def _pk_flip(img, d, box, ctx, text, opening):
    """立場の逆転: 2 体を入れ替える円の矢印。「読まれる側」など語がある時だけ札を出す。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    names = ctx.names + ["？", "？"]
    _creature(img, x0 + W * 0.24, y0 + H * 0.78, H * 0.52, names[0], P1)
    _creature(img, x0 + W * 0.76, y0 + H * 0.78, H * 0.52, names[1], P2, flip=True)
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy, r = x0 + W * 0.5, y0 + H * 0.28, W * 0.26
    d.arc([cx - r, cy - r * 0.6, cx + r, cy + r * 0.6], 200, 340, fill=(230, 60, 50), width=16 * SS)
    _arrow(d, (cx + r * math.cos(math.radians(330)), cy + r * 0.6 * math.sin(math.radians(330))),
           (cx + r * math.cos(math.radians(342)), cy + r * 0.6 * math.sin(math.radians(342))), (230, 60, 50), 16 * SS, 50 * SS)
    d.arc([cx - r, cy - r * 0.6 + H * 0.16, cx + r, cy + r * 0.6 + H * 0.16], 20, 160, fill=(60, 120, 230), width=16 * SS)
    _arrow(d, (cx + r * math.cos(math.radians(150)), cy + H * 0.16 + r * 0.6 * math.sin(math.radians(150))),
           (cx + r * math.cos(math.radians(162)), cy + H * 0.16 + r * 0.6 * math.sin(math.radians(162))), (60, 120, 230), 16 * SS, 50 * SS)
    lab = "読まれる側に" if "読まれる" in text else "逆転"
    _text(d, (int(cx), int(y0 + H * 0.1)), lab, _fit_size(lab, W * 0.8, int(84 * SS)), (230, 60, 50), stroke=7 * SS,
          stroke_fill=(255, 255, 255))


def _pk_race(img, d, box, ctx, text, opening):
    """素早さ順の行動: 速い方が先に動く（素早さの値が台本にある方を先頭に）。"""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    names = ctx.names + ["？", "？"]
    fast = names[0]
    for nm in ctx.names:
        if re.search(re.escape(nm), text) and re.search(r"素早さ|速", text):
            fast = nm
    slow = names[1] if fast == names[0] else names[0]
    _text(d, (int(x0 + W * 0.5), int(y0 + H * 0.07)), "行動の順番（素早さ順）", int(50 * SS), NAVY)
    for k, (nm, col, frac) in enumerate(((fast, P1 if fast == names[0] else P2, 0.86), (slow, P2 if fast == names[0] else P1, 0.42))):
        lane = y0 + H * (0.5 + 0.42 * k)
        d.line([(x0 + W * 0.04, lane), (x1 - W * 0.04, lane)], fill=(200, 208, 228), width=6 * SS)
        px = x0 + W * (0.08 + 0.8 * frac)
        for j in range(4):  # スピード線
            yy = lane - H * (0.24 - j * 0.05)
            d.line([(px - W * (0.18 + 0.05 * j), yy), (px - W * 0.1, yy)], fill=(*col, 160), width=5 * SS)
        _creature(img, px - W * 0.03, lane, H * 0.36, nm, col, flip=(k == 1))
        d = ImageDraw.Draw(img, "RGBA")
        _chip(d, int(x0 + W * 0.12), int(lane - H * 0.25), f"{k + 1}番", int(40 * SS), col)
    if "先に" in text:
        _text(d, (int(x0 + W * 0.36), int(y0 + H * 0.2)), "先に殴れる？" if "殴" in text else "先に動く？",
              int(58 * SS), (230, 60, 50), stroke=6 * SS, stroke_fill=(255, 255, 255))


# ---------------------------------------------------------------------
# 質感（ホラー 2 ジャンル）: 静止したフィルム粒子・周辺減光・赤のずれ
# ---------------------------------------------------------------------
_GLITCH_KINDS = {"expunged", "roster", "ward", "number"}


def _texture(img: Image.Image, genre: str, kind: str, seed: int) -> Image.Image:
    """枠の中身に、動かない粒子・周辺減光（SCP は走査線と赤ずれ）を足す。毎フレーム変えない。"""
    try:
        import numpy as np
    except Exception:  # pragma: no cover
        return img
    w, h = img.size
    arr = np.asarray(img).astype(np.int16)
    rgb = arr[..., :3]
    rng = np.random.default_rng(seed)
    grain = rng.normal(0, 11 if genre == "scp" else 9, (h, w, 1)).astype(np.int16)
    rgb = rgb + grain
    yy, xx = np.mgrid[0:h, 0:w]
    dx = (xx - w / 2) / (w / 2)
    dy = (yy - h / 2) / (h / 2)
    vig = np.clip((dx * dx + dy * dy) ** 1.2 * (0.55 if genre == "yokai" else 0.42), 0, 0.8)
    rgb = (rgb * (1 - vig[..., None])).astype(np.int16)
    if genre == "scp":
        rgb[::4] = (rgb[::4] * 0.88).astype(np.int16)        # 走査線
        if kind in _GLITCH_KINDS:
            # 数本の横帯だけ赤をずらす（静止）
            for _ in range(4):
                y0 = int(rng.integers(int(h * 0.1), int(h * 0.85)))
                bh = int(rng.integers(6, max(8, h // 40)))
                sh = int(rng.integers(8, 22))
                band = rgb[y0:y0 + bh].copy()
                rgb[y0:y0 + bh, sh:, 0] = band[:, :-sh, 0] + 40
                rgb[y0:y0 + bh, :, 1:] = (band[:, :, 1:] * 0.8).astype(np.int16)
    if genre == "yokai":
        # 足元の霧
        fog = np.clip((yy / h - 0.72) / 0.28, 0, 1) ** 1.5 * 38
        rgb = rgb + (fog[..., None] * np.array([0.8, 0.9, 1.1])).astype(np.int16)
    arr[..., :3] = np.clip(rgb, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def _focus(content: Image.Image, box, f, mark: str = "") -> Image.Image:
    """同じ図の「別の状態」: 注目点の外を暗くして（スポットライト）丸印と句の「？/！」を付ける。

    画を切り抜いて拡大すると図の中の文字が途中で切れて壊れて見えたので（r3 試作）、
    構図は保ったまま見る場所だけを変える。"""
    x0, y0, x1, y1 = [int(v) for v in box]
    bw, bh = x1 - x0, y1 - y0
    fx, fy, z = f
    px, py = x0 + bw * fx, y0 + bh * fy
    r = min(bw, bh) * (0.42 / max(1.0, z) + 0.06)
    out = content.copy()
    dark = Image.new("RGBA", content.size, (6, 8, 20, 170))
    hole = Image.new("L", content.size, 255)
    ImageDraw.Draw(hole).ellipse([px - r, py - r, px + r, py + r], fill=0)
    hole = hole.filter(ImageFilter.GaussianBlur(int(r * 0.12)))
    clip = Image.new("L", content.size, 0)
    ImageDraw.Draw(clip).rectangle([x0, y0, x1, y1], fill=255)
    dark.putalpha(Image.composite(hole, Image.new("L", content.size, 0), clip).point(lambda v: int(v * 0.68)))
    base = Image.new("RGBA", content.size, (0, 0, 0, 0))
    base.alpha_composite(out)
    base.alpha_composite(dark)
    d = ImageDraw.Draw(base, "RGBA")
    d.ellipse([px - r, py - r, px + r, py + r], outline=(255, 255, 255, 230), width=22 * SS)
    d.ellipse([px - r, py - r, px + r, py + r], outline=(230, 40, 40, 255), width=12 * SS)
    if mark:
        mx = x1 - bw * 0.14 if fx < 0.6 else x0 + bw * 0.14
        my = y0 + bh * 0.16 if fy > 0.4 else y1 - bh * 0.16
        _text(d, (int(mx), int(my)), mark, int(min(bw, bh) * 0.26), (230, 40, 40), stroke=10 * SS,
              stroke_fill=(255, 255, 255))
    return base


# ---------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------
_NIGHT = {"gate", "skull", "moon", "lovers", "lantern", "knock", "shoji", "pull", "contrast", "deny", "number"}

_DRAW = {
    "science": {"foot": _sci_foot, "water": _sci_water, "hose": _sci_hose, "pump": _sci_pump,
                "clock": _sci_clock, "subject": _sci_subject},
    "scp": {"pill": _scp_pill, "roster": _scp_roster, "expunged": _scp_expunged, "note": _scp_note,
            "door": _scp_door, "eye": _scp_eye, "dossier": _scp_dossier, "ward": _scp_ward,
            "classroom": _scp_classroom, "deny": _deny},
    "yokai": {"gate": _yk_gate, "skull": _yk_skull, "moon": _yk_moon, "lovers": _yk_lovers,
              "lantern": _yk_lantern, "scroll": _yk_scroll, "knock": _yk_knock, "shoji": _yk_shoji,
              "pull": _yk_pull, "contrast": _yk_contrast, "deny": _deny},
    "pokemon": {"versus": _pk_versus, "stat": _pk_stat, "priority": _pk_priority, "wall": _pk_wall,
                "flip": _pk_flip, "deny": _deny},
}


def render_panel(kind: str, text: str, ctx: PanelContext, w: int, h: int, variant: int = 0,
                 opening: bool = False, pre: bool = False) -> Image.Image:
    """w×h の素材枠（RGBA）。

    variant: 0..(_NSEM-1) は図の描き分け、それ以上は _FOCUS の寄り先（丸印付き）。
    pre=True は冒頭の「変化の前」（例: 足がまだむくんでいない／門をまだ叩いていない）。
    """
    W, H = w * SS, h * SS
    g = ctx.genre
    nsem = _NSEM.get(kind, 1)
    ctx.state = variant if variant < nsem else 0
    ctx.pre = bool(pre)
    night = g == "yokai" and kind in _NIGHT
    img, d, box = _frame(ctx, W, H, night=night)
    content = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(content, "RGBA")
    if kind == "number":
        _number(cd, box, ctx, text, opening, dark=(g == "scp" or night))
    elif kind == "deny" and g == "science":
        _deny(content, cd, box, ctx, text, opening)
    else:
        fn = _DRAW.get(g, {}).get(kind) or _DRAW[g][_FALLBACK[g]]
        try:
            if g == "science":
                fn(cd, box, ctx, text, opening)
            else:
                fn(content, cd, box, ctx, text, opening)
        except Exception as e:  # 図が壊れても動画は止めない
            print(f"⚠️ short_panels: {g}/{kind} failed: {e}")
    if variant >= nsem and _FOCUS.get(kind):
        f = _FOCUS[kind][(variant - nsem) % len(_FOCUS[kind])]
        mark = "？" if ("？" in text or "?" in text) else ("！" if ("！" in text or "!" in text) else "")
        content = _focus(content, box, f, mark)
    elif variant >= nsem:
        # 寄り先の無い図: 中身の中央 80% を箱いっぱいに
        content = _focus(content, box, (0.5, 0.5, 1.0))
    # 中身は箱の内側だけに見せる
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    clipped = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    clipped.paste(content, (0, 0), Image.composite(content.split()[3], Image.new("L", (W, H), 0), mask))
    img.alpha_composite(clipped)
    if g == "scp":
        # 札とテープは中身より手前
        dd = ImageDraw.Draw(img, "RGBA")
        _stripes(dd, (0, 0, W, 30 * SS))
    out = img.resize((w, h), Image.LANCZOS)
    if g in ("scp", "yokai"):
        seed = sum(ord(c) for c in f"{kind}{variant}{text}") % 100000
        out = _texture(out, g, kind, seed)
    return out
