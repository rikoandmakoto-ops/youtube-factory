#!/usr/bin/env python3
"""2026-09-17 指揮者レポート xlsx。集計値は式で持たせ、生の実測だけを定数として置く。"""
import json, os, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(BASE, 'reports/_orch_20260917_data.json'), encoding='utf-8'))
CH, CFG = D['channels'], D['configs']
ORDER = ['scp-lab', 'daily-science', 'yokai-watch', 'company-facts', '2ch-matome', 'socio-rx',
         'pokemon-lab', 'fake-paper', 'akashic-librarian', 'clip-lab', 'clip-fukada',
         'clip-kaneko', 'clip-animal']
ACT5 = ['scp-lab', 'daily-science', 'yokai-watch', 'company-facts', '2ch-matome']
F = 'Arial'
H1 = Font(name=F, size=14, bold=True)
H2 = Font(name=F, size=11, bold=True)
NB = Font(name=F, size=10)
BLD = Font(name=F, size=10, bold=True)
SM = Font(name=F, size=9, color='595959')
HDRT = Font(name=F, size=10, bold=True, color='FFFFFF')
HDRF = PatternFill('solid', fgColor='1F3864')
WARN = PatternFill('solid', fgColor='FFF2CC')
BAD = PatternFill('solid', fgColor='FCE4EC')
GOOD = PatternFill('solid', fgColor='E2EFDA')
GREY = PatternFill('solid', fgColor='F2F2F2')
THIN = Border(*[Side(style='thin', color='BFBFBF')] * 4)
N3, N2, PC, IN = '0.000', '0.00', '0.000"%"', '#,##0'
wb = openpyxl.Workbook()


def widths(ws, ws_w):
    for i, w in enumerate(ws_w, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def hdr(ws, row, cols):
    for i, t in enumerate(cols, 1):
        c = ws.cell(row=row, column=i, value=t)
        c.font, c.fill, c.border = HDRT, HDRF, THIN
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[row].height = 32


def put(ws, r, c, v, font=None, fmt=None, fill=None, wrap=False):
    x = ws.cell(row=r, column=c, value=v)
    x.font = font or NB
    if fmt: x.number_format = fmt
    if fill: x.fill = fill
    if wrap: x.alignment = Alignment(wrap_text=True, vertical='top')
    x.border = THIN
    return x


SNAP = '2026-09-16'
# =====================================================================
# 1. サマリ
# =====================================================================
ws = wb.active; ws.title = 'サマリ'
widths(ws, [16, 13, 11, 11, 11, 11, 11, 11, 13, 40])
put(ws, 1, 1, 'YouTube Factory 指揮者レポート  2026-09-17（木）', H1)
put(ws, 2, 1, 'データ源: data/analytics/analytics.db（YouTube Analytics API 経由で収集済みのもの）。'
              'ブラウザでの YouTube 直接アクセス・APIキーは一切使用していない。', SM)
put(ws, 3, 1, f"生成: {D['generated_at']}  /  最新スナップショット: {SNAP}"
              "（fetch 2026-09-16 22:30–22:41 JST）  /  前回レポートは 09-15 スナップショットを使用", SM)
put(ws, 4, 1, '⚠️ video_metrics.views は「直近30日窓」であり生涯累計ではない。'
              '同一動画の views が日をまたいで減るのは窓が古い日を落としているだけで、'
              '「再生が減った」と読んではいけない。', SM)

r = 6
put(ws, r, 1, '■ 本日の結論', H2); r += 1
for t in [
    '1. 新規データは 09-16 22:41 fetch の1本ぶん。更新されたのは稼働6chのみ。'
    '他7ch（pokemon-lab / fake-paper / akashic-librarian / clip 4ch）は 09-06〜09-08 で凍結＝OAuth invalid_grant。',
    '2. ★最大の発見★ 「なぜ／のか」型タイトルが ch内対照で 4/4ch すべて自ch平均超。'
    'ch内一致が測定可能な全chで取れたタイトル指標はこれが初めて。'
    '対して「正体/真相」は 1/4ch、「実は」2/3ch、「理由/わけ」2/3ch で一致しない。'
    'ただし「？」だけを足すと 3/5ch まで落ちるので、効いているのは疑問符ではなく「なぜ／のか」の語である。',
    '3. 13時は ch固定効果で 3/3ch すべて自ch平均割れ（中央値0.50）＝測定できた全時刻で最下位。'
    '17時は 5/5ch で測定でき中央値1.67倍で最良。早朝6-10時は 5ch中4chで最下位ブロック。',
    '4. 至上指標 登録/千再生は 6ch中4chで前日比マイナス。ただし同一動画の再生は全ch増えており'
    '（scp-lab +2,446 / daily-science +3,645 / company-facts +4,785）、'
    '登録が追いつかないぶん分母が膨らんだ希釈。「悪化」と読むのは早い。',
    '5. ⚠️ 09-16 に再有効化した 2ch-matome の autopilot は一度も発火していない（09-16の3枠・09-17 07:30 とも0本）。'
    'config は反映されたが APScheduler にジョブが再登録されないバグ。並走 run がコード修正済みで、要バックエンド再起動。',
    '6. ⚠️ 本日は指揮者 run が並走した。既定のマーカーファイル（orch_config_changes_YYYYMMDD.json）が'
    '置かれていなかったため検知できず、同一スナップショットで二重に Phase3 を実行した。'
    '変更同士は加算的で矛盾はないが鉄則違反。スケジュール側で1本に寄せること（3日連続で同じ指摘）。',
]:
    put(ws, r, 1, t, NB, wrap=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    ws.row_dimensions[r].height = 30
    r += 1

r += 1
put(ws, r, 1, '■ 至上指標 登録/千再生（最新スナップショット・直近50本ローリング窓）', H2); r += 1
hdr(ws, r, ['channel', 'スナップ', '本数', '再生(30日窓)', '登録', '登録/千再生', 'いいね率%', '平均維持率%',
            '同一動画Δ再生', '判定'])
top = r; r += 1
first_data = r
for ch in ORDER:
    v = CH.get(ch)
    if not v: continue
    cur, same = v['cur'], v['same']
    stale = v['stale']
    put(ws, r, 1, v['name'][:14] if v.get('name') else ch, BLD if not stale else NB)
    put(ws, r, 2, v['snap'], NB, fill=None if not stale else GREY)
    put(ws, r, 3, cur['n'], NB, IN)
    put(ws, r, 4, cur['views'], NB, IN)
    put(ws, r, 5, cur['subs'], NB, IN)
    put(ws, r, 6, f'=IF(D{r}=0,0,E{r}/D{r}*1000)', BLD, N3)      # 登録/千再生 ← 式
    put(ws, r, 7, cur['lr'], NB, PC)
    put(ws, r, 8, cur['avp'], NB, N2)
    put(ws, r, 9, same['dviews'], NB, IN)
    note = 'OAuth失効・データ凍結' if stale else ('母数不足(n<10)' if cur['n'] < 10 else '')
    put(ws, r, 10, note, SM, fill=GREY if stale else None)
    r += 1
last_data = r - 1
put(ws, r, 1, '稼働6ch 合計', BLD, fill=GOOD)
for col, L in [(3, 'C'), (4, 'D'), (5, 'E')]:
    put(ws, r, col, f'=SUM({L}{first_data}:{L}{first_data + 5})', BLD, IN, fill=GOOD)
put(ws, r, 6, f'=IF(D{r}=0,0,E{r}/D{r}*1000)', BLD, N3, fill=GOOD)
put(ws, r, 10, '稼働6ch = 09-16 スナップショットが取れた ch', SM, fill=GOOD)
sumrow = r
r += 2

put(ws, r, 1, '■ 系統別（各ch最新スナップショット）', H2); r += 1
hdr(ws, r, ['系統', 'ch数', '本数', '再生', '登録', '登録/千再生', 'いいね率%'])
r += 1
sysrow0 = r
for k, v in D['systems'].items():
    put(ws, r, 1, k, BLD); put(ws, r, 2, v['nch'], NB, IN); put(ws, r, 3, v['n'], NB, IN)
    put(ws, r, 4, v['views'], NB, IN); put(ws, r, 5, v['subs'], NB, IN)
    put(ws, r, 6, f'=IF(D{r}=0,0,E{r}/D{r}*1000)', BLD, N3)
    put(ws, r, 7, v['lr'], NB, PC)
    r += 1
put(ws, r, 1, 'ゆっくり系 ÷ 切り抜き系', BLD, fill=WARN)
put(ws, r, 6, f'=IF(F{sysrow0 + 1}=0,0,F{sysrow0}/F{sysrow0 + 1})', BLD, '0.00"倍"', fill=WARN)
put(ws, r, 7, '09-12 4.58 → 09-13 4.56 → 09-14 4.81 → 09-15 4.72 → 09-16 4.81 → 本日。'
              '切り抜き4chは OAuth 失効でデータが 09-08 で止まっている点に注意。', SM)
r += 2

put(ws, r, 1, '■ 公開実績（JST・09-13〜09-16）', H2); r += 1
days = ['09-13', '09-14', '09-15', '09-16']
hdr(ws, r, ['channel'] + days + ['1日の枠数', '枠到達率(09-16)'])
r += 1
for ch in ACT5 + ['socio-rx']:
    pc = D['publish_counts'].get(ch, {})
    put(ws, r, 1, ch, BLD)
    for i, d in enumerate(days):
        put(ws, r, 2 + i, pc.get(d, 0), NB, IN, fill=BAD if pc.get(d, 0) == 0 else None)
    ns = CFG[ch]['nslots']
    put(ws, r, 6, ns, NB, IN)
    put(ws, r, 7, f'=IF(F{r}=0,0,E{r}/F{r})', BLD, '0%')
    r += 1
put(ws, r, 1, '2ch-matome は 09-13 以降ずっと0本。09-16 に autopilot を true へ戻したが '
              'APScheduler にジョブが登録されず一度も発火していない（backend.log に "Autopilot fired for 2ch-matome" が皆無）。', SM, wrap=True)
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
ws.row_dimensions[r].height = 28

# =====================================================================
# 2. チャンネル別詳細
# =====================================================================
ws = wb.create_sheet('チャンネル別詳細')
widths(ws, [15, 20, 11, 10, 12, 8, 11, 10, 10, 12, 10, 26, 8, 9])
put(ws, 1, 1, 'チャンネル別詳細  （最新スナップショット vs 前回スナップショット）', H1)
put(ws, 2, 1, '「登録/千再生」が至上指標。前日差は式で算出。'
              '同一動画Δ は両スナップショットに共通して存在する動画だけの純増で、窓の入れ替わりを除いた値。', SM)
r = 4
hdr(ws, r, ['channel', 'チャンネル名', '最新スナップ', '前回スナップ', '本数',
            '登録/千再生', '前回', '差', 'いいね率%', '前回いいね率%',
            '平均維持率%', '投稿枠(JST)', 'キュー', '在庫(日)'])
r += 1
for ch in ORDER:
    v = CH.get(ch)
    if not v: continue
    cur, pv, cf = v['cur'], v['prev'], CFG[ch]
    stale = v['stale']
    put(ws, r, 1, ch, BLD)
    put(ws, r, 2, v['name'], NB)
    put(ws, r, 3, v['snap'], NB, fill=GREY if stale else None)
    put(ws, r, 4, v['prev_snap'] or '—', NB)
    put(ws, r, 5, cur['n'], NB, IN)
    put(ws, r, 6, cur['sp'], BLD, N3)
    put(ws, r, 7, pv['sp'], NB, N3)
    d = put(ws, r, 8, f'=F{r}-G{r}', BLD, '+0.000;-0.000;0.000')
    d.fill = GOOD if cur['sp'] >= pv['sp'] else BAD
    put(ws, r, 9, cur['lr'], NB, PC)
    put(ws, r, 10, pv['lr'], NB, PC)
    put(ws, r, 11, cur['avp'], NB, N2)
    put(ws, r, 12, ' / '.join(cf['slots']) + ('' if cf['enabled'] else '  ⛔停止中'), NB)
    put(ws, r, 13, cf['queue'], NB, IN)
    put(ws, r, 14, f'=IF({cf["nslots"]}=0,0,M{r}/{cf["nslots"]})', NB, '0.0')
    r += 1
r += 1

put(ws, r, 1, '■ 公開時刻（JST）の ch固定効果 — 各chの自ch平均を 1.00 に正規化して比較', H2); r += 1
put(ws, r, 1, 'プールしたまま時刻を比べると「どの時刻が良いか」ではなく「どのchが強いか」を測ってしまう'
              '（ch間で登録/千は最大4.8倍違う）。そこで各動画を自ch平均で割った比で評価する。'
              'n>=3 の ch が2つ以上ある時刻のみ掲載。', SM, wrap=True)
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=14); ws.row_dimensions[r].height = 28
r += 1
hdr(ws, r, ['公開時刻', '測定ch数', '本数', '比(中央値)', '比(views加重)', '自ch平均割れのch数',
            'ch別内訳（比・本数）', '', '', '', '', '', '', ''])
r += 1
for h in D['hour_fixed_effect']:
    put(ws, r, 1, f"{h['hour']:02d}時", BLD)
    put(ws, r, 2, h['nch'], NB, IN)
    put(ws, r, 3, h['n'], NB, IN)
    x = put(ws, r, 4, h['median_ratio'], BLD, '0.00"倍"')
    if h['median_ratio'] >= 1.2:
        x.fill = GOOD
    elif h['median_ratio'] < 0.8:
        x.fill = BAD
    put(ws, r, 5, h['weighted_ratio'], NB, '0.00"倍"')
    put(ws, r, 6, f"{h['below_own_avg']} / {h['nch']}", NB)
    put(ws, r, 7, '  '.join(f"{p['ch']} {p['ratio']:.2f}(n={p['n']})" for p in h['detail']), SM)
    ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=14)
    r += 1
r += 1

put(ws, r, 1, '■ 時間帯ブロック × ch（登録/千再生）— 単一時刻より n を稼いだ見方', H2); r += 1
BL = D['blocks']['labels']
hdr(ws, r, ['channel'] + BL + ['最良ブロック(n>=4)'])
r += 1
for ch in ACT5:
    put(ws, r, 1, ch, BLD)
    best, bv = None, -1
    for i, b in enumerate(BL):
        x = D['blocks']['by_ch'][ch][b]
        if not x:
            put(ws, r, 2 + i, '—', SM); continue
        cell = put(ws, r, 2 + i, x['sp'], NB, N3)
        ws.cell(row=r, column=2 + i).comment = None
        put(ws, r, 2 + i, x['sp'], NB, N3)
        ws.cell(row=r, column=2 + i).value = x['sp']
        if x['n'] >= 4 and x['sp'] > bv:
            best, bv = b, x['sp']
    put(ws, r, 6, best or '—', BLD)
    r += 1
put(ws, r, 1, 'プール5ch', BLD, fill=GREY)
for i, b in enumerate(BL):
    put(ws, r, 2 + i, D['blocks']['pool'][b]['sp'], BLD, N3, fill=GREY)
put(ws, r, 6, '夕16-19 が 3/5ch で最良', SM, fill=GREY)
r += 1
put(ws, r, 1, '各セルの n は「直近動画一覧」から数えられる。'
              'yokai-watch だけが昼11-15 を最良とし全体傾向の逆を行く（17時も5ch中唯一の平均割れ）。', SM)
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=14)

# =====================================================================
# 3. 直近動画一覧
# =====================================================================
ws = wb.create_sheet('直近動画一覧')
widths(ws, [15, 17, 52, 10, 8, 8, 8, 10, 10, 12])
put(ws, 1, 1, f'直近動画一覧（2026-09-07 以降に公開・各ch最新スナップショット時点の実測）', H1)
put(ws, 2, 1, 'views=0 は削除でも失敗でもなく Analytics の反映ラグ（実測で約2日）。'
              '「登録/千再生」は式。公開時刻は JST。', SM)
r = 4
hdr(ws, r, ['channel', '公開(JST)', 'タイトル', '再生', 'いいね', 'コメント', '登録',
            '登録/千再生', '維持率%', '状態'])
r += 1
vids = sorted(D['videos'], key=lambda v: (v['ch'], v['pub_jst']))
for v in vids:
    put(ws, r, 1, v['ch'], NB)
    put(ws, r, 2, v['pub_jst'], NB)
    put(ws, r, 3, v['title'], NB)
    put(ws, r, 4, v['views'], NB, IN)
    put(ws, r, 5, v['likes'], NB, IN)
    put(ws, r, 6, v['comments'], NB, IN)
    put(ws, r, 7, v['subs'], NB, IN)
    put(ws, r, 8, f'=IF(D{r}=0,"",G{r}/D{r}*1000)', BLD, N3)
    put(ws, r, 9, v['avp'], NB, N2)
    put(ws, r, 10, v['state'], SM, fill=GREY if v['views'] == 0 else None)
    r += 1
put(ws, r, 1, f"計 {len(vids)} 本 / うち未計測 {D['videos_zero']} 本", BLD, fill=GREY)
put(ws, r, 4, f'=SUM(D5:D{r - 1})', BLD, IN, fill=GREY)
put(ws, r, 7, f'=SUM(G5:G{r - 1})', BLD, IN, fill=GREY)
put(ws, r, 8, f'=IF(D{r}=0,0,G{r}/D{r}*1000)', BLD, N3, fill=GREY)

# =====================================================================
# 4. 改善提案
# =====================================================================
ws = wb.create_sheet('改善提案')
widths(ws, [4, 26, 15, 62, 16, 13])
put(ws, 1, 1, '改善提案と本日実施したアクション', H1)
put(ws, 2, 1, '「実施」は本日 config に書き込み済み。「提案」は根拠が n 不足などで保留したもの。'
              '実施したものには必ず評価期日と撤回条件を付けている。', SM)

r = 4
put(ws, r, 1, '■ タイトル型の ch内対照（本日の最重要）', H2); r += 1
hdr(ws, r, ['', 'パターン', '該当/非該当 本数', '登録/千再生（該当 vs 非該当）', 'ch内一致', '採否'])
r += 1
for i, p in enumerate(D['title_patterns'], 1):
    put(ws, r, 1, i, NB)
    put(ws, r, 2, p['pattern'], BLD)
    put(ws, r, 3, f"{p['n_hit']} / {p['n_mis']}", NB)
    put(ws, r, 4, f"{p['sp_hit']:.3f} vs {p['sp_mis']:.3f}"
                  f"（{p['sp_hit'] / p['sp_mis']:.2f}倍）" if p['sp_mis'] else '—', NB)
    x = put(ws, r, 5, f"{p['agree']} / {p['ch_tested']} ch", BLD)
    ok = p['ch_tested'] > 0 and p['agree'] == p['ch_tested']
    x.fill = GOOD if ok else (BAD if p['agree'] * 2 < p['ch_tested'] else WARN)
    put(ws, r, 6, '★採用' if ok else '不採用', BLD if ok else SM, fill=GOOD if ok else None)
    r += 1
put(ws, r, 1, '', NB)
put(ws, r, 2, '「数字あり」は 1/3ch・0.530 vs 0.739 で負。yokai-watch の forbid_digits は妥当であり、'
              '他chでもタイトルの数字は増やさないこと。', SM)
ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
r += 2

put(ws, r, 1, '■ 本日実施したアクション（config 反映済み）', H2); r += 1
hdr(ws, r, ['', 'channel', '種別', '内容と根拠（すべて実測）', '評価期日', '撤回条件'])
r += 1
ACTS = [
    ('scp-lab', '投稿枠', '13:00 → 12:45。13時は ch固定効果で 3/3ch すべて自ch平均割れ'
                '（scp-lab 0.55(n=11) / daily-science 0.50(n=3) / company-facts 0.00(n=4)、中央値0.50）'
                '＝測定できた全時刻で最下位。当ch内でも 13時 0.437(n=11) は 17時 1.322(n=4)・19時 1.025(n=10) の半分以下。'
                '振替先12時は中央値1.24倍。12:45 にしたのは生成開始(12:00)を他chと衝突させないため。',
     '2026-09-24', '12時台枠が ch平均×0.8 未満(n>=5) なら 16:00 へ再振替'),
    ('daily-science', '投稿枠', '07:30 → 19:00。当chの早朝6-10時 0.240(n=4) に対し夕16-19時 0.926(n=20) で 3.9倍。'
                      '早朝は稼働5ch中4chで最下位ブロック（プール 0.299(n=23) vs 0.695(n=89)）。'
                      '⚠️ 本 run は当初 16:30 を適用したが、17:00 枠と生成発火が30分差となり'
                      '連投ガード(90分)で毎日1本落ちる。並走 run が検出し 19:00 へ訂正した。',
     '2026-09-24', '19時台枠が ch平均×0.8 未満(n>=5) なら 16:00（16:30 ではない）へ'),
    ('5ch共通', 'タイトルゲート', 'require_any_of.words に「のか」を追加。'
                '「なぜ/のか」型は ch内対照 4/4ch 一致（0.708 vs 0.499）で本日唯一の全ch一致指標なのに、'
                '許容語に「のか」が無く「…は何だったのか」等が answer-marker 違反として再生成に回されていた。'
                'ゲートを緩める方向なので publish_blocked は増えない。キュー違反 scp-lab 5→4 / company-facts 4→2。',
     '2026-09-24', 'backend.log の「タイトル規約違反」件数が減らなければ撤回'),
    ('scp-lab / 2ch-matome', 'テーマキュー', '疑問型を前方へ安定ソート（内容・件数は変更なし）。'
                             'scp-lab は先頭3件が非疑問型（地震トレンドの重複テーマ）だった。',
     '2026-09-24', '効果が出なければ並び替えではなくキュー入替に切り替える'),
    ('company-facts', 'テーマキュー', '規約違反タイトルを事前修正。'
                      '「セブン-イレブンの日販68万円、24時間営業の採算」（数字2個・上限1）→'
                      '「セブン-イレブンの日販68万円が維持できる本当の理由」。'
                      '09-15 に scp-lab が同種の違反で publish_blocked となり1枠を失っているため先回りした。',
     '—', '—'),
]
for i, (ch, kind, body, ev, kill) in enumerate(ACTS, 1):
    put(ws, r, 1, i, NB)
    put(ws, r, 2, ch, BLD)
    put(ws, r, 3, kind, NB)
    put(ws, r, 4, body, NB, wrap=True)
    put(ws, r, 5, ev, BLD, fill=WARN if ev != '—' else None)
    put(ws, r, 6, kill, SM, wrap=True)
    ws.row_dimensions[r].height = 74
    r += 1
r += 1

put(ws, r, 1, '■ あえて変更しなかったもの（理由を残さないと後続 run が蒸し返すため）', H2); r += 1
hdr(ws, r, ['', 'channel', '種別', '見送った理由', '再判定の条件', ''])
r += 1
SKIP = [
    ('yokai-watch', '投稿枠', '最弱は 19時 0.347(n=8)＝自ch平均の0.49倍だが、振替先に根拠がない。'
                    '18時は n=3 かつ 3/3ch で平均割れ、13時は全時刻最下位、11/14時は当ch実績ゼロ。'
                    '当chの昼ブロックの強さは実質 12時(n=11) 単独で、13-15時へ外挿できない。'
                    '当chは5ch中唯一 昼>夕 で、17時も唯一の平均割れ（0.65倍）。',
     '09-14 新設の 16:00 枠が n>=5 に達する 09-24'),
    ('company-facts', '投稿枠', 'auto_optimize_schedule=true でバックエンドが枠を自動最適化しており、'
                     '手動変更は上書きされる（09-15 のログに "current slot underperforms recommended by 100%" が実在）。'
                     '夕16-19 が当ch最良 0.741(n=18) である事実はメモリに記録した。',
     'auto_optimize を切るかどうかの仕様判断が先'),
    ('2ch-matome', '投稿枠 / autopilot', '09-16 に enabled を true へ戻したが 09-16 の3枠・09-17 07:30 とも'
                   '一度も発火せず、効果測定が成立していない。原因は config 再読込では '
                   'APScheduler にジョブが再登録されないバグ。同一データで二重に判断しないため据え置き。',
     'バックエンド再起動後、発火を確認してから'),
    ('socio-rx', '全般', '5本・1,091再生・登録0人。登録/千再生を推定できる母数に達していない'
                 '（他chの判断基準は views>=200 かつ ch内 n>=10）。'
                 '⚠️ ただしキュー12件が全件タイトル規約違反で、毎枠が再生成2回→機械修復に落ちている。',
     'n>=10 到達後。キュー違反は母数と無関係なので別途対処が必要'),
    ('OAuth失効7ch', '全般', 'pokemon-lab / fake-paper / akashic-librarian / clip-lab / clip-fukada / '
                   'clip-kaneko / clip-animal はスナップショットが 09-06〜09-08 で凍結。'
                   '同一データでの二重意思決定を避けるため一切変更しない。',
     '再認可してスナップショットが動いてから'),
]
for i, (ch, kind, why, cond) in enumerate(SKIP, 1):
    put(ws, r, 1, i, NB); put(ws, r, 2, ch, BLD); put(ws, r, 3, kind, NB)
    put(ws, r, 4, why, NB, wrap=True); put(ws, r, 5, cond, SM, wrap=True); put(ws, r, 6, '', NB)
    ws.row_dimensions[r].height = 62
    r += 1
r += 1

put(ws, r, 1, '■ 未解決・次の指揮者への申し送り', H2); r += 1
for i, t in enumerate([
    '1. 【最優先】バックエンド再起動。2ch-matome は 09-13 以降0本のまま。'
    '並走 run がスケジューラ再登録のバグを直しているが、反映には再起動が要る（restart_and_trigger_20260917.command）。',
    '2. 【本日できなかった】config のコミット。.git/HEAD.lock が 09-16 23:17 の残骸として残っており、'
    'サンドボックスVMのマウントでは自分が作っていないファイルを削除できない（Operation not permitted）。'
    'commit_orch_20260917.command を用意したので Mac 側で実行が必要。config 自体は書き込み済み。',
    '3. OAuth 失効 7ch。09-20 昼に稼働6chも一斉失効する見込み。同意画面の本番公開が先。',
    '4. 09-21: いいね率と維持率のどちらを先行指標にするかを 09-14 以降の独立コホート（n>=20/ch）で本判定。'
    '本日 ch内対照は いいね率 3/5ch・維持率 4/5ch。維持率も 09-13〜09-15 の 5/5 から落ちたので、'
    '「維持率へ乗り換える」根拠は今日もできていない。',
    '5. 09-24: 本日の 投稿枠2件・「のか」追加・キュー並べ替えを評価。撤回条件は上表のとおり。',
    '6. 並走 run の抑止を仕組みにする。3日連続で並走しており、本日はついに同一スナップショットでの'
    '二重 Phase3 が起きた。マーカーファイル方式は「先に走った方が置く」前提が守られないと機能しない。',
], 1):
    put(ws, r, 1, '', NB)
    put(ws, r, 2, t, NB, wrap=True)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
    ws.row_dimensions[r].height = 30
    r += 1

# =====================================================================
# 5. 前回比較
# =====================================================================
ws = wb.create_sheet('前回比較')
widths(ws, [16, 13, 13, 12, 12, 12, 12, 12, 12, 34])
put(ws, 1, 1, '前回比較  2026-09-16 レポート（09-15 スナップショット） → 本日（09-16 スナップショット）', H1)
P = D['prev_report']
put(ws, 2, 1, f"前回生成: {P.get('generated_at')}  /  差分は1スナップショットぶん。"
              "連続スナップショットは同一動画が約95%重なるため独立標本ではない点に注意。", SM)
r = 4
hdr(ws, r, ['channel', '前回スナップ', '今回スナップ', '登録/千(前)', '登録/千(今)', '差',
            'いいね率%(前)', 'いいね率%(今)', '維持率%(今)', '読み方'])
r += 1
NOTE = {
    'scp-lab': '同一動画で +2,446 再生。分母が増えたぶんの希釈で、実質は伸びている。',
    'daily-science': '同一動画で +3,645 再生・登録+0。本日の最大の下げ幅だが希釈が主因。いいね率は +0.018 で全ch最高を維持。',
    'yokai-watch': 'いいね率 -0.034 と登録 -2 が同方向。5ch中唯一 昼>夕 の ch。',
    'company-facts': '同一動画で +4,785 再生＝5ch最大。6日連続の微減だが下げ幅は最小(-0.008)。',
    '2ch-matome': '前日と完全に横ばい。09-13 以降1本も公開していないため当然（autopilot 未発火）。',
    'socio-rx': '5本・登録0。いいね率 -0.586 は n=5 の揺れで、意味を読んではいけない。',
}
for ch in ORDER:
    v, pv = CH.get(ch), P.get('channels', {}).get(ch)
    if not v: continue
    put(ws, r, 1, ch, BLD)
    put(ws, r, 2, pv['snap'] if pv else '—', NB)
    put(ws, r, 3, v['snap'], NB, fill=GREY if v['stale'] else None)
    put(ws, r, 4, pv['sp'] if pv else None, NB, N3)
    put(ws, r, 5, v['cur']['sp'], BLD, N3)
    x = put(ws, r, 6, f'=IF(D{r}="","",E{r}-D{r})', BLD, '+0.000;-0.000;0.000')
    if pv:
        x.fill = GOOD if v['cur']['sp'] >= pv['sp'] else BAD
    put(ws, r, 7, pv['lr'] if pv else None, NB, PC)
    put(ws, r, 8, v['cur']['lr'], NB, PC)
    put(ws, r, 9, v['cur']['avp'], NB, N2)
    put(ws, r, 10, NOTE.get(ch, 'OAuth失効でスナップショットが動いていない＝前回と同一データ。'), SM, wrap=True)
    ws.row_dimensions[r].height = 26
    r += 1
r += 1

put(ws, r, 1, '■ 前回 config 変更の効果検証（PDCA の Check）', H2); r += 1
hdr(ws, r, ['実施日', '対象', '変更内容', '期待した効果', '実測', '判定', '次アクション', '', '', ''])
r += 1
VER = [
    ('09-16', 'scp-lab / pokemon-lab', 'max_digit_groups 1 → 2',
     'scp-lab の枠到達率が 3/3 になる（09-15 は SCP-2718 が数字2個で publish_blocked となり1枠喪失）',
     'scp-lab の 09-16 公開は 3本＝3/3 で枠到達。publish_blocked の新規発生は0件。',
     '○ 効果あり', '継続。pokemon-lab は autopilot 停止中のため未検証。'),
    ('09-16', '2ch-matome', 'autopilot.enabled false → true',
     '1日3枠・約 +0.7 登録/日 の上積み',
     '09-16 の3枠・09-17 07:30 とも発火0回・公開0本。backend.log に "Autopilot fired for 2ch-matome" が皆無。',
     '× 効果ゼロ（施策の是非以前にバグ）', 'config は据え置き。バックエンド再起動後に再計測。'),
    ('09-16', '6ch', 'optimization._retention_note（70%帯は再現せず）',
     '維持率70%超を目標にしないという方針の明文化',
     '本日の維持率バンドも頂点は 40-50%(0.629)、70%+ は 0.536 で 4日連続再現。',
     '○ 記述は実測と整合', '維持率を目的関数にしない方針を継続。'),
    ('09-14', '5ch', '投稿枠の再編（17時中心へ）',
     '17時枠の登録効率が他時刻を上回る',
     '17時は 5/5ch で測定でき ch固定効果 中央値1.67倍・加重1.47倍で全時刻中最良。'
     '4/5ch で自ch平均超（例外は yokai-watch 0.65）。',
     '○ 再現（3日連続）', '17時は維持。yokai-watch だけ例外として扱う。'),
    ('09-14', 'daily-science / company-facts', '15:00 枠の新設',
     '15時が使える時刻かどうか',
     '15時は n=5 までしか増えず、ch固定効果の掲載基準（2ch以上で n>=3）に届かない。',
     '△ 判定不能', '09-24 まで保留。09-15 の「15時が悪化」も母集団が変更前なので無効。'),
]
for d0, tgt, chg, exp, act, jd, nx in VER:
    put(ws, r, 1, d0, BLD); put(ws, r, 2, tgt, NB); put(ws, r, 3, chg, NB, wrap=True)
    put(ws, r, 4, exp, SM, wrap=True); put(ws, r, 5, act, NB, wrap=True)
    x = put(ws, r, 6, jd, BLD, wrap=True)
    x.fill = GOOD if jd.startswith('○') else (BAD if jd.startswith('×') else WARN)
    put(ws, r, 7, nx, SM, wrap=True)
    ws.row_dimensions[r].height = 58
    r += 1
r += 1

put(ws, r, 1, '■ 指標の安定性（再現しているか／崩れたか）', H2); r += 1
hdr(ws, r, ['指標', '09-08', '09-13', '09-14', '09-15', '09-16', '判定', '', '', ''])
r += 1
W = D['within_ch']
for label, key in [('いいね率 ch内対照 一致ch数', 'like_ok'), ('維持率 ch内対照 一致ch数', 'ret_ok')]:
    put(ws, r, 1, label, BLD)
    vals = []
    for i, sd in enumerate(['2026-09-08', '2026-09-13', '2026-09-14', '2026-09-15', '2026-09-16']):
        res = W.get(sd, {})
        ok = sum(1 for v in res.values() if v and v[key])
        tot = sum(1 for v in res.values() if v)
        vals.append(ok)
        put(ws, r, 2 + i, f'{ok}/{tot}', NB, fill=GOOD if ok == tot else (BAD if ok * 2 < tot else WARN))
    put(ws, r, 7, ('5→4→4→3→3 と単調に落ちている。「符号が反転しない」は誤りで、'
                   '2ch-matome は4スナップショット連続で逆。' if key == 'like_ok' else
                   '3→5→5→5→4。本日 daily-science が初めて逆転（0.633→0.623 と僅差）。'
                   '維持率も全ch一致ではなくなったので、いいね率から乗り換える根拠は本日もできていない。'), SM, wrap=True)
    ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=10)
    ws.row_dimensions[r].height = 40
    r += 1
put(ws, r, 1, 'いいね率4分位 Q4/Q1', BLD)
put(ws, r, 5, P.get('like_q_ratio'), NB, '0.00"倍"')
put(ws, r, 6, D['like_q_ratio'], BLD, '0.00"倍"')
put(ws, r, 7, f"単調性は前回 {P.get('like_q_monotone')} → 今回 {D['like_q_monotone']}。"
              "Q2>Q3 の逆転が2日連続で、6回続いた単調の記録は止まったまま。", SM, wrap=True)
ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=10)
r += 1
put(ws, r, 1, '維持率バンドの頂点', BLD)
put(ws, r, 6, '40-50%', BLD, fill=GOOD)
put(ws, r, 7, f"本日 {D['ret_bands'][2]['sp']:.3f}（n={D['ret_bands'][2]['n']}）。最下位は <30% "
              f"{D['ret_bands'][0]['sp']:.3f}。4日連続で再現。", SM, wrap=True)
ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=10)

for s in wb.worksheets:
    s.freeze_panes = 'A5'
out = os.path.join(BASE, 'reports/youtube-analysis-2026-09-17.xlsx')
wb.save(out)
print('saved', out, '/ sheets:', wb.sheetnames)
