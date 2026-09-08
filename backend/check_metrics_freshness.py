#!/usr/bin/env python3
"""video_metrics の欠測点検 — 横断集計をする前に必ずこれを通すこと。

`video_metrics` は run_daily_pdca が ch を1つずつ sync するので
**23:01〜23:19 に ch名のアルファベット順で埋まる**。23:20 より前に
横断集計すると後半の ch だけが「0行」に見え、取得障害と誤診する
（09-05/06 の「yokai-watch 2日連続0行」がこれ）。

    python3 backend/check_metrics_freshness.py            # 今日
    python3 backend/check_metrics_freshness.py 2026-09-08 # 日付指定

終了コード: 0 = 欠測なし / 1 = 欠測あり
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analytics import freshness  # noqa: E402


def main(argv):
    date = argv[1] if len(argv) > 1 else None
    cov = freshness.snapshot_coverage(date=date)
    print(freshness.coverage_markdown(cov))
    return 0 if cov["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
