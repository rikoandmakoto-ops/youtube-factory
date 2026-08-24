#!/usr/bin/env python3
"""
サムネ impressions / CTR 用の YouTube Reporting API ジョブを全チャンネルに用意する。

サムネ指標は Analytics API v2 では取得できず（metrics=impressions は 400）、
Reporting API のバルクレポート `channel_reach_basic_a1` が唯一の経路。
そのレポートは **ジョブを作らないと生成が始まらない**ので、チャンネルごとに
一度だけこのスクリプトを流す。

    python3 backend/setup_reach_jobs.py            # 状態確認のみ（何も作らない）
    python3 backend/setup_reach_jobs.py --create   # 未作成のチャンネルにジョブを作る
    python3 backend/setup_reach_jobs.py --create --channel scp-lab

注意:
  - ジョブ作成から最初のレポートが出るまで最大 48 時間。
  - 作成時点で過去 30 日分がバックフィルされる。それより前は永久に取得できない。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(BACKEND_DIR / ".env")
except Exception:
    pass

from pipeline import youtube_oauth as yt_oauth  # noqa: E402
from pipeline import youtube_reporting as yt_reporting  # noqa: E402


def _all_channel_ids() -> list:
    d = PROJECT_ROOT / "data" / "channels"
    return sorted(p.stem for p in d.glob("*.json"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true", help="未作成ならジョブを作る")
    ap.add_argument("--channel", help="対象チャンネルを1つに限定")
    args = ap.parse_args()

    channels = [args.channel] if args.channel else _all_channel_ids()
    if not channels:
        print("チャンネルが見つからない")
        return 1

    created = 0
    for ch in channels:
        if not yt_oauth.get_credentials_for(ch):
            print(f"{ch:20s} : OAuth 未連携 — スキップ")
            continue

        if args.create:
            res = yt_reporting.ensure_job(ch)
            if not res.get("ok"):
                print(f"{ch:20s} : ✗ {res.get('error')}")
                continue
            if res.get("created"):
                created += 1
                print(f"{ch:20s} : ✅ ジョブ作成 job_id={res.get('job_id')}")
            else:
                print(f"{ch:20s} : 既存 job_id={res.get('job_id')} "
                      f"(created {res.get('create_time')})")
        else:
            res = yt_reporting.list_jobs(ch)
            if not res.get("ok"):
                print(f"{ch:20s} : ✗ {res.get('error')}")
                continue
            jobs = [
                j for j in res.get("jobs", [])
                if j.get("reportTypeId") == yt_reporting.REPORT_TYPE_ID
            ]
            if jobs:
                j = jobs[0]
                print(f"{ch:20s} : 有 job_id={j.get('id')} "
                      f"(created {j.get('createTime')})")
            else:
                print(f"{ch:20s} : 無 — --create で作成が必要")

    if args.create and created:
        print(
            f"\n{created} 件のジョブを作成。最初のレポートが出るまで最大48時間、"
            "作成時点から過去30日分がバックフィルされる。\n"
            "その後は sync_channel が自動で取り込む（手動なら "
            "python3 -c \"import sys;sys.path.insert(0,'backend');"
            "from pipeline import youtube_reporting as r;print(r.sync_reach('<channel>'))\"）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
