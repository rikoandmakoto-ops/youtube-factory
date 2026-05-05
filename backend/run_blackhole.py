#!/usr/bin/env python3
"""daily-scienceチャンネル: ブラックホールに落ちたらどうなる? 動画を1本生成"""

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
from pipeline.auto_scenario import ScenarioGenerator
from pipeline import video_generator as vg

CHANNEL_ID = "daily-science"
TARGET_DURATION_SEC = 720  # 12分目安、最低10分(600s)
# Note: generator.py was patched to use 9 sections (was 6). GPT writes ~1000 chars/section,
# so 9 sections × ~1000 chars = ~9000 chars → ~756s (12.6 min) at 11.9 char/sec.

THEME_OVERRIDE = {
    "title": "ブラックホールに落ちたらどうなる？",
    "angle": "スパゲッティ化・時間の歪み・事象の地平線を、最新の物理学で徹底解説",
}

cm = ChannelManager()
ch = cm.get(CHANNEL_ID)
if ch is None:
    print(f"❌ Channel not found: {CHANNEL_ID}")
    sys.exit(1)

print(f"📺 Channel: {ch.name}")
print(f"🎯 Theme: {THEME_OVERRIDE['title']}")

gen = ScenarioGenerator()

print(f"\n🎬 Generating scenario (target: {TARGET_DURATION_SEC}s = {TARGET_DURATION_SEC/60:.1f}min)")
result = gen.generate(ch, theme_override=THEME_OVERRIDE, target_duration=TARGET_DURATION_SEC)
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
