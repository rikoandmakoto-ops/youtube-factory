#!/usr/bin/env python3
"""
あるチャンネルの OAuth クライアント (client_id / client_secret) を
別チャンネルに流用コピーするユーティリティ。

用途:
  GCP プロジェクト側のリダイレクトURI登録漏れ等で特定チャンネルの
  OAuth クライアントが redirect_uri_mismatch になる場合に、
  正常動作している別チャンネルの OAuth クライアントを流用する。

  OAuth クライアントは「アプリの識別子」であって YouTube アカウントには
  紐付かない。複数チャンネル(複数 Google アカウント)が同一 OAuth
  クライアントで認可しても問題ない。リダイレクトURIが共有できるのが利点。

実行前に backend/.env を読み込んで JWT_SECRET (Fernet鍵) を有効化すること。

例:
  python -m scripts.copy_oauth_client --from scp-lab --to daily-science
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _load_env() -> None:
    """backend/.env を環境変数へ流し込む(既存値は上書きしない)。"""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="src", required=True, help="コピー元 channel_id")
    ap.add_argument("--to", dest="dst", required=True, help="コピー先 channel_id")
    ap.add_argument(
        "--yes", action="store_true", help="確認プロンプトを省略して即適用"
    )
    args = ap.parse_args()

    _load_env()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pipeline import youtube_oauth as yo  # noqa: E402

    src_cfg = yo.get_oauth_client_for(args.src)
    if not src_cfg:
        print(f"[ERR] コピー元 '{args.src}' に OAuth クライアントがありません", file=sys.stderr)
        return 1

    dst_cfg = yo.get_oauth_client_for(args.dst)

    def _preview(cfg: dict | None) -> str:
        if not cfg:
            return "<none>"
        cid = cfg["client_id"]
        return f"{cid[:20]}...{cid[-24:]}"

    print(f"コピー元 [{args.src}] : {_preview(src_cfg)}")
    print(f"コピー先 [{args.dst}] (現在): {_preview(dst_cfg)}")

    if dst_cfg and dst_cfg["client_id"] == src_cfg["client_id"]:
        print("[OK] 既に同一クライアントです。変更不要。")
        return 0

    if not args.yes:
        ans = input(f"\n'{args.dst}' のクライアントを '{args.src}' のものに更新しますか? [y/N] ")
        if ans.strip().lower() not in ("y", "yes"):
            print("中止しました。")
            return 0

    yo.set_oauth_client_for(
        args.dst, src_cfg["client_id"], src_cfg["client_secret"]
    )

    after = yo.get_oauth_client_for(args.dst)
    print(f"\n[DONE] コピー先 [{args.dst}] (更新後): {_preview(after)}")
    print(
        "次に Vercel 経由でこのチャンネルを再認証してください。"
        "既存トークンは旧クライアント発行のため、新クライアントで再取得が必要です。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
