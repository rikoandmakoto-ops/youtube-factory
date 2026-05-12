"""
CompetitorDiscovery (Phase F-1b) — 同ジャンルの競合チャンネルを YouTube Search API で
自動検出し、Claude で関連度をスコアリングして候補として提案する。

ユーザーが承認した候補だけが正式に `data/channels/{id}.json` の `competitors` に追加される
（自動追加はしない）。

公開関数:
  - discover(channel_id, *, max_candidates=15, max_videos_for_keywords=20)
  - approve_candidate(channel_id, candidate_id) → competitor_analyzer.add_competitor を呼ぶ
  - dismiss_candidate(channel_id, candidate_id)
  - discover_all_channels() ← scheduler から呼ぶ（月1）

設計方針:
  - YOUTUBE_API_KEY が無いと search/channels が叩けないので no-op を返す
  - 既に登録済み / dismiss 済みのチャンネルはスキップ
  - quota を消費しすぎないよう、抽出キーワード数と検索結果数を絞る
  - Claude 未設定でもルールベースで動くようにフォールバックを用意
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import store as analytics_store
from . import competitor_analyzer


YT_API_BASE = "https://www.googleapis.com/youtube/v3"

# 拾わない汎用ワード（チャンネル名に紛れ込みがちな日本語ストップワード）
_STOPWORDS = {
    "解説", "ゆっくり", "動画", "今日", "毎日", "おすすめ", "完全", "公式",
    "最強", "最新", "実況", "雑談", "簡単", "面白い", "話", "件", "選",
    "について", "とは", "なぜ", "どうして", "やってみた", "やってみる",
    "https", "youtube", "channel", "subscribe", "shorts", "公開",
    "the", "and", "for", "with", "this", "that", "from", "your",
}

# トークン抽出: 日本語の漢字/カタカナ連続 or ASCII 単語
_TOKEN_RE = re.compile(r"[一-龥々ぁ-んァ-ヴー]+|[A-Za-z][A-Za-z0-9]+")


# ---------------------------------------------------------------------
# Keyword extraction (from own channel's recent videos)
# ---------------------------------------------------------------------

def _extract_keywords(
    *,
    concept: str,
    own_titles: List[str],
    own_tags: List[str],
    own_seeds: List[str],
    top_n: int = 6,
) -> List[str]:
    """自チャンネルの concept / タイトル / タグ / シードから検索クエリを組み立てる。"""
    counter: Counter = Counter()

    # tags は強めに重み付け
    for tag in own_tags:
        for tok in _TOKEN_RE.findall(tag or ""):
            if len(tok) < 2:
                continue
            if tok.lower() in _STOPWORDS or tok in _STOPWORDS:
                continue
            counter[tok] += 3

    # seeds（テーマ候補）も重め
    for seed in own_seeds:
        for tok in _TOKEN_RE.findall(seed or ""):
            if len(tok) < 2:
                continue
            if tok.lower() in _STOPWORDS or tok in _STOPWORDS:
                continue
            counter[tok] += 2

    # titles
    for t in own_titles:
        for tok in _TOKEN_RE.findall(t or ""):
            if len(tok) < 2:
                continue
            if tok.lower() in _STOPWORDS or tok in _STOPWORDS:
                continue
            counter[tok] += 1

    # concept から拾うキーワード（重み低め）
    for tok in _TOKEN_RE.findall(concept or ""):
        if len(tok) < 2:
            continue
        if tok.lower() in _STOPWORDS or tok in _STOPWORDS:
            continue
        counter[tok] += 1

    ranked = [kw for kw, _ in counter.most_common(top_n * 2)]

    # 上位 N に絞る。最低 1 個は concept から拾う努力をする
    if not ranked and concept:
        ranked = [concept.strip()[:20]]

    return ranked[:top_n]


# ---------------------------------------------------------------------
# YouTube API helpers
# ---------------------------------------------------------------------

def _yt_get(path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return None
    p = dict(params)
    p["key"] = api_key
    url = f"{YT_API_BASE}/{path}?{urllib.parse.urlencode(p)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "youtube-factory/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"⚠️ YouTube API GET failed ({path}): {e}")
        return None


def _search_channels(query: str, *, max_results: int = 10) -> List[Dict[str, Any]]:
    """search.list?type=channel — チャンネルID + 簡易メタを返す。"""
    data = _yt_get(
        "search",
        {
            "part": "snippet",
            "type": "channel",
            "q": query,
            "maxResults": max(1, min(max_results, 25)),
            "regionCode": "JP",
            "relevanceLanguage": "ja",
        },
    )
    if not data:
        return []
    out: List[Dict[str, Any]] = []
    for it in data.get("items") or []:
        cid = (it.get("id") or {}).get("channelId")
        sn = it.get("snippet") or {}
        if not cid:
            continue
        out.append({
            "channel_id": cid,
            "title": sn.get("title"),
            "description": sn.get("description"),
            "thumbnail": ((sn.get("thumbnails") or {}).get("default") or {}).get("url"),
        })
    return out


def _fetch_channels_batch(channel_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """channels.list で一気に統計を取得（id は最大 50）。"""
    out: Dict[str, Dict[str, Any]] = {}
    if not channel_ids:
        return out
    for i in range(0, len(channel_ids), 50):
        chunk = channel_ids[i : i + 50]
        data = _yt_get(
            "channels",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)},
        )
        if not data:
            continue
        for it in data.get("items") or []:
            cid = it.get("id")
            if not cid:
                continue
            sn = it.get("snippet") or {}
            st = it.get("statistics") or {}
            cd = it.get("contentDetails") or {}
            uploads = ((cd.get("relatedPlaylists") or {}).get("uploads")) or None
            out[cid] = {
                "channel_id": cid,
                "title": sn.get("title"),
                "description": sn.get("description"),
                "thumbnail": (
                    (sn.get("thumbnails") or {}).get("default") or {}
                ).get("url"),
                "subscriber_count": (
                    int(st.get("subscriberCount") or 0)
                    if not st.get("hiddenSubscriberCount") else None
                ),
                "video_count": int(st.get("videoCount") or 0),
                "view_count": int(st.get("viewCount") or 0),
                "uploads_playlist": uploads,
            }
    return out


def _fetch_recent_videos(uploads_playlist: str, max_videos: int = 10) -> List[Dict[str, Any]]:
    """playlistItems + videos を最小限で叩いて、最近の動画タイトルと公開日を取る。"""
    vids: List[str] = []
    page_token: Optional[str] = None
    while len(vids) < max_videos:
        params: Dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": min(50, max_videos - len(vids)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = _yt_get("playlistItems", params)
        if not data:
            break
        for it in data.get("items") or []:
            vid = ((it.get("contentDetails") or {}).get("videoId")) or None
            if vid:
                vids.append(vid)
            if len(vids) >= max_videos:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    out: List[Dict[str, Any]] = []
    for i in range(0, len(vids), 50):
        chunk = vids[i : i + 50]
        data = _yt_get(
            "videos",
            {"part": "snippet", "id": ",".join(chunk), "maxResults": 50},
        )
        if not data:
            continue
        for it in data.get("items") or []:
            sn = it.get("snippet") or {}
            out.append({
                "video_id": it.get("id"),
                "title": sn.get("title"),
                "published_at": sn.get("publishedAt"),
            })
    return out


def _parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _posting_freq_per_week(videos: List[Dict[str, Any]]) -> Optional[float]:
    dates = [d for d in (_parse_iso_date(v.get("published_at")) for v in videos) if d]
    if len(dates) < 2:
        return None
    dates.sort()
    span_seconds = (dates[-1] - dates[0]).total_seconds() or 1.0
    span_weeks = max(span_seconds / (7 * 24 * 3600), 1 / 7)
    return round(len(dates) / span_weeks, 2)


# ---------------------------------------------------------------------
# Channel profile for context
# ---------------------------------------------------------------------

def _own_channel_context(channel_id: str) -> Tuple[str, str, List[str], List[str], List[str]]:
    """自チャンネルの (name, concept, titles, tags, seeds) を集める。"""
    try:
        from main import channel_manager  # type: ignore
    except Exception:
        channel_manager = None
    ch_profile = channel_manager.get(channel_id) if channel_manager else None

    name = channel_id
    concept = ""
    own_titles: List[str] = []
    own_tags: List[str] = []
    own_seeds: List[str] = []

    if ch_profile is not None:
        name = getattr(ch_profile, "name", channel_id)
        concept = getattr(ch_profile, "concept", "") or ""
        for s in getattr(ch_profile, "theme_seeds", []) or []:
            if isinstance(s, dict):
                t = s.get("title") or s.get("keyword") or s.get("angle")
                if t:
                    own_seeds.append(str(t))
            elif isinstance(s, str):
                own_seeds.append(s)
        # video_format に default_tags があれば拾う
        vf = getattr(ch_profile, "video_format", None)
        if vf is not None:
            yt = getattr(vf, "youtube", None)
            if yt is not None:
                for tag in getattr(yt, "default_tags", []) or []:
                    if tag:
                        own_tags.append(str(tag))

    # 直近の analytics から自チャンネル動画タイトルも拾えるが、最小実装では seeds + tags で十分
    return name, concept, own_titles, own_tags, own_seeds


# ---------------------------------------------------------------------
# Claude relevance scoring
# ---------------------------------------------------------------------

def _score_with_claude(
    *,
    own_name: str,
    own_concept: str,
    own_seeds: List[str],
    candidates: List[Dict[str, Any]],
    channel_id: str,
) -> Optional[List[Dict[str, Any]]]:
    """Claude に候補一覧を渡して、それぞれ relevance_score (0..1) と rationale を返してもらう。"""
    if not candidates:
        return []
    try:
        from pipeline import claude_client
    except Exception:
        return None
    if not claude_client.has_api_key():
        return None

    cand_lines: List[str] = []
    for i, c in enumerate(candidates):
        sample = c.get("sample_titles") or []
        desc = (c.get("description") or "").replace("\n", " ")[:180]
        cand_lines.append(
            f"[{i}] id={c.get('channel_id')} | title={c.get('title')} | "
            f"subs={c.get('subscriber_count')} | videos={c.get('video_count')} | "
            f"desc={desc} | recent_titles={sample[:5]}"
        )

    user = (
        f"自チャンネル: {own_name}\n"
        f"コンセプト: {own_concept}\n"
        f"代表的なテーマ: {('、'.join(own_seeds[:8])) or '（未設定）'}\n\n"
        f"以下は自動検出した競合候補チャンネルです。"
        f"自チャンネルのテーマと「どれくらい近いか」を 0.0〜1.0 の数値でスコアしてください。\n"
        f"- 1.0 = 同ジャンル・同ターゲット視聴者で完全に競合\n"
        f"- 0.7 = テーマがかなり近い\n"
        f"- 0.4 = 一部のテーマが重なる\n"
        f"- 0.0 = 無関係\n\n"
        f"候補:\n" + "\n".join(cand_lines) + "\n\n"
        f"以下の JSON 形式で返してください:\n"
        f"{{\n"
        f"  \"scores\": [\n"
        f"    {{\"index\": 0, \"score\": 0.0〜1.0, \"rationale\": \"<短い日本語>\"}},\n"
        f"    ...\n"
        f"  ]\n"
        f"}}\n"
        f"全候補に対して順番通り回答してください。"
    )

    res = claude_client.call_claude_json(
        system=(
            "あなたは YouTube チャンネル分析の専門家。"
            "競合チャンネル候補を自チャンネルとの近さでスコアリングする。"
        ),
        user=user,
        temperature=0.2,
        max_tokens=1500,
        channel_id=channel_id,
        purpose="competitor_discovery_score",
    )
    if not isinstance(res, dict):
        return None
    scores = res.get("scores")
    if not isinstance(scores, list):
        return None
    out: List[Dict[str, Any]] = []
    for entry in scores:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
            continue
        try:
            score = float(entry.get("score") or 0)
        except Exception:
            score = 0.0
        score = max(0.0, min(1.0, score))
        out.append({
            "index": idx,
            "score": score,
            "rationale": (entry.get("rationale") or "").strip()[:300],
        })
    return out


def _heuristic_score(
    *,
    own_concept: str,
    own_seeds: List[str],
    cand: Dict[str, Any],
) -> Tuple[float, str]:
    """Claude が無いときの簡易スコア — concept/seeds の語が候補側にどれだけ出るか。"""
    needles = set()
    for src in [own_concept] + own_seeds:
        for tok in _TOKEN_RE.findall(src or ""):
            if len(tok) >= 2 and tok not in _STOPWORDS:
                needles.add(tok)
    haystack = " ".join(
        [cand.get("title") or "", cand.get("description") or ""]
        + (cand.get("sample_titles") or [])
    )
    if not needles:
        return 0.0, "needles なし"
    hits = sum(1 for n in needles if n in haystack)
    score = min(1.0, hits / max(len(needles), 1) * 1.5)
    return round(score, 2), f"{hits}/{len(needles)} のキーワードが一致"


# ---------------------------------------------------------------------
# Public: discover
# ---------------------------------------------------------------------

def discover(
    channel_id: str,
    *,
    max_candidates: int = 15,
    max_videos_for_keywords: int = 0,  # 未使用（将来拡張用）
    min_subscribers: int = 1000,
    relevance_threshold: float = 0.3,
) -> Dict[str, Any]:
    """新規競合候補を YouTube Search API から発掘して DB に保存。

    Returns: {"ok": True, "candidates": [...], "matched_keywords": [...]}.
    """
    started_at = int(time.time())
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "channel_id": channel_id,
            "error": "YOUTUBE_API_KEY not set",
            "started_at": started_at,
        }

    name, concept, own_titles, own_tags, own_seeds = _own_channel_context(channel_id)

    # キーワード抽出
    keywords = _extract_keywords(
        concept=concept,
        own_titles=own_titles,
        own_tags=own_tags,
        own_seeds=own_seeds,
        top_n=6,
    )
    # コンセプト自体もクエリにする（短く区切る）
    if concept and concept not in keywords:
        keywords = [concept[:30]] + keywords

    if not keywords:
        return {
            "ok": False,
            "channel_id": channel_id,
            "error": "no keywords could be extracted (set channel concept or theme_seeds)",
            "started_at": started_at,
        }

    existing_competitors = set(competitor_analyzer.list_competitors(channel_id))
    dismissed = {
        c["competitor_id"]
        for c in analytics_store.list_competitor_candidates(channel_id, status="dismissed", limit=500)
    }
    approved = {
        c["competitor_id"]
        for c in analytics_store.list_competitor_candidates(channel_id, status="approved", limit=500)
    }
    skip_set = existing_competitors | dismissed | approved

    # 自チャンネルの YouTube ID もスキップ
    try:
        from main import channel_manager  # type: ignore
    except Exception:
        channel_manager = None
    own_yt_id: Optional[str] = None
    if channel_manager is not None:
        ch_profile = channel_manager.get(channel_id)
        if ch_profile is not None:
            own_yt_id = getattr(ch_profile, "youtube_channel_id", None)
    if own_yt_id:
        skip_set.add(own_yt_id)

    # キーワードごとに検索 → 統合
    seen: Dict[str, Dict[str, Any]] = {}
    matched_by_keyword: Dict[str, List[str]] = {}
    per_kw = max(3, max_candidates // max(len(keywords), 1) + 2)
    for kw in keywords:
        hits = _search_channels(kw, max_results=min(per_kw, 10))
        for h in hits:
            cid = h["channel_id"]
            if cid in skip_set:
                continue
            seen.setdefault(cid, h)
            matched_by_keyword.setdefault(cid, []).append(kw)
        # quota 保護
        time.sleep(0.15)

    if not seen:
        return {
            "ok": True,
            "channel_id": channel_id,
            "started_at": started_at,
            "matched_keywords": keywords,
            "candidates": [],
            "note": "search hits 0",
        }

    # 統計を一括取得
    ids = list(seen.keys())[: max_candidates * 3]
    meta = _fetch_channels_batch(ids)

    enriched: List[Dict[str, Any]] = []
    for cid, base in seen.items():
        if cid not in meta:
            continue
        m = meta[cid]
        subs = m.get("subscriber_count")
        if subs is not None and subs < min_subscribers:
            continue
        sample_titles: List[str] = []
        freq: Optional[float] = None
        if m.get("uploads_playlist"):
            vids = _fetch_recent_videos(m["uploads_playlist"], max_videos=10)
            sample_titles = [v.get("title") for v in vids if v.get("title")][:8]
            freq = _posting_freq_per_week(vids)
            time.sleep(0.1)
        enriched.append({
            "channel_id": cid,
            "title": m.get("title") or base.get("title"),
            "description": m.get("description") or base.get("description"),
            "thumbnail": m.get("thumbnail") or base.get("thumbnail"),
            "subscriber_count": subs,
            "video_count": m.get("video_count"),
            "view_count": m.get("view_count"),
            "posting_frequency_per_week": freq,
            "sample_titles": sample_titles,
            "matched_keywords": matched_by_keyword.get(cid, []),
        })
        if len(enriched) >= max_candidates * 2:
            break

    if not enriched:
        return {
            "ok": True,
            "channel_id": channel_id,
            "started_at": started_at,
            "matched_keywords": keywords,
            "candidates": [],
            "note": "no candidates met min_subscribers",
        }

    # Claude でスコアリング
    claude_scores = _score_with_claude(
        own_name=name,
        own_concept=concept,
        own_seeds=own_seeds,
        candidates=enriched,
        channel_id=channel_id,
    )
    if claude_scores:
        # index → (score, rationale) のマップ
        score_map: Dict[int, Tuple[float, str]] = {
            s["index"]: (s["score"], s["rationale"]) for s in claude_scores
        }
        for i, c in enumerate(enriched):
            score, rationale = score_map.get(i, (0.0, ""))
            c["relevance_score"] = score
            c["rationale"] = rationale or f"検索キーワード: {', '.join(c.get('matched_keywords', []))}"
    else:
        for c in enriched:
            score, rationale = _heuristic_score(
                own_concept=concept, own_seeds=own_seeds, cand=c
            )
            c["relevance_score"] = score
            c["rationale"] = rationale + f" / 検索キーワード: {', '.join(c.get('matched_keywords', []))}"

    # threshold 以上のものだけ採用
    enriched = [c for c in enriched if c["relevance_score"] >= relevance_threshold]
    enriched.sort(key=lambda c: c["relevance_score"], reverse=True)
    enriched = enriched[:max_candidates]

    # DB へ upsert
    saved: List[Dict[str, Any]] = []
    for c in enriched:
        cand_id = analytics_store.upsert_competitor_candidate(
            channel_id=channel_id,
            competitor_id=c["channel_id"],
            competitor_title=c.get("title"),
            competitor_description=(c.get("description") or "")[:600],
            thumbnail_url=c.get("thumbnail"),
            subscriber_count=c.get("subscriber_count"),
            video_count=c.get("video_count"),
            view_count=c.get("view_count"),
            posting_frequency_per_week=c.get("posting_frequency_per_week"),
            relevance_score=c["relevance_score"],
            rationale=c.get("rationale"),
            matched_keywords=c.get("matched_keywords"),
            sample_titles=c.get("sample_titles"),
        )
        saved.append({"candidate_id": cand_id, **c})

    return {
        "ok": True,
        "channel_id": channel_id,
        "started_at": started_at,
        "finished_at": int(time.time()),
        "matched_keywords": keywords,
        "candidates": saved,
        "count": len(saved),
    }


def list_candidates(channel_id: str, *, status: Optional[str] = "pending", limit: int = 50) -> List[Dict[str, Any]]:
    return analytics_store.list_competitor_candidates(channel_id, status=status, limit=limit)


def approve_candidate(channel_id: str, candidate_id: str) -> Dict[str, Any]:
    cand = analytics_store.get_competitor_candidate(channel_id, candidate_id)
    if not cand:
        return {"ok": False, "error": "candidate not found"}
    if cand.get("status") != "pending":
        return {"ok": False, "error": f"already {cand.get('status')}"}
    competitor_id = cand.get("competitor_id")
    if not competitor_id:
        return {"ok": False, "error": "competitor_id missing"}
    add_res = competitor_analyzer.add_competitor(channel_id, competitor_id)
    if not add_res.get("ok"):
        return {"ok": False, "error": add_res.get("error") or "add failed"}
    analytics_store.update_candidate_status(channel_id, candidate_id, "approved")
    return {
        "ok": True,
        "candidate_id": candidate_id,
        "competitor_id": competitor_id,
        "note": add_res.get("note"),
    }


def dismiss_candidate(channel_id: str, candidate_id: str) -> Dict[str, Any]:
    cand = analytics_store.get_competitor_candidate(channel_id, candidate_id)
    if not cand:
        return {"ok": False, "error": "candidate not found"}
    if cand.get("status") == "dismissed":
        return {"ok": True, "note": "already dismissed"}
    analytics_store.update_candidate_status(channel_id, candidate_id, "dismissed")
    return {"ok": True, "candidate_id": candidate_id}


# ---------------------------------------------------------------------
# Scheduler entry
# ---------------------------------------------------------------------

def discover_all_channels() -> Dict[str, Any]:
    """全チャンネル × discover() を回す（月1スキャン用）。"""
    try:
        from main import channel_manager  # type: ignore
    except Exception:
        return {"ok": False, "error": "channel_manager not available"}
    if channel_manager is None:
        return {"ok": False, "error": "channel_manager not available"}

    results: List[Dict[str, Any]] = []
    try:
        channels = channel_manager.list_channels()
    except Exception as e:
        return {"ok": False, "error": f"list channels failed: {e}"}

    for ch in channels:
        cid = getattr(ch, "id", None)
        if not cid:
            continue
        try:
            r = discover(cid)
            results.append({
                "channel_id": cid,
                "count": r.get("count"),
                "ok": r.get("ok"),
                "error": r.get("error"),
            })
        except Exception as e:
            results.append({"channel_id": cid, "ok": False, "error": str(e)})
    return {"ok": True, "ran_at": int(time.time()), "results": results}
