#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OAuth トークン寿命の健康診断（読み取り専用）

2026-09-09〜09-12 に公開が全停止した（33本/日 → 0〜2本/日）原因は
リフレッシュトークンの一斉失効だった。Google の OAuth 同意画面が「テスト」
公開ステータスのままだと、リフレッシュトークンは付与から 7 日で失効する。
実際、失効した ch の最終リフレッシュ成功時刻は 7〜9 日前に固まっていた。

このスクリプトは data/youtube_tokens.db を読んで、ch ごとの
「最後にリフレッシュに成功した時刻」と経過日数を出す。
7 日に近い ch は再認可が必要になる（＝同意画面が本番公開されていない証拠）。

    python3 scripts/oauth_health_check.py

書き込みは一切しない。cron/日次タスクからそのまま呼べる。
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "data" / "youtube_tokens.db"

# テスト公開ステータスのリフレッシュトークン寿命
TESTING_TTL_DAYS = 7.0
WARN_DAYS = 5.0


def main() -> int:
    if not DB.exists():
        print(f"❌ {DB} が見つかりません")
        return 1

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = [
        dict(r)
        for r in con.execute(
            "select channel_id, youtube_channel_name, updated_at from oauth_tokens"
        )
    ]
    if not rows:
        print("⚠️ oauth_tokens が空です")
        return 1

    now = datetime.now().timestamp()
    rows.sort(key=lambda r: -int(r["updated_at"] or 0))

    print(f"OAuth トークン健康診断 — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"（テスト公開ステータスの場合の寿命 = {TESTING_TTL_DAYS:.0f} 日）\n")
    print(f"{'channel_id':20}{'最終リフレッシュ成功':22}{'経過日':>7}  状態")
    print("-" * 68)

    dead, warn, ok = [], [], []
    for r in rows:
        ts = int(r["updated_at"] or 0)
        age = (now - ts) / 86400.0
        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        if age >= TESTING_TTL_DAYS:
            mark, bucket = "❌ 失効済みの可能性大 → 要再認可", dead
        elif age >= WARN_DAYS:
            mark, bucket = "⚠️ まもなく失効", warn
        else:
            mark, bucket = "✅ 正常", ok
        bucket.append(r["channel_id"])
        print(f"{r['channel_id']:20}{when:22}{age:>7.1f}  {mark}")

    print("-" * 68)
    print(f"正常 {len(ok)} / 警告 {len(warn)} / 失効 {len(dead)}（全 {len(rows)} ch）")
    if dead:
        print(f"\n要再認可: {', '.join(dead)}")
    if warn:
        print(f"まもなく失効: {', '.join(warn)}")
    if dead or warn:
        print(
            "\n恒久対策: Google Cloud Console → OAuth 同意画面 の公開ステータスを\n"
            "「テスト」から「本番環境」へ変更する。テストのままだとリフレッシュ\n"
            "トークンが 7 日で失効し、7 日ごとに全 ch の公開が止まる。"
        )
    return 2 if dead else (1 if warn else 0)


if __name__ == "__main__":
    sys.exit(main())
