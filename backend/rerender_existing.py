#!/usr/bin/env python3
"""既存シナリオ + 既存イラストキャッシュで動画だけ再レンダリング。
画像配置の調整やレイアウトの再生成に使う。"""

import os
import sys
import json
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

os.environ.setdefault("VOICEVOX_URL", "http://localhost:50021")

from channels import ChannelManager
from pipeline import video_generator as vg

CHANNEL_ID = "daily-science"
TARGET_DURATION_SEC = 720  # 12分目安（最低10分を割らない）

SCENARIO_PATH = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/ayukiyamazaki/BAT用/youtube-factory/data/scenarios/daily-science/お風呂でひらめきその科学的秘密とは.json"

with open(SCENARIO_PATH, encoding="utf-8") as f:
    result = json.load(f)

print(f"📄 Loaded scenario: {result['title']}")
print(f"   short: {len(result['short_scenario'])} lines / full: {len(result['full_scenario'])} lines")

cm = ChannelManager()
ch = cm.get(CHANNEL_ID)

bg_path = str(BACKEND_DIR.parent / "assets" / "backgrounds" / "ocean_waves.mp4")
char_config = ch.char_config()
channel_format = ch.video_format.to_dict()

gen_type = ch.video_format.output.gen_type or "both"
use_illustrations = ch.get_use_illustrations()
print(f"🎥 Re-rendering (gen_type={gen_type}, use_illustrations={use_illustrations})")

out = vg.generate_all(
    title=result['title'],
    prefix=f"{CHANNEL_ID}_auto",
    short_scenario=result['short_scenario'],
    full_scenario=result['full_scenario'],
    bg_video_path=bg_path,
    output_dir=None,
    gen_type=gen_type,
    bg_type=ch.get_bg_type(),
    thumb_info=result.get('thumb_info'),
    speed=ch.get_speed(),
    target_duration=TARGET_DURATION_SEC,
    video_title=result['title'],
    style=ch.style,
    use_illustrations=use_illustrations,
    channel_format=channel_format,
    char_config=char_config,
)

print("\n=== Output ===")
for k, v in out.items():
    print(f"  {k}: {v}")
