"""内製切り抜きエンジン。

台本アライメント → 区間選定 → 縦型レンダリングを自前で回す。外部SaaSも
ネットワークも要らないので autopilot から無人で走らせられる。
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import segments as seg_mod
from ..align import build_timeline
from ..renderer import ClipLayout, render_clip, render_thumbnail
from ..sources import SourceVideo

# 元チャンネルの話者色を字幕に引き継ぐ（切り抜き元が分かる手掛かりになる）
DEFAULT_SPEAKER_COLORS: Dict[str, Tuple[int, int, int]] = {}


def _speaker_colors(source_channel_raw: Dict[str, Any]) -> Dict[str, Tuple[int, int, int]]:
    colors: Dict[str, Tuple[int, int, int]] = {}
    for name, cfg in (source_channel_raw.get("characters") or {}).items():
        c = cfg.get("text_color")
        if isinstance(c, (list, tuple)) and len(c) >= 3:
            colors[name] = (int(c[0]), int(c[1]), int(c[2]))
    return colors


def generate(
    *,
    source: SourceVideo,
    clip_cfg: Dict[str, Any],
    channel_raw: Dict[str, Any],
    source_channel_raw: Dict[str, Any],
    out_dir: Path,
    count: int = 1,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """1本の元動画から count 本の切り抜きを作る。"""
    lines = source.lines
    if not lines:
        raise RuntimeError(f"台本（full_scenario）がありません: {source.title}")

    layout = ClipLayout.from_channel(channel_raw)
    sel = clip_cfg.get("segment_selection") or {}

    print(f"  🧭 台本 {len(lines)} 行をタイムラインに整列中…")
    timings = build_timeline(
        source.video_path, lines,
        textbox_ratio=layout.source_crop_bottom_ratio,
        duration=source.duration,
    )

    curve = []
    if sel.get("prefer_retention_peaks", True):
        curve = seg_mod.fetch_retention_curve(source.source_channel_id, source.youtube_video_id)

    candidates = seg_mod.build_candidates(
        timings,
        total_duration=source.duration,
        min_sec=float(clip_cfg.get("min_duration_sec") or 30),
        max_sec=float(clip_cfg.get("max_duration_sec") or 59),
        exclude_head_sec=float(sel.get("exclude_head_sec") or 8),
        exclude_tail_sec=float(sel.get("exclude_tail_sec") or 15),
        retention_curve=curve,
        retention_weight=float(sel.get("retention_weight") or 0.5),
        script_weight=float(sel.get("script_weight") or 0.5),
    )
    if not candidates:
        raise RuntimeError(f"切り抜き候補が作れません（尺条件に合う区間なし）: {source.title}")

    picked = seg_mod.pick_segments(
        candidates,
        count=count,
        min_gap_sec=float(sel.get("min_gap_sec") or 30),
        used_segments=source.used_segments,
    )
    if not picked:
        raise RuntimeError(f"未使用の切り抜き区間が残っていません: {source.title}")

    used_claude = seg_mod.refine_with_claude(
        picked, source_title=source.video_title, channel_id=channel_raw.get("id", "clip-lab"),
    )
    seg_mod.finalize_hooks(picked)
    picked.sort(key=lambda s: s.score, reverse=True)
    print(f"  ✂️ 区間 {len(picked)} 本を選定 "
          f"({'Claude' if used_claude else 'ヒューリスティック'} / "
          f"retention {'あり' if curve else 'なし'})")

    colors = _speaker_colors(source_channel_raw)
    branding = (channel_raw.get("video_format") or {}).get("branding") or {}
    watermark = str(branding.get("watermark_text") or "")

    results: List[Dict[str, Any]] = []
    for n, segment in enumerate(picked):
        clip_id = f"{source.source_channel_id}_{int(time.time())}_{n}"
        print(f"    [{n + 1}/{len(picked)}] {segment.start:.1f}s〜{segment.end:.1f}s "
              f"({segment.duration:.1f}s) hook={segment.hook!r}")
        entry: Dict[str, Any] = {
            "clip_id": clip_id,
            "engine": "local",
            "segment": segment.to_dict(),
            "hook": segment.hook,
            "video_path": None,
            "thumbnail_path": None,
        }
        if dry_run:
            results.append(entry)
            continue

        work = out_dir / f"_work_{clip_id}"
        video_out = out_dir / f"{clip_id}.mp4"
        render_clip(
            source_path=source.video_path,
            start=segment.start,
            end=segment.end,
            hook=segment.hook,
            subtitle_lines=segment.lines,
            layout=layout,
            out_path=video_out,
            cta_text=str(clip_cfg.get("cta_text") or "続きは本編で（概要欄）"),
            watermark=watermark,
            speaker_colors=colors,
            work_dir=work,
        )
        entry["video_path"] = str(video_out)
        thumb = render_thumbnail(
            source_path=source.video_path,
            at_sec=segment.start + min(3.0, segment.duration / 3),
            hook=segment.hook,
            layout=layout,
            out_path=out_dir / f"{clip_id}_thumb.jpg",
        )
        entry["thumbnail_path"] = str(thumb) if thumb else None
        # 中間 PNG（字幕コマ）は1本あたり数十枚出るので残さない
        shutil.rmtree(work, ignore_errors=True)
        results.append(entry)

    return results
