#!/usr/bin/env python3
"""ショート動画のみ生成（YouTube アップロードなし）— feedback前の確認用

- gen_type="short" でショート動画 + ショートサムネ + ショート説明文のみ生成
- テーマは autopilot.theme_queue 先頭 → theme_seeds → theme_priority.good_examples の順に自動選択
- theme_queue は pop しない（バックエンドと共有のため非破壊）
- 完了後 YouTube には触らない
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

REPO_ROOT = BACKEND_DIR.parent
TARGET_DURATION_SEC = 60


DEDUP_WINDOW_DAYS = 60


def _candidate_themes(ch, raw):
    """選択候補を優先順に列挙（queue先頭→seeds→good_examples）。"""
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

    autopilot.theme_queue は pop しない（非破壊）ため、何度実行しても先頭の
    同じテーマを掴んでしまう。過去 DEDUP_WINDOW_DAYS 日の投稿テーマと語彙重複する
    候補はスキップし、初の非重複テーマを返す。SHORT_FORCE_DUP=1 でガード無効化。"""
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
        if force or _td is None or not past:
            return theme, source
        hit = _td.find_lexical_duplicate(theme["title"], past)
        if hit:
            print(f"  ♻️ skip dup theme: '{theme['title']}' ≈ '{hit[0]}' ({hit[1]:.2f})")
            continue
        return theme, source

    if first is not None:
        print("  ⚠️ all candidates were recent duplicates — using first anyway "
              "(set a fresh theme_queue or SHORT_FORCE_DUP=1 to silence)")
        return first
    return None, None


def run_for(channel_id: str) -> dict:
    cm = ChannelManager()
    ch = cm.get(channel_id)
    if ch is None:
        return {"error": f"Channel not found: {channel_id}"}

    raw_path = REPO_ROOT / "data" / "channels" / f"{channel_id}.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))

    theme, source = _select_theme(ch, raw, channel_id)
    if not theme:
        return {"error": f"No theme available for {channel_id}"}

    print(f"\n{'=' * 70}")
    print(f"📺 [{channel_id}] {ch.name}")
    print(f"🎯 theme ({source}): {theme['title']}")
    if theme.get("angle"):
        print(f"   angle: {theme['angle']}")
    print(f"{'=' * 70}")

    sg = ScenarioGenerator()
    if not getattr(sg, "api_key", None):
        return {"error": "OpenAI API key not set"}

    print(f"\n🎬 Generating scenario (target: {TARGET_DURATION_SEC}s)")
    scenario = None
    last_err = None
    for attempt in range(3):
        try:
            scenario = sg.generate(
                ch, theme_override=theme, target_duration=TARGET_DURATION_SEC
            )
            break
        except Exception as e:
            last_err = e
            wait = 20 * (attempt + 1)
            print(f"⚠️ scenario attempt {attempt + 1} failed: {e}. Waiting {wait}s...")
            time.sleep(wait)
    if scenario is None:
        return {"error": f"Scenario generation failed: {last_err}"}

    try:
        scenario_path = sg.save_scenario(scenario)
    except Exception as e:
        scenario_path = None
        print(f"⚠️ save_scenario failed: {e}")

    print(f"✅ Scenario title: {scenario.get('title')}")
    print(f"   short lines: {len(scenario.get('short_scenario') or [])}")
    print(f"   scenario_path: {scenario_path}")

    char_config = ch.char_config()
    channel_format = ch.video_format.to_dict()
    use_illustrations = ch.get_use_illustrations()
    image_mode = ch.get_image_mode()
    image_collect_settings = ch.get_image_collect_settings()
    bg_type = ch.get_bg_type()
    bg_path = ch.get_bg_video_path()

    prefix = f"{channel_id}_short_{int(time.time())}"
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

    print("\n=== Output ===")
    for k, v in out.items():
        print(f"  {k}: {v}")

    out["_channel_id"] = channel_id
    out["_theme"] = theme
    out["_theme_source"] = source
    out["_scenario_path"] = scenario_path
    return out


def main():
    channel_ids = sys.argv[1:] or ["daily-science", "scp-lab"]
    results = {}

    for cid in channel_ids:
        print(f"\n\n>>>>>> START {cid} <<<<<<\n")
        try:
            results[cid] = run_for(cid)
        except Exception as e:
            traceback.print_exc()
            results[cid] = {"error": str(e), "trace": traceback.format_exc()}

    summary_path = BACKEND_DIR / f"short_only_results_{int(time.time())}.json"
    summary_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print("\n\n========= FINAL =========")
    print(f"summary: {summary_path}")
    for cid, r in results.items():
        print(f"\n[{cid}]")
        if not r or "error" in r:
            print(f"  ❌ ERROR: {(r or {}).get('error')}")
            continue
        print(f"  theme: {r['_theme']['title']}")
        print(f"  output_dir: {r.get('output_dir')}")
        print(f"  short_video: {r.get('short')}")
        print(f"  short_thumbnail: {r.get('short_thumbnail')}")
        print(f"  thumbnail (main): {r.get('thumbnail')}")
        print(f"  short_description: {r.get('short_description')}")
        print(f"  short_title: {r.get('short_title')}")


if __name__ == "__main__":
    main()
