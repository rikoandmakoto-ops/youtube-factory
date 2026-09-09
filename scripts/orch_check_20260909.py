import sqlite3
c = sqlite3.connect('data/analytics/analytics.db')
MK = ['理由', '正体', '本当の', '実は', 'わけ', 'なぜ', '真相', '裏側', '実態']
rows = c.execute('''select title,views,subscribers_gained from video_metrics
 where date=(select max(date) from video_metrics) and channel_id='pokemon-lab'
 and substr(published_at,1,10)<='2026-09-05' and views>=200''').fetchall()


def agg(s):
    v = sum(r[1] for r in s)
    sb = sum(r[2] for r in s)
    return f'n={len(s):<3} v={v:<6} subs={sb:<2} 登録/千={1000*sb/v:.3f}' if v else 'n=0'


def cmp(label, rs):
    h = [r for r in rs if any(m in r[0] for m in MK)]
    n = [r for r in rs if not any(m in r[0] for m in MK)]
    print(f'=== {label} ===')
    print('  答え語あり', agg(h))
    print('  答え語なし', agg(n))


cmp('pokemon-lab 全体', rows)
r2 = [r for r in rows if not r[0].startswith(('なぜ', '何故', 'なんで', 'どうして'))]
cmp('なぜ始まり(09-07に禁止済み)を除外', r2)
r3 = [r for r in r2 if '秘密' not in r[0]]
cmp('さらに「秘密」を除外', r3)
print()
print('--- 除外後に残った pokemon-lab タイトル ---')
for t, v, s in sorted(r3, key=lambda r: -(1000 * r[2] / r[1])):
    print(f'  {1000*s/v:.2f} v={v:<5} {t[:56]}')
