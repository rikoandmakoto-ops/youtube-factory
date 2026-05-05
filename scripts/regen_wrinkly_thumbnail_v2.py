"""Regenerate wrinkly fingers thumbnail v2 — reuse existing background,
add character images (Riko left, Makoto bottom-right), fix text layout.
Uses DroidSansFallbackFull for sandbox, falls back to Hiragino on macOS."""

import os
import sys
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

BG_PATH = ROOT / "sample_wrinkly_fingers_thumb_bg.png"
RIKO_PATH = ROOT / "assets" / "characters" / "riko" / "surprise.png"
MAKOTO_PATH = ROOT / "assets" / "characters" / "makoto" / "surprise.png"
FACTORY_OUT = ROOT / "wrinkly_fingers_サムネイル_v2.png"

DESKTOP_OUT = Path(
    "/Users/ayukiyamazaki/Desktop/動画出力用/お風呂で指がシワシワになる本当の理由/wrinkly_fingers_サムネイル.png"
)
ICLOUD_OUT = Path(
    "/Users/ayukiyamazaki/Library/Mobile Documents/com~apple~CloudDocs/"
    "macmini iphone共有用/動画出力/お風呂で指がシワシワになる本当の理由/wrinkly_fingers_サムネイル.png"
)

FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]


def get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def is_bold_font_available():
    """Check if we have a proper bold Japanese font (Hiragino)."""
    for path in FONT_CANDIDATES[:4]:
        if os.path.exists(path):
            return True
    return False


def fit_text_to_width(draw, text, max_width, start_size, min_size=40):
    size = start_size
    while size >= min_size:
        font = get_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            return font, w, bbox[3] - bbox[1], size
        size -= 4
    font = get_font(min_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    return font, bbox[2] - bbox[0], bbox[3] - bbox[1], min_size


def draw_text_bold_outline(draw, xy, text, font, fill, outline, outline_w=6, bold_extra=0):
    """Draw text with outline. If bold_extra > 0, draw fill multiple times for faux-bold."""
    x, y = xy
    # Outline
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx * dx + dy * dy <= outline_w * outline_w:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    # Faux bold: draw fill text with small offsets
    for dx in range(-bold_extra, bold_extra + 1):
        for dy in range(-bold_extra, bold_extra + 1):
            draw.text((x + dx, y + dy), text, font=font, fill=fill)


def compose_thumbnail():
    print("背景画像を読み込み...")
    bg = Image.open(BG_PATH).convert("RGBA")
    W, H = bg.size  # 1280x720
    img = bg.copy()

    bold_available = is_bold_font_available()
    bold_extra = 0 if bold_available else 2  # faux-bold offset for non-bold fonts
    print(f"  Bold font: {'Hiragino' if bold_available else 'DroidSans (faux-bold)'}")

    # --- 1. グラデーション帯を先に適用 ---
    top_band_h = int(H * 0.58)
    top_band = Image.new("RGBA", (W, top_band_h), (0, 0, 0, 0))
    tbd = ImageDraw.Draw(top_band)
    for y in range(top_band_h):
        a = int(200 * (1 - y / top_band_h) ** 1.2)
        tbd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    img.alpha_composite(top_band, (0, 0))

    bot_h = int(H * 0.32)
    bot_band = Image.new("RGBA", (W, bot_h), (0, 0, 0, 0))
    bbd = ImageDraw.Draw(bot_band)
    for y in range(bot_h):
        a = int(140 * (y / bot_h) ** 1.2)
        bbd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    img.alpha_composite(bot_band, (0, H - bot_h))

    # --- 2. キャラクター画像をグラデーションの上に配置 ---
    print("キャラクター画像を配置...")

    char_h = 290  # 両キャラ同じ高さ

    riko = Image.open(RIKO_PATH).convert("RGBA")
    riko_ratio = char_h / riko.height
    riko_w = int(riko.width * riko_ratio)
    riko = riko.resize((riko_w, char_h), Image.LANCZOS)
    riko_x = 10
    riko_y = H - char_h
    img.alpha_composite(riko, (riko_x, riko_y))

    makoto = Image.open(MAKOTO_PATH).convert("RGBA")
    makoto_ratio = char_h / makoto.height
    makoto_w = int(makoto.width * makoto_ratio)
    makoto = makoto.resize((makoto_w, char_h), Image.LANCZOS)
    makoto_x = W - makoto_w - 10
    makoto_y = H - char_h
    img.alpha_composite(makoto, (makoto_x, makoto_y))

    # --- 3. テキスト合成 ---
    draw = ImageDraw.Draw(img)
    print("テキストを合成...")

    text_area_w = W - 100
    y_pos = 10

    # Line 1: 指がシワシワになるのは（白）
    line1 = "指がシワシワになるのは"
    font1, w1, h1, _ = fit_text_to_width(draw, line1, text_area_w, start_size=100, min_size=50)
    x1 = (W - w1) // 2
    draw_text_bold_outline(draw, (x1, y_pos), line1, font1,
                           fill=(255, 255, 255, 255), outline=(0, 0, 0, 255),
                           outline_w=8, bold_extra=bold_extra)
    y_pos += h1 + 24

    # Line 2: 水を吸うから？（黄色強調）
    line2 = "水を吸うから？"
    font2, w2, h2, _ = fit_text_to_width(draw, line2, text_area_w, start_size=110, min_size=50)
    x2 = (W - w2) // 2
    draw_text_bold_outline(draw, (x2, y_pos), line2, font2,
                           fill=(255, 235, 60, 255), outline=(160, 0, 0, 255),
                           outline_w=10, bold_extra=bold_extra + 1)
    y_pos += h2 + 28

    # Line 3: 驚きの真実！？（赤バー＋白文字）
    line3 = "驚きの真実！？"
    font3, w3, h3, _ = fit_text_to_width(draw, line3, text_area_w, start_size=90, min_size=45)
    x3 = (W - w3) // 2
    pad_x, pad_y = 30, 16
    bar_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(bar_layer)
    bar_draw.rounded_rectangle(
        [x3 - pad_x, y_pos - pad_y, x3 + w3 + pad_x, y_pos + h3 + pad_y],
        radius=14, fill=(220, 20, 20, 240),
        outline=(255, 255, 255, 230), width=5,
    )
    img.alpha_composite(bar_layer)
    draw = ImageDraw.Draw(img)
    draw_text_bold_outline(draw, (x3, y_pos), line3, font3,
                           fill=(255, 255, 255, 255), outline=(80, 0, 0, 255),
                           outline_w=6, bold_extra=bold_extra)

    # サブテキスト（キャラの間）
    sub_text = "神経が起こす驚きの反応"
    sub_left = riko_x + riko_w + 15
    sub_right = makoto_x - 15
    sub_w_area = sub_right - sub_left
    if sub_w_area > 200:
        sub_font, sub_w, sub_h, _ = fit_text_to_width(draw, sub_text, sub_w_area, start_size=46, min_size=28)
        sub_x = sub_left + (sub_w_area - sub_w) // 2
        sub_y = H - sub_h - 30
        draw_text_bold_outline(draw, (sub_x, sub_y), sub_text, sub_font,
                               fill=(255, 240, 100, 255), outline=(60, 0, 0, 255),
                               outline_w=5, bold_extra=bold_extra)

    # --- 保存 ---
    final = img.convert("RGB")
    final.save(FACTORY_OUT, "PNG", optimize=True)
    print(f"  saved: {FACTORY_OUT}")

    # macOS paths (will fail in sandbox, that's ok)
    for dest in [DESKTOP_OUT, ICLOUD_OUT]:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(FACTORY_OUT, dest)
            print(f"  copied: {dest}")
        except (PermissionError, OSError) as e:
            print(f"  skip (sandbox): {dest.name}")

    print("DONE!")


if __name__ == "__main__":
    compose_thumbnail()
