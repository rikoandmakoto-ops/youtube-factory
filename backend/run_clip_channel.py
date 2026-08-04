#!/usr/bin/env python3
"""切り抜きチャンネルの動画を生成 →（任意で）YouTube に公開

  python run_clip_channel.py                    # clip-lab で1本生成（投稿なし）
  python run_clip_channel.py --count 2 --upload # 2本作って投稿
  python run_clip_channel.py --list             # 切り抜ける元動画の在庫を表示
  python run_clip_channel.py --dry-run          # 区間選定だけ確認（レンダリングなし）

env:
  CLIP_CHANNEL_ID   対象チャンネル（既定 clip-lab）
  CLIP_PRIVACY      公開設定（既定はチャンネルJSONの default_privacy）
  NOIMOS_API_KEY    clip.engine="noimos" のとき必要
"""

import argparse
import json
import os
import sys
from pathlib import Path

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

from pipeline.clip_factory import generate_clip, list_available_sources  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="切り抜きショートを生成する")
    ap.add_argument("--channel", default=os.environ.get("CLIP_CHANNEL_ID", "clip-lab"))
    ap.add_argument("--count", type=int, default=1, help="生成本数")
    ap.add_argument("--source", default=None, help="元動画のタイトル（省略時は自動選択）")
    ap.add_argument("--upload", action="store_true", help="YouTube に投稿する")
    ap.add_argument("--privacy", default=os.environ.get("CLIP_PRIVACY") or None)
    ap.add_argument("--dry-run", action="store_true", help="レンダリングせず区間だけ出す")
    ap.add_argument("--list", action="store_true", help="在庫一覧を表示して終了")
    ap.add_argument("--out", default=None, help="出力先ディレクトリ")
    args = ap.parse_args()

    if args.list:
        stock = list_available_sources(args.channel)
        remaining = sum(s["remaining_clips"] for s in stock)
        print(f"📦 元動画 {len(stock)} 本 / 残り切り抜き枠 {remaining} 本\n")
        for s in sorted(stock, key=lambda x: -x["remaining_clips"]):
            print(f"  [{s['source_channel_id']}] {s['title'][:52]}")
            print(f"      {s['duration']:.0f}s / {s['line_count']}行 / 残り{s['remaining_clips']}本")
        return 0

    res = generate_clip(
        args.channel,
        count=args.count,
        source_title=args.source,
        out_dir=Path(args.out) if args.out else None,
        upload=args.upload,
        privacy=args.privacy,
        dry_run=args.dry_run,
    )

    print("\n========= RESULT =========")
    if not res.get("ok"):
        print(f"❌ {res.get('error')}")
        return 1
    print(f"engine: {res['engine']}")
    print(f"source: [{res['source']['source_channel_id']}] {res['source']['title']}")
    for c in res["clips"]:
        seg = c.get("segment") or {}
        print(f"\n  ▶ {c.get('clip_id')}")
        print(f"    区間:  {seg.get('start')}s 〜 {seg.get('end')}s ({seg.get('duration')}s)")
        print(f"    hook:  {c.get('hook')}")
        print(f"    title: {c.get('title')}")
        print(f"    video: {c.get('video_path')}")
        up = c.get("upload")
        if up:
            print(f"    url:   {up.get('url') or up.get('error')}")
    print(f"\nmeta: {res.get('meta_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
