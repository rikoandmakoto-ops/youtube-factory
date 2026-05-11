"""
YouTube Factory — Analytics API (`/api/analytics/*`)

YouTube Analytics API v2 とコメント分析を統合した参照系 + 手動同期エンドポイント。

エンドポイント:
  - GET  /api/analytics/channel/{channel_id}/overview    — 直近30日のチャンネル概要
  - GET  /api/analytics/videos/{channel_id}              — 動画別メトリクス一覧
  - GET  /api/analytics/video/{video_id}/retention       — 視聴維持率カーブ
  - GET  /api/analytics/video/{video_id}/comments        — コメント分析（感情/トピック）
  - POST /api/analytics/sync/{channel_id}                — 手動同期トリガー
  - GET  /api/analytics/insights/{channel_id}            — 成功パターン + 維持率分析（Phase B）
  - POST /api/analytics/analyze/{channel_id}             — 分析実行トリガー（Phase B）

認証: require_session（JWT、api_phase1 と同じ）
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api_phase1 import require_session
from pipeline import youtube_analytics, youtube_comments
from pipeline.analytics import (
    retention_analyzer,
    store as analytics_store,
    success_analyzer,
)


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# =====================================================================
# Pydantic
# =====================================================================

class SyncRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=365)
    max_videos: int = Field(default=50, ge=1, le=200)
    fetch_retention_for: int = Field(default=5, ge=0, le=50)
    sync_comments_for: int = Field(default=5, ge=0, le=50)
    max_comments_per_video: int = Field(default=200, ge=1, le=1000)
    analyze_comments: bool = True


class AnalyzeRequest(BaseModel):
    use_gpt: bool = True
    max_videos: int = Field(default=50, ge=1, le=200)


# =====================================================================
# GET endpoints (cached read from SQLite)
# =====================================================================

@router.get("/channel/{channel_id}/overview")
async def channel_overview(
    channel_id: str,
    days: int = Query(default=30, ge=1, le=365),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """直近 days 日のチャンネル概要（SQLite キャッシュから即時返却）。
    まだ同期していなければ totals は 0。"""
    daily = analytics_store.list_channel_metrics(channel_id, days=days)
    totals = {
        "views": sum(d.get("views", 0) for d in daily),
        "watch_time_minutes": sum(d.get("watch_time_minutes", 0.0) for d in daily),
        "subscribers_gained": sum(d.get("subscribers_gained", 0) for d in daily),
        "subscribers_lost": sum(d.get("subscribers_lost", 0) for d in daily),
    }
    totals["net_subscribers"] = (
        totals["subscribers_gained"] - totals["subscribers_lost"]
    )
    return {
        "channel_id": channel_id,
        "days_requested": days,
        "totals": totals,
        "daily": sorted(daily, key=lambda d: d.get("date", "")),
    }


@router.get("/videos/{channel_id}")
async def videos(
    channel_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """動画別メトリクス一覧（各 video_id の最新スナップショット）。"""
    items = analytics_store.list_video_metrics(
        channel_id, limit=limit, latest_per_video=True
    )
    return {"channel_id": channel_id, "count": len(items), "items": items}


@router.get("/video/{video_id}/retention")
async def video_retention(
    video_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """視聴維持率カーブ。未取得なら 404。"""
    data = analytics_store.get_retention(video_id)
    if not data:
        raise HTTPException(
            status_code=404,
            detail="retention curve not synced for this video — POST /api/analytics/sync",
        )
    return data


@router.get("/video/{video_id}/comments")
async def video_comments(
    video_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """コメント分析サマリ + 個別コメント一覧。"""
    summary = analytics_store.comment_summary_for_video(video_id)
    comments = analytics_store.list_comments_for_video(video_id, limit=limit)
    return {
        "video_id": video_id,
        "summary": summary,
        "comments": comments,
    }


# =====================================================================
# POST: 手動同期
# =====================================================================

# 同チャンネルの同時同期を抑制（YouTube API クォータ保護）
_sync_locks: Dict[str, threading.Lock] = {}


def _lock_for(channel_id: str) -> threading.Lock:
    lock = _sync_locks.get(channel_id)
    if lock is None:
        lock = threading.Lock()
        _sync_locks[channel_id] = lock
    return lock


@router.post("/sync/{channel_id}")
async def sync_channel(
    channel_id: str,
    body: Optional[SyncRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """指定チャンネルのメトリクスを YouTube から取得して SQLite に書き込む。

    重い処理（最大数十秒）になる可能性があるため、同チャンネルの並列実行はロックで弾く。
    """
    opts = body or SyncRequest()
    lock = _lock_for(channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail=f"channel {channel_id} is already syncing",
        )
    try:
        result = youtube_analytics.sync_channel(
            channel_id,
            days=opts.days,
            max_videos=opts.max_videos,
            fetch_retention_for=opts.fetch_retention_for,
        )

        comment_results: List[Dict[str, Any]] = []
        if opts.sync_comments_for > 0 and result.get("videos", {}).get("ok"):
            top_videos = sorted(
                result["videos"].get("items", []) or [],
                key=lambda v: int(v.get("views", 0) or 0),
                reverse=True,
            )[: opts.sync_comments_for]
            for v in top_videos:
                vid = v.get("video_id")
                if not vid:
                    continue
                comment_results.append(
                    youtube_comments.sync_video_comments(
                        channel_id,
                        vid,
                        max_comments=opts.max_comments_per_video,
                        analyze=opts.analyze_comments,
                    )
                )
        result["comments"] = comment_results
        return result
    finally:
        lock.release()


# =====================================================================
# Phase B: insights (success patterns + retention)
# =====================================================================

# 分析実行用ロック（GPT 呼び出しを含むので並列実行を抑制）
_analyze_locks: Dict[str, threading.Lock] = {}


def _analyze_lock_for(channel_id: str) -> threading.Lock:
    lock = _analyze_locks.get(channel_id)
    if lock is None:
        lock = threading.Lock()
        _analyze_locks[channel_id] = lock
    return lock


@router.get("/insights/{channel_id}")
async def insights(
    channel_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """成功パターン + 視聴維持率インサイトをまとめて返す。
    未分析なら各セクションは null（フロント側で「分析を実行」ボタンを出せる想定）。"""
    patterns = success_analyzer.load_patterns(channel_id)
    retention = retention_analyzer.load_insights(channel_id)
    return {
        "channel_id": channel_id,
        "success_patterns": patterns,
        "retention_insights": retention,
    }


@router.post("/analyze/{channel_id}")
async def analyze_channel(
    channel_id: str,
    body: Optional[AnalyzeRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """指定チャンネルの SQLite に既にあるデータを使って成功パターン + 維持率を再分析。

    YouTube への外部呼び出しは行わない（GPT-4o のみ）。
    別途 /sync で SQLite を最新化してから呼ぶ想定。
    """
    opts = body or AnalyzeRequest()
    lock = _analyze_lock_for(channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail=f"channel {channel_id} is already analyzing",
        )
    try:
        patterns = success_analyzer.analyze_channel(
            channel_id, use_gpt=opts.use_gpt, limit=opts.max_videos
        )
        retention = retention_analyzer.analyze_channel(
            channel_id, use_gpt=opts.use_gpt, max_videos=opts.max_videos
        )
        return {
            "channel_id": channel_id,
            "success_patterns": patterns,
            "retention_insights": retention,
        }
    finally:
        lock.release()
