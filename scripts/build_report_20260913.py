#!/usr/bin/env python3
"""指揮者 09-13 レポート生成。analytics.db(09-08スナップショット)から5シートのxlsxを作る。"""
import json, sqlite3, os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, 'data/analytics/analytics.db')
OUT = os.path.join(ROOT, 'reports/youtube-analysis-2026-09-13.xlsx')
SNAP = '2026-09-08'
W0, W1 = '2026-08-10', '2026-09-08'

FONT = 'Arial'
H_FILL = PatternFill('solid', fgColor='1F3864')
H_FONT = Font(name=FONT, bold=True, color='FFFFFF', size=10)
T_FONT = Font(name=FONT, bold=True, size=13, color='1F3864')
B_FONT = Font(name=FONT, size=10)
BOLD = Font(name=FONT, bold=True, size=10)
WARN = PatternFill('solid', fgColor='FCE4D6')
GOOD = PatternFill('solid', fgColor='E2EFDA')
GREY = PatternFill('solid', fgColor='F2F2F2')
THIN = Border(*[Side('thin', color='BFBFBF')] * 4)

CH_NAME = {
    'scp-lab': 'ゆっくり異常存在SCPラボ', 'daily-science': 'リコとマコトのゆっくり日常科学',
    'pokemon-lab': 'pokemon-lab', 'yokai-watch': 'yokai-watch', '2ch-matome': '2ch-matome',
    'company-facts': '企業のホンネ', 'clip-lab': '切り抜きラボ(ひろゆき)',
    'clip-fukada': '深田えいみ 切り抜き', 'clip-kaneko': '金子みゆ 切り抜き',
    'fake-paper': 'fake-paper', 'akashic-librarian': 'ラグナロクの司書',
    'clip-animal': '動物情報局', 'socio-rx': '社会学の処方箋',
}
YUKKURI = ['scp-lab', 'company-facts', 'daily-science', 'yokai-watch', 'pokemon-lab',
           '2ch-matome', 'fake-paper', 'akashic-librarian']
CLIPS = ['clip-lab', 'clip-fukada', 'clip-kaneko', 'clip-animal']


def fetch():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    ch = {r['channel_id']: dict(r) for r in c.execute(f"""
        SELECT channel_id, COUNT(DISTINCT video_id) n, SUM(views) views, SUM(likes) likes,
          SUM(comments) cmts, SUM(subscribers_gained) subs,
          SUM(views*avg_view_percentage)/NULLIF(SUM(views),0) avp,
          SUM(views*ctr)/NULLIF(SUM(views),0) ctr
        FROM video_metrics WHERE date BETWEEN '{W0}' AND '{W1}' GROUP BY channel_id""")}
    recent = [dict(r) for r in c.execute(f"""
        SELECT channel_id, title, substr(published_at,1,16) pub, SUM(views) v, SUM(likes) l,
          SUM(subscribers_gained) s, SUM(views*avg_view_percentage)/NULLIF(SUM(views),0) avp,
          SUM(views*ctr)/NULLIF(SUM(views),0) ctr
        FROM video_metrics WHERE published_at>='2026-09-02' AND date<='{W1}'
        GROUP BY video_id ORDER BY s DESC, v DESC""")]
    freshness = {r[0]: (r[1], r[2]) for r in c.execute(
        "SELECT channel_id, MAX(date), MAX(substr(published_at,1,10)) FROM video_metrics GROUP BY channel_id")}
    c.close()
    return ch, recent, freshness


def style_header(ws, row, ncols):
    for i in range(1, ncols + 1):
        cl = ws.cell(row=row, column=i)
        cl.fill = H_FILL; cl.font = H_FONT; cl.border = THIN
        cl.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def put(ws, row, vals, font=None, fill=None, fmt=None):
    for i, v in enumerate(vals, 1):
        cl = ws.cell(row=row, column=i, value=v)
        cl.font = font or B_FONT
        if fill: cl.fill = fill
        if fmt and i > 1 and isinstance(v, (int, float)): cl.number_format = fmt
    return row + 1


def widths(ws, ws_widths):
    for i, w in enumerate(ws_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build():
    ch, recent, fresh = fetch()
    wb = Workbook(); wb.remove(wb.active)

    # ---------------- サマリ ----------------
    ws = wb.create_sheet('サマリ')
    widths(ws, [30, 14, 14, 14, 14, 14, 16, 60])
    r = 1
    ws.cell(row=r, column=1, value='YouTube Factory 指揮者レポート 2026-09-13（土）').font = T_FONT; r += 2
    for line in [
        f'計測スナップショット: video_metrics の最終日 = {SNAP}（fetched_at 2026-09-08 14:19 UTC）',
        '★ 新規実績は 09-09 以降 5 日連続ゼロ。本日の分析は 09-12 と同一スナップショットに基づく。',
        '★ したがって本日は config を一切変更していない（鉄則: 同じスナップショットで2回判断しない）。',
    ]:
        ws.cell(row=r, column=1, value=line).font = BOLD if line.startswith('★') else B_FONT; r += 1
    r += 1

    ws.cell(row=r, column=1, value='■ 結論（3行）').font = BOLD; r += 1
    for line in [
        '① 詰まりは制作ではなく公開にある。全13chのOAuthトークンが失効済み（最終 pokemon-lab 09-09 14:43 UTC / 約3.4日前）。生成は動いているが公開が0本。',
        '② 登録者を説明する指標は「高評価率」のみ。205本で再検証して r=+0.308。維持率は r=-0.047（無相関）、CTRは r=+0.069（ほぼ無相関）。09-12の結論を独立に再確認した。',
        '③ 本日の新発見は「絵文字先頭が強い」が見かけ倒しだったこと。横断では 0.590 vs 0.353 だが、company-facts 内で見ると 0.686 vs 0.915 で逆転する（シンプソンのパラドックス）。',
    ]:
        ws.cell(row=r, column=1, value=line).font = B_FONT; r += 1
    r += 1

    ws.cell(row=r, column=1, value='■ 30日窓 全体KPI（2026-08-10 〜 2026-09-08）').font = BOLD; r += 1
    hdr = r
    r = put(ws, r, ['指標', '値', '', '', '', '', '', '算出根拠'])
    style_header(ws, hdr, 2)
    tot_start = r
    rows_kpi = []
    for cid in YUKKURI + CLIPS:
        d = ch.get(cid)
        if d: rows_kpi.append(d)
    tv = sum(d['views'] or 0 for d in rows_kpi)
    ts = sum(d['subs'] or 0 for d in rows_kpi)
    tl = sum(d['likes'] or 0 for d in rows_kpi)
    tn = sum(d['n'] or 0 for d in rows_kpi)
    kpi = [
        ('公開本数（30日）', tn, 'video_metrics の DISTINCT video_id'),
        ('総再生数', tv, '日次 views の窓内合計'),
        ('総高評価', tl, '日次 likes の窓内合計'),
        ('獲得登録者', ts, '日次 subscribers_gained の窓内合計'),
    ]
    for name, v, src in kpi:
        r = put(ws, r, [name, v, '', '', '', '', '', src], fmt='#,##0')
    r = put(ws, r, ['登録/千再生（至上指標）', f'=ROUND(B{tot_start+3}*1000/B{tot_start+1},3)', '', '', '', '', '',
                    '獲得登録者 ÷ 総再生数 × 1000'], font=BOLD)
    ws.cell(row=r-1, column=2).number_format = '0.000'
    r = put(ws, r, ['高評価率（%）', f'=ROUND(B{tot_start+2}*100/B{tot_start+1},3)', '', '', '', '', '',
                    '総高評価 ÷ 総再生数 × 100'])
    ws.cell(row=r-1, column=2).number_format = '0.000'
    r += 1

    ws.cell(row=r, column=1, value='■ 系統別（30日窓）').font = BOLD; r += 1
    hdr = r
    r = put(ws, r, ['系統', 'ch数', '本数', '再生数', '登録者', '登録/千', '高評価率%', '所見'])
    style_header(ws, hdr, 8)
    for label, ids in [('ゆっくり系 8ch', YUKKURI), ('切り抜き系 4ch', CLIPS)]:
        g = [ch[c] for c in ids if c in ch]
        v = sum(x['views'] or 0 for x in g); s = sum(x['subs'] or 0 for x in g)
        l = sum(x['likes'] or 0 for x in g); n = sum(x['n'] or 0 for x in g)
        note = ('登録転換の主力。ここに投稿枠を寄せるのが正しい'
                if 'ゆっくり' in label else '再生は取れるが登録に変換できない。clip-lab は223,866再生で登録1')
        r = put(ws, r, [label, len(g), n, v, s, round(s*1000/max(v,1), 3), round(l*100/max(v,1), 3), note])
        for c_ in (3, 4, 5): ws.cell(row=r-1, column=c_).number_format = '#,##0'
    r = put(ws, r, ['倍率（ゆっくり ÷ 切り抜き）', '', '', '', '', '=ROUND(F{0}/F{1},2)'.format(hdr+1, hdr+2), '', ''],
            font=BOLD)
    ws.cell(row=r-1, column=6).number_format = '0.00'
    ws.cell(row=r-1, column=8, value='窓=30日 / 構成=ゆっくり8ch・切り抜き4ch。倍率を引用するときは窓とch構成を必ず併記すること').font = B_FONT
    r += 1

    ws.cell(row=r, column=1, value='■ 公開が止まっている原因（OAuthトークン失効・data/youtube_tokens.db 実測）').font = BOLD; r += 1
    hdr = r
    r = put(ws, r, ['channel_id', 'expires_at (UTC)', '状態', '', '', '', '', '備考'])
    style_header(ws, hdr, 3)
    tok = [('pokemon-lab', '2026-09-09 14:43'), ('2ch-matome', '2026-09-09 08:13'),
           ('company-facts', '2026-09-09 06:55'), ('daily-science', '2026-09-08 18:56'),
           ('scp-lab', '2026-09-08 06:00'), ('yokai-watch', '2026-09-08 06:00'),
           ('clip-lab', '2026-09-08 06:00'), ('clip-kaneko', '2026-09-08 06:00'),
           ('clip-fukada', '2026-09-08 06:00'), ('akashic-librarian', '2026-09-06 19:52'),
           ('fake-paper', '2026-09-06 17:20'), ('clip-animal', '2026-09-06 06:00'),
           ('socio-rx', '2026-09-06 06:00')]
    for cid, exp in tok:
        r = put(ws, r, [cid, exp, '失効', '', '', '', '', 'updated_at が expires_at + 8h のまま＝リフレッシュ成功歴ゼロ'],
                fill=WARN)
    r += 1
    ws.cell(row=r, column=1, value='→ 13ch すべて失効。ユーザーによる再認可が必要（自動リフレッシュは一度も成功していない）。').font = BOLD
    r += 2
    ws.cell(row=r, column=1, value='■ socio-rx について').font = BOLD; r += 1
    ws.cell(row=r, column=1, value='analytics.db に video_metrics / channel_metrics の行が1件も無い。OAuthは登録済みだが 09-06 失効。実質未稼働のため本レポートの集計対象外。').font = B_FONT

    # ---------------- チャンネル別詳細 ----------------
    ws = wb.create_sheet('チャンネル別詳細')
    widths(ws, [18, 26, 8, 12, 12, 12, 12, 12, 12, 52])
    r = 1
    ws.cell(row=r, column=1, value=f'チャンネル別詳細（30日窓 {W0}〜{W1}）').font = T_FONT; r += 2
    hdr = r
    r = put(ws, r, ['channel_id', 'チャンネル名', '本数', '再生数', '登録者', '登録/千',
                    '高評価率%', '維持率%', '有効CTR%', '判定'])
    style_header(ws, hdr, 10)
    first = r
    notes = {
        'scp-lab': '★登録効率1位(0.851)。09-12に週7日化(週15→21本)。効果検証は新データ到着後',
        'company-facts': '★2位(0.733)かつ維持率1位(59.9%)。09-12に4枠目(12:30)増設。絵文字先頭は自ch内では逆効果(下記参照)',
        'akashic-librarian': '3位(0.727)だが母数が小さい(23,383再生)。長尺のみ・台本はユーザー作成',
        'daily-science': '高評価率1位(0.40%)。登録/千0.423は全体平均ちょうど。伸びしろは有効CTR 0.78%',
        'pokemon-lab': '再生は3位(810,327)だが登録/千0.336。「どっちが勝つ？」型は再生に効き登録に効かない',
        'yokai-watch': '登録/千0.324。40,312再生で登録0の動画あり。怪談フックは再生単独で完結してしまう',
        '2ch-matome': '登録/千0.175。497,948再生で87登録。ゆっくり系で最も変換が悪い',
        'fake-paper': '★30日で登録0。39,985再生・17本。全ch唯一の登録ゼロ。維持率38.2%も最低水準',
        'clip-lab': '★223,866再生で登録1(0.004)。凍結中。再生を登録に変換する導線が機能していない',
        'clip-fukada': '有効CTR 6.24%で全ch1位だが登録/千0.193。CTRは登録を説明しない実例',
        'clip-kaneko': '登録/千0.178。切り抜き系の平均的な水準',
        'clip-animal': '3本・17再生。実質未稼働。Autopilotは「切り抜ける元動画が見つかりません」で毎回失敗中',
    }
    order = sorted([c for c in ch], key=lambda c: -((ch[c]['subs'] or 0) * 1000 / max(ch[c]['views'] or 1, 1)))
    for cid in order:
        d = ch[cid]; v = d['views'] or 0; s = d['subs'] or 0; l = d['likes'] or 0
        fill = GOOD if s * 1000 / max(v, 1) >= 0.5 else (WARN if s * 1000 / max(v, 1) < 0.2 else None)
        r = put(ws, r, [cid, CH_NAME.get(cid, cid), d['n'], v, s,
                        round(s * 1000 / max(v, 1), 3), round(l * 100 / max(v, 1), 3),
                        round(d['avp'] or 0, 1), round((d['ctr'] or 0) * 100, 2),
                        notes.get(cid, '')], fill=fill)
        for c_ in (4, 5): ws.cell(row=r-1, column=c_).number_format = '#,##0'
    last = r - 1
    r = put(ws, r, ['合計 / 加重平均', '', f'=SUM(C{first}:C{last})', f'=SUM(D{first}:D{last})',
                    f'=SUM(E{first}:E{last})', f'=ROUND(E{r}*1000/D{r},3)', '', '', '',
                    'socio-rx はデータ0行のため行なし'], font=BOLD, fill=GREY)
    for c_ in (3, 4, 5): ws.cell(row=r-1, column=c_).number_format = '#,##0'
    ws.cell(row=r-1, column=6).number_format = '0.000'
    r += 2

    ws.cell(row=r, column=1, value='■ 登録/千 と各指標の相関（ゆっくり6ch・500再生以上の205本）').font = BOLD; r += 1
    hdr = r
    r = put(ws, r, ['説明変数', '相関係数 r', '', '', '', '', '', '', '', '解釈'])
    style_header(ws, hdr, 2)
    for name, rr, interp in [
        ('高評価率%', 0.308, '唯一の有意な説明変数。登録を伸ばしたいならここを狙う'),
        ('CTR%', 0.069, 'ほぼ無相関。clip-fukada がCTR1位(6.24%)で登録/千0.193なのが好例'),
        ('維持率%', -0.047, '無相関。維持率のために入れた構造ルールは登録には効かない'),
        ('再生数', -0.140, '弱い負。再生が増えるほど登録/千は下がる＝再生の最大化は目的関数ではない'),
    ]:
        r = put(ws, r, [name, rr, '', '', '', '', '', '', '', interp])
        ws.cell(row=r-1, column=2).number_format = '+0.000;-0.000'
    r += 1
    ws.cell(row=r, column=1, value='※ 09-12 レポートの同結論を、本日 独立に再計算して確認した（母数205本）。').font = B_FONT

    # ---------------- 直近動画一覧 ----------------
    ws = wb.create_sheet('直近動画一覧')
    widths(ws, [18, 62, 17, 11, 10, 9, 10, 10, 10])
    r = 1
    ws.cell(row=r, column=1, value='直近動画一覧（公開 2026-09-02 〜 2026-09-08 / 登録獲得順）').font = T_FONT; r += 1
    ws.cell(row=r, column=1, value='※ 09-09 以降の公開は0本のため、この7日間がスナップショット時点の「直近」。').font = B_FONT; r += 2
    hdr = r
    r = put(ws, r, ['channel_id', 'タイトル', '公開日時(UTC)', '再生数', '高評価', '登録', '登録/千', '維持率%', 'CTR%'])
    style_header(ws, hdr, 9)
    for d in recent:
        v = d['v'] or 0; s = d['s'] or 0
        fill = GOOD if s >= 5 else (WARN if (s == 0 and v >= 3000) else None)
        r = put(ws, r, [d['channel_id'], (d['title'] or '')[:80], d['pub'], v, d['l'] or 0, s,
                        round(s * 1000 / max(v, 1), 2), round(d['avp'] or 0, 1),
                        round((d['ctr'] or 0) * 100, 2)], fill=fill)
        ws.cell(row=r-1, column=4).number_format = '#,##0'
    ws.freeze_panes = ws.cell(row=hdr+1, column=1)
    ws.auto_filter.ref = f'A{hdr}:I{r-1}'

    # ---------------- 改善提案 ----------------
    ws = wb.create_sheet('改善提案')
    widths(ws, [6, 26, 14, 62, 52, 16])
    r = 1
    ws.cell(row=r, column=1, value='改善提案 2026-09-13').font = T_FONT; r += 1
    ws.cell(row=r, column=1, value='★ 本日は config を変更していない。新規実績が5日連続ゼロで、09-12 と同じスナップショットしか無いため。下記は新データ到着後に着手する順序。').font = BOLD; r += 2
    hdr = r
    r = put(ws, r, ['#', '対象', '優先度', '提案', '根拠（実測）', '着手条件'])
    style_header(ws, hdr, 6)
    props = [
        (1, '全13ch / 運用基盤', 'P0 即時',
         'ユーザーによる OAuth 再認可。13ch すべて失効し、リフレッシュ成功歴がゼロなので自動復旧は起こらない。',
         'data/youtube_tokens.db: 全13件の expires_at が過去。updated_at が一律 expires_at+8h＝リフレッシュ実績なし。backend.log 直近5000行に OAuth系エラー258件。',
         'ユーザー操作（自動不可）'),
        (2, '全13ch / 運用基盤', 'P0 即時',
         '公開が止まっている間は生成も止める判断を検討。09-09以降も生成は回り続けており、未公開在庫だけが積み上がっている。',
         '公開実績: 09-08 が最後（09-04〜08は日20〜32本）。以降 5 日間で 0 本。',
         'ユーザー判断'),
        (3, 'fake-paper', 'P1',
         '停止または全面作り直し。30日・17本・39,985再生で登録0は構造的な失敗であって調整では動かない。',
         '登録/千 0.000（全12ch中唯一）。維持率 38.2% も最低水準。',
         '新データ到着後'),
        (4, 'clip-lab / clip-kaneko / clip-fukada', 'P1',
         '切り抜き3chは登録導線を持たない前提で、投稿枠をゆっくり系へ振り替える。',
         '切り抜き4ch 登録/千 0.101 に対しゆっくり8ch 0.461＝4.58倍（窓30日・ゆっくり8ch/切り抜き4ch構成）。clip-lab は223,866再生で登録1。',
         '新データ到着後'),
        (5, '2ch-matome', 'P1',
         '再生ではなく高評価を取りに行く構成へ。現状は「あげてけ」系スレで再生は出るが高評価率0.24%で止まっている。',
         '登録/千 0.175（ゆっくり系最下位）。497,948再生で87登録。29,761再生・登録0の動画あり。',
         '新データ到着後'),
        (6, '全ゆっくり系', 'P1',
         '高評価を明示的に取りにいく施策を1つ入れて効果を測る。登録と相関する指標がこれしか無い。',
         '登録/千 vs 高評価率 r=+0.308（205本）。維持率 r=-0.047、CTR r=+0.069 はいずれも無相関。',
         '新データ到着後'),
        (7, 'company-facts', 'P2',
         '絵文字先頭を「強い」前提で扱うのをやめる。ch内比較では逆効果。',
         'ch横断では絵文字先頭 0.590 / なし 0.353 だが、company-facts 内では 0.686 / 0.915 と逆転。横断の差は「company-facts が絵文字を多用する高効率ch」であることの反映（シンプソンのパラドックス）。',
         '新データ到着後'),
        (8, 'scp-lab', 'P2',
         '09-12 の週7日化の効果検証。ただし全ゆっくり系の曜日別では土曜が最悪(0.268)で、scp-lab 単独の土日の強さ(0.763/0.774)と食い違う。検証は ch 単独で行うこと。',
         '曜日別 登録/千（ゆっくり6ch）: 水0.531 木0.512 日0.446 金0.445 火0.388 土0.268 月0.148。',
         '新データ到着後（verify_on 2026-09-19）'),
        (9, 'pokemon-lab / yokai-watch', 'P2',
         '「どっちが勝つ？」「元ネタが怖すぎる」型の量産を絞る。再生は出るが登録に変換されていない。',
         'yokai-watch: 40,312再生／40,231再生／37,483再生 の3本がいずれも登録0。pokemon-lab も33,977・33,522・31,532再生で登録0。',
         '新データ到着後'),
        (10, 'clip-animal / socio-rx', 'P2',
         '稼働できていない事実を認めて停止するか、素材要件を満たすまで対象外にする。',
         'clip-animal: 3本・17再生。Autopilot は「切り抜ける元動画が見つかりません」で継続失敗。socio-rx: analytics.db に行が1件も無い。',
         '新データ到着後'),
    ]
    for p in props:
        fill = WARN if p[2].startswith('P0') else None
        r = put(ws, r, list(p), fill=fill)
        for c_ in range(1, 7):
            ws.cell(row=r-1, column=c_).alignment = Alignment(wrap_text=True, vertical='top')
        ws.row_dimensions[r-1].height = 58

    # ---------------- 前回比較 ----------------
    ws = wb.create_sheet('前回比較')
    widths(ws, [24, 18, 18, 14, 60])
    r = 1
    ws.cell(row=r, column=1, value='前回比較（前回 = reports/youtube_analysis_20260912.xlsx）').font = T_FONT; r += 2
    ws.cell(row=r, column=1, value='■ データ鮮度').font = BOLD; r += 1
    hdr = r
    r = put(ws, r, ['項目', '前回(09-12)', '今回(09-13)', '差分', '意味'])
    style_header(ws, hdr, 5)
    for row_ in [
        ('video_metrics 最終日', '2026-09-08', '2026-09-08', '変化なし', '新規実績ゼロが4日連続→5日連続に伸びた'),
        ('channel_metrics 最終日', '2026-09-05', '2026-09-05', '変化なし', '同上'),
        ('最終公開日', '2026-09-08', '2026-09-08', '変化なし', '5日間 公開0本'),
        ('OAuth 失効ch数', '13 / 13', '13 / 13', '変化なし', '最新でも pokemon-lab 09-09 14:43 UTC＝約3.4日前'),
        ('リフレッシュ成功歴', 'ゼロ', 'ゼロ', '変化なし', 'updated_at が全件 expires_at+8h のまま'),
    ]:
        r = put(ws, r, list(row_))
    r += 1

    ws.cell(row=r, column=1, value='■ 30日窓KPI（前回と同一スナップショットのため数値も同一。整合確認として掲載）').font = BOLD; r += 1
    hdr = r
    r = put(ws, r, ['チャンネル', '前回 登録/千', '今回 登録/千', '差分', '備考'])
    style_header(ws, hdr, 5)
    prev = {'scp-lab': 0.851, 'company-facts': 0.733, 'akashic-librarian': 0.727,
            'daily-science': 0.423, 'pokemon-lab': 0.336, 'yokai-watch': 0.324,
            'clip-fukada': 0.193, 'clip-kaneko': 0.178, '2ch-matome': 0.175,
            'clip-lab': 0.004, 'fake-paper': 0.000}
    for cid, pv in sorted(prev.items(), key=lambda x: -x[1]):
        d = ch.get(cid)
        cur = round((d['subs'] or 0) * 1000 / max(d['views'] or 1, 1), 3) if d else None
        diff = round((cur or 0) - pv, 3)
        r = put(ws, r, [cid, pv, cur, diff, '一致' if abs(diff) < 0.0015 else '再計算で差分あり'])
        for c_ in (2, 3, 4): ws.cell(row=r-1, column=c_).number_format = '0.000'
    r += 1

    ws.cell(row=r, column=1, value='■ 前回(09-12)の config 変更と検証状況').font = BOLD; r += 1
    hdr = r
    r = put(ws, r, ['対象', '変更内容', '根拠', '検証期日', '本日時点の判定'])
    style_header(ws, hdr, 5)
    for row_ in [
        ('scp-lab', 'autopilot.schedule を平日限定→週7日（週15→21本）', '曜日別 登録/千 土0.763 日0.774、登録/千は6ch中1位',
         '2026-09-19', '検証不能。変更後に公開された動画が0本のため、効果を測る材料が存在しない'),
        ('company-facts', 'autopilot 枠を3→4（12:30 を増設、週21→28本）', '登録/千0.711(2位)・維持率56.7%(1位)・有効CTR2.19%(1位)、正午帯が未使用',
         '2026-09-19', '検証不能。同上'),
        ('切り抜き3ch', 'ゲート付与＋キュー補充を title_constraints に通す', 'キュー99件中ゲート合格24件(24.2%)、company-facts は12件全滅',
         '—', '構造修正のため実績待ちではない。効果は次回公開分のタイトル品質で測る'),
    ]:
        r = put(ws, r, list(row_))
        for c_ in range(1, 6):
            ws.cell(row=r-1, column=c_).alignment = Alignment(wrap_text=True, vertical='top')
        ws.row_dimensions[r-1].height = 44
    r += 1
    ws.cell(row=r, column=1, value='★ 結論: 09-12 の2件はいずれも「投稿本数を増やす」変更だが、公開経路が止まっているため本数は増えていない。'
                                    'トークン再認可までは、どの施策変更も効果検証ができない。').font = BOLD
    r += 1
    ws.cell(row=r, column=1, value='★ 本日 config を変更しなかった理由: 同一スナップショットでの二重判断を避けるため（タスク定義の鉄則）。').font = BOLD

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    wb.save(OUT)
    print('saved', OUT)


if __name__ == '__main__':
    build()
