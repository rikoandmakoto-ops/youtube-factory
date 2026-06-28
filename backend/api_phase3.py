"""
YouTube Factory — Phase 3 API

- YouTube OAuth 2.0 (web flow)
- 動画アップロード（再開可能 + 進捗）
- YouTube Analytics（接続済み: 実データ / 未接続: モック）
- 公開ステータス管理（draft / published / scheduled）
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_phase1 import _state, require_session
from pipeline import youtube_oauth as yt_oauth
from pipeline import youtube_pair_publisher as pair_pub

# ── 任意依存（Google API） ──
try:
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.http import MediaFileUpload  # type: ignore
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False


router = APIRouter(prefix="/api", tags=["phase3"])

PROJECT_ROOT = Path(__file__).parent.parent

# 公開素材として許可するルート（PROJECT_ROOT に加え、動画の正規出力先）。
# 動画生成は ~/Desktop/動画出力用/ と iCloud に出力するため、これらを許可しないと
# job_id 経由の publish-pair で「プロジェクト外」エラーになる。
_ALLOWED_FILE_ROOTS = [
    PROJECT_ROOT,
    Path.home() / "Desktop" / "動画出力用",
    Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs",
]

# 公開ジョブ追跡
_publish_jobs: Dict[str, Dict[str, Any]] = {}


# =====================================================================
# OAuth: 接続状態 / クライアント情報
# =====================================================================

class SetClientRequest(BaseModel):
    client_id: str = Field(min_length=10)
    client_secret: str = Field(min_length=10)


@router.get("/youtube/status")
async def youtube_status(_=Depends(require_session)) -> Dict[str, Any]:
    return yt_oauth.get_status()


@router.post("/youtube/client")
async def set_youtube_client(
    request: SetClientRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    """OAuth クライアントID/シークレットを保存"""
    yt_oauth.set_oauth_client(request.client_id, request.client_secret)
    return {"status": "ok"}


class AuthUrlRequest(BaseModel):
    redirect_uri: str = Field(min_length=8)


@router.post("/youtube/auth-url")
async def youtube_auth_url(
    request: AuthUrlRequest, _=Depends(require_session)
) -> Dict[str, str]:
    try:
        return yt_oauth.build_auth_url(request.redirect_uri)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CallbackRequest(BaseModel):
    state: str
    code: str


@router.post("/youtube/callback")
async def youtube_callback(
    request: CallbackRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    try:
        return yt_oauth.exchange_code(request.state, request.code)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth exchange failed: {e}")


@router.post("/youtube/disconnect")
async def youtube_disconnect(_=Depends(require_session)) -> Dict[str, str]:
    yt_oauth.clear_credentials()
    return {"status": "disconnected"}


# =====================================================================
# OAuth: チャンネル別エンドポイント
# =====================================================================

def _require_channel(channel_id: str):
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return ch


@router.get("/channels/{channel_id}/youtube/status")
async def channel_youtube_status(
    channel_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    _require_channel(channel_id)
    return yt_oauth.get_status_for(channel_id)


@router.post("/channels/{channel_id}/youtube/client")
async def channel_set_youtube_client(
    channel_id: str,
    request: SetClientRequest,
    _=Depends(require_session),
) -> Dict[str, Any]:
    """チャンネル別 OAuth クライアントID/シークレットを保存。"""
    _require_channel(channel_id)
    yt_oauth.set_oauth_client_for(channel_id, request.client_id, request.client_secret)
    return {"status": "ok", "channel_id": channel_id}


class ChannelAuthUrlRequest(BaseModel):
    redirect_uri: str = Field(min_length=8)


@router.post("/channels/{channel_id}/youtube/auth")
async def channel_youtube_auth_url(
    channel_id: str,
    request: ChannelAuthUrlRequest,
    _=Depends(require_session),
) -> Dict[str, str]:
    """指定チャンネル用の認可URLを発行。"""
    _require_channel(channel_id)
    try:
        return yt_oauth.build_auth_url_for(channel_id, request.redirect_uri)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ChannelCallbackRequest(BaseModel):
    state: str
    code: str


@router.post("/channels/{channel_id}/youtube/callback")
async def channel_youtube_callback(
    channel_id: str,
    request: ChannelCallbackRequest,
    _=Depends(require_session),
) -> Dict[str, Any]:
    """指定チャンネル用の OAuth コールバック処理。"""
    ch = _require_channel(channel_id)
    try:
        result = yt_oauth.exchange_code_for(channel_id, request.state, request.code)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth exchange failed: {e}")

    # YouTube API から取得した本当のチャンネル名・IDをチャンネルJSONに反映。
    # 表示名(`name`)はユーザーが内部ID以外に変更していなければ更新する
    # （`scp-lab` のような placeholder のまま放置されているケースを救う）。
    yt_name = result.get("youtube_channel_name")
    yt_id = result.get("youtube_channel_id")
    updates: Dict[str, Any] = {}
    if yt_id and ch.youtube_channel_id != yt_id:
        updates["youtube_channel_id"] = yt_id
    if yt_name and ch.name in (None, "", channel_id):
        updates["name"] = yt_name
    if updates:
        cm = _state.get("channel_manager")
        if cm is not None:
            try:
                cm.update_channel(channel_id, updates)
            except Exception as e:
                # 同期に失敗しても OAuth 連携自体は成功扱いとする
                print(f"⚠️ Failed to sync YouTube metadata to channel JSON: {e}")
    return result


@router.delete("/channels/{channel_id}/youtube")
async def channel_youtube_disconnect(
    channel_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    """指定チャンネルの YouTube 連携を解除（トークン + クライアント削除）。"""
    _require_channel(channel_id)
    yt_oauth.clear_credentials_for(channel_id)
    yt_oauth.clear_oauth_client_for(channel_id)
    return {"status": "disconnected", "channel_id": channel_id}


# =====================================================================
# TikTok OAuth: チャンネル別エンドポイント（YouTube と並行）
# =====================================================================

from pipeline import tiktok_oauth as tt_oauth  # noqa: E402


class SetTiktokClientRequest(BaseModel):
    client_key: str = Field(min_length=4)
    client_secret: str = Field(min_length=4)


@router.get("/channels/{channel_id}/tiktok/status")
async def channel_tiktok_status(
    channel_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    _require_channel(channel_id)
    return tt_oauth.get_status_for(channel_id)


@router.post("/channels/{channel_id}/tiktok/client")
async def channel_set_tiktok_client(
    channel_id: str,
    request: SetTiktokClientRequest,
    _=Depends(require_session),
) -> Dict[str, Any]:
    """チャンネル別 TikTok client_key/client_secret を保存。"""
    _require_channel(channel_id)
    tt_oauth.set_oauth_client_for(channel_id, request.client_key, request.client_secret)
    return {"status": "ok", "channel_id": channel_id}


@router.post("/channels/{channel_id}/tiktok/auth")
async def channel_tiktok_auth_url(
    channel_id: str,
    request: ChannelAuthUrlRequest,
    _=Depends(require_session),
) -> Dict[str, str]:
    """指定チャンネル用の TikTok 認可URLを発行。"""
    _require_channel(channel_id)
    try:
        return tt_oauth.build_auth_url_for(channel_id, request.redirect_uri)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/channels/{channel_id}/tiktok/callback")
async def channel_tiktok_callback(
    channel_id: str,
    request: ChannelCallbackRequest,
    _=Depends(require_session),
) -> Dict[str, Any]:
    """指定チャンネル用の TikTok OAuth コールバック処理。"""
    _require_channel(channel_id)
    try:
        return tt_oauth.exchange_code_for(channel_id, request.state, request.code)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TikTok OAuth exchange failed: {e}")


@router.delete("/channels/{channel_id}/tiktok")
async def channel_tiktok_disconnect(
    channel_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    """指定チャンネルの TikTok 連携を解除（トークン + クライアント削除）。"""
    _require_channel(channel_id)
    tt_oauth.clear_credentials_for(channel_id)
    tt_oauth.clear_oauth_client_for(channel_id)
    return {"status": "disconnected", "channel_id": channel_id}


# =====================================================================
# 動画アップロード
# =====================================================================

class PublishRequest(BaseModel):
    video_path: str
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: List[str] = []
    category_id: str = "27"
    privacy: str = Field(default="private")  # private | unlisted | public
    scheduled_at: Optional[str] = None  # ISO 8601 — 指定時は private + publishAt
    thumbnail_path: Optional[str] = None
    is_short: bool = False
    made_for_kids: bool = False
    youtube_channel_id: Optional[str] = None  # ブランドアカウント指定 (UC...)
    auth_channel_id: Optional[str] = None  # 内部チャンネルID (per-channel OAuth)


def _validate_file(path_str: str, label: str = "file") -> Path:
    p = Path(path_str).expanduser()
    # 許可ルート配下に限定（PROJECT_ROOT + 動画の正規出力先）
    try:
        p_resolved = p.resolve()
        allowed = False
        for root in _ALLOWED_FILE_ROOTS:
            try:
                if str(p_resolved).startswith(str(root.resolve())):
                    allowed = True
                    break
            except Exception:
                continue
        if not allowed:
            raise HTTPException(status_code=400, detail=f"{label} がプロジェクト外です")
    except HTTPException:
        raise
    except Exception:
        pass
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"{label} not found: {path_str}")
    return p


def _normalize_publish_at(dt_str: str) -> str:
    """ISO8601 を YouTube API 用 UTC RFC3339 に正規化"""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid datetime: {dt_str}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_publish(job_id: str, req: PublishRequest):
    job = _publish_jobs[job_id]
    try:
        if not HAS_GOOGLE:
            raise RuntimeError(
                "google-api-python-client がインストールされていません"
            )
        creds = (
            yt_oauth.get_credentials_for(req.auth_channel_id)
            if req.auth_channel_id
            else yt_oauth.get_credentials()
        )
        if not creds:
            raise RuntimeError("YouTube が未連携です。チャンネル設定から接続してください")

        video = _validate_file(req.video_path, "video")
        thumb = _validate_file(req.thumbnail_path, "thumbnail") if req.thumbnail_path else None

        tags = list(req.tags or [])
        if req.is_short and "#Shorts" not in tags:
            tags.insert(0, "#Shorts")

        privacy = req.privacy
        if req.scheduled_at:
            privacy = "private"

        body: Dict[str, Any] = {
            "snippet": {
                "title": req.title[:100],
                "description": req.description[:5000],
                "tags": tags,
                "categoryId": req.category_id,
                "defaultLanguage": "ja",
                "defaultAudioLanguage": "ja",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": req.made_for_kids,
            },
        }
        if req.youtube_channel_id:
            body["snippet"]["channelId"] = req.youtube_channel_id
        if req.scheduled_at:
            body["status"]["publishAt"] = _normalize_publish_at(req.scheduled_at)

        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        media = MediaFileUpload(
            str(video),
            mimetype="video/mp4",
            resumable=True,
            chunksize=8 * 1024 * 1024,
        )
        request_call = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )

        job["status"] = "uploading"
        response = None
        while response is None:
            status, response = request_call.next_chunk()
            if status:
                job["progress"] = round(status.progress() * 100, 1)
        video_id = response["id"]

        # サムネイル
        if thumb:
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumb), mimetype="image/png"),
                ).execute()
                job["thumbnail_set"] = True
            except Exception as e:
                job["thumbnail_error"] = str(e)

        job["status"] = "completed"
        job["progress"] = 100.0
        job["video_id"] = video_id
        job["url"] = f"https://youtube.com/watch?v={video_id}"
        job["completed_at"] = datetime.now().isoformat()
    except HTTPException as e:
        job["status"] = "failed"
        job["error"] = e.detail
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


@router.post("/youtube/publish")
async def youtube_publish(
    request: PublishRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    connected = (
        yt_oauth.is_connected_for(request.auth_channel_id)
        if request.auth_channel_id
        else yt_oauth.is_connected()
    )
    if not connected:
        raise HTTPException(status_code=400, detail="YouTube が未連携です")

    job_id = str(uuid.uuid4())[:8]
    _publish_jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 0.0,
        "title": request.title,
        "started_at": datetime.now().isoformat(),
    }
    threading.Thread(
        target=_run_publish, args=(job_id, request), daemon=True
    ).start()
    return {"job_id": job_id, "status": "queued"}


@router.get("/youtube/publish/{job_id}")
async def youtube_publish_status(
    job_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    if job_id not in _publish_jobs:
        raise HTTPException(status_code=404, detail="Publish job not found")
    return _publish_jobs[job_id]


@router.get("/youtube/publish")
async def youtube_publish_list(_=Depends(require_session)) -> Dict[str, Any]:
    """最近のアップロードジョブ一覧（最新20件）"""
    jobs = sorted(
        _publish_jobs.values(),
        key=lambda j: j.get("started_at", ""),
        reverse=True,
    )[:20]
    return {"jobs": jobs}


# =====================================================================
# ペア公開（メイン → 時差付きショート）
# =====================================================================

class PublishPairRequest(BaseModel):
    job_id: Optional[str] = None  # 既存の生成ジョブから自動解決する場合
    main_video_path: Optional[str] = None
    short_video_path: Optional[str] = None
    main_thumbnail_path: Optional[str] = None
    short_thumbnail_path: Optional[str] = None
    main_title: Optional[str] = None
    short_title: Optional[str] = None
    main_description: Optional[str] = None
    short_description: Optional[str] = None
    tags: List[str] = []
    category_id: str = "27"
    privacy: str = Field(default="public")  # private | unlisted | public
    short_delay_minutes: int = Field(default=10, ge=1, le=24 * 60)
    short_description_template: Optional[str] = None
    youtube_channel_id: Optional[str] = None
    channel_id: Optional[str] = None  # 内部チャンネルID（publish_settings 解決用）


def _resolve_pair_inputs(req: PublishPairRequest) -> Dict[str, Any]:
    """job_id 指定時はキューから result を引いて素材パス・既定値を埋める。"""
    queue = _state.get("job_queue")
    cm = _state.get("channel_manager")

    main_video = req.main_video_path
    short_video = req.short_video_path
    main_thumb = req.main_thumbnail_path
    short_thumb = req.short_thumbnail_path
    main_title = req.main_title
    short_title = req.short_title
    main_desc = req.main_description
    short_desc = req.short_description
    channel_id = req.channel_id

    job = None
    if req.job_id and queue:
        try:
            job = queue.get_status(req.job_id)
        except Exception:
            job = None

    if job:
        channel_id = channel_id or job.get("channel_id")
        result = job.get("result") or {}
        paths = pair_pub._resolve_paths_from_result(result)
        main_video = main_video or paths["main_video"]
        short_video = short_video or paths["short_video"]
        main_thumb = main_thumb or paths["main_thumb"]
        short_thumb = short_thumb or paths["short_thumb"]
        if not main_title or not main_desc:
            d = pair_pub._read_desc(paths["main_desc_file"])
            main_title = main_title or d["title"] or job.get("title")
            main_desc = main_desc if main_desc is not None else d["body"]
        if not short_title or not short_desc:
            d = pair_pub._read_desc(paths["short_desc_file"])
            short_title = short_title or d["title"] or (job.get("title", "") + "【ショート】")
            short_desc = short_desc if short_desc is not None else d["body"]

    # チャンネル設定からデフォルト値を補完
    ch_publish = {}
    ch_yt_id = req.youtube_channel_id
    ch_tags: List[str] = []
    ch_category = "27"
    if cm and channel_id:
        ch = cm.get(channel_id)
        if ch:
            ch_publish = ch.get_publish_settings()
            ch_yt_id = ch_yt_id or ch.youtube_channel_id
            ch_tags = ch.get_hashtags() or []
            ch_category = ch.get_category() or "27"

    template = req.short_description_template or ch_publish.get("short_description_template")
    delay = req.short_delay_minutes
    if delay == 10 and ch_publish.get("short_delay_minutes"):
        delay = int(ch_publish["short_delay_minutes"])
    privacy = req.privacy or ch_publish.get("default_privacy") or "public"

    tags = req.tags or [t.lstrip("#") for t in ch_tags] or []
    category_id = req.category_id or ch_category

    if not main_video or not short_video:
        raise HTTPException(
            status_code=400,
            detail="メイン/ショート動画パスを解決できませんでした (job_id か明示パスを指定)",
        )

    # ファイル存在チェック
    _validate_file(main_video, "main_video")
    _validate_file(short_video, "short_video")
    if main_thumb:
        try:
            _validate_file(main_thumb, "main_thumbnail")
        except HTTPException:
            main_thumb = None
    if short_thumb:
        try:
            _validate_file(short_thumb, "short_thumbnail")
        except HTTPException:
            short_thumb = None

    return {
        "main_video": main_video,
        "short_video": short_video,
        "main_thumb": main_thumb,
        "short_thumb": short_thumb,
        "main_title": main_title or "メイン動画",
        "short_title": short_title or (main_title or "ショート") + "【ショート】",
        "main_description": main_desc or "",
        "short_description": short_desc or "",
        "tags": tags,
        "category_id": category_id,
        "privacy": privacy,
        "short_delay_minutes": delay,
        "short_description_template": template,
        "youtube_channel_id": ch_yt_id,
        "channel_id": channel_id,
        "auth_channel_id": channel_id,  # per-channel OAuth に使う内部チャンネルID
        "source_job_id": req.job_id,
    }


def _record_pair_status_to_db(
    source_job_id: Optional[str],
    channel_id: Optional[str],
    main: Dict[str, Any],
    short: Dict[str, Any],
) -> None:
    """video_status DB に pair 公開結果を残す（PublishDialog 同等の永続化）。"""
    if not source_job_id:
        return
    conn = _publish_db()
    try:
        # メイン
        conn.execute(
            "INSERT OR REPLACE INTO video_status "
            "(job_id, channel_id, status, video_id, url, scheduled_at, published_at, updated_at) "
            "VALUES (?, ?, 'published', ?, ?, NULL, ?, ?)",
            (
                source_job_id,
                channel_id or "",
                main.get("video_id"),
                main.get("url"),
                datetime.now().isoformat(),
                int(time.time()),
            ),
        )
        # ショート用に別キーで記録（"<job_id>:short"）
        conn.execute(
            "INSERT OR REPLACE INTO video_status "
            "(job_id, channel_id, status, video_id, url, scheduled_at, published_at, updated_at) "
            "VALUES (?, ?, 'scheduled', ?, ?, ?, NULL, ?)",
            (
                f"{source_job_id}:short",
                channel_id or "",
                short.get("video_id"),
                short.get("url"),
                short.get("publish_at"),
                int(time.time()),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _run_pair_publish_async(job_id: str, params: Dict[str, Any]) -> None:
    """バックグラウンドワーカー: pair_pub.run_pair_publish を実行 → 通知 → DB 永続化。"""

    def _on_complete(job: Dict[str, Any]) -> None:
        main = job.get("main") or {}
        short = job.get("short") or {}
        try:
            _record_pair_status_to_db(
                params.get("source_job_id"),
                params.get("channel_id"),
                main, short,
            )
        except Exception:
            pass
        # 通知
        try:
            from api_phase4 import notify_event  # 遅延 import で循環回避
            msg = (
                f"📤 ペア公開完了\n"
                f"メイン: {main.get('url', '?')}\n"
                f"ショート: {short.get('url', '?')} (公開予定: {short.get('publish_at', '?')})"
            )
            notify_event("upload_done", msg)
        except Exception:
            pass

    pair_pub.run_pair_publish(
        job_id=job_id,
        main_video_path=params["main_video"],
        short_video_path=params["short_video"],
        main_title=params["main_title"],
        short_title=params["short_title"],
        main_description=params["main_description"],
        short_description=params["short_description"],
        tags=params["tags"],
        category_id=params["category_id"],
        privacy=params["privacy"],
        short_delay_minutes=params["short_delay_minutes"],
        short_description_template=params["short_description_template"],
        youtube_channel_id=params["youtube_channel_id"],
        main_thumbnail_path=params["main_thumb"],
        short_thumbnail_path=params["short_thumb"],
        on_complete=_on_complete,
        auth_channel_id=params.get("auth_channel_id"),
    )


@router.post("/youtube/publish-pair")
async def youtube_publish_pair(
    request: PublishPairRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    """メイン+ショートをペア公開（メイン即時 → 指定分後にショート）。"""
    params = _resolve_pair_inputs(request)
    auth_ch = params.get("auth_channel_id")
    connected = (
        yt_oauth.is_connected_for(auth_ch) if auth_ch else yt_oauth.is_connected()
    )
    if not connected:
        raise HTTPException(status_code=400, detail="YouTube が未連携です")
    job_id = pair_pub.create_pair_job()
    threading.Thread(
        target=_run_pair_publish_async, args=(job_id, params), daemon=True
    ).start()
    return {
        "job_id": job_id,
        "status": "queued",
        "short_delay_minutes": params["short_delay_minutes"],
    }


@router.get("/youtube/publish-pair/{job_id}")
async def youtube_publish_pair_status(
    job_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    job = pair_pub.get_pair_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Pair publish job not found")
    return job


@router.get("/youtube/publish-pair")
async def youtube_publish_pair_list(_=Depends(require_session)) -> Dict[str, Any]:
    return {"jobs": pair_pub.list_pair_jobs(20)}


# =====================================================================
# Analytics
# =====================================================================

def _mock_analytics(channel_id: str) -> Dict[str, Any]:
    """未連携時のモックデータ"""
    import hashlib
    import random

    # チャンネル ID をシードにして安定値を返す
    seed = int(hashlib.sha256(channel_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    days = []
    base = rng.randint(50, 300)
    for i in range(28):
        date = (datetime.now() - timedelta(days=27 - i)).date().isoformat()
        # ゆるやかに増加するトレンド + ランダムノイズ
        views = max(0, int(base + i * rng.uniform(2, 8) + rng.randint(-30, 30)))
        days.append({"date": date, "views": views})

    total_views = sum(d["views"] for d in days)
    return {
        "connected": False,
        "source": "mock",
        "channel_id": channel_id,
        "metrics": {
            "total_views": total_views * 2,
            "subscribers": rng.randint(15, 300),
            "video_count": rng.randint(3, 20),
            "avg_views_per_video": int(total_views / 14),
        },
        "views_by_day": days,
        "top_videos": [
            {"video_id": f"mock{i}", "title": f"モック動画 {i+1}", "views": rng.randint(100, 2000)}
            for i in range(5)
        ],
    }


def _top_videos_via_data_api(
    yt, youtube_channel_id: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """YouTube Data API v3 で全アップロード動画から再生数上位を返す。

    YouTube Analytics API が無効な GCP プロジェクトでも動作する。
    uploads プレイリストを最大250件辿り、viewCount で降順ソートする。
    """
    try:
        ch = (
            yt.channels()
            .list(part="contentDetails", id=youtube_channel_id)
            .execute()
        )
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

        video_ids: List[str] = []
        next_token: Optional[str] = None
        # 最大 5 ページ × 50 = 250 件まで
        for _ in range(5):
            pl = (
                yt.playlistItems()
                .list(
                    part="contentDetails",
                    playlistId=uploads,
                    maxResults=50,
                    pageToken=next_token,
                )
                .execute()
            )
            for it in pl.get("items", []):
                vid = it.get("contentDetails", {}).get("videoId")
                if vid:
                    video_ids.append(vid)
            next_token = pl.get("nextPageToken")
            if not next_token:
                break

        videos: List[Dict[str, Any]] = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i : i + 50]
            resp = (
                yt.videos()
                .list(part="snippet,statistics", id=",".join(batch))
                .execute()
            )
            for v in resp.get("items", []):
                videos.append(
                    {
                        "video_id": v["id"],
                        "title": v.get("snippet", {}).get("title", v["id"]),
                        "views": int(v.get("statistics", {}).get("viewCount", 0)),
                    }
                )

        videos.sort(key=lambda x: x["views"], reverse=True)
        return videos[:limit]
    except Exception:
        return []


def _real_analytics(channel_id: str, youtube_channel_id: str) -> Optional[Dict[str, Any]]:
    """YouTube Analytics API v2 で実データ取得。失敗時 None。

    認証は per-channel トークン（channel_id 指定）を優先し、未連携時はレガシーへフォールバック。
    """
    if not HAS_GOOGLE:
        return None
    creds = yt_oauth.get_credentials_for(channel_id) or yt_oauth.get_credentials()
    if not creds:
        return None

    try:
        # チャンネル統計（snippet, statistics）
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        ch_resp = (
            yt.channels()
            .list(part="snippet,statistics", id=youtube_channel_id)
            .execute()
        )
        items = ch_resp.get("items", [])
        if not items:
            return None
        stats = items[0].get("statistics", {})
        total_views = int(stats.get("viewCount", 0))
        subscribers = int(stats.get("subscriberCount", 0))
        video_count = int(stats.get("videoCount", 0))

        # 過去28日の再生数推移（YouTube Analytics API）
        analytics = build(
            "youtubeAnalytics", "v2", credentials=creds, cache_discovery=False
        )
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=27)
        try:
            ar = analytics.reports().query(
                ids=f"channel=={youtube_channel_id}",
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                metrics="views",
                dimensions="day",
                sort="day",
            ).execute()
            rows = ar.get("rows", [])
            views_by_day = [{"date": r[0], "views": int(r[1])} for r in rows]
        except Exception:
            views_by_day = []

        # 人気動画（上位5件）— Analytics API → 失敗時 Data API フォールバック
        top_videos: List[Dict[str, Any]] = []
        try:
            top = analytics.reports().query(
                ids=f"channel=={youtube_channel_id}",
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                metrics="views",
                dimensions="video",
                sort="-views",
                maxResults=5,
            ).execute()
            top_rows = top.get("rows", [])
            if top_rows:
                ids = [r[0] for r in top_rows]
                resp = (
                    yt.videos()
                    .list(part="snippet", id=",".join(ids))
                    .execute()
                )
                title_map = {
                    item["id"]: item["snippet"]["title"]
                    for item in resp.get("items", [])
                }
                for vid, views in top_rows:
                    top_videos.append(
                        {
                            "video_id": vid,
                            "title": title_map.get(vid, vid),
                            "views": int(views),
                        }
                    )
        except Exception:
            top_videos = []

        if not top_videos:
            top_videos = _top_videos_via_data_api(yt, youtube_channel_id, limit=5)

        return {
            "connected": True,
            "source": "youtube_analytics",
            "channel_id": channel_id,
            "youtube_channel_id": youtube_channel_id,
            "metrics": {
                "total_views": total_views,
                "subscribers": subscribers,
                "video_count": video_count,
                "avg_views_per_video": total_views // max(1, video_count),
            },
            "views_by_day": views_by_day,
            "top_videos": top_videos,
        }
    except Exception as e:
        return {"connected": True, "source": "error", "error": str(e)}


@router.get("/channels/{channel_id}/analytics")
async def channel_analytics(
    channel_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")

    yt_id = ch.youtube_channel_id
    has_auth = yt_oauth.is_connected_for(channel_id) or yt_oauth.is_connected()
    if not yt_id and has_auth:
        # チャンネルプロファイル未設定でも OAuth 連携済みなら、
        # トークンに紐付いた YouTube チャンネル ID を使う
        try:
            yt_id = yt_oauth.get_status_for(channel_id).get("youtube_channel_id")
        except Exception:
            yt_id = None
    if yt_id and has_auth:
        real = _real_analytics(channel_id, yt_id)
        if real and real.get("source") != "error":
            return real
        if real and real.get("source") == "error":
            # API エラー時はエラーを露出しつつモックも返す
            mock = _mock_analytics(channel_id)
            mock["error"] = real.get("error")
            return mock

    mock = _mock_analytics(channel_id)
    mock["youtube_channel_id"] = yt_id
    return mock


# =====================================================================
# 公開ステータス管理（簡易: SQLite）
# =====================================================================

PUBLISH_DB = PROJECT_ROOT / "data" / "video_publish.db"


def _publish_db():
    import sqlite3
    PUBLISH_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(PUBLISH_DB))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_status (
            job_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            video_id TEXT,
            url TEXT,
            scheduled_at TEXT,
            published_at TEXT,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


class SetVideoStatusRequest(BaseModel):
    status: str  # draft | published | scheduled
    video_id: Optional[str] = None
    url: Optional[str] = None
    scheduled_at: Optional[str] = None


@router.put("/videos/{job_id}/status")
async def set_video_status(
    job_id: str,
    request: SetVideoStatusRequest,
    _=Depends(require_session),
) -> Dict[str, Any]:
    queue = _state.get("job_queue")
    channel_id = ""
    if queue:
        try:
            j = queue.get_status(job_id)
            channel_id = j.get("channel_id", "") if j else ""
        except Exception:
            pass

    conn = _publish_db()
    try:
        existing = conn.execute(
            "SELECT channel_id FROM video_status WHERE job_id = ?", (job_id,)
        ).fetchone()
        if existing and not channel_id:
            channel_id = existing[0]
        published_at = (
            datetime.now().isoformat() if request.status == "published" else None
        )
        conn.execute(
            "INSERT OR REPLACE INTO video_status "
            "(job_id, channel_id, status, video_id, url, scheduled_at, published_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                channel_id,
                request.status,
                request.video_id,
                request.url,
                request.scheduled_at,
                published_at,
                int(time.time()),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "job_id": job_id, "video_status": request.status}


@router.get("/videos/{job_id}/status")
async def get_video_status(
    job_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    conn = _publish_db()
    try:
        row = conn.execute(
            "SELECT status, video_id, url, scheduled_at, published_at FROM video_status WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"status": "draft", "job_id": job_id}
    return {
        "job_id": job_id,
        "status": row[0],
        "video_id": row[1],
        "url": row[2],
        "scheduled_at": row[3],
        "published_at": row[4],
    }


def get_video_statuses_for_channel(channel_id: str) -> Dict[str, Dict[str, Any]]:
    """チャンネル詳細用：全ジョブの公開ステータスを map で返す"""
    conn = _publish_db()
    try:
        rows = conn.execute(
            "SELECT job_id, status, video_id, url, scheduled_at, published_at "
            "FROM video_status WHERE channel_id = ?",
            (channel_id,),
        ).fetchall()
    finally:
        conn.close()
    return {
        r[0]: {
            "status": r[1],
            "video_id": r[2],
            "url": r[3],
            "scheduled_at": r[4],
            "published_at": r[5],
        }
        for r in rows
    }
