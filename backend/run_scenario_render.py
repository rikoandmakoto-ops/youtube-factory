#!/usr/bin/env python3
"""事前生成済みシナリオJSONから動画をレンダリングする汎用ランナー（Anthropic API不要）

シナリオ生成だけを外に出したパイプライン。シナリオ本文は Claude（Claude Code の
セッション自身など）が直接書いて JSON に保存し、このスクリプトがレンダリングだけを
担当する。ANTHROPIC_API_KEY が失効していても動く。

レンダリング側が使う外部依存は VOICEVOX（ローカル）と画像収集（image_mode="collect"
なら Pexels 等）だけで、タイトル・概要文の生成は純粋な文字列処理なので LLM を呼ばない。

使い方:
    python3 backend/run_scenario_render.py \
        --channel 2ch-matome \
        --scenario data/scenarios/2ch-matome/_claude_kenmei.json

    # 尺・種別を明示したい場合
    python3 backend/run_scenario_render.py -c scp-lab -s path/to.json \
        --gen-type full --duration 720

シナリオJSONの形式:
    {
      "title": "...",                  # 必須。出力フォルダ名にも使われる
      "video_title": "...",            # 任意（省略時は title から自動生成）
      "theme": {"title": "...", "angle": "..."},   # 任意（アーカイブ用メタ）
      "short_scenario": [{"speaker","text","expression","mood"}, ...],
      "full_scenario":  [...],         # 任意（省略時は short_scenario を流用）
      "thumb_info": {"hook_lines": [...], "subtitle": "...", "tagline": "..."}
    }
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
REPO_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# .env 読み込み（VOICEVOX_URL / PEXELS_API_KEY / JWT_SECRET などが必要）
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


def validate_short(scenario, ch_dict):
    """channel の short_format に対してシナリオを検証し、警告を出す（落とさない）。"""
    sf = (ch_dict or {}).get("short_format") or {}
    lines = scenario.get("short_scenario") or []
    warns = []

    want = sf.get("line_count")
    if want and len(lines) != want:
        warns.append(f"line_count={len(lines)} (期待 {want})")

    total = sum(len(str(l.get("text", ""))) for l in lines)
    lo, hi = sf.get("total_chars_min"), sf.get("total_chars_max")
    if lo and total < lo:
        warns.append(f"total_chars={total} < {lo}")
    if hi and total > hi:
        warns.append(f"total_chars={total} > {hi}")

    forbidden = ((ch_dict or {}).get("voice_style") or {}).get("forbidden") or []
    hits = sorted({w for w in forbidden for l in lines if w in str(l.get("text", ""))})
    if hits:
        warns.append(f"forbidden words: {hits}")

    known = set((ch_dict or {}).get("characters") or {})
    bad = sorted({l.get("speaker") for l in lines if l.get("speaker") not in known})
    if known and bad:
        warns.append(f"unknown speakers: {bad} (定義済み: {sorted(known)})")

    print(f"  short lines={len(lines)} chars={total}")
    for w in warns:
        print(f"  ⚠️  {w}")
    return warns


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--channel", required=True, help="チャンネルID (例: 2ch-matome)")
    ap.add_argument("-s", "--scenario", required=True, help="シナリオJSONのパス")
    ap.add_argument("--gen-type", default=None, choices=["short", "full", "both"],
                    help="省略時は autopilot.gen_type → 'short'")
    ap.add_argument("--duration", type=int, default=None,
                    help="目標秒数。省略時は defaults.target_duration")
    ap.add_argument("--output-dir", default=None, help="出力先の親ディレクトリを上書き")
    ap.add_argument("--prefix", default=None, help="ファイル接頭辞を上書き")
    ap.add_argument("--dry-run", action="store_true",
                    help="検証だけしてレンダリングしない")
    args = ap.parse_args()

    cm = ChannelManager()
    ch = cm.get(args.channel)
    if ch is None:
        print(f"❌ Channel not found: {args.channel}")
        sys.exit(1)
    ch_dict = ch.to_dict()

    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        # リポジトリルート基準でも backend 基準でも受け付ける
        for base in (Path.cwd(), REPO_DIR, BACKEND_DIR):
            if (base / scenario_path).exists():
                scenario_path = base / scenario_path
                break
    if not scenario_path.exists():
        print(f"❌ Scenario not found: {args.scenario}")
        sys.exit(1)

    result = json.loads(scenario_path.read_text(encoding="utf-8"))
    if not result.get("title") or not result.get("short_scenario"):
        print("❌ シナリオJSONに title / short_scenario が必要")
        sys.exit(1)

    gen_type = args.gen_type or (ch_dict.get("autopilot") or {}).get("gen_type") or "short"
    duration = args.duration or (ch_dict.get("defaults") or {}).get("target_duration") or 45

    full_scenario = result.get("full_scenario") or result["short_scenario"]
    if gen_type in ("full", "both") and not result.get("full_scenario"):
        print("⚠️  full_scenario が無いので short_scenario を流用する（尺が足りない可能性）")

    print(f"Channel : {ch.name} ({args.channel})")
    print(f"Scenario: {scenario_path}")
    print(f"Title   : {result['title']}")
    print(f"gen_type={gen_type} duration={duration}s style={ch.style}")
    print("Validation:")
    validate_short(result, ch_dict)

    if args.dry_run:
        print("\n--dry-run: レンダリングせず終了")
        return

    prefix = args.prefix or f"{args.channel.replace('-', '_')}_{gen_type}_{int(time.time())}"

    out = vg.generate_all(
        title=result["title"],
        prefix=prefix,
        short_scenario=result["short_scenario"],
        full_scenario=full_scenario,
        bg_video_path=ch.get_bg_video_path(),
        output_dir=args.output_dir,
        gen_type=gen_type,
        bg_type=ch.get_bg_type(),
        thumb_info=result.get("thumb_info"),
        speed=ch.get_speed(),
        target_duration=duration,
        video_title=result.get("video_title") or result["title"],
        style=ch.style,
        use_illustrations=ch.get_use_illustrations(),
        channel_format=ch.video_format.to_dict(),
        char_config=ch.char_config(),
        channel_dict=ch_dict,
        image_mode=ch.get_image_mode(),
        image_collect_settings=ch.get_image_collect_settings(),
        scenario_meta={
            "theme": result.get("theme"),
            "generated_by": result.get("generated_by", "claude-direct"),
        },
    )

    print("\n=== Video Output ===")
    for k, v in out.items():
        print(f"  {k}: {v}")

    meta_path = Path(out["output_dir"]) / "_run_meta.json"
    meta_path.write_text(json.dumps({
        "channel_id": args.channel,
        "theme": result.get("theme"),
        "prefix": prefix,
        "gen_type": gen_type,
        "target_duration": duration,
        "scenario_path": str(scenario_path),
        "video_title": out.get("video_title"),
        "short_title": out.get("short_title"),
        "output": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDONE\n  output_dir: {out['output_dir']}\n  meta: {meta_path}")


if __name__ == "__main__":
    main()
