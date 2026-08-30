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
import shutil
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

# TCC を避けるためのミラー置き場。~/Movies は Desktop / Documents / Downloads と
# 違って TCC の保護対象ではないので、launchd 下の backend からも読める。
# `run_clip_channel.py --mirror` が OUTPUT_BASE からハードリンクを張る。
MIRROR_BASE = Path(os.environ.get("CLIP_SOURCE_MIRROR")
                   or (Path.home() / "Movies" / "yf_clip_sources"))

#: 素材を探す順番。読めるミラーを先に見る
DEFAULT_SOURCE_ROOTS = [MIRROR_BASE, OUTPUT_BASE]


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False

# 長尺 mp4 のファイル名パターン（プレフィックスは prefix 依存なので後方一致で拾う）
MAIN_SUFFIXES = ("_メイン.mp4",)
SHORT_MARKERS = ("ショート", "short")


@dataclass
class SourceVideo:
    """切り抜き元の1本。

    自社動画と外部動画（許諾済みチャンネル）の両方を同じ形で表す。違いは3点で、
    どれも「外部は動画本体が手元に無い」ことから来ている:

      1. `timings` — 自社は台本＋シーン検出で行タイムラインを復元するが、外部は
         YouTube 字幕から先に作ってあるのでそれをそのまま持たせる。
      2. `materializer` — 外部は2〜6時間の配信なので丸ごと落とせない。区間が
         決まってから「その区間だけ」落とす関数をここに差す。
      3. `crop_bottom_ratio` — 自社（ゆっくり）は下部の焼き込み字幕を切り落とすが、
         外部動画にその帯は無いので切ってはいけない（顔が欠ける）。
    """

    source_channel_id: str
    title: str
    video_path: Optional[Path]
    scenario: Dict[str, Any]
    duration: float
    youtube_video_id: Optional[str] = None
    used_segments: List[Dict[str, Any]] = field(default_factory=list)

    #: 外部素材かどうか。retention 取得や下部クロップの有無が変わる
    is_external: bool = False
    #: 事前に確定している行タイムライン（外部素材＝字幕由来）
    timings: Optional[List[Any]] = None
    #: 説明欄に出すクレジット名。外部は元チャンネル名
    credit_name: Optional[str] = None
    #: 出典表示（CC BY の帰属表示義務にも使う）
    attribution: str = ""
    #: 元動画の下部を切り落とす比率。None ならチャンネル既定
    crop_bottom_ratio: Optional[float] = None
    #: 区間を指定すると (ファイル, そのファイルの0秒が元動画の何秒か) を返す関数
    materializer: Optional[Any] = None
    #: 許諾判定の記録（監査用）
    permission: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        # 外部素材はタイトルが被りうるので video_id を鍵にする
        if self.is_external and self.youtube_video_id:
            return f"{self.source_channel_id}::{self.youtube_video_id}"
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
        # YouTube 以外の出典（Reddit の投稿ページなど）は permission に入る。
        # 説明欄の出典表示は必須なので、ここで拾えないと「本編URLはプロフィールから」
        # という嘘の案内が出てしまう。
        url = (self.permission or {}).get("url")
        return str(url) if url else None

    def materialize(self, start: float, end: float) -> Tuple[Path, float]:
        """切り抜く区間の映像を手元に用意する。

        Returns:
            (ファイルパス, オフセット秒)。オフセットは「そのファイルの 0 秒が
            元動画の何秒に当たるか」。自社動画は丸ごと手元にあるので 0.0。
        """
        if self.materializer is not None:
            return self.materializer(start, end)
        if self.video_path is None:
            raise RuntimeError(f"素材ファイルがありません: {self.title}")
        return self.video_path, 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_channel_id": self.source_channel_id,
            "title": self.title,
            "video_path": str(self.video_path) if self.video_path else None,
            "duration": round(self.duration, 2),
            "line_count": len(self.lines),
            "youtube_video_id": self.youtube_video_id,
            "used_segments": self.used_segments,
            "is_external": self.is_external,
            "credit_name": self.credit_name,
            "permission": self.permission,
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
# ディレクトリ列挙（macOS TCC 対策）
# ---------------------------------------------------------------------
#
# OUTPUT_BASE は既定で ~/Desktop 配下にある。macOS の TCC は launchd が起動した
# プロセスに対して Desktop の**列挙**だけを拒否する（書き込みと、パスを直接
# 指定した open/stat は通る）。そのため:
#
#   - 手で叩く `python3 run_clip_channel.py` … ターミナルに権限があるので動く
#   - launchd 経由の backend / autopilot  … iterdir() が EPERM で落ちる
#
# という「手動では再現しない」形で autopilot だけが死ぬ。実際 2026-08-21 時点の
# backend.log に `PermissionError: [Errno 1] Operation not permitted:
# '/Users/ayukiyamazaki/Desktop/動画出力用'` が出続けており、切り抜きの在庫探索が
# 毎回 500 になっていた。
#
# 対策は「列挙しないで済ませる」。素材のパスは
#   OUTPUT_BASE / <シナリオtitle> / <channel_id>_メイン.mp4
# と決まっていて、シナリオ title は data/scenarios（列挙できる場所）にあるので、
# **パスを組み立てて exists() で確認すれば列挙は要らない**。
#
# 恒久的に直したいなら、フルディスクアクセスを python3 に与えるか、
# VIDEO_OUTPUT_BASE を Desktop の外（例 ~/Movies/動画出力用）に移すこと。

def _is_readable(path: Path) -> bool:
    """実際に1バイト読んで確かめる。

    TCC は `os.access` や `stat` では検出できない（stat は通るのに open が
    EPERM になる）。しかも ffprobe に読ませると **120秒のタイムアウトまで
    ぶら下がる**ので、在庫探索が数十分固まる。ffprobe を呼ぶ前に必ずここで
    弾くこと（実測 2026-08-21: これが無いと /api/clips/.../sources が
    10分でも返ってこなかった）。
    """
    try:
        with open(path, "rb") as fh:
            fh.read(1)
        return True
    except OSError:
        return False


def _can_enumerate(path: Path) -> bool:
    try:
        next(iter(path.iterdir()), None)
        return True
    except PermissionError:
        return False
    except OSError:
        return False


def _folder_videos(folder: Path, channel_ids: List[str],
                   *, can_enumerate: bool = True) -> List[Path]:
    """フォルダ内の長尺 mp4 を返す。

    ⚠️ TCC 下の glob() は **例外を投げずに空リストを返す**（実測 2026-08-21）。
    そのため「glob が空だったら列挙不可かもしれない」と疑って、必ず命名規則
    による直接指定にフォールバックする。ここを try/except だけで書くと
    「エラーは出ないが在庫0本」という静かな死に方をする。
    """
    if can_enumerate:
        try:
            hits = [p for p in folder.glob("*.mp4") if _is_main_video(p)]
            if hits:
                return hits
        except PermissionError:
            pass

    # 列挙不可（or 空）: video_generator の命名規則 <prefix>_メイン.mp4 を直接叩く。
    # prefix は channel_id なので、対象チャンネル分だけ試せばよい。
    # stat/open はパス直指定なら TCC でも通る（列挙だけが拒否される）。
    out: List[Path] = []
    for cid in channel_ids:
        for sfx in MAIN_SUFFIXES:
            cand = folder / f"{cid}{sfx}"
            try:
                if cand.is_file():
                    out.append(cand)
            except OSError:
                continue
    return out


# ---------------------------------------------------------------------
# 在庫探索
# ---------------------------------------------------------------------

def discover_sources(
    source_channel_ids: List[str],
    *,
    min_duration_sec: float = 180.0,
    resolve_youtube_ids: bool = True,
    source_roots: Optional[List[Path]] = None,
) -> List[SourceVideo]:
    """切り抜き可能な長尺動画を列挙する。

    Args:
        source_roots: 素材を探すルート。先頭から順に見て、**最初に読める方**を
            採用する。TCC で読めない ~/Desktop を避けるためのミラー
            （`--mirror` で作る）を先に置く運用を想定している。
            省略時は [MIRROR_BASE, OUTPUT_BASE]。
    """
    roots = [Path(r) for r in (source_roots or DEFAULT_SOURCE_ROOTS)]
    roots = [r for r in roots if _safe_is_dir(r)]
    if not roots:
        print(f"⚠️ 素材フォルダが見つかりません: "
              f"{', '.join(str(r) for r in (source_roots or DEFAULT_SOURCE_ROOTS))}")
        return []

    index = _scenario_index(source_channel_ids)
    by_title: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for (cid, title), sc in index.items():
        by_title.setdefault(title, []).append((cid, sc))

    state = load_state().get("sources", {})

    # 列挙できるなら従来どおりフォルダを走査する（命名規則から外れた mp4 も拾える）。
    # できないなら（launchd 下の TCC）、シナリオ title からパスを組んで直接当たる。
    found: List[SourceVideo] = []
    seen_titles = set()
    unreadable = 0

    for root in roots:
        can_enum = _can_enumerate(root)
        if can_enum:
            try:
                folders = [p for p in sorted(root.iterdir()) if p.is_dir()]
            except PermissionError:
                can_enum = False
                folders = [root / t for t in sorted(by_title)]
        else:
            print(f"⚠️ 素材フォルダを列挙できません（macOS の TCC）: {root}\n"
                  f"   シナリオ {len(by_title)} 件からパスを直接組み立てて探索します。")
            folders = [root / t for t in sorted(by_title)]

        for folder in folders:
            if folder.name in seen_titles:
                continue          # 先に見つかった（＝読めた）ルートを優先する
            candidates = by_title.get(folder.name)
            if not candidates:
                continue
            if not _safe_is_dir(folder):
                continue
            mains = _folder_videos(folder, source_channel_ids, can_enumerate=can_enum)
            if not mains:
                continue
            # 同フォルダに複数あるときは最大サイズ（＝完成版）を採用
            try:
                video = max(mains, key=lambda p: p.stat().st_size)
            except OSError:
                continue
            # ffprobe に渡す前に必ず可読性を確かめる。ここを飛ばすと TCC で
            # 読めないファイル1本につき 120 秒ぶら下がる。
            if not _is_readable(video):
                unreadable += 1
                continue
            cid, scenario = candidates[0]
            dur = probe_duration(video) or 0.0
            if dur < min_duration_sec:
                continue
            seen_titles.add(folder.name)
            found.append(SourceVideo(
                source_channel_id=cid,
                title=folder.name,
                video_path=video,
                scenario=scenario,
                duration=dur,
                used_segments=list(
                    (state.get(f"{cid}::{folder.name}") or {}).get("segments") or []),
            ))

    if unreadable:
        print(f"⚠️ 読み取りを拒否された素材が {unreadable} 本ありました（macOS の TCC）。\n"
              f"   `python3 run_clip_channel.py --mirror` で読める場所へミラーするか、\n"
              f"   /usr/bin/python3 にフルディスクアクセスを与えてください。")

    if resolve_youtube_ids:
        _attach_youtube_ids(found)
    return found


# ---------------------------------------------------------------------
# ミラー作成（TCC 回避）
# ---------------------------------------------------------------------

def build_mirror(
    source_channel_ids: List[str],
    *,
    mirror_base: Optional[Path] = None,
    min_duration_sec: float = 180.0,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """OUTPUT_BASE の長尺 mp4 を、TCC 保護外のミラーへハードリンクする。

    **権限のあるコンテキストから実行すること**（＝ターミナルから
    `python3 run_clip_channel.py --mirror`）。launchd 配下の backend は
    ~/Desktop を読めないので、この関数自体をそこから呼んでも失敗する。

    ハードリンクなので追加のディスクは消費しない（同一ボリューム前提）。
    別ボリュームだった場合は自動的にコピーへ切り替える。
    """
    mirror_base = Path(mirror_base or MIRROR_BASE)
    mirror_base.mkdir(parents=True, exist_ok=True)

    index = _scenario_index(source_channel_ids)
    by_title: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for (cid, title), sc in index.items():
        by_title.setdefault(title, []).append((cid, sc))

    linked, skipped, failed = [], 0, []
    for title in sorted(by_title):
        if limit is not None and len(linked) >= limit:
            break
        src_folder = OUTPUT_BASE / title
        if not _safe_is_dir(src_folder):
            continue
        mains = _folder_videos(src_folder, source_channel_ids, can_enumerate=True)
        if not mains:
            continue
        try:
            video = max(mains, key=lambda p: p.stat().st_size)
        except OSError:
            continue
        if not _is_readable(video):
            failed.append(f"{title}（読み取り拒否）")
            continue
        dur = probe_duration(video) or 0.0
        if dur < min_duration_sec:
            continue

        dst_folder = mirror_base / title
        dst_folder.mkdir(parents=True, exist_ok=True)
        dst = dst_folder / video.name
        if dst.exists():
            skipped += 1
            continue
        try:
            os.link(video, dst)
        except OSError:
            try:
                shutil.copy2(video, dst)   # 別ボリューム等
            except OSError as e:
                failed.append(f"{title}（{e}）")
                continue
        linked.append(str(dst))

    return {"mirror_base": str(mirror_base), "linked": linked,
            "already": skipped, "failed": failed}


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
