#!/usr/bin/env python3
"""
TikTok Content Posting API — 動画アップロード（チャンネル別 OAuth 対応）

YouTube (`youtube_uploader.py`) と並行して動く TikTok 投稿モジュール。
内部 channel_id ごとに保存された OAuth トークン（`tiktok_oauth.py`）を使う。

投稿フロー（Direct Post / FILE_UPLOAD）:
  1. POST /v2/post/publish/creator_info/query/   … 投稿可能な privacy 等を取得
  2. POST /v2/post/publish/video/init/           … publish_id と upload_url を取得
  3. PUT  {upload_url}                            … 動画をチャンク分割アップロード
  4. POST /v2/post/publish/status/fetch/         … 公開ステータスをポーリング

重要な制限（2026 時点）:
  - **未審査(unaudited)アプリ**は全投稿が SELF_ONLY（非公開）に強制される。
    一般公開するにはアプリの監査(audit)通過が必要。
  - 動画は MP4(H.264) / 3〜600秒 / 最大 4GB。
  - チャンク: 最小 5MB・最大 64MB（最終チャンクのみ最大 128MB）、最大 1000 チャンク。
    5MB 未満は単一チャンクで丸ごと送る。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests  # type: ignore
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from . import tiktok_oauth

# ── エンドポイント ──
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
VIDEO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# ── チャンク仕様 ──
MIN_CHUNK = 5 * 1024 * 1024          # 5 MB
MAX_CHUNK = 64 * 1024 * 1024         # 64 MB
MAX_CHUNK_COUNT = 1000

# ── デフォルト ──
DEFAULT_PRIVACY = "SELF_ONLY"        # 未審査アプリでは SELF_ONLY が強制される
VALID_PRIVACY = {"PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"}
DEFAULT_HASHTAGS = ["#fyp", "#おすすめ"]
MAX_TITLE_LEN = 2200                 # TikTok caption 上限（概ね 2200 文字）

_HTTP_TIMEOUT = 60
_UPLOAD_TIMEOUT = 600


def _ensure_requests() -> None:
    if not HAS_REQUESTS:
        raise RuntimeError("requests がインストールされていません: pip install requests")


# =====================================================================
# キャプション整形（YouTube の説明文 → TikTok 向け）
# =====================================================================

def build_caption(
    title: str,
    description: str = "",
    hashtags: Optional[List[str]] = None,
) -> str:
    """TikTok の caption（title フィールド）を組み立てる。

    TikTok は概要欄を持たず caption 1 本なので、タイトル + 説明の要点 + ハッシュタグを
    1 つの文字列にまとめる。URL は TikTok caption ではクリックできないため除去する。
    """
    tags = hashtags if hashtags is not None else DEFAULT_HASHTAGS
    # "#" を正規化（重複付与を避ける）
    norm_tags = []
    seen = set()
    for t in tags:
        t = t.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t.lstrip("#")
        key = t.lower()
        if key not in seen:
            seen.add(key)
            norm_tags.append(t)

    parts: List[str] = []
    if title:
        parts.append(title.strip())

    if description:
        # URL 行は TikTok では無意味なので落とす。先頭数行だけ拾って簡潔に。
        lines = []
        for line in description.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("http://") or s.startswith("https://"):
                continue
            if s.startswith("▼") or s.startswith("🎬") or s.startswith("【関連"):
                continue
            lines.append(s)
            if len(lines) >= 3:
                break
        if lines:
            parts.append(" ".join(lines))

    caption = "\n".join(parts).strip()
    if norm_tags:
        caption = (caption + "\n" + " ".join(norm_tags)).strip()
    return caption[:MAX_TITLE_LEN]


# =====================================================================
# Creator info
# =====================================================================

def query_creator_info(access_token: str) -> Dict[str, Any]:
    """投稿前に呼ぶ必須クエリ。許可された privacy_level や最大尺を返す。"""
    _ensure_requests()
    resp = requests.post(
        CREATOR_INFO_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=_HTTP_TIMEOUT,
    )
    body = resp.json()
    err = body.get("error", {})
    if err and err.get("code") not in ("ok", None, ""):
        raise RuntimeError(
            f"creator_info 取得失敗: {err.get('code')} - {err.get('message')}"
        )
    return body.get("data", {})


# =====================================================================
# チャンク計算
# =====================================================================

def _plan_chunks(video_size: int) -> Dict[str, int]:
    """video_size から chunk_size / total_chunk_count を決める。

    - 5MB 未満: 単一チャンク（chunk_size = video_size）
    - 5MB〜64MB: 単一チャンク（chunk_size = video_size）
    - 64MB 超: 64MB チャンク。total_chunk_count = floor(video_size / chunk_size)。
      端数は最終チャンクに吸収させる（最終チャンクは最大 128MB まで）。
    """
    if video_size <= MAX_CHUNK:
        return {"chunk_size": video_size, "total_chunk_count": 1}
    chunk_size = MAX_CHUNK
    total = video_size // chunk_size  # floor。端数は最終チャンクへ
    if total > MAX_CHUNK_COUNT:
        # 1000 チャンク以内に収まるようチャンクサイズを引き上げる
        chunk_size = -(-video_size // MAX_CHUNK_COUNT)  # ceil
        total = video_size // chunk_size
    return {"chunk_size": chunk_size, "total_chunk_count": max(1, total)}


# =====================================================================
# 動画アップロード
# =====================================================================

def _video_init(
    access_token: str,
    post_info: Dict[str, Any],
    video_size: int,
    chunk_plan: Dict[str, int],
) -> Dict[str, Any]:
    payload = {
        "post_info": post_info,
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_plan["chunk_size"],
            "total_chunk_count": chunk_plan["total_chunk_count"],
        },
    }
    resp = requests.post(
        VIDEO_INIT_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=_HTTP_TIMEOUT,
    )
    body = resp.json()
    err = body.get("error", {})
    if err and err.get("code") not in ("ok", None, ""):
        raise RuntimeError(
            f"video/init 失敗: {err.get('code')} - {err.get('message')} "
            f"(log_id={err.get('log_id')})"
        )
    data = body.get("data", {})
    if not data.get("publish_id") or not data.get("upload_url"):
        raise RuntimeError(f"video/init 応答が不正: {body}")
    return data


def _upload_chunks(upload_url: str, video_path: Path, video_size: int, chunk_plan: Dict[str, int]) -> None:
    chunk_size = chunk_plan["chunk_size"]
    total = chunk_plan["total_chunk_count"]
    with open(video_path, "rb") as f:
        for i in range(total):
            start = i * chunk_size
            if i == total - 1:
                # 最終チャンクは残り全部（端数を吸収）
                f.seek(start)
                data = f.read()
            else:
                f.seek(start)
                data = f.read(chunk_size)
            end = start + len(data) - 1
            headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(len(data)),
                "Content-Range": f"bytes {start}-{end}/{video_size}",
            }
            resp = requests.put(
                upload_url, data=data, headers=headers, timeout=_UPLOAD_TIMEOUT
            )
            if resp.status_code not in (200, 201, 206):
                raise RuntimeError(
                    f"チャンク {i+1}/{total} アップロード失敗: HTTP {resp.status_code} {resp.text[:200]}"
                )


def get_post_status(access_token: str, publish_id: str) -> Dict[str, Any]:
    _ensure_requests()
    resp = requests.post(
        STATUS_URL,
        json={"publish_id": publish_id},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=_HTTP_TIMEOUT,
    )
    body = resp.json()
    return body.get("data", {})


def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    hashtags: Optional[List[str]] = None,
    privacy_level: str = DEFAULT_PRIVACY,
    disable_comment: bool = False,
    disable_duet: bool = False,
    disable_stitch: bool = False,
    auth_channel_id: Optional[str] = None,
    access_token: Optional[str] = None,
    poll_status: bool = True,
    poll_timeout: int = 120,
) -> Dict[str, Any]:
    """TikTok に動画を Direct Post でアップロードする。

    Args:
        auth_channel_id: 内部チャンネルID — チャンネル別 OAuth トークンを使う場合に指定。
        access_token:    直接トークンを渡す場合（テスト用）。未指定なら auth_channel_id から解決。
        privacy_level:   PUBLIC_TO_EVERYONE / MUTUAL_FOLLOW_FRIENDS / SELF_ONLY。
                         未審査アプリでは creator_info に応じて SELF_ONLY に落とす。
        poll_status:     True なら公開完了/失敗までステータスをポーリングする。

    Returns:
        {publish_id, status, privacy_level, title, channel_id, ...}
    """
    _ensure_requests()

    vpath = Path(video_path)
    if not vpath.exists():
        raise FileNotFoundError(f"動画ファイルが見つかりません: {vpath}")

    if access_token is None:
        if not auth_channel_id:
            raise ValueError("auth_channel_id または access_token が必要です")
        access_token = tiktok_oauth.get_access_token_for(auth_channel_id)
        if not access_token:
            raise RuntimeError(
                f"チャンネル '{auth_channel_id}' は TikTok 未連携、またはトークン更新に失敗しました"
            )

    # 1. creator_info（必須・privacy 制約の確認）
    creator = query_creator_info(access_token)
    allowed = creator.get("privacy_level_options") or []
    if privacy_level not in VALID_PRIVACY:
        privacy_level = DEFAULT_PRIVACY
    # 許可リストに無い privacy は、許可されている中で最も非公開寄りに落とす
    if allowed and privacy_level not in allowed:
        for fallback in ("SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"):
            if fallback in allowed:
                print(
                    f"⚠️ privacy '{privacy_level}' は未許可（未審査アプリ等）。'{fallback}' に変更します。"
                )
                privacy_level = fallback
                break

    # creator が無効化している項目は尊重する
    if creator.get("comment_disabled"):
        disable_comment = True
    if creator.get("duet_disabled"):
        disable_duet = True
    if creator.get("stitch_disabled"):
        disable_stitch = True

    caption = build_caption(title, description, hashtags)

    post_info = {
        "title": caption,
        "privacy_level": privacy_level,
        "disable_comment": bool(disable_comment),
        "disable_duet": bool(disable_duet),
        "disable_stitch": bool(disable_stitch),
    }

    video_size = vpath.stat().st_size
    chunk_plan = _plan_chunks(video_size)

    print(f"📤 TikTok アップロード開始: {vpath.name} ({video_size/1024/1024:.1f}MB)")
    print(f"   privacy={privacy_level} chunks={chunk_plan['total_chunk_count']}")

    # 2. init
    init = _video_init(access_token, post_info, video_size, chunk_plan)
    publish_id = init["publish_id"]
    upload_url = init["upload_url"]

    # 3. chunked upload
    _upload_chunks(upload_url, vpath, video_size, chunk_plan)
    print(f"✅ TikTok アップロード送信完了: publish_id={publish_id}")

    result: Dict[str, Any] = {
        "publish_id": publish_id,
        "privacy_level": privacy_level,
        "title": caption,
        "channel_id": auth_channel_id,
        "status": "PROCESSING_UPLOAD",
    }

    # 4. ステータスポーリング（TikTok 側の処理完了を待つ）
    if poll_status:
        deadline = time.time() + poll_timeout
        last: Dict[str, Any] = {}
        while time.time() < deadline:
            time.sleep(5)
            try:
                last = get_post_status(access_token, publish_id)
            except Exception as e:
                print(f"⚠️ status fetch エラー（継続）: {e}")
                continue
            st = last.get("status")
            if st in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                result["status"] = st
                result["public_post_id"] = last.get("publicaly_available_post_id") or last.get(
                    "publicly_available_post_id"
                )
                print(f"🎉 TikTok 公開完了: {st}")
                break
            if st == "FAILED":
                result["status"] = "FAILED"
                result["fail_reason"] = last.get("fail_reason")
                raise RuntimeError(f"TikTok 公開失敗: {last.get('fail_reason')}")
            result["status"] = st or result["status"]
        else:
            print(f"⏳ TikTok ステータス確定前にタイムアウト（最終: {result['status']}）")

    return result


# =====================================================================
# CLI（手動テスト用）
# =====================================================================

def main() -> None:
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="TikTok 動画アップロード（手動テスト）")
    ap.add_argument("--channel", required=True, help="内部チャンネルID（OAuth トークン解決に使用）")
    ap.add_argument("--video", required=True, help="動画ファイルパス（MP4）")
    ap.add_argument("--title", default="", help="タイトル/キャプション")
    ap.add_argument("--description", default="", help="説明（要点のみ caption に転記）")
    ap.add_argument("--privacy", default=DEFAULT_PRIVACY, help="privacy_level")
    ap.add_argument("--hashtags", default="", help="カンマ区切りハッシュタグ")
    args = ap.parse_args()

    # backend/.env を読む（JWT_SECRET / TIKTOK_* のため）
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(Path(__file__).parent.parent / ".env")
    except Exception:
        pass

    tags = [t for t in args.hashtags.split(",") if t.strip()] if args.hashtags else None
    res = upload_video(
        video_path=args.video,
        title=args.title,
        description=args.description,
        hashtags=tags,
        privacy_level=args.privacy,
        auth_channel_id=args.channel,
    )
    print(_json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
