#!/usr/bin/env python3
"""投稿済み動画の台本出所（Claude / GPT）を台帳に後から書き込む。

台帳（analytics.db の video_script_source）はアップロード時に post_upload が
書くが、それ以前に投稿した分や、手作業で台本を差し込んで投稿した分は空になる。
このスクリプトは video_id と出所の対応を明示的に与えて埋める。

使い方:
  # 2026-08-27 に投稿した Claude 台本 11 本（既定の埋め込みバッチ）
  python backfill_script_source.py --batch 20260827-claude

  # 個別指定
  python backfill_script_source.py --set scp-lab=eTMuSrunkIY --source claude

  # JSON から（[{"channel_id": ..., "video_id": ..., "script_source": ...}, ...]）
  python backfill_script_source.py --file entries.json

  # 書かずに確認だけ
  python backfill_script_source.py --batch 20260827-claude --dry-run

タイトルと公開日時は YouTube Data API から補完する（取れなければ空のまま。
台帳の主キーは video_id なので、後から再実行すれば上書きで埋まる）。
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from pipeline.analytics import script_source as ss  # noqa: E402


# 2026-08-27 の一斉投稿。11ch すべて Claude が書いたショート台本。
# この回は台本を対話で書いて SHORT_SCENARIO_PATH 経由でレンダしたため、
# 生成器の generated_by 経路（gpt/claude の自動コンペ）を通っていない。
BATCHES: Dict[str, Dict[str, Any]] = {
    "20260827-claude": {
        "script_source": "claude",
        "note": "2026-08-27 一斉投稿。台本は対話で作成（in-session Claude）。",
        "videos": {
            "scp-lab": "eTMuSrunkIY",
            "daily-science": "oOgvPuK0Ib0",
            "pokemon-lab": "P_Xoy67_Lm8",
            "yokai-watch": "bT9_GYofA_w",
            "2ch-matome": "v9CmgSdcTs4",
            "fake-paper": "b4o3CXX6J9w",
            "company-facts": "dPkVQBSCzXs",
            "akashic-librarian": "B_F721NK9Oo",
            "clip-lab": "-RJilEKS3L0",
            "clip-fukada": "PMRxu_8hIt4",
            "clip-kaneko": "-ft7KCmlOEE",
        },
    },
}


def _fetch_snippets(channel_id: str, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """YouTube Data API から title / publishedAt を引く（失敗しても空を返す）。"""
    try:
        from pipeline.youtube_analytics import _build_data_service

        data = _build_data_service(channel_id)
        if not data:
            return {}
        resp = (
            data.videos()
            .list(part="snippet", id=",".join(video_ids[:50]))
            .execute()
        )
    except Exception as e:
        print(f"   ⚠️ snippet 取得失敗 [{channel_id}]: {e}")
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for it in resp.get("items", []) or []:
        sn = it.get("snippet") or {}
        out[it.get("id")] = {
            "title": sn.get("title"),
            "published_at": sn.get("publishedAt"),
        }
    return out


def _entries_from_archive(
    channels: Optional[List[str]], min_score: float
) -> List[Dict[str, Any]]:
    """既に実績スナップショットがある動画を scenario archive とタイトル照合して埋める。

    過去の投稿は generated_by が scenario archive の _index.json に残っているが、
    video_id が付いていない。ここで両者を突き合わせ、A/B 集計の母数を過去分にも
    広げる。照合はタイトルの緩い前方一致なので、確度の低いものは min_score で落とす。
    """
    from pipeline.analytics import store as analytics_store

    if channels:
        target_channels = channels
    else:
        base = Path(__file__).parent.parent / "data" / "channels"
        target_channels = sorted(p.stem for p in base.glob("*.json"))

    entries: List[Dict[str, Any]] = []
    for ch in target_channels:
        metrics = analytics_store.list_video_metrics(ch, limit=2000)
        hit = 0
        for m in metrics:
            title = m.get("title")
            resolved = ss.resolve_from_archive(ch, title, min_score=min_score)
            if not resolved:
                continue
            entries.append(
                {
                    "channel_id": ch,
                    "video_id": m["video_id"],
                    "script_source": resolved["script_source"],
                    "title": title,
                    "published_at": m.get("published_at"),
                    "note": f"archive照合 ({resolved.get('archive_file')})",
                    "resolved_from": "archive",
                }
            )
            hit += 1
        if metrics:
            print(f"  {ch:22s} {hit}/{len(metrics)} 本を archive と照合")
    return entries


def _entries_from_args(args: argparse.Namespace) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []

    if args.from_archive:
        entries.extend(_entries_from_archive(args.channel, args.min_score))

    if args.batch:
        batch = BATCHES.get(args.batch)
        if not batch:
            raise SystemExit(
                f"未知の batch: {args.batch}（既知: {', '.join(BATCHES)}）"
            )
        for ch, vid in batch["videos"].items():
            entries.append(
                {
                    "channel_id": ch,
                    "video_id": vid,
                    "script_source": batch["script_source"],
                    "note": batch.get("note"),
                }
            )

    if args.file:
        loaded = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise SystemExit("--file は [{channel_id, video_id, script_source}] の配列")
        entries.extend(loaded)

    for pair in args.set or []:
        if "=" not in pair:
            raise SystemExit(f"--set は channel_id=video_id 形式: {pair}")
        ch, vid = pair.split("=", 1)
        entries.append(
            {
                "channel_id": ch.strip(),
                "video_id": vid.strip(),
                "script_source": args.source,
            }
        )

    for e in entries:
        if not e.get("script_source"):
            e["script_source"] = args.source
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description="台本出所の後追い記録")
    ap.add_argument("--batch", help=f"埋め込みバッチ名（{', '.join(BATCHES)}）")
    ap.add_argument("--file", help="エントリ JSON ファイル")
    ap.add_argument("--set", action="append", help="channel_id=video_id（複数可）")
    ap.add_argument("--from-archive", action="store_true",
                    help="実績スナップショットのある過去動画を scenario archive と"
                         "タイトル照合して一括で埋める")
    ap.add_argument("--channel", action="append",
                    help="--from-archive の対象チャンネル（既定は全部）")
    ap.add_argument("--min-score", type=float, default=0.55,
                    help="--from-archive のタイトル一致スコア下限（既定 0.55）")
    ap.add_argument("--source", default="claude", choices=["claude", "gpt"],
                    help="--set / batch 未指定時の出所（既定 claude）")
    ap.add_argument("--is-short", dest="is_short", action="store_true", default=True)
    ap.add_argument("--long", dest="is_short", action="store_false",
                    help="ロング動画として記録する")
    ap.add_argument("--no-api", action="store_true",
                    help="YouTube API を叩かず title/published_at を空のまま記録")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    entries = _entries_from_args(args)
    if not entries:
        ap.error("--batch / --file / --set のいずれかを指定してください")

    # タイトルが未解決のものだけ、チャンネルごとにまとめて snippet を引く
    by_channel: Dict[str, List[str]] = {}
    for e in entries:
        if not e.get("title"):
            by_channel.setdefault(e["channel_id"], []).append(e["video_id"])

    snippets: Dict[str, Dict[str, Any]] = {}
    if not args.no_api:
        for ch, vids in by_channel.items():
            snippets.update(_fetch_snippets(ch, vids))

    written = 0
    skipped = 0
    for e in entries:
        vid = e["video_id"]
        sn = snippets.get(vid) or {}
        title = e.get("title") or sn.get("title")
        published_at = e.get("published_at") or sn.get("published_at")
        label = f"{e['channel_id']:20s} {vid:12s} {e['script_source']:6s}"
        if args.dry_run:
            print(f"[dry-run] {label} {(title or '(title不明)')[:44]}")
            continue
        res = ss.record(
            video_id=vid,
            channel_id=e["channel_id"],
            script_source=e["script_source"],
            title=title,
            is_short=args.is_short,
            published_at=published_at,
            resolved_from=e.get("resolved_from") or "manual",
            extra={"note": e.get("note") or "backfill_script_source.py"},
        )
        if res.get("ok"):
            written += 1
            print(f"✅ {label} {(title or '(title不明)')[:44]}")
        else:
            skipped += 1
            print(f"⚠️ {label} 記録せず: {res}")

    if not args.dry_run:
        print(f"\n記録 {written} 件 / スキップ {skipped} 件")
        print("\n現在の台帳（チャンネル別）:")
        for ch, c in sorted(ss.counts_by_channel().items()):
            print(f"  {ch:22s} claude={c.get('claude', 0):3d}  gpt={c.get('gpt', 0):3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
