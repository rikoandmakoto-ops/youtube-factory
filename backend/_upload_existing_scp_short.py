#!/usr/bin/env python3
"""今日(6/23)の autopilot で生成済みだが自動公開に失敗した scp-lab ショートを
そのまま YouTube に public 公開する（再生成しない）。原因は gen_type=short 単体公開の
未実装バグ（api_phase4.py 修正済み）。本スクリプトは既存ファイルを直接アップロードする。
"""
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

from channels import ChannelManager
from pipeline import youtube_uploader as yu

CHANNEL_ID = "scp-lab"
D = Path("/Users/ayukiyamazaki/Desktop/動画出力用/SCP-3999【世界が、一人の研究員のために終わり続けた】")
VIDEO = D / "scp-lab_ショート.mp4"
THUMB = D / "scp-lab_ショート_サムネイル.png"
DESC = D / "scp-lab_ショート_説明文.txt"


def _read_desc(p):
    if not p or not p.exists():
        return "", ""
    title = ""
    body = []
    for line in p.read_text(encoding="utf-8").split("\n"):
        if (not title) and (line.startswith("タイトル:") or line.startswith("タイトル：")):
            title = line.split(":", 1)[-1].split("：", 1)[-1].strip()
            continue
        body.append(line)
    return title, "\n".join(body).strip()


def main():
    cm = ChannelManager()
    ch = cm.get(CHANNEL_ID)
    assert VIDEO.exists(), f"missing video: {VIDEO}"
    desc_title, desc_body = _read_desc(DESC)
    title = desc_title or "一口SCP：SCP-3999【世界が、一人の研究員のために終わり続けた】 #shorts #ゆっくり解説"
    print(f"📺 {ch.name} ({CHANNEL_ID}) → {ch.youtube_channel_id}")
    print(f"🎬 {title}")
    print(f"📤 Uploading existing short ({VIDEO.stat().st_size/1024/1024:.1f}MB)...")
    r = yu.upload_video(
        video_path=str(VIDEO),
        title=title,
        description=desc_body,
        tags=ch.video_format.youtube.default_tags or ch.get_hashtags() or None,
        thumbnail_path=str(THUMB) if THUMB.exists() else None,
        privacy="public",
        category_id=ch.video_format.youtube.default_category or ch.get_category() or "24",
        is_short=True,
        channel_id=ch.youtube_channel_id,
        auth_channel_id=CHANNEL_ID,
    )
    print("\n========= DONE =========")
    print(f"  url:      {r.get('url')}")
    print(f"  video_id: {r.get('video_id')}")
    print(f"  privacy:  {r.get('privacy_status') or r.get('privacy')}")


if __name__ == "__main__":
    main()
