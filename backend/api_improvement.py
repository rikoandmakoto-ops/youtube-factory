"""
YouTube Factory — Phase 6 API: いいね率改善ループ

機能:
  1. アップロード済み動画のいいね率取得（YouTube Data API or OAuth）
  2. いいね率が閾値（既定 3.0%）を下回った動画を検出して改善フィードバックを永続化
  3. 次回シナリオ生成時、main.py の factory_run / generate_scenario が自動で
     未消費フィードバックを `improvement_feedback` として GPT プロンプトに注入する
  4. APScheduler で日次自動チェック（Phase 4 のスケジューラを再利用）

エンドポイント (`/api/improvement/*`、 require_session 認証):
  - GET  /improvement/settings/{channel_id}
  - PUT  /improvement/settings/{channel_id}
  - POST /improvement/check/{channel_id}            — その場でチェック（即時実行）
  - POST /improvement/check-all                     — 全チャンネルをチェック
  - GET  /improvement/feedback/{channel_id}         — フィードバック一覧
  - POST /improvement/feedback/{video_id}/consume   — 手動で「反映済み」に
  - DELETE /improvement/feedback/{video_id}         — 削除
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_phase1 import _state, require_session
from pipeline.analytics import feedback_store, like_rate as lr


router = APIRouter(prefix="/api/improvement", tags=["phase6"])

PROJECT_ROOT = Path(__file__).parent.parent
PUBLISH_DB = PROJECT_ROOT / "data" / "video_publish.db"


# =====================================================================
# Helpers
# =====================================================================

def _published_videos_for_channel(channel_id: str) -> List[Dict[str, Any]]:
    """data/video_publish.db から「公開済み」video_id を取り出す。
    api_phase3 の video_status テーブルを再利用する。"""
    if not PUBLISH_DB.exists():
        return []
    conn = sqlite3.connect(str(PUBLISH_DB))
    try:
        rows = conn.execute(
            "SELECT job_id, video_id, status, url, published_at "
            "FROM video_status WHERE channel_id = ? AND video_id IS NOT NULL "
            "AND video_id != ''",
            (channel_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "job_id": r[0],
            "video_id": r[1],
            "status": r[2],
            "url": r[3],
            "published_at": r[4],
        }
        for r in rows
    ]


def _check_channel(
    channel_id: str,
    *,
    threshold_percent: Optional[float] = None,
    min_views: Optional[int] = None,
) -> Dict[str, Any]:
    """1チャンネルに対してチェックを実行。新規 / 更新フィードバックを返す。"""
    cm = _state.get("channel_manager")
    if cm is None:
        return {"error": "channel manager not ready", "channel_id": channel_id}
    ch = cm.get(channel_id)
    if not ch:
        return {"error": f"channel not found: {channel_id}", "channel_id": channel_id}

    threshold = (
        threshold_percent / 100.0
        if threshold_percent is not None
        else feedback_store.resolve_threshold_for_channel(ch)
    )
    minv = min_views if min_views is not None else feedback_store.resolve_min_views_for_channel(ch)

    published = _published_videos_for_channel(channel_id)
    video_ids = [p["video_id"] for p in published if p.get("video_id")]
    if not video_ids:
        return {
            "channel_id": channel_id,
            "checked": 0,
            "below_threshold": 0,
            "threshold_percent": threshold * 100.0,
            "min_views": minv,
            "items": [],
            "message": "公開済みの動画がまだありません",
        }

    stats = lr.fetch_video_stats(video_ids)
    if stats.get("source") == "none":
        return {
            "channel_id": channel_id,
            "checked": 0,
            "below_threshold": 0,
            "threshold_percent": threshold * 100.0,
            "min_views": minv,
            "items": [],
            "error": stats.get("error"),
        }

    job_by_video = {p["video_id"]: p.get("job_id") for p in published}
    low_items = lr.find_low_like_rate(stats["items"], threshold, min_views=minv)

    saved: List[Dict[str, Any]] = []
    for it in low_items:
        rec = feedback_store.save_feedback(
            video_id=it["video_id"],
            channel_id=channel_id,
            video_title=it.get("title"),
            views=it.get("views", 0),
            likes=it.get("likes", 0),
            like_rate=it.get("like_rate", 0.0),
            threshold=threshold,
            job_id=job_by_video.get(it["video_id"]),
        )
        saved.append(rec)

    return {
        "channel_id": channel_id,
        "checked": len(stats["items"]),
        "below_threshold": len(low_items),
        "threshold_percent": threshold * 100.0,
        "min_views": minv,
        "source": stats["source"],
        "missing": stats.get("missing", []),
        "items": [
            {
                "video_id": it.get("video_id"),
                "title": it.get("title"),
                "views": it.get("views"),
                "likes": it.get("likes"),
                "like_rate_percent": float(it.get("like_rate", 0.0)) * 100.0,
                "below_threshold": (
                    float(it.get("like_rate") or 0.0) < threshold
                    and int(it.get("views") or 0) >= minv
                    and not it.get("likes_hidden")
                ),
                "likes_hidden": bool(it.get("likes_hidden")),
            }
            for it in stats["items"]
        ],
        "saved_feedback": saved,
    }


# =====================================================================
# Settings
# =====================================================================

class ImprovementSettingsIn(BaseModel):
    like_rate_threshold_percent: float = Field(default=3.0, ge=0.0, le=100.0)
    min_views: int = Field(default=100, ge=0)
    auto_check_enabled: bool = True


@router.get("/settings/{channel_id}")
async def get_settings(channel_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    return feedback_store.get_settings(channel_id)


@router.put("/settings/{channel_id}")
async def put_settings(
    channel_id: str,
    req: ImprovementSettingsIn,
    _=Depends(require_session),
) -> Dict[str, Any]:
    return feedback_store.save_settings(
        channel_id=channel_id,
        like_rate_threshold_percent=req.like_rate_threshold_percent,
        min_views=req.min_views,
        auto_check_enabled=req.auto_check_enabled,
    )


# =====================================================================
# Manual check
# =====================================================================

class CheckRequest(BaseModel):
    threshold_percent: Optional[float] = None
    min_views: Optional[int] = None


@router.post("/check/{channel_id}")
async def check_channel(
    channel_id: str,
    req: Optional[CheckRequest] = None,
    _=Depends(require_session),
) -> Dict[str, Any]:
    req = req or CheckRequest()
    res = _check_channel(
        channel_id,
        threshold_percent=req.threshold_percent,
        min_views=req.min_views,
    )
    if res.get("error") and res.get("checked") == 0 and not res.get("source"):
        # 設定不備系は 400 で返す（API キー未設定など）
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.post("/check-all")
async def check_all_channels(_=Depends(require_session)) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    results: Dict[str, Any] = {}
    for ch in cm.list_channels():
        try:
            results[ch.id] = _check_channel(ch.id)
        except Exception as e:
            results[ch.id] = {"error": str(e)}
    return {"checked_at": int(time.time()), "results": results}


# =====================================================================
# Feedback CRUD
# =====================================================================

@router.get("/feedback/{channel_id}")
async def get_feedback(
    channel_id: str,
    pending_only: bool = False,
    limit: int = 100,
    _=Depends(require_session),
) -> Dict[str, Any]:
    items = feedback_store.list_feedback(
        channel_id=channel_id, pending_only=pending_only, limit=limit
    )
    return {
        "channel_id": channel_id,
        "pending_only": pending_only,
        "count": len(items),
        "items": items,
    }


class ConsumeBody(BaseModel):
    consumed_by_job_id: Optional[str] = None


@router.post("/feedback/{video_id}/consume")
async def consume_feedback(
    video_id: str,
    body: Optional[ConsumeBody] = None,
    _=Depends(require_session),
) -> Dict[str, Any]:
    body = body or ConsumeBody()
    n = feedback_store.mark_consumed([video_id], body.consumed_by_job_id)
    if n == 0:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"status": "consumed", "video_id": video_id}


@router.delete("/feedback/{video_id}")
async def delete_feedback(video_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    if not feedback_store.delete_feedback(video_id):
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"status": "deleted", "video_id": video_id}


# =====================================================================
# Pull pending feedback (used by main.py before scenario generation)
# =====================================================================

def pull_pending_feedback(channel_id: str) -> List[Dict[str, Any]]:
    """シナリオ生成側から呼ばれる: 未消費フィードバックを返す。
    （消費マークは生成成功後に呼び出し側で行う）"""
    return feedback_store.get_pending_for_channel(channel_id)


def mark_feedback_used(items: List[Dict[str, Any]], job_id: Optional[str]) -> int:
    if not items:
        return 0
    ids = [it.get("video_id") for it in items if it.get("video_id")]
    return feedback_store.mark_consumed(ids, job_id)


# =====================================================================
# 自動チェック (APScheduler — Phase 4 のスケジューラを再利用)
# =====================================================================

_AUTO_JOB_ID = "improvement:auto_check"
_auto_check_lock = threading.Lock()


def _auto_check_all() -> None:
    """全チャンネルを順次チェック。例外はチャンネル単位で握る。"""
    cm = _state.get("channel_manager")
    if cm is None:
        print("⚠️ improvement auto-check skipped: channel manager not ready")
        return
    for ch in cm.list_channels():
        s = feedback_store.get_settings(ch.id)
        if not s.get("auto_check_enabled", True):
            continue
        try:
            res = _check_channel(ch.id)
            below = res.get("below_threshold", 0)
            if below:
                print(
                    f"🔻 improvement auto-check [{ch.id}]: {below} 動画がいいね率閾値を下回りました"
                )
                # 通知（Phase 4）
                try:
                    from api_phase4 import notify_event

                    notify_event(
                        "schedule_run",
                        f"📉 改善ループ [{ch.id}]: {below} 件の低いいね率動画を検出。次回シナリオに反映予定。",
                    )
                except Exception:
                    pass
            else:
                print(f"✅ improvement auto-check [{ch.id}]: OK ({res.get('checked', 0)} 件)")
        except Exception as e:
            print(f"❌ improvement auto-check [{ch.id}] failed: {e}")


def setup_on_startup() -> None:
    """main.py の startup から呼ぶ。Phase 4 の scheduler に日次ジョブを差し込む。
    スケジューラ未準備（APScheduler 未インストール）の場合は no-op。"""
    try:
        from api_phase4 import _ensure_scheduler  # type: ignore
    except Exception as e:
        print(f"⚠️ improvement scheduler 未起動: {e}")
        return

    sch = _ensure_scheduler()
    if sch is None:
        print("⚠️ improvement scheduler 未起動（APScheduler 不在）")
        return

    try:
        from apscheduler.triggers.cron import CronTrigger  # type: ignore
    except Exception:
        return

    try:
        try:
            sch.remove_job(_AUTO_JOB_ID)
        except Exception:
            pass
        # JST 06:00 に毎日チェック
        trigger = CronTrigger(hour=6, minute=0, timezone="Asia/Tokyo")
        sch.add_job(
            _auto_check_all,
            trigger=trigger,
            id=_AUTO_JOB_ID,
            replace_existing=True,
        )
        print("⏰ improvement auto-check scheduled daily 06:00 JST")
    except Exception as e:
        print(f"⚠️ improvement scheduler add_job failed: {e}")


@router.post("/run-auto-check-now")
async def run_auto_check_now(_=Depends(require_session)) -> Dict[str, Any]:
    """テスト用: 自動チェックを即時実行（バックグラウンドスレッド）。"""
    if _auto_check_lock.locked():
        raise HTTPException(status_code=409, detail="Auto-check already running")

    def _wrapped() -> None:
        with _auto_check_lock:
            _auto_check_all()

    threading.Thread(target=_wrapped, daemon=True).start()
    return {"status": "triggered"}
