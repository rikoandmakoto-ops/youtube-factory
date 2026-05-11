"""
YouTube コメント取得 + GPT-4o による感情/トピック分析。

提供する関数:
  - fetch_comments(channel_id, video_id, max_comments=200)
      commentThreads.list を呼んでコメント本体を SQLite に保存（分析はせず）。
  - analyze_pending(video_id, batch_size=20)
      未分析コメントを GPT-4o に投げ、感情/トピック/リクエスト判定を保存。
  - sync_video_comments(channel_id, video_id, max_comments=200, analyze=True)
      取得 → 分析 をまとめて実行。

設計メモ:
  - 取得は OAuth 必須ではなく、YOUTUBE_API_KEY があればそちらを優先（quota が安い）。
  - 分析は OPENAI_API_KEY が必要。未設定なら fetch のみ実行されて分析は no-op。
  - GPT 呼び出しは1リクエストで複数コメントをまとめて分類（コスト圧縮）。
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from . import youtube_oauth as yt_oauth
from .analytics import store as analytics_store


YT_API_BASE = "https://www.googleapis.com/youtube/v3"
GPT_MODEL = "gpt-4o"
GPT_MODEL_LIGHT = "gpt-4o-mini"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


# ---------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------

def _fetch_via_api_key(
    video_id: str, max_comments: int, api_key: str
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while len(items) < max_comments:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(100, max_comments - len(items)),
            "order": "relevance",
            "textFormat": "plainText",
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        url = f"{YT_API_BASE}/commentThreads?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception:
            break
        for it in data.get("items", []):
            top = (
                it.get("snippet", {})
                .get("topLevelComment", {})
                .get("snippet", {})
            )
            cid = it.get("snippet", {}).get("topLevelComment", {}).get("id") or it.get("id")
            if not cid or not top.get("textDisplay"):
                continue
            items.append(
                {
                    "comment_id": cid,
                    "video_id": video_id,
                    "text": top.get("textDisplay", ""),
                    "author": top.get("authorDisplayName"),
                    "like_count": int(top.get("likeCount", 0) or 0),
                    "published_at": top.get("publishedAt"),
                }
            )
            if len(items) >= max_comments:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return items


def _fetch_via_oauth(
    channel_id: str, video_id: str, max_comments: int
) -> List[Dict[str, Any]]:
    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception:
        return []
    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return []
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return []
    items: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while len(items) < max_comments:
        try:
            resp = (
                yt.commentThreads()
                .list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=min(100, max_comments - len(items)),
                    order="relevance",
                    textFormat="plainText",
                    pageToken=page_token,
                )
                .execute()
            )
        except Exception:
            break
        for it in resp.get("items", []):
            top = (
                it.get("snippet", {})
                .get("topLevelComment", {})
                .get("snippet", {})
            )
            cid = it.get("snippet", {}).get("topLevelComment", {}).get("id") or it.get("id")
            if not cid or not top.get("textDisplay"):
                continue
            items.append(
                {
                    "comment_id": cid,
                    "video_id": video_id,
                    "text": top.get("textDisplay", ""),
                    "author": top.get("authorDisplayName"),
                    "like_count": int(top.get("likeCount", 0) or 0),
                    "published_at": top.get("publishedAt"),
                }
            )
            if len(items) >= max_comments:
                break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def fetch_comments(
    channel_id: str,
    video_id: str,
    *,
    max_comments: int = 200,
) -> Dict[str, Any]:
    """コメントを取得して SQLite に保存（分析はしない）。"""
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    items: List[Dict[str, Any]] = []
    source = "none"
    if api_key:
        try:
            items = _fetch_via_api_key(video_id, max_comments, api_key)
            source = "api_key"
        except Exception:
            items = []
    if not items:
        items = _fetch_via_oauth(channel_id, video_id, max_comments)
        source = "oauth" if items else source

    for it in items:
        analytics_store.upsert_comment(
            comment_id=it["comment_id"],
            video_id=video_id,
            channel_id=channel_id,
            author=it.get("author"),
            text=it["text"],
            like_count=it.get("like_count", 0),
            published_at=it.get("published_at"),
        )

    return {
        "channel_id": channel_id,
        "video_id": video_id,
        "source": source,
        "fetched": len(items),
    }


# ---------------------------------------------------------------------
# GPT analysis
# ---------------------------------------------------------------------

_ANALYZE_SYSTEM = (
    "あなたは YouTube のコメント分析の専門家です。"
    "渡された複数のコメントを1件ずつ、以下のJSON配列の形式で分類してください。\n"
    "各要素: {\n"
    '  "index": <0始まりのコメント番号>,\n'
    '  "sentiment": "positive" | "negative" | "request" | "neutral",\n'
    '  "topics": [<1〜3個の短い名詞句。日本語可>],\n'
    '  "is_request": true | false   // 「もっと◯◯について知りたい」「次回は△△を扱って」のような要望なら true\n'
    "}\n"
    "出力は { \"items\": [...] } のJSONのみ。コードブロックや説明文を含めないこと。"
)


def _call_openai(payload_messages: List[Dict[str, str]], model: str) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    payload = json.dumps(
        {
            "model": model,
            "messages": payload_messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
    )
    req = urllib.request.Request(
        OPENAI_CHAT_URL,
        data=payload.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    try:
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return None


def analyze_pending(
    video_id: str,
    *,
    batch_size: int = 20,
    max_batches: int = 10,
    model: str = GPT_MODEL,
) -> Dict[str, Any]:
    """この動画の未分析コメントを GPT-4o で分析して保存。"""
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return {
            "video_id": video_id,
            "analyzed": 0,
            "skipped": True,
            "reason": "OPENAI_API_KEY 未設定",
        }

    pending = [
        c
        for c in analytics_store.list_comments_for_video(
            video_id, limit=batch_size * max_batches, analyzed_only=False
        )
        if not c.get("analyzed_at")
    ]
    if not pending:
        return {"video_id": video_id, "analyzed": 0, "skipped": False}

    analyzed_count = 0
    for batch_idx in range(0, len(pending), batch_size):
        batch = pending[batch_idx : batch_idx + batch_size]
        bullet_list = "\n".join(
            f"{i}. {c['text']}" for i, c in enumerate(batch)
        )
        user_msg = (
            f"以下は YouTube 動画 ({video_id}) の視聴者コメントです。"
            "1件ずつ感情とトピックを分類してください。\n\n" + bullet_list
        )
        result = _call_openai(
            [
                {"role": "system", "content": _ANALYZE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            model=model,
        )
        if not result:
            continue
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list):
            continue
        by_index = {int(x.get("index", -1)): x for x in items if isinstance(x, dict)}
        for i, c in enumerate(batch):
            r = by_index.get(i)
            if not r:
                continue
            sentiment = str(r.get("sentiment") or "neutral").lower()
            if sentiment not in ("positive", "negative", "request", "neutral"):
                sentiment = "neutral"
            topics = r.get("topics") or []
            if not isinstance(topics, list):
                topics = []
            topics = [str(t).strip() for t in topics if str(t).strip()][:3]
            is_request = bool(r.get("is_request")) or sentiment == "request"
            analytics_store.upsert_comment(
                comment_id=c["comment_id"],
                video_id=video_id,
                channel_id=c.get("channel_id"),
                author=c.get("author"),
                text=c["text"],
                like_count=c.get("like_count", 0),
                published_at=c.get("published_at"),
                sentiment=sentiment,
                topics=topics,
                is_request=is_request,
                analyzed=True,
            )
            analyzed_count += 1
        time.sleep(0.1)

    return {"video_id": video_id, "analyzed": analyzed_count, "skipped": False}


def sync_video_comments(
    channel_id: str,
    video_id: str,
    *,
    max_comments: int = 200,
    analyze: bool = True,
) -> Dict[str, Any]:
    fetched = fetch_comments(channel_id, video_id, max_comments=max_comments)
    analysis = (
        analyze_pending(video_id)
        if analyze
        else {"video_id": video_id, "analyzed": 0, "skipped": True, "reason": "analyze=False"}
    )
    summary = analytics_store.comment_summary_for_video(video_id)
    return {
        "channel_id": channel_id,
        "video_id": video_id,
        "fetch": fetched,
        "analysis": analysis,
        "summary": summary,
    }
