#!/usr/bin/env python3
"""daily-scienceチャンネルで動画を1本生成するスクリプト"""

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

from channels import ChannelManager
from pipeline.auto_scenario import ScenarioGenerator
from pipeline import video_generator as vg

CHANNEL_ID = "daily-science"
# target_duration は秒。フル動画12分目安=720秒。最低10分(600秒)を割らない。
TARGET_DURATION_SEC = 720

cm = ChannelManager()
ch = cm.get(CHANNEL_ID)
if ch is None:
    print(f"❌ Channel not found: {CHANNEL_ID}")
    sys.exit(1)

print(f"📺 Channel: {ch.name}")

gen = ScenarioGenerator()

if not ch.theme_seeds:
    print("🤖 No theme_seeds — asking GPT to suggest themes")
    suggestions = gen.suggest_themes(ch, count=3)
    print(f"   GPT suggested {len(suggestions)} themes")
    for i, t in enumerate(suggestions):
        print(f"   {i+1}. {t.get('title')} — angle: {t.get('angle')}")
    theme_override = suggestions[0]
else:
    theme_override = None

print(f"\n🎬 Generating scenario (target: {TARGET_DURATION_SEC}s = {TARGET_DURATION_SEC/60:.1f}min)")
result = gen.generate(ch, theme_override=theme_override, target_duration=TARGET_DURATION_SEC)
print(f"✅ Scenario: {result['title']}")
print(f"   short: {len(result['short_scenario'])} lines")
print(f"   full:  {len(result['full_scenario'])} lines")

scenario_path = gen.save_scenario(result)
print(f"💾 Saved to: {scenario_path}")

prefix = f"{CHANNEL_ID}_auto"

bg_path = None
for cand in [
    BACKEND_DIR.parent / "assets" / "backgrounds" / "ocean_waves.mp4",
]:
    if cand.exists():
        bg_path = str(cand)
        break

print(f"🎨 Background: {bg_path}")

char_config = ch.char_config()
channel_format = ch.video_format.to_dict()

gen_type = ch.video_format.output.gen_type or "both"
use_illustrations = ch.get_use_illustrations()

print(f"\n🎥 Generating video (gen_type={gen_type}, use_illustrations={use_illustrations})")
out = vg.generate_all(
    title=result['title'],
    prefix=prefix,
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
