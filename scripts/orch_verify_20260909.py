# -*- coding: utf-8 -*-
"""2026-09-09 指揮者 — 反映内容の検証。

(1) JSON が壊れていないか / symlink が生きているか
(2) 新しい機械ゲートが「止めたい実タイトル」を実際に止めるか
(3) 「止めてはいけない実タイトル（上位実績）」を誤爆していないか
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
os.chdir(ROOT)

from pipeline import title_constraints as tc  # noqa: E402

CH6 = ['daily-science', 'scp-lab', '2ch-matome',
       'pokemon-lab', 'yokai-watch', 'company-facts']

fail = 0

print('=== (1) JSON / symlink 健全性 ===')
for ch in CH6:
    p = f'data/channels/{ch}.json'
    o = f'data/channels_orchestrator/{ch}.json'
    try:
        d = json.load(open(p, encoding='utf-8'))
    except Exception as e:
        print(f'  ✗ {ch}: JSON 破損 {e}')
        fail += 1
        continue
    link_ok = os.path.islink(o) and os.path.realpath(o) == os.path.realpath(p)
    times = [(t['hour'], t['minute'])
             for t in d['autopilot']['schedule']['times']]
    dup = len(times) != len(set(times))
    print(f'  {"✓" if (link_ok and not dup) else "✗"} {ch:<15} '
          f'symlink={link_ok} 枠={times} 重複={dup} '
          f'seeds={len(d.get("theme_seeds", []))}')
    if not link_ok or dup:
        fail += 1

print()
print('=== (2) 止めたい実タイトルが止まるか ===')
con = sqlite3.connect('data/analytics/analytics.db')
cfg = {ch: json.load(open(f'data/channels/{ch}.json', encoding='utf-8'))
       for ch in CH6}

must_block = con.execute('''
 select channel_id,title,views,subscribers_gained from video_metrics
 where date=(select max(date) from video_metrics)
 and substr(published_at,1,10)<='2026-09-05' and views>=200
 and channel_id in ({})
 and (title like '%秘密%' or title like '%99%' or title like 'ワイ%'
      or title like '%質問ある%')
'''.format(','.join(f"'{c}'" for c in CH6))).fetchall()
blocked = 0
for ch, t, v, s in must_block:
    r = tc.check(t, cfg[ch])
    if not r['ok']:
        blocked += 1
    else:
        print(f'  ✗ 素通り {ch:<14} v={v:<5} subs={s} {t[:44]}')
print(f'  → 対象 {len(must_block)}本中 {blocked}本を機械ゲートが停止 '
      f'({100*blocked/len(must_block):.0f}%)')
if blocked < len(must_block):
    fail += 1

print()
print('=== (3) 上位実績タイトルを誤爆していないか ===')
top = con.execute('''
 select channel_id,title,views,subscribers_gained from video_metrics
 where date=(select max(date) from video_metrics)
 and substr(published_at,1,10)<='2026-09-05' and views>=200
 and subscribers_gained>=2
 and channel_id in ({})
'''.format(','.join(f"'{c}'" for c in CH6))).fetchall()
fp = 0
for ch, t, v, s in top:
    clean = t.split(' #')[0].replace('【ショート】', '')
    r = tc.check(clean, cfg[ch])
    if not r['ok']:
        labels = ' / '.join(x['label'] for x in r['violations'])
        # 旧フォーマット由来（連番プレフィックス等）は今回の追加分ではない
        if any(k in labels for k in ('秘密', '99', 'ワイ', '質問ある')):
            fp += 1
            print(f'  ✗ 誤爆 {ch:<14} subs={s} [{labels}] {clean[:40]}')
print(f'  → 高転換 {len(top)}本のうち今回の追加ゲートによる誤爆 {fp}本')
if fp:
    fail += 1

print()
print('=== (4) 新パターンの正規表現が有効か ===')
for ch in CH6:
    hc = cfg[ch]['title_rules']['hard_constraints']
    import re
    for p in hc.get('forbid_patterns', []):
        try:
            re.compile(p['pattern'])
        except re.error as e:
            print(f'  ✗ {ch} 不正な正規表現 {p["pattern"]}: {e}')
            fail += 1
    print(f'  ✓ {ch:<15} banned_words={hc.get("banned_words")} '
          f'patterns={[p["label"] for p in hc.get("forbid_patterns", [])]}')

print()
print('検証結果:', 'すべて合格' if fail == 0 else f'{fail} 件の不合格')
sys.exit(1 if fail else 0)
