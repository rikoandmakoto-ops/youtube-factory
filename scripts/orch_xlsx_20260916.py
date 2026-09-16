#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指揮者 Phase 5 — 2026-09-16 分析シート生成

reports/youtube_analysis_20260916.xlsx を作る。
集計値はすべて Excel の数式（SUMIFS / SUMPRODUCT / IFERROR）で書き、
Python で計算した数値をハードコードしない。生データは「動画別パフォーマンス」
シートに置き、他シートはそこを参照する。

    python3 scripts/orch_xlsx_20260916.py [出力先.xlsx]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

REPO = Path(__file__).resolve().parents[1]
DATE = "20260916"
CORE = [
    "scp-lab",
    "company-facts",
    "yokai-watch",
    "daily-science",
    "pokemon-lab",
    "2ch-matome",
]

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
H_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
SUB_FILL = PatternFill("solid", fgColor="D9E2F3")
TITLE_FONT = Font(name=FONT, bold=True, size=14, color="1F3864")
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
WARN_FILL = PatternFill("solid", fgColor="FFF2CC")
BAD_FILL = PatternFill("solid", fgColor="FCE4E4")
OK_FILL = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

PCT3 = "0.000"
PCT2 = '0.00"%"'
INT = "#,##0"


# ---------------------------------------------------------------- data load
def load() -> dict:
    a = sqlite3.connect(str(REPO / "data" / "analytics" / "analytics.db"))
    a.row_factory = sqlite3.Row
    p = sqlite3.connect(str(REPO / "data" / "video_publish.db"))
    t = sqlite3.connect(str(REPO / "data" / "youtube_tokens.db"))
    t.row_factory = sqlite3.Row

    vids = [
        dict(r)
        for r in a.execute(
            """select channel_id ch, video_id, title, substr(published_at,1,10) pub,
               max(views) v, max(avg_view_percentage) ret, max(likes) lk,
               max(comments) cm, max(subscribers_gained) sb, max(impressions) imp,
               max(ctr) ctr, max(avg_view_duration) dur
               from video_metrics group by video_id"""
        )
    ]
    measured = [v for v in vids if v["ch"] in CORE and (v["v"] or 0) > 0]
    measured.sort(key=lambda r: (r["ch"], r["pub"] or ""))
    unmeasured = [
        v for v in vids if v["ch"] in CORE and (v["v"] or 0) == 0 and (v["pub"] or "") >= "2026-09-13"
    ]

    pub = defaultdict(int)
    pub_ch = defaultdict(lambda: defaultdict(int))
    for d, c, n in p.execute(
        "select substr(published_at,1,10), channel_id, count(*) from video_status "
        "where published_at>='2026-09-03' group by 1,2"
    ):
        pub[d] += n
        pub_ch[d][c] = n

    sync = {r[0] for r in a.execute("select distinct date from video_metrics where date>='2026-09-03'")}
    tokens = sorted(
        (dict(r) for r in t.execute("select channel_id, youtube_channel_name, updated_at from oauth_tokens")),
        key=lambda r: -int(r["updated_at"] or 0),
    )
    last_sync = a.execute("select max(fetched_at) from video_metrics").fetchone()[0]

    # 高評価率の四分位境界（200再生以上）。集計自体は COUNTIFS/SUMIFS で行うが、
    # 境界値だけは Python 側で算出してシートに明記する。
    lr = sorted((v["lk"] or 0) / v["v"] * 100 for v in measured if v["v"] >= 200)
    q = len(lr) // 4
    qb = [0.0, round(lr[q], 4), round(lr[2 * q], 4), round(lr[3 * q], 4), 100.0]

    return {
        "measured": measured,
        "unmeasured": unmeasured,
        "pub": dict(pub),
        "pub_ch": {k: dict(v) for k, v in pub_ch.items()},
        "sync": sync,
        "tokens": tokens,
        "last_sync": datetime.fromtimestamp(int(last_sync)),
        "like_quartiles": qb,
        "like_n": len(lr),
    }


# ---------------------------------------------------------------- helpers
def style_header(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = H_FILL
        cell.font = H_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[row].height = 30


def widths(ws, spec: dict) -> None:
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def put(ws, row, col, value, *, font=BODY, fmt=None, fill=None, align=None, border=True):
    c = ws.cell(row=row, column=col, value=value)
    c.font = font
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if align:
        c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
    if border:
        c.border = BORDER
    return c


# ---------------------------------------------------------------- sheet 3
def sheet_videos(wb, d) -> int:
    """生データ。他シートはここを SUMIFS で参照する。戻り値は最終行。"""
    ws = wb.create_sheet("動画別パフォーマンス")
    cols = [
        "チャンネル", "公開日", "タイトル", "動画ID", "再生数", "インプレッション",
        "CTR(%)", "維持率(%)", "平均視聴秒", "高評価", "コメント", "登録者",
        "登録/千再生", "高評価率(%)", "維持率バンド", "公開日key",
    ]
    ws["A1"] = "動画別パフォーマンス（moviepy 6ch・views>0 のみ・video_id で畳んだ最大値）"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        f"出典: data/analytics/analytics.db（最終同期 {d['last_sync']:%Y-%m-%d %H:%M}）。"
        "1動画につき複数日のスナップショットがあるため video_id ごとに最大値を採用。"
        "E〜L 列は DB の実測値、M〜O 列は数式。"
    )
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="595959")
    ws.merge_cells("A2:O2")

    hr = 4
    for i, h in enumerate(cols, 1):
        ws.cell(row=hr, column=i, value=h)
    style_header(ws, hr, len(cols))

    r = hr + 1
    for v in d["measured"]:
        put(ws, r, 1, v["ch"])
        put(ws, r, 2, v["pub"], align="center")
        put(ws, r, 3, (v["title"] or "")[:80])
        put(ws, r, 4, v["video_id"], align="center")
        put(ws, r, 5, v["v"] or 0, fmt=INT)
        put(ws, r, 6, v["imp"] or 0, fmt=INT)
        put(ws, r, 7, round(v["ctr"] or 0, 3), fmt=PCT3)
        put(ws, r, 8, round(v["ret"] or 0, 2), fmt=PCT3)
        put(ws, r, 9, round(v["dur"] or 0, 1), fmt="0.0")
        put(ws, r, 10, v["lk"] or 0, fmt=INT)
        put(ws, r, 11, v["cm"] or 0, fmt=INT)
        put(ws, r, 12, v["sb"] or 0, fmt=INT)
        put(ws, r, 13, f"=IFERROR(L{r}/E{r}*1000,0)", fmt=PCT3)
        put(ws, r, 14, f"=IFERROR(J{r}/E{r}*100,0)", fmt=PCT3)
        put(
            ws, r, 15,
            f'=IF(H{r}<30,"00-30",IF(H{r}<40,"30-40",IF(H{r}<50,"40-50",'
            f'IF(H{r}<60,"50-60",IF(H{r}<70,"60-70","70+")))))',
            align="center",
        )
        # 公開日を数値キーにする。B 列はテキストなので SUMIFS の日付条件が効かない。
        put(ws, r, 16, f'=IFERROR(VALUE(SUBSTITUTE(B{r},"-","")),0)', fmt="0", align="center")
        r += 1
    last = r - 1

    ws.cell(row=hr, column=16).comment = Comment(
        "B列（公開日）はテキストなので SUMIFS/COUNTIFS の日付条件が一致しない。"
        "YYYYMMDD の整数に直したこの列を他シートの集計条件に使う。",
        "orchestrator",
    )
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A{hr}:P{last}"
    widths(ws, {"A": 15, "B": 11, "C": 46, "D": 13, "E": 10, "F": 15, "G": 9,
                "H": 10, "I": 11, "J": 8, "K": 9, "L": 8, "M": 11, "N": 12,
                "O": 12, "P": 11})

    # 未計測分（参考）
    r = last + 3
    put(ws, r, 1, "【参考】09-13 以降に公開したが analytics でまだ計測されていない動画",
        font=Font(name=FONT, size=11, bold=True, color="C00000"), border=False)
    r += 1
    put(ws, r, 1, (
        "YouTube Analytics の反映は公開からおよそ 2 日遅れる（09-13 公開の scp-lab は "
        "09-15 スナップショットで初めて views>0 になった）。下記は本日時点で評価に使えない。"
    ), font=Font(name=FONT, size=9, italic=True, color="595959"), border=False)
    r += 2
    for i, h in enumerate(["チャンネル", "公開日", "タイトル", "動画ID"], 1):
        ws.cell(row=r, column=i, value=h)
    style_header(ws, r, 4)
    r += 1
    for v in sorted(d["unmeasured"], key=lambda x: (x["pub"], x["ch"])):
        put(ws, r, 1, v["ch"])
        put(ws, r, 2, v["pub"], align="center")
        put(ws, r, 3, (v["title"] or "")[:80])
        put(ws, r, 4, v["video_id"], align="center")
        r += 1
    return last


# ---------------------------------------------------------------- sheet 2
def sheet_channels(wb, last: int, d: dict) -> None:
    ws = wb.create_sheet("チャンネル別詳細")
    V = "動画別パフォーマンス"
    rng = lambda col: f"'{V}'!${col}$5:${col}${last}"  # noqa: E731
    ch = rng("A")

    ws["A1"] = "チャンネル別詳細（全期間 / 直近14日）"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "すべて「動画別パフォーマンス」シートを SUMIFS で集計した数式。"
        "登録/千再生 = 登録者合計 ÷ 再生数合計 × 1000（動画ごとの比の平均ではない）。"
        "至上目標は登録者数なので、この列で順位を付けている。"
    )
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="595959")
    ws.merge_cells("A2:L2")

    hr = 4
    cols = ["チャンネル", "本数", "再生数合計", "平均再生", "登録者合計",
            "登録/千再生", "高評価率(%)", "平均維持率(%)",
            "直近14日 本数", "直近14日 登録/千", "直近14日 高評価率(%)", "全期間比"]
    for i, h in enumerate(cols, 1):
        ws.cell(row=hr, column=i, value=h)
    style_header(ws, hr, len(cols))

    r = hr + 1
    first = r
    for c in CORE:
        put(ws, r, 1, c, font=BOLD)
        put(ws, r, 2, f'=COUNTIFS({ch},A{r})', fmt=INT)
        put(ws, r, 3, f'=SUMIFS({rng("E")},{ch},A{r})', fmt=INT)
        put(ws, r, 4, f"=IFERROR(C{r}/B{r},0)", fmt=INT)
        put(ws, r, 5, f'=SUMIFS({rng("L")},{ch},A{r})', fmt=INT)
        put(ws, r, 6, f"=IFERROR(E{r}/C{r}*1000,0)", fmt=PCT3)
        put(ws, r, 7, f'=IFERROR(SUMIFS({rng("J")},{ch},A{r})/C{r}*100,0)', fmt=PCT3)
        put(ws, r, 8, f'=IFERROR(SUMPRODUCT(({ch}=A{r})*{rng("H")}*{rng("E")})/C{r},0)', fmt="0.0")
        put(ws, r, 9, f'=COUNTIFS({ch},A{r},{rng("P")},">=20260902")', fmt=INT)
        put(ws, r, 10,
            f'=IFERROR(SUMIFS({rng("L")},{ch},A{r},{rng("P")},">=20260902")'
            f'/SUMIFS({rng("E")},{ch},A{r},{rng("P")},">=20260902")*1000,0)', fmt=PCT3)
        put(ws, r, 11,
            f'=IFERROR(SUMIFS({rng("J")},{ch},A{r},{rng("P")},">=20260902")'
            f'/SUMIFS({rng("E")},{ch},A{r},{rng("P")},">=20260902")*100,0)', fmt=PCT3)
        put(ws, r, 12, f"=IFERROR(J{r}/F{r},0)", fmt="0.00x")
        r += 1
    lastc = r - 1

    put(ws, r, 1, "合計", font=BOLD, fill=SUB_FILL)
    put(ws, r, 2, f"=SUM(B{first}:B{lastc})", font=BOLD, fmt=INT, fill=SUB_FILL)
    put(ws, r, 3, f"=SUM(C{first}:C{lastc})", font=BOLD, fmt=INT, fill=SUB_FILL)
    put(ws, r, 4, f"=IFERROR(C{r}/B{r},0)", font=BOLD, fmt=INT, fill=SUB_FILL)
    put(ws, r, 5, f"=SUM(E{first}:E{lastc})", font=BOLD, fmt=INT, fill=SUB_FILL)
    put(ws, r, 6, f"=IFERROR(E{r}/C{r}*1000,0)", font=BOLD, fmt=PCT3, fill=SUB_FILL)
    put(ws, r, 7, f'=IFERROR(SUM({rng("J")})/C{r}*100,0)', font=BOLD, fmt=PCT3, fill=SUB_FILL)
    put(ws, r, 8, f'=IFERROR(SUMPRODUCT({rng("H")},{rng("E")})/C{r},0)', font=BOLD, fmt="0.0", fill=SUB_FILL)
    put(ws, r, 9, f"=SUM(I{first}:I{lastc})", font=BOLD, fmt=INT, fill=SUB_FILL)
    put(ws, r, 10,
        f'=IFERROR(SUMIFS({rng("L")},{rng("P")},">=20260902")'
        f'/SUMIFS({rng("E")},{rng("P")},">=20260902")*1000,0)', font=BOLD, fmt=PCT3, fill=SUB_FILL)
    put(ws, r, 11,
        f'=IFERROR(SUMIFS({rng("J")},{rng("P")},">=20260902")'
        f'/SUMIFS({rng("E")},{rng("P")},">=20260902")*100,0)', font=BOLD, fmt=PCT3, fill=SUB_FILL)
    put(ws, r, 12, f"=IFERROR(J{r}/F{r},0)", font=BOLD, fmt="0.00x", fill=SUB_FILL)
    ws.cell(row=r, column=12).comment = Comment(
        "直近14日の登録/千再生 ÷ 全期間の登録/千再生。1.00 より大きければ改善方向。",
        "orchestrator",
    )

    # 維持率バンド
    r += 3
    put(ws, r, 1, "維持率バンド別 登録効率（公開 2026-08-01 以降・200再生以上）",
        font=Font(name=FONT, size=11, bold=True, color="1F3864"), border=False)
    r += 1
    put(ws, r, 1, (
        "09-15 に記録した「70%以上が最下位（0.294）」は本日の再集計で 0.471 となり再現しなかった。"
        "頂点が 40-50% 帯であることだけが再現している。"
    ), font=Font(name=FONT, size=9, italic=True, color="C00000"), border=False)
    r += 2
    bh = r
    for i, h in enumerate(["維持率バンド", "本数", "再生数", "登録者", "登録/千再生", "高評価率(%)"], 1):
        ws.cell(row=r, column=i, value=h)
    style_header(ws, r, 6)
    r += 1
    cond = f'{rng("O")},A{{r}},{rng("E")},">=200",{rng("P")},">=20260801"'
    for b in ["00-30", "30-40", "40-50", "50-60", "60-70", "70+"]:
        put(ws, r, 1, b, align="center", fill=OK_FILL if b == "40-50" else None)
        c = cond.format(r=r)
        put(ws, r, 2, f"=COUNTIFS({c})", fmt=INT)
        put(ws, r, 3, f'=SUMIFS({rng("E")},{c})', fmt=INT)
        put(ws, r, 4, f'=SUMIFS({rng("L")},{c})', fmt=INT)
        put(ws, r, 5, f"=IFERROR(D{r}/C{r}*1000,0)", fmt=PCT3,
            fill=OK_FILL if b == "40-50" else None)
        put(ws, r, 6, f'=IFERROR(SUMIFS({rng("J")},{c})/C{r}*100,0)', fmt=PCT3)
        r += 1

    # 高評価率四分位
    r += 2
    put(ws, r, 1, "高評価率と登録効率の関係（最も頑健な所見・6回目の再現）",
        font=Font(name=FONT, size=11, bold=True, color="1F3864"), border=False)
    r += 1
    put(ws, r, 1, (
        f"200再生以上 n={d['like_n']} を高評価率で四分位に分けると、登録/千再生が単調に増える。"
        "維持率・再生数にはこの単調性が無い。改善の主レバーは高評価率である。"
    ), font=Font(name=FONT, size=9, italic=True, color="595959"), border=False)
    r += 2
    for i, h in enumerate(["高評価率 四分位", "境界(%)", "本数", "再生数", "登録者", "登録/千再生"], 1):
        ws.cell(row=r, column=i, value=h)
    style_header(ws, r, 6)
    r += 1
    # 四分位の境界は Python 側で決めるが、集計そのものは数式で行う
    qb = d["like_quartiles"]
    bounds = [
        ("Q1(低)", qb[0], qb[1]), ("Q2", qb[1], qb[2]),
        ("Q3", qb[2], qb[3]), ("Q4(高)", qb[3], qb[4]),
    ]
    for name, lo, hi in bounds:
        op = "<=" if hi >= 100.0 else "<"
        cq = (f'{rng("N")},">={lo}",{rng("N")},"{op}{hi}",'
              f'{rng("E")},">=200"')
        put(ws, r, 1, name, align="center")
        put(ws, r, 2, f"{lo:.3f} 〜 {hi:.3f}", align="center")
        put(ws, r, 3, f"=COUNTIFS({cq})", fmt=INT)
        put(ws, r, 4, f'=SUMIFS({rng("E")},{cq})', fmt=INT)
        put(ws, r, 5, f'=SUMIFS({rng("L")},{cq})', fmt=INT)
        put(ws, r, 6, f"=IFERROR(E{r}/D{r}*1000,0)", fmt=PCT3,
            fill=OK_FILL if name == "Q4(高)" else None)
        r += 1
    ws.cell(row=r - 4, column=2).comment = Comment(
        "四分位の境界値は Python 側で算出したハードコード。集計そのものは COUNTIFS/SUMIFS。",
        "orchestrator",
    )

    ws.freeze_panes = "A5"
    widths(ws, {"A": 22, "B": 10, "C": 13, "D": 11, "E": 12, "F": 12,
                "G": 13, "H": 14, "I": 13, "J": 15, "K": 17, "L": 10})


# ---------------------------------------------------------------- sheet 5
def sheet_trend(wb, d) -> None:
    ws = wb.create_sheet("トレンド")
    ws["A1"] = "公開本数の推移と analytics 同期の欠測"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "出典: data/video_publish.db（公開実績）と data/analytics/analytics.db の date 列（同期実績）。"
        "2026-09-09〜09-12 は公開と同期が同時に止まっている。"
    )
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="595959")
    ws.merge_cells("A2:H2")

    hr = 4
    cols = ["日付", "公開本数", "analytics 同期", "daily-science", "scp-lab",
            "yokai-watch", "company-facts", "2ch-matome", "pokemon-lab", "その他ch", "備考"]
    for i, h in enumerate(cols, 1):
        ws.cell(row=hr, column=i, value=h)
    style_header(ws, hr, len(cols))

    named = ["daily-science", "scp-lab", "yokai-watch", "company-facts", "2ch-matome", "pokemon-lab"]
    r = hr + 1
    first = r
    days = sorted(set(list(d["pub"].keys()) + ["2026-09-11", "2026-09-12", "2026-09-16"]))
    for day in days:
        per = dict(d["pub_ch"].get(day, {}))
        total = d["pub"].get(day, 0)
        if day == "2026-09-16":
            # video_publish.db は当日分をまだ書いていない。backend.log の
            # 「🚀 ショート自動公開完了 … v=cTHPSuJr0nA」で確認した実績を入れる。
            per, total = {"daily-science": 1}, 1
        put(ws, r, 1, day, align="center")
        put(ws, r, 2, total, fmt=INT,
            fill=BAD_FILL if total <= 2 else (WARN_FILL if total < 15 else None))
        synced = "○" if day in d["sync"] else "×"
        put(ws, r, 3, synced, align="center", fill=None if synced == "○" else BAD_FILL)
        for i, c in enumerate(named, 4):
            put(ws, r, i, per.get(c, 0), fmt=INT)
        put(ws, r, 10, f"=IFERROR(B{r}-SUM(D{r}:I{r}),0)", fmt=INT)
        note = ""
        if day in ("2026-09-10", "2026-09-11", "2026-09-12"):
            note = ("OAuth 失効で公開不能。autopilot は 31/31/28 回発火しており"
                    "生成は動いていた（失効スキップ 39/24/21 件）")
        elif day == "2026-09-09":
            note = ("29 回発火して 2 本のみ公開。この日はトークン失効ログが 0 件で、"
                    "原因は特定できていない（clip 系のエンジン失敗のみ確認）")
        elif day >= "2026-09-13" and day <= "2026-09-15":
            note = "5ch 再認可で復帰（8ch は失効のまま）"
        elif day == "2026-09-16":
            note = ("本日。07:30 に daily-science が公開済み（cTHPSuJr0nA）。"
                    "video_publish.db は当日分を未記録のため backend.log から補った。進行中の値。")
        put(ws, r, 11, note)
        r += 1
    last = r - 1
    put(ws, r, 1, "合計", font=BOLD, fill=SUB_FILL)
    put(ws, r, 2, f"=SUM(B{first}:B{last})", font=BOLD, fmt=INT, fill=SUB_FILL)
    put(ws, r, 3, "", fill=SUB_FILL)
    for i in range(4, 11):
        col = get_column_letter(i)
        put(ws, r, i, f"=SUM({col}{first}:{col}{last})", font=BOLD, fmt=INT, fill=SUB_FILL)
    put(ws, r, 11, "", fill=SUB_FILL)

    # 機会損失
    r += 2
    put(ws, r, 1, "停止によって失われた公開機会の見積り",
        font=Font(name=FONT, size=11, bold=True, color="C00000"), border=False)
    r += 2
    base = r + 1  # ヘッダー行の次（最初のデータ行）
    rows = [
        ("停止前 4日間（09-05〜09-08）の公開本数", f"=SUM(B{first+2}:B{first+5})", INT,
         "09-05 33本 / 09-06 30本 / 09-07 27本 / 09-08 21本"),
        ("停止前の 1日あたり公開本数", f"=B{base}/4", "0.0", "上記 ÷ 4日"),
        ("停止 4日間（09-09〜09-12）の実績", f"=SUM(B{first+6}:B{first+9})", INT, "09-09 2 / 09-10 2 / 09-11 0 / 09-12 0"),
        ("失われた公開本数", f"=MAX(0,B{base+1}*4-B{base+2})", "0.0", "停止前ペースとの差"),
        ("平均再生数（全期間・6ch）", "=IFERROR('チャンネル別詳細'!D11,0)", INT, "チャンネル別詳細の合計行"),
        ("登録/千再生（直近14日・6ch）", "=IFERROR('チャンネル別詳細'!J11,0)", PCT3, "チャンネル別詳細の合計行"),
        ("失われた登録者の見積り（人）", f"=B{base+3}*B{base+4}*B{base+5}/1000", "0.0",
         "失われた本数 × 平均再生 × 登録/千 ÷ 1000。粗い外挿であり実測ではない"),
    ]
    for i, h in enumerate(["項目", "値", "根拠"], 1):
        ws.cell(row=r, column=i, value=h)
    style_header(ws, r, 3)
    r += 1
    for label, formula, fmt, src in rows:
        put(ws, r, 1, label)
        put(ws, r, 2, formula, fmt=fmt, font=BOLD)
        put(ws, r, 3, src, font=Font(name=FONT, size=9, color="595959"))
        r += 1
    ws.cell(row=r - 1, column=2).fill = WARN_FILL
    ws.cell(row=r - 1, column=2).comment = Comment(
        "停止がなければ得られたはずの登録者数の粗い見積り。停止前ペースが続いた前提の外挿で、"
        "実測ではない。桁感をつかむための数字として扱うこと。",
        "orchestrator",
    )

    # OAuth
    r += 2
    put(ws, r, 1, "OAuth トークンの寿命（scripts/oauth_health_check.py と同じ集計）",
        font=Font(name=FONT, size=11, bold=True, color="1F3864"), border=False)
    r += 1
    put(ws, r, 1, (
        "同意画面が「テスト」公開ステータスのままだと、リフレッシュトークンは付与から 7 日で失効する。"
        "失効済み 6ch の最終リフレッシュは 7.5〜9.5 日前に固まっており、この仮説と整合する。"
    ), font=Font(name=FONT, size=9, italic=True, color="595959"), border=False)
    r += 2
    for i, h in enumerate(["channel_id", "チャンネル名", "最終リフレッシュ成功", "経過日", "状態"], 1):
        ws.cell(row=r, column=i, value=h)
    style_header(ws, r, 5)
    r += 1
    now = datetime.now().timestamp()
    for t in d["tokens"]:
        ts = int(t["updated_at"] or 0)
        age = (now - ts) / 86400.0
        state = "失効（要再認可）" if age >= 7 else ("まもなく失効" if age >= 5 else "正常")
        fill = BAD_FILL if age >= 7 else (WARN_FILL if age >= 5 else OK_FILL)
        put(ws, r, 1, t["channel_id"])
        put(ws, r, 2, t["youtube_channel_name"] or "")
        put(ws, r, 3, datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"), align="center")
        put(ws, r, 4, round(age, 1), fmt="0.0", align="center")
        put(ws, r, 5, state, fill=fill, align="center")
        r += 1

    ws.freeze_panes = "A5"
    widths(ws, {"A": 34, "B": 22, "C": 22, "D": 14, "E": 18, "F": 14,
                "G": 15, "H": 13, "I": 13, "J": 11, "K": 40})


# ---------------------------------------------------------------- sheet 4
def sheet_actions(wb) -> None:
    ws = wb.create_sheet("改善アクション")
    ws["A1"] = "改善アクション — 2026-09-16"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "実行者が「人」の項目は指揮者では動かせない。"
        "至上目標（チャンネル登録者数）への効き目が大きい順に並べてある。"
    )
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="595959")
    ws.merge_cells("A2:G2")

    hr = 4
    cols = ["#", "アクション", "根拠（実データ）", "効き目", "実行者", "状態", "期日"]
    for i, h in enumerate(cols, 1):
        ws.cell(row=hr, column=i, value=h)
    style_header(ws, hr, len(cols))

    acts = [
        (1, "Google OAuth 同意画面を「テスト」から「本番環境」へ公開する",
         "09-09〜09-12 に公開が 33本/日 → 0〜2本/日 へ全停止。原因は全 ch の"
         "リフレッシュトークン一斉失効。失効 6ch の最終リフレッシュは 7.5〜9.5 日前に"
         "固まっており、テスト公開時の 7 日寿命と一致する。09-13 に再認可した 6ch も"
         "同じ寿命なら 09-20 前後に再失効する。",
         "最大（停止1回あたり約 100 本 ≒ 60 人分の公開機会）", "人", "未着手", "至急"),
        (2, "失効 6ch（clip-lab / clip-kaneko / clip-fukada / akashic-librarian / "
            "fake-paper / clip-animal）と pokemon-lab を再認可する",
         "oauth_health_check.py: 6ch が 7.5〜9.5 日経過で失効、pokemon-lab は 6.1 日で警告。"
         "この 7ch は 09-10 以降 1 本も公開していない。",
         "大（13ch 中 7ch が停止中）", "人", "未着手", "至急（#1 の後）"),
        (3, "サムネイル権限の 403 を解消する（YouTube の電話番号確認）",
         "09-16 の公開でも scp-lab / company-facts / yokai-watch は全件 403。"
         "成功しているのは daily-science のみ。4 日連続で未解決。"
         "pokemon-lab は browse/suggested CTR 0.69% で 6ch 最低であり、"
         "サムネが当 ch の最大のボトルネックと特定済み。",
         "大（CTR 経由で全 ch に効く）", "人", "未着手", "至急"),
        (4, "Anthropic API キーを差し替える",
         "backend.log: claude_client call failed (thumbnail_brief) 401。"
         "連動して series_engine が全 ch で「Claude 未応答のため続編候補を生成しません」。"
         "サムネ指示文と続編候補が両方止まっている。",
         "中", "人", "未着手", "至急"),
        (5, "2ch-matome の autopilot を再開した（本日実施）",
         "youtube_tokens.db の最終リフレッシュ成功が 09-15 22:30 で当 ch のトークンは生存。"
         "トークンが生きているのに autopilot=false なのは当 ch だけだった。1日3枠 = 約 +0.7 登録/日。",
         "小（+0.7 登録/日）", "指揮者", "適用済", "2026-09-16"),
        (6, "バックエンドを 1 回再起動する",
         "APScheduler のジョブ登録は restore_all() が起動時に "
         "data/channels/*.json を読んで行う。#5 の変更は再起動しないと反映されない。",
         "小（#5 の前提）", "人", "未着手", "本日中"),
        (7, "09-09〜09-12 の analytics を遡って同期する",
         "video_metrics の date 列に 2026-09-09〜09-12 が 1 行も無い。"
         "当該期間に公開した動画は 4 本だけなので損失は小さいが、"
         "同期ジョブが止まっても気づけない構造が残っている。",
         "小（監視の穴）", "人", "未着手", "任意"),
        (8, "型ルール・投稿枠の効果検証を 09-17 → 09-23 へ延期した（本日実施）",
         "評価対象コホート 09-10〜09-15 のうち views>0 は 6ch 合計 1 本のみ。"
         "09-09〜09-12 の公開停止に加え、views は公開から約 2 日遅れて入る。"
         "09-17 では n が揃わず評価できない。",
         "—（判断の質を守る）", "指揮者", "適用済", "2026-09-16"),
        (9, "維持率 70%以上帯のペナルティを根拠にした施策をこれ以上積まない（本日実施）",
         "09-15 の「70%以上は登録/千 0.294 で最下位」は、同一条件の再集計で 0.471 となり"
         "再現しなかった。頂点が 40-50% 帯であることのみ再現。"
         "retention_target_band(40-50) は据え置き、単調な主張は取り下げた。",
         "—（誤った施策の予防）", "指揮者", "適用済", "2026-09-16"),
        (10, "改善リソースは引き続き高評価率に振る",
         "200再生以上の四分位で登録/千再生が単調に増える"
         "（Q1 0.273 → Q2 0.431 → Q3 0.510 → Q4 0.945・Q4/Q1 3.46倍）。6 回目の再現。"
         "コンフィグに記録した 3.40倍 は四分位の切り方が僅かに違うだけで同じ事実。"
         "維持率・再生数にはこの単調性が無い。",
         "大（唯一の単調な説明変数）", "指揮者", "継続", "常時"),
    ]
    r = hr + 1
    for num, act, why, impact, who, state, due in acts:
        fill = OK_FILL if state == "適用済" else (BAD_FILL if due.startswith("至急") else None)
        put(ws, r, 1, num, align="center", font=BOLD)
        put(ws, r, 2, act)
        put(ws, r, 3, why, font=Font(name=FONT, size=9))
        put(ws, r, 4, impact, align="center")
        put(ws, r, 5, who, align="center", font=BOLD)
        put(ws, r, 6, state, align="center", fill=fill)
        put(ws, r, 7, due, align="center")
        ws.row_dimensions[r].height = 62
        r += 1

    ws.freeze_panes = "A5"
    widths(ws, {"A": 5, "B": 40, "C": 62, "D": 24, "E": 10, "F": 11, "G": 16})


# ---------------------------------------------------------------- sheet 1
def sheet_summary(wb, d, last: int) -> None:
    ws = wb.create_sheet("サマリー", 0)
    V = "動画別パフォーマンス"
    ws["A1"] = "YouTube Factory 指揮者レポート — 2026-09-16"
    ws["A1"].font = Font(name=FONT, bold=True, size=16, color="1F3864")
    ws["A2"] = (
        f"analytics.db 最終同期 {d['last_sync']:%Y-%m-%d %H:%M}／"
        "集計対象は moviepy 6ch の views>0 の動画。"
        "数値はすべて他シートを参照する数式で、ハードコードしていない。"
    )
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="595959")
    ws.merge_cells("A2:E2")

    r = 4
    put(ws, r, 1, "本日の結論", font=Font(name=FONT, size=12, bold=True, color="C00000"), border=False)
    r += 1
    for line in [
        "1. 09-09〜09-12 の 4 日間、公開が 33本/日 から 0〜2本/日 へ全停止していた。09-10〜09-12 は"
        "OAuth リフレッシュトークンの一斉失効が原因（失効スキップ 39/24/21 件）。この 3 日間も"
        "autopilot は 31/31/28 回発火しており、生成した約 90 本が公開されずに捨てられている。",
        "2. 13ch 中 7ch がいまも停止中。トークンが生きているのに autopilot=false だったのは "
        "2ch-matome だけだったので、本日 autopilot を戻した（要バックエンド再起動）。",
        "3. 同意画面が「テスト」のままならトークン寿命は 7 日。09-13 再認可組は 09-20 前後に"
        "また全部止まる。本番公開への切り替えが今日いちばん効く一手で、これは人手でしかできない。",
        "4. analytics は 09-13 に再開したが 09-09〜09-12 が欠測、加えて views は公開から"
        "約 2 日遅れて入る。09-17 に予定していた型ルール・投稿枠の評価は n が足りず実行不能なので 09-23 へ延期した。",
        "5. 09-15 の「維持率 70%以上は登録効率が最下位」は再現しなかった（0.294 → 0.471）。"
        "頂点が 40-50% 帯であることだけが再現。単調な主張は取り下げた。",
        "6. 最も頑健なのは依然として高評価率。四分位で登録/千再生が単調に増える（Q4/Q1 3.46倍・6回目の再現）。",
    ]:
        c = put(ws, r, 1, line, font=Font(name=FONT, size=10), border=False)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        ws.row_dimensions[r].height = 30
        r += 1

    r += 1
    put(ws, r, 1, "主要指標", font=Font(name=FONT, size=12, bold=True, color="1F3864"), border=False)
    r += 1
    for i, h in enumerate(["指標", "値", "参照元", "読み方"], 1):
        ws.cell(row=r, column=i, value=h)
    style_header(ws, r, 4)
    r += 1
    kpis = [
        ("計測済み動画（6ch・全期間）", "='チャンネル別詳細'!B11", INT, "チャンネル別詳細 合計行", ""),
        ("再生数合計", "='チャンネル別詳細'!C11", INT, "同上", ""),
        ("登録者合計", "='チャンネル別詳細'!E11", INT, "同上", ""),
        ("登録/千再生（全期間）", "='チャンネル別詳細'!F11", PCT3, "同上", "至上目標の効率指標"),
        ("登録/千再生（直近14日）", "='チャンネル別詳細'!J11", PCT3, "同上", "全期間より高ければ改善方向"),
        ("直近14日 / 全期間", "='チャンネル別詳細'!L11", "0.00x", "同上", "1.00 超で改善"),
        ("高評価率（全期間）", "='チャンネル別詳細'!G11", PCT3, "同上", "登録の主説明変数"),
        ("最良チャンネル（登録/千・全期間）", "=INDEX('チャンネル別詳細'!A5:A10,MATCH(MAX('チャンネル別詳細'!F5:F10),'チャンネル別詳細'!F5:F10,0))", None, "チャンネル別詳細", ""),
        ("最弱チャンネル（登録/千・全期間）", "=INDEX('チャンネル別詳細'!A5:A10,MATCH(MIN('チャンネル別詳細'!F5:F10),'チャンネル別詳細'!F5:F10,0))", None, "チャンネル別詳細", ""),
        ("09-13 以降公開で未計測の動画", f"=COUNTA('{V}'!D{last+7}:D{last+7+80})", INT, "動画別パフォーマンス 下段", "計測待ち。評価に使えない"),
        ("OAuth 失効中の ch 数", "=COUNTIF(トレンド!E:E,\"失効（要再認可）\")", INT, "トレンド", "公開に到達できない"),
        ("本日の未完了アクション数", "=COUNTIF(改善アクション!F:F,\"未着手\")", INT, "改善アクション", "すべて人手でしか動かせない"),
    ]
    for label, formula, fmt, src, how in kpis:
        put(ws, r, 1, label)
        c = put(ws, r, 2, formula, font=BOLD, align="center")
        if fmt:
            c.number_format = fmt
        put(ws, r, 3, src, font=Font(name=FONT, size=9, color="595959"))
        put(ws, r, 4, how, font=Font(name=FONT, size=9, color="595959"))
        r += 1

    r += 2
    put(ws, r, 1, "本日のコンフィグ変更（適用済）",
        font=Font(name=FONT, size=12, bold=True, color="1F3864"), border=False)
    r += 1
    for i, h in enumerate(["チャンネル", "変更内容"], 1):
        ws.cell(row=r, column=i, value=h)
    style_header(ws, r, 2)
    r += 1
    changes = [
        ("2ch-matome", "autopilot.enabled false → true（トークン生存を確認・1日3枠）／評価期日 09-17 → 09-23／維持率メモ更新"),
        ("daily-science", "評価期日 09-17 → 09-23／維持率メモ更新"),
        ("scp-lab", "評価期日 09-17 → 09-23／維持率メモ更新"),
        ("pokemon-lab", "評価期日 09-17 → 09-23／維持率メモ更新（autopilot は OAuth 失効中のため false のまま）"),
        ("company-facts", "評価期日 09-17 → 09-23／維持率メモ更新"),
        ("yokai-watch", "維持率メモ更新（09-17 の記載は元から無し）"),
        ("（変更なし）", "投稿枠 / タイトル型ルール / voice_style / テーマキュー補充 — 理由は改善アクション #8・#9 と、キュー在庫が 28〜34 件（9〜11 日分）あること"),
    ]
    for ch, txt in changes:
        put(ws, r, 1, ch, font=BOLD)
        c = put(ws, r, 2, txt)
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[r].height = 30
        r += 1

    widths(ws, {"A": 34, "B": 62, "C": 26, "D": 30, "E": 14})


# ---------------------------------------------------------------- main
def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "reports" / f"youtube_analysis_{DATE}.xlsx"
    d = load()
    wb = Workbook()
    wb.remove(wb.active)
    last = sheet_videos(wb, d)
    sheet_channels(wb, last, d)
    sheet_actions(wb)
    sheet_trend(wb, d)
    sheet_summary(wb, d, last)
    wb._sheets = [wb["サマリー"], wb["チャンネル別詳細"], wb["動画別パフォーマンス"],
                  wb["改善アクション"], wb["トレンド"]]
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"✅ {out}")
    print(f"   動画行: {last - 4}  未計測: {len(d['unmeasured'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
