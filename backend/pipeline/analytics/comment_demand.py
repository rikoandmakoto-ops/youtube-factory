"""
CommentDemand (Phase F-2) — 視聴者コメントからの需要発掘。

「○○やってほしい」「○○が気になる」「なんで○○なの？」系のリクエスト/質問を
Claude で抽出し、頻度・いいね数・チャンネル適合度でスコアリングして
theme_queue へ「視聴者リクエスト」として投入する。

入力:
  - `comment_analysis` テーブル（既に youtube_comments.py が貯めている）
    is_request=1 / sentiment=request のものを優先的に取り出す

出力:
  - `comment_demands` テーブルに保存
  - 高スコアは theme_queue へ自動投入（source="comment_demand", priority=high）

公開関数:
  - scan_channel(channel_id, *, since_days=30, auto_queue=True)
  - queue_demand(channel_id, demand_id)
  - dismiss_demand(channel_id, demand_id)
  - scan_all_channels()
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from . import store as analytics_store


AUTO_QUEUE_THRESHOLD = 0.7  # combined score 上限 1.0 想定
MAX_AUTO_QUEUE_PER_SCAN = 3
MAX_DEMANDS_RETURNED = 40
MAX_COMMENTS_INPUT = 300


# ---------------------------------------------------------------------
# Theme queue helper
# ---------------------------------------------------------------------

def _queue_theme(channel_id: str, title: str, angle: str, *, priority_high: bool = True) -> Optional[str]:
    try:
        import api_channel_autopilot as autopilot_api
    except Exception:
        return None
    try:
        ap = autopilot_api._load_autopilot(channel_id)
    except Exception:
        return None
    theme_id = autopilot_api._new_theme_id()
    item = {
        "id": theme_id,
        "title": title.strip()[:120],
        "angle": (angle or "").strip()[:300],
        "priority": "high" if priority_high else "normal",
        "source": "comment_demand",
    }
    queue = list(ap.get("theme_queue") or [])
    existing_titles = {t.get("title") for t in queue}
    if item["title"] in existing_titles:
        return None
    if priority_high:
        queue.insert(0, item)
    else:
        queue.append(item)
    ap["theme_queue"] = queue
    try:
        autopilot_api._save_autopilot(channel_id, ap)
    except Exception:
        return None
    return theme_id


# ---------------------------------------------------------------------
# Claude extractor
# ---------------------------------------------------------------------

def _build_extract_prompt(
    *,
    channel_name: str,
    concept: str,
    seeds: List[str],
    comments: List[Dict[str, Any]],
) -> str:
    seed_block = "、".join(seeds[:10]) if seeds else "（未設定）"
    lines = []
    for i, c in enumerate(comments):
        text = (c.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        lines.append(
            f"{i}: [likes={c.get('like_count', 0)}] {text[:200]}"
        )
    blob = "\n".join(lines)
    return (
        f"チャンネル: {channel_name}\n"
        f"コンセプト: {concept}\n"
        f"代表テーマ: {seed_block}\n\n"
        f"以下は視聴者コメントです。リクエスト系（「○○やってほしい」「○○の動画見たい」「○○について教えて」）"
        f"と質問系（「なんで○○なの？」「○○ってどうなってる？」）をクラスタリングして、\n"
        f"重複や言い換えを束ねて1つの需要として出してください。\n\n"
        f"コメント一覧:\n{blob}\n\n"
        f"以下を JSON で:\n"
        f"{{\n"
        f"  \"demands\": [\n"
        f"    {{\n"
        f"      \"demand_text\": \"○○を解説してほしい\",  // 短い日本語、最大 80 文字\n"
        f"      \"demand_type\": \"request\" | \"question\",\n"
        f"      \"source_indices\": [<元コメントの index>, ...],\n"
        f"      \"relevance\": 0.0〜1.0,  // チャンネルコンセプトとの適合度\n"
        f"      \"suggested_title\": \"動画タイトル案\",\n"
        f"      \"suggested_angle\": \"切り口の要約\",\n"
        f"      \"rationale\": \"なぜ伸びそうかを 1 文で\"\n"
        f"    }}, ...\n"
        f"  ]\n"
        f"}}\n"
        f"似た要望は1つの demand に束ねること。チャンネルと無関係なものや雑談は無視。"
        f"必ず JSON オブジェクトのみを返してください。"
    )


def _classify_request_or_question_local(text: str) -> Optional[str]:
    """Claude 未設定時の超ライトな振り分け。"""
    if not text:
        return None
    t = text.lower()
    if any(k in t for k in ("やってほしい", "見たい", "教えて", "解説して", "扱って", "聞きたい")):
        return "request"
    if any(k in t for k in ("なんで", "なぜ", "どうして", "どうなって", "って何", "とは")) or "?" in text or "？" in text:
        return "question"
    return None


def _fallback_extract(
    comments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Claude 未設定時の簡易抽出: いいね多い順に request/question を取り出す。"""
    out: List[Dict[str, Any]] = []
    for i, c in enumerate(comments[:50]):
        text = (c.get("text") or "").strip()
        if not text:
            continue
        cls = _classify_request_or_question_local(text)
        if not cls:
            continue
        out.append({
            "demand_text": text[:80],
            "demand_type": cls,
            "source_indices": [i],
            "relevance": 0.4,
            "suggested_title": text[:80],
            "suggested_angle": "",
            "rationale": "Claude API 未設定 — 簡易抽出",
        })
    return out


def _extract_with_claude(
    *,
    channel_id: str,
    channel_name: str,
    concept: str,
    seeds: List[str],
    comments: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    try:
        from pipeline import claude_client
    except Exception:
        return None
    if not claude_client.has_api_key():
        return None
    if not comments:
        return []
    system = (
        "あなたは YouTube チャンネルのリサーチアシスタント。"
        "視聴者コメントから「次に作るべき動画のヒント」になるリクエスト / 質問を抽出し、"
        "ノイズを除いてクラスタリングする。"
    )
    user = _build_extract_prompt(
        channel_name=channel_name,
        concept=concept,
        seeds=seeds,
        comments=comments,
    )
    res = claude_client.call_claude_json(
        system=system, user=user,
        temperature=0.3, max_tokens=3000,
        channel_id=channel_id, purpose="comment_demand_extraction",
    )
    if not res or not isinstance(res, dict):
        return None
    demands = res.get("demands")
    if not isinstance(demands, list):
        return None
    return [d for d in demands if isinstance(d, dict)]


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def _demand_id_for(channel_id: str, demand_text: str) -> str:
    h = hashlib.sha1(f"{channel_id}::{demand_text}".encode("utf-8")).hexdigest()
    return h[:12]


def _score(*, frequency: int, total_likes: int, relevance: float) -> float:
    """3 軸からまとめスコア (0..1)。
    frequency / likes は log1p で潰し、各 0..1 に押し込んでから加重平均。"""
    import math
    freq_n = min(1.0, math.log1p(frequency) / math.log(10))   # 1→0, 10→1
    likes_n = min(1.0, math.log1p(total_likes) / math.log(200))
    rel_n = max(0.0, min(1.0, relevance))
    return round(0.30 * freq_n + 0.30 * likes_n + 0.40 * rel_n, 3)


def scan_channel(
    channel_id: str,
    *,
    since_days: int = 30,
    max_comments: int = MAX_COMMENTS_INPUT,
    auto_queue: bool = True,
) -> Dict[str, Any]:
    """チャンネルのコメント DB からリクエスト系を抽出して保存 → 高スコアは自動キュー。"""
    started_at = int(time.time())
    since_ts: Optional[int] = None
    if since_days and since_days > 0:
        since_ts = int(time.time()) - int(since_days) * 86400

    request_comments = analytics_store.list_request_comments(
        channel_id, since_ts=since_ts, limit=max_comments
    )
    # request コメントだけだと少ない場合、全コメントから拾う
    if len(request_comments) < 10:
        all_comments: List[Dict[str, Any]] = []
        # 直接 DB から取る代わりに、簡易に list_comments_for_video を使うのは
        # 全 video_id を回らないと面倒なので、まずは request コメントのみで進める。
        # （フォールバック: classification heuristics は extract 側でも掛ける）
    # 重複テキスト削減
    seen_text = set()
    unique_comments: List[Dict[str, Any]] = []
    for c in request_comments:
        t = (c.get("text") or "").strip()
        key = t[:120]
        if not key or key in seen_text:
            continue
        seen_text.add(key)
        unique_comments.append(c)

    # チャンネルプロファイル
    try:
        from main import channel_manager  # type: ignore
    except Exception:
        channel_manager = None
    ch = channel_manager.get(channel_id) if channel_manager else None
    channel_name = getattr(ch, "name", channel_id)
    concept = getattr(ch, "concept", "")
    seeds: List[str] = []
    for s in getattr(ch, "theme_seeds", []) or []:
        if isinstance(s, dict):
            t = s.get("title") or s.get("keyword") or s.get("angle")
            if t:
                seeds.append(str(t))
        elif isinstance(s, str):
            seeds.append(s)

    extracted: List[Dict[str, Any]] = []
    if unique_comments:
        claude_res = _extract_with_claude(
            channel_id=channel_id,
            channel_name=channel_name,
            concept=concept,
            seeds=seeds,
            comments=unique_comments,
        )
        if claude_res is None:
            extracted = _fallback_extract(unique_comments)
        else:
            extracted = claude_res

    saved_count = 0
    auto_queued_count = 0
    items_out: List[Dict[str, Any]] = []

    for d in extracted[:MAX_DEMANDS_RETURNED]:
        demand_text = (d.get("demand_text") or "").strip()
        if not demand_text:
            continue
        demand_type = (d.get("demand_type") or "request").lower()
        if demand_type not in ("request", "question"):
            demand_type = "request"

        # 元コメントを索引
        src_idx = d.get("source_indices") or []
        if not isinstance(src_idx, list):
            src_idx = []
        source_comments: List[Dict[str, Any]] = []
        for ix in src_idx:
            try:
                ix_int = int(ix)
                if 0 <= ix_int < len(unique_comments):
                    source_comments.append(unique_comments[ix_int])
            except Exception:
                continue
        frequency = max(1, len(source_comments))
        total_likes = sum(int(c.get("like_count") or 0) for c in source_comments)

        relevance = float(d.get("relevance") or 0.0)
        score = _score(
            frequency=frequency, total_likes=total_likes, relevance=relevance
        )

        suggested_title = (d.get("suggested_title") or demand_text)[:120]
        suggested_angle = (d.get("suggested_angle") or "")[:300]
        rationale = (d.get("rationale") or "")[:400]

        demand_id = _demand_id_for(channel_id, demand_text)

        # 既存と重複なら status を維持しつつスコアを更新
        existing = analytics_store.find_existing_demand(channel_id, demand_text)
        if existing:
            demand_id = existing["id"]
            # 既に dismiss されていれば再度上げない
            if existing.get("status") == "dismissed":
                continue

        # 自動キュー判定
        queue_theme_id: Optional[str] = None
        do_auto = (
            auto_queue
            and score >= AUTO_QUEUE_THRESHOLD
            and auto_queued_count < MAX_AUTO_QUEUE_PER_SCAN
            and bool(suggested_title)
            and (not existing or existing.get("status") not in ("queued", "auto_queued"))
        )
        if do_auto:
            queue_theme_id = _queue_theme(
                channel_id, suggested_title, suggested_angle, priority_high=True
            )
            if queue_theme_id:
                auto_queued_count += 1

        status = "auto_queued" if queue_theme_id else (existing.get("status") if existing else "pending")
        analytics_store.upsert_comment_demand(
            demand_id=demand_id,
            channel_id=channel_id,
            video_id=(source_comments[0].get("video_id") if source_comments else None),
            comment_ids=[c.get("comment_id") for c in source_comments if c.get("comment_id")],
            demand_text=demand_text,
            demand_type=demand_type,
            frequency=frequency,
            total_likes=total_likes,
            relevance_score=relevance,
            score=score,
            suggested_title=suggested_title,
            suggested_angle=suggested_angle,
            rationale=rationale,
            status=status or "pending",
            queue_theme_id=queue_theme_id,
            auto_queued=bool(queue_theme_id),
        )
        saved_count += 1
        items_out.append({
            "demand_id": demand_id,
            "demand_text": demand_text,
            "demand_type": demand_type,
            "frequency": frequency,
            "total_likes": total_likes,
            "relevance_score": relevance,
            "score": score,
            "suggested_title": suggested_title,
            "status": status,
            "auto_queued": bool(queue_theme_id),
        })

    return {
        "ok": True,
        "channel_id": channel_id,
        "started_at": started_at,
        "finished_at": int(time.time()),
        "request_comments_considered": len(unique_comments),
        "demands_saved": saved_count,
        "auto_queued": auto_queued_count,
        "items": items_out,
    }


def queue_demand(channel_id: str, demand_id: str) -> Dict[str, Any]:
    rec = analytics_store.get_comment_demand(demand_id)
    if not rec or rec.get("channel_id") != channel_id:
        return {"ok": False, "error": "demand not found"}
    title = rec.get("suggested_title") or rec.get("demand_text") or ""
    angle = rec.get("suggested_angle") or rec.get("rationale") or ""
    if not title:
        return {"ok": False, "error": "no title to queue"}
    theme_id = _queue_theme(channel_id, title, angle, priority_high=True)
    if not theme_id:
        return {"ok": False, "error": "failed to queue (duplicate or save error)"}
    analytics_store.update_comment_demand_status(
        demand_id, "queued", queue_theme_id=theme_id
    )
    return {"ok": True, "theme_id": theme_id, "title": title}


def dismiss_demand(channel_id: str, demand_id: str) -> Dict[str, Any]:
    rec = analytics_store.get_comment_demand(demand_id)
    if not rec or rec.get("channel_id") != channel_id:
        return {"ok": False, "error": "demand not found"}
    analytics_store.update_comment_demand_status(demand_id, "dismissed")
    return {"ok": True}


def scan_all_channels(*, auto_queue: bool = True) -> Dict[str, Any]:
    """全チャンネル分のコメント需要スキャン（scheduler 用）。"""
    try:
        from main import channel_manager  # type: ignore
    except Exception:
        return {"ok": False, "error": "channel_manager not available"}
    if channel_manager is None:
        return {"ok": False, "error": "channel_manager not available"}

    results: List[Dict[str, Any]] = []
    try:
        channels = channel_manager.list_channels()
    except Exception as e:
        return {"ok": False, "error": f"list channels failed: {e}"}

    for ch in channels:
        cid = getattr(ch, "id", None)
        if not cid:
            continue
        try:
            r = scan_channel(cid, auto_queue=auto_queue)
            results.append({
                "channel_id": cid,
                "demands_saved": r.get("demands_saved", 0),
                "auto_queued": r.get("auto_queued", 0),
            })
        except Exception as e:
            results.append({"channel_id": cid, "error": str(e)})
    return {"ok": True, "ran_at": int(time.time()), "results": results}
