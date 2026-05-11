"""
低 CTR 動画の自動改善キュー (Phase D — C)

仕組み:
  1. チャンネル平均 CTR を算出
  2. 平均 CTR の 80% 未満を「要改善」として検出
  3. ab_test_generator を再利用して新キャッチコピー・タイトルを 3 パターン生成
  4. analytics.db.improvement_queue に upsert

公開関数:
  - detect_and_queue(channel_id, *, threshold_ratio=0.8, max_videos=20, regen_titles=True)
  - regenerate_for_video(channel_id, video_id, *, regen=True)
  - channel_avg_ctr(channel_id) -> Optional[float]
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import store as analytics_store

try:
    from pipeline import ab_test_generator
except Exception:  # pragma: no cover
    ab_test_generator = None  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"


def channel_avg_ctr(channel_id: str, *, min_views: int = 100) -> Optional[float]:
    """過去の動画から CTR の平均値を計算。views フィルタで初動の弱い動画を除外。"""
    items = analytics_store.list_video_metrics(channel_id, limit=200)
    pool = [
        float(m.get("ctr") or 0.0)
        for m in items
        if int(m.get("views") or 0) >= min_views and (m.get("ctr") or 0) > 0
    ]
    if not pool:
        return None
    return sum(pool) / len(pool)


def _scenario_summary_for(channel_id: str, video_title: Optional[str]) -> Optional[str]:
    if not video_title:
        return None
    base = SCENARIOS_DIR / channel_id
    if not base.exists():
        return None
    norm = "".join(c for c in video_title.lower() if c.isalnum() or c > "　")
    best: Optional[Path] = None
    best_score = 0.0
    for f in base.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        cand = (data.get("video_title") or data.get("title") or "").lower()
        cand_norm = "".join(c for c in cand if c.isalnum() or c > "　")
        if not cand_norm:
            continue
        shared = 0
        for n in range(3, min(len(norm), len(cand_norm)) + 1):
            if norm[:n] in cand_norm or cand_norm[:n] in norm:
                shared = n
        score = shared / max(len(norm), len(cand_norm), 1)
        if score > best_score and score > 0.4:
            best_score = score
            best = f
    if best is None:
        return None
    try:
        data = json.loads(best.read_text(encoding="utf-8"))
    except Exception:
        return None
    angle = (data.get("theme") or {}).get("angle") or ""
    first_lines = []
    for ln in (data.get("full_scenario") or data.get("full") or [])[:6]:
        if isinstance(ln, dict) and ln.get("text"):
            first_lines.append(ln["text"][:90])
    summary = angle
    if first_lines:
        summary = (summary + "\n" if summary else "") + " / ".join(first_lines[:3])
    return summary[:600] if summary else None


def regenerate_for_video(
    channel_id: str,
    video_id: str,
    *,
    regen: bool = True,
    threshold_ratio: float = 0.8,
) -> Dict[str, Any]:
    """1 動画に対してキャッチコピー再生成を実行。"""
    metrics = analytics_store.list_video_metrics(channel_id, limit=500)
    metric = next((m for m in metrics if m.get("video_id") == video_id), None)
    if not metric:
        return {"video_id": video_id, "error": "metric_not_found"}

    current_title = metric.get("title")
    current_ctr = float(metric.get("ctr") or 0.0)
    avg_ctr = channel_avg_ctr(channel_id) or 0.0
    threshold = avg_ctr * threshold_ratio

    catchcopies: List[Dict[str, Any]] = []
    suggested_titles: List[str] = []
    predicted_improvement: Optional[float] = None

    if regen and ab_test_generator is not None:
        try:
            summary = _scenario_summary_for(channel_id, current_title)
            ab = ab_test_generator.generate_ab_test(
                current_title or "",
                "",
                channel_id=channel_id,
                scenario_summary=summary,
                save=True,
            )
            for v in ab.get("variants") or []:
                catchcopies.append({
                    "pattern": v.get("pattern"),
                    "title": v.get("title"),
                    "thumb_copy": v.get("thumb_copy"),
                    "score": v.get("score"),
                    "comment": v.get("comment"),
                })
                if v.get("title"):
                    suggested_titles.append(v["title"])
            best = ab.get("best") or {}
            best_score = float(best.get("score") or 0.0)
            # 予測スコア (1-10) を CTR 改善見込み (%) に粗く写像
            # 仮: score 8 = +30%、score 5 = +10%、score < 5 = +5%
            if best_score >= 8:
                predicted_improvement = 30.0
            elif best_score >= 7:
                predicted_improvement = 20.0
            elif best_score >= 6:
                predicted_improvement = 12.0
            elif best_score >= 5:
                predicted_improvement = 8.0
            elif best_score > 0:
                predicted_improvement = 5.0
        except Exception as e:
            print(f"⚠️ regenerate_for_video {video_id} ab_test failed: {e}")

    rec = analytics_store.upsert_improvement_entry(
        video_id=video_id,
        channel_id=channel_id,
        current_title=current_title,
        current_ctr=current_ctr,
        channel_avg_ctr=avg_ctr,
        suggested_titles=suggested_titles,
        suggested_catchcopies=catchcopies,
        predicted_improvement=predicted_improvement,
        status="pending",
    )
    rec["threshold_ctr"] = threshold
    return rec


def detect_and_queue(
    channel_id: str,
    *,
    threshold_ratio: float = 0.8,
    max_videos: int = 20,
    regen_titles: bool = True,
    min_views: int = 100,
) -> Dict[str, Any]:
    """チャンネル平均 CTR の `threshold_ratio` 未満の動画を検出してキューに積む。"""
    avg = channel_avg_ctr(channel_id, min_views=min_views)
    if avg is None:
        return {
            "channel_id": channel_id,
            "skipped": True,
            "reason": "no_videos_with_ctr",
            "channel_avg_ctr": None,
        }
    threshold = avg * threshold_ratio
    items = analytics_store.list_video_metrics(channel_id, limit=200)
    candidates = [
        m for m in items
        if int(m.get("views") or 0) >= min_views
        and (m.get("ctr") or 0.0) > 0
        and float(m.get("ctr") or 0.0) < threshold
    ]
    # views が多くて潜在ある順
    candidates.sort(key=lambda m: int(m.get("views") or 0), reverse=True)
    candidates = candidates[:max_videos]

    queued: List[Dict[str, Any]] = []
    for m in candidates:
        vid = m.get("video_id")
        if not vid:
            continue
        try:
            rec = regenerate_for_video(
                channel_id,
                vid,
                regen=regen_titles,
                threshold_ratio=threshold_ratio,
            )
            queued.append(rec)
        except Exception as e:
            queued.append({"video_id": vid, "error": str(e)})

    return {
        "channel_id": channel_id,
        "channel_avg_ctr": avg,
        "threshold_ctr": threshold,
        "threshold_percent": threshold_ratio * 100.0,
        "candidates_found": len(candidates),
        "queued": queued,
        "ran_at": int(time.time()),
    }
