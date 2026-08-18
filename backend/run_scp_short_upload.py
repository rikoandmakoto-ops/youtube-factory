#!/usr/bin/env python3
"""scp-lab チャンネルで SHORT 動画を1本生成 → YouTube に public 公開

- gen_type="short" のみ（ロング動画は生成しない）
- テーマ: autopilot.theme_queue 先頭 → theme_seeds → good_examples の順に自動選択
  （theme_queue は先頭を pop して JSON に書き戻し、同じテーマの再利用を防ぐ）
- target_duration: 60s
- 完了後 YouTube に public で公開（auth_channel_id='scp-lab' = SCP YouTube / UCXEyJqJt9Ug94iOHdpd5a8w）
"""

import json
import os
import sys
import time
import traceback
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
AUTH_CHANNEL_ID = "scp-lab"
TARGET_DURATION_SEC = int(os.environ.get("SHORT_TARGET_SEC", "60"))
PRIVACY = os.environ.get("SHORT_PRIVACY", "public")

REPO_ROOT = BACKEND_DIR.parent


def _select_theme(ch, raw, raw_path=None):
    # 環境変数によるテーマ明示指定（過去投稿との重複回避用）を最優先
    env_title = os.environ.get("SHORT_THEME_TITLE")
    if env_title and env_title.strip():
        return {
            "title": env_title.strip(),
            "angle": (os.environ.get("SHORT_THEME_ANGLE") or "").strip(),
        }, "env.SHORT_THEME_TITLE"
    ap = raw.get("autopilot") or {}
    queue = ap.get("theme_queue") or []
    if queue:
        # 先頭を取り出し（pop）、キューから除去した状態を JSON に永続化して再利用を防ぐ
        head = queue.pop(0)
        if raw_path is not None:
            try:
                ap["theme_queue"] = queue
                raw["autopilot"] = ap
                raw_path.write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception as e:
                print(f"⚠️ theme_queue pop の永続化に失敗（続行）: {e}")
        return {"title": str(head["title"]), "angle": str(head.get("angle") or "")}, "autopilot.theme_queue"
    seeds = list(getattr(ch, "theme_seeds", None) or [])
    if seeds:
        s = seeds[0]
        if isinstance(s, dict) and s.get("title"):
            return {"title": str(s["title"]), "angle": str(s.get("angle") or "")}, "theme_seeds"
    examples = (raw.get("theme_priority") or {}).get("good_examples") or []
    for s in examples:
        if isinstance(s, str) and s.strip():
            return {"title": s.strip(), "angle": ""}, "theme_priority.good_examples"
    return None, None


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


def main():
    cm = ChannelManager()
    ch = cm.get(CHANNEL_ID)
    if ch is None:
        print(f"❌ Channel not found: {CHANNEL_ID}")
        sys.exit(1)

    raw_path = REPO_ROOT / "data" / "channels" / f"{CHANNEL_ID}.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    theme, source = _select_theme(ch, raw, raw_path)
    if not theme:
        print(f"❌ No theme available for {CHANNEL_ID}")
        sys.exit(1)

    print(f"📺 Channel: {ch.name} ({CHANNEL_ID}) → {ch.youtube_channel_id}")
    print(f"🎯 Theme ({source}): {theme['title']}")
    if theme.get("angle"):
        print(f"   angle: {theme['angle']}")

    # ── 1. シナリオ生成（GPT quota切れ → Claude単独採用にフォールバック） ──
    sg = ScenarioGenerator()
    print(f"\n🎬 Generating scenario (target: {TARGET_DURATION_SEC}s, gen_type=short)")
    scenario = None
    last_err = None
    for attempt in range(4):
        try:
            scenario = sg.generate(ch, theme_override=theme, target_duration=TARGET_DURATION_SEC)
            break
        except Exception as e:
            last_err = e
            wait = 20 * (attempt + 1)
            print(f"⚠️ scenario attempt {attempt + 1} failed: {e}. Waiting {wait}s...")
            time.sleep(wait)
    if scenario is None:
        print(f"❌ Scenario generation failed: {last_err}")
        sys.exit(1)

    try:
        scenario_path = sg.save_scenario(scenario)
    except Exception as e:
        scenario_path = None
        print(f"⚠️ save_scenario failed: {e}")
    print(f"✅ Scenario: {scenario.get('title')}")
    print(f"   short lines: {len(scenario.get('short_scenario') or [])}  | generated_by={scenario.get('generated_by')}")

    # ── 2. 動画生成（short のみ） ──
    char_config = ch.char_config()
    channel_format = ch.video_format.to_dict()
    use_illustrations = ch.get_use_illustrations()
    image_mode = ch.get_image_mode()
    image_collect_settings = ch.get_image_collect_settings()
    bg_type = ch.get_bg_type()
    bg_path = ch.get_bg_video_path()

    prefix = f"scp_short_{int(time.time())}"
    print(f"\n🎥 Video pipeline (gen_type=short, prefix={prefix})")

    out = vg.generate_all(
        title=scenario["title"],
        prefix=prefix,
        short_scenario=scenario["short_scenario"],
        full_scenario=scenario.get("full_scenario") or scenario["short_scenario"],
        bg_video_path=bg_path,
        output_dir=None,
        gen_type="short",
        bg_type=bg_type,
        thumb_info=scenario.get("thumb_info"),
        speed=ch.get_speed(),
        target_duration=TARGET_DURATION_SEC,
        video_title=scenario.get("video_title") or scenario["title"],
        style=ch.style,
        use_illustrations=use_illustrations,
        channel_format=channel_format,
        char_config=char_config,
        channel_dict=ch.to_dict(),
        image_mode=image_mode,
        image_collect_settings=image_collect_settings,
        scenario_meta={"theme": theme, "generated_by": scenario.get("generated_by")},
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
    final_short_title = short_desc_title or out.get("short_title") or scenario["title"]

    # ── 3. YouTube アップロード（public） ──
    print(f"\n📤 Uploading SHORT to YouTube ({PRIVACY})...")
    from pipeline import youtube_uploader as yu

    r = yu.upload_video(
        video_path=str(short_video),
        title=final_short_title,
        description=short_desc_body,
        tags=ch.get_upload_tags(is_short=True) or None,
        thumbnail_path=str(short_thumb) if short_thumb.exists() else None,
        privacy=PRIVACY,
        category_id=ch.video_format.youtube.default_category or ch.get_category() or "24",
        is_short=True,
        channel_id=ch.youtube_channel_id,
        auth_channel_id=AUTH_CHANNEL_ID,
    )
    print(f"  ✅ short URL: {r.get('url')}")

    # 結果メタ
    meta = {
        "channel_id": CHANNEL_ID,
        "auth_channel_id": AUTH_CHANNEL_ID,
        "youtube_channel_id": ch.youtube_channel_id,
        "theme": theme,
        "theme_source": source,
        "scenario_path": scenario_path,
        "short_title": final_short_title,
        "short_video": str(short_video),
        "short_thumbnail": str(short_thumb) if short_thumb.exists() else None,
        "privacy": PRIVACY,
        "upload": r,
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
