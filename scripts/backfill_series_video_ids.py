#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""series_suggestions.queued_video_id のバックフィル。

承認された続編はキュー投入時点では動画IDが無く、レンダ・公開後も誰も書き戻さない
ため、続編の効果測定（登録/千の続編 vs 非続編）がリンク切れになっていた（2026-10-06発見）。

経路: suggestion.suggested_title ≒ scenario.theme.title（正規化16字）
      → scenario.title（最終タイトル）→ video_metrics.title 前方一致 → video_id

    python3 scripts/backfill_series_video_ids.py        # 書き込み
    python3 scripts/backfill_series_video_ids.py --dry  # 確認のみ
"""
import json, glob, re, sqlite3, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DRY = "--dry" in sys.argv


def norm(t: str) -> str:
    return re.sub(r"[\s、。「」！？!?#＃・…]", "", (t or ""))[:16]


def main() -> int:
    con = sqlite3.connect(REPO / "data" / "analytics" / "analytics.db")
    con.row_factory = sqlite3.Row
    sugs = [dict(r) for r in con.execute(
        "select id, suggested_title, channel_id from series_suggestions "
        "where status='approved' and (queued_video_id is null or queued_video_id='')")]
    if not sugs:
        print("バックフィル対象なし")
        return 0
    smap = {}
    for s in sugs:
        smap.setdefault(norm(s["suggested_title"]), s)

    updated = 0
    for f in glob.glob(str(REPO / "data/scenarios/*/*.json")) + \
             glob.glob(str(REPO / "data/scenarios/*/archive/*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        th = d.get("theme")
        key = norm(th.get("title") if isinstance(th, dict) else "")
        s = smap.get(key)
        if not s:
            continue
        final_title = (d.get("title") or "").strip()
        if not final_title:
            continue
        row = con.execute(
            "select video_id from video_metrics where channel_id=? and title like ? limit 1",
            (s["channel_id"], final_title[:20] + "%")).fetchone()
        if not row:
            continue
        print(f"  {s['channel_id']:13} {row['video_id']}  ← {final_title[:38]}")
        if not DRY:
            con.execute("update series_suggestions set queued_video_id=? where id=?",
                        (row["video_id"], s["id"]))
        updated += 1
        smap.pop(key, None)
    if not DRY:
        con.commit()
    print(f"{'(dry) ' if DRY else ''}backfilled: {updated} / {len(sugs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
