#!/usr/bin/env python3
"""指揮者 2026-09-12 のレポート xlsx を組む。

シート: サマリ / チャンネル別詳細 / 直近動画一覧 / 改善提案 / 前回比較
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "youtube-analysis-2026-09-12.xlsx"

# サンドボックスの soffice は OOM kill されるため recalc が通らない日がある。
# 数式は数式のまま残し、キャッシュ値だけを保存後に XML へ注入する。
sys_path_added = str(ROOT / "reports")
if sys_path_added not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path_added)
from inject_cached_values import FormulaCache  # noqa: E402

FC = FormulaCache()


def F(ws, row, col, formula, value, fmt=None, font=None):
    """数式を書き、同時に計算結果を控える（保存後に注入される）。

    openpyxl は先頭が "=" の文字列だけを数式として扱う。"=" を落とすと
    ただの文字列セルになり、注入も0件になる（09-12 に一度踏んだ）。
    """
    if not formula.startswith("="):
        formula = "=" + formula
    cell = FC.put(ws, row, col, formula, value, number_format=fmt,
                  font=font or BASE, border=BORDER)
    return cell


def per_k(sg, views):
    return (sg / views * 1000) if views else 0


def ratio(a, b):
    return (a / b) if b else 0

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
H_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(name=FONT, bold=True, size=14, color="1F3864")
NOTE_FONT = Font(name=FONT, size=9, italic=True, color="808080")
BASE = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
WARN_FILL = PatternFill("solid", fgColor="FCE4D6")
BAD_FILL = PatternFill("solid", fgColor="F8CBAD")
GOOD_FILL = PatternFill("solid", fgColor="E2EFDA")
INPUT_FONT = Font(name=FONT, size=10, color="0000FF")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

data = json.loads((ROOT / "reports" / "_orch_20260912_data.json").read_text("utf-8"))
CHANNELS = data["channels"]
VIDEOS = data["videos"]
APPLY = json.loads(
    (ROOT / "reports" / "orch_apply_20260912_result.json").read_text("utf-8")
)
CONF = {r["channel"]: r for r in APPLY["conformance"]}


def header(ws, row, cols, widths=None):
    for i, c in enumerate(cols, start=1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.fill, cell.font = H_FILL, H_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 30


def body(ws, r0, rows, numfmts=None):
    for ri, row in enumerate(rows):
        for ci, v in enumerate(row, start=1):
            cell = ws.cell(row=r0 + ri, column=ci, value=v)
            cell.font = BASE
            cell.border = BORDER
            if numfmts and ci in numfmts:
                cell.number_format = numfmts[ci]
    return r0 + len(rows)


# ---------------------------------------------------------------- サマリ
def sheet_summary(wb):
    ws = wb.create_sheet("サマリ")
    ws["A1"] = "YouTube Factory 指揮者レポート 2026-09-12（土）"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "⚠ 本レポートの実績値は analytics.db の最終スナップショット 2026-09-08 のもの。"
        "09-09 以降は video_metrics が0行で、5日連続で新規実績が無い。"
        "原因は YouTube OAuth の全13ch失効（後述）。ブラウザからの直接収集は"
        "無人実行ではサイト承認が下りず不成立（17夜連続）。"
    )
    ws["A2"].font = NOTE_FONT
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:H2")
    ws.row_dimensions[2].height = 46

    r = 4
    ws.cell(row=r, column=1, value="■ 全体（直近30日 2026-08-10〜09-08）").font = BOLD
    r += 1
    header(
        ws, r,
        ["チャンネル", "系統", "動画本数", "再生", "登録", "登録/千再生",
         "いいね率", "平均再生", "キュー適合率"],
        [26, 9, 10, 12, 9, 13, 10, 11, 13],
    )
    r += 1
    first = r
    for ch in CHANNELS:
        c = CONF.get(ch["id"], {})
        rate = c.get("queue_pass_rate")
        vals = [
            ch["name"], ch["系統"], ch["動画本数_30日"], ch["再生_30日"], ch["登録_30日"],
            None, None, None,
            (rate / 100) if rate is not None else "キュー無し",
        ]
        for ci, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=ci, value=v)
            cell.font = BASE
            cell.border = BORDER
        # 計算はシート上の値から引く（入力が変われば追随する）
        v30, sg30, l30, n30 = (
            ch["再生_30日"], ch["登録_30日"], ch["いいね_30日"], ch["動画本数_30日"],
        )
        F(ws, r, 6, f"IF(D{r}=0,0,E{r}/D{r}*1000)", per_k(sg30, v30), "0.000")
        F(ws, r, 7, f"IF(D{r}=0,0,{l30}/D{r})", ratio(l30, v30), "0.00%")
        F(ws, r, 8, f"IF(C{r}=0,0,D{r}/C{r})", ratio(v30, n30), "#,##0")
        ws.cell(row=r, column=4).number_format = "#,##0"
        ws.cell(row=r, column=9).number_format = "0.0%" if rate is not None else "General"
        if ch["登録_30日"] == 0:
            for ci in range(1, 10):
                ws.cell(row=r, column=ci).fill = BAD_FILL
        r += 1
    last = r - 1
    ws.cell(row=r, column=1, value="合計 / 加重平均").font = BOLD
    tN = sum(c["動画本数_30日"] for c in CHANNELS)
    tV = sum(c["再生_30日"] for c in CHANNELS)
    tS = sum(c["登録_30日"] for c in CHANNELS)
    F(ws, r, 3, f"SUM(C{first}:C{last})", tN, font=BOLD)
    F(ws, r, 4, f"SUM(D{first}:D{last})", tV, "#,##0", font=BOLD)
    F(ws, r, 5, f"SUM(E{first}:E{last})", tS, font=BOLD)
    F(ws, r, 6, f"IF(D{r}=0,0,E{r}/D{r}*1000)", per_k(tS, tV), "0.000", font=BOLD)
    total_row = r

    r += 3
    ws.cell(row=r, column=1, value="■ 系統別（唯一の判断指標＝登録/千再生）").font = BOLD
    r += 1
    header(ws, r, ["系統", "ch数", "再生", "登録", "登録/千再生"], [26, 9, 12, 9, 13])
    r += 1
    sys_start = r
    sysk = {}
    for label in ("ゆっくり", "切り抜き"):
        grp = [c for c in CHANNELS if c["系統"] == label]
        gV = sum(c["再生_30日"] for c in grp)
        gS = sum(c["登録_30日"] for c in grp)
        sysk[label] = per_k(gS, gV)
        ws.cell(row=r, column=1, value=label).font = BASE
        ws.cell(row=r, column=1).border = BORDER
        F(ws, r, 2, f"COUNTIF($B${first}:$B${last},A{r})", len(grp))
        F(ws, r, 3, f"SUMIF($B${first}:$B${last},A{r},$D${first}:$D${last})", gV, "#,##0")
        F(ws, r, 4, f"SUMIF($B${first}:$B${last},A{r},$E${first}:$E${last})", gS)
        F(ws, r, 5, f"IF(C{r}=0,0,D{r}/C{r}*1000)", sysk[label], "0.000")
        r += 1
    ws.cell(row=r, column=1, value="ゆっくり ÷ 切り抜き（倍率）").font = BOLD
    F(ws, r, 5, f"IF(E{sys_start+1}=0,0,E{sys_start}/E{sys_start+1})",
      ratio(sysk["ゆっくり"], sysk["切り抜き"]), "0.0\"倍\"", font=BOLD)
    ws.cell(row=r, column=5).comment = Comment(
        "集計窓は 30日（2026-08-10〜09-08）。同じデータでもスナップショット当日行だけで"
        "集計すると倍率が大きく変わるため、倍率を引用するときは必ず窓を併記すること。",
        "指揮者",
    )
    r += 2

    ws.cell(row=r, column=1, value="■ 基盤の状態（本日の実測）").font = BOLD
    r += 1
    header(ws, r, ["項目", "状態", "詳細"], [26, 14, 96])
    r += 1
    facts = [
        ("analytics スナップショット", "停止", "最終 2026-09-08。09-09/10/11/12 は video_metrics が0行（5日連続）。channel_metrics は 09-05 で停止。"),
        ("YouTube OAuth", "全13ch失効", "oauth_tokens の expires_at が全13chで過去。最も新しいもので約52時間前。updated_at は全件 expires_at+8h のままで、リフレッシュに一度も成功していない。"),
        ("動画の公開", "2日連続ゼロ", "video_publish.db の公開実績は 09-10 の2本が最後。09-11・09-12 は0本。09-04〜09-08 は日25〜33本だった。"),
        ("ANTHROPIC_API_KEY", "無効", "backend/.env の18行目でコメントアウトされたまま（13夜連続）。clip-lab の海外バイラル枠 / clip-kaneko のフック生成 / PDCA の Claude 分析 / series_engine の続編生成が同時に停止。"),
        ("バイラル翻訳の滞留", "16件", "data/analytics/viral_translation_pending/ に未処理依頼が16件（08-31〜09-12）。上の API キーが原因。"),
        ("backend.log", "79MB", "ローテーション未実装。grep がタイムアウトするので tail -c で末尾だけ読むこと。"),
        ("pytest", "14 failed / 4 errors", "本日の作業前後で同数（既存の赤）。うち4件は前夜 09-12 01:44 のコミットが追加した test_fixes_20260912.py が最初から赤。passed は 603 → 630。"),
    ]
    for f in facts:
        ws.cell(row=r, column=1, value=f[0]).font = BASE
        c2 = ws.cell(row=r, column=2, value=f[1])
        c2.font = BOLD
        c2.fill = BAD_FILL if f[1] not in ("16件", "79MB") else WARN_FILL
        c3 = ws.cell(row=r, column=3, value=f[2])
        c3.font = BASE
        c3.alignment = Alignment(wrap_text=True, vertical="top")
        for ci in range(1, 4):
            ws.cell(row=r, column=ci).border = BORDER
        ws.row_dimensions[r].height = 30
        r += 1

    r += 1
    ws.cell(row=r, column=1, value=(
        "■ 結論: 本日のボトルネックは制作でも企画でもなく「OAuth の再認可」1点。"
        "動画は作れているが4日ぶん上げられずに積み上がっている。"
        "恒久対策は GCP OAuth 同意画面（project 844705815004）を「テスト中」→「本番」へ公開すること。"
        "テスト中のままだとリフレッシュトークンが7日で強制失効し、再認可しても必ず1週間で再発する。"
    )).font = Font(name=FONT, size=10, bold=True, color="C00000")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 44
    ws.freeze_panes = "A6"
    return total_row


# ------------------------------------------------------- チャンネル別詳細
def sheet_channels(wb):
    ws = wb.create_sheet("チャンネル別詳細")
    ws["A1"] = "チャンネル別詳細（直近30日 2026-08-10〜2026-09-08）"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "登録/千再生 が唯一の判断指標（2026-09-04 決定）。維持率は ch ごとに登録転換との"
        "符号が逆転するため判断に使わない（参考値）。いいね率は符号が反転しない先行指標。"
    )
    ws["A2"].font = NOTE_FONT
    ws.merge_cells("A2:N2")

    cols = ["チャンネル", "ID", "系統", "最終計測日", "動画本数", "再生", "いいね",
            "コメント", "登録", "登録/千再生", "いいね率", "平均再生", "平均維持率",
            "CTR", "ゲート有効", "キュー未公開", "キュー合格", "キュー適合率"]
    header(ws, 4, cols,
           [26, 18, 9, 12, 10, 11, 9, 10, 8, 13, 10, 11, 12, 8, 11, 13, 12, 13])
    r = 5
    first = r
    for ch in CHANNELS:
        c = CONF.get(ch["id"], {})
        ws.cell(row=r, column=1, value=ch["name"])
        ws.cell(row=r, column=2, value=ch["id"])
        ws.cell(row=r, column=3, value=ch["系統"])
        ws.cell(row=r, column=4, value=ch["最終計測日"])
        ws.cell(row=r, column=5, value=ch["動画本数_30日"])
        ws.cell(row=r, column=6, value=ch["再生_30日"]).number_format = "#,##0"
        ws.cell(row=r, column=7, value=ch["いいね_30日"]).number_format = "#,##0"
        ws.cell(row=r, column=8, value=ch["コメント_30日"]).number_format = "#,##0"
        ws.cell(row=r, column=9, value=ch["登録_30日"])
        v30, sg30, l30, n30 = (
            ch["再生_30日"], ch["登録_30日"], ch["いいね_30日"], ch["動画本数_30日"],
        )
        F(ws, r, 10, f"IF(F{r}=0,0,I{r}/F{r}*1000)", per_k(sg30, v30), "0.000")
        F(ws, r, 11, f"IF(F{r}=0,0,G{r}/F{r})", ratio(l30, v30), "0.00%")
        F(ws, r, 12, f"IF(E{r}=0,0,F{r}/E{r})", ratio(v30, n30), "#,##0")
        ws.cell(row=r, column=13, value=ch["平均維持率pct"] / 100).number_format = "0.0%"
        ws.cell(row=r, column=14, value=ch["CTRpct"] / 100).number_format = "0.00%"
        ws.cell(row=r, column=15, value="有効" if c.get("enforced") else "無効")
        ws.cell(row=r, column=16, value=c.get("queue_pending", 0))
        ws.cell(row=r, column=17, value=c.get("queue_pass", 0))
        qp, qk = c.get("queue_pending", 0), c.get("queue_pass", 0)
        F(ws, r, 18, f'IF(P{r}=0,"—",Q{r}/P{r})',
          ratio(qk, qp) if qp else "—", "0.0%")
        for ci in range(1, 19):
            cell = ws.cell(row=r, column=ci)
            cell.font = BASE
            cell.border = BORDER
        if ch["登録_30日"] == 0:
            ws.cell(row=r, column=9).fill = BAD_FILL
            ws.cell(row=r, column=10).fill = BAD_FILL
        if ch["最終計測日"] != "2026-09-08":
            ws.cell(row=r, column=4).fill = WARN_FILL
        r += 1
    ws.cell(row=r, column=1, value="合計").font = BOLD
    tot = {
        5: sum(c["動画本数_30日"] for c in CHANNELS),
        6: sum(c["再生_30日"] for c in CHANNELS),
        7: sum(c["いいね_30日"] for c in CHANNELS),
        8: sum(c["コメント_30日"] for c in CHANNELS),
        9: sum(c["登録_30日"] for c in CHANNELS),
        16: sum(CONF.get(c["id"], {}).get("queue_pending", 0) for c in CHANNELS),
        17: sum(CONF.get(c["id"], {}).get("queue_pass", 0) for c in CHANNELS),
    }
    for ci, col in [(5, "E"), (6, "F"), (7, "G"), (8, "H"), (9, "I"), (16, "P"), (17, "Q")]:
        F(ws, r, ci, f"SUM({col}{first}:{col}{r-1})", tot[ci], "#,##0", font=BOLD)
    F(ws, r, 10, f"IF(F{r}=0,0,I{r}/F{r}*1000)", per_k(tot[9], tot[6]), "0.000", font=BOLD)
    F(ws, r, 18, f"IF(P{r}=0,0,Q{r}/P{r})", ratio(tot[17], tot[16]), "0.0%", font=BOLD)

    ws.cell(row=r + 2, column=1, value=(
        "注: fake-paper と akashic-librarian は 09-06 が最終計測日（他9chは 09-08）。"
        "両chは計測窓が2日短いため、再生・登録の絶対値を他chと直接比べないこと。"
    )).font = NOTE_FONT
    ws.freeze_panes = "C5"


# ------------------------------------------------------- 直近動画一覧
def sheet_videos(wb):
    ws = wb.create_sheet("直近動画一覧")
    ws["A1"] = "直近投稿5本 × 11ch（公開日の新しい順）"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "再生・いいね・登録は各動画の計測期間中の最大値。実効文字数は"
        "ハッシュタグと【】を除いた本文の長さ（title_constraints.effective_len と同じ定義）。"
        "25〜29字が登録転換の頂点（2026-09-11・n=330 の逆U字）。"
    )
    ws["A2"].font = NOTE_FONT
    ws.merge_cells("A2:J2")

    import sys as _sys
    _sys.path.insert(0, str(ROOT / "backend"))
    from pipeline import title_constraints as tc

    cfgs = {
        ch["id"]: json.loads(
            (ROOT / "data" / "channels" / f"{ch['id']}.json").read_text("utf-8")
        )
        for ch in CHANNELS
    }

    header(ws, 4,
           ["チャンネル", "公開日", "タイトル", "実効文字数", "再生", "いいね",
            "登録", "登録/千再生", "いいね率", "ゲート判定", "違反内容"],
           [24, 11, 58, 11, 10, 9, 7, 13, 10, 11, 34])
    r = 5
    first = r
    gate_flags, eff_lens = [], []
    for v in VIDEOS:
        cfg = cfgs[v["ch"]]
        res = tc.check(v["title"], cfg)
        viols = [x.get("label") for x in res.get("violations", []) if x.get("label")]
        ws.cell(row=r, column=1, value=v["name"])
        ws.cell(row=r, column=2, value=v["published_at"])
        ws.cell(row=r, column=3, value=v["title"])
        ws.cell(row=r, column=4, value=tc.effective_len(v["title"]))
        ws.cell(row=r, column=5, value=v["views"]).number_format = "#,##0"
        ws.cell(row=r, column=6, value=v["likes"]).number_format = "#,##0"
        ws.cell(row=r, column=7, value=v["sg"])
        F(ws, r, 8, f"IF(E{r}=0,0,G{r}/E{r}*1000)", per_k(v["sg"], v["views"]), "0.000")
        F(ws, r, 9, f"IF(E{r}=0,0,F{r}/E{r})", ratio(v["likes"], v["views"]), "0.00%")
        gate = ws.cell(row=r, column=10, value="合格" if res["ok"] else "不合格")
        gate_flags.append(res["ok"])
        eff_lens.append(tc.effective_len(v["title"]))
        gate.fill = GOOD_FILL if res["ok"] else WARN_FILL
        ws.cell(row=r, column=11, value="、".join(viols[:4]))
        eff = ws.cell(row=r, column=4)
        if eff.value is not None and eff.value < 20:
            eff.fill = BAD_FILL
        for ci in range(1, 12):
            cell = ws.cell(row=r, column=ci)
            cell.font = BASE
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=(ci in (3, 11)))
        r += 1
    last = r - 1

    r += 1
    ws.cell(row=r, column=1, value="集計").font = BOLD
    n_ok, n_all = sum(gate_flags), len(gate_flags)
    n_short = sum(1 for x in eff_lens if x < 20)
    ws.cell(row=r, column=3, value="ゲート合格の本数").font = BASE
    F(ws, r, 4, f'COUNTIF(J{first}:J{last},"合格")', n_ok, font=BOLD)
    F(ws, r, 5, f"COUNTA(J{first}:J{last})", n_all)
    F(ws, r, 6, f"IF(E{r}=0,0,D{r}/E{r})", ratio(n_ok, n_all), "0.0%", font=BOLD)
    r += 1
    ws.cell(row=r, column=3, value="実効20字未満の本数").font = BASE
    F(ws, r, 4, f'COUNTIF(D{first}:D{last},"<20")', n_short, font=BOLD)
    F(ws, r, 5, f"COUNT(D{first}:D{last})", len(eff_lens))
    F(ws, r, 6, f"IF(E{r}=0,0,D{r}/E{r})", ratio(n_short, len(eff_lens)), "0.0%", font=BOLD)
    r += 1
    ws.cell(row=r, column=3, value="実効文字数の平均").font = BASE
    F(ws, r, 4, f"AVERAGE(D{first}:D{last})",
      ratio(sum(eff_lens), len(eff_lens)), "0.0", font=BOLD)
    r += 2
    ws.cell(row=r, column=1, value=(
        "注: ここでの「不合格」は過去に公開済みの動画を現在のゲートで測り直した結果であり、"
        "公開当時は該当のゲートがまだ存在しなかった。ゲートの効果判定には使えない"
        "（09-09 以降の公開が4本しかなく、うち analytics に載ったものは0本のため、"
        "本日時点でゲートの効果は測定不能）。"
    )).font = NOTE_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=11)
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 40
    ws.freeze_panes = "C5"


# ------------------------------------------------------------ 改善提案
def sheet_actions(wb):
    ws = wb.create_sheet("改善提案")
    ws["A1"] = "改善提案 — 2026-09-12"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "本日は新規の再生実績がゼロ（5日連続）のため、実績に基づく施策変更は行っていない。"
        "「新規の再生実績が無い日は config を変更しない」— 二重適用すると効果の切り分けが"
        "永久に不能になるため。本日実施したのは config とキューの内部矛盾の解消のみ。"
    )
    ws["A2"].font = NOTE_FONT
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:F2")
    ws.row_dimensions[2].height = 32

    header(ws, 4,
           ["優先", "対象", "課題", "打ち手", "状態", "根拠 / 実測値"],
           [7, 20, 42, 52, 16, 56])
    rows = [
        (1, "基盤（全13ch）",
         "OAuth が全13ch で失効。動画は作れているが4日ぶん公開できていない。",
         "GCP OAuth 同意画面（project 844705815004）を「テスト中」→「本番」へ公開し、全chを再認可する。",
         "未着手（要ホスト操作）",
         "oauth_tokens の expires_at が全13chで過去。最新でも約52時間前。updated_at は全件 expires_at+8h でリフレッシュ成功歴ゼロ。公開実績は 09-10 の2本が最後。"),
        (2, "基盤",
         "ANTHROPIC_API_KEY が無効のまま13夜連続。切り抜き系は「上げられない」以前に「作れていない」枠がある。",
         "backend/.env 18行目のコメントアウトを解除する（1行）。",
         "未着手（要ホスト操作）",
         "viral_translation_pending に未処理16件が 08-31 から滞留。clip-lab のバイラル枠 / clip-kaneko のフック生成 / PDCA の Claude 分析 / series_engine が同時停止。"),
        (3, "clip-lab / clip-fukada / clip-kaneko",
         "hard_constraints 未設定のため is_enforced() が False。検査が丸ごとスキップされ、禁止したはずの負け型が素通りしていた。",
         "禁止系のみのゲートを新規付与（秘密 / 99%が知らない / 連番プレフィックス / 絵文字）。引用を壊す min_effective_chars と require_any_of は入れない。",
         "本日適用・コミット済",
         "3ch とも is_enforced()=True を書き込み直後に確認。回帰テスト test_fixes_20260912_orch.py で固定。切り抜き3chは 30日窓の登録/千が 0.004〜0.193 と全系統で最下位。"),
        (4, "全ch（キュー補充）",
         "theme_queue.replenish() が title_constraints を一度も通っていなかった。各chが自分で設定したゲートに自分のキューが落ちる状態。",
         "_annotate_title_gate() を追加。弾かずに title_gate_ok の印を付け、台本生成側が作り直せるようにする。",
         "本日適用・コミット済",
         "未公開99件のうちゲート合格は24件＝24.2%。弾く実装にしないのは 09-11 に「キュー全件ブロック」を起こしたため。"),
        (5, "company-facts",
         "キュー12件すべてが、自ch の banned_words にある絵文字（💸📉💰）を先頭に付けて100%自滅していた。",
         "絵文字を除去。意味を変えない唯一の安全な修復なのでこれだけ機械適用した。",
         "本日適用・コミット済",
         "適合率 0%（0/12）→ 75%（9/12）。残る3件は実効20字未満1件・数字2個以上2件で、これらは再生成が要る。"),
        (6, "全ch（キュー修復の方針）",
         "title_constraints.repair() をキューに当てると日本語が壊れる。",
         "repair はキューに使わない。長さ・数字の違反は LLM 再生成に回す。判断を回帰テストで固定した。",
         "本日確定・コミット済",
         "57件に当てた実測: 「…外見が起こした財団史上最恐の収容違反」→「…外見が起こしの真相」/「…が[DATA EXPUNGED]した恐ろしい記録」→「…が[DATA EXP」/「シェイミの2形態を分ける気温5度の正体」→「…気温正体」。違反数は減るが公開できないものが「合格」として通る。"),
        (7, "yokai-watch",
         "forbid_digits=true なのにキュー10件中10件が数字入りで生成されている。config と生成側が真逆を向いている。",
         "上記4の印付けで可視化された。次回の補充から title_gate_ok=False が付くので再生成対象になる。数字を許すか禁止を続けるかは、実績が戻ってから決める。",
         "観測に載せた（判断は保留）",
         "キュー適合率 0%（0/10）。違反の内訳は「数字禁止」10件。実績ゼロの日に禁止の是非を決めると二重適用になるため本日は判断しない。"),
        (8, "scp-lab / daily-science",
         "キューの平均実効文字数が 39.2字 / 35.8字 で、自ch の max_chars=30 を大きく超えている。",
         "同じく印付けで再生成対象になる。max_chars 自体は 25-29字の頂点に基づくので変えない。",
         "観測に載せた",
         "適合率 scp-lab 4.3%（1/23）・daily-science 0%（0/12）。最多の違反は両chとも「30文字以内」。"),
        (9, "基盤（保守）",
         "前夜 09-12 01:44 のコミットが追加した test_fixes_20260912.py が4件とも最初から赤。構造修正が未完了のまま入っている。",
         "title_gate の配線（clip の dirname / video_generator の sanitize / キュー全件ブロック時の選択 / 疑問形キューの消費順）を直す。",
         "未着手",
         "pytest: 14 failed / 4 errors。うち4件が test_fixes_20260912.py。本日の作業で増減なし。"),
        (10, "基盤（保守）",
         "backend.log が 79MB でローテーション未実装。障害調査時に grep がタイムアウトする。",
         "logrotate か、起動時の切り詰めを入れる。当面は tail -c で末尾だけ読む。",
         "未着手",
         "09-11 時点 81.4MB → 09-12 時点 79MB。"),
    ]
    r = 5
    for row in rows:
        for ci, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=ci, value=v)
            cell.font = BASE
            cell.border = BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        st = row[4]
        ws.cell(row=r, column=5).fill = (
            GOOD_FILL if "済" in st else (WARN_FILL if "観測" in st else BAD_FILL)
        )
        ws.row_dimensions[r].height = 62
        r += 1
    ws.freeze_panes = "A5"


# ------------------------------------------------------------ 前回比較
def sheet_diff(wb):
    ws = wb.create_sheet("前回比較")
    ws["A1"] = "前回比較 — 09-11 の施策は効いたか"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "結論: 効果は測定不能。09-09 以降に公開できた動画が4本しかなく、"
        "そのどれも analytics に載っていないため、ゲート導入前後で比較できる実績が存在しない。"
        "ただし「適用が生き残っているか」は検証でき、こちらは前進があった。"
    )
    ws["A2"].font = Font(name=FONT, size=10, bold=True, color="C00000")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:E2")
    ws.row_dimensions[2].height = 34

    r = 4
    ws.cell(row=r, column=1, value="■ 09-11 施策の生存確認").font = BOLD
    r += 1
    header(ws, r, ["施策", "09-11 の適用", "09-12 の状態", "判定", "備考"],
           [34, 26, 26, 12, 62])
    r += 1
    surv = [
        ("min_effective_chars=20 の付与",
         "8ch に適用（23:10 時点で生存確認）",
         "8ch すべてで生存",
         "継続",
         "09-11 は適用11分後に 2ch-matome の値が別プロセスに消された。今回は14時間後も全ch残存。前夜のコミット 32197ee が ChannelManager.patch_channel_file に書き込みを集約し、ディスクを土台に RLock + tmp/replace するようにした効果とみられる。上書き事故は止まったと判断してよい。"),
        ("akashic-librarian へのゲート新規付与",
         "09-11 に付与",
         "生存（enforced=True）",
         "継続",
         "キュー適合率は 30%（3/10）。最多の違反は「答え提示語が必須」6件。"),
        ("answer-marker（答え提示語）の必須化",
         "6ch で有効",
         "生存",
         "継続",
         "ただし実績が無いため効果は未検証。キュー側の違反は25件で全違反の2番目に多い。"),
        ("fake-paper の「架空論文ファイル」接頭辞禁止",
         "09-11 に付与",
         "生存",
         "継続",
         "キュー10件中5件がまだ接頭辞を含む。生成側が config を見ていないため、印付け（本日の施策4）で可視化した。"),
    ]
    first = r
    for row in surv:
        for ci, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=ci, value=v)
            cell.font = BASE
            cell.border = BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=r, column=4).fill = GOOD_FILL
        ws.row_dimensions[r].height = 58
        r += 1

    r += 2
    ws.cell(row=r, column=1, value="■ キュー適合率の前後（本日の施策の効果）").font = BOLD
    r += 1
    header(ws, r, ["チャンネル", "適用前 合格", "適用後 合格", "未公開件数", "適合率 適用後"],
           [26, 14, 14, 13, 15])
    r += 1
    before = {"scp-lab": 1, "daily-science": 0, "pokemon-lab": 7, "yokai-watch": 0,
              "2ch-matome": 9, "company-facts": 0, "fake-paper": 4,
              "akashic-librarian": 3, "clip-lab": 0, "clip-fukada": 0, "clip-kaneko": 0}
    qfirst = r
    for ch in CHANNELS:
        c = CONF.get(ch["id"], {})
        ws.cell(row=r, column=1, value=ch["name"])
        ws.cell(row=r, column=2, value=before.get(ch["id"], 0))
        ws.cell(row=r, column=3, value=c.get("queue_pass", 0))
        ws.cell(row=r, column=4, value=c.get("queue_pending", 0))
        qp, qk = c.get("queue_pending", 0), c.get("queue_pass", 0)
        F(ws, r, 5, f'IF(D{r}=0,"—",C{r}/D{r})',
          ratio(qk, qp) if qp else "—", "0.0%")
        if c.get("queue_pass", 0) > before.get(ch["id"], 0):
            for ci in range(1, 6):
                ws.cell(row=r, column=ci).fill = GOOD_FILL
        for ci in range(1, 6):
            ws.cell(row=r, column=ci).font = BASE
            ws.cell(row=r, column=ci).border = BORDER
        r += 1
    qlast = r - 1
    ws.cell(row=r, column=1, value="合計").font = BOLD
    tB = sum(before.get(c["id"], 0) for c in CHANNELS)
    tC = sum(CONF.get(c["id"], {}).get("queue_pass", 0) for c in CHANNELS)
    tD = sum(CONF.get(c["id"], {}).get("queue_pending", 0) for c in CHANNELS)
    for ci, col, val in [(2, "B", tB), (3, "C", tC), (4, "D", tD)]:
        F(ws, r, ci, f"SUM({col}{qfirst}:{col}{qlast})", val, font=BOLD)
    cell = F(ws, r, 5, f"IF(D{r}=0,0,C{r}/D{r})", ratio(tC, tD), "0.0%", font=BOLD)
    cell.comment = Comment(
        "company-facts の絵文字除去12件のみによる改善。長さ・数字の違反は "
        "repair が日本語を壊すため機械修復せず、LLM 再生成に回している。",
        "指揮者",
    )
    r += 2
    ws.cell(row=r, column=1, value=(
        "注: 本日の施策の本体はキュー適合率の数字ではなく、①切り抜き3chで検査が"
        "そもそも走っていなかったことの解消と、②補充がゲートを通るようになったこと。"
        "①②は実績が戻った時点で初めて効果が測れる。"
    )).font = NOTE_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 42


def main():
    wb = Workbook()
    wb.remove(wb.active)
    sheet_summary(wb)
    sheet_channels(wb)
    sheet_videos(wb)
    sheet_actions(wb)
    sheet_diff(wb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    n = FC.inject(str(OUT))
    print(f"saved: {OUT}  (キャッシュ値を {n} セルに注入)")


if __name__ == "__main__":
    main()
