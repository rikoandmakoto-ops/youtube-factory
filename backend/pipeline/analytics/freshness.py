"""freshness — その日の `video_metrics` が全チャンネル揃っているかを見る。

背景（2026-09-09）:
    `video_metrics` は **23:01〜23:19 にチャンネル名のアルファベット順で
    埋まる**（`run_daily_pdca` がチャンネルを1つずつ順に sync するため。
    09-08 の点検中に scp-lab 18→50行、yokai-watch 0→48行 が埋まるのを観測）。
    そのため 23:20 より前に横断集計をすると、**後半のチャンネルだけが
    「欠測」に見える**。09-05/06 に「yokai-watch が2日連続0行」と報告した
    のはおそらくこれで、取得側の障害ではなかった。

    「集計を遅らせる」だけでは、次に sync が遅くなった日に同じ誤診が出る。
    集計の入口で**充足を機械的に確認**し、揃っていなければレポートに
    「欠測」と明示する（0行を実績0と読ませない）。

使い方:
    from pipeline.analytics import freshness
    cov = freshness.snapshot_coverage()          # 今日ぶん
    if not cov["ok"]:
        print(freshness.coverage_markdown(cov))  # どのchが未取得か

CLI:
    python3 backend/check_metrics_freshness.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "analytics" / "analytics.db"
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"

JST = timezone(timedelta(hours=9))

# sync が全ch分を書き終わる想定時刻。run_daily_pdca の起動（launchd
# com.youtube-factory.pdca）＋ 実測所要 約20分（09-08 は 23:01〜23:19）に
# 余裕を足したもの。2026-09-09 に起動を 23:00 → 22:30 へ前倒ししたので、
# 23:00 には揃っている。ここを過ぎても揃わないなら「まだ走っている」では
# なく本当の欠測として扱う。**PDCA の起動時刻を変えたらここも直すこと。**
SYNC_COMPLETE_HOUR = 23
SYNC_COMPLETE_MINUTE = 0


def analytics_enabled_channels() -> List[str]:
    """`video_format.analytics.enabled` が true のチャンネル ID。

    ここを設定キーから引くのが要点。「レポートに載っていない」の主因は
    API 失敗ではなくこのキーの書き忘れなので、期待値そのものを設定から作る。
    """
    out: List[str] = []
    for p in sorted(CHANNELS_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (((d.get("video_format") or {}).get("analytics") or {}).get("enabled")):
            out.append(p.stem)
    return out


def snapshot_coverage(*, expected_channels: Optional[Sequence[str]] = None,
                      date: Optional[str] = None,
                      db_path: Optional[Path] = None) -> Dict[str, Any]:
    """指定日の `video_metrics` が期待どおり全chぶん入っているか。

    Returns:
        {
          "date": "2026-09-09",
          "expected": [ch...],          # analytics.enabled なチャンネル
          "rows": {ch: 行数},           # 0 のチャンネルは入らない
          "missing": [ch...],           # 1行も無いチャンネル
          "ok": bool,                   # missing が空
          "sync_may_be_running": bool,  # sync 完了想定時刻より前＝まだ埋まっている最中
        }
    """
    day = date or datetime.now(JST).strftime("%Y-%m-%d")
    expected = list(expected_channels if expected_channels is not None
                    else analytics_enabled_channels())
    path = Path(db_path) if db_path else DB_PATH

    rows: Dict[str, int] = {}
    if path.exists():
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            for cid, n in conn.execute(
                    "SELECT channel_id, COUNT(*) FROM video_metrics "
                    "WHERE date = ? GROUP BY channel_id", (day,)):
                rows[str(cid)] = int(n)
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    missing = [c for c in expected if rows.get(c, 0) == 0]
    now = datetime.now(JST)
    running = (day == now.strftime("%Y-%m-%d")
               and (now.hour, now.minute) < (SYNC_COMPLETE_HOUR, SYNC_COMPLETE_MINUTE))
    return {
        "date": day,
        "expected": expected,
        "rows": rows,
        "missing": missing,
        "ok": not missing,
        "sync_may_be_running": running,
    }


def coverage_markdown(cov: Dict[str, Any]) -> str:
    """レポートに貼る節。欠測があれば必ず名指しする。"""
    lines = ["### 計測データの充足（video_metrics）", ""]
    day = cov.get("date")
    got = len(cov.get("expected") or []) - len(cov.get("missing") or [])
    lines.append(f"- 対象日: {day} / 取得済み {got}/{len(cov.get('expected') or [])} ch")
    if cov.get("ok"):
        lines.append("- ✅ 欠測なし。横断集計に使ってよい。")
    else:
        lines.append(f"- ⚠️ **欠測 {len(cov['missing'])} ch**: "
                     + " / ".join(cov["missing"]))
        if cov.get("sync_may_be_running"):
            lines.append(f"- ℹ️ sync は PDCA 起動後 約20分かけて ch名のアルファベット順で"
                         f"埋まる。**{SYNC_COMPLETE_HOUR}:{SYNC_COMPLETE_MINUTE:02d} より前**"
                         f"なのでまだ取得中の可能性が高い。"
                         f"この欠測を「実績0」や「取得障害」と読まないこと。")
        else:
            lines.append("- 🚨 sync 完了時刻を過ぎている。OAuth 失効 / "
                         "`video_format.analytics.enabled` の欠落 / API エラーを疑う。")
    if cov.get("rows"):
        lines.append("")
        lines.append("| チャンネル | 行数 |")
        lines.append("|---|---:|")
        for cid in cov.get("expected") or []:
            n = cov["rows"].get(cid, 0)
            lines.append(f"| {cid} | {n if n else '**0（欠測）**'} |")
    lines.append("")
    return "\n".join(lines)
