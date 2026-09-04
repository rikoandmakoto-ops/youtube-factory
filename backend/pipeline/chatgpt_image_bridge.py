"""ChatGPT（ブラウザ）経由で画像を作るためのファイルキュー。

OpenAI Images API を直接叩くのをやめ、生成依頼を `data/image_requests/` に積む。
キューを処理するのは **Claude in Chrome を持つ Claude セッション**で、ChatGPT の
「チャンネルごとに固定した1スレッド」にプロンプトを送り、出てきた画像を回収して
`deliver()` でキューに戻す（手順は `docs/CHATGPT_IMAGE_BRIDGE.md`）。

こうする理由:

  * **ユーザーが横から直せる。** API 直叩きだと会話が毎回消えるので、
    「もっと暗く」「顔を大きく」といった指示の積み上げが効かない。
    同じスレッドを人間が開いて修正すれば、次の生成からその文脈が乗る。
  * **投稿パイプラインが OPENAI_API_KEY / 429 に引きずられない。**
    2026-09-03 18:49 の 429 で投稿が止まった件の再発防止。

パイプラインは既定で**待たない**（`wait_seconds=0`）。依頼を積んで即 None を返し、
呼び出し側は従来どおり Pillow などのフォールバックに落ちる。後からワーカーが
画像を納品すると `cache/` に入り、**次回の同一プロンプトで即ヒットする**。
同期的に画像が要る用途（手動スクリプト等）は `wait_seconds` を明示する。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DIR = Path(os.environ.get("IMAGE_BRIDGE_DIR") or (ROOT / "data" / "image_requests"))

PENDING_DIR = BRIDGE_DIR / "pending"
DELIVERED_DIR = BRIDGE_DIR / "delivered"
FAILED_DIR = BRIDGE_DIR / "failed"
IMAGES_DIR = BRIDGE_DIR / "images"
CACHE_DIR = BRIDGE_DIR / "cache"
THREADS_PATH = BRIDGE_DIR / "threads.json"

_DIRS = (PENDING_DIR, DELIVERED_DIR, FAILED_DIR, IMAGES_DIR, CACHE_DIR)

# 依頼を積んでから何秒待つか。既定 0 = 待たない（autopilot を止めないため）。
DEFAULT_WAIT_SECONDS = float(os.environ.get("IMAGE_BRIDGE_WAIT_SECONDS", "0") or 0)
_POLL_INTERVAL = 3.0

# pending が溜まりっぱなしになるのを防ぐ。これより古い依頼は gc() で failed へ。
PENDING_TTL_DAYS = float(os.environ.get("IMAGE_BRIDGE_TTL_DAYS", "7") or 7)


def is_enabled() -> bool:
    """ブリッジを使うか。`IMAGE_BRIDGE=0` で無効化できる（緊急時の退避口）。"""
    return (os.environ.get("IMAGE_BRIDGE", "1") or "1").strip().lower() not in ("0", "false", "no")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_dirs() -> None:
    for d in _DIRS:
        d.mkdir(parents=True, exist_ok=True)


def prompt_hash(prompt: str, size: str) -> str:
    return hashlib.sha256(f"{size}\n{prompt}".encode("utf-8")).hexdigest()[:20]


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ────────────────────────────────────────────────────────────────────────
# ChatGPT スレッドの台帳
# ────────────────────────────────────────────────────────────────────────
def load_threads() -> Dict[str, Any]:
    return _read_json(THREADS_PATH) or {}


def thread_url_for(channel_id: Optional[str]) -> Optional[str]:
    """チャンネル専用スレッド → 既定スレッドの順で URL を返す。

    ここが「ユーザーが横から直せる場所」。チャンネルごとに1本の会話を維持し、
    生成もユーザーの修正指示も同じスレッドに積む。
    """
    threads = load_threads()
    entry = threads.get(channel_id or "") or threads.get("_default") or {}
    if isinstance(entry, str):
        return entry or None
    return (entry.get("url") or "").strip() or None


def set_thread_url(channel_id: str, url: str, note: str = "") -> Dict[str, Any]:
    threads = load_threads()
    threads[channel_id] = {"url": url.strip(), "note": note, "updated_at": _now()}
    _ensure_dirs()
    _write_json(THREADS_PATH, threads)
    return threads


# ────────────────────────────────────────────────────────────────────────
# 依頼を積む / 受け取る
# ────────────────────────────────────────────────────────────────────────
def _cache_path(phash: str) -> Path:
    return CACHE_DIR / f"{phash}.png"


def _find_pending_by_hash(phash: str) -> Optional[Path]:
    for path in PENDING_DIR.glob("*.json"):
        data = _read_json(path)
        if data and data.get("prompt_hash") == phash:
            return path
    return None


def enqueue(
    prompt: str,
    *,
    size: str = "1536x1024",
    channel_id: Optional[str] = None,
    purpose: str = "illustration",
    quality: str = "high",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """依頼を pending に積んで、その依頼 dict を返す。

    同じ (prompt, size) の依頼が既に pending にあれば積み直さず既存を返す。
    autopilot が毎日同じプロンプトを投げてもキューがゴミで溢れないようにするため。
    """
    _ensure_dirs()
    phash = prompt_hash(prompt, size)
    existing = _find_pending_by_hash(phash)
    if existing:
        data = _read_json(existing) or {}
        data["requested_again_at"] = _now()
        data["request_count"] = int(data.get("request_count") or 1) + 1
        _write_json(existing, data)
        return data

    req_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    data: Dict[str, Any] = {
        "id": req_id,
        "status": "pending",
        "created_at": _now(),
        "channel_id": channel_id or "",
        "purpose": purpose,
        "size": size,
        "quality": quality,
        "prompt": prompt,
        "prompt_hash": phash,
        "thread_url": thread_url_for(channel_id) or "",
        "request_count": 1,
    }
    if extra:
        data["extra"] = extra
    _write_json(PENDING_DIR / f"{req_id}.json", data)
    return data


def request_image(
    prompt: str,
    *,
    size: str = "1536x1024",
    channel_id: Optional[str] = None,
    purpose: str = "illustration",
    quality: str = "high",
    wait_seconds: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[bytes]:
    """画像を要求する。取れたら PNG バイト列、取れなければ None。

    1. 同一プロンプトの納品済みキャッシュがあれば即返す
    2. 無ければ pending に積む
    3. `wait_seconds`（既定 0 = 待たない）だけ納品を待つ
    """
    if not is_enabled():
        return None
    _ensure_dirs()

    phash = prompt_hash(prompt, size)
    cached = _cache_path(phash)
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_bytes()

    req = enqueue(
        prompt, size=size, channel_id=channel_id,
        purpose=purpose, quality=quality, extra=extra,
    )

    wait = DEFAULT_WAIT_SECONDS if wait_seconds is None else float(wait_seconds)
    if wait <= 0:
        print(
            f"  🖼️ 画像依頼をキューに積みました（ChatGPT スレッド経由） id={req['id']} "
            f"purpose={purpose} ch={channel_id or '-'}"
        )
        return None

    deadline = time.time() + wait
    while time.time() < deadline:
        if cached.exists() and cached.stat().st_size > 0:
            return cached.read_bytes()
        time.sleep(_POLL_INTERVAL)
    print(f"  ⚠️ 画像ブリッジ待機タイムアウト（{wait:.0f}s） id={req['id']}")
    return None


class Queued(RuntimeError):
    """依頼はキューに積んだが、まだ ChatGPT から画像が返っていない。

    手動スクリプト用。「失敗」ではなく「ワーカーの処理待ち」であることを
    呼び出し側が区別できるようにするための例外。
    """

    def __init__(self, req_id: str, thread_url: Optional[str] = None):
        self.req_id = req_id
        self.thread_url = thread_url
        super().__init__(
            f"ChatGPT スレッドのキューに投入済み（未納品） id={req_id} "
            f"thread={thread_url or '(未登録)'} — "
            f"`python3 scripts/image_bridge.py show {req_id}` で確認"
        )


def generate_or_queue(
    prompt: str,
    *,
    size: str = "1536x1024",
    channel_id: Optional[str] = None,
    purpose: str = "manual",
    quality: str = "high",
    wait_seconds: Optional[float] = None,
) -> bytes:
    """手動スクリプト用の同期取得。未納品なら `Queued` を投げる。

    運用は「1回目の実行で全部キューに積む → Claude セッションがまとめて
    ChatGPT で処理 → もう一度実行するとキャッシュヒットで全部揃う」。
    """
    data = request_image(
        prompt, size=size, channel_id=channel_id,
        purpose=purpose, quality=quality, wait_seconds=wait_seconds,
    )
    if data:
        return data
    phash = prompt_hash(prompt, size)
    pending = _find_pending_by_hash(phash)
    req_id = (_read_json(pending) or {}).get("id", "?") if pending else "?"
    raise Queued(req_id, thread_url_for(channel_id))


# ────────────────────────────────────────────────────────────────────────
# ワーカー側 API
# ────────────────────────────────────────────────────────────────────────
def pending_requests() -> List[Dict[str, Any]]:
    """古い順に pending 依頼を返す。"""
    out: List[Dict[str, Any]] = []
    if not PENDING_DIR.exists():
        return out
    for path in sorted(PENDING_DIR.glob("*.json")):
        data = _read_json(path)
        if data:
            data["_path"] = str(path)
            out.append(data)
    return out


def load_request(req_id: str) -> Optional[Dict[str, Any]]:
    for d in (PENDING_DIR, DELIVERED_DIR, FAILED_DIR):
        path = d / f"{req_id}.json"
        if path.exists():
            data = _read_json(path)
            if data:
                data["_path"] = str(path)
                return data
    return None


def deliver(req_id: str, image_path) -> Dict[str, Any]:
    """ChatGPT から回収した画像をキューに納品する。

    画像は `images/<id>.png` と `cache/<prompt_hash>.png` の両方に置く。
    キャッシュ側が次回以降の即時ヒットに効く。
    """
    _ensure_dirs()
    src = Path(image_path)
    if not src.exists() or src.stat().st_size == 0:
        raise FileNotFoundError(f"納品する画像が見つかりません: {src}")

    pending_path = PENDING_DIR / f"{req_id}.json"
    data = _read_json(pending_path) or load_request(req_id)
    if not data:
        raise KeyError(f"依頼 {req_id} が見つかりません")

    dest = IMAGES_DIR / f"{req_id}.png"
    _normalize_png(src, dest)
    shutil.copyfile(dest, _cache_path(data["prompt_hash"]))

    data.pop("_path", None)
    data["status"] = "delivered"
    data["delivered_at"] = _now()
    data["image_path"] = str(dest)
    _write_json(DELIVERED_DIR / f"{req_id}.json", data)
    if pending_path.exists():
        pending_path.unlink()
    return data


def fail(req_id: str, reason: str) -> Dict[str, Any]:
    """処理できなかった依頼を failed に落とす（理由つき）。"""
    _ensure_dirs()
    pending_path = PENDING_DIR / f"{req_id}.json"
    data = _read_json(pending_path) or load_request(req_id)
    if not data:
        raise KeyError(f"依頼 {req_id} が見つかりません")
    data.pop("_path", None)
    data["status"] = "failed"
    data["failed_at"] = _now()
    data["reason"] = reason
    _write_json(FAILED_DIR / f"{req_id}.json", data)
    if pending_path.exists():
        pending_path.unlink()
    return data


def _normalize_png(src: Path, dest: Path) -> None:
    """納品画像を PNG に正規化して dest に書く。Pillow が無ければそのままコピー。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        with Image.open(src) as img:
            img.convert("RGBA").save(dest, "PNG")
        return
    except Exception:
        shutil.copyfile(src, dest)


def gc(max_age_days: Optional[float] = None) -> Dict[str, int]:
    """TTL を過ぎた pending を failed へ流す。戻り値は件数サマリ。"""
    ttl = PENDING_TTL_DAYS if max_age_days is None else float(max_age_days)
    expired = 0
    cutoff = time.time() - ttl * 86400
    for path in list(PENDING_DIR.glob("*.json")) if PENDING_DIR.exists() else []:
        if path.stat().st_mtime < cutoff:
            data = _read_json(path)
            if data:
                fail(data["id"], f"TTL {ttl:.0f} 日を超過（未処理のまま放置）")
                expired += 1
    return {"expired": expired, "pending": len(pending_requests())}


def status() -> Dict[str, Any]:
    def _count(d: Path) -> int:
        return len(list(d.glob("*.json"))) if d.exists() else 0

    return {
        "enabled": is_enabled(),
        "dir": str(BRIDGE_DIR),
        "pending": _count(PENDING_DIR),
        "delivered": _count(DELIVERED_DIR),
        "failed": _count(FAILED_DIR),
        "cached_images": len(list(CACHE_DIR.glob("*.png"))) if CACHE_DIR.exists() else 0,
        "threads": load_threads(),
        "default_wait_seconds": DEFAULT_WAIT_SECONDS,
    }
