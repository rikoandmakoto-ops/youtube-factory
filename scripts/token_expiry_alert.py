#!/usr/bin/env python3
"""OAuth トークンの残り寿命を見て、危ういときだけ短く知らせる。

PDCA レポートの中にも同じ警告は出ているが、245KB のログと長いレポートに埋もれて
2026-09-19 の「6ch が 0.5 日で一斉失効」を誰も拾えなかった。要点だけを短く出すのが目的。

このスクリプト自体は通知を送らない。標準出力に1行サマリと詳細を出し、
対応が必要なときだけ終了コード 2 を返す。通知はこれを呼ぶ側（Claude routine 等）が行う。

実行: /usr/bin/python3 scripts/token_expiry_alert.py [--warn-days 3]
終了コード: 0=問題なし / 2=要対応 / 1=実行エラー
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = "https://youtube-factory-eight.vercel.app"


def check(warn_days: float) -> tuple[list[str], list[str], str]:
    """check_youtube_tokens.py を動かして (警告行, 失効ch, 生出力) を返す。"""
    proc = subprocess.run(
        [sys.executable, "backend/check_youtube_tokens.py", "--warn-days", str(warn_days)],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    warn: list[str] = []
    dead: list[str] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        ch, state = parts[0], parts[1]
        if state == "警告":
            warn.append(line.strip())
        elif state == "失効":
            dead.append(ch)
    return warn, dead, proc.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn-days", type=float, default=3.0)
    ap.add_argument("--verbose", action="store_true", help="生出力も付ける")
    args = ap.parse_args()

    try:
        warn, dead, raw = check(args.warn_days)
    except Exception as exc:  # noqa: BLE001
        print(f"OAuth チェックに失敗: {exc}")
        return 1

    if not warn:
        print(f"OAuth: 残り {args.warn_days:g} 日を切ったチャンネルなし（失効済み {len(dead)}ch）")
        return 0

    chans = ", ".join(w.split()[0] for w in warn)
    shortest = min((w.split()[2] for w in warn), default="?")
    print(f"要対応: YouTube OAuth {len(warn)}ch が失効間近（最短 {shortest}）: {chans}")
    print(f"ダッシュボード → チャンネル設定 →「YouTube連携」→「再接続」: {DASHBOARD}")
    for w in warn:
        print(f"  {w}")
    if dead:
        print(f"失効済み（投稿・計測とも停止中）: {', '.join(dead)}")
    if args.verbose:
        print("--- 生出力 ---")
        print(raw)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
