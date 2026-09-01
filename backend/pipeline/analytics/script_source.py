"""台本の出所（Claude / GPT）を投稿済み動画に紐づける台帳。

なぜ必要か:
  シナリオ側には最初から `generated_by` があり、scenario archive の
  frontmatter / _index.json にも残っている。しかしそこには YouTube の
  video_id が無い。逆に model_scenario_records には video_id 列があるが
  一度も埋められておらず（718件すべて NULL）、実績と突き合わせられない。
  結果「Claude台本とGPT台本のどちらが伸びたか」を後から集計できなかった。

このモジュールは video_id ↔ script_source の1対1台帳を持ち、
アップロード直後（post_upload）に1行書く。出所は次の順に解決する:

  1. explicit      — 呼び出し側が script_source / generated_by を渡した
  2. archive       — scenario archive の _index.json をタイトル照合
  3. model_records — model_scenario_records を selected + タイトル照合
  4. 解決不能      — 記録しない（不明を "gpt" などに寄せない）

集計は `backend/ab_script_source_report.py`。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import store as analytics_store

CLAUDE = "claude"
GPT = "gpt"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCENARIOS_BASE = PROJECT_ROOT / "data" / "scenarios"


def normalize(raw: Optional[str]) -> Optional[str]:
    """generated_by の生値を "claude" / "gpt" に正規化する。

    実データに入っている値: claude / gpt / claude-manual / claude-direct /
    "claude-opus-5 (in-session, no API)" / edge-tts-pipeline / None。
    最後の2つのようにモデルを表していない値は None を返す（不明は不明のまま）。
    """
    if not raw:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s.startswith("claude") or "anthropic" in s or "sonnet" in s or "opus" in s:
        return CLAUDE
    if s.startswith("gpt") or "openai" in s or s.startswith("o1") or s.startswith("o3"):
        return GPT
    return None


_TOKEN_RE = re.compile(r"[ぁ-んァ-ン一-龥A-Za-z0-9]+")


def _normalize_title(s: Optional[str]) -> str:
    if not s:
        return ""
    return "".join(_TOKEN_RE.findall(s)).lower()


def _title_similarity(a: str, b: str) -> float:
    """scenario_archive.find_archive_for_title と同じ流儀の緩い前方一致スコア。"""
    if not a or not b:
        return 0.0
    shared = 0
    for n in range(3, min(len(a), len(b)) + 1):
        if a[:n] in b or b[:n] in a:
            shared = n
    return shared / max(len(a), len(b), 1)


def resolve_from_archive(
    channel_id: str, title: Optional[str], *, min_score: float = 0.4
) -> Optional[Dict[str, Any]]:
    """scenario archive の _index.json をタイトル照合して generated_by を引く。"""
    if not title or not channel_id:
        return None
    index_path = SCENARIOS_BASE / channel_id / "archive" / "_index.json"
    if not index_path.exists():
        return None
    try:
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(entries, list):
        return None

    target = _normalize_title(title)
    best: Optional[tuple] = None
    for e in entries:
        if not isinstance(e, dict):
            continue
        src = normalize(e.get("script_source") or e.get("generated_by"))
        if not src:
            continue
        for cand_title in (e.get("video_title"), e.get("title")):
            score = _title_similarity(target, _normalize_title(cand_title))
            if score >= min_score and (best is None or score > best[0]):
                best = (score, e, src)
    if not best:
        return None
    _, entry, src = best
    return {
        "script_source": src,
        "generated_by": entry.get("generated_by"),
        "resolved_from": "archive",
        "archive_file": entry.get("file"),
    }


def resolve_from_model_records(
    channel_id: str, title: Optional[str], *, min_score: float = 0.4
) -> Optional[Dict[str, Any]]:
    """model_scenario_records の selected 行をタイトル照合して引く。"""
    if not title or not channel_id:
        return None
    try:
        records = analytics_store.list_model_scenario_records(
            channel_id, limit=2000, selected_only=True
        )
    except Exception:
        return None
    target = _normalize_title(title)
    best: Optional[tuple] = None
    for r in records:
        src = normalize(r.get("model_name"))
        if not src:
            continue
        score = _title_similarity(target, _normalize_title(r.get("title")))
        if score >= min_score and (best is None or score > best[0]):
            best = (score, r, src)
    if not best:
        return None
    _, rec, src = best
    return {
        "script_source": src,
        "generated_by": rec.get("model_name"),
        "resolved_from": "model_records",
        "model_record_id": rec.get("id"),
    }


def resolve(
    channel_id: str,
    *,
    script_source: Optional[str] = None,
    generated_by: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """出所を解決する。解決できなければ None。"""
    explicit = normalize(script_source) or normalize(generated_by)
    if explicit:
        return {
            "script_source": explicit,
            "generated_by": generated_by or script_source,
            "resolved_from": "explicit",
        }
    return (
        resolve_from_archive(channel_id, title)
        or resolve_from_model_records(channel_id, title)
    )


def record(
    *,
    video_id: Optional[str],
    channel_id: str,
    script_source: Optional[str] = None,
    generated_by: Optional[str] = None,
    title: Optional[str] = None,
    url: str = "",
    is_short: bool = True,
    published_at: Optional[str] = None,
    resolved_from: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """投稿済み動画の台本出所を台帳に書く。

    出所が解決できない場合は書かずに {"ok": False, "skipped": "unresolved"} を返す
    （不明を片方のモデルに寄せると A/B 集計が静かに歪むため）。
    ここでの失敗は投稿処理を壊してはいけないので、呼び出し側は例外を握り潰す前提。
    """
    if not video_id:
        return {"ok": False, "skipped": "no_video_id"}

    resolved = resolve(
        channel_id,
        script_source=script_source,
        generated_by=generated_by,
        title=title,
    )
    if not resolved:
        return {"ok": False, "skipped": "unresolved", "video_id": video_id}

    payload = dict(extra or {})
    for k in ("archive_file", "model_record_id"):
        if k in resolved:
            payload[k] = resolved[k]

    analytics_store.upsert_video_script_source(
        video_id=video_id,
        channel_id=channel_id,
        script_source=resolved["script_source"],
        generated_by=resolved.get("generated_by"),
        title=title,
        url=url or f"https://youtube.com/watch?v={video_id}",
        is_short=is_short,
        published_at=published_at,
        resolved_from=resolved_from or resolved.get("resolved_from"),
        extra=payload,
    )

    # model_scenario_records 側の video_id も埋める（これまで常に NULL だった）。
    if title:
        try:
            analytics_store.link_model_record_by_title(channel_id, title, video_id)
        except Exception:
            pass

    return {
        "ok": True,
        "video_id": video_id,
        "script_source": resolved["script_source"],
        "resolved_from": resolved_from or resolved.get("resolved_from"),
    }


def get(video_id: str) -> Optional[Dict[str, Any]]:
    return analytics_store.get_video_script_source(video_id)


def list_for_channel(channel_id: Optional[str] = None, *, limit: int = 1000) -> List[Dict[str, Any]]:
    return analytics_store.list_video_script_sources(channel_id, limit=limit)


def counts_by_channel() -> Dict[str, Dict[str, int]]:
    """{channel_id: {"claude": n, "gpt": n}} — 溜まり具合の確認用。"""
    out: Dict[str, Dict[str, int]] = {}
    for row in analytics_store.list_video_script_sources(limit=10000):
        ch = row.get("channel_id") or "?"
        src = row.get("script_source") or "?"
        out.setdefault(ch, {CLAUDE: 0, GPT: 0})
        out[ch][src] = out[ch].get(src, 0) + 1
    return out


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="台本出所（Claude/GPT）台帳")
    ap.add_argument("--channel", help="チャンネルID で絞る")
    ap.add_argument("--counts", action="store_true", help="チャンネル別の本数だけ出す")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    if args.counts:
        for ch, c in sorted(counts_by_channel().items()):
            total = sum(c.values())
            print(f"{ch:22s} claude={c.get(CLAUDE, 0):3d}  gpt={c.get(GPT, 0):3d}  計={total}")
        return

    for r in list_for_channel(args.channel, limit=args.limit):
        print(
            f"{r['video_id']:12s} {r['channel_id']:20s} {r['script_source']:6s} "
            f"({r.get('resolved_from')}) {(r.get('title') or '')[:40]}"
        )


if __name__ == "__main__":
    _main()
