#!/usr/bin/env python3
"""企業のホンネ（company-facts）チャンネルのプロフィール画像を生成する。

競合の傾向（クリーン・プロフェッショナル・ダークネイビー背景・ビジネスアイコン
＋チャンネル名テキスト）に寄せた 800x800 の PNG を Pillow だけで描く。

  python3 backend/make_company_facts_profile.py

出力: data/assets/company-facts-profile.png
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 800
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "assets" / "company-facts-profile.png"

# --- パレット（ダークネイビー基調＋ゴールドのアクセント） ---
NAVY_TOP = (18, 30, 56)
NAVY_BOTTOM = (8, 14, 30)
GOLD = (226, 178, 84)
GOLD_DIM = (150, 116, 52)
WHITE = (245, 248, 255)
BLUE_SOFT = (120, 160, 214)

# video_generator.py と同じ探索順（太字系を優先）
BOLD_FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
MEDIUM_FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]


def load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_background(img: Image.Image) -> None:
    """縦グラデーション＋中央のソフトなハイライト＋薄いグリッド。"""
    draw = ImageDraw.Draw(img)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        # 上を明るく、下に向かって落とす（軽いイージング）
        e = t * t * (3 - 2 * t)
        color = tuple(int(NAVY_TOP[i] + (NAVY_BOTTOM[i] - NAVY_TOP[i]) * e) for i in range(3))
        draw.line([(0, y), (SIZE, y)], fill=color)

    # 中央上部のスポットライト
    glow = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(glow).ellipse([120, 40, SIZE - 120, SIZE - 240], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img.paste(Image.new("RGB", (SIZE, SIZE), (58, 92, 150)), (0, 0), glow)

    # 薄いグリッド（資料・データ感）
    grid = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, SIZE + 1, 50):
        gd.line([(x, 0), (x, SIZE)], fill=(120, 160, 214, 16), width=1)
    for y in range(0, SIZE + 1, 50):
        gd.line([(0, y), (SIZE, y)], fill=(120, 160, 214, 16), width=1)
    img.paste(Image.alpha_composite(img.convert("RGBA"), grid).convert("RGB"), (0, 0))


def draw_ring(img: Image.Image) -> None:
    """外周のゴールドリング（アイコンが丸くクロップされても内側に収まる径）。"""
    layer = Image.new("RGBA", (SIZE * 2, SIZE * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([44, 44, SIZE * 2 - 44, SIZE * 2 - 44], outline=GOLD + (150,), width=8)
    d.ellipse([76, 76, SIZE * 2 - 76, SIZE * 2 - 76], outline=GOLD_DIM + (90,), width=3)
    layer = layer.resize((SIZE, SIZE), Image.LANCZOS)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def draw_emblem(img: Image.Image) -> None:
    """ビル群＋伸びるグラフ＋虫眼鏡のビジネスアイコン。4倍で描いて縮小＝アンチエイリアス。"""
    s = 4
    w = SIZE * s
    layer = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    base_y = 452 * s  # ビルの足元
    # --- ビル群（シンプルな矩形＋窓） ---
    buildings = [
        # (x, 幅, 高さ, 本体色, 窓色)
        (268, 92, 150, (86, 120, 176), (18, 30, 56)),
        (372, 108, 232, WHITE, (18, 30, 56)),
        (492, 92, 182, (86, 120, 176), (18, 30, 56)),
    ]
    for bx, bw, bh, body, win in buildings:
        x0, y0 = bx * s, (base_y - bh * s)
        d.rectangle([x0, y0, x0 + bw * s, base_y], fill=body)
        # 窓（3列 x n行）
        cols, pad = 3, 12 * s
        cw = (bw * s - pad * 2) / (cols * 2 - 1)
        rows = max(2, int((bh * s - pad * 2) // (cw * 2)))
        for r in range(rows):
            for c in range(cols):
                wx = x0 + pad + c * cw * 2
                wy = y0 + pad + r * cw * 2
                d.rectangle([wx, wy, wx + cw, wy + cw], fill=win)

    # 足元のライン（地面）
    d.rectangle([236 * s, base_y, 596 * s, base_y + 5 * s], fill=GOLD)

    # --- 右肩上がりの折れ線グラフ ---
    pts = [(258, 378), (330, 324), (398, 354), (470, 270), (556, 214)]
    d.line([(x * s, y * s) for x, y in pts], fill=GOLD, width=7 * s, joint="curve")
    for x, y in pts:
        d.ellipse([(x - 9) * s, (y - 9) * s, (x + 9) * s, (y + 9) * s], fill=GOLD)
    # 矢印の先端
    tip = pts[-1]
    ang = math.atan2(pts[-1][1] - pts[-2][1], pts[-1][0] - pts[-2][0])
    head = 30
    d.polygon(
        [
            ((tip[0] + math.cos(ang) * head * 0.9) * s, (tip[1] + math.sin(ang) * head * 0.9) * s),
            ((tip[0] + math.cos(ang + 2.5) * head) * s, (tip[1] + math.sin(ang + 2.5) * head) * s),
            ((tip[0] + math.cos(ang - 2.5) * head) * s, (tip[1] + math.sin(ang - 2.5) * head) * s),
        ],
        fill=GOLD,
    )

    # --- 虫眼鏡（“ホンネを覗く”の記号） ---
    cx, cy, r = 452, 340, 92
    d.ellipse(
        [(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s],
        fill=(10, 18, 36, 120),
        outline=WHITE + (255,),
        width=11 * s,
    )
    # レンズのハイライト
    d.arc(
        [(cx - r + 22) * s, (cy - r + 22) * s, (cx + r - 22) * s, (cy + r - 22) * s],
        start=200,
        end=260,
        fill=(255, 255, 255, 130),
        width=6 * s,
    )
    # 柄
    hx0, hy0 = cx + r * 0.72, cy + r * 0.72
    hx1, hy1 = cx + r * 1.52, cy + r * 1.52
    d.line([(hx0 * s, hy0 * s), (hx1 * s, hy1 * s)], fill=WHITE, width=22 * s)
    d.ellipse([(hx1 - 11) * s, (hy1 - 11) * s, (hx1 + 11) * s, (hy1 + 11) * s], fill=WHITE)

    layer = layer.resize((SIZE, SIZE), Image.LANCZOS)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def draw_text(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)

    def measure(text: str, font: ImageFont.ImageFont, spacing: int) -> float:
        return sum(draw.textlength(ch, font=font) for ch in text) + spacing * (len(text) - 1)

    def fit_font(text: str, candidates: list[str], start: int, max_w: float, spacing: int):
        """円形クロップの内側に収まる最大サイズを選ぶ。"""
        size = start
        while size > 12:
            font = load_font(candidates, size)
            if measure(text, font, spacing) <= max_w:
                return font
            size -= 2
        return load_font(candidates, 12)

    def centered(text: str, font: ImageFont.ImageFont, y: int, fill, spacing: int = 0) -> None:
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + spacing * (len(text) - 1)
        x = (SIZE - total) / 2
        for ch, cw in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill)
            x += cw + spacing

    # 区切り線（エンブレムとテキストの境目）
    draw.line([(312, 528), (488, 528)], fill=GOLD_DIM, width=3)

    # 丸くクロップされた際の内接円（半径356px）の内側に収まる横幅に抑える
    title_font = fit_font("企業のホンネ", BOLD_FONT_CANDIDATES, 92, 480, 4)
    sub_font = fit_font("BUSINESS FACTS", MEDIUM_FONT_CANDIDATES, 26, 330, 6)

    centered("企業のホンネ", title_font, 558, WHITE, spacing=4)
    centered("BUSINESS FACTS", sub_font, 672, BLUE_SOFT, spacing=6)


def main() -> Path:
    img = Image.new("RGB", (SIZE, SIZE), NAVY_BOTTOM)
    draw_background(img)
    draw_emblem(img)
    draw_text(img)
    draw_ring(img)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PATH, "PNG")
    print(f"saved: {OUT_PATH} ({img.size[0]}x{img.size[1]})")
    return OUT_PATH


if __name__ == "__main__":
    main()
