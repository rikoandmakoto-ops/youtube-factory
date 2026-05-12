"""
YouTube Factory — Phase D API (`/api/evaluations/*`, `/api/ab-reconciliation/*`, `/api/improvements/*`)

シナリオ評価・AB 答え合わせ・改善キューの参照系 + 手動トリガーをまとめたルーター。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api_phase1 import require_session
from pipeline.analytics import (
    ab_reconciler,
    improvement_queue,
    model_compete,
    posting_optimizer,
    scenario_evaluator,
    series_engine,
    store as analytics_store,
    thumbnail_ab_test,
    trend_scanner,
)


router = APIRouter(prefix="/api", tags=["pdca"])

_eval_locks: Dict[str, threading.Lock] = {}
_recon_locks: Dict[str, threading.Lock] = {}
_imp_locks: Dict[str, threading.Lock] = {}
_trend_locks: Dict[str, threading.Lock] = {}
_series_locks: Dict[str, threading.Lock] = {}


def _lock(d: Dict[str, threading.Lock], key: str) -> threading.Lock:
    lock = d.get(key)
    if lock is None:
        lock = threading.Lock()
        d[key] = lock
    return lock


# =====================================================================
# Pydantic
# =====================================================================

class EvalRunRequest(BaseModel):
    use_gpt: bool = True
    only_new: bool = True
    max_videos: int = Field(default=20, ge=1, le=100)


class ReconcileRunRequest(BaseModel):
    min_age_days: float = Field(default=7.0, ge=0.0, le=365.0)


class ImprovementRunRequest(BaseModel):
    threshold_ratio: float = Field(default=0.8, ge=0.0, le=1.0)
    max_videos: int = Field(default=20, ge=1, le=100)
    regen_titles: bool = True


class ImprovementStatusRequest(BaseModel):
    status: str  # pending | applied | dismissed


# =====================================================================
# /api/evaluations
# =====================================================================

@router.get("/evaluations/{channel_id}")
async def list_evaluations(
    channel_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    items = analytics_store.list_scenario_evaluations(channel_id, limit=limit)
    return {
        "channel_id": channel_id,
        "count": len(items),
        "items": items,
        "weak_patterns": scenario_evaluator.aggregate_weak_patterns(channel_id, recent=10),
    }


@router.get("/evaluations/{channel_id}/{video_id}")
async def get_evaluation(
    channel_id: str,
    video_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    rec = analytics_store.get_scenario_evaluation(video_id)
    if not rec or rec.get("channel_id") != channel_id:
        raise HTTPException(status_code=404, detail="evaluation not found")
    # 該当動画の retention curve も同梱
    retention = analytics_store.get_retention(video_id)
    comments = analytics_store.comment_summary_for_video(video_id)
    return {
        "evaluation": rec,
        "retention": retention,
        "comment_summary": comments,
    }


@router.post("/evaluations/{channel_id}/run")
async def run_evaluation(
    channel_id: str,
    body: Optional[EvalRunRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    opts = body or EvalRunRequest()
    lock = _lock(_eval_locks, channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="evaluation already running for this channel")
    try:
        return scenario_evaluator.evaluate_channel(
            channel_id,
            max_videos=opts.max_videos,
            use_gpt=opts.use_gpt,
            only_new=opts.only_new,
        )
    finally:
        lock.release()


@router.post("/evaluations/{channel_id}/{video_id}/run")
async def run_evaluation_single(
    channel_id: str,
    video_id: str,
    body: Optional[EvalRunRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    opts = body or EvalRunRequest()
    return scenario_evaluator.evaluate_video(
        video_id=video_id,
        channel_id=channel_id,
        use_gpt=opts.use_gpt,
        force=not opts.only_new,
    )


# =====================================================================
# /api/ab-reconciliation
# =====================================================================

@router.get("/ab-reconciliation/{channel_id}")
async def list_ab_reconciliation(
    channel_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    items = analytics_store.list_ab_reconciliations(channel_id, limit=limit)
    return {
        "channel_id": channel_id,
        "count": len(items),
        "items": items,
        "pattern_insights": ab_reconciler.pattern_insights(channel_id),
    }


@router.post("/ab-reconciliation/{channel_id}/run")
async def run_ab_reconciliation(
    channel_id: str,
    body: Optional[ReconcileRunRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    opts = body or ReconcileRunRequest()
    lock = _lock(_recon_locks, channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="reconciliation already running")
    try:
        return ab_reconciler.reconcile_channel(channel_id, min_age_days=opts.min_age_days)
    finally:
        lock.release()


# =====================================================================
# /api/improvements
# =====================================================================

@router.get("/improvements/{channel_id}")
async def list_improvements(
    channel_id: str,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    items = analytics_store.list_improvement_entries(channel_id, status=status, limit=limit)
    return {
        "channel_id": channel_id,
        "count": len(items),
        "items": items,
        "channel_avg_ctr": improvement_queue.channel_avg_ctr(channel_id),
    }


@router.post("/improvements/{channel_id}/run")
async def run_improvement_detect(
    channel_id: str,
    body: Optional[ImprovementRunRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    opts = body or ImprovementRunRequest()
    lock = _lock(_imp_locks, channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="improvement detection already running")
    try:
        return improvement_queue.detect_and_queue(
            channel_id,
            threshold_ratio=opts.threshold_ratio,
            max_videos=opts.max_videos,
            regen_titles=opts.regen_titles,
        )
    finally:
        lock.release()


@router.post("/improvements/{channel_id}/{video_id}/regenerate")
async def regenerate_catchcopy(
    channel_id: str,
    video_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    return improvement_queue.regenerate_for_video(channel_id, video_id, regen=True)


@router.put("/improvements/{channel_id}/{video_id}/status")
async def set_improvement_status(
    channel_id: str,
    video_id: str,
    body: ImprovementStatusRequest,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    if not analytics_store.update_improvement_status(video_id, body.status):
        raise HTTPException(status_code=404, detail="improvement entry not found")
    return {"video_id": video_id, "status": body.status}


# =====================================================================
# /api/model-performance — GPT vs Claude AI compete
# =====================================================================

@router.get("/model-performance/{channel_id}")
async def model_performance(
    channel_id: str,
    recent_runs: int = Query(default=20, ge=1, le=200),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """GPT / Claude のコンペ実績（ブラインド勝率 + 実 CTR / 維持率）を返す。"""
    agg = model_compete.aggregate_performance(channel_id)
    strategy = model_compete.decide_selection_strategy(channel_id)
    # 直近のコンペ run を run_id でグルーピングして UI に出せる形に整形
    records = analytics_store.list_model_scenario_records(channel_id, limit=recent_runs * 2)
    runs: Dict[str, Dict[str, Any]] = {}
    for r in records:
        rid = r.get("run_id")
        if not rid:
            continue
        entry = runs.setdefault(rid, {"run_id": rid, "created_at": r.get("created_at"), "candidates": {}})
        entry["candidates"][r.get("model_name")] = {
            "title": r.get("title"),
            "won_blind_eval": r.get("won_blind_eval"),
            "blind_overall": r.get("blind_overall"),
            "blind_scores": r.get("blind_scores"),
            "selected": r.get("selected"),
            "selected_by": r.get("selected_by"),
            "video_id": r.get("video_id"),
        }
    recent = sorted(
        runs.values(), key=lambda x: x.get("created_at") or 0, reverse=True
    )[:recent_runs]
    return {
        "channel_id": channel_id,
        "performance": agg,
        "strategy": strategy,
        "recent_runs": recent,
    }


# =====================================================================
# /api/optimal-posting-time — Posting Optimizer
# =====================================================================

class OptimalPostingApplyRequest(BaseModel):
    days: int = Field(default=30, ge=7, le=180)


@router.get("/optimal-posting-time/{channel_id}")
async def get_optimal_posting_time(
    channel_id: str,
    days: int = Query(default=30, ge=7, le=180),
    recompute: bool = Query(default=False),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """過去 `days` 日の (曜日 × 時間帯) 別パフォーマンスから最適投稿スロットを返す。"""
    return posting_optimizer.get_status(channel_id, days=days, recompute=recompute)


@router.post("/optimal-posting-time/{channel_id}/apply")
async def apply_optimal_posting_time(
    channel_id: str,
    body: Optional[OptimalPostingApplyRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """推奨スロットを autopilot.schedule に書き戻して再スケジュール。"""
    opts = body or OptimalPostingApplyRequest()
    result = posting_optimizer.apply_to_autopilot(channel_id, days=opts.days)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "apply failed")
    return result


# =====================================================================
# /api/thumbnail-tests — Thumbnail AB Test
# =====================================================================

class ThumbnailTestRegisterRequest(BaseModel):
    video_id: str
    channel_id: str
    video_title: str
    original_thumbnail_path: Optional[str] = None
    threshold_ratio: float = Field(default=0.8, ge=0.1, le=1.0)
    generate_variants: bool = True


@router.get("/thumbnail-tests/{channel_id}")
async def list_thumbnail_tests(
    channel_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    items = thumbnail_ab_test.list_tests(channel_id, limit=limit)
    return {
        "channel_id": channel_id,
        "count": len(items),
        "items": items,
        "summary": thumbnail_ab_test.summary(channel_id),
    }


@router.get("/thumbnail-tests/{channel_id}/{video_id}")
async def get_thumbnail_test(
    channel_id: str,
    video_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    t = thumbnail_ab_test.get_test(video_id)
    if not t or t.get("channel_id") != channel_id:
        raise HTTPException(status_code=404, detail="thumbnail test not found")
    return t


@router.post("/thumbnail-tests/register")
async def register_thumbnail_test(
    body: ThumbnailTestRegisterRequest,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    return thumbnail_ab_test.register_test(
        video_id=body.video_id,
        channel_id=body.channel_id,
        video_title=body.video_title,
        original_thumbnail_path=body.original_thumbnail_path,
        threshold_ratio=body.threshold_ratio,
        generate_variants=body.generate_variants,
    )


@router.post("/thumbnail-tests/{channel_id}/{video_id}/check")
async def check_thumbnail_test(
    channel_id: str,
    video_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    t = thumbnail_ab_test.get_test(video_id)
    if not t or t.get("channel_id") != channel_id:
        raise HTTPException(status_code=404, detail="thumbnail test not found")
    return thumbnail_ab_test.check_one(video_id)


@router.post("/thumbnail-tests/{channel_id}/{video_id}/switch")
async def switch_thumbnail_test(
    channel_id: str,
    video_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    t = thumbnail_ab_test.get_test(video_id)
    if not t or t.get("channel_id") != channel_id:
        raise HTTPException(status_code=404, detail="thumbnail test not found")
    res = thumbnail_ab_test.force_switch(video_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "switch failed")
    return res


@router.post("/thumbnail-tests/{channel_id}/{video_id}/stop")
async def stop_thumbnail_test(
    channel_id: str,
    video_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    t = thumbnail_ab_test.get_test(video_id)
    if not t or t.get("channel_id") != channel_id:
        raise HTTPException(status_code=404, detail="thumbnail test not found")
    return thumbnail_ab_test.stop_test(video_id)


@router.post("/thumbnail-tests/{channel_id}/check-all")
async def check_all_thumbnail_tests(
    channel_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    return thumbnail_ab_test.check_pending(channel_id=channel_id)


# =====================================================================
# /api/trend-scanner — Trend Scanner (Phase E-1)
# =====================================================================

class TrendScanRequest(BaseModel):
    auto_queue: bool = True
    sources: Optional[List[str]] = None  # ["google_trends", "news_api", "youtube_trending"]


@router.get("/trend-scanner/{channel_id}")
async def list_trend_detections_api(
    channel_id: str,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """検出済みトレンド一覧 + スキャン履歴を返す。"""
    items = analytics_store.list_trend_detections(channel_id, status=status, limit=limit)
    history = analytics_store.list_trend_scan_history(channel_id, limit=20)
    by_source: Dict[str, int] = {}
    for it in items:
        s = it.get("source") or "unknown"
        by_source[s] = by_source.get(s, 0) + 1
    return {
        "channel_id": channel_id,
        "count": len(items),
        "items": items,
        "history": history,
        "by_source": by_source,
        "auto_queue_threshold": trend_scanner.AUTO_QUEUE_THRESHOLD,
    }


@router.post("/trend-scanner/{channel_id}/scan")
async def run_trend_scan(
    channel_id: str,
    body: Optional[TrendScanRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    opts = body or TrendScanRequest()
    lock = _lock(_trend_locks, channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="trend scan already running for this channel")
    try:
        return trend_scanner.scan_channel(
            channel_id,
            auto_queue=opts.auto_queue,
            sources=opts.sources,
        )
    finally:
        lock.release()


@router.post("/trend-scanner/{channel_id}/queue/{detection_id}")
async def queue_trend_detection(
    channel_id: str,
    detection_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """手動でトレンド検出を theme_queue に投入。"""
    result = trend_scanner.queue_detection(channel_id, detection_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "queue failed")
    return result


@router.post("/trend-scanner/{channel_id}/dismiss/{detection_id}")
async def dismiss_trend_detection(
    channel_id: str,
    detection_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    result = trend_scanner.dismiss_detection(channel_id, detection_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "not found")
    return result


# =====================================================================
# /api/series — Series Engine (Phase E-2)
# =====================================================================

class SeriesDetectRequest(BaseModel):
    threshold: float = Field(default=1.5, ge=1.0, le=10.0)
    max_viral: int = Field(default=5, ge=1, le=20)


@router.get("/series/{channel_id}")
async def list_series_suggestions_api(
    channel_id: str,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """シリーズ候補 + バズ動画 + サマリを返す。"""
    suggestions = analytics_store.list_series_suggestions(channel_id, status=status, limit=limit)
    detection = series_engine.detect_viral(channel_id)
    summary = series_engine.channel_summary(channel_id)
    # バズ動画ごとに候補を束ねる
    grouped: Dict[str, Dict[str, Any]] = {}
    for s in suggestions:
        vid = s.get("original_video_id") or "unknown"
        g = grouped.setdefault(vid, {
            "original_video_id": vid,
            "original_title": s.get("original_title"),
            "original_views": s.get("original_views"),
            "viral_ratio": s.get("viral_ratio"),
            "suggestions": [],
        })
        g["suggestions"].append(s)
    return {
        "channel_id": channel_id,
        "count": len(suggestions),
        "items": suggestions,
        "grouped": list(grouped.values()),
        "viral_videos": detection.get("viral", []),
        "channel_avg_views": detection.get("avg"),
        "summary": summary,
    }


@router.post("/series/{channel_id}/detect")
async def run_series_detection(
    channel_id: str,
    body: Optional[SeriesDetectRequest] = None,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    """バズ動画検出 → 続編候補生成を手動実行。"""
    opts = body or SeriesDetectRequest()
    lock = _lock(_series_locks, channel_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="series detection already running for this channel")
    try:
        return series_engine.detect_for_channel(
            channel_id,
            threshold=opts.threshold,
            max_viral=opts.max_viral,
        )
    finally:
        lock.release()


@router.post("/series/{channel_id}/approve/{suggestion_id}")
async def approve_series_suggestion(
    channel_id: str,
    suggestion_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    result = series_engine.approve_suggestion(channel_id, suggestion_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "approve failed")
    return result


@router.post("/series/{channel_id}/reject/{suggestion_id}")
async def reject_series_suggestion(
    channel_id: str,
    suggestion_id: str,
    _: Dict[str, Any] = Depends(require_session),
) -> Dict[str, Any]:
    result = series_engine.reject_suggestion(channel_id, suggestion_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "not found")
    return result
