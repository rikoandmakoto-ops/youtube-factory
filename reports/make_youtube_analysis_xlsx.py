#!/usr/bin/env python3
"""YouTube Factory 指揮者レポートの xlsx 出力。

2026-09-10 のランでは Linux サンドボックスが起動せず openpyxl を実行できなかったため、
同内容を Markdown (reports/youtube_analysis_20260910.md) で出力し、本スクリプトを
再現用に残している。サンドボックス復旧後に以下を実行すると xlsx が生成される。

    cd /Users/ayukiyamazaki/Developer/youtube-factory
    python3 reports/make_youtube_analysis_xlsx.py            # 最新の _analysis_*.json を使う
    python3 reports/make_youtube_analysis_xlsx.py 20260910   # 日付を指定する

生成先: reports/youtube_analysis_<YYYYMMDD>.xlsx
シート: サマリー / チャンネル別詳細 / 動画別パフォーマンス / 改善アクション / トレンド
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("openpyxl が必要です:  pip install openpyxl --break-system-packages")

REPO = Path(__file__).resolve().parent.parent
ORCH_DIR = REPO / "data" / "channels_orchestrator"
ANALYTICS_DIR = REPO / "data" / "analytics"
REPORTS_DIR = REPO / "reports"

MANAGED = [
    "daily-science",
    "scp-lab",
    "2ch-matome",
    "pokemon-lab",
    "yokai-watch",
    "company-facts",
]

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WARN_FILL = PatternFill("solid", fgColor="FFF2CC")


def resolve_stamp(argv: list[str]) -> str:
    """引数の YYYYMMDD、無ければ最新の _analysis_*.json から日付を拾う。"""
    if len(argv) > 1:
        return argv[1]
    found = sorted(glob.glob(str(ORCH_DIR / "_analysis_*.json")))
    if not found:
        sys.exit(f"_analysis_*.json が見つかりません: {ORCH_DIR}")
    m = re.search(r"_analysis_(\d{8})\.json$", found[-1])
    if not m:
        sys.exit(f"日付を解釈できません: {found[-1]}")
    return m.group(1)


def load_json(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"見つかりません: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def write_rows(ws, rows: list[list], widths: list[int], freeze: str = "A2") -> None:
    for row in rows:
        ws.append(row)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = freeze


def pct(value) -> str:
    return "" if value is None else f"{value * 100:.2f}%"


def sheet_summary(wb, index: dict, analysis: dict) -> None:
    ws = wb.create_sheet("サマリー")
    rows = [[
        "channel", "n", "success", "success率",
        "再生 success", "再生 others", "再生倍率",
        "CTR success", "CTR others", "CTR倍率",
        "維持率 success", "維持率 others", "維持率倍率",
        "主レバー",
    ]]
    for ch in MANAGED:
        c = analysis["channels"][ch]
        m = c["metrics"]
        s = m["sample"]
        rows.append([
            ch, s["total"], s["success"], f"{s['success'] / s['total'] * 100:.1f}%",
            m["views"]["success"], m["views"]["others"], m["views"]["ratio"],
            pct(m["ctr"]["success"]), pct(m["ctr"]["others"]), m["ctr"]["ratio"],
            m["avg_view_percentage"]["success"], m["avg_view_percentage"]["others"],
            m["avg_view_percentage"]["ratio"],
            c.get("primary_lever", ""),
        ])
    write_rows(ws, rows, [16, 6, 9, 10, 12, 12, 10, 12, 12, 9, 13, 13, 11, 24])

    ws.append([])
    ws.append(["本日の主要所見"])
    ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
    for f in index.get("headline_findings", []):
        ws.append([f"[{f['severity']}] {f['id']}"])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        ws.append(["主張", f["claim"]])
        ws.append(["根拠", f["evidence"]])
        if f.get("action"):
            ws.append(["対応", f["action"]])
        ws.append([])

    ws.append(["本ランで実行できなかった項目"])
    ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
    for b in index.get("blocked_this_run", []):
        ws.append([b["phase"], b["reason"], b["impact"]])
        for cell in ws[ws.max_row][:3]:
            cell.fill = WARN_FILL


def sheet_channels(wb, analysis: dict) -> None:
    ws = wb.create_sheet("チャンネル別詳細")
    rows = [[
        "channel", "診断", "主レバー", "実施した変更", "根拠",
        "タイトル長 s/o", "疑問形率 s/o", "数字率 s/o",
        "維持率曲線", "留意点", "評価日", "撤回条件",
    ]]
    for ch in MANAGED:
        c = analysis["channels"][ch]
        m = c["metrics"]
        tf = m["title_features"]
        review = c.get("review", {})
        notes = c.get("caveats", []) + c.get("open_issues", []) + [
            a["candidate"] + " → 見送り理由: " + a["reason"]
            for a in c.get("actions_rejected", [])
        ]
        rows.append([
            ch,
            c.get("diagnosis", ""),
            c.get("primary_lever", ""),
            "\n".join(f"・{a}" for a in c.get("actions_taken", [])),
            c.get("key_evidence", ""),
            f"{tf['avg_length']['success']} / {tf['avg_length']['others']}",
            f"{tf['question_ratio']['success']} / {tf['question_ratio']['others']}",
            f"{tf['number_ratio']['success']} / {tf['number_ratio']['others']}",
            "取得済み" if m["retention"].get("curves_available") else "未取得",
            "\n".join(f"・{n}" for n in notes),
            review.get("date", ""),
            review.get("rollback_if", ""),
        ])
    write_rows(ws, rows, [16, 60, 22, 70, 60, 14, 14, 14, 11, 60, 11, 40])


def sheet_videos(wb) -> None:
    ws = wb.create_sheet("動画別パフォーマンス")
    patterns = load_json(ANALYTICS_DIR / "success_patterns.json")
    rows = [["channel", "video_id", "title", "views", "CTR", "維持率", "区分"]]
    for ch in MANAGED:
        for v in patterns.get(ch, {}).get("success_videos", []):
            rows.append([
                ch, v.get("video_id", ""), v.get("title", ""),
                v.get("views"), pct(v.get("ctr")),
                v.get("avg_view_percentage"), "success",
            ])
    write_rows(ws, rows, [16, 14, 80, 9, 10, 10, 9])

    ws2 = wb.create_sheet("離脱ポイント")
    insights = load_json(ANALYTICS_DIR / "retention_insights.json")
    rows2 = [[
        "channel", "video_id", "title", "維持率",
        "位置from", "位置to", "drop", "bucket", "該当台本行",
    ]]
    for ch, data in insights.items():
        if data.get("skipped"):
            rows2.append([ch, "", f"曲線なし: {data.get('reason', '')}", "", "", "", "", "", ""])
            continue
        for v in data.get("per_video", []):
            for d in v.get("drops", []):
                line = (d.get("scenario_line") or {}).get("text", "")
                rows2.append([
                    ch, v.get("video_id", ""), v.get("title", ""),
                    v.get("avg_view_percentage"),
                    d.get("ratio_from"), d.get("ratio_to"), d.get("drop"),
                    d.get("bucket", ""), line.replace("\n", " / "),
                ])
    write_rows(ws2, rows2, [16, 14, 50, 9, 10, 10, 9, 10, 90])


def sheet_actions(wb, index: dict, analysis: dict) -> None:
    ws = wb.create_sheet("改善アクション")
    rows = [["#", "対象", "内容", "根拠", "評価日", "撤回条件"]]
    n = 0
    for ch in MANAGED:
        c = analysis["channels"][ch]
        review = c.get("review", {})
        for a in c.get("actions_taken", []):
            n += 1
            rows.append([
                f"A{n}", ch, a, c.get("key_evidence", ""),
                review.get("date", ""), review.get("rollback_if", ""),
            ])
    gaps = index.get("retention_data_gaps", {})
    if gaps:
        n += 1
        rows.append([
            f"A{n}", "運用課題（全ch）",
            "主要6ch中5chで維持率曲線が未取得。sync の保存経路を調査する",
            f"未取得: {', '.join(gaps.get('curves_missing', []))} / 原因: {gaps.get('cause', '')}",
            "復旧後即", "",
        ])
    write_rows(ws, rows, [6, 18, 80, 70, 11, 40])


def sheet_trend(wb, index: dict) -> None:
    ws = wb.create_sheet("トレンド")
    rows = [["区分", "項目", "内容"]]
    for f in index.get("headline_findings", []):
        rows.append([f"所見({f['severity']})", f["id"], f["claim"]])
        rows.append(["└ 根拠", "", f["evidence"]])
        if f.get("supersedes"):
            rows.append(["└ 上書き関係", "", f["supersedes"]])
        if f.get("review_on"):
            rows.append(["└ 評価日", "", f["review_on"]])
    for b in index.get("blocked_this_run", []):
        rows.append(["未実行", b["phase"], f"{b['reason']} / 影響: {b['impact']}"])
    gaps = index.get("retention_data_gaps", {})
    if gaps:
        rows.append(["データ欠損", "維持率曲線", gaps.get("recommended_fix", "")])
        rows.append(["└ 取得済み", "", ", ".join(gaps.get("curves_available", []))])
        rows.append(["└ 未取得", "", ", ".join(gaps.get("curves_missing", []))])
    layout = index.get("config_layout", {})
    if layout:
        rows.append(["構成", "channels_orchestrator", layout.get("finding", "")])
    for cid, reason in (index.get("skipped_channels") or {}).items():
        rows.append(["対象外ch", cid, reason])
    write_rows(ws, rows, [16, 26, 110])


def main() -> None:
    stamp = resolve_stamp(sys.argv)
    index = load_json(ORCH_DIR / "_index.json")
    analysis = load_json(ORCH_DIR / f"_analysis_{stamp}.json")

    wb = Workbook()
    wb.remove(wb.active)
    sheet_summary(wb, index, analysis)
    sheet_channels(wb, analysis)
    sheet_videos(wb)
    sheet_actions(wb, index, analysis)
    sheet_trend(wb, index)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"youtube_analysis_{stamp}.xlsx"
    wb.save(out)
    print(f"生成しました: {out}")


if __name__ == "__main__":
    main()
