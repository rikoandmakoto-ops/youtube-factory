"""
CompetitorAnalyzer (Phase F-1) — 同ジャンルの伸びてるチャンネルのタイトル / サムネ / 投稿頻度
を週1回スキャンして、Claude でパターンを抽出する。

入力:
  data/channels/{channel_id}.json の `competitors` フィールド（YouTube channel ID の配列）

ソース:
  - YouTube Data API v3 `channels.list` — 登録者数・動画数・uploads playlist
  - YouTube Data API v3 `playlistItems.list` — 直近の uploads
  - YouTube Data API v3 `videos.list` — タイトル・サムネ URL・再生数・公開日・duration

スコアリング & インサイト:
  - 投稿頻度（本/週）と曜日傾向
  - 高パフォーマンス動画の共通点（再生数上位）
  - Claude にタイトル / サムネ URL を渡してパターン抽出
  - 自チャンネルとの差分 / 改善ポイント

公開関数:
  - scan_channel(channel_id, *, max_competitors=10, max_videos_per_competitor=20)
  - scan_one_competitor(channel_id, competitor_id, ch_profile=None)
  - add_competitor(channel_id, competitor_channel_id)
  - remove_competitor(channel_id, competitor_id)
  - list_competitors(channel_id)
  - scan_all_channels()  ← scheduler から呼ぶ

設計方針:
  - YOUTUBE_API_KEY 未設定 / Claude 未設定でもクラッシュさせない。
  - 競合チャンネルが多くて quota を食い切らないよう、`max_videos_per_competitor` を絞れる。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import store as analytics_store


YT_API_BASE = "https://www.googleapis.com/youtube/v3"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"


# ---------------------------------------------------------------------
# Channel JSON helpers (competitors list lives in data/channels/*.json)
# ---------------------------------------------------------------------

def _channel_file(channel_id: str) -> Path:
    return CHANNELS_DIR / f"{channel_id}.json"


def _load_channel_json(channel_id: str) -> Dict[str, Any]:
    p = _channel_file(channel_id)
    if not p.exists():
        raise FileNotFoundError(f"channel json not found: {channel_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_channel_json(channel_id: str, data: Dict[str, Any]) -> None:
    p = _channel_file(channel_id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_competitors(channel_id: str) -> List[str]:
    """登録済み競合チャンネル ID 一覧。"""
    try:
        data = _load_channel_json(channel_id)
    except Exception:
        return []
    comp = data.get("competitors") or []
    return [str(c).strip() for c in comp if str(c).strip()]


_YT_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_\-]{20,}$")
_YT_URL_RE = re.compile(
    r"(?:youtube\.com/(?:channel/(UC[A-Za-z0-9_\-]+)|@([A-Za-z0-9_\-\.]+)|c/([A-Za-z0-9_\-\.]+)))",
    re.IGNORECASE,
)


def _resolve_channel_input(raw: str) -> Optional[str]:
    """ユーザー入力（URL / @handle / UC...) を UC... ID に正規化。

    handle / custom URL の場合は YouTube Data API でルックアップ（YOUTUBE_API_KEY が必要）。
    """
    if not raw:
        return None
    raw = raw.strip()
    if _YT_CHANNEL_ID_RE.match(raw):
        return raw
    m = _YT_URL_RE.search(raw)
    handle: Optional[str] = None
    if m:
        uc, at, cust = m.group(1), m.group(2), m.group(3)
        if uc and _YT_CHANNEL_ID_RE.match(uc):
            return uc
        handle = at or cust
    if not handle:
        # bare handle like "@foo" or "foo"
        if raw.startswith("@"):
            handle = raw[1:]
        elif "/" not in raw and " " not in raw:
            handle = raw
    if not handle:
        return None
    return _lookup_channel_by_handle(handle)


def _lookup_channel_by_handle(handle: str) -> Optional[str]:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return None
    # forHandle was added in YT API v3 in 2023 — try it, fall back to search.
    params = {"part": "id", "forHandle": handle.lstrip("@"), "key": api_key}
    try:
        url = f"{YT_API_BASE}/channels?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        items = data.get("items") or []
        if items:
            cid = items[0].get("id")
            if cid and _YT_CHANNEL_ID_RE.match(cid):
                return cid
    except Exception:
        pass
    # Fallback: search
    try:
        params = {
            "part": "snippet",
            "type": "channel",
            "q": handle,
            "maxResults": 1,
            "key": api_key,
        }
        url = f"{YT_API_BASE}/search?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        items = data.get("items") or []
        if items:
            cid = (items[0].get("id") or {}).get("channelId")
            if cid and _YT_CHANNEL_ID_RE.match(cid):
                return cid
    except Exception:
        pass
    return None


def add_competitor(channel_id: str, competitor_input: str) -> Dict[str, Any]:
    """data/channels/{id}.json の `competitors` に追加。重複は無視。"""
    resolved = _resolve_channel_input(competitor_input)
    if not resolved:
        return {
            "ok": False,
            "error": "channel ID を解決できませんでした (URL / @handle / UC...) — YOUTUBE_API_KEY が必要な場合があります",
        }
    try:
        data = _load_channel_json(channel_id)
    except FileNotFoundError:
        return {"ok": False, "error": f"channel {channel_id} not found"}
    comps = list(data.get("competitors") or [])
    if resolved in comps:
        return {"ok": True, "competitor_id": resolved, "note": "already registered"}
    comps.append(resolved)
    data["competitors"] = comps
    _save_channel_json(channel_id, data)
    return {"ok": True, "competitor_id": resolved}


def remove_competitor(channel_id: str, competitor_id: str) -> Dict[str, Any]:
    try:
        data = _load_channel_json(channel_id)
    except FileNotFoundError:
        return {"ok": False, "error": f"channel {channel_id} not found"}
    comps = list(data.get("competitors") or [])
    if competitor_id not in comps:
        return {"ok": False, "error": "competitor not registered"}
    comps = [c for c in comps if c != competitor_id]
    data["competitors"] = comps
    _save_channel_json(channel_id, data)
    # 分析データも削除
    try:
        analytics_store.delete_competitor_analyses(channel_id, competitor_id)
    except Exception:
        pass
    return {"ok": True}


# ---------------------------------------------------------------------
# YouTube Data API fetchers
# ---------------------------------------------------------------------

def _yt_get(path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return None
    p = dict(params)
    p["key"] = api_key
    url = f"{YT_API_BASE}/{path}?{urllib.parse.urlencode(p)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "youtube-factory/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"⚠️ YouTube API GET failed ({path}): {e}")
        return None


def _fetch_channel_meta(competitor_id: str) -> Optional[Dict[str, Any]]:
    data = _yt_get(
        "channels",
        {"part": "snippet,statistics,contentDetails", "id": competitor_id},
    )
    if not data:
        return None
    items = data.get("items") or []
    if not items:
        return None
    it = items[0]
    sn = it.get("snippet") or {}
    st = it.get("statistics") or {}
    cd = it.get("contentDetails") or {}
    uploads = ((cd.get("relatedPlaylists") or {}).get("uploads")) or None
    return {
        "channel_id": it.get("id") or competitor_id,
        "title": sn.get("title"),
        "description": sn.get("description"),
        "thumbnail": ((sn.get("thumbnails") or {}).get("default") or {}).get("url"),
        "subscriber_count": int(st.get("subscriberCount") or 0)
        if not st.get("hiddenSubscriberCount") else None,
        "video_count": int(st.get("videoCount") or 0),
        "view_count": int(st.get("viewCount") or 0),
        "uploads_playlist": uploads,
    }


def _fetch_uploads(uploads_playlist: str, max_videos: int) -> List[str]:
    """uploads playlist から最新動画 ID を集める。"""
    video_ids: List[str] = []
    page_token: Optional[str] = None
    while len(video_ids) < max_videos:
        params: Dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": min(50, max_videos - len(video_ids)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = _yt_get("playlistItems", params)
        if not data:
            break
        for it in data.get("items") or []:
            vid = ((it.get("contentDetails") or {}).get("videoId")) or None
            if vid:
                video_ids.append(vid)
            if len(video_ids) >= max_videos:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def _fetch_video_details(video_ids: List[str]) -> List[Dict[str, Any]]:
    """videos.list でタイトル / サムネ / 統計 / duration をまとめて取得。"""
    out: List[Dict[str, Any]] = []
    # videos.list は id を最大 50 件まで一度に渡せる
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        data = _yt_get(
            "videos",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(chunk),
                "maxResults": 50,
            },
        )
        if not data:
            continue
        for it in data.get("items") or []:
            sn = it.get("snippet") or {}
            st = it.get("statistics") or {}
            cd = it.get("contentDetails") or {}
            thumbs = sn.get("thumbnails") or {}
            thumb = (
                (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {})
                .get("url")
            )
            out.append({
                "video_id": it.get("id"),
                "title": sn.get("title"),
                "published_at": sn.get("publishedAt"),
                "thumbnail_url": thumb,
                "duration": cd.get("duration"),
                "views": int(st.get("viewCount") or 0),
                "likes": int(st.get("likeCount") or 0),
                "comments": int(st.get("commentCount") or 0),
                "tags": (sn.get("tags") or [])[:10],
            })
    return out


# ---------------------------------------------------------------------
# Heuristics: posting frequency, day-of-week
# ---------------------------------------------------------------------

def _parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s.replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None


def _summarize_posting(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """投稿頻度（本/週）と曜日分布を計算。"""
    dates: List[datetime] = []
    for v in videos:
        d = _parse_iso_date(v.get("published_at"))
        if d:
            dates.append(d)
    if not dates:
        return {
            "videos_observed": 0,
            "posting_frequency_per_week": None,
            "day_of_week_counts": {},
            "first_published_at": None,
            "last_published_at": None,
        }
    dates.sort()
    span_seconds = (dates[-1] - dates[0]).total_seconds() or 1.0
    span_weeks = max(span_seconds / (7 * 24 * 3600), 1 / 7)
    freq = len(dates) / span_weeks
    dow_counts = Counter(d.weekday() for d in dates)  # Mon=0..Sun=6
    return {
        "videos_observed": len(dates),
        "posting_frequency_per_week": round(freq, 2),
        "day_of_week_counts": {str(k): int(v) for k, v in dow_counts.items()},
        "first_published_at": dates[0].isoformat(),
        "last_published_at": dates[-1].isoformat(),
    }


# ---------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------

def _build_claude_prompt(
    *,
    own_channel_name: str,
    own_concept: str,
    own_seed_titles: List[str],
    competitor_title: str,
    competitor_videos: List[Dict[str, Any]],
    posting_summary: Dict[str, Any],
) -> str:
    top10 = sorted(competitor_videos, key=lambda v: v.get("views") or 0, reverse=True)[:10]
    lines = []
    for v in top10:
        lines.append(
            f"- 「{v.get('title')}」 | 再生数={v.get('views'):,} | "
            f"いいね={v.get('likes'):,} | published={v.get('published_at')} | "
            f"thumbnail={v.get('thumbnail_url') or '—'}"
        )
    video_lines = "\n".join(lines) if lines else "（取得失敗）"

    own_seed_block = "、".join(own_seed_titles[:10]) if own_seed_titles else "（未設定）"
    freq = posting_summary.get("posting_frequency_per_week")
    dow_counts = posting_summary.get("day_of_week_counts") or {}
    dow_label = {"0": "月", "1": "火", "2": "水", "3": "木", "4": "金", "5": "土", "6": "日"}
    dow_str = "、".join(
        f"{dow_label.get(k, k)}={v}本" for k, v in sorted(dow_counts.items())
    ) or "（不明）"

    return (
        f"自チャンネル: {own_channel_name}\n"
        f"コンセプト: {own_concept}\n"
        f"代表的なテーマ: {own_seed_block}\n\n"
        f"競合チャンネル: {competitor_title}\n"
        f"投稿頻度: {freq if freq is not None else '不明'} 本/週\n"
        f"曜日分布: {dow_str}\n\n"
        f"競合の高パフォーマンス動画 TOP10:\n{video_lines}\n\n"
        f"以下を JSON で出してください:\n"
        f"{{\n"
        f"  \"title_patterns\": {{\n"
        f"    \"question_form_ratio\": 0.0〜1.0,\n"
        f"    \"number_usage_ratio\": 0.0〜1.0,\n"
        f"    \"exclamation_usage_ratio\": 0.0〜1.0,\n"
        f"    \"common_keywords\": [\"...\", ...],\n"
        f"    \"typical_length_chars\": <int>,\n"
        f"    \"hook_styles\": [\"疑問形\", \"数字訴求\", ...]\n"
        f"  }},\n"
        f"  \"thumbnail_patterns\": [\"...\", ...],  // 例: 顔ドアップ多用 / 赤いバッジ / 数字の大きいフォント\n"
        f"  \"top_videos_common_traits\": [\"...\", ...],\n"
        f"  \"posting_schedule_insights\": \"...\",\n"
        f"  \"own_channel_diff\": [\"...\", ...],   // 自チャンネルとの差分\n"
        f"  \"improvement_suggestions\": [\"...\", ...] // 自チャンネルが取り入れるべき具体策\n"
        f"}}\n"
        f"必ず JSON オブジェクトのみを返してください。"
    )


def _analyze_with_claude(
    *,
    own_channel_name: str,
    own_concept: str,
    own_seed_titles: List[str],
    competitor_title: str,
    competitor_videos: List[Dict[str, Any]],
    posting_summary: Dict[str, Any],
    channel_id: str,
) -> Optional[Dict[str, Any]]:
    try:
        from pipeline import claude_client
    except Exception:
        return None
    if not claude_client.has_api_key():
        return None
    system = (
        "あなたは YouTube チャンネルのコンサルタント。"
        "競合チャンネルの動画タイトル・サムネ URL・投稿頻度から、"
        "再現性のあるパターンを抽出し、自チャンネルが学べる具体的なアクションを提案する。"
    )
    user = _build_claude_prompt(
        own_channel_name=own_channel_name,
        own_concept=own_concept,
        own_seed_titles=own_seed_titles,
        competitor_title=competitor_title,
        competitor_videos=competitor_videos,
        posting_summary=posting_summary,
    )
    res = claude_client.call_claude_json(
        system=system, user=user,
        temperature=0.3, max_tokens=2500,
        channel_id=channel_id, purpose="competitor_analysis",
    )
    return res if isinstance(res, dict) else None


def _fallback_insights(
    videos: List[Dict[str, Any]],
    posting_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Claude 未設定時の簡易フォールバック。"""
    titles = [v.get("title") or "" for v in videos]
    if not titles:
        return {
            "title_patterns": {},
            "thumbnail_patterns": [],
            "top_videos_common_traits": [],
            "posting_schedule_insights": "データ不足",
            "own_channel_diff": [],
            "improvement_suggestions": [],
            "note": "Claude API 未設定 — 簡易統計のみ",
        }
    question = sum(1 for t in titles if "？" in t or "?" in t or t.startswith("なぜ"))
    has_num = sum(1 for t in titles if re.search(r"\d", t))
    excl = sum(1 for t in titles if "!" in t or "！" in t)
    avg_len = int(sum(len(t) for t in titles) / max(len(titles), 1))
    return {
        "title_patterns": {
            "question_form_ratio": round(question / len(titles), 2),
            "number_usage_ratio": round(has_num / len(titles), 2),
            "exclamation_usage_ratio": round(excl / len(titles), 2),
            "common_keywords": [],
            "typical_length_chars": avg_len,
            "hook_styles": [],
        },
        "thumbnail_patterns": [],
        "top_videos_common_traits": [
            f"観測動画 {len(titles)} 本、平均タイトル長 {avg_len} 文字"
        ],
        "posting_schedule_insights": f"投稿頻度 約 {posting_summary.get('posting_frequency_per_week') or '?'} 本/週",
        "own_channel_diff": [],
        "improvement_suggestions": [],
        "note": "Claude API 未設定 — 簡易統計のみ",
    }


# ---------------------------------------------------------------------
# Scan entry points
# ---------------------------------------------------------------------

def scan_one_competitor(
    channel_id: str,
    competitor_id: str,
    *,
    max_videos: int = 20,
    ch_profile: Optional[Any] = None,
) -> Dict[str, Any]:
    """1 競合チャンネルの分析を実行して DB に保存。"""
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "competitor_id": competitor_id,
            "error": "YOUTUBE_API_KEY not set",
        }
    meta = _fetch_channel_meta(competitor_id)
    if not meta:
        return {
            "ok": False,
            "competitor_id": competitor_id,
            "error": "failed to fetch channel meta",
        }
    uploads = meta.get("uploads_playlist")
    videos: List[Dict[str, Any]] = []
    if uploads:
        vids = _fetch_uploads(uploads, max_videos)
        if vids:
            videos = _fetch_video_details(vids)

    posting = _summarize_posting(videos)

    # チャンネルプロファイル
    own_name = competitor_id
    own_concept = ""
    own_seeds: List[str] = []
    if ch_profile is None:
        try:
            from main import channel_manager  # type: ignore
        except Exception:
            channel_manager = None
        ch_profile = channel_manager.get(channel_id) if channel_manager else None

    if ch_profile is not None:
        own_name = getattr(ch_profile, "name", channel_id)
        own_concept = getattr(ch_profile, "concept", "")
        for s in getattr(ch_profile, "theme_seeds", []) or []:
            if isinstance(s, dict):
                t = s.get("title") or s.get("keyword") or s.get("angle")
                if t:
                    own_seeds.append(str(t))
            elif isinstance(s, str):
                own_seeds.append(s)

    insights = _analyze_with_claude(
        own_channel_name=own_name,
        own_concept=own_concept,
        own_seed_titles=own_seeds,
        competitor_title=meta.get("title") or competitor_id,
        competitor_videos=videos,
        posting_summary=posting,
        channel_id=channel_id,
    )
    if insights is None:
        insights = _fallback_insights(videos, posting)
    # 投稿頻度 / 曜日サマリは別フィールドにも保持
    insights["posting_summary"] = posting

    avg_views = (
        int(sum((v.get("views") or 0) for v in videos) / len(videos))
        if videos else None
    )

    top_videos = sorted(
        videos, key=lambda v: v.get("views") or 0, reverse=True
    )[:15]

    today = date.today().isoformat()
    rec_id = analytics_store.insert_competitor_analysis(
        channel_id=channel_id,
        competitor_id=competitor_id,
        competitor_title=meta.get("title"),
        subscriber_count=meta.get("subscriber_count"),
        video_count=meta.get("video_count"),
        view_count=meta.get("view_count"),
        analysis_date=today,
        insights=insights,
        top_videos=top_videos,
        posting_frequency_per_week=posting.get("posting_frequency_per_week"),
        avg_views=avg_views,
    )

    return {
        "ok": True,
        "competitor_id": competitor_id,
        "record_id": rec_id,
        "competitor_title": meta.get("title"),
        "videos_fetched": len(videos),
        "analysis_date": today,
        "insights": insights,
    }


def scan_channel(
    channel_id: str,
    *,
    max_videos_per_competitor: int = 20,
    max_competitors: int = 10,
) -> Dict[str, Any]:
    """指定チャンネルの全競合をまとめて分析。"""
    started_at = int(time.time())
    competitors = list_competitors(channel_id)[:max_competitors]
    if not competitors:
        return {
            "ok": True,
            "channel_id": channel_id,
            "started_at": started_at,
            "competitors": [],
            "note": "no competitors registered",
        }

    try:
        from main import channel_manager  # type: ignore
    except Exception:
        channel_manager = None
    ch_profile = channel_manager.get(channel_id) if channel_manager else None

    results: List[Dict[str, Any]] = []
    for cid in competitors:
        try:
            r = scan_one_competitor(
                channel_id, cid,
                max_videos=max_videos_per_competitor,
                ch_profile=ch_profile,
            )
        except Exception as e:
            r = {"ok": False, "competitor_id": cid, "error": str(e)}
        results.append(r)
        # quota 保護のため軽くスリープ
        time.sleep(0.3)

    return {
        "ok": True,
        "channel_id": channel_id,
        "started_at": started_at,
        "finished_at": int(time.time()),
        "competitors": results,
        "count": len(results),
    }


def scan_all_channels() -> Dict[str, Any]:
    """全チャンネルを順番にスキャン（scheduler 用）。"""
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
        if not list_competitors(cid):
            continue
        try:
            r = scan_channel(cid)
            results.append({
                "channel_id": cid,
                "count": r.get("count"),
                "competitors": [
                    {
                        "competitor_id": x.get("competitor_id"),
                        "ok": x.get("ok"),
                        "videos_fetched": x.get("videos_fetched"),
                        "error": x.get("error"),
                    }
                    for x in r.get("competitors", [])
                ],
            })
        except Exception as e:
            results.append({"channel_id": cid, "error": str(e)})
    return {"ok": True, "ran_at": int(time.time()), "results": results}


# ---------------------------------------------------------------------
# Read helpers (for API)
# ---------------------------------------------------------------------

def latest_analyses(channel_id: str) -> List[Dict[str, Any]]:
    return analytics_store.list_competitor_analyses(
        channel_id, latest_per_competitor=True, limit=50
    )
