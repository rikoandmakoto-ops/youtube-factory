# -*- coding: utf-8 -*-
"""指揮者 Phase 5 — 2026-09-15 分析 xlsx 生成

使い方:
    python3 scripts/orch_xlsx_20260915.py <data.json> <out.xlsx>

data.json は orch_xlsx_data_20260915.py が analytics.db から作る集計済み JSON。
reports/ には LibreOffice のロックファイルが滞留していて recalc が固まるので、
/tmp 等で生成・recalc してから reports/ へ cp すること。
"""
import json
import sys

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

D = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = sys.argv[2]

F = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
H_FONT = Font(name=F, bold=True, color="FFFFFF", size=10)
T_FONT = Font(name=F, bold=True, size=13, color="1F3864")
N_FONT = Font(name=F, size=10)
B_FONT = Font(name=F, bold=True, size=10)
NOTE = Font(name=F, size=9, italic=True, color="595959")
WARN = PatternFill("solid", fgColor="FFF2CC")
GOOD = PatternFill("solid", fgColor="E2EFDA")
BAD = PatternFill("solid", fgColor="FCE4E4")
_t = Side(style="thin", color="BFBFBF")
BD = Border(left=_t, right=_t, top=_t, bottom=_t)

INT = "#,##0"
PCT2 = "0.00%"
PCT3 = "0.000%"
DEC3 = "0.000"
DEC1 = "0.0"

wb = Workbook()


def header(ws, row, cols):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.fill = H_FILL
        cell.font = H_FONT
        cell.border = BD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30


def widths(ws, w):
    for i, x in enumerate(w, 1):
        ws.column_dimensions[get_column_letter(i)].width = x


def title(ws, text, sub=None):
    ws["A1"] = text
    ws["A1"].font = T_FONT
    if sub:
        ws["A2"] = sub
        ws["A2"].font = NOTE


# ======================================================= 1. サマリー
ws = wb.active
ws.title = "サマリー"
widths(ws, [30, 16, 14, 14, 14, 14, 14, 52])
title(ws, "YouTube Factory 日次分析  2026-09-15",
      "データ: data/analytics/analytics.db（最終同期 2026-09-14 22:41 JST）／"
      "video_id ごとに最新スナップショット1行へ畳んでから集計。"
      "09-13 以降に公開した 25 本は views=0 = 未計測のため全集計から除外。")

ws["A4"] = "■ 本日の結論"
ws["A4"].font = B_FONT
concl = [
    "1. カスタムサムネイル 403 が 3 日連続で未解決。09-15 の公開でも scp-lab / company-facts / "
    "yokai-watch は全件失敗し、成功は daily-science のみ。",
    "2. 【新規知見】維持率は高いほど良いという前提は誤り。登録/千は維持率 40-50% を頂点に逆U字。"
    "70% 以上の帯は再生が最大なのに登録は最下位。6ch 中 5ch で ch 内再現。",
    "3. 【新規】バックエンドの Anthropic API キーが 401。サムネ指示文の生成と続編候補の生成が"
    "両方止まっている。",
    "4. OAuth は 09-13 再認可の 5ch が正常稼働。未再認可の 7ch（pokemon-lab ほか）は "
    "invalid_grant のまま。",
    "5. 投稿枠・タイトル型ルール・voice_style は据え置き。09-14 変更分の評価に必要な実測が "
    "1 本も届いていないため（評価日 2026-09-21）。",
]
r = 5
for t in concl:
    ws.cell(row=r, column=1, value=t).font = N_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 28
    r += 1

r += 1
ws.cell(row=r, column=1, value="■ チャンネル別 実績（全期間・畳み済み）").font = B_FONT
r += 1
header(ws, r, ["チャンネル", "本数", "総再生", "平均再生", "登録者",
               "登録/千再生", "高評価率", "平均維持率"])
r += 1
first = r
for c in D["channels"]:
    a = c["all"]
    ws.cell(row=r, column=1, value=c["name"]).font = N_FONT
    ws.cell(row=r, column=2, value=a["n"]).font = N_FONT
    ws.cell(row=r, column=3, value=a["views"]).font = N_FONT
    ws.cell(row=r, column=4, value="=IF(B%d=0,0,C%d/B%d)" % (r, r, r)).font = N_FONT
    ws.cell(row=r, column=5, value=a["subs"]).font = N_FONT
    ws.cell(row=r, column=6, value="=IF(C%d=0,0,E%d/C%d*1000)" % (r, r, r)).font = B_FONT
    ws.cell(row=r, column=7, value="=IF(C%d=0,0,%d/C%d)" % (r, a["likes"], r)).font = N_FONT
    ws.cell(row=r, column=8, value=a["avp"] / 100).font = N_FONT
    for col in range(1, 9):
        ws.cell(row=r, column=col).border = BD
    for col, fmt in [(3, INT), (4, INT), (6, DEC3), (7, PCT3), (8, PCT2)]:
        ws.cell(row=r, column=col).number_format = fmt
    r += 1
last = r - 1
ws.cell(row=r, column=1, value="合計 / 加重平均").font = B_FONT
ws.cell(row=r, column=2, value="=SUM(B%d:B%d)" % (first, last)).font = B_FONT
ws.cell(row=r, column=3, value="=SUM(C%d:C%d)" % (first, last)).font = B_FONT
ws.cell(row=r, column=4, value="=IF(B%d=0,0,C%d/B%d)" % (r, r, r)).font = B_FONT
ws.cell(row=r, column=5, value="=SUM(E%d:E%d)" % (first, last)).font = B_FONT
ws.cell(row=r, column=6, value="=IF(C%d=0,0,E%d/C%d*1000)" % (r, r, r)).font = B_FONT
ws.cell(row=r, column=7,
        value="=IF(C%d=0,0,SUMPRODUCT(C%d:C%d,G%d:G%d)/C%d)" % (r, first, last, first, last, r)).font = B_FONT
ws.cell(row=r, column=8,
        value="=IF(C%d=0,0,SUMPRODUCT(C%d:C%d,H%d:H%d)/C%d)" % (r, first, last, first, last, r)).font = B_FONT
for col in range(1, 9):
    ws.cell(row=r, column=col).fill = GOOD
    ws.cell(row=r, column=col).border = BD
for col, fmt in [(3, INT), (4, INT), (6, DEC3), (7, PCT3), (8, PCT2)]:
    ws.cell(row=r, column=col).number_format = fmt
tot_row = r

r += 2
ws.cell(row=r, column=1, value="■ 直近14日公開（2026-09-01 以降）").font = B_FONT
r += 1
header(ws, r, ["チャンネル", "本数", "総再生", "平均再生", "登録者",
               "登録/千再生", "高評価率", "平均維持率"])
r += 1
rf = r
for c in D["channels"]:
    a = c["recent"]
    ws.cell(row=r, column=1, value=c["name"]).font = N_FONT
    if a:
        ws.cell(row=r, column=2, value=a["n"]).font = N_FONT
        ws.cell(row=r, column=3, value=a["views"]).font = N_FONT
        ws.cell(row=r, column=4, value="=IF(B%d=0,0,C%d/B%d)" % (r, r, r)).font = N_FONT
        ws.cell(row=r, column=5, value=a["subs"]).font = N_FONT
        ws.cell(row=r, column=6, value="=IF(C%d=0,0,E%d/C%d*1000)" % (r, r, r)).font = B_FONT
        ws.cell(row=r, column=7, value="=IF(C%d=0,0,%d/C%d)" % (r, a["likes"], r)).font = N_FONT
        ws.cell(row=r, column=8, value=a["avp"] / 100).font = N_FONT
        for col, fmt in [(3, INT), (4, INT), (6, DEC3), (7, PCT3), (8, PCT2)]:
            ws.cell(row=r, column=col).number_format = fmt
    for col in range(1, 9):
        ws.cell(row=r, column=col).border = BD
    r += 1
rl = r - 1
ws.cell(row=r, column=1, value="合計 / 加重平均").font = B_FONT
ws.cell(row=r, column=2, value="=SUM(B%d:B%d)" % (rf, rl)).font = B_FONT
ws.cell(row=r, column=3, value="=SUM(C%d:C%d)" % (rf, rl)).font = B_FONT
ws.cell(row=r, column=4, value="=IF(B%d=0,0,C%d/B%d)" % (r, r, r)).font = B_FONT
ws.cell(row=r, column=5, value="=SUM(E%d:E%d)" % (rf, rl)).font = B_FONT
ws.cell(row=r, column=6, value="=IF(C%d=0,0,E%d/C%d*1000)" % (r, r, r)).font = B_FONT
for col in range(1, 9):
    ws.cell(row=r, column=col).fill = GOOD
    ws.cell(row=r, column=col).border = BD
for col, fmt in [(3, INT), (4, INT), (6, DEC3)]:
    ws.cell(row=r, column=col).number_format = fmt
rec_row = r

r += 2
ws.cell(row=r, column=1, value="■ 至上目標（登録者増）に対する進捗").font = B_FONT
r += 1
ws.cell(row=r, column=1, value="全期間 登録/千再生").font = N_FONT
ws.cell(row=r, column=2, value="=F%d" % tot_row).font = N_FONT
ws.cell(row=r, column=2).number_format = DEC3
r += 1
ws.cell(row=r, column=1, value="直近14日 登録/千再生").font = N_FONT
ws.cell(row=r, column=2, value="=F%d" % rec_row).font = N_FONT
ws.cell(row=r, column=2).number_format = DEC3
r += 1
ws.cell(row=r, column=1, value="改善率（直近14日 ÷ 全期間）").font = B_FONT
ws.cell(row=r, column=2, value="=IF(B%d=0,0,B%d/B%d-1)" % (r - 2, r - 1, r - 2)).font = B_FONT
ws.cell(row=r, column=2).number_format = '+0.0%;-0.0%;0.0%'
ws.cell(row=r, column=2).fill = GOOD
ws.cell(row=r, column=3, value="プラスであれば改善方向が正しい").font = NOTE

# ======================================================= 2. チャンネル別詳細
ws = wb.create_sheet("チャンネル別詳細")
widths(ws, [14, 26, 10, 12, 12, 10, 12, 12, 12, 12, 12, 14, 14])
title(ws, "チャンネル別 詳細",
      "末尾2列 = 維持率 50% 未満／50% 以上の ch 内対照（公開 2026-08-01 以降・200再生以上）。"
      "登録/千再生で比較する。")
header(ws, 4, ["channel_id", "チャンネル名", "本数", "総再生", "平均再生", "登録者",
               "登録/千再生", "高評価率", "コメント/千", "平均CTR", "平均維持率",
               "維持<50% 登録/千", "維持>=50% 登録/千"])
r = 5
for c in D["channels"]:
    a = c["all"]
    lo_v = (c["lo"]["subs"] / c["lo"]["views"] * 1000) if c["lo"] and c["lo"]["views"] else 0
    hi_v = (c["hi"]["subs"] / c["hi"]["views"] * 1000) if c["hi"] and c["hi"]["views"] else 0
    ws.cell(row=r, column=1, value=c["ch"]).font = N_FONT
    ws.cell(row=r, column=2, value=c["name"]).font = N_FONT
    ws.cell(row=r, column=3, value=a["n"]).font = N_FONT
    ws.cell(row=r, column=4, value=a["views"]).font = N_FONT
    ws.cell(row=r, column=5, value="=IF(C%d=0,0,D%d/C%d)" % (r, r, r)).font = N_FONT
    ws.cell(row=r, column=6, value=a["subs"]).font = N_FONT
    ws.cell(row=r, column=7, value="=IF(D%d=0,0,F%d/D%d*1000)" % (r, r, r)).font = B_FONT
    ws.cell(row=r, column=8, value="=IF(D%d=0,0,%d/D%d)" % (r, a["likes"], r)).font = N_FONT
    ws.cell(row=r, column=9, value="=IF(D%d=0,0,%d/D%d*1000)" % (r, a["comments"], r)).font = N_FONT
    ws.cell(row=r, column=10, value=a["ctr"]).font = N_FONT
    ws.cell(row=r, column=11, value=a["avp"] / 100).font = N_FONT
    ws.cell(row=r, column=12, value=lo_v).font = N_FONT
    ws.cell(row=r, column=13, value=hi_v).font = N_FONT
    for col in range(1, 14):
        ws.cell(row=r, column=col).border = BD
    for col, fmt in [(4, INT), (5, INT), (7, DEC3), (8, PCT3), (9, DEC1),
                     (10, PCT2), (11, PCT2), (12, DEC3), (13, DEC3)]:
        ws.cell(row=r, column=col).number_format = fmt
    if lo_v or hi_v:
        ws.cell(row=r, column=12 if lo_v > hi_v else 13).fill = GOOD
    r += 1
r += 1
ws.cell(row=r, column=1,
        value="注: 緑=その ch で登録/千が高かった側。6ch 中 5ch で「維持率 50% 未満」の側が高い。").font = NOTE

r += 2
ws.cell(row=r, column=1,
        value="■ 投稿枠別 登録/千再生（公開 2026-08-15 以降・n>=3 の枠のみ）").font = B_FONT
r += 1
header(ws, r, ["channel_id", "投稿枠", "本数", "総再生", "登録者", "登録/千再生"])
r += 1
for s in D["slots"]:
    ws.cell(row=r, column=1, value=s["ch"]).font = N_FONT
    ws.cell(row=r, column=2, value=s["hour"]).font = N_FONT
    ws.cell(row=r, column=3, value=s["n"]).font = N_FONT
    ws.cell(row=r, column=4, value=s["views"]).font = N_FONT
    ws.cell(row=r, column=5, value=s["subs"]).font = N_FONT
    ws.cell(row=r, column=6, value="=IF(D%d=0,0,E%d/D%d*1000)" % (r, r, r)).font = N_FONT
    ws.cell(row=r, column=4).number_format = INT
    ws.cell(row=r, column=6).number_format = DEC3
    for col in range(1, 7):
        ws.cell(row=r, column=col).border = BD
    r += 1

# ======================================================= 3. 動画別パフォーマンス
ws = wb.create_sheet("動画別パフォーマンス")
widths(ws, [14, 12, 8, 56, 11, 10, 10, 9, 12, 11, 11, 11])
title(ws, "動画別パフォーマンス（2026-09-01 以降公開・再生数上位60本）",
      "09-13 以降の公開分は analytics 上 views=0 = 未計測のため本表には現れない。")
header(ws, 4, ["channel_id", "公開日", "時刻", "タイトル", "再生数", "高評価", "コメント",
               "登録者", "登録/千再生", "高評価率", "CTR", "維持率"])
r = 5
for v in D["videos"]:
    ws.cell(row=r, column=1, value=v["ch"]).font = N_FONT
    ws.cell(row=r, column=2, value=v["pub"]).font = N_FONT
    ws.cell(row=r, column=3, value=v["hhmm"]).font = N_FONT
    ws.cell(row=r, column=4, value=v["title"]).font = N_FONT
    ws.cell(row=r, column=5, value=v["v"]).font = N_FONT
    ws.cell(row=r, column=6, value=v["lk"]).font = N_FONT
    ws.cell(row=r, column=7, value=v["cm"]).font = N_FONT
    ws.cell(row=r, column=8, value=v["sg"]).font = N_FONT
    ws.cell(row=r, column=9, value="=IF(E%d=0,0,H%d/E%d*1000)" % (r, r, r)).font = N_FONT
    ws.cell(row=r, column=10, value="=IF(E%d=0,0,F%d/E%d)" % (r, r, r)).font = N_FONT
    ws.cell(row=r, column=11, value=v["ctr"]).font = N_FONT
    ws.cell(row=r, column=12, value=v["avp"] / 100).font = N_FONT
    for col, fmt in [(5, INT), (9, DEC3), (10, PCT3), (11, PCT2), (12, PCT2)]:
        ws.cell(row=r, column=col).number_format = fmt
    for col in range(1, 13):
        ws.cell(row=r, column=col).border = BD
    if v["sg"] == 0 and v["v"] >= 800:
        ws.cell(row=r, column=8).fill = BAD
    if v["v"] and v["sg"] / v["v"] * 1000 >= 1.5:
        ws.cell(row=r, column=9).fill = GOOD
    r += 1
r += 1
ws.cell(row=r, column=1,
        value="赤=800再生以上あるのに登録0（再生は出ても登録に繋がらない型）／"
              "緑=登録/千が 1.5 以上の高転換本。").font = NOTE

# ======================================================= 4. 改善アクション
ws = wb.create_sheet("改善アクション")
widths(ws, [6, 13, 34, 62, 15, 16])
title(ws, "改善アクション  2026-09-15",
      "すべて本日の実測に基づく。適用済みのものは 状態=適用済 と記す。")
header(ws, 4, ["#", "優先度", "項目", "内容・根拠", "担当", "状態"])
acts = [
    (1, "最優先", "カスタムサムネイル 403（電話番号確認）",
     "09-15 の公開でも scp-lab / company-facts / yokai-watch の全件で 403 forbidden が継続。"
     "成功は daily-science のみ。https://www.youtube.com/verify を該当 9ch で通す。"
     "反映まで最大24時間。パイプライン側では直せない。", "人手", "未着手"),
    (2, "最優先", "Anthropic API キーが 401（新規検出）",
     "backend ログに claude_client call failed (thumbnail_brief): Error code: 401 API key is invalid。"
     "series_engine も「Claude 未応答のため続編候補を生成しません」で停止。"
     "サムネ指示文と続編候補の生成が両方止まっている。", "人手", "未着手"),
    (3, "高", "OAuth 同意画面を「本番」公開 → そのあと再認可",
     "09-13 再認可の 5ch（daily-science / scp-lab / yokai-watch / company-facts / socio-rx）は "
     "09-15 時点で正常。未再認可の 7ch（pokemon-lab / clip-lab / clip-kaneko / clip-fukada / "
     "clip-animal / fake-paper / akashic-librarian）は invalid_grant のまま。"
     "テスト状態のままだと再認可しても 7 日で失効する。", "人手", "未着手"),
    (4, "高", "維持率の目標帯を 40-50% に変更（最大化をやめる）",
     "公開08-01以降・200再生以上・n=350 を維持率バンド別に見ると登録/千は "
     "<30% 0.243 / 30-40% 0.426 / 40-50% 0.624 / 50-60% 0.414 / 60-70% 0.451 / 70%以上 0.294 の逆U字。"
     "ch 内対照でも維持率<50% の側が高いのが 6ch 中 5ch。"
     "平均尺は各バンド 33〜39 秒でほぼ一定なので尺の交絡ではない。"
     "optimization.retention_target_band に明記し、維持率目的の voice_style 調整は今後行わない。",
     "指揮者", "適用済"),
    (5, "中", "テーマキュー在庫を 7 日以上へ補充",
     "daily-science 18→21 / scp-lab 18→21 / yokai-watch 20→21 / company-facts 26→28。"
     "型は 09-14 に ch 内対照で確定した最良型（ds=A型 / scp=A型 / yokai=B型・数字禁止 / "
     "cf=C型）を踏襲。", "指揮者", "適用済"),
    (6, "中", "analytics バックフィルの実行",
     "09-13 以降に公開した 25 本が views=0 のまま記録されている。"
     "OAuth 復旧後のバックフィルが未実行。これが走らない限り 09-14 の投稿枠・型ルール変更を"
     "評価できない。", "バックエンド", "未着手"),
    (7, "低", "reports/ の LibreOffice ロックファイル掃除",
     ".~lock.youtube_analysis_*.xlsx# が 20 個滞留。サンドボックスからは権限の都合で削除できない。"
     "本日も /tmp 相当で recalc してから reports/ へ cp する回避策を使った。", "人手", "回避中"),
    (8, "—", "投稿枠・タイトル型ルール・voice_style は据え置き",
     "09-14 に全6ch で変更したばかりで、その後の公開分（25本）が 1 本も計測されていない。"
     "同一データで二度目の意思決定をしない。評価は n≧20/ch が揃う 2026-09-21。",
     "指揮者", "意図的に変更なし"),
    (9, "—", "pokemon-lab / 2ch-matome の autopilot は false のまま",
     "pokemon-lab は 09-15 のログでも invalid_grant が継続しており公開に到達しない。"
     "加えてサムネ権限が未解決のまま生成を増やすと自動抽出サムネの動画が増えるだけ。"
     "サムネ権限の解消後に再判断。", "指揮者", "意図的に変更なし"),
]
r = 5
for a in acts:
    for i, val in enumerate(a, 1):
        cell = ws.cell(row=r, column=i, value=val)
        cell.font = B_FONT if i == 3 else N_FONT
        cell.border = BD
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    if a[1] == "最優先":
        ws.cell(row=r, column=2).fill = BAD
    elif a[1] == "高":
        ws.cell(row=r, column=2).fill = WARN
    if a[5] == "適用済":
        ws.cell(row=r, column=6).fill = GOOD
    ws.row_dimensions[r].height = 64
    r += 1

# ======================================================= 5. トレンド
ws = wb.create_sheet("トレンド")
widths(ws, [16, 12, 13, 14, 12, 12, 14, 14])
title(ws, "トレンド",
      "上段=公開日別の実績推移／下段=維持率バンド別の登録転換（本日の最重要発見）。")
header(ws, 4, ["公開日", "公開本数", "計測済本数", "総再生", "登録者", "高評価",
               "登録/千再生", "高評価率"])
r = 5
tf = r
for t in D["trend"]:
    ws.cell(row=r, column=1, value=t["date"]).font = N_FONT
    ws.cell(row=r, column=2, value=t["n_pub"]).font = N_FONT
    ws.cell(row=r, column=3, value=t["n_meas"]).font = N_FONT
    ws.cell(row=r, column=4, value=t["views"]).font = N_FONT
    ws.cell(row=r, column=5, value=t["subs"]).font = N_FONT
    ws.cell(row=r, column=6, value=t["likes"]).font = N_FONT
    ws.cell(row=r, column=7, value="=IF(D%d=0,0,E%d/D%d*1000)" % (r, r, r)).font = N_FONT
    ws.cell(row=r, column=8, value="=IF(D%d=0,0,F%d/D%d)" % (r, r, r)).font = N_FONT
    ws.cell(row=r, column=4).number_format = INT
    ws.cell(row=r, column=7).number_format = DEC3
    ws.cell(row=r, column=8).number_format = PCT3
    for col in range(1, 9):
        ws.cell(row=r, column=col).border = BD
    if t["n_meas"] == 0:
        for col in range(1, 9):
            ws.cell(row=r, column=col).fill = WARN
    r += 1
tl = r - 1
ws.cell(row=r, column=1, value="合計").font = B_FONT
for col, L in [(2, "B"), (3, "C"), (4, "D"), (5, "E"), (6, "F")]:
    ws.cell(row=r, column=col, value="=SUM(%s%d:%s%d)" % (L, tf, L, tl)).font = B_FONT
ws.cell(row=r, column=7, value="=IF(D%d=0,0,E%d/D%d*1000)" % (r, r, r)).font = B_FONT
ws.cell(row=r, column=8, value="=IF(D%d=0,0,F%d/D%d)" % (r, r, r)).font = B_FONT
for col in range(1, 9):
    ws.cell(row=r, column=col).fill = GOOD
    ws.cell(row=r, column=col).border = BD
ws.cell(row=r, column=4).number_format = INT
ws.cell(row=r, column=7).number_format = DEC3
ws.cell(row=r, column=8).number_format = PCT3
r += 1
ws.cell(row=r, column=1,
        value="黄=公開したが analytics 上まだ 1 本も計測されていない日（09-13 / 09-14）。"
              "09-10〜09-12 は OAuth 失効で公開そのものが 0 本。").font = NOTE

r += 2
ws.cell(row=r, column=1,
        value="■ 【本日の最重要発見】維持率バンド別 登録転換"
              "（公開 2026-08-01 以降・200再生以上・n=350）").font = B_FONT
r += 1
header(ws, r, ["維持率バンド", "本数", "総再生", "登録者", "登録/千再生",
               "高評価率", "平均視聴秒", "推定尺(秒)"])
r += 1
bf = r
for b in D["bands"]:
    ws.cell(row=r, column=1, value=b["band"]).font = N_FONT
    ws.cell(row=r, column=2, value=b["n"]).font = N_FONT
    ws.cell(row=r, column=3, value=b["views"]).font = N_FONT
    ws.cell(row=r, column=4, value=b["subs"]).font = N_FONT
    ws.cell(row=r, column=5, value="=IF(C%d=0,0,D%d/C%d*1000)" % (r, r, r)).font = B_FONT
    ws.cell(row=r, column=6, value="=IF(C%d=0,0,%d/C%d)" % (r, b["likes"], r)).font = N_FONT
    ws.cell(row=r, column=7, value=b["avd"]).font = N_FONT
    ws.cell(row=r, column=8, value=b["est"]).font = N_FONT
    for col, fmt in [(3, INT), (5, DEC3), (6, PCT3), (7, DEC1), (8, DEC1)]:
        ws.cell(row=r, column=col).number_format = fmt
    for col in range(1, 9):
        ws.cell(row=r, column=col).border = BD
    if b["band"] == "40-50%":
        for col in range(1, 9):
            ws.cell(row=r, column=col).fill = GOOD
    if b["band"] == "70%以上":
        for col in range(1, 9):
            ws.cell(row=r, column=col).fill = BAD
    r += 1
bl = r - 1
r += 1
ws.cell(row=r, column=1, value="最良帯の登録/千").font = B_FONT
ws.cell(row=r, column=2, value="=MAX(E%d:E%d)" % (bf, bl)).font = B_FONT
ws.cell(row=r, column=2).number_format = DEC3
r += 1
ws.cell(row=r, column=1, value="最良帯 ÷ 70%以上帯").font = B_FONT
ws.cell(row=r, column=2,
        value="=IF(E%d=0,0,MAX(E%d:E%d)/E%d)" % (bl, bf, bl, bl)).font = B_FONT
ws.cell(row=r, column=2).number_format = '0.00"倍"'
ws.cell(row=r, column=2).fill = WARN
r += 2
for line in [
    "解釈: 登録/千は維持率 40-50% を頂点に逆U字を描く。"
    "70% 以上の帯は平均再生が最大（1,982）なのに登録/千は全帯で最下位。",
    "交絡チェック: 推定尺は 30-70% の各バンドで 33〜39 秒とほぼ一定であり、"
    "尺の違いによる見かけの差ではない。",
    "ch 内再現: 維持率<50% の側が高いのが daily-science 1.43倍 / scp-lab 1.20 / "
    "2ch-matome 1.18 / pokemon-lab 1.70 / yokai-watch 1.20（company-facts のみ 0.83 で逆）。",
    "運用への反映: 維持率は最大化目標から外し 40-50% を目標帯とする。"
    "維持率改善を理由とした voice_style 調整は今後行わない。"
    "登録の主説明変数は引き続き高評価率（四分位 Q4/Q1 3.90倍・5回再現）。",
]:
    ws.cell(row=r, column=1, value=line).font = N_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 26
    r += 1

for s in wb.worksheets:
    s.freeze_panes = "A5"
    s.sheet_view.showGridLines = False

wb.save(OUT)
print("saved", OUT)
