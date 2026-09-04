#!/usr/bin/env python3
"""ChatGPT 画像ブリッジの操作 CLI。

Claude in Chrome を持つセッション（＝キューのワーカー）と、人間が両方これを使う。
手順の全体像は `docs/CHATGPT_IMAGE_BRIDGE.md`。

    python3 scripts/image_bridge.py status
    python3 scripts/image_bridge.py thread set scp-lab https://chatgpt.com/c/xxxx
    python3 scripts/image_bridge.py list
    python3 scripts/image_bridge.py show <req_id>          # 送るプロンプトを出す
    python3 scripts/image_bridge.py deliver <req_id> path/to/downloaded.png
    python3 scripts/image_bridge.py fail <req_id> "理由"
    python3 scripts/image_bridge.py gc
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pipeline import chatgpt_image_bridge as bridge  # noqa: E402


def cmd_status(_args: argparse.Namespace) -> int:
    print(json.dumps(bridge.status(), ensure_ascii=False, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    reqs = bridge.pending_requests()
    if not reqs:
        print("pending なし")
        return 0
    for r in reqs[: args.limit]:
        head = (r.get("prompt") or "").replace("\n", " ")[:70]
        print(
            f"{r['id']}  ch={r.get('channel_id') or '-':<18} "
            f"purpose={r.get('purpose'):<22} size={r.get('size'):<10} x{r.get('request_count', 1)}"
        )
        print(f"    thread: {r.get('thread_url') or '(未登録)'}")
        print(f"    {head}…")
    if len(reqs) > args.limit:
        print(f"… 他 {len(reqs) - args.limit} 件")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    req = bridge.load_request(args.req_id)
    if not req:
        print(f"依頼が見つかりません: {args.req_id}", file=sys.stderr)
        return 1
    if args.prompt_only:
        print(req["prompt"])
        return 0
    print(f"id:      {req['id']}")
    print(f"status:  {req.get('status')}")
    print(f"channel: {req.get('channel_id') or '-'}")
    print(f"purpose: {req.get('purpose')}")
    print(f"size:    {req.get('size')}  quality={req.get('quality')}")
    print(f"thread:  {req.get('thread_url') or '(未登録 — thread set で登録する)'}")
    print("--- prompt ---")
    print(req["prompt"])
    return 0


def cmd_deliver(args: argparse.Namespace) -> int:
    data = bridge.deliver(args.req_id, args.image)
    print(f"✅ 納品: {data['id']} → {data['image_path']}")
    print(f"   cache: {bridge.CACHE_DIR / (data['prompt_hash'] + '.png')}")
    return 0


def cmd_fail(args: argparse.Namespace) -> int:
    data = bridge.fail(args.req_id, args.reason)
    print(f"✋ failed: {data['id']} — {data['reason']}")
    return 0


def cmd_thread(args: argparse.Namespace) -> int:
    if args.action == "get":
        url = bridge.thread_url_for(args.channel_id)
        print(url or "(未登録)")
        return 0
    if not args.url:
        print("url が必要です", file=sys.stderr)
        return 1
    bridge.set_thread_url(args.channel_id, args.url, note=args.note or "")
    print(f"✅ {args.channel_id} → {args.url}")
    return 0


def cmd_gc(args: argparse.Namespace) -> int:
    print(json.dumps(bridge.gc(args.days), ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ChatGPT 画像ブリッジの操作")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="キューの状態").set_defaults(func=cmd_status)

    p = sub.add_parser("list", help="pending 依頼の一覧")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="依頼の詳細（ChatGPT に貼るプロンプト）")
    p.add_argument("req_id")
    p.add_argument("--prompt-only", action="store_true", help="プロンプト本文だけ出力")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("deliver", help="回収した画像を納品する")
    p.add_argument("req_id")
    p.add_argument("image")
    p.set_defaults(func=cmd_deliver)

    p = sub.add_parser("fail", help="処理できなかった依頼を落とす")
    p.add_argument("req_id")
    p.add_argument("reason")
    p.set_defaults(func=cmd_fail)

    p = sub.add_parser("thread", help="チャンネル ↔ ChatGPT スレッドの対応")
    p.add_argument("action", choices=["set", "get"])
    p.add_argument("channel_id", help="チャンネル ID（既定スレッドは _default）")
    p.add_argument("url", nargs="?")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_thread)

    p = sub.add_parser("gc", help="TTL 超過の pending を failed へ")
    p.add_argument("--days", type=float, default=None)
    p.set_defaults(func=cmd_gc)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
