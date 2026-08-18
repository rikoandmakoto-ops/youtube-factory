"""視聴者参加型 — 「リクエスト募集中」の定型ブロック。

狙い:
    コメントは「書いていい」と明示されると一気に増える。コメント数と返信は
    アルゴリズム上のエンゲージメント指標であり、同時に comment_demand が
    テーマキューを埋める燃料にもなる（視聴者リクエスト → 次の動画）。
    つまり募集文はエンゲージメント施策とネタ供給の両方を兼ねる。

出力先:
    - 説明文（video_generator.generate_descriptions の ショート/メイン 両方）
    - 投稿直後の自動コメント（auto_comment.build_comment_text）

「いま多いリクエスト」:
    comment_demands テーブル（comment_demand.scan_channel が貯める）から
    status=pending の上位を拾って載せる。「自分の声が届いている」感を出すと
    次のコメントが増える。DB が無い/空でもブロック自体は出す。

設定（チャンネル JSON の publish_settings.viewer_requests）:
    {
      "enabled": true,              # 既定 true
      "prompt": "...",              # 募集の一文（省略時は既定文）
      "show_top_demands": true,     # 実際に集まっているリクエストを載せる
      "max_demands": 3
    }
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"

HEADER = "▼ リクエスト募集中！"
DEFAULT_PROMPT = "「これ解説してほしい」「ここが気になる」をコメントで教えてください。"
DEFAULT_FOLLOWUP = "リクエストが多かったテーマから動画にしていきます。"
DEFAULT_COMMENT_LINE = "📮 リクエストはこのコメントへの返信でどうぞ！多かったテーマから動画にします"

MAX_DEMANDS = 3


def _load_channel(channel_id: str) -> Dict[str, Any]:
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cfg(channel_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = ((channel_dict or {}).get("publish_settings") or {}).get("viewer_requests")
    return cfg if isinstance(cfg, dict) else {}


def is_enabled(
    channel_id: str = "", channel_dict: Optional[Dict[str, Any]] = None
) -> bool:
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    return _cfg(cd).get("enabled", True) is not False


def _clean(text: str, limit: int = 28) -> str:
    """需要テキストを一行の見出しに詰める。"""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = t.strip("　「」『』\"'")
    if len(t) > limit:
        t = t[: limit - 1] + "…"
    return t


def top_demands(channel_id: str, *, limit: int = MAX_DEMANDS) -> List[str]:
    """いまリクエストが多いテーマ（comment_demands の pending 上位）。

    analytics DB が無い / 空でも落ちない。UI 表示ではなく説明文に載せるので、
    重複や似た表現はここで軽く畳む。
    """
    if not channel_id:
        return []
    try:
        from .analytics import store as analytics_store  # type: ignore
    except Exception:
        return []
    try:
        items = analytics_store.list_comment_demands(
            channel_id, status="pending", limit=30
        )
    except Exception:
        return []

    def _score(it: Dict[str, Any]) -> float:
        try:
            return float(it.get("score") or 0.0)
        except Exception:
            return 0.0

    out: List[str] = []
    seen = set()
    for it in sorted(items or [], key=_score, reverse=True):
        label = _clean(it.get("demand_text") or it.get("suggested_title") or "")
        key = label.lower()
        if not label or key in seen:
            continue
        seen.add(key)
        out.append(label)
        if len(out) >= max(1, limit):
            break
    return out


def build_request_block(
    channel_id: str = "",
    *,
    channel_dict: Optional[Dict[str, Any]] = None,
    compact: bool = False,
    include_demands: Optional[bool] = None,
) -> List[str]:
    """説明文に差し込む「リクエスト募集中」ブロック（無効なら空リスト）。"""
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    if not is_enabled(channel_id, cd):
        return []
    cfg = _cfg(cd)

    prompt = str(cfg.get("prompt") or DEFAULT_PROMPT).strip()
    lines = [HEADER, prompt]
    if not compact:
        lines.append(str(cfg.get("followup") or DEFAULT_FOLLOWUP).strip())

    show = cfg.get("show_top_demands", True) is not False
    if include_demands is not None:
        show = include_demands
    if show:
        try:
            limit = int(cfg.get("max_demands") or MAX_DEMANDS)
        except Exception:
            limit = MAX_DEMANDS
        demands = top_demands(channel_id, limit=limit)
        if demands:
            lines.append(f"🔥 いま多いリクエスト: {' / '.join(demands)}")

    return [ln for ln in lines if ln]


def build_comment_line(
    channel_id: str = "", *, channel_dict: Optional[Dict[str, Any]] = None
) -> str:
    """自動コメントに1行足す用（コメント欄は短さが命なので1行）。"""
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    if not is_enabled(channel_id, cd):
        return ""
    cfg = _cfg(cd)
    line = str(cfg.get("comment_line") or DEFAULT_COMMENT_LINE).strip()
    return line
