"""
YouTube Analytics API v2 連携 — チャンネル別 OAuth でメトリクスを取得し SQLite に永続化。

提供する関数（チャンネル別。channel_id は内部 channel_id 文字列）:
  - fetch_channel_overview(channel_id, days=30)
      チャンネル全体の直近メトリクス（views, watch_time, subs gained/lost）を取得・保存。
  - fetch_video_metrics(channel_id, video_ids=None, days=30)
      指定動画（未指定なら直近の動画を YouTube Data API で列挙）のメトリクスを取得・保存。
  - fetch_retention(channel_id, video_id)
      audienceWatchRatio / relativeRetentionPerformance を取得・保存（カーブ）。
  - sync_channel(channel_id, days=30, max_videos=50)
      上記をまとめて実行し、サマリを返す。

YouTube Analytics API v2 は OAuth が必須（API key 不可）。
yt-analytics.readonly スコープは既に `youtube_oauth.SCOPES` に含まれている。
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from . import youtube_oauth as yt_oauth
from .analytics import store as analytics_store


# ---------------------------------------------------------------------
# Service builders
# ---------------------------------------------------------------------

def _build_analytics_service(channel_id: str):
    """YouTube Analytics API v2 サービスを返す（未連携 / ライブラリ未導入なら None）。"""
    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception:
        return None
    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return None
    try:
        return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def _build_data_service(channel_id: str):
    """YouTube Data API v3 サービスを返す（OAuth 経由）。"""
    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception:
        return None
    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return None
    try:
        return build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def _today() -> date:
    return datetime.utcnow().date()


def _date_str(d: date) -> str:
    return d.isoformat()


# ---------------------------------------------------------------------
# YouTube channel discovery
# ---------------------------------------------------------------------

def _resolve_youtube_channel_id(channel_id: str) -> Optional[str]:
    """OAuth 連携時に保存されている YouTube の channel_id を返す。
    未保存なら API で取得して埋める。"""
    d = yt_oauth.load_credentials_dict_for(channel_id)
    if not d:
        return None
    yt_channel = d.get("_youtube_channel_id")
    if yt_channel:
        return yt_channel
    svc = _build_data_service(channel_id)
    if not svc:
        return None
    try:
        resp = svc.channels().list(part="id", mine=True).execute()
        items = resp.get("items", [])
        if items:
            return items[0].get("id")
    except Exception:
        return None
    return None


def _list_recent_video_ids(
    channel_id: str, max_videos: int = 50
) -> List[Dict[str, Any]]:
    """チャンネルにアップロード済みの動画を新着順で max_videos 件返す。
    返り値は [{"video_id","title","published_at"}, ...]。"""
    svc = _build_data_service(channel_id)
    if not svc:
        return []
    try:
        ch = svc.channels().list(part="contentDetails", mine=True).execute()
        items = ch.get("items", [])
        if not items:
            return []
        uploads = (
            items[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if not uploads:
            return []
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while len(out) < max_videos:
        try:
            resp = (
                svc.playlistItems()
                .list(
                    part="contentDetails,snippet",
                    playlistId=uploads,
                    maxResults=min(50, max_videos - len(out)),
                    pageToken=page_token,
                )
                .execute()
            )
        except Exception:
            break
        for it in resp.get("items", []):
            cd = it.get("contentDetails", {}) or {}
            sn = it.get("snippet", {}) or {}
            vid = cd.get("videoId")
            if not vid:
                continue
            out.append(
                {
                    "video_id": vid,
                    "title": sn.get("title"),
                    "published_at": cd.get("videoPublishedAt") or sn.get("publishedAt"),
                }
            )
            if len(out) >= max_videos:
                break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def fetch_channel_overview(channel_id: str, *, days: int = 30) -> Dict[str, Any]:
    """チャンネル全体のメトリクス（直近 days 日）を取得し SQLite に保存。"""
    analytics = _build_analytics_service(channel_id)
    if not analytics:
        return {
            "channel_id": channel_id,
            "ok": False,
            "error": "OAuth 未連携または googleapiclient 未導入",
        }
    end = _today()
    start = end - timedelta(days=days)
    try:
        resp = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=_date_str(start),
                endDate=_date_str(end),
                metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
                dimensions="day",
                sort="day",
            )
            .execute()
        )
    except Exception as e:
        return {"channel_id": channel_id, "ok": False, "error": f"analytics query failed: {e}"}

    rows = resp.get("rows", []) or []
    headers = [h.get("name") for h in resp.get("columnHeaders", [])]
    idx = {h: i for i, h in enumerate(headers)}

    totals = {
        "views": 0,
        "watch_time_minutes": 0.0,
        "subscribers_gained": 0,
        "subscribers_lost": 0,
    }
    days_payload: List[Dict[str, Any]] = []
    for row in rows:
        d = row[idx["day"]]
        v = int(row[idx["views"]] or 0)
        wt = float(row[idx["estimatedMinutesWatched"]] or 0)
        sg = int(row[idx["subscribersGained"]] or 0)
        sl = int(row[idx["subscribersLost"]] or 0)
        analytics_store.upsert_channel_metric(
            channel_id=channel_id,
            date=d,
            views=v,
            watch_time_minutes=wt,
            subscribers_gained=sg,
            subscribers_lost=sl,
        )
        days_payload.append(
            {
                "date": d,
                "views": v,
                "watch_time_minutes": wt,
                "subscribers_gained": sg,
                "subscribers_lost": sl,
            }
        )
        totals["views"] += v
        totals["watch_time_minutes"] += wt
        totals["subscribers_gained"] += sg
        totals["subscribers_lost"] += sl

    return {
        "channel_id": channel_id,
        "ok": True,
        "days": days_payload,
        "totals": totals,
        "range": {"start": _date_str(start), "end": _date_str(end)},
    }


def fetch_video_metrics(
    channel_id: str,
    video_ids: Optional[List[str]] = None,
    *,
    days: int = 30,
    max_videos: int = 50,
) -> Dict[str, Any]:
    """動画別メトリクスを取得・保存。

    video_ids 未指定なら uploads プレイリストから新着順で max_videos 件取得する。
    """
    analytics = _build_analytics_service(channel_id)
    data = _build_data_service(channel_id)
    if not analytics or not data:
        return {
            "channel_id": channel_id,
            "ok": False,
            "error": "OAuth 未連携または googleapiclient 未導入",
        }

    if not video_ids:
        recent = _list_recent_video_ids(channel_id, max_videos=max_videos)
    else:
        try:
            resp = (
                data.videos()
                .list(part="snippet", id=",".join(video_ids[:50]))
                .execute()
            )
        except Exception:
            resp = {"items": []}
        recent = []
        for it in resp.get("items", []):
            sn = it.get("snippet", {}) or {}
            recent.append(
                {
                    "video_id": it.get("id"),
                    "title": sn.get("title"),
                    "published_at": sn.get("publishedAt"),
                }
            )

    if not recent:
        return {"channel_id": channel_id, "ok": True, "items": [], "note": "no videos found"}

    end = _today()
    start = end - timedelta(days=days)
    snapshot_date = _date_str(end)

    items_out: List[Dict[str, Any]] = []
    for v in recent:
        vid = v["video_id"]
        metrics = _query_video_analytics(analytics, vid, start, end)
        # CTR / impressions / avg_view_percentage は別ディメンションで取れる
        ctr_pkg = _query_video_ctr(analytics, vid, start, end)
        merged = {**metrics, **ctr_pkg}

        analytics_store.upsert_video_metric(
            video_id=vid,
            channel_id=channel_id,
            date=snapshot_date,
            title=v.get("title"),
            published_at=v.get("published_at"),
            views=merged.get("views", 0),
            watch_time_minutes=merged.get("watch_time_minutes", 0.0),
            avg_view_duration=merged.get("avg_view_duration", 0.0),
            avg_view_percentage=merged.get("avg_view_percentage", 0.0),
            impressions=merged.get("impressions", 0),
            ctr=merged.get("ctr", 0.0),
            likes=merged.get("likes", 0),
            comments=merged.get("comments", 0),
            shares=merged.get("shares", 0),
            subscribers_gained=merged.get("subscribers_gained", 0),
        )
        items_out.append({"video_id": vid, "title": v.get("title"), **merged})
        # API クォータと相手側レート制限を考慮した軽い間隔
        time.sleep(0.05)

    return {
        "channel_id": channel_id,
        "ok": True,
        "items": items_out,
        "range": {"start": _date_str(start), "end": _date_str(end)},
    }


def _query_video_analytics(
    analytics, video_id: str, start: date, end: date
) -> Dict[str, Any]:
    """1動画の基本メトリクス（views, watch_time, avgDuration, likes, comments, shares）。"""
    try:
        resp = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=_date_str(start),
                endDate=_date_str(end),
                metrics=(
                    "views,estimatedMinutesWatched,averageViewDuration,"
                    "likes,comments,shares,subscribersGained"
                ),
                filters=f"video=={video_id}",
            )
            .execute()
        )
    except Exception:
        return {}
    rows = resp.get("rows", []) or []
    if not rows:
        return {
            "views": 0,
            "watch_time_minutes": 0.0,
            "avg_view_duration": 0.0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "subscribers_gained": 0,
        }
    headers = [h.get("name") for h in resp.get("columnHeaders", [])]
    idx = {h: i for i, h in enumerate(headers)}
    r = rows[0]

    def _get(name: str, default=0):
        return r[idx[name]] if name in idx else default

    return {
        "views": int(_get("views", 0) or 0),
        "watch_time_minutes": float(_get("estimatedMinutesWatched", 0) or 0),
        "avg_view_duration": float(_get("averageViewDuration", 0) or 0),
        "likes": int(_get("likes", 0) or 0),
        "comments": int(_get("comments", 0) or 0),
        "shares": int(_get("shares", 0) or 0),
        "subscribers_gained": int(_get("subscribersGained", 0) or 0),
    }


def _query_video_ctr(
    analytics, video_id: str, start: date, end: date
) -> Dict[str, Any]:
    """impressions / CTR / 視聴維持率の平均。
    cardImpressions vs cardClickRate ではなく、サムネ impressions の方を使う。
    """
    try:
        resp = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=_date_str(start),
                endDate=_date_str(end),
                metrics=(
                    "cardImpressions,cardClickRate,"
                    "averageViewPercentage"
                ),
                filters=f"video=={video_id}",
            )
            .execute()
        )
    except Exception:
        resp = {"rows": []}
    impressions = 0
    ctr = 0.0
    avg_view_percentage = 0.0
    rows = resp.get("rows", []) or []
    if rows:
        headers = [h.get("name") for h in resp.get("columnHeaders", [])]
        idx = {h: i for i, h in enumerate(headers)}
        r = rows[0]
        if "cardImpressions" in idx:
            impressions = int(r[idx["cardImpressions"]] or 0)
        if "cardClickRate" in idx:
            ctr = float(r[idx["cardClickRate"]] or 0)
        if "averageViewPercentage" in idx:
            avg_view_percentage = float(r[idx["averageViewPercentage"]] or 0)

    # サムネ impressions/CTR は別レポート (Creator Studio の "impressions" 系)
    # こちらは権限スコープで取れないことが多いので best-effort
    try:
        resp2 = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=_date_str(start),
                endDate=_date_str(end),
                metrics="impressions,impressionsClickThroughRate",
                filters=f"video=={video_id}",
            )
            .execute()
        )
        rows2 = resp2.get("rows", []) or []
        if rows2:
            headers2 = [h.get("name") for h in resp2.get("columnHeaders", [])]
            idx2 = {h: i for i, h in enumerate(headers2)}
            r2 = rows2[0]
            if "impressions" in idx2:
                impressions = int(r2[idx2["impressions"]] or impressions)
            if "impressionsClickThroughRate" in idx2:
                ctr = float(r2[idx2["impressionsClickThroughRate"]] or ctr)
    except Exception:
        pass

    return {
        "impressions": impressions,
        "ctr": ctr,
        "avg_view_percentage": avg_view_percentage,
    }


def fetch_retention(channel_id: str, video_id: str) -> Dict[str, Any]:
    """1動画の audienceWatchRatio カーブを取得・保存。"""
    analytics = _build_analytics_service(channel_id)
    if not analytics:
        return {"ok": False, "error": "OAuth 未連携または googleapiclient 未導入"}
    end = _today()
    start = end - timedelta(days=90)
    try:
        resp = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=_date_str(start),
                endDate=_date_str(end),
                metrics="audienceWatchRatio,relativeRetentionPerformance",
                dimensions="elapsedVideoTimeRatio",
                filters=f"video=={video_id}",
                sort="elapsedVideoTimeRatio",
            )
            .execute()
        )
    except Exception as e:
        return {"ok": False, "error": f"retention query failed: {e}"}

    rows = resp.get("rows", []) or []
    curve: List[Dict[str, float]] = []
    for row in rows:
        if len(row) < 2:
            continue
        ratio = float(row[0] or 0)
        awr = float(row[1] or 0)
        rrp = float(row[2] or 0) if len(row) > 2 else 0.0
        curve.append(
            {
                "ratio": ratio,
                "audience_watch_ratio": awr,
                "relative_retention": rrp,
            }
        )
    analytics_store.save_retention(video_id, channel_id, curve)
    return {"ok": True, "video_id": video_id, "curve": curve}


def sync_channel(
    channel_id: str,
    *,
    days: int = 30,
    max_videos: int = 50,
    fetch_retention_for: int = 5,
) -> Dict[str, Any]:
    """まとめて同期。返り値は各 fetch_* のサマリを束ねたもの。"""
    overview = fetch_channel_overview(channel_id, days=days)
    videos = fetch_video_metrics(channel_id, days=days, max_videos=max_videos)
    retention: List[Dict[str, Any]] = []
    if videos.get("ok"):
        top = sorted(
            videos.get("items", []) or [],
            key=lambda v: int(v.get("views", 0) or 0),
            reverse=True,
        )[:fetch_retention_for]
        for v in top:
            r = fetch_retention(channel_id, v["video_id"])
            retention.append(
                {"video_id": v["video_id"], "ok": r.get("ok"), "error": r.get("error")}
            )
            time.sleep(0.05)

    return {
        "channel_id": channel_id,
        "overview": overview,
        "videos": videos,
        "retention": retention,
        "synced_at": int(time.time()),
    }
