#!/usr/bin/env python3
"""
gen_thumbs_v4_all.py が生成した v4.1 サムネを daily-science の実動画へ反映する。

`gen_thumbs_v4_all.py` は PNG を書き出すだけで YouTube には一切上げない。
そのため 2026-08-27 に 26 本ぶん生成しても、チャンネル上のサムネは古いままだった。
このスクリプトがその欠けている後半（thumbnails.set）を担う。

使い方:
    python3 apply_thumbs_v4_all.py --dry-run    # 対応表と現状の確認だけ
    python3 apply_thumbs_v4_all.py              # 26本すべて反映
    python3 apply_thumbs_v4_all.py 9 13-26      # 番号指定
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
THUMB_DIR = ROOT / "output" / "daily-science" / "thumbnails" / "v4_all"
CHANNEL = "daily-science"
MAX_BYTES = 2 * 1024 * 1024  # YouTube のカスタムサムネ上限

sys.path.insert(0, str(BACKEND_DIR))

_env = BACKEND_DIR / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())


# (番号, サムネのstem, YouTube動画ID, タイトル照合用キーワード)
# キーワードは「その動画に必ず含まれる語」。取り違えたまま上書きすると
# 復旧できないので、アップロード前に必ず実タイトルと突き合わせる。
MAPPING = [
    (1,  "01_42do",          "0rV1a0lshzg", "42度"),
    (2,  "02_haranooto",     "2ugo8k-niHw", "お腹の音"),
    (3,  "03_yumekioku",     "KV7ZYcFA2lc", "夢が『選ぶ』記憶"),
    (4,  "04_yorusumaho",    "MpFJSJ8V-d8", "ブルーライトのせいじゃなかった"),
    (5,  "05_curtain",       "nilcKHrAuTI", "空気の流れがまさかの原因"),
    (6,  "06_mieno",         "_bAjl_LGy4k", "『3割増し』"),
    (7,  "07_souzoku",       "4_RjiR4WHTg", "相続"),
    (8,  "08_yubipaki",      "dJv-ZdzK7Oc", "指を鳴らした瞬間"),
    (9,  "09_ongakunamida",  "B4Z0yJ5HZUo", "音楽で涙"),
    (10, "10_akubi",         "IBSmic--0Yw", "あくび"),
    (11, "11_suitsuku",      "GolB0NPi1AY", "カーテンが張り付く秘密"),
    (12, "12_mizutamari",    "Izz6LIO3G-s", "水たまりの色が変わる"),
    (13, "13_sanso",         "XMOe7mt_Zmg", "酸素が1秒消えたら"),
    (14, "14_mewarui",       "eU9fUhDb2O4", "暗い部屋でスマホ"),
    (15, "15_seiza",         "KLXvN5VrotM", "星座の形"),
    (16, "16_amenohi",       "r7fbiiF1NGc", "雨の日に気分が落ち込む"),
    (17, "17_mizunazo",      "HYK_Em0OvkQ", "水たまりができる理由"),
    (18, "18_hoshizora",     "b8imAy_9jiw", "星空が見えなくなる"),
    (19, "19_kansetsu",      "8L3Ld7L9BPo", "指はポキポキ"),
    (20, "20_amenonioi",     "tXwJpJgH3Pk", "雨の匂いの正体"),
    (21, "21_hashirenai",    "L_LrapHeMPo", "夢の中では走れない"),
    (22, "22_shiwashiwa",    "DhafqbQRDBE", "指がシワシワ"),
    (23, "23_nekoyasai",     "Qb91l1LO5-0", "キュウリで飛び上がる"),
    (24, "24_senzai",        "dPGqflt0DYw", "洗剤vs激落ちくん"),
    (25, "25_atamanokyoku",  "Ml1JNgEK8iQ", "イヤーワーム"),
    (26, "26_canon",         "fflI31zgYIU", "カノン進行"),
]


def _parse_selection(argv: list) -> set:
    """'9' '13-26' のような指定を番号集合へ。無指定なら全部。"""
    picked = set()
    for a in argv:
        if a.startswith("-"):
            continue
        if "-" in a:
            lo, hi = a.split("-", 1)
            picked.update(range(int(lo), int(hi) + 1))
        else:
            picked.add(int(a))
    return picked or {n for n, _, _, _ in MAPPING}


def _shrink_if_needed(path: Path, work_dir: Path) -> Path:
    """2MB を超える PNG は JPEG に落として上限内に収める。"""
    if path.stat().st_size <= MAX_BYTES:
        return path
    from PIL import Image

    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / (path.stem + ".jpg")
    im = Image.open(path).convert("RGB")
    for quality in (92, 85, 78, 70, 60):
        im.save(out, "JPEG", quality=quality, optimize=True)
        if out.stat().st_size <= MAX_BYTES:
            break
    return out


def main() -> int:
    argv = sys.argv[1:]
    dry_run = "--dry-run" in argv
    picked = _parse_selection(argv)

    from pipeline import youtube_oauth as yo
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = yo.get_credentials_for(CHANNEL)
    if not creds:
        print(f"❌ {CHANNEL} が OAuth 未連携です")
        return 1
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    targets = [m for m in MAPPING if m[0] in picked]
    ids = [m[2] for m in targets]

    # 実タイトルを引いて対応表を検証する
    titles = {}
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute()
        for it in resp.get("items", []):
            titles[it["id"]] = it["snippet"]["title"]

    problems = []
    for num, stem, vid, keyword in targets:
        png = THUMB_DIR / f"{stem}.png"
        title = titles.get(vid)
        if not png.exists():
            problems.append(f"#{num} {stem}: PNG が無い ({png})")
        if title is None:
            problems.append(f"#{num} {stem}: 動画 {vid} が取得できない（削除済み?）")
        elif keyword not in title:
            problems.append(f"#{num} {stem}: {vid} のタイトルに『{keyword}』が無い → {title}")

    print(f"📋 対象 {len(targets)} 本 / チャンネル {CHANNEL}\n")
    for num, stem, vid, keyword in targets:
        title = titles.get(vid, "(取得失敗)")
        mark = "✅" if (THUMB_DIR / f"{stem}.png").exists() and keyword in (title or "") else "⚠️"
        print(f"{mark} #{num:>2} {stem:<18} {vid}  {title[:52]}")

    if problems:
        print("\n❌ 対応表の検証に失敗しました:")
        for p in problems:
            print(f"   - {p}")
        return 1

    if dry_run:
        print("\n(--dry-run のため反映しません)")
        return 0

    work_dir = ROOT / "output" / "daily-science" / "thumbnails" / "v4_all_compressed"
    ok, ng = 0, 0
    print()
    for num, stem, vid, _kw in targets:
        src = _shrink_if_needed(THUMB_DIR / f"{stem}.png", work_dir)
        mime = "image/jpeg" if src.suffix == ".jpg" else "image/png"
        try:
            yt.thumbnails().set(
                videoId=vid,
                media_body=MediaFileUpload(str(src), mimetype=mime),
            ).execute()
            ok += 1
            print(f"✅ #{num:>2} {stem:<18} → {vid}")
        except Exception as e:
            ng += 1
            print(f"❌ #{num:>2} {stem:<18} → {vid}: {e}")
        time.sleep(1)  # クォータと連打回避

    print(f"\n完了: 成功 {ok} / 失敗 {ng}")
    return 0 if ng == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
