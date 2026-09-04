"""
image_collector — Web image search + download with attribution.

Used by the video pipeline when a channel's image_mode is "collect" or "mix".
Each downloaded image carries an attribution record so the renderer can show
the source URL on screen (compliance with image licenses).

Providers (env-driven, all optional):
    wikimedia    — (no key)                      Wikimedia Commons; CC/PD
    openverse    — (no key)                      Openverse aggregate; CC/PD
    pixabay      — PIXABAY_API_KEY               (CC0 / Pixabay license; free key)
    pexels       — PEXELS_API_KEY                (Pexels license, credit appreciated; free key)
    unsplash     — UNSPLASH_ACCESS_KEY           (Unsplash license, credit required)
    google_cse   — GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID  (Custom Search JSON API)

Free-key signup:
    Pixabay  https://pixabay.com/api/docs/
    Pexels   https://www.pexels.com/api/
    Unsplash https://unsplash.com/developers

wikimedia / openverse need no credentials, so they are always available. They
are the only providers that reliably return *the actual subject* for a named
real-world entity ("ニトリ 店舗"), where stock-photo providers can only return
a generic lookalike. Channels about real companies/places should ask for them
explicitly (image_collect.provider) — "auto" keeps the historical stock-first
order so existing channels' output does not change.

`provider` may also be a list or a comma-separated string, in which case each
entry is tried in order until one returns an image.

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
        "pexels_key": os.environ.get("PEXELS_API_KEY", ""),
        "unsplash_key": os.environ.get("UNSPLASH_ACCESS_KEY", ""),
        "google_cse_key": os.environ.get("GOOGLE_CSE_API_KEY", ""),
        "google_cse_id": os.environ.get("GOOGLE_CSE_ID", ""),
    }


def _resolve_provider(preferred: str) -> Optional[str]:
    """Pick a provider that actually has credentials. 'auto' tries in order."""
    env = _provider_env()
    # 認証不要のプロバイダは常に使える
    if preferred in ("wikimedia", "openverse"):
        return preferred
    if preferred == "pixabay":
        return "pixabay" if env["pixabay_key"] else None
    if preferred == "pexels":
        return "pexels" if env["pexels_key"] else None
    if preferred == "unsplash":
        return "unsplash" if env["unsplash_key"] else None
    if preferred == "google_cse":
        return "google_cse" if env["google_cse_key"] and env["google_cse_id"] else None
    # auto / unknown — try the free-key providers first, then paid/limited.
    # 既存チャンネルの絵柄を変えないため auto の順序は従来のまま。keyless の
    # wikimedia/openverse は「実在の被写体」が要るチャンネルが明示指定する。
    if env["pixabay_key"]:
        return "pixabay"
    if env["pexels_key"]:
        return "pexels"
    if env["unsplash_key"]:
        return "unsplash"
    if env["google_cse_key"] and env["google_cse_id"]:
        return "google_cse"
    return None


def _provider_chain(preferred) -> List[str]:
    """`provider` 設定（文字列 / カンマ区切り / リスト）を実行可能な順序列にする。"""
    if isinstance(preferred, (list, tuple)):
        wanted = [str(p).strip() for p in preferred]
    else:
        wanted = [p.strip() for p in str(preferred or "auto").split(",")]
    chain = []
    for name in wanted:
        if not name:
            continue
        resolved = _resolve_provider(name)
        if resolved and resolved not in chain:
            chain.append(resolved)
    return chain


# ============================================================
# Public: search & download
# ============================================================

# 企業名から落とす接尾辞・法人格。「株式会社トヨタ自動車」→「トヨタ自動車」。
_ENTITY_SUFFIXES = [
    "株式会社", "有限会社", "合同会社", "ホールディングス", "グループ",
    "Co., Ltd.", "Co.,Ltd.", "Corporation", "Corp.", "Inc.", "Ltd.", "K.K.",
]
_ENTITY_TOKEN_RE = re.compile(r"[一-龥々]{2,}|[ァ-ヶー]{2,}|[A-Za-z]{3,}")

# 業種を表すだけで企業を特定しない語。これ単独の一致は「無関係な写真」を通す。
_GENERIC_ENTITY_TOKENS = {
    "自動車", "工業", "製作所", "製造", "産業", "商事", "銀行", "証券", "保険",
    "電機", "電気", "電子", "重工", "化学", "食品", "製薬", "建設", "運輸",
    "鉄道", "航空", "海運", "不動産", "百貨店", "放送", "新聞", "出版",
    "通信", "情報", "システム", "サービス", "ホールディング", "カンパニー",
    "company", "corporation", "industries", "motor", "motors", "group",
    "holdings", "bank", "electric", "systems", "japan",
}


def _entity_variants(name: str) -> List[str]:
    """企業名の照合キー（法人格を落とした表記・英字小文字）を返す。"""
    n = (name or "").strip()
    if not n:
        return []
    for suf in _ENTITY_SUFFIXES:
        n = n.replace(suf, "")
    n = n.strip(" 　・")
    out = {n.lower()} if n else set()
    for tok in _ENTITY_TOKEN_RE.findall(n):
        # 業種語だけの一致は誤検出になる（「自動車」で無関係な車の写真が通る）。
        # 固有名部分に当たるトークンだけを照合キーにする。
        if len(tok) >= 2 and tok.lower() not in _GENERIC_ENTITY_TOKENS:
            out.add(tok.lower())
    return [v for v in out if v]


def matches_entity(hit: "CollectedImage", entity: str) -> bool:
    """検索ヒットがその企業のものだと確認できるか。

    実写背景は「企業の話をしているのに全く無関係な会社/風景の写真」が乗ると
    誤情報になる。ヒットのタイトル・出典URLに企業名（またはその主要トークン）が
    含まれていることを最低条件にする。判定できないものは**採用しない**
    （検証できないなら使わない、が安全側）。
    """
    variants = _entity_variants(entity)
    if not variants:
        return True  # 企業名が無いなら検証しようがない＝従来どおり通す
    haystack = " ".join([
        str(getattr(hit, "source_title", "") or ""),
        str(getattr(hit, "source_url", "") or ""),
        str(getattr(hit, "direct_url", "") or ""),
    ]).lower()
    if not haystack.strip():
        return False
    return any(v in haystack for v in variants)


def search(query: str, settings: Optional[Dict] = None) -> Optional[CollectedImage]:
    """Search the configured provider for `query` and return the first usable
    image as a CollectedImage (with attribution). Returns None when no
    provider is configured or no image was found.
    """
    settings = settings or {}
    chain = _provider_chain(settings.get("provider", "auto"))
    if not chain:
        print("⚠️ image_collector: no provider configured "
              "(set PIXABAY_API_KEY / PEXELS_API_KEY / UNSPLASH_ACCESS_KEY / GOOGLE_CSE_API_KEY, "
              "or use the keyless 'wikimedia' / 'openverse' providers)")
        return None

    safe = bool(settings.get("safe_search", True))
    license_filter = settings.get("license_filter", "cc")
    max_n = int(settings.get("max_per_query", 5) or 5)
    # 縦型ショートの全画面背景では landscape を9:16に切ると被写体が飛ぶため、
    # 呼び出し側が "portrait" を要求できるようにする（未指定は従来通り landscape）。
    orientation = settings.get("orientation") or "landscape"
    # 同じ被写体を何枚も並べたいときに「N番目のヒット」を取るためのオフセット。
    # 検索語を変えても上位が同じ写真になりがちなスライドショー用途で使う。
    skip = max(0, int(settings.get("skip", 0) or 0))

    keywords = _extract_keywords(query)
    if not keywords:
        return None

    # 実体（企業名）との一致検証。設定されていれば、ヒットのタイトル・URL に
    # その企業名が出てこない写真は採用しない（2026-09-04）。
    entity = str(settings.get("entity") or "").strip()
    require_match = bool(settings.get("require_entity_match")) and bool(entity)
    if require_match:
        tries = max(1, int(settings.get("entity_match_tries", 4) or 4))
        for offset in range(tries):
            sub = dict(settings)
            sub["require_entity_match"] = False
            sub["skip"] = skip + offset
            hit = search(query, settings=sub)
            if hit is None:
                break
            if matches_entity(hit, entity):
                if offset:
                    print(f"  ✅ 実写背景の一致確認: '{entity}' ← {_short_host(hit.source_url)}"
                          f"（{offset + 1}件目で一致）")
                return hit
            print(f"  ⛔ 実写背景を却下: '{entity}' と一致しない "
                  f"（{hit.source_title[:36]!r} / {_short_host(hit.source_url)}）")
        print(f"  ⚠️ '{entity}' に一致する実写が見つからず — この枠は採用しません")
        return None

    for provider in chain:
        try:
            if provider == "wikimedia":
                hit = _search_wikimedia(keywords, safe=safe, max_n=max_n, skip=skip)
            elif provider == "openverse":
                hit = _search_openverse(keywords, safe=safe, max_n=max_n, skip=skip)
            elif provider == "pixabay":
                hit = _search_pixabay(keywords, safe=safe, max_n=max_n,
                                      orientation=orientation, skip=skip)
            elif provider == "pexels":
                hit = _search_pexels(keywords, safe=safe, max_n=max_n,
                                     orientation=orientation, skip=skip)
            elif provider == "unsplash":
                hit = _search_unsplash(keywords, safe=safe, max_n=max_n,
                                       orientation=orientation, skip=skip)
            elif provider == "google_cse":
                hit = _search_google_cse(keywords, safe=safe, max_n=max_n,
                                         license_filter=license_filter, skip=skip)
            else:
                hit = None
        except Exception as e:
            print(f"⚠️ image_collector ({provider}) failed: {e}")
            continue
        if hit is not None:
            return hit
        if len(chain) > 1:
            print(f"  ↪️ {provider}: no hit for '{keywords[:30]}' → next provider")
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
            # 実体一致が必須の用途では、キャッシュも同じ基準で検証する
            # （キャッシュ経由で別企業の写真が復活するのを防ぐ）。
            entity = str((settings or {}).get("entity") or "").strip()
            if (settings or {}).get("require_entity_match") and entity:
                cached_hit = CollectedImage(
                    image=None, source_url=meta.get("source_url", ""),
                    source_title=meta.get("source_title", ""),
                    provider=meta.get("provider", ""),
                    direct_url=meta.get("direct_url", ""))
                if not matches_entity(cached_hit, entity):
                    raise ValueError("cached image does not match entity")
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

# Wikimedia の User-Agent ポリシーは「ツール名 + 連絡先」を要求しており、
# 汎用UAだと upload.wikimedia.org が 429 を返す。連絡先は環境変数で上書き可。
_UA_CONTACT = os.environ.get("IMAGE_COLLECTOR_CONTACT", "https://github.com/youtube-factory")
_UA = f"youtube-factory/1.0 ({_UA_CONTACT}) python-urllib"


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


# 写真として使えない/使いたくないファイル種別。Commons はアイコンや図表、
# 地図、紋章も同じ名前空間に入っているので拡張子とタイトルの両方で弾く。
_NON_PHOTO_EXT = (".svg", ".pdf", ".tif", ".tiff", ".ogv", ".webm", ".gif", ".xcf", ".djvu")
_NON_PHOTO_WORDS = ("icon", "logo", "map", "diagram", "chart", "coat of arms",
                    "flag of", "seal of", "signature", "地図", "紋章", "ロゴ")


def _looks_like_photo(title: str, width: int = 0, height: int = 0) -> bool:
    t = (title or "").lower()
    if t.endswith(_NON_PHOTO_EXT):
        return False
    if any(w in t for w in _NON_PHOTO_WORDS):
        return False
    # 極端に小さい/細長いものはサムネや帯素材なので背景に使えない
    if width and height:
        if min(width, height) < 400:
            return False
        ratio = max(width, height) / max(1, min(width, height))
        if ratio > 3.0:
            return False
    return True


def _search_wikimedia(query: str, safe: bool, max_n: int,
                      skip: int = 0) -> Optional[CollectedImage]:
    """Wikimedia Commons のファイル検索（APIキー不要）。

    実在の企業・店舗・建物・製品の「本物の写真」が取れる唯一の無料経路。
    ストックフォト各社は名前で引いても“それらしい別物”しか返さないため、
    固有名詞が主題のチャンネルはここを最優先で使う。
    """
    # Commons の検索は全語 AND。「ユニクロ 店舗 外観」のように修飾語を重ねると
    # 0件になるので、語を後ろから落としながら再試行する。
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    attempts = []
    for cut in range(len(tokens), 0, -1):
        cand = " ".join(tokens[:cut])
        if cand and cand not in attempts:
            attempts.append(cand)

    for attempt in attempts:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {attempt}",
            "gsrnamespace": "6",          # File:
            "gsrlimit": str(max(3, min(max_n * 3, 30))),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": "1600",
        }
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        data = _http_get_json(url)
        pages = ((data.get("query") or {}).get("pages") or {})
        # generator 検索の index 順（=関連度順）を保つ
        ordered = sorted(pages.values(), key=lambda p: p.get("index", 999))
        remaining = skip
        for page in ordered:
            info = (page.get("imageinfo") or [{}])[0]
            title = page.get("title", "")
            if not _looks_like_photo(title, info.get("width", 0), info.get("height", 0)):
                continue
            # 原寸(url)は upload.wikimedia.org の帯域制限に触れやすいので
            # 必ずサムネイル(thumburl)経由で取る。
            direct = info.get("thumburl") or info.get("url")
            if not direct:
                continue
            if remaining > 0:
                remaining -= 1
                continue
            img = _load_image(direct)
            if img is None:
                continue
            meta = info.get("extmetadata") or {}
            artist = (meta.get("Artist") or {}).get("value") or "Wikimedia Commons"
            artist = re.sub(r"<[^>]+>", "", artist).strip()[:60]
            return CollectedImage(
                image=img,
                source_url=info.get("descriptionurl") or "https://commons.wikimedia.org/",
                source_title=artist or "Wikimedia Commons",
                provider="wikimedia",
                direct_url=direct,
            )
    return None


def _search_openverse(query: str, safe: bool, max_n: int,
                      skip: int = 0) -> Optional[CollectedImage]:
    """Openverse（CC画像アグリゲータ / APIキー不要）検索。

    Commons に無い店舗外観・街角写真を Flickr 等から拾える。商用利用可の
    ライセンスだけに絞る。
    """
    params = {
        "q": query,
        "page_size": str(max(3, min(max_n * 2, 20))),
        "license_type": "commercial",
        "mature": "false",
    }
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)
    data = _http_get_json(url)
    remaining = skip
    for hit in data.get("results") or []:
        direct = hit.get("url")
        if not direct:
            continue
        if remaining > 0:
            remaining -= 1
            continue
        if not _looks_like_photo(hit.get("title", "") or "",
                                 hit.get("width", 0) or 0, hit.get("height", 0) or 0):
            continue
        img = _load_image(direct)
        if img is None:
            continue
        return CollectedImage(
            image=img,
            source_url=hit.get("foreign_landing_url") or direct,
            source_title=(hit.get("creator") or "Openverse")[:60],
            provider="openverse",
            direct_url=direct,
        )
    return None


def fetch_entity_logo(name: str, lang: str = "ja") -> Optional[CollectedImage]:
    """Wikidata の logo image (P154) から企業ロゴを1枚取る（APIキー不要）。

    企業ファクト系の画面では、ロゴが1つ乗っているだけで「どの会社の話か」が
    一目で伝わる。写真より情報密度が高いので背景とは別レイヤーで扱う。

    Wikipedia の pageimage は本社ビルの写真が入っていることが多く「ロゴ」に
    ならないため、ロゴ専用プロパティである P154 だけを使う。見つからなければ
    None（＝ロゴチップを描かない）。
    """
    name = (name or "").strip()
    if not name:
        return None

    entity_ids: List[str] = []
    for language in (lang, "en"):
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "search": name,
            "language": language,
            "uselang": language,
            "type": "item",
            "limit": "3",
        }
        url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params)
        try:
            data = _http_get_json(url)
        except Exception as e:
            print(f"⚠️ logo lookup (search/{language}) failed for '{name}': {e}")
            continue
        for hit in data.get("search") or []:
            if hit.get("id") and hit["id"] not in entity_ids:
                entity_ids.append(hit["id"])
        if entity_ids:
            break

    for qid in entity_ids[:3]:
        params = {
            "action": "wbgetclaims",
            "format": "json",
            "entity": qid,
            "property": "P154",       # logo image
        }
        url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params)
        try:
            data = _http_get_json(url)
        except Exception as e:
            print(f"⚠️ logo lookup (claims/{qid}) failed for '{name}': {e}")
            continue
        for claim in (data.get("claims") or {}).get("P154") or []:
            filename = (((claim.get("mainsnak") or {}).get("datavalue") or {})
                        .get("value"))
            if not isinstance(filename, str) or not filename:
                continue
            # Commons の Special:FilePath はリダイレクトで実体を返す。width 指定で
            # SVG も PNG にラスタライズされるため、そのまま PIL で開ける。
            direct = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
                      + urllib.parse.quote(filename.replace(" ", "_")) + "?width=512")
            img = _load_image(direct)
            if img is None:
                continue
            return CollectedImage(
                image=img,
                source_url="https://commons.wikimedia.org/wiki/File:"
                           + urllib.parse.quote(filename.replace(" ", "_")),
                source_title=name,
                provider="wikidata",
                direct_url=direct,
            )
    return None


def _search_pixabay(query: str, safe: bool, max_n: int,
                    orientation: str = "landscape",
                    skip: int = 0) -> Optional[CollectedImage]:
    key = _provider_env()["pixabay_key"]
    params = {
        "key": key,
        "q": query,
        "image_type": "photo",
        "safesearch": "true" if safe else "false",
        "per_page": max(3, min(max_n, 20)),
        "lang": "ja",
    }
    # 既存挙動（orientation 指定なし＝all）を変えないよう、portrait のときだけ付ける
    if orientation == "portrait":
        params["orientation"] = "vertical"
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode(params)
    data = _http_get_json(url)
    hits = data.get("hits") or []
    remaining = skip
    for hit in hits:
        direct = hit.get("largeImageURL") or hit.get("webformatURL")
        if not direct:
            continue
        if remaining > 0:
            remaining -= 1
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


def _search_pexels(query: str, safe: bool, max_n: int,
                   orientation: str = "landscape",
                   skip: int = 0) -> Optional[CollectedImage]:
    # Pexels has no public safesearch toggle — the `safe` flag is accepted
    # for API parity but ignored. Content is curated/moderated upstream.
    key = _provider_env()["pexels_key"]
    params = {
        "query": query,
        "per_page": max(3, min(max_n, 20)),
        "orientation": "portrait" if orientation == "portrait" else "landscape",
    }
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Authorization": key,
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    remaining = skip
    for hit in data.get("photos") or []:
        src = hit.get("src") or {}
        direct = src.get("large2x") or src.get("large") or src.get("original")
        if not direct:
            continue
        if remaining > 0:
            remaining -= 1
            continue
        img = _load_image(direct)
        if img is None:
            continue
        return CollectedImage(
            image=img,
            source_url=hit.get("url", "https://www.pexels.com/"),
            source_title=hit.get("photographer", "Pexels"),
            provider="pexels",
            direct_url=direct,
        )
    return None


def _search_unsplash(query: str, safe: bool, max_n: int,
                     orientation: str = "landscape",
                     skip: int = 0) -> Optional[CollectedImage]:
    key = _provider_env()["unsplash_key"]
    params = {
        "query": query,
        "per_page": max(3, min(max_n, 20)),
        "content_filter": "high" if safe else "low",
        "orientation": "portrait" if orientation == "portrait" else "landscape",
    }
    url = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Authorization": f"Client-ID {key}",
        "Accept-Version": "v1",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    remaining = skip
    for hit in data.get("results") or []:
        urls = hit.get("urls") or {}
        direct = urls.get("regular") or urls.get("small")
        if not direct:
            continue
        if remaining > 0:
            remaining -= 1
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
                       license_filter: str = "cc",
                       skip: int = 0) -> Optional[CollectedImage]:
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
    remaining = skip
    for item in data.get("items") or []:
        direct = item.get("link")
        if not direct:
            continue
        if remaining > 0:
            remaining -= 1
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
