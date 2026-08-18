"""再生リスト自動管理 — アップロード直後に動画を再生リストへ入れる。

狙い:
    再生リストに入った動画は「次の動画」が自動再生されるので、1本あたりの
    視聴時間（セッション時間）が伸びる。YouTube のアルゴリズムはセッション時間を
    強く見るため、同じ本数でも再生リストに束ねてあるチャンネルの方が伸びる。
    手作業では毎日2本×7chを捌けないので、投稿処理の直後に API で入れる。

API の制約:
    - playlists.list / playlists.insert / playlistItems.insert は
      `youtube.force-ssl` スコープで足りる（本プロジェクトは取得済み）。
    - 再生リストの取得は playlists.list(mine=True)。ブランドアカウントは
      チャンネル別 OAuth トークンを使うので、そのトークンの持ち主の
      再生リストがそのまま返る。
    - 予約公開（private + publishAt）の動画でも playlistItems.insert は通る。

設定（チャンネル JSON の publish_settings.playlists）:
    {
      "enabled": true,               # 既定 true（明示的に false で無効化）
      "auto_create": true,           # 無い再生リストを自動作成する
      "privacy": "public",
      "shorts": "ショート まとめ",     # ショートの投入先タイトル（null で入れない）
      "main": "本編 まとめ",           # 長尺の投入先タイトル（null で入れない）
      "rules": [                     # タイトル一致で追加投入（複数ヒット可）
        {"match": ["睡眠", "脳"], "title": "脳と睡眠の科学"}
      ]
    }
    未設定でも既定名（チャンネル名ベース）で動く。

再生リストIDのキャッシュ:
    data/playlists/{channel_id}.json に {タイトル: playlist_id} で保存する。
    API 側で消された場合に備え、insert が 404 を返したらキャッシュを捨てて作り直す。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import youtube_oauth as yt_oauth

PROJECT_ROOT = Path(__file__).parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"
CACHE_DIR = PROJECT_ROOT / "data" / "playlists"

# YouTube 側の上限。再生リストのタイトルは 150 文字、説明は 5000 文字。
MAX_TITLE = 150
MAX_DESC = 5000

_lock = threading.Lock()


# ---------------------------------------------------------------------
# チャンネル設定
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
    cfg = ((channel_dict or {}).get("publish_settings") or {}).get("playlists")
    return cfg if isinstance(cfg, dict) else {}


def is_enabled(channel_id: str, channel_dict: Optional[Dict[str, Any]] = None) -> bool:
    """明示的に false を書かない限り有効（投稿導線は初期値ONで効かせたい）。"""
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    cfg = _cfg(cd)
    return cfg.get("enabled", True) is not False


def default_playlist_title(channel_dict: Dict[str, Any], *, is_short: bool) -> str:
    """設定が無いときの既定タイトル。チャンネル名から作る。"""
    name = (channel_dict or {}).get("name") or (channel_dict or {}).get("id") or "チャンネル"
    return f"{name}｜ショート" if is_short else f"{name}｜本編"


def resolve_playlist_titles(
    channel_id: str,
    *,
    video_title: str = "",
    is_short: bool = True,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """この動画を入れるべき再生リストのタイトル一覧（重複なし・順序保持）。

    1. shorts / main の既定の受け皿
    2. rules の キーワード一致（タイトルに含まれていれば追加）
    """
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    cfg = _cfg(cd)

    titles: List[str] = []
    key = "shorts" if is_short else "main"
    if key in cfg:
        base = cfg.get(key)
        # 明示的に null / "" を入れたチャンネルは既定の受け皿に入れない
        if isinstance(base, str) and base.strip():
            titles.append(base.strip())
    else:
        titles.append(default_playlist_title(cd, is_short=is_short))

    haystack = (video_title or "").lower()
    for rule in cfg.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        title = str(rule.get("title") or "").strip()
        words = rule.get("match") or []
        if not title or not isinstance(words, list):
            continue
        if any(str(w).strip() and str(w).strip().lower() in haystack for w in words):
            titles.append(title)

    out: List[str] = []
    seen = set()
    for t in titles:
        t = t[:MAX_TITLE]
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ---------------------------------------------------------------------
# ID キャッシュ
# ---------------------------------------------------------------------

def _cache_path(channel_id: str) -> Path:
    return CACHE_DIR / f"{channel_id}.json"


def _read_cache(channel_id: str) -> Dict[str, str]:
    p = _cache_path(channel_id)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(channel_id: str, mapping: Dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(channel_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _cache_put(channel_id: str, title: str, playlist_id: str) -> None:
    with _lock:
        mapping = _read_cache(channel_id)
        mapping[title] = playlist_id
        _write_cache(channel_id, mapping)


def _cache_drop(channel_id: str, title: str) -> None:
    with _lock:
        mapping = _read_cache(channel_id)
        if mapping.pop(title, None) is not None:
            _write_cache(channel_id, mapping)


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


def list_my_playlists(channel_id: str, *, youtube=None) -> List[Dict[str, str]]:
    """自分の再生リスト一覧（最大200件）。"""
    yt = youtube or _service(channel_id)
    items: List[Dict[str, str]] = []
    page = None
    for _ in range(4):  # 50 件 × 4 ページ
        resp = (
            yt.playlists()
            .list(part="snippet", mine=True, maxResults=50, pageToken=page)
            .execute()
        )
        for it in resp.get("items", []):
            items.append(
                {"id": it.get("id", ""), "title": (it.get("snippet") or {}).get("title", "")}
            )
        page = resp.get("nextPageToken")
        if not page:
            break
    return items


def ensure_playlist(
    channel_id: str,
    title: str,
    *,
    description: str = "",
    privacy: str = "public",
    auto_create: bool = True,
    youtube=None,
) -> Optional[str]:
    """タイトルの再生リストIDを返す。無ければ作る（auto_create=False なら None）。"""
    title = (title or "").strip()[:MAX_TITLE]
    if not title:
        return None

    cached = _read_cache(channel_id).get(title)
    if cached:
        return cached

    yt = youtube or _service(channel_id)
    for pl in list_my_playlists(channel_id, youtube=yt):
        if pl["title"].strip() == title:
            _cache_put(channel_id, title, pl["id"])
            return pl["id"]

    if not auto_create:
        return None

    resp = (
        yt.playlists()
        .insert(
            part="snippet,status",
            body={
                "snippet": {"title": title, "description": (description or "")[:MAX_DESC]},
                "status": {"privacyStatus": privacy or "public"},
            },
        )
        .execute()
    )
    playlist_id = resp.get("id")
    if playlist_id:
        _cache_put(channel_id, title, playlist_id)
        print(f"📚 再生リスト作成: [{channel_id}] {title} ({playlist_id})")
    return playlist_id


def add_to_playlist(
    channel_id: str, playlist_id: str, video_id: str, *, youtube=None
) -> Dict[str, Any]:
    """playlistItems.insert。既に入っていれば YouTube 側で重複が作られる点に注意し、
    呼び出し側（add_video_to_playlists）で二重投入を防ぐ。"""
    yt = youtube or _service(channel_id)
    resp = (
        yt.playlistItems()
        .insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        )
        .execute()
    )
    return {"ok": True, "item_id": resp.get("id"), "playlist_id": playlist_id}


def _already_in_playlist(yt, playlist_id: str, video_id: str) -> bool:
    try:
        resp = (
            yt.playlistItems()
            .list(part="snippet", playlistId=playlist_id, videoId=video_id, maxResults=1)
            .execute()
        )
        return bool(resp.get("items"))
    except Exception:
        return False


# ---------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------

def add_video_to_playlists(
    channel_id: str,
    video_id: str,
    *,
    title: str = "",
    is_short: bool = True,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """アップロード完了後に呼ぶ入口。失敗しても投稿処理は壊さない。"""
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    if not is_enabled(channel_id, cd):
        return {"ok": False, "skipped": "disabled"}
    if not video_id:
        return {"ok": False, "skipped": "no_video_id"}

    cfg = _cfg(cd)
    titles = resolve_playlist_titles(
        channel_id, video_title=title, is_short=is_short, channel_dict=cd
    )
    if not titles:
        return {"ok": False, "skipped": "no_target_playlist"}

    try:
        yt = _service(channel_id)
    except Exception as e:
        print(f"⚠️ playlist: service unavailable for {channel_id}: {e}")
        return {"ok": False, "error": str(e)}

    concept = (cd.get("concept") or "").strip()
    added: List[Dict[str, Any]] = []
    errors: List[str] = []
    for pl_title in titles:
        try:
            pid = ensure_playlist(
                channel_id,
                pl_title,
                description=concept,
                privacy=str(cfg.get("privacy") or "public"),
                auto_create=cfg.get("auto_create", True) is not False,
                youtube=yt,
            )
            if not pid:
                continue
            if _already_in_playlist(yt, pid, video_id):
                added.append({"playlist": pl_title, "playlist_id": pid, "already": True})
                continue
            try:
                add_to_playlist(channel_id, pid, video_id, youtube=yt)
            except Exception as e:
                # 再生リストが手動削除されているとここで 404。キャッシュを捨てて作り直す。
                if "404" in str(e) or "playlistNotFound" in str(e):
                    _cache_drop(channel_id, pl_title)
                    pid = ensure_playlist(
                        channel_id,
                        pl_title,
                        description=concept,
                        privacy=str(cfg.get("privacy") or "public"),
                        auto_create=True,
                        youtube=yt,
                    )
                    if not pid:
                        raise
                    add_to_playlist(channel_id, pid, video_id, youtube=yt)
                else:
                    raise
            added.append({"playlist": pl_title, "playlist_id": pid, "already": False})
            print(f"📚 再生リスト追加: [{channel_id}] {pl_title} ← {video_id}")
        except Exception as e:
            errors.append(f"{pl_title}: {e}")
            print(f"⚠️ playlist add failed [{channel_id}] {pl_title}: {e}")

    return {"ok": bool(added), "added": added, "errors": errors}


def add_video_to_playlists_async(**kwargs: Any) -> None:
    """アップロードスレッドを塞がない fire-and-forget ラッパ。"""

    def _work() -> None:
        try:
            add_video_to_playlists(**kwargs)
        except Exception as e:
            print(f"⚠️ playlist thread failed: {e}")

    threading.Thread(target=_work, name="playlist-add", daemon=True).start()
