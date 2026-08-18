#!/usr/bin/env python3
"""ゆっくり2chスレまとめ劇場（2ch-matome）チャンネルのプロフィール画像を生成する。

競合の傾向（2ch風のカジュアルなデザイン・掲示板風レイアウト・赤／黄の目立つ色）に
寄せた 800x800 の PNG を Pillow だけで描く。YouTube の丸クロップを想定し、重要な
要素はすべて内接円（中心 400,400 / 半径 356px）の内側に収めている。

  python3 backend/make_2ch_matome_profile.py

出力: data/assets/2ch-matome-profile.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 800
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "assets" / "2ch-matome-profile.png"

# --- パレット（ダークグリーン基調＋2ch的な赤／黄のアクセント） ---
GREEN_TOP = (16, 58, 40)
GREEN_BOTTOM = (6, 24, 17)
GLOW_GREEN = (46, 132, 88)
RED = (208, 46, 42)
RED_DARK = (150, 28, 26)
YELLOW = (255, 208, 48)
YELLOW_DIM = (188, 148, 24)
BOARD_BG = (238, 236, 226)  # 2ch の板っぽい生成りの背景
BOARD_LINE = (200, 196, 182)
NAME_GREEN = (22, 120, 52)  # 名前欄の緑
INK = (28, 28, 28)
WHITE = (248, 248, 244)

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
    """縦グラデーション＋中央のスポットライト＋『＞＞』のウォーターマーク。"""
    draw = ImageDraw.Draw(img)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        e = t * t * (3 - 2 * t)
        color = tuple(int(GREEN_TOP[i] + (GREEN_BOTTOM[i] - GREEN_TOP[i]) * e) for i in range(3))
        draw.line([(0, y), (SIZE, y)], fill=color)

    # 中央のスポットライト
    glow = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(glow).ellipse([90, 60, SIZE - 90, SIZE - 180], fill=80)
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    img.paste(Image.new("RGB", (SIZE, SIZE), GLOW_GREEN), (0, 0), glow)

    # 薄い横罫（掲示板のログっぽさ）
    lines = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines)
    for y in range(0, SIZE + 1, 14):
        ld.line([(0, y), (SIZE, y)], fill=(0, 0, 0, 26), width=1)
    img.paste(Image.alpha_composite(img.convert("RGBA"), lines).convert("RGB"), (0, 0))

    # 背景の『＞＞』（アンカー記号）を薄く配置
    marks = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    md = ImageDraw.Draw(marks)
    f = load_font(BOLD_FONT_CANDIDATES, 150)
    for x, y in ((-30, 60), (628, 92), (-10, 560), (612, 590)):
        md.text((x, y), ">>", font=f, fill=(255, 255, 255, 18))
    img.paste(Image.alpha_composite(img.convert("RGBA"), marks).convert("RGB"), (0, 0))


def draw_board(img: Image.Image) -> None:
    """掲示板のスレ画面（赤ヘッダ＋緑の名無し＋本文バー）と『w』の吹き出し。"""
    s = 4  # 4倍で描いて縮小＝アンチエイリアス
    layer = Image.new("RGBA", (SIZE * s, SIZE * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def rrect(box, radius, **kw):
        d.rounded_rectangle([v * s for v in box], radius=radius * s, **kw)

    # --- スレ画面の影 ---
    shadow = Image.new("RGBA", (SIZE * s, SIZE * s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [v * s for v in (184, 168, 632, 486)], radius=26 * s, fill=(0, 0, 0, 110)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(10 * s))
    layer = Image.alpha_composite(layer, shadow)
    d = ImageDraw.Draw(layer)

    def rrect(box, radius, **kw):  # noqa: F811  (layer 差し替え後の描画先に付け替え)
        d.rounded_rectangle([v * s for v in box], radius=radius * s, **kw)

    # --- スレ画面本体 ---
    rrect((176, 156, 624, 474), 26, fill=BOARD_BG + (255,))

    # ヘッダ（赤帯）— 上側だけ角丸にするため、角丸矩形＋矩形で下端を潰す
    rrect((176, 156, 624, 220), 26, fill=RED + (255,))
    d.rectangle([176 * s, 200 * s, 624 * s, 220 * s], fill=RED + (255,))
    d.rectangle([176 * s, 216 * s, 624 * s, 222 * s], fill=RED_DARK + (255,))

    # ヘッダの信号ボタン（ウィンドウ感）
    for i, cx in enumerate((206, 232, 258)):
        col = (255, 255, 255, 235) if i == 0 else (255, 255, 255, 150)
        d.ellipse([(cx - 8) * s, 180 * s, (cx + 8) * s, 196 * s], fill=col)

    head_font = load_font(BOLD_FONT_CANDIDATES, 30 * s)
    d.text((292 * s, 172 * s), "【衝撃】スレまとめ", font=head_font, fill=WHITE + (255,))

    # --- レス（名無し行＋本文バー）を3件 ---
    name_font = load_font(BOLD_FONT_CANDIDATES, 19 * s)
    res_font = load_font(BOLD_FONT_CANDIDATES, 21 * s)
    rows = [
        (240, ">>1", "名無しさん", (352, 300)),
        (322, ">>2", "名無しさん", (330, 268)),
        (404, ">>3", "名無しさん", (300, 0)),
    ]
    for top, anchor, name, bars in rows:
        d.text((202 * s, top * s), anchor, font=res_font, fill=RED + (255,))
        d.text((262 * s, (top + 3) * s), name, font=name_font, fill=NAME_GREEN + (255,))
        # 本文バー（ダミーテキスト）
        for i, bw in enumerate(bars):
            if not bw:
                continue
            by = top + 32 + i * 22
            rrect((202, by, 202 + bw, by + 13), 6, fill=BOARD_LINE + (255,))
        # レスの区切り線
        if top != 404:
            d.line(
                [(196 * s, (top + 70) * s), (604 * s, (top + 70) * s)],
                fill=BOARD_LINE + (170,),
                width=1 * s,
            )

    # --- 右下に重なる黄色の吹き出し（『www』） ---
    bub = (446, 396, 662, 508)
    # 尻尾（左下に向かう三角）
    d.polygon(
        [(470 * s, 500 * s), (438 * s, 536 * s), (512 * s, 506 * s)],
        fill=YELLOW + (255,),
    )
    d.polygon(
        [(470 * s, 500 * s), (438 * s, 536 * s), (512 * s, 506 * s)],
        outline=INK + (255,),
        width=5 * s,
    )
    rrect(bub, 30, fill=YELLOW + (255,), outline=INK + (255,), width=5 * s)
    w_font = load_font(BOLD_FONT_CANDIDATES, 62 * s)
    tw = d.textlength("www", font=w_font)
    d.text(
        (((bub[0] + bub[2]) / 2) * s - tw / 2, 412 * s),
        "www",
        font=w_font,
        fill=INK + (255,),
    )

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

    def centered(text, font, y, fill, spacing=0, stroke=0, stroke_fill=None) -> None:
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + spacing * (len(text) - 1)
        x = (SIZE - total) / 2
        for ch, cw in zip(text, widths):
            draw.text(
                (x, y), ch, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill
            )
            x += cw + spacing

    # 丸クロップの内接円（半径356px）の内側に収まる横幅に抑える
    title_font = fit_font("2chまとめ劇場", BOLD_FONT_CANDIDATES, 86, 470, 2)
    sub_font = fit_font("ゆっくり実況 / 毎日更新", MEDIUM_FONT_CANDIDATES, 27, 330, 4)

    centered("2chまとめ劇場", title_font, 556, YELLOW, spacing=2, stroke=7, stroke_fill=(4, 18, 12))

    # タイトル下のアンダーライン（赤＋黄の2本）
    draw.rounded_rectangle([272, 660, 528, 668], radius=4, fill=RED)
    draw.rounded_rectangle([320, 674, 480, 679], radius=3, fill=YELLOW_DIM)

    centered("ゆっくり実況 / 毎日更新", sub_font, 692, WHITE, spacing=4)


def draw_ring(img: Image.Image) -> None:
    """外周のリング（丸クロップ後も内側に残る径）。"""
    layer = Image.new("RGBA", (SIZE * 2, SIZE * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([40, 40, SIZE * 2 - 40, SIZE * 2 - 40], outline=YELLOW + (170,), width=10)
    d.ellipse([76, 76, SIZE * 2 - 76, SIZE * 2 - 76], outline=RED + (110,), width=4)
    layer = layer.resize((SIZE, SIZE), Image.LANCZOS)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def main() -> Path:
    img = Image.new("RGB", (SIZE, SIZE), GREEN_BOTTOM)
    draw_background(img)
    draw_board(img)
    draw_text(img)
    draw_ring(img)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PATH, "PNG")
    print(f"saved: {OUT_PATH} ({img.size[0]}x{img.size[1]})")
    return OUT_PATH


if __name__ == "__main__":
    main()
