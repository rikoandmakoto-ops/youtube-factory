"""
TrendScanner (Phase E-1) — Google Trends / News / YouTube 急上昇を 6h ごとにスキャンし、
チャンネル適合度の高いキーワードを `trend_detections` に保存 → 高スコアは theme_queue に自動投入。

ソース:
  1. Google Trends（pytrends） — `trend_fetcher.fetch_google_trends`
  2. NewsAPI.org — NEWSAPI_KEY が設定されていれば、科学・テクノロジー系トピックを取得
  3. YouTube 急上昇（教育/科学） — 既存 `trend_fetcher.fetch_youtube_trending`

スコアリング:
  - trend_score: ソース由来（pytrends: ランキング順、NewsAPI: relevance / 新しさ）
  - relevance_score: Claude (claude_client) でチャンネルコンセプトとの適合度を 0..1 採点
                      Claude 未設定時はキーワードと既存 `theme_seeds` の語彙重なりでフォールバック
  - combined_score = 0.4*trend_score + 0.6*relevance_score
  - combined_score >= AUTO_QUEUE_THRESHOLD (0.7) のものは theme_queue に自動投入 (auto_queued=1)

依存: api_channel_autopilot._load_autopilot / _save_autopilot を使って theme_queue を編集。
失敗時はクラッシュさせず、空結果＋エラー文字列を返す（呼び出し側で history に書く）。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import store as analytics_store


AUTO_QUEUE_THRESHOLD = 0.7
MAX_AUTO_QUEUE_PER_SCAN = 3
MAX_DETECTIONS_PER_SOURCE = 15


# ---------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------

def _fetch_google_trends() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        from pipeline.trend_fetcher import fetch_google_trends
    except Exception as e:
        return [], f"trend_fetcher import failed: {e}"
    res = fetch_google_trends() or {}
    trends: List[str] = res.get("trends") or []
    if not trends:
        return [], res.get("error")
    out: List[Dict[str, Any]] = []
    n = min(len(trends), MAX_DETECTIONS_PER_SOURCE)
    for i, kw in enumerate(trends[:n]):
        rank_score = 1.0 - (i / max(n, 1)) * 0.5  # top=1.0, bottom=0.5
        out.append({
            "keyword": str(kw).strip(),
            "source": "google_trends",
            "trend_score": round(rank_score, 3),
            "raw": {"rank": i, "region": res.get("region")},
        })
    return out, None


def _fetch_news_api(query_topics: List[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """NewsAPI.org の無料枠で科学・テクノロジー系トピックを取得。

    NEWSAPI_KEY が無ければ everything endpoint は使えないため、無料枠の
    `top-headlines?category=science|technology&country=jp` をフォールバックで叩く。
    """
    api_key = (os.environ.get("NEWSAPI_KEY") or os.environ.get("NEWS_API_KEY") or "").strip()
    if not api_key:
        return [], "NEWSAPI_KEY not set"

    out: List[Dict[str, Any]] = []
    errors: List[str] = []

    # 1) top-headlines (jp, science / technology)
    for category in ("science", "technology"):
        params = {
            "country": "jp",
            "category": category,
            "pageSize": 10,
            "apiKey": api_key,
        }
        url = f"https://newsapi.org/v2/top-headlines?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "youtube-factory/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            errors.append(f"{category}: {type(e).__name__}")
            continue
        articles = data.get("articles") or []
        n = min(len(articles), 8)
        for i, art in enumerate(articles[:n]):
            title = (art.get("title") or "").strip()
            if not title or "[Removed]" in title:
                continue
            # 媒体名サフィックスを削る
            for sep in (" - ", " | ", "｜"):
                if sep in title:
                    title = title.split(sep)[0].strip()
            if not title:
                continue
            freshness = 1.0 - (i / max(n, 1)) * 0.4  # top=1.0
            out.append({
                "keyword": title[:80],
                "source": "news_api",
                "trend_score": round(freshness, 3),
                "raw": {
                    "category": category,
                    "url": art.get("url"),
                    "source_name": (art.get("source") or {}).get("name"),
                    "published_at": art.get("publishedAt"),
                    "description": (art.get("description") or "")[:200],
                },
            })

    if not out and errors:
        return [], "; ".join(errors)
    return out[:MAX_DETECTIONS_PER_SOURCE], None


def _fetch_youtube_trending() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        from pipeline.trend_fetcher import fetch_youtube_trending
    except Exception as e:
        return [], f"trend_fetcher import failed: {e}"
    res = fetch_youtube_trending() or {}
    # fetch_youtube_trending が返すキーは "videos"。ここが "items" になっていたため
    # 取得は成功しているのに常に 0 件と判定され、trend_detections が
    # 984 回のスキャンで 1 件も入らないまま機能が死んでいた（2026-08-19 修正）。
    items = res.get("videos") or []
    if not items:
        return [], res.get("error")
    out: List[Dict[str, Any]] = []
    n = min(len(items), MAX_DETECTIONS_PER_SOURCE)
    for i, it in enumerate(items[:n]):
        title = (it.get("title") or "").strip()
        if not title:
            continue
        rank_score = 1.0 - (i / max(n, 1)) * 0.5
        out.append({
            "keyword": title[:80],
            "source": "youtube_trending",
            "trend_score": round(rank_score, 3),
            "raw": {
                "video_id": it.get("video_id"),
                "channel": it.get("channel_title"),
                "views": it.get("views"),
                "tags": (it.get("tags") or [])[:8],
            },
        })
    return out, None


# ---------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------

def _fallback_relevance(keyword: str, seeds: List[str]) -> float:
    """Claude 未設定時の簡易フォールバック: シードキーワードとの語彙重なり。"""
    if not keyword:
        return 0.0
    kw = keyword.lower()
    # シードが空でも科学系チャンネルが多いので、安全側 0.4 を底に
    base = 0.35
    if not seeds:
        return base
    hits = 0
    for s in seeds:
        s = (s or "").lower().strip()
        if not s:
            continue
        if s in kw or kw in s:
            hits += 1
    return min(1.0, base + 0.15 * hits)


def _score_via_claude(system: str, user: str, channel_id: str) -> Optional[Dict[str, Any]]:
    try:
        from pipeline import claude_client
    except Exception:
        return None
    if not claude_client.has_api_key():
        return None
    try:
        return claude_client.call_claude_json(
            system=system, user=user,
            temperature=0.4, max_tokens=2500,
            channel_id=channel_id, purpose="trend_relevance",
        )
    except Exception:
        return None


# GPT フォールバック用。軽量モデルで十分（採点とタイトル案の生成のみ）。
_GPT_SCORING_MODEL = os.environ.get("TREND_SCORING_MODEL", "gpt-4o-mini")
_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


def _score_via_gpt(system: str, user: str, channel_id: str) -> Optional[Dict[str, Any]]:
    """Claude が使えないときの採点バックエンド。"""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from pipeline import openai_compat
    except Exception:
        return None

    payload = openai_compat.build_chat_payload(
        _GPT_SCORING_MODEL,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
        max_tokens=2500,
        response_format={"type": "json_object"},
    )
    req = urllib.request.Request(
        _OPENAI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"⚠️ trend relevance GPT fallback failed: {e}")
        return None

    try:
        from pipeline import api_usage
        usage = data.get("usage", {}) or {}
        api_usage.record_chat_usage(
            model=_GPT_SCORING_MODEL,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            channel_id=channel_id,
            purpose="trend_relevance",
        )
    except Exception:
        pass

    try:
        return json.loads(data["choices"][0]["message"]["content"])
    except Exception:
        return None


def _build_scoring_prompt(
    candidates: List[Dict[str, Any]],
    *,
    channel_name: str,
    channel_concept: str,
    seeds: List[str],
) -> Tuple[str, str]:
    """relevance 採点用の (system, user) プロンプトを組み立てる。

    Claude / GPT どちらのバックエンドでも同じ基準で採点させるため、
    プロンプトは1か所で持つ。
    """
    lines = []
    for i, c in enumerate(candidates):
        lines.append(f"{i}: {c.get('keyword')}  [source={c.get('source')}]")
    user = (
        f"チャンネル名: {channel_name}\n"
        f"チャンネルコンセプト: {channel_concept}\n"
        f"代表的なテーマ例: {', '.join(seeds[:8]) if seeds else 'なし'}\n\n"
        f"以下は今のトレンドキーワード/ニュース見出しです。\n"
        f"各候補について、このチャンネル「日常の疑問を科学視点で解説」スタイルで\n"
        f"動画化したらどれくらい伸びそうかを 0.0〜1.0 で採点し、\n"
        f"採用するなら付ける動画タイトル案と切り口を 1 行ずつ作ってください。\n\n"
        f"候補:\n" + "\n".join(lines) + "\n\n"
        f"出力は JSON: {{ \"scores\": [ {{ \"index\": 0, \"relevance\": 0.0〜1.0, "
        f"\"title\": \"...\", \"angle\": \"...\", \"reason\": \"短い日本語\" }}, ... ] }}\n"
        f"relevance は厳しめに採点（雑なものは 0.2 以下）。"
    )
    system = (
        "あなたは YouTube チャンネル運営の編集ディレクター。"
        "視聴者の知的好奇心を引く切り口を見抜き、トレンドをチャンネル文脈に翻訳する。"
    )
    return system, user


def _score_with_llm(
    candidates: List[Dict[str, Any]],
    *,
    channel_name: str,
    channel_concept: str,
    seeds: List[str],
    channel_id: str,
) -> Optional[List[Dict[str, Any]]]:
    """LLM にバルクで relevance + 提案タイトル/アングルを生成させる。失敗時 None。

    Claude を先に試し、落ちたら GPT に回す。Claude だけに依存していた頃は
    ANTHROPIC_API_KEY が失効した時点で採点が語彙一致フォールバック（上限 0.35 前後）
    に落ち、AUTO_QUEUE_THRESHOLD 0.7 に永久に届かず自動キュー投入が止まっていた。
    シナリオ生成が GPT で回っている以上、そちらに逃がせば機能を維持できる。
    """
    if not candidates:
        return []

    system, user = _build_scoring_prompt(
        candidates,
        channel_name=channel_name,
        channel_concept=channel_concept,
        seeds=seeds,
    )

    res = _score_via_claude(system, user, channel_id)
    if res is None:
        res = _score_via_gpt(system, user, channel_id)
    if not res or not isinstance(res, dict):
        return None
    scores = res.get("scores")
    if not isinstance(scores, list):
        return None
    by_index: Dict[int, Dict[str, Any]] = {}
    for s in scores:
        if not isinstance(s, dict):
            continue
        try:
            idx = int(s.get("index"))
        except Exception:
            continue
        by_index[idx] = {
            "relevance": max(0.0, min(1.0, float(s.get("relevance") or 0.0))),
            "title": str(s.get("title") or "").strip(),
            "angle": str(s.get("angle") or "").strip(),
            "reason": str(s.get("reason") or "").strip(),
        }
    out: List[Dict[str, Any]] = []
    for i, c in enumerate(candidates):
        info = by_index.get(i, {})
        out.append({
            **c,
            "relevance_score": info.get("relevance", _fallback_relevance(c["keyword"], seeds)),
            "suggested_title": info.get("title") or "",
            "suggested_angle": info.get("angle") or "",
            "rationale": info.get("reason") or "",
        })
    return out


# ---------------------------------------------------------------------
# Queue injection
# ---------------------------------------------------------------------

def _queue_theme(channel_id: str, title: str, angle: str, *, priority_high: bool = True) -> Optional[str]:
    """theme_queue の先頭に挿入。返り値は theme_id。"""
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
        "source": "trend_scanner",
    }
    queue = list(ap.get("theme_queue") or [])
    # 重複（同タイトル）チェック
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
# Main entrypoint
# ---------------------------------------------------------------------

def scan_channel(
    channel_id: str,
    *,
    auto_queue: bool = True,
    sources: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """1 チャンネル分のトレンドスキャンを実行。"""
    started_at = int(time.time())
    sources = sources or ["google_trends", "news_api", "youtube_trending"]

    # チャンネル取得
    try:
        from main import channel_manager  # type: ignore
    except Exception:
        channel_manager = None  # type: ignore
    ch = channel_manager.get(channel_id) if channel_manager else None

    channel_name = getattr(ch, "name", channel_id)
    channel_concept = getattr(ch, "concept", "")
    seeds: List[str] = []
    for s in getattr(ch, "theme_seeds", []) or []:
        if isinstance(s, dict):
            t = s.get("title") or s.get("keyword") or s.get("angle")
            if t:
                seeds.append(str(t))
        elif isinstance(s, str):
            seeds.append(s)

    fetch_errors: Dict[str, str] = {}
    candidates: List[Dict[str, Any]] = []

    if "google_trends" in sources:
        items, err = _fetch_google_trends()
        candidates.extend(items)
        if err:
            fetch_errors["google_trends"] = err
    if "news_api" in sources:
        items, err = _fetch_news_api(seeds)
        candidates.extend(items)
        if err:
            fetch_errors["news_api"] = err
    if "youtube_trending" in sources:
        items, err = _fetch_youtube_trending()
        candidates.extend(items)
        if err:
            fetch_errors["youtube_trending"] = err

    # 重複キーワード排除（同スキャン内、ソース横断）
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for c in candidates:
        kw = c.get("keyword") or ""
        key = kw.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(c)

    # 直近 7d で同キーワードを既に検出済みなら飛ばす（重複保存抑制）
    fresh: List[Dict[str, Any]] = []
    for c in unique:
        prev = analytics_store.find_recent_trend_by_keyword(channel_id, c["keyword"])
        if prev:
            continue
        fresh.append(c)

    scored: List[Dict[str, Any]] = []
    if fresh:
        llm_res = _score_with_llm(
            fresh,
            channel_name=channel_name,
            channel_concept=channel_concept,
            seeds=seeds,
            channel_id=channel_id,
        )
        if llm_res is None:
            # フォールバック（Claude も GPT も使えないとき）。
            # 語彙一致ベースなので上限が低く、AUTO_QUEUE_THRESHOLD には届かない。
            # 検出は残るので UI から手動でキュー投入できる。
            for c in fresh:
                rel = _fallback_relevance(c["keyword"], seeds)
                scored.append({
                    **c,
                    "relevance_score": rel,
                    "suggested_title": c["keyword"],
                    "suggested_angle": "",
                    "rationale": "LLM 未設定: 語彙重なりベースのフォールバックスコア",
                })
        else:
            scored = llm_res

    for s in scored:
        trend = float(s.get("trend_score") or 0.0)
        rel = float(s.get("relevance_score") or 0.0)
        s["combined_score"] = round(0.4 * trend + 0.6 * rel, 3)

    scored.sort(key=lambda x: x.get("combined_score", 0.0), reverse=True)

    # 自動キュー投入: 上位 N 件のみ
    auto_queued_count = 0
    detected_count = 0
    for s in scored:
        det_id = uuid.uuid4().hex[:10]
        queue_theme_id: Optional[str] = None
        do_auto = (
            auto_queue
            and s.get("combined_score", 0.0) >= AUTO_QUEUE_THRESHOLD
            and auto_queued_count < MAX_AUTO_QUEUE_PER_SCAN
            and bool(s.get("suggested_title"))
        )
        if do_auto:
            queue_theme_id = _queue_theme(
                channel_id,
                s["suggested_title"],
                s.get("suggested_angle") or "",
                priority_high=True,
            )
            if queue_theme_id:
                auto_queued_count += 1
        status = "queued" if queue_theme_id else "detected"
        analytics_store.upsert_trend_detection(
            detection_id=det_id,
            channel_id=channel_id,
            keyword=s["keyword"],
            source=s["source"],
            trend_score=float(s.get("trend_score") or 0.0),
            relevance_score=float(s.get("relevance_score") or 0.0),
            combined_score=float(s.get("combined_score") or 0.0),
            suggested_title=s.get("suggested_title") or None,
            suggested_angle=s.get("suggested_angle") or None,
            rationale=s.get("rationale") or None,
            raw=s.get("raw") or {},
            auto_queued=bool(queue_theme_id),
            status=status,
            queue_theme_id=queue_theme_id,
        )
        detected_count += 1

    error_str = "; ".join(f"{k}: {v}" for k, v in fetch_errors.items()) if fetch_errors else None
    analytics_store.insert_trend_scan_history(
        channel_id,
        sources=sources,
        detected=detected_count,
        auto_queued=auto_queued_count,
        error=error_str,
        started_at=started_at,
    )

    return {
        "channel_id": channel_id,
        "started_at": started_at,
        "finished_at": int(time.time()),
        "sources": sources,
        "detected": detected_count,
        "auto_queued": auto_queued_count,
        "errors": fetch_errors,
        "skipped_dedup": len(unique) - len(fresh),
        "items": scored,
    }


def queue_detection(channel_id: str, detection_id: str) -> Dict[str, Any]:
    """手動で 1 件をテーマキューへ投入する。"""
    det = analytics_store.get_trend_detection(detection_id)
    if not det or det.get("channel_id") != channel_id:
        return {"ok": False, "error": "detection not found"}
    title = det.get("suggested_title") or det.get("keyword") or ""
    angle = det.get("suggested_angle") or det.get("rationale") or ""
    if not title:
        return {"ok": False, "error": "no title to queue"}
    theme_id = _queue_theme(channel_id, title, angle, priority_high=True)
    if not theme_id:
        return {"ok": False, "error": "failed to queue (duplicate or save error)"}
    analytics_store.update_trend_status(
        detection_id, "queued", queue_theme_id=theme_id, queued=True
    )
    return {"ok": True, "theme_id": theme_id, "title": title, "angle": angle}


def dismiss_detection(channel_id: str, detection_id: str) -> Dict[str, Any]:
    det = analytics_store.get_trend_detection(detection_id)
    if not det or det.get("channel_id") != channel_id:
        return {"ok": False, "error": "detection not found"}
    analytics_store.update_trend_status(detection_id, "dismissed")
    return {"ok": True}


def scan_all_channels(*, auto_queue: bool = True) -> Dict[str, Any]:
    """全チャンネルでスキャン実行。スケジューラから呼ばれる。"""
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
            results.append({"channel_id": cid, **{k: r[k] for k in ("detected", "auto_queued", "errors")}})
        except Exception as e:
            print(f"⚠️ trend_scanner.scan_channel({cid}) failed: {e}")
            results.append({"channel_id": cid, "error": str(e)})
    return {"ok": True, "results": results, "ran_at": int(time.time())}
