"""切り抜きチャンネル用 REST API。

    GET  /api/clips/{channel_id}/sources   切り抜ける元動画の在庫
    GET  /api/clips/{channel_id}/state     消化済み区間の記録
    POST /api/clips/generate               切り抜きを生成（任意で投稿）

生成はレンダリングに数十秒かかるのでバックグラウンドで走らせ、結果は
data/analytics/clip_state.json と出力先の _clip_meta_*.json に残す。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_phase1 import require_session

router = APIRouter(prefix="/api/clips", tags=["clips"])

# 進行中ジョブ（チャンネルごとに1本まで）
_running: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


class ClipGenerateRequest(BaseModel):
    channel_id: str = "clip-lab"
    count: int = Field(default=1, ge=1, le=5)
    source_title: Optional[str] = None
    upload: bool = False
    privacy: Optional[str] = None
    dry_run: bool = False
    # True なら生成完了まで待つ（CLI 相当）。既定は非同期。
    wait: bool = False


def _generate(req: ClipGenerateRequest) -> Dict[str, Any]:
    from pipeline.clip_factory import generate_clip

    return generate_clip(
        req.channel_id,
        count=req.count,
        source_title=req.source_title,
        upload=req.upload,
        privacy=req.privacy,
        dry_run=req.dry_run,
    )


@router.get("/{channel_id}/sources")
async def get_sources(channel_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    from pipeline.clip_factory import list_available_sources

    try:
        stock = list_available_sources(channel_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "channel_id": channel_id,
        "source_count": len(stock),
        "remaining_clips": sum(s["remaining_clips"] for s in stock),
        "sources": stock,
    }


@router.get("/{channel_id}/state")
async def get_state(channel_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    from pipeline.clip_factory import sources as src_mod

    state = src_mod.load_state().get("sources", {})
    return {
        "channel_id": channel_id,
        "clipped_videos": len(state),
        "clip_count": sum(len(v.get("segments") or []) for v in state.values()),
        "running": _running.get(channel_id),
        "state": state,
    }


@router.post("/generate")
async def generate(req: ClipGenerateRequest, _=Depends(require_session)) -> Dict[str, Any]:
    with _lock:
        current = _running.get(req.channel_id)
        if current and current.get("status") == "running":
            raise HTTPException(
                status_code=409,
                detail=f"{req.channel_id} の切り抜き生成が既に実行中です",
            )
        _running[req.channel_id] = {"status": "running", "result": None}

    if req.wait or req.dry_run:
        try:
            res = _generate(req)
        finally:
            with _lock:
                _running.pop(req.channel_id, None)
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("error") or "生成に失敗しました")
        return res

    def _work() -> None:
        try:
            res = _generate(req)
        except Exception as e:  # noqa: BLE001 — 状態に残して UI から見えるようにする
            res = {"ok": False, "error": str(e)}
        with _lock:
            _running[req.channel_id] = {
                "status": "done" if res.get("ok") else "failed",
                "result": res,
            }

    threading.Thread(target=_work, name=f"clip-gen-{req.channel_id}", daemon=True).start()
    return {"ok": True, "status": "started", "channel_id": req.channel_id}
