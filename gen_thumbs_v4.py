#!/usr/bin/env python3
"""
サムネ v4 生成（スタンドアロン）

方式は v3 と同じく gpt-image-1 で「文字込みの一枚絵」を生成する。
違うのはスタイル方針で、v4 は競合（化け学のふしぎ / るーいのゆっくり科学）に寄せた
「ダーク背景＋巨大テキスト主役＋キーワード色分け」型。

2026-08-27 調整（v4.1）: 初版が暗く地味だったため「少しだけ賑やかに」振った。
  - 背景を真っ黒から「光源＋グラデーション」ベースに（DECOR ブロックを追加）
  - 各テーマにテーマ由来の小アイコン／粒子を少量散らす
  - LINE2 の色を彩度・明度ともに一段ビビッドへ
  - テキスト主役（視覚重量 60%）とマスコットの小ささは維持

  1536x1024 で生成 → 上部寄りで 16:9 にクロップ → 1280x720 に縮小

既存の backend/pipeline/.../thumbnail_generator.py には一切触らない。

使い方:
    python3 gen_thumbs_v4.py            # 5本すべて
    python3 gen_thumbs_v4.py 2 4        # 2番と4番だけ再生成
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

OUT_DIR = ROOT / "output" / "daily-science" / "thumbnails" / "v4"
ENV_PATH = ROOT / "backend" / ".env"

MODEL = "gpt-image-1"
GEN_SIZE = "1536x1024"          # 3:2
FINAL_SIZE = (1280, 720)        # 16:9
TOP_CUT_RATIO = 0.35            # 余剰高さのうち上から捨てる割合（残り0.65を下から）
TIMEOUT = 600
MAX_RETRIES = 3


# --------------------------------------------------------------------------
# サムネ用テキスト設計
# --------------------------------------------------------------------------
# ルール:
#   - タイトルそのままではなく短縮・インパクト化
#   - LINE1 = 文脈を補う小さめのサブ（「？」で好奇心）
#   - LINE2 = 巨大キーワード（2-4文字中心）＋強い色
#   - chars は一文字ずつの読み上げリスト。小さいカナは明示（今回は該当なし）
THEMES = [
    {
        "slug": "01_hiyake",
        "title": "なぜ日焼けすると肌が痛むのか",
        "line1": {
            "text": "なぜ肌が痛む？",
            "chars": "な (hiragana NA), ぜ (hiragana ZE with dakuten), 肌 (kanji hada), "
                     "が (hiragana GA with dakuten), 痛 (kanji ita), む (hiragana MU), "
                     "？ (full-width question mark)",
            "color": "pure white letters with a thin black outline",
        },
        "line2": {
            "text": "日焼け",
            "chars": "日 (kanji hi), 焼 (kanji yaki), け (hiragana KE)",
            "color": "blazing vivid orange letters (#FF6A00) that graduate to hot "
                     "golden-yellow (#FFC400) toward the bottom of every stroke, fully "
                     "saturated, with a heavy black outline",
        },
        "bg": (
            "a dark scorched-red background lit by a strong glowing sun low behind the "
            "lettering: a smooth radial gradient from a hot orange-red core out to deep "
            "crimson and then to near-black at the corners. A few broad, faint heat rays "
            "radiate outward from behind the hero line, plus drifting embers and a "
            "subtle close-up of sun-reddened skin texture in the lower right, kept dim. "
            "Scattered sparsely around the outer area, a small handful of simple dim "
            "icons: a tiny sun symbol, two or three little downward UV-ray arrows and a "
            "small thermometer, drawn thin and low-contrast. No blue sky, no beach, no "
            "cheerful summer mood, and the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "02_mimi",
        "title": "なぜ耳に水が入ると音がこもって聞こえるのか？",
        "line1": {
            "text": "なぜ音がこもる？",
            "chars": "な (hiragana NA), ぜ (hiragana ZE with dakuten), 音 (kanji oto), "
                     "が (hiragana GA with dakuten), こ (hiragana KO), も (hiragana MO), "
                     "る (hiragana RU), ？ (full-width question mark)",
            "color": "pure white letters with a thin black outline",
        },
        "line2": {
            "text": "耳に水",
            "chars": "耳 (kanji mimi), に (hiragana NI), 水 (kanji mizu)",
            "color": "solid flat electric cyan (#22E5FF), fully saturated and completely "
                     "filled in like flat poster paint, wrapped in a THICK hard black "
                     "outline with a thin crisp white keyline around that. These "
                     "characters must NOT glow, must NOT be soft-edged, must NOT look "
                     "like neon tubing or backlit ice — every edge is razor sharp against "
                     "its black outline",
        },
        "bg": (
            "a deep underwater background with a clear vertical gradient: teal water at "
            "the top fading down through deep navy to near-black at the bottom corners. "
            "One shaft of cyan light angles down from the top LEFT, well clear of the "
            "lettering, and the water directly behind the text stays deep dark navy so "
            "the cyan characters cut hard against it. A single trapped water droplet and "
            "clusters of small rising air bubbles drift through the water, with a "
            "darkened silhouette of an ear in the lower left. Scattered sparsely in the "
            "outer area, a small handful of simple dim icons: two or three concentric "
            "sound-wave rings and a few tiny bubble circles, drawn thin and low-contrast. "
            "Keep the water clear and readable — no white fog, no milky haze, no glowing "
            "mist, no washed-out bright areas, no daylight, no swimming pool, and the "
            "decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "03_hana",
        "title": "なぜ鼻をつまむと味がわからなくなるのか？",
        "line1": {
            "text": "鼻をつまむと？",
            "chars": "鼻 (kanji hana), を (hiragana WO), つ (hiragana TSU, normal full "
                     "size), ま (hiragana MA), む (hiragana MU), と (hiragana TO), "
                     "？ (full-width question mark)",
            "color": "pure white letters with a thin black outline",
        },
        "line2": {
            "text": "味が消える",
            "chars": "味 (kanji aji), が (hiragana GA with dakuten), 消 (kanji kie), "
                     "え (hiragana E), る (hiragana RU)",
            "color": "vivid saturated golden-yellow letters (#FFDD22) with a heavy black "
                     "outline, the last two characters fading slightly like they are "
                     "vanishing. All five characters sit side by side on ONE single row "
                     "— draw them narrower and smaller if needed, but never wrap them "
                     "onto a second row",
        },
        "bg": (
            "a dark charcoal background lit by a warm amber glow blooming up from behind "
            "the lettering: a smooth gradient from glowing amber-orange at the centre out "
            "to deep charcoal-black at the corners. Behind the lettering, a plate of food "
            "dissolving into grey nothingness, a few curling steam wisps, and a faint "
            "diagram of a nose and mouth cavity drawn in thin dim lines. Scattered "
            "sparsely in the outer area, a small handful of simple dim icons: a tiny fork "
            "and spoon, two or three small scent-wave squiggles and a couple of floating "
            "flavour particles, drawn thin and low-contrast. No bright kitchen, no "
            "appetising food photography, no warm cosy mood, and the decoration must stay "
            "far dimmer than the text."
        ),
    },
    {
        "slug": "04_anki",
        "title": "なぜ暗記したはずのことが試験中だけ思い出せなくなるのか？",
        "line1": {
            "text": "なぜ試験中だけ？",
            "chars": "な (hiragana NA), ぜ (hiragana ZE with dakuten), 試 (kanji shi), "
                     "験 (kanji ken), 中 (kanji chuu), だ (hiragana DA with dakuten), "
                     "け (hiragana KE), ？ (full-width question mark)",
            "color": "pure white letters with a thin black outline",
        },
        "line2": {
            "text": "度忘れ",
            "chars": "度 (kanji do), 忘 (kanji wasu), れ (hiragana RE)",
            "color": "solid flat vivid red (#FF2D46), fully filled in and bright, with a "
                     "thick black outline and a crisp white keyline around that so it "
                     "separates hard from the dark background — no glow, no dark or "
                     "muddy red",
        },
        "bg": (
            "a dark blue-black classroom lit by one cold spotlight behind the lettering: "
            "a smooth gradient from cool electric blue at the centre out to deep blue-"
            "black at the corners, with a strong vignette. Behind the lettering, a dim "
            "empty exam desk with a blank answer sheet and a clock, plus a ghostly "
            "outline of a human head with characters dissolving and drifting out of it. "
            "Scattered sparsely in the outer area, a small handful of simple dim icons: "
            "three or four floating question marks, a tiny pencil and a small clock face, "
            "drawn thin and low-contrast. No bright classroom, no cheerful students, and "
            "the decoration must stay far dimmer than the text."
        ),
    },
    {
        "slug": "05_kami",
        "title": "なぜ紙に指を切られると痛みがジンジン続くのか？",
        "line1": {
            "text": "なぜ痛みが続く？",
            "chars": "な (hiragana NA), ぜ (hiragana ZE with dakuten), 痛 (kanji ita), "
                     "み (hiragana MI), が (hiragana GA with dakuten), 続 (kanji tsuzu), "
                     "く (hiragana KU), ？ (full-width question mark)",
            "color": "pure white letters with a thin black outline",
        },
        "line2": {
            "text": "紙の傷",
            "chars": "紙 (kanji kami), の (hiragana NO), 傷 (kanji kizu)",
            "color": "solid flat blood-red (#FF2E2E), fully filled in and bright, with a "
                     "thick black outline and a crisp white keyline around that — no "
                     "glow, not hollow, not an outlined-only shape",
        },
        "bg": (
            "a dark grey-blue background lit by one hard narrow light behind the "
            "lettering: a smooth gradient from a cold pale-blue glow at the centre out to "
            "near-black at the corners. A single sheet of white paper catches that light "
            "so its razor-thin edge glints brightly, and a darkened close-up of a "
            "fingertip with a fine cut sits low in the frame with red throbbing rings "
            "pulsing out of it. Scattered sparsely in the outer area, a small handful of "
            "simple dim icons: two or three small concentric pain rings, a few thin nerve "
            "lines and a couple of tiny paper-sheet shapes, drawn thin and low-contrast. "
            "No gore, no bright office, no cheerful colours, and the decoration must stay "
            "far dimmer than the text."
        ),
    },
]


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
    "character marked 'small' (small kana such as ッ ャ ュ ョ) must be drawn at about "
    "60% the height of the surrounding characters and sit low on the baseline; every "
    "other character is full size. Each line is one single unbroken horizontal block "
    "of lettering — never split a line across separate banners and never scatter its "
    "characters around the picture. Do NOT add any other text: no English words, no "
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
    "girl scientist — long silver-white hair in a high ponytail, aqua eyes, white lab "
    "coat — drawn in the BOTTOM-RIGHT corner, waist-up, dimly lit and partly in "
    "shadow so she reads as a corner accent, not a subject. Her total drawn height "
    "must be no more than one quarter of the canvas height and her head no wider than "
    "about one twelfth of the canvas width — she is a small figure tucked into the "
    "corner, not a co-star, and she must be noticeably smaller than a single character "
    "of the hero line. She must sit entirely below and to the "
    "right of the lettering and must never overlap or touch any character. She must be "
    "drawn whole and fully inside the frame — never cropped by the bottom or right edge, "
    "never bleeding off the canvas. Only ONE character in the image."
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
    l1, l2 = theme["line1"], theme["line2"]
    return "\n\n".join([
        STYLE,
        f"BACKGROUND / ARTWORK: {theme['bg']}",
        DECOR,
        TYPOGRAPHY,
        (
            "Text to draw:\n"
            f"LINE 1 (smaller sub-line, {l1['color']}) — exactly these characters in "
            f"order: {l1['chars']} → 「{l1['text']}」\n"
            f"LINE 2 (THE HERO LINE, gigantic, {l2['color']}) — exactly these "
            f"characters in order: {l2['chars']} → 「{l2['text']}」"
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


def main() -> int:
    wanted = set()
    for arg in sys.argv[1:]:
        if not arg.isdigit():
            raise SystemExit(f"引数は 1-{len(THEMES)} の番号のみ: {arg!r}")
        wanted.add(int(arg))

    api_key = load_api_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    failures = []
    for i, theme in enumerate(THEMES, start=1):
        if wanted and i not in wanted:
            continue
        slug = theme["slug"]
        prompt = build_prompt(theme)

        (OUT_DIR / f"{slug}.prompt.json").write_text(
            json.dumps(
                {
                    "title": theme["title"],
                    "line1": theme["line1"]["text"],
                    "line2": theme["line2"]["text"],
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

        print(f"[{i}/{len(THEMES)}] {slug}  「{theme['line1']['text']}」/"
              f"「{theme['line2']['text']}」")
        try:
            img = crop_to_16x9(generate(prompt, api_key))
        except Exception as e:
            print(f"    NG: {e}")
            failures.append((slug, str(e)))
            continue
        path = OUT_DIR / f"{slug}.png"
        img.save(path)
        print(f"    OK: {path.relative_to(ROOT)}  {img.size}")

    if failures:
        print("\n失敗:")
        for slug, err in failures:
            print(f"  - {slug}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
