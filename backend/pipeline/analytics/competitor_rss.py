"""競合チャンネル RSS 監視 — 同ジャンル人気チャンネルの新着を API クォータ0で追う。

なぜ RSS か:
    既存の competitor_analyzer は YouTube Data API（search/videos）を叩くので
    クォータを食い、週1回しか回せない。YouTube はチャンネルごとに公開 RSS
    (`/feeds/videos.xml?channel_id=UC...`) を出していて、これは API キーもクォータも
    不要。数時間おきに回せるので「競合が何を出したか」をほぼリアルタイムで拾える。

RSS で取れるもの / 取れないもの:
    取れる: video_id / タイトル / 公開日時 / チャンネル名（直近15件）
    取れない: 再生数・登録者数（media:community は返らないことが多く、
              返っても遅延が大きいので当てにしない）
    → 「何を出したか」の速報として使い、数字が要る分析は既存の
      competitor_analyzer（週次）に任せる、という役割分担。

出力:
    - `competitor_rss_videos` テーブル（新着のみ INSERT）
    - スキャン結果に頻出キーワードを添える（複数の競合が同時に触れた語＝旬）

競合の定義:
    チャンネル JSON の `competitors`（competitor_analyzer と同じソース）に加えて、
    competitor_discovery が承認済みにした候補も対象にする。

公開関数:
    scan_channel(channel_id, *, since_hours=72)
    scan_all_channels()
    recent(channel_id, *, hours=72, limit=100)
    hot_keywords(videos, *, limit=10)
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from calendar import timegm
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree

from . import store as analytics_store

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
USER_AGENT = "youtube-factory/1.0 (+competitor-rss)"
TIMEOUT_SECONDS = 12
MAX_COMPETITORS_PER_SCAN = 30
DEFAULT_SINCE_HOURS = 72

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}

# キーワード抽出で落とすノイズ（日本語タイトルの定型語）
_STOPWORDS = {
    "ゆっくり", "解説", "動画", "まとめ", "shorts", "short", "ショート",
    "です", "ます", "この", "その", "ある", "いる", "する", "した", "して",
    "こと", "もの", "ため", "とは", "なぜ", "実は", "衝撃", "驚愕",
}


# ---------------------------------------------------------------------
# 監視対象
# ---------------------------------------------------------------------

def _load_channel_json(channel_id: str) -> Dict[str, Any]:
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def list_channel_ids() -> List[str]:
    if not CHANNELS_DIR.exists():
        return []
    return sorted(p.stem for p in CHANNELS_DIR.glob("*.json"))


PENDING_RELEVANCE_MIN = 0.5


def watch_targets(channel_id: str, *, limit: int = MAX_COMPETITORS_PER_SCAN) -> List[str]:
    """監視する競合チャンネルID一覧。

    登録済み `competitors` + 承認済み候補 + 適合度の高い未承認候補。
    未承認まで見るのは、RSS 監視が読み取りだけで副作用が無いから。
    （テーマキューに流し込む competitor_analyzer 側は承認済みに限る、という
    使い分け。監視は広く、生成に効かせるのは絞る。）
    """
    raw = _load_channel_json(channel_id).get("competitors") or []
    ids: List[str] = [str(c).strip() for c in raw if str(c).strip().startswith("UC")]

    try:
        from . import competitor_discovery  # type: ignore

        for cand in competitor_discovery.list_candidates(
            channel_id, status="approved", limit=50
        ):
            cid = str(cand.get("competitor_id") or "").strip()
            if cid.startswith("UC"):
                ids.append(cid)

        for cand in competitor_discovery.list_candidates(
            channel_id, status="pending", limit=50
        ):
            cid = str(cand.get("competitor_id") or "").strip()
            try:
                score = float(cand.get("relevance_score") or 0.0)
            except Exception:
                score = 0.0
            if cid.startswith("UC") and score >= PENDING_RELEVANCE_MIN:
                ids.append(cid)
    except Exception:
        pass

    out: List[str] = []
    seen = set()
    for cid in ids:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out[: max(1, limit)]


# ---------------------------------------------------------------------
# フィード取得 / パース
# ---------------------------------------------------------------------

def fetch_feed(competitor_id: str, *, timeout: int = TIMEOUT_SECONDS) -> Optional[str]:
    """RSS 本文を取る。404（チャンネル消滅）などは None を返して呼び出し側で継続。"""
    url = FEED_URL.format(cid=competitor_id)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"⚠️ rss fetch {competitor_id}: HTTP {e.code}")
    except Exception as e:
        print(f"⚠️ rss fetch {competitor_id}: {e}")
    return None


def _parse_ts(published: Optional[str]) -> Optional[int]:
    """RFC3339 ("2026-08-19T09:00:00+00:00" / "...Z") を epoch 秒に。"""
    if not published:
        return None
    text = published.strip()
    # %z は Python 3.7 以降 "+00:00" / "Z" の両方を受け付ける
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if dt.tzinfo is None:
            return timegm(dt.timetuple())  # tz 無しは UTC とみなす
        return int(dt.timestamp())
    return None


def parse_feed(xml_text: str) -> Dict[str, Any]:
    """RSS を {"competitor_title": ..., "entries": [...]} に。

    パース失敗は例外を投げず空を返す（1件の壊れたフィードで全体を止めない）。
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except Exception:
        return {"competitor_title": None, "entries": []}

    title_el = root.find("atom:title", _NS)
    feed_title = (title_el.text or "").strip() if title_el is not None else None

    entries: List[Dict[str, Any]] = []
    for entry in root.findall("atom:entry", _NS):
        vid_el = entry.find("yt:videoId", _NS)
        video_id = (vid_el.text or "").strip() if vid_el is not None else ""
        if not video_id:
            continue
        t_el = entry.find("atom:title", _NS)
        p_el = entry.find("atom:published", _NS)
        published = (p_el.text or "").strip() if p_el is not None else None
        link = f"https://www.youtube.com/watch?v={video_id}"
        entries.append(
            {
                "video_id": video_id,
                "title": (t_el.text or "").strip() if t_el is not None else "",
                "published_at": published,
                "published_ts": _parse_ts(published),
                "link": link,
            }
        )
    return {"competitor_title": feed_title, "entries": entries}


# ---------------------------------------------------------------------
# キーワード
# ---------------------------------------------------------------------

# 形態素解析は入れず、ひらがな（助詞）を区切りとして漢字/カタカナ/英数の塊だけを拾う。
# 「睡眠の新常識」→「睡眠」「新常識」。ひらがな込みで拾うと助詞が接着して
# 「睡眠の新常識」が丸ごと1語になり、チャンネル間で一致しなくなる。
_TOKEN_RE = re.compile(r"[一-龠々]{2,}|[ァ-ヶー]{2,}|[A-Za-z0-9]{2,}")


def _tokens(title: str) -> List[str]:
    out: List[str] = []
    for tok in _TOKEN_RE.findall(title or ""):
        t = tok.strip()
        if len(t) < 2 or t.lower() in _STOPWORDS:
            continue
        out.append(t)
    return out


def hot_keywords(videos: Iterable[Dict[str, Any]], *, limit: int = 10) -> List[Dict[str, Any]]:
    """複数の競合が同時期に触れた語を頻度順で返す。

    同じチャンネルが連呼しても1票になるよう、語ごとに competitor_id を数える。
    """
    voters: Dict[str, set] = {}
    counts: Counter = Counter()
    for v in videos:
        cid = str(v.get("competitor_id") or "")
        for tok in set(_tokens(v.get("title") or "")):
            counts[tok] += 1
            voters.setdefault(tok, set()).add(cid)
    items = [
        {"keyword": k, "count": c, "competitors": len(voters.get(k) or set())}
        for k, c in counts.items()
    ]
    items.sort(key=lambda x: (x["competitors"], x["count"]), reverse=True)
    return [i for i in items if i["competitors"] >= 2][:limit] or items[:limit]


# ---------------------------------------------------------------------
# スキャン
# ---------------------------------------------------------------------

def scan_channel(
    channel_id: str,
    *,
    since_hours: int = DEFAULT_SINCE_HOURS,
    max_competitors: int = MAX_COMPETITORS_PER_SCAN,
) -> Dict[str, Any]:
    """自チャンネルの競合を一巡して新着を記録する。"""
    started = time.time()
    targets = watch_targets(channel_id, limit=max_competitors)
    if not targets:
        return {
            "ok": True,
            "channel_id": channel_id,
            "competitors": 0,
            "new_videos": 0,
            "items": [],
            "hot_keywords": [],
        }

    cutoff = int(started - max(1, since_hours) * 3600)
    new_items: List[Dict[str, Any]] = []
    recent_items: List[Dict[str, Any]] = []
    failed: List[str] = []

    for cid in targets:
        xml_text = fetch_feed(cid)
        if not xml_text:
            failed.append(cid)
            continue
        parsed = parse_feed(xml_text)
        comp_title = parsed.get("competitor_title")
        for e in parsed["entries"]:
            is_new = analytics_store.insert_rss_video(
                channel_id=channel_id,
                competitor_id=cid,
                competitor_title=comp_title,
                video_id=e["video_id"],
                title=e["title"],
                link=e["link"],
                published_at=e["published_at"],
                published_ts=e["published_ts"],
            )
            record = {
                "competitor_id": cid,
                "competitor_title": comp_title,
                **e,
            }
            ts = e.get("published_ts")
            if ts is None or ts >= cutoff:
                recent_items.append(record)
            if is_new and (ts is None or ts >= cutoff):
                new_items.append(record)

    new_items.sort(key=lambda x: x.get("published_ts") or 0, reverse=True)
    result = {
        "ok": True,
        "channel_id": channel_id,
        "competitors": len(targets),
        "failed_feeds": failed,
        "new_videos": len(new_items),
        "items": new_items[:50],
        "hot_keywords": hot_keywords(recent_items),
        "since_hours": since_hours,
        "took_seconds": round(time.time() - started, 1),
    }
    if new_items:
        print(
            f"📡 RSS scan [{channel_id}]: {len(new_items)} new from "
            f"{len(targets)} competitor(s)"
        )
    return result


def scan_all_channels(*, since_hours: int = DEFAULT_SINCE_HOURS) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for cid in list_channel_ids():
        try:
            results.append(scan_channel(cid, since_hours=since_hours))
        except Exception as e:
            results.append({"ok": False, "channel_id": cid, "error": str(e)})
    return {"ok": True, "results": results}


def recent(
    channel_id: str, *, hours: int = DEFAULT_SINCE_HOURS, limit: int = 100
) -> Dict[str, Any]:
    """保存済みの競合新着（DB 参照のみ、ネットワークを叩かない）。"""
    since_ts = int(time.time() - max(1, hours) * 3600)
    items = analytics_store.list_rss_videos(channel_id, since_ts=since_ts, limit=limit)
    return {
        "channel_id": channel_id,
        "hours": hours,
        "count": len(items),
        "items": items,
        "hot_keywords": hot_keywords(items),
        "total_tracked": analytics_store.count_rss_videos(channel_id),
    }
