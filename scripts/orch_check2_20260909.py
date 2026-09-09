import sqlite3

c = sqlite3.connect('data/analytics/analytics.db')
CH = ('daily-science', 'scp-lab', '2ch-matome', 'pokemon-lab', 'yokai-watch', 'company-facts')
rows = c.execute('''select channel_id,title,views,subscribers_gained,published_at
 from video_metrics where date=(select max(date) from video_metrics)
 and substr(published_at,1,10)<='2026-09-05' and views>=200
 and channel_id in {}'''.format(CH)).fetchall()


def agg(s):
    v = sum(r[2] for r in s)
    sb = sum(r[3] for r in s)
    d = sorted(r[4][:10] for r in s)
    span = f'{d[0]}..{d[-1]}' if d else '-'
    return f'n={len(s):<3} v={v:<6} subs={sb:<3} 登録/千={1000*sb/v:.3f} 公開{span}' if v else 'n=0'


print('=== タイトル末尾フォーマット x 登録/千 (全ch) ===')
kakko = [r for r in rows if '【ショート】' in r[1]]
hashs = [r for r in rows if '#shorts' in r[1]]
print(' 【ショート】型 ', agg(kakko))
print(' #shorts型     ', agg(hashs))
print()
print('=== 「秘密」の内訳 ch別 ===')
for ch in sorted(set(r[0] for r in rows)):
    sub = [r for r in rows if r[0] == ch]
    h = [r for r in sub if '秘密' in r[1]]
    n = [r for r in sub if '秘密' not in r[1]]
    if h:
        print(f'{ch:<15} 秘密あり {agg(h)}')
        print(f'{"":<15} 秘密なし {agg(n)}')
print()
print('=== 高views・低転換 (views>=1200 かつ subs=0) = 最大の取りこぼし ===')
waste = sorted([r for r in rows if r[2] >= 1200 and r[3] == 0], key=lambda r: -r[2])
print(f'  該当 {len(waste)}本 / 合計 {sum(r[2] for r in waste):,}再生 / 登録0')
for r in waste[:12]:
    print(f'   {r[0]:<14} v={r[2]:<5} {r[1][:46]}')
