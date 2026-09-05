#!/usr/bin/env python3
"""辻褄の合わない video_metrics スナップショットを洗い直す（2026-09-05 指揮者）。

## 何が壊れていたか

2026-09-04 の取得に `views=0` なのに `avg_view_percentage>0` の行が 10 件あった
（通常は1〜5件、全期間で53件）。維持率は再生があって初めて定義されるので、
この組み合わせは実績としてありえない。

`fetch_video_metrics` は1動画につき2本の Analytics クエリを投げている。

  - `_query_video_analytics` … views / watch_time / likes ほか。**例外時は `{}`**
  - `_query_video_ctr`       … avg_view_percentage。例外時も 0 を返す

前者だけが落ちると `merged.get("views", 0)` が 0 になり、後者の維持率だけが残った
矛盾行が書かれる。例: company-facts zq6I-VSqt5k は 09-03 に views=28 / 視聴秒29
だったのが、09-04 に views=0 / 視聴秒0 / 維持率49.65% / impressions=215 になった。

## ⚠️ 「累積値が減った35本」は破損ではない

`MEMORY_UPDATE_20260905.md` §0 の「量的指標は累積カウンタ」は誤り。
`fetch_video_metrics` は **30日窓**の集計（`start = end - 30日`）を投げているので、
公開30日を過ぎた動画は初動の再生が窓から抜けて正当に減る。
例: daily-science hoQaClKwu60 は 08-05 公開で、09-03 に 1169 → 09-04 に 2。
30日窓の開始が公開日を追い越しただけで、取得不良ではない。
**単調増加を強制する修正を入れてはいけない**（古い動画の実データを壊す）。

## この修正がやること

書き込み側は `youtube_analytics.fetch_video_metrics`（取得失敗の動画はその日を
書かない）と `store._guard_partial_fetch()`（矛盾行を弾く）で今後を守る。
このスクリプトは **すでに DB に入ってしまった行** を同じ判定で洗い直す。
日付の古い順に処理するので、連続して壊れた日も順に埋まる。

判定は書き込み側と同一の関数を import して使う（条件が二重管理にならないように）。

## 実行方法（Mac 上、バックエンド停止中に実行すること）

    cd ~/Developer/youtube-factory
    python3 scripts/repair_video_metrics_20260905.py                 # ドライラン
    python3 scripts/repair_video_metrics_20260905.py --apply         # 実際に書き込む
    python3 scripts/repair_video_metrics_20260905.py --since 2026-09-04 --apply
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from pipeline.analytics import store  # noqa: E402

FIELDS = (
    "views", "watch_time_minutes", "avg_view_duration", "avg_view_percentage",
    "impressions", "ctr", "likes", "comments", "shares", "subscribers_gained",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="実際に DB を更新する")
    ap.add_argument("--since", default="2026-01-01",
                    help="この日付以降のスナップショットを洗い直す（既定 2026-01-01＝全期間）")
    args = ap.parse_args()

    if not store.DB_PATH.exists():
        print(f"DB が見つからない: {store.DB_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(store.DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = list(conn.execute(
        "SELECT * FROM video_metrics WHERE date >= ? ORDER BY date ASC, video_id ASC",
        (args.since,),
    ))
    print(f"対象スナップショット: {len(rows)} 行（{args.since} 以降）\n")

    fixed = 0
    for row in rows:
        prev = store._previous_snapshot(conn, row["video_id"], row["date"])
        incoming = {f: row[f] for f in FIELDS}
        guarded = store._guard_partial_fetch(prev, incoming, row["video_id"])
        changed = {f: (incoming[f], guarded[f]) for f in FIELDS
                   if incoming[f] != guarded[f]}
        if not changed:
            continue
        fixed += 1
        detail = ", ".join(f"{f} {o}→{n}" for f, (o, n) in changed.items())
        print(f"  {row['date']} {row['channel_id']:16} {row['video_id']}  {detail}")
        if args.apply:
            conn.execute(
                "UPDATE video_metrics SET "
                + ", ".join(f"{f} = ?" for f in FIELDS)
                + " WHERE video_id = ? AND date = ?",
                tuple(guarded[f] for f in FIELDS) + (row["video_id"], row["date"]),
            )

    print(f"\n差し戻し対象: {fixed}/{len(rows)} 行")
    if args.apply:
        conn.commit()
        print("更新した。")
    else:
        print("（ドライラン。書き込むには --apply を付ける）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
