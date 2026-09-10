#!/usr/bin/env python3
"""レンダリング環境の点検 — 「投稿が出ない」の原因がホスト側かを先に切り分ける。

2026-09-09 の実例:
    投稿 21本 → 1本。API も OAuth もサムネも正常で、**ERROR ログは0件**。
    ジョブは失敗しておらず、1フレームに 20〜162 秒かかっていただけだった。
    ワーカー2本が 11時間21分 / 16時間51分 のジョブに占有され、22件が滞留。

    翌日の実測: load 68.04（8コア）／ swap 20,146MB / 21,504MB（94%）／
    空き 24MB ／ `Image.alpha_composite(1080x1920)` が 670ms（健全 10〜20ms）。
    backend の CPU 時間は実時間90秒に対して 7.1 秒しか進んでいなかった。

    つまりコードではなくホストが原因。**投稿が止まったらまずこれを走らせる。**

    python3 backend/check_render_health.py

終了コード: 0 = ok / 1 = degraded / 2 = critical
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import render_health  # noqa: E402


def main(argv):
    snap = render_health.probe()
    print(render_health.format_section(snap))
    return {"ok": 0, "degraded": 1, "critical": 2}[snap["verdict"]]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
