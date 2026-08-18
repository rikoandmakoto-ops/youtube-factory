#!/usr/bin/env python3
"""scp-lab チャンネルで SCP-3000「アナンタシェーシャ」長尺動画を1本フル生成

- テーマ: SCP-3000「アナンタシェーシャ」
- target_duration: 720s (12分目安 / 最低10分)
- gen_type: "full" を明示上書き（scp-lab のデフォルトは short 固定のため）
- bg: 静的 (channel デフォルトの dark bg_color)
- 画像: image_mode='collect' (Pexels 収集)
- VOICEVOX 音声
- アップロードは既定で行わない。`--upload` を付けたときだけ private で投稿する。
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
GEN_TYPE = "full"  # ← scp-lab は short 固定なので長尺を明示指定

THEME = {
    "title": "SCP-3000「アナンタシェーシャ」",
    "angle": (
        "ベンガル湾の海底に横たわる、全長が測定不能なウナギ型の巨大存在。"
        "近づいた者は記憶を逆流させながら失っていき、財団はその体から分泌される物質Y-909を"
        "採取して最強クラスの記憶処理薬を精製している——つまり『忘れさせる薬』は"
        "『忘れさせる怪物』から搾り取られている。潜水した研究員の音声記録が壊れていく過程、"
        "サイト-120で繰り返される採取作業の異常性、そして誰もこの存在の全長を"
        "知ることができない理由を、発見経緯・潜行記録・収容の代償の順に、"
        "物語として引き込む構成で解説"
    ),
}


def main():
    do_upload = "--upload" in sys.argv

    cm = ChannelManager()
    ch = cm.get(CHANNEL_ID)
    if ch is None:
        print(f"❌ Channel not found: {CHANNEL_ID}")
        sys.exit(1)

    print(f"📺 Channel: {ch.name} ({CHANNEL_ID})")
    print(f"🎯 Theme: {THEME['title']}")
    print(f"   Angle: {THEME['angle']}")
    print(f"   gen_type(forced): {GEN_TYPE}")
    print(f"   upload: {do_upload}")

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
    full_chars = sum(len(str(l.get('text', ''))) for l in result['full_scenario'])
    print(f"   full chars:  {full_chars} (推定 {full_chars/7.8/60:.1f}min @1.3x)")

    # 題材ロックが効いているか（SCP-3000 以外に乗り換えていないか）を検査
    title_blob = (result['title'] + json.dumps(result.get('thumb_info') or {}, ensure_ascii=False))
    if "3000" not in title_blob:
        print(f"⚠️ WARNING: タイトルに SCP-3000 が含まれていません: {result['title']}")

    scenario_path = gen.save_scenario(result)
    print(f"💾 Saved: {scenario_path}")

    # ── 2. 動画生成 ──
    char_config = ch.char_config()
    channel_format = ch.video_format.to_dict()
    gen_type = GEN_TYPE  # ← 明示上書き（channel は short 固定）
    use_illustrations = ch.get_use_illustrations()
    image_mode = ch.get_image_mode()
    image_collect_settings = ch.get_image_collect_settings()
    bg_type = ch.get_bg_type()
    bg_path = ch.get_bg_video_path()  # None (静的 dark bg を使用)

    print(f"\n🎥 Video pipeline")
    print(f"   gen_type={gen_type}, bg_type={bg_type}")
    print(f"   image_mode={image_mode}, use_illustrations={use_illustrations}")
    print(f"   effects preset={channel_format.get('effects', {}).get('preset')}")

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

    # ── 3. 結果メタを書き出し ──
    meta_path = Path(out["output_dir"]) / "_run_meta.json"
    meta_path.write_text(json.dumps({
        "channel_id": CHANNEL_ID,
        "auth_channel_id": AUTH_CHANNEL_ID,
        "theme": THEME,
        "prefix": prefix,
        "gen_type": gen_type,
        "target_duration": TARGET_DURATION_SEC,
        "scenario_path": scenario_path,
        "video_title": out.get("video_title"),
        "output": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📝 meta: {meta_path}")

    output_dir = Path(out["output_dir"])

    if not do_upload:
        print("\n🎉 DONE (generation only — アップロードは未実行)")
        print(f"   output_dir: {output_dir}")
        print(f"   投稿する場合: python3 run_scp_lab_3000_full.py --upload （再生成されます）")
        return

    # ── 4. YouTube アップロード ──
    print("\n📤 Uploading to YouTube (SCP channel, private)...")
    from pipeline import youtube_uploader as yu

    main_video = Path(out.get("full") or "")
    main_thumb = Path(out.get("thumbnail") or "")

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
    final_main_title = main_desc_title or out.get("video_title") or result["title"]

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

    # 結果を保存
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["upload"] = upload_results
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📝 final meta: {meta_path}")

    print("\n🎉 DONE")
    print(f"   output_dir: {output_dir}")
    if upload_results.get("main"):
        print(f"   main URL: {upload_results['main']['url']}")


if __name__ == "__main__":
    main()
