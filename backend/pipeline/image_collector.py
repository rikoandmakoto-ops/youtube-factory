"""
image_collector — Web image search + download with attribution.

Used by the video pipeline when a channel's image_mode is "collect" or "mix".
Each downloaded image carries an attribution record so the renderer can show
the source URL on screen (compliance with image licenses).

Providers (env-driven, all optional):
    pixabay      — PIXABAY_API_KEY               (CC0 / Pixabay license)
    unsplash     — UNSPLASH_ACCESS_KEY           (Unsplash license, credit required)
    google_cse   — GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID  (Custom Search JSON API)

If no provider is configured, search() returns None and the caller falls
back to AI generation.

Mix-mode decision (decide_mode):
    Heuristic that picks "collect" for narration that names a real-world
    entity (person, place, year, brand, named event) and "generate"
    otherwise. Tunable per-channel via image_collect.mix_strategy:
        - "heuristic"        (default)
        - "always_collect"
        - "always_generate"
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image


# ============================================================
# Public types
# ============================================================

@dataclass
class CollectedImage:
    """One downloaded image with its provenance."""
    image: Image.Image
    source_url: str          # page the image came from (for human attribution)
    source_title: str        # photographer / page title / "Pixabay" etc.
    provider: str            # "pixabay" | "unsplash" | "google_cse"
    direct_url: str = ""     # raw image URL (for re-fetch / cache key)

    def attribution_text(self, template: str = "出典: {source}") -> str:
        """Short human-readable line for on-screen overlay.

        We keep this short (host + a tiny tail) so it fits in one line under
        the illustration card without breaking layout.
        """
        host = _short_host(self.source_url) or self.provider
        return template.format(source=host)


# ============================================================
# Provider config
# ============================================================

def _provider_env() -> Dict[str, str]:
    return {
        "pixabay_key": os.environ.get("PIXABAY_API_KEY", ""),
        "unsplash_key": os.environ.get("UNSPLASH_ACCESS_KEY", ""),
        "google_cse_key": os.environ.get("GOOGLE_CSE_API_KEY", ""),
        "google_cse_id": os.environ.get("GOOGLE_CSE_ID", ""),
    }


def _resolve_provider(preferred: str) -> Optional[str]:
    """Pick a provider that actually has credentials. 'auto' tries in order."""
    env = _provider_env()
    if preferred == "pixabay":
        return "pixabay" if env["pixabay_key"] else None
    if preferred == "unsplash":
        return "unsplash" if env["unsplash_key"] else None
    if preferred == "google_cse":
        return "google_cse" if env["google_cse_key"] and env["google_cse_id"] else None
    # auto / unknown
    if env["pixabay_key"]:
        return "pixabay"
    if env["unsplash_key"]:
        return "unsplash"
    if env["google_cse_key"] and env["google_cse_id"]:
        return "google_cse"
    return None


# ============================================================
# Public: search & download
# ============================================================

def search(query: str, settings: Optional[Dict] = None) -> Optional[CollectedImage]:
    """Search the configured provider for `query` and return the first usable
    image as a CollectedImage (with attribution). Returns None when no
    provider is configured or no image was found.
    """
    settings = settings or {}
    provider = _resolve_provider(settings.get("provider", "auto"))
    if not provider:
        print("⚠️ image_collector: no provider configured "
              "(set PIXABAY_API_KEY / UNSPLASH_ACCESS_KEY / GOOGLE_CSE_API_KEY)")
        return None

    safe = bool(settings.get("safe_search", True))
    license_filter = settings.get("license_filter", "cc")
    max_n = int(settings.get("max_per_query", 5) or 5)

    keywords = _extract_keywords(query)
    if not keywords:
        return None

    try:
        if provider == "pixabay":
            return _search_pixabay(keywords, safe=safe, max_n=max_n)
        if provider == "unsplash":
            return _search_unsplash(keywords, safe=safe, max_n=max_n)
        if provider == "google_cse":
            return _search_google_cse(keywords, safe=safe, max_n=max_n,
                                      license_filter=license_filter)
    except Exception as e:
        print(f"⚠️ image_collector ({provider}) failed: {e}")
        return None
    return None


def search_and_cache(query: str, cache_dir: Path, idx: int,
                     settings: Optional[Dict] = None) -> Optional[Dict]:
    """Wrap search() with disk caching. Returns {image, attribution_text,
    source_url, ...} or None.

    Attribution metadata is sidecar JSON next to the image so subsequent
    runs (after the PIL Image is GC'd) can still recover the source.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    img_path = cache_dir / f"collected_{idx:03d}.png"
    meta_path = cache_dir / f"collected_{idx:03d}.json"
    if img_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            img = Image.open(str(img_path)).convert("RGBA")
            return {
                "image": img,
                "source_url": meta.get("source_url", ""),
                "source_title": meta.get("source_title", ""),
                "provider": meta.get("provider", ""),
                "attribution_text": meta.get("attribution_text", ""),
            }
        except Exception:
            pass

    result = search(query, settings=settings)
    if not result:
        return None

    template = (settings or {}).get("attribution_template", "出典: {source}")
    attribution = result.attribution_text(template=template)
    try:
        result.image.save(str(img_path))
        meta_path.write_text(json.dumps({
            "source_url": result.source_url,
            "source_title": result.source_title,
            "provider": result.provider,
            "direct_url": result.direct_url,
            "attribution_text": attribution,
            "query": query,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  💾 Collected image cached: {img_path} (from {_short_host(result.source_url)})")
    except Exception as e:
        print(f"⚠️ image_collector cache write failed: {e}")

    return {
        "image": result.image,
        "source_url": result.source_url,
        "source_title": result.source_title,
        "provider": result.provider,
        "attribution_text": attribution,
    }


# ============================================================
# Mix-mode decision
# ============================================================

# Hits on these markers → topic is grounded in a real entity → prefer collect.
# Keep narrow — false positives mean copyrighted photos over an AI-safe diagram.
_REAL_ENTITY_HINTS = [
    r"\d{3,4}\s*年",            # years (1995年)
    r"\d{4}\s*月",
    r"会社|企業|社長|首相|大統領|大臣|博士|教授|氏\b|さん\b",
    r"アメリカ|日本|中国|ロシア|イギリス|ドイツ|フランス|韓国|台湾|インド",
    r"東京|大阪|京都|ニューヨーク|ロンドン|パリ|ベルリン",
    r"NASA|JAXA|ESA|UN|EU|WHO|NHK|IBM|Google|Apple|Microsoft|Amazon|Tesla",
    r"事件|事故|戦争|地震|噴火|大震災",
    r"写真|画像|映像|資料",
]

# Hits here → abstract / fictional / would-look-better-AI-drawn → prefer generate.
_GENERATE_HINTS = [
    r"SCP-\d+",
    r"キャラ|主人公|アニメ|漫画|物語|架空|概念図|イラスト",
    r"理論|原理|仕組み|モデル|構造|反応|細胞|分子|原子|遺伝子",
    r"なぜ|どうして|もし|想像",
]


def decide_mode(topic_text: str, settings: Optional[Dict] = None) -> str:
    """Return 'collect' or 'generate' for a mix-mode scene.

    Strategy override via settings.mix_strategy:
        always_collect / always_generate → forced.
        heuristic (default)              → regex scoring below.
    """
    settings = settings or {}
    strategy = settings.get("mix_strategy", "heuristic")
    if strategy == "always_collect":
        return "collect"
    if strategy == "always_generate":
        return "generate"

    text = topic_text or ""
    if not text.strip():
        return "generate"

    real_score = sum(1 for pat in _REAL_ENTITY_HINTS if re.search(pat, text))
    gen_score = sum(1 for pat in _GENERATE_HINTS if re.search(pat, text))
    # Tie-break: prefer generate (safer — no licensing risk).
    if real_score > gen_score:
        return "collect"
    return "generate"


# ============================================================
# Internal: provider implementations
# ============================================================

_UA = "youtube-factory/1.0 (+image_collector)"


def _http_get_json(url: str, timeout: int = 20) -> Dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _load_image(url: str) -> Optional[Image.Image]:
    try:
        data = _http_get_bytes(url)
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        print(f"⚠️ image download failed ({url}): {e}")
        return None


def _search_pixabay(query: str, safe: bool, max_n: int) -> Optional[CollectedImage]:
    key = _provider_env()["pixabay_key"]
    params = {
        "key": key,
        "q": query,
        "image_type": "photo",
        "safesearch": "true" if safe else "false",
        "per_page": max(3, min(max_n, 20)),
        "lang": "ja",
    }
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode(params)
    data = _http_get_json(url)
    hits = data.get("hits") or []
    for hit in hits:
        direct = hit.get("largeImageURL") or hit.get("webformatURL")
        if not direct:
            continue
        img = _load_image(direct)
        if img is None:
            continue
        return CollectedImage(
            image=img,
            source_url=hit.get("pageURL", "https://pixabay.com/"),
            source_title=hit.get("user", "Pixabay"),
            provider="pixabay",
            direct_url=direct,
        )
    return None


def _search_unsplash(query: str, safe: bool, max_n: int) -> Optional[CollectedImage]:
    key = _provider_env()["unsplash_key"]
    params = {
        "query": query,
        "per_page": max(3, min(max_n, 20)),
        "content_filter": "high" if safe else "low",
        "orientation": "landscape",
    }
    url = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Authorization": f"Client-ID {key}",
        "Accept-Version": "v1",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for hit in data.get("results") or []:
        urls = hit.get("urls") or {}
        direct = urls.get("regular") or urls.get("small")
        if not direct:
            continue
        img = _load_image(direct)
        if img is None:
            continue
        user = (hit.get("user") or {}).get("name", "Unsplash")
        page = (hit.get("links") or {}).get("html", "https://unsplash.com/")
        return CollectedImage(
            image=img,
            source_url=page,
            source_title=user,
            provider="unsplash",
            direct_url=direct,
        )
    return None


def _search_google_cse(query: str, safe: bool, max_n: int,
                       license_filter: str = "cc") -> Optional[CollectedImage]:
    env = _provider_env()
    key, cx = env["google_cse_key"], env["google_cse_id"]
    params = {
        "key": key,
        "cx": cx,
        "q": query,
        "searchType": "image",
        "num": max(1, min(max_n, 10)),
        "safe": "active" if safe else "off",
    }
    if license_filter == "cc":
        # Restrict to a permissive CC license set when requested.
        params["rights"] = "cc_publicdomain,cc_attribute,cc_sharealike"
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params)
    data = _http_get_json(url)
    for item in data.get("items") or []:
        direct = item.get("link")
        if not direct:
            continue
        img = _load_image(direct)
        if img is None:
            continue
        ctx = item.get("image") or {}
        page = ctx.get("contextLink") or direct
        title = item.get("title") or "Google"
        return CollectedImage(
            image=img,
            source_url=page,
            source_title=title,
            provider="google_cse",
            direct_url=direct,
        )
    return None


# ============================================================
# Internal: text helpers
# ============================================================

# Strip filler so the search query targets the topical nouns.
_FILLER_PATTERNS = [
    r"だよね|でしょ|なんだ|なんですよ|だから|ですから|なんです|ですよ|ですね",
    r"こんにちは|やぁ|ねえ|うん|まあ|ええと|あのー|そうそう",
    r"今日は|今回は|それじゃあ|では|さて",
]


def _extract_keywords(topic_text: str, max_words: int = 6) -> str:
    """Squeeze a narration window down to a short search query.

    Drops trailing punctuation and dialogue filler. Keeps the order of words
    so person+place combinations stay together.
    """
    text = (topic_text or "").strip()
    if not text:
        return ""
    for pat in _FILLER_PATTERNS:
        text = re.sub(pat, " ", text)
    # Cap to avoid blowing past provider query limits.
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 80:
        text = text[:80]
    return text


def _short_host(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc or url
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url
