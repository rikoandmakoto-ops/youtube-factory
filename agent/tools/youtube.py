"""YouTube ツール: 投稿状況の観測・アップロード・トークン更新。

既存の backend.pipeline.youtube_uploader / youtube_oauth を利用する。
トークンの自動リフレッシュは get_credentials_for に内蔵されている。
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import DATA_DIR
from .base import Tool

# 内部チャンネルID → YouTube チャンネルID は data/channels/*.json から引く
_CHANNEL_CACHE: dict[str, dict] = {}


def _channel_conf(channel_id: str) -> dict:
    if channel_id not in _CHANNEL_CACHE:
        p = DATA_DIR / "channels" / f"{channel_id}.json"
        _CHANNEL_CACHE[channel_id] = json.loads(p.read_text(encoding="utf-8"))
    return _CHANNEL_CACHE[channel_id]


def _observe_post_status(channel_id: str, max_videos: int = 5) -> dict:
    """OAuth 経由で uploads プレイリストの直近動画を取得し、今日の投稿有無を返す。"""
    from datetime import datetime, timezone

    from googleapiclient.discovery import build  # type: ignore
    from pipeline import youtube_oauth  # type: ignore

    creds = youtube_oauth.get_credentials_for(channel_id)
    if creds is None:
        return {"ok": False, "connected": False,
                "error": f"{channel_id} の YouTube OAuth トークンがない/失効。UIで再認証が必要。"}

    conf = _channel_conf(channel_id)
    yt_channel_id = conf.get("youtube_channel_id")
    # uploads プレイリストID = "UU" + チャンネルIDの3文字目以降
    uploads = "UU" + yt_channel_id[2:] if yt_channel_id else None
    if not uploads:
        return {"ok": False, "connected": True,
                "error": "youtube_channel_id が channel json にない"}

    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = yt.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads,
            maxResults=max_videos,
        ).execute()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "connected": True, "error": f"API error: {e}"}

    today = datetime.now(timezone.utc).date().isoformat()
    items = []
    posted_today = 0
    for it in resp.get("items", []):
        sn = it.get("snippet", {})
        published = (it.get("contentDetails", {}).get("videoPublishedAt")
                     or sn.get("publishedAt", ""))
        if published[:10] == today:
            posted_today += 1
        items.append({
            "title": sn.get("title"),
            "published_at": published,
            "video_id": it.get("contentDetails", {}).get("videoId"),
        })

    return {
        "ok": True,
        "connected": True,
        "channel_id": channel_id,
        "today_utc": today,
        "posted_today": posted_today,
        "recent": items,
    }


def _refresh_youtube_token(channel_id: str) -> dict:
    from pipeline import youtube_oauth  # type: ignore

    creds = youtube_oauth.get_credentials_for(channel_id)  # 内部でリフレッシュ
    if creds is None:
        return {"ok": False, "channel_id": channel_id,
                "error": "リフレッシュ失敗（refresh_token 失効の可能性）。UIで再認証が必要。"}
    return {"ok": True, "channel_id": channel_id, "valid": bool(getattr(creds, "valid", False))}


def _resolve_description(description: str) -> str:
    """description がファイルパスなら中身を読む。そうでなければそのまま返す。"""
    try:
        p = Path(description)
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return description


def _upload_to_youtube(
    channel_id: str,
    video_path: str,
    title: str,
    description: str,
    thumbnail_path: str | None = None,
    privacy: str = "public",
    is_short: bool = True,
) -> dict:
    from pipeline import youtube_uploader as yu  # type: ignore

    conf = _channel_conf(channel_id)
    yt_channel_id = conf.get("youtube_channel_id")

    if not Path(video_path).exists():
        return {"ok": False, "error": f"動画ファイルがない: {video_path}"}

    try:
        result = yu.upload_video(
            video_path=video_path,
            title=title,
            description=_resolve_description(description),
            thumbnail_path=thumbnail_path,
            privacy=privacy,
            is_short=is_short,
            channel_id=yt_channel_id,
            auth_channel_id=channel_id,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    return {"ok": True, "channel_id": channel_id, **(result or {})}


OBSERVE_STATUS_TOOL = Tool(
    name="observe_post_status",
    description=(
        "指定チャンネルの YouTube 投稿状況を観測する。直近の動画一覧と、今日(UTC)既に"
        "投稿済みかどうか(posted_today)を返す。トークン失効も検知できる。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "enum": ["scp-lab", "daily-science"]},
        },
        "required": ["channel_id"],
    },
    func=_observe_post_status,
    safe_in_dry_run=True,
)

REFRESH_TOKEN_TOOL = Tool(
    name="refresh_youtube_token",
    description=(
        "指定チャンネルの YouTube OAuth トークンを更新する（refresh_token があれば自動更新）。"
        "アップロードで認証エラーが出たときに使う。失敗したら UI 再認証が必要。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "enum": ["scp-lab", "daily-science"]},
        },
        "required": ["channel_id"],
    },
    func=_refresh_youtube_token,
    safe_in_dry_run=True,
)

UPLOAD_TOOL = Tool(
    name="upload_to_youtube",
    description=(
        "生成済みの動画ファイルを YouTube にアップロードする。description はテキストでも"
        "説明文.txt のパスでもよい。privacy 既定 public、is_short 既定 true。"
        "認証エラー時はまず refresh_youtube_token を試すこと。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "enum": ["scp-lab", "daily-science"]},
            "video_path": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string", "description": "本文テキスト、または説明文.txt のパス"},
            "thumbnail_path": {"type": "string"},
            "privacy": {"type": "string", "enum": ["public", "unlisted", "private"]},
            "is_short": {"type": "boolean"},
        },
        "required": ["channel_id", "video_path", "title", "description"],
    },
    func=_upload_to_youtube,
)
