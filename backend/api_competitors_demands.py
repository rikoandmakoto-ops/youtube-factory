"""
YouTube Factory — Competitor Analysis + Comment Demand API (Phase F)

エンドポイント:
  Competitor analysis
    - GET  /api/competitors/{channel_id}                       — 最新分析結果
    - POST /api/competitors/{channel_id}/scan                  — 手動スキャン
    - POST /api/competitors/{channel_id}/add                   — 競合チャンネル追加
    - DELETE /api/competitors/{channel_id}/remove/{competitor_id} — 削除

  Comment demand
    - GET  /api/comment-demands/{channel_id}                   — 需要一覧
    - POST /api/comment-demands/{channel_id}/scan              — 手動スキャン
    - POST /api/comment-demands/{channel_id}/queue/{demand_id} — テーマキューに追加
    - POST /api/comment-demands/{channel_id}/dismiss/{demand_id} — 却下

認証: api_phase1 と同じ require_session（JWT）。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api_phase1 import require_session
from pipeline.analytics import (
    comment_demand,
    competitor_analyzer,
    store as analytics_store,
)


router = APIRouter(prefix="/api", tags=["competitors", "comment-demands"])


# =====================================================================
# Locks (同チャンネルの同時スキャンを抑制)
# =====================================================================

_competitor_locks: Dict[str, threading.Lock] = {}
_demand_locks: Dict[str, threading.Lock] = {}


def _lock(d: Dict[str, threading.Lock], key: str) -> threading.Lock:
    lock = d.get(key)
    if lock is None:
        lock = threading.Lock()
        d[key] = lock
    return lock


# =====================================================================
# Pydantic
# =====================================================================

class CompetitorScanRequest(BaseModel):
    max_videos_per_competitor: int = Field(default=20, ge=1, le=50)
    max_competitors: int = Field(default=10, ge=1, le=50)


class CompetitorAddRequest(BaseModel):
    competitor_channel_id: str  # UC... / URL / @handle


class DemandScanRequest(BaseModel):
    since_days: int = Field(default=30, ge=1, le=365)
    auto_queue: bool = True


# =====================================================================
# Competitors
# =====================================================================

@router.get("/competitors/{channel_id}")
async def get_competitor_overview(
    channel_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """登録済み競合と最新分析結果。"""
    competitor_ids = competitor_analyzer.list_competitors(channel_id)
    analyses = analytics_store.list_competitor_analyses(
        channel_id, latest_per_competitor=True, limit=limit
    )
    # 履歴: 全件（時系列で並べる）
    history = analytics_store.list_competitor_analyses(
        channel_id, latest_per_competitor=False, limit=200
    )
    return {
        "channel_id": channel_id,
        "competitor_ids": competitor_ids,
        "latest_analyses": analyses,
        "history": history,
        "count": len(analyses),
    }


@router.post("/competitors/{channel_id}/scan")
async def run_competitor_scan(
    channel_id: str,
    body: Optional[CompetitorScanRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """手動で競合スキャンを実行。"""
    opts = body or CompetitorScanRequest()
    lock = _lock(_competitor_locks, channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409, detail="competitor scan already running for this channel"
        )
    try:
        return competitor_analyzer.scan_channel(
            channel_id,
            max_videos_per_competitor=opts.max_videos_per_competitor,
            max_competitors=opts.max_competitors,
        )
    finally:
        lock.release()


@router.post("/competitors/{channel_id}/add")
async def add_competitor(
    channel_id: str,
    body: CompetitorAddRequest,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """競合チャンネルを追加（URL / @handle / UC... を受け付ける）。"""
    result = competitor_analyzer.add_competitor(channel_id, body.competitor_channel_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "add failed")
    return result


@router.delete("/competitors/{channel_id}/remove/{competitor_id}")
async def remove_competitor(
    channel_id: str,
    competitor_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    result = competitor_analyzer.remove_competitor(channel_id, competitor_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "remove failed")
    return result


# =====================================================================
# Comment demands
# =====================================================================

@router.get("/comment-demands/{channel_id}")
async def list_demands(
    channel_id: str,
    status: Optional[str] = Query(default=None),
    demand_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    items = analytics_store.list_comment_demands(
        channel_id,
        status=status,
        demand_type=demand_type,
        limit=limit,
    )
    # サマリ
    by_status: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    for it in items:
        s = it.get("status") or "pending"
        t = it.get("demand_type") or "request"
        by_status[s] = by_status.get(s, 0) + 1
        by_type[t] = by_type.get(t, 0) + 1
    return {
        "channel_id": channel_id,
        "count": len(items),
        "items": items,
        "by_status": by_status,
        "by_type": by_type,
        "auto_queue_threshold": comment_demand.AUTO_QUEUE_THRESHOLD,
    }


@router.post("/comment-demands/{channel_id}/scan")
async def run_demand_scan(
    channel_id: str,
    body: Optional[DemandScanRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    opts = body or DemandScanRequest()
    lock = _lock(_demand_locks, channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409, detail="comment demand scan already running for this channel"
        )
    try:
        return comment_demand.scan_channel(
            channel_id,
            since_days=opts.since_days,
            auto_queue=opts.auto_queue,
        )
    finally:
        lock.release()


@router.post("/comment-demands/{channel_id}/queue/{demand_id}")
async def queue_demand(
    channel_id: str,
    demand_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    result = comment_demand.queue_demand(channel_id, demand_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "queue failed")
    return result


@router.post("/comment-demands/{channel_id}/dismiss/{demand_id}")
async def dismiss_demand(
    channel_id: str,
    demand_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    result = comment_demand.dismiss_demand(channel_id, demand_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "not found")
    return result
