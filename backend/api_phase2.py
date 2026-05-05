"""
YouTube Factory — Phase 2 API

設定 + アナリティクス + アセット管理エンドポイント群。
- チャンネル設定 (config) の取得 / 更新
- 新規チャンネル作成 / 削除
- 画像 / BGM / 動画ファイルのアップロード / 削除
- システム設定（VOICEVOX URL, OpenAI API キー, 出力ディレクトリ等）
- パスワード変更

`api_phase1.router` と同じ prefix `/api` を共有する。
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api_phase1 import _state, require_session

router = APIRouter(prefix="/api", tags=["phase2"])


# =====================================================================
# 共通ヘルパ
# =====================================================================

PROJECT_ROOT = Path(__file__).parent.parent
ASSETS_ROOT = PROJECT_ROOT / "data" / "channels_assets"

ALLOWED_ASSET_KINDS = {
    "background",   # 背景画像
    "character",    # キャラ立ち絵
    "reference",    # 参考画像
    "bgm",          # BGM 音源
    "se",           # SE 音源
    "intro",        # OP 動画
    "outro",        # ED 動画
    "thumbnail",    # サムネ素材
}

ALLOWED_EXT = {
    "background": {".png", ".jpg", ".jpeg", ".webp"},
    "character": {".png", ".jpg", ".jpeg", ".webp"},
    "reference": {".png", ".jpg", ".jpeg", ".webp"},
    "thumbnail": {".png", ".jpg", ".jpeg", ".webp"},
    "bgm": {".mp3", ".m4a", ".wav", ".ogg"},
    "se": {".mp3", ".m4a", ".wav", ".ogg"},
    "intro": {".mp4", ".mov", ".webm"},
    "outro": {".mp4", ".mov", ".webm"},
}

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100MB

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\-]")


def _safe_filename(name: str) -> str:
    """ファイル名の危険文字を除去（パス区切りを含めて全部置換）"""
    base = Path(name).name  # ディレクトリ要素を破棄
    return _SAFE_NAME_RE.sub("_", base)[:128] or "file"


def _ensure_channel_or_404(channel_id: str):
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_id}")
    return cm, ch


def _channel_assets_dir(channel_id: str, kind: Optional[str] = None) -> Path:
    p = ASSETS_ROOT / _safe_filename(channel_id)
    if kind:
        p = p / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


# =====================================================================
# チャンネル設定 (config)
# =====================================================================

@router.get("/channels/{channel_id}/config")
async def get_channel_config(
    channel_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    """生の JSON 設定を返す（エディタ用）。"""
    _, ch = _ensure_channel_or_404(channel_id)
    return ch._raw


class UpdateConfigRequest(BaseModel):
    """部分更新。dict のままサーバ側でマージする。"""
    name: Optional[str] = None
    concept: Optional[str] = None
    style: Optional[str] = None
    youtube_channel_id: Optional[str] = None
    characters: Optional[Dict[str, Any]] = None
    thumbnail_template: Optional[Dict[str, Any]] = None
    defaults: Optional[Dict[str, Any]] = None
    content_policy: Optional[Dict[str, Any]] = None
    theme_seeds: Optional[List[Dict[str, Any]]] = None
    video_format: Optional[Dict[str, Any]] = None
    # Phase 2 で追加されたフィールド
    references: Optional[List[Dict[str, Any]]] = None
    prompts: Optional[Dict[str, str]] = None
    generation_rules: Optional[Dict[str, Any]] = None


@router.put("/channels/{channel_id}/config")
async def update_channel_config(
    channel_id: str,
    request: UpdateConfigRequest,
    _=Depends(require_session),
) -> Dict[str, Any]:
    cm, _ch = _ensure_channel_or_404(channel_id)
    updates = {k: v for k, v in request.dict().items() if v is not None}

    # ChannelManager.update_channel は一部のキーしか反映しないので、
    # その他のトップレベルキー（references / prompts / generation_rules）は
    # 直接 JSON ファイルにマージする。
    file_path = cm._data_dir / f"{channel_id}.json"
    raw = json.loads(file_path.read_text(encoding="utf-8"))

    # ChannelManager にない直書きキー
    for extra_key in ("references", "prompts", "generation_rules"):
        if extra_key in updates:
            raw[extra_key] = updates.pop(extra_key)

    # ChannelManager 経由で標準キーを更新（バリデーション + 再読み込み付き）
    if updates:
        cm.update_channel(channel_id, updates)
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    else:
        # update_channel を呼ばない場合は手動で書き戻し
        file_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cm.reload()

    # Phase 2 拡張フィールドの再書き込み（reload で消える可能性があるため最後に再保存）
    raw_after = json.loads(file_path.read_text(encoding="utf-8"))
    changed = False
    for extra_key in ("references", "prompts", "generation_rules"):
        if extra_key in raw and raw_after.get(extra_key) != raw[extra_key]:
            raw_after[extra_key] = raw[extra_key]
            changed = True
    if changed:
        file_path.write_text(
            json.dumps(raw_after, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cm.reload()

    refreshed = cm.get(channel_id)
    return {"status": "updated", "config": refreshed._raw if refreshed else raw_after}


# =====================================================================
# チャンネル作成 / 削除
# =====================================================================

class CreateChannelRequest(BaseModel):
    id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=1, max_length=120)
    concept: str = Field(default="", max_length=500)
    style: str = Field(default="yukkuri")  # yukkuri | monologue
    template: Optional[str] = None  # 既存チャンネルIDをベースにコピーする場合
    characters: Dict[str, Any] = {}
    thumbnail_template: Dict[str, Any] = {}
    defaults: Dict[str, Any] = {}
    content_policy: Dict[str, Any] = {}
    theme_seeds: List[Dict[str, Any]] = []
    # Phase 5: 新規登録ウィザードからイラストスタイルを直接設定できるように
    video_format: Optional[Dict[str, Any]] = None


def _default_channel_skeleton(req: CreateChannelRequest) -> Dict[str, Any]:
    """空白テンプレート"""
    return {
        "id": req.id,
        "name": req.name,
        "concept": req.concept,
        "style": req.style,
        "youtube_channel_id": None,
        "characters": req.characters or (
            {
                "narrator": {
                    "speaker_id": 13,
                    "text_color": [240, 240, 240],
                    "role": "ナレーター",
                }
            } if req.style == "monologue" else {}
        ),
        "thumbnail_template": req.thumbnail_template or {
            "badge_text": req.name[:8],
            "badge_color": [220, 40, 40],
            "hook_color": [255, 255, 50],
            "subtitle_color": [80, 220, 255],
        },
        "defaults": req.defaults or {
            "speed": 1.3,
            "target_duration": 720,
            "bg_type": "static",
            "use_illustrations": True,
            "hashtags": [],
            "category": "27",
        },
        "content_policy": req.content_policy or {
            "tone": "friendly",
            "age_rating": "all_ages",
        },
        "theme_seeds": req.theme_seeds,
        "video_format": {},
    }


@router.post("/channels", status_code=201)
async def create_channel(
    request: CreateChannelRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    if cm.get(request.id):
        raise HTTPException(status_code=409, detail=f"Channel already exists: {request.id}")

    # テンプレートからコピー or 空白
    if request.template:
        src = cm.get(request.template)
        if not src:
            raise HTTPException(
                status_code=400,
                detail=f"Template channel not found: {request.template}",
            )
        skel = json.loads(json.dumps(src._raw))  # deep copy
        skel["id"] = request.id
        skel["name"] = request.name
        skel["concept"] = request.concept or skel.get("concept", "")
        skel["style"] = request.style
        skel["youtube_channel_id"] = None
        # 上書き指定があれば反映
        if request.characters:
            skel["characters"] = request.characters
        if request.thumbnail_template:
            skel["thumbnail_template"].update(request.thumbnail_template)
        if request.defaults:
            skel["defaults"].update(request.defaults)
        if request.content_policy:
            skel["content_policy"].update(request.content_policy)
        if request.theme_seeds:
            skel["theme_seeds"] = request.theme_seeds
    else:
        skel = _default_channel_skeleton(request)

    # video_format をディープマージ（ウィザードが設定した illustration_style 等）
    if request.video_format:
        existing_vf = skel.get("video_format") or {}
        for section, vals in request.video_format.items():
            if isinstance(vals, dict):
                merged = dict(existing_vf.get(section) or {})
                merged.update(vals)
                existing_vf[section] = merged
            else:
                existing_vf[section] = vals
        skel["video_format"] = existing_vf

    profile = cm.add_channel(skel)
    return {"status": "created", "channel": profile.to_dict()}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    cm, _ch = _ensure_channel_or_404(channel_id)
    if not cm.remove_channel(channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    # アセットディレクトリも削除
    assets_dir = ASSETS_ROOT / _safe_filename(channel_id)
    if assets_dir.exists():
        shutil.rmtree(assets_dir, ignore_errors=True)
    return {"status": "deleted", "channel_id": channel_id}


# =====================================================================
# アセット（画像 / 音源 / 動画）アップロード
# =====================================================================

@router.get("/channels/{channel_id}/assets")
async def list_assets(channel_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    _ensure_channel_or_404(channel_id)
    base = ASSETS_ROOT / _safe_filename(channel_id)
    out: Dict[str, List[Dict[str, Any]]] = {kind: [] for kind in ALLOWED_ASSET_KINDS}
    if not base.exists():
        return {"assets": out}
    for kind in ALLOWED_ASSET_KINDS:
        kind_dir = base / kind
        if not kind_dir.exists():
            continue
        for f in sorted(kind_dir.iterdir()):
            if not f.is_file():
                continue
            out[kind].append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "url": f"/api/channels/{channel_id}/assets/{kind}/{f.name}",
            })
    return {"assets": out}


@router.post("/channels/{channel_id}/upload")
async def upload_asset(
    channel_id: str,
    kind: str = Form(...),
    file: UploadFile = File(...),
    _=Depends(require_session),
) -> Dict[str, Any]:
    _ensure_channel_or_404(channel_id)
    if kind not in ALLOWED_ASSET_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown asset kind: {kind}")

    ext = Path(file.filename or "").suffix.lower()
    allowed = ALLOWED_EXT.get(kind, set())
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Disallowed extension '{ext}' for kind '{kind}' (allowed: {sorted(allowed)})",
        )

    safe = _safe_filename(file.filename or f"upload{ext}")
    target = _channel_assets_dir(channel_id, kind) / safe

    # 容量制限を見ながら書き込み
    written = 0
    with target.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large (>100MB)")
            out.write(chunk)

    return {
        "status": "uploaded",
        "kind": kind,
        "filename": safe,
        "size_bytes": written,
        "url": f"/api/channels/{channel_id}/assets/{kind}/{safe}",
    }


@router.delete("/channels/{channel_id}/assets/{kind}/{filename}")
async def delete_asset(
    channel_id: str,
    kind: str,
    filename: str,
    _=Depends(require_session),
) -> Dict[str, Any]:
    _ensure_channel_or_404(channel_id)
    if kind not in ALLOWED_ASSET_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown asset kind: {kind}")
    safe = _safe_filename(filename)
    target = ASSETS_ROOT / _safe_filename(channel_id) / kind / safe
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    target.unlink()
    return {"status": "deleted", "filename": safe}


@router.get("/channels/{channel_id}/assets/{kind}/{filename}")
async def serve_asset(
    channel_id: str,
    kind: str,
    filename: str,
    _=Depends(require_session),
):
    """アップロードされたアセットを返す（プレビュー用）。"""
    from fastapi.responses import FileResponse

    _ensure_channel_or_404(channel_id)
    if kind not in ALLOWED_ASSET_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown asset kind: {kind}")
    safe = _safe_filename(filename)
    target = ASSETS_ROOT / _safe_filename(channel_id) / kind / safe
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(str(target), filename=safe)


# =====================================================================
# システム設定
# =====================================================================

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 12:
        return "***"
    return f"{key[:7]}...{key[-4:]}"


@router.get("/settings")
async def get_settings(_=Depends(require_session)) -> Dict[str, Any]:
    """システム設定取得（API キーはマスク）。"""
    import pipeline.video_generator as vg

    openai_key = getattr(vg, "OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    voicevox_url = getattr(vg, "VOICEVOX_URL", os.environ.get("VOICEVOX_URL", "http://localhost:50021"))

    # 出力ディレクトリ・iCloud同期は env / settings から
    output_dir = os.environ.get("YTF_OUTPUT_DIR", str(PROJECT_ROOT / "jobs"))
    icloud_sync = os.environ.get("YTF_ICLOUD_SYNC", "false").lower() == "true"

    return {
        "openai": {
            "configured": bool(openai_key),
            "preview": _mask_key(openai_key),
        },
        "voicevox_url": voicevox_url,
        "output_dir": output_dir,
        "icloud_sync": icloud_sync,
        "youtube_oauth": {
            "configured": False,
            "client_id_preview": "",
            "note": "Phase 3 で OAuth フローを実装予定",
        },
        "password_set": bool(
            os.environ.get("APP_PASSWORD_HASH") or os.environ.get("APP_PASSWORD")
        ),
    }


class UpdateSettingsRequest(BaseModel):
    openai_api_key: Optional[str] = None
    voicevox_url: Optional[str] = None
    output_dir: Optional[str] = None
    icloud_sync: Optional[bool] = None


@router.put("/settings")
async def update_settings(
    request: UpdateSettingsRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    """設定更新。OpenAI / VOICEVOX は既存の credentials/api_settings.json に保存。"""
    import pipeline.video_generator as vg

    settings_file = Path(__file__).parent / "pipeline" / "credentials" / "api_settings.json"
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    if settings_file.exists():
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
    else:
        settings = {}

    updated: List[str] = []

    if request.openai_api_key is not None:
        settings["openai_api_key"] = request.openai_api_key
        os.environ["OPENAI_API_KEY"] = request.openai_api_key
        vg.OPENAI_API_KEY = request.openai_api_key
        # ScenarioGenerator も更新
        sg = _state.get("scenario_generator")
        if sg is not None:
            sg.api_key = request.openai_api_key
        updated.append("openai_api_key")

    if request.voicevox_url is not None:
        settings["voicevox_url"] = request.voicevox_url
        vg.VOICEVOX_URL = request.voicevox_url
        updated.append("voicevox_url")

    if request.output_dir is not None:
        settings["output_dir"] = request.output_dir
        os.environ["YTF_OUTPUT_DIR"] = request.output_dir
        updated.append("output_dir")

    if request.icloud_sync is not None:
        settings["icloud_sync"] = bool(request.icloud_sync)
        os.environ["YTF_ICLOUD_SYNC"] = "true" if request.icloud_sync else "false"
        updated.append("icloud_sync")

    settings_file.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"status": "ok", "updated": updated}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=4, max_length=128)


@router.put("/auth/password")
async def change_password(
    request: ChangePasswordRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    """パスワード変更。新しい bcrypt ハッシュを返すので .env に貼り直してもらう。"""
    from api_phase1 import _verify_password, HAS_BCRYPT

    if not HAS_BCRYPT:
        raise HTTPException(status_code=500, detail="bcrypt not installed")
    if not _verify_password(request.current_password):
        raise HTTPException(status_code=401, detail="現在のパスワードが違います")

    import bcrypt  # type: ignore
    new_hash = bcrypt.hashpw(
        request.new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode()

    return {
        "status": "ok",
        "new_password_hash": new_hash,
        "instruction": (
            "backend/.env の APP_PASSWORD_HASH を新しい値に置き換えて、"
            "サーバを再起動してください。"
        ),
    }
