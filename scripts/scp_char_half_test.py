#!/usr/bin/env python3
"""SCPラボ：キャラサイズ半減後の確認用10秒動画生成。"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Load .env so VOICEVOX / OPENAI keys are available when present.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=True)
except Exception:
    pass

os.environ.setdefault("ICLOUD_SYNC", "0")

from pipeline.video_generator import generate_full_video

CHANNEL_JSON = ROOT / "data" / "channels" / "scp-lab.json"
OUT_DIR = Path.home() / "Desktop" / "動画出力用" / "SCP_背景テスト"


def main():
    cfg = json.loads(CHANNEL_JSON.read_text(encoding="utf-8"))
    channel_format = cfg.get("video_format", {})
    char_config = cfg.get("characters", {})

    for c in char_config.values():
        if isinstance(c.get("text_color"), list):
            c["text_color"] = tuple(c["text_color"])

    scenario = [
        {"speaker": "シロ", "text": "今日のSCPは173番。視線を外すと近づいてくる彫刻だよ。"},
        {"speaker": "クロ", "text": "えっ、それ目を瞑ったら終わりってこと？怖すぎる！"},
        {"speaker": "シロ", "text": "そう。だから収容室には常に二人以上の職員が必要なんだ。"},
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out = generate_full_video(
        scenario=scenario,
        title="SCP_背景テスト",
        output_prefix="char_half",
        bg_video_path=None,
        out_dir=OUT_DIR,
        bg_type="static",
        speed=1.3,
        target_duration=10,
        use_illustrations=False,
        channel_format=channel_format,
        char_config=char_config,
        channel_id="scp-lab",
        bgm_volume=0.0,
        image_mode="generate",
    )
    print(f"\n出力: {out}")


if __name__ == "__main__":
    main()
