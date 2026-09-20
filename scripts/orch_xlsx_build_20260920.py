# -*- coding: utf-8 -*-
import json, datetime as dt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

D = json.load(open('/tmp/orch_data.json'))
wb = Workbook()
F = "Arial"
H1 = Font(name=F, size=14, bold=True, color="FFFFFF")
HD = Font(name=F, size=10, bold=True, color="FFFFFF")
BD = Font(name=F, size=10, bold=True)
NM = Font(name=F, size=10)
SM = Font(name=F, size=9, color="555555")
FILL_T = PatternFill("solid", fgColor="1F3864")
FILL_H = PatternFill("solid", fgColor="4472C4")
FILL_W = PatternFill("solid", fgColor="FCE4D6")   # warn
FILL_G = PatternFill("solid", fgColor="E2EFDA")   # good
FILL_Y = PatternFill("solid", fgColor="FFF2CC")   # note
THIN = Border(*[Side(style="thin", color="BFBFBF")]*4)
CEN = Alignment(horizontal="center", vertical="center")
WRP = Alignment(wrap_text=True, vertical="top")

def title(ws, text, span):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    c = ws.cell(1, 1, text); c.font = H1; c.fill = FILL_T; c.alignment = CEN
    ws.row_dimensions[1].height = 26

def header(ws, row, cols):
    for i, h in enumerate(cols, 1):
        c = ws.cell(row, i, h); c.font = HD; c.fill = FILL_H; c.alignment = CEN; c.border = THIN
    ws.row_dimensions[row].height = 30

def widths(ws, ws_widths):
    for i, w in enumerate(ws_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

def note(ws, row, text, span, fill=FILL_Y):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    c = ws.cell(row, 1, text); c.font = NM; c.fill = fill; c.alignment = WRP
    return row

# ============================================================ 1. サマリー
ws = wb.active; ws.title = "サマリー"
title(ws, "YouTube Factory 指揮者レポート  2026-09-20（データ: analytics.db 09-19 スナップショット）", 9)
widths(ws, [18, 11, 8, 12, 11, 11, 9, 11, 11])
r = 3
ws.cell(r, 1, "■ 本日の結論").font = BD
r += 1
concl = ("08-19 に降りたリーチの天井は、台本ではなく『動画の末尾』が原因である可能性が高い。\n"
 "維持曲線をコホート分解すると 再生位置0〜10% は 08-19 前後で同一（冒頭フックは壊れていない）で、\n"
 "差は15%以降で開き末尾ほど拡大し、100%地点は 17.2% → 9.8% とほぼ半減している。\n"
 "完走率とループ率は5ch同時に 08-19 で落ち、以後戻っていない。同日 short_endcard.py が新設され、\n"
 "無音静止画のエンドカード1.6〜1.8秒が全6chの末尾に焼き込まれた。09-18 に長尺事故を戻しても\n"
 "完走率と再生は戻らず、08-19 に入って今も戻していない末尾変更はこのエンドカードだけである。\n"
 "→ 本日 daily-science / yokai-watch / 2ch-matome で enabled=false。scp-lab / company-facts は対照。判定 09-27。")
ws.merge_cells(start_row=r, start_column=1, end_row=r+6, end_column=9)
cc = ws.cell(r, 1, concl); cc.font = NM; cc.fill = FILL_W; cc.alignment = WRP
r += 8

ws.cell(r, 1, "■ チャンネル別サマリー（各chの最新スナップショット・直近50本）").font = BD
r += 1
hr = r
header(ws, r, ["チャンネル", "スナップ", "本数", "総再生", "再生中央", "維持率中央%", "登録", "登録/千再生", "高評価率%"])
r += 1
first = r
for s in D['summary']:
    ws.cell(r, 1, s['ch']).font = NM
    ws.cell(r, 2, s['snapshot']).font = NM
    ws.cell(r, 3, s['n']).font = NM
    ws.cell(r, 4, s['views']).font = NM
    ws.cell(r, 5, s['med_views']).font = NM
    ws.cell(r, 6, round(s['ret'], 1)).font = NM
    ws.cell(r, 7, s['subs']).font = NM
    ws.cell(r, 8, f"=IF(D{r}=0,0,G{r}/D{r}*1000)").font = NM
    ws.cell(r, 9, f"=IF(D{r}=0,0,{s['likes']}/D{r}*100)").font = NM
    for col in range(1, 10):
        ws.cell(r, col).border = THIN
    ws.cell(r, 8).number_format = "0.000"; ws.cell(r, 9).number_format = "0.000"
    ws.cell(r, 4).number_format = "#,##0"; ws.cell(r, 5).number_format = "#,##0"
    r += 1
last = r - 1
ws.cell(r, 1, "合計/中央").font = BD
ws.cell(r, 3, f"=SUM(C{first}:C{last})").font = BD
ws.cell(r, 4, f"=SUM(D{first}:D{last})").font = BD
ws.cell(r, 5, f"=MEDIAN(E{first}:E{last})").font = BD
ws.cell(r, 6, f"=MEDIAN(F{first}:F{last})").font = BD
ws.cell(r, 7, f"=SUM(G{first}:G{last})").font = BD
ws.cell(r, 8, f"=IF(D{r}=0,0,G{r}/D{r}*1000)").font = BD
ws.cell(r, 8).number_format = "0.000"
ws.cell(r, 4).number_format = "#,##0"; ws.cell(r, 5).number_format = "#,##0"
for col in range(1, 10):
    ws.cell(r, col).fill = FILL_G; ws.cell(r, col).border = THIN
r += 2
note(ws, r, "※ pokemon-lab は OAuth 失効により 09-08 が最終スナップショット（11日停止中）。"
            "至上目標は『登録/千再生』。数値は各chの最新スナップショット時点の直近50本の累計で、"
            "views は YouTube Analytics の直近30日ウィンドウ（fetch_video_metrics days=30）。", 9)
r += 2
ws.cell(r, 1, "■ ザキ様の対応が必要（1件）").font = BD
r += 1
note(ws, r, "pokemon-lab の OAuth 再認可（11日放置・09-17/18/19 も同じ依頼）。成熟動画の 40% が1,200再生超で "
            "6ch中いちばん天井が高いch。止めている損が最大。手順は restart_and_trigger_20260920.command に記載。\n"
            "サムネ403は 09-19 の実測どおり優先度を下げたまま（再生の99.5%はShortsフィード由来で、サムネの効きうる上限は0.48%）。", 9, FILL_W)
ws.row_dimensions[r].height = 42

# ============================================================ 2. チャンネル別詳細
ws2 = wb.create_sheet("チャンネル別詳細")
title(ws2, "チャンネル別詳細 — 08-19 前後のコホート比較（ループ率・20%地点・完走率・再生）", 7)
widths(ws2, [17, 16, 7, 13, 13, 13, 13])
r = 3
note(ws2, r, "audience_watch_ratio の中央値。Shortsはループ再生されるため 0%地点は100%を超える（超過分＝ループ発生分）。"
             "完走率は再生位置95-100%の値。コホート①はエンドカード導入前、②以降は導入後。", 7)
ws2.row_dimensions[r].height = 30
r += 2
header(ws2, r, ["チャンネル", "コホート", "n", "ループ率0%", "20%地点", "完走率95-100%", "再生中央値"])
r += 1
prev = None
for x in D['loop']:
    if prev and prev != x['ch']:
        r += 1
    prev = x['ch']
    ws2.cell(r, 1, x['ch']).font = NM
    ws2.cell(r, 2, x['cohort']).font = NM
    ws2.cell(r, 3, x['n']).font = NM
    for i, k in enumerate(['loop', 'p20', 'fin'], 4):
        c = ws2.cell(r, i, round(x[k], 1) if x[k] is not None else None); c.font = NM; c.number_format = "0.0"
    c = ws2.cell(r, 7, x['med_views']); c.font = NM; c.number_format = "#,##0"
    fill = FILL_G if x['cohort'].startswith('1:') else (FILL_W if x['fin'] and x['fin'] < 13 else None)
    for col in range(1, 8):
        ws2.cell(r, col).border = THIN
        if fill: ws2.cell(r, col).fill = fill
    r += 1
r += 1
note(ws2, r, "読み方: 緑=エンドカード導入前(①)。橙=完走率13%未満。5ch すべてで ① → ②以降に "
             "ループ率が 5〜13pt、完走率がほぼ半減し、再生中央値が 20〜45% 落ちている。"
             "ch個別の台本改訂では『5chが同じ日に同時に落ちる』ことを説明できない。", 7)
ws2.row_dimensions[r].height = 30
r += 2
ws2.cell(r, 1, "■ 維持曲線の形状（再生位置ごとの audience_watch_ratio 中央値 %）").font = BD
r += 1
BINS = [0, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100]
header(ws2, r, ["グループ", "コホート", "n"] + [f"{b}%" for b in BINS])
for i in range(1, 4 + len(BINS)):
    ws2.column_dimensions[get_column_letter(i)].width = max(ws2.column_dimensions[get_column_letter(i)].width or 8, 8)
ws2.column_dimensions['A'].width = 17; ws2.column_dimensions['B'].width = 16
r += 1
for x in D['retention']:
    ws2.cell(r, 1, x['grp']).font = NM
    ws2.cell(r, 2, x['cohort']).font = NM
    ws2.cell(r, 3, x['n']).font = NM
    for i, b in enumerate(BINS, 4):
        v = x.get(f'p{b}')
        c = ws2.cell(r, i, round(v, 1) if v else None); c.font = NM; c.number_format = "0.0"; c.border = THIN
    for col in range(1, 4):
        ws2.cell(r, col).border = THIN
    if x['cohort'].startswith('1:'):
        for col in range(1, 4 + len(BINS)): ws2.cell(r, col).fill = FILL_G
    r += 1
r += 1
note(ws2, r, "0%・5%・10% は ① と ③④ でほぼ同値（111.1 vs 107.7）＝冒頭フックは壊れていない。"
             "差は15%以降で開き（90.8→74.7）、末尾ほど拡大して100%地点で 17.2→9.8 と半減する。"
             "壊れているのは動画の後半〜末尾である。", 4 + len(BINS))
ws2.row_dimensions[r].height = 30

# ============================================================ 3. 動画別パフォーマンス
ws3 = wb.create_sheet("動画別パフォーマンス")
title(ws3, "動画別パフォーマンス — 09-12 以降公開（最新スナップショット時点）", 11)
widths(ws3, [15, 46, 16, 9, 10, 10, 9, 8, 8, 8, 9])
r = 3
header(ws3, r, ["チャンネル", "タイトル", "公開", "再生", "維持率%", "平均視聴s", "推定尺s", "高評価", "コメント", "登録", "CTR%"])
r += 1
first3 = r
for v in D['videos']:
    ws3.cell(r, 1, v['ch']).font = NM
    ws3.cell(r, 2, v['title']).font = NM
    ws3.cell(r, 3, v['pub']).font = NM
    ws3.cell(r, 4, v['views']).font = NM
    ws3.cell(r, 5, round(v['ret'], 1)).font = NM
    ws3.cell(r, 6, round(v['dur'], 1)).font = NM
    ws3.cell(r, 7, f"=IF(E{r}<=5,\"\",F{r}/(E{r}/100))").font = NM
    ws3.cell(r, 8, v['likes']).font = NM
    ws3.cell(r, 9, v['comments']).font = NM
    ws3.cell(r, 10, v['subs']).font = NM
    ws3.cell(r, 11, round(v['ctr'], 2)).font = NM
    ws3.cell(r, 4).number_format = "#,##0"; ws3.cell(r, 7).number_format = "0.0"
    for col in range(1, 12): ws3.cell(r, col).border = THIN
    if v['views'] >= 1200: 
        for col in range(1, 12): ws3.cell(r, col).fill = FILL_G
    r += 1
last3 = r - 1
ws3.cell(r, 1, "中央値").font = BD
for col, L in [(4, 'D'), (5, 'E'), (6, 'F'), (7, 'G'), (11, 'K')]:
    ws3.cell(r, col, f"=MEDIAN({L}{first3}:{L}{last3})").font = BD
    ws3.cell(r, col).fill = FILL_G; ws3.cell(r, col).border = THIN
ws3.cell(r, 4).number_format = "#,##0"
ws3.cell(r, 8, f"=SUM(H{first3}:H{last3})").font = BD
ws3.cell(r, 10, f"=SUM(J{first3}:J{last3})").font = BD
r += 2
note(ws3, r, "緑=1,200再生超。推定尺 = 平均視聴時間 ÷ (維持率/100)。エンドカード1.6〜1.8秒を含む値である点に注意。", 11)
ws3.freeze_panes = "A4"

# ============================================================ 4. 改善アクション
ws4 = wb.create_sheet("改善アクション")
title(ws4, "改善アクション（2026-09-20）— すべて実データ由来", 6)
widths(ws4, [5, 17, 34, 46, 13, 13])
r = 3
header(ws4, r, ["#", "対象", "アクション", "根拠（実測）", "状態", "判定日"])
r += 1
ACT = [
 (1, "daily-science\nyokai-watch\n2ch-matome",
  "defaults.short_endcard.enabled = false\n（無音静止画1.6〜1.8秒の末尾カードを撤去）",
  "維持曲線の 0〜10% は 08-19 前後で同一、差は15%以降で開き100%地点で 17.2→9.8% と半減。"
  "完走率・ループ率が5ch同時に08-19で落ち戻らない。同日 short_endcard.py が新設・全6ch有効化。"
  "09-18 に長尺事故を戻しても回復せず、08-19 で未撤回の末尾変更はこれだけ。",
  "適用済", "2026-09-27"),
 (2, "scp-lab\ncompany-facts",
  "エンドカードを true のまま維持（対照群）\n09-27 まで defaults.short_endcard を触らない",
  "A/Bの対照。company-facts は完走率19.3〜31.6%・再生中央1059〜1714 を保つ唯一のchで情報量が最大。"
  "scp-lab は 09-19 の台本修正ありなので、同じく修正済の daily-science との対で"
  "『台本修正 × カード有無』が読める。",
  "適用済", "2026-09-27"),
 (3, "moviepy 5ch",
  "Phase4 の手動トリガーは発行しない",
  "APScheduler が本日分14枠を予約済（yokai 11:15 / company-facts 11:45 / scp-lab 12:00 …）で、"
  "09-13〜09-19 は毎日 枠数どおり 13〜14本を公開できている。手動トリガーは重複投稿と"
  "連投ガード(min_fire_interval 90分)の空振りを生むだけ。load_channel はディスクを毎回読むため"
  "本日の生成から新設定が反映される。",
  "判断のみ", "—"),
 (4, "pokemon-lab",
  "★ザキ様: OAuth 再認可（11日放置）",
  "09-10 07:43 を最後にトークン未更新、09-14 に autopilot.enabled=false。"
  "成熟動画の 40%(10/25) が1,200再生超で6ch中いちばん天井が高い。止めている損が最大。",
  "依頼中", "—"),
 (5, "company-facts",
  "サムネ2MB超で失敗している件を記録（対応は保留）",
  "logs/backend.log に『サムネ失敗: Media larger than: 2097152』。403とは別原因。"
  "ただし再生の99.5%はShortsフィード由来でサムネの効きうる上限は0.48%のため、優先度は低い。",
  "記録のみ", "—"),
 (6, "全6ch",
  "テーマキューは補充しない",
  "queue は daily-science 5 / scp-lab 3 / yokai-watch 7 / company-facts 6 / 2ch-matome 24 だが、"
  "theme_seeds が 28〜33件あり生成は seeds にフォールバックする。水増し補充は09-19に続き見送る。",
  "判断のみ", "—"),
 (7, "全6ch",
  "投稿時刻・文字数帯・voice_style は変更しない",
  "投稿時刻は09-17、文字数帯は09-18、台本は09-19 に変更済で評価が 09-24〜09-26 に来る。"
  "本日さらに触ると本日のエンドカードA/Bと三重に交絡する。",
  "判断のみ", "—"),
]
for a in ACT:
    for i, v in enumerate(a, 1):
        c = ws4.cell(r, i, v); c.font = NM; c.alignment = WRP; c.border = THIN
    ws4.cell(r, 5).fill = FILL_G if a[4] == "適用済" else (FILL_W if a[4] == "依頼中" else FILL_Y)
    ws4.row_dimensions[r].height = 76
    r += 1
r += 1
note(ws4, r, "判定 2026-09-27 の読み方: 主指標=完走率(95-100%) OFF群が 11.5% → 16%以上へ回復するか。"
             "副指標=ループ率(0%) 110→114%以上 / 再生中央値d3 / 登録/千再生。"
             "回復しなければ撤回してエンドカードを戻す（登録導線としての価値は残るため）。", 6)
ws4.row_dimensions[r].height = 30

# ============================================================ 5. トレンド
ws5 = wb.create_sheet("トレンド")
title(ws5, "トレンド — 日次チャンネル指標（08-10以降）", 7)
widths(ws5, [12, 17, 11, 12, 12, 12, 14])
r = 3
note(ws5, r, "channel_metrics（YouTube Analytics の日別）。純増 = 登録増 − 登録減。"
             "08-19 の縦線がエンドカード導入日。", 7)
r += 2
header(ws5, r, ["日付", "チャンネル", "再生", "登録増", "登録減", "純増", "視聴時間(分)"])
r += 1
first5 = r
for t in D['trend']:
    if t['channel_id'] not in ['daily-science', 'scp-lab', '2ch-matome', 'pokemon-lab', 'yokai-watch', 'company-facts']:
        continue
    ws5.cell(r, 1, t['date']).font = NM
    ws5.cell(r, 2, t['channel_id']).font = NM
    ws5.cell(r, 3, t['views']).font = NM
    ws5.cell(r, 4, t['subscribers_gained']).font = NM
    ws5.cell(r, 5, t['subscribers_lost']).font = NM
    ws5.cell(r, 6, f"=D{r}-E{r}").font = NM
    ws5.cell(r, 7, round(t['watch_time_minutes'], 1)).font = NM
    ws5.cell(r, 3).number_format = "#,##0"; ws5.cell(r, 7).number_format = "#,##0.0"
    for col in range(1, 8): ws5.cell(r, col).border = THIN
    if t['date'] == '2026-08-19':
        for col in range(1, 8): ws5.cell(r, col).fill = FILL_W
    r += 1
last5 = r - 1
ws5.cell(r, 1, "合計").font = BD
for col, L in [(3, 'C'), (4, 'D'), (5, 'E'), (6, 'F'), (7, 'G')]:
    ws5.cell(r, col, f"=SUM({L}{first5}:{L}{last5})").font = BD
    ws5.cell(r, col).fill = FILL_G; ws5.cell(r, col).border = THIN
ws5.cell(r, 3).number_format = "#,##0"; ws5.cell(r, 7).number_format = "#,##0.0"
ws5.freeze_panes = "A6"

# 登録/千再生 コホート表
r += 2
ws5.cell(r, 1, "■ 登録/千再生（至上目標）のコホート推移 — エンドカードは登録を稼いだか").font = BD
r += 1
header(ws5, r, ["チャンネル", "コホート", "本数", "総再生", "登録", "登録/千再生", "高評価率%"])
r += 1
f6 = r
for s in D['subs']:
    ws5.cell(r, 1, s['ch']).font = NM
    ws5.cell(r, 2, s['cohort']).font = NM
    ws5.cell(r, 3, s['n']).font = NM
    ws5.cell(r, 4, s['views']).font = NM
    ws5.cell(r, 5, s['subs']).font = NM
    ws5.cell(r, 6, f"=IF(D{r}=0,0,E{r}/D{r}*1000)").font = NM
    ws5.cell(r, 7, round(s['like'], 3)).font = NM
    ws5.cell(r, 4).number_format = "#,##0"; ws5.cell(r, 6).number_format = "0.000"; ws5.cell(r, 7).number_format = "0.000"
    for col in range(1, 8): ws5.cell(r, col).border = THIN
    if s['cohort'].startswith('1:'):
        for col in range(1, 8): ws5.cell(r, col).fill = FILL_G
    r += 1
l6 = r - 1
ws5.cell(r, 1, "6ch合計").font = BD
ws5.cell(r, 4, f"=SUM(D{f6}:D{l6})").font = BD
ws5.cell(r, 5, f"=SUM(E{f6}:E{l6})").font = BD
ws5.cell(r, 6, f"=IF(D{r}=0,0,E{r}/D{r}*1000)").font = BD
ws5.cell(r, 4).number_format = "#,##0"; ws5.cell(r, 6).number_format = "0.000"
for col in range(1, 8): ws5.cell(r, col).fill = FILL_G; ws5.cell(r, col).border = THIN
r += 2
note(ws5, r, "緑=エンドカード導入前(①)。6ch合計の登録/千再生は ①0.512 → ②0.510 → ③0.730 → ④0.436 で、"
             "エンドカード導入による跳ねが無い。一方で完走率は半減している。"
             "＝エンドカードは登録を稼がずにリーチだけを削っている疑いが強い。"
             "（④は公開後1〜8日で登録の計上が遅れるため過小評価側）", 7)
ws5.row_dimensions[r].height = 42

import os
os.makedirs('/tmp/out', exist_ok=True)
wb.save('/tmp/out/youtube_analysis_20260920.xlsx')
print("saved")
