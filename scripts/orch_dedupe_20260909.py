# -*- coding: utf-8 -*-
"""2ch-matome の「ワイ」パターンの重複を解消する。

行頭限定 `^\\s*ワイ` は位置不問 `(?<![ハスロ])ワイ(?![ドヤンルフパブザ])` の
部分集合なので、両方あっても挙動は変わらないが読み手が混乱する。
（稼働中のバックエンドに設定を上書きされた後、再適用したときに復活したもの）
"""
import json
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
p = 'data/channels/2ch-matome.json'
d = json.load(open(p, encoding='utf-8'))
pats = d['title_rules']['hard_constraints']['forbid_patterns']
before = len(pats)
d['title_rules']['hard_constraints']['forbid_patterns'] = [
    q for q in pats if q.get('pattern') != r'^\s*ワイ']
after = len(d['title_rules']['hard_constraints']['forbid_patterns'])
with open(p + '.tmp', 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
os.replace(p + '.tmp', p)
print(f'2ch-matome forbid_patterns: {before} → {after}')
for q in d['title_rules']['hard_constraints']['forbid_patterns']:
    print('  -', q['label'], '|', q['pattern'])
