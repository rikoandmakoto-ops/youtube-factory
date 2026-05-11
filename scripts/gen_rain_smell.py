"""Full pipeline runner: 'なぜ雨の匂いがするのか' (ペトリコール).

シナリオ自動生成 → 音声 → 動画（メイン12分目安 + ショート）。
チャンネル: daily-science（リコとマコトのゆっくり日常科学）
"""
import os
import sys
import json
import time
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
MAIN_REPO_ENV = Path("/Users/ayukiyamazaki/Developer/youtube-factory/backend/.env")
WORKTREE_ENV = WORKTREE / "backend" / ".env"

ENV_PATH = WORKTREE_ENV if WORKTREE_ENV.exists() else MAIN_REPO_ENV
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    print(f"🔑 env loaded: {ENV_PATH}")

sys.path.insert(0, str(WORKTREE / "backend"))

from channels import ChannelManager
from pipeline.auto_scenario import ScenarioGenerator
from pipeline.video_generator import generate_all

CHANNEL_ID = "daily-science"
TARGET_DURATION_SEC = 720  # 12 min target (floor 10 min enforced inside generator)

THEME = {
    "title": "なぜ雨の匂いがするのか",
    "angle": (
        "雨が降り始めに漂うあの独特な匂いの正体は『ペトリコール』。"
        "晴れた日に植物が分泌する油が乾燥した土壌に染み込み、"
        "雨粒の衝撃で土の中の放線菌が作るジオスミンと一緒にエアロゾルとして空中に飛散する。"
        "なぜ降り始めだけ匂いが強いのか、なぜ人間はジオスミンを5兆分の1濃度でも検知できるのかを"
        "化学・生態学・進化の視点で解説する。"
    ),
}

cm = ChannelManager(data_dir=str(WORKTREE / "data" / "channels"))
ch = cm.get(CHANNEL_ID)
if ch is None:
    print(f"❌ channel not found: {CHANNEL_ID}")
    sys.exit(1)

print(f"📺 channel: {ch.name}")
print(f"🎯 theme:   {THEME['title']}")
print(f"   angle:   {THEME['angle'][:80]}...")
print(f"⏱️  target:  {TARGET_DURATION_SEC}s ({TARGET_DURATION_SEC/60:.1f}min)")

# ---- 1) シナリオ生成 ---------------------------------------------------------
gen = ScenarioGenerator()

result = None
last_err = None
for attempt in range(5):
    try:
        result = gen.generate(ch, theme_override=THEME, target_duration=TARGET_DURATION_SEC)
        break
    except Exception as e:
        last_err = e
        wait = 30 * (attempt + 1)
        print(f"⚠️  scenario attempt {attempt+1} failed: {e}. waiting {wait}s")
        time.sleep(wait)

if result is None:
    print(f"❌ scenario generation failed: {last_err}")
    sys.exit(1)

print(f"✅ scenario: {result['title']}")
print(f"   short: {len(result['short_scenario'])} lines")
print(f"   full : {len(result['full_scenario'])} lines, "
      f"{sum(len(e.get('text','')) for e in result['full_scenario'])} chars")

scenario_path = gen.save_scenario(result)
print(f"💾 scenario saved: {scenario_path}")

# ---- 2) 音声 + 動画 + サムネ ------------------------------------------------
bg_rel = ch.defaults.get("bg_path")
bg = str(WORKTREE / bg_rel) if bg_rel and (WORKTREE / bg_rel).exists() else None
print(f"🖼️  background: {bg}")

print(f"🎥 generate_all (gen_type={ch.video_format.output.gen_type or 'both'}, "
      f"use_illustrations={ch.get_use_illustrations()})")

out = generate_all(
    title=result["title"],
    prefix="rain_smell",
    short_scenario=result["short_scenario"],
    full_scenario=result["full_scenario"],
    bg_video_path=bg,
    output_dir=None,                      # → ~/Desktop/動画出力用/<title>/
    gen_type=ch.video_format.output.gen_type or "both",
    bg_type=ch.get_bg_type(),
    thumb_info=result.get("thumb_info"),
    speed=ch.get_speed(),
    target_duration=TARGET_DURATION_SEC,
    video_title=result.get("video_title") or result["title"],
    style=ch.style or "yukkuri",
    use_illustrations=ch.get_use_illustrations(),
    channel_format=ch.video_format.to_dict(),
    char_config=ch.char_config(),
    channel_dict=ch.to_dict(),            # HTML+Playwright thumbnail を有効化
)

print("\n=== RESULT ===")
print(json.dumps(out, ensure_ascii=False, indent=2))
