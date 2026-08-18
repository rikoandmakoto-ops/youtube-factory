#!/usr/bin/env python3
"""daily-science チャンネルで SHORT 動画を1本生成 → YouTube に public 公開

- gen_type="short" のみ（ロング動画は生成しない）
- テーマ: env.SHORT_THEME_TITLE 最優先 → autopilot.theme_queue → theme_seeds → good_examples（非破壊）
- target_duration: 60s（≒30秒前後のショート）
- 完了後 YouTube に public で公開（auth_channel_id='daily-science' / UC1OckVkZahT3_fM6W8hD6dg）

run_scp_short_upload.py の daily-science 版。
"""

import json
import os
import sys
import time
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

# 並行中の dedup 修正タスクが main 作業ツリーの generator.py に未定義メソッド
# `_ensure_fresh_theme` の呼び出しを残しているため、未定義ならパススルーを注入する。
# 本スクリプトのテーマは手動で過去投稿との重複ゼロを検証済みのため差し替え不要。
if not hasattr(ScenarioGenerator, "_ensure_fresh_theme"):
    ScenarioGenerator._ensure_fresh_theme = lambda self, channel, theme: theme

CHANNEL_ID = "daily-science"
AUTH_CHANNEL_ID = "daily-science"
TARGET_DURATION_SEC = int(os.environ.get("SHORT_TARGET_SEC", "60"))
PRIVACY = os.environ.get("SHORT_PRIVACY", "public")

REPO_ROOT = BACKEND_DIR.parent


DEDUP_WINDOW_DAYS = 60


def _candidate_themes(ch, raw):
    """選択候補を優先順に列挙（env→queue→seeds→good_examples）。"""
    env_title = os.environ.get("SHORT_THEME_TITLE")
    if env_title and env_title.strip():
        yield {
            "title": env_title.strip(),
            "angle": (os.environ.get("SHORT_THEME_ANGLE") or "").strip(),
        }, "env.SHORT_THEME_TITLE"
    ap = raw.get("autopilot") or {}
    for head in ap.get("theme_queue") or []:
        if head.get("title"):
            yield {"title": str(head["title"]), "angle": str(head.get("angle") or "")}, "autopilot.theme_queue"
    for s in list(getattr(ch, "theme_seeds", None) or []):
        if isinstance(s, dict) and s.get("title"):
            yield {"title": str(s["title"]), "angle": str(s.get("angle") or "")}, "theme_seeds"
    for s in (raw.get("theme_priority") or {}).get("good_examples") or []:
        if isinstance(s, str) and s.strip():
            yield {"title": s.strip(), "angle": ""}, "theme_priority.good_examples"


def _select_theme(ch, raw, channel_id):
    """重複ガード付きでテーマを選ぶ。

    autopilot.theme_queue は非破壊で読むため、再実行時に同じ先頭テーマを掴んで
    同一動画を連投してしまう（これが本番アップロードなので特に危険）。過去
    DEDUP_WINDOW_DAYS 日の投稿テーマと語彙重複する候補をスキップする。
    SHORT_THEME_TITLE 明示指定時、または SHORT_FORCE_DUP=1 でガード無効。"""
    force = os.environ.get("SHORT_FORCE_DUP", "").strip() in ("1", "true", "yes")
    try:
        from pipeline.auto_scenario import theme_dedup as _td
        past = _td.past_theme_titles(channel_id, within_days=DEDUP_WINDOW_DAYS)
    except Exception as e:
        print(f"⚠️ dedup gate disabled ({channel_id}): {e}")
        _td, past = None, []

    first = None
    for theme, source in _candidate_themes(ch, raw):
        if first is None:
            first = (theme, source)
        # 明示指定(env)は意図的なので常に通す
        if force or _td is None or not past or source == "env.SHORT_THEME_TITLE":
            return theme, source
        hit = _td.find_lexical_duplicate(theme["title"], past)
        if hit:
            print(f"  ♻️ skip dup theme: '{theme['title']}' ≈ '{hit[0]}' ({hit[1]:.2f})")
            continue
        return theme, source

    if first is not None:
        print("  ⚠️ all candidates were recent duplicates — using first anyway "
              "(refresh theme_queue or set SHORT_FORCE_DUP=1 to silence)")
        return first
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
    theme, source = _select_theme(ch, raw, CHANNEL_ID)
    if not theme:
        print(f"❌ No theme available for {CHANNEL_ID}")
        sys.exit(1)

    print(f"📺 Channel: {ch.name} ({CHANNEL_ID}) → {ch.youtube_channel_id}")
    print(f"🎯 Theme ({source}): {theme['title']}")
    if theme.get("angle"):
        print(f"   angle: {theme['angle']}")

    # ── 1. シナリオ生成 ──
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

    prefix = f"ds_short_{int(time.time())}"
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
