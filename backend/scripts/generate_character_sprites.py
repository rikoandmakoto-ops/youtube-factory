#!/usr/bin/env python3
"""チャンネルJSONの characters[].appearance からキャラ立ち絵PNGを生成する。

video_generator は assets/characters/<dir>/<expression>.png を読み、無ければ
そのキャラのアイコン描画を丸ごとスキップする（ショートだと話者アイコンが
消えて中央が空く）。新チャンネル追加時にこのスクリプトで一式を用意する。

  python -m scripts.generate_character_sprites pokemon-lab yokai-watch

- 生成対象は characters[].expressions（既定 ["normal"]）
- 既存ファイルはスキップ（--force で再生成）
- gpt-image-1 / background=transparent / 1024x1024 で生成
- 並列生成（既定4スレッド）

env: OPENAI_API_KEY（backend/.env から自動読み込み）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
ASSETS_DIR = REPO_ROOT / "assets" / "characters"

# 表情ごとの追加指示。video_generator が参照する表情キーを網羅する。
EXPRESSION_PROMPTS = {
    "normal": "calm neutral friendly expression, mouth closed, looking at the viewer",
    "happy": "bright cheerful smile, eyes crinkled with joy, upbeat",
    "sad": "downcast worried expression, eyebrows drawn together, slight frown",
    "angry": "annoyed frowning expression, furrowed brows, puffed cheeks",
    "surprise": "wide-eyed astonished expression, mouth open in a small gasp",
    "think": "thoughtful pondering expression, eyes looking up and to the side, "
             "one hand raised near the chin",
}

STYLE_SUFFIX = (
    "Waist-up bust portrait, centered, facing the viewer, head fully visible with "
    "generous margin above the hair. Clean flat anime cel-shading with crisp outlines, "
    "bright saturated colors, no text, no watermark, no border, no frame. "
    "Fully transparent background."
)

# gpt-image-1 の透過処理は「ほぼ白」の領域を背景と誤認して抜いてしまう。白い
# 白衣・白い帽子などが穴になり、動画上でキャラが透けて見える原因になる。
# 白を使わせない指示を足したプロンプトで再試行する。
NO_WHITE_SUFFIX = (
    "IMPORTANT: do not use pure white (#ffffff) or near-white anywhere on the "
    "character. Render any white clothing as warm off-white / light cream / pale "
    "grey with clearly visible shading so it never matches the background. "
    "Every part of the character must be fully opaque and solid — no see-through, "
    "no translucent or faded areas."
)

# 内部の穴の許容割合（画像全体に対する%）。これを超えたら再生成する。
HOLE_RATIO_LIMIT = 0.5


def _interior_hole_ratio(path: Path) -> float:
    """キャラ内部にある「外周とつながっていない透明領域」の割合(%)を返す。

    アルファを二値化し、画像の外周から透明領域を flood fill して「外側の背景」を
    特定する。そこに到達しない透明画素＝シルエット内部の穴。
    """
    from PIL import Image, ImageDraw
    import numpy as np

    im = Image.open(path).convert("RGBA")
    alpha = np.array(im.getchannel("A"))
    binary = np.where(alpha < 128, 0, 255).astype(np.uint8)

    padded = Image.new("L", (im.width + 2, im.height + 2), 0)
    padded.paste(Image.fromarray(binary), (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128, thresh=0)
    outside = np.array(padded)[1:-1, 1:-1] == 128

    holes = (alpha < 128) & (~outside)
    return float(holes.mean() * 100)


def _load_env() -> None:
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _generate(prompt: str, out_path: Path, quality: str) -> None:
    payload = json.dumps({
        "model": "gpt-image-1",
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "quality": quality,
        "background": "transparent",
        "output_format": "png",
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=payload,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    b64 = data["data"][0]["b64_json"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(b64))


def _jobs_for_channel(channel_id: str, force: bool):
    raw_path = REPO_ROOT / "data" / "channels" / f"{channel_id}.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    for name, cfg in (raw.get("characters") or {}).items():
        appearance = (cfg.get("appearance") or "").strip()
        if not appearance:
            print(f"  ⚠️ {channel_id}/{name}: appearance 未設定 — スキップ")
            continue
        dir_name = cfg.get("dir") or cfg.get("slug") or name.lower()
        for expr in cfg.get("expressions") or ["normal"]:
            out_path = ASSETS_DIR / dir_name / f"{expr}.png"
            if out_path.exists() and not force:
                print(f"  ⏭️  exists: {out_path.relative_to(REPO_ROOT)}")
                continue
            expr_hint = EXPRESSION_PROMPTS.get(expr, f"{expr} expression")
            prompt = f"{appearance}. {expr_hint}. {STYLE_SUFFIX}"
            yield {
                "label": f"{channel_id}/{dir_name}/{expr}",
                "prompt": prompt,
                "out_path": out_path,
            }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("channels", nargs="+", help="channel_id（複数可）")
    ap.add_argument("--force", action="store_true", help="既存ファイルも再生成")
    ap.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--attempts", type=int, default=3,
                    help="内部の穴が閾値超過だった場合の最大生成回数")
    args = ap.parse_args()

    _load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        print("[ERR] OPENAI_API_KEY 未設定", file=sys.stderr)
        return 1

    jobs = []
    for cid in args.channels:
        print(f"📺 {cid}")
        jobs.extend(_jobs_for_channel(cid, args.force))

    if not jobs:
        print("生成対象なし。")
        return 0

    print(f"\n🎨 {len(jobs)} 枚を生成（quality={args.quality}, workers={args.workers}）")

    failures = []

    def _run(job):
        """生成 → 内部の穴を検査 → 超過なら白禁止プロンプトで再試行。"""
        tmp = job["out_path"].with_suffix(".gen.png")
        best = None  # (hole_ratio, bytes)
        try:
            for attempt in range(args.attempts):
                prompt = job["prompt"]
                if attempt > 0:
                    prompt = f"{prompt} {NO_WHITE_SUFFIX}"
                _generate(prompt, tmp, args.quality)
                ratio = _interior_hole_ratio(tmp)
                data = tmp.read_bytes()
                if best is None or ratio < best[0]:
                    best = (ratio, data)
                if ratio <= HOLE_RATIO_LIMIT:
                    break
                print(f"  ♻️ {job['label']}: 内部の穴 {ratio:.2f}% > {HOLE_RATIO_LIMIT}% — 再生成 "
                      f"({attempt + 1}/{args.attempts})")

            tmp.unlink(missing_ok=True)
            job["out_path"].write_bytes(best[1])
            mark = "✅" if best[0] <= HOLE_RATIO_LIMIT else "⚠️"
            note = "" if best[0] <= HOLE_RATIO_LIMIT else "  ← 穴が残存（要目視確認）"
            print(f"  {mark} {job['label']} 穴={best[0]:.2f}% → "
                  f"{job['out_path'].relative_to(REPO_ROOT)}{note}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"  ❌ {job['label']}: HTTP {e.code} {body}")
            failures.append(job["label"])
        except Exception as e:
            print(f"  ❌ {job['label']}: {type(e).__name__} {e}")
            failures.append(job["label"])
        finally:
            tmp.unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(_run, jobs))

    print(f"\n{'=' * 50}")
    print(f"完了: {len(jobs) - len(failures)}/{len(jobs)}")
    if failures:
        print("失敗: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
