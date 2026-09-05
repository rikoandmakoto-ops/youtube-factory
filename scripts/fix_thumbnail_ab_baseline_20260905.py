#!/usr/bin/env python3
"""thumbnail_ab_tests.channel_avg_ctr の単位混在を修正する（2026-09-05 指揮者）。

## 何が壊れていたか

`thumbnail_ab_tests.channel_avg_ctr` に 2 種類の単位が混在していた。

    daily-science: 0.029113044331873048  ← 比率（正しい）
    daily-science: 42.909021329774575    ← 百分率スケールの遺物（誤り）
    scp-lab:       37.285581033982794    ← 同上

一方 `video_metrics.ctr` は全 1,352 行が 0.0029〜0.3333 の比率で、
100 以上どころか 1 以上の値すら 1 行も存在しない（2026-09-05 実測）。
つまり 42.4 / 37.3 は現行スキーマではあり得ない値で、
過去に ctr を百分率で保存していた頃のベースラインが残ったものと判断できる。

`thumbnail_ab_test.py` の切替判定は

    last_check_ctr < channel_avg_ctr * threshold_ratio(0.8)

なので、ベースラインが 1456 倍ズレていると全動画が常に「基準割れ」と判定される。
実際 19 件中 17 件が status=monitoring のまま放置され、切替は 2 件しか発生していない。
サムネ A/B が事実上機能していない状態だった。

## この修正がやること

現行の `video_metrics.ctr`（比率）から channel_avg_ctr を再計算して上書きする。
`_channel_avg_ctr()` / `improvement_queue.channel_avg_ctr()` と同じ母集団条件
（ctr > 0、views >= 100）を使うので、以後の再計算値とも整合する。

## 実行方法（Mac 上、バックエンド停止中に実行すること）

    cd ~/Developer/youtube-factory
    python3 scripts/fix_thumbnail_ab_baseline_20260905.py            # ドライラン
    python3 scripts/fix_thumbnail_ab_baseline_20260905.py --apply    # 実際に書き込む

※ 指揮者の実行環境（サンドボックス）からは analytics.db への書き込みが
   disk I/O error になるため、DB 更新のみ手元実行に切り出している。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "analytics" / "analytics.db"

MIN_VIEWS = 100


def recompute_baselines(conn: sqlite3.Connection) -> dict[str, tuple[float, int]]:
    """ch 別に video_metrics.ctr（比率）の平均を返す。"""
    out: dict[str, tuple[float, int]] = {}
    for row in conn.execute(
        "SELECT channel_id, AVG(ctr) AS a, COUNT(*) AS n FROM video_metrics "
        "WHERE ctr > 0 AND views >= ? GROUP BY channel_id",
        (MIN_VIEWS,),
    ):
        out[row["channel_id"]] = (float(row["a"]), int(row["n"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="実際に DB を更新する")
    args = ap.parse_args()

    if not DB.exists():
        print(f"DB が見つからない: {DB}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # 前提の再確認: ctr が比率であることを実データで検証してから書き換える
    bad = conn.execute("SELECT COUNT(*) FROM video_metrics WHERE ctr >= 1").fetchone()[0]
    if bad:
        print(
            f"中止: video_metrics.ctr に 1 以上の行が {bad} 件ある。"
            "比率前提が崩れているので手で確認すること。",
            file=sys.stderr,
        )
        return 2

    baselines = recompute_baselines(conn)
    print("再計算ベースライン（比率）:")
    for ch, (val, n) in sorted(baselines.items()):
        print(f"  {ch:20} {val:.5f}  (n={n})")
    print()

    rows = list(
        conn.execute(
            "SELECT video_id, channel_id, channel_avg_ctr FROM thumbnail_ab_tests"
        )
    )
    now = int(time.time())
    changes: list[tuple[str, str, float | None, float]] = []
    for row in rows:
        entry = baselines.get(row["channel_id"])
        if entry is None:
            continue
        new = entry[0]
        old = row["channel_avg_ctr"]
        if old is None or abs(float(old) - new) > 1e-9:
            changes.append((row["video_id"], row["channel_id"], old, new))

    for vid, ch, old, new in changes:
        old_s = "None" if old is None else f"{old:.5f}"
        print(f"  {ch:16} {vid}  {old_s} -> {new:.5f}")
    print(f"\n対象 {len(changes)}/{len(rows)} 件")

    if not args.apply:
        print("\n（ドライラン。書き込むには --apply を付ける）")
        return 0

    for vid, _ch, _old, new in changes:
        conn.execute(
            "UPDATE thumbnail_ab_tests SET channel_avg_ctr = ?, updated_at = ? "
            "WHERE video_id = ?",
            (new, now, vid),
        )
    conn.commit()
    print(f"\n更新した: {len(changes)} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
