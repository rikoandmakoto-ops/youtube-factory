#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-11 指揮者レポート (xlsx) 生成."""
import sqlite3, json, os, sys, re, statistics as st
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "analytics", "analytics.db")
OUT = os.path.join(ROOT, "reports", "youtube_analysis_20260911.xlsx")

YK = ["scp-lab", "daily-science", "yokai-watch", "pokemon-lab", "2ch-matome", "company-facts"]
NAMES = {
    "daily-science": "リコとマコトのゆっくり日常科学", "scp-lab": "異常存在SCPゆっくり解説ラボ",
    "2ch-matome": "ゆっくり2chスレまとめ劇場", "pokemon-lab": "ゆっくりポケラボ",
    "yokai-watch": "ゆっくり妖怪ラボ", "company-facts": "企業のホンネ",
    "clip-lab": "切り抜きLab", "akashic-librarian": "アカシックの司書",
    "clip-fukada": "深田えいみ 切り抜き", "clip-kaneko": "金子みゆ 切り抜き",
    "clip-animal": "動物情報局", "fake-paper": "虚構論文チャンネル", "socio-rx": "社会学の処方箋",
}

con = sqlite3.connect(DB); con.row_factory = sqlite3.Row

# ---------- 成熟コホート（公開 08-10〜09-04, 主指標 = 登録/千再生） ----------
MAT_Q = """
select v.channel_id, v.video_id, v.title, substr(v.published_at,1,10) pub,
       v.views, v.likes, v.comments, v.subscribers_gained subs,
       v.avg_view_percentage avp, v.avg_view_duration avd
from video_metrics v
join (select video_id, max(date) d from video_metrics group by video_id) m
  on v.video_id = m.video_id and v.date = m.d
where v.published_at >= ? and v.published_at < ? and v.views > 0
"""
mature = [dict(r) for r in con.execute(MAT_Q, ("2026-08-10", "2026-09-05"))]
recent = [dict(r) for r in con.execute(MAT_Q, ("2026-09-05", "2026-09-12"))]


def s1k(rows):
    tv = sum(r["views"] for r in rows) or 1
    return 1000 * sum(r["subs"] for r in rows) / tv


# ---------- 到達 CTR ----------
ctr = {r["channel_id"]: (r["imp"], r["clk"], r["pct"]) for r in con.execute("""
 select channel_id, sum(impressions) imp, sum(clicks) clk,
        round(100.0*sum(clicks)/nullif(sum(impressions),0),2) pct
 from video_reach_daily where date>='2026-09-01' group by channel_id""")}

# ---------- 登録純増 ----------
netsub = {r["channel_id"]: (r["g"], r["l"], r["net"]) for r in con.execute("""
 select channel_id, sum(subscribers_gained) g, sum(subscribers_lost) l,
        sum(subscribers_gained)-sum(subscribers_lost) net
 from channel_metrics where date>='2026-08-30' group by channel_id""")}

# ---------- 投稿本数 ----------
pub = sqlite3.connect(os.path.join(ROOT, "data", "video_publish.db"))
pub_by_day = defaultdict(int); pub_by_ch_day = defaultdict(int)
for d, ch, n in pub.execute("""select substr(published_at,1,10) d, channel_id, count(*)
        from video_status where published_at is not null and published_at>='2026-08-28'
        group by d, channel_id"""):
    pub_by_day[d] += n; pub_by_ch_day[(ch, d)] = n

# ---------- 維持率カーブ ----------
curves = defaultdict(list)
for r in con.execute("select channel_id, curve from retention_curve"):
    try:
        pts = json.loads(r["curve"])
    except Exception:
        continue
    if isinstance(pts, list) and pts:
        curves[r["channel_id"]].append({round(p["ratio"], 2): p.get("audience_watch_ratio")
                                        for p in pts if "ratio" in p})
MARKS = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 0.70, 0.90, 1.00]


def curve_row(ch):
    ds = curves.get(ch, [])
    out = []
    for m in MARKS:
        v = [d[m] for d in ds if d.get(m) is not None]
        out.append(round(st.mean(v) * 100, 1) if v else None)
    return len(ds), out


# ---------- タイトル型のch内対照 ----------
def seg(ch, pred):
    rs = [r for r in mature if r["channel_id"] == ch]
    a = [r for r in rs if pred(r)]; b = [r for r in rs if not pred(r)]
    if len(a) < 3 or len(b) < 3:
        return None
    return (len(a), round(s1k(a), 2), len(b), round(s1k(b), 2))


EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿️]")
MK = ["正体", "真相", "理由", "裏側", "仕組み", "原因", "本当は", "実は", "答え"]
PATTERNS = [
    ("「なぜ」疑問形", lambda r: "なぜ" in r["title"]),
    ("絵文字あり", lambda r: bool(EMOJI.search(r["title"]))),
    ("二人称(君/あなた)", lambda r: any(w in r["title"] for w in ["君", "あなた", "きみ"])),
    ("答え提示語", lambda r: any(w in r["title"] for w in MK)),
]

data = {
    "mature": mature, "recent": recent, "ctr": ctr, "netsub": netsub,
    "pub_by_day": dict(pub_by_day), "pub_by_ch_day": {f"{k[0]}|{k[1]}": v for k, v in pub_by_ch_day.items()},
}

# =====================================================================
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
H_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
T_FONT = Font(name=FONT, bold=True, size=14)
B_FONT = Font(name=FONT, size=10)
WARN = PatternFill("solid", fgColor="FFC7CE")
GOOD = PatternFill("solid", fgColor="C6EFCE")
MID = PatternFill("solid", fgColor="FFEB9C")
THIN = Border(*[Side(style="thin", color="BFBFBF")] * 4)

wb = openpyxl.Workbook()


def head(ws, row, cols, widths=None):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.fill = H_FILL; cell.font = H_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def body(ws, r0, rows, numfmt=None):
    for ri, row in enumerate(rows):
        for ci, v in enumerate(row, 1):
            c = ws.cell(row=r0 + ri, column=ci, value=v)
            c.font = B_FONT; c.border = THIN
            if numfmt and ci in numfmt:
                c.number_format = numfmt[ci]
    return r0 + len(rows)


# ---------------- 1. サマリー ----------------
ws = wb.active; ws.title = "サマリー"
ws["A1"] = "YouTube Factory 指揮者レポート 2026-09-11"; ws["A1"].font = T_FONT
ws["A2"] = ("データ範囲: analytics.db の最終取得は 2026-09-08 23:19 JST（以降 2日以上更新なし）。"
            "成熟コホート = 公開 2026-08-10〜09-04・4日以上経過。主指標 = 登録者/千再生。")
ws["A2"].font = Font(name=FONT, size=9, italic=True)
ws.merge_cells("A2:H2"); ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
ws.row_dimensions[2].height = 28

ws["A4"] = "■ 最重要: 全13chの YouTube OAuth が失効し、投稿が実質停止している"
ws["A4"].font = Font(name=FONT, bold=True, size=12, color="9C0006")
head(ws, 5, ["日付", "全ch合計 投稿本数", "状態"], [14, 20, 62])
pub_rows = []
for d in sorted(pub_by_day):
    n = pub_by_day[d]
    if d >= "2026-09-09" and n < 5:
        state = "停止（OAuth invalid_grant によりアップロード失敗）"
    elif n >= 15:
        state = "正常"
    elif n >= 5:
        state = "低下"
    else:
        state = "低下（要因未特定。当日のログは別途確認）"
    pub_rows.append([d, n, state])
r = body(ws, 6, pub_rows, {2: "0"})
for i in range(6, r):
    if ws.cell(row=i, column=2).value < 5:
        for c in range(1, 4):
            ws.cell(row=i, column=c).fill = WARN
ws.cell(row=r, column=1, value="合計").font = Font(name=FONT, bold=True)
ws.cell(row=r, column=2, value=f"=SUM(B6:B{r-1})").font = Font(name=FONT, bold=True)

r += 2
ws.cell(row=r, column=1, value="■ チャンネル別サマリー（成熟コホート）").font = Font(name=FONT, bold=True, size=12)
r += 1
head(ws, r, ["channel_id", "チャンネル名", "本数", "中央値 再生", "登録/千再生",
             "平均 維持率%", "到達CTR%", "登録 純増(7日)", "評価"],
     [18, 30, 8, 12, 13, 13, 11, 14, 34])
rows = []
for ch in YK + ["clip-lab", "clip-fukada", "clip-kaneko", "akashic-librarian", "fake-paper", "clip-animal"]:
    rs = [x for x in mature if x["channel_id"] == ch]
    if not rs:
        continue
    v = s1k(rs)
    ev = ("最優先で伸ばす" if v >= 0.8 else "維持" if v >= 0.5 else
          "要改善" if v >= 0.25 else "抜本見直し")
    rows.append([ch, NAMES.get(ch, ch), len(rs), st.median([x["views"] for x in rs]),
                 round(v, 2), round(st.mean([x["avp"] for x in rs]), 1),
                 ctr.get(ch, (0, 0, None))[2], netsub.get(ch, (0, 0, None))[2], ev])
rows.sort(key=lambda x: -(x[4] or 0))
r2 = body(ws, r + 1, rows, {4: "#,##0", 5: "0.00", 6: "0.0", 7: "0.00", 8: "0"})
for i in range(r + 1, r2):
    val = ws.cell(row=i, column=5).value
    ws.cell(row=i, column=9).fill = GOOD if val >= 0.8 else MID if val >= 0.5 else WARN

r = r2 + 2
ws.cell(row=r, column=1, value="■ 本日の主要所見").font = Font(name=FONT, bold=True, size=12)
findings = [
 ["1", "全13chで OAuth refresh が invalid_grant。09-09 以降の公開は 2本/日（09-05〜09-08 は 21〜33本/日）。生成は動いているがアップロードが全滅。",
  "管理UIから全ch再認可。最優先。"],
 ["2", "絵文字入りタイトルは 5/6ch で登録効率が悪化（scp-lab 0.32 vs 0.98、yokai-watch 0.19 vs 0.46、2ch-matome 0.00 vs 0.27）。title_rules.max_emoji=0 は backend が読まないキーだった。",
  "hard_constraints へ移設済（本日反映）。"],
 ["3", "「なぜ〇〇なのか」型が 4ch で最大レバー（scp-lab 1.45 vs 0.45 / yokai-watch 0.66 vs 0.20 / daily-science 0.56 vs 0.27 / 2ch-matome 0.33 vs 0.18）。",
  "4chの title_style を「なぜ」最優先へ更新済。"],
 ["4", "pokemon-lab のみ逆パターン。「なぜ」0.00(n=9) に対し二人称(君/あなた) 0.45 vs 0.15。08-25 以降 0.26→0.20 と6ch中唯一悪化、到達CTR 0.69% も最下位。",
  "二人称主軸へ方針変更＋枯渇していた theme_queue に20本補充。"],
 ["5", "維持率は全252本平均で 15%地点102% → 20%地点84% → 30%地点63% と中盤で崖。尺は 09-12 まで実験ロック中のため構成で手当て。",
  "short_format.extra_rules に3行目の反転必須ルールを追加。"],
 ["6", "theme_queue 142本中 54本が hard_constraints を通らず、backend の機械修復で語尾に「の正体」等が付く状態だった。",
  "54本を実測で効く型に書き直し、全ch NG 0 本に。"],
]
head(ws, r + 1, ["#", "所見", "本日の対応"], [5, 96, 44])
body(ws, r + 2, findings)
for i in range(r + 2, r + 2 + len(findings)):
    ws.cell(row=i, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=i, column=3).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[i].height = 46
ws.cell(row=r + 2, column=1).fill = WARN

# ---------------- 2. チャンネル別詳細 ----------------
ws = wb.create_sheet("チャンネル別詳細")
ws["A1"] = "チャンネル別詳細（成熟コホート 2026-08-10〜09-04）"; ws["A1"].font = T_FONT
head(ws, 3, ["channel_id", "チャンネル名", "本数", "総再生", "中央値", "登録数",
             "登録/千再生", "高評価率%", "コメント率%", "平均 維持率%", "平均 視聴秒",
             "到達 表示回数", "到達 CTR%", "theme_queue 本数"],
     [18, 28, 7, 11, 10, 8, 12, 11, 12, 12, 11, 13, 11, 15])
qlen = {}
for ch in YK:
    try:
        qlen[ch] = len(json.load(open(os.path.join(ROOT, "data", "channels", f"{ch}.json"),
                                     encoding="utf-8")).get("autopilot", {}).get("theme_queue", []))
    except Exception:
        qlen[ch] = None
rows = []
for ch in sorted({x["channel_id"] for x in mature}):
    rs = [x for x in mature if x["channel_id"] == ch]
    tv = sum(x["views"] for x in rs)
    rows.append([ch, NAMES.get(ch, ch), len(rs), tv, st.median([x["views"] for x in rs]),
                 sum(x["subs"] for x in rs), round(s1k(rs), 2),
                 round(100 * sum(x["likes"] for x in rs) / max(tv, 1), 2),
                 round(100 * sum(x["comments"] for x in rs) / max(tv, 1), 3),
                 round(st.mean([x["avp"] for x in rs]), 1),
                 round(st.mean([x["avd"] for x in rs]), 1),
                 ctr.get(ch, (0, 0, 0))[0], ctr.get(ch, (0, 0, None))[2], qlen.get(ch)])
rows.sort(key=lambda x: -x[6])
r = body(ws, 4, rows, {4: "#,##0", 5: "#,##0", 7: "0.00", 8: "0.00", 9: "0.000",
                       10: "0.0", 11: "0.0", 12: "#,##0", 13: "0.00", 14: "0"})
ws.cell(row=r, column=1, value="合計/平均").font = Font(name=FONT, bold=True)
for col, f in [(3, "SUM"), (4, "SUM"), (6, "SUM"), (10, "AVERAGE"), (11, "AVERAGE"), (12, "SUM")]:
    L = get_column_letter(col)
    c = ws.cell(row=r, column=col, value=f"={f}({L}4:{L}{r-1})")
    c.font = Font(name=FONT, bold=True); c.number_format = "#,##0.0" if f == "AVERAGE" else "#,##0"
ws.cell(row=r, column=7, value=f"=IF(D{r}=0,0,1000*F{r}/D{r})").font = Font(name=FONT, bold=True)
ws.cell(row=r, column=7).number_format = "0.00"

r += 2
ws.cell(row=r, column=1, value="■ 平均 視聴維持率カーブ（%・retention_curve）").font = Font(name=FONT, bold=True, size=12)
head(ws, r + 1, ["channel_id", "本数"] + [f"{int(m*100)}%地点" for m in MARKS], [18, 7] + [11] * len(MARKS))
crows = []
for ch in sorted(curves):
    n, vals = curve_row(ch)
    if n >= 3:
        crows.append([ch, n] + vals)
r2 = body(ws, r + 2, crows, {i: "0.0" for i in range(3, 3 + len(MARKS))})
for i in range(r + 2, r2):
    v15, v30 = ws.cell(row=i, column=5).value, ws.cell(row=i, column=7).value
    if v15 and v30:
        drop = v15 - v30
        ws.cell(row=i, column=7).fill = WARN if drop >= 38 else MID if drop >= 30 else GOOD
ws.cell(row=r2 + 1, column=1,
        value="※ 15%→30% の落差が 38pt 以上を赤、30pt 以上を黄。全体平均は 15%地点102% → 30%地点63%。"
        ).font = Font(name=FONT, size=9, italic=True)

# ---------------- 3. 動画別パフォーマンス ----------------
ws = wb.create_sheet("動画別パフォーマンス")
ws["A1"] = "動画別パフォーマンス"; ws["A1"].font = T_FONT
ws["A3"] = "■ 登録獲得 効率トップ30（成熟コホート・再生200以上）"; ws["A3"].font = Font(name=FONT, bold=True, size=12)
head(ws, 4, ["channel_id", "公開日", "タイトル", "再生", "登録", "登録/千再生", "維持率%", "視聴秒", "高評価"],
     [16, 11, 62, 9, 7, 12, 10, 9, 8])
top = sorted([x for x in mature if x["views"] >= 200], key=lambda x: -1000 * x["subs"] / x["views"])[:30]
body(ws, 5, [[x["channel_id"], x["pub"], x["title"], x["views"], x["subs"],
              round(1000 * x["subs"] / x["views"], 2), x["avp"], x["avd"], x["likes"]] for x in top],
     {4: "#,##0", 6: "0.00", 7: "0.0", 8: "0.0"})

r = 5 + len(top) + 2
ws.cell(row=r, column=1, value="■ 再生は出たが登録0（再生700以上・改善余地が最大の層）").font = Font(name=FONT, bold=True, size=12)
head(ws, r + 1, ["channel_id", "公開日", "タイトル", "再生", "維持率%", "視聴秒", "想定要因"],
     [16, 11, 62, 9, 10, 9, 34])
zero = sorted([x for x in mature if x["views"] >= 700 and x["subs"] == 0], key=lambda x: -x["views"])[:25]
zrows = []
for x in zero:
    if x["avp"] >= 60:
        why = "最後まで見られているのにCTAが弱い"
    elif x["avp"] < 35:
        why = "中盤で離脱。フック/3行目の反転が不足"
    else:
        why = "題材は届いたがch固有の価値が伝わっていない"
    zrows.append([x["channel_id"], x["pub"], x["title"], x["views"], x["avp"], x["avd"], why])
body(ws, r + 2, zrows, {4: "#,##0", 5: "0.0", 6: "0.0"})

r = r + 2 + len(zrows) + 2
ws.cell(row=r, column=1, value="■ 直近投稿（09-05以降・Analytics 2〜3日遅延のため参考値）").font = Font(name=FONT, bold=True, size=12)
head(ws, r + 1, ["channel_id", "公開日", "タイトル", "再生", "登録", "維持率%"], [16, 11, 62, 9, 7, 10])
body(ws, r + 2, [[x["channel_id"], x["pub"], x["title"], x["views"], x["subs"], x["avp"]]
                 for x in sorted(recent, key=lambda x: (x["channel_id"], x["pub"]))],
     {4: "#,##0", 6: "0.0"})

# ---------------- 4. 改善アクション ----------------
ws = wb.create_sheet("改善アクション")
ws["A1"] = "改善アクション 2026-09-11"; ws["A1"].font = T_FONT
head(ws, 3, ["優先", "対象", "課題（実データ）", "アクション", "実装状況", "検証方法", "評価日"],
     [6, 16, 60, 56, 22, 40, 12])
acts = [
 ["S", "全13ch", "OAuth refresh が invalid_grant。09-09/09-10 の公開は各2本のみ（09-05〜09-08 は 21〜33本/日）。生成は成功しアップロードだけ失敗している。",
  "管理UIの「YouTubeと連携する」から全chを再認可する。指揮者側では実行不可。",
  "未対応（要ユーザー操作）", "backend.log の『refresh 失敗』が消え、日次公開が15本以上に戻ること", "2026-09-12"],
 ["A", "pokemon-lab", "theme_queue が 0 本で枯渇。08-25以降 登録/千再生 0.26→0.20 と6ch中唯一悪化、到達CTR 0.69% も最下位。",
  "実測で効く二人称型（0.45 vs 0.15）でテーマ20本を補充。title_style を二人称主軸・「なぜ」回避へ変更。",
  "反映済", "補充テーマ由来の動画の 登録/千再生 が 0.20 を上回るか", "2026-09-18"],
 ["A", "全6ch", "絵文字入りタイトルが 5/6ch で悪化（scp-lab 0.32 vs 0.98）。max_emoji=0 は backend が読まないキーで 09-08 まで毎日1〜2本流出していた。",
  "hard_constraints.forbid_patterns に絵文字正規表現、banned_words に流出実績のある18字を追加。検知＋機械修復の両方を有効化。",
  "反映済・検証済", "公開タイトルの絵文字率が 0% を維持すること", "2026-09-14"],
 ["A", "scp-lab / yokai-watch / daily-science / 2ch-matome", "「なぜ〇〇なのか」型の登録効率が非該当の1.8〜3.2倍（scp-lab 1.45 vs 0.45）。一方 09-08 に全chへ入れた答え提示語は単独では効果が確認できない。",
  "theme_priority.title_style の先頭に『なぜ型を第一候補』を明記。答え提示語は併用条件として残す。",
  "反映済", "「なぜ」型の比率と、ch内対照の 登録/千再生 の差", "2026-09-18"],
 ["A", "scp-lab / yokai-watch / company-facts / 2ch-matome", "theme_queue 142本中54本が hard_constraints 不通過。backend の repair() が語尾に『の正体』等を機械追加する状態だった。",
  "54本を実測型に書き直し（scp/yokai は なぜ型、company-facts は 理由・実態・裏側型、2ch は ワイ除去）。全件をゲートで事前検証。",
  "反映済・検証済（NG 0/142）", "repair() 発動回数が 0 に近づくこと", "2026-09-14"],
 ["B", "全6ch", "維持率は 15%地点102% → 20%地点84% → 30%地点63% と中盤で崖。特に 2ch-matome（89→53）と scp-lab（100→59）。",
  "short_format.extra_rules に『3行目に必ず前提を覆す一言か具体数字を置く／説明を2行続けない』を追加。尺は 09-12 の実験ロックを順守し変更しない。",
  "反映済", "20%・30%地点の維持率が各+5pt改善するか", "2026-09-20"],
 ["B", "pokemon-lab / scp-lab / yokai-watch", "到達CTR が 0.69% / 1.30% / 1.39% と低位（company-facts 2.62%・clip-fukada 4.31% と比べ半分以下）。",
  "サムネ品質を次サイクルの最優先枠にする。company-facts のサムネ構成（数字を大きく1つだけ／人物なし）を3chへ横展開する案を次回検証。",
  "次サイクルで着手", "video_reach_daily の ch別 CTR", "2026-09-18"],
 ["C", "指揮者基盤", "analytics.db の最終取得が 2026-09-08 23:19 で 2日以上停止。09-09 以降の実績が評価できない。",
  "OAuth 再認可と同時に Analytics 取得ジョブを手動で1回走らせ、欠測日を埋める。",
  "未対応（OAuth待ち）", "video_metrics に 09-09 以降の行が入ること", "2026-09-12"],
]
r = body(ws, 4, acts)
for i in range(4, r):
    for c in (3, 4, 6):
        ws.cell(row=i, column=c).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[i].height = 62
    pr = ws.cell(row=i, column=1)
    pr.fill = WARN if pr.value == "S" else MID if pr.value == "A" else GOOD
    pr.alignment = Alignment(horizontal="center", vertical="center")

# ---------------- 5. トレンド ----------------
ws = wb.create_sheet("トレンド")
ws["A1"] = "トレンド"; ws["A1"].font = T_FONT
ws["A3"] = "■ 施策前後の比較（前期 08-10〜08-24 / 後期 08-25〜09-04・登録/千再生）"
ws["A3"].font = Font(name=FONT, bold=True, size=12)
head(ws, 4, ["channel_id", "前期 本数", "前期 登録/千", "後期 本数", "後期 登録/千", "変化", "中央値 再生 前期→後期"],
     [18, 11, 14, 11, 14, 10, 24])
rows = []
for ch in YK:
    a = [x for x in mature if x["channel_id"] == ch and x["pub"] < "2026-08-25"]
    b = [x for x in mature if x["channel_id"] == ch and x["pub"] >= "2026-08-25"]
    if not a or not b:
        continue
    rows.append([ch, len(a), round(s1k(a), 2), len(b), round(s1k(b), 2),
                 round(s1k(b) - s1k(a), 2),
                 f"{st.median([x['views'] for x in a]):.0f} → {st.median([x['views'] for x in b]):.0f}"])
rows.sort(key=lambda x: -x[5])
r = body(ws, 5, rows, {3: "0.00", 5: "0.00", 6: "+0.00;-0.00;0.00"})
for i in range(5, r):
    ws.cell(row=i, column=6).fill = GOOD if ws.cell(row=i, column=6).value > 0 else WARN

r += 2
ws.cell(row=r, column=1, value="■ タイトル型 × チャンネル内対照（登録/千再生・成熟コホート）").font = Font(name=FONT, bold=True, size=12)
head(ws, r + 1, ["型", "channel_id", "該当 本数", "該当 登録/千", "非該当 本数", "非該当 登録/千", "差", "判定"],
     [20, 18, 11, 14, 12, 15, 9, 16])
prows = []
for label, pred in PATTERNS:
    for ch in YK:
        s = seg(ch, pred)
        if s:
            diff = round(s[1] - s[3], 2)
            prows.append([label, ch, s[0], s[1], s[2], s[3], diff,
                          "採用" if diff > 0.1 else "不採用" if diff < -0.1 else "差なし"])
r2 = body(ws, r + 2, prows, {4: "0.00", 6: "0.00", 7: "+0.00;-0.00;0.00"})
for i in range(r + 2, r2):
    v = ws.cell(row=i, column=8).value
    ws.cell(row=i, column=8).fill = GOOD if v == "採用" else WARN if v == "不採用" else MID

r = r2 + 2
ws.cell(row=r, column=1, value="■ 日次 公開本数の推移（video_publish.db）").font = Font(name=FONT, bold=True, size=12)
head(ws, r + 1, ["日付"] + YK + ["合計"], [12] + [16] * len(YK) + [10])
drows = []
for d in sorted({k.split("|")[1] for k in data["pub_by_ch_day"]}):
    row = [d] + [data["pub_by_ch_day"].get(f"{ch}|{d}", 0) for ch in YK]
    drows.append(row + [sum(row[1:])])
r3 = body(ws, r + 2, drows, {i: "0" for i in range(2, len(YK) + 3)})
for i in range(r + 2, r3):
    if ws.cell(row=i, column=len(YK) + 2).value <= 4:
        for c in range(1, len(YK) + 3):
            ws.cell(row=i, column=c).fill = WARN
ws.cell(row=r3 + 1, column=1,
        value="※ 赤 = 合計4本以下。09-09 以降の落ち込みは OAuth 失効による公開失敗（生成自体は継続している）。"
        ).font = Font(name=FONT, size=9, italic=True)

for s in wb.worksheets:
    s.sheet_view.showGridLines = False

os.makedirs(os.path.dirname(OUT), exist_ok=True)
wb.save(OUT)
print("saved:", OUT)
json.dump({"generated": "2026-09-11"}, open(os.path.join(ROOT, "reports", "youtube_analysis_20260911.json"), "w"))
