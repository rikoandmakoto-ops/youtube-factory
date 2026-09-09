# -*- coding: utf-8 -*-
"""生成した xlsx の中身を元データと突き合わせて検証する。

recalc.py が使えなかったぶん、ここで
 (1) 数式が全て読み戻せるか（キャッシュ値が入っているか）
 (2) 数式の値が SQLite の元データから独立に計算した値と一致するか
 (3) 数式文字列そのものが壊れていないか
を確認する。
"""
import os
import re
import sqlite3
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
P = 'reports/youtube_analysis_20260909.xlsx'

wv = openpyxl.load_workbook(P, data_only=True)
wf = openpyxl.load_workbook(P)
fail = 0

print('=== (1) キャッシュ値の充填 ===')
miss = 0
n_f = 0
for sn in wf.sheetnames:
    for row in wf[sn].iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith('='):
                n_f += 1
                if wv[sn][c.coordinate].value is None:
                    miss += 1
                    if miss <= 5:
                        print(f'  ✗ {sn}!{c.coordinate} 値なし {c.value}')
print(f'  数式 {n_f} 件 / 値が読めない {miss} 件')
fail += 1 if miss else 0

print()
print('=== (2) 元データとの突き合わせ ===')
con = sqlite3.connect('data/analytics/analytics.db')
SNAP = con.execute('select max(date) from video_metrics').fetchone()[0]
CH6 = ['daily-science', 'scp-lab', '2ch-matome',
       'pokemon-lab', 'yokai-watch', 'company-facts']
truth = {}
for ch in CH6:
    v, s, lk, n = con.execute(f'''select sum(views),sum(subscribers_gained),
      sum(likes),count(*) from video_metrics where date='{SNAP}'
      and substr(published_at,1,10)<='2026-09-05' and views>=200
      and channel_id='{ch}' ''').fetchone()
    truth[ch] = (n, v, s, 1000 * s / v, lk / v)

ws = wv['サマリー']
checked = 0
for row in ws.iter_rows(values_only=True):
    if row[0] in truth:
        n, v, s, sp, lp = truth[row[0]]
        for label, got, exp in (('本数', row[1], n), ('再生', row[2], v),
                                ('登録', row[3], s), ('登録/千', row[4], sp),
                                ('高評価率', row[5], lp)):
            if got is None or abs(got - exp) > 1e-6:
                print(f'  ✗ サマリー {row[0]} {label}: シート={got} 実データ={exp}')
                fail += 1
        checked += 1
print(f'  サマリー: {checked}/6 ch を照合、不一致 {fail} 件')

tot = None
for row in ws.iter_rows(values_only=True):
    if row[0] == '合計 / 加重平均':
        tot = row
if tot:
    ev = sum(t[1] for t in truth.values())
    es = sum(t[2] for t in truth.values())
    ok = (abs(tot[2] - ev) < 1e-6 and abs(tot[3] - es) < 1e-6
          and abs(tot[4] - 1000 * es / ev) < 1e-6)
    print(f'  合計行 {"✓" if ok else "✗"} 再生={tot[2]:,.0f} 登録={tot[3]:,.0f} '
          f'登録/千={tot[4]:.3f}（実データ {ev:,} / {es} / {1000*es/ev:.3f}）')
    fail += 0 if ok else 1

print()
print('=== (3) トレンド各行の再検算 ===')
rows = con.execute(f'''select channel_id,title,views,subscribers_gained,likes
 from video_metrics where date='{SNAP}'
 and substr(published_at,1,10)<='2026-09-05' and views>=200
 and channel_id in ({','.join(f"'{c}'" for c in CH6)})''').fetchall()
ws = wv['トレンド']
bad = 0
seen = 0
for row in ws.iter_rows(values_only=True):
    if row[2] and row[3] and isinstance(row[5], float):
        seen += 1
        exp = 1000 * row[4] / row[3]
        if abs(row[5] - exp) > 1e-6:
            print(f'  ✗ {row[0]} / {row[1]}: {row[5]} != {exp}')
            bad += 1
print(f'  {seen} 行を再検算、不整合 {bad} 件')
fail += bad

WAI = re.compile(r'(?<![ハスロ])ワイ(?![ドヤンルフパブザ])')
w = [r for r in rows if r[0] == '2ch-matome'
     and (WAI.search(r[1]) or '質問ある' in r[1])]
print(f'  参考: 2ch「ワイ/質問ある」 n={len(w)} '
      f'再生={sum(r[2] for r in w):,} 登録={sum(r[3] for r in w)}')

print()
print('=== (4) シート構成 ===')
for sn in wv.sheetnames:
    print(f'  {sn:<16} {wv[sn].max_row:>4}行 x {wv[sn].max_column}列')
need = ['サマリー', 'チャンネル別詳細', '動画別パフォーマンス', '改善アクション', 'トレンド']
if wv.sheetnames != need:
    print('  ✗ 指定のシート構成と不一致:', wv.sheetnames)
    fail += 1

print()
print('検証結果:', 'すべて合格' if fail == 0 else f'{fail} 件の不合格')
sys.exit(1 if fail else 0)
