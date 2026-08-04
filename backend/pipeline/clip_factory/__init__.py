"""clip_factory — 既存長尺動画から縦型切り抜きショートを自動生成する。

    from pipeline.clip_factory import generate_clip, list_available_sources

    generate_clip("clip-lab", count=1, upload=True)

演出仕様は data/research/clip_shorts_visual_analysis.json の競合横断分析に準拠。
エンジンは clip.engine で local / noimos を切り替える（NoimosAI の制約は
engines/noimos.py の冒頭コメントを参照）。
"""

from .pipeline import (
    build_description,
    build_title,
    generate_clip,
    list_available_sources,
    load_channel_raw,
)

__all__ = [
    "generate_clip",
    "list_available_sources",
    "build_title",
    "build_description",
    "load_channel_raw",
]
