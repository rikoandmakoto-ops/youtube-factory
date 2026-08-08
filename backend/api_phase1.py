"""
YouTube Factory — Phase 1 API

新フロントエンド（Next.js 14）が叩く `/api/*` エンドポイント群。
既存の channel_manager / scenario_generator / job_queue を再利用しつつ、
- パスワード認証（bcrypt + JWT）
- レート制限（IPあたり5回/分）
- システムステータス
- チャンネル一覧 / 詳細
- 動画生成ジョブ開始 / 進捗
- AIテーマ提案
を提供する。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, Field

from pipeline.scheduler.job_queue import Job, JobStatus

# ── 依存（main.py から後付け）──
_state: Dict[str, Any] = {
    "channel_manager": None,
    "scenario_generator": None,
    "job_queue": None,
}


def configure(*, channel_manager, scenario_generator, job_queue) -> None:
    """main.py の startup で呼ぶ。グローバル参照を差し込む。"""
    _state["channel_manager"] = channel_manager
    _state["scenario_generator"] = scenario_generator
    _state["job_queue"] = job_queue


# =====================================================================
# 認証
# =====================================================================

# bcrypt と PyJWT は遅延 import（依存未インストール時の起動失敗を避ける）
try:
    import bcrypt  # type: ignore
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

try:
    import jwt  # type: ignore  # PyJWT
    HAS_JWT = True
except ImportError:
    HAS_JWT = False


JWT_ALG = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _jwt_secret() -> str:
    """JWT署名用シークレット。.env の JWT_SECRET、なければ APP_PASSWORD_HASH の派生。"""
    s = os.environ.get("JWT_SECRET", "").strip()
    if s:
        return s
    # フォールバック: ハッシュからキー導出（本番では明示設定推奨）
    h = os.environ.get("APP_PASSWORD_HASH", "") or os.environ.get("APP_PASSWORD", "")
    return f"ytf-{h}-fallback" if h else "ytf-development-fallback-secret"


def _verify_password(plain: str) -> bool:
    """環境変数のパスワード設定と照合する。

    - APP_PASSWORD_HASH（bcrypt の $2... 形式）が優先
    - 未設定時は APP_PASSWORD（平文）と単純比較（開発用フォールバック）
    """
    hashed = os.environ.get("APP_PASSWORD_HASH", "").strip()
    if hashed:
        if not HAS_BCRYPT:
            raise HTTPException(
                status_code=500,
                detail="bcrypt がインストールされていません。`pip install bcrypt`",
            )
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    plaintext = os.environ.get("APP_PASSWORD", "").strip()
    if plaintext:
        # constant-time compare
        import hmac
        return hmac.compare_digest(plain, plaintext)

    raise HTTPException(
        status_code=500,
        detail=(
            "APP_PASSWORD_HASH も APP_PASSWORD も .env に未設定です。"
            "backend/.env に設定してください。"
        ),
    )


def _create_token(subject: str = "user") -> tuple[str, int]:
    if not HAS_JWT:
        raise HTTPException(
            status_code=500,
            detail="PyJWT がインストールされていません。`pip install PyJWT`",
        )
    now = int(time.time())
    exp = now + JWT_TTL_SECONDS
    payload = {"sub": subject, "iat": now, "exp": exp}
    token = jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALG)
    return token, JWT_TTL_SECONDS


def _verify_token(token: str) -> Dict[str, Any]:
    if not HAS_JWT:
        raise HTTPException(status_code=500, detail="PyJWT not installed")
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALG])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── レート制限（ログイン: 5回/分/IP）──
_login_attempts: Dict[str, List[float]] = {}
_LOGIN_WINDOW = 60.0
_LOGIN_LIMIT = 5


def _check_login_rate(ip: str) -> None:
    now = time.time()
    bucket = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW]
    if len(bucket) >= _LOGIN_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Retry in {int(_LOGIN_WINDOW)}s",
        )
    bucket.append(now)
    _login_attempts[ip] = bucket


def require_session(
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """セッショントークン必須エンドポイント用 Depends."""
    scheme, token = get_authorization_scheme_param(authorization or "")
    if not token or scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    return _verify_token(token)


# =====================================================================
# Router
# =====================================================================

router = APIRouter(prefix="/api", tags=["phase1"])


# ── スキーマ ──
class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    token: str
    expires_in: int


class SystemStatusResponse(BaseModel):
    voicevox: Dict[str, Any]
    gpt: Dict[str, Any]
    disk: Dict[str, Any]


class GenerateRequest(BaseModel):
    channel_id: str
    theme: str = Field(min_length=1, max_length=300)
    duration_minutes: int = Field(ge=1, le=60, default=12)
    generate_short: bool = True
    generate_thumbnail: bool = True
    copy_to_icloud: bool = False
    # 0..1 — overrides channel's audio.bgm_volume when provided.
    bgm_volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class GenerateResponse(BaseModel):
    job_id: str
    status: str


class ThemeSuggestRequest(BaseModel):
    channel_id: str
    count: int = Field(ge=1, le=10, default=5)


# =====================================================================
# 認証エンドポイント
# =====================================================================

@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request) -> LoginResponse:
    """パスワードログイン。成功時は JWT を返す。"""
    ip = request.client.host if request.client else "unknown"
    _check_login_rate(ip)

    if not _verify_password(req.password):
        raise HTTPException(status_code=401, detail="Incorrect password")

    token, ttl = _create_token()
    return LoginResponse(token=token, expires_in=ttl)


@router.get("/auth/me")
async def me(session: Dict[str, Any] = Depends(require_session)) -> Dict[str, Any]:
    return {"sub": session.get("sub"), "exp": session.get("exp")}


# =====================================================================
# システムステータス
# =====================================================================

def _check_voicevox(url: str, timeout: float = 1.5) -> bool:
    try:
        urllib.request.urlopen(f"{url.rstrip('/')}/speakers", timeout=timeout)
        return True
    except Exception:
        return False


def _check_openai(api_key: str, timeout: float = 3.0) -> bool:
    if not api_key:
        return False
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


# ヘルスチェックは VOICEVOX と OpenAI への実 HTTP 往復なので、毎リクエスト
# 叩くとダッシュボードの TTFB に直接乗る。数十秒は変わらない情報なのでキャッシュ。
_STATUS_TTL_SECONDS = 30.0
_status_cache: Dict[str, tuple] = {}


@router.get("/system/status", response_model=SystemStatusResponse)
async def system_status(_=Depends(require_session)) -> SystemStatusResponse:
    """VOICEVOX / GPT / ディスク容量のヘルスチェック。"""
    cached = _status_cache.get("v")
    if cached and time.time() - cached[0] < _STATUS_TTL_SECONDS:
        return cached[1]

    # video_generator から実際の URL/Key を読む
    try:
        import pipeline.video_generator as vg
        vv_url = getattr(vg, "VOICEVOX_URL", "http://localhost:50021")
        openai_key = getattr(vg, "OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    except Exception:
        vv_url = os.environ.get("VOICEVOX_URL", "http://localhost:50021")
        openai_key = os.environ.get("OPENAI_API_KEY", "")

    # どちらも blocking な urlopen。直列に await するとイベントループごと
    # 止まるので、スレッドに逃がして並列に走らせる。
    vv_ok, gpt_ok = await asyncio.gather(
        asyncio.to_thread(_check_voicevox, vv_url),
        asyncio.to_thread(_check_openai, openai_key),
    )

    # ディスク
    disk_path = Path(__file__).parent.parent
    try:
        usage = shutil.disk_usage(str(disk_path))
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
    except Exception:
        free_gb = total_gb = 0.0

    resp = SystemStatusResponse(
        voicevox={"connected": vv_ok, "url": vv_url},
        gpt={"connected": gpt_ok, "configured": bool(openai_key)},
        disk={"free_gb": round(free_gb, 1), "total_gb": round(total_gb, 1)},
    )
    _status_cache["v"] = (time.time(), resp)
    return resp


# =====================================================================
# チャンネル
# =====================================================================

# チャンネルカードのメトリクスは YouTube API 往復が要るため TTL キャッシュする。
# ダッシュボードは force-dynamic SSR で毎回叩かれるので、これが無いと
# 表示のたびに 1 チャンネル 1 往復（未キャッシュ時）が直列に積み上がる。
_METRICS_TTL_SECONDS = 300.0
_metrics_cache: Dict[str, tuple] = {}


def _channel_metrics(channel_id: str) -> Dict[str, int]:
    """チャンネル別のメトリクスを集計。

    YouTube が連携済みなら Analytics の数値を、未連携なら JobQueue ベースの推定を返す。
    結果は `_METRICS_TTL_SECONDS` 秒だけメモリキャッシュする。
    """
    cached = _metrics_cache.get(channel_id)
    if cached and time.time() - cached[0] < _METRICS_TTL_SECONDS:
        return cached[1]
    metrics = _channel_metrics_uncached(channel_id)
    _metrics_cache[channel_id] = (time.time(), metrics)
    return metrics


def _channel_metrics_uncached(channel_id: str) -> Dict[str, int]:
    # 連携済みなら Analytics を使用
    try:
        from pipeline import youtube_oauth as yo
        cm = _state.get("channel_manager")
        ch = cm.get(channel_id) if cm else None
        connected = yo.is_connected_for(channel_id) or yo.is_connected()
        yt_id = ch.youtube_channel_id if ch else None
        if not yt_id and connected:
            # チャンネルプロファイル未設定でも OAuth トークンに紐付いた ID を使う
            try:
                yt_id = yo.get_status_for(channel_id).get("youtube_channel_id")
            except Exception:
                yt_id = None
        if ch and yt_id and connected:
            # 一覧に必要なのは 3 つの数値だけなので、28日推移・人気動画まで取る
            # `_real_analytics` ではなく 1 往復で済む軽量版を使う。
            from api_phase3 import channel_stats_light
            stats = channel_stats_light(channel_id, yt_id)
            if stats:
                return stats
    except Exception:
        pass

    # フォールバック: ジョブ数を動画数とする
    queue = _state.get("job_queue")
    video_count = 0
    if queue is not None:
        try:
            jobs = queue.list_jobs(channel_id=channel_id)
            video_count = sum(1 for j in jobs if j.get("status") == "completed")
        except Exception:
            pass
    return {
        "video_count": video_count,
        "total_views": 0,
        "subscribers": 0,
    }


@router.get("/channels")
async def list_channels(_=Depends(require_session)) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    channels = list(cm.list_channels())
    # メトリクスは 1 チャンネル 1 往復（キャッシュミス時）の blocking IO。
    # 直列だとチャンネル数に比例して TTFB が伸びるうえ、イベントループを
    # 塞いで他のリクエストまで待たせるので to_thread で並列に逃がす。
    results = await asyncio.gather(
        *(asyncio.to_thread(_channel_metrics, ch.id) for ch in channels),
        return_exceptions=True,
    )
    out: List[Dict[str, Any]] = []
    for ch, m in zip(channels, results):
        d = {
            "id": ch.id,
            "name": ch.name,
            "concept": ch.concept,
            "style": ch.style,
        }
        d.update(
            m
            if isinstance(m, dict)
            else {"video_count": 0, "total_views": 0, "subscribers": 0}
        )
        out.append(d)
    return {"channels": out}


@router.get("/channels/{channel_id}")
async def channel_detail(
    channel_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    queue = _state.get("job_queue")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")

    # ジョブから動画リストを構築（公開ステータスがあれば優先）
    videos: List[Dict[str, Any]] = []
    metrics = _channel_metrics(channel_id)

    # 公開ステータス map を取得
    publish_status_map: Dict[str, Dict[str, Any]] = {}
    try:
        from api_phase3 import get_video_statuses_for_channel
        publish_status_map = get_video_statuses_for_channel(channel_id)
    except Exception:
        pass

    if queue is not None:
        try:
            jobs = queue.list_jobs(channel_id=channel_id)
            for j in sorted(
                jobs,
                key=lambda x: x.get("created_at", ""),
                reverse=True,
            ):
                job_id = j.get("id", "")
                pub = publish_status_map.get(job_id, {})
                # 公開ステータスを優先 — 未登録は queue 状態から推定
                if pub.get("status"):
                    ui_status = pub["status"]
                else:
                    ui_status_map = {
                        "completed": "draft",  # 生成完了は下書き扱い（公開操作待ち）
                        "running": "pending",
                        "pending": "pending",
                        "failed": "failed",
                        "cancelled": "failed",
                    }
                    ui_status = ui_status_map.get(j.get("status"), "draft")
                videos.append({
                    "id": job_id,
                    "title": j.get("title", ""),
                    "created_at": (j.get("created_at") or "")[:16].replace("T", " "),
                    "duration": _format_duration(ch.get_target_duration()),
                    "views": 0,
                    "status": ui_status,
                    "thumbnail_url": None,
                    "youtube_url": pub.get("url"),
                    "youtube_video_id": pub.get("video_id"),
                    "scheduled_at": pub.get("scheduled_at"),
                    "result": j.get("result"),
                    "queue_status": j.get("status"),
                })
        except Exception:
            pass

    avg = (
        metrics["total_views"] / metrics["video_count"]
        if metrics["video_count"]
        else 0
    )

    return {
        "id": ch.id,
        "name": ch.name,
        "concept": ch.concept,
        "style": ch.style,
        "youtube_channel_id": ch.youtube_channel_id,
        "publish_settings": ch.get_publish_settings(),
        "videos": videos,
        "metrics": {
            "total_views": metrics["total_views"],
            "subscribers": metrics["subscribers"],
            "video_count": metrics["video_count"],
            "avg_views_per_video": avg,
        },
        **metrics,
    }


def _format_duration(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


# =====================================================================
# 動画生成
# =====================================================================

def _resolve_gen_type(gen_short: bool) -> str:
    """ショート生成の有無を pipeline の gen_type に変換。"""
    return "both" if gen_short else "full"


@router.post("/generate", response_model=GenerateResponse)
async def start_generate(
    req: GenerateRequest, _=Depends(require_session)
) -> GenerateResponse:
    """テーマからシナリオ生成 → 動画ジョブをキューに投入。

    シナリオ生成は GPT-4o の同期呼び出しで 30〜60s 掛かる。これを
    リクエスト中に走らせると Vercel のサーバレス・タイムアウトや
    Safari のタブ・スロットリングでフロント側に "Load failed" が
    出てしまうので、placeholder ジョブをすぐ作って `job_id` を返し、
    シナリオ生成は背景タスクに逃がす。ジョブは status=running /
    progress="シナリオ生成中..." の状態で /api/generate/active に
    最初から見えるので、タブを切り替えても進捗が消えない。
    """
    cm = _state.get("channel_manager")
    sg = _state.get("scenario_generator")
    queue = _state.get("job_queue")
    if not cm or not sg or not queue:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    ch = cm.get(req.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {req.channel_id}")
    # 切り抜きチャンネルは台本生成を行わない（素材は既存の長尺動画）。
    # このまま流すとキャラクター未定義のまま対話用レンダラーに入って落ちる。
    if ch.style == "clip":
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{req.channel_id}' は切り抜きチャンネルです。テーマからの生成は行いません。"
                " POST /api/clips/generate または run_clip_channel.py を使ってください。"
            ),
        )
    if not getattr(sg, "api_key", None):
        raise HTTPException(
            status_code=400,
            detail="OpenAI API キーが設定されていません（/settings/api で設定）",
        )

    target_seconds = max(60, req.duration_minutes * 60)

    # Placeholder ジョブを先に作る。`scenario_data` はあとから差し替える。
    # `_queue.put` は呼ばないのでワーカーは拾わない。フロント向け API
    # （/active, /status）は `_jobs` を見るのでこの時点で進捗が出る。
    job_id = str(uuid.uuid4())[:8]
    placeholder = Job(
        id=job_id,
        channel_id=req.channel_id,
        title=req.theme,
        style="yukkuri",
        scenario_data={
            "_preparing": True,
            "_options": {
                "generate_thumbnail": req.generate_thumbnail,
                "copy_to_icloud": req.copy_to_icloud,
                "duration_minutes": req.duration_minutes,
                "bgm_volume": req.bgm_volume,
            },
        },
        priority=5,
        gen_type=_resolve_gen_type(req.generate_short),
    )
    placeholder.status = JobStatus.RUNNING
    placeholder.started_at = datetime.now().isoformat()
    placeholder.progress = "シナリオ生成中..."
    with queue._lock:
        queue._jobs[job_id] = placeholder

    async def _prepare_scenario() -> None:
        """背景タスク: シナリオを生成してジョブをキューに流し込む。"""
        try:
            # 同期API。スレッドに逃がして event loop をブロックしない。
            scenario = await asyncio.to_thread(
                sg.generate,
                ch,
                theme_override={"title": req.theme, "angle": "ユーザー指定テーマ"},
                target_duration=target_seconds,
            )
            await asyncio.to_thread(sg.save_scenario, scenario)
        except Exception as e:
            with queue._lock:
                j = queue._jobs.get(job_id)
                if j:
                    j.status = JobStatus.FAILED
                    j.error = f"Scenario generation failed: {e}"
                    j.progress = "シナリオ生成に失敗"
                    j.completed_at = datetime.now().isoformat()
            print(f"❌ Scenario prep failed for [{job_id}]: {e}")
            return

        # ユーザーが既に中断していたら enqueue しない。
        with queue._lock:
            j = queue._jobs.get(job_id)
            if not j:
                return
            if j.cancel_requested or j.status == JobStatus.CANCELLED:
                j.status = JobStatus.CANCELLED
                j.completed_at = datetime.now().isoformat()
                j.progress = "中断しました"
                return
            # オプション情報を保ったまま scenario_data を差し替える
            options = j.scenario_data.get("_options") or {}
            j.scenario_data = dict(scenario)
            j.scenario_data["_options"] = options
            j.title = scenario.get("title", j.title)
            # placeholder では style が確定しないので "yukkuri" を仮置きしている。
            # シナリオが出揃ったここで JobQueue.add() と同じ規則で確定させる。
            # 直さないと facts_overlay 等のチャンネルが対話用レンダラーに流れ、
            # シナリオ形式が合わず KeyError で落ちる。
            j.style = scenario.get("style") or ch.style or "yukkuri"
            j.status = JobStatus.PENDING
            j.progress = "順番待ち"
            queue._queue.put((j.priority, job_id))
        print(f"📥 Job queued after scenario prep: [{job_id}] {req.theme}")

    asyncio.create_task(_prepare_scenario())
    return GenerateResponse(job_id=job_id, status="preparing")


def _job_to_status(job: Dict[str, Any]) -> Dict[str, Any]:
    """JobQueue の dict を フロントエンド用 step ベースに変換する。"""
    s = job.get("status", "pending")
    progress_msg = (job.get("progress") or "").lower()

    # ヒューリスティックでステップを推定
    step = 1
    step_label = "シナリオ生成中"
    pct = 5.0

    if s == "pending":
        step, step_label, pct = 1, "順番待ち", 5.0
    elif s == "running":
        if "シナリオ" in progress_msg or "scenario" in progress_msg:
            # POST /api/generate 直後の "シナリオ生成中..." 状態
            step, step_label, pct = 1, "シナリオ生成中", 10.0
        elif "イラスト" in progress_msg or "dall-e" in progress_msg or "illustration" in progress_msg:
            step, step_label, pct = 2, "DALL-E イラスト生成中", 30.0
        elif "tts" in progress_msg or "音声" in progress_msg or "voicevox" in progress_msg:
            step, step_label, pct = 3, "TTS音声生成中", 55.0
        elif "encode" in progress_msg or "moviepy" in progress_msg or "mp4" in progress_msg or "エンコード" in progress_msg:
            step, step_label, pct = 4, "動画エンコード中", 80.0
        elif "出力" in progress_msg or "icloud" in progress_msg:
            step, step_label, pct = 5, "ファイル出力中", 95.0
        else:
            step, step_label, pct = 2, "生成中", 25.0
    elif s == "completed":
        step, step_label, pct = 5, "完了", 100.0
    elif s == "failed":
        step, step_label, pct = 1, "失敗", 0.0
    elif s == "cancelled":
        step, step_label, pct = 1, "キャンセル", 0.0

    return {
        "job_id": job.get("id"),
        "status": s,
        "step": step,
        "step_label": step_label,
        "progress": pct,
        "log": job.get("progress") or step_label,
        "title": job.get("title"),
        "error": job.get("error"),
        "result": job.get("result"),
        "channel_id": job.get("channel_id"),
    }


@router.get("/generate/{job_id}/status")
async def generate_status(
    job_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    queue = _state.get("job_queue")
    if not queue:
        raise HTTPException(status_code=503, detail="Job queue not ready")
    j = queue.get_status(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_status(j)


@router.post("/generate/{job_id}/cancel")
async def cancel_generate(
    job_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    """生成ジョブの中断。

    - pending: 即時 cancelled に切り替え
    - running: cancel_requested フラグを立て、各ステップ間で
      安全に停止する
    - completed/failed/cancelled: そのまま現在の状態を返す（idempotent）
    """
    queue = _state.get("job_queue")
    if not queue:
        raise HTTPException(status_code=503, detail="Job queue not ready")
    j = queue.get_status(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")

    cur = j.get("status")
    if cur in ("completed", "failed", "cancelled"):
        return _job_to_status(j)

    queue.cancel(job_id)
    return _job_to_status(queue.get_status(job_id) or j)


@router.delete("/generate/{job_id}")
async def delete_generate(
    job_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    """RESTful別名: DELETE /api/generate/{job_id} もキャンセル扱い"""
    queue = _state.get("job_queue")
    if not queue:
        raise HTTPException(status_code=503, detail="Job queue not ready")
    j = queue.get_status(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    if j.get("status") in ("completed", "failed", "cancelled"):
        return _job_to_status(j)
    queue.cancel(job_id)
    return _job_to_status(queue.get_status(job_id) or j)


@router.get("/generate/active")
async def list_active_jobs(_=Depends(require_session)) -> Dict[str, Any]:
    queue = _state.get("job_queue")
    if not queue:
        return {"jobs": []}
    out: List[Dict[str, Any]] = []
    try:
        jobs = queue.list_jobs()
        for j in jobs:
            if j.get("status") in ("running", "pending"):
                s = _job_to_status(j)
                out.append({
                    "job_id": s["job_id"],
                    "title": s["title"] or "（無題）",
                    "step": s["step"],
                    "step_label": s["step_label"],
                    "progress": s["progress"],
                    "channel_id": s.get("channel_id"),
                    "status": s["status"],
                })
    except Exception:
        pass
    return {"jobs": out}


@router.post("/generate/suggest-theme")
async def suggest_theme(
    req: ThemeSuggestRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    sg = _state.get("scenario_generator")
    if not cm or not sg:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    ch = cm.get(req.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {req.channel_id}")
    if not getattr(sg, "api_key", None):
        raise HTTPException(status_code=400, detail="OpenAI API キーが設定されていません")
    try:
        themes = sg.suggest_themes(ch, req.count)
        return {"themes": themes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suggest failed: {e}")


# =====================================================================
# Theme Queue — チャンネル別「動画ネタストック」の管理 (JWT 保護)
# =====================================================================
from pipeline.auto_scenario import theme_queue as _tq  # noqa: E402


class ThemeQueueSettingsBody(BaseModel):
    target_size: Optional[int] = Field(default=None, ge=1, le=50)
    min_threshold: Optional[int] = Field(default=None, ge=0, le=50)


class ThemeQueueReplenishBody(BaseModel):
    count: Optional[int] = Field(default=None, ge=1, le=20)


class ThemeQueueAddItemBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    angle: Optional[str] = ""
    parent_title: Optional[str] = None


class ThemeQueueReorderBody(BaseModel):
    ordered_ids: List[str]


def _require_channel(channel_id: str):
    cm = _state.get("channel_manager")
    if not cm:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return ch


@router.get("/theme-queue/{channel_id}")
async def api_theme_queue_get(channel_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    _require_channel(channel_id)
    return _tq.get_status(channel_id)


@router.put("/theme-queue/{channel_id}/settings")
async def api_theme_queue_settings(
    channel_id: str, body: ThemeQueueSettingsBody, _=Depends(require_session)
) -> Dict[str, Any]:
    _require_channel(channel_id)
    return _tq.update_settings(
        channel_id,
        target_size=body.target_size,
        min_threshold=body.min_threshold,
    )


@router.post("/theme-queue/{channel_id}/replenish")
async def api_theme_queue_replenish(
    channel_id: str, body: ThemeQueueReplenishBody, _=Depends(require_session)
) -> Dict[str, Any]:
    ch = _require_channel(channel_id)
    sg = _state.get("scenario_generator")
    if not sg or not getattr(sg, "api_key", None):
        raise HTTPException(status_code=400, detail="OpenAI API キーが設定されていません")
    # LLM 呼び出しは数十秒掛かることがあるのでスレッドへ
    try:
        return await asyncio.to_thread(_tq.replenish, ch, sg, count=body.count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Replenish failed: {e}")


@router.post("/theme-queue/{channel_id}/items")
async def api_theme_queue_add_item(
    channel_id: str, body: ThemeQueueAddItemBody, _=Depends(require_session)
) -> Dict[str, Any]:
    _require_channel(channel_id)
    item = _tq.add_item(
        channel_id,
        {"title": body.title, "angle": body.angle or "", "parent_title": body.parent_title},
        source="manual",
    )
    if not item:
        raise HTTPException(status_code=400, detail="無効または重複したタイトル")
    return {"status": "added", "item": item, "queue": _tq.get_status(channel_id)}


@router.delete("/theme-queue/{channel_id}/items/{item_id}")
async def api_theme_queue_remove_item(
    channel_id: str, item_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    _require_channel(channel_id)
    if not _tq.remove_item(channel_id, item_id):
        raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
    return {"status": "removed", "queue": _tq.get_status(channel_id)}


@router.put("/theme-queue/{channel_id}/reorder")
async def api_theme_queue_reorder(
    channel_id: str, body: ThemeQueueReorderBody, _=Depends(require_session)
) -> Dict[str, Any]:
    _require_channel(channel_id)
    return _tq.reorder(channel_id, body.ordered_ids)


@router.post("/theme-queue/check-all")
async def api_theme_queue_check_all(_=Depends(require_session)) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    sg = _state.get("scenario_generator")
    if not cm or not sg:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    if not getattr(sg, "api_key", None):
        raise HTTPException(status_code=400, detail="OpenAI API キーが設定されていません")
    return await asyncio.to_thread(_tq.check_all_channels, cm, sg)
