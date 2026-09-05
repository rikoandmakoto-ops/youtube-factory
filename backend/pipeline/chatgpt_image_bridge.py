"""ChatGPT（ブラウザ）で画像を作るためのキュー。OpenAI Images API は使わない。

**Claude 主導の 生成 → 目視チェック → 修正 のループ**を回すための土台。
ChatGPT スレッドは「DALL-E を動かすレンダリング基盤」としてだけ使い、
プロンプトの設計も品質判定も Claude 側が持つ（bot 任せにしない）。

    Claude がプロンプトを書く
        └─ pending/<id>.json に積む（パイプラインは待たない）
             └─ Claude in Chrome が **そのチャンネル専用スレッド**へ送る
                  └─ 出た画像を Claude がスクショで見て判定
                       ├─ NG → reject() で修正指示を積み、同じスレッドで再生成
                       └─ OK → deliver() で採用 → cache に入り次回から即ヒット

**1チャンネル = 1スレッド固定。** スレッド URL は
`data/channels/<ch>.json` の `image_generation.chatgpt_thread_url` に保存する。
毎回新しい会話を開くと、ChatGPT 側に溜まった文脈も、ユーザーが横から入れた
修正指示も全部消える。それを消さないことがこの仕組みの目的。

パイプラインは既定で**待たない**（`wait_seconds=0`）。依頼を積んで即 None を返し、
呼び出し側は Pillow などのフォールバックに落ちる。autopilot は無人で回るので、
画像を待つと投稿枠を落とすため。納品済みの画像は `cache/` に入り、
**次回の同一プロンプトで即ヒットする**。
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
# スレッド URL の正は data/channels/<ch>.json。threads.json は
# `_default`（チャンネルに紐づかない依頼の受け皿）専用の置き場として残す。
THREADS_PATH = BRIDGE_DIR / "threads.json"
CHANNELS_DIR = Path(os.environ.get("IMAGE_BRIDGE_CHANNELS_DIR") or (ROOT / "data" / "channels"))
CHANNEL_CONFIG_KEY = "image_generation"
CHANNEL_THREAD_FIELD = "chatgpt_thread_url"
# 09-05 に 12ch 分の URL が `image_generation` ブロックではなく **トップレベル**の
# `chatgpt_thread_url` に書かれていた。読む側は片方しか見ていなかったので
# `thread_url_for()` が全チャンネルで None を返し、49件の依頼が宛先不明のまま
# 溜まっていた（delivered 0 の直接原因）。書き込みは今も
# `image_generation` ブロックが正だが、読むときは両方見る。
# 「設定に URL があるのに配送されない」を二度と無言で起こさないため。
LEGACY_TOP_LEVEL_THREAD_FIELD = "chatgpt_thread_url"

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
# ChatGPT スレッド — 1チャンネル = 1スレッド固定
#
# 正は `data/channels/<ch>.json` の `image_generation.chatgpt_thread_url`。
# チャンネル設定と同じ場所に置くことで、チャンネルを増やしたときに
# 「スレッドの登録漏れ」がコンフィグ差分として見えるようにしている。
# ────────────────────────────────────────────────────────────────────────
def _channel_config_path(channel_id: str) -> Path:
    return CHANNELS_DIR / f"{channel_id}.json"


def _thread_url_in_config(cfg: Optional[Dict[str, Any]]) -> str:
    """チャンネル設定 dict からスレッド URL を取り出す。

    正の置き場は `image_generation.chatgpt_thread_url`。見つからなければ
    トップレベルの `chatgpt_thread_url`（09-05 の書き込み事故で出来た旧形）へ落ちる。
    """
    if not isinstance(cfg, dict):
        return ""
    block = cfg.get(CHANNEL_CONFIG_KEY)
    if isinstance(block, dict):
        url = (block.get(CHANNEL_THREAD_FIELD) or "").strip()
        if url:
            return url
    return (cfg.get(LEGACY_TOP_LEVEL_THREAD_FIELD) or "").strip()


def load_threads() -> Dict[str, Any]:
    """全チャンネルのスレッド対応を1つの dict にして返す（表示用）。"""
    out: Dict[str, Any] = {}
    if CHANNELS_DIR.exists():
        for path in sorted(CHANNELS_DIR.glob("*.json")):
            cfg = _read_json(path)
            if not isinstance(cfg, dict):
                continue
            block = cfg.get(CHANNEL_CONFIG_KEY)
            block = block if isinstance(block, dict) else {}
            url = _thread_url_in_config(cfg)
            if url:
                out[path.stem] = {
                    "url": url,
                    "note": block.get("note", ""),
                    "updated_at": block.get("updated_at", ""),
                    "source": str(path),
                }
    for key, entry in (_read_json(THREADS_PATH) or {}).items():
        # threads.json は `_default` 専用。チャンネル設定側が勝つ。
        if key not in out:
            out[key] = entry if isinstance(entry, dict) else {"url": entry}
    return out


def thread_url_for(channel_id: Optional[str]) -> Optional[str]:
    """そのチャンネル専用スレッド → `_default` の順で URL を返す。

    ここが「ユーザーが横から直せる場所」。チャンネルごとに1本の会話を維持し、
    生成もユーザーの修正指示も同じスレッドに積む。
    """
    if channel_id:
        url = _thread_url_in_config(_read_json(_channel_config_path(channel_id)))
        if url:
            return url
    entry = (_read_json(THREADS_PATH) or {}).get("_default") or {}
    if isinstance(entry, str):
        return entry.strip() or None
    return (entry.get("url") or "").strip() or None


def set_thread_url(channel_id: str, url: str, note: str = "") -> str:
    """スレッド URL を保存する。書き込んだ場所のパスを返す。

    チャンネル設定が存在すればそこへ（`image_generation` ブロック）、
    `_default` など設定ファイルの無いキーは `threads.json` へ書く。
    """
    url = url.strip()
    path = _channel_config_path(channel_id)
    if path.exists():
        cfg = _read_json(path)
        if not isinstance(cfg, dict):
            raise ValueError(f"チャンネル設定が読めません: {path}")
        block = cfg.get(CHANNEL_CONFIG_KEY)
        if not isinstance(block, dict):
            block = {}
        block[CHANNEL_THREAD_FIELD] = url
        if note:
            block["note"] = note
        block["updated_at"] = _now()
        cfg[CHANNEL_CONFIG_KEY] = block
        # 旧形（トップレベル）が残っていると、どちらが本物か分からない設定が
        # 2 つ並ぶ。正の側へ移したのでここで畳む。
        cfg.pop(LEGACY_TOP_LEVEL_THREAD_FIELD, None)
        _write_json(path, cfg)
        return str(path)

    threads = _read_json(THREADS_PATH) or {}
    threads[channel_id] = {"url": url, "note": note, "updated_at": _now()}
    _ensure_dirs()
    _write_json(THREADS_PATH, threads)
    return str(THREADS_PATH)


def _channel_art_styles() -> List[tuple]:
    """(channel_id, art_style) のリスト。長い順＝具体的な順に並べて返す。

    `video_format.illustration_style.art_style` はチャンネルごとに固有の長文で、
    イラスト依頼のプロンプトはこの文字列で始まる。channel_id が空のまま積まれた
    依頼の宛先を、プロンプト本文から決定論的に復元するために使う。
    """
    out: List[tuple] = []
    if not CHANNELS_DIR.exists():
        return out
    for path in sorted(CHANNELS_DIR.glob("*.json")):
        cfg = _read_json(path)
        if not isinstance(cfg, dict):
            continue
        style = ((cfg.get("video_format") or {}).get("illustration_style") or {})
        art = (style.get("art_style") or "").strip() if isinstance(style, dict) else ""
        if len(art) >= 40:  # 短い共通文言での誤爆を避ける
            out.append((path.stem, art))
    out.sort(key=lambda x: len(x[1]), reverse=True)
    return out


def infer_channel_id(req: Dict[str, Any]) -> Optional[str]:
    """依頼の prompt から発注元チャンネルを推定する。判らなければ None。"""
    prompt = req.get("prompt") or ""
    if not prompt:
        return None
    for channel_id, art in _channel_art_styles():
        if art in prompt:
            return channel_id
    return None


def backfill_pending(*, infer: bool = True) -> Dict[str, Any]:
    """pending 依頼の `channel_id` / `thread_url` を今の設定で貼り直す。

    設定側の書き込み位置がずれていた期間に積まれた依頼は `thread_url` が空の
    ままで、ワーカーが宛先スレッドを決められない。設定を直しても**既存の
    pending は古いスナップショットのまま**なので、ここで貼り直す必要がある。

    `infer=True` のときは `channel_id` が空の依頼をプロンプトから推定して埋める。
    """
    fixed_channel = 0
    fixed_thread = 0
    unresolved: List[str] = []
    for path in sorted(PENDING_DIR.glob("*.json")) if PENDING_DIR.exists() else []:
        data = _read_json(path)
        if not data:
            continue
        changed = False
        if infer and not (data.get("channel_id") or "").strip():
            guess = infer_channel_id(data)
            if guess:
                data["channel_id"] = guess
                fixed_channel += 1
                changed = True
        url = thread_url_for(data.get("channel_id") or None) or ""
        if url != (data.get("thread_url") or ""):
            data["thread_url"] = url
            fixed_thread += 1
            changed = True
        if not url:
            unresolved.append(data.get("id") or path.stem)
        if changed:
            _write_json(path, data)
    return {
        "channel_id_filled": fixed_channel,
        "thread_url_updated": fixed_thread,
        "still_without_thread": unresolved,
    }


def channels_missing_thread() -> List[str]:
    """スレッド未登録のチャンネル ID。登録漏れの検出用。"""
    if not CHANNELS_DIR.exists():
        return []
    return [
        path.stem for path in sorted(CHANNELS_DIR.glob("*.json"))
        if not thread_url_for(path.stem)
    ]


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
        # Claude の 生成 → 目視チェック → 修正 ループの履歴。
        "attempts": [],
        "revisions": [],
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


def deliver(req_id: str, image_path, qc_note: str = "") -> Dict[str, Any]:
    """Claude の品質チェックを通った画像を採用する。

    画像は `images/<id>.png` と `cache/<prompt_hash>.png` の両方に置く。
    キャッシュ側が次回以降の即時ヒットに効く。
    `qc_note` には「何を見て OK にしたか」を残す（後で基準を見直すため）。
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
    data.setdefault("attempts", []).append(
        {"at": data["delivered_at"], "verdict": "accepted", "reason": qc_note}
    )
    if qc_note:
        data["qc_note"] = qc_note
    _write_json(DELIVERED_DIR / f"{req_id}.json", data)
    if pending_path.exists():
        pending_path.unlink()
    return data


def reject(req_id: str, reason: str, revision_prompt: str = "") -> Dict[str, Any]:
    """Claude が品質チェックで落としたときに呼ぶ。**依頼は pending のまま残る。**

    `revision_prompt` は「同じスレッドに次に送る修正指示」。空なら `reason` を使う。
    ワーカーはこれを読んで、新しい会話ではなく**同じスレッド**に投げ直す。
    """
    _ensure_dirs()
    path = PENDING_DIR / f"{req_id}.json"
    data = _read_json(path)
    if not data:
        raise KeyError(f"pending の依頼 {req_id} が見つかりません")

    attempts = data.setdefault("attempts", [])
    attempts.append({"at": _now(), "verdict": "rejected", "reason": reason})
    revisions = data.setdefault("revisions", [])
    revisions.append(revision_prompt.strip() or reason.strip())
    data["last_rejected_at"] = _now()
    _write_json(path, data)
    return data


def next_prompt(req_id: str) -> str:
    """次に ChatGPT スレッドへ送る文面。

    1回目は元のプロンプトそのまま。2回目以降は「直前の生成を、この指示で直す」
    という修正指示だけを送る（同じスレッドなので元の指定は文脈に残っている）。
    """
    data = load_request(req_id)
    if not data:
        raise KeyError(f"依頼 {req_id} が見つかりません")
    revisions = data.get("revisions") or []
    if not revisions:
        return data["prompt"]
    return (
        "直前に生成した画像を、次の指摘を反映して作り直してください。"
        "他の条件（16:9・文字を入れない・下部を空ける等）は前のまま維持すること。\n\n"
        + "\n".join(f"- {r}" for r in revisions)
    )


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
        "channels_missing_thread": channels_missing_thread(),
        "default_wait_seconds": DEFAULT_WAIT_SECONDS,
    }
