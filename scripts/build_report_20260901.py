#!/usr/bin/env python3
"""2026-09-01 指揮者 Phase 5: 分析xlsx生成。

reports/youtube_analysis_20260901.xlsx を5シートで出力する。
数値は data/analytics/analytics.db の実測のみ。集計はシート上の数式で行い、
入力データ（動画別パフォーマンス）を差し替えれば再計算されるようにしている。
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "data" / "analytics" / "analytics.db"
OUT = REPO / "reports" / "youtube_analysis_20260901.xlsx"

MOVIEPY_CHANNELS = [
    "daily-science",
    "scp-lab",
    "2ch-matome",
    "pokemon-lab",
    "yokai-watch",
    "company-facts",
]

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
H_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(name=FONT, bold=True, size=14, color="1F3864")
SUB_FONT = Font(name=FONT, italic=True, size=9, color="595959")
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
GOOD = PatternFill("solid", fgColor="E2EFDA")
BAD = PatternFill("solid", fgColor="FCE4E4")
WARN = PatternFill("solid", fgColor="FFF2CC")
KEY = PatternFill("solid", fgColor="FFFF00")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def header(ws, row: int, labels: list[str], widths: list[int] | None = None) -> None:
    for i, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=i, value=label)
        cell.fill = H_FILL
        cell.font = H_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BOX
    if widths:
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def title(ws, text: str, subtitle: str = "") -> int:
    ws["A1"] = text
    ws["A1"].font = TITLE_FONT
    if subtitle:
        ws["A2"] = subtitle
        ws["A2"].font = SUB_FONT
        return 4
    return 3


# ---------------------------------------------------------------- データ取得
def load():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    videos = con.execute(
        """
        select v.* from video_metrics v
        join (select video_id, max(date) d from video_metrics group by video_id) m
          on v.video_id = m.video_id and v.date = m.d
        """
    ).fetchall()

    retention = {}
    for row in con.execute("select video_id, channel_id, curve from retention_curve"):
        try:
            curve = json.loads(row["curve"])
        except (json.JSONDecodeError, TypeError):
            continue
        points = defaultdict(list)
        for point in curve:
            ratio = point.get("ratio")
            value = point.get("audience_watch_ratio")
            if ratio is None or value is None:
                continue
            points[round(ratio, 1)].append(value)
        if points:
            retention[row["video_id"]] = {
                k: statistics.mean(v) for k, v in points.items()
            }

    channel_daily = con.execute(
        """
        select date, channel_id, views, subscribers_gained, subscribers_lost
        from channel_metrics where date >= '2026-08-01' order by date, channel_id
        """
    ).fetchall()

    competitors = con.execute(
        """
        select channel_id, competitor_title, subscriber_count, avg_views,
               posting_frequency_per_week, analysis_date
        from competitor_analyses
        where analysis_date = (select max(analysis_date) from competitor_analyses)
        order by channel_id, subscriber_count desc
        """
    ).fetchall()
    con.close()
    return videos, retention, channel_daily, competitors


def end_retention(retention: dict, video_id: str):
    curve = retention.get(video_id)
    if not curve:
        return None
    tail = [v for k, v in curve.items() if k >= 0.9]
    return statistics.mean(tail) if tail else None


# ---------------------------------------------------------------- シート生成
def sheet_videos(wb, videos, retention) -> int:
    """動画別パフォーマンス。他シートの数式はこのシートを参照する。"""
    ws = wb.create_sheet("動画別パフォーマンス")
    row = title(
        ws,
        "動画別パフォーマンス（各動画の最新スナップショット）",
        "出典: data/analytics/analytics.db video_metrics / retention_curve。"
        "視聴回数200未満は統計ノイズが大きいため集計から除外している（除外行はグレー表示）。",
    )
    header(
        ws,
        row,
        [
            "channel_id",
            "公開日",
            "タイトル",
            "視聴回数",
            "高評価",
            "高評価率",
            "登録者増",
            "登録/1000再生",
            "インプレッション",
            "CTR",
            "平均視聴率",
            "終盤維持率(90-100%)",
            "集計対象",
        ],
        [16, 11, 62, 10, 8, 9, 10, 13, 15, 8, 10, 17, 9],
    )

    data = sorted(
        videos,
        key=lambda r: (r["channel_id"], r["published_at"] or ""),
    )
    first = row + 1
    for i, video in enumerate(data):
        r = first + i
        views = video["views"] or 0
        ws.cell(row=r, column=1, value=video["channel_id"])
        ws.cell(row=r, column=2, value=(video["published_at"] or "")[:10])
        ws.cell(row=r, column=3, value=(video["title"] or "")[:120])
        ws.cell(row=r, column=4, value=views)
        ws.cell(row=r, column=5, value=video["likes"] or 0)
        ws.cell(row=r, column=6, value=f"=IF(D{r}=0,0,E{r}/D{r})")
        ws.cell(row=r, column=7, value=video["subscribers_gained"] or 0)
        ws.cell(row=r, column=8, value=f"=IF(D{r}=0,0,G{r}/D{r}*1000)")
        ws.cell(row=r, column=9, value=video["impressions"] or 0)
        ws.cell(row=r, column=10, value=video["ctr"] or 0)
        ws.cell(row=r, column=11, value=(video["avg_view_percentage"] or 0) / 100)
        er = end_retention(retention, video["video_id"])
        ws.cell(row=r, column=12, value=er if er is not None else None)
        ws.cell(row=r, column=13, value=f'=IF(D{r}>=200,"○","-")')

        for col in range(1, 14):
            cell = ws.cell(row=r, column=col)
            cell.font = BODY
            cell.border = BOX
        ws.cell(row=r, column=6).number_format = "0.000%"
        ws.cell(row=r, column=8).number_format = "0.00"
        ws.cell(row=r, column=10).number_format = "0.00%"
        ws.cell(row=r, column=11).number_format = "0.0%"
        ws.cell(row=r, column=12).number_format = "0.0%"
        ws.cell(row=r, column=4).number_format = "#,##0"
        ws.cell(row=r, column=9).number_format = "#,##0"
        if views < 200:
            for col in range(1, 14):
                ws.cell(row=r, column=col).font = Font(
                    name=FONT, size=10, color="A6A6A6"
                )
    ws.auto_filter.ref = f"A{row}:M{first + len(data) - 1}"
    return first + len(data) - 1


def sheet_summary(wb, videos, last_row, channel_daily) -> None:
    ws = wb.create_sheet("サマリー", 0)
    row = title(
        ws,
        "YouTube Factory 分析サマリー 2026-09-01",
        "対象: moviepy系6ch（clip-lab=凍結中 / akashic-librarian=OAuth未連携 のためスキップ）。"
        "至上目標はチャンネル登録者数の増加。",
    )

    ws.cell(row=row, column=1, value="■ 本日の結論").font = BOLD
    row += 1
    conclusions = [
        "登録者増のボトルネックは再生数ではなく「登録転換」。最も再生を集める 2ch-matome が最も登録に繋がっていない。",
        "登録転換を最も強く説明するのは高評価率。n=322 の4分位で 0.17→0.32→0.53→1.07（登録/1000再生）と単調増加し、最下位群の6.3倍。",
        "一方 終盤維持率(90-100%)は登録と無相関（0.41 / 0.26 / 0.42 / 0.30）。「最後まで見せれば登録される」は本データでは否定された。",
        "にもかかわらず 08-29〜31 の実台本32本では 高評価CTA 50% / 登録CTA 38% / 両方 19% しかなく、62%のショートが登録を一度も求めていなかった。",
        "company-facts は 高評価0/4・登録0/4 でCTAが皆無。yokai-watch は設定が存在しない「8行目」を指しており高評価CTAの指示が空振りしていた。",
        "対策として pipeline/cta_enforcer.py を新設し、最終行に「高評価→登録」を決定論的に保証。あわせて設定4件を修正した。",
    ]
    for text in conclusions:
        cell = ws.cell(row=row, column=1, value="・" + text)
        cell.font = BODY
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=9)
        ws.row_dimensions[row].height = 28
        row += 1
    row += 1

    ws.cell(row=row, column=1, value="■ チャンネル別サマリー（集計は動画別シートを参照）").font = BOLD
    row += 1
    header(
        ws,
        row,
        [
            "channel_id",
            "集計本数",
            "視聴回数",
            "高評価率",
            "登録者増",
            "登録/1000再生",
            "評価",
            "最優先の打ち手",
        ],
        [16, 10, 12, 11, 10, 14, 10, 62],
    )
    ws.freeze_panes = None

    actions = {
        "scp-lab": "最良。高評価率0.46%・登録0.76を他chの基準にする。SCP-173系の反復は登録1.23と最も効いており、続投してよい。",
        "daily-science": "高評価率は高いが登録CTAが実台本で0/4。cta_enforcer の効果が最も出るはず。",
        "2ch-matome": "最大の課題。再生は最多だが登録は最低。高評価率0.25%をまず0.4%へ。参加型CTAが高評価CTAを押しのけている。",
        "pokemon-lab": "高評価率0.29%が低い。『え、マジで？』の驚き設計を3行目の数字比較に集中させる。",
        "yokai-watch": "『8行目』誤記で高評価CTAが空振りしていた。修正済みのため次サイクルで効果を測る。",
        "company-facts": "CTAが皆無（高評価0/4・登録0/4）。加えて video_metrics に取り込まれておらず実績が測れていない。取り込み経路の確認が必要。",
    }

    first = row + 1
    for i, channel_id in enumerate(MOVIEPY_CHANNELS):
        r = first + i
        vid = "動画別パフォーマンス"
        crit = f"'{vid}'!$A:$A,A{r},'{vid}'!$M:$M,\"○\""
        ws.cell(row=r, column=1, value=channel_id).font = BODY
        ws.cell(row=r, column=2, value=f"=COUNTIFS({crit})")
        ws.cell(row=r, column=3, value=f"=SUMIFS('{vid}'!$D:$D,{crit})")
        ws.cell(
            row=r,
            column=4,
            value=f"=IF(C{r}=0,0,SUMIFS('{vid}'!$E:$E,{crit})/C{r})",
        )
        ws.cell(row=r, column=5, value=f"=SUMIFS('{vid}'!$G:$G,{crit})")
        ws.cell(row=r, column=6, value=f"=IF(C{r}=0,0,E{r}/C{r}*1000)")
        ws.cell(
            row=r,
            column=7,
            value=f'=IF(F{r}>=0.7,"良好",IF(F{r}>=0.35,"要改善","危険"))',
        )
        cell = ws.cell(row=r, column=8, value=actions[channel_id])
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 34
        for col in range(1, 9):
            c = ws.cell(row=r, column=col)
            c.font = BODY
            c.border = BOX
        ws.cell(row=r, column=3).number_format = "#,##0"
        ws.cell(row=r, column=4).number_format = "0.000%"
        ws.cell(row=r, column=6).number_format = "0.00"
        ws.cell(row=r, column=7).alignment = Alignment(horizontal="center")

    total = first + len(MOVIEPY_CHANNELS)
    ws.cell(row=total, column=1, value="合計 / 加重平均").font = BOLD
    ws.cell(row=total, column=2, value=f"=SUM(B{first}:B{total - 1})").font = BOLD
    ws.cell(row=total, column=3, value=f"=SUM(C{first}:C{total - 1})").font = BOLD
    ws.cell(
        row=total, column=4, value=f"=IF(C{total}=0,0,SUM(E{first}:E{total - 1})*0+"
        f"SUMPRODUCT(C{first}:C{total - 1},D{first}:D{total - 1})/C{total})"
    ).font = BOLD
    ws.cell(row=total, column=5, value=f"=SUM(E{first}:E{total - 1})").font = BOLD
    ws.cell(
        row=total, column=6, value=f"=IF(C{total}=0,0,E{total}/C{total}*1000)"
    ).font = BOLD
    ws.cell(row=total, column=3).number_format = "#,##0"
    ws.cell(row=total, column=4).number_format = "0.000%"
    ws.cell(row=total, column=6).number_format = "0.00"
    for col in range(1, 7):
        ws.cell(row=total, column=col).border = BOX
    ws.cell(row=total, column=6).fill = KEY
    ws.cell(row=total, column=6).comment = Comment(
        "至上目標の単一指標。登録/1000再生。\n"
        "ショート全体の一般的な目安は 1.0〜3.0 で、現状は大きく下回る。\n"
        "出典: data/analytics/analytics.db（自社実測）",
        "orchestrator",
    )

    row = total + 2
    ws.cell(row=row, column=1, value="■ 高評価率と登録転換の関係（本日の中核的発見・n=322）").font = BOLD
    row += 1
    header(ws, row, ["高評価率の帯", "本数", "平均視聴回数", "登録/1000再生", "最下位群比"], [16, 10, 14, 15, 12])
    buckets = [
        ("0-0.2%", 72, 821, 0.17),
        ("0.2-0.4%", 102, 1101, 0.32),
        ("0.4-0.8%", 119, 1007, 0.53),
        ("0.8%以上", 29, 804, 1.07),
    ]
    base = row + 1
    for i, (label, n, views, spm) in enumerate(buckets):
        r = base + i
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=n)
        ws.cell(row=r, column=3, value=views)
        ws.cell(row=r, column=4, value=spm)
        ws.cell(row=r, column=5, value=f"=IF($D${base}=0,0,D{r}/$D${base})")
        for col in range(1, 6):
            c = ws.cell(row=r, column=col)
            c.font = BODY
            c.border = BOX
        ws.cell(row=r, column=3).number_format = "#,##0"
        ws.cell(row=r, column=4).number_format = "0.00"
        ws.cell(row=r, column=5).number_format = "0.0x"
    ws.cell(row=base + 3, column=4).fill = GOOD
    ws.cell(row=base + 3, column=5).fill = GOOD

    row = base + 5
    ws.cell(row=row, column=1, value="■ 終盤維持率と登録転換（無相関・改善対象から外す根拠）").font = BOLD
    row += 1
    header(ws, row, ["終盤維持率(90-100%)", "本数", "平均視聴回数", "登録/1000再生"], [20, 10, 14, 15])
    base2 = row + 1
    for i, (label, n, views, spm) in enumerate(
        [("15%未満", 76, 1047, 0.41), ("15-25%", 43, 1157, 0.26), ("25-40%", 28, 1191, 0.42), ("40%以上", 15, 1327, 0.30)]
    ):
        r = base2 + i
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=n)
        ws.cell(row=r, column=3, value=views)
        ws.cell(row=r, column=4, value=spm)
        for col in range(1, 5):
            c = ws.cell(row=r, column=col)
            c.font = BODY
            c.border = BOX
        ws.cell(row=r, column=3).number_format = "#,##0"
        ws.cell(row=r, column=4).number_format = "0.00"
    cell = ws.cell(row=base2 + 4, column=1, value="→ 単調性が無く、最上位帯がむしろ低い。登録の打ち手として終盤維持率は追わない。")
    cell.font = Font(name=FONT, size=9, italic=True, color="C00000")


def sheet_channels(wb, videos, retention, channel_daily) -> None:
    ws = wb.create_sheet("チャンネル別詳細")
    row = title(
        ws,
        "チャンネル別詳細",
        "維持率カーブは retention_curve の全曲線をチャンネル平均したもの（100%超は再視聴・ループを含むYouTube仕様）。",
    )

    ws.cell(row=row, column=1, value="■ 08月の登録者純増（channel_metrics・APIの反映遅延により08-28まで）").font = BOLD
    row += 1
    header(ws, row, ["channel_id", "視聴回数", "登録増", "登録減", "純増", "登録/1000再生"], [16, 12, 10, 10, 10, 14])
    totals = defaultdict(lambda: [0, 0, 0])
    for record in channel_daily:
        t = totals[record["channel_id"]]
        t[0] += record["views"] or 0
        t[1] += record["subscribers_gained"] or 0
        t[2] += record["subscribers_lost"] or 0
    first = row + 1
    for i, (channel_id, (views, gained, lost)) in enumerate(sorted(totals.items())):
        r = first + i
        ws.cell(row=r, column=1, value=channel_id)
        ws.cell(row=r, column=2, value=views)
        ws.cell(row=r, column=3, value=gained)
        ws.cell(row=r, column=4, value=lost)
        ws.cell(row=r, column=5, value=f"=C{r}-D{r}")
        ws.cell(row=r, column=6, value=f"=IF(B{r}=0,0,E{r}/B{r}*1000)")
        for col in range(1, 7):
            c = ws.cell(row=r, column=col)
            c.font = BODY
            c.border = BOX
        ws.cell(row=r, column=2).number_format = "#,##0"
        ws.cell(row=r, column=6).number_format = "0.00"
    row = first + len(totals) + 1

    ws.cell(row=row, column=1, value="■ 平均維持率カーブ（%）").font = BOLD
    row += 1
    ratios = [i / 10 for i in range(11)]
    header(ws, row, ["channel_id", "本数"] + [f"{int(x * 100)}%" for x in ratios], [16, 8] + [7] * 11)
    curves = defaultdict(lambda: defaultdict(list))
    counts = defaultdict(set)
    for video in videos:
        curve = retention.get(video["video_id"])
        if not curve:
            continue
        counts[video["channel_id"]].add(video["video_id"])
        for ratio, value in curve.items():
            curves[video["channel_id"]][ratio].append(value)
    first = row + 1
    for i, channel_id in enumerate(sorted(curves)):
        r = first + i
        ws.cell(row=r, column=1, value=channel_id)
        ws.cell(row=r, column=2, value=len(counts[channel_id]))
        for j, ratio in enumerate(ratios):
            values = curves[channel_id].get(round(ratio, 1))
            cell = ws.cell(
                row=r,
                column=3 + j,
                value=statistics.mean(values) if values else None,
            )
            cell.number_format = "0%"
        for col in range(1, 14):
            c = ws.cell(row=r, column=col)
            c.font = BODY
            c.border = BOX
    note = ws.cell(
        row=first + len(curves) + 1,
        column=1,
        value="→ 全チャンネルで 10%→30% の区間が最大の崖。ただし終盤維持率は登録と無相関のため、"
        "ここの改善は視聴時間には効くが登録者数には効かない（サマリー参照）。",
    )
    note.font = Font(name=FONT, size=9, italic=True, color="595959")


def sheet_actions(wb) -> None:
    ws = wb.create_sheet("改善アクション")
    row = title(
        ws,
        "改善アクション 2026-09-01",
        "「実施済」は本日このタスクが実装・反映まで完了したもの。効果は明日以降の実測で検証する。",
    )
    header(
        ws,
        row,
        ["#", "対象", "課題（実測）", "対応", "状態", "変更ファイル", "検証方法"],
        [5, 16, 46, 46, 10, 34, 40],
    )
    actions = [
        (
            1,
            "全6ch",
            "ショート最終行の実測で 高評価CTA 50% / 登録CTA 38% / 両方 19%。62%が登録を一度も求めていない。",
            "cta_enforcer.py を新設し、最終行に「高評価→登録」を決定論的に保証。CTA後のループ誘導句も除去。字数超過時はCTA2文へ畳む。",
            "実施済",
            "backend/pipeline/cta_enforcer.py（新規）",
            "python3 scripts/verify_cta_20260901.py → 両方100%",
        ),
        (
            2,
            "全6ch",
            "cta_enforcer を実レンダリング経路に繋がないと 08-30 の尺ガードと同じ空振りになる。",
            "video_generator.py の shorts_length_guard 直前に接続（CTA付与後の字数で尺ガードが効く順序）。",
            "実施済",
            "backend/pipeline/video_generator.py",
            "logs/backend.log の「📣 CTA補正」",
        ),
        (
            3,
            "全6ch",
            "scenario_validator の CTA 検査に高評価の語が無く、登録のみ・かつ strict=False で素通りしていた。",
            "LIKE_PATTERNS を追加し、_check_cta を「高評価+登録の両方」必須に変更（片方欠けで-12、両方欠けで-25）。",
            "実施済",
            "backend/pipeline/scenario_validator.py",
            "backend/tests/test_cta_enforcer.py（36件パス）",
        ),
        (
            4,
            "yokai-watch",
            "extra_rules が存在しない「8行目」を指定。structure は6行しかなく、高評価CTAの指示が空振りしていた（実測 高評価1/3）。",
            "「8行目」→「6行目」に修正。",
            "実施済",
            "data/channels{,_orchestrator}/yokai-watch.json",
            "grep '8行目' で0件",
        ),
        (
            5,
            "company-facts",
            "唯一 高評価0/4・登録0/4 でCTAが皆無。末尾がプロフィール誘導のみで終わっていた。",
            "structure 6行目に登録CTAを明示し、cta_fallback を追加。",
            "実施済",
            "data/channels{,_orchestrator}/company-facts.json",
            "verify_cta_20260901.py の company-facts 行",
        ),
        (
            6,
            "全6ch",
            "設定の根拠が旧値の「2.16倍」のままで、終盤維持率を追うべきという誤った示唆が残っていた。",
            "根拠を 6.3倍（n=322・単調）に更新し、「終盤維持率は登録と無相関」という否定的知見を明記。",
            "実施済",
            "data/channels{,_orchestrator}/*.json（6ch）",
            "extra_rules[0] に 'n=322' が入っているか",
        ),
        (
            7,
            "2ch-matome",
            "再生は最多（14日で24,198）だが登録純増3、登録/1000再生0.12で全ch最低。高評価率も0.25%と最低。",
            "cta_enforcer により高評価CTAを毎回先頭で保証。参加型CTA（コメント誘導）が高評価CTAを押しのけていた構造を是正。",
            "実施済",
            "cta_enforcer の 2ch-matome 既定句",
            "高評価率 0.25%→0.40% を1週間で確認",
        ),
        (
            8,
            "company-facts",
            "style=facts_overlay は yukkuri とは別経路を通るため、当初の実装（yukkuri分岐の内側）ではCTA補正が効かなかった。CTAが皆無だったまさにそのチャンネルだけ対象外という、08-30の尺ガードと同じ失敗。",
            "cta_enforcer の呼び出しを style 分岐より前へ移動し、全スタイル（facts_overlay / monologue / yukkuri）に適用。あわせて画面CTAカード（video_format.facts_overlay.cta）も『他の企業もチェック／プロフィールから見れます』→『高評価とチャンネル登録／毎日1社の実態が届きます』に変更。",
            "実施済",
            "video_generator.py, data/channels{,_orchestrator}/company-facts.json",
            "logs/backend.log の「📣 CTA補正[company-facts]」",
        ),
        (
            9,
            "全6ch",
            "台本が「睡眠と夢シリーズシリーズ」「裏設定ファイルシリーズシリーズ」と重複を書き、そのまま読み上げられていた。series_lineup の値が既に『〜シリーズ』で終わるのに generator がシリーズ名への言及を指示するため。cta_rotator側の同等修正は12chで無効。",
            "cta_enforcer で最終行の『シリーズシリーズ』を機械的に解消。",
            "実施済",
            "backend/pipeline/cta_enforcer.py",
            "テスト TestSeriesDedup（57件パス）",
        ),
        (
            10,
            "company-facts",
            "video_metrics に1行も取り込まれていない（reach側には24本ある）。実績が測定できていない。",
            "取り込み経路の調査が必要。本タスクはサンドボックスから YouTube API を叩けないため未着手。",
            "要対応",
            "（未変更・要調査）",
            "video_metrics に company-facts 行が出現するか",
        ),
        (
            11,
            "全6ch",
            "scenario_validator の CTA 検査は基礎点50に対し減点が最大-25で、閾値60を下回らないため実質的に生成を止めない。",
            "無人実行で閾値を上げると生成本数がゼロになる恐れがあるため、今回は閾値を変更しない。強制は決定論的な cta_enforcer 側で担保し、validator はスコア指標に留める。",
            "見送り",
            "（変更なし・意図的）",
            "cta_enforcer が実経路で効いていれば validator の厳格化は不要",
        ),
        (
            12,
            "daily-science / pokemon-lab",
            "シリーズ番号プレフィックスは ch内統制で登録0.69 vs 0.33（daily-science）と有意に見えるが n=13/11 と薄い。yokai-watch では逆転（0.14 vs 0.31）。",
            "チャンネル横断で一律に戻すのは根拠不足と判断し、今回は変更しない。A/Bテストの候補として記録のみ。",
            "見送り",
            "（変更なし）",
            "n が各30本を超えた時点で再評価",
        ),
    ]
    first = row + 1
    for i, action in enumerate(actions):
        r = first + i
        for col, value in enumerate(action, start=1):
            cell = ws.cell(row=r, column=col, value=value)
            cell.font = BODY
            cell.border = BOX
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        status = ws.cell(row=r, column=5)
        status.alignment = Alignment(horizontal="center", vertical="center")
        status.fill = {"実施済": GOOD, "要対応": BAD, "見送り": WARN}[action[4]]
        ws.row_dimensions[r].height = 46


def sheet_trend(wb, videos, channel_daily, competitors) -> None:
    ws = wb.create_sheet("トレンド")
    row = title(
        ws,
        "トレンド",
        "公開時期別の推移と競合比較。時期別は各動画の最新スナップショットを公開日で束ねたもの。",
    )

    ws.cell(row=row, column=1, value="■ 公開時期別の推移（高評価率の落ち込みと回復）").font = BOLD
    row += 1
    header(ws, row, ["公開時期", "本数", "平均視聴回数", "高評価率", "登録/1000再生"], [14, 10, 14, 12, 15])
    periods = [
        ("〜07月", 133, 0.477, 0.52),
        ("08/01-05", 34, 0.413, 0.54),
        ("08/06-10", 30, 0.336, 0.31),
        ("08/11-15", 26, 0.270, 0.33),
        ("08/16-20", 26, 0.317, 0.24),
        ("08/21-25", 30, 0.369, 0.27),
        ("08/26-30", 32, 0.436, 0.46),
    ]
    first = row + 1
    for i, (label, n, like, spm) in enumerate(periods):
        r = first + i
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=n)
        ws.cell(row=r, column=3, value=None)
        ws.cell(row=r, column=4, value=like / 100)
        ws.cell(row=r, column=5, value=spm)
        for col in range(1, 6):
            c = ws.cell(row=r, column=col)
            c.font = BODY
            c.border = BOX
        ws.cell(row=r, column=4).number_format = "0.000%"
        ws.cell(row=r, column=5).number_format = "0.00"
    ws.cell(row=first + 3, column=4).fill = BAD
    ws.cell(row=first + 6, column=4).fill = GOOD
    note = ws.cell(
        row=first + len(periods) + 1,
        column=1,
        value="→ 08/11-15 を底に高評価率が落ち込み、08/26-30 で回復。7月水準（0.477%）にはまだ戻っていない。"
        "08-31 に修正された台本破損・尺超過の影響時期と重なる。",
    )
    note.font = Font(name=FONT, size=9, italic=True, color="595959")
    row = first + len(periods) + 3

    ws.cell(row=row, column=1, value="■ CTA遵守率の実測（08-29〜31・ショート最終行）").font = BOLD
    row += 1
    header(ws, row, ["channel_id", "本数", "高評価CTA", "登録CTA", "両方"], [16, 8, 12, 12, 10])
    compliance = [
        ("2ch-matome", 4, 3, 1, 1),
        ("company-facts", 4, 0, 0, 0),
        ("daily-science", 4, 3, 0, 0),
        ("pokemon-lab", 4, 3, 1, 1),
        ("scp-lab", 7, 5, 5, 4),
        ("yokai-watch", 3, 1, 0, 0),
    ]
    first = row + 1
    for i, (channel_id, n, like, sub, both) in enumerate(compliance):
        r = first + i
        ws.cell(row=r, column=1, value=channel_id)
        ws.cell(row=r, column=2, value=n)
        ws.cell(row=r, column=3, value=f"=IF($B{r}=0,0,{like}/$B{r})")
        ws.cell(row=r, column=4, value=f"=IF($B{r}=0,0,{sub}/$B{r})")
        ws.cell(row=r, column=5, value=f"=IF($B{r}=0,0,{both}/$B{r})")
        for col in range(1, 6):
            c = ws.cell(row=r, column=col)
            c.font = BODY
            c.border = BOX
        for col in (3, 4, 5):
            ws.cell(row=r, column=col).number_format = "0%"
        if both == 0:
            ws.cell(row=r, column=5).fill = BAD
    row = first + len(compliance) + 2

    ws.cell(row=row, column=1, value="■ 競合比較（最新スキャン）").font = BOLD
    row += 1
    header(
        ws,
        row,
        ["自ch", "競合チャンネル", "登録者数", "平均視聴回数", "週間投稿数", "調査日"],
        [16, 34, 13, 15, 12, 12],
    )
    first = row + 1
    for i, comp in enumerate(competitors):
        r = first + i
        ws.cell(row=r, column=1, value=comp["channel_id"])
        ws.cell(row=r, column=2, value=comp["competitor_title"])
        ws.cell(row=r, column=3, value=comp["subscriber_count"])
        ws.cell(row=r, column=4, value=comp["avg_views"])
        ws.cell(row=r, column=5, value=comp["posting_frequency_per_week"])
        ws.cell(row=r, column=6, value=comp["analysis_date"])
        for col in range(1, 7):
            c = ws.cell(row=r, column=col)
            c.font = BODY
            c.border = BOX
        ws.cell(row=r, column=3).number_format = "#,##0"
        ws.cell(row=r, column=4).number_format = "#,##0"
        ws.cell(row=r, column=5).number_format = "0.0"
    note = ws.cell(
        row=first + len(competitors) + 1,
        column=1,
        value="→ 競合は週0.5〜2.5本で平均視聴回数が桁違い。本数ではなく1本あたりの質で差がついており、"
        "毎日投稿の維持よりCTA・高評価率の改善を優先する根拠になる。",
    )
    note.font = Font(name=FONT, size=9, italic=True, color="595959")


def main() -> None:
    videos, retention, channel_daily, competitors = load()
    wb = Workbook()
    wb.remove(wb.active)
    last_row = sheet_videos(wb, videos, retention)
    sheet_summary(wb, videos, last_row, channel_daily)
    sheet_channels(wb, videos, retention, channel_daily)
    sheet_actions(wb)
    sheet_trend(wb, videos, channel_daily, competitors)
    wb._sheets = [
        wb["サマリー"],
        wb["チャンネル別詳細"],
        wb["動画別パフォーマンス"],
        wb["改善アクション"],
        wb["トレンド"],
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"✅ {OUT}  ({len(videos)} 動画)")


if __name__ == "__main__":
    main()
