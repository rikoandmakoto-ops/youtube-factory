"""Full pipeline runner for the 'why-can-we-crack-our-fingers' video."""
import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"
CHANNEL_ID = "daily-science"
SCENARIO_PATH = ROOT / "data" / "scenarios" / CHANNEL_ID / "なぜ指をポキポキ鳴らせるのか.json"

# Load .env so OPENAI_API_KEY is visible to the pipeline
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Make backend importable
sys.path.insert(0, str(ROOT / "backend"))

from channels import ChannelManager  # noqa: E402
from pipeline.video_generator import generate_all  # noqa: E402

cm = ChannelManager(data_dir=str(ROOT / "data" / "channels"))
ch = cm.get(CHANNEL_ID)
if ch is None:
    print(f"❌ Unknown channel: {CHANNEL_ID}")
    sys.exit(1)

sc = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))

bg_rel = ch.defaults.get("bg_path")
bg = str(ROOT / bg_rel) if bg_rel and (ROOT / bg_rel).exists() else None

print(f"📺 Channel: {ch.id} ({ch.name})")
print(f"📄 Scenario: {SCENARIO_PATH.name}")
print(f"🖼️ Background: {bg}")
print(f"🎬 Lines — short:{len(sc.get('short_scenario', []))} full:{len(sc.get('full_scenario', []))}")

result = generate_all(
    title=sc["title"],
    prefix=sc["prefix"],
    short_scenario=sc["short_scenario"],
    full_scenario=sc["full_scenario"],
    bg_video_path=bg,
    output_dir=None,
    gen_type="full",
    bg_type=ch.defaults.get("bg_type", "static"),
    thumb_info=sc.get("thumb_info"),
    speed=ch.get_speed(),
    target_duration=ch.get_target_duration(),
    video_title=sc.get("video_title"),
    style=ch.style or "yukkuri",
    use_illustrations=True,
    channel_format=ch.video_format.to_dict(),
    char_config=ch.char_config(),
    channel_dict=ch.to_dict(),
)

print("\n=== RESULT ===")
print(json.dumps(result, ensure_ascii=False, indent=2))
