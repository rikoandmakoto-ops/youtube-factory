"""アップロード直後に走る共通処理（再生リスト投入 / シリーズ相互リンク）。

自動公開（api_phase4）と手動アップロードスクリプト（run_*_upload.py）の
両方から同じ入口を呼べるようにまとめる。ここでの失敗は投稿を壊さない。

自動コメント（auto_comment）は「予約公開の解除待ち」という別の都合があるため
従来どおり api_phase4 側から個別に呼ぶ。ここでは公開状態に依存しない
（private/予約公開でも通る）処理だけを扱う。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"


def _load_channel(channel_id: str) -> Dict[str, Any]:
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run(
    *,
    channel_id: str,
    video_id: Optional[str],
    title: str = "",
    url: str = "",
    is_short: bool = True,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """再生リスト投入 → シリーズリンクの順に実行し、結果をまとめて返す。"""
    if not video_id:
        return {"ok": False, "skipped": "no_video_id"}

    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    video_url = url or f"https://youtube.com/watch?v={video_id}"
    out: Dict[str, Any] = {"channel_id": channel_id, "video_id": video_id}

    try:
        from . import playlist_manager

        out["playlists"] = playlist_manager.add_video_to_playlists(
            channel_id, video_id, title=title, is_short=is_short, channel_dict=cd
        )
    except Exception as e:
        out["playlists"] = {"ok": False, "error": str(e)}
        print(f"⚠️ post_upload playlists failed [{channel_id}] {video_id}: {e}")

    try:
        from . import series_links

        out["series_links"] = series_links.link_and_record(
            channel_id,
            video_id,
            title=title,
            url=video_url,
            is_short=is_short,
            channel_dict=cd,
        )
    except Exception as e:
        out["series_links"] = {"ok": False, "error": str(e)}
        print(f"⚠️ post_upload series_links failed [{channel_id}] {video_id}: {e}")

    return out


def run_async(**kwargs: Any) -> None:
    """アップロードスレッドを塞がない fire-and-forget ラッパ。"""

    def _work() -> None:
        try:
            run(**kwargs)
        except Exception as e:
            print(f"⚠️ post_upload thread failed: {e}")

    threading.Thread(target=_work, name="post-upload", daemon=True).start()
