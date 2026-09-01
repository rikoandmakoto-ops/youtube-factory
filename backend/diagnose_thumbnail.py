#!/usr/bin/env python3
"""
サムネイルアップロード診断スクリプト

使い方:
  # daily-science のサムネイル権限を確認
  python3 backend/diagnose_thumbnail.py --channel daily-science

  # 特定の動画にサムネイルをアップロード
  python3 backend/diagnose_thumbnail.py --channel daily-science --video VIDEO_ID --thumb /path/to/thumb.png

  # 全チャンネルの状態を一覧
  python3 backend/diagnose_thumbnail.py --all
"""

import os
import sys
import json
import argparse
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

# .env 読み込み
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def check_channel(channel_id: str) -> dict:
    """チャンネルのサムネイルアップロード権限を診断"""
    from pipeline import youtube_oauth as yo

    result = {
        "channel_id": channel_id,
        "oauth_connected": False,
        "scopes": [],
        "has_upload_scope": False,
        "creds_valid": False,
        "custom_thumbnail_allowed": None,
        "error": None,
    }

    # 1. OAuth 状態チェック
    status = yo.get_status_for(channel_id)
    result["oauth_connected"] = status.get("connected", False)
    result["scopes"] = status.get("scopes", [])
    result["has_upload_scope"] = any(
        "youtube.upload" in s for s in result["scopes"]
    )
    result["needs_reauth"] = status.get("needs_reauth", False)
    result["auth_error"] = status.get("auth_error")
    result["youtube_channel_id"] = status.get("youtube_channel_id")
    result["youtube_channel_name"] = status.get("youtube_channel_name")

    if not result["oauth_connected"]:
        result["error"] = "OAuth 未連携 or トークン期限切れ"
        return result

    # 2. Credentials 取得テスト
    creds = yo.get_credentials_for(channel_id)
    if not creds:
        result["error"] = "Credentials 取得失敗（refresh 失敗?）"
        err = yo.get_auth_error_for(channel_id)
        if err:
            result["error"] += f": {err.get('error')}: {err.get('detail')}"
        return result

    result["creds_valid"] = True

    # 3. YouTube API でチャンネルの機能ステータスを確認
    try:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        # チャンネル情報取得
        ch_resp = youtube.channels().list(
            part="status,snippet",
            mine=True,
        ).execute()
        items = ch_resp.get("items", [])
        if items:
            ch_item = items[0]
            result["channel_title"] = ch_item["snippet"]["title"]
            result["channel_status"] = ch_item.get("status", {})
            # longUploadsStatus が "allowed" なら電話認証済み
            long_uploads = ch_item.get("status", {}).get("longUploadsStatus")
            result["long_uploads_status"] = long_uploads
            # カスタムサムネイル: YouTube API v3 には直接的な
            # "customThumbnailAllowed" フィールドはないが、
            # 実際に thumbnails.set を試行して判定する
        else:
            result["error"] = "チャンネル情報取得失敗（items 空）"

    except Exception as e:
        result["error"] = f"API エラー: {e}"

    return result


def test_thumbnail_upload(channel_id: str, video_id: str, thumb_path: str) -> dict:
    """実際にサムネイルをアップロードして結果を返す"""
    from pipeline import youtube_oauth as yo
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    result = {"channel_id": channel_id, "video_id": video_id, "thumb_path": thumb_path}

    if not Path(thumb_path).exists():
        result["error"] = f"サムネイルファイルが見つかりません: {thumb_path}"
        return result

    # ファイルサイズチェック (YouTube 上限 2MB)
    size_bytes = Path(thumb_path).stat().st_size
    result["file_size_bytes"] = size_bytes
    result["file_size_mb"] = round(size_bytes / 1024 / 1024, 2)
    if size_bytes > 2 * 1024 * 1024:
        result["warning"] = f"ファイルサイズ {result['file_size_mb']}MB — YouTube 上限 2MB を超過"

    creds = yo.get_credentials_for(channel_id)
    if not creds:
        result["error"] = "OAuth 未連携 or トークン期限切れ"
        return result

    try:
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumb_path, mimetype="image/png"),
        ).execute()
        result["success"] = True
        result["response"] = resp
        print(f"✅ サムネイルアップロード成功: {video_id}")
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        # エラーの詳細分析
        err_str = str(e)
        if "doesn't have permissions to upload and set custom video thumbnails" in err_str:
            result["diagnosis"] = (
                "YouTube チャンネルの電話番号認証が未完了。"
                "YouTube Studio → 設定 → チャンネル → 機能の利用資格 → 「電話番号を確認」"
            )
        elif "insufficientPermissions" in err_str:
            result["diagnosis"] = (
                "OAuth スコープ不足。youtube.upload スコープを含む再認可が必要"
            )
        elif "videoNotFound" in err_str:
            result["diagnosis"] = f"動画 {video_id} が見つかりません（削除済み or 別チャンネル?）"
        elif "forbidden" in err_str.lower():
            result["diagnosis"] = "アクセス拒否。チャンネルの所有権・権限を確認してください"
        print(f"❌ サムネイルアップロード失敗: {e}")

    return result


def get_recent_videos(channel_id: str, max_results: int = 5) -> list:
    """チャンネルの直近動画一覧を取得"""
    from pipeline import youtube_oauth as yo
    from googleapiclient.discovery import build

    creds = yo.get_credentials_for(channel_id)
    if not creds:
        return []

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    # 自分の動画を検索
    resp = youtube.search().list(
        part="snippet",
        forMine=True,
        type="video",
        order="date",
        maxResults=max_results,
    ).execute()

    videos = []
    for item in resp.get("items", []):
        vid = item["id"].get("videoId")
        snip = item.get("snippet", {})
        videos.append({
            "video_id": vid,
            "title": snip.get("title", ""),
            "published_at": snip.get("publishedAt", ""),
            "thumbnail_url": snip.get("thumbnails", {}).get("default", {}).get("url", ""),
        })
    return videos


def main():
    parser = argparse.ArgumentParser(description="サムネイルアップロード診断")
    parser.add_argument("--channel", "-c", help="内部チャンネルID (例: daily-science)")
    parser.add_argument("--all", "-a", action="store_true", help="全チャンネルの状態を一覧")
    parser.add_argument("--video", "-v", help="テストアップロード先の YouTube 動画ID")
    parser.add_argument("--thumb", "-t", help="アップロードするサムネイル画像パス")
    parser.add_argument("--recent", "-r", action="store_true", help="直近動画を表示")
    args = parser.parse_args()

    if args.all:
        from pipeline import youtube_oauth as yo

        channels = yo.list_connected_channels()
        print(f"\n📊 連携済みチャンネル: {len(channels)} 件\n")
        print(f"{'チャンネルID':<20} {'YouTube名':<30} {'OAuth':>5} {'upload scope':>12} {'エラー'}")
        print("-" * 100)
        for ch_id, yt_ch_id, yt_ch_name in channels:
            r = check_channel(ch_id)
            scope_ok = "✅" if r["has_upload_scope"] else "❌"
            oauth_ok = "✅" if r["creds_valid"] else "❌"
            err = r.get("error") or r.get("auth_error") or ""
            print(f"{ch_id:<20} {(yt_ch_name or ''):<30} {oauth_ok:>5} {scope_ok:>12} {err}")
        return

    if not args.channel:
        parser.print_help()
        return

    # チャンネル診断
    print(f"\n🔍 チャンネル診断: {args.channel}\n")
    result = check_channel(args.channel)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    # 直近動画表示
    if args.recent:
        print(f"\n📹 直近動画:")
        videos = get_recent_videos(args.channel)
        for v in videos:
            print(f"  {v['video_id']} | {v['title'][:50]} | {v['published_at']}")

    # サムネイルテストアップロード
    if args.video and args.thumb:
        print(f"\n🖼️ サムネイルテストアップロード:")
        test_result = test_thumbnail_upload(args.channel, args.video, args.thumb)
        print(json.dumps(test_result, indent=2, ensure_ascii=False, default=str))
    elif args.video:
        print("\n⚠️ --thumb も指定してください")


if __name__ == "__main__":
    main()
