"""外部ナレーション音源から長尺動画を組み立てるパイプライン。

video_generator.py は VOICEVOX で1行ずつ合成した音声を前提にしており、
「1行 = 1音声ファイル = 1クリップ」で尺を積み上げていく。
運営者が完成済みの音源を持ち込むチャンネル（scenario_source: "manual"）では
その前提が成り立たないため、ここでは音声を動かせないタイムラインとして扱い、
背景（章ごと）と字幕オーバーレイだけを描いて ffmpeg で1パス合成する。

入力:
    audio    完成済みナレーション音声（wav/mp3）
    cues     [{start, end, text}, ...] 字幕。時刻は音声に対する秒。
    chapters [{index, title, start, end}, ...] 章立て。

描画は Pillow（video_generator と同じ体裁）、合成は ffmpeg。
オーバーレイは concat demuxer で「PNG + 表示秒数」の列として流し込み、
章ごとにゆっくり流れる背景の上に overlay フィルタで重ねる。
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.video_generator import (  # noqa: E402
    _apply_vignette,
    _call_openai_image,
    draw_composite_text,
    get_en_font,
    measure_composite_text,
    wrap_text,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHANNELS_DIR = REPO_ROOT / "data" / "channels"

FPS = 30
CARD_SECONDS = 6.0        # 章タイトルカードの表示秒数
CARD_FADE = 0.7           # カードのフェードイン/アウト秒数
FADE_STEPS = 12           # フェードを何段階のPNGで表現するか
PAN_ZOOM = 1.14           # 背景の流し込み倍率（大きいほど動きが速い）

_KANJI_NUM = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def kanji_chapter(n):
    """1 → 「第一章」。10章構成なので十まで対応すれば足りる。"""
    if 1 <= n < len(_KANJI_NUM):
        return f"第{_KANJI_NUM[n]}章"
    return f"第{n}章"


def load_channel(channel_id):
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"channel config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(channel_dict):
    return (channel_dict or {}).get("video_format", {}) or {}


def _narrator_color(channel_dict):
    chars = (channel_dict or {}).get("characters", {}) or {}
    for cfg in chars.values():
        col = cfg.get("text_color")
        if col:
            return tuple(int(c) for c in col[:3])
    return (235, 231, 220)


# ============================================================
# 背景
# ============================================================
def _background_prompt(chapter, channel_dict, topic):
    """章ごとの背景プロンプト。チャンネルの illustration_style をそのまま使う。"""
    style = _fmt(channel_dict).get("illustration_style", {}) or {}
    art = style.get("art_style", "dim candle-lit archive aesthetic, desaturated indigo and sepia")
    bg = style.get("background", "deep indigo darkness with a faint vignette")
    extra = style.get("extra_prompt", "no text, no letters")
    return (
        f"Atmospheric background illustration for a quiet, serious documentary about {topic}. "
        f"This chapter concerns: {chapter['title']}. "
        f"Wide horizontal landscape composition (16:9). "
        f"Art style: {art}. Background: {bg}. "
        "The image is a BACKDROP that sits behind subtitles — keep the lower third simple and dark, "
        "keep the whole image low-contrast and dim so white text stays readable on top. "
        "Evocative and symbolic rather than literal. No faces looking at the camera. "
        f"{extra}. Absolutely no text, no letters, no numbers, no watermarks."
    )


def build_backgrounds(chapters, channel_dict, cache_dir, topic, size=(1920, 1080)):
    """章ごとの背景画像を作る。生成済みのものはキャッシュから再利用する。

    画像APIが失敗した章は、直前の章の背景を使い回す（暗い単色より自然）。
    それも無ければ手続き的なグラデーション背景にフォールバックする。
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = []
    last_ok = None
    for ch in chapters:
        dest = cache_dir / f"bg_ch{ch['index']:02d}.png"
        if dest.exists():
            print(f"  ♻️  第{ch['index']}章 背景: キャッシュ再利用")
            out.append(dest)
            last_ok = dest
            continue
        print(f"  🎨 第{ch['index']}章 背景を生成中...", flush=True)
        img = _call_openai_image(
            _background_prompt(ch, channel_dict, topic),
            size="1536x1024", quality="medium",
            channel_id=(channel_dict or {}).get("id"),
        )
        if img is None:
            if last_ok is not None:
                print(f"  ⚠️ 第{ch['index']}章 背景の生成に失敗 → 前章の背景を流用")
                out.append(last_ok)
                continue
            print(f"  ⚠️ 第{ch['index']}章 背景の生成に失敗 → 手続き的背景を使用")
            img = _fallback_background(size)
        img = _prepare_background(img, size)
        img.save(dest)
        out.append(dest)
        last_ok = dest
    return out


def _fallback_background(size):
    """画像APIが使えないときの、深い藍のグラデーション + 星屑。"""
    w, h = size
    base = Image.new("RGB", (1, 2), (18, 20, 44))
    base.putpixel((0, 1), (6, 7, 18))
    img = base.resize((w, h)).convert("RGBA")
    stars = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(stars)
    rng = 12345
    for _ in range(220):
        rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
        x = rng % w
        rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
        y = rng % h
        rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
        a = 40 + rng % 90
        d.ellipse([x, y, x + 2, y + 2], fill=(220, 214, 196, a))
    stars = stars.filter(ImageFilter.GaussianBlur(0.6))
    return Image.alpha_composite(img, stars)


def _prepare_background(img, size):
    """16:9 に切り出し、ビネットと暗幕を足して字幕が乗る明るさまで落とす。"""
    w, h = size
    img = img.convert("RGB")
    iw, ih = img.size
    target_ratio = w / h
    if iw / ih > target_ratio:
        new_w = int(ih * target_ratio)
        img = img.crop(((iw - new_w) // 2, 0, (iw - new_w) // 2 + new_w, ih))
    else:
        new_h = int(iw / target_ratio)
        img = img.crop((0, (ih - new_h) // 2, iw, (ih - new_h) // 2 + new_h))
    img = img.resize((w, h), Image.LANCZOS)
    img = _apply_vignette(img, 0.55)
    veil = Image.new("RGB", (w, h), (4, 5, 14))
    return Image.blend(img, veil, 0.28).convert("RGBA")


# ============================================================
# オーバーレイ描画
# ============================================================
class OverlayPainter:
    def __init__(self, channel_dict, chapters, size=(1920, 1080)):
        self.W, self.H = size
        self.chapters = chapters
        fmt = _fmt(channel_dict)
        layout = fmt.get("layout", {}) or {}
        colors = fmt.get("colors", {}) or {}
        self.band_h = int(self.H * layout.get("text_box_height_ratio", 0.20))
        self.band_opacity = int(layout.get("text_box_opacity", 205))
        self.band_color = tuple(colors.get("text_box_color", [0, 0, 0]))
        self.font_size = int(layout.get("text_font_size", 44))
        self.stroke_w = int(layout.get("text_stroke_width", 3))
        self.stroke_color = tuple(colors.get("text_stroke_color", [0, 0, 0]))
        self.line_spacing = int(layout.get("text_line_spacing", 6))
        self.margin_x = int(layout.get("text_margin_x", 110))
        self.text_color = _narrator_color(channel_dict)
        self.accent = (198, 166, 106)      # 書庫の金 — 章表記のアクセント
        self._band = None

    # -- 字幕帯 -------------------------------------------------
    def _band_layer(self):
        """下端の字幕帯。上辺は硬い線ではなくグラデーションで闇に溶かす。"""
        if self._band is not None:
            return self._band
        band = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        fade_h = int(self.band_h * 0.55)
        solid_h = self.band_h
        # グラデーション部（上に向かって透明へ）
        grad = Image.new("L", (1, 2), self.band_opacity)
        grad.putpixel((0, 0), 0)
        grad = grad.resize((self.W, fade_h))
        top = Image.new("RGBA", (self.W, fade_h), (*self.band_color, 255))
        top.putalpha(grad)
        band.alpha_composite(top, (0, self.H - solid_h - fade_h))
        solid = Image.new("RGBA", (self.W, solid_h), (*self.band_color, self.band_opacity))
        band.alpha_composite(solid, (0, self.H - solid_h))
        self._band = band
        return band

    def subtitle(self, text, chapter):
        """通常フレーム: 字幕帯 + 本文 + 左上の章表示。"""
        overlay = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        if chapter is not None:
            overlay.alpha_composite(self._chapter_tag(chapter))
        if not text:
            return overlay
        overlay.alpha_composite(self._band_layer())
        draw = ImageDraw.Draw(overlay)
        max_w = self.W - self.margin_x * 2
        lines = wrap_text(text, self.font_size, max_w, draw)
        line_h = int(self.font_size * 1.15)
        total_h = len(lines) * line_h + (len(lines) - 1) * self.line_spacing
        y = self.H - self.band_h + (self.band_h - total_h) // 2
        for line in lines:
            tw = measure_composite_text(draw, line, self.font_size)
            draw_composite_text(draw, ((self.W - tw) // 2, y), line, self.font_size,
                                self.text_color, stroke_fill=self.stroke_color,
                                stroke_width=self.stroke_w)
            y += line_h + self.line_spacing
        return overlay

    def _chapter_tag(self, chapter):
        """左上に小さく「第三章」。読み手が今どこにいるか常に分かるように。"""
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        label = kanji_chapter(chapter["index"])
        size = 30
        x, y = 58, 46
        draw.line([(x, y + 6), (x, y + size + 2)], fill=(*self.accent, 150), width=2)
        draw_composite_text(draw, (x + 18, y), label, size, (*self.accent, 210),
                            stroke_fill=(0, 0, 0), stroke_width=2)
        return layer

    # -- 章タイトルカード ---------------------------------------
    def chapter_card(self, chapter, alpha=1.0):
        """章の頭で全面に出すタイトルカード。alpha でフェードを表現する。"""
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        veil = Image.new("RGBA", (self.W, self.H), (3, 4, 12, 165))
        layer.alpha_composite(veil)
        draw = ImageDraw.Draw(layer)

        cx = self.W // 2
        cy = self.H // 2

        # CHAPTER 03 — 字間を空けた小さなラテン文字
        en = f"CHAPTER {chapter['index']:02d}"
        en_size = 26
        en_font = get_en_font(en_size)
        spaced = " ".join(en)
        ew = draw.textlength(spaced, font=en_font)
        draw.text((cx - ew / 2, cy - 132), spaced, font=en_font, fill=(*self.accent, 190))

        # 第三章
        kj = kanji_chapter(chapter["index"])
        kj_size = 40
        kw = measure_composite_text(draw, kj, kj_size)
        draw_composite_text(draw, (cx - kw // 2, cy - 92), kj, kj_size,
                            (*self.accent, 235), stroke_fill=(0, 0, 0), stroke_width=2)

        # 罫線
        rule_w = 300
        draw.line([(cx - rule_w // 2, cy - 30), (cx + rule_w // 2, cy - 30)],
                  fill=(*self.accent, 120), width=1)

        # タイトル本体
        title_size = 58
        max_w = int(self.W * 0.74)
        lines = []
        for seg in chapter["title"].split("\n"):
            lines.extend(wrap_text(seg, title_size, max_w, draw))
        line_h = int(title_size * 1.42)
        y = cy + 6
        for line in lines:
            tw = measure_composite_text(draw, line, title_size)
            draw_composite_text(draw, (cx - tw // 2, y), line, title_size,
                                self.text_color, stroke_fill=(0, 0, 0), stroke_width=3)
            y += line_h

        draw.line([(cx - rule_w // 2, y + 16), (cx + rule_w // 2, y + 16)],
                  fill=(*self.accent, 120), width=1)

        if alpha >= 1.0:
            return layer
        faded = layer.copy()
        a = faded.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, alpha))))
        faded.putalpha(a)
        return faded


# ============================================================
# タイムライン組み立て
# ============================================================
def _chapter_at(chapters, t):
    for ch in chapters:
        if ch["start"] <= t < ch["end"]:
            return ch
    return chapters[-1] if chapters else None


def build_timeline(cues, chapters, duration):
    """(開始時刻, 種別, ペイロード) の列を作る。

    章の頭では字幕を止めてタイトルカードを出す。カードのフェードは
    離散的な段階として時刻を刻み、後段でPNG1枚ずつに落とす。
    """
    marks = {0.0, float(duration)}
    for c in cues:
        marks.add(round(float(c["start"]), 3))
        marks.add(round(float(c["end"]), 3))
    card_windows = []
    for ch in chapters:
        cs = float(ch["start"])
        ce = min(cs + CARD_SECONDS, float(ch["end"]))
        card_windows.append((cs, ce, ch))
        for k in range(FADE_STEPS + 1):
            marks.add(round(cs + CARD_FADE * k / FADE_STEPS, 3))
            marks.add(round(ce - CARD_FADE + CARD_FADE * k / FADE_STEPS, 3))
        marks.add(round(ce, 3))

    marks = sorted(m for m in marks if 0.0 <= m <= duration)
    frames = []
    for a, b in zip(marks, marks[1:]):
        if b - a < 1e-3:
            continue
        mid = (a + b) / 2
        card = next((w for w in card_windows if w[0] <= mid < w[1]), None)
        if card:
            cs, ce, ch = card
            if mid < cs + CARD_FADE:
                alpha = (mid - cs) / CARD_FADE
            elif mid > ce - CARD_FADE:
                alpha = max(0.0, (ce - mid) / CARD_FADE)
            else:
                alpha = 1.0
            frames.append({"start": a, "dur": b - a, "kind": "card",
                           "chapter": ch, "alpha": round(alpha, 3)})
            continue
        text = next((c["text"] for c in cues
                     if float(c["start"]) <= mid < float(c["end"])), "")
        frames.append({"start": a, "dur": b - a, "kind": "sub",
                       "chapter": _chapter_at(chapters, mid), "text": text})
    return frames


def _render_overlays(frames, painter, out_dir):
    """フレーム定義をPNGに落とす。内容が同じ連続フレームは1枚にまとめる。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []          # [描画キー, 表示秒数]
    cache = {}            # 描画キー → 書き出し済みPNG
    for f in frames:
        if f["kind"] == "card":
            key = ("card", f["chapter"]["index"], f["alpha"])
        else:
            key = ("sub", f["chapter"]["index"] if f["chapter"] else -1, f["text"])
        if entries and entries[-1][0] == key:
            entries[-1][1] += f["dur"]      # 直前と同じ絵 → 尺だけ伸ばす
            continue
        entries.append([key, f["dur"]])

    paths = []
    for i, (key, dur) in enumerate(entries):
        if key in cache:
            paths.append((cache[key], dur))
            continue
        if key[0] == "card":
            ch = next(c for c in painter.chapters if c["index"] == key[1])
            img = painter.chapter_card(ch, alpha=key[2])
        else:
            ch = next((c for c in painter.chapters if c["index"] == key[1]), None)
            img = painter.subtitle(key[2], ch)
        p = out_dir / f"ov_{i:05d}.png"
        img.save(p, optimize=False, compress_level=1)
        cache[key] = p
        paths.append((p, dur))
        if (i + 1) % 50 == 0:
            print(f"    …{i + 1}/{len(entries)} 枚", flush=True)
    return paths


# ============================================================
# ffmpeg 合成
# ============================================================
def _build_background_track(backgrounds, chapters, work_dir, size, fps):
    """章ごとに背景をゆっくり流し、連結して1本の無音映像にする。"""
    work_dir = Path(work_dir)
    parts = []
    W, H = size
    zw, zh = int(W * PAN_ZOOM) // 2 * 2, int(H * PAN_ZOOM) // 2 * 2
    for i, (ch, bg) in enumerate(zip(chapters, backgrounds)):
        dur = max(0.5, float(ch["end"]) - float(ch["start"]))
        part = work_dir / f"bgpart_{i:02d}.mp4"
        # 章ごとに流れる向きを変えて、長尺でも単調にならないようにする
        dirs = [(1, 1), (-1, 1), (1, -1), (-1, -1)][i % 4]
        xs = f"(in_w-out_w)*(t/{dur:.3f})" if dirs[0] > 0 else f"(in_w-out_w)*(1-t/{dur:.3f})"
        ys = f"(in_h-out_h)*(t/{dur:.3f})" if dirs[1] > 0 else f"(in_h-out_h)*(1-t/{dur:.3f})"
        vf = f"scale={zw}:{zh},crop={W}:{H}:x='{xs}':y='{ys}',format=yuv420p"
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(bg), "-t", f"{dur:.3f}",
               "-r", str(fps), "-vf", vf,
               "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
               "-pix_fmt", "yuv420p", str(part), "-loglevel", "error"]
        subprocess.run(cmd, check=True)
        parts.append(part)
        print(f"    第{ch['index']}章 背景 {dur:.1f}s", flush=True)

    listing = work_dir / "bgparts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    bg_track = work_dir / "background.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(bg_track), "-loglevel", "error"],
                   check=True, cwd=str(work_dir))
    return bg_track


def _write_overlay_list(paths, work_dir):
    lines = []
    for p, dur in paths:
        lines.append(f"file '{Path(p).name}'\n")
        lines.append(f"duration {dur:.3f}\n")
    lines.append(f"file '{Path(paths[-1][0]).name}'\n")   # concat は最終フレームの再掲が要る
    listing = Path(work_dir) / "overlays.txt"
    listing.write_text("".join(lines), encoding="utf-8")
    return listing


def render(audio_path, cues, chapters, out_path, channel_dict=None,
           backgrounds=None, work_dir=None, size=(1920, 1080), fps=FPS,
           crf=18, keep_work=False):
    """音声・字幕・章立てから完成動画を1本書き出す。"""
    if not backgrounds or len(backgrounds) != len(chapters):
        raise ValueError("backgrounds は章と同数必要です（build_backgrounds の戻り値を渡す）")
    audio_path = Path(audio_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(work_dir or (out_path.parent / "_work"))
    ov_dir = work_dir / "overlays"
    work_dir.mkdir(parents=True, exist_ok=True)

    duration = _probe_duration(audio_path)
    print(f"🎧 音声 {duration:.1f}s / 章 {len(chapters)} / 字幕 {len(cues)}")

    print("🌌 背景トラックを作成中...")
    bg_track = _build_background_track(backgrounds, chapters, work_dir, size, fps)

    print("📝 オーバーレイを描画中...")
    painter = OverlayPainter(channel_dict, chapters, size=size)
    frames = build_timeline(cues, chapters, duration)
    paths = _render_overlays(frames, painter, ov_dir)
    print(f"    {len(paths)} 枚（{len(frames)} 区間から圧縮）")
    listing = _write_overlay_list(paths, ov_dir)

    print("🎬 合成中...")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(bg_track),
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-i", str(audio_path),
        "-filter_complex", "[0:v][1:v]overlay=format=auto:eof_action=pass[v]",
        "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-t", f"{duration:.3f}",
        str(out_path), "-loglevel", "error", "-stats",
    ]
    subprocess.run(cmd, check=True)

    if not keep_work:
        shutil.rmtree(work_dir, ignore_errors=True)
    print(f"✅ 出力: {out_path}")
    return out_path


def _probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


# ============================================================
# サムネイル
# ============================================================
def generate_thumbnail(title, background, out_path, channel_dict=None, size=(1280, 720)):
    """章1の背景を使った、チャンネル体裁のサムネイル。"""
    W, H = size
    img = Image.open(background).convert("RGB").resize((W, H), Image.LANCZOS)
    img = _apply_vignette(img, 0.5)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.alpha_composite(Image.new("RGBA", (W, H), (3, 4, 12, 110)))
    draw = ImageDraw.Draw(layer)

    tmpl = (channel_dict or {}).get("thumbnail_template", {}) or {}
    accent = (198, 166, 106)
    text_color = _narrator_color(channel_dict)

    badge = tmpl.get("badge_text") or ""
    if badge:
        bs = 30
        bw = measure_composite_text(draw, badge, bs)
        draw.rectangle([56, 46, 56 + bw + 44, 46 + bs + 26],
                       fill=(*tuple(tmpl.get("badge_color", [52, 38, 92])), 220))
        draw_composite_text(draw, (78, 58), badge, bs, (235, 230, 218),
                            stroke_fill=(0, 0, 0), stroke_width=2)

    fsize = 86
    lines = wrap_text(title, fsize, int(W * 0.86), draw)
    line_h = int(fsize * 1.3)
    y = (H - (len(lines) * line_h)) // 2 + 10
    for line in lines:
        tw = measure_composite_text(draw, line, fsize)
        draw_composite_text(draw, ((W - tw) // 2, y), line, fsize, text_color,
                            stroke_fill=(0, 0, 0), stroke_width=7)
        y += line_h

    draw.line([(W // 2 - 190, y + 12), (W // 2 + 190, y + 12)], fill=(*accent, 160), width=2)
    out = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    out.save(out_path, quality=94)
    return out_path


# ============================================================
# 概要欄
# ============================================================
def _timestamp(seconds):
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def build_description(title, chapters, channel_dict=None):
    """章タイムスタンプ付きの概要欄。先頭章を 0:00 にすると YouTube 側で
    チャプターとして認識される（長尺の離脱対策として効く）。"""
    tmpl = (channel_dict or {}).get("description_template", {}) or {}
    parts = [title, ""]
    intro = tmpl.get("main_intro")
    if intro:
        parts += [intro, ""]
    parts.append("▼ 目次")
    for ch in chapters:
        label = ch["title"].replace("\n", " ")
        parts.append(f"{_timestamp(ch['start'])} {kanji_chapter(ch['index'])} {label}")
    tags = tmpl.get("main_hashtags")
    if tags:
        parts += ["", tags]
    return "\n".join(parts)


# ============================================================
# CLI
# ============================================================
def main():
    import argparse
    ap = argparse.ArgumentParser(description="完成済みナレーション音源から長尺動画を作る")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--cues", required=True, help="{duration, chapters, cues} を持つJSON")
    ap.add_argument("--channel", required=True, help="channel id (data/channels/<id>.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default=None, help="サムネイル用タイトル")
    ap.add_argument("--topic", default=None, help="背景生成に使う題材（既定: --title）")
    ap.add_argument("--bg-cache", default=None)
    ap.add_argument("--keep-work", action="store_true")
    args = ap.parse_args()

    channel = load_channel(args.channel)
    data = json.loads(Path(args.cues).read_text(encoding="utf-8"))
    chapters, cues = data["chapters"], data["cues"]
    out_path = Path(args.out)
    title = args.title or out_path.stem

    bg_cache = Path(args.bg_cache or (out_path.parent / "backgrounds"))
    print("🖼️  背景を準備中...")
    backgrounds = build_backgrounds(chapters, channel, bg_cache, args.topic or title)

    render(args.audio, cues, chapters, out_path, channel_dict=channel,
           backgrounds=backgrounds, keep_work=args.keep_work)

    thumb = out_path.with_name(out_path.stem + "_thumb.jpg")
    generate_thumbnail(title, backgrounds[0], thumb, channel_dict=channel)
    print(f"🖼️  サムネイル: {thumb}")

    desc = out_path.with_name(out_path.stem + "_description.txt")
    desc.write_text(build_description(title, chapters, channel), encoding="utf-8")
    print(f"📄 概要欄: {desc}")


if __name__ == "__main__":
    main()
