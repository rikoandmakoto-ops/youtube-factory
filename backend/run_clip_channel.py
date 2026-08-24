#!/usr/bin/env python3
"""切り抜きチャンネルの動画を生成 →（任意で）YouTube に公開

  python run_clip_channel.py                    # clip-lab で1本生成（投稿なし）
  python run_clip_channel.py --count 2 --upload # 2本作って投稿
  python run_clip_channel.py --list             # 自社在庫を表示
  python run_clip_channel.py --list --external  # 許諾済み外部素材も含めて表示
  python run_clip_channel.py --acquire          # 許諾判定の結果だけ確認（DLしない）
  python run_clip_channel.py --dry-run          # 区間選定だけ確認（レンダリングなし）
  python run_clip_channel.py --noimos-check     # NoimosAI の接続診断（キー/WS/ツール）

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
from typing import Optional

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
from pipeline.clip_factory.pipeline import load_channel_raw  # noqa: E402


def noimos_check(channel_id: str) -> int:
    """NoimosAI への到達性を段階的に診断する。

    キー未設定でも「どこで止まっているか」が分かるように、各段を個別に報告する。
    """
    from pipeline.clip_factory.engines import noimos as engine
    from pipeline.clip_factory.engines import noimos_client as nc

    clip_cfg = (load_channel_raw(channel_id).get("clip") or {})
    cfg = clip_cfg.get("noimos") or {}

    print("========= NoimosAI 接続診断 =========")
    print(f"channel      : {channel_id}")
    print(f"clip.engine  : {clip_cfg.get('engine')}")
    print(f"mode         : {cfg.get('mode') or 'api'}")
    endpoint = str(cfg.get("api_endpoint") or os.environ.get("NOIMOS_API_ENDPOINT")
                   or nc.DEFAULT_API_ENDPOINT)
    print(f"api_endpoint : {endpoint}")
    print(f"region       : {cfg.get('region') or nc.infer_region_from_timezone()}")
    print(f"agent 実行先 : {nc.agent_endpoint(endpoint)}")
    print(f"deliver      : {cfg.get('deliver_source') or 'upload'}")

    reason = engine.preflight(clip_cfg)
    if reason:
        print(f"\n❌ preflight NG: {reason}")
        return 1
    print("\n✅ preflight OK（認証情報あり）")

    try:
        client = nc.client_from_env(cfg)
    except nc.NoimosError as e:
        print(f"❌ クライアント生成に失敗: {e}")
        return 1

    try:
        res = client.validate_key()
        print(f"✅ APIキー検証: valid={res.get('valid')} {res.get('error') or ''}")
    except nc.NoimosError as e:
        print(f"❌ APIキー検証に失敗: {e}")
        return 1

    try:
        spaces = client.list_workspaces()
        print(f"✅ ワークスペース {len(spaces)} 件")
        for s in spaces[:10]:
            print(f"     - {s.get('id')}  {s.get('name')}")
    except nc.NoimosError as e:
        print(f"❌ ワークスペース取得に失敗: {e}")
        return 1

    try:
        tools = client.list_tools()
        print(f"\n✅ ツール {len(tools)} 件（切り抜き関連を優先表示）")
        keywords = ("clip", "short", "video", "highlight", "media", "crop", "trim")
        hits = [t for t in tools
                if any(k in json.dumps(t, ensure_ascii=False).lower() for k in keywords)]
        for t in (hits or tools)[:40]:
            print(f"     - {t.get('server')}/{t.get('name')}"
                  f"{' [billed]' if t.get('billed') else ''}"
                  f"  {str(t.get('description') or '')[:80]}")
        if hits:
            print(f"\n   ℹ️ 上は動画/切り抜きに関係しそうな {len(hits)} 件だけ。"
                  f"全 {len(tools)} 件を見るには --noimos-tools を使ってください。")
    except nc.NoimosError as e:
        print(f"⚠️ ツール一覧の取得に失敗（チャット経路は使える可能性あり）: {e}")

    print("\n次の一手: python3 run_clip_channel.py --count 1 で実際に切り抜きを依頼する")
    return 0


def build_mirror(channel_id: str, limit: Optional[int]) -> int:
    """TCC 保護外へ素材をミラーする（ターミナルから実行すること）。"""
    from pipeline.clip_factory import sources as src_mod

    clip_cfg = load_channel_raw(channel_id).get("clip") or {}
    source_ids = [str(s.get("channel_id")) for s in (clip_cfg.get("sources") or [])
                  if s.get("channel_id")]
    print(f"🪞 ミラー作成: {', '.join(source_ids)} → {src_mod.MIRROR_BASE}")
    print("   （ハードリンクなのでディスクは消費しません）\n")

    res = src_mod.build_mirror(source_ids, limit=limit)
    print(f"✅ 新規リンク {len(res['linked'])} 本 / 既存 {res['already']} 本")
    if res["failed"]:
        print(f"⚠️ 失敗 {len(res['failed'])} 本")
        for f in res["failed"][:10]:
            print(f"   - {f}")
    print(f"\n置き場: {res['mirror_base']}")
    print("これで launchd 配下の backend からも素材を読めるようになります。")
    return 0


def acquire_external(channel_id: str, *, download: bool, limit: int,
                     force: bool) -> int:
    """外部素材を調達して結果を表示する。"""
    from pipeline.clip_factory import acquisition as acq

    clip_cfg = dict(load_channel_raw(channel_id).get("clip") or {})
    if force and not acq.is_enabled(clip_cfg):
        # 設定を書き換えずに一度だけ試す（調達結果を見てから有効化を判断できる）
        ext = dict(clip_cfg.get("external_sources") or {})
        ext["enabled"] = True
        clip_cfg["external_sources"] = ext
        print("ℹ️ --force により external_sources を一時的に有効化して実行します"
              "（channel JSON は書き換えません）\n")

    res = acq.acquire(clip_cfg, download=download, limit=limit)
    if res.get("skipped"):
        print(f"⏭️ スキップ: {res['skipped']}")
        print("   一度だけ試すなら --acquire --force を使ってください。")
        return 0
    if res.get("error"):
        print(f"❌ {res['error']}")
        return 1

    clippable = res.get("clippable") or []
    theme_only = res.get("theme_only") or []

    print(f"\n✂️ 切り抜き可 (clippable): {len(clippable)} 本")
    for c in clippable[:20]:
        print(f"  - [{c['license']}] {c['title'][:56]}")
        print(f"      {c['channel_title']} / {c['duration_sec']:.0f}s / "
              f"{c['view_count']:,} views")
        print(f"      理由: {c['reason']}")
        print(f"      {c['url']}")

    print(f"\n📰 テーマ専用 (theme_only / 映像は使わない): {len(theme_only)} 本")
    for c in theme_only[:20]:
        print(f"  - {c['title'][:60]}")
        print(f"      {c['channel_title']} / {c['view_count']:,} views / "
              f"license={c['license']}")

    excluded = res.get("excluded_by_duration") or {}
    for key, label in (("too_long", "長すぎ"), ("too_short", "短すぎ")):
        rows = excluded.get(key) or []
        if rows:
            print(f"\n⏱️ 許諾ありだが尺で除外（{label}）: {len(rows)} 本")
            for c in rows[:5]:
                print(f"  - {c['title'][:50]} / {c['duration_sec']:.0f}s")

    if res.get("downloaded"):
        print(f"\n⬇️ ダウンロード済み {len(res['downloaded'])} 本")
        for p in res["downloaded"]:
            print(f"  - {p}")
    return 0


def noimos_tools(channel_id: str) -> int:
    """ツールカタログを全件 JSON で吐く。"""
    from pipeline.clip_factory.engines import noimos_client as nc
    cfg = ((load_channel_raw(channel_id).get("clip") or {}).get("noimos") or {})
    try:
        tools = nc.client_from_env(cfg).list_tools()
    except nc.NoimosError as e:
        print(f"❌ {e}")
        return 1
    print(json.dumps(tools, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="切り抜きショートを生成する")
    ap.add_argument("--channel", default=os.environ.get("CLIP_CHANNEL_ID", "clip-lab"))
    ap.add_argument("--count", type=int, default=1, help="生成本数")
    ap.add_argument("--source", default=None, help="元動画のタイトル（省略時は自動選択）")
    ap.add_argument("--upload", action="store_true", help="YouTube に投稿する")
    ap.add_argument("--privacy", default=os.environ.get("CLIP_PRIVACY") or None)
    ap.add_argument("--dry-run", action="store_true", help="レンダリングせず区間だけ出す")
    ap.add_argument("--list", action="store_true", help="在庫一覧を表示して終了")
    ap.add_argument("--external", action="store_true",
                    help="--list で外部（許諾済み）素材も含める（API + yt-dlp を叩くので遅い）")
    ap.add_argument("--out", default=None, help="出力先ディレクトリ")
    ap.add_argument("--noimos-check", action="store_true",
                    help="NoimosAI の接続診断をして終了")
    ap.add_argument("--noimos-tools", action="store_true",
                    help="NoimosAI のツールカタログを JSON で出して終了")
    ap.add_argument("--acquire", action="store_true",
                    help="外部素材を調達して一覧表示（既定はダウンロードしない）")
    ap.add_argument("--acquire-download", action="store_true",
                    help="--acquire に加えて clippable な素材を実際に落とす")
    ap.add_argument("--force", action="store_true",
                    help="--acquire で external_sources.enabled=false でも一度試す")
    ap.add_argument("--mirror", action="store_true",
                    help="素材をTCC保護外(~/Movies)へハードリンクしてautopilotから読めるようにする")
    ap.add_argument("--mirror-limit", type=int, default=None,
                    help="--mirror で作る本数の上限")
    args = ap.parse_args()

    if args.noimos_check:
        return noimos_check(args.channel)
    if args.noimos_tools:
        return noimos_tools(args.channel)
    if args.mirror:
        return build_mirror(args.channel, args.mirror_limit)
    if args.acquire or args.acquire_download:
        return acquire_external(args.channel, download=args.acquire_download,
                                limit=args.count, force=args.force)

    if args.list:
        stock = list_available_sources(args.channel, include_external=args.external)
        remaining = sum(s["remaining_clips"] for s in stock)
        print(f"📦 元動画 {len(stock)} 本 / 残り切り抜き枠 {remaining} 本\n")
        for s in sorted(stock, key=lambda x: -x["remaining_clips"]):
            mark = "🌐" if s.get("is_external") else "🏠"
            print(f"  {mark} [{s['source_channel_id']}] {s['title'][:52]}")
            print(f"      {s['duration']:.0f}s / {s['line_count']}行 / 残り{s['remaining_clips']}本")
            if s.get("is_external"):
                print(f"      🔏 {(s.get('permission') or {}).get('reason', '')}")
        if not args.external:
            print("\nℹ️ 外部（許諾済み）素材も見るには --external を付けてください。")
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
