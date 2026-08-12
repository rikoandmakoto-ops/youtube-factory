#!/usr/bin/env python3
"""
ローカル Pillow 図解ジェネレータ (APIコスト0)

ショート動画のイラストカードに差し込む「解説図」を、DALL-E を使わず
Pillow だけで描画する。テーマ文字列のキーワードからアイコン・図形を
自動選択し、教科書風(daily-science)/流出文書風(scp-lab)の2系統で
作図する。video_generator.ShortFrameRenderer のカード枠
(_draw_textbook_card / _draw_leaked_card)に contain 配置される前提なので、
ここでは「カード内に入れる図そのもの」だけを返す。

  - card_style="textbook"        … 透過背景・カラー(白カード上に乗る)
  - card_style="leaked-document" … 不透明ダーク背景・ライトグレー(後段でL変換)

DALL-E が 429 / billing_hard_limit 等で失敗したときのフォールバックにも使う。
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# カード内寸 (≈2.8:1) に合わせた作図キャンバス。2x 相当で描いて contain 縮小。
CANVAS_W, CANVAS_H = 1840, 650


# ------------------------------------------------------------------
# テキスト描画 (video_generator のフォントヘルパを遅延 import して再利用)
# ------------------------------------------------------------------
def _text_helpers():
    from pipeline.video_generator import draw_composite_text, measure_composite_text
    return draw_composite_text, measure_composite_text


def _label(draw, cx, cy, text, size, fill, stroke_fill=(0, 0, 0), stroke_width=0):
    """中央揃えでラベルを描く。cx,cy はテキスト中心。"""
    if not text:
        return
    draw_composite_text, measure_composite_text = _text_helpers()
    w = measure_composite_text(draw, text, size)
    draw_composite_text(draw, (int(cx - w / 2), int(cy - size / 2)), text, size,
                        fill, stroke_fill=stroke_fill, stroke_width=stroke_width)


# ==================================================================
# 共通プリミティブ
# ==================================================================
def _arrow(draw, x0, y0, x1, y1, color, width=10, head=26):
    draw.line([(x0, y0), (x1, y1)], fill=color, width=width)
    ang = math.atan2(y1 - y0, x1 - x0)
    for da in (math.radians(150), math.radians(-150)):
        hx = x1 + head * math.cos(ang + da)
        hy = y1 + head * math.sin(ang + da)
        draw.line([(x1, y1), (hx, hy)], fill=color, width=width)


def _poly(draw, pts, fill=None, outline=None, width=6):
    draw.polygon(pts, fill=fill, outline=outline)
    if outline and width > 1:
        # polygon の outline は1px。太線が欲しいので辺をなぞる。
        n = len(pts)
        for i in range(n):
            draw.line([pts[i], pts[(i + 1) % n]], fill=outline, width=width)


# ==================================================================
# 教科書風アイコン (カラー / 透過背景前提)
# ==================================================================
def _ic_sun(d, cx, cy, r, c):
    col = (255, 196, 38)
    for k in range(12):
        a = math.radians(k * 30)
        d.line([(cx + r * 1.05 * math.cos(a), cy + r * 1.05 * math.sin(a)),
                (cx + r * 1.5 * math.cos(a), cy + r * 1.5 * math.sin(a))],
               fill=col, width=12)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=(214, 150, 0), width=8)


def _ic_moon(d, cx, cy, r, c):
    col = (240, 224, 150)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    d.ellipse([cx - r + r * 0.55, cy - r, cx + r + r * 0.55, cy + r], fill=(0, 0, 0, 0))
    # 上の塗りで欠けないので、欠け側は透明で抜く代わりに背景色不要 → 再描画
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(200, 180, 90), width=8)


def _ic_planet(d, cx, cy, r, c):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(94, 150, 222), outline=(40, 90, 160), width=8)
    d.ellipse([cx - r * 0.5, cy - r * 0.4, cx + r * 0.1, cy + r * 0.1], fill=(140, 196, 120))
    d.ellipse([cx - r * 0.1, cy + r * 0.1, cx + r * 0.55, cy + r * 0.6], fill=(140, 196, 120))
    ring = Image.new("RGBA", (int(r * 4), int(r * 4)), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse([0, int(r * 1.4), int(r * 4), int(r * 2.6)], outline=(220, 200, 150), width=14)
    ring = ring.rotate(-18, expand=False, resample=Image.BICUBIC)
    d._image.paste(ring, (int(cx - r * 2), int(cy - r * 2)), ring)


def _ic_water(d, cx, cy, r, c):
    top = (cx, cy - r * 1.15)
    pts = [top]
    for k in range(1, 13):
        a = math.radians(-90 + k * (360 / 14))
        pts.append((cx + r * math.cos(a), cy + r * 0.55 + r * math.sin(a)))
    d.polygon(pts, fill=(70, 160, 230), outline=(30, 110, 190))
    d.ellipse([cx - r * 0.55, cy + r * 0.1, cx - r * 0.1, cy + r * 0.55], fill=(190, 225, 255))


def _ic_fire(d, cx, cy, r, c):
    pts = [(cx, cy - r * 1.2), (cx + r * 0.7, cy - r * 0.1), (cx + r * 0.45, cy + r),
           (cx - r * 0.45, cy + r), (cx - r * 0.7, cy - r * 0.1)]
    d.polygon(pts, fill=(240, 110, 30))
    inner = [(cx, cy - r * 0.55), (cx + r * 0.38, cy + r * 0.2), (cx, cy + r * 0.8),
             (cx - r * 0.38, cy + r * 0.2)]
    d.polygon(inner, fill=(255, 210, 70))


def _ic_snow(d, cx, cy, r, c):
    col = (150, 210, 255)
    for k in range(6):
        a = math.radians(k * 60)
        ex, ey = cx + r * math.cos(a), cy + r * math.sin(a)
        d.line([(cx, cy), (ex, ey)], fill=col, width=10)
        for s in (0.45, 0.7):
            bx, by = cx + r * s * math.cos(a), cy + r * s * math.sin(a)
            for db in (math.radians(35), math.radians(-35)):
                d.line([(bx, by), (bx + r * 0.22 * math.cos(a + db),
                                   by + r * 0.22 * math.sin(a + db))], fill=col, width=8)


def _ic_bolt(d, cx, cy, r, c):
    pts = [(cx - r * 0.15, cy - r), (cx + r * 0.55, cy - r * 0.1),
           (cx + r * 0.08, cy - r * 0.1), (cx + r * 0.35, cy + r),
           (cx - r * 0.55, cy + r * 0.05), (cx - r * 0.02, cy + r * 0.05)]
    d.polygon(pts, fill=(255, 205, 40), outline=(210, 150, 0))


def _ic_magnet(d, cx, cy, r, c):
    w = int(r * 0.5)
    d.arc([cx - r, cy - r, cx + r, cy + r], 200, 340, fill=(120, 120, 130), width=w)
    d.rectangle([cx - r, cy, cx - r + w, cy + r * 0.7], fill=(210, 50, 50))
    d.rectangle([cx + r - w, cy, cx + r, cy + r * 0.7], fill=(60, 90, 220))


def _ic_atom(d, cx, cy, r, c):
    for ang in (0, 60, 120):
        orbit = Image.new("RGBA", (int(r * 3), int(r * 3)), (0, 0, 0, 0))
        od = ImageDraw.Draw(orbit)
        od.ellipse([0, int(r * 0.9), int(r * 3), int(r * 2.1)], outline=(90, 160, 220), width=8)
        orbit = orbit.rotate(ang, expand=False, resample=Image.BICUBIC)
        d._image.paste(orbit, (int(cx - r * 1.5), int(cy - r * 1.5)), orbit)
    d.ellipse([cx - r * 0.28, cy - r * 0.28, cx + r * 0.28, cy + r * 0.28], fill=(230, 80, 60))


def _ic_dna(d, cx, cy, r, c):
    a = (220, 70, 90)
    b = (70, 130, 220)
    pts_a, pts_b = [], []
    for t in range(0, 101, 4):
        y = cy - r + (2 * r) * t / 100
        off = r * 0.55 * math.sin(t / 100 * math.pi * 3)
        pts_a.append((cx + off, y))
        pts_b.append((cx - off, y))
    for i in range(0, len(pts_a), 3):
        d.line([pts_a[i], pts_b[i]], fill=(170, 170, 170), width=6)
    d.line(pts_a, fill=a, width=12, joint="curve")
    d.line(pts_b, fill=b, width=12, joint="curve")


def _ic_brain(d, cx, cy, r, c):
    d.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], fill=(244, 160, 180),
              outline=(200, 100, 130), width=8)
    for off in (-r * 0.4, 0, r * 0.4):
        d.arc([cx + off - r * 0.35, cy - r * 0.6, cx + off + r * 0.35, cy + r * 0.6],
              0, 360, fill=(200, 100, 130), width=6)


def _ic_heart(d, cx, cy, r, c):
    d.ellipse([cx - r, cy - r * 0.8, cx, cy + r * 0.2], fill=(225, 60, 80))
    d.ellipse([cx, cy - r * 0.8, cx + r, cy + r * 0.2], fill=(225, 60, 80))
    d.polygon([(cx - r * 0.92, cy - r * 0.15), (cx + r * 0.92, cy - r * 0.15),
               (cx, cy + r)], fill=(225, 60, 80))


def _ic_eye(d, cx, cy, r, c):
    d.polygon([(cx - r, cy), (cx, cy - r * 0.6), (cx + r, cy), (cx, cy + r * 0.6)],
              fill=(255, 255, 255), outline=(60, 60, 70))
    d.ellipse([cx - r, cy - r * 0.55, cx + r, cy + r * 0.55], outline=(60, 60, 70), width=8)
    d.ellipse([cx - r * 0.34, cy - r * 0.34, cx + r * 0.34, cy + r * 0.34], fill=(90, 130, 90))
    d.ellipse([cx - r * 0.15, cy - r * 0.15, cx + r * 0.15, cy + r * 0.15], fill=(20, 20, 20))


def _ic_leaf(d, cx, cy, r, c):
    pts = [(cx, cy - r), (cx + r * 0.8, cy), (cx, cy + r), (cx - r * 0.8, cy)]
    d.polygon(pts, fill=(110, 190, 90), outline=(50, 130, 50))
    d.line([(cx, cy - r), (cx, cy + r)], fill=(50, 130, 50), width=8)
    for s in (-0.5, 0, 0.5):
        d.line([(cx, cy + r * s), (cx + r * 0.5, cy + r * s - r * 0.25)],
               fill=(50, 130, 50), width=5)


def _ic_microbe(d, cx, cy, r, c):
    for k in range(16):
        a = math.radians(k * 22.5)
        d.line([(cx + r * math.cos(a), cy + r * math.sin(a)),
                (cx + r * 1.25 * math.cos(a), cy + r * 1.25 * math.sin(a))],
               fill=(80, 170, 110), width=7)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(130, 205, 140), outline=(50, 130, 70), width=7)
    for dx, dy in [(-0.35, -0.2), (0.3, 0.1), (0.0, 0.4), (-0.15, 0.25)]:
        d.ellipse([cx + r * dx - 14, cy + r * dy - 14, cx + r * dx + 14, cy + r * dy + 14],
                  fill=(50, 130, 70))


def _ic_rocket(d, cx, cy, r, c):
    body = (235, 235, 240)
    d.polygon([(cx, cy - r), (cx + r * 0.4, cy - r * 0.2), (cx + r * 0.4, cy + r * 0.6),
               (cx - r * 0.4, cy + r * 0.6), (cx - r * 0.4, cy - r * 0.2)],
              fill=body, outline=(120, 120, 130))
    d.ellipse([cx - r * 0.18, cy - r * 0.4, cx + r * 0.18, cy - r * 0.04], fill=(90, 150, 220))
    d.polygon([(cx - r * 0.4, cy + r * 0.2), (cx - r * 0.7, cy + r * 0.65),
               (cx - r * 0.4, cy + r * 0.6)], fill=(220, 70, 70))
    d.polygon([(cx + r * 0.4, cy + r * 0.2), (cx + r * 0.7, cy + r * 0.65),
               (cx + r * 0.4, cy + r * 0.6)], fill=(220, 70, 70))
    d.polygon([(cx - r * 0.2, cy + r * 0.6), (cx, cy + r * 1.1), (cx + r * 0.2, cy + r * 0.6)],
              fill=(255, 180, 50))


def _ic_gear(d, cx, cy, r, c):
    col = (150, 155, 165)
    for k in range(8):
        a = math.radians(k * 45)
        d.rectangle([cx + r * 0.9 * math.cos(a) - 18, cy + r * 0.9 * math.sin(a) - 18,
                     cx + r * 0.9 * math.cos(a) + 18, cy + r * 0.9 * math.sin(a) + 18], fill=col)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=(90, 95, 105), width=6)
    d.ellipse([cx - r * 0.35, cy - r * 0.35, cx + r * 0.35, cy + r * 0.35], fill=(60, 65, 75))


def _ic_clock(d, cx, cy, r, c):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(250, 250, 245), outline=(70, 70, 80), width=10)
    d.line([(cx, cy), (cx, cy - r * 0.6)], fill=(40, 40, 50), width=12)
    d.line([(cx, cy), (cx + r * 0.5, cy + r * 0.15)], fill=(40, 40, 50), width=10)
    d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(210, 60, 60))


def _ic_wave(d, cx, cy, r, c):
    col = (90, 150, 220)
    for off in (-r * 0.5, 0, r * 0.5):
        pts = [(cx - r + i * (2 * r / 40), cy + off + r * 0.4 * math.sin(i / 40 * math.pi * 4))
               for i in range(41)]
        d.line(pts, fill=col, width=9, joint="curve")


def _ic_cloud(d, cx, cy, r, c):
    col = (200, 215, 235)
    for dx, dy, rr in [(-0.55, 0.1, 0.55), (0.0, -0.25, 0.7), (0.6, 0.1, 0.55), (0.0, 0.2, 0.65)]:
        d.ellipse([cx + r * dx - r * rr, cy + r * dy - r * rr,
                   cx + r * dx + r * rr, cy + r * dy + r * rr], fill=col)


def _ic_mountain(d, cx, cy, r, c):
    d.polygon([(cx - r, cy + r * 0.7), (cx - r * 0.2, cy - r), (cx + r * 0.5, cy + r * 0.7)],
              fill=(110, 120, 110))
    d.polygon([(cx - r * 0.1, cy + r * 0.7), (cx + r * 0.5, cy - r * 0.6), (cx + r, cy + r * 0.7)],
              fill=(140, 150, 140))
    d.polygon([(cx - r * 0.45, cy - r * 0.45), (cx - r * 0.2, cy - r), (cx + r * 0.05, cy - r * 0.45)],
              fill=(250, 250, 255))


def _ic_thermo(d, cx, cy, r, c):
    d.rounded_rectangle([cx - r * 0.18, cy - r, cx + r * 0.18, cy + r * 0.5],
                        radius=int(r * 0.18), fill=(240, 240, 245), outline=(80, 80, 90), width=8)
    d.ellipse([cx - r * 0.42, cy + r * 0.3, cx + r * 0.42, cy + r * 1.05],
              fill=(220, 60, 60), outline=(80, 80, 90), width=8)
    d.rectangle([cx - r * 0.1, cy - r * 0.2, cx + r * 0.1, cy + r * 0.6], fill=(220, 60, 60))


def _ic_bulb(d, cx, cy, r, c):
    d.ellipse([cx - r * 0.7, cy - r, cx + r * 0.7, cy + r * 0.4], fill=(255, 224, 120),
              outline=(210, 170, 40), width=8)
    d.rectangle([cx - r * 0.3, cy + r * 0.35, cx + r * 0.3, cy + r * 0.7], fill=(170, 170, 180))
    d.line([(cx - r * 0.3, cy + r * 0.5), (cx + r * 0.3, cy + r * 0.5)], fill=(120, 120, 130), width=6)
    for k in range(6):
        a = math.radians(-90 + (k - 2.5) * 28)
        d.line([(cx + r * 0.95 * math.cos(a), cy - r * 0.3 + r * 0.95 * math.sin(a)),
                (cx + r * 1.35 * math.cos(a), cy - r * 0.3 + r * 1.35 * math.sin(a))],
               fill=(255, 200, 60), width=8)


# ------------------------------------------------------------------
# 体・生理系アイコン (daily-science は身近な体の不思議テーマが多い)
# ------------------------------------------------------------------
def _ic_droplet(d, cx, cy, r, c):
    """汗・水滴。"""
    col = (90, 175, 235)
    pts = [(cx, cy - r * 1.15)]
    for k in range(1, 15):
        a = math.radians(-90 + k * (360 / 16))
        pts.append((cx + r * math.cos(a), cy + r * 0.45 + r * math.sin(a)))
    d.polygon(pts, fill=col, outline=(40, 120, 195))
    d.ellipse([cx - r * 0.5, cy + r * 0.05, cx - r * 0.12, cy + r * 0.45], fill=(200, 230, 255))


def _ic_lungs(d, cx, cy, r, c):
    """呼吸・肺。"""
    col = (235, 150, 165)
    line = (185, 90, 115)
    d.line([(cx, cy - r), (cx, cy - r * 0.2)], fill=line, width=10)  # 気管
    d.line([(cx, cy - r * 0.2), (cx - r * 0.5, cy - r * 0.05)], fill=line, width=8)
    d.line([(cx, cy - r * 0.2), (cx + r * 0.5, cy - r * 0.05)], fill=line, width=8)
    for sx in (-1, 1):
        box = [cx + (sx * r * 0.1), cy - r * 0.1, cx + sx * r, cy + r]
        x0, x1 = min(box[0], box[2]), max(box[0], box[2])
        d.rounded_rectangle([x0, box[1], x1, box[3]], radius=int(r * 0.35),
                            fill=col, outline=line, width=6)


def _ic_bone(d, cx, cy, r, c):
    """骨・骨伝導。"""
    col = (245, 243, 232)
    line = (170, 165, 150)
    for sx in (-1, 1):
        for sy in (-1, 1):
            d.ellipse([cx + sx * r - r * 0.32, cy + sy * r * 0.55 - r * 0.32,
                       cx + sx * r + r * 0.32, cy + sy * r * 0.55 + r * 0.32],
                      fill=col, outline=line, width=6)
    d.line([(cx - r, cy), (cx + r, cy)], fill=col, width=int(r * 0.5))
    d.line([(cx - r, cy - r * 0.24), (cx + r, cy - r * 0.24)], fill=line, width=4)
    d.line([(cx - r, cy + r * 0.24), (cx + r, cy + r * 0.24)], fill=line, width=4)


def _ic_hand(d, cx, cy, r, c):
    """手。"""
    col = (250, 214, 190)
    line = (205, 155, 130)
    d.rounded_rectangle([cx - r * 0.6, cy - r * 0.1, cx + r * 0.6, cy + r],
                        radius=int(r * 0.3), fill=col, outline=line, width=6)
    for i, fx in enumerate((-0.42, -0.14, 0.14, 0.42)):
        h = r * (0.85 + (0.12 if i in (1, 2) else 0))
        d.rounded_rectangle([cx + fx * r - r * 0.14, cy - h, cx + fx * r + r * 0.14, cy + r * 0.05],
                            radius=int(r * 0.14), fill=col, outline=line, width=5)
    d.rounded_rectangle([cx - r, cy + r * 0.05, cx - r * 0.45, cy + r * 0.4],
                        radius=int(r * 0.14), fill=col, outline=line, width=5)


def _ic_skin(d, cx, cy, r, c):
    """皮膚（層構造）。"""
    layers = [(248, 220, 200), (232, 190, 168), (210, 158, 140)]
    for i, col in enumerate(layers):
        y0 = cy - r * 0.7 + i * r * 0.55
        d.rounded_rectangle([cx - r, y0, cx + r, y0 + r * 0.5],
                            radius=int(r * 0.12), fill=col, outline=(170, 120, 100), width=4)
    for hx in (-0.5, 0.0, 0.5):
        d.line([(cx + hx * r, cy - r * 0.7), (cx + hx * r, cy - r * 1.05)],
               fill=(140, 100, 80), width=6)  # 毛


def _ic_muscle(d, cx, cy, r, c):
    """筋肉（力こぶ）。"""
    col = (225, 120, 110)
    line = (180, 75, 70)
    d.pieslice([cx - r, cy - r, cx + r * 0.6, cy + r * 0.3], 200, 20, fill=col, outline=line, width=6)
    d.rounded_rectangle([cx + r * 0.2, cy + r * 0.05, cx + r, cy + r],
                        radius=int(r * 0.25), fill=col, outline=line, width=6)  # 前腕
    d.arc([cx - r * 0.6, cy - r * 0.6, cx + r * 0.2, cy + r * 0.2], 210, 350, fill=line, width=5)


def _ic_stomach(d, cx, cy, r, c):
    """胃。"""
    col = (240, 165, 150)
    line = (195, 105, 95)
    d.line([(cx - r * 0.1, cy - r), (cx - r * 0.1, cy - r * 0.3)], fill=line, width=10)  # 食道
    d.pieslice([cx - r, cy - r * 0.5, cx + r, cy + r], 0, 360, fill=col, outline=line, width=6)
    d.line([(cx + r * 0.65, cy + r * 0.4), (cx + r, cy + r * 0.2)], fill=line, width=10)  # 十二指腸


def _ic_intestine(d, cx, cy, r, c):
    """腸。"""
    col = (240, 175, 160)
    d.rounded_rectangle([cx - r, cy - r, cx + r, cy + r], radius=int(r * 0.3),
                        outline=col, width=int(r * 0.28))
    pts = []
    for i in range(0, 61):
        t = i / 60
        x = cx - r * 0.55 + t * r * 1.1
        y = cy + r * 0.4 * math.sin(t * math.pi * 4)
        pts.append((x, y))
    d.line(pts, fill=(210, 130, 120), width=int(r * 0.22), joint="curve")


def _ic_ear(d, cx, cy, r, c):
    """耳。"""
    col = (250, 214, 190)
    line = (200, 150, 125)
    d.pieslice([cx - r, cy - r, cx + r, cy + r], 60, 330, fill=col, outline=line, width=7)
    d.arc([cx - r * 0.5, cy - r * 0.6, cx + r * 0.4, cy + r * 0.4], 40, 320, fill=line, width=7)
    d.arc([cx - r * 0.15, cy - r * 0.2, cx + r * 0.3, cy + r * 0.35], 0, 360, fill=line, width=6)


def _ic_nose(d, cx, cy, r, c):
    """鼻。"""
    col = (250, 214, 190)
    line = (200, 150, 125)
    d.polygon([(cx, cy - r), (cx + r * 0.55, cy + r * 0.6), (cx - r * 0.55, cy + r * 0.6)],
              fill=col, outline=line)
    d.line([(cx, cy - r), (cx + r * 0.55, cy + r * 0.6)], fill=line, width=6)
    d.line([(cx, cy - r), (cx - r * 0.55, cy + r * 0.6)], fill=line, width=6)
    for sx in (-1, 1):
        d.ellipse([cx + sx * r * 0.34 - r * 0.14, cy + r * 0.35, cx + sx * r * 0.34 + r * 0.14, cy + r * 0.6],
                  fill=(150, 100, 85))


def _ic_tongue(d, cx, cy, r, c):
    """舌・味覚。"""
    d.pieslice([cx - r, cy - r * 0.9, cx + r, cy + r * 0.7], 0, 180, fill=(235, 120, 130), outline=(190, 70, 90), width=6)  # 口(下唇)
    d.chord([cx - r, cy - r, cx + r, cy + r * 0.4], 0, 180, fill=(70, 40, 45))  # 口内
    d.pieslice([cx - r * 0.55, cy - r * 0.25, cx + r * 0.55, cy + r * 0.9], 180, 360, fill=(240, 130, 145), outline=(200, 80, 100), width=5)  # 舌
    d.line([(cx, cy + r * 0.05), (cx, cy + r * 0.7)], fill=(200, 80, 100), width=5)


def _ic_tooth(d, cx, cy, r, c):
    """歯。"""
    col = (250, 250, 245)
    line = (185, 185, 175)
    d.pieslice([cx - r * 0.8, cy - r, cx + r * 0.8, cy + r * 0.2], 180, 360, fill=col, outline=line, width=6)
    d.polygon([(cx - r * 0.8, cy - r * 0.4), (cx - r * 0.55, cy + r), (cx - r * 0.2, cy - r * 0.1)],
              fill=col, outline=line)
    d.polygon([(cx + r * 0.8, cy - r * 0.4), (cx + r * 0.55, cy + r), (cx + r * 0.2, cy - r * 0.1)],
              fill=col, outline=line)
    d.line([(cx - r * 0.8, cy - r * 0.3), (cx - r * 0.55, cy + r)], fill=line, width=5)
    d.line([(cx + r * 0.8, cy - r * 0.3), (cx + r * 0.55, cy + r)], fill=line, width=5)


def _ic_hair(d, cx, cy, r, c):
    """髪。"""
    col = (90, 70, 60)
    for off in (-0.6, -0.2, 0.2, 0.6):
        pts = [(cx + off * r + r * 0.35 * math.sin(t / 10 * math.pi * 2), cy - r + t / 10 * r * 2)
               for t in range(0, 11)]
        d.line(pts, fill=col, width=12, joint="curve")


_TEXTBOOK_ICONS = {
    "sun": _ic_sun, "moon": _ic_moon, "planet": _ic_planet, "water": _ic_water,
    "fire": _ic_fire, "snow": _ic_snow, "bolt": _ic_bolt, "magnet": _ic_magnet,
    "atom": _ic_atom, "dna": _ic_dna, "brain": _ic_brain, "heart": _ic_heart,
    "eye": _ic_eye, "leaf": _ic_leaf, "microbe": _ic_microbe, "rocket": _ic_rocket,
    "gear": _ic_gear, "clock": _ic_clock, "wave": _ic_wave, "cloud": _ic_cloud,
    "mountain": _ic_mountain, "thermo": _ic_thermo, "bulb": _ic_bulb,
    "droplet": _ic_droplet, "lungs": _ic_lungs, "bone": _ic_bone, "hand": _ic_hand,
    "skin": _ic_skin, "muscle": _ic_muscle, "stomach": _ic_stomach,
    "intestine": _ic_intestine, "ear": _ic_ear, "nose": _ic_nose,
    "tongue": _ic_tongue, "tooth": _ic_tooth, "hair": _ic_hair,
}

# キーワード → (icon, ラベル)。先に書いたものほど優先(longerマッチ重視で順序配置)。
_TEXTBOOK_KEYWORDS = [
    (("光合成",), ("leaf", "光合成")),
    # --- 体・生理系(daily-science は身近な体の不思議テーマが多いので優先的に先頭付近へ) ---
    (("骨伝導", "骨", "骨格"), ("bone", "骨")),
    (("汗", "発汗"), ("droplet", "汗")),
    (("呼吸", "肺", "息", "酸欠"), ("lungs", "呼吸")),
    (("筋肉", "筋", "こむら", "つる"), ("muscle", "筋肉")),
    (("皮膚", "肌", "鳥肌", "かゆ", "湿疹"), ("skin", "皮膚")),
    (("胃", "胃酸", "空腹", "消化"), ("stomach", "胃")),
    (("腸", "便", "腸内", "お腹"), ("intestine", "腸")),
    (("耳", "聴覚", "鼓膜", "耳鳴り"), ("ear", "耳")),
    (("鼻", "嗅覚", "くしゃみ", "匂い", "におい"), ("nose", "鼻")),
    (("舌", "味覚", "味", "唾液"), ("tongue", "味覚")),
    (("歯", "虫歯", "咀嚼", "噛"), ("tooth", "歯")),
    (("髪", "毛", "抜け毛", "白髪"), ("hair", "髪")),
    (("手", "指", "爪", "握"), ("hand", "手")),
    (("睡眠", "眠", "寝", "夢", "あくび"), ("moon", "睡眠")),
    (("血液", "血流", "血管", "貧血"), ("heart", "血液")),
    (("太陽", "日光", "恒星", "サン"), ("sun", "太陽")),
    (("月", "ムーン"), ("moon", "月")),
    (("惑星", "地球", "宇宙", "星", "天体"), ("planet", "惑星")),
    (("ロケット", "宇宙船", "打ち上げ"), ("rocket", "ロケット")),
    (("酸素", "気体", "空気", "大気", "二酸化炭素"), ("cloud", "気体")),
    (("水", "海", "液体", "水分", "湿"), ("water", "水")),
    (("炎", "火", "燃焼", "熱", "高温"), ("fire", "熱")),
    (("氷", "雪", "冷", "低温", "凍"), ("snow", "氷")),
    (("雷", "電気", "電流", "電子", "放電", "感電"), ("bolt", "電気")),
    (("磁", "磁石", "磁場"), ("magnet", "磁力")),
    (("原子", "分子", "元素", "化学", "物質"), ("atom", "原子")),
    (("DNA", "遺伝", "ゲノム", "染色体"), ("dna", "遺伝子")),
    (("脳", "神経", "記憶", "思考"), ("brain", "脳")),
    (("心臓", "血", "血液", "鼓動", "循環"), ("heart", "心臓")),
    (("目", "視覚", "視力", "網膜", "光", "見え"), ("eye", "視覚")),
    (("細胞", "菌", "ウイルス", "微生物", "バクテリア", "感染"), ("microbe", "細胞")),
    (("植物", "葉", "緑", "森", "木"), ("leaf", "植物")),
    (("歯車", "機械", "仕組み", "装置", "エンジン", "構造"), ("gear", "仕組み")),
    (("時間", "時計", "速度", "秒", "周期"), ("clock", "時間")),
    (("音", "振動", "波", "周波", "音波"), ("wave", "波")),
    (("山", "地震", "火山", "地層", "岩"), ("mountain", "地形")),
    (("雲", "雨", "天気", "気象", "嵐"), ("cloud", "天気")),
    (("温度", "気温", "体温"), ("thermo", "温度")),
    (("エネルギー", "力", "パワー"), ("bolt", "エネルギー")),
]


def _match_textbook(topic):
    found = []
    seen = set()
    for keys, (icon, label) in _TEXTBOOK_KEYWORDS:
        if any(k in topic for k in keys):
            if icon not in seen:
                found.append((icon, label))
                seen.add(icon)
        if len(found) >= 2:
            break
    return found


def _render_textbook(topic, use_keyword_icons=True):
    """daily-science: 透過背景に色付き解説図。

    `_TEXTBOOK_KEYWORDS` は理科系の語彙で組んであるため、実話系スレ・雑談系の
    チャンネルに使うと部分一致で無関係な図が出る（「月額いくら払えば」→ 月アイコン、
    「全員が黙った」→ 視覚アイコン等）。図解が題材と噛み合わないチャンネルは
    use_keyword_icons=False を渡して、テーマ語を大きく見せる分岐に倒す。
    """
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    found = _match_textbook(topic or "") if use_keyword_icons else []
    accent = (74, 108, 212)
    label_col = (40, 50, 70)

    if len(found) >= 2:
        (ic1, lb1), (ic2, lb2) = found[0], found[1]
        r = 175
        cy = CANVAS_H // 2 - 40
        x1, x2 = int(CANVAS_W * 0.24), int(CANVAS_W * 0.76)
        _TEXTBOOK_ICONS[ic1](d, x1, cy, r, accent)
        _TEXTBOOK_ICONS[ic2](d, x2, cy, r, accent)
        _arrow(d, x1 + int(r * 1.35), cy, x2 - int(r * 1.35), cy, accent, width=14, head=34)
        _label(d, x1, cy + r + 70, lb1, 64, label_col)
        _label(d, x2, cy + r + 70, lb2, 64, label_col)
    elif len(found) == 1:
        ic, lb = found[0]
        r = 215
        cx, cy = CANVAS_W // 2, CANVAS_H // 2 - 50
        _TEXTBOOK_ICONS[ic](d, cx, cy, r, accent)
        # 装飾の指し示し点
        for sx in (cx - int(r * 2.1), cx + int(r * 2.1)):
            d.ellipse([sx - 12, cy - 12, sx + 12, cy + 12], fill=accent)
            _arrow(d, sx + (28 if sx < cx else -28), cy,
                   cx + (int(-r * 1.25) if sx < cx else int(r * 1.25)), cy,
                   accent, width=9, head=22)
        _label(d, cx, cy + r + 78, lb, 70, label_col)
    else:
        # キーワード未ヒット: テーマ語そのものを大きく見せる(電球固定はやめる)。
        snippet = (topic or "").strip().replace("\n", " ")
        # 助詞を落として要点だけ残す簡易処理。「！？」はセリフの温度を運ぶので残す
        # （use_keyword_icons=False のチャンネルではこの分岐が主役の描画になる）。
        for junk in ("なぜ", "とは", "について", "の理由", "の正体", "の秘密", "…"):
            snippet = snippet.replace(junk, " ")
        snippet = " ".join(snippet.split())
        # 文の途中でぶつ切りにせず、句読点・記号で切れるならそこで閉じる
        if len(snippet) > 24:
            head = snippet[:24]
            cut = max((head.rfind(c) for c in "。！？、」"), default=-1)
            snippet = head[: cut + 1] if cut >= 12 else head
        snippet = snippet or "ポイント"
        # 1行あたりの文字数で 2〜3 行に折り返し
        per_line = 8
        lines = [snippet[i:i + per_line] for i in range(0, len(snippet), per_line)][:3]
        # 文字サイズは行数に応じて可変(1行=特大)
        size = {1: 150, 2: 120}.get(len(lines), 96)
        line_h = size + 26
        total_h = line_h * len(lines)
        top = CANVAS_H // 2 - total_h // 2 + size // 2 - 10
        # 装飾: 上下のアクセントバー
        bar_w = int(CANVAS_W * 0.34)
        cx = CANVAS_W // 2
        d.rounded_rectangle([cx - bar_w // 2, top - size, cx + bar_w // 2, top - size + 14],
                            radius=7, fill=accent)
        for li, ln in enumerate(lines):
            _label(d, cx, top + li * line_h, ln, size, (30, 42, 66),
                   stroke_fill=(255, 255, 255), stroke_width=6)
        d.rounded_rectangle([cx - bar_w // 2, top + total_h - line_h + size,
                             cx + bar_w // 2, top + total_h - line_h + size + 14],
                            radius=7, fill=accent)
    return img


# ==================================================================
# 流出文書風シルエット (モノクロ前提 / 不透明ダーク背景)
# ==================================================================
LK_BG = (32, 30, 28, 255)
LK_LINE = (205, 205, 200)
LK_DIM = (120, 118, 114)


def _lk_humanoid(d, cx, cy, r):
    d.ellipse([cx - r * 0.32, cy - r, cx + r * 0.32, cy - r * 0.36], outline=LK_LINE, width=8)
    d.polygon([(cx - r * 0.5, cy + r), (cx - r * 0.42, cy - r * 0.2),
               (cx + r * 0.42, cy - r * 0.2), (cx + r * 0.5, cy + r)], outline=LK_LINE)
    for pts in [[(cx - r * 0.5, cy + r), (cx - r * 0.42, cy - r * 0.2),
                 (cx + r * 0.42, cy - r * 0.2), (cx + r * 0.5, cy + r)]]:
        for i in range(len(pts)):
            d.line([pts[i], pts[(i + 1) % len(pts)]], fill=LK_LINE, width=8)


def _lk_eye(d, cx, cy, r):
    d.ellipse([cx - r, cy - r * 0.55, cx + r, cy + r * 0.55], outline=LK_LINE, width=9)
    d.ellipse([cx - r * 0.36, cy - r * 0.36, cx + r * 0.36, cy + r * 0.36], outline=LK_LINE, width=8)
    d.ellipse([cx - r * 0.12, cy - r * 0.12, cx + r * 0.12, cy + r * 0.12], fill=LK_LINE)
    # 不穏な放射
    for k in range(12):
        a = math.radians(k * 30)
        d.line([(cx + r * 0.4 * math.cos(a), cy + r * 0.4 * math.sin(a)),
                (cx + r * 0.34 * math.cos(a), cy + r * 0.34 * math.sin(a))], fill=LK_DIM, width=5)


def _lk_statue(d, cx, cy, r):
    _lk_humanoid(d, cx, cy - r * 0.2, r * 0.85)
    d.rectangle([cx - r * 0.7, cy + r * 0.8, cx + r * 0.7, cy + r * 1.1], outline=LK_LINE, width=8)
    d.rectangle([cx - r * 0.9, cy + r * 1.1, cx + r * 0.9, cy + r * 1.3], outline=LK_LINE, width=8)


def _lk_object(d, cx, cy, r):
    # 立方体(異常物体)
    s = r * 0.7
    front = [(cx - s, cy - s + r * 0.25), (cx + s, cy - s + r * 0.25),
             (cx + s, cy + s + r * 0.25), (cx - s, cy + s + r * 0.25)]
    for i in range(4):
        d.line([front[i], front[(i + 1) % 4]], fill=LK_LINE, width=8)
    off = r * 0.4
    for (x, y) in front[:3]:
        d.line([(x, y), (x + off, y - off)], fill=LK_DIM, width=6)
    d.line([(front[0][0] + off, front[0][1] - off), (front[1][0] + off, front[1][1] - off)],
           fill=LK_DIM, width=6)
    d.line([(front[1][0] + off, front[1][1] - off), (front[2][0] + off, front[2][1] - off)],
           fill=LK_DIM, width=6)


def _lk_door(d, cx, cy, r):
    d.rectangle([cx - r * 0.55, cy - r, cx + r * 0.55, cy + r], outline=LK_LINE, width=9)
    d.line([(cx, cy - r), (cx, cy + r)], fill=LK_DIM, width=5)
    d.ellipse([cx - r * 0.45, cy - 10, cx - r * 0.45 + 20, cy + 10], fill=LK_LINE)


_LEAKED_FIG = {
    "humanoid": _lk_humanoid, "eye": _lk_eye, "statue": _lk_statue,
    "object": _lk_object, "door": _lk_door,
}

_LEAKED_KEYWORDS = [
    (("目", "視線", "見つめ", "瞳", "監視"), ("eye", "視認体")),
    (("像", "彫像", "石像", "人形", "マネキン"), ("statue", "実体")),
    (("人型", "人影", "人間", "ヒューマノイド", "姿", "影"), ("humanoid", "対象")),
    (("扉", "ドア", "出入口", "ゲート"), ("door", "封鎖")),
    (("物体", "装置", "箱", "立方", "オブジェクト", "遺物", "鏡"), ("object", "異常物体")),
]


def _match_leaked(topic):
    for keys, (fig, label) in _LEAKED_KEYWORDS:
        if any(k in topic for k in keys):
            return fig, label
    return "humanoid", "対象実体"


def _render_leaked(topic):
    """scp-lab: 不透明ダーク背景・ライトグレーの収容図(後段でL変換される)。"""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), LK_BG)
    d = ImageDraw.Draw(img)
    # film-grain っぽいスキャンライン
    for y in range(0, CANVAS_H, 6):
        d.line([(0, y), (CANVAS_W, y)], fill=(0, 0, 0, 40), width=1)

    fig, label = _match_leaked(topic or "")
    cx, cy = CANVAS_W // 2, CANVAS_H // 2 - 20
    r = 190

    # 収容チャンバー枠 (二重枠 + コーナーティック)
    m = 70
    box = [m, m, CANVAS_W - m, CANVAS_H - m]
    d.rectangle(box, outline=LK_DIM, width=4)
    inset = 16
    d.rectangle([box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset],
                outline=LK_DIM, width=2)
    tick = 46
    for (x, y, dx, dy) in [(box[0], box[1], 1, 1), (box[2], box[1], -1, 1),
                           (box[0], box[3], 1, -1), (box[2], box[3], -1, -1)]:
        d.line([(x, y), (x + dx * tick, y)], fill=LK_LINE, width=7)
        d.line([(x, y), (x, y + dy * tick)], fill=LK_LINE, width=7)

    # 中央シルエット
    _LEAKED_FIG[fig](d, cx, cy, r)

    # 指し示し線 + 偽の寸法
    d.line([(cx + r * 0.7, cy - r * 0.6), (cx + r * 2.0, cy - r * 1.0)], fill=LK_DIM, width=3)
    _label(d, cx + r * 2.0 + 110, cy - r * 1.0, "?.?m", 44, LK_LINE)

    # ハザード三角(左下)
    hx, hy, hr = m + 80, CANVAS_H - m - 70, 56
    d.polygon([(hx, hy - hr), (hx - hr * 0.9, hy + hr * 0.6), (hx + hr * 0.9, hy + hr * 0.6)],
              outline=LK_LINE)
    tri = [(hx, hy - hr), (hx - hr * 0.9, hy + hr * 0.6), (hx + hr * 0.9, hy + hr * 0.6)]
    for i in range(3):
        d.line([tri[i], tri[(i + 1) % 3]], fill=LK_LINE, width=6)
    _label(d, hx, hy + 4, "!", 50, LK_LINE)

    # 分類ラベル(中央下)
    _label(d, cx, CANVAS_H - m - 36, label, 50, LK_LINE)
    return img


# ==================================================================
# 公開エントリ
# ==================================================================
def generate_pillow_illustration(topic_text, *, card_style="textbook",
                                 illust_style=None, idx=0, cache_dir=None,
                                 channel_id=None, use_keyword_icons=True):
    """テーマからローカル図解を描いて RGBA PIL Image を返す (APIコスト0)。

    card_style:
      "leaked-document" → scp-lab 流出文書風(モノクロ前提のダーク図)
      それ以外          → daily-science 教科書風(透過カラー図)

    use_keyword_icons=False で理科系アイコンの語句マッチを止め、テーマ語を
    大きく見せる描画に倒す（実話系スレなど、図解が題材と噛み合わないチャンネル用）。
    """
    if cache_dir:
        cache_path = Path(cache_dir) / f"pillow_{idx:03d}.png"
        if cache_path.exists():
            try:
                return Image.open(str(cache_path)).convert("RGBA")
            except Exception:
                pass

    topic = (topic_text or "").strip()
    style = (card_style or "textbook").lower()
    try:
        if style == "leaked-document":
            img = _render_leaked(topic)
        else:
            img = _render_textbook(topic, use_keyword_icons=use_keyword_icons)
    except Exception as e:
        print(f"⚠️ pillow illustration draw failed: {e}")
        return None

    if cache_dir:
        try:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            img.save(str(Path(cache_dir) / f"pillow_{idx:03d}.png"))
        except Exception:
            pass
    return img
