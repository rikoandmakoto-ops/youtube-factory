#!/usr/bin/env python3
"""コーヒー動画を10分尺で再生成 + フル動画を作成して /Users/ayukiyamazaki/BAT用/ にコピー"""

import os
import sys
import shutil
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

# VOICEVOX URL を localhost:50021 に
os.environ.setdefault("VOICEVOX_URL", "http://localhost:50021")

from channels import ChannelManager
from pipeline.auto_scenario import ScenarioGenerator
from pipeline import video_generator as vg

CHANNEL_ID = "daily-science"
TARGET_DURATION_SEC = 720  # 12分目安（最低10分を割らない）
COPY_DEST = Path("/Users/ayukiyamazaki/BAT用/")

cm = ChannelManager()
ch = cm.get(CHANNEL_ID)
if ch is None:
    print(f"❌ Channel not found: {CHANNEL_ID}")
    sys.exit(1)

print(f"📺 Channel: {ch.name}")
print(f"🎯 Target duration: {TARGET_DURATION_SEC}s ({TARGET_DURATION_SEC/60:.1f} min)")

theme_override = {
    "title": "なぜコーヒーを飲むと目が覚めるのか？",
    "angle": "カフェインの科学と脳活動のメカニズム — アデノシン受容体ブロック、ドーパミン放出、半減期5時間まで深掘り",
}

gen = ScenarioGenerator()
print(f"\n🎬 Generating 10-min scenario via GPT...")
result = gen.generate(ch, theme_override=theme_override, target_duration=TARGET_DURATION_SEC)
print(f"✅ Scenario: {result['title']}")
print(f"   short: {len(result['short_scenario'])} lines")
print(f"   full:  {len(result['full_scenario'])} lines")

scenario_path = gen.save_scenario(result)
print(f"💾 Saved to: {scenario_path}")

# キャラ位置オフセット +130 は daily-science.json の char_y_offset で既に設定済み
char_config = ch.char_config()
channel_format = ch.video_format.to_dict()
print(f"📐 char_y_offset: {channel_format.get('layout', {}).get('char_y_offset')}")

bg_path = None
for cand in [BACKEND_DIR.parent / "assets" / "backgrounds" / "ocean_waves.mp4"]:
    if cand.exists():
        bg_path = str(cand)
        break
print(f"🎨 Background: {bg_path}")

prefix = "coffee_10min"
gen_type = ch.video_format.output.gen_type or "both"
use_illustrations = ch.get_use_illustrations()
print(f"\n🎥 Generating videos (gen_type={gen_type}, use_illustrations={use_illustrations})")
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

# Copy full video to BAT用
COPY_DEST.mkdir(parents=True, exist_ok=True)
full_path = out.get("full")
if full_path and Path(full_path).exists():
    dest = COPY_DEST / Path(full_path).name
    shutil.copy2(full_path, dest)
    print(f"\n📦 Copied to: {dest}")
    print(f"   Size: {dest.stat().st_size/1024/1024:.1f}MB")
else:
    print("\n⚠️ Full video not generated")
