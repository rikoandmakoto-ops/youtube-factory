"""
YouTube Pair Publisher — メイン+ショートをペアで時差公開

フロー:
  1. メイン動画を即時公開（または publish 即時）
  2. メイン動画のURL（https://youtube.com/watch?v=...）を取得
  3. ショートの説明文にチャンネル設定の short_description_template を使ってメインURLを差し込む
  4. ショート動画を private + publishAt = now + short_delay_minutes でスケジュール公開
     → YouTube ネイティブの予約公開機能を使うのでサーバが落ちても予定通り公開される

呼び出し元:
  - api_phase3 の /api/youtube/publish-pair エンドポイント
  - api_phase4 の _run_schedule から auto_publish 連携時
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.http import MediaFileUpload  # type: ignore
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

from . import youtube_oauth as yt_oauth


PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_TEMPLATE = "🎬 フル解説はこちら！\n{main_url}\n\n{original_description}"

# In-memory pair-publish jobs (api_phase3 から共有)
_pair_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


# =====================================================================
# ヘルパ: ジョブ result から動画 / サムネ / 説明 のパスを推論
# =====================================================================

def _coerce_path(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("video_path", "path", "output", "main_video_path", "full_video_path"):
            v = value.get(key)
            if isinstance(v, str):
                return v
    return None


def _resolve_paths_from_result(result: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """generate_all() の戻り値からメイン/ショートの素材パスを抽出する。"""
    if not isinstance(result, dict):
        result = {}

    main_video = (
        _coerce_path(result.get("full"))
        or _coerce_path(result.get("main"))
        or result.get("full_video_path")
        or result.get("main_video_path")
    )
    short_video = (
        _coerce_path(result.get("short"))
        or result.get("short_video_path")
    )
    main_thumb = result.get("thumbnail") or result.get("thumbnail_path")
    short_thumb = result.get("short_thumbnail") or result.get("short_thumbnail_path")
    main_desc = result.get("main_description")
    short_desc = result.get("short_description")

    out_dir = result.get("output_dir")
    # フォールバック: 出力ディレクトリから直接スキャン
    if out_dir and (not main_desc or not short_desc):
        od = Path(out_dir)
        if od.exists():
            for f in od.iterdir():
                name = f.name
                if not main_desc and name.endswith("_メイン_説明文.txt"):
                    main_desc = str(f)
                if not short_desc and name.endswith("_ショート_説明文.txt"):
                    short_desc = str(f)

    return {
        "main_video": str(main_video) if main_video else None,
        "short_video": str(short_video) if short_video else None,
        "main_thumb": str(main_thumb) if main_thumb else None,
        "short_thumb": str(short_thumb) if short_thumb else None,
        "main_desc_file": str(main_desc) if main_desc else None,
        "short_desc_file": str(short_desc) if short_desc else None,
    }


def _read_desc(path: Optional[str]) -> Dict[str, str]:
    """説明文ファイルから 'タイトル: ...' 行と本文を分離して返す。"""
    if not path:
        return {"title": "", "body": ""}
    p = Path(path)
    if not p.exists():
        return {"title": "", "body": ""}
    text = p.read_text(encoding="utf-8")
    title = ""
    body_lines: List[str] = []
    for line in text.split("\n"):
        if not title and (line.startswith("タイトル:") or line.startswith("タイトル：")):
            title = line.split(":", 1)[-1].split("：", 1)[-1].strip()
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return {"title": title, "body": body}


def _safe_format_template(template: str, mapping: Dict[str, str]) -> str:
    """{key} スタイルのテンプレ展開。未知のキーは原文のまま残す。"""
    out = template
    for k, v in mapping.items():
        out = out.replace("{" + k + "}", v)
    return out


def build_short_description(
    main_url: str,
    original_short_desc: str,
    main_title: str,
    template: Optional[str],
) -> str:
    """ショート説明文に メイン動画 URL を差し込む。"""
    tmpl = template or DEFAULT_TEMPLATE
    return _safe_format_template(
        tmpl,
        {
            "main_url": main_url,
            "main_title": main_title,
            "original_description": original_short_desc,
        },
    ).strip()


def _now_jst() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def _format_publish_at(dt: datetime) -> str:
    """YouTube API 用 RFC3339 (UTC, Z 付き)。"""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# =====================================================================
# 単発アップロード（pair 内部用）
# =====================================================================

def _upload_one(
    youtube,
    video_path: str,
    title: str,
    description: str,
    tags: List[str],
    category_id: str,
    privacy: str,
    is_short: bool,
    youtube_channel_id: Optional[str],
    publish_at: Optional[str],
    thumbnail_path: Optional[str],
    progress_cb=None,
) -> Dict[str, Any]:
    if not HAS_GOOGLE:
        raise RuntimeError("google-api-python-client が未インストールです")

    final_tags = list(tags or [])
    if is_short and "#Shorts" not in final_tags:
        final_tags.insert(0, "#Shorts")

    final_privacy = "private" if publish_at else privacy

    body: Dict[str, Any] = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": final_tags,
            "categoryId": category_id or "27",
            "defaultLanguage": "ja",
            "defaultAudioLanguage": "ja",
        },
        "status": {
            "privacyStatus": final_privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    if youtube_channel_id:
        body["snippet"]["channelId"] = youtube_channel_id
    if publish_at:
        body["status"]["publishAt"] = publish_at

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=8 * 1024 * 1024,
    )
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status and progress_cb:
            try:
                progress_cb(round(status.progress() * 100, 1))
            except Exception:
                pass
    video_id = response["id"]

    thumb_error = None
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
            ).execute()
        except Exception as e:
            thumb_error = str(e)

    return {
        "video_id": video_id,
        "url": f"https://youtube.com/watch?v={video_id}",
        "privacy": final_privacy,
        "publish_at": publish_at,
        "thumbnail_error": thumb_error,
    }


# =====================================================================
# ペア公開: メイン → ショート（時差付き）
# =====================================================================

def create_pair_job() -> str:
    job_id = "pp_" + uuid.uuid4().hex[:10]
    with _jobs_lock:
        _pair_jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "step": "queued",
            "progress": 0.0,
            "main": None,
            "short": None,
            "started_at": datetime.now().isoformat(),
            "error": None,
        }
    return job_id


def get_pair_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        return dict(_pair_jobs[job_id]) if job_id in _pair_jobs else None


def list_pair_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    with _jobs_lock:
        items = list(_pair_jobs.values())
    items.sort(key=lambda j: j.get("started_at", ""), reverse=True)
    return [dict(i) for i in items[:limit]]


def _update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        j = _pair_jobs.get(job_id)
        if j:
            j.update(fields)


def run_pair_publish(
    *,
    job_id: str,
    main_video_path: str,
    short_video_path: str,
    main_title: str,
    short_title: str,
    main_description: str,
    short_description: str,
    tags: List[str],
    category_id: str = "27",
    privacy: str = "public",
    short_delay_minutes: int = 10,
    short_description_template: Optional[str] = None,
    youtube_channel_id: Optional[str] = None,
    main_thumbnail_path: Optional[str] = None,
    short_thumbnail_path: Optional[str] = None,
    on_complete=None,
    auth_channel_id: Optional[str] = None,
    main_publish_at: Optional[str] = None,
) -> None:
    """同期実行（ワーカー側で呼ぶ）: メインを公開してショートを time-shift スケジュール。

    Args:
        auth_channel_id: 認証に使う内部チャンネルID（per-channel OAuth）。
            未指定時はレガシー（DEFAULT_CHANNEL_ID）にフォールバック。
        youtube_channel_id: YouTube 側のブランドチャンネルID（UC...）。snippet.channelId に設定。
        main_publish_at: メイン動画の予約公開日時 (RFC3339 UTC, 例 "2025-03-15T14:30:00Z")。
            指定時はメインも private + publishAt でスケジュールされ、ショートは
            (main_publish_at + short_delay_minutes) で時差公開される。未指定時は従来通りメイン即時。
    """
    try:
        creds = (
            yt_oauth.get_credentials_for(auth_channel_id)
            if auth_channel_id
            else yt_oauth.get_credentials()
        )
        if not creds:
            raise RuntimeError("YouTube が未連携です。チャンネル設定から接続してください")
        if not HAS_GOOGLE:
            raise RuntimeError("google-api-python-client が未インストールです")

        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        # ── 1. メイン公開 ──
        _update_job(job_id, status="uploading_main", step="メイン動画アップロード中", progress=5.0)

        def main_progress(pct: float):
            _update_job(job_id, progress=5.0 + pct * 0.40)  # 5..45

        main_result = _upload_one(
            youtube,
            video_path=main_video_path,
            title=main_title,
            description=main_description,
            tags=tags,
            category_id=category_id,
            privacy=privacy,
            is_short=False,
            youtube_channel_id=youtube_channel_id,
            publish_at=main_publish_at,  # 指定時はメインもスケジュール公開
            thumbnail_path=main_thumbnail_path,
            progress_cb=main_progress,
        )
        _update_job(
            job_id,
            main=main_result,
            status="main_uploaded",
            step="メイン公開完了 — ショート準備中",
            progress=50.0,
        )

        # ── 2. ショート説明文を組み立て ──
        final_short_desc = build_short_description(
            main_url=main_result["url"],
            original_short_desc=short_description,
            main_title=main_title,
            template=short_description_template,
        )

        # ── 3. ショート予約公開 ──
        # メインがスケジュール公開ならショートは「メイン公開時刻 + delay」、
        # 未指定なら従来通り「現時点 + delay」。
        if main_publish_at:
            try:
                base_dt = datetime.strptime(
                    main_publish_at, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                base_dt = _now_jst()
        else:
            base_dt = _now_jst()
        publish_at_dt = base_dt + timedelta(minutes=max(1, short_delay_minutes))
        publish_at_str = _format_publish_at(publish_at_dt)
        _update_job(
            job_id,
            status="uploading_short",
            step=f"ショート動画アップロード中 (公開予定: {publish_at_dt.isoformat()})",
            progress=55.0,
        )

        def short_progress(pct: float):
            _update_job(job_id, progress=55.0 + pct * 0.40)  # 55..95

        short_result = _upload_one(
            youtube,
            video_path=short_video_path,
            title=short_title,
            description=final_short_desc,
            tags=tags,
            category_id=category_id,
            privacy=privacy,
            is_short=True,
            youtube_channel_id=youtube_channel_id,
            publish_at=publish_at_str,
            thumbnail_path=short_thumbnail_path,
            progress_cb=short_progress,
        )
        _update_job(
            job_id,
            short=short_result,
            status="completed",
            step="完了",
            progress=100.0,
            completed_at=datetime.now().isoformat(),
        )
        if on_complete:
            try:
                on_complete(get_pair_job(job_id) or {})
            except Exception:
                pass

    except Exception as e:
        _update_job(
            job_id,
            status="failed",
            step="失敗",
            error=str(e),
            completed_at=datetime.now().isoformat(),
        )
