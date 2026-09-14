#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-14 指揮者 Phase 5: 分析 xlsx 出力"""
import json, os, re, sqlite3, datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = "2026-09-14"
OUT = os.path.join(ROOT, "reports", f"youtube_analysis_{TODAY.replace('-','')}.xlsx")
DATA = json.load(open("/tmp/analysis_20260914.json", encoding="utf-8"))

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
H_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
T_FONT = Font(name=FONT, size=10)
B_FONT = Font(name=FONT, size=10, bold=True)
TITLE_FONT = Font(name=FONT, size=14, bold=True, color="1F3864")
NOTE_FONT = Font(name=FONT, size=9, italic=True, color="666666")
WARN_FILL = PatternFill("solid", fgColor="FFC7CE")
GOOD_FILL = PatternFill("solid", fgColor="C6EFCE")
WARN_FONT = Font(name=FONT, size=10, bold=True, color="9C0006")
THIN = Border(*[Side(style="thin", color="BFBFBF")] * 4)

wb = Workbook()


def head(ws, row, cols, widths=None):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.fill, cell.font, cell.border = H_FILL, H_FONT, THIN
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def put(ws, r, c, v, fmt=None, font=None, fill=None):
    cell = ws.cell(row=r, column=c, value=v)
    cell.font = font or T_FONT
    cell.border = THIN
    if fmt:
        cell.number_format = fmt
    if fill:
        cell.fill = fill
    return cell


CH_ORDER = ["daily-science", "scp-lab", "yokai-watch", "company-facts", "pokemon-lab", "2ch-matome"]
CH_JP = {"daily-science": "リコとマコトのゆっくり日常科学", "scp-lab": "異常存在SCPゆっくり解説ラボ",
         "yokai-watch": "ゆっくり妖怪ラボ", "company-facts": "企業のホンネ",
         "pokemon-lab": "ゆっくりポケラボ", "2ch-matome": "ゆっくり2chスレまとめ劇場"}

cohort = {r["ch"]: r for r in DATA["cohort"]}
recent = {r["ch"]: r for r in DATA["recent14"]}

# ==================================================== 1. サマリー
ws = wb.active
ws.title = "サマリー"
ws["A1"] = f"YouTube Factory 指揮者レポート  {TODAY}"
ws["A1"].font = TITLE_FONT
ws["A2"] = ("データ源: data/analytics/analytics.db（最終同期 2026-09-13 13:40 UTC）。"
            "video_metrics を video_id ごとの最新スナップショット1行に畳んで集計。"
            "判断軸は至上目標である 登録者/千再生。")
ws["A2"].font = NOTE_FONT
ws.column_dimensions["A"].width = 30

r = 4
ws.cell(row=r, column=1, value="■ 本日の結論").font = B_FONT
r += 1
for line in [
    "1. OAuth は 2026-09-13 に復旧した。09-09 から 5 日間ゼロだった公開が再開し、"
    "バックエンドログの直近 200KB に invalid_grant は 1 件も出ていない。",
    "2. ただしカスタムサムネイルは 10ch 中 daily-science の 1ch でしか設定できていない。"
    "ログ全体で 成功 21 本（全部 daily-science）／失敗 163 本（他 9ch 全部）。"
    "原因は YouTube アカウントの電話番号確認が未了であること。パイプラインでは直せない。",
    "3. 直近14日の全体 登録/千再生は 0.708 で、コホート全期間 0.544 から +30%。改善方向は正しい。",
    "4. タイトルの「型」が登録変換をチャンネルごとに強く分ける。本日この型ルールを 6ch 全部に反映した。",
    "5. 投稿枠は 17 時前後が 4ch で最良。登録ゼロの枠（2ch-matome 21時 など）を潰して夕方へ寄せた。",
]:
    c = ws.cell(row=r, column=1, value=line)
    c.font = T_FONT
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    ws.row_dimensions[r].height = 30
    r += 1

r += 1
ws.cell(row=r, column=1, value="■ チャンネル別 実績（左: 公開2026-08-10以降の全コホート / 右: 直近14日 公開2026-08-31以降）").font = B_FONT
r += 1
hdr = ["チャンネル", "名称", "本数", "総再生", "平均再生", "登録者", "登録/千再生",
       "高評価率%", "平均維持率%", "直近14日 本数", "直近14日 登録/千", "前期比"]
head(ws, r, hdr, [15, 28, 7, 10, 10, 8, 12, 11, 12, 13, 15, 9])
hr = r
r += 1
first = r
for ch in CH_ORDER:
    c0, r14 = cohort.get(ch), recent.get(ch)
    if not c0:
        continue
    put(ws, r, 1, ch)
    put(ws, r, 2, CH_JP[ch])
    put(ws, r, 3, c0["n"], "#,##0")
    put(ws, r, 4, c0["tv"], "#,##0")
    put(ws, r, 5, f"=IFERROR(D{r}/C{r},0)", "#,##0")
    put(ws, r, 6, c0["ts"], "#,##0")
    put(ws, r, 7, f"=IFERROR(F{r}*1000/D{r},0)", "0.000")
    put(ws, r, 8, c0["tl"] * 100.0 / c0["tv"] if c0["tv"] else 0, "0.000")
    put(ws, r, 9, c0["ret"] or 0, "0.0")
    put(ws, r, 10, r14["n"] if r14 else 0, "#,##0")
    put(ws, r, 11, (r14["ts"] * 1000.0 / r14["tv"]) if r14 and r14["tv"] else 0, "0.000")
    put(ws, r, 12, f"=IFERROR(K{r}/G{r},0)", "0.00x")
    r += 1
last = r - 1
put(ws, r, 1, "合計 / 加重平均", font=B_FONT, fill=PatternFill("solid", fgColor="D9E1F2"))
put(ws, r, 2, "moviepy 6ch", font=B_FONT, fill=PatternFill("solid", fgColor="D9E1F2"))
for col, f in [(3, f"=SUM(C{first}:C{last})"), (4, f"=SUM(D{first}:D{last})"),
               (5, f"=IFERROR(D{r}/C{r},0)"), (6, f"=SUM(F{first}:F{last})"),
               (7, f"=IFERROR(F{r}*1000/D{r},0)"), (10, f"=SUM(J{first}:J{last})")]:
    cell = put(ws, r, col, f, "#,##0" if col in (3, 4, 5, 6, 10) else "0.000", B_FONT,
               PatternFill("solid", fgColor="D9E1F2"))
tot_row = r
tv = sum(cohort[c]["tv"] for c in CH_ORDER if c in cohort)
tl = sum(cohort[c]["tl"] for c in CH_ORDER if c in cohort)
put(ws, r, 8, tl * 100.0 / tv, "0.000", B_FONT, PatternFill("solid", fgColor="D9E1F2"))
rv = sum(recent[c]["tv"] for c in CH_ORDER if c in recent)
rs = sum(recent[c]["ts"] for c in CH_ORDER if c in recent)
put(ws, r, 11, rs * 1000.0 / rv, "0.000", B_FONT, PatternFill("solid", fgColor="D9E1F2"))
put(ws, r, 12, f"=IFERROR(K{r}/G{r},0)", "0.00x", B_FONT, PatternFill("solid", fgColor="D9E1F2"))
for col in (9,):
    put(ws, r, col, "", None, B_FONT, PatternFill("solid", fgColor="D9E1F2"))

r += 2
ws.cell(row=r, column=1, value="■ ブロッカー（指揮者では解消できない・人の作業が必要）").font = B_FONT
r += 1
head(ws, r, ["項目", "状態", "影響", "必要な作業", "期限感"], [26, 22, 46, 46, 16])
r += 1
for row in [
    ("カスタムサムネイル権限", "9ch で 403（未解決）",
     "daily-science 以外の全 ch で自作サムネが 1 枚も反映されていない（失敗 163 本 / 成功 21 本）。"
     "YouTube の自動抽出フレームがサムネになっている。",
     "各チャンネルで https://www.youtube.com/verify を開き電話番号確認を通す（9 ch 分）。反映まで最大24時間。",
     "最優先"),
    ("OAuth 同意画面が「テスト」", "未対応（再発リスク）",
     "テスト状態のリフレッシュトークンは 7 日で失効する。09-01/09-07/09-09 と 3 回再発している。",
     "GCP の OAuth 同意画面を「本番」に公開 → そのあと全 ch を再認可（順序が逆だと意味がない）。",
     "2026-09-20 前後に再発"),
    ("pokemon-lab の再認可", "未実施",
     "他 4ch は 09-13 に再認可済みだが pokemon-lab のトークンは 09-09 以降更新なし。公開は落ちたまま。",
     "管理画面 → チャンネル設定 → YouTube 連携 → 再認可。",
     "高"),
    ("analytics 同期", "最終 2026-09-13 13:40 UTC",
     "09-13 公開分 7 本は再生数 0 で記録されており、実績ではなく未計測。本日の集計から除外している。",
     "復旧後に backfill を流す。",
     "中"),
    ("autopilot 無効の 2ch", "2ch-matome / pokemon-lab",
     "生成が止まっている。指揮者は enabled を変更していない（人が落とした状態のため）。",
     "サムネ権限の解消後に有効化を判断。pokemon-lab は再認可が先。",
     "サムネ解消後"),
]:
    for i, v in enumerate(row, 1):
        c = put(ws, r, i, v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 2:
            c.fill, c.font = WARN_FILL, WARN_FONT
    ws.row_dimensions[r].height = 46
    r += 1

# ==================================================== 2. チャンネル別詳細
ws2 = wb.create_sheet("チャンネル別詳細")
ws2["A1"] = "チャンネル別詳細 — 本日のコンフィグ変更と根拠"
ws2["A1"].font = TITLE_FONT
changes = json.load(open(os.path.join(ROOT, "reports", "orch_config_changes_20260914.json"), encoding="utf-8"))
head(ws2, 3, ["チャンネル", "投稿枠(変更前)", "投稿枠(変更後)", "投稿枠の根拠",
               "目標タイトル型", "型ルール", "型の根拠", "キュー本数", "残日数", "autopilot"],
     [15, 22, 22, 52, 26, 52, 52, 10, 9, 11])
r = 4
for ch in CH_ORDER:
    v = changes[ch]
    slots = len(v["schedule_to"])
    put(ws2, r, 1, ch)
    put(ws2, r, 2, " / ".join(v["schedule_from"]))
    put(ws2, r, 3, " / ".join(v["schedule_to"]))
    put(ws2, r, 4, v["schedule_reason"])
    put(ws2, r, 5, v["target_type"])
    put(ws2, r, 6, v["type_rule"])
    put(ws2, r, 7, v["type_evidence"])
    put(ws2, r, 8, v["queue_len"], "#,##0")
    put(ws2, r, 9, f"=IFERROR(H{r}/{slots},0)", "0.0")
    c = put(ws2, r, 10, "有効" if v["autopilot_enabled"] else "無効")
    c.fill = GOOD_FILL if v["autopilot_enabled"] else WARN_FILL
    for i in range(1, 11):
        ws2.cell(row=r, column=i).alignment = Alignment(wrap_text=True, vertical="top")
    ws2.row_dimensions[r].height = 92
    r += 1
r += 1
ws2.cell(row=r, column=1, value="※ 残日数 = キュー本数 ÷ 1日あたりの投稿枠数。目標は 7 日分以上。").font = NOTE_FONT
r += 1
ws2.cell(row=r, column=1, value="※ autopilot.enabled は指揮者では変更していない。" + changes["_hold"]["hold_reason"]).font = NOTE_FONT
ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
ws2.row_dimensions[r].height = 60
ws2.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")

# ==================================================== 3. 動画別パフォーマンス
ws3 = wb.create_sheet("動画別パフォーマンス")
ws3["A1"] = "動画別パフォーマンス（公開 2026-08-20 以降・views>0）"
ws3["A1"].font = TITLE_FONT
ws3["A2"] = "型: A=疑問フレーム+数字 / B=疑問フレームのみ / C=数字のみ / D=共感・あるある"
ws3["A2"].font = NOTE_FONT
head(ws3, 4, ["チャンネル", "公開日", "投稿時刻(JST)", "型", "タイトル", "再生", "登録者",
               "登録/千再生", "高評価", "高評価率%", "コメント", "維持率%", "インプ", "CTR%"],
     [15, 11, 13, 6, 56, 9, 8, 12, 8, 11, 10, 10, 9, 8])


def typ(t):
    hq = bool(re.search(r"(なぜ|本当の理由|理由とは|理由$|正体|真相|どこに|とは？|のか|知ってる|わけ)", t))
    hn = bool(re.search(r"[0-9０-９]", t))
    return ("A" if hn else "B") if hq else ("C" if hn else "D")


vids = sorted(DATA["videos"], key=lambda v: (-(v["subscribers_gained"] * 1000.0 / v["views"]), -v["views"]))
r = 5
for v in vids:
    put(ws3, r, 1, v["channel_id"])
    put(ws3, r, 2, v["pub"])
    put(ws3, r, 3, f"{v['hour_jst']:02d}時")
    put(ws3, r, 4, typ(v["title"] or ""))
    put(ws3, r, 5, (v["title"] or "")[:80])
    put(ws3, r, 6, v["views"], "#,##0")
    put(ws3, r, 7, v["subscribers_gained"], "#,##0")
    c = put(ws3, r, 8, f"=IFERROR(G{r}*1000/F{r},0)", "0.00")
    if v["views"] and v["subscribers_gained"] * 1000.0 / v["views"] >= 1.5:
        c.fill = GOOD_FILL
    elif v["subscribers_gained"] == 0 and v["views"] >= 800:
        c.fill = WARN_FILL
    put(ws3, r, 9, v["likes"], "#,##0")
    put(ws3, r, 10, f"=IFERROR(I{r}*100/F{r},0)", "0.000")
    put(ws3, r, 11, v["comments"], "#,##0")
    put(ws3, r, 12, v["ret"] or 0, "0.0")
    put(ws3, r, 13, v["impressions"] or 0, "#,##0")
    put(ws3, r, 14, (v["ctr"] or 0) * 100, "0.00")
    r += 1
ws3.auto_filter.ref = f"A4:N{r-1}"
r += 1
ws3.cell(row=r, column=1, value="※ 緑=登録/千再生 1.5 以上 / 赤=800再生以上あるのに登録 0 人。"
                                "※ インプレッションとCTRは Shorts では大半が未計測のため参考値。").font = NOTE_FONT

# ==================================================== 4. 改善アクション
ws4 = wb.create_sheet("改善アクション")
ws4["A1"] = "改善アクション"
ws4["A1"].font = TITLE_FONT
head(ws4, 3, ["#", "優先", "対象", "アクション", "根拠（実測）", "実施状況", "期待効果", "検証日"],
     [5, 9, 16, 50, 56, 20, 32, 12])
acts = [
    (1, "最優先", "全9ch", "各チャンネルで youtube.com/verify から電話番号確認を通し、"
     "カスタムサムネイル権限を取得する。取得後に滞留分のサムネを貼り直す。",
     "バックエンドログ全体(84MB)を横断集計。サムネ設定成功=daily-science 21本のみ、"
     "失敗=他9ch 163本。全件 HTTP 403 'doesn't have permissions to upload and set custom video thumbnails'。",
     "★人の作業が必要（未実施）", "サムネ改善施策が初めて視聴者に届く。CTR経由で再生・登録の双方に効く。", "2026-09-21"),
    (2, "最優先", "GCP", "OAuth 同意画面を「テスト」→「本番」に公開し、そのあと全 ch を再認可する。",
     "テスト状態のリフレッシュトークンは 7 日で失効。09-01/09-07/09-09 と 3 回全 ch 同時に落ちている。",
     "★人の作業が必要（未実施）", "7日周期の全停止が止まる。前回の逸失は5日で約77,300再生・登録38人相当。", "2026-09-20"),
    (3, "高", "2ch-matome", "タイトルを「なぜ／本当の理由＋具体数字」の A 型に統一。"
     "大喜利・参加型・共感あるある型は先頭に置かない。下ネタ・面白ジャンルは維持（変えるのは型）。",
     "A型 0.36(n=16) に対し C型 0.07(n=16)・D型 0.09(n=10)。A型は他型の4〜5倍。"
     "再生上位5本（1,236〜1,815再生・維持率41.9〜81.4%）はすべて共感型で登録0人。",
     "✅ 本日適用（キュー再配置＋5件補充）", "当ch 登録/千 0.184 → 0.35 前後", "2026-09-21"),
    (4, "高", "yokai-watch", "タイトルから数字を完全に排除し、疑問フレームのみの B 型に統一する。",
     "B型 1.37(n=9) > D型 0.53(n=8) > C型 0.39(n=8) > A型 0.00(n=5)。数字を入れた瞬間に登録がゼロになる。",
     "✅ 本日適用（型ルール設定・キュー全23件がB型）", "直近14日 1.202 の水準を維持・上積み", "2026-09-21"),
    (5, "高", "pokemon-lab", "数値提示（C型）を最優先に据え、「なぜ〜？」の疑問フレームは当chでは使わない。",
     "C型 0.53(n=9) > B型 0.35(n=6) > A型 0.17(n=16)。09-13 の『数値提示型 0.429 vs 対決型 0.191』とも整合し2回目の再現。",
     "✅ 本日適用（キューをC型先頭へ再配置）", "0.277 → 0.45 前後（直近14日は既に 0.467）", "2026-09-21"),
    (6, "高", "scp-lab", "SCP番号・具体数字と『なぜ〜のか』を併用する A 型を先頭に置く。",
     "A型 1.00(n=25) > C型 0.49(n=26)。A型は2.0倍。",
     "✅ 本日適用（キューをA型先頭へ再配置）", "0.831 → 1.0 前後", "2026-09-21"),
    (7, "中", "2ch-matome", "投稿枠 9:00 / 21:00 を廃止し、7:30 / 12:15 / 17:30 へ移す。",
     "21時枠は n=7・3,430再生で登録0人、9時枠も n=3 で登録0人。7時 0.339 / 17時 0.279 / 12時 0.204。",
     "✅ 本日適用", "死に枠の除去で当chの登録/千が底上げされる", "2026-09-21"),
    (8, "中", "daily-science", "投稿枠 12:30 を 15:00 へ前倒しし、夕方ピークに寄せる。",
     "17時 1.236(n=14) vs 12時 0.180(n=6)。6.9倍の差。",
     "✅ 本日適用", "1枠あたりの登録変換が改善", "2026-09-21"),
    (9, "中", "scp-lab / company-facts / pokemon-lab",
     "朝枠（9:00 / 8:15 / 8:30）を廃止し、実測最良の 17 時前後へ集約する。",
     "scp-lab 9時 0.520 vs 17時 1.321 / company-facts 8時 0.235 vs 17時 0.824 / "
     "pokemon-lab 17時 0.369 が当ch最良。朝枠はいずれも下位かサンプル不足。",
     "✅ 本日適用", "3ch とも1枠あたりの登録変換が改善", "2026-09-21"),
    (10, "中", "全6ch", "テーマキューを 7 日分以上に維持する（本日 daily-science 21 / company-facts 28 / 2ch-matome 21）。",
     "枯渇すると型ルールの効かない即席テーマで埋まるため。",
     "✅ 本日適用（計14件補充）", "型ルールの適用率が保たれる", "継続"),
    (11, "保留", "2ch-matome / pokemon-lab", "autopilot.enabled を true に戻すかを判断する。",
     "現在 false。指揮者の分析の外側で人が落とした状態であり、本日のデータはこの値を動かす根拠にならない。"
     "さらにサムネ権限が未解決のまま生成を増やすと、自動生成サムネの動画が増えるだけになる。",
     "⏸ 保留（サムネ権限の解消後に再判断）", "—", "サムネ解消後"),
]
r = 4
for a_ in acts:
    for i, v in enumerate(a_, 1):
        c = put(ws4, r, i, v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 2:
            c.fill = WARN_FILL if v in ("最優先", "高") else PatternFill("solid", fgColor="FFEB9C")
            c.font = B_FONT
        if i == 6:
            c.fill = GOOD_FILL if str(v).startswith("✅") else WARN_FILL
    ws4.row_dimensions[r].height = 62
    r += 1

# ==================================================== 5. トレンド
ws5 = wb.create_sheet("トレンド")
ws5["A1"] = "トレンド"
ws5["A1"].font = TITLE_FONT
ws5.cell(row=3, column=1, value="■ 投稿時刻（JST）× 登録/千再生 — 公開 2026-08-15 以降・n>=3 の枠のみ").font = B_FONT
head(ws5, 4, ["チャンネル", "時刻(JST)", "本数", "総再生", "登録者", "登録/千再生", "判定"],
     [15, 11, 7, 10, 8, 13, 24])
r = 5
best = {}
for h in DATA["hours"]:
    k = h["ch"]
    v = h["ts"] * 1000.0 / h["tv"] if h["tv"] else 0
    best[k] = max(best.get(k, 0), v)
for h in sorted(DATA["hours"], key=lambda x: (x["ch"], -(x["ts"] * 1000.0 / x["tv"] if x["tv"] else 0))):
    v = h["ts"] * 1000.0 / h["tv"] if h["tv"] else 0
    put(ws5, r, 1, h["ch"])
    put(ws5, r, 2, f"{h['h']:02d}時")
    put(ws5, r, 3, h["n"], "#,##0")
    put(ws5, r, 4, h["tv"], "#,##0")
    put(ws5, r, 5, h["ts"], "#,##0")
    c = put(ws5, r, 6, f"=IFERROR(E{r}*1000/D{r},0)", "0.000")
    if v >= best[h["ch"]] * 0.85 and v > 0:
        c.fill = GOOD_FILL
        put(ws5, r, 7, "当ch最良帯")
    elif v == 0:
        c.fill = WARN_FILL
        put(ws5, r, 7, "登録ゼロ — 枠を潰した")
    else:
        put(ws5, r, 7, "")
    r += 1

r += 2
ws5.cell(row=r, column=1, value="■ 日次トレンド（公開日ベース・moviepy 6ch 合計）").font = B_FONT
r += 1
head(ws5, r, ["公開日", "本数", "総再生", "登録者", "登録/千再生", "備考"], [12, 8, 11, 9, 13, 44])
r += 1
for d in DATA["daily"]:
    put(ws5, r, 1, d["d"])
    put(ws5, r, 2, d["n"], "#,##0")
    put(ws5, r, 3, d["tv"], "#,##0")
    put(ws5, r, 4, d["ts"], "#,##0")
    put(ws5, r, 5, f"=IFERROR(D{r}*1000/C{r},0)", "0.000")
    note = ""
    if d["d"] >= "2026-09-10" and d["n"] == 0:
        note = "OAuth 失効で公開ゼロ"
    elif d["d"] == "2026-09-13":
        note = "OAuth 復旧・公開再開（再生数は未計測）"
        put(ws5, r, 6, note, None, WARN_FONT, WARN_FILL)
        r += 1
        continue
    elif d["d"] >= "2026-09-09":
        note = "OAuth 失効期間"
    put(ws5, r, 6, note)
    r += 1
for gap in ["2026-09-10", "2026-09-11", "2026-09-12"]:
    put(ws5, r, 1, gap)
    put(ws5, r, 2, 0, "#,##0")
    put(ws5, r, 3, 0, "#,##0")
    put(ws5, r, 4, 0, "#,##0")
    put(ws5, r, 5, 0, "0.000")
    put(ws5, r, 6, "OAuth 失効で公開ゼロ（生成は継続）", None, WARN_FONT, WARN_FILL)
    r += 1

r += 2
ws5.cell(row=r, column=1, value="■ タイトル型 × 登録/千再生（公開 2026-08-01 以降・views>=200・ch内対照）").font = B_FONT
r += 1
head(ws5, r, ["チャンネル", "A 疑問+数字", "B 疑問のみ", "C 数字のみ", "D 共感/あるある", "最良型", "本日の対応"],
     [15, 16, 15, 15, 18, 16, 40])
r += 1
TYPE_TABLE = [
    ("scp-lab", "1.00 (n=25)", "—", "0.49 (n=26)", "—", "A", "A型を先頭へ再配置"),
    ("yokai-watch", "0.00 (n=5)", "1.37 (n=9)", "0.39 (n=8)", "0.53 (n=8)", "B", "タイトルから数字を排除"),
    ("daily-science", "0.59 (n=30)", "—", "0.00 (n=3)", "—", "A", "現行が最良のため維持"),
    ("company-facts", "0.55 (n=4)", "—", "0.66 (n=31)", "—", "C", "現行が最良のため維持"),
    ("pokemon-lab", "0.17 (n=16)", "0.35 (n=6)", "0.53 (n=9)", "—", "C", "C型を先頭へ・疑問フレーム不使用"),
    ("2ch-matome", "0.36 (n=16)", "—", "0.07 (n=16)", "0.09 (n=10)", "A", "A型を先頭へ・5件補充"),
]
for row in TYPE_TABLE:
    for i, v in enumerate(row, 1):
        c = put(ws5, r, i, v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 6:
            c.fill, c.font = GOOD_FILL, B_FONT
    r += 1
r += 1
ws5.cell(row=r, column=1, value="※ 型の効き方はチャンネルごとに逆向きになる。"
         "yokai-watch は数字を入れると登録が消え、pokemon-lab は逆に数字だけが効く。"
         "全ch共通の型ルールは存在しない。").font = NOTE_FONT
ws5.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
ws5.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
ws5.row_dimensions[r].height = 32

for s in wb.worksheets:
    for row in s.iter_rows():
        for c in row:
            if c.font is None or c.font.name is None:
                c.font = T_FONT

wb.save(OUT)
print("saved:", OUT)
