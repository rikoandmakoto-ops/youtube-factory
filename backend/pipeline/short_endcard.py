"""ショート末尾のエンドカード — 見終わった直後に次の行き先を出す。

狙い:
    ショートは最後まで見た視聴者がそのまま次のショートへスワイプしてしまう。
    最後の 1.5 秒に「次の動画」「チャンネル登録」を大きく出すと、
    その一瞬でプロフィールへ飛ぶ導線ができる。YouTube のエンドスクリーン機能は
    Shorts では使えず、Data API からも設定できないので、映像自体に焼き込む。

    尺は短く保つ（既定 1.6 秒）。ショートは尺が伸びるほど平均視聴率が落ちるため、
    「次」を認識できる最小限だけ足す。

設定（チャンネル JSON の defaults.short_endcard）:
    {
      "enabled": true,           # 既定 true
      "duration": 1.6,
      "headline": "次の動画へ →",   # 省略時は既定文
      "sub": "毎日20時に投稿",
      "cta": "チャンネル登録で見逃さない",
      "bg_color": [12, 14, 22],
      "accent_color": [255, 210, 60]
    }
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

DEFAULT_DURATION = 1.6
MIN_DURATION = 0.6
MAX_DURATION = 4.0

DEFAULT_HEADLINE = "次の動画はこちら →"
DEFAULT_CTA = "チャンネル登録で見逃さない"
DEFAULT_BG = (12, 14, 22)
DEFAULT_ACCENT = (255, 210, 60)


def _cfg(channel_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = ((channel_dict or {}).get("defaults") or {}).get("short_endcard")
    return cfg if isinstance(cfg, dict) else {}


def is_enabled(channel_dict: Optional[Dict[str, Any]] = None) -> bool:
    return _cfg(channel_dict).get("enabled", True) is not False


def duration_for(channel_dict: Optional[Dict[str, Any]] = None) -> float:
    try:
        d = float(_cfg(channel_dict).get("duration") or DEFAULT_DURATION)
    except Exception:
        d = DEFAULT_DURATION
    return max(MIN_DURATION, min(MAX_DURATION, d))


def _color(value: Any, fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return tuple(int(v) for v in value[:3])  # type: ignore[return-value]
        except Exception:
            return fallback
    return fallback


def build_texts(
    channel_dict: Optional[Dict[str, Any]] = None,
    *,
    next_hint: str = "",
) -> Dict[str, str]:
    """エンドカードに出す3行（見出し / サブ / CTA）を決める。"""
    cfg = _cfg(channel_dict)
    name = (channel_dict or {}).get("name") or ""
    sub = str(cfg.get("sub") or next_hint or name or "").strip()
    return {
        "headline": str(cfg.get("headline") or DEFAULT_HEADLINE).strip(),
        "sub": sub,
        "cta": str(cfg.get("cta") or DEFAULT_CTA).strip(),
    }


def _wrap(text: str, per_line: int) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    return [text[i : i + per_line] for i in range(0, len(text), per_line)] or [text]


def render_image(
    width: int,
    height: int,
    channel_dict: Optional[Dict[str, Any]] = None,
    *,
    next_hint: str = "",
    font_loader=None,
    backdrop: Optional[Image.Image] = None,
    accent_color: Optional[Tuple[int, int, int]] = None,
) -> Image.Image:
    """エンドカードの静止画（RGB）。

    Args:
        font_loader: size -> PIL font。video_generator.get_font を渡す想定。
            未指定ならデフォルトフォント（テストや単体実行用）。
        backdrop: 直前の本編の最終コマ。渡すとそれをぼかして暗くした上に文字を
            置く（render_on_backdrop）。無地の紺に切り替わると「動画が壊れた／
            終わった」に見えてスワイプされるので、本編と地続きに見せる。
        accent_color: 見出しの色（チャンネル設定より優先。本編の強調色と揃える）。
    """
    if backdrop is not None:
        return render_on_backdrop(width, height, backdrop, channel_dict,
                                  next_hint=next_hint, accent_color=accent_color)
    cfg = _cfg(channel_dict)
    bg = _color(cfg.get("bg_color"), DEFAULT_BG)
    accent = _color(cfg.get("accent_color"), accent_color or DEFAULT_ACCENT)
    texts = build_texts(channel_dict, next_hint=next_hint)

    def _font(size: int):
        if font_loader is not None:
            try:
                return font_loader(size)
            except Exception:
                pass
        from PIL import ImageFont

        return ImageFont.load_default()

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    # 上下に薄いアクセント帯（無地だと「動画が終わった」ではなく「壊れた」に見える）
    band = max(6, height // 220)
    draw.rectangle([0, 0, width, band], fill=accent)
    draw.rectangle([0, height - band, width, height], fill=accent)

    cy = height // 2
    head_size = max(40, width // 13)
    sub_size = max(30, width // 22)
    cta_size = max(28, width // 26)

    def _draw_center(text: str, y: int, size: int, fill, stroke=6) -> int:
        font = _font(size)
        for line in _wrap(text, max(6, int(width / (size * 0.62)))):
            try:
                bbox = draw.textbbox((0, 0), line, font=font)
                w = bbox[2] - bbox[0]
            except Exception:
                w = len(line) * size // 2
            draw.text(
                ((width - w) // 2, y),
                line,
                font=font,
                fill=fill,
                stroke_width=stroke,
                stroke_fill=(0, 0, 0),
            )
            y += int(size * 1.25)
        return y

    y = cy - int(head_size * 1.6)
    y = _draw_center(texts["headline"], y, head_size, accent)
    if texts["sub"]:
        y += int(sub_size * 0.5)
        y = _draw_center(texts["sub"], y, sub_size, (255, 255, 255))
    if texts["cta"]:
        y += int(cta_size * 0.7)
        _draw_center(texts["cta"], y, cta_size, (235, 235, 235), stroke=5)

    return img


def _heavy_font(size: int):
    try:
        from pipeline import short_telop  # type: ignore
    except Exception:
        try:
            from . import short_telop  # type: ignore
        except Exception:
            short_telop = None  # type: ignore
    if short_telop is not None:
        return short_telop.font(size, "heavy")
    from PIL import ImageFont

    return ImageFont.load_default()


def render_on_backdrop(
    width: int,
    height: int,
    backdrop: Image.Image,
    channel_dict: Optional[Dict[str, Any]] = None,
    *,
    next_hint: str = "",
    accent_color: Optional[Tuple[int, int, int]] = None,
) -> Image.Image:
    """本編の最終コマをぼかして暗くし、その上に 3 行を置く（2026-10-03 visual r1）。

    比較対象の上位ショートはどれも「暗転した別画面」で終わらない（3本は答えの直前で
    切れてそのまま先頭へループする）。末尾カードを残す場合でも、本編から地続きの
    画面にして、見出しは極太・本編の強調色で揃える。
    """
    cfg = _cfg(channel_dict)
    accent = accent_color or _color(cfg.get("accent_color"), DEFAULT_ACCENT)
    texts = build_texts(channel_dict, next_hint=next_hint)
    img = backdrop.convert("RGB").resize((width, height))
    img = img.filter(ImageFilter.GaussianBlur(max(6, width // 60)))
    dark = Image.new("RGB", (width, height), (0, 0, 0))
    img = Image.blend(img, dark, 0.62)
    draw = ImageDraw.Draw(img)

    def center(text: str, y: int, size: int, fill, stroke: int) -> int:
        # 1 行に収まるまで字を小さくする（「→」だけが次の行に落ちるのを防ぐ）
        while size > 20:
            try:
                if _heavy_font(size).getlength(text) <= width * 0.88:
                    break
            except Exception:
                break
            size -= 2
        f = _heavy_font(size)
        for line in [text]:
            try:
                w = int(f.getlength(line))
            except Exception:
                w = len(line) * size
            draw.text(((width - w) // 2, y), line, font=f, fill=fill,
                      stroke_width=stroke, stroke_fill=(0, 0, 0))
            y += int(size * 1.22)
        return y

    head = max(40, width // 11)
    sub = max(28, width // 20)
    y = int(height * 0.36)
    y = center(texts["headline"], y, head, accent, max(4, head // 10))
    if texts["sub"]:
        y = center(texts["sub"], y + int(sub * 0.6), sub, (255, 255, 255), max(3, sub // 9))
    if texts["cta"]:
        # 登録ボタン風のピル（赤地・白字）。文字だけより「押す場所」に見える。
        size = max(26, width // 24)
        f = _heavy_font(size)
        try:
            tw = int(f.getlength(texts["cta"]))
        except Exception:
            tw = len(texts["cta"]) * size
        tw = min(tw, int(width * 0.84))
        px, py = int(size * 0.9), int(size * 0.55)
        y += int(size * 1.2)
        x0 = (width - tw) // 2 - px
        draw.rounded_rectangle([x0, y, x0 + tw + 2 * px, y + size + 2 * py],
                               radius=(size + 2 * py) // 2, fill=(220, 30, 30))
        draw.text(((width - tw) // 2, y + py - int(size * 0.08)), texts["cta"], font=f,
                  fill=(255, 255, 255))
    return img


def render_loop_card(
    width: int,
    height: int,
    first_frame: Image.Image,
    channel_dict: Optional[Dict[str, Any]] = None,
    *,
    next_hint: str = "",
    accent_color: Optional[Tuple[int, int, int]] = None,
) -> Image.Image:
    """冒頭の 1 コマに戻す末尾カード（2026-10-03 visual r2）。

    r1 の批評: 末尾がぼかした「次の動画はこちら→」と赤い登録ボタンで、本編と切れた
    別画面になっていた。バー 03 は最初の呼びかけに戻って終わり、01/02/07 は答えの直前で
    切ってそのまま先頭へループする。ここでは画面を冒頭のコマ（題名の問い＋題材の図）に
    戻し、テロップの位置にだけ「次へ」とチャンネル名の 2 行を置く。ループで先頭に
    戻ったとき、同じ画が続くので継ぎ目に見えない。登録のお願いの赤ボタンは出さない。
    """
    cfg = _cfg(channel_dict)
    accent = accent_color or _color(cfg.get("accent_color"), DEFAULT_ACCENT)
    texts = build_texts(channel_dict, next_hint=next_hint)
    img = first_frame.convert("RGB").resize((width, height))
    img = Image.blend(img, Image.new("RGB", (width, height), (0, 0, 0)), 0.18)
    draw = ImageDraw.Draw(img)
    name = ((channel_dict or {}).get("name") or "").strip()
    head = texts["headline"]
    # r3: 素材枠が 1370px まで伸びたので、帯は読み上げテロップの位置（1370〜1610px）に置く
    band_top, band_bot = int(height * 0.712), int(height * 0.84)
    band = Image.new("RGBA", (width, band_bot - band_top), (0, 0, 0, 245))
    img.paste(band, (0, band_top), band)
    draw.rectangle([0, band_top, width, band_top + 6], fill=accent)

    def center(text, y, size, fill):
        while size > 20:
            try:
                if _heavy_font(size).getlength(text) <= width * 0.88:
                    break
            except Exception:
                break
            size -= 2
        f = _heavy_font(size)
        try:
            w = int(f.getlength(text))
        except Exception:
            w = len(text) * size
        draw.text(((width - w) // 2, y), text, font=f, fill=fill,
                  stroke_width=max(3, size // 12), stroke_fill=(0, 0, 0))

    mid = (band_top + band_bot) // 2
    if name:
        center(head, mid - int(width * 0.085), max(40, width // 13), accent)
        center(name, mid + int(width * 0.01), max(30, width // 19), (255, 255, 255))
    else:
        center(head, mid - int(width * 0.04), max(40, width // 13), accent)
    return img


def make_clip(
    width: int,
    height: int,
    channel_dict: Optional[Dict[str, Any]] = None,
    *,
    next_hint: str = "",
    font_loader=None,
    duration: Optional[float] = None,
    backdrop: Optional[Image.Image] = None,
    accent_color: Optional[Tuple[int, int, int]] = None,
    first_frame: Optional[Image.Image] = None,
):
    """moviepy のクリップを返す（無音トラック付き）。moviepy 未導入なら None。

    concatenate_videoclips に音声ありのクリップと混ぜるため、無音の音声を
    明示的に付ける。付けないと moviepy が音声の有無で分岐して落ちることがある。
    """
    try:
        import numpy as np
        from moviepy import AudioArrayClip, ImageClip  # type: ignore
    except Exception as e:  # pragma: no cover — moviepy 無し環境
        print(f"⚠️ endcard: moviepy unavailable ({e})")
        return None

    dur = float(duration if duration is not None else duration_for(channel_dict))
    img = render_image(
        width, height, channel_dict, next_hint=next_hint, font_loader=font_loader,
        backdrop=backdrop, accent_color=accent_color,
    )
    if first_frame is not None:
        img = render_loop_card(width, height, first_frame, channel_dict, next_hint=next_hint,
                               accent_color=accent_color)
    clip = ImageClip(np.array(img)).with_duration(dur)

    fps = 44100
    silence = AudioArrayClip(np.zeros((int(fps * dur), 2)), fps=fps)
    return clip.with_audio(silence)


def append_to_clips(
    clips: List[Any],
    *,
    width: int,
    height: int,
    channel_dict: Optional[Dict[str, Any]] = None,
    next_hint: str = "",
    font_loader=None,
    backdrop_from_last: bool = False,
    accent_color: Optional[Tuple[int, int, int]] = None,
    backdrop_from_first: bool = False,
) -> List[Any]:
    """クリップ列の末尾にエンドカードを足す（無効・失敗時は元のまま返す）。

    backdrop_from_last=True なら、最後のクリップの最終コマを背景に使う。
    backdrop_from_first=True なら、冒頭のコマに戻す（render_loop_card）。
    """
    if not is_enabled(channel_dict):
        return clips
    first_frame = None
    if backdrop_from_first and clips:
        try:
            first_frame = Image.fromarray(clips[0].get_frame(0.0))
        except Exception as e:
            print(f"⚠️ endcard first-frame failed: {e}")
            first_frame = None
    backdrop = None
    if backdrop_from_last and clips:
        try:
            last = clips[-1]
            t = max(0.0, float(last.duration or 0) - 0.05)
            backdrop = Image.fromarray(last.get_frame(t))
        except Exception as e:
            print(f"⚠️ endcard backdrop failed (plain card used): {e}")
            backdrop = None
    try:
        kwargs = {}
        if backdrop is not None or accent_color is not None:
            kwargs = {"backdrop": backdrop, "accent_color": accent_color}
        if first_frame is not None:
            kwargs["first_frame"] = first_frame
            kwargs.setdefault("accent_color", accent_color)
        clip = make_clip(
            width, height, channel_dict, next_hint=next_hint, font_loader=font_loader,
            **kwargs,
        )
    except Exception as e:
        print(f"⚠️ endcard build failed: {e}")
        return clips
    if clip is None:
        return clips
    print(f"🎬 エンドカード付与: {duration_for(channel_dict):.1f}s")
    return list(clips) + [clip]
