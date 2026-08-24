"""内製切り抜きエンジン。

台本アライメント → 区間選定 → 縦型レンダリングを自前で回す。外部SaaSも
ネットワークも要らないので autopilot から無人で走らせられる。
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import segments as seg_mod
from .. import visual_guard
from ..align import LineTiming, build_timeline
from ..renderer import ClipLayout, render_clip, render_thumbnail
from ..sources import SourceVideo


def safe_clip_id(value: str) -> str:
    """clip_id はそのままファイル名になるので、パスとして危ない文字を落とす。

    特に `:` は ffmpeg / ffprobe がプロトコル指定（`yt:...`）と解釈して
    「Protocol not found」で落ちるため、混入を許さない。
    """
    return re.sub(r"[^0-9A-Za-z_\-]", "_", value)


def _rebase(lines: Sequence[LineTiming], offset: float) -> List[LineTiming]:
    """行タイムラインを「素材ファイル内の秒」に直す。

    外部素材は該当区間だけを切り出して落とすので、ファイルの 0 秒は元動画の
    offset 秒に当たる。字幕の時刻は元動画基準のままなので、ここでずらさないと
    字幕が offset 秒ぶん先走る。
    """
    if not offset:
        return list(lines)
    return [replace(l, start=l.start - offset, end=l.end - offset) for l in lines]

# 元チャンネルの話者色を字幕に引き継ぐ（切り抜き元が分かる手掛かりになる）
DEFAULT_SPEAKER_COLORS: Dict[str, Tuple[int, int, int]] = {}


def _speaker_colors(source_channel_raw: Dict[str, Any]) -> Dict[str, Tuple[int, int, int]]:
    colors: Dict[str, Tuple[int, int, int]] = {}
    for name, cfg in (source_channel_raw.get("characters") or {}).items():
        c = cfg.get("text_color")
        if isinstance(c, (list, tuple)) and len(c) >= 3:
            colors[name] = (int(c[0]), int(c[1]), int(c[2]))
    return colors


def _materialize_checked(
    source: SourceVideo,
    segment,
    spares: List[Any],
    *,
    clip_cfg: Dict[str, Any],
):
    """区間の映像を用意し、映像ゲートを通ったものだけ返す。

    落ちたら `spares` の先頭から差し替えて落とし直す（spares は破壊的に消費する
    ので、同じ区間を次の本で再試行しない）。全滅したら None。

    戻り値: (segment, src_path, offset, verdict) または None
    """
    guard_on = visual_guard.is_enabled(clip_cfg)
    guard_cfg = visual_guard.config(clip_cfg)
    current = segment

    while True:
        src_path, offset = source.materialize(current.start, current.end)
        if not guard_on:
            return current, src_path, offset, None

        verdict = visual_guard.inspect(
            src_path,
            start=current.start - offset,
            duration=current.duration,
            cfg=guard_cfg,
        )
        if verdict.ok:
            print(f"    👁️ 映像チェック: {verdict.reason}")
            return current, src_path, offset, verdict

        print(f"    🚫 映像チェックで不採用: {verdict.reason}")
        if not spares:
            return None
        current = spares.pop(0)
        print(f"    ↩️ 予備区間に差し替え: {current.start:.1f}s〜{current.end:.1f}s "
              f"hook={current.hook!r}")


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
    # 外部素材には「下部の焼き込み字幕帯」が無いので切り落としてはいけない
    if source.crop_bottom_ratio is not None:
        layout.source_crop_bottom_ratio = float(source.crop_bottom_ratio)
    sel = clip_cfg.get("segment_selection") or {}

    from_captions = bool(source.timings)
    if from_captions:
        # 外部素材: YouTube 字幕から行タイムラインが確定済み。映像を触らずに済む
        timings = list(source.timings)
        print(f"  🧭 字幕由来のタイムライン {len(timings)} 行を使用")
    else:
        print(f"  🧭 台本 {len(lines)} 行をタイムラインに整列中…")
        timings = build_timeline(
            source.video_path, lines,
            textbox_ratio=layout.source_crop_bottom_ratio,
            duration=source.duration,
        )

    curve = []
    if sel.get("prefer_retention_peaks", True) and not source.is_external:
        # Analytics は自社チャンネルしか引けない。外部素材では台本スコアのみ
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
        # 自動字幕由来のときだけ無音を弾く。台本アライメントの行は隙間なく
        # 連続しているので、自社素材には効かせない（既定 0 ＝無効）。
        min_speech_ratio=float(sel.get("min_speech_ratio") or 0.0) if from_captions else 0.0,
        max_line_gap_sec=float(sel.get("max_line_gap_sec") or 0.0) if from_captions else 0.0,
        # 区間そのものの発話内容で落とすゲート。既定は空＝無効なので、
        # 設定していないチャンネル（clip-lab 等）の挙動は変わらない。
        exclude_text_patterns=sel.get("exclude_text_patterns") or (),
    )
    if not candidates:
        raise RuntimeError(f"切り抜き候補が作れません（尺条件に合う区間なし）: {source.title}")

    # 字幕由来（＝自動字幕）のときは LLM に多めに見せて選ばせる。ヒューリスティックの
    # スコアは整った台本向けなので、ASR の壊れた行が上位に来ることがある。多めに
    # 渡せば LLM が usable=false で落として、読めるものだけが残る。
    over_pick = min(count * 3, 6) if from_captions else count
    picked = seg_mod.pick_segments(
        candidates,
        count=max(count, over_pick),
        min_gap_sec=float(sel.get("min_gap_sec") or 30),
        used_segments=source.used_segments,
    )
    if not picked:
        raise RuntimeError(f"未使用の切り抜き区間が残っていません: {source.title}")

    used_llm = seg_mod.refine_with_claude(
        picked, source_title=source.video_title,
        channel_id=channel_raw.get("id", "clip-lab"),
        from_captions=from_captions,
    )
    if from_captions and not used_llm:
        # 自動字幕そのままのフック文は「結局そのガソリンスタンプとかが」のように
        # 壊れていることが多い。無人投稿でこれを公開する方が、その日を落とすより
        # 損害が大きいので、ここで止める。
        raise RuntimeError(
            "自動字幕由来の素材で LLM のフック生成に失敗しました。"
            "壊れたフック文で公開しないため中止します"
            "（OPENAI_API_KEY / ANTHROPIC_API_KEY を確認してください）"
        )
    seg_mod.finalize_hooks(picked)
    picked.sort(key=lambda s: s.score, reverse=True)
    # 上位 count 本を本命に、残りは映像ゲート（visual_guard）で弾かれたときの
    # 差し替え候補として取っておく。ここで捨てると、静止画区間を掴んだ日は
    # 素材を落とし直すところからやり直しになり autopilot がその日を落とす。
    spares = picked[count:]
    picked = picked[:count]
    print(f"  ✂️ 区間 {len(picked)} 本を選定 "
          f"({'LLM' if used_llm else 'ヒューリスティック'} / "
          f"retention {'あり' if curve else 'なし'}"
          f"{f' / 予備 {len(spares)} 本' if spares else ''})")

    colors = _speaker_colors(source_channel_raw)
    branding = (channel_raw.get("video_format") or {}).get("branding") or {}
    watermark = str(branding.get("watermark_text") or "")

    results: List[Dict[str, Any]] = []
    for n, segment in enumerate(picked):
        clip_id = safe_clip_id(f"{source.source_channel_id}_{int(time.time())}_{n}")
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

        # 外部素材はここで初めて映像を落とす（区間が決まるまで触らない）。
        # 落としてから映像ゲートに掛け、静止画（画面共有・資料）だったら
        # 予備の区間に差し替えて落とし直す。
        materialized = _materialize_checked(
            source, segment, spares, clip_cfg=clip_cfg)
        if materialized is None:
            print("    ⏭️ 映像ゲートを通る区間が無かったのでこの本はスキップします")
            continue
        segment, src_path, offset, verdict = materialized
        entry["segment"] = segment.to_dict()
        entry["hook"] = segment.hook
        entry["visual_check"] = verdict.to_dict() if verdict else None
        local_start = segment.start - offset
        local_end = segment.end - offset

        work = out_dir / f"_work_{clip_id}"
        video_out = out_dir / f"{clip_id}.mp4"
        render_clip(
            source_path=src_path,
            start=local_start,
            end=local_end,
            hook=segment.hook,
            subtitle_lines=_rebase(segment.lines, offset),
            layout=layout,
            out_path=video_out,
            cta_text=str(clip_cfg.get("cta_text") or "続きは本編で（概要欄）"),
            watermark=watermark,
            speaker_colors=colors,
            work_dir=work,
        )
        entry["video_path"] = str(video_out)
        entry["source_file"] = str(src_path)
        thumb = render_thumbnail(
            source_path=src_path,
            at_sec=local_start + min(3.0, segment.duration / 3),
            hook=segment.hook,
            layout=layout,
            out_path=out_dir / f"{clip_id}_thumb.jpg",
        )
        entry["thumbnail_path"] = str(thumb) if thumb else None
        # 中間 PNG（字幕コマ）は1本あたり数十枚出るので残さない
        shutil.rmtree(work, ignore_errors=True)
        results.append(entry)

    if not dry_run and picked and not results:
        # 全部が映像ゲートで落ちた。ok=True で 0 本を返すと autopilot が
        # 「成功したが何も出ていない」状態になり、静かに投稿が止まる。
        raise RuntimeError(
            "選定した区間がすべて映像ゲートで不採用になりました"
            "（画面共有・静止画の回だった可能性）。別の元動画を使ってください")

    return results
