#!/usr/bin/env python3
"""Pexels-collect + 10s render smoke test for scp-lab channel."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

WORKTREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKTREE / "backend"))
load_dotenv(WORKTREE / "backend" / ".env", override=True)

os.environ.setdefault("ICLOUD_SYNC", "0")
os.environ.setdefault("OUTPUT_BASE", str(Path.home() / "Desktop" / "動画出力用"))

assert os.environ.get("PEXELS_API_KEY"), "PEXELS_API_KEY not set in backend/.env"

from pipeline import image_collector
from pipeline.video_generator import generate_full_video

CH_PATH = WORKTREE / "data" / "channels" / "scp-lab.json"
channel = json.loads(CH_PATH.read_text(encoding="utf-8"))

OUT_BASE = Path.home() / "Desktop" / "動画出力用" / "SCP_背景テスト"
OUT_BASE.mkdir(parents=True, exist_ok=True)
illust_cache = OUT_BASE / "illustrations"
illust_cache.mkdir(parents=True, exist_ok=True)

KEYWORDS = [
    "dark laboratory",
    "horror corridor",
    "abandoned facility",
    "mysterious experiment",
]
collect_settings = {
    "provider": "pexels",
    "max_per_query": 5,
    "safe_search": True,
    "attribution_template": "出典: {source}",
}

print("=" * 60)
print("STEP 1: Collect 4 background images from Pexels")
print("=" * 60)
collected = []
for i, kw in enumerate(KEYWORDS):
    got = image_collector.search_and_cache(
        kw, cache_dir=illust_cache, idx=i, settings=collect_settings
    )
    if not got:
        print(f"  ❌ [{i}] '{kw}' — no image")
        continue
    src = got.get("source_url", "")
    print(f"  ✅ [{i}] '{kw}' ← {src}")
    collected.append((i, kw, got))

if not collected:
    sys.exit("ABORT: no images collected from Pexels")

print(f"\nCollected {len(collected)}/{len(KEYWORDS)} images into {illust_cache}")

print("\n" + "=" * 60)
print("STEP 2: Render 10s test video")
print("=" * 60)

scenario = [
    {"speaker": "シロ", "text": "やぁ、今日も財団から流出した報告書が届いたよ。",
     "mood": "mysterious"},
    {"speaker": "クロ", "text": "シロ姉……これ、本当に読んでも大丈夫なの？",
     "mood": "anxious"},
    {"speaker": "シロ", "text": "覚悟を決めて。これが、闇に潜む異常存在の正体だ。",
     "mood": "ominous"},
]

bg_path = str(illust_cache / "collected_000.png")

channel_format = json.loads(json.dumps(channel.get("video_format", {})))
channel_format.setdefault("layout", {})
# Force shorter illustration interval so the collected images cycle within ~10s.
channel_format["layout"]["illustration_interval"] = 3

char_config = channel.get("characters", {})

out = generate_full_video(
    scenario=scenario,
    title="SCP_背景テスト",
    output_prefix="SCP_背景テスト",
    bg_video_path=bg_path,
    out_dir=OUT_BASE,
    bg_type="static",
    speed=1.3,
    target_duration=10,
    use_illustrations=True,
    channel_format=channel_format,
    char_config=char_config,
    channel_id="scp-lab",
    bgm_volume=0.0,           # mute BGM — smoke test
    image_mode="collect",
    image_collect_settings=collect_settings,
)

print("\n" + "=" * 60)
print(f"VIDEO OUTPUT: {out}")
print("=" * 60)
