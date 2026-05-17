"""
YouTube Factory — Competitor Effects Research API (Phase F-2)

エンドポイント:
  - POST   /api/channels/{channel_id}/research-effects          — リサーチ実行
  - GET    /api/channels/{channel_id}/research-effects/latest   — 最新結果
  - GET    /api/channels/{channel_id}/research-effects          — 履歴
  - POST   /api/channels/{channel_id}/research-effects/{record_id}/apply
                                                                — suggested_effects を JSON へ反映

リサーチ本体は重い（YouTube DL + Claude Vision）ので、API ではバックグラウンド
スレッドで実行し、即時に job_id を返す。完了後の結果は analytics_store の
effects_research テーブルに保存される。

認証: api_phase1 と同じ require_session（JWT）。
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from api_phase1 import require_session
from pipeline.analytics import effects_researcher, store as analytics_store


router = APIRouter(prefix="/api", tags=["research-effects"])


# =====================================================================
# Locks + ephemeral job tracking
# =====================================================================

_locks: Dict[str, threading.Lock] = {}
# job_id → status dict（メモリ上のみ。プロセス再起動で消える）
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _lock_for(channel_id: str) -> threading.Lock:
    lock = _locks.get(channel_id)
    if lock is None:
        lock = threading.Lock()
        _locks[channel_id] = lock
    return lock


def _set_job(job_id: str, **fields: Any) -> None:
    with _jobs_lock:
        cur = _jobs.get(job_id) or {}
        cur.update(fields)
        _jobs[job_id] = cur


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


# =====================================================================
# Pydantic
# =====================================================================

class ResearchRequest(BaseModel):
    target_channels: Optional[int] = Field(default=None, ge=1, le=15)
    videos_per_channel: Optional[int] = Field(default=None, ge=1, le=5)
    max_videos_per_query: Optional[int] = Field(default=None, ge=5, le=50)
    queries: Optional[List[str]] = None
    must_include_token: Optional[str] = None
    blacklist_words: Optional[List[str]] = None
    require_japanese: Optional[bool] = None
    auto_apply: bool = False           # True で JSON へ自動反映
    run_in_background: bool = True     # False で同期実行（テスト用）


class ApplyRequest(BaseModel):
    effects: Optional[Dict[str, Any]] = None  # None なら DB の suggested_effects を使う


# =====================================================================
# Background worker
# =====================================================================

def _run_research_job(
    job_id: str,
    channel_id: str,
    overrides: Dict[str, Any],
    auto_apply: bool,
) -> None:
    """Background thread entrypoint."""
    lock = _lock_for(channel_id)
    if not lock.acquire(blocking=False):
        _set_job(job_id, status="failed",
                 error="another research already running for this channel",
                 finished_at=int(time.time()))
        return
    _set_job(job_id, status="running", started_at=int(time.time()))

    def _progress(done: int, total: int, label: str) -> None:
        _set_job(job_id, progress={"done": done, "total": total, "label": label[:80]})

    try:
        result = effects_researcher.run_effects_research(
            channel_id,
            save=True, auto_apply=auto_apply,
            overrides=overrides or None,
            progress=_progress,
        )
        _set_job(job_id, status="done", finished_at=int(time.time()), result=result)
    except Exception as e:
        import traceback
        _set_job(
            job_id, status="failed", finished_at=int(time.time()),
            error=str(e), traceback=traceback.format_exc()[-2000:],
        )
    finally:
        lock.release()


# =====================================================================
# Endpoints
# =====================================================================

@router.post("/channels/{channel_id}/research-effects")
async def start_research(
    channel_id: str,
    body: Optional[ResearchRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """競合動画から画面演出をリサーチし結果を保存する。

    既定では即時 job_id を返し、バックグラウンドで実行。
    run_in_background=False で同期実行。
    """
    opts = body or ResearchRequest()
    if effects_researcher._load_channel_json(channel_id) is None:
        raise HTTPException(status_code=404, detail=f"channel '{channel_id}' not found")
    overrides: Dict[str, Any] = {}
    for k in ("target_channels", "videos_per_channel", "max_videos_per_query",
              "queries", "must_include_token", "blacklist_words", "require_japanese"):
        v = getattr(opts, k)
        if v is not None:
            overrides[k] = v

    if not opts.run_in_background:
        # 同期実行（重い: 5〜15 分かかりうる）
        lock = _lock_for(channel_id)
        if not lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="research already running")
        try:
            return effects_researcher.run_effects_research(
                channel_id, save=True, auto_apply=opts.auto_apply,
                overrides=overrides or None,
            )
        finally:
            lock.release()

    # 非同期: スレッドで走らせて job_id を返す
    job_id = uuid.uuid4().hex[:12]
    _set_job(job_id, status="queued", channel_id=channel_id,
             created_at=int(time.time()),
             auto_apply=opts.auto_apply)
    t = threading.Thread(
        target=_run_research_job,
        args=(job_id, channel_id, overrides, opts.auto_apply),
        daemon=True,
    )
    t.start()
    return {"ok": True, "job_id": job_id, "channel_id": channel_id, "status": "queued"}


@router.get("/channels/{channel_id}/research-effects/job/{job_id}")
async def get_research_job(
    channel_id: str,
    job_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found (or expired)")
    return {"ok": True, "job_id": job_id, **job}


@router.get("/channels/{channel_id}/research-effects/latest")
async def get_latest_research(
    channel_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    rec = analytics_store.get_latest_effects_research(channel_id)
    return {"ok": True, "channel_id": channel_id, "latest": rec}


@router.get("/channels/{channel_id}/research-effects")
async def list_research(
    channel_id: str,
    limit: int = 20,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    rows = analytics_store.list_effects_research(channel_id, limit=limit)
    return {"ok": True, "channel_id": channel_id, "history": rows, "count": len(rows)}


@router.post("/channels/{channel_id}/research-effects/{record_id}/apply")
async def apply_research(
    channel_id: str,
    record_id: int,
    body: Optional[ApplyRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """指定レコードの suggested_effects を data/channels/<id>.json に書き込む。

    body.effects を渡せばそれを使う（UI 上で編集後に保存するパス）。
    """
    rec = analytics_store.get_effects_research(record_id)
    if not rec or rec.get("channel_id") != channel_id:
        raise HTTPException(status_code=404, detail="research record not found")
    effects = (body.effects if body and body.effects is not None
               else rec.get("suggested_effects"))
    if not effects:
        raise HTTPException(status_code=400, detail="no effects to apply")
    result = effects_researcher.apply_effects_to_channel(channel_id, effects)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or "apply failed")
    try:
        analytics_store.mark_effects_research_applied(record_id)
    except Exception:
        pass
    return {"ok": True, "channel_id": channel_id, "record_id": record_id,
            "applied_effects": effects}
