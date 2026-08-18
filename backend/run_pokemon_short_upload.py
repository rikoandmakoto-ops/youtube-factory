#!/usr/bin/env python3
"""pokemon-lab チャンネルで SHORT 動画を1本生成 → YouTube に public 公開

- edge-tts を使用（VOICEVOX 非起動環境用）
- gen_type="short" のみ
- 未投稿シナリオを使用
"""

import json
import os
import sys
import time
import subprocess
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

# Load .env
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

if not hasattr(ScenarioGenerator, "_ensure_fresh_theme"):
    ScenarioGenerator._ensure_fresh_theme = lambda self, channel, theme: theme

CHANNEL_ID = "pokemon-lab"
AUTH_CHANNEL_ID = "pokemon-lab"
TARGET_DURATION_SEC = 60
PRIVACY = "public"
REPO_ROOT = BACKEND_DIR.parent


# No monkey-patching needed — VOICEVOX runs on the host macOS machine.
# The pipeline will auto-detect VOICEVOX via check_voicevox().


def _read_desc(p):
    if not p or not Path(p).exists():
        return "", ""
    text = Path(p).read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if (not title) and (line.startswith("タイトル:") or line.startswith("タイトル：")):
            title = line.split(":", 1)[-1].split("：", 1)[-1].strip()
            continue
        body_lines.append(line)
    return title, "\n".join(body_lines).strip()


def _pick_unposted_scenario():
    """Pick a short scenario from existing unposted files."""
    scenario_dir = REPO_ROOT / "data" / "scenarios" / CHANNEL_ID
    candidates = sorted(scenario_dir.glob("*.json"))

    for p in candidates:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            ss = data.get("short_scenario")
            if ss and isinstance(ss, list) and len(ss) >= 3:
                # Check it hasn't been uploaded
                if not data.get("uploaded"):
                    return data, p
        except Exception:
            continue
    return None, None


def main():
    cm = ChannelManager()
    ch = cm.get(CHANNEL_ID)
    if ch is None:
        print(f"❌ Channel not found: {CHANNEL_ID}")
        sys.exit(1)

    print(f"📺 Channel: {ch.name} ({CHANNEL_ID}) → {ch.youtube_channel_id}")

    # ── 1. Pick scenario ──
    scenario, scenario_path = _pick_unposted_scenario()
    if scenario is None:
        print("⚠️ No unposted scenario found. Generating new one...")
        raw_path = REPO_ROOT / "data" / "channels" / f"{CHANNEL_ID}.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))

        # Pick a theme
        theme_seeds = raw.get("theme_seeds", [])
        if theme_seeds:
            import random
            theme = random.choice(theme_seeds)
        else:
            theme = {"title": "ピカチュウの意外な裏設定", "angle": "図鑑テキストから読み解く"}

        sg = ScenarioGenerator()
        print(f"🎯 Theme: {theme['title']}")

        try:
            scenario = sg.generate(ch, theme_override=theme, target_duration=TARGET_DURATION_SEC)
        except Exception as e:
            print(f"❌ Scenario generation failed: {e}")
            sys.exit(1)

    title = scenario.get("title", "ポケモン考察")
    short_scenario = scenario["short_scenario"]
    thumb_info = scenario.get("thumb_info")

    print(f"✅ Scenario: {title}")
    print(f"   short lines: {len(short_scenario)}")
    for i, line in enumerate(short_scenario):
        print(f"   [{i+1}] {line.get('speaker', '?')}: {line.get('text', '')[:50]}")

    # ── 2. Generate short video ──
    char_config = ch.char_config()
    channel_format = ch.video_format.to_dict()
    image_mode = ch.get_image_mode()
    image_collect_settings = ch.get_image_collect_settings()
    bg_type = ch.get_bg_type()
    bg_path = ch.get_bg_video_path()

    prefix = f"pokemon_lab_short_{int(time.time())}"
    print(f"\n🎥 Video pipeline (gen_type=short, prefix={prefix})")

    out = vg.generate_all(
        title=title,
        prefix=prefix,
        short_scenario=short_scenario,
        full_scenario=scenario.get("full_scenario") or short_scenario,
        bg_video_path=bg_path,
        output_dir=None,
        gen_type="short",
        bg_type=bg_type,
        thumb_info=thumb_info,
        speed=ch.get_speed(),
        target_duration=TARGET_DURATION_SEC,
        video_title=scenario.get("video_title") or title,
        style=ch.style,
        use_illustrations=False,  # Skip illustration generation for speed
        channel_format=channel_format,
        char_config=char_config,
        channel_dict=ch.to_dict(),
        image_mode=image_mode,
        image_collect_settings=image_collect_settings,
        scenario_meta={"theme": {"title": title}, "generated_by": "edge-tts-pipeline"},
    )

    print("\n=== Video Output ===")
    for k, v in out.items():
        print(f"  {k}: {v}")

    short_video = Path(out.get("short") or "")
    short_thumb = Path(out.get("short_thumbnail") or "")
    if not short_video.exists():
        print(f"❌ short video not found: {short_video}")
        sys.exit(1)

    short_desc_title, short_desc_body = _read_desc(out.get("short_description"))
    final_short_title = short_desc_title or out.get("short_title") or title

    # ── 3. YouTube upload (public) ──
    print(f"\n📤 Uploading SHORT to YouTube ({PRIVACY})...")
    from pipeline import youtube_uploader as yu

    tags = ch.get_upload_tags(is_short=True) or None
    category = ch.video_format.youtube.default_category or ch.get_category() or "24"

    r = yu.upload_video(
        video_path=str(short_video),
        title=final_short_title,
        description=short_desc_body,
        tags=tags,
        thumbnail_path=None,  # Skip custom thumbnail (phone verification not done)
        privacy=PRIVACY,
        category_id=str(category),
        is_short=True,
        channel_id=ch.youtube_channel_id,
        auth_channel_id=AUTH_CHANNEL_ID,
    )
    print(f"  ✅ short URL: {r.get('url')}")

    # Save metadata
    meta = {
        "channel_id": CHANNEL_ID,
        "auth_channel_id": AUTH_CHANNEL_ID,
        "youtube_channel_id": ch.youtube_channel_id,
        "theme": {"title": title},
        "short_title": final_short_title,
        "short_video": str(short_video),
        "privacy": PRIVACY,
        "upload": r,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_path = Path(out["output_dir"]) / "_short_upload_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n📝 meta: {meta_path}")
    print("\n========= DONE =========")
    print(f"  title: {final_short_title}")
    print(f"  url:   {r.get('url')}")
    print(f"  video_id: {r.get('video_id')}")


if __name__ == "__main__":
    main()
