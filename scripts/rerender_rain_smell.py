"""拡張済みシナリオでメイン動画だけ再レンダリング（イラストキャッシュ再利用）。"""
import os
import sys
import json
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
ENV_PATH = Path("/Users/ayukiyamazaki/Developer/youtube-factory/backend/.env")
for line in ENV_PATH.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(WORKTREE / "backend"))

from channels import ChannelManager
from pipeline.video_generator import generate_all

CHANNEL_ID = "daily-science"
SCENARIO_PATH = (
    WORKTREE / "data" / "scenarios" / "daily-science"
    / "雨の匂いの正体とはペトリコールの科学を解明.json"
)

cm = ChannelManager(data_dir=str(WORKTREE / "data" / "channels"))
ch = cm.get(CHANNEL_ID)
sc = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))

bg_rel = ch.defaults.get("bg_path")
bg = str(WORKTREE / bg_rel) if bg_rel and (WORKTREE / bg_rel).exists() else None

total_chars = sum(len(e["text"]) for e in sc["full_scenario"])
print(f"📺 channel: {ch.name}")
print(f"📄 scenario: {sc['title']}")
print(f"   full: {len(sc['full_scenario'])} lines, {total_chars} chars "
      f"(est {total_chars/7.55/60 + 0.3*len(sc['full_scenario'])/60:.1f} min)")
print(f"🖼️  background: {bg}")
print(f"♻️  illustrations cache will be reused at "
      f"~/Desktop/動画出力用/{sc['title']}/illustrations/")

out = generate_all(
    title=sc["title"],
    prefix="rain_smell",
    short_scenario=sc["short_scenario"],   # 渡すが gen_type=full なので使われない
    full_scenario=sc["full_scenario"],
    bg_video_path=bg,
    output_dir=None,
    gen_type="full",                       # メインだけ
    bg_type=ch.get_bg_type(),
    thumb_info=sc.get("thumb_info"),
    speed=ch.get_speed(),
    target_duration=ch.get_target_duration(),
    video_title=sc.get("video_title") or sc["title"],
    style=ch.style or "yukkuri",
    use_illustrations=ch.get_use_illustrations(),
    channel_format=ch.video_format.to_dict(),
    char_config=ch.char_config(),
    channel_dict=ch.to_dict(),
)

print("\n=== RESULT ===")
print(json.dumps(out, ensure_ascii=False, indent=2))
