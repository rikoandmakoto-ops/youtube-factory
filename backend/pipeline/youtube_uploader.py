#!/usr/bin/env python3
"""
YouTube Data API v3 — マルチチャンネル対応 動画アップロード・予約投稿

ブランドアカウント方式:
  1つのGoogleアカウントで複数YouTubeチャンネルを管理。
  チャンネルIDを指定してアップロード先を切り替え。

初回セットアップ:
  1. Google Cloud Console → プロジェクト作成
  2. YouTube Data API v3 有効化
  3. OAuth 2.0 クライアントID発行 (デスクトップアプリ)
  4. client_secret.json を backend/pipeline/credentials/ に配置
  5. python3 -m backend.pipeline.youtube_uploader --auth で認証
  6. python3 -m backend.pipeline.youtube_uploader --list-channels でチャンネル一覧確認
"""

import os
import json
import pickle
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    HAS_GOOGLE_API = True
except ImportError:
    HAS_GOOGLE_API = False

# ============================================================
# Config
# ============================================================
SCRIPT_DIR = Path(__file__).parent
CREDENTIALS_DIR = SCRIPT_DIR / "credentials"
CLIENT_SECRET_FILE = CREDENTIALS_DIR / "client_secret.json"
TOKEN_FILE = CREDENTIALS_DIR / "youtube_token.pickle"
CHANNELS_FILE = CREDENTIALS_DIR / "channels.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CATEGORIES = {
    "education": "27",
    "science": "28",
    "entertainment": "24",
    "howto": "26",
    "people": "22",
}
DEFAULT_CATEGORY = CATEGORIES["education"]
DEFAULT_TAGS = ["ゆっくり解説", "科学", "日常科学", "教育", "雑学"]


# ============================================================
# Authentication
# ============================================================
def ensure_deps():
    if not HAS_GOOGLE_API:
        raise RuntimeError(
            "Google API ライブラリが未インストールです:\n"
            "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )


def get_authenticated_service(auth_channel_id: str = None):
    """Get authenticated YouTube API service.

    Args:
        auth_channel_id: 内部チャンネルID。指定時はチャンネル別 OAuth トークンを使用。
            未指定時は legacy（DEFAULT_CHANNEL_ID）にフォールバック。
    """
    ensure_deps()

    # ── 1. チャンネル別 OAuth (新方式) を優先 ──
    try:
        from . import youtube_oauth as _oauth
        creds = (
            _oauth.get_credentials_for(auth_channel_id)
            if auth_channel_id
            else _oauth.get_credentials()
        )
        if creds:
            return build("youtube", "v3", credentials=creds)
    except Exception:
        pass

    # ── 2. レガシー pickle ファイル方式（CLI 専用） ──
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"client_secret.json が見つかりません: {CLIENT_SECRET_FILE}\n"
                    "Google Cloud Console → 認証情報 → OAuth 2.0 クライアントID → JSONダウンロード"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            creds = flow.run_local_server(port=8090, prompt="consent")

        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
        print(f"✅ トークン保存: {TOKEN_FILE}")

    return build("youtube", "v3", credentials=creds)


# ============================================================
# Multi-Channel (Brand Account) Management
# ============================================================
def list_youtube_channels():
    """
    List all YouTube channels accessible by the authenticated account.
    Includes brand accounts / managed channels.

    Returns:
        list of dicts: [{id, title, thumbnail, subscriber_count, is_default}, ...]
    """
    youtube = get_authenticated_service()

    # Method 1: channels.list mine=True returns the default channel
    # Method 2: channels.list managedByMe=True doesn't always work
    # Best approach: use channels.list with mine=True, then also check
    # the brandAccount channels via the same credentials

    channels = []

    # Get all channels the user can act as (including brand accounts)
    # The YouTube API's `channels.list` with `mine=True` returns the primary channel.
    # To list brand accounts, we query `youtube.channels().list(part="snippet,statistics", managedByMe=True)`
    # But this only works for content managers. Alternatively, list via `mine=True` which
    # returns the active channel, and we supplement with stored channel config.

    try:
        # Primary channel
        resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        for item in resp.get("items", []):
            channels.append(_parse_channel(item, is_default=True))
    except Exception as e:
        print(f"⚠️ プライマリチャンネル取得エラー: {e}")

    # Try managedByMe (returns brand account channels you manage)
    try:
        resp = youtube.channels().list(
            part="snippet,statistics", managedByMe=True, maxResults=50
        ).execute()
        existing_ids = {c["id"] for c in channels}
        for item in resp.get("items", []):
            if item["id"] not in existing_ids:
                channels.append(_parse_channel(item, is_default=False))
    except Exception:
        pass  # managedByMe not always available

    # Supplement with manually registered channels
    saved = _load_saved_channels()
    existing_ids = {c["id"] for c in channels}
    for sc in saved:
        if sc["id"] not in existing_ids:
            # Verify channel still exists via API
            try:
                resp = youtube.channels().list(part="snippet,statistics", id=sc["id"]).execute()
                if resp.get("items"):
                    ch = _parse_channel(resp["items"][0], is_default=False)
                    ch["custom_tags"] = sc.get("custom_tags", [])
                    ch["custom_category"] = sc.get("custom_category")
                    channels.append(ch)
            except Exception:
                channels.append(sc)  # Return saved data even if API fails

    return channels


def _parse_channel(item, is_default=False):
    """Parse a YouTube API channel item into our format."""
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    thumb = snippet.get("thumbnails", {}).get("default", {}).get("url", "")
    return {
        "id": item["id"],
        "title": snippet.get("title", ""),
        "description": snippet.get("description", "")[:100],
        "thumbnail": thumb,
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "is_default": is_default,
        "custom_tags": [],
        "custom_category": None,
    }


def add_channel(channel_id: str, custom_tags: list = None, custom_category: str = None):
    """
    Manually register a channel (brand account) by its channel ID.
    Useful when managedByMe doesn't return all brand accounts.

    Args:
        channel_id: YouTube channel ID (starts with UC...)
        custom_tags: Default tags for this channel
        custom_category: Default category ID for this channel
    """
    youtube = get_authenticated_service()

    # Verify channel exists
    resp = youtube.channels().list(part="snippet,statistics", id=channel_id).execute()
    if not resp.get("items"):
        raise ValueError(f"チャンネルが見つかりません: {channel_id}")

    ch = _parse_channel(resp["items"][0], is_default=False)
    ch["custom_tags"] = custom_tags or []
    ch["custom_category"] = custom_category

    # Save to channels.json
    saved = _load_saved_channels()
    # Update or add
    saved = [s for s in saved if s["id"] != channel_id]
    saved.append(ch)
    _save_channels(saved)

    print(f"✅ チャンネル追加: {ch['title']} ({channel_id})")
    return ch


def remove_channel(channel_id: str):
    """Remove a manually registered channel."""
    saved = _load_saved_channels()
    saved = [s for s in saved if s["id"] != channel_id]
    _save_channels(saved)
    print(f"🗑️ チャンネル削除: {channel_id}")


def update_channel_config(channel_id: str, custom_tags: list = None, custom_category: str = None):
    """Update channel-specific settings (default tags, category)."""
    saved = _load_saved_channels()
    for ch in saved:
        if ch["id"] == channel_id:
            if custom_tags is not None:
                ch["custom_tags"] = custom_tags
            if custom_category is not None:
                ch["custom_category"] = custom_category
            _save_channels(saved)
            return ch
    raise ValueError(f"チャンネルが見つかりません: {channel_id}")


def _load_saved_channels():
    """Load manually registered channels from channels.json."""
    if CHANNELS_FILE.exists():
        try:
            return json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_channels(channels):
    """Save channels to channels.json."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    CHANNELS_FILE.write_text(
        json.dumps(channels, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ============================================================
# Auth Status (multi-channel aware)
# ============================================================
def check_auth_status():
    """Check YouTube authentication status with channel list."""
    status = {
        "has_client_secret": CLIENT_SECRET_FILE.exists(),
        "has_token": TOKEN_FILE.exists(),
        "token_valid": False,
        "channel_name": None,
        "channels": [],
    }

    if not status["has_token"]:
        return status

    try:
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
        if creds and creds.valid:
            status["token_valid"] = True
        elif creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            status["token_valid"] = True
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(creds, f)

        if status["token_valid"]:
            channels = list_youtube_channels()
            status["channels"] = channels
            if channels:
                default_ch = next((c for c in channels if c["is_default"]), channels[0])
                status["channel_name"] = default_ch["title"]
    except Exception as e:
        status["token_valid"] = False
        status["error"] = str(e)

    return status


# ============================================================
# Upload (channel_id対応)
# ============================================================
def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list = None,
    thumbnail_path: str = None,
    scheduled_at: str = None,
    privacy: str = "private",
    category_id: str = DEFAULT_CATEGORY,
    is_short: bool = False,
    made_for_kids: bool = False,
    channel_id: str = None,
    auth_channel_id: str = None,
):
    """
    Upload a video to YouTube with optional scheduling.
    Supports uploading to a specific channel (brand account) via onBehalfOfContentOwner
    or by switching the active channel.

    Args:
        channel_id: Target YouTube channel ID (UC...). If None, uploads to default channel.
        auth_channel_id: 内部チャンネルID — per-channel OAuth トークンを使う場合に指定。
        (other args same as before)
    """
    ensure_deps()

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")

    # Channel-specific defaults
    if channel_id and tags is None:
        saved = _load_saved_channels()
        ch_config = next((c for c in saved if c["id"] == channel_id), None)
        if ch_config and ch_config.get("custom_tags"):
            tags = ch_config["custom_tags"]
        if ch_config and ch_config.get("custom_category"):
            category_id = ch_config["custom_category"]

    if tags is None:
        tags = DEFAULT_TAGS.copy()

    if is_short and "#Shorts" not in tags:
        tags.insert(0, "#Shorts")

    if scheduled_at:
        privacy = "private"

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "ja",
            "defaultAudioLanguage": "ja",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    # Channel targeting: set channelId in snippet for brand accounts
    if channel_id:
        body["snippet"]["channelId"] = channel_id

    if scheduled_at:
        body["status"]["publishAt"] = _normalize_datetime(scheduled_at)

    print(f"📤 アップロード開始: {video_path.name}")
    print(f"   タイトル: {title[:50]}...")
    print(f"   チャンネル: {channel_id or 'デフォルト'}")
    if scheduled_at:
        print(f"   予約公開: {scheduled_at}")

    youtube = get_authenticated_service(auth_channel_id=auth_channel_id)

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )

    insert_kwargs = {
        "part": "snippet,status",
        "body": body,
        "media_body": media,
    }

    request = youtube.videos().insert(**insert_kwargs)
    response = _resumable_upload(request)
    video_id = response["id"]

    print(f"✅ アップロード完了: https://youtube.com/watch?v={video_id}")

    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
            ).execute()
            print(f"🖼️ サムネイル設定完了")
        except Exception as e:
            print(f"⚠️ サムネイル設定失敗: {e}")

    result = {
        "video_id": video_id,
        "url": f"https://youtube.com/watch?v={video_id}",
        "status": privacy,
        "title": title,
        "channel_id": channel_id,
    }
    if scheduled_at:
        result["scheduled_at"] = scheduled_at

    return result


def delete_video(video_id: str, auth_channel_id: str = None) -> dict:
    """
    Delete a video from YouTube via the Data API.

    Requires the `youtube.force-ssl` OAuth scope. トークンが古いスコープの場合は
    再認証が必要（403 insufficientPermissions になる）。

    Args:
        video_id: 削除する YouTube 動画ID。
        auth_channel_id: 内部チャンネルID — per-channel OAuth トークンを使う場合に指定。

    Returns:
        {"video_id": ..., "deleted": True}
    """
    ensure_deps()
    if not video_id:
        raise ValueError("video_id is required")

    youtube = get_authenticated_service(auth_channel_id=auth_channel_id)
    youtube.videos().delete(id=video_id).execute()
    print(f"🗑️ 動画削除完了: {video_id}")
    return {"video_id": video_id, "deleted": True}


def _resumable_upload(request):
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"   ⬆️ {pct}%")
    return response


def _normalize_datetime(dt_str: str) -> str:
    """Normalize to YouTube API UTC format."""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(dt_str)
    except (ImportError, ValueError):
        dt = datetime.fromisoformat(dt_str)

    if dt.tzinfo is None:
        from datetime import timedelta
        jst = timezone(timedelta(hours=9))
        dt = dt.replace(tzinfo=jst)

    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.0Z")


# ============================================================
# Batch upload (channel_id対応)
# ============================================================
def upload_generated_videos(
    output_dir: str,
    prefix: str,
    scheduled_at: str = None,
    short_scheduled_at: str = None,
    upload_main: bool = True,
    upload_short: bool = True,
    channel_id: str = None,
    auth_channel_id: str = None,
):
    """Upload generated videos, optionally targeting a specific channel."""
    out = Path(output_dir)
    results = {}

    main_desc_file = out / f"{prefix}_メイン_説明文.txt"
    short_desc_file = out / f"{prefix}_ショート_説明文.txt"

    main_desc = main_desc_file.read_text(encoding="utf-8") if main_desc_file.exists() else ""
    short_desc = short_desc_file.read_text(encoding="utf-8") if short_desc_file.exists() else ""

    def extract_title(desc):
        for line in desc.split("\n"):
            if line.startswith("タイトル:") or line.startswith("タイトル："):
                return line.split(":", 1)[-1].split("：", 1)[-1].strip()
        return ""

    def strip_title_line(desc):
        return "\n".join(
            line for line in desc.split("\n")
            if not line.startswith("タイトル:") and not line.startswith("タイトル：")
        ).strip()

    if upload_main:
        main_video = out / f"{prefix}_メイン.mp4"
        main_thumb = out / f"{prefix}_サムネイル.png"
        if main_video.exists():
            results["main"] = upload_video(
                video_path=str(main_video),
                title=extract_title(main_desc),
                description=strip_title_line(main_desc),
                thumbnail_path=str(main_thumb) if main_thumb.exists() else None,
                scheduled_at=scheduled_at,
                is_short=False,
                channel_id=channel_id,
                auth_channel_id=auth_channel_id,
            )

    if upload_short:
        short_video = out / f"{prefix}_ショート.mp4"
        short_thumb = out / f"{prefix}_ショート_サムネイル.png"
        if short_video.exists():
            results["short"] = upload_video(
                video_path=str(short_video),
                title=extract_title(short_desc),
                description=strip_title_line(short_desc),
                thumbnail_path=str(short_thumb) if short_thumb.exists() else None,
                scheduled_at=short_scheduled_at or scheduled_at,
                is_short=True,
                channel_id=channel_id,
                auth_channel_id=auth_channel_id,
            )

    return results


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="YouTube アップロード (マルチチャンネル対応)")
    parser.add_argument("--auth", action="store_true", help="初回認証")
    parser.add_argument("--status", action="store_true", help="認証状態確認")
    parser.add_argument("--list-channels", action="store_true", help="チャンネル一覧")
    parser.add_argument("--add-channel", help="チャンネルID追加 (UC...)")
    parser.add_argument("--remove-channel", help="チャンネルID削除")
    parser.add_argument("--channel", help="アップロード先チャンネルID")
    parser.add_argument("--upload", help="動画ファイルパス")
    parser.add_argument("--title", help="動画タイトル")
    parser.add_argument("--description", help="説明文")
    parser.add_argument("--thumbnail", help="サムネイル画像パス")
    parser.add_argument("--schedule", help="予約公開日時 (ISO 8601)")
    parser.add_argument("--short", action="store_true", help="Shortとしてアップロード")
    parser.add_argument("--batch-dir", help="一括アップロード: 出力ディレクトリ")
    parser.add_argument("--prefix", help="一括アップロード: ファイルプレフィックス")
    args = parser.parse_args()

    if args.auth:
        print("🔑 YouTube認証を開始します...")
        get_authenticated_service()
        status = check_auth_status()
        if status.get("channels"):
            print(f"✅ {len(status['channels'])} チャンネルが見つかりました:")
            for ch in status["channels"]:
                mark = "⭐" if ch.get("is_default") else "  "
                print(f"  {mark} {ch['title']} ({ch['id']})")
        return

    if args.status:
        print(json.dumps(check_auth_status(), ensure_ascii=False, indent=2))
        return

    if args.list_channels:
        channels = list_youtube_channels()
        for ch in channels:
            mark = "⭐" if ch.get("is_default") else "  "
            print(f"{mark} {ch['title']}")
            print(f"   ID: {ch['id']}")
            print(f"   登録者: {ch['subscriber_count']:,}  動画数: {ch['video_count']}")
            if ch.get("custom_tags"):
                print(f"   タグ: {', '.join(ch['custom_tags'])}")
            print()
        return

    if args.add_channel:
        add_channel(args.add_channel)
        return

    if args.remove_channel:
        remove_channel(args.remove_channel)
        return

    if args.batch_dir and args.prefix:
        results = upload_generated_videos(
            output_dir=args.batch_dir,
            prefix=args.prefix,
            scheduled_at=args.schedule,
            channel_id=args.channel,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if args.upload:
        if not args.title:
            print("❌ --title が必要です")
            return
        result = upload_video(
            video_path=args.upload,
            title=args.title,
            description=args.description or "",
            thumbnail_path=args.thumbnail,
            scheduled_at=args.schedule,
            is_short=args.short,
            channel_id=args.channel,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
