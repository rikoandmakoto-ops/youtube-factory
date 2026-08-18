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

from PIL import Image, ImageDraw

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
) -> Image.Image:
    """エンドカードの静止画（RGB）。

    Args:
        font_loader: size -> PIL font。video_generator.get_font を渡す想定。
            未指定ならデフォルトフォント（テストや単体実行用）。
    """
    cfg = _cfg(channel_dict)
    bg = _color(cfg.get("bg_color"), DEFAULT_BG)
    accent = _color(cfg.get("accent_color"), DEFAULT_ACCENT)
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


def make_clip(
    width: int,
    height: int,
    channel_dict: Optional[Dict[str, Any]] = None,
    *,
    next_hint: str = "",
    font_loader=None,
    duration: Optional[float] = None,
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
        width, height, channel_dict, next_hint=next_hint, font_loader=font_loader
    )
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
) -> List[Any]:
    """クリップ列の末尾にエンドカードを足す（無効・失敗時は元のまま返す）。"""
    if not is_enabled(channel_dict):
        return clips
    try:
        clip = make_clip(
            width, height, channel_dict, next_hint=next_hint, font_loader=font_loader
        )
    except Exception as e:
        print(f"⚠️ endcard build failed: {e}")
        return clips
    if clip is None:
        return clips
    print(f"🎬 エンドカード付与: {duration_for(channel_dict):.1f}s")
    return list(clips) + [clip]
