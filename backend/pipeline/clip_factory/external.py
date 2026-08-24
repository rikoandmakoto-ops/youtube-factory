"""許諾済み外部チャンネルの動画を、切り抜き元（SourceVideo）に変換する。

自社動画の在庫探索（`sources.discover_sources`）の外部版。違いは調達の順番で、
外部素材は **軽いものから順に取る**:

    1. YouTube Data API で候補を列挙し、説明欄の許諾文言で切り抜き可否を判定
       （`acquisition.classify`。ここを通らないものは映像に一切触れない）
    2. 字幕だけダウンロード（数百KB）→ 行タイムラインを復元
    3. 区間が決まってから、その区間だけダウンロード（数十MB）

丸ごと落としてから考える作りにすると、2〜6時間の配信が相手では1本あたり
数GB・数十分かかって autopilot の枠に収まらない。字幕を先に見るのは
「どこが面白いか」を決めるのに映像が要らないから成立する。

════════════════════════════════════════════════════════════════════
■ 権利面の位置づけ
════════════════════════════════════════════════════════════════════

このモジュールは `acquisition.classify` が `clippable` と判定したものしか
扱わない。`download_section` / `fetch_subtitles` の側でも二重にチェックして
いるので、theme_only の動画はここを通っても落とせない。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import acquisition as acq
from . import captions as cap
from .sources import PROJECT_ROOT, SourceVideo, load_state

#: 字幕が取れなかった動画を覚えておく（毎回 yt-dlp を叩き直さない）
SUBTITLE_MISS_STATE = PROJECT_ROOT / "data" / "analytics" / "clip_subtitle_misses.json"

#: 外部素材の source_channel_id に付ける接頭辞。
#: この値は clip_id →**ファイル名**に入るので `:` を使ってはいけない。
#: `yt:UC...` にすると ffmpeg / ffprobe が `yt:` をプロトコル指定と解釈して
#: 「Protocol not found」で落ちる（実測 2026-08-21）。
EXTERNAL_PREFIX = "yt_"


def external_channel_key(youtube_channel_id: str) -> str:
    return f"{EXTERNAL_PREFIX}{youtube_channel_id}"


def _download_dir(clip_cfg: Dict[str, Any]) -> Path:
    cfg = clip_cfg.get("external_sources") or {}
    raw = cfg.get("download_dir")
    if raw:
        return Path(str(raw)).expanduser()
    return acq.DEFAULT_DOWNLOAD_DIR


def _allowlist_weights(clip_cfg: Dict[str, Any]) -> Dict[str, float]:
    """allowlist_channels の weight を {youtube_channel_id: weight} で返す。"""
    cfg = clip_cfg.get("external_sources") or {}
    out: Dict[str, float] = {}
    for entry in cfg.get("allowlist_channels") or []:
        cid = str(entry.get("channel_id") or "").strip()
        if cid:
            out[cid] = float(entry.get("weight") or 1.0)
    return out


def _load_misses() -> Dict[str, Any]:
    if not SUBTITLE_MISS_STATE.exists():
        return {}
    try:
        return json.loads(SUBTITLE_MISS_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _record_miss(video_id: str, reason: str) -> None:
    data = _load_misses()
    data[video_id] = {"reason": reason, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    SUBTITLE_MISS_STATE.parent.mkdir(parents=True, exist_ok=True)
    SUBTITLE_MISS_STATE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------
# 候補 → SourceVideo
# ---------------------------------------------------------------------

def _make_materializer(cand: acq.ExternalCandidate, clip_cfg: Dict[str, Any],
                       dest_dir: Path, max_height: int):
    """区間が決まってから呼ばれるダウンローダを作る。"""

    def materialize(start: float, end: float) -> Tuple[Path, float]:
        return acq.download_section(
            cand, start=start, end=end, clip_cfg=clip_cfg,
            dest_dir=dest_dir, max_height=max_height,
        )

    return materialize


def build_source(
    cand: acq.ExternalCandidate,
    *,
    clip_cfg: Dict[str, Any],
    used_segments: Optional[List[Dict[str, Any]]] = None,
) -> Optional[SourceVideo]:
    """1本の候補を SourceVideo にする。字幕が取れなければ None。"""
    if cand.use_as != acq.USE_CLIPPABLE:
        return None

    cfg = clip_cfg.get("external_sources") or {}
    dest_dir = _download_dir(clip_cfg)
    langs = [str(l) for l in (cfg.get("subtitle_langs") or ["ja-orig", "ja"])]

    vtt = acq.fetch_subtitles(cand, clip_cfg=clip_cfg, dest_dir=dest_dir, langs=langs)
    if not vtt:
        _record_miss(cand.video_id, "字幕なし")
        return None

    timings = cap.parse_vtt_file(
        vtt,
        total_duration=cand.duration_sec,
        speaker=cand.credit_name or cand.channel_title,
        line_chars=int(cfg.get("subtitle_line_chars") or cap.DEFAULT_LINE_CHARS),
    )
    if len(timings) < 10:
        _record_miss(cand.video_id, f"字幕が短すぎる（{len(timings)}行）")
        print(f"  ⚠️ 字幕が薄いので除外: {cand.title[:40]}（{len(timings)}行）")
        return None

    return SourceVideo(
        source_channel_id=external_channel_key(cand.channel_id),
        title=cand.title,
        video_path=None,                     # 区間が決まってから落とす
        scenario={
            "video_title": cand.title,
            "full_scenario": cap.timings_to_scenario_lines(timings),
            "channel_id": cand.channel_id,
        },
        duration=cand.duration_sec,
        youtube_video_id=cand.video_id,
        used_segments=list(used_segments or []),
        is_external=True,
        timings=timings,
        credit_name=cand.credit_name or cand.channel_title,
        attribution=acq.attribution_text(cand),
        # 外部動画に「下部の焼き込み字幕帯」は無い。切ると顔や字幕が欠ける
        crop_bottom_ratio=float(cfg.get("source_crop_bottom_ratio") or 0.0),
        materializer=_make_materializer(
            cand, clip_cfg, dest_dir, int(cfg.get("max_height") or 1080)),
        permission={
            "use_as": cand.use_as,
            "reason": cand.reason,
            "phrase": cand.permission_phrase,
            "license": cand.license,
            "channel_id": cand.channel_id,
            "channel_title": cand.channel_title,
            "url": cand.url,
        },
    )


def discover_external_sources(
    clip_cfg: Dict[str, Any],
    *,
    limit: int = 5,
    candidates: Optional[Sequence[acq.ExternalCandidate]] = None,
) -> List[SourceVideo]:
    """許諾済み外部チャンネルから切り抜ける元動画を集める。

    Args:
        limit: 字幕まで取りに行く本数の上限。多く見ても使うのは1本なので、
            既定では上位数本で打ち切る（yt-dlp 呼び出しを増やさない）。
    """
    if not acq.is_enabled(clip_cfg):
        return []

    if candidates is None:
        res = acq.acquire(clip_cfg, download=False)
        if res.get("error"):
            print(f"⚠️ 外部素材の調達に失敗: {res['error']}")
            return []
        pool = [_rehydrate(c) for c in (res.get("clippable") or [])]
    else:
        pool = list(candidates)

    if not pool:
        print("ℹ️ 切り抜き可能な外部素材が0本でした（許諾文言のある回が無い可能性）")
        return []

    # allowlist の weight が高いチャンネルから先に用意する。
    #
    # `limit`（prepare_limit）で打ち切るので、ここの順番がそのまま
    # 「どのチャンネルが候補に上がるか」になる。再生数だけで並べると、
    # 主ソースに指定したチャンネルより再生数の多い別チャンネルの回が
    # 枠を埋めてしまう。さらに pick_source は「切り抜き済みの本数が最少」の
    # 動画に絞ってから weight 抽選をするので、未使用の動画が1本でも混ざると
    # weight が効く前に主ソースが候補から消える（実測 2026-08-24: weight 5 の
    # ひろゆきを設定したのに weight 1 の岡田斗司夫が選ばれた）。
    #
    # weight 順に用意しておけば、主ソースの在庫が尽きた日だけ下位チャンネルが
    # 出てくる＝フォールバックとして期待どおりに振る舞う。
    weights = _allowlist_weights(clip_cfg)
    pool.sort(key=lambda c: (-weights.get(c.channel_id, 1.0), -c.view_count))

    state = load_state().get("sources", {})
    misses = _load_misses()

    found: List[SourceVideo] = []
    for cand in pool:
        if len(found) >= limit:
            break
        if cand.video_id in misses:
            continue
        key = f"{external_channel_key(cand.channel_id)}::{cand.video_id}"
        used = (state.get(key) or {}).get("segments") or []
        src = build_source(cand, clip_cfg=clip_cfg, used_segments=used)
        if src:
            found.append(src)
    return found


def _rehydrate(d: Dict[str, Any]) -> acq.ExternalCandidate:
    """acquire() が返した dict を ExternalCandidate に戻す。"""
    return acq.ExternalCandidate(
        video_id=str(d.get("video_id") or ""),
        title=str(d.get("title") or ""),
        channel_id=str(d.get("channel_id") or ""),
        channel_title=str(d.get("channel_title") or ""),
        published_at=str(d.get("published_at") or ""),
        duration_sec=float(d.get("duration_sec") or 0.0),
        view_count=int(d.get("view_count") or 0),
        license=str(d.get("license") or ""),
        use_as=str(d.get("use_as") or acq.USE_THEME_ONLY),
        reason=str(d.get("reason") or ""),
        origin=str(d.get("origin") or ""),
        local_path=d.get("local_path"),
        tags=list(d.get("tags") or []),
        permission_phrase=str(d.get("permission_phrase") or ""),
        credit_name=str(d.get("credit_name") or ""),
    )
