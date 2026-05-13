"""
Competitor thumbnail cache — download YouTube competitor thumbnails to a local
cache so they can be passed to GPT-4o Vision as visual references during
thumbnail design generation.

Cache layout:
  data/cache/competitor_thumbnails/{competitor_id}/{video_id}.jpg

The downloader is best-effort: failures never raise; missing thumbnails are
simply absent from the returned list. Files that already exist (non-empty)
are reused.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "competitor_thumbnails"

_FALLBACK_TEMPLATE = "https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def cache_path(competitor_id: str, video_id: str) -> Path:
    return CACHE_DIR / competitor_id / f"{video_id}.jpg"


def _download(url: str, dest: Path, timeout: int = 15) -> bool:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "youtube-factory/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"⚠️ competitor thumbnail download failed ({url}): {e}")
        return False


def ensure_cached(
    competitor_id: str,
    video_id: str,
    thumbnail_url: Optional[str] = None,
) -> Optional[Path]:
    """Return the cached path; download if missing.

    Falls back to the canonical `i.ytimg.com/vi/{id}/hqdefault.jpg` URL when
    the provided thumbnail_url is empty or fails.
    """
    if not competitor_id or not video_id:
        return None
    dest = cache_path(competitor_id, video_id)
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    url = thumbnail_url or _FALLBACK_TEMPLATE.format(video_id=video_id)
    if _download(url, dest):
        return dest

    if thumbnail_url and "hqdefault.jpg" not in thumbnail_url:
        if _download(_FALLBACK_TEMPLATE.format(video_id=video_id), dest):
            return dest
    return None


def cache_top_thumbnails(
    competitor_id: str,
    videos: Iterable[dict],
    *,
    max_count: int = 5,
) -> List[Path]:
    """Download/cache top-N video thumbnails for a competitor (sorted by views).

    `videos` is the list of dicts produced by `competitor_analyzer._fetch_video_details`
    (each has `video_id`, `views`, `thumbnail_url`).
    """
    sorted_vs = sorted(
        (v for v in videos if isinstance(v, dict) and v.get("video_id")),
        key=lambda v: int(v.get("views") or 0),
        reverse=True,
    )[: max(0, int(max_count))]
    out: List[Path] = []
    for v in sorted_vs:
        path = ensure_cached(
            competitor_id,
            str(v["video_id"]),
            thumbnail_url=v.get("thumbnail_url"),
        )
        if path:
            out.append(path)
    return out
