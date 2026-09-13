#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube Factory 指揮者 Phase 5 — xlsx 出力 (2026-09-13)

reports/youtube_analysis_20260913.xlsx を 5 シート構成で生成する。
  1. サマリー              全ch横断の主要KPI + 本日の最重要事項（公開停止）
  2. チャンネル別詳細      ch毎の再生/CTR/維持率/登録
  3. 動画別パフォーマンス  コホート全本の個別成績
  4. 改善アクション        本日実施した変更と根拠
  5. トレンド              日別の公開本数・再生・登録の推移
"""
from __future__ import annotations

import collections
import datetime
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analytics" / "analytics.db"
OUT = ROOT / "reports" / "youtube_analysis_20260913.xlsx"

CHANNELS = ["daily-science", "scp-lab", "2ch-matome", "pokemon-lab", "yokai-watch", "company-facts"]
COHORT_FROM = "2026-08-10"
TODAY = "2026-09-13"
OUTAGE_FROM = "2026-09-09"

FONT = "Arial"
HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(name=FONT, bold=True, size=14, color="1F3864")
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
ALERT_FILL = PatternFill("solid", fgColor="FFC7CE")
ALERT_FONT = Font(name=FONT, size=10, bold=True, color="9C0006")
GOOD_FILL = PatternFill("solid", fgColor="C6EFCE")
NOTE_FILL = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


# ---------------------------------------------------------------- data ----
def fetch():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    ph = ",".join("?" * len(CHANNELS))
    q = f"""WITH latest AS (
              SELECT vm.*, ROW_NUMBER() OVER (
                PARTITION BY video_id ORDER BY date DESC, fetched_at DESC) rn
              FROM video_metrics vm
              WHERE channel_id IN ({ph}) AND published_at >= ?)
            SELECT * FROM latest WHERE rn = 1 ORDER BY published_at DESC"""
    rows = [dict(r) for r in c.execute(q, CHANNELS + [COHORT_FROM])]
    c.close()
    return rows


def by_channel(rows):
    agg = collections.defaultdict(
        lambda: dict(n=0, views=0, subs=0, likes=0, comments=0, ret=[], imp=0, clk=0, cn=0))
    for r in rows:
        a = agg[r["channel_id"]]
        a["n"] += 1
        a["views"] += r["views"] or 0
        a["subs"] += r["subscribers_gained"] or 0
        a["likes"] += r["likes"] or 0
        a["comments"] += r["comments"] or 0
        if r["avg_view_percentage"]:
            a["ret"].append(r["avg_view_percentage"])
        if (r["impressions"] or 0) > 0 and (r["ctr"] or 0) > 0:
            a["imp"] += r["impressions"]
            a["clk"] += r["impressions"] * r["ctr"]
            a["cn"] += 1
    return agg


# --------------------------------------------------------------- style ----
def header(ws, row, headers, widths=None):
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=i, value=h)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 28
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def put(ws, row, col, value, *, font=None, fmt=None, fill=None, align=None, border=True):
    c = ws.cell(row=row, column=col, value=value)
    c.font = font or BODY
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if align:
        c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=(align == "left"))
    if border:
        c.border = BORDER
    return c


# ---------------------------------------------------------------- build ---
def sheet_summary(wb, rows, agg, daily):
    ws = wb.create_sheet("サマリー")
    ws.sheet_view.showGridLines = False
    ws["A1"] = f"YouTube Factory 日次分析  {TODAY}"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:G1")

    # --- 最重要 ---
    ws["A3"] = "★本日の最重要事項"
    ws["A3"].font = Font(name=FONT, bold=True, size=11, color="9C0006")
    msg = (f"{OUTAGE_FROM} 以降、全チャンネルの OAuth リフレッシュトークンが失効し"
           f"（invalid_grant: Token has been expired or revoked）、公開が 1 本も成立していない。"
           f"生成パイプラインは正常稼働しており、{OUTAGE_FROM}〜{TODAY} で 95 本が生成済み・未公開のまま滞留。")
    ws["A4"] = msg
    ws["A4"].font = ALERT_FONT
    ws["A4"].fill = ALERT_FILL
    ws["A4"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A4:G6")
    ws.row_dimensions[4].height = 22

    ws["A8"] = "推定原因: GCP OAuth 同意画面が「テスト」のままだとリフレッシュトークンは 7 日で失効する。"
    ws["A8"].font = BODY
    ws["A9"] = "対処: ①同意画面を「本番」公開 → ②全ch再認可 → ③滞留分を公開  (scripts/orch_recover_20260913.command)"
    ws["A9"].font = BOLD
    ws["A9"].fill = NOTE_FILL
    ws.merge_cells("A8:G8")
    ws.merge_cells("A9:G9")

    # --- 影響 ---
    r = 11
    ws.cell(row=r, column=1, value="公開停止の影響").font = Font(name=FONT, bold=True, size=11)
    r += 1
    header(ws, r, ["指標", "値", "算出根拠"], [30, 16, 62])
    ws.freeze_panes = None
    impact = [
        ("公開停止日数", 5, f"{OUTAGE_FROM}〜{TODAY}（最終公開 2026-09-08）"),
        ("停止前の平均公開本数/日", 17.2, "2026-09-04〜09-08 の 5 日平均（17/19/18/18/14 本）"),
        ("未公開の滞留本数", 95, "iCloud 動画出力フォルダの 09-09 以降作成ディレクトリ数"),
        ("逸失再生（推計）", None, "滞留本数 × コホート平均再生"),
        ("逸失登録（推計）", None, "逸失再生 × 全ch平均 登録/千再生"),
    ]
    start = r + 1
    for i, (label, val, basis) in enumerate(impact):
        rr = start + i
        put(ws, rr, 1, label, font=BOLD, align="left")
        if val is not None:
            put(ws, rr, 2, val, fmt="#,##0.0" if isinstance(val, float) else "#,##0", align="right")
        put(ws, rr, 3, basis, align="left")
    # 逸失は数式で（サマリー内の値を参照）
    put(ws, start + 3, 2, f"=B{start+2}*'チャンネル別詳細'!$C$10", fmt="#,##0", align="right")
    put(ws, start + 4, 2, f"=B{start+3}*'チャンネル別詳細'!$F$10/1000", fmt="#,##0.0", align="right")
    ws.cell(row=start + 3, column=2).comment = Comment(
        "滞留95本 × コホート全体の平均再生数。実際の再生は公開時期により変動するため概算。", "orchestrator")

    # --- 全ch KPI ---
    r = start + 6
    ws.cell(row=r, column=1, value="コホート実績（公開 2026-08-10 以降 / 09-08 時点で凍結）").font = Font(
        name=FONT, bold=True, size=11)
    r += 1
    header(ws, r, ["チャンネル", "本数", "総再生", "平均再生", "登録", "登録/千再生", "維持率"],
           [20, 8, 12, 11, 8, 13, 10])
    ws.freeze_panes = None
    first = r + 1
    for i, ch in enumerate(CHANNELS):
        a = agg[ch]
        rr = first + i
        put(ws, rr, 1, ch, align="left")
        put(ws, rr, 2, a["n"], fmt="#,##0", align="right")
        put(ws, rr, 3, a["views"], fmt="#,##0", align="right")
        put(ws, rr, 4, f"=IFERROR(C{rr}/B{rr},0)", fmt="#,##0", align="right")
        put(ws, rr, 5, a["subs"], fmt="#,##0", align="right")
        put(ws, rr, 6, f"=IFERROR(E{rr}/C{rr}*1000,0)", fmt="0.000", align="right")
        ret = sum(a["ret"]) / len(a["ret"]) / 100 if a["ret"] else 0
        put(ws, rr, 7, ret, fmt="0.0%", align="right")
    last = first + len(CHANNELS) - 1
    tr = last + 1
    put(ws, tr, 1, "合計 / 加重平均", font=BOLD, align="left", fill=GOOD_FILL)
    put(ws, tr, 2, f"=SUM(B{first}:B{last})", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)
    put(ws, tr, 3, f"=SUM(C{first}:C{last})", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)
    put(ws, tr, 4, f"=IFERROR(C{tr}/B{tr},0)", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)
    put(ws, tr, 5, f"=SUM(E{first}:E{last})", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)
    put(ws, tr, 6, f"=IFERROR(E{tr}/C{tr}*1000,0)", font=BOLD, fmt="0.000", align="right", fill=GOOD_FILL)
    put(ws, tr, 7, f"=IFERROR(SUMPRODUCT(B{first}:B{last},G{first}:G{last})/B{tr},0)",
        font=BOLD, fmt="0.0%", align="right", fill=GOOD_FILL)

    ws.cell(row=tr + 2, column=1,
            value="至上目標は登録者数の増加。登録/千再生の上位は scp-lab / company-facts、下位は 2ch-matome / pokemon-lab。"
            ).font = BODY
    return ws


def sheet_channel(wb, agg):
    ws = wb.create_sheet("チャンネル別詳細")
    ws.sheet_view.showGridLines = False
    ws["A1"] = "チャンネル別詳細（コホート: 公開 2026-08-10 以降）"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:J1")
    header(ws, 3, ["チャンネル", "本数", "平均再生", "総再生", "登録", "登録/千再生",
                   "高評価率", "維持率", "有効CTR", "CTR有効n"],
           [20, 8, 11, 12, 8, 13, 11, 10, 11, 10])
    for i, ch in enumerate(CHANNELS):
        a = agg[ch]
        r = 4 + i
        put(ws, r, 1, ch, align="left")
        put(ws, r, 2, a["n"], fmt="#,##0", align="right")
        put(ws, r, 3, f"=IFERROR(D{r}/B{r},0)", fmt="#,##0", align="right")
        put(ws, r, 4, a["views"], fmt="#,##0", align="right")
        put(ws, r, 5, a["subs"], fmt="#,##0", align="right")
        put(ws, r, 6, f"=IFERROR(E{r}/D{r}*1000,0)", fmt="0.000", align="right")
        put(ws, r, 7, a["likes"] / a["views"] if a["views"] else 0, fmt="0.000%", align="right")
        put(ws, r, 8, (sum(a["ret"]) / len(a["ret"]) / 100) if a["ret"] else 0, fmt="0.0%", align="right")
        put(ws, r, 9, (a["clk"] / a["imp"]) if a["imp"] else 0, fmt="0.00%", align="right")
        put(ws, r, 10, a["cn"], fmt="#,##0", align="right")
    # 10行目 = 合計行（サマリーから参照される）
    r = 10
    put(ws, r, 1, "合計 / 加重平均", font=BOLD, align="left", fill=GOOD_FILL)
    put(ws, r, 2, "=SUM(B4:B9)", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)
    put(ws, r, 3, "=IFERROR(D10/B10,0)", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)
    put(ws, r, 4, "=SUM(D4:D9)", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)
    put(ws, r, 5, "=SUM(E4:E9)", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)
    put(ws, r, 6, "=IFERROR(E10/D10*1000,0)", font=BOLD, fmt="0.000", align="right", fill=GOOD_FILL)
    put(ws, r, 7, "=IFERROR(SUMPRODUCT(D4:D9,G4:G9)/D10,0)", font=BOLD, fmt="0.000%", align="right", fill=GOOD_FILL)
    put(ws, r, 8, "=IFERROR(SUMPRODUCT(B4:B9,H4:H9)/B10,0)", font=BOLD, fmt="0.0%", align="right", fill=GOOD_FILL)
    put(ws, r, 9, "=IFERROR(SUMPRODUCT(J4:J9,I4:I9)/SUM(J4:J9),0)", font=BOLD, fmt="0.00%", align="right", fill=GOOD_FILL)
    put(ws, r, 10, "=SUM(J4:J9)", font=BOLD, fmt="#,##0", align="right", fill=GOOD_FILL)

    ws["A12"] = "注意事項"
    ws["A12"].font = BOLD
    notes = [
        "有効CTR は impressions>0 かつ ctr>0 の動画のみで集計している。コホート 263 本中、条件を満たすのは 156 本。",
        "CTR を根拠にした判断は、この限定が必要（母数の少ない ch は 2ch-matome n=13、company-facts n=31 と差が大きい）。",
        "維持率は動画単純平均ではなく本数加重。retention_curve は主力 5ch で未取得のままで、離脱点分析は daily-science のみ可能。",
        "本コホートは 2026-09-08 で凍結している（09-09 以降の公開が 0 本のため）。09-12 の分析値と同一。",
        "さらに 09-07（18本）・09-08（14本）の計 32 本は再生数がすべて 0 で記録されている。"
        "これは実績ではなく analytics 同期も 09-08 前後で止まったことによる欠測。復旧後に backfill が必要。",
    ]
    for i, n in enumerate(notes):
        c = ws.cell(row=13 + i, column=1, value="・" + n)
        c.font = BODY
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=13 + i, start_column=1, end_row=13 + i, end_column=10)
    return ws


def sheet_videos(wb, rows):
    ws = wb.create_sheet("動画別パフォーマンス")
    ws["A1"] = "動画別パフォーマンス（コホート全 %d 本 / 登録数の降順）" % len(rows)
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:I1")
    header(ws, 3, ["チャンネル", "公開日", "タイトル", "再生", "登録", "登録/千再生",
                   "維持率", "高評価", "CTR"],
           [17, 12, 62, 9, 8, 12, 10, 9, 9])
    ordered = sorted(rows, key=lambda r: (-(r["subscribers_gained"] or 0), -(r["views"] or 0)))
    for i, r in enumerate(ordered):
        rr = 4 + i
        put(ws, rr, 1, r["channel_id"], align="left")
        put(ws, rr, 2, (r["published_at"] or "")[:10], align="center")
        put(ws, rr, 3, (r["title"] or "")[:110], align="left")
        put(ws, rr, 4, r["views"] or 0, fmt="#,##0", align="right")
        put(ws, rr, 5, r["subscribers_gained"] or 0, fmt="#,##0", align="right")
        put(ws, rr, 6, f"=IFERROR(E{rr}/D{rr}*1000,0)", fmt="0.00", align="right")
        put(ws, rr, 7, (r["avg_view_percentage"] or 0) / 100, fmt="0.0%", align="right")
        put(ws, rr, 8, r["likes"] or 0, fmt="#,##0", align="right")
        put(ws, rr, 9, r["ctr"] or 0, fmt="0.00%", align="right")
    ws.auto_filter.ref = f"A3:I{3+len(ordered)}"
    return ws


def sheet_actions(wb):
    ws = wb.create_sheet("改善アクション")
    ws.sheet_view.showGridLines = False
    ws["A1"] = "本日（2026-09-13）実施した変更と根拠"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:F1")
    ws["A2"] = ("方針: コホートが 2026-09-08 で凍結しているため、投稿枠・voice_style・スタイルルールは"
                "一切変更しない（同一データでの二重意思決定を避ける）。実施したのは在庫補充と、"
                "新規に実測で裏付けが取れたキュー構成の是正のみ。")
    ws["A2"].font = BODY
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:F3")

    header(ws, 5, ["ID", "対象", "変更内容", "根拠（実データ）", "検証方法", "状態"],
           [7, 17, 40, 58, 30, 12])
    actions = [
        ("A1", "全ch", "OAuth 復旧手順スクリプトを作成 (scripts/orch_recover_20260913.command)",
         "backend.log に invalid_grant 1005 件 / RefreshError 498 件。09-09 以降の公開 0 本、"
         "生成済み未公開 95 本。トークン最終更新は全ch 09-08〜09-09 に集中。",
         "再認可後に oauth_tokens.updated_at が更新され、公開が通ること", "要人手"),
        ("A2", "pokemon-lab", "テーマキューの構成を是正。数値提示型を先頭へ、対決（どっちが）型を末尾へ",
         "公開 07-20 以降 n=33（views>=150）: 数値提示型 登録/千 0.429(n=16) > その他 0.212(n=10) "
         "> 対決型 0.191(n=7)。対決型は平均1493再生と再生では1.7倍だが登録変換は1/2.2。"
         "pokemon-lab は登録/千 0.277 で 6ch ワースト2 なのにキュー先頭が対決型だった。",
         "復旧後コホート n>=20 で数値提示型の登録/千が対決型を上回るか", "適用済"),
        ("A3", "scp-lab", "テーマキュー 10 → 21 本へ補充（実測トップの「番号+具体数字+消失/途絶」型）",
         "残 10 本 / 3枠日 = 3.3 日で枯渇見込み。実測トップ: SCP-1283-JP 踏切 3.03、"
         "SCP-096 記録消失 2.20、SCP-1987 24時間ごと 2.10、SCP-4335 観測途絶 2.08。",
         "枯渇せず稼働継続すること / 新規テーマの登録/千", "適用済"),
        ("A4", "daily-science", "テーマキュー 13 → 21 本へ補充（「身体感覚 + 具体的な倍率/秒数」型）",
         "残 13 本 / 3枠日 = 4.3 日。実測トップ: 座ると腰 圧力1.4倍 3.47、濡れた紙 3倍 2.42。"
         "当ch は高評価率 0.580% で 1 位だが有効CTR 1.97% は中位でサムネに伸びしろ。",
         "枯渇せず稼働継続 / サムネ改善は復旧後データで別途", "適用済"),
        ("A5", "company-facts", "テーマキュー 18 → 28 本へ補充（「企業名 + 具体年収 + 実は/本当はどこに」型）",
         "残 18 本 / 4枠日 = 4.5 日。維持率 56.1%・有効CTR 2.87% でともに 1 位、"
         "登録/千 0.709 で 2 位。勝ち型が明確なので同型で補充。",
         "枯渇せず稼働継続すること", "適用済"),
        ("A6", "全ch", "投稿枠・voice_style・スタイルルールは変更しない",
         "09-09 以降の新規公開が 0 本でコホートが 09-12 分析時と完全に同一。"
         "同じデータで二度目の意思決定をすると、効果検証ができなくなる。",
         "復旧後 n>=20/ch のコホートが揃った時点で再評価（目安 2026-09-20）", "意図的に見送り"),
        ("A7", "制作トリガ", "moviepy 6ch への手動トリガは実行しない",
         "APScheduler が 09-13 も daily-science / scp-lab / pokemon-lab / yokai-watch / "
         "company-facts / akashic を自動発火済み。公開が通らない状態で追加生成しても"
         "未公開在庫 95 本に積み増すだけ。",
         "公開復旧後に在庫が捌けるか", "意図的に見送り"),
    ]
    for i, a in enumerate(actions):
        r = 6 + i
        for j, v in enumerate(a, start=1):
            fill = None
            if j == 6:
                fill = ALERT_FILL if v == "要人手" else (GOOD_FILL if v == "適用済" else NOTE_FILL)
            put(ws, r, j, v, align="center" if j in (1, 6) else "left", fill=fill)
        ws.row_dimensions[r].height = 58

    r = 6 + len(actions) + 2
    ws.cell(row=r, column=1, value="未対応・要人手（前日から継続）").font = Font(name=FONT, bold=True, size=11)
    pend = [
        "clip-animal: 許諾済み外部素材が max_duration_sec(3600s) 超で 5 本除外（最長 4328s）。素材が枯渇。",
        "clip-lab / clip-kaneko: ANTHROPIC_API_KEY / OPENAI_API_KEY 未設定で viral エンジンが停止。"
        "「壊れた字幕で公開しない」ガードが正しく働いて中止している。",
        "akashic-librarian: OAuth 未連携（生成は成功、公開のみスキップ）。今回の全ch失効とは別件。",
        "retention_curve が主力 6ch 中 5ch で未取得。離脱点分析が daily-science でしかできない。",
    ]
    for i, p in enumerate(pend):
        c = ws.cell(row=r + 1 + i, column=1, value="・" + p)
        c.font = BODY
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r + 1 + i, start_column=1, end_row=r + 1 + i, end_column=6)
        ws.row_dimensions[r + 1 + i].height = 26
    return ws


def sheet_trend(wb, daily):
    ws = wb.create_sheet("トレンド")
    ws.sheet_view.showGridLines = False
    ws["A1"] = "日別推移（公開日ベース / 2026-08-25 以降）"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:F1")
    header(ws, 3, ["公開日", "公開本数", "再生合計", "登録合計", "平均再生/本", "登録/千再生"],
           [14, 11, 13, 11, 13, 13])
    days = sorted(daily)
    for i, d in enumerate(days):
        r = 4 + i
        v = daily[d]
        put(ws, r, 1, d, align="center")
        put(ws, r, 2, v["n"], fmt="#,##0", align="right")
        put(ws, r, 3, v["views"], fmt="#,##0", align="right")
        put(ws, r, 4, v["subs"], fmt="#,##0", align="right")
        put(ws, r, 5, f"=IFERROR(C{r}/B{r},0)", fmt="#,##0", align="right")
        put(ws, r, 6, f"=IFERROR(D{r}/C{r}*1000,0)", fmt="0.000", align="right")
    last = 3 + len(days)

    # 公開が止まった 5 日間を明示的に行として出す
    r = last + 1
    for i, d in enumerate(["2026-09-09", "2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"]):
        rr = r + i
        put(ws, rr, 1, d, align="center", fill=ALERT_FILL)
        put(ws, rr, 2, 0, fmt="#,##0", align="right", fill=ALERT_FILL, font=ALERT_FONT)
        for col in (3, 4, 5, 6):
            put(ws, rr, col, 0, fmt="#,##0", align="right", fill=ALERT_FILL)
    ws.cell(row=r, column=7, value="← OAuth 失効により公開停止").font = ALERT_FONT

    r2 = r + 6
    ws.cell(row=r2, column=1, value="週次サマリー").font = Font(name=FONT, bold=True, size=11)
    header(ws, r2 + 1, ["期間", "公開本数", "再生合計", "登録合計", "登録/千再生", "備考"],
           [20, 11, 13, 11, 13, 34])
    weeks = [
        ("2026-09-01〜09-08", 4, last, "最終稼働週。1日あたり 14〜19 本"),
        ("2026-09-09〜09-13", None, None, "OAuth 失効により公開 0 本"),
    ]
    rr = r2 + 2
    put(ws, rr, 1, weeks[0][0], align="left")
    # 公開日は文字列で格納しているため SUMIFS の比較演算子が効かない。
    # 09-01 以降が始まる行を Python 側で特定し、明示的な範囲で SUM する。
    sep = next((4 + i for i, d in enumerate(days) if d >= "2026-09-01"), last)
    put(ws, rr, 2, f"=SUM($B${sep}:$B${last})", fmt="#,##0", align="right")
    put(ws, rr, 3, f"=SUM($C${sep}:$C${last})", fmt="#,##0", align="right")
    put(ws, rr, 4, f"=SUM($D${sep}:$D${last})", fmt="#,##0", align="right")
    put(ws, rr, 5, f"=IFERROR(D{rr}/C{rr}*1000,0)", fmt="0.000", align="right")
    put(ws, rr, 6, weeks[0][3], align="left")
    rr += 1
    put(ws, rr, 1, weeks[1][0], align="left", fill=ALERT_FILL)
    for col, fmt in ((2, "#,##0"), (3, "#,##0"), (4, "#,##0"), (5, "0.000")):
        put(ws, rr, col, 0, fmt=fmt, align="right", fill=ALERT_FILL, font=ALERT_FONT)
    put(ws, rr, 6, weeks[1][3], align="left", fill=ALERT_FILL, font=ALERT_FONT)
    return ws


def main():
    rows = fetch()
    agg = by_channel(rows)
    daily = collections.defaultdict(lambda: dict(n=0, views=0, subs=0))
    for r in rows:
        d = (r["published_at"] or "")[:10]
        if d >= "2026-08-25":
            daily[d]["n"] += 1
            daily[d]["views"] += r["views"] or 0
            daily[d]["subs"] += r["subscribers_gained"] or 0

    wb = Workbook()
    wb.remove(wb.active)
    sheet_summary(wb, rows, agg, daily)
    sheet_channel(wb, agg)
    sheet_videos(wb, rows)
    sheet_actions(wb)
    sheet_trend(wb, daily)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"✅ {OUT}  (cohort n={len(rows)})")


if __name__ == "__main__":
    main()
