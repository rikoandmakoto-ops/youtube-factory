"""シリーズ連続性 — 説明文に「前回の動画」「次回の動画」を相互リンクする。

狙い:
    1本見た人を次の1本へ送る導線を、投稿のたびに自動で貼り直す。
    説明文の関連リンク（description_blocks.build_related_block）はチャンネルの
    タブへ飛ばすだけで「次にどれを見ればいいか」を指定できない。前回/次回の
    実動画URLを入れると回遊が直線になる。

仕組み:
    投稿履歴を data/series_links/{channel_id}.json に残し、新規投稿のたびに
      - 新しい動画の説明文に「▼ 前回の動画」を差し込む
      - 1つ前の動画の説明文に「▶ 次回の動画」を差し込む（videos.update）
    ショートと長尺は別系列として扱う（ショートの次回はショート）。

API の制約:
    - videos.update は snippet を丸ごと送り直す必要があるので、必ず
      videos.list で現在の snippet を取得してから description だけ差し替える。
      categoryId / title を落とすと更新が 400 になる。
    - `youtube.force-ssl` スコープで通る（本プロジェクトは取得済み）。
    - 予約公開（private + publishAt）の動画でも説明文の更新は可能。

設定（チャンネル JSON の publish_settings.series_links）:
    {"enabled": true}   # 既定 true。false で無効化
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import youtube_oauth as yt_oauth

PROJECT_ROOT = Path(__file__).parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"
HISTORY_DIR = PROJECT_ROOT / "data" / "series_links"

PREV_HEADER = "▼ 前回の動画"
NEXT_HEADER = "▶ 次回の動画"

# 説明文は 5000 文字上限。リンクブロックを足して溢れないよう余白を見る。
MAX_DESCRIPTION = 5000
# 履歴に残す件数（前回リンクに必要なのは直近だけなので、肥大化を防ぐ）
MAX_HISTORY = 200

_lock = threading.Lock()


# ---------------------------------------------------------------------
# 設定 / 履歴
# ---------------------------------------------------------------------

def _load_channel(channel_id: str) -> Dict[str, Any]:
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cfg(channel_dict: Dict[str, Any]) -> Dict[str, Any]:
    cfg = ((channel_dict or {}).get("publish_settings") or {}).get("series_links")
    return cfg if isinstance(cfg, dict) else {}


def is_enabled(channel_id: str, channel_dict: Optional[Dict[str, Any]] = None) -> bool:
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    return _cfg(cd).get("enabled", True) is not False


def _history_path(channel_id: str) -> Path:
    return HISTORY_DIR / f"{channel_id}.json"


def read_history(channel_id: str) -> List[Dict[str, Any]]:
    p = _history_path(channel_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("entries") or []
    return [e for e in data if isinstance(e, dict)]


def _write_history(channel_id: str, entries: List[Dict[str, Any]]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    p = _history_path(channel_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(entries[-MAX_HISTORY:], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    os.replace(tmp, p)


def last_entry(
    channel_id: str, *, is_short: bool, exclude_video_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """同じ系列（ショート/長尺）の直近の投稿。"""
    kind = "short" if is_short else "main"
    for e in reversed(read_history(channel_id)):
        if e.get("kind") != kind:
            continue
        if exclude_video_id and e.get("video_id") == exclude_video_id:
            continue
        if e.get("video_id"):
            return e
    return None


# ---------------------------------------------------------------------
# 説明文のブロック編集
# ---------------------------------------------------------------------

def strip_block(description: str, header: str) -> str:
    """既存の 前回/次回 ブロック（ヘッダ行＋続く非空行）を取り除く。

    投稿のたびに貼り直すので、同じヘッダが積み重ならないよう先に消す。
    """
    lines = (description or "").split("\n")
    out: List[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == header:
            i += 1
            while i < len(lines) and lines[i].strip():
                i += 1
            # ブロック直後の空行も1つだけ食べる（空行が増殖しないように）
            if i < len(lines) and not lines[i].strip():
                i += 1
            # ブロック直前に置いた空行も畳む
            while out and not out[-1].strip():
                out.pop()
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def build_link_block(header: str, title: str, url: str) -> List[str]:
    label = (title or "").strip()
    if len(label) > 60:
        label = label[:59] + "…"
    lines = [header]
    if label:
        lines.append(f"・{label}")
    lines.append(url)
    return lines


def apply_block(description: str, header: str, title: str, url: str) -> str:
    """説明文の末尾に 前回/次回 ブロックを（重複させずに）足す。"""
    if not url:
        return description
    base = strip_block(description or "", header).rstrip()
    block = "\n".join(build_link_block(header, title, url))
    merged = f"{base}\n\n{block}" if base else block
    if len(merged) <= MAX_DESCRIPTION:
        return merged
    # 溢れる場合は本文側を削ってリンクを優先する（導線が本体より価値が高い）
    budget = MAX_DESCRIPTION - len(block) - 2
    if budget <= 0:
        return block[:MAX_DESCRIPTION]
    return f"{base[:budget].rstrip()}\n\n{block}"


# ---------------------------------------------------------------------
# YouTube API
# ---------------------------------------------------------------------

def _service(channel_id: str):
    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception as e:
        raise RuntimeError(f"google-api-python-client 未導入: {e}")
    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        raise RuntimeError(f"{channel_id} が YouTube 未連携")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def update_description(
    channel_id: str,
    video_id: str,
    *,
    header: str,
    link_title: str,
    link_url: str,
    youtube=None,
) -> Dict[str, Any]:
    """既存動画の説明文にリンクブロックを差し込む（snippet を保全して update）。"""
    yt = youtube or _service(channel_id)
    resp = yt.videos().list(part="snippet", id=video_id).execute()
    items = resp.get("items") or []
    if not items:
        return {"ok": False, "error": f"video not found: {video_id}"}

    snippet = dict(items[0].get("snippet") or {})
    new_desc = apply_block(snippet.get("description") or "", header, link_title, link_url)
    if new_desc == (snippet.get("description") or ""):
        return {"ok": True, "unchanged": True, "video_id": video_id}

    snippet["description"] = new_desc
    # videos.update は snippet を丸ごと置き換えるので、必須項目を落とさない
    body = {
        "id": video_id,
        "snippet": {
            "title": snippet.get("title") or "",
            "description": new_desc,
            "categoryId": snippet.get("categoryId") or "27",
        },
    }
    for key in ("tags", "defaultLanguage", "defaultAudioLanguage"):
        if snippet.get(key):
            body["snippet"][key] = snippet[key]

    yt.videos().update(part="snippet", body=body).execute()
    return {"ok": True, "video_id": video_id, "header": header}


# ---------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------

def record_upload(
    channel_id: str,
    video_id: str,
    *,
    title: str = "",
    url: str = "",
    is_short: bool = True,
) -> Dict[str, Any]:
    """履歴に1件足す（リンク処理はしない）。"""
    entry = {
        "video_id": video_id,
        "title": title or "",
        "url": url or f"https://youtube.com/watch?v={video_id}",
        "kind": "short" if is_short else "main",
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with _lock:
        entries = read_history(channel_id)
        if any(e.get("video_id") == video_id for e in entries):
            return {"ok": True, "already": True}
        entries.append(entry)
        _write_history(channel_id, entries)
    return {"ok": True, "entry": entry}


def link_and_record(
    channel_id: str,
    video_id: str,
    *,
    title: str = "",
    url: str = "",
    is_short: bool = True,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """アップロード完了後に呼ぶ入口。

    - 直前の同系列動画があれば、新動画へ「前回」、旧動画へ「次回」を貼る。
    - どちらの API 呼び出しが失敗しても履歴には残す（次回以降の起点は進める）。
    """
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    if not is_enabled(channel_id, cd):
        return {"ok": False, "skipped": "disabled"}
    if not video_id:
        return {"ok": False, "skipped": "no_video_id"}

    video_url = url or f"https://youtube.com/watch?v={video_id}"
    prev = last_entry(channel_id, is_short=is_short, exclude_video_id=video_id)
    result: Dict[str, Any] = {"ok": True, "prev_linked": False, "next_linked": False}

    if prev:
        try:
            yt = _service(channel_id)
        except Exception as e:
            print(f"⚠️ series_links: service unavailable for {channel_id}: {e}")
            record_upload(channel_id, video_id, title=title, url=video_url, is_short=is_short)
            return {"ok": False, "error": str(e)}

        try:
            update_description(
                channel_id,
                video_id,
                header=PREV_HEADER,
                link_title=prev.get("title") or "",
                link_url=prev.get("url") or "",
                youtube=yt,
            )
            result["prev_linked"] = True
            print(f"🔗 series_links: {video_id} ← 前回 {prev.get('video_id')}")
        except Exception as e:
            result["prev_error"] = str(e)
            print(f"⚠️ series_links prev failed [{channel_id}] {video_id}: {e}")

        try:
            update_description(
                channel_id,
                str(prev.get("video_id")),
                header=NEXT_HEADER,
                link_title=title,
                link_url=video_url,
                youtube=yt,
            )
            result["next_linked"] = True
            print(f"🔗 series_links: {prev.get('video_id')} → 次回 {video_id}")
        except Exception as e:
            result["next_error"] = str(e)
            print(f"⚠️ series_links next failed [{channel_id}] {prev.get('video_id')}: {e}")

    record_upload(channel_id, video_id, title=title, url=video_url, is_short=is_short)
    result["prev_video_id"] = (prev or {}).get("video_id")
    return result


def seed_from_youtube(
    channel_id: str, *, limit: int = 10, short_max_seconds: int = 185
) -> Dict[str, Any]:
    """既存のアップロードから履歴を作る（導入時の1回だけ使う想定）。

    履歴が空だと最初の1本に「前回」を貼れないので、直近の投稿を古い順に
    流し込んで起点を作る。説明文の書き換えは行わない（読み取りのみ）。
    ショート判定は尺（既定 185 秒以下）で行う。
    """
    yt = _service(channel_id)
    resp = yt.channels().list(part="contentDetails", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        return {"ok": False, "error": "channel not found"}
    uploads = (
        ((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {})
        .get("uploads")
    )
    if not uploads:
        return {"ok": False, "error": "uploads playlist not found"}

    pl = (
        yt.playlistItems()
        .list(part="snippet,contentDetails", playlistId=uploads, maxResults=min(50, limit))
        .execute()
    )
    entries = list(reversed(pl.get("items") or []))  # 古い順に積む
    video_ids = [
        (it.get("contentDetails") or {}).get("videoId") for it in entries
    ]
    video_ids = [v for v in video_ids if v]
    if not video_ids:
        return {"ok": True, "seeded": 0}

    details = yt.videos().list(part="contentDetails,snippet", id=",".join(video_ids)).execute()
    by_id = {d["id"]: d for d in details.get("items", [])}

    seeded = 0
    for vid in video_ids:
        d = by_id.get(vid) or {}
        dur = _iso8601_seconds(((d.get("contentDetails") or {}).get("duration")) or "")
        title = (d.get("snippet") or {}).get("title") or ""
        res = record_upload(
            channel_id,
            vid,
            title=title,
            url=f"https://youtube.com/watch?v={vid}",
            is_short=dur is not None and dur <= short_max_seconds,
        )
        if not res.get("already"):
            seeded += 1
    return {"ok": True, "seeded": seeded, "total": len(video_ids)}


def _iso8601_seconds(duration: str) -> Optional[int]:
    """"PT1M30S" → 90。パースできなければ None。"""
    import re

    m = re.fullmatch(
        r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", (duration or "").strip()
    )
    if not m:
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def link_and_record_async(**kwargs: Any) -> None:
    def _work() -> None:
        try:
            link_and_record(**kwargs)
        except Exception as e:
            print(f"⚠️ series_links thread failed: {e}")

    threading.Thread(target=_work, name="series-links", daemon=True).start()
