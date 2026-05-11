"""
YouTube Factory — Phase 6 API

BGM volume preview.

The /generate form has a slider that overrides the channel's BGM volume for the
upcoming job. Before paying for a full render, the user clicks ▶ Preview to
hear a few seconds of the channel's narration voice mixed with the channel's
BGM at the slider's volume — the same `_mix_bgm` math the pipeline will use.

Endpoints:
  - POST /api/bgm-preview              — synth narration + mix with BGM, return URL
  - GET  /api/bgm-preview/{preview_id} — serve the resulting MP3
"""

from __future__ import annotations

import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api_phase1 import _state, require_session

router = APIRouter(prefix="/api", tags=["phase6"])


PROJECT_ROOT = Path(__file__).parent.parent
BGM_PREVIEW_DIR = PROJECT_ROOT / "data" / "bgm_previews"
BGM_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

PREVIEW_TTL_SECONDS = 60 * 30  # 30 min — short, this is just a quick listen

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

# Fixed sample text — short enough to render in a couple seconds.
_SAMPLE_TEXT = "BGMの音量プレビューです。お好みのバランスに調整してください。"


def _prune_old_previews() -> None:
    cutoff = time.time() - PREVIEW_TTL_SECONDS
    try:
        for f in BGM_PREVIEW_DIR.glob("*.mp3"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except Exception:
        pass


class BgmPreviewRequest(BaseModel):
    channel_id: str
    bgm_volume: float = Field(ge=0.0, le=1.0)
    duration_seconds: float = Field(default=5.0, ge=2.0, le=15.0)


class BgmPreviewResponse(BaseModel):
    preview_id: str
    url: str
    bgm_volume: float
    duration_seconds: float
    bgm_filename: Optional[str]
    voicevox_used: bool


def _mix_to_mp3(narration_wav: Path, bgm_path: Optional[Path],
                bgm_volume: float, target_duration: float, out_path: Path) -> None:
    """Mix narration + (optional) BGM at `bgm_volume` and write MP3.

    Mirrors the volume math in `pipeline.video_generator._mix_bgm` so the
    preview matches what the full render will produce.
    """
    try:
        from moviepy import AudioFileClip, CompositeAudioClip
    except ImportError:
        from moviepy.editor import AudioFileClip, CompositeAudioClip
    try:
        from moviepy.audio.AudioClip import concatenate_audioclips
    except ImportError:
        from moviepy.editor import concatenate_audioclips

    narr = AudioFileClip(str(narration_wav))
    narr_dur = float(narr.duration or 0)
    target = max(target_duration, narr_dur + 0.4)

    layers = [narr]
    bgm = None
    if bgm_path is not None and bgm_volume > 0:
        bgm = AudioFileClip(str(bgm_path))
        src = float(bgm.duration or 0)
        if src <= 0:
            bgm.close()
            bgm = None
        else:
            if src < target:
                n_loops = int(target // src) + 1
                bgm.close()
                bgm = concatenate_audioclips(
                    [AudioFileClip(str(bgm_path)) for _ in range(n_loops)]
                )
            try:
                bgm = bgm.subclipped(0, target)
            except AttributeError:
                bgm = bgm.subclip(0, target)
            try:
                bgm = bgm.with_volume_scaled(bgm_volume)
            except AttributeError:
                bgm = bgm.volumex(bgm_volume)
            layers.append(bgm)

    mixed = CompositeAudioClip(layers)
    try:
        mixed = mixed.with_duration(target)
    except AttributeError:
        mixed = mixed.set_duration(target)

    try:
        mixed.write_audiofile(
            str(out_path), codec="libmp3lame", logger=None, fps=44100
        )
    finally:
        try:
            mixed.close()
        except Exception:
            pass
        if bgm is not None:
            try:
                bgm.close()
            except Exception:
                pass
        narr.close()


@router.post("/bgm-preview", response_model=BgmPreviewResponse)
async def bgm_preview(
    req: BgmPreviewRequest, _=Depends(require_session)
) -> BgmPreviewResponse:
    """Render a few seconds of narration + BGM at the supplied volume.

    Uses the channel's BGM file (resolved with the same lookup as the full
    pipeline) and a short Japanese sample line. Returns an URL to the MP3.
    """
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(req.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {req.channel_id}")

    # Lazy-import: pulls in moviepy/PIL.
    try:
        from pipeline.video_generator import (
            _resolve_bgm_file,
            _resolve_bgm_for_mood,
            check_voicevox,
            synthesize,
            CHAR_CONFIG,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline import failed: {e}")

    audio_cfg = ((ch.video_format.to_dict() if ch else {}) or {}).get("audio") or {}
    bgm_file = _resolve_bgm_file(audio_cfg.get("bgm_path"), req.channel_id)
    # Legacy lookup only sees files directly under bgm/. When the channel uses
    # the per-mood layout (bgm/calm/*, bgm/bright/*, ...), fall back to a
    # mood-based lookup so the preview matches what the per-scene mix would
    # actually play.
    if bgm_file is None and not audio_cfg.get("bgm_path"):
        try:
            bgm_file = _resolve_bgm_for_mood("calm", req.channel_id)
        except Exception:
            bgm_file = None

    use_vv = check_voicevox()
    # Pick a sensible speaker — first character in channel config, else default.
    speaker_id = 2
    try:
        char_cfg = ch.char_config() if ch else None
        if char_cfg:
            for v in char_cfg.values():
                sid = v.get("speaker_id") if isinstance(v, dict) else None
                if isinstance(sid, int):
                    speaker_id = sid
                    break
        else:
            speaker_id = next(iter(CHAR_CONFIG.values()))["speaker_id"]
    except Exception:
        pass

    _prune_old_previews()
    preview_id = uuid.uuid4().hex
    out_path = BGM_PREVIEW_DIR / f"{preview_id}.mp3"

    with tempfile.TemporaryDirectory(prefix="bgm_preview_") as tmp:
        narr_wav = Path(tmp) / "narration.wav"
        try:
            synthesize(_SAMPLE_TEXT, speaker_id, str(narr_wav), use_vv)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"TTS failed for preview: {e}"
            )
        if not narr_wav.exists() or narr_wav.stat().st_size == 0:
            raise HTTPException(status_code=502, detail="TTS produced empty audio")

        try:
            _mix_to_mp3(
                narr_wav,
                bgm_file,
                float(req.bgm_volume),
                float(req.duration_seconds),
                out_path,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Audio mix failed: {e}")

    return BgmPreviewResponse(
        preview_id=preview_id,
        url=f"/api/bgm-preview/{preview_id}",
        bgm_volume=float(req.bgm_volume),
        duration_seconds=float(req.duration_seconds),
        bgm_filename=bgm_file.name if bgm_file else None,
        voicevox_used=use_vv,
    )


@router.get("/bgm-preview/{preview_id}")
async def serve_bgm_preview(preview_id: str, _=Depends(require_session)):
    if not _SAFE_ID_RE.match(preview_id):
        raise HTTPException(status_code=400, detail="Invalid preview_id")
    target = BGM_PREVIEW_DIR / f"{preview_id}.mp3"
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(str(target), media_type="audio/mpeg", filename=target.name)
