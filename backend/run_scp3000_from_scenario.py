#!/usr/bin/env python3
"""SCP-3000 動画生成 — 事前生成済みシナリオから動画レンダリングのみ実行

シナリオ生成をスキップし、data/scenarios/scp-lab/_scp3000_new.json を読み込んで
動画パイプラインを実行する。
"""

import os
import sys
import time
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

# .env 読み込み
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

CHANNEL_ID = "scp-lab"
TARGET_DURATION_SEC = 720
GEN_TYPE = "full"

SCENARIO_PATH = BACKEND_DIR.parent / "data" / "scenarios" / "scp-lab" / "_scp3000_new.json"

THEME = {
    "title": "SCP-3000「アナンタシェーシャ」",
    "angle": "ベンガル湾の海底に横たわる全長測定不能のウナギ型巨大存在。記憶を溶かす怪物から搾り取られる物質Y-909の正体を解説",
}


def main():
    cm = ChannelManager()
    ch = cm.get(CHANNEL_ID)
    if ch is None:
        print(f"Channel not found: {CHANNEL_ID}")
        sys.exit(1)

    print(f"Channel: {ch.name} ({CHANNEL_ID})")

    # ── 1. シナリオ読み込み ──
    if not SCENARIO_PATH.exists():
        print(f"Scenario not found: {SCENARIO_PATH}")
        sys.exit(1)

    result = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    print(f"Scenario loaded: {result['title']}")
    print(f"  full lines:  {len(result['full_scenario'])}")
    full_chars = sum(len(str(l.get('text', ''))) for l in result['full_scenario'])
    print(f"  full chars:  {full_chars}")

    if full_chars < 5760:
        print(f"WARN: full_chars={full_chars} < 5760")

    # ── 2. 動画生成 ──
    char_config = ch.char_config()
    channel_format = ch.video_format.to_dict()
    gen_type = GEN_TYPE
    use_illustrations = ch.get_use_illustrations()
    image_mode = ch.get_image_mode()
    image_collect_settings = ch.get_image_collect_settings()
    bg_type = ch.get_bg_type()
    bg_path = ch.get_bg_video_path()

    print(f"\nVideo pipeline")
    print(f"  gen_type={gen_type}, bg_type={bg_type}")
    print(f"  image_mode={image_mode}, use_illustrations={use_illustrations}")
    print(f"  effects preset={channel_format.get('effects', {}).get('preset')}")

    prefix = f"scp3000_{int(time.time())}"

    out = vg.generate_all(
        title=result['title'],
        prefix=prefix,
        short_scenario=result['short_scenario'],
        full_scenario=result['full_scenario'],
        bg_video_path=bg_path,
        output_dir=None,
        gen_type=gen_type,
        bg_type=bg_type,
        thumb_info=result.get('thumb_info'),
        speed=ch.get_speed(),
        target_duration=TARGET_DURATION_SEC,
        video_title=result.get('video_title') or result['title'],
        style=ch.style,
        use_illustrations=use_illustrations,
        channel_format=channel_format,
        char_config=char_config,
        channel_dict=ch.to_dict(),
        image_mode=image_mode,
        image_collect_settings=image_collect_settings,
        scenario_meta={"theme": THEME, "generated_by": result.get("generated_by")},
    )

    print("\n=== Video Output ===")
    for k, v in out.items():
        print(f"  {k}: {v}")

    # ── 3. メタ書き出し ──
    meta_path = Path(out["output_dir"]) / "_run_meta.json"
    meta_path.write_text(json.dumps({
        "channel_id": CHANNEL_ID,
        "theme": THEME,
        "prefix": prefix,
        "gen_type": gen_type,
        "target_duration": TARGET_DURATION_SEC,
        "scenario_path": str(SCENARIO_PATH),
        "video_title": out.get("video_title"),
        "output": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"meta: {meta_path}")

    output_dir = Path(out["output_dir"])
    print(f"\nDONE")
    print(f"  output_dir: {output_dir}")


if __name__ == "__main__":
    main()
