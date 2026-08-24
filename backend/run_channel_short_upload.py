#!/usr/bin/env python3
"""任意チャンネルで SHORT 動画を1本生成 →（任意で）YouTube に公開

run_ds_short_upload.py / run_scp_short_upload.py のチャンネル汎用版。

  python run_channel_short_upload.py <channel_id> [<channel_id> ...]

- gen_type="short" のみ（ロング動画は生成しない）
- テーマ: env.SHORT_THEME_TITLE 最優先 → autopilot.theme_queue → theme_seeds
  → theme_priority.good_examples（いずれも非破壊読み）
- 過去 DEDUP_WINDOW_DAYS 日の投稿テーマと語彙重複する候補はスキップ
- SKIP_UPLOAD=1 で生成のみ（OAuth 未連携チャンネルの下準備に使う）
- 生成結果は output_dir/_short_upload_meta.json に保存し、後追いアップロード
  （upload_from_meta.py 相当の手作業）に必要な情報を全部残す

env:
  SHORT_THEME_TITLE / SHORT_THEME_ANGLE  テーマ明示指定（複数チャンネル指定時は
                                         SHORT_THEME_TITLE__<channel_id> も可）
  SHORT_SCENARIO_PATH[__<channel_id>]
                     保存済みシナリオJSONを再利用し生成をスキップ（台本を変えず
                     映像だけ作り直す用途。描画バグ修正後の差し替えなど）
  SHORT_TARGET_SEC   目標尺（既定 60）
  SHORT_PRIVACY      公開設定（既定 public）
  SKIP_UPLOAD=1      アップロードせず生成だけ行う
  SHORT_FORCE_DUP=1  重複ガード無効化
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

TARGET_DURATION_SEC = int(os.environ.get("SHORT_TARGET_SEC", "60"))
PRIVACY = os.environ.get("SHORT_PRIVACY", "public")
SKIP_UPLOAD = os.environ.get("SKIP_UPLOAD", "").strip() in ("1", "true", "yes")

REPO_ROOT = BACKEND_DIR.parent
DEDUP_WINDOW_DAYS = 60


def _env_theme(channel_id):
    """SHORT_THEME_TITLE__<channel_id> を優先し、無ければ共通 SHORT_THEME_TITLE。"""
    suffix = channel_id.replace("-", "_")
    for key in (f"SHORT_THEME_TITLE__{suffix}", "SHORT_THEME_TITLE"):
        title = (os.environ.get(key) or "").strip()
        if title:
            angle_key = key.replace("SHORT_THEME_TITLE", "SHORT_THEME_ANGLE", 1)
            angle = (os.environ.get(angle_key) or os.environ.get("SHORT_THEME_ANGLE") or "").strip()
            return {"title": title, "angle": angle}
    return None


def _candidate_themes(ch, raw, channel_id):
    """選択候補を優先順に列挙（env→queue→seeds→good_examples）。"""
    env_theme = _env_theme(channel_id)
    if env_theme:
        yield env_theme, "env.SHORT_THEME_TITLE"
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

    theme_queue は非破壊で読むため、再実行時に同じ先頭テーマを掴んで同一動画を
    連投してしまう。過去 DEDUP_WINDOW_DAYS 日の投稿テーマと語彙重複する候補を
    スキップする。SHORT_THEME_TITLE 明示指定時、または SHORT_FORCE_DUP=1 で無効。"""
    force = os.environ.get("SHORT_FORCE_DUP", "").strip() in ("1", "true", "yes")
    try:
        from pipeline.auto_scenario import theme_dedup as _td
        past = _td.past_theme_titles(channel_id, within_days=DEDUP_WINDOW_DAYS)
    except Exception as e:
        print(f"⚠️ dedup gate disabled ({channel_id}): {e}")
        _td, past = None, []

    first = None
    for theme, source in _candidate_themes(ch, raw, channel_id):
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
    print(f"📺 Channel: {ch.name} ({channel_id}) → {ch.youtube_channel_id}")
    print(f"🎯 Theme ({source}): {theme['title']}")
    if theme.get("angle"):
        print(f"   angle: {theme['angle']}")
    print(f"{'=' * 70}")

    # ── 1. シナリオ（既存JSONを読むか、新規生成する） ──
    # 台本を変えずに映像だけ作り直したい場合（描画バグ修正後の差し替え等）は
    # SHORT_SCENARIO_PATH に保存済みシナリオJSONを渡す。
    reuse_path = (os.environ.get(f"SHORT_SCENARIO_PATH__{channel_id.replace('-', '_')}")
                  or os.environ.get("SHORT_SCENARIO_PATH") or "").strip()
    if reuse_path:
        scenario_path = reuse_path
        scenario = json.loads(Path(reuse_path).read_text(encoding="utf-8"))
        if not scenario.get("short_scenario"):
            return {"error": f"scenario に short_scenario がありません: {reuse_path}"}
        theme = scenario.get("theme") or theme
        source = "SHORT_SCENARIO_PATH (再利用)"
        print(f"\n♻️ 既存シナリオを再利用（生成をスキップ）: {reuse_path}")
    else:
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
            return {"error": f"Scenario generation failed: {last_err}"}

        try:
            scenario_path = sg.save_scenario(scenario)
        except Exception as e:
            scenario_path = None
            print(f"⚠️ save_scenario failed: {e}")
    print(f"✅ Scenario: {scenario.get('title')}")
    print(f"   short lines: {len(scenario.get('short_scenario') or [])}  | generated_by={scenario.get('generated_by')}")

    # ── 2. 動画生成（short のみ） ──
    prefix = f"{channel_id.replace('-', '_')}_short_{int(time.time())}"
    print(f"\n🎥 Video pipeline (gen_type=short, prefix={prefix})")

    out = vg.generate_all(
        title=scenario["title"],
        prefix=prefix,
        short_scenario=scenario["short_scenario"],
        full_scenario=scenario.get("full_scenario") or scenario["short_scenario"],
        bg_video_path=ch.get_bg_video_path(),
        output_dir=None,
        gen_type="short",
        bg_type=ch.get_bg_type(),
        thumb_info=scenario.get("thumb_info"),
        speed=ch.get_speed(),
        target_duration=TARGET_DURATION_SEC,
        video_title=scenario.get("video_title") or scenario["title"],
        style=ch.style,
        use_illustrations=ch.get_use_illustrations(),
        channel_format=ch.video_format.to_dict(),
        char_config=ch.char_config(),
        channel_dict=ch.to_dict(),
        image_mode=ch.get_image_mode(),
        image_collect_settings=ch.get_image_collect_settings(),
        scenario_meta={"theme": theme, "generated_by": scenario.get("generated_by")},
    )

    print("\n=== Video Output ===")
    for k, v in out.items():
        print(f"  {k}: {v}")

    short_video = Path(out.get("short") or "")
    # monologue / clip 系はショート専用サムネを作らないので short_thumbnail が無い。
    # Path("") は "." （＝カレントディレクトリ）になり exists() を通ってしまうため、
    # アップローダに "." が渡って「Is a directory」で失敗する。無い場合は None。
    short_thumb = Path(out["short_thumbnail"]) if out.get("short_thumbnail") else None
    if not short_video.exists():
        return {"error": f"short video not found: {short_video}", "output_dir": out.get("output_dir")}

    short_desc_title, short_desc_body = _read_desc(out.get("short_description"))
    final_short_title = short_desc_title or out.get("short_title") or scenario["title"]

    meta = {
        "channel_id": channel_id,
        "auth_channel_id": channel_id,
        "youtube_channel_id": ch.youtube_channel_id,
        "theme": theme,
        "theme_source": source,
        "scenario_path": scenario_path,
        "short_title": final_short_title,
        "short_description": short_desc_body,
        "short_video": str(short_video),
        "short_thumbnail": str(short_thumb) if (short_thumb and short_thumb.exists()) else None,
        # タイトル由来の固有名詞もタグに載せる（ロングテール検索流入用）
        "tags": ch.get_upload_tags(is_short=True, title=final_short_title) or None,
        "category_id": ch.video_format.youtube.default_category or ch.get_category() or "24",
        "privacy": PRIVACY,
        "upload": None,
    }

    # ── 3. YouTube アップロード ──
    if SKIP_UPLOAD:
        print("\n⏭️  SKIP_UPLOAD=1 — アップロードせず生成物のみ保存")
    else:
        print(f"\n📤 Uploading SHORT to YouTube ({PRIVACY})...")
        from pipeline import youtube_uploader as yu

        r = yu.upload_video(
            video_path=str(short_video),
            title=final_short_title,
            description=short_desc_body,
            tags=meta["tags"],
            thumbnail_path=str(short_thumb) if (short_thumb and short_thumb.exists()) else None,
            privacy=PRIVACY,
            category_id=meta["category_id"],
            is_short=True,
            channel_id=ch.youtube_channel_id,
            auth_channel_id=channel_id,
        )
        meta["upload"] = r
        print(f"  ✅ short URL: {r.get('url')}")

        # 再生リスト投入 + 前回/次回リンク（自動公開と同じ後処理）
        try:
            from pipeline import post_upload

            meta["post_upload"] = post_upload.run(
                channel_id=channel_id,
                video_id=r.get("video_id"),
                title=final_short_title,
                url=r.get("url") or "",
                is_short=True,
            )
        except Exception as e:
            print(f"  ⚠️ post_upload failed: {e}")
            meta["post_upload"] = {"ok": False, "error": str(e)}

    meta_path = Path(out["output_dir"]) / "_short_upload_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n📝 meta: {meta_path}")

    out["_meta_path"] = str(meta_path)
    out["_meta"] = meta
    return out


def main():
    channel_ids = sys.argv[1:]
    if not channel_ids:
        print(__doc__)
        sys.exit(2)

    results = {}
    for cid in channel_ids:
        print(f"\n\n>>>>>> START {cid} <<<<<<\n")
        try:
            results[cid] = run_for(cid)
        except Exception as e:
            traceback.print_exc()
            results[cid] = {"error": str(e), "trace": traceback.format_exc()}

    print("\n\n========= FINAL =========")
    for cid, r in results.items():
        print(f"\n[{cid}]")
        if not r or "error" in r:
            print(f"  ❌ ERROR: {(r or {}).get('error')}")
            continue
        m = r.get("_meta") or {}
        print(f"  theme:    {m.get('theme', {}).get('title')}")
        print(f"  title:    {m.get('short_title')}")
        print(f"  video:    {m.get('short_video')}")
        print(f"  thumb:    {m.get('short_thumbnail')}")
        print(f"  meta:     {r.get('_meta_path')}")
        up = m.get("upload")
        print(f"  url:      {(up or {}).get('url') if up else '(not uploaded)'}")


if __name__ == "__main__":
    main()
