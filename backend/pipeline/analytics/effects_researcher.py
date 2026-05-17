"""
EffectsResearcher — 競合動画の画面演出を学習し、チャンネル JSON の effects
セクションに反映するための提案を返す機能。

フロー:
  1. チャンネル JSON から「ジャンル」を推定（明示 effects_research.queries / genre が
     あれば優先、無ければ concept や theme_seeds からヒューリスティック）。
  2. 検索クエリ群で YouTube Data API を叩き、再生数 / 日本語 / Shorts 除外 /
     ブラックリストでフィルタ。
  3. チャンネルごとに TOP N 動画を選び、competitor_video_analyzer.analyze_one_video で
     サムネ + ランダムフレーム + 字幕を分析（Claude Vision / Claude content）。
  4. 全チャンネルの結果を Claude に投げて「画面演出パターン」を集約。
  5. 集約結果から `effects` セクションの推奨設定を導出（preset / 各種 allow_*）。

公開 API:
  - resolve_research_spec(channel_id) -> ResearchSpec
  - run_effects_research(channel_id, *, target_channels=7, videos_per_channel=2,
                        save=True) -> dict
  - latest_research(channel_id) -> Optional[dict]
  - suggest_effects_from_patterns(aggregated_patterns) -> dict
  - apply_effects_to_channel(channel_id, effects_dict) -> dict
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import competitor_video_analyzer as cva
from . import store as analytics_store


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"


# ---------------------------------------------------------------------
# Research spec — どんなクエリで何を集めるか
# ---------------------------------------------------------------------

@dataclass
class ResearchSpec:
    channel_id: str
    queries: List[str] = field(default_factory=list)
    must_include_token: Optional[str] = None        # 例: SCP / ゆっくり
    blacklist_words: List[str] = field(default_factory=list)
    target_channels: int = 7
    videos_per_channel: int = 2
    max_videos_per_query: int = 15
    shorts_threshold_sec: int = 90
    require_japanese: bool = True
    genre: str = "general"                           # scp / science / horror / general


# 既知ジャンルのデフォルトクエリ（ユーザー指定が無いときのフォールバック）
_GENRE_PRESETS: Dict[str, Dict[str, Any]] = {
    "scp": {
        "queries": [
            "SCP 解説 ゆっくり", "SCP解説 ゆっくり", "ゆっくりSCP紹介",
            "SCP-", "SCP 財団 解説",
        ],
        "must_include_token": "SCP",
        "blacklist_words": ["マイクラ", "ROBLOX", "ロブロックス", "GMOD",
                            "アンパンマン", "Minecraft", "フォートナイト"],
    },
    "science": {
        "queries": [
            "科学 ゆっくり 解説", "雑学 ゆっくり", "ゆっくり 科学解説",
            "豆知識 ゆっくり 解説", "日常 科学 ゆっくり",
        ],
        "must_include_token": "ゆっくり",
        "blacklist_words": ["マイクラ", "ROBLOX", "GMOD", "Minecraft",
                            "SCP", "フォートナイト", "ホラー"],
    },
    "horror": {
        "queries": [
            "怖い話 ゆっくり 朗読", "都市伝説 ゆっくり 解説",
            "怪談 ゆっくり", "ホラー ゆっくり 解説",
        ],
        "must_include_token": "ゆっくり",
        "blacklist_words": ["マイクラ", "ROBLOX", "GMOD", "Minecraft"],
    },
    "general": {
        "queries": [
            "ゆっくり 解説", "ゆっくり実況",
        ],
        "must_include_token": "ゆっくり",
        "blacklist_words": [],
    },
}


# ---------------------------------------------------------------------
# Channel JSON helpers
# ---------------------------------------------------------------------

def _load_channel_json(channel_id: str) -> Optional[Dict[str, Any]]:
    p = CHANNELS_DIR / f"{channel_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ channel JSON read failed ({channel_id}): {e}")
        return None


def _write_channel_json(channel_id: str, data: Dict[str, Any]) -> bool:
    p = CHANNELS_DIR / f"{channel_id}.json"
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"⚠️ channel JSON write failed ({channel_id}): {e}")
        return False


def _detect_genre(channel: Dict[str, Any]) -> str:
    """concept / id / theme_seeds から雑にジャンル推定。"""
    text = " ".join([
        str(channel.get("id", "")),
        str(channel.get("name", "")),
        str(channel.get("concept", "")),
    ])
    for seed in channel.get("theme_seeds") or []:
        text += " " + str(seed.get("title", "")) + " " + str(seed.get("angle", ""))
    t = text.lower()
    if "scp" in t:
        return "scp"
    if any(w in t for w in ("怖", "ホラー", "都市伝説", "怪談")):
        return "horror"
    if any(w in t for w in ("科学", "雑学", "豆知識", "日常", "解剖", "化学", "物理")):
        return "science"
    return "general"


def resolve_research_spec(channel_id: str) -> ResearchSpec:
    """チャンネル JSON から ResearchSpec を構築。明示設定 > ジャンル既定。"""
    data = _load_channel_json(channel_id) or {}
    er = data.get("effects_research") or {}
    genre = (er.get("genre") or _detect_genre(data) or "general").lower()
    preset = _GENRE_PRESETS.get(genre, _GENRE_PRESETS["general"])
    queries = er.get("queries") or preset["queries"]
    token = er.get("must_include_token") or preset.get("must_include_token")
    blacklist = er.get("blacklist_words") or preset.get("blacklist_words") or []
    return ResearchSpec(
        channel_id=channel_id,
        queries=list(queries),
        must_include_token=token,
        blacklist_words=list(blacklist),
        target_channels=int(er.get("target_channels") or 7),
        videos_per_channel=int(er.get("videos_per_channel") or 2),
        max_videos_per_query=int(er.get("max_videos_per_query") or 15),
        shorts_threshold_sec=int(er.get("shorts_threshold_sec") or 90),
        require_japanese=bool(er.get("require_japanese", True)),
        genre=genre,
    )


# ---------------------------------------------------------------------
# YouTube search
# ---------------------------------------------------------------------

def _yt_client():
    from googleapiclient.discovery import build  # type: ignore

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY missing — set in backend/.env")
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


_ISO_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _iso_duration_to_seconds(dur: str) -> int:
    m = _ISO_DUR_RE.match(dur or "")
    if not m:
        return 0
    h, mn, s = m.groups()
    return int(h or 0) * 3600 + int(mn or 0) * 60 + int(s or 0)


def _has_japanese(s: str) -> bool:
    for ch in s:
        if "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿":
            return True
    return False


def _search_videos(spec: ResearchSpec) -> List[Dict[str, Any]]:
    yt = _yt_client()
    seen: Dict[str, Dict[str, Any]] = {}
    for q in spec.queries:
        try:
            resp = (
                yt.search()
                .list(
                    q=q, type="video", part="snippet",
                    maxResults=spec.max_videos_per_query,
                    regionCode="JP",
                    relevanceLanguage="ja",
                    order="viewCount",
                    videoDuration="medium",
                )
                .execute()
            )
        except Exception as e:
            print(f"⚠️ search failed for '{q}': {e}")
            continue
        for item in resp.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            sn = item.get("snippet") or {}
            if not vid or vid in seen:
                continue
            seen[vid] = {
                "video_id": vid,
                "title": sn.get("title", ""),
                "channel_id": sn.get("channelId", ""),
                "channel_title": sn.get("channelTitle", ""),
                "published_at": sn.get("publishedAt", ""),
            }
        time.sleep(0.2)
    return list(seen.values())


def _enrich_with_stats(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    yt = _yt_client()
    out: List[Dict[str, Any]] = []
    by_id = {v["video_id"]: v for v in videos}
    ids = list(by_id.keys())
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        try:
            resp = (
                yt.videos()
                .list(part="contentDetails,statistics", id=",".join(chunk))
                .execute()
            )
        except Exception as e:
            print(f"⚠️ videos.list failed: {e}")
            continue
        for item in resp.get("items", []):
            base = by_id.get(item["id"])
            if not base:
                continue
            cd = item.get("contentDetails") or {}
            st = item.get("statistics") or {}
            base["duration_seconds"] = _iso_duration_to_seconds(cd.get("duration", ""))
            base["views"] = int(st.get("viewCount") or 0)
            base["likes"] = int(st.get("likeCount") or 0)
            out.append(base)
    return out


def _select_per_channel(
    videos: List[Dict[str, Any]], spec: ResearchSpec
) -> List[Tuple[str, str, List[Dict[str, Any]]]]:
    def _ok(v: Dict[str, Any]) -> bool:
        title = v.get("title") or ""
        ch = v.get("channel_title") or ""
        if v.get("duration_seconds", 0) < spec.shorts_threshold_sec:
            return False
        if spec.blacklist_words:
            blob = title.lower()
            if any(b.lower() in blob for b in spec.blacklist_words):
                return False
        if spec.must_include_token:
            if spec.must_include_token.lower() not in (title + " " + ch).lower():
                return False
        if spec.require_japanese:
            if not (_has_japanese(title) or _has_japanese(ch)):
                return False
        return True

    videos = [v for v in videos if _ok(v)]
    by_channel: Dict[str, List[Dict[str, Any]]] = {}
    titles: Dict[str, str] = {}
    for v in videos:
        cid = v.get("channel_id")
        if not cid:
            continue
        by_channel.setdefault(cid, []).append(v)
        titles[cid] = v.get("channel_title") or titles.get(cid, "")
    ranked = sorted(
        by_channel.items(),
        key=lambda kv: sum(int(x.get("views") or 0) for x in kv[1]),
        reverse=True,
    )
    out: List[Tuple[str, str, List[Dict[str, Any]]]] = []
    for cid, vs in ranked[: spec.target_channels]:
        vs_sorted = sorted(vs, key=lambda x: int(x.get("views") or 0), reverse=True)
        out.append((cid, titles.get(cid, cid), vs_sorted[: spec.videos_per_channel]))
    return out


# ---------------------------------------------------------------------
# Per-video analysis (delegates to competitor_video_analyzer)
# ---------------------------------------------------------------------

def _analyze_videos(
    selection: List[Tuple[str, str, List[Dict[str, Any]]]],
    *,
    research_channel_id: str,
    progress: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    total = sum(len(vs) for _, _, vs in selection)
    done = 0
    for cid, ctitle, videos in selection:
        for v in videos:
            done += 1
            if progress is not None:
                try:
                    progress(done, total, f"{ctitle}: {v['title'][:40]}")
                except Exception:
                    pass
            try:
                r = cva.analyze_one_video(
                    research_channel_id, cid,
                    {
                        "video_id": v["video_id"],
                        "title": v["title"],
                        "views": v.get("views"),
                        "published_at": v.get("published_at"),
                        "duration": v.get("duration_seconds"),
                    },
                    competitor_title=ctitle,
                    frame_count=3,
                )
            except Exception as e:
                r = {"ok": False, "error": str(e), "video_id": v["video_id"]}
            r["channel_title"] = ctitle
            r["channel_id"] = cid
            r["views"] = v.get("views")
            r["title"] = v["title"]
            results.append(r)
    return results


# ---------------------------------------------------------------------
# Aggregation via Claude
# ---------------------------------------------------------------------

def _aggregate_patterns(
    results: List[Dict[str, Any]], *, channel_id: str, genre: str
) -> Optional[Dict[str, Any]]:
    try:
        from pipeline import claude_client  # type: ignore
    except Exception:
        return None
    pieces: List[str] = []
    for r in results:
        if not r.get("ok"):
            continue
        v = r.get("visual_insights") or {}
        c = r.get("content_insights") or {}
        if not v and not c:
            continue
        pieces.append(json.dumps({
            "channel": r.get("channel_title"),
            "title": r.get("title"),
            "views": r.get("views"),
            "visual": v,
            "content": c,
        }, ensure_ascii=False))
    if not pieces:
        return None
    joined = "\n\n".join(pieces)[:18000]
    user = (
        f"以下は『{genre}』ジャンルの YouTube 解説系チャンネル人気動画の分析結果 JSON 配列。\n"
        "各エントリにはサムネ+本編 3 フレームの視覚分析と、字幕の内容分析が入っています。\n\n"
        f"--- 個別分析 ---\n{joined}\n--- ここまで ---\n\n"
        "これらを横断的に俯瞰し、自チャンネルが取り入れるべき「画面演出パターン」を抽出してください。\n"
        "以下 JSON のみを返してください:\n"
        "{\n"
        "  \"pixel_art\": {\"used\":\"high|medium|low|none\",\"how\":\"\",\"examples\":[]},\n"
        "  \"background_motion\": {\"techniques\":[],\"frequency\":\"\",\"notes\":\"\"},\n"
        "  \"image_appearance\": {\"entrance\":[],\"exit\":[],\"emphasis\":[]},\n"
        "  \"text_effects\": {\"styles\":[],\"animation\":[],\"role\":\"\"},\n"
        "  \"scene_transition\": {\"types\":[],\"pacing\":\"\"},\n"
        "  \"character_motion\": {\"idle\":\"\",\"talking\":\"\",\"reaction\":\"\"},\n"
        "  \"horror_specific\": {\"screen_shake\":\"\",\"color_grading\":\"\",\"glitch_noise\":\"\",\"sound_design_hints\":\"\"},\n"
        "  \"common_patterns\": [],\n"
        "  \"differentiators\": [],\n"
        "  \"recommendations\": [\"自チャンネルに取り入れるべき具体演出（実装難度低めから順に）\"]\n"
        "}\n"
        "JSON のみを返してください。"
    )
    return claude_client.call_claude_json(
        system=(
            "あなたは YouTube 解説動画の演出ディレクター。"
            "複数チャンネルの分析データを俯瞰して、再現可能な演出パターンを抽出する。"
        ),
        user=user,
        temperature=0.4,
        max_tokens=3500,
        channel_id=channel_id,
        purpose=f"effects_meta_{genre}",
    )


# ---------------------------------------------------------------------
# Pattern → effects config suggestion
# ---------------------------------------------------------------------

def suggest_effects_from_patterns(
    aggregated_patterns: Optional[Dict[str, Any]], *, genre: str = "general",
) -> Dict[str, Any]:
    """集約パターンから effects セクションを提案。

    実装方針:
      - ジャンルから base preset を決める (scp/horror → "horror", science → "minimal",
        その他 → "balanced")。
      - パターン中の語彙からブースト指示 (allow_* を強制 True/False, ratio 引き上げ等)。
    """
    base_preset = {
        "scp": "horror",
        "horror": "horror",
        "science": "science",   # video_effects.py の science プリセットを使う
        "general": "balanced",
    }.get(genre, "balanced")
    suggestion: Dict[str, Any] = {
        "enabled": True,
        "preset": base_preset,
    }
    if not aggregated_patterns:
        return suggestion

    horror = aggregated_patterns.get("horror_specific") or {}
    bg = aggregated_patterns.get("background_motion") or {}
    img = aggregated_patterns.get("image_appearance") or {}
    text = aggregated_patterns.get("text_effects") or {}
    trans = aggregated_patterns.get("scene_transition") or {}

    def _joined_str(*parts) -> str:
        out: List[str] = []
        for p in parts:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, (list, tuple)):
                out.extend(str(x) for x in p)
            elif isinstance(p, dict):
                out.extend(str(v) for v in p.values())
        return " ".join(out).lower()

    horror_str = _joined_str(horror.get("screen_shake"), horror.get("color_grading"),
                              horror.get("glitch_noise"), horror.get("sound_design_hints"))
    bg_str = _joined_str(bg.get("techniques"), bg.get("notes"), bg.get("frequency"))
    img_str = _joined_str(img.get("entrance"), img.get("exit"), img.get("emphasis"))
    text_str = _joined_str(text.get("animation"), text.get("styles"), text.get("role"))
    trans_str = _joined_str(trans.get("types"), trans.get("pacing"))

    # Boost rules
    suggestion["allow_shake"] = bool(
        re.search(r"揺|振|shake|ぶる", horror_str + bg_str)
    ) or genre in ("scp", "horror")
    suggestion["allow_flash"] = bool(
        re.search(r"フラッシュ|閃光|flash|赤|白|爆", horror_str + bg_str)
    ) or genre in ("scp", "horror")
    suggestion["allow_glitch"] = bool(
        re.search(r"グリッチ|ノイズ|RGB|glitch|乱れ", horror_str)
    ) or genre in ("scp", "horror")
    suggestion["allow_pixelate"] = bool(
        re.search(r"ピクセル|モザイク|pixel", horror_str + bg_str + img_str)
    )
    suggestion["allow_zoom"] = bool(
        re.search(r"ズーム|寄|zoom|pan|パン|ken", bg_str + img_str)
    ) or True  # ズームはほぼ常時 OK
    suggestion["allow_tint"] = bool(
        re.search(r"色|tint|赤|青|フィルタ|grading|彩度", horror_str + bg_str)
    ) or genre in ("scp", "horror")
    suggestion["allow_transitions"] = bool(
        re.search(r"カット|トランジション|フェード|スワイプ|cut|fade", trans_str)
    ) or True

    # Intensity tuning
    if genre in ("scp", "horror"):
        suggestion["max_effects_per_scene"] = 3
        suggestion["shake_max_px"] = 22
        suggestion["zoom_max"] = 0.09
        suggestion["transition_duration"] = 0.45
    elif genre == "science":
        suggestion["max_effects_per_scene"] = 1
        suggestion["shake_max_px"] = 6
        suggestion["zoom_max"] = 0.04
        suggestion["transition_duration"] = 0.25
    else:
        suggestion["max_effects_per_scene"] = 2
        suggestion["shake_max_px"] = 14
        suggestion["zoom_max"] = 0.06
        suggestion["transition_duration"] = 0.35

    suggestion["fade_in_first"] = True
    suggestion["fade_out_last"] = True
    return suggestion


def apply_effects_to_channel(
    channel_id: str, effects_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """effects_dict を data/channels/<id>.json の video_format.effects に書き込む。"""
    data = _load_channel_json(channel_id)
    if data is None:
        return {"ok": False, "error": f"channel '{channel_id}' not found"}
    vf = data.setdefault("video_format", {})
    vf["effects"] = effects_dict
    ok = _write_channel_json(channel_id, data)
    return {"ok": ok, "channel_id": channel_id, "effects": effects_dict}


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------

def run_effects_research(
    channel_id: str,
    *,
    save: bool = True,
    auto_apply: bool = False,
    progress: Optional[Any] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """1 チャンネル分のリサーチを実行して結果を返す。

    save=True なら analytics_store の effects_research テーブルに保存。
    auto_apply=True なら導出された effects 設定を channel JSON にも書き込む。
    overrides={"target_channels": ..., "videos_per_channel": ...} で上書き可能。
    """
    spec = resolve_research_spec(channel_id)
    if overrides:
        for k in ("target_channels", "videos_per_channel",
                  "max_videos_per_query", "queries", "must_include_token",
                  "blacklist_words", "require_japanese"):
            if k in overrides and overrides[k] is not None:
                setattr(spec, k, overrides[k])

    started = int(time.time())
    print(f"🔬 effects_research: {channel_id} (genre={spec.genre})")
    raw = _search_videos(spec)
    enriched = _enrich_with_stats(raw)
    selection = _select_per_channel(enriched, spec)
    selected_meta = [
        {
            "channel_id": cid,
            "channel_title": ctitle,
            "video_ids": [v["video_id"] for v in vs],
            "videos": [
                {"video_id": v["video_id"], "title": v["title"],
                 "views": v.get("views")} for v in vs
            ],
        }
        for cid, ctitle, vs in selection
    ]
    if not selection:
        result = {
            "ok": False,
            "channel_id": channel_id,
            "genre": spec.genre,
            "error": "no SCP-relevant videos passed the filter",
            "started_at": started,
            "finished_at": int(time.time()),
            "queries": spec.queries,
            "channels_analyzed": [],
            "per_video_results": [],
            "aggregated_patterns": None,
            "suggested_effects": suggest_effects_from_patterns(None, genre=spec.genre),
            "applied": False,
        }
        if save:
            try:
                rec_id = analytics_store.upsert_effects_research(
                    channel_id=channel_id,
                    genre=spec.genre,
                    queries=spec.queries,
                    channels_analyzed=[],
                    per_video_results=[],
                    aggregated_patterns=None,
                    suggested_effects=result["suggested_effects"],
                    started_at=started,
                    finished_at=result["finished_at"],
                    error=result["error"],
                )
                result["record_id"] = rec_id
            except Exception as e:
                result["save_error"] = str(e)
        return result

    per_video = _analyze_videos(
        selection, research_channel_id=f"effects-research-{channel_id}",
        progress=progress,
    )
    aggregated = _aggregate_patterns(per_video, channel_id=channel_id, genre=spec.genre)
    suggested = suggest_effects_from_patterns(aggregated, genre=spec.genre)

    applied_status = False
    if auto_apply:
        ar = apply_effects_to_channel(channel_id, suggested)
        applied_status = bool(ar.get("ok"))

    finished = int(time.time())
    result = {
        "ok": True,
        "channel_id": channel_id,
        "genre": spec.genre,
        "started_at": started,
        "finished_at": finished,
        "elapsed_seconds": finished - started,
        "queries": spec.queries,
        "channels_analyzed": selected_meta,
        "per_video_results": per_video,
        "aggregated_patterns": aggregated,
        "suggested_effects": suggested,
        "applied": applied_status,
    }
    if save:
        try:
            rec_id = analytics_store.upsert_effects_research(
                channel_id=channel_id,
                genre=spec.genre,
                queries=spec.queries,
                channels_analyzed=selected_meta,
                per_video_results=per_video,
                aggregated_patterns=aggregated,
                suggested_effects=suggested,
                started_at=started,
                finished_at=finished,
                error=None,
            )
            result["record_id"] = rec_id
        except Exception as e:
            result["save_error"] = str(e)
    return result


def latest_research(channel_id: str) -> Optional[Dict[str, Any]]:
    try:
        return analytics_store.get_latest_effects_research(channel_id)
    except Exception as e:
        print(f"⚠️ latest_research read failed: {e}")
        return None
