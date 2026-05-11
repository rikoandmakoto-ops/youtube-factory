"""
TrendFetcher — Phase C: トレンドワード連動

リアルタイムのトレンド情報をかき集めて「旬のテーマ」生成に使う。

ソース:
  1. Google Trends（pytrends 非公式 API） — 日本の急上昇キーワード
     - 未インストール / レート制限時は黙ってスキップ
  2. YouTube Data API v3 `videos.list?chart=mostPopular`
     - 教育(27) / 科学(28) カテゴリの急上昇動画
     - YOUTUBE_API_KEY が必要（無くてもクラッシュしない）
  3. キャッシュ — data/trends/<source>_<date>.json に1日キャッシュ

公開関数:
  - fetch_google_trends(region="JP", limit=20) -> List[str]
  - fetch_youtube_trending(region="JP", category_id="27", limit=15) -> List[Dict]
  - fetch_combined_trends(channel=None) -> Dict
      総合: { "google_trends": [...], "youtube_trending": [...],
              "relevant_to_channel": [...], "fetched_at": "...", "sources_used": [...] }
  - score_theme_against_trends(theme_title, trends) -> float
      テーマ文字列とトレンドリストの語彙重なりから 0.0〜1.0 のスコアを返す

設計方針:
  - 失敗時は例外を投げず、空配列＋エラー情報を返す（呼び出し側で組み立てを継続できる）。
  - キャッシュで pytrends のレート制限を緩和（同日2回目以降は再ヒットしない）。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional


_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "trends"
_CACHE_TTL_SECONDS = 6 * 3600  # 6 時間で新しく取り直す
YT_API_BASE = "https://www.googleapis.com/youtube/v3"

# 教育・科学カテゴリ既定値（チャンネル側で上書き可能）
DEFAULT_CATEGORIES = ["27", "28"]  # 27=Education, 28=Science & Technology


def _ensure_cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def _cache_path(name: str) -> Path:
    today = date.today().isoformat()
    return _ensure_cache_dir() / f"{name}_{today}.json"


def _read_cache(name: str) -> Optional[Dict[str, Any]]:
    p = _cache_path(name)
    if not p.exists():
        return None
    try:
        age = time.time() - p.stat().st_mtime
        if age > _CACHE_TTL_SECONDS:
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(name: str, data: Dict[str, Any]) -> None:
    try:
        p = _cache_path(name)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------
# Google Trends (pytrends)
# ---------------------------------------------------------------------

def fetch_google_trends(
    region: str = "japan",
    *,
    limit: int = 20,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """日本の Google 急上昇トレンドを取得。pytrends 未導入 / 失敗時は空配列。"""
    cache_key = f"google_{region}"
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached

    result: Dict[str, Any] = {
        "source": "google_trends",
        "region": region,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "trends": [],
        "ok": False,
        "error": None,
    }

    try:
        from pytrends.request import TrendReq  # type: ignore
    except Exception as e:
        result["error"] = f"pytrends not installed: {e}"
        _write_cache(cache_key, result)
        return result

    pytrends = None
    try:
        pytrends = TrendReq(hl="ja-JP", tz=540, timeout=(5, 15))
    except Exception as e:
        result["error"] = f"TrendReq init failed: {type(e).__name__}: {e}"
        _write_cache(cache_key, result)
        return result

    trends: List[str] = []
    last_err: Optional[str] = None

    # 1) trending_searches(pn=region) — 国別の急上昇キーワード（pn は地域名）
    try:
        df = pytrends.trending_searches(pn=region)
        for v in df.iloc[:, 0].tolist():
            s = str(v).strip()
            if s:
                trends.append(s)
            if len(trends) >= limit:
                break
    except Exception as e:
        last_err = f"trending_searches[{region}]: {type(e).__name__}: {e}"

    # 2) realtime_trending_searches — JP の急上昇（リアルタイム）
    if not trends:
        try:
            df = pytrends.realtime_trending_searches(pn="JP")
            if df is not None and not df.empty:
                col = "title" if "title" in df.columns else df.columns[0]
                for v in df[col].tolist():
                    s = str(v).strip()
                    if s:
                        trends.append(s)
                    if len(trends) >= limit:
                        break
        except Exception as e:
            last_err = f"{last_err or ''} | realtime: {type(e).__name__}: {e}"

    # 3) today_searches — 国別の "today" 急上昇（最終フォールバック）
    if not trends:
        try:
            df = pytrends.today_searches(pn="JP")
            if df is not None and not df.empty:
                for v in df.tolist() if hasattr(df, "tolist") else df:
                    s = str(v).strip()
                    if s:
                        trends.append(s)
                    if len(trends) >= limit:
                        break
        except Exception as e:
            last_err = f"{last_err or ''} | today: {type(e).__name__}: {e}"

    if trends:
        result["trends"] = trends
        result["ok"] = True
    else:
        result["error"] = last_err or "all pytrends endpoints returned empty"

    _write_cache(cache_key, result)
    return result


# ---------------------------------------------------------------------
# YouTube Trending
# ---------------------------------------------------------------------

def _fetch_yt_most_popular(
    api_key: str, region: str, category_id: str, max_results: int
) -> List[Dict[str, Any]]:
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region,
        "videoCategoryId": category_id,
        "maxResults": min(50, max(1, max_results)),
        "key": api_key,
    }
    url = f"{YT_API_BASE}/videos?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for it in data.get("items", []) or []:
        sn = it.get("snippet", {}) or {}
        st = it.get("statistics", {}) or {}
        title = sn.get("title")
        if not title:
            continue
        out.append({
            "video_id": it.get("id"),
            "title": title,
            "channel_title": sn.get("channelTitle"),
            "category_id": category_id,
            "published_at": sn.get("publishedAt"),
            "tags": sn.get("tags") or [],
            "views": int(st.get("viewCount", 0) or 0),
            "likes": int(st.get("likeCount", 0) or 0),
        })
    return out


def _fetch_yt_search(
    api_key: str, region: str, category_id: str, max_results: int, days: int = 7
) -> List[Dict[str, Any]]:
    """search.list — 直近 days 日のカテゴリ別人気動画（mostPopular が空の時のフォールバック）。"""
    try:
        from datetime import timedelta
        published_after = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        published_after = None
    params = {
        "part": "snippet",
        "type": "video",
        "regionCode": region,
        "relevanceLanguage": "ja",
        "videoCategoryId": category_id,
        "order": "viewCount",
        "maxResults": min(50, max(1, max_results)),
        "key": api_key,
    }
    if published_after:
        params["publishedAfter"] = published_after
    url = f"{YT_API_BASE}/search?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for it in data.get("items", []) or []:
        sn = it.get("snippet", {}) or {}
        vid = (it.get("id") or {}).get("videoId")
        title = sn.get("title")
        if not vid or not title:
            continue
        out.append({
            "video_id": vid,
            "title": title,
            "channel_title": sn.get("channelTitle"),
            "category_id": category_id,
            "published_at": sn.get("publishedAt"),
            "tags": [],
            "views": 0,
            "likes": 0,
        })
    return out


def fetch_youtube_trending(
    *,
    region: str = "JP",
    category_ids: Optional[List[str]] = None,
    days: int = 7,
    limit: int = 25,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """YouTube の急上昇動画 + 直近人気動画を取得。

    1. videos.list?chart=mostPopular（カテゴリ別の急上昇）
    2. mostPopular が空ならフォールバックで search.list?order=viewCount

    YOUTUBE_API_KEY 未設定なら空配列で返す。
    """
    categories = category_ids or DEFAULT_CATEGORIES
    cache_key = f"youtube_{region}_{'_'.join(categories)}"
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    result: Dict[str, Any] = {
        "source": "youtube",
        "region": region,
        "category_ids": categories,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "videos": [],
        "ok": False,
        "error": None,
    }
    if not api_key:
        result["error"] = "YOUTUBE_API_KEY not set"
        _write_cache(cache_key, result)
        return result

    all_videos: List[Dict[str, Any]] = []
    per_cat = max(3, limit // max(1, len(categories)))
    for cat in categories:
        chunk = _fetch_yt_most_popular(api_key, region, cat, per_cat)
        if not chunk:
            chunk = _fetch_yt_search(api_key, region, cat, per_cat, days=days)
        all_videos.extend(chunk)

    # 重複除去 & 再生数で降順
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for v in sorted(all_videos, key=lambda x: x.get("views", 0), reverse=True):
        if v["video_id"] in seen:
            continue
        seen.add(v["video_id"])
        deduped.append(v)
        if len(deduped) >= limit:
            break

    result["videos"] = deduped
    result["ok"] = True
    _write_cache(cache_key, result)
    return result


# ---------------------------------------------------------------------
# キーワード抽出 / 関連度スコアリング
# ---------------------------------------------------------------------

_HIRAGANA_RE = re.compile(r"[ぁ-んー]+")
_KATAKANA_RE = re.compile(r"[ァ-ヶー]+")
_KANJI_RE = re.compile(r"[一-龠々]+")
_ASCII_RE = re.compile(r"[a-zA-Z0-9]+")


def _bigrams(s: str) -> List[str]:
    if len(s) < 2:
        return [s] if s else []
    return [s[i:i + 2] for i in range(len(s) - 1)]


def _tokens(text: str) -> List[str]:
    """形態素解析なしで「ざっくり」トークン化。

    Japanese は文字種境界で分割しただけだと「なぜ空は青いのか」が1トークンになって
    照合に使えないため、漢字/カタカナ列は bigram 化、英数字とひらがな列はそのまま
    （長さ2 以上）を返す。
    """
    if not text:
        return []
    out: List[str] = []
    seen: set = set()

    def _emit(t: str, *, min_len: int = 1):
        t = t.strip()
        if len(t) < min_len or t in seen:
            return
        seen.add(t)
        out.append(t)

    # 漢字: 連語(全体・bigram) と単漢字を全部拾う。重複は seen で潰す。
    for kanji in _KANJI_RE.findall(text):
        if len(kanji) <= 4:
            _emit(kanji, min_len=1)
        for bg in _bigrams(kanji):
            _emit(bg, min_len=2)
        # 単漢字: 「青空」→「青」「空」、「正体」→「正」「体」
        if len(kanji) >= 2:
            for ch in kanji:
                _emit(ch, min_len=1)
    # カタカナ: 長さ2 以上の連続を語として、長すぎる場合は bigram でも分解
    for kata in _KATAKANA_RE.findall(text):
        if len(kata) >= 2:
            _emit(kata, min_len=2)
        for bg in _bigrams(kata):
            _emit(bg, min_len=2)
    # ひらがな: ノイズが多いので 3 文字以上の連続のみ
    for hira in _HIRAGANA_RE.findall(text):
        if len(hira) >= 3:
            _emit(hira, min_len=3)
    for asc in _ASCII_RE.findall(text):
        if len(asc) >= 2:
            _emit(asc.lower(), min_len=2)
    return out


def extract_keywords_from_videos(videos: List[Dict[str, Any]], *, top_n: int = 25) -> List[str]:
    """急上昇動画タイトル+タグから頻出語を抽出。"""
    freq: Dict[str, int] = {}
    for v in videos:
        text = " ".join(filter(None, [v.get("title"), " ".join(v.get("tags") or [])]))
        for t in _tokens(text):
            freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    return [w for w, _ in ranked[:top_n]]


def score_theme_against_trends(theme_title: str, trends: List[str]) -> float:
    """テーマタイトルとトレンド語彙の重なり度（0.0〜1.0）。"""
    if not theme_title or not trends:
        return 0.0
    theme_tokens = set(_tokens(theme_title))
    if not theme_tokens:
        return 0.0
    trend_tokens: set = set()
    for t in trends:
        trend_tokens.update(_tokens(t))
    if not trend_tokens:
        return 0.0
    overlap = theme_tokens & trend_tokens
    # シンプルな Jaccard ライク
    return round(len(overlap) / len(theme_tokens), 3)


# ---------------------------------------------------------------------
# 総合エントリポイント
# ---------------------------------------------------------------------

def fetch_combined_trends(
    channel: Optional[Any] = None,
    *,
    region_google: str = "japan",
    region_youtube: str = "JP",
    category_ids: Optional[List[str]] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Google Trends + YouTube 急上昇を1つにまとめて返す。

    Returns:
        {
          "google_trends": [str, ...],
          "youtube_trending": [{video_id, title, ...}, ...],
          "youtube_keywords": [str, ...],       # 急上昇動画タイトルからの抽出ワード
          "relevant_to_channel": [str, ...],    # チャンネル過去テーマと意味的に被るワード
          "fetched_at": "...",
          "sources_used": ["google", "youtube"],
          "errors": {"google": "...", "youtube": "..."},
        }
    """
    google = fetch_google_trends(region=region_google, use_cache=use_cache)
    youtube = fetch_youtube_trending(
        region=region_youtube, category_ids=category_ids, use_cache=use_cache
    )

    sources_used = []
    if google.get("ok"):
        sources_used.append("google")
    if youtube.get("ok"):
        sources_used.append("youtube")

    yt_keywords = extract_keywords_from_videos(youtube.get("videos", []) or [])
    google_keywords = list(google.get("trends") or [])

    # チャンネル関連度: 過去テーマや theme_seeds と被るキーワードを抽出
    relevant: List[str] = []
    if channel is not None:
        channel_tokens: set = set()
        try:
            for seed in (channel.theme_seeds or []):
                channel_tokens.update(_tokens(seed.get("title", "")))
                channel_tokens.update(_tokens(seed.get("angle", "")))
            channel_tokens.update(_tokens(getattr(channel, "concept", "") or ""))
            channel_tokens.update(_tokens(getattr(channel, "name", "") or ""))
        except Exception:
            channel_tokens = set()

        all_trend_keywords = google_keywords + yt_keywords
        seen = set()
        for kw in all_trend_keywords:
            if kw in seen:
                continue
            seen.add(kw)
            kw_tokens = set(_tokens(kw))
            # 1 トークンでも channel と被ったら「関連あり」
            if kw_tokens & channel_tokens:
                relevant.append(kw)
            if len(relevant) >= 15:
                break

    return {
        "google_trends": google_keywords,
        "youtube_trending": youtube.get("videos", []),
        "youtube_keywords": yt_keywords,
        "relevant_to_channel": relevant,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "sources_used": sources_used,
        "errors": {
            "google": google.get("error"),
            "youtube": youtube.get("error"),
        },
    }


def build_prompt_block(combined: Dict[str, Any], *, max_items: int = 8) -> str:
    """fetch_combined_trends の結果から GPT プロンプト用ブロックを組み立てる。"""
    g = (combined.get("google_trends") or [])[:max_items]
    yk = (combined.get("youtube_keywords") or [])[:max_items]
    rel = (combined.get("relevant_to_channel") or [])[:max_items]
    yt_videos = (combined.get("youtube_trending") or [])[:max_items]

    lines: List[str] = []
    if rel:
        lines.append("**チャンネルと相性が良い旬のキーワード**: " + " / ".join(rel))
    if g:
        lines.append("**Google 急上昇 (日本)**: " + " / ".join(g))
    if yk:
        lines.append("**YouTube 教育・科学カテゴリの頻出ワード**: " + " / ".join(yk))
    if yt_videos:
        top_titles = [v.get("title") for v in yt_videos if v.get("title")][:5]
        if top_titles:
            lines.append("**直近の急上昇動画タイトル例**: " + " / ".join(top_titles))

    if not lines:
        return ""

    header = "## 現在のトレンド（提案テーマに反映できれば反映）"
    footer = (
        "- 上記キーワードと**自然に**結び付くテーマには `is_trending: true` を付与する。"
        " 無理矢理ねじ込まず、本来のチャンネル文脈で語れる場合のみ。"
    )
    return header + "\n" + "\n".join(f"- {l}" for l in lines) + "\n" + footer
