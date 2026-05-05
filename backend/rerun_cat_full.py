#!/usr/bin/env python3
"""既存の修正済みシナリオJSONからフル動画だけ再生成する。
イラストはキャッシュ済み (output_dir/illustrations/) を再利用。"""

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

from channels import ChannelManager
from pipeline import video_generator as vg

CHANNEL_ID = "daily-science"
TARGET_DURATION_SEC = 720
SCENARIO_PATH = BACKEND_DIR.parent / "data" / "scenarios" / CHANNEL_ID / "驚きの物理なぜ猫はいつも足から着地できるのか.json"

cm = ChannelManager()
ch = cm.get(CHANNEL_ID)
if ch is None:
    print(f"❌ Channel not found: {CHANNEL_ID}"); sys.exit(1)

result = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
print(f"📺 Channel: {ch.name}")
print(f"🎯 Title: {result['title']}")
print(f"📄 Scenario: {SCENARIO_PATH}")
print(f"   short: {len(result['short_scenario'])} lines / full: {len(result['full_scenario'])} lines")

bg_path = None
for cand in [BACKEND_DIR.parent / "assets" / "backgrounds" / "ocean_waves.mp4"]:
    if cand.exists():
        bg_path = str(cand); break

prefix = f"{CHANNEL_ID}_auto"
char_config = ch.char_config()
channel_format = ch.video_format.to_dict()
use_illustrations = ch.get_use_illustrations()

print(f"\n🎥 Re-generating FULL video only (illustrations cached)")
out = vg.generate_all(
    title=result['title'],
    prefix=prefix,
    short_scenario=result['short_scenario'],
    full_scenario=result['full_scenario'],
    bg_video_path=bg_path,
    output_dir=None,
    gen_type="full",
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
