#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""有効chの当日(JST)公開分をYouTube APIで実照合する。読み取り専用。

「記録なし＝未投稿」は誤り（autopilotは記録を残さない）ため、未投稿判定は
このスクリプトのように uploads プレイリスト直読みで行う。

    python3 scripts/check_uploads_today.py [YYYY-MM-DD]
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))
from dotenv import load_dotenv
load_dotenv(BACKEND / ".env")

from googleapiclient.discovery import build  # noqa: E402
from pipeline import youtube_oauth  # noqa: E402

JST = timezone(timedelta(hours=9))
TARGET = sys.argv[1] if len(sys.argv) > 1 else datetime.now(JST).strftime("%Y-%m-%d")


def active_channels():
    out = []
    for f in sorted((REPO / "data" / "channels").glob("*.json")):
        d = json.loads(f.read_text())
        if (d.get("autopilot") or {}).get("enabled"):
            out.append((f.stem, d.get("youtube_channel_id")))
    return out


def main():
    for ch, cid in active_channels():
        try:
            creds = youtube_oauth.get_credentials_for(ch)
            if creds is None:
                print(f"{ch:15} ❌ creds None（トークン失効）")
                continue
            if not getattr(creds, "valid", False):
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
            pl = yt.playlistItems().list(
                part="snippet,contentDetails",
                playlistId="UU" + cid[2:], maxResults=8,
            ).execute()
            todays, latest = [], None
            for it in pl.get("items", []):
                pub = it.get("contentDetails", {}).get("videoPublishedAt")
                if not pub:
                    continue
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(JST)
                if latest is None:
                    latest = (dt, it["snippet"].get("title", "")[:35])
                if dt.strftime("%Y-%m-%d") == TARGET:
                    todays.append((dt.strftime("%H:%M"), it["snippet"].get("title", "")[:35]))
            if todays:
                print(f"{ch:15} ✅ {len(todays)}本  " + " / ".join(f"{t} {ti}" for t, ti in todays))
            else:
                l = f"最新: {latest[0]:%m-%d %H:%M} {latest[1]}" if latest else "動画なし"
                print(f"{ch:15} ⚠️ {TARGET}は0本  {l}")
        except Exception as e:
            print(f"{ch:15} ❌ {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
