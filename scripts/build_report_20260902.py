#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指揮者タスク Phase 5: 分析xlsx生成 (2026-09-02)"""
import json, os, datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open("/tmp/analysis.json", encoding="utf-8"))
OUT = os.path.join(ROOT, "reports", "youtube_analysis_20260902.xlsx")

F = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
H_FONT = Font(name=F, bold=True, color="FFFFFF", size=10)
T_FONT = Font(name=F, size=10)
B_FONT = Font(name=F, bold=True, size=10)
TITLE = Font(name=F, bold=True, size=14, color="1F3864")
NOTE = Font(name=F, size=9, italic=True, color="666666")
GOOD = PatternFill("solid", fgColor="C6EFCE")
BAD = PatternFill("solid", fgColor="FFC7CE")
WARN = PatternFill("solid", fgColor="FFEB9C")
THIN = Border(*[Side(style="thin", color="BFBFBF")] * 4)

CH = ["daily-science", "scp-lab", "2ch-matome", "pokemon-lab", "yokai-watch", "company-facts"]
NAME = {c: D["ch_quality"][c]["name"] for c in CH}

wb = Workbook()


def head(ws, row, cols, widths=None):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font, cell.fill, cell.border = H_FONT, H_FILL, THIN
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 30


def put(ws, r, c, v, fmt=None, font=None, fill=None, align=None):
    cell = ws.cell(row=r, column=c, value=v)
    cell.font = font or T_FONT
    cell.border = THIN
    if fmt: cell.number_format = fmt
    if fill: cell.fill = fill
    if align: cell.alignment = Alignment(horizontal=align)
    return cell


# ============================================================ 1. サマリー
ws = wb.active
ws.title = "サマリー"
ws["A1"] = "YouTube Factory 指揮者レポート 2026-09-02"
ws["A1"].font = TITLE
ws["A2"] = ("分析対象: data/analytics/analytics.db / 直近コホート published_at>=2026-08-10・再生150超 (n=138本) / "
            "実績スナップショット最新 2026-08-31（company-facts のみ 09-01）")
ws["A2"].font = NOTE
ws["A3"] = ("注意: video_metrics.views は累積スナップショットのため単純合計は不可。増分は前週スナップショットとの差分で算出。")
ws["A3"].font = NOTE

head(ws, 5, ["チャンネル", "本数", "総再生", "中央値再生", "平均維持率", "平均視聴秒",
             "推定尺", "登録者", "登録転換率", "高評価率", "判定"],
     [22, 8, 11, 12, 11, 11, 10, 9, 12, 11, 26])

r = 6
first = r
for ch in CH:
    q = D["ch_quality"][ch]
    put(ws, r, 1, q["name"], font=B_FONT)
    put(ws, r, 2, q["n"], "#,##0")
    put(ws, r, 3, q["views"], "#,##0")
    put(ws, r, 4, q["med_views"], "#,##0")
    put(ws, r, 5, q["avp"] / 100, "0.0%")
    put(ws, r, 6, q["dur"], '0.0"s"')
    put(ws, r, 7, q["est_len"], '0.0"s"')
    put(ws, r, 8, q["subs"], "#,##0")
    put(ws, r, 9, f"=IF(C{r}=0,0,H{r}/C{r})", "0.000%")   # 登録転換率
    put(ws, r, 10, f"=IF(C{r}=0,0,{q['likes']}/C{r})", "0.00%")  # 高評価率
    # 判定は維持率と登録転換率の実測から
    if q["avp"] >= 55 and q["conv"] >= 0.06:
        put(ws, r, 11, "最良。増産の第一候補", fill=GOOD)
    elif q["avp"] < 35:
        put(ws, r, 11, "維持率が最下位帯。構成改善が最優先", fill=BAD)
    elif q["conv"] < 0.02:
        put(ws, r, 11, "登録動線が機能していない", fill=BAD)
    else:
        put(ws, r, 11, "維持率が改善余地", fill=WARN)
    r += 1
last = r - 1

put(ws, r, 1, "合計 / 加重平均", font=B_FONT)
for col, fmt in ((2, "#,##0"), (3, "#,##0"), (8, "#,##0")):
    put(ws, r, col, f"=SUM({get_column_letter(col)}{first}:{get_column_letter(col)}{last})", fmt, font=B_FONT)
put(ws, r, 5, f"=SUMPRODUCT(C{first}:C{last},E{first}:E{last})/SUM(C{first}:C{last})", "0.0%", font=B_FONT)
put(ws, r, 6, f"=SUMPRODUCT(C{first}:C{last},F{first}:F{last})/SUM(C{first}:C{last})", '0.0"s"', font=B_FONT)
put(ws, r, 9, f"=H{r}/C{r}", "0.000%", font=B_FONT)
ws.cell(row=r, column=9).comment = Comment(
    "至上目標であるチャンネル登録者に対する全社ボトルネック指標。\n"
    "1,000再生あたり登録者に換算すると約0.4人。", "orchestrator")

r += 3
ws.cell(row=r, column=1, value="本日の結論（実測ベース）").font = Font(name=F, bold=True, size=12, color="1F3864")
r += 1
for line in [
    "1. 登録転換の実質的なドライバは「絶対視聴秒」。22秒以上視聴された動画は登録転換0.061%で、14秒未満(0.031%)の約2倍。",
    "2. 維持率(AVP)は単独では判断材料にならない。尺に交絡するため。",
    "   例: 2ch-matome はAVP52.4%（2位）だが推定尺30.7秒（最短）によるもので、視聴15.6秒・登録転換0.016%（最下位）。",
    "3. company-facts だけが例外的に強い。推定尺55.5秒（最長）をAVP58.5%で維持し、視聴33.9秒＝他ch(14.8-17.3秒)の約2倍。登録転換0.076%も最良。",
    "4. company-facts の設定上の唯一の差分は読み上げ速度 speed=1.2（他5chは1.3-1.35）。",
    "   → 本日 daily-science/scp-lab/pokemon-lab/yokai-watch を1.2へ、2ch-matome を1.25へ変更。company-facts は対照群として据え置き。",
    "   ※ これは確定的な改善ではなく仮説検証。company-facts は尺も最長であり速度単独の効果とは分離できていない。",
    "     反証条件: 変更5chの絶対視聴秒が3日以内に改善しなければ speed を元の値へ戻す。",
    "5. ナンバリング型タイトルはAVP33.3%、自然文は52.3%。08-31適用の禁止ルールは有効（08-31公開分 0/7本）。維持。",
    "6. 流入のほぼ全てがショートフィード。サムネ経由のインプレッションは6ch合計で18,365に対し実再生は15万超。",
    "   → サムネ最優先の運用方針は費用対効果が低い。改善原資はフック・維持率・CTAに配分すべき（方針変更は要判断・未実施）。",
    "7. scp-lab のテーマキューが0本＝本日の制作が停止する状態だった。全6chへ計37テーマを補充済み。",
    "8. 2ch-matome は登録転換率0.016%で全ch最下位（最良の company-facts の約1/5）。エンドカードを登録訴求型に変更した。",
]:
    ws.cell(row=r, column=1, value=line).font = T_FONT
    r += 1

# ============================================================ 2. チャンネル別詳細
ws = wb.create_sheet("チャンネル別詳細")
ws["A1"] = "チャンネル別詳細 / 適用した変更"
ws["A1"].font = TITLE
head(ws, 3, ["チャンネル", "7日増分再生", "7日増分高評価", "維持率", "登録転換率",
             "サムネimp", "サムネclick", "サムネCTR", "サムネ流入比率", "キュー本数",
             "speed 変更前", "speed 変更後", "本日の変更"],
     [20, 13, 14, 10, 12, 11, 11, 11, 14, 11, 13, 13, 52])

SPEED_OLD = {"daily-science": 1.3, "scp-lab": 1.3, "2ch-matome": 1.35,
             "pokemon-lab": 1.3, "yokai-watch": 1.3, "company-facts": 1.2}
SPEED_NEW = {"daily-science": 1.2, "scp-lab": 1.2, "2ch-matome": 1.25,
             "pokemon-lab": 1.2, "yokai-watch": 1.2, "company-facts": 1.2}
QUEUE = {"daily-science": 13, "scp-lab": 12, "2ch-matome": 18,
         "pokemon-lab": 12, "yokai-watch": 16, "company-facts": 16}
CHANGES = {
    "daily-science": "speed 1.3→1.2 / 答えの遅延ルール追加 / テーマ+8",
    "scp-lab": "speed 1.3→1.2 / 答えの遅延ルール追加 / テーマ+12（キュー0本の枯渇を解消）",
    "2ch-matome": "speed 1.35→1.25 / エンドカードを登録訴求型に変更",
    "pokemon-lab": "speed 1.3→1.2 / 答えの遅延ルール追加 / テーマ+5",
    "yokai-watch": "speed 1.3→1.2 / 答えの遅延ルール追加 / テーマ+4",
    "company-facts": "テーマ+8のみ（speed 1.2 据え置き＝対照群）",
}
reach = {x["ch"]: x for x in D["reach"]}
r = 4
for ch in CH:
    q = D["ch_quality"][ch]
    dl = D["ch_delta"][ch]
    rc = reach.get(ch, {"imp": 0, "clk": 0})
    put(ws, r, 1, q["name"], font=B_FONT)
    put(ws, r, 2, dl["dviews"], "#,##0")
    put(ws, r, 3, dl["dlikes"], "#,##0")
    put(ws, r, 4, q["avp"] / 100, "0.0%")
    put(ws, r, 5, q["conv"] / 100, "0.000%")
    put(ws, r, 6, rc["imp"], "#,##0")
    put(ws, r, 7, rc["clk"], "#,##0")
    put(ws, r, 8, f"=IF(F{r}=0,0,G{r}/F{r})", "0.00%")
    put(ws, r, 9, f"=IF(B{r}=0,0,G{r}/B{r})", "0.00%")
    ws.cell(row=r, column=9).comment = Comment(
        "サムネクリック数 ÷ 7日増分再生。\n"
        "この比率が示すのは、総再生のうちサムネ経由で獲得できている割合。\n"
        "全ch数%に留まり、残りはショートフィードからの流入。", "orchestrator")
    put(ws, r, 10, QUEUE[ch], "0", fill=None if QUEUE[ch] >= 12 else WARN)
    put(ws, r, 11, SPEED_OLD[ch], "0.00")
    put(ws, r, 12, SPEED_NEW[ch], "0.00",
        fill=GOOD if SPEED_NEW[ch] != SPEED_OLD[ch] else None)
    put(ws, r, 13, CHANGES[ch])
    r += 1

r += 2
ws.cell(row=r, column=1, value="speed変更の根拠と検証設計").font = B_FONT
r += 1
for line in [
    "仮説: 読み上げ速度が高いほど単位時間あたりの情報密度が上がり、処理が追いつかず離脱が早まる。",
    "根拠: speed=1.2 の company-facts のみ 平均視聴33.9秒＝他ch(14.8-17.3秒)の約2倍。登録転換0.076%も最良。",
    "      speed は company-facts と他5chの間にある設定上の唯一の差分。",
    "      絶対視聴秒×登録転換: 0-14秒 0.031% / 14-17秒 0.038% / 17-22秒 0.035% / 22秒以上 0.061%。",
    "",
    "留意点（この変更は確定的な改善ではなく仮説検証である）:",
    "  ・2ch-matome は speed 1.35（最速）でありながら維持率52.4%（2位）。「速度が低いほど維持率が高い」は単純には成立しない。",
    "    2ch-matome の高維持率は推定尺30.7秒（最短）による機械的なもので、視聴15.6秒・登録転換0.016%（最下位）。",
    "  ・したがって維持率(率)は尺に交絡する。判断は絶対視聴秒で行う。",
    "  ・company-facts は推定尺55.5秒（最長）でもあり、速度単独の効果とは分離できていない。",
    "",
    "検証: company-facts を speed 1.2 据え置きの対照群とし、変更5chの絶対視聴秒を翌日以降のコホートで比較する。",
    "反証条件: 変更5chの絶対視聴秒が3日以内に改善しない場合、速度は主因ではないと判断し",
    "          元の値（4ch=1.3 / 2ch-matome=1.35）へ戻す。",
]:
    ws.cell(row=r, column=1, value=line).font = T_FONT
    r += 1

# ============================================================ 3. 動画別パフォーマンス
ws = wb.create_sheet("動画別パフォーマンス")
ws["A1"] = "動画別パフォーマンス（published_at>=2026-08-10 / 再生150超）"
ws["A1"].font = TITLE
head(ws, 3, ["チャンネル", "公開日", "タイトル", "再生", "維持率", "視聴秒",
             "推定尺", "高評価", "高評価率", "コメント", "登録", "ナンバリング"],
     [18, 12, 62, 10, 10, 10, 10, 9, 11, 10, 8, 13])
vids = sorted(D["videos"], key=lambda x: (x["channel_id"], -x["views"]))
r = 4
for v in vids:
    put(ws, r, 1, NAME[v["channel_id"]])
    put(ws, r, 2, v["published_at"][:10])
    put(ws, r, 3, v["title"][:90])
    put(ws, r, 4, v["views"], "#,##0")
    cell = put(ws, r, 5, (v["avg_view_percentage"] or 0) / 100, "0.0%")
    if (v["avg_view_percentage"] or 0) >= 60: cell.fill = GOOD
    elif (v["avg_view_percentage"] or 0) < 30: cell.fill = BAD
    put(ws, r, 6, v["avg_view_duration"], '0"s"')
    put(ws, r, 7, v["est_len"], '0.0"s"')
    put(ws, r, 8, v["likes"], "#,##0")
    put(ws, r, 9, f"=IF(D{r}=0,0,H{r}/D{r})", "0.00%")
    put(ws, r, 10, v["comments"], "#,##0")
    put(ws, r, 11, v["subscribers_gained"] or 0, "#,##0")
    put(ws, r, 12, v["numbered"], align="center",
        fill=BAD if v["numbered"] == "あり" else None)
    r += 1
ws.freeze_panes = "A4"
ws.auto_filter.ref = f"A3:L{r-1}"

# ============================================================ 4. 改善アクション
ws = wb.create_sheet("改善アクション")
ws["A1"] = "改善アクション（2026-09-02 実施済み / 保留）"
ws["A1"].font = TITLE
head(ws, 3, ["#", "対象", "アクション", "根拠（実測）", "期待効果", "状態", "検証方法"],
     [5, 20, 40, 60, 26, 14, 42])
ACTIONS = [
    ("scp-lab", "テーマキューを0→12本に補充",
     "theme_queue が空。本日の自動制作が起動できない状態だった",
     "制作停止の回避", "実施済み", "翌日のキュー残量が減っていること"),
    ("全6ch", "テーマキューを計37本補充（各ch12本以上を確保）",
     "daily-science 5本 / pokemon-lab 7本 / company-facts 8本と枯渇寸前",
     "制作の連続性確保", "実施済み", "各chのqueue長を毎日監視"),
    ("daily-science / scp-lab / pokemon-lab / yokai-watch", "読み上げ速度 1.3→1.2【仮説検証】",
     "speed=1.2 の company-facts のみ平均視聴33.9秒＝他ch(14.8-17.3秒)の約2倍・登録転換0.076%で最良。speed が設定上の唯一の差分。"
     "ただし company-facts は推定尺55.5秒（最長）でもあり速度単独の効果とは分離できていない",
     "絶対視聴秒 22秒超へ", "実施済み（要検証）",
     "対照群 company-facts との絶対視聴秒の差を3日追跡。改善しなければ1.3へ戻す"),
    ("2ch-matome", "読み上げ速度 1.35→1.25【仮説検証】",
     "全ch最速。掲示板ノリのテンポを残すため中間値に留めた。"
     "なお2ch-matomeは最速でありながら維持率52.4%（2位）で、速度仮説の反例にあたる（尺30.7秒＝最短による機械的な高率）",
     "絶対視聴秒の改善", "実施済み（要検証）", "同上。改善しなければ1.35へ戻す"),
    ("scp-lab / pokemon-lab / daily-science / yokai-watch", "short_format に「答えの遅延」ルールを追加",
     "scp-lab は維持率40.3%・平均視聴14.8秒でいずれも全ch最下位。各chとも推定尺の39-46%地点で離脱しており、3行目で核心を出し切る構成が原因",
     "後半維持率の改善", "実施済み", "生成台本の5行目に結論が置かれているか目視"),
    ("2ch-matome", "エンドカードを登録訴求型に変更",
     "登録転換率0.016%で全ch最下位（最良の company-facts 0.076%の約1/5）。参加型お題でコメント誘導はできているが登録動線が無かった",
     "登録転換率を0.03%以上へ", "実施済み", "翌週コホートの登録転換率"),
    ("全6ch", "ナンバリング型タイトル禁止の維持",
     "AVP 33.3%(ナンバリング) vs 52.3%(自然文)。08-31適用ルールにより08-31公開分は0/7本で遵守されている",
     "維持率の下支え", "継続中", "公開日別のナンバリング混入本数を毎日確認"),
    ("company-facts", "投稿本数の増加を検討",
     "維持率58.5% / 絶対視聴33.9秒 / 登録転換0.076% / 中央値再生1,284 と全指標で最良。にもかかわらず本数は最少水準",
     "登録者増の最短経路", "保留（判断待ち）", "1日2本化した場合の1本あたり再生の希釈を測定"),
    ("運用方針", "「サムネ品質最優先」の見直しを提案",
     "6ch合計のサムネimp 18,365に対しコホート総再生は151,975。サムネ経由は総流入の十数%以下に留まり、大半はショートフィード流入",
     "改善リソースの再配分", "要判断", "ユーザー判断待ち。方針変更は指示があるまで行わない"),
    ("データ基盤", "channel_metrics の取得欠損を修正",
     "channel_metrics は 2026-08-29 以降が欠損。video_metrics も09-01は4chのみ取得",
     "登録者数の直接追跡", "未対応", "バックエンド復旧後に取得ジョブの状態を確認"),
]
r = 4
for i, a in enumerate(ACTIONS, 1):
    put(ws, r, 1, i, align="center")
    put(ws, r, 2, a[0], font=B_FONT)
    for j, v in enumerate(a[1:], 3):
        c = put(ws, r, j, v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    st = ws.cell(row=r, column=6)
    st.fill = GOOD if a[4] == "実施済み" else (WARN if a[4] in ("継続中",) else BAD)
    ws.row_dimensions[r].height = 46
    r += 1

# ============================================================ 5. トレンド
ws = wb.create_sheet("トレンド")
ws["A1"] = "トレンド分析"
ws["A1"].font = TITLE

ws["A3"] = "① 日次増分再生（前日スナップショットとの差分）"
ws["A3"].font = B_FONT
head(ws, 4, ["日付"] + [NAME[c] for c in CH] + ["合計"], [12] + [16] * 6 + [12])
r = 5
tstart = r
for t in D["trend"]:
    if all(t.get(c) is None for c in CH):
        continue
    put(ws, r, 1, t["date"])
    for i, c in enumerate(CH, 2):
        put(ws, r, i, t.get(c), "#,##0")
    put(ws, r, 8, f"=SUM(B{r}:G{r})", "#,##0", font=B_FONT)
    r += 1
tend = r - 1
put(ws, r, 1, "平均", font=B_FONT)
for i in range(2, 9):
    L = get_column_letter(i)
    put(ws, r, i, f"=IFERROR(AVERAGE({L}{tstart}:{L}{tend}),0)", "#,##0", font=B_FONT)

r += 3
ws.cell(row=r, column=1, value="② 維持率帯別パフォーマンス（維持率が再生数を決めている）").font = B_FONT
r += 1
head(ws, r, ["維持率帯", "本数", "中央値再生", "平均維持率", "登録転換率"], [16, 9, 13, 12, 12])
r += 1
for s in D["seg_avp"]:
    put(ws, r, 1, s["label"]); put(ws, r, 2, s["n"], "0")
    put(ws, r, 3, s["med"], "#,##0"); put(ws, r, 4, s["avp"] / 100, "0.0%")
    put(ws, r, 5, s["conv"] / 100, "0.000%")
    r += 1

r += 2
ws.cell(row=r, column=1, value="③ 平均視聴秒数帯別（25秒以上視聴されると登録転換が跳ねる）").font = B_FONT
r += 1
head(ws, r, ["視聴秒数帯", "本数", "中央値再生", "平均維持率", "登録転換率"], [16, 9, 13, 12, 12])
r += 1
for s in D["seg_dur"]:
    put(ws, r, 1, s["label"]); put(ws, r, 2, s["n"], "0")
    put(ws, r, 3, s["med"], "#,##0"); put(ws, r, 4, s["avp"] / 100, "0.0%")
    put(ws, r, 5, s["conv"] / 100, "0.000%")
    r += 1

r += 2
ws.cell(row=r, column=1, value="④ 推定尺別（尺そのものは維持率を説明しない＝速度仮説の裏付け）").font = B_FONT
r += 1
head(ws, r, ["推定尺帯", "本数", "中央値再生", "平均維持率", "登録転換率"], [16, 9, 13, 12, 12])
r += 1
for s in D["seg_len"]:
    put(ws, r, 1, s["label"]); put(ws, r, 2, s["n"], "0")
    put(ws, r, 3, s["med"], "#,##0"); put(ws, r, 4, s["avp"] / 100, "0.0%")
    put(ws, r, 5, s["conv"] / 100, "0.000%")
    r += 1

r += 2
ws.cell(row=r, column=1, value="⑤ タイトル形式別（ナンバリング禁止ルールの妥当性）").font = B_FONT
r += 1
head(ws, r, ["タイトル形式", "本数", "中央値再生", "平均維持率", "登録転換率"], [24, 9, 13, 12, 12])
r += 1
for s in D["seg_num"]:
    put(ws, r, 1, s["label"]); put(ws, r, 2, s["n"], "0")
    put(ws, r, 3, s["med"], "#,##0")
    c = put(ws, r, 4, s["avp"] / 100, "0.0%")
    c.fill = BAD if s["avp"] < 40 else GOOD
    put(ws, r, 5, s["conv"] / 100, "0.000%")
    r += 1

r += 2
ws.cell(row=r, column=1,
        value="注: 上記②〜⑤は同一コホート（published_at>=2026-08-10・再生150超・n=138）に対する層別集計。").font = NOTE

os.makedirs(os.path.dirname(OUT), exist_ok=True)
wb.save(OUT)
print("saved:", OUT)
