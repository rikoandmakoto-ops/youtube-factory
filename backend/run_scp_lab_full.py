#!/usr/bin/env python3
"""scp-lab チャンネルで SCP-096 動画を1本フル生成 → YouTube アップロード

- テーマ: SCP-096「シャイガイ」
- target_duration: 720s (12分)
- bg: 静的 (channel デフォルトの dark bg_color)
- 画像: image_mode='collect' (Pexels 収集)
- VOICEVOX 音声
- 完了後 YouTube に private で公開（auth_channel_id='scp-lab' = SCP YouTube）
"""

import os
import sys
import time
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

CHANNEL_ID = "scp-lab"
AUTH_CHANNEL_ID = "scp-lab"  # SCP YouTube channel OAuth は scp-lab キーに登録済み
TARGET_DURATION_SEC = 720

THEME = {
    "title": "SCP-096「シャイガイ」",
    "angle": "顔を見られると殺しに来る存在。徹底した隠蔽体制と発見経緯、収容違反事例を解説",
}


def main():
    cm = ChannelManager()
    ch = cm.get(CHANNEL_ID)
    if ch is None:
        print(f"❌ Channel not found: {CHANNEL_ID}")
        sys.exit(1)

    print(f"📺 Channel: {ch.name} ({CHANNEL_ID})")
    print(f"🎯 Theme: {THEME['title']}")
    print(f"   Angle: {THEME['angle']}")

    # ── 1. シナリオ生成 ──
    gen = ScenarioGenerator()
    print(f"\n🎬 Generating scenario (target: {TARGET_DURATION_SEC}s = {TARGET_DURATION_SEC/60:.1f}min)")
    result = None
    last_err = None
    for attempt in range(4):
        try:
            result = gen.generate(ch, theme_override=THEME, target_duration=TARGET_DURATION_SEC)
            break
        except Exception as e:
            last_err = e
            wait = 30 * (attempt + 1)
            print(f"⚠️ generate attempt {attempt+1} failed: {e}. Waiting {wait}s...")
            time.sleep(wait)
    if result is None:
        print(f"❌ Scenario generation failed: {last_err}")
        sys.exit(1)

    print(f"✅ Scenario: {result['title']}")
    print(f"   short lines: {len(result['short_scenario'])}")
    print(f"   full lines:  {len(result['full_scenario'])}")
    scenario_path = gen.save_scenario(result)
    print(f"💾 Saved: {scenario_path}")

    # ── 2. 動画生成 ──
    char_config = ch.char_config()
    channel_format = ch.video_format.to_dict()
    gen_type = ch.video_format.output.gen_type or "both"
    use_illustrations = ch.get_use_illustrations()
    image_mode = ch.get_image_mode()
    image_collect_settings = ch.get_image_collect_settings()
    bg_type = ch.get_bg_type()
    bg_path = ch.get_bg_video_path()  # None (静的 dark bg を使用)

    print(f"\n🎥 Video pipeline")
    print(f"   gen_type={gen_type}, bg_type={bg_type}")
    print(f"   image_mode={image_mode}, use_illustrations={use_illustrations}")
    print(f"   effects preset={channel_format.get('effects', {}).get('preset')}")
    print(f"   char_canvas_w_ratio={channel_format.get('layout', {}).get('char_canvas_w_ratio')}")

    prefix = f"scp096_{int(time.time())}"

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

    # ── 3. 結果メタを書き出し ──
    meta_path = Path(out["output_dir"]) / "_run_meta.json"
    meta_path.write_text(json.dumps({
        "channel_id": CHANNEL_ID,
        "auth_channel_id": AUTH_CHANNEL_ID,
        "theme": THEME,
        "prefix": prefix,
        "scenario_path": scenario_path,
        "video_title": out.get("video_title"),
        "short_title": out.get("short_title"),
        "output": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📝 meta: {meta_path}")

    # ── 4. YouTube アップロード ──
    print("\n📤 Uploading to YouTube (SCP channel, private)...")
    from pipeline import youtube_uploader as yu

    output_dir = Path(out["output_dir"])
    main_video = Path(out.get("full") or "")
    short_video = Path(out.get("short") or "")
    main_thumb = Path(out.get("thumbnail") or "")
    short_thumb = Path(out.get("short_thumbnail") or "")

    # 説明文 (txt) を読み込み (タイトル行は除外)
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

    main_desc_title, main_desc_body = _read_desc(out.get("main_description"))
    short_desc_title, short_desc_body = _read_desc(out.get("short_description"))

    final_main_title = main_desc_title or out.get("video_title") or result["title"]
    final_short_title = short_desc_title or out.get("short_title") or result["title"]

    upload_results = {}

    if main_video.exists():
        try:
            print(f"  📤 main: {main_video.name}")
            r = yu.upload_video(
                video_path=str(main_video),
                title=final_main_title,
                description=main_desc_body,
                tags=ch.get_upload_tags(is_short=False) or None,
                thumbnail_path=str(main_thumb) if main_thumb.exists() else None,
                privacy="private",
                category_id=ch.video_format.youtube.default_category or ch.get_category() or "24",
                is_short=False,
                channel_id=ch.youtube_channel_id,  # UCXEy... (SCP)
                auth_channel_id=AUTH_CHANNEL_ID,
            )
            upload_results["main"] = r
            print(f"  ✅ main URL: {r['url']}")
        except Exception as e:
            print(f"  ❌ main upload failed: {e}")
            upload_results["main_error"] = str(e)
    else:
        print(f"  ⚠️ main video not found: {main_video}")

    if short_video.exists():
        try:
            print(f"  📤 short: {short_video.name}")
            r = yu.upload_video(
                video_path=str(short_video),
                title=final_short_title,
                description=short_desc_body,
                tags=ch.get_upload_tags(is_short=True) or None,
                thumbnail_path=str(short_thumb) if short_thumb.exists() else None,
                privacy="private",
                category_id=ch.video_format.youtube.default_category or ch.get_category() or "24",
                is_short=True,
                channel_id=ch.youtube_channel_id,
                auth_channel_id=AUTH_CHANNEL_ID,
            )
            upload_results["short"] = r
            print(f"  ✅ short URL: {r['url']}")
        except Exception as e:
            print(f"  ❌ short upload failed: {e}")
            upload_results["short_error"] = str(e)
    else:
        print(f"  ⚠️ short video not found: {short_video}")

    # 結果を保存
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["upload"] = upload_results
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📝 final meta: {meta_path}")

    print("\n🎉 DONE")
    print(f"   output_dir: {output_dir}")
    if upload_results.get("main"):
        print(f"   main URL: {upload_results['main']['url']}")
    if upload_results.get("short"):
        print(f"   short URL: {upload_results['short']['url']}")


if __name__ == "__main__":
    main()
