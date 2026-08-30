#!/usr/bin/env python3
"""海外バイラル動画の翻訳切り抜きを生成 →（任意で）YouTube に公開

投稿先は **既存の切り抜きラボ（clip-lab）**。専用チャンネルは作らず、
17:45 の国内切り抜きと 20:45 の海外バイラルを同じチャンネルで回す
（2026-08-30 の運用決定）。エンジンは常に `viral` を明示して呼ぶので、
`clip.engine`（国内切り抜き用の local）とは干渉しない。

  python3 run_viral_clip.py                 # 1本生成（投稿なし）
  python3 run_viral_clip.py --upload        # 生成して投稿（public）
  python3 run_viral_clip.py --acquire       # 調達とゲート判定だけ確認（DLしない）
  python3 run_viral_clip.py --dry-run       # 区間選定・翻訳まで（レンダリングなし）
  python3 run_viral_clip.py --check         # 依存と認証の診断
  python3 run_viral_clip.py --add-url URL   # TikTok / IG / X の URL を手動キューへ

env:
  CLIP_CHANNEL_ID       対象チャンネル（既定 clip-lab）
  REDDIT_CLIENT_ID      Reddit OAuth（無いと RSS 経路に落ちる）
  REDDIT_CLIENT_SECRET
  ANTHROPIC_API_KEY     翻訳・フック文の生成に必須（Claude 固定・3回まで再試行）

パイプラインの構成は docs/CLIP_VIRAL_CHANNEL.md を参照。
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

from pipeline.clip_factory import generate_clip  # noqa: E402
from pipeline.clip_factory.pipeline import VIRAL_ENGINE, load_channel_raw  # noqa: E402

#: 海外バイラル枠の投稿先。専用チャンネルは作らず clip-lab に同居する。
DEFAULT_CHANNEL_ID = "clip-lab"


def check(channel_id: str) -> int:
    """動かすのに必要なものが揃っているかを段階的に診断する。"""
    from pipeline.clip_factory import asr as asr_mod
    from pipeline.clip_factory import viral_sources as vs

    clip_cfg = load_channel_raw(channel_id).get("clip") or {}
    cfg = vs.cfg(clip_cfg)

    print("========= 海外バイラル切り抜き 診断 =========")
    print(f"channel        : {channel_id}（国内切り抜きと同居）")
    print(f"engine         : {VIRAL_ENGINE}（clip.engine="
          f"{clip_cfg.get('engine')} は 17:45 の国内枠用）")
    print(f"viral_sources  : {'有効' if vs.is_enabled(clip_cfg) else '無効'}")
    print(f"auth_mode      : {cfg.get('auth_mode') or 'auto'}")
    subs = [s if isinstance(s, str) else s.get("name")
            for s in (cfg.get("subreddits") or [])]
    print(f"subreddits     : {', '.join(str(s) for s in subs)}")

    ng = []

    cid, secret = vs.reddit_credentials()
    if cid:
        token = vs.reddit_token(user_agent=str(cfg.get("user_agent")
                                               or vs.DEFAULT_USER_AGENT))
        print(f"Reddit OAuth   : {'✅ トークン取得OK' if token else '❌ トークン取得に失敗'}"
              f"（secret {'あり' if secret else 'なし'}）")
        if not token:
            ng.append("Reddit OAuth のトークンを取得できない")
    else:
        print("Reddit OAuth   : ⚠️ REDDIT_CLIENT_ID 未設定 → RSS 経路に落ちる"
              "（スコア・NSFWフラグが取れない）")

    backend = asr_mod.available_backend()
    print(f"Whisper        : {'✅ ' + backend if backend else '❌ 未導入'}")
    if not backend:
        ng.append("faster-whisper が入っていない（pip install faster-whisper）")

    try:
        from pipeline import claude_client
        if claude_client.has_api_key():
            print("Claude         : ✅ ANTHROPIC_API_KEY あり")
        else:
            print(f"Claude         : ❌ {claude_client.unavailable_reason()}")
            ng.append("Claude が使えない（翻訳・フック文が作れないので必須）")
    except Exception as e:
        print(f"Claude         : ❌ claude_client を読み込めません: {e}")
        ng.append("claude_client を読み込めない")

    ch = load_channel_raw(channel_id)
    if not ch.get("youtube_channel_id"):
        print("YouTube        : ⚠️ youtube_channel_id 未設定（投稿はできない）")
    else:
        print(f"YouTube        : ✅ {ch['youtube_channel_id']}")

    gate = vs.gate_cfg(clip_cfg)
    privacy = ((ch.get("publish_settings") or {}).get("default_privacy") or "public")
    review = vs.requires_review(clip_cfg)
    print(f"内容ゲート     : over_18={'許可' if gate.get('allow_over_18') else '禁止'}"
          f" / 目視レビュー={'あり(private投稿)' if review else 'なし'}")
    print(f"公開設定       : {'private（レビュー待ち）' if review else privacy}")

    if ng:
        print("\n❌ 足りないもの:")
        for x in ng:
            print(f"   - {x}")
        return 1
    print("\n✅ 生成に必要なものは揃っています")
    return 0


def acquire(channel_id: str) -> int:
    from pipeline.clip_factory import viral_sources as vs

    clip_cfg = load_channel_raw(channel_id).get("clip") or {}
    res = vs.acquire(clip_cfg)
    if res.get("error"):
        print(f"❌ {res['error']}")
        return 1
    print(f"\n✅ 採用候補 {len(res['ok'])} 件 / ゲート除外 {len(res['blocked'])} 件 "
          f"/ 既出 {res['skipped_seen']} 件")
    for r in res["ok"][:20]:
        print(f"  [{r['score']:>7}] {r['community']:<24} {r['duration_sec']:>5}s  "
              f"{r['title'][:56]}")
    if res["blocked"]:
        print("\n🚫 ゲートで除外:")
        for r in res["blocked"][:10]:
            print(f"  {r['title'][:46]:<48} … {r['gate_reason'][:50]}")
    return 0


def add_url(url: str, note: str = "") -> int:
    from pipeline.clip_factory import viral_sources as vs

    vs.MANUAL_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with vs.MANUAL_QUEUE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"url": url, "note": note}, ensure_ascii=False) + "\n")
    print(f"✅ 手動キューに追加しました: {url}\n   {vs.MANUAL_QUEUE}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="海外バイラル動画の翻訳切り抜き")
    ap.add_argument("--channel",
                    default=os.environ.get("CLIP_CHANNEL_ID", DEFAULT_CHANNEL_ID))
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--upload", action="store_true", help="YouTube に投稿する")
    ap.add_argument("--privacy", default=None, help="public / unlisted / private")
    ap.add_argument("--dry-run", action="store_true", help="レンダリングしない")
    ap.add_argument("--acquire", action="store_true", help="調達とゲート判定だけ")
    ap.add_argument("--check", action="store_true", help="依存・認証の診断")
    ap.add_argument("--add-url", default=None, help="手動キューに URL を積む")
    ap.add_argument("--note", default="", help="--add-url のメモ")
    args = ap.parse_args()

    if args.check:
        return check(args.channel)
    if args.acquire:
        return acquire(args.channel)
    if args.add_url:
        return add_url(args.add_url, args.note)

    res = generate_clip(
        args.channel, count=args.count, upload=args.upload,
        privacy=args.privacy, dry_run=args.dry_run,
        # 同居先の clip.engine（国内切り抜きの local）に引っ張られないよう明示する
        engine=VIRAL_ENGINE,
    )
    if not res.get("ok"):
        print(f"\n❌ {res.get('error')}")
        for r in (res.get("rejected") or []):
            print(f"   - {r['title'][:40]}: {r['reason'][:70]}")
        return 1

    print(f"\n✅ engine={res['engine']} / {len(res['clips'])} 本")
    for clip in res["clips"]:
        print(f"  🎬 {clip.get('video_path')}")
        print(f"     title  : {clip.get('title')}")
        print(f"     privacy: {clip.get('privacy')}")
        up = clip.get("upload") or {}
        if up:
            print(f"     upload : {up.get('url') or up.get('error')}")
    print(f"  📝 meta: {res.get('meta_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
