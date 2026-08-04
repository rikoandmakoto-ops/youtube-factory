"""切り抜きショートの縦型レンダリング。

レイアウトは data/research/clip_shorts_visual_analysis.json の横断分析に準拠する。
再生数 500万〜3300万の切り抜き/解説ショート7本を実測した結果、4本すべてが
同じ骨格だった:

    ┌──────────────┐
    │  フック帯（常時表示・極太・2〜3行）  │  ← サムネの代わり。スクロールを止める
    ├──────────────┤
    │   元動画 16:9 を横幅いっぱい      │  ← 9:16 クロップは 0本。情報量を捨てない
    ├──────────────┤
    │  打ち直し字幕（巨大・2行・太縁）   │  ← 元の焼き込み字幕は小さくなるので切り落とす
    │  CTA帯（本編誘導・常時表示）      │
    └──────────────┘

エフェクト（ズーム/シェイク/グリッチ/トランジション）は 7本中 0本で不使用。
「加工していない感」が切り抜きの信頼性なので、意図的に足さない。

縦位置は固定値ではなく元動画のアスペクト比から毎回組み直す。16:9 を横幅いっぱいに
置くと高さが 486px にしかならず、固定レイアウトだと帯の間に大きな黒余白が空くため。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from .align import LineTiming

# ---------------------------------------------------------------------
# フォント
# ---------------------------------------------------------------------
_FONT_SEARCH_JP = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]
JP_FONT_PATH = next((f for f in _FONT_SEARCH_JP if os.path.exists(f)), None)


def _font(size: int) -> ImageFont.FreeTypeFont:
    if JP_FONT_PATH:
        return ImageFont.truetype(JP_FONT_PATH, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------------
# レイアウト設定
# ---------------------------------------------------------------------

@dataclass
class ClipLayout:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    bg_color: Tuple[int, int, int] = (10, 10, 14)

    # 元動画の下部字幕ボックスを切り落とす比率。yukkuri の text_box_height_ratio は
    # 0.20 だが、実測すると文字の上端がちょうど 0.80 に接するので少し多めに削る
    # （残すと打ち直し字幕と二重に見える）。
    source_crop_bottom_ratio: float = 0.22

    # フック帯
    hook_font_sizes: Tuple[int, ...] = (88, 80, 72, 64, 58)
    hook_max_lines: int = 3
    hook_color: Tuple[int, int, int] = (255, 255, 255)
    hook_stroke: Tuple[int, int, int] = (0, 0, 0)
    hook_stroke_width: int = 10
    accent_color: Tuple[int, int, int] = (255, 90, 0)

    # 字幕
    subtitle_font_sizes: Tuple[int, ...] = (72, 66, 60, 54)
    subtitle_max_lines: int = 2
    subtitle_stroke_width: int = 9
    subtitle_default_color: Tuple[int, int, int] = (255, 255, 255)
    subtitle_stroke_color: Tuple[int, int, int] = (0, 0, 0)

    # CTA / ウォーターマーク
    cta_font_size: int = 46
    cta_color: Tuple[int, int, int] = (255, 220, 60)
    watermark_font_size: int = 24
    watermark_color: Tuple[int, int, int] = (170, 170, 180)

    # 余白
    side_margin: int = 36
    gap: int = 26
    # ショートのUI（タイトル/チャンネル/ボタン）に隠れる下端
    bottom_safe: int = 250

    @property
    def usable_width(self) -> int:
        return self.width - self.side_margin * 2

    @classmethod
    def from_channel(cls, channel_raw: Dict[str, Any]) -> "ClipLayout":
        spec = (channel_raw or {}).get("layout_spec") or {}
        layout = cls()
        canvas = spec.get("canvas")
        if isinstance(canvas, (list, tuple)) and len(canvas) == 2:
            layout.width, layout.height = int(canvas[0]), int(canvas[1])
        if spec.get("fps"):
            layout.fps = int(spec["fps"])
        if spec.get("source_crop_bottom_ratio") is not None:
            layout.source_crop_bottom_ratio = float(spec["source_crop_bottom_ratio"])
        colors = ((channel_raw or {}).get("video_format") or {}).get("colors") or {}
        bg = colors.get("bg_color")
        if isinstance(bg, (list, tuple)) and len(bg) >= 3:
            layout.bg_color = (int(bg[0]), int(bg[1]), int(bg[2]))
        thumb = (channel_raw or {}).get("thumbnail_template") or {}
        badge = thumb.get("badge_color")
        if isinstance(badge, (list, tuple)) and len(badge) >= 3:
            layout.accent_color = (int(badge[0]), int(badge[1]), int(badge[2]))
        return layout


@dataclass
class ComputedLayout:
    """1本分の実寸レイアウト。"""

    layout: ClipLayout
    hook_lines: List[str]
    hook_font_size: int
    hook_line_height: int
    hook_y: int
    accent_y: int
    video_y: int
    video_h: int
    subtitle_y: int
    subtitle_band_h: int
    subtitle_font_size: int
    subtitle_line_height: int
    subtitle_chars_per_line: int
    cta_y: int


# ---------------------------------------------------------------------
# テキスト整形
# ---------------------------------------------------------------------

_NO_LINE_START = "、。，．),）」』】！？!?ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮー"
# 途中で折ると読めなくなる連続（英数字・カタカナ語・漢字熟語）。ここでは改行しない。
# 『重要な指標』が「…重要な指 / 標として」と割れるのを防ぐ。
_ATOMIC_RE = re.compile(r"[A-Za-z0-9０-９][A-Za-z0-9０-９.\-]*|[ァ-ヴ]{2,}|[一-龥]{2,}")

_probe_draw = ImageDraw.Draw(Image.new("RGBA", (8, 8)))


def _text_width(text: str, font: ImageFont.FreeTypeFont, stroke: int) -> int:
    bbox = _probe_draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return bbox[2] - bbox[0]


def fit_chars_per_line(
    font: ImageFont.FreeTypeFont, usable_width: int, stroke: int, *, sample: str = "あ"
) -> int:
    """指定フォントで1行に入る全角文字数を実測する。"""
    n = 1
    while n < 60 and _text_width(sample * (n + 1), font, stroke) <= usable_width:
        n += 1
    return max(4, n)


def _safe_break(text: str, pos: int) -> int:
    """pos で折ると英数字/カタカナ語の途中になる場合、語頭まで戻す。"""
    if pos <= 0 or pos >= len(text):
        return pos
    for m in _ATOMIC_RE.finditer(text):
        if m.start() < pos < m.end():
            return m.start() if m.start() > max(1, pos // 2) else pos
    return pos


def wrap_text(text: str, max_chars: int, max_lines: int) -> List[str]:
    """日本語を文字数で折り返す。行頭禁則と英数字/カタカナの分断を避ける。"""
    text = text.strip()
    lines: List[str] = []
    i = 0
    while i < len(text) and len(lines) < max_lines:
        take = min(max_chars, len(text) - i)
        if i + take < len(text):
            if text[i + take] in _NO_LINE_START and take < max_chars:
                take += 1
            take = max(1, _safe_break(text[i:], take))
        lines.append(text[i:i + take])
        i += take
    if i < len(text) and lines:
        lines[-1] = lines[-1][:max(1, max_chars - 1)] + "…"
    return lines


def fit_lines(
    text: str,
    *,
    usable_width: int,
    max_lines: int,
    font_sizes: Sequence[int],
    stroke: int,
) -> Tuple[List[str], int]:
    """max_lines に収まる最大のフォントサイズで折り返す。

    固定の「1行N文字」だと、同じ文字数でも英数字混じりの行だけ横幅を溢れる。
    実測しながらサイズを落とすことで、フック帯が画面外にはみ出すのを防ぐ。
    """
    text = (text or "").strip()
    if not text:
        return [], font_sizes[0]
    for size in font_sizes:
        font = _font(size)
        per_line = fit_chars_per_line(font, usable_width, stroke)
        lines = wrap_text(text, per_line, max_lines)
        joined = "".join(lines)
        if not joined.endswith("…") and len(joined) >= len(text):
            if all(_text_width(l, font, stroke) <= usable_width for l in lines):
                return lines, size
    size = font_sizes[-1]
    per_line = fit_chars_per_line(_font(size), usable_width, stroke)
    return wrap_text(text, per_line, max_lines), size


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    *,
    width: int,
    top: int,
    font: ImageFont.FreeTypeFont,
    line_height: int,
    fill: Tuple[int, int, int],
    stroke: Tuple[int, int, int],
    stroke_width: int,
) -> None:
    for n, line in enumerate(lines):
        w = _text_width(line, font, stroke_width)
        draw.text(
            ((width - w) // 2, top + n * line_height), line, font=font,
            fill=fill + (255,), stroke_width=stroke_width, stroke_fill=stroke + (255,),
        )


# ---------------------------------------------------------------------
# レイアウト計算
# ---------------------------------------------------------------------

def probe_size(video_path: Path | str) -> Tuple[int, int]:
    out = subprocess.run(
        [_ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(video_path)],
        capture_output=True, text=True, timeout=120,
    ).stdout
    try:
        stream = json.loads(out)["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except Exception:
        return 1920, 1080


def compute_layout(layout: ClipLayout, *, hook: str, source_size: Tuple[int, int]) -> ComputedLayout:
    """元動画のサイズとフックの行数から、縦の積み方を決める。"""
    src_w, src_h = source_size
    keep = max(0.3, 1.0 - layout.source_crop_bottom_ratio)
    video_h = int(round(layout.width * (src_h * keep) / max(1, src_w)))
    video_h -= video_h % 2

    hook_lines, hook_size = fit_lines(
        hook, usable_width=layout.usable_width, max_lines=layout.hook_max_lines,
        font_sizes=layout.hook_font_sizes, stroke=layout.hook_stroke_width,
    )
    hook_line_height = int(hook_size * 1.26)
    hook_block = len(hook_lines) * hook_line_height

    sub_size = layout.subtitle_font_sizes[0]
    sub_line_height = int(sub_size * 1.30)
    sub_band = sub_line_height * layout.subtitle_max_lines + 36
    sub_chars = fit_chars_per_line(
        _font(sub_size), layout.usable_width, layout.subtitle_stroke_width,
    )

    accent_h = 8
    cta_h = layout.cta_font_size + 16
    # CTA はショートUIの直上に固定する。フック〜字幕のブロックは残りの領域で
    # 天地中央に置く。ブロックの直下に CTA を置くと、16:9 を横幅に合わせた分の
    # 余白がすべて画面下部に溜まって間延びして見えるため。
    cta_y = layout.height - layout.bottom_safe - cta_h
    block = (hook_block + layout.gap + accent_h + layout.gap + video_h
             + layout.gap + sub_band)
    hook_y = max(90, (cta_y - layout.gap * 2 - block) // 2)

    accent_y = hook_y + hook_block + layout.gap
    video_y = accent_y + accent_h + layout.gap
    subtitle_y = video_y + video_h + layout.gap

    return ComputedLayout(
        layout=layout,
        hook_lines=hook_lines,
        hook_font_size=hook_size,
        hook_line_height=hook_line_height,
        hook_y=hook_y,
        accent_y=accent_y,
        video_y=video_y,
        video_h=video_h,
        subtitle_y=subtitle_y,
        subtitle_band_h=sub_band,
        subtitle_font_size=sub_size,
        subtitle_line_height=sub_line_height,
        subtitle_chars_per_line=sub_chars,
        cta_y=cta_y,
    )


# ---------------------------------------------------------------------
# 静的オーバーレイ（フック帯 + CTA + ウォーターマーク）
# ---------------------------------------------------------------------

def render_static_overlay(
    computed: ComputedLayout, *, cta_text: str, watermark: str, out_path: Path,
) -> Path:
    layout = computed.layout
    img = Image.new("RGBA", (layout.width, layout.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _draw_centered(
        draw, computed.hook_lines, width=layout.width, top=computed.hook_y,
        font=_font(computed.hook_font_size), line_height=computed.hook_line_height,
        fill=layout.hook_color, stroke=layout.hook_stroke,
        stroke_width=layout.hook_stroke_width,
    )

    # フック帯と映像の間にアクセントバー（チャンネル識別）
    bar_w = int(layout.width * 0.42)
    draw.rectangle(
        [(layout.width - bar_w) // 2, computed.accent_y,
         (layout.width + bar_w) // 2, computed.accent_y + 8],
        fill=layout.accent_color + (255,),
    )

    if cta_text:
        _draw_centered(
            draw, [cta_text], width=layout.width, top=computed.cta_y,
            font=_font(layout.cta_font_size), line_height=layout.cta_font_size + 12,
            fill=layout.cta_color, stroke=(0, 0, 0), stroke_width=6,
        )

    if watermark:
        wm_font = _font(layout.watermark_font_size)
        w = _text_width(watermark, wm_font, 0)
        draw.text((layout.width - w - 28, layout.height - 70), watermark,
                  font=wm_font, fill=layout.watermark_color + (200,))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


# ---------------------------------------------------------------------
# 字幕
# ---------------------------------------------------------------------

@dataclass
class SubtitleChunk:
    lines: List[str]
    start: float
    end: float
    color: Tuple[int, int, int]

    @property
    def char_count(self) -> int:
        return sum(len(l) for l in self.lines)


def build_subtitle_chunks(
    timings: Sequence[LineTiming],
    computed: ComputedLayout,
    *,
    clip_start: float,
    speaker_colors: Optional[Dict[str, Tuple[int, int, int]]] = None,
) -> List[SubtitleChunk]:
    """台本行を「2行で読める塊」に割り、行の尺を文字数比で配分する。

    先に折り返してから塊にまとめる（塊にしてから折り返すと、塊の境界で
    英単語や熟語が割れる）。
    """
    layout = computed.layout
    speaker_colors = speaker_colors or {}
    chunks: List[SubtitleChunk] = []
    for timing in timings:
        text = timing.text.strip()
        if not text:
            continue
        wrapped = wrap_text(text, computed.subtitle_chars_per_line, max_lines=99)
        groups = [wrapped[i:i + layout.subtitle_max_lines]
                  for i in range(0, len(wrapped), layout.subtitle_max_lines)]
        total_chars = sum(len("".join(g)) for g in groups) or 1
        color = speaker_colors.get(timing.speaker, layout.subtitle_default_color)
        cursor = timing.start
        for group in groups:
            span = timing.duration * (len("".join(group)) / total_chars)
            chunks.append(SubtitleChunk(
                lines=group,
                start=max(0.0, cursor - clip_start),
                end=max(0.0, cursor + span - clip_start),
                color=color,
            ))
            cursor += span
    return chunks


def render_subtitle_sequence(
    chunks: Sequence[SubtitleChunk],
    computed: ComputedLayout,
    work_dir: Path,
    *,
    clip_duration: float,
) -> Optional[Path]:
    """字幕帯だけの透過 PNG 列と concat リストを作る。

    チャンク数だけ overlay を重ねると極端に遅くなるため、concat demuxer で
    1本の映像入力にまとめて overlay 1回で済ませる。
    """
    if not chunks:
        return None
    layout = computed.layout
    band_w, band_h = layout.width, computed.subtitle_band_h
    font = _font(computed.subtitle_font_size)

    blank = work_dir / "sub_blank.png"
    Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0)).save(blank)

    entries: List[Tuple[Path, float]] = []
    cursor = 0.0
    for i, chunk in enumerate(chunks):
        if chunk.start > cursor + 0.05:
            entries.append((blank, chunk.start - cursor))
            cursor = chunk.start
        img = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        top = (band_h - len(chunk.lines) * computed.subtitle_line_height) // 2
        _draw_centered(
            draw, chunk.lines, width=band_w, top=top, font=font,
            line_height=computed.subtitle_line_height,
            fill=chunk.color, stroke=layout.subtitle_stroke_color,
            stroke_width=layout.subtitle_stroke_width,
        )
        path = work_dir / f"sub_{i:04d}.png"
        img.save(path)
        entries.append((path, max(0.08, chunk.end - chunk.start)))
        cursor = chunk.end

    if cursor < clip_duration:
        entries.append((blank, clip_duration - cursor))

    concat_path = work_dir / "subs.txt"
    body: List[str] = []
    for path, dur in entries:
        body.append(f"file '{path.as_posix()}'")
        body.append(f"duration {dur:.3f}")
    # concat demuxer は最終フレームの duration を無視するので末尾を置き直す
    body.append(f"file '{entries[-1][0].as_posix()}'")
    concat_path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return concat_path


# ---------------------------------------------------------------------
# ffmpeg 合成
# ---------------------------------------------------------------------

def _ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe_bin() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def render_clip(
    *,
    source_path: Path,
    start: float,
    end: float,
    hook: str,
    subtitle_lines: Sequence[LineTiming],
    layout: ClipLayout,
    out_path: Path,
    cta_text: str = "続きは本編で（概要欄）",
    watermark: str = "",
    speaker_colors: Optional[Dict[str, Tuple[int, int, int]]] = None,
    work_dir: Optional[Path] = None,
) -> Path:
    """1区間を縦型ショートに焼く。"""
    duration = max(1.0, end - start)
    tmp = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="clip_"))
    tmp.mkdir(parents=True, exist_ok=True)

    computed = compute_layout(layout, hook=hook, source_size=probe_size(source_path))
    static_png = render_static_overlay(
        computed, cta_text=cta_text, watermark=watermark, out_path=tmp / "static.png",
    )
    chunks = build_subtitle_chunks(
        subtitle_lines, computed, clip_start=start, speaker_colors=speaker_colors,
    )
    subs_concat = render_subtitle_sequence(chunks, computed, tmp, clip_duration=duration)

    keep = 1.0 - layout.source_crop_bottom_ratio
    r, g, b = layout.bg_color
    filters = [
        f"color=c=0x{r:02x}{g:02x}{b:02x}:s={layout.width}x{layout.height}"
        f":r={layout.fps}:d={duration:.3f}[bg]",
        f"[0:v]crop=iw:ih*{keep:.4f}:0:0,scale={layout.width}:{computed.video_h},setsar=1[src]",
        f"[bg][src]overlay=x=0:y={computed.video_y}:shortest=1[v0]",
        "[v0][1:v]overlay=x=0:y=0[v1]",
    ]

    cmd: List[str] = [
        _ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source_path),
        "-loop", "1", "-t", f"{duration:.3f}", "-i", str(static_png),
    ]

    if subs_concat:
        cmd += ["-f", "concat", "-safe", "0", "-i", str(subs_concat)]
        filters.append("[2:v]format=rgba[subs]")
        filters.append(f"[v1][subs]overlay=x=0:y={computed.subtitle_y}:shortest=1[vout]")
    else:
        filters.append("[v1]copy[vout]")

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "0:a?",
        "-r", str(layout.fps),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        "-t", f"{duration:.3f}",
        str(out_path),
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {proc.stderr[-1500:]}")
    return out_path


def render_thumbnail(
    *,
    source_path: Path,
    at_sec: float,
    hook: str,
    layout: ClipLayout,
    out_path: Path,
) -> Optional[Path]:
    """ピーク位置のフレームにフックを乗せた簡易サムネ。失敗しても致命的ではない。"""
    try:
        tmp_frame = out_path.parent / "_frame.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
             "-ss", f"{at_sec:.2f}", "-i", str(source_path), "-frames:v", "1",
             str(tmp_frame)],
            capture_output=True, timeout=180, check=True,
        )
        computed = compute_layout(layout, hook=hook, source_size=probe_size(source_path))
        base = Image.open(tmp_frame).convert("RGB")
        keep = 1.0 - layout.source_crop_bottom_ratio
        base = base.crop((0, 0, base.width, int(base.height * keep)))
        base = base.resize((layout.width, computed.video_h))
        canvas = Image.new("RGBA", (layout.width, layout.height), layout.bg_color + (255,))
        canvas.paste(base, (0, computed.video_y))
        draw = ImageDraw.Draw(canvas)
        _draw_centered(
            draw, computed.hook_lines, width=layout.width, top=computed.hook_y,
            font=_font(computed.hook_font_size), line_height=computed.hook_line_height,
            fill=layout.hook_color, stroke=layout.hook_stroke,
            stroke_width=layout.hook_stroke_width,
        )
        canvas.convert("RGB").save(out_path, quality=92)
        tmp_frame.unlink(missing_ok=True)
        return out_path
    except Exception as e:
        print(f"  ⚠️ サムネ生成スキップ: {e}")
        return None
