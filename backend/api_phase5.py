"""
YouTube Factory — Phase 5 API

Sample-then-confirm illustration flow.

Used by:
  1. `/generate` page — generate ONE sample illustration before submitting the
     full video job, so the user can approve the style before paying for ~24
     more DALL-E calls.
  2. `/channels/new` wizard — generate a sample using the prospective channel's
     style config to validate the prompt before saving the channel JSON.

Endpoints:
  - POST   /api/illustrations/sample          — generate a sample, save to disk
  - GET    /api/illustrations/sample/{id}     — serve the PNG (for <img src>)
  - DELETE /api/illustrations/sample/{id}     — cleanup
"""

from __future__ import annotations

import io
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api_phase1 import _state, require_session

router = APIRouter(prefix="/api", tags=["phase5"])


PROJECT_ROOT = Path(__file__).parent.parent
SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAILS_DIR = PROJECT_ROOT / "data" / "thumbnails"
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

# Samples older than this are pruned on each new request (best-effort GC).
SAMPLE_TTL_SECONDS = 60 * 60 * 24  # 24h
THUMBNAIL_TTL_SECONDS = 60 * 60 * 24 * 3  # 3d (kept longer so users can pick later)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _prune_old_samples() -> None:
    cutoff = time.time() - SAMPLE_TTL_SECONDS
    try:
        for f in SAMPLES_DIR.glob("*.png"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except Exception:
        pass


def _prune_old_thumbnails() -> None:
    cutoff = time.time() - THUMBNAIL_TTL_SECONDS
    try:
        for f in THUMBNAILS_DIR.glob("*.png"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except Exception:
        pass


# =====================================================================
# Schemas
# =====================================================================

class IllustrationStyle(BaseModel):
    """Channel-style overrides for DALL-E. Mirrors IllustrationStyleConfig."""
    style: Optional[str] = "vivid"           # vivid | natural
    format: Optional[str] = "landscape"      # landscape | square | portrait
    art_style: Optional[str] = None
    background: Optional[str] = None
    include_characters: Optional[bool] = True
    frame_style: Optional[str] = None
    extra_prompt: Optional[str] = ""
    allow_text_labels: Optional[bool] = False
    allow_frame: Optional[bool] = False


class SampleRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=400)
    illust_style: Optional[IllustrationStyle] = None
    # When channel_id is provided, the channel's saved style/character config is
    # used as the base, and `illust_style` (if any) overrides it field-by-field.
    channel_id: Optional[str] = None
    include_characters: Optional[bool] = None  # explicit override at request level
    # Ordered list of free-text feedback strings the user has supplied across
    # previous regenerations of the SAME sample. Applied to the DALL-E prompt as
    # explicit revision instructions. Empty/None → fresh first-time generation.
    feedback: Optional[List[str]] = None


def _build_feedback_block(feedback: Optional[List[str]]) -> str:
    """Render the user's feedback history into a prompt-safe instruction block."""
    if not feedback:
        return ""
    cleaned = [f.strip() for f in feedback if f and f.strip()]
    if not cleaned:
        return ""
    bullets = "\n".join(f"- {f}" for f in cleaned)
    return (
        "USER REVISION INSTRUCTIONS (apply ALL of the following corrections from "
        "the user; the latest items take priority over earlier ones if they "
        "conflict):\n" + bullets
    )


class SampleResponse(BaseModel):
    sample_id: str
    url: str
    prompt: str
    style: Dict[str, Any]
    # Echo the feedback list back so the client can show "n回目の修正" etc.
    feedback: List[str] = Field(default_factory=list)


# =====================================================================
# Endpoints
# =====================================================================

@router.post("/illustrations/sample", response_model=SampleResponse)
async def generate_sample_illustration(
    req: SampleRequest, _=Depends(require_session)
) -> SampleResponse:
    """Generate ONE DALL-E illustration and persist it as a sample.

    Each call returns a fresh `sample_id` even for identical inputs — this is
    the "regenerate" button on the frontend.
    """
    _prune_old_samples()

    # Resolve effective style + char_config
    style_dict: Dict[str, Any] = {}
    char_config: Optional[Dict[str, Any]] = None

    if req.channel_id:
        cm = _state.get("channel_manager")
        if cm is None:
            raise HTTPException(status_code=503, detail="Channel manager not ready")
        ch = cm.get(req.channel_id)
        if not ch:
            raise HTTPException(
                status_code=404, detail=f"Channel not found: {req.channel_id}"
            )
        style_dict = ch.illustration_style_config()
        char_config = ch.char_config()

    if req.illust_style is not None:
        for k, v in req.illust_style.dict(exclude_none=True).items():
            style_dict[k] = v

    if req.include_characters is not None:
        style_dict["include_characters"] = req.include_characters
        if not req.include_characters:
            char_config = None

    # Lazy-import: heavy module pulls in moviepy etc.
    try:
        from pipeline.video_generator import (
            _build_illustration_prompt,
            _call_openai_image,
            _ILLUST_FORMAT_SIZE,
            OPENAI_API_KEY,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline import failed: {e}")

    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY not configured (/settings から設定してください)",
        )

    fmt = style_dict.get("format", "landscape")
    size = _ILLUST_FORMAT_SIZE.get(fmt, "1792x1024")
    dalle_style = style_dict.get("style", "vivid")
    if dalle_style not in ("vivid", "natural"):
        dalle_style = "vivid"

    prompt = _build_illustration_prompt(
        req.topic, char_config=char_config, illust_style=style_dict
    )

    feedback_block = _build_feedback_block(req.feedback)
    if feedback_block:
        # Append the user's revision history to the DALL-E prompt so the new
        # generation actively incorporates the requested fixes.
        prompt = f"{prompt}\n\n{feedback_block}"

    img = _call_openai_image(
        prompt, size=size, style=dalle_style, channel_id=req.channel_id
    )
    if img is None:
        raise HTTPException(status_code=502, detail="DALL-E sample generation failed")

    sample_id = uuid.uuid4().hex
    out_path = SAMPLES_DIR / f"{sample_id}.png"
    img.save(str(out_path))

    return SampleResponse(
        sample_id=sample_id,
        url=f"/api/illustrations/sample/{sample_id}",
        prompt=prompt,
        style=style_dict,
        feedback=[f.strip() for f in (req.feedback or []) if f and f.strip()],
    )


@router.get("/illustrations/sample/{sample_id}")
async def serve_sample(sample_id: str, _=Depends(require_session)):
    if not _SAFE_ID_RE.match(sample_id):
        raise HTTPException(status_code=400, detail="Invalid sample_id")
    target = SAMPLES_DIR / f"{sample_id}.png"
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Sample not found")
    return FileResponse(str(target), media_type="image/png", filename=target.name)


@router.delete("/illustrations/sample/{sample_id}")
async def delete_sample(
    sample_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    if not _SAFE_ID_RE.match(sample_id):
        raise HTTPException(status_code=400, detail="Invalid sample_id")
    target = SAMPLES_DIR / f"{sample_id}.png"
    if target.exists():
        target.unlink()
    return {"status": "deleted", "sample_id": sample_id}


# =====================================================================
# Thumbnail generation (HTML+CSS+Playwright pipeline)
# =====================================================================

class ThumbnailGenerateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    channel_id: str = Field(min_length=1)
    # If supplied, reuse the existing background instead of calling DALL-E
    # again — useful for "regenerate text only" preview iterations.
    reuse_background_id: Optional[str] = None
    # Optional brief overrides — when the user wants to force specific lines.
    line1: Optional[str] = None
    line2: Optional[str] = None
    line3_badge: Optional[str] = None
    sub_text: Optional[str] = None
    # Ordered list of free-text revision instructions accumulated across
    # previous regenerations of the same thumbnail. Each string is a single
    # user feedback message ("もっとインパクトを強く" など). Most recent items take
    # priority. When non-empty, the GPT-4o brief generation is instructed to
    # apply these revisions on top of the title.
    feedback: Optional[List[str]] = None


class ThumbnailGenerateResponse(BaseModel):
    thumbnail_id: str
    thumbnail_url: str
    background_id: str
    background_url: str
    brief: Dict[str, Any]
    feedback: List[str] = Field(default_factory=list)


def _build_brief_override(req: ThumbnailGenerateRequest) -> Optional[Dict[str, Any]]:
    if not any([req.line1, req.line2, req.line3_badge, req.sub_text]):
        return None
    return {
        "line1": req.line1 or "",
        "line2": req.line2 or "",
        "line3_badge": req.line3_badge or "",
        "sub_text": req.sub_text or "",
        "highlight_word": "",
        "background_concept": f"Cinematic illustration related to: {req.title}",
    }


async def _do_generate_thumbnail(
    req: ThumbnailGenerateRequest,
) -> ThumbnailGenerateResponse:
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(req.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {req.channel_id}")

    try:
        from pipeline.thumbnail_generator import generate_thumbnail_async
        from pipeline.video_generator import OPENAI_API_KEY
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline import failed: {e}")

    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY not configured (/settings から設定してください)",
        )

    _prune_old_thumbnails()

    thumb_id = uuid.uuid4().hex
    thumb_path = THUMBNAILS_DIR / f"{thumb_id}.png"

    if req.reuse_background_id:
        if not _SAFE_ID_RE.match(req.reuse_background_id):
            raise HTTPException(status_code=400, detail="Invalid reuse_background_id")
        bg_path = THUMBNAILS_DIR / f"{req.reuse_background_id}_bg.png"
        if not bg_path.exists():
            raise HTTPException(status_code=404, detail="Background not found")
        bg_id = req.reuse_background_id
    else:
        bg_id = thumb_id
        bg_path = THUMBNAILS_DIR / f"{bg_id}_bg.png"

    cleaned_feedback = [f.strip() for f in (req.feedback or []) if f and f.strip()]

    try:
        result = await generate_thumbnail_async(
            req.title,
            ch.to_dict(),
            thumb_path,
            openai_api_key=OPENAI_API_KEY,
            reuse_background_path=bg_path if req.reuse_background_id else None,
            background_save_path=bg_path,
            brief_override=_build_brief_override(req),
            feedback=cleaned_feedback or None,
        )
    except TypeError:
        # Older pipeline that does not yet accept `feedback` — fall back so the
        # endpoint keeps working, but without the new instructions threading.
        result = await generate_thumbnail_async(
            req.title,
            ch.to_dict(),
            thumb_path,
            openai_api_key=OPENAI_API_KEY,
            reuse_background_path=bg_path if req.reuse_background_id else None,
            background_save_path=bg_path,
            brief_override=_build_brief_override(req),
        )
    except RuntimeError as e:
        # OPENAI_API_KEY missing or playwright not installed
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Thumbnail generation failed: {e}")

    return ThumbnailGenerateResponse(
        thumbnail_id=thumb_id,
        thumbnail_url=f"/api/thumbnails/{thumb_id}",
        background_id=bg_id,
        background_url=f"/api/thumbnails/{bg_id}/background",
        brief=result.get("brief", {}),
        feedback=cleaned_feedback,
    )


@router.post("/thumbnails/generate", response_model=ThumbnailGenerateResponse)
async def generate_thumbnail_endpoint(
    req: ThumbnailGenerateRequest, _=Depends(require_session)
) -> ThumbnailGenerateResponse:
    """Generate a fresh thumbnail (GPT-4o brief + DALL-E 3 BG + HTML render)."""
    return await _do_generate_thumbnail(req)


@router.post("/thumbnails/preview", response_model=ThumbnailGenerateResponse)
async def preview_thumbnail_endpoint(
    req: ThumbnailGenerateRequest, _=Depends(require_session)
) -> ThumbnailGenerateResponse:
    """Same as /generate but explicitly intended for preview iterations.

    When `reuse_background_id` is provided the DALL-E call is skipped and the
    saved background PNG is reused — only the HTML/text changes are re-rendered.
    """
    return await _do_generate_thumbnail(req)


@router.get("/thumbnails/{thumbnail_id}")
async def serve_thumbnail(thumbnail_id: str, _=Depends(require_session)):
    if not _SAFE_ID_RE.match(thumbnail_id):
        raise HTTPException(status_code=400, detail="Invalid thumbnail_id")
    target = THUMBNAILS_DIR / f"{thumbnail_id}.png"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(str(target), media_type="image/png", filename=target.name)


@router.get("/thumbnails/{background_id}/background")
async def serve_thumbnail_background(background_id: str, _=Depends(require_session)):
    if not _SAFE_ID_RE.match(background_id):
        raise HTTPException(status_code=400, detail="Invalid background_id")
    target = THUMBNAILS_DIR / f"{background_id}_bg.png"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Background not found")
    return FileResponse(str(target), media_type="image/png", filename=target.name)


@router.delete("/thumbnails/{thumbnail_id}")
async def delete_thumbnail(
    thumbnail_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    if not _SAFE_ID_RE.match(thumbnail_id):
        raise HTTPException(status_code=400, detail="Invalid thumbnail_id")
    deleted = []
    for suffix in (".png", "_bg.png"):
        target = THUMBNAILS_DIR / f"{thumbnail_id}{suffix}"
        if target.exists():
            target.unlink()
            deleted.append(target.name)
    return {"status": "deleted", "thumbnail_id": thumbnail_id, "files": deleted}
