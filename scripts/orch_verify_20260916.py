#!/usr/bin/env python3
"""xlsx のセル値を analytics.db から独立に再集計して突合する（鉄則: 手集計を根拠にしない）。"""
import sqlite3, openpyxl, sys

c=sqlite3.connect('data/analytics/analytics.db'); c.row_factory=sqlite3.Row
wb=openpyxl.load_workbook('reports/youtube-analysis-2026-09-16.xlsx', data_only=True)
ws=wb['サマリ']
# サマリのch別表を探す
hdr=None
for row in ws.iter_rows(min_row=1,max_row=60):
    if row[0].value=='チャンネル': hdr=row[0].row; break
assert hdr, 'ヘッダが見つからない'
fails=[]; checked=0
r=hdr+1
while ws.cell(r,1).value and ws.cell(r,1).value!='合計 / 全13ch':
    ch=ws.cell(r,1).value; snap=ws.cell(r,4).value
    q=c.execute("""SELECT COUNT(*) n, COALESCE(SUM(views),0) v, COALESCE(SUM(likes),0) l,
        COALESCE(SUM(subscribers_gained),0) s, COALESCE(SUM(comments),0) cm
        FROM video_metrics WHERE channel_id=? AND date=?""",(ch,snap)).fetchone()
    exp_sp = q['s']/q['v']*1000 if q['v'] else 0
    exp_lr = q['l']/q['v']*100 if q['v'] else 0
    exp_avg = q['v']/q['n'] if q['n'] else 0
    for label,got,exp in [('本数',ws.cell(r,5).value,q['n']),('総再生',ws.cell(r,6).value,q['v']),
        ('平均再生',ws.cell(r,7).value,exp_avg),('登録者',ws.cell(r,8).value,q['s']),
        ('登録/千',ws.cell(r,9).value,exp_sp),('いいね数',ws.cell(r,10).value,q['l']),
        ('いいね率',ws.cell(r,11).value,exp_lr),('コメント',ws.cell(r,12).value,q['cm'])]:
        checked+=1
        if got is None: fails.append(f'{ch} {label}: セルが None（キャッシュ値なし）'); continue
        if abs(float(got)-float(exp))>max(0.001, abs(exp)*1e-6):
            fails.append(f'{ch} {label}: xlsx={got} db={exp}')
    r+=1
# 合計行
tot=ws.cell(r,6).value
allv=0; alls=0
for ch in [ws.cell(x,1).value for x in range(hdr+1,r)]:
    d=c.execute("SELECT MAX(date) FROM video_metrics WHERE channel_id=?",(ch,)).fetchone()[0]
    q=c.execute("SELECT COALESCE(SUM(views),0) v, COALESCE(SUM(subscribers_gained),0) s FROM video_metrics WHERE channel_id=? AND date=?",(ch,d)).fetchone()
    allv+=q['v']; alls+=q['s']
checked+=2
if abs(float(tot)-allv)>1: fails.append(f'合計 総再生: xlsx={tot} db={allv}')
if abs(float(ws.cell(r,8).value)-alls)>0.5: fails.append(f'合計 登録: xlsx={ws.cell(r,8).value} db={alls}')

# 直近動画一覧: 行数と views=0 件数
ws2=wb['直近動画一覧']
n=0; z=0
for row in ws2.iter_rows(min_row=5):
    if not row[0].value or str(row[0].value).startswith('※'): break
    n+=1
    if (row[3].value or 0)==0: z+=1
dbn=c.execute("""SELECT COUNT(*) FROM video_metrics vm WHERE date=(SELECT MAX(date) FROM video_metrics v2 WHERE v2.channel_id=vm.channel_id)
  AND published_at>='2026-09-07'""").fetchone()[0]
checked+=1
print(f'直近動画一覧 行数 xlsx={n} / db(概算)={dbn} / views=0 は {z}本')

print(f'\n突合 {checked} 項目 / 不一致 {len(fails)} 件')
for f in fails: print('  ✗',f)
sys.exit(1 if fails else 0)
