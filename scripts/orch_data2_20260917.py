#!/usr/bin/env python3
"""2026-09-17 指揮者: 追加集計（時刻ch固定効果 / 時間帯ブロック / タイトル型 / 前回比較）。
既存の reports/_orch_20260917_data.json に追記する。集計は全てここに集約する。"""
import sqlite3, json, re, datetime, statistics, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, 'data/analytics/analytics.db')
OUT = os.path.join(BASE, 'reports/_orch_20260917_data.json')
ACT5 = ['scp-lab', 'daily-science', 'yokai-watch', 'company-facts', '2ch-matome']
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
D = json.load(open(OUT, encoding='utf-8'))


def rows_for(chs, min_views=200, since='2026-08-01'):
    out = []
    for ch in chs:
        d = c.execute("SELECT MAX(date) FROM video_metrics WHERE channel_id=?", (ch,)).fetchone()[0]
        for r in c.execute("SELECT * FROM video_metrics WHERE channel_id=? AND date=?", (ch, d)):
            r = dict(r)
            if r['views'] < min_views or not r['published_at'] or r['published_at'][:10] < since:
                continue
            dt = datetime.datetime.fromisoformat(r['published_at'].replace('Z', '+00:00')) + datetime.timedelta(hours=9)
            r['_h'] = dt.hour; r['_ch'] = ch; r['_jst'] = dt
            out.append(r)
    return out


def sp(v):
    vw = sum(x['views'] for x in v)
    return (sum(x['subscribers_gained'] for x in v) / vw * 1000) if vw else 0.0


R = rows_for(ACT5)
base = {ch: sp([r for r in R if r['_ch'] == ch]) for ch in ACT5}
D['ch_baseline_sp'] = base

# ── 1. 時刻別 ch固定効果（各chの自ch平均=1.0 に正規化）──
hours = []
for h in range(24):
    per = []
    for ch in ACT5:
        v = [r for r in R if r['_ch'] == ch and r['_h'] == h]
        if len(v) < 3 or base[ch] <= 0:
            continue
        per.append({'ch': ch, 'n': len(v), 'views': sum(x['views'] for x in v),
                    'subs': sum(x['subscribers_gained'] for x in v),
                    'sp': sp(v), 'ratio': sp(v) / base[ch]})
    if len(per) < 2:
        continue
    hours.append({'hour': h, 'nch': len(per), 'n': sum(p['n'] for p in per),
                  'median_ratio': statistics.median([p['ratio'] for p in per]),
                  'weighted_ratio': sum(p['views'] * p['ratio'] for p in per) / sum(p['views'] for p in per),
                  'below_own_avg': sum(1 for p in per if p['ratio'] < 1.0),
                  'detail': per})
D['hour_fixed_effect'] = sorted(hours, key=lambda x: -x['median_ratio'])

# ── 2. 時間帯ブロック × ch ──
def blk(h):
    return '早朝6-10' if 6 <= h < 11 else ('昼11-15' if 11 <= h < 16 else ('夕16-19' if 16 <= h < 20 else '夜20-5'))


BL = ['早朝6-10', '昼11-15', '夕16-19', '夜20-5']
D['blocks'] = {'labels': BL, 'by_ch': {}, 'pool': {}}
for ch in ACT5:
    D['blocks']['by_ch'][ch] = {}
    for b in BL:
        v = [r for r in R if r['_ch'] == ch and blk(r['_h']) == b]
        D['blocks']['by_ch'][ch][b] = {'n': len(v), 'sp': sp(v), 'views': sum(x['views'] for x in v)} if v else None
for b in BL:
    v = [r for r in R if blk(r['_h']) == b]
    D['blocks']['pool'][b] = {'n': len(v), 'sp': sp(v), 'views': sum(x['views'] for x in v)}

# ── 3. タイトル型（ch内対照）──
PATS = {'疑問型(なぜ/のか)': r'なぜ|のか', '疑問符(？)のみ': r'？|\?',
        '疑問型(なぜ/のか/？)': r'なぜ|のか|？|\?', '正体/真相': r'正体|真相',
        '理由/わけ': r'理由|わけ', '実は': r'実は', '裏側': r'裏側', '数字あり': r'[0-9０-９]'}
D['title_patterns'] = []
for name, rx in PATS.items():
    hit = [r for r in R if re.search(rx, r['title'] or '')]
    mis = [r for r in R if not re.search(rx, r['title'] or '')]
    per = []
    for ch in ACT5:
        h = [r for r in hit if r['_ch'] == ch]; m = [r for r in mis if r['_ch'] == ch]
        if len(h) >= 3 and len(m) >= 3 and base[ch] > 0:
            per.append({'ch': ch, 'n_hit': len(h), 'n_mis': len(m),
                        'r_hit': sp(h) / base[ch], 'r_mis': sp(m) / base[ch]})
    D['title_patterns'].append({
        'pattern': name, 'n_hit': len(hit), 'n_mis': len(mis),
        'sp_hit': sp(hit), 'sp_mis': sp(mis),
        'agree': sum(1 for p in per if p['r_hit'] > p['r_mis']), 'ch_tested': len(per), 'detail': per})

# ── 4. 実効文字数帯 ──
def eff(t):
    t = re.sub(r'[#＃][^\s:：]+', '', t or ''); t = re.sub(r'【[^】]*】', '', t)
    return len(t.strip())


D['len_bands'] = []
for lo, hi in [(0, 20), (20, 25), (25, 30), (30, 35), (35, 99)]:
    v = [r for r in R if lo <= eff(r['title']) < hi]
    D['len_bands'].append({'band': f"{lo}-{hi if hi < 99 else '+'}字", 'n': len(v), 'sp': sp(v),
                           'views': sum(x['views'] for x in v)})

# ── 5. 前回比較（09-16 レポート＝09-15 スナップショット との差）──
prev_path = os.path.join(BASE, 'reports/_orch_20260916_data.json')
D['prev_report'] = {}
if os.path.exists(prev_path):
    P = json.load(open(prev_path, encoding='utf-8'))
    D['prev_report'] = {
        'generated_at': P.get('generated_at'), 'snapshots': P.get('snapshots'),
        'system_ratio': P.get('system_ratio', {}).get('value'),
        'like_q_ratio': P.get('like_q_ratio'), 'like_q_monotone': P.get('like_q_monotone'),
        'channels': {k: {'sp': v['cur']['sp'], 'lr': v['cur']['lr'], 'avp': v['cur']['avp'],
                         'views': v['cur']['views'], 'subs': v['cur']['subs'], 'snap': v['snap']}
                     for k, v in P.get('channels', {}).items()},
        'configs': {k: {'slots': v['slots'], 'queue': v['queue'], 'enabled': v['enabled']}
                    for k, v in P.get('configs', {}).items()},
    }

# ── 6. 公開実績（09-13 以降・ch×日）──
pub = {}
for r in c.execute("SELECT DISTINCT video_id,channel_id,published_at FROM video_metrics WHERE published_at>='2026-09-12'"):
    dt = datetime.datetime.fromisoformat(r['published_at'].replace('Z', '+00:00')) + datetime.timedelta(hours=9)
    pub.setdefault(r['channel_id'], {}).setdefault(dt.strftime('%m-%d'), 0)
    pub[r['channel_id']][dt.strftime('%m-%d')] += 1
D['publish_counts'] = pub

json.dump(D, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('hour_fixed_effect:', [(h['hour'], round(h['median_ratio'], 2), h['n']) for h in D['hour_fixed_effect']])
print('title_patterns:', [(p['pattern'], f"{p['agree']}/{p['ch_tested']}", round(p['sp_hit'], 3), round(p['sp_mis'], 3)) for p in D['title_patterns']])
print('publish:', {k: v for k, v in pub.items()})
