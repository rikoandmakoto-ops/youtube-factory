#!/usr/bin/env python3
"""猫動画をハイライト修正後に再レンダリング（既存シナリオ + 既存イラスト使用、GPT API禁止）。"""

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


def _no_gpt(*_a, **_kw):
    raise RuntimeError(
        "GPT/DALL-E API呼び出しを検出（キャッシュミス）。"
        "既存のillustrationsキャッシュで満たされていない可能性があります。"
    )


vg._call_openai_image = _no_gpt

CHANNEL_ID = "daily-science"
SCENARIO_PATH = (
    "/Users/ayukiyamazaki/BAT用/youtube-factory/data/scenarios/"
    "daily-science/驚きの物理なぜ猫はいつも足から着地できるのか.json"
)
TARGET_DURATION_SEC = 720

with open(SCENARIO_PATH, encoding="utf-8") as f:
    result = json.load(f)

print(f"📄 Scenario: {result['title']}")
print(f"   short:{len(result['short_scenario'])}  full:{len(result['full_scenario'])}")

cm = ChannelManager()
ch = cm.get(CHANNEL_ID)

bg_rel = ch.defaults.get("bg_path") or "assets/backgrounds/classroom.png"
bg_path = str(BACKEND_DIR.parent / bg_rel)

char_config = ch.char_config()
channel_format = ch.video_format.to_dict()
print(f"🔆 nonspeaker_opacity={channel_format['layout'].get('nonspeaker_opacity')}  "
      f"speaker_glow={channel_format['layout'].get('speaker_glow')}")

out = vg.generate_all(
    title=result["title"],
    prefix=f"{CHANNEL_ID}_auto",
    short_scenario=result["short_scenario"],
    full_scenario=result["full_scenario"],
    bg_video_path=bg_path,
    output_dir=None,
    gen_type="both",
    bg_type=ch.get_bg_type(),
    thumb_info=result.get("thumb_info"),
    speed=ch.get_speed(),
    target_duration=TARGET_DURATION_SEC,
    video_title=result.get("video_title") or result["title"],
    style=ch.style,
    use_illustrations=ch.get_use_illustrations(),
    channel_format=channel_format,
    char_config=char_config,
)

print("\n=== Output ===")
for k, v in out.items():
    print(f"  {k}: {v}")
