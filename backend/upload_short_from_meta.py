#!/usr/bin/env python3
"""生成済みショートを _short_upload_meta.json からアップロードする（再生成しない）

run_channel_short_upload.py を SKIP_UPLOAD=1 で回した後、動画・サムネ・タイトル・
説明文をそのまま使って YouTube に上げ直すための後追いアップローダ。

  python upload_short_from_meta.py <meta.json> [<meta.json> ...]

- meta の privacy を使う（env SHORT_PRIVACY で上書き可）
- 既に upload 済み（meta.upload.video_id あり）の場合は二重投稿を防いでスキップ
  （FORCE_REUPLOAD=1 で強行）
- 成功時は meta を上書き更新して upload 結果を残す
"""

import json
import os
import sys
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

FORCE_REUPLOAD = os.environ.get("FORCE_REUPLOAD", "").strip() in ("1", "true", "yes")


def upload_one(meta_path: Path) -> dict:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    existing = (meta.get("upload") or {}).get("video_id")
    if existing and not FORCE_REUPLOAD:
        print(f"  ⏭️  既にアップロード済み（video_id={existing}）— スキップ")
        print("      再投稿するなら FORCE_REUPLOAD=1")
        return {"skipped": True, "video_id": existing, "url": (meta.get("upload") or {}).get("url")}

    video = Path(meta["short_video"])
    if not video.exists():
        raise FileNotFoundError(f"動画が見つかりません: {video}")
    thumb = meta.get("short_thumbnail")
    thumb = Path(thumb) if thumb else None

    privacy = os.environ.get("SHORT_PRIVACY") or meta.get("privacy") or "private"

    print(f"  channel:  {meta['channel_id']} → {meta['youtube_channel_id']}")
    print(f"  title:    {meta['short_title']}")
    print(f"  video:    {video.name} ({video.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  thumb:    {thumb.name if thumb and thumb.exists() else '(none)'}")
    print(f"  privacy:  {privacy}")

    from pipeline import youtube_uploader as yu

    r = yu.upload_video(
        video_path=str(video),
        title=meta["short_title"],
        description=meta.get("short_description") or "",
        tags=meta.get("tags") or None,
        thumbnail_path=str(thumb) if thumb and thumb.exists() else None,
        privacy=privacy,
        category_id=meta.get("category_id") or "24",
        is_short=True,
        channel_id=meta.get("youtube_channel_id"),
        auth_channel_id=meta.get("auth_channel_id") or meta.get("channel_id"),
    )

    meta["upload"] = r
    meta["privacy"] = privacy
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"  ✅ {r.get('url')}")
    return r


def main():
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print(__doc__)
        sys.exit(2)

    results = {}
    failed = False
    for p in paths:
        print(f"\n{'=' * 70}\n📤 {p}\n{'=' * 70}")
        try:
            results[str(p)] = upload_one(p)
        except Exception as e:
            import traceback
            traceback.print_exc()
            results[str(p)] = {"error": str(e)}
            failed = True

    print("\n\n========= RESULT =========")
    for p, r in results.items():
        if "error" in r:
            print(f"❌ {Path(p).parent.name}: {r['error']}")
        else:
            tag = " (skipped)" if r.get("skipped") else ""
            print(f"✅ {Path(p).parent.name}{tag}: {r.get('url')}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
