"""シリーズ通し番号 — ショートのタイトルにエピソード番号を自動付与する。

狙い:
    競合分析で「シリーズ番号付きのタイトルが収集性を生み、
    ビンジ視聴と登録率を上げる」ことが全ニッチで確認された。
    SCP図鑑は '#3500' まで、中村劇場は連番で400K超え。

    各チャンネルの short_series_name（例: "1分科学："）をプレフィックスとし、
    通し番号を自動で振る:
        1分科学 #47：なぜ正座で足がしびれるのか

仕組み:
    data/series_counter/{channel_id}.json に現在のカウンタを保持。
    generate 時にタイトルを加工し、upload 時にカウンタを進める。

設定（チャンネル JSON）:
    "short_series_name": "1分科学："   ← これがあるチャンネルだけ番号を振る
    未設定 or 空文字列 のチャンネルはスキップ（2ch-matome等）
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COUNTER_DIR = PROJECT_ROOT / "data" / "series_counter"

_lock = threading.Lock()


def _counter_path(channel_id: str) -> Path:
    return COUNTER_DIR / f"{channel_id}.json"


def _load_counter(channel_id: str) -> Dict[str, Any]:
    path = _counter_path(channel_id)
    if not path.exists():
        return {"channel_id": channel_id, "short_count": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"channel_id": channel_id, "short_count": 0}
    except Exception:
        return {"channel_id": channel_id, "short_count": 0}


def _save_counter(channel_id: str, data: Dict[str, Any]) -> None:
    COUNTER_DIR.mkdir(parents=True, exist_ok=True)
    path = _counter_path(channel_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def get_next_number(channel_id: str) -> int:
    """次のエピソード番号を返す（カウンタは進めない）。"""
    with _lock:
        data = _load_counter(channel_id)
        return data.get("short_count", 0) + 1


def increment(channel_id: str) -> int:
    """カウンタを1進めて新しい番号を返す。アップロード成功後に呼ぶ。"""
    with _lock:
        data = _load_counter(channel_id)
        data["short_count"] = data.get("short_count", 0) + 1
        _save_counter(channel_id, data)
        return data["short_count"]


def get_series_prefix(channel_id: str, channel_dict: Optional[Dict[str, Any]] = None) -> str:
    """チャンネルのシリーズプレフィックスを返す。未設定なら空文字。"""
    if channel_dict:
        return str(channel_dict.get("short_series_name") or "").strip()
    # channel_dictが渡されなかった場合はファイルから読む
    path = Path(__file__).resolve().parent.parent.parent / "data" / "channels" / f"{channel_id}.json"
    if not path.exists():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return str(raw.get("short_series_name") or "").strip()
    except Exception:
        return ""


def apply_series_number(
    title: str,
    channel_id: str,
    *,
    channel_dict: Optional[Dict[str, Any]] = None,
    is_short: bool = True,
) -> str:
    """タイトルにシリーズ番号プレフィックスを付与する。

    例: "なぜ正座で足がしびれるのか"
      → "1分科学 #47：なぜ正座で足がしびれるのか"

    - short_series_name が未設定のチャンネルはそのまま返す
    - ロング動画(is_short=False)はスキップ
    - 既にプレフィックスが付いている場合はスキップ
    """
    if not is_short:
        return title

    prefix = get_series_prefix(channel_id, channel_dict)
    if not prefix:
        return title

    # 既にプレフィックスが付いている場合はスキップ
    if title.startswith(prefix) or f"#{get_next_number(channel_id)}" in title:
        return title
    # 既に任意の #数字 パターンが付いている場合もスキップ
    import re
    if re.match(r'^.+#\d+[：:]', title):
        return title

    num = get_next_number(channel_id)
    # プレフィックスの末尾のコロンや句読点を取り除いてから番号を挟む
    base = prefix.rstrip("：:： ")
    return f"{base} #{num}：{title}"


def confirm_upload(channel_id: str) -> int:
    """アップロード成功後に呼ぶ。カウンタを確定させる。"""
    return increment(channel_id)


def get_count(channel_id: str) -> int:
    """現在のカウンタ値を返す。"""
    with _lock:
        data = _load_counter(channel_id)
        return data.get("short_count", 0)


def set_count(channel_id: str, count: int) -> None:
    """カウンタを手動で設定する（既存チャンネルの初期値セット用）。"""
    with _lock:
        data = _load_counter(channel_id)
        data["short_count"] = count
        _save_counter(channel_id, data)
