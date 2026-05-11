"""Regenerate finger-cracking thumbnail with a bright POP, vivid Pillow background.

Used because the OpenAI image API hit a billing hard limit during the main pipeline
run, so the auto-generated thumbnail fell back to the dark default. This script
draws a cheerful pastel-rainbow gradient + sunburst background, then overlays the
finger-cracking title text and the Riko/Makoto characters.

Outputs to:
  ~/Desktop/動画出力用/なぜ指をポキポキ鳴らせるのか/finger_cracking_サムネイル.png
  ~/Desktop/動画出力用/なぜ指をポキポキ鳴らせるのか/finger_cracking_ショート_サムネイル.png
"""

import math
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path("/Users/ayukiyamazaki/Desktop/動画出力用/なぜ指をポキポキ鳴らせるのか")
LANDSCAPE_OUT = OUT_DIR / "finger_cracking_サムネイル.png"
SHORT_OUT = OUT_DIR / "finger_cracking_ショート_サムネイル.png"

RIKO_PATH = ROOT / "assets" / "characters" / "riko" / "surprise.png"
MAKOTO_PATH = ROOT / "assets" / "characters" / "makoto" / "surprise.png"

FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
]


def get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


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


def draw_text_outline(draw, xy, text, font, fill, outline, outline_w=6):
    x, y = xy
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx * dx + dy * dy <= outline_w * outline_w:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def vertical_gradient(W, H, stops):
    """stops: list of (pos 0..1, (r,g,b))"""
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / max(H - 1, 1)
        c = stops[0][1]
        for i in range(len(stops) - 1):
            p1, c1 = stops[i]
            p2, c2 = stops[i + 1]
            if p1 <= t <= p2:
                local = (t - p1) / max(p2 - p1, 1e-6)
                c = lerp_color(c1, c2, local)
                break
            elif t > p2:
                c = c2
        for x in range(W):
            px[x, y] = c
    return img


def add_sunburst(img: Image.Image, center, num_rays=16, color=(255, 255, 220, 80)):
    """Soft sunburst rays from `center`."""
    W, H = img.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    radius = int(math.hypot(W, H))
    for i in range(num_rays):
        ang_a = (i / num_rays) * 2 * math.pi
        ang_b = ((i + 0.5) / num_rays) * 2 * math.pi
        ax = cx + math.cos(ang_a) * radius
        ay = cy + math.sin(ang_a) * radius
        bx = cx + math.cos(ang_b) * radius
        by = cy + math.sin(ang_b) * radius
        draw.polygon([(cx, cy), (ax, ay), (bx, by)], fill=color)
    # blur a little
    layer = layer.filter(ImageFilter.GaussianBlur(8))
    img = img.convert("RGBA")
    img.alpha_composite(layer)
    return img


def add_sparkles(img: Image.Image, count=30, seed=42):
    import random
    rng = random.Random(seed)
    W, H = img.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for _ in range(count):
        x = rng.randint(20, W - 20)
        y = rng.randint(20, int(H * 0.65))
        size = rng.randint(8, 22)
        # 4-pointed sparkle
        c = (255, 255, 255, rng.randint(160, 230))
        draw.polygon([
            (x, y - size), (x + size // 4, y - size // 4),
            (x + size, y), (x + size // 4, y + size // 4),
            (x, y + size), (x - size // 4, y + size // 4),
            (x - size, y), (x - size // 4, y - size // 4),
        ], fill=c)
    layer = layer.filter(ImageFilter.GaussianBlur(0.6))
    img = img.convert("RGBA")
    img.alpha_composite(layer)
    return img


def add_speed_lines(img: Image.Image, center, num=14, color=(255, 90, 40, 200)):
    """Pop comic speed lines."""
    W, H = img.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    inner_r = 80
    outer_r = int(math.hypot(W, H))
    for i in range(num):
        ang = (i / num) * 2 * math.pi + 0.1
        x1 = cx + math.cos(ang) * inner_r
        y1 = cy + math.sin(ang) * inner_r
        x2 = cx + math.cos(ang) * outer_r
        y2 = cy + math.sin(ang) * outer_r
        draw.line([(x1, y1), (x2, y2)], fill=color, width=8)
    layer = layer.filter(ImageFilter.GaussianBlur(1.5))
    img = img.convert("RGBA")
    img.alpha_composite(layer)
    return img


def build_background(W: int, H: int) -> Image.Image:
    """Bright vivid pop sky → pink → yellow gradient with sunburst + sparkles."""
    bg = vertical_gradient(W, H, [
        (0.00, (135, 220, 255)),  # bright sky blue
        (0.45, (255, 200, 230)),  # cotton-candy pink
        (0.78, (255, 235, 130)),  # sunny yellow
        (1.00, (255, 220, 110)),  # warm yellow base
    ])
    bg = add_sunburst(bg, center=(W // 2, int(H * 0.45)),
                      num_rays=20, color=(255, 255, 200, 70))
    bg = add_sparkles(bg, count=36)
    bg = add_speed_lines(bg, center=(W // 2, int(H * 0.42)),
                         num=18, color=(255, 130, 60, 90))
    return bg


def fit_character(path: Path, target_h: int) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    ratio = target_h / img.height
    new_w = int(img.width * ratio)
    return img.resize((new_w, target_h), Image.LANCZOS)


def compose_landscape():
    W, H = 1280, 720
    print(f"build landscape {W}x{H}")
    img = build_background(W, H)

    # characters
    char_h = 380
    riko = fit_character(RIKO_PATH, char_h)
    makoto = fit_character(MAKOTO_PATH, char_h)
    riko_x = -20
    riko_y = H - char_h + 10
    makoto_x = W - makoto.width + 20
    makoto_y = H - char_h + 10
    img.alpha_composite(riko, (riko_x, riko_y))
    img.alpha_composite(makoto, (makoto_x, makoto_y))

    draw = ImageDraw.Draw(img)
    text_area_w = W - 200

    # Top badge
    badge_text = "ゆっくり解説"
    badge_font = get_font(40)
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    bx = (W - bw) // 2
    by = 28
    pad_x, pad_y = 22, 12
    badge_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bdl = ImageDraw.Draw(badge_layer)
    bdl.rounded_rectangle(
        [bx - pad_x, by - pad_y, bx + bw + pad_x, by + bh + pad_y],
        radius=18, fill=(225, 50, 70, 245),
        outline=(255, 255, 255, 255), width=4,
    )
    img.alpha_composite(badge_layer)
    draw = ImageDraw.Draw(img)
    draw_text_outline(draw, (bx, by), badge_text, badge_font,
                      fill=(255, 255, 255, 255), outline=(120, 0, 20, 255), outline_w=3)

    y_pos = by + bh + pad_y + 24

    # Line 1
    line1 = "指がポキッと"
    f1, w1, h1, _ = fit_text_to_width(draw, line1, text_area_w, start_size=130, min_size=70)
    x1 = (W - w1) // 2
    draw_text_outline(draw, (x1, y_pos), line1, f1,
                      fill=(255, 255, 255, 255), outline=(40, 50, 130, 255), outline_w=9)
    y_pos += h1 + 14

    # Line 2 (highlight 気泡 part split? — keep simple full string)
    line2 = "鳴るのはなぜ？"
    f2, w2, h2, _ = fit_text_to_width(draw, line2, text_area_w, start_size=140, min_size=70)
    x2 = (W - w2) // 2
    draw_text_outline(draw, (x2, y_pos), line2, f2,
                      fill=(255, 240, 60, 255), outline=(180, 30, 30, 255), outline_w=11)
    y_pos += h2 + 18

    # Subtitle red bar
    sub = "正体は関節の中の気泡だった！"
    f3, w3, h3, _ = fit_text_to_width(draw, sub, text_area_w - 40, start_size=58, min_size=36)
    x3 = (W - w3) // 2
    bar_pad_x, bar_pad_y = 26, 12
    bar_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar_layer)
    bd.rounded_rectangle(
        [x3 - bar_pad_x, y_pos - bar_pad_y, x3 + w3 + bar_pad_x, y_pos + h3 + bar_pad_y],
        radius=14, fill=(255, 80, 100, 240),
        outline=(255, 255, 255, 255), width=4,
    )
    img.alpha_composite(bar_layer)
    draw = ImageDraw.Draw(img)
    draw_text_outline(draw, (x3, y_pos), sub, f3,
                      fill=(255, 255, 255, 255), outline=(120, 0, 30, 255), outline_w=4)

    # Bottom tagline (between characters)
    tag = "60年実験でついに決着"
    riko_right_edge = riko_x + riko.width
    makoto_left_edge = makoto_x
    sub_left = riko_right_edge - 10
    sub_right = makoto_left_edge + 10
    sub_w_area = max(sub_right - sub_left, 200)
    ft, wt, ht, _ = fit_text_to_width(draw, tag, sub_w_area, start_size=48, min_size=28)
    tx = sub_left + (sub_w_area - wt) // 2
    ty = H - ht - 38
    # yellow pill behind tag
    pill_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill_layer)
    pd.rounded_rectangle(
        [tx - 18, ty - 10, tx + wt + 18, ty + ht + 10],
        radius=20, fill=(255, 230, 80, 235),
        outline=(255, 90, 40, 255), width=4,
    )
    img.alpha_composite(pill_layer)
    draw = ImageDraw.Draw(img)
    draw_text_outline(draw, (tx, ty), tag, ft,
                      fill=(60, 30, 0, 255), outline=(255, 255, 255, 255), outline_w=3)

    return img.convert("RGB")


def compose_short(landscape: Image.Image) -> Image.Image:
    """Build a 720x1280 short thumbnail by re-doing the layout vertically."""
    W, H = 720, 1280
    img = build_background(W, H)

    # characters at the bottom — side by side, scaled to fit the short width
    char_h = 360
    riko = fit_character(RIKO_PATH, char_h)
    makoto = fit_character(MAKOTO_PATH, char_h)
    total_char_w = riko.width + makoto.width
    if total_char_w > W:
        scale = (W - 20) / total_char_w
        new_h = int(char_h * scale)
        riko = fit_character(RIKO_PATH, new_h)
        makoto = fit_character(MAKOTO_PATH, new_h)
        char_h = new_h
    riko_y = H - char_h - 20
    makoto_y = H - char_h - 20
    riko_x = 10
    makoto_x = W - makoto.width - 10
    img.alpha_composite(riko, (riko_x, riko_y))
    img.alpha_composite(makoto, (makoto_x, makoto_y))

    draw = ImageDraw.Draw(img)
    text_area_w = W - 80

    # Top badge
    badge_text = "ゆっくり解説"
    badge_font = get_font(48)
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    bx = (W - bw) // 2
    by = 60
    pad_x, pad_y = 26, 14
    bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bld = ImageDraw.Draw(bl)
    bld.rounded_rectangle(
        [bx - pad_x, by - pad_y, bx + bw + pad_x, by + bh + pad_y],
        radius=22, fill=(225, 50, 70, 245),
        outline=(255, 255, 255, 255), width=5,
    )
    img.alpha_composite(bl)
    draw = ImageDraw.Draw(img)
    draw_text_outline(draw, (bx, by), badge_text, badge_font,
                      fill=(255, 255, 255, 255), outline=(120, 0, 20, 255), outline_w=4)
    y_pos = by + bh + pad_y + 50

    line1 = "指がポキッと"
    f1, w1, h1, _ = fit_text_to_width(draw, line1, text_area_w, start_size=130, min_size=80)
    x1 = (W - w1) // 2
    draw_text_outline(draw, (x1, y_pos), line1, f1,
                      fill=(255, 255, 255, 255), outline=(40, 50, 130, 255), outline_w=10)
    y_pos += h1 + 24

    line2 = "鳴るのはなぜ？"
    f2, w2, h2, _ = fit_text_to_width(draw, line2, text_area_w, start_size=130, min_size=80)
    x2 = (W - w2) // 2
    draw_text_outline(draw, (x2, y_pos), line2, f2,
                      fill=(255, 240, 60, 255), outline=(180, 30, 30, 255), outline_w=12)
    y_pos += h2 + 50

    sub = "正体は関節の気泡！"
    f3, w3, h3, _ = fit_text_to_width(draw, sub, text_area_w - 40, start_size=80, min_size=44)
    x3 = (W - w3) // 2
    bar_pad_x, bar_pad_y = 30, 16
    bl2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bld2 = ImageDraw.Draw(bl2)
    bld2.rounded_rectangle(
        [x3 - bar_pad_x, y_pos - bar_pad_y, x3 + w3 + bar_pad_x, y_pos + h3 + bar_pad_y],
        radius=18, fill=(255, 80, 100, 240),
        outline=(255, 255, 255, 255), width=5,
    )
    img.alpha_composite(bl2)
    draw = ImageDraw.Draw(img)
    draw_text_outline(draw, (x3, y_pos), sub, f3,
                      fill=(255, 255, 255, 255), outline=(120, 0, 30, 255), outline_w=5)

    return img.convert("RGB")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    landscape = compose_landscape()
    landscape.save(LANDSCAPE_OUT, "PNG", optimize=True)
    print(f"saved: {LANDSCAPE_OUT}")
    short = compose_short(landscape)
    short.save(SHORT_OUT, "PNG", optimize=True)
    print(f"saved: {SHORT_OUT}")


if __name__ == "__main__":
    main()
