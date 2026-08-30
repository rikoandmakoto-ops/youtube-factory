"""海外バイラル動画 → 日本語字幕ショートのエンジン。

`engines/local.py` の兄弟。違いは2つ。

    local  : 台本アライメント or YouTube 字幕（日本語がすでにある）／`renderer.py`
    viral  : Whisper で書き起こし → Claude で日本語化／`renderer_overseas.py`

**レンダラは共有していない。** 2026-08-30 の方針変更で海外バイラルは専用の
`clip-viral` ではなく既存の `clip-lab` に同居する運用になったため、レンダラを
共有すると海外枠の見た目調整が 17:45 の国内切り抜きにも波及する。
詳細は `renderer_overseas.py` の冒頭コメント。

════════════════════════════════════════════════════════════════════
■ 処理の順番（重い順に後ろへ）
════════════════════════════════════════════════════════════════════

    1. 素材を落とす（数MB・数秒）          viral_sources.download
    2. 実尺を probe して窓を決める         asr.densest_window
    3. 書き起こす（Whisper・数十秒）       asr.transcribe
    4. 書き起こしに禁止語ゲート            viral_sources.check_text
    5. 日本語化＋フック＋安全判定（Claude） translate.translate_clip
    6. 縦型レンダリング（ffmpeg）          renderer.render_clip

3 より前で落とせるものは全部落とす。Whisper と Claude が一番高いので、
そこへ辿り着く前にゲートを効かせる。

════════════════════════════════════════════════════════════════════
■ 無音動画
════════════════════════════════════════════════════════════════════

r/funny 系は音声なし・BGM のみが普通にある。`content_gate.require_speech` が
false（既定）なら **字幕なし・フック文だけ**で作る。映像で完結する動画は
それで成立するし、無理に字幕を付ける方が事故る。true にすると捨てる。
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import asr as asr_mod
from .. import translate as tr_mod
from .. import viral_sources as vs
from ..align import LineTiming
from ..renderer_overseas import (
    OverseasLayout,
    probe_size,
    render_clip,
    render_thumbnail,
)
from ..sources import SourceVideo
from .local import safe_clip_id


class ViralClipRejected(RuntimeError):
    """ゲートで落ちた。呼び出し側は別の素材に進めばよい。"""


def _probe_duration(path: Path) -> float:
    from ..align import probe_duration
    return float(probe_duration(path) or 0.0)


def _to_line_timings(lines: Sequence[tr_mod.TranslatedLine]) -> List[LineTiming]:
    """翻訳済みの行を renderer が食える形にする。

    speaker は空文字。海外素材に話者情報は無いので、字幕は
    `ClipLayout.subtitle_default_color`（白）で統一される。
    """
    return [
        LineTiming(index=i, speaker="", text=l.text_ja, start=l.start, end=l.end)
        for i, l in enumerate(lines)
    ]


def _choose_window(
    duration: float, *, min_sec: float, target_sec: float, max_sec: float,
    transcript: Optional[asr_mod.Transcript],
) -> Tuple[float, float]:
    """切り出す区間を決める。

    バイラル動画は元から 60 秒未満が大半なので、**基本は丸ごと使う**。
    ショートの尺上限を超える素材だけ、発話が最も詰まっている窓に絞る。
    """
    if duration <= max_sec:
        return 0.0, duration
    window = min(max_sec, max(min_sec, target_sec))
    if transcript and transcript.segments:
        best = asr_mod.densest_window(transcript, window_sec=window)
        if best:
            return best
    return 0.0, window


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
    """1本のバイラル動画から切り抜きを作る（通常 1 本）。"""
    channel_id = str(channel_raw.get("id") or "clip-lab")
    gate = vs.gate_cfg(clip_cfg)
    asr_cfg = vs.asr_cfg(clip_cfg)
    perm = source.permission or {}

    layout = OverseasLayout.from_channel(channel_raw)
    # 海外素材に「下部の焼き込み字幕帯」は無いので切り落とさない
    layout.source_crop_bottom_ratio = float(source.crop_bottom_ratio or 0.0)

    # 尺は海外枠専用の値を使う。clip-lab に同居している以上、`clip.min_duration_sec`
    # （国内切り抜きの 30 秒）をそのまま使うと 10〜25 秒のバイラル動画が全部
    # 「尺が短すぎます」で落ちる。`clip.viral_sources.output` が第一。
    out_cfg = vs.output_cfg(clip_cfg)
    min_sec = float(out_cfg.get("min_duration_sec")
                    or clip_cfg.get("min_duration_sec") or 8)
    target_sec = float(out_cfg.get("target_duration_sec")
                       or clip_cfg.get("target_duration_sec") or 45)
    max_sec = float(out_cfg.get("max_duration_sec")
                    or clip_cfg.get("max_duration_sec") or 59)

    # ---- 1. 素材を手元に置く -------------------------------------------
    src_path, _offset = source.materialize(0.0, source.duration)
    src_path = Path(src_path)
    duration = _probe_duration(src_path) or source.duration
    if duration <= 0:
        raise ViralClipRejected(f"素材の尺を取得できません: {src_path}")
    print(f"  🎬 素材: {src_path.name} ({duration:.1f}s / {probe_size(src_path)})")

    # ---- 2. 書き起こし --------------------------------------------------
    transcript: Optional[asr_mod.Transcript] = None
    try:
        transcript = asr_mod.transcribe(
            src_path,
            model_size=str(asr_cfg.get("model") or "small"),
            compute_type=str(asr_cfg.get("compute_type") or "int8"),
            language=(asr_cfg.get("language") or None),
            beam_size=int(asr_cfg.get("beam_size") or 5),
            duration=duration,
        )
    except asr_mod.AsrUnavailable as e:
        if bool(gate.get("require_speech", False)):
            raise
        print(f"  ⚠️ 書き起こしを飛ばします（{e}）")

    # ---- 3. 区間を決める -------------------------------------------------
    start, end = _choose_window(
        duration, min_sec=min_sec, target_sec=target_sec, max_sec=max_sec,
        transcript=transcript,
    )
    if end - start < min_sec:
        raise ViralClipRejected(
            f"尺が短すぎます（{end - start:.1f}s < {min_sec:.0f}s）: {source.title}")

    speech = (asr_mod.slice_segments(transcript, start, end)
              if transcript else [])
    # 窓の 0 秒基準に直す。renderer は素材ファイル内の絶対秒を受けるので
    # ここでは戻さず、翻訳のためだけに相対化した写しを作る。
    min_ratio = float(gate.get("min_speech_ratio") or 0.0)
    ratio = (sum(s.duration for s in speech) / max(0.1, end - start)) if speech else 0.0
    if bool(gate.get("require_speech", False)) and ratio < max(min_ratio, 0.05):
        raise ViralClipRejected(
            f"発話がほとんどありません（発話率 {ratio:.0%}）: {source.title}")

    # ---- 4. 書き起こしの禁止語ゲート -------------------------------------
    if speech:
        hit = vs.check_text(" ".join(s.text for s in speech),
                            vs.transcript_patterns(clip_cfg))
        if hit:
            raise ViralClipRejected(f"書き起こしに禁止語『{hit}』が含まれます")

    # ---- 5. 日本語化（Claude） -------------------------------------------
    # 海外枠のルールを優先する。同居先 clip-lab の voice_style.style_rules は
    # 「元配信者の発言を改変しない」等の国内切り抜き向けで、翻訳には効かない。
    style_rules = (vs.cfg(clip_cfg).get("style_rules")
                   or (channel_raw.get("voice_style") or {}).get("style_rules")
                   or [])
    request_id = f"viral_{safe_clip_id(str(perm.get('post_id') or source.title))[:40]}"
    translated = tr_mod.translate_clip(
        speech,
        source_title=source.video_title,
        community=str(perm.get("community") or ""),
        channel_id=channel_id,
        style_rules=style_rules,
        request_id=request_id,
    )
    print(f"  🇯🇵 日本語化: hook={translated.hook!r} / 字幕 {len(translated.lines)} 行"
          f"（{translated.source}）")

    timings = _to_line_timings(translated.lines)
    clip_id = safe_clip_id(f"{source.source_channel_id}_{int(time.time())}_0")
    segment = {
        "start": round(start, 2),
        "end": round(end, 2),
        "duration": round(end - start, 2),
        "score": float(perm.get("score") or 0),
        "hook": translated.hook,
        "reason": translated.summary,
        "speech_ratio": round(ratio, 3),
        "language": (transcript.language if transcript else ""),
    }

    entry: Dict[str, Any] = {
        "clip_id": clip_id,
        "engine": "viral",
        "segment": segment,
        "hook": translated.hook,
        "video_path": None,
        "thumbnail_path": None,
        "source_file": str(src_path),
        "translation": translated.to_dict(),
        "transcript": transcript.to_dict() if transcript else None,
        # 目視レビュー運用なら private で上げる（pipeline がこれを優先する）
        "force_privacy": "private" if vs.requires_review(clip_cfg) else None,
    }
    if dry_run:
        return [entry]

    # ---- 6. レンダリング --------------------------------------------------
    branding = (channel_raw.get("video_format") or {}).get("branding") or {}
    # CTA は既定で空（海外枠に「本編」は無い。出典は説明欄に出す）。
    cta_text = str(out_cfg.get("cta_text") if out_cfg.get("cta_text") is not None
                   else (clip_cfg.get("cta_text") or ""))
    watermark = str(out_cfg.get("watermark_text")
                    if out_cfg.get("watermark_text") is not None
                    else (branding.get("watermark_text") or ""))
    work = out_dir / f"_work_{clip_id}"
    video_out = out_dir / f"{clip_id}.mp4"
    render_clip(
        source_path=src_path,
        start=start,
        end=end,
        hook=translated.hook,
        subtitle_lines=timings,
        layout=layout,
        out_path=video_out,
        cta_text=cta_text,
        watermark=watermark,
        work_dir=work,
    )
    entry["video_path"] = str(video_out)

    thumb = render_thumbnail(
        source_path=src_path,
        at_sec=start + min(3.0, (end - start) / 3),
        hook=translated.hook,
        layout=layout,
        out_path=out_dir / f"{clip_id}_thumb.jpg",
        reserve_subtitles=bool(timings),
    )
    entry["thumbnail_path"] = str(thumb) if thumb else None
    shutil.rmtree(work, ignore_errors=True)

    # 採用した投稿は調達履歴に残す（同じ動画を二度作らない）
    _record(source, status="used", note=clip_id)
    return [entry]


def _record(source: SourceVideo, *, status: str, note: str) -> None:
    perm = source.permission or {}
    post_id = str(perm.get("post_id") or "")
    if not post_id:
        return
    cand = vs.ViralCandidate(
        post_id=post_id,
        platform=str(perm.get("platform") or "reddit"),
        title=source.title,
        media_url="",
        permalink=str(perm.get("url") or ""),
        community=str(perm.get("community") or ""),
        author=str(perm.get("author") or ""),
        score=int(perm.get("score") or 0),
        duration_sec=source.duration,
        over_18=bool(perm.get("over_18")),
        gate_ok=True,
        gate_reason=str(perm.get("reason") or ""),
    )
    vs.record(cand, status=status, note=note)


def record_rejection(source: SourceVideo, reason: str) -> None:
    """ゲートで落ちた素材を履歴に残す（毎日同じ動画を落とし直さないため）。"""
    _record(source, status="rejected", note=reason)
