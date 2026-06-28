#!/usr/bin/env python3
"""SCP 演出込み 10秒サンプル — Pexels背景 + video_effects + VOICEVOX."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / "backend" / ".env", override=True)

os.environ.setdefault("ICLOUD_SYNC", "0")
os.environ.setdefault("OUTPUT_BASE", str(Path.home() / "Desktop" / "動画出力用"))

assert os.environ.get("PEXELS_API_KEY"), "PEXELS_API_KEY not set in backend/.env"

from pipeline import image_collector
from pipeline.video_generator import generate_full_video

CH_PATH = ROOT / "data" / "channels" / "scp-lab.json"
channel = json.loads(CH_PATH.read_text(encoding="utf-8"))

OUT_BASE = Path.home() / "Desktop" / "動画出力用" / "SCP_背景テスト"
OUT_BASE.mkdir(parents=True, exist_ok=True)
illust_cache = OUT_BASE / "illustrations_effects_sample"
illust_cache.mkdir(parents=True, exist_ok=True)

KEYWORDS = [
    "dark abandoned hospital corridor",
    "creepy laboratory red light",
    "foggy ruined building horror",
    "occult ritual candle dark room",
]
collect_settings = {
    "provider": "pexels",
    "max_per_query": 5,
    "safe_search": True,
    "attribution_template": "出典: {source}",
}

print("=" * 60)
print("STEP 1: Pexels背景収集")
print("=" * 60)
collected = []
for i, kw in enumerate(KEYWORDS):
    got = image_collector.search_and_cache(
        kw, cache_dir=illust_cache, idx=i, settings=collect_settings
    )
    if not got:
        print(f"  [{i}] '{kw}' — no image")
        continue
    src = got.get("source_url", "")
    print(f"  [{i}] '{kw}' <- {src}")
    collected.append((i, kw, got))

if not collected:
    sys.exit("ABORT: no images collected from Pexels")

print(f"\nCollected {len(collected)}/{len(KEYWORDS)} images into {illust_cache}")

print("\n" + "=" * 60)
print("STEP 2: 演出込み 10秒動画レンダ (VOICEVOX + horror effects)")
print("=" * 60)

# Spooky scenario with mood keywords that video_effects auto-selects against
# (horror/scary/anxious/ominous/sudden -> shake/flash/tint/zoom).
scenario = [
    {"speaker": "シロ", "text": "やぁ……今夜の報告書は、特に危険だ。覚悟して聞いてくれ。",
     "mood": "ominous"},
    {"speaker": "クロ", "text": "シロ姉、無理だよ……うしろから、何か近づいてくる気がする！",
     "mood": "scary"},
    {"speaker": "シロ", "text": "振り向くな。それを見た瞬間、君は終わる。",
     "mood": "horror"},
]

bg_path = str(illust_cache / "collected_000.png")

channel_format = json.loads(json.dumps(channel.get("video_format", {})))
channel_format.setdefault("layout", {})
# Cycle 4 collected backgrounds within ~10s.
channel_format["layout"]["illustration_interval"] = 3
# Make sure horror preset is loaded and effects enabled.
fx = channel_format.setdefault("effects", {})
fx["enabled"] = True
fx["preset"] = "horror"

char_config = channel.get("characters", {})

out = generate_full_video(
    scenario=scenario,
    title="SCP_演出サンプル",
    output_prefix="scp_effects_sample",
    bg_video_path=bg_path,
    out_dir=OUT_BASE,
    bg_type="static",
    speed=1.3,
    target_duration=10,
    use_illustrations=True,
    channel_format=channel_format,
    char_config=char_config,
    channel_id="scp-lab",
    bgm_volume=0.0,
    image_mode="collect",
    image_collect_settings=collect_settings,
)

print("\nrender out:", out)

# Rename to the exact filename the user wants.
out_path = Path(out)
final = OUT_BASE / "scp_effects_sample.mp4"
if out_path.resolve() != final.resolve():
    shutil.move(str(out_path), str(final))
print("FINAL:", final)

repo_copy = ROOT / "scp_effects_sample.mp4"
shutil.copy2(str(final), str(repo_copy))
print("REPO COPY:", repo_copy)
