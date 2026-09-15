#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指揮者 Phase 5 — 2026-09-15 分析レポート(xlsx)生成

データ源: data/analytics/analytics.db のみ（ブラウザ/APIキー不使用）
出力:     reports/youtube-analysis-2026-09-15.xlsx
シート:   サマリ / チャンネル別詳細 / 直近動画一覧 / 改善提案 / 前回比較

スナップショット定義（毎回同じ定義で比較するため明記）:
  * video_metrics は「各chの直近50本ローリング窓・累積値」の日次スナップショット。
    窓の構成が日ごとに入れ替わるため、日次差分は「窓ごと」の比較であり
    個別動画の伸びではない。必ず窓とch構成を併記する（4日連続の注意事項）。
  * channel_metrics は YouTube Analytics の集計ラグで最終日=2026-09-11。
    09-09〜09-11 の views が極端に小さいのは実績の崩壊ではなく未集計。
"""
import json
import os
import sqlite3
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "data", "analytics", "analytics.db")
OUT = os.path.join(REPO, "reports", "youtube-analysis-2026-09-15.xlsx")
TODAY = "2026-09-15"

NAMES = {
    "scp-lab": "ゆっくり異常存在SCPラボ",
    "daily-science": "リコとマコトのゆっくり日常科学",
    "pokemon-lab": "ゆっくりポケラボ",
    "yokai-watch": "ゆっくり妖怪ラボ",
    "2ch-matome": "ゆっくり2chスレまとめ劇場",
    "company-facts": "企業のホンネ",
    "clip-lab": "切り抜きラボ（ひろゆき）",
    "clip-fukada": "深田えいみ 切り抜きチャンネル",
    "clip-kaneko": "金子みゆ 切り抜きチャンネル",
    "fake-paper": "虚構論文チャンネル",
    "akashic-librarian": "ラグナロクの司書",
    "clip-animal": "動物情報局",
    "socio-rx": "社会学の処方箋",
}
# 系統: ゆっくり(moviepy) / 切り抜き(noimos) / 長尺(chatcut)
YUKKURI = ["daily-science", "scp-lab", "yokai-watch", "company-facts",
           "2ch-matome", "pokemon-lab", "fake-paper", "socio-rx"]
KEITO = {ch: "ゆっくり系" for ch in YUKKURI}
KEITO.update({c: "切り抜き系" for c in
              ["clip-lab", "clip-fukada", "clip-kaneko", "clip-animal"]})
KEITO["akashic-librarian"] = "長尺系"
ORDER = ["scp-lab", "daily-science", "yokai-watch", "company-facts", "2ch-matome",
         "pokemon-lab", "socio-rx", "fake-paper", "akashic-librarian",
         "clip-lab", "clip-fukada", "clip-kaneko", "clip-animal"]

FONT = "Arial"
H1 = Font(name=FONT, size=14, bold=True)
H2 = Font(name=FONT, size=11, bold=True, color="FFFFFF")
BOLD = Font(name=FONT, size=10, bold=True)
BODY = Font(name=FONT, size=10)
SMALL = Font(name=FONT, size=9, color="555555")
HDR_FILL = PatternFill("solid", fgColor="2F5597")
WARN_FILL = PatternFill("solid", fgColor="FCE4D6")
GOOD_FILL = PatternFill("solid", fgColor="E2EFDA")
GREY_FILL = PatternFill("solid", fgColor="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


# ------------------------------------------------------------------ データ取得
def fetch():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""create temp view lv as select v.* from video_metrics v
        join (select video_id, max(date) d from video_metrics group by video_id) m
        on v.video_id = m.video_id and v.date = m.d""")
    d = {}

    # 各chの最新スナップショット（=直近50本ローリング窓の合計）
    d["snap"] = {r["ch"]: dict(r) for r in c.execute("""
        with latest as (select channel_id, max(date) d from video_metrics group by channel_id)
        select v.channel_id ch, l.d snap, count(distinct v.video_id) n,
               sum(v.views) views, sum(v.likes) likes, sum(v.comments) comments,
               sum(v.subscribers_gained) subs, round(avg(v.avg_view_percentage), 2) avp,
               datetime(max(v.fetched_at), 'unixepoch') fetched
        from video_metrics v join latest l
          on v.channel_id = l.channel_id and v.date = l.d
        group by v.channel_id""")}

    # 前回スナップショット（最新の1つ前の日付）
    prev = {}
    for r in c.execute("""select channel_id ch, date, count(distinct video_id) n,
            sum(views) views, sum(likes) likes, sum(subscribers_gained) subs
        from video_metrics group by channel_id, date order by channel_id, date"""):
        prev.setdefault(r["ch"], []).append(dict(r))
    d["prev"] = {ch: rows[-2] for ch, rows in prev.items() if len(rows) >= 2}
    d["hist"] = prev

    # channel_metrics（登録純増）
    d["cm"] = [dict(r) for r in c.execute("""select channel_id ch, date, views,
        subscribers_gained sg, subscribers_lost sl from channel_metrics
        where date >= '2026-09-01' order by ch, date""")]

    # 直近動画（09-05以降公開・全ch）
    d["recent"] = [dict(r) for r in c.execute("""select channel_id ch, title,
        substr(published_at, 1, 16) pub, views, likes, comments,
        subscribers_gained subs, avg_view_percentage avp, avg_view_duration dur, ctr
        from lv where published_at >= '2026-09-05'
        order by channel_id, published_at desc""")]

    # 維持率バンド（全ch / ゆっくりのみ）
    band_sql = """select case
        when avg_view_percentage < 30 then '<30%%'
        when avg_view_percentage < 40 then '30-40%%'
        when avg_view_percentage < 50 then '40-50%%'
        when avg_view_percentage < 60 then '50-60%%'
        when avg_view_percentage < 70 then '60-70%%'
        else '>=70%%' end band, count(*) n, sum(views) views,
        sum(subscribers_gained) subs, round(avg(views), 0) av
        from lv where published_at >= '2026-08-01' and views >= 200 %s
        group by band order by min(avg_view_percentage)"""
    d["band_all"] = [dict(r) for r in c.execute(band_sql % "")]
    d["band_yuk"] = [dict(r) for r in c.execute(
        band_sql % ("and channel_id in ('daily-science','scp-lab','yokai-watch',"
                    "'company-facts','2ch-matome','pokemon-lab','fake-paper')"))]
    d["band_clip_share"] = [dict(r) for r in c.execute("""select channel_id ch,
        count(*) n, sum(views) views, sum(subscribers_gained) subs from lv
        where published_at >= '2026-08-01' and views >= 200
          and avg_view_percentage >= 70 group by ch order by views desc""")]

    # 公開時刻別
    d["hour"] = [dict(r) for r in c.execute("""select
        cast(strftime('%H', datetime(published_at, '+9 hours')) as int) h,
        count(*) n, sum(views) views, sum(subscribers_gained) subs
        from lv where published_at >= '2026-08-01' and views >= 200
          and channel_id in ('daily-science','scp-lab','yokai-watch',
                             'company-facts','2ch-matome','pokemon-lab')
        group by h having n >= 4 order by h""")]

    # いいね率四分位
    rows = [dict(r) for r in c.execute("""select views, likes, subscribers_gained subs
        from lv where published_at >= '2026-08-01' and views >= 200""")]
    rows.sort(key=lambda r: r["likes"] / r["views"])
    n = len(rows)
    d["quartile"] = []
    for i in range(4):
        seg = rows[i * n // 4:(i + 1) * n // 4]
        v = sum(x["views"] for x in seg)
        d["quartile"].append({"q": f"Q{i + 1}", "n": len(seg), "views": v,
                              "likes": sum(x["likes"] for x in seg),
                              "subs": sum(x["subs"] for x in seg)})

    # 未計測（09-13以降公開）
    d["unmeasured"] = [dict(r) for r in c.execute("""select channel_id ch,
        count(*) n, sum(views) views from lv
        where published_at >= '2026-09-13' group by ch order by ch""")]

    # TOP動画
    d["top_spk"] = [dict(r) for r in c.execute("""select channel_id ch, title,
        views, likes, subscribers_gained subs, avg_view_percentage avp,
        substr(published_at, 1, 10) pub from lv
        where published_at >= '2026-08-01' and views >= 500
        order by subscribers_gained * 1.0 / views desc limit 12""")]
    c.close()
    return d


# ------------------------------------------------------------------ 書式ヘルパ
def head(ws, row, cols, widths=None):
    for i, t in enumerate(cols, start=1):
        cell = ws.cell(row=row, column=i, value=t)
        cell.font = H2
        cell.fill = HDR_FILL
        cell.border = BOX
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 30


def put(ws, row, values, fmt=None, fill=None, font=None):
    for i, v in enumerate(values, start=1):
        cell = ws.cell(row=row, column=i, value=v)
        cell.font = font or BODY
        cell.border = BOX
        if fill:
            cell.fill = fill
        if fmt and i in fmt:
            cell.number_format = fmt[i]


def title_block(ws, title, note_lines):
    ws["A1"] = title
    ws["A1"].font = H1
    r = 2
    for line in note_lines:
        ws.cell(row=r, column=1, value=line).font = SMALL
        r += 1
    return r + 1


# ------------------------------------------------------------------ 各シート
def sheet_summary(wb, d):
    ws = wb.create_sheet("サマリ")
    concl = [
        "1. 本日の新規データは 09-14 22:31 JST fetch の1本のみ（video_metrics 最終日=2026-09-14）。"
        "channel_metrics は集計ラグで 09-11 止まり。",
        "2. 【鉄則遵守】同一スナップショットでの二重判断を避けるため、指揮者からの新規 config 変更は行っていない。"
        "本日 10:08 の並走 run が適用した変更を独立検算してコミットした。",
        "3. 至上指標 登録/千再生は 5ch 中 3ch が改善（scp-lab +0.044 / yokai-watch +0.054 / daily-science +0.023）、"
        "2ch が悪化（company-facts -0.030 / 2ch-matome -0.013）。",
        "4. 登録の主説明変数は「いいね率」。四分位 Q4/Q1 = 3.96倍（前日 3.90倍の独立再現）。"
        "伸びている 3ch はいずれも いいね率が同時に上昇している。",
        "5. 【前日の知見を一部修正】維持率の頂点が 40-50% であることは再現した。"
        "しかし「>=70% が最下位」は切り抜き2ch（clip-lab/clip-fukada が当該帯 views の58%）による交絡で、"
        "ゆっくり7chに限ると >=70% は 0.514 で最下位ではない。最下位は <30%（0.245）。",
        "6. 09-13 以降に公開した 25 本は全て views=0（Analytics ラグ）。"
        "09-14 の投稿枠・型ルール変更の効果は 1本も測れていない。再判定は n≧20/ch が揃う 09-21。",
        "7. 未解決の人手案件が 3 件（サムネ403=9ch / Anthropic APIキー401 / OAuth未再認可6ch）。"
        "特にサムネ403は「サムネ品質最優先」の施策が daily-science 以外に一切届いていないことを意味する。",
    ]
    r = title_block(ws, f"YouTube Factory 指揮者レポート  {TODAY}", [
        "データ源: data/analytics/analytics.db のみ（ブラウザ・APIキー不使用）",
        "生成: " + datetime.now().strftime("%Y-%m-%d %H:%M"),
    ])
    ws.cell(row=r, column=1, value="■ 本日の結論").font = BOLD
    r += 1
    for t in concl:
        c = ws.cell(row=r, column=1, value=t)
        c.font = BODY
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
        ws.row_dimensions[r].height = 28
        r += 1
    r += 1

    ws.cell(row=r, column=1, value="■ チャンネル別 実績（各chの最新スナップショット・直近50本ローリング窓の累積）").font = BOLD
    r += 1
    head(ws, r, ["チャンネル", "名称", "系統", "スナップ", "本数", "総再生", "平均再生",
                 "登録者", "登録/千再生", "いいね数", "いいね率%", "コメント", "平均維持率%"],
         [17, 26, 9, 11, 7, 10, 10, 8, 12, 9, 10, 9, 12])
    first = r + 1
    r += 1
    for ch in ORDER:
        s = d["snap"].get(ch)
        if not s:
            continue
        kei = KEITO.get(ch, "—")
        fill = None
        if s["views"] == 0:
            fill = GREY_FILL
        elif s["views"] and s["subs"] * 1000.0 / s["views"] >= 0.5:
            fill = GOOD_FILL
        elif s["views"] and s["subs"] * 1000.0 / s["views"] < 0.2:
            fill = WARN_FILL
        put(ws, r, [ch, NAMES[ch], kei, s["snap"], s["n"], s["views"],
                    f"=IFERROR(F{r}/E{r},0)", s["subs"],
                    f"=IFERROR(H{r}*1000/F{r},0)", s["likes"],
                    f"=IFERROR(J{r}*100/F{r},0)", s["comments"], s["avp"]],
            fmt={6: "#,##0", 7: "#,##0", 9: "0.000", 11: "0.000", 13: "0.0"}, fill=fill)
        r += 1
    last = r - 1
    put(ws, r, ["合計/加重", "13ch", "", "", f"=SUM(E{first}:E{last})",
                f"=SUM(F{first}:F{last})", f"=IFERROR(F{r}/E{r},0)",
                f"=SUM(H{first}:H{last})", f"=IFERROR(H{r}*1000/F{r},0)",
                f"=SUM(J{first}:J{last})", f"=IFERROR(J{r}*100/F{r},0)",
                f"=SUM(L{first}:L{last})", ""],
        fmt={5: "#,##0", 6: "#,##0", 7: "#,##0", 9: "0.000", 11: "0.000"}, font=BOLD,
        fill=GREY_FILL)
    r += 2
    ws.cell(row=r, column=1, value=(
        "※ 緑=登録/千再生 0.5以上 ／ 橙=0.2未満 ／ 灰=計測値ゼロ（socio-rx は公開3本すべて Analytics 未集計）。"
    )).font = SMALL
    r += 1
    ws.cell(row=r, column=1, value=(
        "※ スナップ列が 09-14 でない 8ch は OAuth invalid_grant により fetch が止まっており、"
        "表示値は当該日の最終スナップショット（据え置き）。新規判断には使っていない。"
    )).font = SMALL
    return ws


def sheet_channels(wb, d):
    ws = wb.create_sheet("チャンネル別詳細")
    r = title_block(ws, "チャンネル別詳細 — 実績・在庫・本日のconfig状態", [
        "投稿枠/型ルールは 09-14 に変更済み。本日は据え置き（同一スナップショットでの二重判断回避）。",
    ])
    cfg = {}
    for ch in ORDER:
        p = os.path.join(REPO, "data", "channels", f"{ch}.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                cfg[ch] = json.load(f)
    head(ws, r, ["チャンネル", "autopilot", "投稿枠(JST)", "枠数", "キュー本数", "在庫日数",
                 "登録/千再生", "いいね率%", "平均維持率%", "維持率目標帯", "本日の変更", "評価/次アクション"],
         [17, 10, 26, 6, 10, 9, 11, 10, 11, 12, 22, 48])
    r += 1
    verdicts = {
        "scp-lab": "○ 5ch中最良 0.863（+0.044）。いいね率も上昇。現行 A型（疑問＋数字）を継続。次判定 09-21",
        "daily-science": "○ 0.663（+0.023）。いいね率 0.745% で全ch最高。カスタムサムネが通る唯一のch＝サムネ改善の効果測定はここでのみ可能",
        "yokai-watch": "◎ 0.787（+0.054）。6日で +0.324 と最速改善。B型（数字を入れない疑問形）が効いている",
        "company-facts": "△ 0.619（-0.030）。3日連続の低下。総再生は最大だが登録変換が落ちている。いいね率 0.304% が低い",
        "2ch-matome": "× 0.152（-0.013）。5ch中最下位。autopilot 停止中で在庫8.7日。再開前に型の見直しが必要",
        "pokemon-lab": "－ 09-08 以降 fetch 停止（OAuth invalid_grant）。0.272 は据え置き値。評価不能",
        "socio-rx": "－ 公開3本すべて views=0。維持率目標帯も未設定（09-15の適用対象6chに含まれず）。評価不能",
        "fake-paper": "× 登録0人/7,047再生。停止中。据え置き",
        "akashic-librarian": "－ OAuth未連携。0.570 は 09-06 の据え置き値",
        "clip-lab": "× 0.024。総再生42,321は3位だが登録1人。停止中。構造的に登録に繋がらない",
        "clip-fukada": "× 0.211。停止中。再生は取れるが登録変換は ゆっくり系の 1/4",
        "clip-kaneko": "× 0.169。停止中",
        "clip-animal": "× 3本・17再生。実質未稼働",
    }
    for ch in ORDER:
        s = d["snap"].get(ch)
        if not s:
            continue
        c = cfg.get(ch, {})
        ap = c.get("autopilot", {})
        times = ap.get("schedule", {}).get("times", [])
        tstr = " / ".join(f"{t.get('hour')}:{t.get('minute','0'):0>2}" for t in times) or "—"
        q = len(ap.get("theme_queue", []))
        slots = len(times) or 1
        band = (c.get("optimization", {}) or {}).get("retention_target_band")
        bstr = f"{band['min']}-{band['max']}%" if band else "未設定"
        chg = d["changes"].get(ch)
        if chg:
            cs = f"キュー +{chg['queue_added']}（在庫 {chg['stock_days_before']}→{chg['stock_days_after']}日）"
        elif ch in ("2ch-matome", "pokemon-lab"):
            cs = "維持率目標帯のみ明記"
        else:
            cs = "変更なし"
        put(ws, r, [ch, "有効" if ap.get("enabled") else "停止", tstr, slots, q,
                    f"=IFERROR(E{r}/D{r},0)",
                    f"=IFERROR({s['subs']}*1000/{s['views']},0)" if s["views"] else 0,
                    f"=IFERROR({s['likes']}*100/{s['views']},0)" if s["views"] else 0,
                    s["avp"], bstr, cs, verdicts.get(ch, "")],
            fmt={6: "0.0", 7: "0.000", 8: "0.000", 9: "0.0"},
            fill=GOOD_FILL if ap.get("enabled") else None)
        ws.cell(row=r, column=12).alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 30
        r += 1
    r += 1
    for t in [
        "※ 在庫日数 = キュー本数 ÷ 1日あたり投稿枠数。本日 autopilot 有効な4chを 7.0日以上へ補充した（10:08 run が適用、本 run で検算）。",
        "※ 2ch-matome / pokemon-lab は autopilot.enabled=false のため補充対象外（在庫 8.7 / 7.0日）。",
        "※ 維持率目標帯は現時点でコードから参照されていない（grep で参照0件）ため、動作への影響はなくドキュメント値として機能する。",
    ]:
        ws.cell(row=r, column=1, value=t).font = SMALL
        r += 1
    return ws


def sheet_recent(wb, d):
    ws = wb.create_sheet("直近動画一覧")
    r = title_block(ws, "直近動画一覧 — 2026-09-05 以降に公開した全動画", [
        "views=0 は YouTube Analytics の集計ラグ（公開から約2日）。実績ではない。",
    ])
    head(ws, r, ["チャンネル", "公開(UTC)", "タイトル", "再生", "いいね", "いいね率%",
                 "コメント", "登録", "登録/千再生", "維持率%", "平均視聴秒", "CTR", "状態"],
         [16, 17, 56, 8, 8, 10, 9, 7, 12, 9, 11, 8, 12])
    r += 1
    for v in sorted(d["recent"], key=lambda x: (x["ch"], x["pub"]), reverse=False):
        state = "未計測" if (v["views"] or 0) == 0 else "計測済"
        fill = GREY_FILL if state == "未計測" else None
        if state == "計測済" and v["views"] and v["subs"] * 1000.0 / v["views"] >= 1.0:
            fill = GOOD_FILL
        put(ws, r, [v["ch"], v["pub"], v["title"], v["views"], v["likes"],
                    f"=IFERROR(E{r}*100/D{r},0)", v["comments"], v["subs"],
                    f"=IFERROR(H{r}*1000/D{r},0)", v["avp"], v["dur"], v["ctr"], state],
            fmt={4: "#,##0", 6: "0.000", 9: "0.000", 10: "0.0", 11: "0.0", 12: "0.000"},
            fill=fill)
        r += 1
    r += 1
    ws.cell(row=r, column=1, value=(
        f"※ 計 {len(d['recent'])} 本。うち 09-13 以降公開の 25 本は全て未計測。"
        "09-14 の投稿枠・型ルール変更の効果はこの 25 本が計測されるまで判定できない。"
    )).font = SMALL
    r += 1
    ws.cell(row=r, column=1, value=(
        "※ 緑=登録/千再生 1.0以上（当該窓の上位）。灰=未計測。"
    )).font = SMALL
    return ws


def sheet_actions(wb, d):
    ws = wb.create_sheet("改善提案")
    r = title_block(ws, "改善提案 — 本日の判断と根拠", [
        "原則: 実データのみ。勘・一般論は採用しない。同一スナップショットで二度目の意思決定をしない。",
    ])

    ws.cell(row=r, column=1, value="■ A. 本日 適用済みの config 変更（10:08 の並走 run が適用・本 run で独立検算しコミット）").font = BOLD
    r += 1
    head(ws, r, ["対象", "変更内容", "根拠（実測）", "検算結果", "次判定日"],
         [17, 34, 60, 30, 12])
    r += 1
    rows_a = [
        ("daily-science / scp-lab / yokai-watch / company-facts",
         "テーマキュー補充（+3 / +3 / +1 / +2）在庫を 7.0日以上へ",
         "在庫 6.0 / 6.0 / 6.7 / 6.5日 → 補充後 7.0 / 7.0 / 7.0 / 7.0日。型は 09-14 にch内対照で確定した最良型を踏襲",
         "○ キュー件数を実ファイルで確認（21/21/21/28）。JSONパース正常", "—"),
        ("全6ch（socio-rx を除く）",
         "optimization.retention_target_band = 40-50%（policy: target_band_not_maximize）",
         "公開08-01以降・views≧200 のバンド別 登録/千: <30% 0.263 / 30-40 0.398 / 40-50 0.649 / 50-60 0.450 / 60-70 0.587 / >=70 0.258",
         "△ 頂点40-50%は再現。ただし『>=70%が最下位』は切り抜き交絡（下の C 参照）",
         "09-21"),
        ("投稿枠 / 型ルール / voice_style",
         "変更なし（据え置き）",
         "09-14 に全6chで変更済み。その後の公開25本は全て views=0 で未計測。同一データでの二重判断を回避",
         "○ 妥当。schedule/title_rules/voice_style の差分ゼロを git diff で確認", "09-21"),
    ]
    for a in rows_a:
        put(ws, r, list(a))
        for col in (2, 3, 4):
            ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 46
        r += 1
    r += 2

    ws.cell(row=r, column=1, value="■ B. 登録/千再生 の主説明変数 — いいね率（5回連続で再現）").font = BOLD
    r += 1
    head(ws, r, ["いいね率四分位", "本数", "総再生", "いいね率%", "登録数", "登録/千再生", "Q1比"],
         [16, 8, 11, 11, 9, 12, 9])
    r += 1
    qf = r
    for q in d["quartile"]:
        put(ws, r, [q["q"], q["n"], q["views"], f"=IFERROR(D{r},0)" if False else
                    f"=IFERROR({q['likes']}*100/{q['views']},0)", q["subs"],
                    f"=IFERROR(E{r}*1000/C{r},0)", f"=IFERROR(F{r}/$F${qf},0)"],
            fmt={3: "#,##0", 4: "0.000", 6: "0.000", 7: "0.00"},
            fill=GOOD_FILL if q["q"] == "Q4" else None)
        r += 1
    r += 1
    ws.cell(row=r, column=1, value=(
        "→ Q4/Q1 = 3.96倍。前日 run の 3.90倍を独立に再現（窓・条件は同一: 公開08-01以降・views≧200）。"
        "施策としては『いいね率を上げる打ち手＝登録を上げる打ち手』として扱ってよい。"
    )).font = BODY
    r += 3

    ws.cell(row=r, column=1, value="■ C. 【前日知見の修正】維持率の交絡 — 『>=70% は登録が伸びない』は切り抜き2chによる見かけ").font = BOLD
    r += 1
    head(ws, r, ["維持率バンド", "全13ch 本数", "全13ch 登録/千", "ゆっくり7ch 本数",
                 "ゆっくり7ch 登録/千", "差", "判定"], [14, 13, 15, 15, 17, 9, 34])
    r += 1
    yuk = {b["band"]: b for b in d["band_yuk"]}
    for b in d["band_all"]:
        y = yuk.get(b["band"], {})
        judge = ""
        if b["band"] == "40-50%":
            judge = "○ 両方で頂点。目標帯として妥当"
        elif b["band"] == ">=70%":
            judge = "× 全chでは最下位だが ゆっくりでは最下位でない"
        elif b["band"] == "<30%":
            judge = "○ ゆっくりでの真の最下位"
        put(ws, r, [b["band"], b["n"],
                    f"=IFERROR({b['subs']}*1000/{b['views']},0)", y.get("n", 0),
                    f"=IFERROR({y.get('subs', 0)}*1000/{y.get('views', 1) or 1},0)",
                    f"=IFERROR(E{r}-C{r},0)", judge],
            fmt={3: "0.000", 5: "0.000", 6: "0.000"},
            fill=GOOD_FILL if b["band"] == "40-50%" else
                 (WARN_FILL if b["band"] == ">=70%" else None))
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="【交絡の実体】維持率>=70% 帯の ch 構成（views 順）").font = BOLD
    r += 1
    head(ws, r, ["チャンネル", "本数", "総再生", "帯内シェア%", "登録", "登録/千"],
         [17, 8, 11, 13, 8, 11])
    r += 1
    total70 = sum(b["views"] for b in d["band_clip_share"]) or 1
    for b in d["band_clip_share"]:
        put(ws, r, [b["ch"], b["n"], b["views"], f"=IFERROR(C{r}*100/{total70},0)",
                    b["subs"], f"=IFERROR(E{r}*1000/C{r},0)"],
            fmt={3: "#,##0", 4: "0.0", 6: "0.000"},
            fill=WARN_FILL if b["ch"].startswith("clip") else None)
        r += 1
    r += 1
    for t in [
        "→ >=70% 帯の総再生 89,148 のうち clip-lab 30,690 + clip-fukada 21,011 + clip-kaneko 3,185 = 54,886（61.6%）が切り抜き系。",
        "→ 切り抜き系は維持率とは無関係に登録/千 0.137（ゆっくり系 0.533 の 1/3.9）。この構造差がバンド平均を押し下げていた。",
        "→ ゆっくり7chに限れば <30% 0.245 が最下位、40-50% 0.714 が頂点、50%以上は 0.51〜0.58 でほぼ平坦。",
        "【結論】『40-50% を目標帯にする』は妥当。『維持率が高すぎると登録が減る』は根拠不足につき撤回する。",
        "【次アクション】維持率を下げる方向の施策は打たない。09-21 の再判定で >=50% 帯を ch 内対照で再検証する（本日は config を触らない）。",
    ]:
        c = ws.cell(row=r, column=1, value=t)
        c.font = BODY
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 2

    ws.cell(row=r, column=1, value="■ D. 公開時刻別 登録/千再生（ゆっくり6ch・08-01以降・views≧200・n≧4）").font = BOLD
    r += 1
    head(ws, r, ["公開時刻(JST)", "本数", "総再生", "登録", "登録/千再生", "09-14変更後の採用状況", "判定"],
         [14, 8, 11, 8, 12, 30, 40])
    r += 1
    adopt = {
        17: "daily-science / scp-lab / company-facts が採用",
        19: "scp-lab / yokai-watch / company-facts が採用",
        12: "yokai-watch / company-facts / pokemon-lab / 2ch が採用",
        15: "daily-science / company-facts / pokemon-lab が採用",
        13: "scp-lab が採用",
        7: "daily-science / 2ch が採用",
        9: "採用なし（09-14 に全廃）",
        8: "採用なし（09-14 に全廃）",
        21: "採用なし（09-14 に全廃）",
        18: "採用なし",
        14: "採用なし",
    }
    for h in d["hour"]:
        spk = h["subs"] * 1000.0 / h["views"] if h["views"] else 0
        judge = ""
        if h["h"] == 17:
            judge = "◎ 最良 0.831(n=51)。採用は妥当"
        elif h["h"] == 15 and spk < 0.25:
            judge = "⚠ 0.169(n=7) と低いのに 3ch で採用。n が小さく判断保留だが 09-21 に必ず再検証"
        elif h["h"] in (9, 8, 21) :
            judge = "○ 全廃は妥当（0.48 / 0.37 / 0.00）"
        put(ws, r, [f"{h['h']}時", h["n"], h["views"], h["subs"],
                    f"=IFERROR(D{r}*1000/C{r},0)", adopt.get(h["h"], ""), judge],
            fmt={3: "#,##0", 5: "0.000"},
            fill=GOOD_FILL if h["h"] == 17 else (WARN_FILL if h["h"] == 15 else None))
        ws.cell(row=r, column=7).alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 2

    ws.cell(row=r, column=1, value="■ E. 人手が必要な未解決案件（エスカレーション）").font = BOLD
    r += 1
    head(ws, r, ["優先", "案件", "内容", "担当", "影響"], [6, 30, 62, 10, 40])
    r += 1
    for e in d["escalations"]:
        impact = {
            1: "「サムネ品質最優先」の改善が daily-science 以外の 9ch に一切届いていない。登録の主要ドライバを1つ失っている",
            2: "サムネ指示文（thumbnail_brief）と続編候補（series_engine）が生成されていない。両方とも登録に直結する導線",
            3: "6ch が fetch/公開の両方で停止。全13ch中 5ch のみが実質稼働",
            4: "09-13以降の 25 本が views=0 のまま。09-14 の施策評価が 09-21 まで不能",
        }.get(e["pri"], "")
        put(ws, r, [e["pri"], e["item"], e["detail"], e["owner"], impact],
            fill=WARN_FILL if e["pri"] <= 2 else None)
        for col in (3, 5):
            ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 46
        r += 1
    return ws


def sheet_compare(wb, d):
    ws = wb.create_sheet("前回比較")
    r = title_block(ws, "前回比較 — 前スナップショット比 と 前回施策の効果検証", [
        "比較は同一定義（各chの直近50本ローリング窓の累積合計）。窓の構成が入れ替わるため、"
        "総再生の減少は必ずしも実績悪化ではない。",
    ])

    ws.cell(row=r, column=1, value="■ 1. 前スナップショット比（至上指標 登録/千再生）").font = BOLD
    r += 1
    head(ws, r, ["チャンネル", "前回日", "今回日", "前回 登録/千", "今回 登録/千", "差",
                 "前回 いいね率%", "今回 いいね率%", "いいね率 差", "総再生 前回", "総再生 今回", "判定"],
         [17, 11, 11, 13, 13, 9, 14, 14, 13, 12, 12, 30])
    r += 1
    verdict = {
        "scp-lab": "◎ 改善。いいね率も同時上昇（整合）",
        "yokai-watch": "◎ 最速改善。いいね率 +0.032pt",
        "daily-science": "○ 改善。いいね率は全ch最高",
        "company-facts": "× 3日連続低下。いいね率も低下（整合）",
        "2ch-matome": "× 低下。停止中のため施策で動かせない",
    }
    for ch in ["scp-lab", "yokai-watch", "daily-science", "company-facts", "2ch-matome"]:
        cur = d["snap"].get(ch)
        pv = d["prev"].get(ch)
        if not cur or not pv:
            continue
        put(ws, r, [ch, pv["date"], cur["snap"],
                    f"=IFERROR({pv['subs']}*1000/{pv['views']},0)",
                    f"=IFERROR({cur['subs']}*1000/{cur['views']},0)",
                    f"=IFERROR(E{r}-D{r},0)",
                    f"=IFERROR({pv['likes']}*100/{pv['views']},0)",
                    f"=IFERROR({cur['likes']}*100/{cur['views']},0)",
                    f"=IFERROR(H{r}-G{r},0)", pv["views"], cur["views"],
                    verdict.get(ch, "")],
            fmt={4: "0.000", 5: "0.000", 6: "+0.000;-0.000;0.000", 7: "0.000", 8: "0.000",
                 9: "+0.000;-0.000;0.000", 10: "#,##0", 11: "#,##0"},
            fill=GOOD_FILL if ch in ("scp-lab", "yokai-watch", "daily-science") else WARN_FILL)
        r += 1
    r += 2

    ws.cell(row=r, column=1, value="■ 2. 登録/千再生 の6日推移（09-08 → 09-14・同一定義）").font = BOLD
    r += 1
    dates = ["2026-09-08", "2026-09-13", "2026-09-14"]
    head(ws, r, ["チャンネル"] + dates + ["09-08→09-14 差", "トレンド"],
         [17, 13, 13, 13, 15, 26])
    r += 1
    for ch in ["scp-lab", "yokai-watch", "daily-science", "company-facts", "2ch-matome"]:
        vals = []
        for dt in dates:
            row = next((x for x in d["hist"].get(ch, []) if x["date"] == dt), None)
            vals.append(row["subs"] * 1000.0 / row["views"] if row and row["views"] else None)
        trend = "上昇" if (vals[0] is not None and vals[-1] is not None and vals[-1] > vals[0]) else "下降"
        put(ws, r, [ch] + [round(v, 3) if v is not None else "n/a" for v in vals] +
                   [f"=IFERROR(D{r}-B{r},0)", trend],
            fmt={2: "0.000", 3: "0.000", 4: "0.000", 5: "+0.000;-0.000;0.000"},
            fill=GOOD_FILL if trend == "上昇" else WARN_FILL)
        r += 1
    r += 2

    ws.cell(row=r, column=1, value="■ 3. 前回施策の効果検証（差分検証）").font = BOLD
    r += 1
    head(ws, r, ["実施日", "対象", "施策", "前回判定", "本日の判定", "根拠", "次アクション"],
         [10, 22, 30, 12, 12, 54, 34])
    r += 1
    rows = [
        ("09-12", "scp-lab", "autopilot 週7日化（週15→21本）", "△ 未測定", "△ 未測定継続",
         "09-13以降 6本公開・全て views=0。稼働は確認できたが登録効果は不明",
         "09-21 に n≧20 で再判定"),
        ("09-12", "company-facts", "投稿枠 3→4（週21→28本）", "△ 未測定", "× 疑わしい",
         "枠増後の 登録/千 は 0.715(09-08)→0.649(09-13)→0.619(09-14) と単調低下。"
         "総再生は最大だが登録変換が落ちている。本数を増やして1本あたりの質が落ちた可能性",
         "09-21 に枠を4→3へ戻す案を検討。本日は据え置き"),
        ("09-13", "8ch", "autopilot 無効化（5ch集中）", "○ 成立", "○ 成立",
         "09-13以降 25本を5chで安定公開。停止8chの指標は据え置きのまま悪化なし",
         "継続"),
        ("09-13", "company-facts", "毎日投稿化", "○ 成立", "○ 成立（ただし §2 の懸念）",
         "09-13に3本・09-14に4本。週3日制約は解けている",
         "本数と登録変換のトレードオフを 09-21 に検証"),
        ("09-14", "全6ch", "投稿枠を 17時中心へ再編・9/8/21時を全廃", "—", "△ 方向は妥当",
         "17時枠は 0.831(n=51) で最良、廃止した 9時 0.483 / 8時 0.366 / 21時 0.000。"
         "ただし新設した 15時枠は 0.169(n=7) と低い",
         "15時枠を 09-21 に必ず再検証。n が小さいので今は動かさない"),
        ("09-14", "全6ch", "ch別タイトル型ルールの固定", "—", "△ 未測定",
         "型変更後に公開した25本が全て未計測。ただし型を据え置いたまま "
         "登録/千が3ch改善しているのは既存在庫の効果",
         "09-21 に ch 内対照で再判定"),
        ("09-14", "title_constraints", "repair() に forbid_patterns 対応を追加", "—", "○ 成立",
         "09-14以降に公開した 25本のタイトルに forbid_patterns 違反（99%型・絵文字）は無い",
         "継続。ゲート検知後に公開を止める分岐の追加は別課題として残る"),
        ("09-15", "全6ch", "維持率目標帯 40-50% を明記", "—", "△ 一部修正要",
         "頂点40-50%は再現したが『>=70%が最下位』は切り抜き交絡。"
         "なお当該キーはコードから参照されていないため実害なし",
         "維持率を下げる施策は打たない。09-21 に ch 内対照で再検証"),
    ]
    for a in rows:
        put(ws, r, list(a))
        for col in (3, 6, 7):
            ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 44
        r += 1
    r += 2

    ws.cell(row=r, column=1, value="■ 4. 未計測ストック（09-13以降公開・評価対象外）").font = BOLD
    r += 1
    head(ws, r, ["チャンネル", "本数", "計測済 再生", "状態"], [17, 8, 12, 40])
    r += 1
    for u in d["unmeasured"]:
        put(ws, r, [u["ch"], u["n"], u["views"], "未計測（Analytics ラグ約2日＋バックフィル未実行）"],
            fill=GREY_FILL)
        r += 1
    put(ws, r, ["合計", sum(u["n"] for u in d["unmeasured"]),
                sum(u["views"] for u in d["unmeasured"]), "09-21 に評価可能になる見込み"],
        font=BOLD, fill=GREY_FILL)
    return ws


def main():
    d = fetch()
    with open(os.path.join(REPO, "reports", "orch_config_changes_20260915.json"),
              encoding="utf-8") as f:
        cc = json.load(f)
    d["changes"] = {k: v for k, v in cc["channels"].items() if v.get("queue_added")}
    d["escalations"] = cc["escalations"]

    wb = Workbook()
    wb.remove(wb.active)
    sheet_summary(wb, d)
    sheet_channels(wb, d)
    sheet_recent(wb, d)
    sheet_actions(wb, d)
    sheet_compare(wb, d)
    for ws in wb:
        ws.freeze_panes = "A2"
    wb.save(OUT)
    print("saved:", OUT)
    print("sheets:", wb.sheetnames)


if __name__ == "__main__":
    main()
