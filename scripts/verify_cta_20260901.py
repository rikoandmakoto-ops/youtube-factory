#!/usr/bin/env python3
"""生成済みショート台本の CTA 遵守率を測る（2026-09-01 新設）。

「実際にレンダリングされる行」＝ scenario .md の `## ショートシナリオ` 節の
最終行だけを見る。フルシナリオ側の `### CTA / クロージング` には CTA があるのに
ショート側には無い、という取り違えが 08-31 の点検で起きたため、
ここでは意図的にショート節しか読まない。

使い方:
    python3 scripts/verify_cta_20260901.py            # 直近7日
    python3 scripts/verify_cta_20260901.py 2026-08-29 # 指定日以降
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

LIKE = re.compile(r"高評価|いいね|グッドボタン")
SUBSCRIBE = re.compile(r"チャンネル登録|登録|フォロー")
SHORT_SECTION = re.compile(r"##\s*ショートシナリオ\s*\n(.*?)(?=\n##\s|\Z)", re.S)
SPEAKER = re.compile(r"^-\s*(\*\*.+?\*\*[:：])?\s*")


def short_lines(text: str) -> list[str]:
    match = SHORT_SECTION.search(text)
    if not match:
        return []
    return [
        SPEAKER.sub("", line.strip())
        for line in match.group(1).split("\n")
        if line.strip().startswith("-")
    ]


def main() -> int:
    since = sys.argv[1] if len(sys.argv) > 1 else (
        dt.date.today() - dt.timedelta(days=7)
    ).isoformat()

    stats: dict[str, list] = defaultdict(lambda: [0, 0, 0, 0, []])
    for path in (REPO / "data" / "scenarios").rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = short_lines(text)
        if not lines:
            continue
        gen = re.search(r"generated_at:\s*(\d{4}-\d{2}-\d{2})", text)
        date = gen.group(1) if gen else dt.date.fromtimestamp(
            path.stat().st_mtime
        ).isoformat()
        if date < since:
            continue
        channel = re.search(r"channel_id:\s*(\S+)", text)
        channel_id = channel.group(1) if channel else path.name.split("_")[0]

        last = lines[-1]
        has_like = bool(LIKE.search(last))
        has_sub = bool(SUBSCRIBE.search(last))
        entry = stats[channel_id]
        entry[0] += 1
        entry[1] += has_like
        entry[2] += has_sub
        entry[3] += has_like and has_sub
        if not (has_like and has_sub):
            entry[4].append((date, last))

    if not stats:
        print(f"{since} 以降のショート台本が見つかりませんでした。")
        return 0

    print(f"=== ショート最終行の CTA 遵守率（{since} 以降）===\n")
    print(f"{'channel':18s} {'n':>3s} {'高評価':>8s} {'登録':>8s} {'両方':>8s}")
    total = [0, 0, 0, 0]
    for channel_id, (n, like, sub, both, _) in sorted(stats.items()):
        print(
            f"{channel_id:18s} {n:3d} "
            f"{like:3d}({like / n * 100:3.0f}%) "
            f"{sub:3d}({sub / n * 100:3.0f}%) "
            f"{both:3d}({both / n * 100:3.0f}%)"
        )
        total[0] += n
        total[1] += like
        total[2] += sub
        total[3] += both

    n = total[0]
    print(
        f"\n{'合計':18s} {n:3d} "
        f"{total[1]:3d}({total[1] / n * 100:3.0f}%) "
        f"{total[2]:3d}({total[2] / n * 100:3.0f}%) "
        f"{total[3]:3d}({total[3] / n * 100:3.0f}%)"
    )
    print("\n[基準] 2026-08-29〜31 の実測(n=32): 高評価 50% / 登録 38% / 両方 19%")
    print("       cta_enforcer 導入後は 両方 100% が期待値。")

    violations = [(c, d, t) for c, v in stats.items() for d, t in v[4]]
    if violations:
        print(f"\n=== 未遵守 {len(violations)}件 ===")
        for channel_id, date, last in sorted(violations)[:20]:
            print(f"  [{channel_id} {date}] {last[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
