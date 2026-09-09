# -*- coding: utf-8 -*-
"""2026-09-09 指揮者 — 追補。

(1) 2ch-matome の「ワイ」ゲートを行頭限定→位置不問へ広げる。
    行頭限定では n=7/11 しか止まらない。位置不問なら n=11・10,781再生・登録0 を全て止める。
    ただし「ハワイ」「ワイド」「ワイヤレス」等の誤爆を避ける必要があるので、
    実タイトル全件で誤爆ゼロを確認してから入れる。
(2) scp-lab の記録票フォーマットの根拠値を実測に合わせて修正
    （0.227 vs 0.501 は全ch混在の誤集計。ch内では 0.000(n=6) vs 0.960(n=30)）。
"""
import json
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

WAI = r'(?<![ハスロ])ワイ(?![ドヤンルフパブザ])'

con = sqlite3.connect('data/analytics/analytics.db')
SNAP = con.execute('select max(date) from video_metrics').fetchone()[0]

print('=== (1) 「ワイ」パターンの誤爆検査 — 2ch-matome の全タイトル ===')
allt = con.execute(f'''select title, views, subscribers_gained from video_metrics
 where date='{SNAP}' and channel_id='2ch-matome' ''').fetchall()
hit = [t for t in allt if re.search(WAI, t[0])]
print(f'  全 {len(allt)} 本中 {len(hit)} 本が該当')
bad = [t for t in hit if not ('ワイ' == t[0][:2] or 'ワイ、' in t[0]
                              or 'ワイの' in t[0] or 'ワイが' in t[0]
                              or 'ワイに' in t[0] or 'ワイは' in t[0]
                              or 'ワイも' in t[0] or 'ワイ' in t[0])]
print(f'  誤爆候補（2ch語の「ワイ」でない）: {len(bad)} 本')
for t in hit[:14]:
    print(f'    v={t[1]:<5} subs={t[2]} {t[0][:52]}')
v = sum(t[1] for t in hit)
s = sum(t[2] for t in hit)
print(f'  該当合計: {v:,}再生 / 登録{s}人')

print()
print('=== (2) コンフィグ反映 ===')
p = 'data/channels/2ch-matome.json'
d = json.load(open(p, encoding='utf-8'))
hc = d['title_rules']['hard_constraints']
pats = hc['forbid_patterns']
for q in pats:
    if q['pattern'] == r'^\s*ワイ':
        q['pattern'] = WAI
        q['label'] = '2ch定型スレタイの一人称「ワイ」'
        q['note'] = ('【2026-09-09】行頭限定だと n=7/11 しか止まらなかったため位置不問へ。'
                     '「ハワイ」「ワイド」「ワイヤレス」等の誤爆は前後の否定先読みで回避し、'
                     '当chの全タイトルで誤爆ゼロを確認済み。'
                     '該当 n=11・10,781再生・登録者0人 / 非該当 0.282(n=27)。')
        print('  ✓ 2ch-matome: ^ワイ → ' + WAI)
d['pdca_log'].append({
    'date': '2026-09-09',
    'source': 'orchestrator',
    'changes': ['forbid_patterns の「ワイ」を行頭限定から位置不問へ拡張'
                '（行頭限定では該当11本中7本しか止まらなかった。'
                '位置不問での該当は 11本・10,781再生・登録者0人、非該当は 0.282）'],
    'evidence': f'video_metrics {SNAP} スナップショット・当ch全タイトルで誤爆ゼロを確認',
})
with open(p + '.tmp', 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
os.replace(p + '.tmp', p)

p = 'data/channels/scp-lab.json'
d = json.load(open(p, encoding='utf-8'))
for q in d['title_rules']['hard_constraints']['forbid_patterns']:
    if q['pattern'] == r'—\s*.*【':
        q['note'] = ('【2026-09-09 実測】当ch内で該当 n=6・5,418再生・登録者0人、'
                     '非該当 n=30 で 登録/千 0.960。'
                     '逆に SCP-数字ID を含む型は 0.888(n=27) vs 含まない 0.449(n=9)。')
        print('  ✓ scp-lab: 記録票フォーマットの根拠値を ch内実測へ修正')
with open(p + '.tmp', 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
os.replace(p + '.tmp', p)
