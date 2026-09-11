#!/usr/bin/env python3
"""2026-09-11 指揮者レポート xlsx を作る。

データ元: data/analytics/analytics.db
  - 9ch は 09-08 スナップショット / fake-paper・akashic-librarian は 09-06
  - 09-09 以降は analytics 取得が停止しており新規行がゼロ（レポート内に明記）
"""

import os
import re
import sqlite3
import sys
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inject_cached_values import FormulaCache  # noqa: E402

# 実効文字数は backend のゲートと**同じ実装**を使う。ここで別実装を持つと、
# レポートの数字と実際にゲートが弾く基準がずれる（2026-09-11 の検証で
# レポート側の簡易版が本文を巻き込んでいたのが見つかった）。
sys.path.insert(0, os.path.join(ROOT_GUESS := os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))), "backend"))
from pipeline import title_constraints as _tc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "analytics", "analytics.db")
OUT = os.path.join(ROOT, "reports", "youtube-analysis-2026-09-11.xlsx")

CHANNELS = [
    ("scp-lab", "ゆっくり異常存在SCPラボ", "ゆっくり"),
    ("company-facts", "企業のホンネ", "ゆっくり"),
    ("akashic-librarian", "ラグナロクの司書", "ゆっくり"),
    ("daily-science", "リコとマコトのゆっくり日常科学", "ゆっくり"),
    ("yokai-watch", "ゆっくり妖怪ラボ", "ゆっくり"),
    ("pokemon-lab", "ポケモンラボ", "ゆっくり"),
    ("clip-fukada", "深田えいみ 切り抜き", "切り抜き"),
    ("2ch-matome", "2chまとめ", "ゆっくり"),
    ("clip-kaneko", "金子みゆ 切り抜き", "切り抜き"),
    ("clip-lab", "切り抜きラボ（ひろゆき）", "切り抜き"),
    ("fake-paper", "架空論文ラボ", "ゆっくり"),
]

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
H_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
SUB_FILL = PatternFill("solid", fgColor="D9E2F3")
WARN_FILL = PatternFill("solid", fgColor="FCE4D6")
GOOD_FILL = PatternFill("solid", fgColor="E2EFDA")
BAD_FILL = PatternFill("solid", fgColor="F8CBAD")
NOTE_FONT = Font(name=FONT, size=9, italic=True, color="808080")
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def eff_len(t):
    """実効文字数。backend のゲート（title_constraints.effective_len）と同一実装。"""
    return _tc.effective_len(t)


def clean_title(t):
    """表示用にハッシュタグと【】を落とす（長さは eff_len で数える）。"""
    t = re.sub(r"【[^】]*】", "", t or "")
    t = re.sub(r"[#＃][^\s：:]*", "", t)
    return re.sub(r"[\s　]+", " ", t).strip()


def q(t):
    return bool(re.search(r"なぜ|のか|どうして", t or ""))


# ---------------------------------------------------------------- データ取得
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

snap = {}
for cid, _, _ in CHANNELS:
    r = con.execute("select max(date) d from video_metrics where channel_id=?", (cid,)).fetchone()
    snap[cid] = r["d"]

vids = {}
for cid, _, _ in CHANNELS:
    if not snap[cid]:
        vids[cid] = []
        continue
    vids[cid] = [dict(r) for r in con.execute(
        "select * from video_metrics where channel_id=? and date=?", (cid, snap[cid]))]

agg = {}
for cid, name, kind in CHANNELS:
    s = vids[cid]
    v = sum(r["views"] or 0 for r in s)
    sg = sum(r["subscribers_gained"] or 0 for r in s)
    lk = sum(r["likes"] or 0 for r in s)
    cm = sum(r["comments"] or 0 for r in s)
    rets = [r["avg_view_percentage"] for r in s if r["avg_view_percentage"]]
    eff = [eff_len(r["title"]) for r in s if r["title"]]
    agg[cid] = dict(
        name=name, kind=kind, snap=snap[cid], n=len(s), views=v, subs=sg, likes=lk, comments=cm,
        ret=(sum(rets) / len(rets) if rets else 0),
        eff=(sum(eff) / len(eff) if eff else 0),
        short=(sum(1 for x in eff if x < 20) if eff else 0),
    )

# 成長率（channel_metrics は 09-05 までしか無い）
growth = {}
for cid, _, _ in CHANNELS:
    rows = [dict(r) for r in con.execute(
        "select * from channel_metrics where channel_id=? and date>='2026-08-23'", (cid,))]
    p1 = [r for r in rows if "2026-08-23" <= r["date"] <= "2026-08-29"]
    p2 = [r for r in rows if "2026-08-30" <= r["date"] <= "2026-09-05"]
    net = lambda L: sum((r["subscribers_gained"] or 0) - (r["subscribers_lost"] or 0) for r in L)
    vw = lambda L: sum(r["views"] or 0 for r in L)
    growth[cid] = dict(n1=net(p1), n2=net(p2), v1=vw(p1), v2=vw(p2))

wb = Workbook()
fc = FormulaCache()


def F(ws, row, col, formula, value, fmt=None):
    """数式を書き、同時に計算結果を控える（保存後に注入する）。"""
    return fc.put(ws, row, col, formula, value, number_format=fmt, font=BODY, border=BOX)


def header(ws, cols, row=1):
    for i, (label, width) in enumerate(cols, start=1):
        c = ws.cell(row=row, column=i, value=label)
        c.fill, c.font, c.border = H_FILL, H_FONT, BOX
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def note(ws, row, text, col=1, span=None):
    c = ws.cell(row=row, column=col, value=text)
    c.font = NOTE_FONT
    c.alignment = Alignment(wrap_text=True, vertical="top")
    if span:
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=span)


# =====================================================================
# シート1: サマリ
# =====================================================================
ws = wb.active
ws.title = "サマリ"
ws["A1"] = "YouTube Factory 指揮者レポート 2026-09-11"
ws["A1"].font = Font(name=FONT, size=14, bold=True)
ws["A2"] = ("データ基準日: 9ch=2026-09-08 / fake-paper・akashic-librarian=2026-09-06。"
            "09-09 以降 analytics.db に新規行がゼロ（3日連続で取得停止）のため、"
            "本日は新規の実績データ無しで分析している。")
ws["A2"].font = NOTE_FONT
ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
ws.merge_cells("A2:J2")
ws.row_dimensions[2].height = 30

cols = [("#", 5), ("チャンネル", 26), ("ID", 18), ("系統", 9), ("基準日", 11),
        ("動画本数", 9), ("再生数", 11), ("登録獲得", 9), ("登録/千再生", 12),
        ("いいね率%", 10), ("平均再生", 10), ("平均維持率%", 12),
        ("タイトル実効字数", 14), ("20字未満", 10)]
header(ws, cols, row=4)

order = sorted(CHANNELS, key=lambda c: -(agg[c[0]]["subs"] / agg[c[0]]["views"] * 1000
                                         if agg[c[0]]["views"] else -1))
r = 5
first_data = r
for i, (cid, name, kind) in enumerate(order, start=1):
    a = agg[cid]
    ws.cell(row=r, column=1, value=i)
    ws.cell(row=r, column=2, value=name)
    ws.cell(row=r, column=3, value=cid)
    ws.cell(row=r, column=4, value=kind)
    ws.cell(row=r, column=5, value=a["snap"] or "データ無")
    ws.cell(row=r, column=6, value=a["n"])
    ws.cell(row=r, column=7, value=a["views"])
    ws.cell(row=r, column=8, value=a["subs"])
    ws.cell(row=r, column=12, value=round(a["ret"], 1))
    ws.cell(row=r, column=13, value=round(a["eff"], 1))
    for cc in range(1, 15):
        ws.cell(row=r, column=cc).font = BODY
        ws.cell(row=r, column=cc).border = BOX
    V, S, N, SH = a["views"], a["subs"], a["n"], a["short"]
    F(ws, r, 9, f"=IF(G{r}=0,\"\",H{r}/G{r}*1000)",
      round(S / V * 1000, 6) if V else "", "0.000")
    F(ws, r, 10, f"=IF(G{r}=0,\"\",{a['likes']}/G{r}*100)",
      round(a["likes"] / V * 100, 6) if V else "", "0.00")
    F(ws, r, 11, f"=IF(F{r}=0,\"\",G{r}/F{r})",
      round(V / N, 6) if N else "", "#,##0")
    F(ws, r, 14, f"=IF(F{r}=0,\"\",{SH}/F{r})",
      round(SH / N, 6) if N else "", "0%")
    ws.cell(row=r, column=7).number_format = "#,##0"
    if kind == "切り抜き":
        for cc in range(1, 15):
            ws.cell(row=r, column=cc).fill = BAD_FILL
    r += 1
last_data = r - 1

ws.cell(row=r, column=2, value="合計 / 加重平均").font = BOLD
tot_n = sum(agg[c[0]]["n"] for c in CHANNELS)
tot_v = sum(agg[c[0]]["views"] for c in CHANNELS)
tot_s = sum(agg[c[0]]["subs"] for c in CHANNELS)
for col, letter, val in ((6, "F", tot_n), (7, "G", tot_v), (8, "H", tot_s)):
    c = F(ws, r, col, f"=SUM({letter}{first_data}:{letter}{last_data})", val, "#,##0")
    c.font = BOLD
c = F(ws, r, 9, f"=H{r}/G{r}*1000", round(tot_s / tot_v * 1000, 6), "0.000")
c.font = BOLD
total_row = r

r += 2
ws.cell(row=r, column=1, value="系統別の比較（至上戦略＝登録者増加なので登録/千再生で見る）").font = BOLD
r += 1
header(ws, [("系統", 14), ("ch数", 7), ("再生数", 12), ("登録獲得", 10), ("登録/千再生", 12)], row=r)
r += 1
kind_rows = {}
kind_rate = {}
for kind in ("ゆっくり", "切り抜き"):
    ids = [c[0] for c in CHANNELS if c[2] == kind]
    v = sum(agg[i]["views"] for i in ids)
    s = sum(agg[i]["subs"] for i in ids)
    ws.cell(row=r, column=1, value=kind).font = BODY
    ws.cell(row=r, column=2, value=len(ids)).font = BODY
    ws.cell(row=r, column=3, value=v).number_format = "#,##0"
    ws.cell(row=r, column=4, value=s)
    kind_rate[kind] = s / v * 1000 if v else 0
    F(ws, r, 5, f"=IF(C{r}=0,\"\",D{r}/C{r}*1000)", round(kind_rate[kind], 6), "0.000")
    for cc in range(1, 6):
        ws.cell(row=r, column=cc).font = BODY
        ws.cell(row=r, column=cc).border = BOX
    kind_rows[kind] = r
    r += 1
ws.cell(row=r, column=1, value="切り抜きの劣位倍率").font = BOLD
c = F(ws, r, 5, f"=E{kind_rows['ゆっくり']}/E{kind_rows['切り抜き']}",
      round(kind_rate["ゆっくり"] / kind_rate["切り抜き"], 6), "0.0\"倍\"")
c.font = BOLD

r += 2
ws.cell(row=r, column=1, value="本日の最重要トピック").font = BOLD
r += 1
for txt in [
    "① analytics 取得が 09-09 から3日連続でゼロ行。09-08 が最新スナップショットで、"
    "09-09・09-10・09-11 は video_metrics に1行も入っていない。原因は OAuth の全13ch失効"
    "（GCP OAuth 同意画面が「テスト中」のままでリフレッシュトークンが7日で強制失効する）。"
    "GCP project 844705815004 の同意画面を「本番」へ公開しない限り、再認可しても必ず1週間で再発する。",
    "② タイトル実効文字数と登録転換に強い関係があった（n=330）。"
    "0-14字 0.104 / 15-19字 0.279 / 20-24字 0.402 / 25-29字 0.646 / 30-34字 0.389 / 35字以上 0.345。"
    "25〜29字を頂点とする逆U字で、20字未満は最良帯の 1/2.3〜1/6.2。帯の切り方に依存しないことを"
    "4分位でも確認した（Q1 9-21字 0.227 / Q2 0.476 / Q3 27-35字 0.518 / Q4 35-54字 0.352）。"
    "20字未満は全330本中66本（20%）。自然文の min_effective_chars_target は backend が"
    "読まないため1本も効いていなかったので、本日 title_constraints.py に機械ゲートとして実装し8chへ適用した。",
    "③ 切り抜き3chは再生の28%（89,707 / 317,531再生）を占めながら登録獲得は10人で、"
    "ゆっくり系との登録効率差は依然として大きい。平均タイトル実効長も 16.9〜19.5字で全ch最短。"
    "ただし切り抜きのタイトルは発言の引用なので、文字数下限を課すと誤引用を作るリスクがある。"
    "本日は適用を見送り、別施策（引用は保ったまま文脈を添える形）として扱う。",
    "④ 09-11 朝の自動 run が theme_blacklist を退行させていた。scp-lab は 13語→6語 に減り、"
    "同じ run が追記した note（SCP-173 が再生上位40本中12本＝30%）と真逆の状態に。"
    "daily-science は「あくび」「自分の声」が消え、リポジトリ自身の回帰テストが RED になっていた"
    "（過去の重複タイトル8件が素通り）。本日いずれも復元し、テストは GREEN に戻した。",
    "④' 実効文字数の初版集計には実装バグがあり、同日中に検出して直した。"
    "旧実装の正規表現 `[#＃]\\S+` が「一口SCP #110：SCP-███「投稿者の編集室」…」のような"
    "連番つきタイトルで本文を丸ごとハッシュタグと見なして落としており、実効41字を5字と"
    "数えていた（scp-lab 50本中14本が該当）。コロンで止める実装に修正し、レポートと"
    "backend のゲートで同じ関数を使うようにした（別実装を持つとレポートの数字と"
    "実際に弾かれる基準がずれる）。結論（25〜29字が頂点の逆U字・下限20字）は修正後も変わらない。",
    "⑤ 「なぜ〇〇なのか」疑問形は ch を選ぶ。scp-lab 1.32 vs 0.51（2.6倍・leave-one-out 後も 1.15）、"
    "daily-science 0.53 vs 0.18（3.0倍）、yokai-watch 0.61 vs 0.33、2ch-matome 0.25 vs 0.18 で有効。"
    "一方 pokemon-lab は 0.08 vs 0.41 で明確に逆効果、company-facts は疑問形が n=1 しかなく判断不能。"
    "09-11 朝の run はこの ch 差を正しく分けて適用できていた（09-10 の scp-lab「疑問形は負」判定が誤り）。",
]:
    c = ws.cell(row=r, column=1, value=txt)
    c.font = BODY
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=14)
    ws.row_dimensions[r].height = 58
    r += 1

# =====================================================================
# シート2: チャンネル別詳細
# =====================================================================
ws = wb.create_sheet("チャンネル別詳細")
cols = [("チャンネル", 26), ("ID", 18), ("基準日", 11), ("本数", 7), ("再生数", 11),
        ("登録獲得", 9), ("登録/千再生", 12), ("いいね数", 9), ("いいね率%", 10),
        ("コメント", 9), ("平均維持率%", 11),
        ("登録純増 08/23-29", 15), ("登録純増 08/30-09/05", 17), ("成長倍率", 10),
        ("再生 08/23-29", 13), ("再生 08/30-09/05", 15),
        ("平均実効字数", 12), ("20字未満率", 11),
        ("疑問形 登録/千", 13), ("非疑問形 登録/千", 14), ("疑問形の効き", 20)]
header(ws, cols)
r = 2
for cid, name, kind in order:
    a, g = agg[cid], growth[cid]
    s = [x for x in vids[cid] if (x["views"] or 0) >= 200]
    Q = [x for x in s if q(x["title"])]
    N = [x for x in s if not q(x["title"])]
    rate = lambda L: (sum(x["subscribers_gained"] or 0 for x in L)
                      / sum(x["views"] or 0 for x in L) * 1000) if sum(x["views"] or 0 for x in L) else None
    rq, rn = rate(Q), rate(N)
    if rq is None or rn is None or len(Q) < 5 or len(N) < 5:
        # 片側が5本未満だと1本の当たり外れで倍率が動くので判定しない
        verdict = f"判断不能（n={len(Q)}/{len(N)}）"
    elif rq > rn * 1.3:
        verdict = f"有効 {rq/rn:.1f}倍（n={len(Q)}/{len(N)}）"
    elif rn > rq * 1.3:
        verdict = f"逆効果 {rn/rq if rq else 99:.1f}倍（n={len(Q)}/{len(N)}）"
    else:
        verdict = f"差なし（n={len(Q)}/{len(N)}）"
    vals = [name, cid, a["snap"] or "データ無", a["n"], a["views"], a["subs"], None,
            a["likes"], None, a["comments"], round(a["ret"], 1),
            g["n1"], g["n2"], None, g["v1"], g["v2"],
            round(a["eff"], 1), None,
            round(rq, 3) if rq is not None else "n/a",
            round(rn, 3) if rn is not None else "n/a", verdict]
    for i, v in enumerate(vals, start=1):
        c = ws.cell(row=r, column=i, value=v)
        c.font, c.border = BODY, BOX
    V, N = a["views"], a["n"]
    F(ws, r, 7, f"=IF(E{r}=0,\"\",F{r}/E{r}*1000)",
      round(a["subs"] / V * 1000, 6) if V else "", "0.000")
    F(ws, r, 9, f"=IF(E{r}=0,\"\",H{r}/E{r}*100)",
      round(a["likes"] / V * 100, 6) if V else "", "0.00")
    F(ws, r, 14, f"=IF(L{r}=0,\"\",M{r}/L{r})",
      round(g["n2"] / g["n1"], 6) if g["n1"] else "", "0.00\"倍\"")
    F(ws, r, 18, f"=IF(D{r}=0,\"\",{a['short']}/D{r})",
      round(a["short"] / N, 6) if N else "", "0%")
    ws.cell(row=r, column=5).number_format = "#,##0"
    if "逆効果" in verdict:
        ws.cell(row=r, column=21).fill = BAD_FILL
    elif "有効" in verdict:
        ws.cell(row=r, column=21).fill = GOOD_FILL
    r += 1
r += 1
note(ws, r, "「成長倍率」は channel_metrics の登録純増（獲得−喪失）の週次比較。"
            "channel_metrics は 09-05 で停止しているため、直近週は 08/30〜09/05。"
            "「疑問形」の判定は 200再生以上の動画を対象に、タイトルに「なぜ／のか／どうして」を含むかで分けた。", span=21)
ws.row_dimensions[r].height = 44

# =====================================================================
# シート3: 直近動画一覧
# =====================================================================
ws = wb.create_sheet("直近動画一覧")
cols = [("チャンネル", 22), ("公開日時(UTC)", 17), ("枠(JST)", 9), ("タイトル", 58),
        ("実効字数", 9), ("疑問形", 8), ("再生", 9), ("いいね", 8), ("登録", 7),
        ("登録/千再生", 11), ("維持率%", 9), ("CTR%", 8), ("状態", 16)]
header(ws, cols)
r = 2
for cid, name, kind in order:
    rows = sorted(vids[cid], key=lambda x: str(x["published_at"]), reverse=True)
    newest = rows[:5]
    withdata = [x for x in rows if (x["views"] or 0) > 0][:5]
    for tag, group in (("最新5本", newest), ("実績のある直近5本", withdata)):
        for x in group:
            pub = str(x["published_at"])[:16]
            hh = int(str(x["published_at"])[11:13]) if len(str(x["published_at"])) > 13 else 0
            jst = f"{(hh + 9) % 24}時"
            ct = clean_title(x["title"])
            state = tag if (x["views"] or 0) > 0 else f"{tag}／集計待ち(2-3日遅延)"
            vals = [name, pub, jst, ct, eff_len(x["title"]), "○" if q(x["title"]) else "",
                    x["views"] or 0, x["likes"] or 0, x["subscribers_gained"] or 0,
                    None, round(x["avg_view_percentage"] or 0, 1), round(x["ctr"] or 0, 2), state]
            for i, v in enumerate(vals, start=1):
                c = ws.cell(row=r, column=i, value=v)
                c.font, c.border = BODY, BOX
            vv = x["views"] or 0
            F(ws, r, 10, f"=IF(G{r}=0,\"\",I{r}/G{r}*1000)",
              round((x["subscribers_gained"] or 0) / vv * 1000, 6) if vv else "", "0.000")
            if eff_len(x["title"]) < 20:
                ws.cell(row=r, column=5).fill = BAD_FILL
            if (x["views"] or 0) == 0:
                ws.cell(row=r, column=13).fill = WARN_FILL
            r += 1
r += 1
note(ws, r, "「最新5本」は公開が最も新しい5本。YouTube Analytics は2〜3日遅れるため、"
            "09-07 以降公開分は全指標ゼロで表示される（既知・09-05 実測）。"
            "そのため各chについて「実績のある直近5本」（再生>0）も併記した。"
            "「枠(JST)」は published_at(UTC)+9時間。実効字数はハッシュタグと【】を除いた本文の長さで、"
            "20字未満を橙で塗っている。", span=13)
ws.row_dimensions[r].height = 58

# =====================================================================
# シート4: 改善提案
# =====================================================================
ws = wb.create_sheet("改善提案")
cols = [("#", 5), ("優先", 8), ("対象", 20), ("提案", 46), ("根拠（実測）", 60),
        ("本日の実行", 34), ("状態", 14)]
header(ws, cols)
props = [
    (1, "最優先", "基盤（全13ch）",
     "GCP project 844705815004 の OAuth 同意画面を「テスト中」→「本番」へ公開する",
     "analytics.db の video_metrics は 09-08 で止まり、09-09・09-10・09-11 は0行。"
     "同意画面がテスト中だとリフレッシュトークンが7日で強制失効するため、"
     "再認可しても必ず1週間で再発する（09-08 は失効4ch＋警告9ch → 09-10 に全13ch invalid_grant）。",
     "未実行（GCPコンソールでの人手操作が必要）", "要ユーザー操作"),
    (2, "高", "scp-lab / daily-science",
     "theme_blacklist の退行を戻す",
     "09-11 朝の自動 run が scp-lab を 13語→6語、daily-science から「あくび」「自分の声」を削除。"
     "同 run が追記した note（SCP-173 が再生上位40本中12本＝30%／「自分の声」が10本）と真逆で、"
     "リポジトリの回帰テスト test_fixes_20260909.py::TestDailyScienceBlacklist が RED だった。",
     "8語＋2語を復元。テストは GREEN に戻った", "実行済み"),
    (3, "高", "8ch（切り抜き除く）",
     "タイトル実効文字数の下限20字を機械ゲート化（狙いは25〜29字）",
     "n=330（views>0）で登録/千再生は 0-14字 0.104 / 15-19字 0.279 / 20-24字 0.402 / "
     "25-29字 0.646 / 30-34字 0.389 / 35字以上 0.345。25〜29字が頂点の逆U字で、最弱帯の6.2倍。"
     "4分位でも同じ形（Q1 0.227 / Q2 0.476 / Q3 0.518 / Q4 0.352）。"
     "20字未満が全体の20%（66/330本）を占めていた。自然文の min_effective_chars_target は "
     "backend が読まないため1本も効いていなかった。",
     "title_constraints.py に min_effective_chars を実装し、8ch の hard_constraints へ追加"
     "（回帰テスト9件を追加）", "実行済み"),
    (4, "高", "akashic-librarian",
     "hard_constraints を新規付与（絵文字・「秘密」・99%型・答え提示語・実効長）",
     "登録/千再生 0.570 で全11ch中3位なのに、hard_constraints が1つも無く機械ゲートが完全に無効だった。"
     "上位2本は「なぜ600年も読めない？存在しない植物だけが描かれた手稿」1.71 と"
     "「三十八人が見ていて、誰も動かなかった夜」0.95 で、いずれも28字前後。",
     "他6chと同形のゲートを設定（max_chars=36）", "実行済み"),
    (5, "高", "fake-paper",
     "シリーズ接頭辞「架空論文ファイル」を禁止し、本文に情報量を戻す",
     "17本 / 7,047再生 / 登録0 で全11ch唯一の転換ゼロ。再生上位10本のうち5本がこの接頭辞に"
     "9文字を使っており、「架空論文ファイル  — 1,248人が選んだ新形態」のように本文がほぼ残っていない。"
     "連番・シリーズ接頭辞は 08-31 に全chで0.84倍（負）と実測済み。",
     "forbid_patterns に登録。title_style を書き換え、該当キュー1件を改題", "実行済み"),
    (6, "中", "akashic-librarian / clip-animal",
     "18時JST の投稿枠を17時JST へ寄せる",
     "投稿時刻(JST)別の登録/千再生は 17時 0.590(n=51) / 19時 0.470(n=53) / 18時 0.219(n=50)。"
     "最大サンプルの3枠の中で18時が最下位（17時の1/2.7）。",
     "akashic-librarian 18:45→17:45、clip-animal 18:00→17:00", "実行済み"),
    (7, "中", "scp-lab / daily-science / yokai-watch / 2ch-matome",
     "疑問形は「なぜ〜のか」の体言止めで書き、末尾に「？」を付けない",
     "yokai-watch は hard_constraints.forbid_patterns で末尾の疑問符を禁止しているのに、"
     "09-11 朝の run が「なぜ〇〇なのか」を最優先にしたため、疑問符付きで書くと必ずゲートに落ちて"
     "再生成に回る状態だった。疑問形の効果は語順にあり、疑問符の有無ではない。",
     "4ch の theme_priority に注記を追加", "実行済み"),
    (8, "中", "切り抜き3ch",
     "タイトルを引用のまま保ちつつ、引用の後ろに文脈を1節添える形を試す",
     "切り抜き3chは 89,707再生（全体の28%）で登録10人。平均タイトル実効長は "
     "clip-fukada 16.9字 / clip-lab 18.2字 / clip-kaneko 19.5字 で全ch最短3つ、"
     "20字未満率は 85% / 67% / 53%。実効長と登録転換の関係（提案3）はここで最も伸びしろがある。"
     "ただしタイトルが発言の引用なので、文字数下限を機械的に課すと誤引用を作りうる。",
     "未実行（誤引用リスクのため min_effective_chars の適用を見送り）", "次回の実験候補"),
    (9, "中", "scp-lab",
     "最良枠（19時JST）へ枠を寄せる",
     "ch内で 19時 1.28(n=14) > 13時 0.70(n=7) > 9時 0.59(n=17)。9時枠が最弱。",
     "枠は変更せず schedule に実測を記録のみ。新規データが入ってから変更する"
     "（同一データで二重に意思決定しないという運用上の鉄則）", "保留（意図的）"),
    (10, "低", "company-facts",
     "疑問形を強制しない。金額＋比較軸の型を維持する",
     "疑問形は n=1（0登録）しかなく判断不能。非疑問形は 0.739 で全ch最高水準。"
     "上位3本はいずれも金額を先頭に置いた型（Netflix 月額1,590円 1.98 / "
     "サントリー平均年収1,000万円超 1.89 / オリエンタルランド536万円 1.78）。",
     "09-11 朝の run は当chに疑問形ルールを適用しておらず、対応不要と確認", "対応不要"),
]
r = 2
for p in props:
    for i, v in enumerate(p, start=1):
        c = ws.cell(row=r, column=i, value=v)
        c.font, c.border = BODY, BOX
        c.alignment = Alignment(wrap_text=True, vertical="top")
    fill = {"実行済み": GOOD_FILL, "要ユーザー操作": BAD_FILL}.get(p[6], WARN_FILL)
    ws.cell(row=r, column=7).fill = fill
    ws.row_dimensions[r].height = 76
    r += 1

# =====================================================================
# シート5: 前回比較
# =====================================================================
ws = wb.create_sheet("前回比較")
ws["A1"] = "前回（09-10 レポート）との比較と、前回 config 変更の差分検証"
ws["A1"].font = Font(name=FONT, size=12, bold=True)

r = 3
ws.cell(row=r, column=1, value="A. 指標の前回比（09-10 レポートは 09-08 スナップショット基準。本日も同じ基準日）").font = BOLD
r += 1
header(ws, [("チャンネル", 26), ("09-10 レポートの登録/千", 20), ("本日の登録/千", 16),
            ("差", 10), ("備考", 46)], row=r)
r += 1
PREV = {"scp-lab": 0.702, "company-facts": 0.657, "yokai-watch": 0.485, "clip-fukada": 0.431,
        "daily-science": 0.388, "pokemon-lab": 0.274, "2ch-matome": 0.197,
        "clip-kaneko": 0.145, "clip-lab": 0.016, "fake-paper": None, "akashic-librarian": None}
for cid, name, kind in order:
    a = agg[cid]
    cur = a["subs"] / a["views"] * 1000 if a["views"] else None
    prev = PREV.get(cid)
    memo = ("09-10 は算出不能（トークン失効でデータ断）。本日は 09-06 スナップショットから算出できた"
            if prev is None else
            "同じ 09-08 スナップショットなので、差は集計方法（30日窓→スナップショット当日）の違い")
    vals = [name, prev if prev is not None else "算出不能",
            round(cur, 3) if cur is not None else "データ無", None, memo]
    for i, v in enumerate(vals, start=1):
        c = ws.cell(row=r, column=i, value=v)
        c.font, c.border = BODY, BOX
        c.alignment = Alignment(wrap_text=True, vertical="top")
    if prev is not None and cur is not None:
        F(ws, r, 4, f"=C{r}-B{r}", round(cur - prev, 6), "+0.000;-0.000;0.000")
    ws.cell(row=r, column=3).number_format = "0.000"
    r += 1
r += 1
note(ws, r, "09-09 以降 analytics に新規行が無いため、09-10 レポートと本日は同じ基準日（09-08）を見ている。"
            "したがって「前日比の登録者増減」は本日は算出できない。"
            "数値の差は基準日の違いではなく集計窓の違い（09-10 は30日窓、本日はスナップショット当日行の合計）。", span=5)
ws.row_dimensions[r].height = 44

r += 2
ws.cell(row=r, column=1, value="B. 09-10〜09-11朝の config 変更の差分検証").font = BOLD
r += 1
header(ws, [("変更", 32), ("適用日", 10), ("反映確認", 14), ("効果検証", 18), ("判定と対応", 52)], row=r)
r += 1
checks = [
    ("banned_words に絵文字19文字を追加（6ch）", "09-11 朝", "✅ 反映済み",
     "検証不能（新規データ0）",
     "継続。絵文字ありは ch内対照で5/6chが悪化と 09-11 朝の run が記録しており、方向は既存実測と整合。"),
    ("「なぜ〇〇なのか」を最優先化（scp-lab / daily-science / yokai-watch / 2ch-matome）", "09-11 朝",
     "✅ 反映済み", "独立に再測して裏付け",
     "継続。本日独立に測り直して scp-lab 1.32 vs 0.51（leave-one-out 後も 1.15）、"
     "daily-science 0.53 vs 0.18 を確認。09-10 の「scp-lab は疑問形が明確に負」という判定が誤りで、"
     "09-11 朝の run が正しく修正していた。"),
    ("pokemon-lab のみ疑問形を回避し二人称を主軸化", "09-11 朝", "✅ 反映済み",
     "独立に再測して裏付け",
     "継続。本日の再測でも 疑問形 0.08 vs 非疑問形 0.41 で明確に逆効果（n=11/19）。"
     "ch別に分けた判断は妥当。"),
    ("theme_blacklist の削減（scp-lab 13→6語 / daily-science −2語）", "09-11 朝", "✅ 反映済み",
     "❌ 逆効果と判定",
     "撤回。同 run が追記した note と真逆で、リポジトリの回帰テストも RED だった。本日復元。"),
    ("「秘密」を banned_words へ（6ch）", "09-09", "✅ 反映済み", "検証不能（新規データ0）",
     "継続。登録/千 0.120 (n=18) vs 含まない 0.52 という 09-09 実測のまま。"),
    ("「99%が知らない」型を forbid_patterns へ（6ch）", "09-09", "✅ 反映済み",
     "検証不能（新規データ0）", "継続。0.194 (n=11) vs 0.510 の 09-09 実測のまま。"),
    ("short_illustrations.max_count を6へ（全ch）", "09-05", "✅ 反映済み",
     "検証不能（維持率は判断軸外）",
     "継続。ただし維持率は登録転換と符号がchごとに逆転するため採否の判断には使わない。"),
]
for c_ in checks:
    for i, v in enumerate(c_, start=1):
        cc = ws.cell(row=r, column=i, value=v)
        cc.font, cc.border = BODY, BOX
        cc.alignment = Alignment(wrap_text=True, vertical="top")
    if "撤回" in c_[4]:
        ws.cell(row=r, column=4).fill = BAD_FILL
    elif "裏付け" in c_[3]:
        ws.cell(row=r, column=4).fill = GOOD_FILL
    else:
        ws.cell(row=r, column=4).fill = WARN_FILL
    ws.row_dimensions[r].height = 62
    r += 1
r += 1
note(ws, r, "09-09 以降 analytics の新規行がゼロなので、09-10・09-11朝の施策は「反映されたか」までしか"
            "検証できない。効果の検証は analytics が復旧してから（提案1）。"
            "運用上の鉄則どおり、新規の再生実績が無い日は新しい賭けを増やさず、"
            "本日は「明らかな退行の修正」と「既に実測がある関係の機械ゲート化」に限定した。", span=5)
ws.row_dimensions[r].height = 44

os.makedirs(os.path.dirname(OUT), exist_ok=True)
wb.save(OUT)
n = fc.inject(OUT)
print(f"✅ {OUT}")
print(f"   数式 {n} 件にキャッシュ値を注入（数式はそのまま残している）")
