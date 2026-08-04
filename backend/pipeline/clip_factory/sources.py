"""切り抜き元動画の在庫管理。

在庫は「ローカルに残っている長尺 mp4」＋「その台本 JSON」のペア。
video_generator は ~/Desktop/動画出力用/<シナリオtitle>/ に出力し、シナリオは
data/scenarios/<channel>/*.json に title 付きで保存されているので、
フォルダ名 == シナリオ title で突き合わせられる。

どの区間を切り抜き済みかは data/analytics/clip_state.json に記録し、
同じ動画の同じ場所を二度出さないようにする。
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .align import probe_duration

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"
STATE_PATH = PROJECT_ROOT / "data" / "analytics" / "clip_state.json"

# video_generator.OUTPUT_BASE と同じ場所。env で差し替え可能にしておく
OUTPUT_BASE = Path(os.environ.get("VIDEO_OUTPUT_BASE") or (Path.home() / "Desktop" / "動画出力用"))

# 長尺 mp4 のファイル名パターン（プレフィックスは prefix 依存なので後方一致で拾う）
MAIN_SUFFIXES = ("_メイン.mp4",)
SHORT_MARKERS = ("ショート", "short")


@dataclass
class SourceVideo:
    """切り抜き元の1本。"""

    source_channel_id: str
    title: str
    video_path: Path
    scenario: Dict[str, Any]
    duration: float
    youtube_video_id: Optional[str] = None
    used_segments: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source_channel_id}::{self.title}"

    @property
    def lines(self) -> List[Dict[str, Any]]:
        return list(self.scenario.get("full_scenario") or [])

    @property
    def video_title(self) -> str:
        return str(self.scenario.get("video_title") or self.title)

    def source_url(self) -> Optional[str]:
        if self.youtube_video_id:
            return f"https://youtu.be/{self.youtube_video_id}"
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_channel_id": self.source_channel_id,
            "title": self.title,
            "video_path": str(self.video_path),
            "duration": round(self.duration, 2),
            "line_count": len(self.lines),
            "youtube_video_id": self.youtube_video_id,
            "used_segments": self.used_segments,
        }


# ---------------------------------------------------------------------
# 状態（切り抜き済み区間）
# ---------------------------------------------------------------------

def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"sources": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ clip_state 読み込み失敗（新規作成します）: {e}")
        return {"sources": {}}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def record_clip(
    source: SourceVideo,
    segment: Dict[str, Any],
    *,
    clip_id: str,
    upload: Optional[Dict[str, Any]] = None,
) -> None:
    """切り抜き済み区間を記録する。"""
    state = load_state()
    entry = state.setdefault("sources", {}).setdefault(source.key, {
        "source_channel_id": source.source_channel_id,
        "title": source.title,
        "segments": [],
    })
    entry["segments"].append({
        "clip_id": clip_id,
        "start": round(float(segment.get("start", 0.0)), 2),
        "end": round(float(segment.get("end", 0.0)), 2),
        "hook": segment.get("hook"),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "video_id": (upload or {}).get("video_id"),
        "url": (upload or {}).get("url"),
    })
    entry["last_used_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(state)


# ---------------------------------------------------------------------
# シナリオ索引
# ---------------------------------------------------------------------

def _scenario_index(source_channel_ids: List[str]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """(channel_id, title) -> scenario dict。full_scenario を持つものだけ。"""
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for cid in source_channel_ids:
        ch_dir = SCENARIOS_DIR / cid
        if not ch_dir.is_dir():
            continue
        for f in ch_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            title = data.get("title")
            if not title or not data.get("full_scenario"):
                continue
            # 同じ title が複数あるときは行数の多い方を採用（作り直し分を拾う）
            key = (cid, str(title))
            prev = index.get(key)
            if prev is None or len(data["full_scenario"]) > len(prev.get("full_scenario") or []):
                data.setdefault("channel_id", cid)
                index[key] = data
    return index


def _is_main_video(path: Path) -> bool:
    name = path.name
    if any(m in name for m in SHORT_MARKERS):
        return False
    return any(name.endswith(sfx) for sfx in MAIN_SUFFIXES)


# ---------------------------------------------------------------------
# 在庫探索
# ---------------------------------------------------------------------

def discover_sources(
    source_channel_ids: List[str],
    *,
    min_duration_sec: float = 180.0,
    resolve_youtube_ids: bool = True,
) -> List[SourceVideo]:
    """切り抜き可能な長尺動画を列挙する。"""
    if not OUTPUT_BASE.is_dir():
        print(f"⚠️ 出力フォルダが見つかりません: {OUTPUT_BASE}")
        return []

    index = _scenario_index(source_channel_ids)
    by_title: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for (cid, title), sc in index.items():
        by_title.setdefault(title, []).append((cid, sc))

    state = load_state().get("sources", {})
    found: List[SourceVideo] = []
    for folder in sorted(OUTPUT_BASE.iterdir()):
        if not folder.is_dir():
            continue
        candidates = by_title.get(folder.name)
        if not candidates:
            continue
        mains = [p for p in folder.glob("*.mp4") if _is_main_video(p)]
        if not mains:
            continue
        # 同フォルダに複数あるときは最大サイズ（＝完成版）を採用
        video = max(mains, key=lambda p: p.stat().st_size)
        cid, scenario = candidates[0]
        dur = probe_duration(video) or 0.0
        if dur < min_duration_sec:
            continue
        found.append(SourceVideo(
            source_channel_id=cid,
            title=folder.name,
            video_path=video,
            scenario=scenario,
            duration=dur,
            used_segments=list((state.get(f"{cid}::{folder.name}") or {}).get("segments") or []),
        ))

    if resolve_youtube_ids:
        _attach_youtube_ids(found)
    return found


def _normalize(s: str) -> str:
    return re.sub(r"[\s　【】「」『』（）()\[\]|｜・,、。!！?？~〜\-—–_]", "", s).lower()


def _attach_youtube_ids(sources: List[SourceVideo]) -> None:
    """YouTube Data API でタイトル一致から video_id を引く（失敗しても無害）。"""
    api_key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not api_key or not sources:
        return
    try:
        from googleapiclient.discovery import build  # type: ignore
        yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    except Exception as e:
        print(f"⚠️ YouTube API 初期化失敗（元動画URLなしで続行）: {e}")
        return

    # 元チャンネルごとにアップロード一覧を取る
    channel_ids = sorted({s.source_channel_id for s in sources})
    uploads: Dict[str, Dict[str, str]] = {}
    for cid in channel_ids:
        yt_channel = _youtube_channel_id_for(cid)
        if not yt_channel:
            continue
        try:
            ch = yt.channels().list(part="contentDetails", id=yt_channel).execute()
            items = ch.get("items") or []
            if not items:
                continue
            playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            mapping: Dict[str, str] = {}
            token = None
            for _ in range(10):  # 最大 500 本
                res = yt.playlistItems().list(
                    part="snippet", playlistId=playlist, maxResults=50, pageToken=token,
                ).execute()
                for it in res.get("items", []):
                    sn = it["snippet"]
                    mapping[_normalize(sn.get("title", ""))] = sn["resourceId"]["videoId"]
                token = res.get("nextPageToken")
                if not token:
                    break
            uploads[cid] = mapping
        except Exception as e:
            print(f"⚠️ uploads 取得失敗 ({cid}): {e}")

    for s in sources:
        mapping = uploads.get(s.source_channel_id) or {}
        if not mapping:
            continue
        for cand in (s.video_title, s.title):
            norm = _normalize(str(cand))
            if norm in mapping:
                s.youtube_video_id = mapping[norm]
                break
            # 部分一致（タイトルに装飾が付いてアップされている場合）
            hit = next((vid for t, vid in mapping.items() if norm and norm in t), None)
            if hit:
                s.youtube_video_id = hit
                break


def _youtube_channel_id_for(channel_id: str) -> Optional[str]:
    p = PROJECT_ROOT / "data" / "channels" / f"{channel_id}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data.get("youtube_channel_id") or None


# ---------------------------------------------------------------------
# 次に切り抜く動画を選ぶ
# ---------------------------------------------------------------------

def pick_source(
    sources: List[SourceVideo],
    *,
    weights: Optional[Dict[str, float]] = None,
    max_clips_per_video: int = 3,
    seed: Optional[int] = None,
) -> Optional[SourceVideo]:
    """未消化の元動画を1本選ぶ。

    まだ切り抜き数が上限に達していない動画のうち、切り抜き数が少ないものを
    優先し、同点なら元チャンネルの weight で重み付き抽選する。
    """
    available = [s for s in sources if len(s.used_segments) < max_clips_per_video]
    if not available:
        return None
    fewest = min(len(s.used_segments) for s in available)
    pool = [s for s in available if len(s.used_segments) == fewest]
    weights = weights or {}
    w = [max(0.01, float(weights.get(s.source_channel_id, 1.0))) for s in pool]
    rng = random.Random(seed)
    return rng.choices(pool, weights=w, k=1)[0]
