import re
import sqlite3

con = sqlite3.connect('data/analytics/analytics.db')
SNAP = con.execute('select max(date) from video_metrics').fetchone()[0]
CH6 = ['daily-science', 'scp-lab', '2ch-matome',
       'pokemon-lab', 'yokai-watch', 'company-facts']
rows = con.execute(f'''select channel_id,title,views,subscribers_gained
 from video_metrics where date='{SNAP}'
 and substr(published_at,1,10)<='2026-09-05' and views>=200
 and channel_id in ({','.join(f"'{c}'" for c in CH6)})''').fetchall()


def a(seg):
    v = sum(r[2] for r in seg)
    s = sum(r[3] for r in seg)
    return f'n={len(seg)} views={v:,} subs={s} 登録/千={1000*s/v:.3f}' if v else 'n=0'


ch2 = [r for r in rows if r[0] == '2ch-matome']
print('2ch startswith(ワイ) or 質問ある :',
      a([r for r in ch2 if r[1].startswith('ワイ') or '質問ある' in r[1]]))
print('2ch それ以外                   :',
      a([r for r in ch2 if not (r[1].startswith('ワイ') or '質問ある' in r[1])]))
print('2ch ワイ を含む(位置不問)        :',
      a([r for r in ch2 if 'ワイ' in r[1] or '質問ある' in r[1]]))
print('2ch 上記以外                   :',
      a([r for r in ch2 if not ('ワイ' in r[1] or '質問ある' in r[1])]))
print()
scp = [r for r in rows if r[0] == 'scp-lab']
print('scp 「— …【ラベル】」型 :', a([r for r in scp if re.search(r'—\s*.*【', r[1])]))
print('scp それ以外           :', a([r for r in scp if not re.search(r'—\s*.*【', r[1])]))
print('scp SCP-ID あり        :', a([r for r in scp if re.search(r'SCP-\d+', r[1])]))
print('scp SCP-ID なし        :', a([r for r in scp if not re.search(r'SCP-\d+', r[1])]))
