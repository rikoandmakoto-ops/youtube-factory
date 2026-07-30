#!/usr/bin/env python3
"""チャンネルバナー / アイコン画像を生成し、YouTube API でバナーを設定する。

  python -m scripts.setup_channel_branding pokemon-lab yokai-watch
  python -m scripts.setup_channel_branding pokemon-lab --dry-run   # 生成だけ

バナー:
  gpt-image-1 で 1536x1024 の背景アートを生成 → 中央 16:9 で切り出し → 2048x1152 に
  リサイズ → YouTube の「セーフエリア」(中央 1235x338) にチャンネル名を合成。
  セーフエリアの外はテレビ/PC でトリミングされるため、文字は必ず中央帯に置く。
  `channelBanners.insert` → `channels.update(part=brandingSettings)` で反映。

アイコン:
  800x800 の PNG を生成して assets/branding/<channel_id>/icon.png に保存する。
  **YouTube Data API v3 にチャンネルアイコン(アバター)を設定するメソッドは存在しない**
  ため、API 経由の適用は行わない（Google アカウント/YouTube Studio から手動設定）。

生成物: assets/branding/<channel_id>/{banner.png,banner_art.png,icon.png}
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
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
BRANDING_DIR = REPO_ROOT / "assets" / "branding"

BANNER_W, BANNER_H = 2048, 1152
SAFE_W, SAFE_H = 1235, 338          # 全デバイスで必ず見える中央領域
ICON_SIZE = 800

_FONT_SEARCH_JP = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

# 作品名を出さずに世界観だけを伝える、moderation 回避用のチャンネル別モチーフ。
BRANDING_SAFE_THEME = {
    "pokemon-lab": (
        "a bright research laboratory of creature biology — glowing specimen capsules, "
        "an open illustrated field guide, botanical sketches and a sunlit grassy horizon "
        "seen through a window, warm optimistic palette of red, amber and sky blue"
    ),
    "yokai-watch": (
        "a playful Japanese folklore night — paper lanterns, a torii gate, swirling "
        "mischievous wisps and shadow silhouettes, festival stalls, purple-and-gold "
        "twilight palette with a full moon"
    ),
}
BRANDING_SAFE_ICON = {
    "pokemon-lab": (
        "a glowing red-and-white sphere-shaped scientific specimen flask crossed with "
        "a magnifying glass, on a bright amber radial background"
    ),
    "yokai-watch": (
        "a round pocket-watch face fused with a grinning folklore mask and a small "
        "floating wisp, on a deep purple radial background"
    ),
}


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


def _gen_image(prompt: str, size: str, quality: str = "medium") -> bytes:
    payload = json.dumps({
        "model": "gpt-image-1", "prompt": prompt, "n": 1,
        "size": size, "quality": quality, "output_format": "png",
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations", data=payload,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return base64.b64decode(json.loads(r.read())["data"][0]["b64_json"])
    except urllib.error.HTTPError as e:
        # 400 の中身（content policy 拒否など）を捨てずに出す
        raise RuntimeError(f"images/generations HTTP {e.code}: {e.read().decode()[:600]}") from None


def _gen_image_safe(prompt: str, safe_prompt: str, size: str, quality: str, label: str) -> bytes:
    """moderation_blocked なら IP 由来の記述を落とした安全プロンプトで再試行。

    チャンネルの concept には「ポケモン」「妖怪ウォッチ」等の商標名が入っており、
    それをそのまま渡すと既存キャラに似た絵が出て output moderation で弾かれる
    （code=moderation_blocked, stage=output）。その場合は作品名を含まない
    抽象的なアートディレクションのみで描き直す。
    """
    try:
        return _gen_image(prompt, size, quality)
    except RuntimeError as e:
        if "moderation_blocked" not in str(e):
            raise
        print(f"  ⚠️ {label}: moderation_blocked — 作品名を除いた安全プロンプトで再試行")
        return _gen_image(safe_prompt, size, quality)


def _fit_font(draw, text: str, max_w: int, max_h: int):
    """セーフエリアに収まる最大サイズの日本語フォントを返す。"""
    from PIL import ImageFont
    path = next((f for f in _FONT_SEARCH_JP if os.path.exists(f)), None)
    for size in range(160, 40, -4):
        font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font, stroke_width=max(2, size // 18))
        if (box[2] - box[0]) <= max_w and (box[3] - box[1]) <= max_h:
            return font, size
    return (ImageFont.truetype(path, 44) if path else ImageFont.load_default()), 44


def _build_banner(art_bytes: bytes, title: str, tagline: str, accent, out_art: Path,
                  out_banner: Path) -> None:
    from PIL import Image, ImageDraw, ImageFilter
    import io

    out_art.write_bytes(art_bytes)
    art = Image.open(io.BytesIO(art_bytes)).convert("RGB")

    # 中央 16:9 で切り出して 2048x1152 へ
    target_h = int(art.width * BANNER_H / BANNER_W)
    if target_h <= art.height:
        top = (art.height - target_h) // 2
        art = art.crop((0, top, art.width, top + target_h))
    else:
        target_w = int(art.height * BANNER_W / BANNER_H)
        left = (art.width - target_w) // 2
        art = art.crop((left, 0, left + target_w, art.height))
    banner = art.resize((BANNER_W, BANNER_H), Image.LANCZOS).convert("RGBA")

    # セーフエリアだけ暗く落として文字の可読性を確保
    sx, sy = (BANNER_W - SAFE_W) // 2, (BANNER_H - SAFE_H) // 2
    scrim = Image.new("RGBA", (BANNER_W, BANNER_H), (0, 0, 0, 0))
    ImageDraw.Draw(scrim).rounded_rectangle(
        [sx - 40, sy - 24, sx + SAFE_W + 40, sy + SAFE_H + 24],
        radius=48, fill=(0, 0, 0, 130))
    banner = Image.alpha_composite(banner, scrim.filter(ImageFilter.GaussianBlur(18)))

    draw = ImageDraw.Draw(banner)
    font, size = _fit_font(draw, title, SAFE_W - 80, int(SAFE_H * 0.52))
    stroke = max(3, size // 16)
    tb = draw.textbbox((0, 0), title, font=font, stroke_width=stroke)
    tx = (BANNER_W - (tb[2] - tb[0])) // 2 - tb[0]
    ty = sy + int(SAFE_H * 0.16) - tb[1]
    draw.text((tx, ty), title, font=font, fill=(255, 255, 255),
              stroke_width=stroke, stroke_fill=(20, 20, 28))

    if tagline:
        from PIL import ImageFont
        path = next((f for f in _FONT_SEARCH_JP if os.path.exists(f)), None)
        tf = ImageFont.truetype(path, max(30, size // 3)) if path else ImageFont.load_default()
        gb = draw.textbbox((0, 0), tagline, font=tf, stroke_width=4)
        gx = (BANNER_W - (gb[2] - gb[0])) // 2 - gb[0]
        gy = sy + int(SAFE_H * 0.66) - gb[1]
        # card_accent は暗い色（妖怪ラボは濃紫）のこともあり、暗い背景に直に置くと
        # 沈んで読めない。白へ寄せて明度を確保する。
        tint = tuple(int(c + (255 - c) * 0.55) for c in tuple(accent)[:3])
        draw.text((gx, gy), tagline, font=tf, fill=tint,
                  stroke_width=4, stroke_fill=(20, 20, 28))

    banner.convert("RGB").save(out_banner, "PNG")


def _set_banner(channel_id: str, banner_path: Path) -> dict:
    """channelBanners.insert → channels.update でバナーを反映。"""
    sys.path.insert(0, str(BACKEND_DIR))
    from pipeline import youtube_oauth as yo
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = yo.get_credentials_for(channel_id)
    if creds is None:
        raise RuntimeError(f"'{channel_id}' の YouTube 認証情報がありません（UI で連携が必要）")
    yt = build("youtube", "v3", credentials=creds)

    up = yt.channelBanners().insert(
        body={},
        media_body=MediaFileUpload(str(banner_path), mimetype="image/png", resumable=False),
    ).execute()
    url = up.get("url")
    if not url:
        raise RuntimeError(f"channelBanners.insert が url を返しませんでした: {up}")

    mine = yt.channels().list(part="brandingSettings", mine=True).execute()
    if not mine.get("items"):
        raise RuntimeError("channels.list(mine=True) が空です")
    item = mine["items"][0]
    bs = item.get("brandingSettings") or {}
    bs.setdefault("image", {})["bannerExternalUrl"] = url

    yt.channels().update(
        part="brandingSettings",
        body={"id": item["id"], "brandingSettings": bs},
    ).execute()
    return {"youtube_channel_id": item["id"], "banner_url": url}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("channels", nargs="+")
    ap.add_argument("--dry-run", action="store_true", help="画像生成のみ（API 反映しない）")
    ap.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--use-concept", action="store_true",
                    help="チャンネル concept を埋め込んだプロンプトで描く（既存IPに似る恐れあり）")
    ap.add_argument("--reuse-art", action="store_true",
                    help="既存の banner_art.png / icon.png を使い、生成をスキップ")
    args = ap.parse_args()

    _load_env()
    if not os.environ.get("OPENAI_API_KEY") and not args.reuse_art:
        print("[ERR] OPENAI_API_KEY 未設定", file=sys.stderr)
        return 1

    failures = []
    for cid in args.channels:
        print(f"\n{'=' * 66}\n📺 {cid}\n{'=' * 66}")
        try:
            raw = json.loads((REPO_ROOT / "data" / "channels" / f"{cid}.json")
                             .read_text(encoding="utf-8"))
            name = raw.get("name") or cid
            concept = (raw.get("concept") or "")[:340]
            style = (raw.get("video_format") or {}).get("illustration_style") or {}
            accent = ((raw.get("video_format") or {}).get("short_illustrations") or {}).get(
                "card_accent") or [255, 210, 60]
            tagline = raw.get("short_series_name", "").rstrip("：:") or ""

            out_dir = BRANDING_DIR / cid
            out_dir.mkdir(parents=True, exist_ok=True)
            art_p, banner_p, icon_p = (out_dir / "banner_art.png",
                                       out_dir / "banner.png", out_dir / "icon.png")

            if args.reuse_art and art_p.exists():
                art_bytes = art_p.read_bytes()
                print("  ♻️ 既存 banner_art.png を再利用")
            else:
                # 作品名を含む concept をそのまま渡すと既存キャラそっくりの絵が出て
                # しまう（妖怪ウォッチで実際にジバニャン/ウィスパー風が生成された）。
                # チャンネルの「顔」に他社IPの模倣を置くのは避けるため、既定では
                # 作品名を出さない BRANDING_SAFE_* のモチーフだけで描かせる。
                # --use-concept で従来の concept 埋め込みプロンプトに切り替えられる。
                banner_prompt = (
                    f"Wide YouTube channel banner artwork for a Japanese 'yukkuri' "
                    f"commentary channel. Channel concept: {concept}. "
                    f"Art direction: {style.get('art_style', 'clean flat anime illustration')}. "
                    "Rich thematic illustration filling the LEFT and RIGHT thirds of the frame, "
                    "with the CENTRAL horizontal band kept visually calm and uncluttered "
                    "(soft gradient or simple backdrop) so a channel title can be overlaid there. "
                    "No text, no letters, no words, no logo, no watermark, no close-up faces. "
                    "Cinematic, vivid, high contrast, 16:9 composition."
                )
                safe_banner_prompt = (
                    "Wide 16:9 YouTube channel banner background artwork, "
                    f"{style.get('art_style', 'clean flat anime illustration')}, "
                    f"{BRANDING_SAFE_THEME.get(cid, 'mysterious study desk with old books, lanterns and soft glow')}. "
                    "Rich detail on the LEFT and RIGHT thirds, central horizontal band kept calm "
                    "and uncluttered for a title overlay. Entirely original artwork — no existing "
                    "franchise characters, no mascots, no creatures resembling any known media. "
                    "No text, no letters, no logo, no watermark. Cinematic, vivid, high contrast."
                )
                print("  🎨 バナーアート生成中…")
                primary = banner_prompt if args.use_concept else safe_banner_prompt
                art_bytes = _gen_image_safe(primary, safe_banner_prompt,
                                            "1536x1024", args.quality, "banner")

            print("  🖼  バナー合成中（セーフエリアにチャンネル名）…")
            _build_banner(art_bytes, name, tagline, accent, art_p, banner_p)
            print(f"     → {banner_p.relative_to(REPO_ROOT)} ({BANNER_W}x{BANNER_H})")

            if not (args.reuse_art and icon_p.exists()):
                icon_prompt = (
                    f"Circular-friendly YouTube channel avatar icon for: {concept}. "
                    f"Art direction: {style.get('art_style', 'clean flat anime illustration')}. "
                    "ONE bold central emblem/mascot motif, centered, filling the frame, "
                    "thick clean outlines, flat vivid colors, high contrast, instantly readable "
                    "at very small size. No text, no letters, no watermark. Simple solid or "
                    "subtle radial background."
                )
                safe_icon_prompt = (
                    "YouTube channel avatar icon, bold centered emblem, "
                    f"{style.get('art_style', 'clean flat anime illustration')}, "
                    f"{BRANDING_SAFE_ICON.get(cid, 'a glowing magnifying glass over an old scroll')}. "
                    "Thick clean outlines, flat vivid colors, high contrast, readable at small size. "
                    "Entirely original design — no existing franchise characters or mascots. "
                    "No text, no letters, no watermark. Simple radial background."
                )
                print("  🎨 アイコン生成中…")
                primary_icon = icon_prompt if args.use_concept else safe_icon_prompt
                icon_bytes = _gen_image_safe(primary_icon, safe_icon_prompt,
                                             "1024x1024", args.quality, "icon")
                from PIL import Image
                import io
                (Image.open(io.BytesIO(icon_bytes)).convert("RGB")
                 .resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS).save(icon_p, "PNG"))
            print(f"     → {icon_p.relative_to(REPO_ROOT)} ({ICON_SIZE}x{ICON_SIZE})")

            if args.dry_run:
                print("  ⏭️  --dry-run: API 反映はスキップ")
                continue

            print("  📤 バナーを YouTube に設定中…")
            r = _set_banner(cid, banner_p)
            print(f"  ✅ バナー設定完了: {r['youtube_channel_id']}")
            print("  ℹ️  アイコン(アバター)は YouTube Data API v3 に設定メソッドが無いため未適用。"
                  f" {icon_p.relative_to(REPO_ROOT)} を YouTube Studio から手動設定してください。")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ❌ {cid}: {type(e).__name__} {e}")
            failures.append(cid)

    print(f"\n{'=' * 66}")
    print(f"完了: {len(args.channels) - len(failures)}/{len(args.channels)}")
    if failures:
        print("失敗: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
