#!/usr/bin/env python3
"""生成済みだが未投稿のショートを、出力フォルダから後追いで公開する

    python3 backend/republish_short.py <channel_id> --dir "<出力フォルダ>"
    python3 backend/republish_short.py scp-lab --dir ~/Desktop/動画出力用/xxx --dry-run

autopilot は「生成 → 予約時刻に自動公開」の2段構えで、公開側だけが失敗すると
（例: OAuth トークン失効）動画はフォルダに残ったまま投稿されない。その取り残しを
手で拾うためのスクリプト。タイトル・タグ・サムネ・再生リスト投入・前回/次回リンク・
自動コメントまで、api_phase4._start_single_short_publish と同じ経路を通す。

出力フォルダの中身は generate_all() の命名規約に従う:
    <channel_id>_ショート.mp4 / _ショート_サムネイル.png / _ショート_説明文.txt
"""

import argparse
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

# Fernet 鍵は JWT_SECRET 由来。.env を読まないとトークンを復号できない。
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from channels import ChannelManager  # noqa: E402
from pipeline import youtube_oauth as yt_oauth  # noqa: E402
from pipeline import youtube_pair_publisher as pair_pub  # noqa: E402


def _find(out_dir: Path, channel_id: str, suffix: str):
    p = out_dir / f"{channel_id}{suffix}"
    if p.exists():
        return p
    # チャンネルIDでなく別名で書き出されている場合に備えて後方一致で拾う
    for f in out_dir.iterdir():
        if f.name.endswith(suffix):
            return f
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("channel_id")
    ap.add_argument("--dir", required=True, help="生成結果の出力フォルダ")
    ap.add_argument(
        "--title",
        default=None,
        help="投稿タイトル（既定: フォルダ名 + 【ショート】＝ autopilot と同じ）",
    )
    ap.add_argument("--privacy", default=None, help="既定: チャンネル設定の default_privacy")
    ap.add_argument("--publish-at", default=None, help="RFC3339。指定すると予約公開")
    ap.add_argument("--no-thumbnail", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out_dir = Path(os.path.expanduser(args.dir))
    if not out_dir.is_dir():
        print(f"❌ フォルダがありません: {out_dir}")
        return 1

    ch = ChannelManager().get(args.channel_id)
    if not ch:
        print(f"❌ 未知のチャンネル: {args.channel_id}")
        return 1

    video = _find(out_dir, args.channel_id, "_ショート.mp4")
    thumb = _find(out_dir, args.channel_id, "_ショート_サムネイル.png")
    desc_file = _find(out_dir, args.channel_id, "_ショート_説明文.txt")
    if not video:
        print(f"❌ ショート動画が見つかりません: {out_dir}")
        return 1

    desc = pair_pub._read_desc(str(desc_file) if desc_file else None)
    # 説明文に「タイトル:」行が無い通常ケースは autopilot と同じ組み立てにする
    title = args.title or desc.get("title") or f"{out_dir.name}【ショート】"
    privacy = args.privacy or ch.get_publish_settings().get("default_privacy") or "public"

    from api_phase4 import _post_auto_comment, _run_post_upload, _with_title_tags

    tags = _with_title_tags(ch.get_upload_tags(is_short=True), title)

    print(f"📺 {args.channel_id} ({ch.name})")
    print(f"🎬 {video}  ({video.stat().st_size / 1024 / 1024:.1f}MB)")
    print(f"🖼️  {thumb if thumb and not args.no_thumbnail else '（サムネなし）'}")
    print(f"📝 タイトル: {title}")
    print(f"🏷️  タグ: {tags}")
    print(f"🔓 公開設定: {privacy}{' / 予約 ' + args.publish_at if args.publish_at else ''}")
    print(f"📄 説明文: {len(desc.get('body') or '')} 文字")
    if args.dry_run:
        print("\n--dry-run のため投稿しません")
        return 0

    creds = yt_oauth.get_credentials_for(args.channel_id)
    if not creds:
        err = yt_oauth.get_auth_error_for(args.channel_id)
        print(f"\n❌ OAuth トークンが使えません: {err['detail'] if err else '未連携'}")
        print("   → ダッシュボードで再認可してから、このコマンドをもう一度実行する")
        return 2

    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    started = time.time()
    res = pair_pub._upload_one(
        youtube,
        video_path=str(video),
        title=title,
        description=desc.get("body") or "",
        tags=tags,
        category_id=ch.get_category() or "27",
        privacy=privacy,
        is_short=True,
        youtube_channel_id=ch.youtube_channel_id,
        publish_at=args.publish_at,
        thumbnail_path=None if args.no_thumbnail else (str(thumb) if thumb else None),
        progress_cb=lambda pct: print(f"  ⬆️  {pct}%", flush=True),
    )
    print(f"\n🚀 公開完了 ({time.time() - started:.0f}秒): {res.get('url')}")

    # 再生リスト投入・前回/次回リンク・自動コメント（autopilot と同じ後処理）
    _run_post_upload(
        channel_id=args.channel_id,
        video_id=res.get("video_id"),
        title=title,
        url=res.get("url") or "",
        is_short=True,
    )
    _post_auto_comment(
        channel_id=args.channel_id,
        video_id=res.get("video_id"),
        title=title,
        is_short=True,
        publish_at=args.publish_at,
    )
    # 後処理は run_async / post_for_video_async のスレッド。終わるまで待つ。
    time.sleep(20)
    return 0


if __name__ == "__main__":
    sys.exit(main())
