"""
SeriesEngine (Phase E-2) — バズった動画を検出 → Claude で続編パターンを分析 →
3 候補を `series_suggestions` に保存 → 承認時に theme_queue へ投入。

「バズった」= チャンネル平均視聴数の VIRAL_THRESHOLD (1.5) 倍以上。
通常 sync 直後 / 手動トリガで `detect_for_channel()` が走る。

続編パターン (series_type):
  - deep_dive: 同じトピックの深堀り（"なぜ" の更に奥）
  - contrast: 対比・比較（"逆の場合" / "他と何が違う"）
  - application: 応用・派生（"日常での使い方" / "別の現象に当てはめる"）
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import store as analytics_store


VIRAL_THRESHOLD = 1.5  # 平均の何倍で「バズ」とみなすか
MIN_AVG_BASE = 50      # 平均算出の最低サンプル views
MAX_VIRAL_PER_RUN = 5
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"


# ---------------------------------------------------------------------
# Average / detection
# ---------------------------------------------------------------------

def _channel_avg_views(metrics: List[Dict[str, Any]]) -> float:
    pool = [int(m.get("views") or 0) for m in metrics if int(m.get("views") or 0) >= MIN_AVG_BASE]
    if not pool:
        # 全動画の views 平均にフォールバック
        all_views = [int(m.get("views") or 0) for m in metrics]
        if not all_views:
            return 0.0
        return sum(all_views) / len(all_views)
    return sum(pool) / len(pool)


def detect_viral(channel_id: str, *, threshold: float = VIRAL_THRESHOLD) -> Dict[str, Any]:
    """video_metrics からバズ動画を抽出。"""
    metrics = analytics_store.list_video_metrics(channel_id, limit=200)
    if not metrics:
        return {"avg": 0.0, "threshold": threshold, "viral": []}
    avg = _channel_avg_views(metrics)
    if avg <= 0:
        return {"avg": 0.0, "threshold": threshold, "viral": []}
    cutoff = avg * threshold
    viral: List[Dict[str, Any]] = []
    for m in metrics:
        v = int(m.get("views") or 0)
        if v >= cutoff:
            viral.append({
                "video_id": m.get("video_id"),
                "title": m.get("title"),
                "views": v,
                "channel_avg": avg,
                "viral_ratio": v / avg if avg else 0.0,
                "published_at": m.get("published_at"),
            })
    viral.sort(key=lambda x: x["viral_ratio"], reverse=True)
    return {"avg": avg, "threshold": threshold, "viral": viral}


# ---------------------------------------------------------------------
# Scenario lookup
# ---------------------------------------------------------------------

def _scenario_summary(channel_id: str, video_title: Optional[str]) -> Optional[str]:
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
    first_lines: List[str] = []
    for ln in (data.get("full_scenario") or data.get("full") or [])[:6]:
        if isinstance(ln, dict) and ln.get("text"):
            first_lines.append(ln["text"][:120])
    parts = [angle] if angle else []
    if first_lines:
        parts.append(" / ".join(first_lines[:3]))
    return ("\n".join(parts))[:800] if parts else None


# ---------------------------------------------------------------------
# Claude suggestion
# ---------------------------------------------------------------------

def _suggest_with_claude(
    *,
    channel_id: str,
    channel_name: str,
    channel_concept: str,
    viral_title: str,
    viral_views: int,
    viral_ratio: float,
    scenario_summary: Optional[str],
) -> Optional[List[Dict[str, str]]]:
    try:
        from pipeline import claude_client
    except Exception:
        return None
    if not claude_client.has_api_key():
        return None
    user = (
        f"チャンネル名: {channel_name}\n"
        f"チャンネルコンセプト: {channel_concept}\n\n"
        f"以下の動画がチャンネル平均の {viral_ratio:.2f} 倍 ({viral_views:,} views) でバズりました:\n"
        f"  タイトル: {viral_title}\n"
        + (f"  要約: {scenario_summary}\n" if scenario_summary else "")
        + "\n"
        f"このバズ動画の **続編** として、3 つ異なるパターンで動画案を出してください。\n"
        f"パターンは必ず以下の 3 種類を 1 つずつ:\n"
        f"  - deep_dive: 元動画のトピックを更に深堀り（「なぜそうなる」の更に奥）\n"
        f"  - contrast: 対比・比較（逆の場合 / 他と何が違うか）\n"
        f"  - application: 応用・派生（別の現象に当てはめる / 日常での使い方）\n\n"
        f"出力 JSON: {{ \"suggestions\": [\n"
        f"  {{ \"series_type\": \"deep_dive\", \"title\": \"...\", \"angle\": \"...\","
        f" \"rationale\": \"なぜ続編が伸びるかの一言\" }}, ...\n"
        f"] }}\n"
        f"title は 40 字以内、視聴者がクリックしたくなる具体性のあるもの。"
    )
    system = (
        "あなたは YouTube チャンネル運営の編集ディレクター。"
        "バズ動画の余韻と検索流入を活かし、リピート視聴される続編を企画する。"
    )
    res = claude_client.call_claude_json(
        system=system, user=user,
        temperature=0.6, max_tokens=1500,
        channel_id=channel_id, purpose="series_suggest",
    )
    if not res or not isinstance(res, dict):
        return None
    suggestions = res.get("suggestions")
    if not isinstance(suggestions, list):
        return None
    out: List[Dict[str, str]] = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        title = (s.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "series_type": (s.get("series_type") or "").strip() or "deep_dive",
            "title": title[:120],
            "angle": (s.get("angle") or "").strip()[:300],
            "rationale": (s.get("rationale") or "").strip()[:300],
        })
    return out


def _core_topic(viral_title: str, limit: int = 26) -> str:
    """元動画タイトルから「話題の核」だけを取り出す。

    生タイトルをそのまま [:30] で切ると 【ショート】やハッシュタグを巻き込み、
    さらに文の途中でぶつ切りになる（例:「顔を奪う怪談はなぜ生まれた」）。
    装飾を落としたうえで、区切り文字の位置で自然に切る。
    """
    t = viral_title or "前回動画"
    t = re.sub(r"【[^】]*】|\[[^\]]*\]", "", t)          # 【ショート】等
    t = re.sub(r"[#＃][^\s#＃]*", "", t)                  # ハッシュタグ
    t = re.sub(r"^(一口SCP|1分[^：:]*|架空論文ファイル|30秒スレまとめ)\s*[：:]\s*", "", t)
    t = t.strip(" 　—-・")
    if not t:
        return "前回動画"
    if len(t) <= limit:
        return t
    # 区切り記号の直前で切る（見つからなければ限界長で切る）
    cut = max((t.rfind(ch, 0, limit + 1) for ch in "？?！!、。—・「」 　"), default=-1)
    return (t[:cut] if cut >= 8 else t[:limit]).strip(" 　—-・「」、")


def _fallback_suggestions(viral_title: str) -> List[Dict[str, str]]:
    """Claude 未設定時の決め打ち 3 候補。"""
    base = _core_topic(viral_title)
    return [
        {
            "series_type": "deep_dive",
            "title": f"「{base}」に隠された本当の理由を掘り下げる",
            "angle": "原理を更に掘り下げ、視聴者の「なぜ？」に答える",
            "rationale": "深堀り型はリテンションが高い",
        },
        {
            "series_type": "contrast",
            "title": f"「{base}」とは逆のパターンを比較してみた",
            "angle": "対比で違いを際立たせる構成",
            "rationale": "比較型は CTR が安定して取りやすい",
        },
        {
            "series_type": "application",
            "title": f"「{base}」の知識を日常で使う方法",
            "angle": "応用先を具体例で紹介",
            "rationale": "応用型は再生時間が伸びやすい",
        },
    ]


# ---------------------------------------------------------------------
# Main entrypoints
# ---------------------------------------------------------------------

def detect_for_channel(
    channel_id: str,
    *,
    threshold: float = VIRAL_THRESHOLD,
    max_viral: int = MAX_VIRAL_PER_RUN,
) -> Dict[str, Any]:
    """バズ動画検出 → Claude で続編候補生成 → series_suggestions に upsert。"""
    detection = detect_viral(channel_id, threshold=threshold)
    viral_videos = detection["viral"][:max_viral]
    if not viral_videos:
        return {
            "channel_id": channel_id,
            "channel_avg": detection["avg"],
            "threshold": threshold,
            "viral_count": 0,
            "suggestions_added": 0,
            "items": [],
        }

    try:
        from main import channel_manager  # type: ignore
    except Exception:
        channel_manager = None  # type: ignore
    ch = channel_manager.get(channel_id) if channel_manager else None
    channel_name = getattr(ch, "name", channel_id)
    channel_concept = getattr(ch, "concept", "")

    suggestions_added = 0
    items: List[Dict[str, Any]] = []

    for vv in viral_videos:
        # 既に承認 / 提案済みのものは再生成しない（pending か approved があれば skip）
        prev = analytics_store.list_series_for_original(channel_id, vv["video_id"])
        if any(p.get("status") in ("pending", "approved") for p in prev):
            items.append({**vv, "skipped": "already has suggestions"})
            continue

        summary = _scenario_summary(channel_id, vv.get("title"))
        sug = _suggest_with_claude(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_concept=channel_concept,
            viral_title=vv.get("title") or "",
            viral_views=int(vv.get("views") or 0),
            viral_ratio=float(vv.get("viral_ratio") or 0.0),
            scenario_summary=summary,
        )
        if sug is None or not sug:
            sug = _fallback_suggestions(vv.get("title") or "")

        added: List[Dict[str, Any]] = []
        for s in sug:
            sid = uuid.uuid4().hex[:10]
            analytics_store.upsert_series_suggestion(
                suggestion_id=sid,
                channel_id=channel_id,
                original_video_id=vv["video_id"],
                original_title=vv.get("title"),
                original_views=int(vv.get("views") or 0),
                channel_avg_views=int(detection["avg"]),
                viral_ratio=float(vv.get("viral_ratio") or 0.0),
                series_type=s["series_type"],
                suggested_title=s["title"],
                suggested_angle=s.get("angle"),
                rationale=s.get("rationale"),
                status="pending",
            )
            added.append({"id": sid, **s})
            suggestions_added += 1
        items.append({**vv, "suggestions": added})

    return {
        "channel_id": channel_id,
        "channel_avg": detection["avg"],
        "threshold": threshold,
        "viral_count": len(viral_videos),
        "suggestions_added": suggestions_added,
        "items": items,
        "ran_at": int(time.time()),
    }


def approve_suggestion(channel_id: str, suggestion_id: str) -> Dict[str, Any]:
    """承認 → theme_queue に投入 → status=approved。"""
    s = analytics_store.get_series_suggestion(suggestion_id)
    if not s or s.get("channel_id") != channel_id:
        return {"ok": False, "error": "suggestion not found"}
    if s.get("status") == "approved":
        return {"ok": True, "already": True}

    try:
        import api_channel_autopilot as autopilot_api
    except Exception as e:
        return {"ok": False, "error": f"autopilot api unavailable: {e}"}

    try:
        ap = autopilot_api._load_autopilot(channel_id)
    except Exception as e:
        return {"ok": False, "error": f"load autopilot failed: {e}"}

    title = s["suggested_title"]
    angle = s.get("suggested_angle") or ""
    existing_titles = {t.get("title") for t in (ap.get("theme_queue") or [])}
    if title in existing_titles:
        analytics_store.update_series_status(suggestion_id, "approved")
        return {"ok": True, "already_in_queue": True, "title": title}

    theme_id = autopilot_api._new_theme_id()
    item = {
        "id": theme_id,
        "title": title.strip()[:120],
        "angle": (angle or "").strip()[:300],
        "priority": "normal",
        "source": "series_engine",
        "series_type": s.get("series_type"),
        "from_video_id": s.get("original_video_id"),
    }
    ap["theme_queue"] = list(ap.get("theme_queue") or []) + [item]
    try:
        autopilot_api._save_autopilot(channel_id, ap)
    except Exception as e:
        return {"ok": False, "error": f"save autopilot failed: {e}"}

    analytics_store.update_series_status(
        suggestion_id, "approved", queue_theme_id=theme_id
    )
    return {"ok": True, "theme_id": theme_id, "title": title}


def reject_suggestion(channel_id: str, suggestion_id: str) -> Dict[str, Any]:
    s = analytics_store.get_series_suggestion(suggestion_id)
    if not s or s.get("channel_id") != channel_id:
        return {"ok": False, "error": "suggestion not found"}
    analytics_store.update_series_status(suggestion_id, "rejected")
    return {"ok": True}


# ---------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------

def channel_summary(channel_id: str) -> Dict[str, Any]:
    """UI 用に「シリーズ全体のパフォーマンス」サマリを返す。"""
    metrics = analytics_store.list_video_metrics(channel_id, limit=500)
    avg = _channel_avg_views(metrics)
    all_suggestions = analytics_store.list_series_suggestions(channel_id, limit=500)
    by_status: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    spinoffs: List[Dict[str, Any]] = []
    for s in all_suggestions:
        st = s.get("status") or "pending"
        by_status[st] = by_status.get(st, 0) + 1
        t = s.get("series_type") or "unknown"
        by_type[t] = by_type.get(t, 0) + 1
        if st == "approved" and s.get("queued_video_id"):
            spinoffs.append(s)
    return {
        "channel_id": channel_id,
        "channel_avg_views": avg,
        "total_suggestions": len(all_suggestions),
        "by_status": by_status,
        "by_type": by_type,
        "approved_with_video": len(spinoffs),
    }
