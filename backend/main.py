"""
YouTube Factory — マルチチャンネル自動動画生成プラットフォーム API

チャンネル管理・自動シナリオ生成・並列ジョブキュー・動画パイプラインを統合。
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
import uuid
import json
import secrets
import hashlib
from pathlib import Path
from datetime import datetime
from enum import Enum
import threading

from dotenv import load_dotenv
load_dotenv(override=True)

from pipeline.title_generator import generate_titles, select_best_title
from pipeline.description_generator import generate_description, generate_description_from_job
from pipeline.video_generator import (
    generate_all, EARWORM_SHORT, EARWORM_FULL, CLEANING_SHORT, CLEANING_FULL,
    CAT_CUCUMBER_SHORT, CAT_CUCUMBER_FULL,
    QUEUE_MONO_SHORT, QUEUE_MONO_FULL, ASSETS_DIR,
)

# ── Multi-channel modules ──
from channels import ChannelManager
from pipeline.auto_scenario import ScenarioGenerator
from pipeline.scheduler import JobQueue

# ── Phase 1 / 2 / 3 / 4 API (新フロントエンド用) ──
import api_phase1
import api_phase2
import api_phase3
import api_phase4
import api_phase5
import api_phase6
import api_improvement
import api_channel_autopilot
import api_analytics
import api_pdca
import api_logs_archives


# Models
class JobStatus(str, Enum):
    PENDING = "pending"
    GENERATING_TITLE = "generating_title"
    GENERATING_DESCRIPTION = "generating_description"
    GENERATING_THUMBNAIL = "generating_thumbnail"
    GENERATING_VIDEO = "generating_video"
    COMPLETED = "completed"
    FAILED = "failed"


class Timestamp(BaseModel):
    time: str  # Format: "MM:SS"
    title: str


class ComposeRequest(BaseModel):
    scenario: str
    title: Optional[str] = None
    duration_seconds: Optional[int] = None
    timestamps: Optional[List[Timestamp]] = None
    custom_summary: Optional[str] = None
    additional_info: Optional[str] = None


class VideoGenerateRequest(BaseModel):
    scenario: str = "earworm"  # scenario name
    style: Optional[str] = None  # "yukkuri" or "monologue" (None = auto from scenario)
    output_dir: Optional[str] = None  # custom output directory
    gen_type: str = "both"  # "both", "short", "full"
    bg_type: str = "auto"  # "video" = 動的, "static" = 静的, "auto" = 自動判定
    bg_path: Optional[str] = None  # custom background video/image path
    speed: Optional[float] = 1.3  # 話速倍率 (default 1.3x)
    target_duration: Optional[int] = 720  # 目標尺（秒）— 720=12分目安(フル, 最低10分=600), 30=ショート
    use_illustrations: bool = True  # GPT DALL-Eで手書き風イラスト生成


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    title_suggestions: Optional[List[str]] = None
    selected_title: Optional[str] = None
    description: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


# In-memory job storage (in production, use database)
jobs: Dict[str, Dict] = {}

app = FastAPI(title="YouTube Factory — マルチチャンネル自動動画生成")

# ── CORS — Vercelフロントエンドからのアクセス許可 ──
_CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "").split(",") if os.environ.get("CORS_ORIGINS") else []
_CORS_ORIGINS += [
    "http://localhost:3000",        # Next.js dev
    "http://localhost:8000",        # local backend
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Key認証 ──
_API_KEY_FILE = Path(__file__).parent / "pipeline" / "credentials" / "api_key.txt"


def _load_api_key() -> str:
    """APIキーをファイルから読み込み。なければ自動生成"""
    if _API_KEY_FILE.exists():
        return _API_KEY_FILE.read_text().strip()
    key = "ytf_" + secrets.token_urlsafe(32)
    _API_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _API_KEY_FILE.write_text(key)
    print(f"🔐 New API key generated: {key}")
    return key


_FACTORY_API_KEY = _load_api_key()


async def verify_api_key(request: Request):
    """APIキー認証。ヘッダー or クエリパラメータで受付"""
    # ローカルアクセスはスキップ
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return
    # /dashboard/ と /health はスキップ
    if request.url.path.startswith("/dashboard") or request.url.path == "/health" or request.url.path == "/":
        return
    # /api/* (Phase 1) は独自にJWT認証するためスキップ
    if request.url.path.startswith("/api/"):
        return
    # APIキーチェック
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not key or key != _FACTORY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


app.dependency_overrides = {}
# 全エンドポイントにAPIキー認証を適用（ローカルはスキップ）
app.router.dependencies = [Depends(verify_api_key)]

# ── Phase 1 / 2 / 3 / 4 ルーター（/api/* — JWTで認証）──
app.include_router(api_phase1.router)
app.include_router(api_phase2.router)
app.include_router(api_phase3.router)
app.include_router(api_phase4.router)
app.include_router(api_phase5.router)
app.include_router(api_phase6.router)
app.include_router(api_improvement.router)
app.include_router(api_channel_autopilot.router)
app.include_router(api_analytics.router)
app.include_router(api_pdca.router)
app.include_router(api_logs_archives.router)


# ── Global instances (initialized at startup) ──
channel_manager: Optional[ChannelManager] = None
scenario_generator: Optional[ScenarioGenerator] = None
job_queue: Optional[JobQueue] = None


@app.get("/")
async def root():
    """Redirect to dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard/index.html")


# Mount static files for dashboard UI
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_static_dir)), name="dashboard")


@app.post("/compose", response_model=JobResponse)
async def compose(request: ComposeRequest) -> JobResponse:
    """
    Trigger the full composition pipeline: title + description + thumbnail generation.

    Args:
        request: ComposeRequest with scenario and optional parameters

    Returns:
        JobResponse with generated content
    """
    job_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    # Initialize job
    jobs[job_id] = {
        'status': JobStatus.GENERATING_TITLE,
        'created_at': now,
        'updated_at': now,
        'request': request.dict(),
    }

    try:
        # Step 1: Generate title suggestions
        jobs[job_id]['status'] = JobStatus.GENERATING_TITLE
        title_suggestions = generate_titles(request.scenario, num_suggestions=5)
        selected_title = request.title or select_best_title(title_suggestions)

        jobs[job_id]['title_suggestions'] = title_suggestions
        jobs[job_id]['selected_title'] = selected_title

        # Step 2: Generate description
        jobs[job_id]['status'] = JobStatus.GENERATING_DESCRIPTION
        job_data = {
            'title': selected_title,
            'scenario': request.scenario,
            'duration_seconds': request.duration_seconds,
            'timestamps': [ts.dict() for ts in request.timestamps] if request.timestamps else None,
            'custom_summary': request.custom_summary,
            'additional_info': request.additional_info,
        }

        description = generate_description_from_job(job_data)
        jobs[job_id]['description'] = description

        # Step 3: Generate thumbnail (placeholder)
        jobs[job_id]['status'] = JobStatus.GENERATING_THUMBNAIL
        # TODO: Implement thumbnail generation
        jobs[job_id]['thumbnail_url'] = None

        # Mark as completed
        jobs[job_id]['status'] = JobStatus.COMPLETED
        jobs[job_id]['updated_at'] = datetime.now().isoformat()

    except Exception as e:
        jobs[job_id]['status'] = JobStatus.FAILED
        jobs[job_id]['error'] = str(e)
        jobs[job_id]['updated_at'] = datetime.now().isoformat()
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

    return _format_job_response(job_id)


@app.get("/job/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Retrieve job status and results."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return _format_job_response(job_id)


@app.post("/generate-description")
async def generate_description_endpoint(request: ComposeRequest) -> Dict[str, str]:
    """
    Generate description only (without triggering full pipeline).

    Args:
        request: ComposeRequest with scenario and optional parameters

    Returns:
        Dict with description sections
    """
    job_data = {
        'title': request.title or 'Untitled',
        'scenario': request.scenario,
        'duration_seconds': request.duration_seconds,
        'timestamps': [ts.dict() for ts in request.timestamps] if request.timestamps else None,
        'custom_summary': request.custom_summary,
        'additional_info': request.additional_info,
    }

    return generate_description_from_job(job_data)


@app.post("/generate-title")
async def generate_title_endpoint(scenario: str) -> Dict[str, List[str]]:
    """
    Generate title suggestions only.

    Args:
        scenario: The video scenario/script

    Returns:
        Dict with title suggestions
    """
    titles = generate_titles(scenario, num_suggestions=5)
    return {
        'titles': titles,
        'selected': select_best_title(titles),
    }


def _format_job_response(job_id: str) -> JobResponse:
    """Format a job from internal storage to JobResponse."""
    job = jobs[job_id]

    return JobResponse(
        job_id=job_id,
        status=job['status'],
        title_suggestions=job.get('title_suggestions'),
        selected_title=job.get('selected_title'),
        description=job.get('description'),
        error=job.get('error'),
        created_at=job['created_at'],
        updated_at=job['updated_at'],
    )


# Video generation job tracking
video_jobs: Dict[str, Dict] = {}


def _run_video_generation(job_id: str, sc: dict, bg: str, output_dir: str,
                          gen_type: str, bg_type: str = "auto",
                          speed: float = 1.3, target_duration: int = 720,
                          style: str = None, use_illustrations: bool = True):
    """Run video generation in background thread."""
    try:
        video_jobs[job_id]["status"] = "generating"
        # Resolve style: explicit > scenario default > "yukkuri"
        resolved_style = style or sc.get("style", "yukkuri")
        results = generate_all(
            title=sc["title"],
            prefix=sc["prefix"],
            short_scenario=sc["short"],
            full_scenario=sc["full"],
            bg_video_path=bg,
            output_dir=output_dir,
            gen_type=gen_type,
            bg_type=bg_type,
            thumb_info=sc.get("thumb_info"),
            speed=speed,
            target_duration=target_duration,
            video_title=sc.get("video_title"),
            style=resolved_style,
            use_illustrations=use_illustrations,
        )
        video_jobs[job_id]["status"] = "done"
        video_jobs[job_id]["results"] = results
    except Exception as e:
        video_jobs[job_id]["status"] = "error"
        video_jobs[job_id]["error"] = str(e)


@app.post("/generate-video")
async def generate_video_endpoint(request: VideoGenerateRequest):
    """Start video generation in background. Returns job_id immediately."""
    SCENARIOS = {
        "earworm": {
            "title": "イヤーワームの科学",
            "video_title": "【ゆっくり解説】なぜ同じ曲が頭から離れない？98%が経験する「イヤーワーム」の科学",
            "prefix": "earworm",
            "short": EARWORM_SHORT,
            "full": EARWORM_FULL,
            "style": "yukkuri",
            "thumb_info": {
                "hook_lines": ["なぜ同じ曲を", "何度も聴いちゃうの?"],
                "subtitle": "イヤーワームの科学",
                "tagline": "98%の人が経験！脳が勝手にリピートする理由",
            },
        },
        "cleaning": {
            "title": "洗剤vs激落ちくんの科学",
            "video_title": "【ゆっくり解説】洗剤vs激落ちくん、科学的にどっちが強い？化学洗浄vs物理洗浄の科学",
            "prefix": "cleaning",
            "short": CLEANING_SHORT,
            "full": CLEANING_FULL,
            "style": "yukkuri",
            "thumb_info": {
                "hook_lines": ["洗剤vs激落ちくん", "どっちが強い？"],
                "subtitle": "化学洗浄vs物理洗浄",
                "tagline": "科学的に正しい掃除法を徹底比較！",
            },
        },
        "cat_cucumber": {
            "title": "なぜ猫はキュウリに驚くのか",
            "video_title": "【ゆっくり解説】なぜ猫はキュウリで飛び上がる？億再生バズ動画の裏にある脳科学と進化の秘密",
            "prefix": "cat_cucumber",
            "short": CAT_CUCUMBER_SHORT,
            "full": CAT_CUCUMBER_FULL,
            "style": "yukkuri",
            "thumb_info": {
                "hook_lines": ["なぜ猫は", "キュウリで飛ぶ！？"],
                "subtitle": "ヘビ検出モジュール×驚愕反射",
                "tagline": "億再生バズ動画の裏にある脳科学の真実",
            },
        },
        "queue": {
            "title": "なぜ人は行列に並ぶのか",
            "video_title": "なぜディズニーで2時間並べるのに病院の30分が耐えられないのか【行動経済学×神経科学】",
            "prefix": "queue",
            "short": QUEUE_MONO_SHORT,
            "full": QUEUE_MONO_FULL,
            "style": "monologue",
            "thumb_info": {
                "hook_lines": ["行列に並ぶ", "科学的な理由"],
                "subtitle": "行動経済学×神経科学",
                "tagline": "なぜディズニーの2時間は平気なのに病院の30分は地獄なのか",
            },
        },
    }

    sc = SCENARIOS.get(request.scenario)
    if not sc:
        raise HTTPException(status_code=400,
                            detail=f"Unknown scenario: {request.scenario}. "
                                   f"Available: {', '.join(SCENARIOS.keys())}")

    # Determine background path
    bg = request.bg_path
    if bg is None:
        for candidate in [
            ASSETS_DIR / "backgrounds" / "ocean_waves.mp4",
            ASSETS_DIR / "bg" / "ocean_waves.mp4",
        ]:
            if candidate.exists():
                bg = str(candidate)
                break

    # Resolve style
    resolved_style = request.style or sc.get("style", "yukkuri")

    job_id = str(uuid.uuid4())[:8]
    video_jobs[job_id] = {
        "status": "starting",
        "scenario": request.scenario,
        "style": resolved_style,
        "gen_type": request.gen_type,
        "bg_type": request.bg_type,
    }

    thread = threading.Thread(target=_run_video_generation,
                              args=(job_id, sc, bg, request.output_dir, request.gen_type, request.bg_type,
                                    request.speed, request.target_duration, resolved_style,
                                    request.use_illustrations))
    thread.start()

    return {"job_id": job_id, "status": "started", "gen_type": request.gen_type, "style": resolved_style,
            "bg_type": request.bg_type, "title": sc["title"]}


@app.get("/generate-video/{job_id}")
async def get_video_job(job_id: str):
    """Check video generation job status."""
    if job_id not in video_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return video_jobs[job_id]


class MoveRequest(BaseModel):
    path: str


@app.post("/setup/move-to")
async def move_app_to(request: MoveRequest):
    """Copy the entire app to a new location (e.g. ~/Developer/)."""
    import shutil
    target = Path(request.path).expanduser()
    target.mkdir(parents=True, exist_ok=True)

    # Current app location
    app_dir = Path(__file__).parent.parent  # auto-yukkuri-source/
    copied = []
    for item in app_dir.iterdir():
        src = item
        dst = target / item.name
        try:
            if src.is_dir():
                if dst.exists():
                    shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
                else:
                    shutil.copytree(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
            copied.append(item.name)
        except Exception as e:
            copied.append(f"{item.name} (error: {e})")

    return {"status": "ok", "moved_to": str(target), "copied": copied}


@app.get("/list-files")
async def list_files(path: str):
    """List files in a directory with sizes."""
    import os
    p = Path(path).expanduser()
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not p.is_dir():
        size = os.path.getsize(str(p))
        return {"path": str(p), "type": "file", "size_mb": round(size / 1024 / 1024, 2)}
    files = []
    for item in sorted(p.iterdir()):
        size = os.path.getsize(str(item)) if item.is_file() else 0
        files.append({
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
            "size_mb": round(size / 1024 / 1024, 2) if item.is_file() else None,
        })
    return {"path": str(p), "files": files}


from fastapi.responses import FileResponse

@app.get("/download-file")
async def download_file(path: str):
    """Serve a file for download."""
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return FileResponse(str(p), filename=p.name)


# ============================================================
# YouTube Upload endpoints
# ============================================================
try:
    from pipeline.youtube_uploader import (
        upload_video, upload_generated_videos, check_auth_status,
        get_authenticated_service, list_youtube_channels,
        add_channel, remove_channel, update_channel_config,
        CLIENT_SECRET_FILE, CREDENTIALS_DIR,
    )
    HAS_YT_MODULE = True
except ImportError:
    HAS_YT_MODULE = False


class YouTubeUploadRequest(BaseModel):
    output_dir: str
    prefix: str
    scheduled_at: Optional[str] = None
    short_scheduled_at: Optional[str] = None
    upload_main: bool = True
    upload_short: bool = True
    channel_id: Optional[str] = None  # ブランドアカウント指定 (UC...)
    auth_channel_id: Optional[str] = None  # 内部チャンネルID (per-channel OAuth)


class AddChannelRequest(BaseModel):
    channel_id: str  # UC... で始まるチャンネルID
    custom_tags: Optional[List[str]] = None
    custom_category: Optional[str] = None


class UpdateChannelRequest(BaseModel):
    custom_tags: Optional[List[str]] = None
    custom_category: Optional[str] = None


youtube_upload_jobs: Dict[str, Dict] = {}


def _run_youtube_upload(job_id: str, req: dict):
    try:
        youtube_upload_jobs[job_id]["status"] = "uploading"
        results = upload_generated_videos(
            output_dir=req["output_dir"],
            prefix=req["prefix"],
            scheduled_at=req.get("scheduled_at"),
            short_scheduled_at=req.get("short_scheduled_at"),
            upload_main=req.get("upload_main", True),
            upload_short=req.get("upload_short", True),
            channel_id=req.get("channel_id"),
            auth_channel_id=req.get("auth_channel_id"),
        )
        youtube_upload_jobs[job_id]["status"] = "done"
        youtube_upload_jobs[job_id]["results"] = results
    except Exception as e:
        youtube_upload_jobs[job_id]["status"] = "error"
        youtube_upload_jobs[job_id]["error"] = str(e)


@app.post("/youtube/upload")
async def youtube_upload(request: YouTubeUploadRequest):
    if not HAS_YT_MODULE:
        raise HTTPException(status_code=500, detail="YouTube module not installed")

    job_id = str(uuid.uuid4())[:8]
    youtube_upload_jobs[job_id] = {"status": "starting", "request": request.dict()}

    thread = threading.Thread(target=_run_youtube_upload, args=(job_id, request.dict()))
    thread.start()
    return {"job_id": job_id, "status": "started"}


@app.get("/youtube/upload/{job_id}")
async def youtube_upload_status(job_id: str):
    if job_id not in youtube_upload_jobs:
        raise HTTPException(status_code=404, detail="Upload job not found")
    return youtube_upload_jobs[job_id]


@app.get("/youtube/auth-status")
async def youtube_auth_status():
    if not HAS_YT_MODULE:
        return {"has_module": False, "error": "YouTube module not installed"}
    try:
        status = check_auth_status()
        status["has_module"] = True
        return status
    except Exception as e:
        return {"has_module": True, "error": str(e)}


@app.post("/youtube/auth")
async def youtube_auth_start():
    if not HAS_YT_MODULE:
        raise HTTPException(status_code=500, detail="YouTube module not installed")
    try:
        get_authenticated_service()
        status = check_auth_status()
        return {"status": "authenticated", "channels": status.get("channels", [])}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/youtube/channels")
async def youtube_channels():
    """List all accessible YouTube channels (including brand accounts)."""
    if not HAS_YT_MODULE:
        raise HTTPException(status_code=500, detail="YouTube module not installed")
    try:
        return {"channels": list_youtube_channels()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/youtube/channels")
async def youtube_add_channel(request: AddChannelRequest):
    """Register a new channel (brand account) by ID."""
    if not HAS_YT_MODULE:
        raise HTTPException(status_code=500, detail="YouTube module not installed")
    try:
        ch = add_channel(request.channel_id, request.custom_tags, request.custom_category)
        return {"status": "added", "channel": ch}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/youtube/channels/{channel_id}")
async def youtube_remove_channel(channel_id: str):
    """Remove a registered channel."""
    if not HAS_YT_MODULE:
        raise HTTPException(status_code=500, detail="YouTube module not installed")
    try:
        remove_channel(channel_id)
        return {"status": "removed", "channel_id": channel_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/youtube/channels/{channel_id}")
async def youtube_update_channel(channel_id: str, request: UpdateChannelRequest):
    """Update channel-specific settings (default tags, category)."""
    if not HAS_YT_MODULE:
        raise HTTPException(status_code=500, detail="YouTube module not installed")
    try:
        ch = update_channel_config(channel_id, request.custom_tags, request.custom_category)
        return {"status": "updated", "channel": ch}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# API Key Settings (OpenAI, etc.)
# ============================================================
import pipeline.video_generator as _vg

_SETTINGS_FILE = Path(__file__).parent / "pipeline" / "credentials" / "api_settings.json"


def _load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_settings(data: dict):
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_openai_key(key: str):
    """Apply OpenAI API key to both os.environ and video_generator module."""
    import os
    os.environ["OPENAI_API_KEY"] = key
    _vg.OPENAI_API_KEY = key


class APISettingsRequest(BaseModel):
    openai_api_key: Optional[str] = None
    voicevox_url: Optional[str] = None


@app.get("/settings/api")
async def get_api_settings():
    """Get current API settings (keys are masked)."""
    settings = _load_settings()
    result = {}
    # OpenAI
    openai_key = settings.get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        result["openai_api_key_set"] = True
        result["openai_api_key_preview"] = openai_key[:7] + "..." + openai_key[-4:] if len(openai_key) > 12 else "***"
    else:
        result["openai_api_key_set"] = False
        result["openai_api_key_preview"] = ""
    # VOICEVOX
    result["voicevox_url"] = settings.get("voicevox_url", _vg.VOICEVOX_URL)
    # Test VOICEVOX connectivity
    result["voicevox_connected"] = _vg.check_voicevox()
    return result


@app.post("/settings/api")
async def update_api_settings(request: APISettingsRequest):
    """Update API settings. Keys are persisted to credentials/api_settings.json."""
    settings = _load_settings()
    updated = []

    if request.openai_api_key is not None:
        settings["openai_api_key"] = request.openai_api_key
        _apply_openai_key(request.openai_api_key)
        updated.append("openai_api_key")

    if request.voicevox_url is not None:
        settings["voicevox_url"] = request.voicevox_url
        _vg.VOICEVOX_URL = request.voicevox_url
        updated.append("voicevox_url")

    _save_settings(settings)
    return {"status": "ok", "updated": updated}


@app.get("/api-usage")
async def api_usage_summary():
    """OpenAI API使用量サマリー（累計トークン数・推定費用・日別/チャンネル別内訳）"""
    try:
        from pipeline import api_usage
        return api_usage.get_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Usage tracker error: {e}")


@app.post("/api-usage/reset")
async def api_usage_reset():
    """API使用量ログをリセット（admin）"""
    try:
        from pipeline import api_usage
        api_usage.reset_usage()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/settings/api/test-openai")
async def test_openai_key():
    """Test if the current OpenAI API key works."""
    key = _vg.OPENAI_API_KEY
    if not key:
        return {"ok": False, "error": "APIキーが設定されていません"}
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "message": "接続成功"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# Multi-Channel Endpoints
# ============================================================

@app.get("/channels")
async def list_channels():
    """全チャンネル一覧を返す"""
    if not channel_manager:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    return {
        "channels": [ch.to_dict() for ch in channel_manager.list_channels()]
    }


@app.get("/channels/{channel_id}")
async def get_channel(channel_id: str):
    """チャンネル詳細を返す"""
    if not channel_manager:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    ch = channel_manager.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return ch.to_dict()


class CreateChannelRequest(BaseModel):
    id: str
    name: str
    concept: str
    style: str = "yukkuri"
    characters: Dict = {}
    thumbnail_template: Dict = {}
    defaults: Dict = {}
    content_policy: Dict = {}
    theme_seeds: List[Dict] = []


@app.post("/channels")
async def create_channel(request: CreateChannelRequest):
    """新チャンネルを作成"""
    if not channel_manager:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    if channel_manager.get(request.id):
        raise HTTPException(status_code=400, detail=f"Channel already exists: {request.id}")
    profile = channel_manager.add_channel(request.dict())
    return {"status": "created", "channel": profile.to_dict()}


@app.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str):
    """チャンネルを削除"""
    if not channel_manager:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    if channel_manager.remove_channel(channel_id):
        return {"status": "removed", "channel_id": channel_id}
    raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")


class UpdateChannelFormatRequest(BaseModel):
    """チャンネル設定の部分更新（video_format含む）"""
    name: Optional[str] = None
    concept: Optional[str] = None
    style: Optional[str] = None
    video_format: Optional[Dict] = None  # 部分更新: {"layout": {"text_font_size": 44}}
    youtube_channel_id: Optional[str] = None  # YouTubeチャンネルID紐付け


@app.put("/channels/{channel_id}")
async def update_channel(channel_id: str, request: UpdateChannelFormatRequest):
    """チャンネル設定を更新（フォーマット・YouTube紐付け含む）"""
    if not channel_manager:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    updates = {k: v for k, v in request.dict().items() if v is not None}
    # youtube_channel_id → video_format.youtube.channel_id にもマッピング
    if "youtube_channel_id" in updates and updates["youtube_channel_id"]:
        if "video_format" not in updates:
            updates["video_format"] = {}
        if "youtube" not in updates["video_format"]:
            updates["video_format"]["youtube"] = {}
        updates["video_format"]["youtube"]["channel_id"] = updates["youtube_channel_id"]
    ch = channel_manager.update_channel(channel_id, updates)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return {"status": "updated", "channel": ch.to_dict()}


@app.put("/channels/{channel_id}/format")
async def update_channel_format(channel_id: str, format_update: Dict):
    """ビデオフォーマットのみ部分更新"""
    if not channel_manager:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    ch = channel_manager.update_channel(channel_id, {"video_format": format_update})
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return {"status": "updated", "video_format": ch.video_format.to_dict()}


@app.put("/channels/{channel_id}/youtube-link")
async def link_youtube_channel(channel_id: str, youtube_channel_id: str, playlist_id: Optional[str] = None,
                                upload_schedule: Optional[str] = None):
    """YouTubeチャンネルを紐付け"""
    if not channel_manager:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    vf_update = {"youtube": {"channel_id": youtube_channel_id}}
    if playlist_id:
        vf_update["youtube"]["playlist_id"] = playlist_id
    if upload_schedule:
        vf_update["youtube"]["upload_schedule"] = upload_schedule
    ch = channel_manager.update_channel(channel_id, {
        "youtube_channel_id": youtube_channel_id,
        "video_format": vf_update,
    })
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return {"status": "linked", "channel_id": channel_id, "youtube_channel_id": youtube_channel_id}


@app.put("/channels/{channel_id}/analytics")
async def update_channel_analytics(channel_id: str, enabled: bool = True,
                                    auto_adjust: bool = False,
                                    min_ctr: Optional[float] = None,
                                    min_retention: Optional[float] = None,
                                    min_views_7d: Optional[int] = None):
    """アナリティクス連携設定"""
    if not channel_manager:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    analytics_update = {"enabled": enabled, "auto_adjust": auto_adjust}
    thresholds = {}
    if min_ctr is not None:
        thresholds["min_ctr"] = min_ctr
    if min_retention is not None:
        thresholds["min_retention"] = min_retention
    if min_views_7d is not None:
        thresholds["min_views_7d"] = min_views_7d
    if thresholds:
        analytics_update["performance_threshold"] = thresholds
    ch = channel_manager.update_channel(channel_id, {"video_format": {"analytics": analytics_update}})
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return {"status": "updated", "analytics": ch.video_format.analytics.__dict__}


# ============================================================
# Auto Scenario Endpoints
# ============================================================

class GenerateScenarioRequest(BaseModel):
    channel_id: str
    theme_title: Optional[str] = None  # None = ランダム選択
    theme_angle: Optional[str] = None
    target_duration: Optional[int] = None
    save: bool = True  # 自動保存


@app.post("/scenarios/generate")
async def generate_scenario(request: GenerateScenarioRequest):
    """GPTでシナリオを自動生成"""
    if not channel_manager or not scenario_generator:
        raise HTTPException(status_code=500, detail="Not initialized")

    ch = channel_manager.get(request.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {request.channel_id}")

    if not scenario_generator.api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key not set")

    theme_override = None
    if request.theme_title:
        theme_override = {"title": request.theme_title, "angle": request.theme_angle or "自由"}

    try:
        result = scenario_generator.generate(
            ch,
            theme_override=theme_override,
            target_duration=request.target_duration,
        )
        saved_path = None
        if request.save:
            saved_path = scenario_generator.save_scenario(result)
        return {
            "status": "ok",
            "scenario": result,
            "saved_path": saved_path,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BatchScenarioRequest(BaseModel):
    channel_id: str
    count: int = 3
    exclude_themes: Optional[List[str]] = None


@app.post("/scenarios/generate-batch")
async def generate_batch_scenarios(request: BatchScenarioRequest):
    """複数シナリオを一括生成"""
    if not channel_manager or not scenario_generator:
        raise HTTPException(status_code=500, detail="Not initialized")
    ch = channel_manager.get(request.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {request.channel_id}")

    try:
        results = scenario_generator.generate_batch(ch, request.count, request.exclude_themes)
        saved_paths = []
        for r in results:
            try:
                p = scenario_generator.save_scenario(r)
                saved_paths.append(p)
            except Exception:
                saved_paths.append(None)
        return {"status": "ok", "count": len(results), "scenarios": results, "saved_paths": saved_paths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scenarios/suggest-themes")
async def suggest_themes(channel_id: str, count: int = 5):
    """新テーマ候補をGPTに提案させる"""
    if not channel_manager or not scenario_generator:
        raise HTTPException(status_code=500, detail="Not initialized")
    ch = channel_manager.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    try:
        themes = scenario_generator.suggest_themes(ch, count)
        return {"status": "ok", "themes": themes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scenarios/{channel_id}")
async def list_saved_scenarios(channel_id: str):
    """保存済みシナリオ一覧"""
    base = Path(__file__).parent.parent / "data" / "scenarios" / channel_id
    if not base.exists():
        return {"channel_id": channel_id, "scenarios": []}
    scenarios = []
    for f in sorted(base.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            scenarios.append({
                "file": f.name,
                "title": data.get("title", f.stem),
                "theme": data.get("theme", {}),
                "style": data.get("style", "yukkuri"),
                "has_short": bool(data.get("short_scenario")),
                "has_full": bool(data.get("full_scenario")),
            })
        except Exception:
            pass
    return {"channel_id": channel_id, "scenarios": scenarios}


# ============================================================
# Job Queue Endpoints
# ============================================================

class QueueJobRequest(BaseModel):
    channel_id: str
    scenario_file: Optional[str] = None  # data/scenarios/<ch>/<file>.json
    scenario_data: Optional[Dict] = None  # 直接指定
    priority: int = 5
    gen_type: str = "both"


@app.post("/queue/submit")
async def queue_submit(request: QueueJobRequest):
    """ジョブをキューに投入"""
    if not job_queue:
        raise HTTPException(status_code=500, detail="Job queue not initialized")

    # シナリオデータ解決
    scenario_data = request.scenario_data
    if not scenario_data and request.scenario_file:
        ch = channel_manager.get(request.channel_id) if channel_manager else None
        file_path = Path(__file__).parent.parent / "data" / "scenarios" / request.channel_id / request.scenario_file
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Scenario file not found: {request.scenario_file}")
        scenario_data = json.loads(file_path.read_text(encoding="utf-8"))

    if not scenario_data:
        raise HTTPException(status_code=400, detail="scenario_data or scenario_file required")

    job_id = job_queue.submit(
        channel_id=request.channel_id,
        scenario_data=scenario_data,
        priority=request.priority,
        gen_type=request.gen_type,
    )
    return {"job_id": job_id, "status": "queued"}


@app.get("/queue/jobs")
async def queue_list_jobs(channel_id: Optional[str] = None, status: Optional[str] = None):
    """ジョブ一覧"""
    if not job_queue:
        raise HTTPException(status_code=500, detail="Job queue not initialized")
    return {"jobs": job_queue.list_jobs(channel_id=channel_id, status=status)}


@app.get("/queue/jobs/{job_id}")
async def queue_get_job(job_id: str):
    """ジョブ状態取得"""
    if not job_queue:
        raise HTTPException(status_code=500, detail="Job queue not initialized")
    status = job_queue.get_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@app.post("/queue/jobs/{job_id}/cancel")
async def queue_cancel_job(job_id: str):
    """ジョブキャンセル（pending・running 両対応）"""
    if not job_queue:
        raise HTTPException(status_code=500, detail="Job queue not initialized")
    j = job_queue.get_status(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    if j.get("status") in ("completed", "failed", "cancelled"):
        return {"status": j.get("status"), "noop": True}
    job_queue.cancel(job_id)
    return {"status": "cancelled"}


@app.get("/queue/stats")
async def queue_stats():
    """キュー統計"""
    if not job_queue:
        raise HTTPException(status_code=500, detail="Job queue not initialized")
    return job_queue.get_stats()


# ============================================================
# Factory: 全自動パイプライン (generate + queue in one shot)
# ============================================================

class FactoryRunRequest(BaseModel):
    channel_id: str
    count: int = 1  # 生成するシナリオ数
    priority: int = 5
    gen_type: str = "both"
    auto_theme: bool = True  # True=ランダム選択, False=theme_titleを指定
    theme_title: Optional[str] = None
    theme_angle: Optional[str] = None


@app.post("/factory/run")
async def factory_run(request: FactoryRunRequest):
    """
    全自動: シナリオ生成 → ジョブキュー投入 を一気に実行。
    チャンネルのtheme_seedsからランダムに選んでシナリオ生成→動画生成キューへ。
    """
    if not channel_manager or not scenario_generator or not job_queue:
        raise HTTPException(status_code=500, detail="Factory not fully initialized")

    ch = channel_manager.get(request.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {request.channel_id}")

    if not scenario_generator.api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key not set")

    results = []
    for i in range(request.count):
        try:
            theme_override = None
            if not request.auto_theme and request.theme_title:
                theme_override = {"title": request.theme_title, "angle": request.theme_angle or "自由"}

            # 1. シナリオ生成 — 未消費の改善フィードバックがあれば GPT に注入
            try:
                from pipeline.analytics.feedback_store import get_pending_for_channel, mark_consumed
                pending_fb = get_pending_for_channel(request.channel_id)
            except Exception:
                pending_fb = []
                mark_consumed = None  # type: ignore
            scenario = scenario_generator.generate(
                ch,
                theme_override=theme_override,
                improvement_feedback=pending_fb or None,
            )
            scenario_generator.save_scenario(scenario)

            # 2. ジョブキュー投入
            job_id = job_queue.submit(
                channel_id=request.channel_id,
                scenario_data=scenario,
                priority=request.priority,
                gen_type=request.gen_type,
            )
            # 適用したフィードバックは consumed にして同じ動画 ID を再度載せない
            if pending_fb and scenario.get("applied_feedback") and mark_consumed:
                try:
                    mark_consumed(scenario["applied_feedback"], consumed_by_job_id=job_id)
                except Exception:
                    pass
            results.append({"index": i, "title": scenario["title"], "job_id": job_id, "status": "queued"})
        except Exception as e:
            results.append({"index": i, "error": str(e), "status": "failed"})

    return {"status": "ok", "channel_id": request.channel_id, "results": results}


@app.post("/factory/run-all")
async def factory_run_all(count_per_channel: int = 1, priority: int = 5, gen_type: str = "both"):
    """
    全チャンネルに対して自動生成を実行。
    各チャンネルからcount_per_channel本ずつシナリオ生成→キュー投入。
    """
    if not channel_manager or not scenario_generator or not job_queue:
        raise HTTPException(status_code=500, detail="Factory not fully initialized")

    if not scenario_generator.api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key not set")

    all_results = {}
    for ch in channel_manager.list_channels():
        ch_results = []
        for i in range(count_per_channel):
            try:
                try:
                    from pipeline.analytics.feedback_store import get_pending_for_channel, mark_consumed
                    pending_fb = get_pending_for_channel(ch.id)
                except Exception:
                    pending_fb = []
                    mark_consumed = None  # type: ignore
                scenario = scenario_generator.generate(
                    ch, improvement_feedback=pending_fb or None
                )
                scenario_generator.save_scenario(scenario)
                job_id = job_queue.submit(
                    channel_id=ch.id,
                    scenario_data=scenario,
                    priority=priority,
                    gen_type=gen_type,
                )
                if pending_fb and scenario.get("applied_feedback") and mark_consumed:
                    try:
                        mark_consumed(scenario["applied_feedback"], consumed_by_job_id=job_id)
                    except Exception:
                        pass
                ch_results.append({"title": scenario["title"], "job_id": job_id})
            except Exception as e:
                ch_results.append({"error": str(e)})
        all_results[ch.id] = ch_results

    total_jobs = sum(len(v) for v in all_results.values())
    return {"status": "ok", "total_jobs": total_jobs, "by_channel": all_results}


# ============================================================
# Phase C: Trends + AB Testing
# ============================================================

@app.get("/api/trends/{channel_id}")
async def api_get_trends(channel_id: str, count: int = 5):
    """現在のトレンドと、そこから提案される旬のテーマを返す。

    - Google Trends（pytrends）+ YouTube 急上昇（教育/科学）+ チャンネルとの関連語
    - チャンネルが見つかれば、AI 提案テーマ（`/scenarios/suggest-themes` 相当）も
      include_trends=True で同時に取得して `themes` フィールドに付ける。
    """
    try:
        from pipeline.trend_fetcher import fetch_combined_trends
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"trend_fetcher import failed: {e}")

    ch = channel_manager.get(channel_id) if channel_manager else None
    combined = fetch_combined_trends(ch)

    themes: List[Dict] = []
    if ch and scenario_generator and scenario_generator.api_key:
        try:
            themes = scenario_generator.suggest_themes(ch, count=count, include_trends=True) or []
        except Exception as e:
            print(f"⚠️ suggest_themes failed in /api/trends: {e}")
            themes = []

    return {
        "status": "ok",
        "channel_id": channel_id,
        "trends": combined,
        "themes": themes,
    }


class ABTestGenerateRequest(BaseModel):
    theme_title: str
    theme_angle: Optional[str] = ""
    channel_id: Optional[str] = None
    scenario_summary: Optional[str] = None


@app.post("/api/ab-test/generate")
async def api_ab_test_generate(request: ABTestGenerateRequest):
    """タイトル・サムネキャッチコピーを 3 パターン生成して CTR スコアを付ける。"""
    try:
        from pipeline.ab_test_generator import generate_ab_test
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ab_test_generator import failed: {e}")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        # クラッシュさせず、フォールバック生成（スコア 0）を返す
        result = generate_ab_test(
            request.theme_title,
            request.theme_angle or "",
            channel_id=request.channel_id,
            scenario_summary=request.scenario_summary,
        )
        return {"status": "ok_fallback", "note": "OPENAI_API_KEY not set — using fallback variants", "ab_test": result}
    try:
        result = generate_ab_test(
            request.theme_title,
            request.theme_angle or "",
            channel_id=request.channel_id,
            scenario_summary=request.scenario_summary,
        )
        return {"status": "ok", "ab_test": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ab-test/{test_id}")
async def api_ab_test_get(test_id: str):
    """過去の AB テスト結果を取得。"""
    try:
        from pipeline.ab_test_generator import load_ab_test
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ab_test_generator import failed: {e}")
    data = load_ab_test(test_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"AB test not found: {test_id}")
    return data


@app.get("/api/ab-test")
async def api_ab_test_list(channel_id: Optional[str] = None, limit: int = 50):
    """AB テスト一覧（channel_id でフィルタ可）。"""
    try:
        from pipeline.ab_test_generator import list_ab_tests
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ab_test_generator import failed: {e}")
    return {"status": "ok", "items": list_ab_tests(channel_id=channel_id, limit=limit)}


@app.get("/health")
async def health():
    """Health check endpoint."""
    channels_count = len(channel_manager.list_ids()) if channel_manager else 0
    queue_running = job_queue._running if job_queue else False
    return {
        "status": "healthy",
        "channels": channels_count,
        "queue_running": queue_running,
    }


@app.on_event("startup")
async def startup_event():
    """Auto-start: initialize multi-channel system."""
    global channel_manager, scenario_generator, job_queue

    # Restore saved API keys
    try:
        settings = _load_settings()
        if settings.get("openai_api_key"):
            _apply_openai_key(settings["openai_api_key"])
            print("🔑 OpenAI API key loaded from settings")
        if settings.get("voicevox_url"):
            _vg.VOICEVOX_URL = settings["voicevox_url"]
    except Exception:
        pass

    # Initialize Channel Manager
    channel_manager = ChannelManager()

    # Initialize Scenario Generator
    scenario_generator = ScenarioGenerator()

    # Initialize Job Queue
    job_queue = JobQueue(
        max_workers=2,
        on_job_complete=api_phase4.on_generation_complete,
        on_job_failed=lambda j: api_phase4.notify_event(
            "error", f"❌ 生成失敗 [{j.title}]: {j.error}"
        ),
    )
    job_queue.set_pipeline(generate_all, channel_manager)
    job_queue.start()

    # Phase 1 API へ依存を渡す
    api_phase1.configure(
        channel_manager=channel_manager,
        scenario_generator=scenario_generator,
        job_queue=job_queue,
    )

    # Phase 4: スケジューラ起動 + 通知/テンプレートDBをセットアップ
    try:
        api_phase4.setup_on_startup()
    except Exception as e:
        print(f"⚠️ Phase 4 startup failed: {e}")

    # Channel Autopilot: 既存チャンネルの自動投稿ジョブを復元
    try:
        api_channel_autopilot.restore_all()
    except Exception as e:
        print(f"⚠️ Autopilot restore failed: {e}")

    print()
    print("🏭 YouTube Factory ready!")
    print(f"   📺 Channels: {', '.join(channel_manager.list_ids())}")
    print("   POST /factory/run        → 全自動（シナリオ生成→動画生成）")
    print("   POST /scenarios/generate  → シナリオ生成のみ")
    print("   POST /queue/submit        → ジョブキュー投入")
    print("   GET  /channels            → チャンネル一覧")
    print("   GET  /queue/stats         → キュー統計")
    print("   /api/schedules            → スケジュール投稿 (Phase 4)")
    print("   /api/templates            → 動画テンプレート (Phase 4)")
    print("   /api/history              → 生成履歴・コスト (Phase 4)")
    print("   /api/notifications/test   → 通知テスト (Phase 4)")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        api_phase4.shutdown_scheduler()
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
