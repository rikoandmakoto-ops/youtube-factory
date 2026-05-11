"""
YouTube いいね率（like_rate = likes / views）取得ヘルパ。

3つのソースに対応:
  1. YouTube Data API v3 (APIキー認証) — 単純な統計取得用
  2. OAuth (youtube_oauth.get_credentials) — 既存連携を再利用
  3. オフライン / モック — APIキー未設定時のフォールバック

video_id を渡すと {video_id, title, views, likes, like_rate} の dict を返す。
videos.list は1リクエストで最大50 ID まで指定可能（quota 1）。

`like_rate` は 0..1 の float（パーセントではない）。表示時は ×100 すること。
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional


YT_API_BASE = "https://www.googleapis.com/youtube/v3"


def _api_key() -> Optional[str]:
    """環境変数から YouTube Data API キーを取得。空なら None。"""
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    return key or None


def compute_like_rate(likes: int, views: int) -> float:
    """いいね数 / 視聴回数 を 0..1 で返す。views=0 のときは 0."""
    if not views or views <= 0:
        return 0.0
    return float(likes) / float(views)


def _chunk(seq: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _fetch_via_api_key(video_ids: List[str], api_key: str) -> List[Dict[str, Any]]:
    """YouTube Data API v3 (APIキー) で videos.list 経由で取得。"""
    out: List[Dict[str, Any]] = []
    for batch in _chunk(video_ids, 50):
        params = urllib.parse.urlencode(
            {
                "part": "snippet,statistics",
                "id": ",".join(batch),
                "key": api_key,
            }
        )
        req = urllib.request.Request(f"{YT_API_BASE}/videos?{params}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            # バッチ単位で失敗してもエラー情報を載せて返す
            for vid in batch:
                out.append(
                    {
                        "video_id": vid,
                        "title": None,
                        "views": 0,
                        "likes": 0,
                        "like_rate": 0.0,
                        "error": f"api_key fetch failed: {e}",
                    }
                )
            continue
        for item in data.get("items", []):
            stats = item.get("statistics", {}) or {}
            snip = item.get("snippet", {}) or {}
            views = int(stats.get("viewCount", 0) or 0)
            # likeCount は非公開設定で欠落することがある → 0 扱い
            likes = int(stats.get("likeCount", 0) or 0)
            out.append(
                {
                    "video_id": item.get("id"),
                    "title": snip.get("title"),
                    "published_at": snip.get("publishedAt"),
                    "views": views,
                    "likes": likes,
                    "like_rate": compute_like_rate(likes, views),
                    "likes_hidden": "likeCount" not in stats,
                }
            )
    return out


def _fetch_via_oauth(video_ids: List[str]) -> Optional[List[Dict[str, Any]]]:
    """OAuth 連携が利いていれば googleapiclient で同じ取得を行う。
    依存（google-api-python-client）が無い／未連携の場合 None を返す。"""
    try:
        from pipeline import youtube_oauth as yt_oauth
    except Exception:
        return None
    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception:
        return None
    creds = yt_oauth.get_credentials()
    if not creds:
        return None
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None

    out: List[Dict[str, Any]] = []
    for batch in _chunk(video_ids, 50):
        try:
            resp = (
                yt.videos()
                .list(part="snippet,statistics", id=",".join(batch))
                .execute()
            )
        except Exception as e:
            for vid in batch:
                out.append(
                    {
                        "video_id": vid,
                        "title": None,
                        "views": 0,
                        "likes": 0,
                        "like_rate": 0.0,
                        "error": f"oauth fetch failed: {e}",
                    }
                )
            continue
        for item in resp.get("items", []):
            stats = item.get("statistics", {}) or {}
            snip = item.get("snippet", {}) or {}
            views = int(stats.get("viewCount", 0) or 0)
            likes = int(stats.get("likeCount", 0) or 0)
            out.append(
                {
                    "video_id": item.get("id"),
                    "title": snip.get("title"),
                    "published_at": snip.get("publishedAt"),
                    "views": views,
                    "likes": likes,
                    "like_rate": compute_like_rate(likes, views),
                    "likes_hidden": "likeCount" not in stats,
                }
            )
    return out


def fetch_video_stats(video_ids: List[str]) -> Dict[str, Any]:
    """
    複数 video_id についていいね率を含む統計を取得。

    優先順位: APIキー → OAuth → エラー（{"source":"none","items":[]}）

    Returns:
        {
            "source": "api_key" | "oauth" | "none",
            "items": [{"video_id","title","views","likes","like_rate", ...}, ...],
            "missing": [<requested but not returned ids>],
            "error": Optional[str],
        }
    """
    ids = [v for v in (video_ids or []) if v]
    if not ids:
        return {"source": "none", "items": [], "missing": []}

    key = _api_key()
    items: Optional[List[Dict[str, Any]]] = None
    source = "none"
    error: Optional[str] = None

    if key:
        try:
            items = _fetch_via_api_key(ids, key)
            source = "api_key"
        except Exception as e:
            error = f"api_key path failed: {e}"

    if items is None:
        try:
            items = _fetch_via_oauth(ids)
            if items is not None:
                source = "oauth"
        except Exception as e:
            error = f"oauth path failed: {e}"

    if items is None:
        return {
            "source": "none",
            "items": [],
            "missing": ids,
            "error": error or "YOUTUBE_API_KEY 未設定 / OAuth 未連携",
        }

    returned = {it.get("video_id") for it in items if it.get("video_id")}
    missing = [v for v in ids if v not in returned]
    return {
        "source": source,
        "items": items,
        "missing": missing,
        "error": error,
    }


def find_low_like_rate(
    items: List[Dict[str, Any]],
    threshold: float,
    *,
    min_views: int = 100,
) -> List[Dict[str, Any]]:
    """
    threshold (0..1) を下回る動画のみ抽出。
    - min_views 未満の動画はサンプル不足として除外（過剰反応を避ける）
    - likes_hidden=True の動画も除外（測定不能）
    - error 付きはスキップ
    """
    out: List[Dict[str, Any]] = []
    for it in items:
        if it.get("error"):
            continue
        if it.get("likes_hidden"):
            continue
        views = int(it.get("views") or 0)
        if views < min_views:
            continue
        if float(it.get("like_rate") or 0.0) < float(threshold):
            out.append(it)
    return out
