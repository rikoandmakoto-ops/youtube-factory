#!/usr/bin/env python3
"""2026-09-16 指揮者レポート xlsx。数値は式で持たせる（ハードコード結果を置かない）。"""
import json, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

D = json.load(open('reports/_orch_20260916_data.json'))
CH = D['channels']; CFG = D['configs']
ORDER = ['scp-lab','daily-science','yokai-watch','company-facts','2ch-matome','socio-rx',
         'pokemon-lab','fake-paper','akashic-librarian','clip-lab','clip-fukada',
         'clip-kaneko','clip-animal']
F = 'Arial'
H1 = Font(name=F, size=14, bold=True); H2 = Font(name=F, size=11, bold=True)
NB = Font(name=F, size=10); BLD = Font(name=F, size=10, bold=True)
HDRF = PatternFill('solid', fgColor='1F3864')
HDRT = Font(name=F, size=10, bold=True, color='FFFFFF')
WARN = PatternFill('solid', fgColor='FFF2CC'); BAD = PatternFill('solid', fgColor='FCE4EC')
GOOD = PatternFill('solid', fgColor='E2EFDA'); GREY = PatternFill('solid', fgColor='F2F2F2')
THIN = Border(*[Side(style='thin', color='BFBFBF')] * 4)
wb = openpyxl.Workbook()


def hdr(ws, row, cols, widths=None):
    for i, t in enumerate(cols, 1):
        c = ws.cell(row=row, column=i, value=t); c.font = HDRT; c.fill = HDRF
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = THIN
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 30


def put(ws, r, c, v, font=None, fmt=None, fill=None, wrap=False):
    x = ws.cell(row=r, column=c, value=v); x.font = font or NB
    if fmt: x.number_format = fmt
    if fill: x.fill = fill
    if wrap: x.alignment = Alignment(wrap_text=True, vertical='top')
    x.border = THIN
    return x


def widths(ws, ws_widths):
    for i, w in enumerate(ws_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


# ============ 1. サマリ ============
ws = wb.active; ws.title = 'サマリ'
widths(ws, [13, 12, 9, 12, 7, 10, 10, 9, 12, 9, 11, 9, 11])
put(ws, 1, 1, 'YouTube Factory 指揮者レポート  2026-09-16（水）', H1)
put(ws, 2, 1, 'データ源: data/analytics/analytics.db（YouTube Analytics API）。'
              'ブラウザ収集・APIキーは使用していない。', NB)
put(ws, 3, 1, f"生成: {D['generated_at']}  /  "
              "最新スナップショット: 2026-09-15 22:30–22:41 JST fetch", NB)

r = 5
put(ws, r, 1, '■ 本日の結論', H2); r += 1
concl = [
 '1. 新規データは 09-15 22:41 の fetch 1本ぶん。稼働6chのみ更新（他7chは 09-06〜09-08 で停止＝OAuth invalid_grant）。',
 '2. 【鉄則】同一スナップショットでの二重判断を避けるため、実績ベースの config 変更は本 run では行わない。'
 ' 10:10 の並走 run が Phase 3 を先に消費している（reports/orch_config_changes_20260916.json が存在）。並走は3日連続。',
 '3. ★本日の最大の発見★ いいね率の「6回連続の単調関係」は ch 内対照では成り立っていない。'
 ' プール4分位は Q2 0.537 > Q3 0.488 で単調が崩れ（Q4/Q1 も 3.96→3.19 倍に低下）、'
 ' ch 内中央値二分では 3/5ch のみ一致（company-facts と 2ch-matome が逆）。シンプソンのパラドックス4例目の候補。',
 '4. ★入れ替わり★ 代わりに維持率が ch 内対照で 09-13/14/15 の3スナップショット連続 5/5ch 一致した。'
 ' 09-08 時点は逆（いいね率 5/5・維持率 3/5）。ただし連続スナップショットは同一動画が約95%重なり自己相関するため、'
 ' 独立性のある比較点は 09-08 と 09-15 の2つだけ。「維持率は判断に使わない」という現行の鉄則は根拠が弱くなったが、撤回はせず 09-21 に独立コホートで再判定する。',
 '5. 維持率バンドの頂点 40-50%（0.687）は3日連続で再現。<30% が最下位（0.245）も再現。09-15 の訂正版の結論は堅い。',
 '6. 17時枠 0.932（n=38）が再び最良で 09-14 の枠再編は妥当。一方 15時枠は 0.000（n=4）へ悪化（前日 0.169/n=7）。'
 ' ただし 09-14 以降の15時公開分は全て未計測なので、これは変更前の母集団しか見ていない。',
 '7. 09-07以降の公開 85本中 54本が依然 views=0（反映ラグ実測2日）。09-14 の枠/型変更の本判定は変わらず 09-21。',
 '8. 【Act 実行】09-15 夜メモが本 run へ申し送った仕様判断を実行した — scp-lab / pokemon-lab の'
 ' max_digit_groups を 1→2（コミット fb2eee6）。題材名の数字がゲート枠を使い切る構造的衝突で、09-15 に実際に1枠を捨てていた。',
 '9. 人手案件3件（OAuth 09-20失効 / サムネ403 / Anthropic APIキー401）はいずれも未解消。'
 ' とくに OAuth は 09-20 昼に稼働6chが一斉失効する確定予定で、残り4日。',
]
for t in concl:
    put(ws, r, 1, t, NB, wrap=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=13)
    ws.row_dimensions[r].height = 28 if len(t) < 110 else 44
    r += 1

r += 1
put(ws, r, 1, '■ チャンネル別 実績（各chの最新スナップショット・直近50本ローリング窓・30日窓の累積）', H2); r += 1
hdr(ws, r, ['チャンネル', '名称', '系統', 'スナップ', '本数', '総再生', '平均再生', '登録者',
            '登録/千再生', 'いいね数', 'いいね率%', 'コメント', '平均維持率%']); r += 1
first = r
for ch in ORDER:
    if ch not in CH: continue
    x = CH[ch]; a = x['cur']
    put(ws, r, 1, ch, BLD); put(ws, r, 2, x['name']); put(ws, r, 3, x['system'])
    put(ws, r, 4, x['snap'], NB, fill=WARN if x['stale'] else None)
    put(ws, r, 5, a['n']); put(ws, r, 6, a['views'], NB, '#,##0')
    put(ws, r, 7, f'=IFERROR(F{r}/E{r},0)', NB, '#,##0.0')
    put(ws, r, 8, a['subs'])
    put(ws, r, 9, f'=IFERROR(H{r}*1000/F{r},0)', BLD, '0.000')
    put(ws, r, 10, a['likes'])
    put(ws, r, 11, f'=IFERROR(J{r}*100/F{r},0)', NB, '0.000')
    put(ws, r, 12, a['comments']); put(ws, r, 13, a['avp'], NB, '0.0')
    r += 1
last = r - 1
put(ws, r, 1, '合計 / 全13ch', BLD, fill=GREY)
for col in (2, 3, 4, 13):
    put(ws, r, col, '', NB, fill=GREY)
put(ws, r, 5, f'=SUM(E{first}:E{last})', BLD, '#,##0', GREY)
put(ws, r, 6, f'=SUM(F{first}:F{last})', BLD, '#,##0', GREY)
put(ws, r, 7, f'=IFERROR(F{r}/E{r},0)', BLD, '#,##0.0', GREY)
put(ws, r, 8, f'=SUM(H{first}:H{last})', BLD, '#,##0', GREY)
put(ws, r, 9, f'=IFERROR(H{r}*1000/F{r},0)', BLD, '0.000', GREY)
put(ws, r, 10, f'=SUM(J{first}:J{last})', BLD, '#,##0', GREY)
put(ws, r, 11, f'=IFERROR(J{r}*100/F{r},0)', BLD, '0.000', GREY)
put(ws, r, 12, f'=SUM(L{first}:L{last})', BLD, '#,##0', GREY)
r += 2
for t in ['※ 黄色のスナップ日 = 09-15 より古い（OAuth 失効で fetch 停止中）。その ch の数値は当該日時点の値で、本日の実績ではない。',
          '※ 総再生の前日比は指標にならない（窓が固定50本なので新規公開が入ると古い高再生本が落ちる）。判断は 登録/千再生 で行う。',
          '※ video_metrics の views / subscribers_gained は「直近30日窓」の値（fetch_video_metrics の days=30）。生涯累計ではない。']:
    put(ws, r, 1, t, NB); r += 1
r += 1

put(ws, r, 1, '■ 系統別（3分類）', H2); r += 1
hdr(ws, r, ['系統', 'ch数', '本数', '総再生', '登録', '登録/千再生', 'いいね率%']); r += 1
sysrow = {}
for k, v in D['systems'].items():
    put(ws, r, 1, k, BLD); put(ws, r, 2, v['nch']); put(ws, r, 3, v['n'])
    put(ws, r, 4, v['views'], NB, '#,##0'); put(ws, r, 5, v['subs'])
    put(ws, r, 6, f'=IFERROR(E{r}*1000/D{r},0)', BLD, '0.000')
    put(ws, r, 7, f'=IFERROR({v["likes"]}*100/D{r},0)', NB, '0.000')
    sysrow[k] = r; r += 1
put(ws, r, 1, f"{D['system_ratio']['label']} =", BLD)
put(ws, r, 2, f"=IFERROR(F{sysrow['ゆっくり系']}/F{sysrow['切り抜き系']},0)", BLD, '0.00"倍"')
put(ws, r, 3, '倍率は窓とch構成で必ず変わる。分子と分母で同じ分類を使うこと'
              '（09-12 4.58倍/3ch・09-13 4.56倍/4ch・09-14 4.81倍・09-15 4.72倍）', NB)
r += 2

put(ws, r, 1, '■ いいね率4分位 × 登録/千（稼働5ch・views≧200・09-15と同一母集団）', H2); r += 1
hdr(ws, r, ['四分位', '本数', 'いいね率%', '総再生', '登録', '登録/千再生', '判定']); r += 1
qf = r
for q in D['like_quartiles']:
    put(ws, r, 1, q['q'], BLD); put(ws, r, 2, q['n'])
    put(ws, r, 3, f'=IFERROR({q["likes"]}*100/D{r},0)', NB, '0.000')
    put(ws, r, 4, q['views'], NB, '#,##0'); put(ws, r, 5, q['subs'])
    put(ws, r, 6, f'=IFERROR(E{r}*1000/D{r},0)', BLD, '0.000')
    r += 1
put(ws, qf, 7, 'Q2 > Q3 で単調が崩れた（6回連続の単調関係は本日で途切れ）', NB, fill=BAD)
put(ws, qf + 1, 7, 'Q4/Q1 は 3.96倍(09-15) → 3.19倍 に低下', NB, fill=WARN)
put(ws, r, 1, 'Q4/Q1 =', BLD)
put(ws, r, 2, f'=IFERROR(F{qf+3}/F{qf},0)', BLD, '0.00"倍"')
put(ws, r, 3, '方向（高いほど良い）は保つが単調性は崩れた。ch内対照では 3/5ch のみ一致'
              ' →「チャンネル別詳細」シート下部を参照', NB)

# ============ 2. チャンネル別詳細 ============
ws = wb.create_sheet('チャンネル別詳細')
widths(ws, [16, 10, 26, 6, 10, 9, 12, 11, 12, 10, 26, 36])
put(ws, 1, 1, 'チャンネル別詳細 — 実績・在庫・本日の config', H1)
put(ws, 2, 1, '投稿枠 / 型ルール / voice_style は 09-14 に変更済み。'
              '本日は据え置き（実績ベース変更は 10:10 の並走 run が消費）。', NB)
r = 4
hdr(ws, r, ['チャンネル', 'autopilot', '投稿枠(JST)', '枠数', 'キュー本数', '在庫日数',
            '登録/千再生', 'いいね率%', '平均維持率%', 'mdg違反', '本日の変更',
            '評価 / 次アクション']); r += 1
EVAL = {
 'scp-lab': ('mdg 1→2（本 run）',
   '○ 5ch中最良 0.854（-0.009）。同一動画のみでは +961再生で実質は伸びている。'
   'mdg 1→2 で枠落ちを解消したので 09-17 以降の枠到達率を見る。'),
 'daily-science': ('変更なし',
   '◎ 0.725（+0.062）で本日の最大改善。いいね率 0.755% は全ch最高。'
   'サムネ403が通っている唯一の ch である点は、サムネ品質が効いている可能性を示す（403解消後に他chで検証できる）。'),
 'yokai-watch': ('変更なし',
   '○ 0.791（+0.004）。7日で +0.328 と最速。ch内対照でいいね率・維持率とも○で最も素直な ch。'),
 'company-facts': ('変更なし',
   '△ 0.613（-0.006）で4日連続低下。総再生は全ch最大(48,901)なのに登録変換だけ落ち続けている。'
   '枠3→4 の増枠が疑わしい。ch内対照でいいね率が×。09-21 に 4→3 差し戻しを判断。'),
 '2ch-matome': ('autopilot false→true（並走 run）',
   '× 0.163（+0.011）で最下位。ch内対照ではいいね率が3スナップショット連続で逆（いいね率が高い本ほど登録が少ない）。'
   '本 ch にいいね率ベースの施策を当てても効かない。'),
 'socio-rx': ('変更なし',
   '－ 公開4本・260再生・登録0。ゲートは付いたが retention_target_band は未設定。母数が足りず判断不能。'),
 'pokemon-lab': ('mdg 1→2（本 run）',
   '－ 09-08 以降 fetch 停止（OAuth invalid_grant）。種族値が構造的に数字2個になるため mdg を先に 2 へ。'
   '再開時の枠落ちを潰した。'),
 'fake-paper': ('変更なし', '× 登録0人 / 7,047再生。停止中。据え置き。'),
 'akashic-librarian': ('変更なし',
   '－ OAuth未連携。0.570 は 09-06 の値。登録/千は全ch3位なので再認可の優先度は高い（実力で切った ch ではない）。'),
 'clip-lab': ('変更なし', '× 0.024。総再生42,321は3位だが登録1人。切り抜きは再生が登録に変換されない構造。'),
 'clip-fukada': ('変更なし', '× 0.211。CTR 6.29% は全ch1位なのに登録/千は下位＝CTRは目的関数ではない実例。'),
 'clip-kaneko': ('変更なし', '× 0.169。停止中。'),
 'clip-animal': ('変更なし', '× 3本・17再生。実質未稼働。ゲート未設定のまま（稼働させるなら先に付与）。'),
}
for ch in ORDER:
    if ch not in CH: continue
    x = CH[ch]; a = x['cur']; g = CFG[ch]
    put(ws, r, 1, ch, BLD)
    put(ws, r, 2, '有効' if g['enabled'] else '停止', NB,
        fill=GOOD if g['enabled'] else GREY)
    put(ws, r, 3, ' / '.join(g['slots'])); put(ws, r, 4, g['nslots'])
    put(ws, r, 5, g['queue'])
    put(ws, r, 6, f'=IFERROR(E{r}/D{r},0)', NB, '0.0', WARN if g['stock'] < 7 else None)
    put(ws, r, 7, f'=IFERROR({a["subs"]}*1000/{a["views"]},0)' if a['views'] else 0, BLD, '0.000')
    put(ws, r, 8, f'=IFERROR({a["likes"]}*100/{a["views"]},0)' if a['views'] else 0, NB, '0.000')
    put(ws, r, 9, a['avp'], NB, '0.0')
    put(ws, r, 10, g['mdg_viol'], NB, fill=BAD if g['mdg_viol'] else GOOD)
    put(ws, r, 11, EVAL[ch][0], NB, wrap=True)
    put(ws, r, 12, EVAL[ch][1], NB, wrap=True)
    ws.row_dimensions[r].height = 48
    r += 1
r += 1
for t in ['※ 在庫日数 = キュー本数 ÷ 1日あたり投稿枠数。黄色 = 7日未満。'
          '09-15 に4chを 7.0日へ補充したが24時間で 5.7〜6.0日まで落ちた＝補充が消費に追いついていない。',
          '※ mdg違反 = 未使用キューのうち max_digit_groups を超えるタイトル件数。'
          'publish_blocked により、この件数がそのまま「捨てる枠」になる。',
          '※ 2ch-matome / pokemon-lab の autopilot は 09-13 の5ch集中運用で停止したもの。'
          '並走 run が 2ch-matome を 09-16 に再有効化した。',
          '※ company-facts の top-level days_of_week が [3,4,5] に戻っている'
          '（auto_optimize_schedule による書き換え）。各スロットが [0..6] を持つ間は無害。']:
    put(ws, r, 1, t, NB); r += 1

r += 1
put(ws, r, 1, '■ ch内対照（鉄則準拠・中央値二分）— プール集計では見えない符号の食い違い', H2); r += 1
put(ws, r, 1, '各chの中で「いいね率が高い半分」と「維持率が高い半分」の登録/千を、'
              '4つのスナップショットで独立に測った。○ = 高い側の方が登録/千も高い（期待どおり）', NB); r += 1
hdr(ws, r, ['スナップ', 'チャンネル', '本数', 'いいね率 低位半', 'いいね率 高位半',
            'いいね率 判定', '維持率 低位半', '維持率 高位半', '維持率 判定']); r += 1
for sd, res in D['within_ch'].items():
    for ch, v in res.items():
        if not v: continue
        put(ws, r, 1, sd); put(ws, r, 2, ch, BLD); put(ws, r, 3, v['n'])
        put(ws, r, 4, v['like_lo'], NB, '0.000'); put(ws, r, 5, v['like_hi'], NB, '0.000')
        put(ws, r, 6, '○' if v['like_ok'] else '×', BLD,
            fill=GOOD if v['like_ok'] else BAD)
        put(ws, r, 7, v['ret_lo'], NB, '0.000'); put(ws, r, 8, v['ret_hi'], NB, '0.000')
        put(ws, r, 9, '○' if v['ret_ok'] else '×', BLD,
            fill=GOOD if v['ret_ok'] else BAD)
        r += 1
    lk = sum(1 for v in res.values() if v and v['like_ok'])
    rt = sum(1 for v in res.values() if v and v['ret_ok'])
    tot = sum(1 for v in res.values() if v)
    put(ws, r, 1, f'{sd} 小計', BLD, fill=GREY)
    for col in (2, 3, 4, 5, 7, 8):
        put(ws, r, col, '', NB, fill=GREY)
    put(ws, r, 6, f'{lk}/{tot}ch', BLD, fill=GREY)
    put(ws, r, 9, f'{rt}/{tot}ch', BLD, fill=GREY)
    r += 1
put(ws, r, 1, '⚠ 連続スナップショットは同一動画が約95%重なるため独立な標本ではない。'
              '独立性が高いのは 09-08 と 09-15 の2点のみで、そこで符号が入れ替わっている'
              '（09-08: いいね率5/5・維持率3/5 → 09-15: いいね率3/5・維持率5/5）。', NB, fill=WARN)
r += 1
put(ws, r, 1, '⚠ よって「維持率のほうが信頼できる」と結論づけるのは早い。'
              '現行の鉄則（いいね率を先行指標にする / 維持率は判断に使わない）は撤回せず、'
              '09-21 に独立コホートで再判定する。', NB, fill=WARN)

# ============ 3. 直近動画一覧 ============
ws = wb.create_sheet('直近動画一覧')
widths(ws, [15, 17, 52, 9, 8, 10, 8, 7, 12, 9, 9, 10, 14, 8])
put(ws, 1, 1, '直近動画一覧 — 2026-09-07 以降に公開（JST換算）', H1)
put(ws, 2, 1, f"views=0 は YouTube Analytics の反映ラグ（実測約2日）。公開失敗ではない。"
              f"{len(D['videos'])}本中 {D['videos_zero']}本が未計測。", NB)
r = 4
hdr(ws, r, ['チャンネル', '公開(JST)', 'タイトル', '再生', 'いいね', 'いいね率%', 'コメント',
            '登録', '登録/千再生', '維持率%', 'CTR%', '表示回数', '状態', '数字個数']); r += 1
for v in D['videos']:
    put(ws, r, 1, v['ch']); put(ws, r, 2, v['pub_jst']); put(ws, r, 3, v['title'])
    put(ws, r, 4, v['views'], NB, '#,##0'); put(ws, r, 5, v['likes'])
    put(ws, r, 6, f'=IFERROR(E{r}*100/D{r},0)', NB, '0.000')
    put(ws, r, 7, v['comments']); put(ws, r, 8, v['subs'])
    put(ws, r, 9, f'=IFERROR(H{r}*1000/D{r},0)', BLD, '0.000')
    put(ws, r, 10, v['avp'], NB, '0.0'); put(ws, r, 11, v['ctr'] * 100, NB, '0.00')
    put(ws, r, 12, v['imp'], NB, '#,##0')
    put(ws, r, 13, v['state'], NB, fill=WARN if v['views'] == 0 else GOOD)
    put(ws, r, 14, v['digits'])
    r += 1
r += 1
put(ws, r, 1, '※ CTR は表示回数ベースで窓が整合しないため参考値（正しくは video_reach_daily から出す）。', NB); r += 1
put(ws, r, 1, '※ 数字個数 = タイトル内の数字グループ数。scp-lab は題材名 SCP-#### が1つ消費するため、'
              '本日 max_digit_groups を 2 に上げた。', NB)

# ============ 4. 改善提案 ============
ws = wb.create_sheet('改善提案')
widths(ws, [22, 30, 44, 36, 12])
put(ws, 1, 1, '改善提案 — 本日の判断と根拠', H1)
put(ws, 2, 1, '原則: 実データのみ。勘・一般論は採用しない。同一スナップショットで二重に判断しない。', NB)
r = 4
put(ws, r, 1, '■ A. 本日 適用した config 変更', H2); r += 1
hdr(ws, r, ['対象', '変更内容', '根拠（実測）', '検算結果', '次判定日']); r += 1
A_ = [
 ('scp-lab', 'max_digit_groups 1 → 2',
  'キュー 5/17(29%) が違反。公開済み 209本中 112本(54%) が現ルールでは公開不能。'
  '09-15 に publish_blocked が実際に1枠を捨てた（SCP-2718 + 31分）。'
  '数字個数と登録/千は ch 内で無相関（1個 0.863 n=18 / 2個 0.673 n=10 / 3個 1.055 n=3）',
  '○ mdg=2 でキュー違反 0件。回帰 19 failed / 642 passed / 4 errors = HEAD と同一（無退行を実測）',
  '09-17 枠到達率'),
 ('pokemon-lab', 'max_digit_groups 1 → 2',
  '種族値（防御5・HP250 等）が構造的に数字2個。キュー 5/21(24%) が違反。'
  '停止中だが再開時に同じ枠落ちを起こす',
  '○ mdg=2 でキュー違反 0件', '再開時'),
 ('実績ベースの変更', '行わない（鉄則）',
  '10:10 の並走 run が同一スナップショット(09-15 22:41)で Phase 3 を消費済み。'
  'reports/orch_config_changes_20260916.json が存在',
  '○ 投稿枠 / title_rules（mdg 以外）/ voice_style / theme_queue に本 run からの差分ゼロ', '—'),
 ('並走 run の変更（検算のみ）',
  '評価期日 09-17→09-23 / retention_note 追加 / 2ch-matome autopilot 有効化',
  '並走 run の判断。本 run は独立検算のみ',
  '△ 2ch-matome の再有効化は実績根拠が薄い（登録/千 0.163 で最下位・ch内でいいね率が3スナップショット連続逆）。'
  'ただし停止の理由に OAuth と実力が混在しているので再開自体は否定しない', '09-23'),
]
for a in A_:
    for i, t in enumerate(a, 1):
        put(ws, r, i, t, NB, wrap=True)
    ws.row_dimensions[r].height = 80
    r += 1

r += 1
put(ws, r, 1, '■ B. 次回以降に判断する（本日は根拠不足で保留）', H2); r += 1
hdr(ws, r, ['対象', '提案', '根拠（実測）', '保留の理由', '判断予定日']); r += 1
B_ = [
 ('company-facts', '投稿枠 4 → 3 へ差し戻し',
  '登録/千が 0.715→0.649→0.619→0.613 と4日連続低下。'
  '総再生は全ch最大(48,901)なのに変換だけ落ちている。ch内対照でいいね率も×',
  '枠増後に公開した分が全て未計測。増枠の効果とテーマ疲れの切り分けができない', '09-21'),
 ('daily-science / company-facts', '15時枠を 17時 / 19時へ寄せ直す',
  '15時 0.000(n=4)・前日 0.169(n=7) で最下位。17時 0.932(n=38) / 19時 0.672(n=24) が上位',
  'n=4 と小さく、かつ 09-14 新設後の15時公開分は全て未計測＝変更前の母集団しか見ていない', '09-21'),
 ('全6ch', 'いいね率の「先行指標」としての扱いを見直す',
  'プール4分位の単調性が本日崩れた（Q2 0.537 > Q3 0.488・Q4/Q1 3.96→3.19倍）。'
  'ch内対照では 3/5ch のみ一致で company-facts・2ch-matome が逆',
  '連続スナップショットは同一動画95%重複で自己相関する。独立な比較点は 09-08 と 09-15 の2つだけ', '09-21'),
 ('2ch-matome', 'いいね率ベースの施策を外す（ch単独で符号が逆）',
  '09-13/14/15 の3スナップショットすべてで、いいね率が高い半分の方が登録/千が低い'
  '（0.221→0.125 / 0.228→0.093 / 0.258→0.095）',
  '3点とも同一動画が重なる標本。独立性のある 09-08 では○だった', '09-21'),
 ('socio-rx', 'retention_target_band の付与',
  '他6chには付与済みだが socio-rx のみ未設定。公開4本・260再生で母数不足',
  'そもそも当該キーはコードから参照されていない（実害なし）。母数が n≧20 に届いてから', '09-23'),
]
for b in B_:
    for i, t in enumerate(b, 1):
        put(ws, r, i, t, NB, wrap=True)
    ws.row_dimensions[r].height = 76
    r += 1

r += 1
put(ws, r, 1, '■ C. 人手が必要な未解決案件（自動化不可・本日も未解消）', H2); r += 1
hdr(ws, r, ['優先', '案件', '実測の状態', '影響', '必要な操作']); r += 1
C_ = [
 ('1', 'OAuth 09-20 失効（残り4日）',
  'ログに確定値「失効予定 2026-09-20 12:05:39」。同意画面が「テスト中」のため7日で失効する仕様',
  '稼働6chが一斉に停止する。09-09〜09-12 の4日連続データ欠損が再発する',
  'GCP project 844705815004 の同意画面を「テスト中」→「本番」へ公開し、そのあと再認可'),
 ('2', 'カスタムサムネイル 403（5日連続）',
  '通っているのは daily-science のみ。scp-lab / yokai-watch / company-facts は全件 403',
  '「サムネ品質最優先」の改善が9chに1枚も届いていない。'
  'daily-science が本日の最大改善 ch であることは、サムネが効いている可能性を示す',
  'youtube.com/verify で電話番号確認'),
 ('3', 'Anthropic APIキー 401',
  'backend/.env 18行目に108文字の値が入った状態で 401。入れ忘れではなくキー自体が無効',
  'thumbnail_brief / trend_relevance / series_engine が全ch で停止。続編候補が生成されない',
  'キーの貼り直し'),
 ('4', 'OAuth 未再認可 7ch',
  'clip-animal / fake-paper / akashic-librarian / clip-fukada / clip-kaneko / clip-lab / '
  'pokemon-lab が invalid_grant',
  '13ch中6chしか実質稼働していない。akashic-librarian は登録/千 0.570 で全ch3位なので損失が大きい',
  '同意画面の本番公開後にまとめて再認可'),
 ('5', 'テーマキュー在庫の目減り',
  '09-15 に4chを 7.0日へ補充したが24時間で 5.7〜6.0日へ。本 run では補充しない（Phase 3 消費済み）',
  '今のペースだと 09-21 前後に在庫が枯れて枠が空く',
  '（自動）次 run で補充。並走 run が補充しない場合は指揮者が入れる'),
]
for x in C_:
    for i, t in enumerate(x, 1):
        put(ws, r, i, t, NB, wrap=True)
    ws.row_dimensions[r].height = 76
    r += 1

r += 1
put(ws, r, 1, '■ D. 公開時刻(JST)別 登録/千 — 稼働6ch・公開08-01以降・views≧200', H2); r += 1
hdr(ws, r, ['時刻', '本数', '総再生', '登録', '登録/千再生', '判定']); r += 1
JUDGE = {17: '◎ 最良。09-14 の枠再編は妥当', 19: '○ 2番目', 12: '○',
         15: '⚠ 最下位 0.000。09-14 に3chへ新設したが、変更後の公開分は未計測',
         18: '× 採用なしは妥当', 21: '× 採用なしは妥当', 13: '△ scp-lab が使用中',
         9: '○ 全廃は妥当', 7: '△ daily-science / 2ch が使用中', 8: '○ 全廃は妥当',
         14: '× 採用なし'}
for h in D['by_hour']:
    if h['n'] < 3: continue
    put(ws, r, 1, f"{h['hour']}時", BLD); put(ws, r, 2, h['n'])
    put(ws, r, 3, h['views'], NB, '#,##0'); put(ws, r, 4, h['subs'])
    put(ws, r, 5, f'=IFERROR(D{r}*1000/C{r},0)', BLD, '0.000')
    put(ws, r, 6, JUDGE.get(h['hour'], ''), NB, fill=WARN if h['hour'] == 15 else None)
    r += 1
put(ws, r, 1, '※ n<3 の時刻は除外。※ この表は ch をプールしているため系統・ch実力差で交絡する（鉄則）。'
              '時刻の採否は ch 内対照で最終判断する。', NB)

# ============ 5. 前回比較 ============
ws = wb.create_sheet('前回比較')
widths(ws, [15, 12, 12, 12, 12, 10, 12, 12, 11, 10, 14, 30])
put(ws, 1, 1, '前回比較 — 前スナップショット比 と 前回施策の効果検証', H1)
put(ws, 2, 1, '比較は同一定義（各chの直近50本ローリング窓）。'
              '前回レポート: reports/youtube-analysis-2026-09-15.xlsx', NB)
r = 4
put(ws, r, 1, '■ 1. 前スナップショット比（至上指標 登録/千再生）', H2); r += 1
hdr(ws, r, ['チャンネル', '前回日', '今回日', '前回 登録/千', '今回 登録/千', '差',
            '前回 いいね率%', '今回 いいね率%', 'いいね率 差', '符号一致',
            '同一動画のみ Δ再生', '判定']); r += 1
agree = 0; tot = 0
for ch in ['scp-lab', 'yokai-watch', 'daily-science', 'company-facts', '2ch-matome', 'socio-rx']:
    if ch not in CH: continue
    x = CH[ch]; a = x['cur']; b = x['prev']
    put(ws, r, 1, ch, BLD); put(ws, r, 2, x['prev_snap']); put(ws, r, 3, x['snap'])
    put(ws, r, 4, f'=IFERROR({b["subs"]}*1000/{b["views"]},0)' if b['views'] else 0, NB, '0.000')
    put(ws, r, 5, f'=IFERROR({a["subs"]}*1000/{a["views"]},0)' if a['views'] else 0, BLD, '0.000')
    put(ws, r, 6, f'=IFERROR(E{r}-D{r},0)', BLD, '+0.000;-0.000;0.000')
    put(ws, r, 7, f'=IFERROR({b["likes"]}*100/{b["views"]},0)' if b['views'] else 0, NB, '0.000')
    put(ws, r, 8, f'=IFERROR({a["likes"]}*100/{a["views"]},0)' if a['views'] else 0, NB, '0.000')
    put(ws, r, 9, f'=IFERROR(H{r}-G{r},0)', NB, '+0.000;-0.000;0.000')
    put(ws, r, 10, f'=IF(OR(AND(F{r}>0,I{r}>0),AND(F{r}<0,I{r}<0)),"○","×")', BLD)
    put(ws, r, 11, x['same']['dviews'], NB, '+#,##0;-#,##0;0')
    ds = a['sp'] - b['sp']; dl = a['lr'] - b['lr']
    if b['views']:
        agree += ((ds > 0 and dl > 0) or (ds < 0 and dl < 0)); tot += 1
    put(ws, r, 12, ('◎ 改善' if ds > 0.03 else '○ 改善' if ds > 0
                    else '△ 微減' if ds > -0.02 else '× 低下') if b['views'] else '－ 母数不足', NB)
    r += 1
put(ws, r, 1, f'符号一致 {agree}/{tot}ch', BLD, fill=WARN)
put(ws, r, 2, 'いいね率と登録/千の前日比の符号一致。09-15 は 4/5ch。'
              '「全ch一致」という言い方は使わない（09-15 に自己訂正済み）', NB)
r += 2
put(ws, r, 1, '■ 2. 前回施策の効果検証（差分検証）', H2); r += 1
hdr(ws, r, ['実施日', '対象', '施策', '前回判定', '本日の判定', '次判定日']); r += 1
V = [
 ('09-12', 'scp-lab', 'autopilot 週7日化', '△ 未測定',
  '△ 未測定継続。公開は継続しているが 09-07以降の 85本中 54本が未計測', '09-21'),
 ('09-12', 'company-facts', '投稿枠 3→4', '× 疑わしい',
  '× 疑わしいまま。0.715→0.649→0.619→0.613 と4日連続低下。'
  '総再生は全ch最大なので「本数を増やすと1本あたりの変換が落ちる」の実例候補', '09-21'),
 ('09-13', '8ch', 'autopilot 無効化（5ch集中）', '○ 成立',
  '○ 成立継続。停止chの指標に悪化なし。'
  'ただし akashic-librarian(0.570・全ch3位) を実力ではなく OAuth 都合で止めている点は損失', '09-21'),
 ('09-14', '全6ch', '投稿枠を17時中心へ再編', '△ 方向は妥当',
  '○ 方向は再現。17時 0.932(n=38) が再び最良。廃止した 18時 0.279 / 21時 0.000 も妥当。'
  'ただし新設15時枠は 0.000(n=4) に悪化', '09-21'),
 ('09-14', '全6ch', 'ch別タイトル型ルール固定', '△ 未測定',
  '△ 未測定継続（変更後の公開分が未計測）', '09-21'),
 ('09-14', 'title_constraints', 'repair() に forbid_patterns 追加', '○ 成立',
  '○ 成立継続。09-14以降の公開分に 99%型・絵文字の違反なし', '—'),
 ('09-15', '全6ch', '維持率目標帯 40-50% を明記', '△ 一部修正要',
  '○ 頂点 40-50%(0.687) は3日連続で再現。最下位 <30%(0.245) も再現。'
  'ただし当該キーはコード未参照なのでドキュメント値', '09-21'),
 ('09-15', '全4ch', 'テーマキュー 7日以上へ補充', '○ 成立',
  '△ 効果が24時間しか持たない。7.0日→5.7〜6.0日。補充が消費に追いついていない', '09-17'),
 ('09-15', 'backend', 'publish_blocked の導入', '○ 初めて公開を止めた',
  '○ 成立。ただし代償が枠の欠落だと確認できたので、本 run で原因側（mdg=1）を修正した', '09-17'),
 ('09-16', 'scp-lab / pokemon-lab', 'max_digit_groups 1→2（本 run）', '—',
  '— 本日適用。キュー違反 0件・無退行を確認。効果は 09-17 の枠到達率で見る', '09-17'),
]
for v in V:
    for i, t in enumerate(v, 1):
        put(ws, r, i, t, NB, wrap=True)
    ws.row_dimensions[r].height = 64
    r += 1

r += 1
put(ws, r, 1, '■ 3. 維持率バンド（ゆっくり8ch・views≧200）— 09-15 の訂正版結論の再現確認', H2); r += 1
hdr(ws, r, ['維持率バンド', '本数', '総再生', '登録', '登録/千再生', '判定']); r += 1
for bd in D['ret_bands']:
    if bd['n'] == 0: continue
    put(ws, r, 1, bd['band'], BLD); put(ws, r, 2, bd['n'])
    put(ws, r, 3, bd['views'], NB, '#,##0'); put(ws, r, 4, bd['subs'])
    put(ws, r, 5, f'=IFERROR(D{r}*1000/C{r},0)', BLD, '0.000')
    j = ('◎ 頂点（3日連続で再現）' if bd['band'] == '40-50%'
         else '× 最下位（再現）' if bd['band'] == '0-30%' else '○ ほぼ平坦')
    put(ws, r, 6, j, NB,
        fill=GOOD if bd['band'] == '40-50%' else (BAD if bd['band'] == '0-30%' else None))
    r += 1
put(ws, r, 1, '※ 09-15 の「維持率が高すぎると登録が減る」の撤回は本日も支持される'
              '（50%以上は 0.545〜0.627 で平坦・最下位は <30%）。維持率を下げる施策は打たない。', NB)

wb.save('reports/youtube-analysis-2026-09-16.xlsx')
print('saved reports/youtube-analysis-2026-09-16.xlsx  sheets=', wb.sheetnames)
