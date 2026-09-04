#!/usr/bin/env python3
"""
サムネ v4.1 一括生成 — リコ＆マコトのゆっくり日常科学 既存26本ぶん

gen_thumbs_v4.py と同じ方式（gpt-image-1 で文字込みの一枚絵を 1536x1024 生成 →
上寄せ 16:9 クロップ → 1280x720）。プロンプト構造も v4.1 をそのまま踏襲し、
テーマだけ26本へ拡張した。

v4.1 との差分は「テーマ表の書き方」だけ:
  v4 は line1/line2 の chars を手書きしていたが、26本×2行=52行を手書きすると
  取りこぼしが出るので、注釈つき文字列から chars を機械生成する方式にした。
      "な ぜ 止[to] め ら れ な い ？"
  → 空白区切りの1トークン=1文字。カナは表から自動、漢字は [読み] を明示。

使い方:
    python3 gen_thumbs_v4_all.py            # 26本すべて
    python3 gen_thumbs_v4_all.py 1-5        # 1〜5番だけ（バッチ実行用）
    python3 gen_thumbs_v4_all.py 7 19       # 7番と19番だけ再生成
    python3 gen_thumbs_v4_all.py --list     # 一覧だけ出して終了（API を叩かない）
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent

# ── 画像生成は ChatGPT のブラウザスレッド経由（OpenAI API 直叩きはしない） ──
# ユーザーが同じスレッドを開いてプロンプトを直せることが必須要件のため。
# 手順: docs/CHATGPT_IMAGE_BRIDGE.md
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import chatgpt_image_bridge as _bridge  # noqa: E402

OUT_DIR = ROOT / "output" / "daily-science" / "thumbnails" / "v4_all"
ENV_PATH = ROOT / "backend" / ".env"

MODEL = "gpt-image-1"
GEN_SIZE = "1536x1024"          # 3:2
FINAL_SIZE = (1280, 720)        # 16:9
TOP_CUT_RATIO = 0.35            # 余剰高さのうち上から捨てる割合（残り0.65を下から）
TIMEOUT = 600
MAX_RETRIES = 3


# --------------------------------------------------------------------------
# 文字注釈 — 「1トークン=1文字」を gpt-image-1 に読み上げさせるための展開表
# --------------------------------------------------------------------------
_HIRA = {
    "あ": "A", "い": "I", "う": "U", "え": "E", "お": "O",
    "か": "KA", "き": "KI", "く": "KU", "け": "KE", "こ": "KO",
    "さ": "SA", "し": "SHI", "す": "SU", "せ": "SE", "そ": "SO",
    "た": "TA", "ち": "CHI", "つ": "TSU", "て": "TE", "と": "TO",
    "な": "NA", "に": "NI", "ぬ": "NU", "ね": "NE", "の": "NO",
    "は": "HA", "ひ": "HI", "ふ": "FU", "へ": "HE", "ほ": "HO",
    "ま": "MA", "み": "MI", "む": "MU", "め": "ME", "も": "MO",
    "や": "YA", "ゆ": "YU", "よ": "YO",
    "ら": "RA", "り": "RI", "る": "RU", "れ": "RE", "ろ": "RO",
    "わ": "WA", "を": "WO", "ん": "N",
}
_HIRA_DAKU = {
    "が": "GA", "ぎ": "GI", "ぐ": "GU", "げ": "GE", "ご": "GO",
    "ざ": "ZA", "じ": "JI", "ず": "ZU", "ぜ": "ZE", "ぞ": "ZO",
    "だ": "DA", "ぢ": "DJI", "づ": "DZU", "で": "DE", "ど": "DO",
    "ば": "BA", "び": "BI", "ぶ": "BU", "べ": "BE", "ぼ": "BO",
}
_HIRA_HANDAKU = {"ぱ": "PA", "ぴ": "PI", "ぷ": "PU", "ぺ": "PE", "ぽ": "PO"}
_HIRA_SMALL = {
    "ぁ": "A", "ぃ": "I", "ぅ": "U", "ぇ": "E", "ぉ": "O",
    "ゃ": "YA", "ゅ": "YU", "ょ": "YO", "っ": "TSU",
}

_KATA = {
    "ア": "A", "イ": "I", "ウ": "U", "エ": "E", "オ": "O",
    "カ": "KA", "キ": "KI", "ク": "KU", "ケ": "KE", "コ": "KO",
    "サ": "SA", "シ": "SHI", "ス": "SU", "セ": "SE", "ソ": "SO",
    "タ": "TA", "チ": "CHI", "ツ": "TSU", "テ": "TE", "ト": "TO",
    "ナ": "NA", "ニ": "NI", "ヌ": "NU", "ネ": "NE", "ノ": "NO",
    "ハ": "HA", "ヒ": "HI", "フ": "FU", "ヘ": "HE", "ホ": "HO",
    "マ": "MA", "ミ": "MI", "ム": "MU", "メ": "ME", "モ": "MO",
    "ヤ": "YA", "ユ": "YU", "ヨ": "YO",
    "ラ": "RA", "リ": "RI", "ル": "RU", "レ": "RE", "ロ": "RO",
    "ワ": "WA", "ヲ": "WO", "ン": "N", "ー": None,   # 長音符は個別処理
}
_KATA_DAKU = {
    "ガ": "GA", "ギ": "GI", "グ": "GU", "ゲ": "GE", "ゴ": "GO",
    "ザ": "ZA", "ジ": "JI", "ズ": "ZU", "ゼ": "ZE", "ゾ": "ZO",
    "ダ": "DA", "ヂ": "DJI", "ヅ": "DZU", "デ": "DE", "ド": "DO",
    "バ": "BA", "ビ": "BI", "ブ": "BU", "ベ": "BE", "ボ": "BO",
}
_KATA_HANDAKU = {"パ": "PA", "ピ": "PI", "プ": "PU", "ペ": "PE", "ポ": "PO"}
_KATA_SMALL = {
    "ァ": "A", "ィ": "I", "ゥ": "U", "ェ": "E", "ォ": "O",
    "ャ": "YA", "ュ": "YU", "ョ": "YO", "ッ": "TSU",
}

_DIGITS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

_SYMBOLS = {
    "？": "？ (full-width question mark)",
    "?": "? (question mark)",
    "%": "% (percent sign)",
    "！": "！ (full-width exclamation mark)",
    "ー": "ー (katakana long-vowel bar, a single horizontal stroke)",
    "・": "・ (katakana middle dot)",
}


def describe_char(ch: str, reading: str | None) -> str:
    """1文字を gpt-image-1 向けの説明に展開する。"""
    if ch in _SYMBOLS:
        return _SYMBOLS[ch]
    if ch in _DIGITS:
        return f"{ch} (the numeral {_DIGITS[ch]})"
    if ch in _HIRA:
        return f"{ch} (hiragana {_HIRA[ch]}, normal full size)"
    if ch in _HIRA_DAKU:
        return f"{ch} (hiragana {_HIRA_DAKU[ch]} with dakuten)"
    if ch in _HIRA_HANDAKU:
        return f"{ch} (hiragana {_HIRA_HANDAKU[ch]} with handakuten)"
    if ch in _HIRA_SMALL:
        return (f"{ch} (SMALL hiragana {_HIRA_SMALL[ch]} — draw it at about 60% the "
                f"height of the neighbouring characters, sitting low on the baseline)")
    if ch in _KATA and _KATA[ch]:
        return f"{ch} (katakana {_KATA[ch]}, normal full size)"
    if ch in _KATA_DAKU:
        return f"{ch} (katakana {_KATA_DAKU[ch]} with dakuten)"
    if ch in _KATA_HANDAKU:
        return f"{ch} (katakana {_KATA_HANDAKU[ch]} with handakuten)"
    if ch in _KATA_SMALL:
        return (f"{ch} (SMALL katakana {_KATA_SMALL[ch]} — draw it at about 60% the "
                f"height of the neighbouring characters, sitting low on the baseline)")
    if reading:
        return f"{ch} (kanji {reading})"
    raise ValueError(f"読みが指定されていない文字: {ch!r}")


def parse_line(spec: str) -> tuple[str, str]:
    """注釈つき文字列 → (プレーンな本文, chars 説明文)。

    例: "な ぜ 止[to] め ？"  →  ("なぜ止め？", "な (hiragana NA, ...), ぜ (...), ...")
    """
    text_parts: list[str] = []
    desc_parts: list[str] = []
    for token in spec.split():
        if "[" in token:
            ch, _, rest = token.partition("[")
            reading = rest.rstrip("]")
        else:
            ch, reading = token, None
        if len(ch) != 1:
            raise ValueError(f"1トークンは1文字でなければならない: {token!r}")
        text_parts.append(ch)
        desc_parts.append(describe_char(ch, reading))
    return "".join(text_parts), ", ".join(desc_parts)


# --------------------------------------------------------------------------
# 色の言い回し（v4.1 の「SOLID fill・黒アウトライン・白キーライン・グロー禁止」を固定）
# --------------------------------------------------------------------------
SUB_COLOR = (
    "pure white letters with a thin black outline and a soft dark drop shadow, "
    "solidly filled in, never glowing"
)


def hero_color(name: str, hexcode: str, extra: str = "") -> str:
    base = (
        f"solid flat vivid {name} ({hexcode}), fully saturated and completely filled "
        f"in like flat poster paint, wrapped in a THICK hard black outline with a thin "
        f"crisp white keyline around that. These characters must NOT glow, must NOT be "
        f"soft-edged, must NOT look like neon tubing — every edge is razor sharp "
        f"against its black outline"
    )
    return f"{base}. {extra}" if extra else base


ONE_ROW = (
    "All of these characters sit side by side on ONE single row — draw them narrower "
    "and smaller if needed, but never wrap them onto a second row"
)


# --------------------------------------------------------------------------
# 26本ぶんのテーマ表
# --------------------------------------------------------------------------
THEMES = [
    {
        "slug": "01_42do",
        "title": "42度の風呂は熱いのに42度の空気は熱くないのはなぜか",
        "line1_spec": "風[fu] 呂[ro] と 空[kuu] 気[ki] の 差[sa]",
        "line2_spec": "4 2 度[do]",
        "line2_color": hero_color("orange-red", "#FF4A1C"),
        "bg": (
            "a dark scorched background lit by a hot glow rising from behind the "
            "lettering: a smooth gradient from a fierce orange-red core out through deep "
            "maroon to near-black at the corners. Low in the frame, a dim bathtub filled "
            "with steaming dark water, with thick curls of steam rising and dissolving, "
            "and beside it a darkened mercury thermometer whose red column stands high. "
            "Scattered sparsely around the outer edges, a small handful of simple dim "
            "icons: two or three tiny thermometer shapes, a few small steam wisps and a "
            "couple of little water droplets, drawn thin and low-contrast. No bright "
            "bathroom, no cheerful spa mood, no daylight, and the decoration must stay "
            "far dimmer than the text."
        ),
    },
    {
        "slug": "02_haranooto",
        "title": "お腹の音はなぜ止められないのか",
        "line1_spec": "な ぜ 止[to] め ら れ な い ？",
        "line2_spec": "腹[hara] の 音[oto]",
        "line2_color": hero_color("grass green", "#3BE05A"),
        "bg": (
            "a dark olive-black background lit by one green glow blooming from behind the "
            "lettering: a smooth gradient from luminous green at the centre out to deep "
            "black-green at the corners. Behind and below the lettering, a dim anatomical "
            "silhouette of a stomach and coiled intestines drawn in thin glowing lines, "
            "with concentric sound rings rippling outward from it. Scattered sparsely "
            "around the outer edges, a small handful of simple dim icons: two or three "
            "concentric sound-wave arcs, a tiny empty plate, a small clock face and a "
            "couple of little gas bubbles, drawn thin and low-contrast. No food "
            "photography, no bright kitchen, no cute cartoon organs, and the decoration "
            "must stay far dimmer than the text."
        ),
    },
    {
        "slug": "03_yumekioku",
        "title": "夢はなぜ昨日の記憶ばかり選ぶのか",
        "line1_spec": "な ぜ 昨[saku] 日[jitsu] だ け ？",
        "line2_spec": "夢[yume] の 記[ki] 憶[oku]",
        "line2_color": hero_color("electric purple", "#B45CFF"),
        "bg": (
            "a deep violet-black background lit by a soft nebula glow behind the "
            "lettering: a smooth gradient from luminous purple at the centre out through "
            "indigo to near-black at the corners. Below the lettering, the darkened "
            "profile of a sleeping head on a pillow, with torn fragments of memory — "
            "faint half-dissolved images — drifting up and out of it and breaking apart "
            "into motes. Scattered sparsely around the outer edges, a small handful of "
            "simple dim icons: a thin crescent moon, three or four small stars and a "
            "couple of tiny film frames, drawn thin and low-contrast. No cute dreamscape, "
            "no pastel clouds, no rainbow, and the decoration must stay far dimmer than "
            "the text."
        ),
    },
    {
        "slug": "04_yorusumaho",
        "title": "夜スマホで眠れなくなる本当の原因",
        "line1_spec": "犯[han] 人[nin] は 別[betsu] に い た",
        "line2_spec": "夜[yoru] ス マ ホ",
        "line2_color": hero_color("electric blue", "#2E8BFF"),
        "bg": (
            "a near-black bedroom lit from one point only: a cold blue phone screen "
            "glowing up from low in the frame, throwing a hard blue wash across the dark "
            "and falling off to pure black at the corners. A darkened hand holds that "
            "phone in the lower area, and the dim outline of a bed and a rumpled duvet "
            "recedes into shadow behind it. Scattered sparsely around the outer edges, a "
            "small handful of simple dim icons: a thin crescent moon, a small clock face "
            "reading late, two or three tiny Z shapes and a little pillow, drawn thin and "
            "low-contrast. No warm lamp light, no cosy mood, no daylight, and the "
            "decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "05_curtain",
        "title": "シャワーカーテンはなぜ体に張り付いてくるのか",
        "line1_spec": "空[kuu] 気[ki] の 流[naga] れ が 原[gen] 因[in]",
        "line2_spec": "張[ha] り 付[tsu] く",
        "line2_color": hero_color("electric cyan", "#22E5FF"),
        "bg": (
            "a dark bathroom lit by one cold cyan light behind the lettering: a smooth "
            "gradient from pale glowing cyan at the centre out to near-black at the "
            "corners. Below the lettering, a plastic shower curtain billows sharply "
            "inward in deep folds, caught in that light, with a fine spray of water "
            "falling past it and thin curved arrows tracing the air being pulled inward. "
            "Scattered sparsely around the outer edges, a small handful of simple dim "
            "icons: two or three small water droplets, a tiny shower head and a couple of "
            "thin curved flow arrows, drawn thin and low-contrast. No bright tiled "
            "bathroom, no steam fog washing out the frame, no people, and the decoration "
            "must stay far dimmer than the text."
        ),
    },
    {
        "slug": "06_mieno",
        "title": "脳は自分を3割増しで評価している",
        "line1_spec": "な ぜ 盛[mo] る ？",
        "line2_spec": "見[mi] 栄[e] の 脳[nou]",
        "line2_color": hero_color("rich gold", "#FFC21A"),
        "bg": (
            "a dark bronze-black background lit by a warm golden glow behind the "
            "lettering: a smooth gradient from luminous gold at the centre out through "
            "deep brown to near-black at the corners. Below the lettering, a darkened "
            "human head in profile faces a dim mirror, and the reflection in the mirror is "
            "drawn noticeably grander and brighter than the head itself, with a faint "
            "glowing brain shape inside the skull. Scattered sparsely around the outer "
            "edges, a small handful of simple dim icons: a small crown, a thin upward "
            "arrow, two or three tiny sparkle marks and a little mirror frame, drawn thin "
            "and low-contrast. No luxury photography, no cheerful portrait, and the "
            "decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "07_souzoku",
        "title": "仲の良い家族ほど相続でもめる脳科学的な理由",
        "line1_spec": "脳[nou] 科[ka] 学[gaku] が 暴[aba] く",
        "line2_spec": "相[sou] 続[zoku]",
        "line2_color": hero_color("deep blood red", "#E01B2E"),
        "bg": (
            "a dark, heavy background lit by one cold hard light behind the lettering: a "
            "smooth gradient from dim grey-red at the centre out to near-black at the "
            "corners, with a strong vignette. Below the lettering, the silhouettes of "
            "several family members stand in a row and a jagged crack splits the ground "
            "and the air between them, widening as it rises. A dim legal document and a "
            "small house outline sit low in the shadow. Scattered sparsely around the "
            "outer edges, a small handful of simple dim icons: a small pair of scales, a "
            "thin document sheet, a tiny house and a couple of crack lines, drawn thin and "
            "low-contrast. No smiling family photo, no warm light, no gore, and the "
            "decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "08_yubipaki",
        "title": "指をパキッと鳴らすと快感物質が出ている",
        "line1_spec": "快[kai] 感[kan] 物[bus] 質[shitsu] 放[hou] 出[shutsu]",
        "line2_spec": "指[yubi] パ キ",
        "line2_color": hero_color("electric lime", "#B6FF1A"),
        "bg": (
            "a dark charcoal background lit by a sharp lime-green burst behind the "
            "lettering: a smooth gradient from bright yellow-green at the centre out to "
            "near-black at the corners. Below the lettering, a darkened close-up of a "
            "hand mid-knuckle-crack, with one hard ring of light snapping outward from the "
            "joint and a dim cutaway of the joint capsule showing a gas bubble collapsing "
            "inside it. Scattered sparsely around the outer edges, a small handful of "
            "simple dim icons: three or four small bubble circles, two concentric impact "
            "rings and a tiny hand outline, drawn thin and low-contrast. No gore, no "
            "medical photography, no bright clinic, and the decoration must stay far "
            "dimmer than the text."
        ),
    },
    {
        "slug": "09_ongakunamida",
        "title": "音楽で涙が出るのはなぜか",
        "line1_spec": "な ぜ 涙[namida] が 出[de] る ？",
        "line2_spec": "音[on] 楽[gaku] と 涙[namida]",
        "line2_color": hero_color("hot pink", "#FF3D8B"),
        "bg": (
            "a dark plum-black background lit by a soft rose glow behind the lettering: a "
            "smooth gradient from luminous pink at the centre out through deep magenta to "
            "near-black at the corners. Below the lettering, a darkened profile of a face "
            "in shadow wearing headphones, a single tear catching the light on the cheek, "
            "and a dim sound waveform running horizontally low across the frame. Scattered "
            "sparsely around the outer edges, a small handful of simple dim icons: three "
            "or four small musical notes, a thin waveform segment and a couple of tiny "
            "droplet shapes, drawn thin and low-contrast. No concert crowd, no bright "
            "stage lights, no cute cartoon hearts, and the decoration must stay far dimmer "
            "than the text."
        ),
    },
    {
        "slug": "10_akubi",
        "title": "あくびはなぜうつるのか",
        "line1_spec": "な ぜ う つ る ？",
        "line2_spec": "あ く び",
        "line2_color": hero_color("golden yellow", "#FFD426"),
        "bg": (
            "a dark navy-black background lit by a warm yellow glow behind the lettering: "
            "a smooth gradient from luminous yellow at the centre out to near-black at the "
            "corners. Below the lettering, two darkened head silhouettes face each other, "
            "both mid-yawn, with concentric ripple rings spreading from the first one to "
            "the second like a contagion passing between them. Scattered sparsely around "
            "the outer edges, a small handful of simple dim icons: three or four small Z "
            "shapes, two concentric ripple rings and a tiny clock face, drawn thin and "
            "low-contrast. No cartoon faces, no cute mascots, no bright daytime scene, and "
            "the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "11_suitsuku",
        "title": "シャワーカーテンが吸い付く物理現象",
        "line1_spec": "意[i] 外[gai] な 物[butsu] 理[ri] 現[gen] 象[shou]",
        "line2_spec": "吸[su] い 付[tsu] く",
        "line2_color": hero_color("aqua", "#3DF0D0"),
        "bg": (
            "a dark slate background lit by one aqua-green light from the upper left, well "
            "clear of the lettering: a smooth gradient from pale glowing aqua out to "
            "near-black at the corners, the area directly behind the text kept deep and "
            "dark. Below the lettering, tall vertical folds of a shower curtain sweep "
            "inward and a dim spiral of low-pressure air swirls behind them, traced by "
            "thin curved arrows. Scattered sparsely around the outer edges, a small "
            "handful of simple dim icons: two or three thin swirl arrows, a couple of "
            "small pressure-gauge circles and a tiny droplet, drawn thin and low-contrast. "
            "No bright bathroom, no white steam haze, no washed-out areas, and the "
            "decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "12_mizutamari",
        "title": "水たまりの水は普通の水ではない",
        "line1_spec": "た だ の 水[mizu] で は な い",
        "line2_spec": "水[mizu] た ま り",
        "line2_color": hero_color("bright teal", "#1FD6C2"),
        "bg": (
            "a dark wet-asphalt background at night, lit by one teal reflection glowing "
            "from a puddle low in the frame: a smooth gradient from luminous teal near the "
            "puddle out to near-black at the corners. The puddle sits on cracked dark road "
            "surface, mirroring a dim streetlight, with a faint low-saturation oil sheen "
            "curling across its surface and a few slow ripple rings. Scattered sparsely "
            "around the outer edges, a small handful of simple dim icons: two or three "
            "small droplet shapes, a couple of concentric ripple rings and a tiny leaf, "
            "drawn thin and low-contrast. No rainbow explosion, no bright street scene, no "
            "daylight, and the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "13_sanso",
        "title": "地球から酸素が1秒だけ消えたら何が起きるか",
        "line1_spec": "想[sou] 像[zou] 以[i] 上[jou] の 危[ki] 機[ki]",
        "line2_spec": "酸[san] 素[so] 消[shou] 滅[metsu]",
        "line2_color": hero_color("alarm red", "#FF1F2E"),
        "bg": (
            "a near-black apocalyptic background lit by one dying red glow low behind the "
            "lettering: a smooth gradient from deep ember-red at the horizon out to pure "
            "black at the top corners. Below the lettering, a darkened city skyline stands "
            "against a sky drained to blackness, with concrete buildings crumbling at the "
            "edges and dust falling in thin veils. Scattered sparsely around the outer "
            "edges, a small handful of simple dim icons: a small two-atom molecule symbol, "
            "two or three crumbling brick fragments and a thin dimmed sun disc, drawn thin "
            "and low-contrast. No fire, no explosion, no blue sky, no people, and the "
            "decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "14_mewarui",
        "title": "暗い部屋でスマホを見ると目が悪くなる本当の理由",
        "line1_spec": "原[gen] 因[in] は 別[betsu] に あ る",
        "line2_spec": "目[me] が 悪[waru] い",
        "line2_color": hero_color("emerald green", "#1FE38A"),
        "bg": (
            "a near-black room lit by one cold emerald-green glow behind the lettering: a "
            "smooth gradient from luminous green at the centre out to pure black at the "
            "corners. Below the lettering, an extreme close-up of a single human eye sits "
            "half in shadow, its pupil blown wide, with a small rectangular screen "
            "reflected in the iris. Thin dim lines trace the eye's focusing muscle "
            "straining. Scattered sparsely around the outer edges, a small handful of "
            "simple dim icons: a small pair of glasses, two or three thin focus-ring "
            "circles and a tiny lightbulb, drawn thin and low-contrast. No medical "
            "photography, no bright clinic, no gore, and the decoration must stay far "
            "dimmer than the text."
        ),
    },
    {
        "slug": "15_seiza",
        "title": "同じ星並びなのに星座の形が国で違う理由",
        "line1_spec": "文[bun] 化[ka] で 変[ka] わ る",
        "line2_spec": "星[hoshi] 座[za]",
        "line2_color": hero_color("rich gold", "#FFC91F",
                                  "The two characters sit against deep navy so the gold "
                                  "cuts hard against it"),
        "bg": (
            "a deep navy night-sky background, darkest at the corners and lifting to a "
            "faint luminous navy-blue behind the lettering. Scattered stars of varying "
            "brightness fill the sky, and below the lettering the same cluster of stars is "
            "joined twice by thin gold constellation lines into two clearly different "
            "figures, side by side, showing two cultures reading the same sky differently. "
            "Scattered sparsely around the outer edges, a small handful of simple dim "
            "icons: four or five tiny star points, a small compass rose and a thin rolled "
            "scroll, drawn thin and low-contrast. No cartoon zodiac characters, no bright "
            "nebula colours, no daylight, and the decoration must stay far dimmer than the "
            "text."
        ),
    },
    {
        "slug": "16_amenohi",
        "title": "雨の日に気分が沈むのはなぜか",
        "line1_spec": "な ぜ 気[ki] 分[bun] が 沈[shizu] む ？",
        "line2_spec": "雨[ame] の 日[hi]",
        "line2_color": hero_color("cold steel blue", "#6FA8D6"),
        "bg": (
            "a dark grey-blue background lit by one flat dim light behind the lettering: a "
            "smooth gradient from muted slate-blue at the centre out to near-black at the "
            "corners, deliberately heavy and low-key. Below the lettering, rain streaks "
            "run down a dark window pane and a darkened human silhouette sits slumped "
            "behind it, shoulders low, seen only in outline. Scattered sparsely around the "
            "outer edges, a small handful of simple dim icons: a small umbrella, a thin "
            "rain cloud and three or four little raindrops, drawn thin and low-contrast. "
            "No cheerful rainy-day illustration, no bright colours, no rainbow, and the "
            "decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "17_mizunazo",
        "title": "水たまりの謎を科学で解明する",
        "line1_spec": "科[ka] 学[gaku] で 解[kai] 明[mei]",
        "line2_spec": "水[mizu] の 謎[nazo]",
        "line2_color": hero_color("blue-green", "#20C9A0"),
        "bg": (
            "a dark background lit by one blue-green glow rising from a puddle low in the "
            "frame: a smooth gradient from luminous blue-green near the water out to "
            "near-black at the corners. Below the lettering, a dark puddle on wet ground "
            "is being examined — a dim magnifying-glass ring hovers over part of it and "
            "thin analysis lines and tick marks are drawn over the water surface like a "
            "diagram. A few slow ripple rings spread outward. Scattered sparsely around "
            "the outer edges, a small handful of simple dim icons: a small magnifier, two "
            "or three droplet shapes and a thin test-tube outline, drawn thin and "
            "low-contrast. No bright laboratory, no daylight, no cartoon detective, and "
            "the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "18_hoshizora",
        "title": "都会で星空が見えなくなった理由",
        "line1_spec": "な ぜ 見[mi] え な い ？",
        "line2_spec": "星[hoshi] 空[zora]",
        "line2_color": hero_color("pure white", "#FFFFFF",
                                  "Because these characters are white, their black "
                                  "outline must be extra thick and the sky directly "
                                  "behind them must stay deep dark blue, never bright"),
        "bg": (
            "a deep dark-blue night sky that is being eaten from below by a dirty orange "
            "city glow: a gradient from near-black at the top corners down to a murky "
            "amber haze along the bottom edge. Only a handful of faint stars survive in "
            "the upper sky and they thin out to nothing as the glow rises. Low in the "
            "frame, a darkened city skyline and one bright streetlamp throw that light "
            "upward. Scattered sparsely around the outer edges, a small handful of simple "
            "dim icons: three or four tiny star points, a small streetlamp and a thin "
            "telescope outline, drawn thin and low-contrast. No milky way spectacle, no "
            "bright nebula, no daylight, and the decoration must stay far dimmer than the "
            "text."
        ),
    },
    {
        "slug": "19_kansetsu",
        "title": "指をポキポキ鳴らし続けた60年の実験",
        "line1_spec": "6 0 年[nen] の 実[jik] 験[ken]",
        "line2_spec": "関[kan] 節[setsu] の 音[oto]",
        "line2_color": hero_color("lime green", "#8CE81F"),
        "bg": (
            "a dark charcoal-black background lit by one cool green-white light behind the "
            "lettering: a smooth gradient from pale glowing green at the centre out to "
            "near-black at the corners. Below the lettering, an X-ray style view of a hand "
            "shows the finger bones and joint gaps glowing faintly, with one knuckle "
            "highlighted. Beside it, a dim stack of calendar pages suggests decades "
            "passing. Scattered sparsely around the outer edges, a small handful of simple "
            "dim icons: a small calendar sheet, two or three bubble circles and a thin "
            "bone-joint outline, drawn thin and low-contrast. No medical photography, no "
            "gore, no bright clinic, and the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "20_amenonioi",
        "title": "雨が降る前のあの匂いの正体",
        "line1_spec": "あ の 匂[nio] い の 正[shou] 体[tai]",
        "line2_spec": "雨[ame] の 匂[nio] い",
        "line2_color": hero_color("earthy green", "#6FD13B"),
        "bg": (
            "a dark earth-brown and black background lit by one soft green-grey glow "
            "behind the lettering: a smooth gradient from dim mossy green at the centre "
            "out to near-black at the corners. Below the lettering, the first heavy "
            "raindrops strike dark dry soil, each impact kicking up a tiny burst of "
            "aerosol, with thin scent-wave squiggles curling upward from the wet ground. "
            "Scattered sparsely around the outer edges, a small handful of simple dim "
            "icons: two or three small raindrops, a thin leaf, a couple of scent-wave "
            "squiggles and a tiny soil particle cluster, drawn thin and low-contrast. No "
            "lush green landscape, no bright daylight, no flowers, and the decoration must "
            "stay far dimmer than the text."
        ),
    },
    {
        "slug": "21_hashirenai",
        "title": "夢の中で全力で走れないのはなぜか",
        "line1_spec": "脳[nou] が 体[karada] を 止[to] め る",
        "line2_spec": "走[hashi] れ な い",
        "line2_color": hero_color("electric indigo", "#7A5CFF"),
        "bg": (
            "a deep indigo-black background lit by a cold violet glow behind the "
            "lettering: a smooth gradient from luminous indigo at the centre out to pure "
            "black at the corners, with a heavy vignette. Below the lettering, a darkened "
            "running figure is frozen mid-stride, its legs blurred and dragging as if "
            "moving through something thick, with dim chain-like lines trailing from its "
            "ankles. A faint brain outline sits above with a small closed padlock over its "
            "motor area. Scattered sparsely around the outer edges, a small handful of "
            "simple dim icons: a small padlock, two or three Z shapes and a couple of "
            "faded footprints, drawn thin and low-contrast. No horror imagery, no monster, "
            "no gore, and the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "22_shiwashiwa",
        "title": "お風呂で指がシワシワになる本当の理由",
        "line1_spec": "原[gen] 因[in] は 水[mizu] で は な い",
        "line2_spec": "シ ワ シ ワ",
        "line2_color": hero_color("water blue", "#37B8FF"),
        "bg": (
            "a dark underwater-blue background with a clear gradient: dim blue water "
            "behind the lettering falling away to near-black at the bottom corners. Below "
            "the lettering, an extreme close-up of a fingertip held under water shows deep "
            "ridged wrinkles catching the light, with small air bubbles clinging to the "
            "skin and drifting up. A thin dim nerve line runs from the fingertip up out of "
            "frame. Scattered sparsely around the outer edges, a small handful of simple "
            "dim icons: two or three small bubble circles, a thin fingerprint whorl and a "
            "couple of droplets, drawn thin and low-contrast. No bright bathroom, no milky "
            "haze, no washed-out areas, and the decoration must stay far dimmer than the "
            "text."
        ),
    },
    {
        "slug": "23_nekoyasai",
        "title": "猫がキュウリに驚く動画が億再生された裏側",
        "line1_spec": "億[oku] 再[sai] 生[sei] の 裏[ura] 側[gawa]",
        "line2_spec": "猫[neko] と 野[ya] 菜[sai]",
        "line2_color": hero_color("bright orange", "#FF8A1F"),
        "bg": (
            "a dark background lit by one warm orange glow behind the lettering: a smooth "
            "gradient from luminous orange at the centre out through deep brown to "
            "near-black at the corners. Below the lettering, a darkened cat is caught "
            "mid-leap, back arched and fur raised, twisting away from a long green "
            "vegetable lying on the dim floor behind it, its shape reading faintly like a "
            "coiled snake. Scattered sparsely around the outer edges, a small handful of "
            "simple dim icons: two or three small paw prints, a thin exclamation mark and "
            "a couple of little motion-burst lines, drawn thin and low-contrast. No cute "
            "cartoon cat, no bright kitchen, no comedy meme framing, and the decoration "
            "must stay far dimmer than the text."
        ),
    },
    {
        "slug": "24_senzai",
        "title": "洗剤とメラミンスポンジはどちらが本当に落ちるのか",
        "line1_spec": "科[ka] 学[gaku] で 比[kura] べ た",
        "line2_spec": "洗[sen] 剤[zai] 対[tai] 決[ketsu]",
        "line2_color": hero_color("icy white-blue", "#DCF3FF",
                                  "Because these characters are nearly white, their black "
                                  "outline must be extra thick and the area directly "
                                  "behind them must stay deep dark blue, never bright"),
        "bg": (
            "a dark blue-black background split down the middle into two dim halves by a "
            "single hard vertical light seam behind the lettering, the gradient falling "
            "off to near-black at both outer corners. On the left half, a darkened "
            "detergent bottle with foam curling from its cap; on the right half, a "
            "darkened white cleaning sponge block with one corner worn away — both dimly "
            "lit, facing off. Scattered sparsely around the outer edges, a small handful "
            "of simple dim icons: three or four small foam bubbles, a thin sparkle mark "
            "and a couple of tiny droplets, drawn thin and low-contrast. No bright "
            "supermarket shelf, no product-photography gloss, no brand logos or labels of "
            "any kind, and the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "25_atamanokyoku",
        "title": "頭の中で曲が延々リピートするイヤーワームの正体",
        "line1_spec": "9 8 % が 経[kei] 験[ken]",
        "line2_spec": "頭[atama] の 中[naka] の 曲[kyoku]",
        "line2_color": hero_color("magenta", "#FF2ECC", ONE_ROW),
        "bg": (
            "a dark purple-black background lit by a magenta glow behind the lettering: a "
            "smooth gradient from luminous magenta at the centre out to near-black at the "
            "corners. Below the lettering, a darkened head silhouette is seen in profile "
            "and a single ribbon of musical notes spirals endlessly around inside the "
            "skull, looping back on itself in a closed circuit. Scattered sparsely around "
            "the outer edges, a small handful of simple dim icons: three or four small "
            "musical notes, a thin circular repeat arrow and a tiny ear outline, drawn "
            "thin and low-contrast. No concert scene, no bright stage, no cartoon "
            "characters, and the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "26_canon",
        "title": "名曲に共通するカノン進行の正体",
        "line1_spec": "名[mei] 曲[kyoku] の 共[kyou] 通[tsuu] 点[ten]",
        "line2_spec": "カ ノ ン 進[shin] 行[kou]",
        "line2_color": hero_color("royal blue", "#3355FF", ONE_ROW),
        "bg": (
            "a dark navy-black background lit by one royal-blue glow behind the lettering: "
            "a smooth gradient from luminous blue at the centre out to near-black at the "
            "corners. Below the lettering, a darkened piano keyboard runs across the lower "
            "frame with a descending series of keys lit one after another in a stepping "
            "pattern, and thin dim staff lines stretch behind it with a few chord blocks "
            "stacked along them. Scattered sparsely around the outer edges, a small "
            "handful of simple dim icons: three or four small musical notes, a thin treble "
            "clef and a couple of little chord-block rectangles, drawn thin and "
            "low-contrast. No concert hall, no bright stage lights, no sheet music close-up "
            "filling the frame, and the decoration must stay far dimmer than the text."
        ),
    },
]


# --------------------------------------------------------------------------
# プロンプト構成ブロック（v4.1 をそのまま踏襲）
# --------------------------------------------------------------------------
STYLE = (
    "A YouTube thumbnail in the style of a popular Japanese science-explainer channel. "
    "Dark-based, high-impact, cinematic — but ENERGETIC and eye-catching, never a flat "
    "empty black void. The image is TEXT-FIRST: giant Japanese typography occupies "
    "roughly 60% of the visual weight and the artwork exists only to make that "
    "typography hit harder. Dark background built around ONE dominant, saturated accent "
    "colour with a clear glowing light source and a smooth colour gradient falling off "
    "to near-black in the corners. Absolutely NOT pastel, NOT cute, NOT a busy collage, "
    "NOT a cheerful anime scene."
)

DECOR = (
    "BACKGROUND ENERGY (add a little life — restrained): the frame must feel alive "
    "rather than empty. Include a visible glowing light source behind the lettering "
    "with a smooth gradient falling away to near-black at the corners, a few broad soft "
    "light rays fanning out from behind the hero line, and a light scattering of small "
    "drifting particles or motes catching that light. Add a small handful — roughly "
    "five to eight, no more — of simple, thin, low-contrast thematic icons or symbols "
    "spread around the OUTER edges and corners of the frame. Push the accent colour "
    "saturated and punchy.\n"
    "This is a SMALL dose of extra liveliness, not a redesign. All of it must stay "
    "clearly dimmer and lower-contrast than the lettering. Nothing decorative may sit "
    "behind, overlap, touch or crowd any character, or reduce the contrast between the "
    "lettering and its backing. The area immediately around the text stays clean and "
    "dark. Never let the decoration become a pattern, a texture fill, a confetti "
    "explosion or a cluttered collage, and never brighten the overall image to the "
    "point where the text stops being the first thing the eye lands on."
)

TYPOGRAPHY = (
    "TYPOGRAPHY (the single most important part of this image): draw the Japanese text "
    "below directly into the artwork as massive thumbnail lettering — extra-bold / "
    "black-weight Japanese gothic (ゴシック体) impact lettering, extremely thick "
    "strokes, no thin or delicate fonts anywhere, heavy black outline plus a strong "
    "drop shadow so it separates from the background. The lettering must be "
    "instantly readable at phone-thumbnail size. The text is baked into the "
    "composition, integrated with the lighting of the scene — it must NOT look like a "
    "flat caption bar or an HTML template pasted on top of a photo.\n"
    "Every character must be a SOLID, completely filled shape in its stated colour — "
    "never hollow, never outline-only, never a thin neon wireframe, never "
    "semi-transparent, never faded into the background. Keep the edges hard and "
    "crisp: no large soft glow, no bloom, no blur, no misty halo washing over the "
    "letters or the background. The lettering must be the brightest, highest-contrast "
    "thing in the picture. The glowing light source belongs to the BACKGROUND only — it "
    "must never spill onto the letters and turn them into soft neon; the letters keep "
    "flat solid fill and hard black edges no matter how bright the scene behind them.\n"
    "Each line is written on ONE single row. Never wrap a line, never break it onto a "
    "second row, never stack part of it underneath the rest. If a line has many "
    "characters, draw every character narrower and smaller so the whole line still fits "
    "on one row within the margins.\n"
    "Reproduce every character EXACTLY as listed, stroke for stroke, in the given "
    "order, with no extra characters inserted and none dropped or duplicated. Any "
    "character marked 'SMALL' (small kana such as ッ ャ ュ ョ) must be drawn at about "
    "60% the height of the surrounding characters and sit low on the baseline; every "
    "other character is full size. Each line is one single unbroken horizontal block "
    "of lettering — never split a line across separate banners and never scatter its "
    "characters around the picture. Beyond the two lines listed below, do NOT add any "
    "other text anywhere in the image: no extra Japanese, no English words, no extra "
    "numbers, no watermark, no logo, no signature, no captions, no writing on props."
)

PLACEMENT = (
    "TEXT PLACEMENT (obey exactly): the two lines are stacked, line 1 directly above "
    "line 2, horizontally centred, both inside the UPPER 60% of the canvas. Line 1 "
    "starts about 12% down from the top edge. The bottom of line 2 ends no lower than "
    "60% down the canvas — nothing may be written below that. Line 2 is the hero: it "
    "is at least 2.5 times the character height of line 1 and its characters are as "
    "large as the margin rules allow."
)

CHARACTER = (
    "MASCOT (small, secondary, must not compete with the text): a single small anime "
    "girl scientist — long silver-white hair in a high ponytail, aqua eyes, thin-framed "
    "round glasses, white lab coat — drawn in the BOTTOM-RIGHT corner, waist-up, dimly "
    "lit and partly in shadow so she reads as a corner accent, not a subject. Her total "
    "drawn height must be no more than one quarter of the canvas height and her head no "
    "wider than about one twelfth of the canvas width — she is a small figure tucked "
    "into the corner, not a co-star, and she must be noticeably smaller than a single "
    "character of the hero line. She must sit entirely below and to the right of the "
    "lettering and must never overlap or touch any character. She must be drawn whole "
    "and fully inside the frame — never cropped by the bottom or right edge, never "
    "bleeding off the canvas. Only ONE character in the image."
)

MARGINS = (
    "CANVAS AND MARGINS (obey strictly): the composition must be fully contained with "
    "generous empty margins. The outer 8% along the TOP edge and the outer 10% along "
    "the BOTTOM edge, plus the outer 7% along the LEFT and RIGHT edges, must contain "
    "nothing but plain dark background — no lettering, no faces, no hands, no props "
    "may touch or cross into those bands. Every single Japanese character must appear "
    "whole and fully visible with its complete shape, never cropped, never bleeding "
    "off any edge. If the text does not fit, make the characters smaller — never crop "
    "them. Each text line spans at most 80% of the canvas width, leaving at least one "
    "full character width of plain background to the left and to the right. The first "
    "and last character of every line must be fully inside the picture."
)


def build_prompt(theme: dict) -> str:
    l1_text, l1_chars = parse_line(theme["line1_spec"])
    l2_text, l2_chars = parse_line(theme["line2_spec"])
    # 4文字以上のヒーロー行は放っておくと2行に折り返される（#9 が実際に折り返した上に
    # 「と」を重複させた）ので、そこから上は必ず1行厳守の指示を足す。
    l2_color = theme["line2_color"]
    if len(l2_text) >= 4 and ONE_ROW not in l2_color:
        l2_color = f"{l2_color}. {ONE_ROW}"
    return "\n\n".join([
        STYLE,
        f"BACKGROUND / ARTWORK: {theme['bg']}",
        DECOR,
        TYPOGRAPHY,
        (
            "Text to draw:\n"
            f"LINE 1 (smaller sub-line, {SUB_COLOR}) — exactly these characters in "
            f"order: {l1_chars} → 「{l1_text}」\n"
            f"LINE 2 (THE HERO LINE, gigantic, {l2_color}) — exactly these "
            f"characters in order: {l2_chars} → 「{l2_text}」"
        ),
        PLACEMENT,
        CHARACTER,
        MARGINS,
    ])


# --------------------------------------------------------------------------
def load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""  # ChatGPT スレッド経由なのでキーは不要


def generate(prompt: str, api_key: str) -> bytes:
    """ChatGPT スレッド経由で1枚生成する。未納品なら `_bridge.Queued` を投げる。

    `api_key` は互換のため残しているが使わない（OpenAI API は叩かない）。
    """
    return _bridge.generate_or_queue(
        prompt, size=GEN_SIZE, purpose="thumbnail_v4",
    )


def crop_to_16x9(raw: bytes) -> Image.Image:
    """3:2 の生成画像を上部寄りで 16:9 に切り出して 1280x720 に縮小する。"""
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = img.size
    target_h = round(w * 9 / 16)
    if target_h >= h:                       # 念のため（横基準で切る）
        target_w = round(h * 16 / 9)
        left = (w - target_w) // 2
        img = img.crop((left, 0, left + target_w, h))
    else:
        excess = h - target_h
        top = round(excess * TOP_CUT_RATIO)  # 上 35% / 下 65% で捨てる
        img = img.crop((0, top, w, top + target_h))
    return img.resize(FINAL_SIZE, Image.LANCZOS)


def parse_selection(argv: list[str]) -> set[int]:
    """'1-5' や '7' '19' 形式の引数を番号集合にする。"""
    wanted: set[int] = set()
    for arg in argv:
        if "-" in arg and not arg.startswith("-"):
            a, _, b = arg.partition("-")
            if not (a.isdigit() and b.isdigit()):
                raise SystemExit(f"範囲指定は 1-5 の形式で: {arg!r}")
            wanted.update(range(int(a), int(b) + 1))
        elif arg.isdigit():
            wanted.add(int(arg))
        else:
            raise SystemExit(f"引数は 1-{len(THEMES)} の番号か範囲のみ: {arg!r}")
    bad = [n for n in wanted if not 1 <= n <= len(THEMES)]
    if bad:
        raise SystemExit(f"範囲外の番号: {sorted(bad)} (1-{len(THEMES)})")
    return wanted


def main() -> int:
    argv = sys.argv[1:]
    list_only = "--list" in argv
    wanted = parse_selection([a for a in argv if a != "--list"])

    if list_only:
        for i, theme in enumerate(THEMES, start=1):
            l1, _ = parse_line(theme["line1_spec"])
            l2, _ = parse_line(theme["line2_spec"])
            print(f"{i:2d}. {theme['slug']:<18} 「{l1}」/「{l2}」")
        return 0

    api_key = load_api_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = [(i, t) for i, t in enumerate(THEMES, start=1) if not wanted or i in wanted]
    failures = []
    for n, (i, theme) in enumerate(targets, start=1):
        slug = theme["slug"]
        l1_text, _ = parse_line(theme["line1_spec"])
        l2_text, _ = parse_line(theme["line2_spec"])
        prompt = build_prompt(theme)

        (OUT_DIR / f"{slug}.prompt.json").write_text(
            json.dumps(
                {
                    "index": i,
                    "title": theme["title"],
                    "line1": l1_text,
                    "line2": l2_text,
                    "model": MODEL,
                    "gen_size": GEN_SIZE,
                    "final_size": list(FINAL_SIZE),
                    "top_cut_ratio": TOP_CUT_RATIO,
                    "prompt": prompt,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"[{n}/{len(targets)}] #{i} {slug}  「{l1_text}」/「{l2_text}」", flush=True)
        try:
            img = crop_to_16x9(generate(prompt, api_key))
        except Exception as e:
            print(f"    NG: {e}", flush=True)
            failures.append((i, slug, str(e)))
            continue
        path = OUT_DIR / f"{slug}.png"
        img.save(path)
        print(f"    OK: {path.relative_to(ROOT)}  {img.size}", flush=True)

    if failures:
        print("\n失敗（この番号で再実行できる）:")
        for i, slug, err in failures:
            print(f"  - #{i} {slug}: {err}")
        print("  再実行: python3 gen_thumbs_v4_all.py " +
              " ".join(str(i) for i, _, _ in failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
