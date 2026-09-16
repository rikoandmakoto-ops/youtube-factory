#!/usr/bin/env python3
"""2026-09-16 指揮者: analytics.db から xlsx 用のデータを全部出す（集計は1箇所に集約）。"""
import sqlite3, json, re, datetime, os

DB='data/analytics/analytics.db'
NAMES={'scp-lab':'ゆっくり異常存在SCPラボ','daily-science':'リコとマコトのゆっくり日常科学',
 'yokai-watch':'ゆっくり妖怪ラボ','company-facts':'企業のホンネ','2ch-matome':'ゆっくり2chスレまとめ劇場',
 'pokemon-lab':'ポケモン考察ラボ','socio-rx':'社会学の処方箋','fake-paper':'架空論文ファイル',
 'akashic-librarian':'ラグナロクの司書','clip-lab':'切り抜きラボ（ひろゆき）',
 'clip-fukada':'深田えいみ 切り抜き','clip-kaneko':'金子みゆ 切り抜き','clip-animal':'動物情報局'}
SYS={'scp-lab':'ゆっくり系','daily-science':'ゆっくり系','yokai-watch':'ゆっくり系',
 'company-facts':'ゆっくり系','2ch-matome':'ゆっくり系','pokemon-lab':'ゆっくり系',
 'socio-rx':'ゆっくり系','fake-paper':'ゆっくり系','akashic-librarian':'長尺系',
 'clip-lab':'切り抜き系','clip-fukada':'切り抜き系','clip-kaneko':'切り抜き系','clip-animal':'切り抜き系'}
ORDER=['scp-lab','daily-science','yokai-watch','company-facts','2ch-matome','socio-rx',
 'pokemon-lab','fake-paper','akashic-librarian','clip-lab','clip-fukada','clip-kaneko','clip-animal']
ACT5=['scp-lab','daily-science','yokai-watch','company-facts','2ch-matome']
DG=re.compile(r"[0-9０-９]+(?:[,，.．\-−―ー/／:：][0-9０-９]+)*")

c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
def rows_at(ch,d):
    return [dict(r) for r in c.execute("SELECT * FROM video_metrics WHERE channel_id=? AND date=?",(ch,d))]
def latest(ch):
    r=c.execute("SELECT MAX(date) FROM video_metrics WHERE channel_id=?",(ch,)).fetchone()[0]; return r
def prev(ch,d):
    r=c.execute("SELECT MAX(date) FROM video_metrics WHERE channel_id=? AND date<?",(ch,d)).fetchone()[0]; return r
def A(sel):
    v=sum(r['views'] for r in sel); s=sum(r['subscribers_gained'] for r in sel)
    l=sum(r['likes'] for r in sel); cm=sum(r['comments'] for r in sel)
    avp=(sum(r['avg_view_percentage'] for r in sel)/len(sel)) if sel else 0
    return dict(n=len(sel),views=v,subs=s,likes=l,comments=cm,avp=avp,
                sp=(s/v*1000 if v else 0), lr=(l/v*100 if v else 0))

out={'generated_at':datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),'channels':{},'snapshots':{}}

# ---- ch別 最新/前回スナップショット
for ch in ORDER:
    d=latest(ch)
    if not d: continue
    p=prev(ch,d)
    cur=rows_at(ch,d); pre=rows_at(ch,p) if p else []
    a=A(cur); b=A(pre)
    # 同一動画のみの純増（窓回転を除去）
    curm={r['video_id']:r for r in cur}; prem={r['video_id']:r for r in pre}
    both=set(curm)&set(prem)
    same=dict(n=len(both),
        dviews=sum(curm[v]['views'] for v in both)-sum(prem[v]['views'] for v in both),
        dsubs=sum(curm[v]['subscribers_gained'] for v in both)-sum(prem[v]['subscribers_gained'] for v in both),
        dlikes=sum(curm[v]['likes'] for v in both)-sum(prem[v]['likes'] for v in both))
    out['channels'][ch]=dict(name=NAMES[ch],system=SYS[ch],snap=d,prev_snap=p,cur=a,prev=b,same=same,
        stale=(d<'2026-09-15'))
    out['snapshots'][ch]=d

# ---- 系統別
allrows=[]
for ch in ORDER:
    d=latest(ch)
    if d: allrows+= [dict(r,**{'_ch':ch}) for r in rows_at(ch,d)]
out['systems']={}
for sysname in ['ゆっくり系','切り抜き系','長尺系']:
    sel=[r for r in allrows if SYS[r['_ch']]==sysname]
    chs=sorted({r['_ch'] for r in sel})
    out['systems'][sysname]=dict(A(sel), nch=len(chs), chs=chs)
yy=out['systems']['ゆっくり系']['sp']; cl=out['systems']['切り抜き系']['sp']
out['system_ratio']=dict(value=yy/cl if cl else 0,
    label=f"ゆっくり{out['systems']['ゆっくり系']['nch']}ch ÷ 切り抜き{out['systems']['切り抜き系']['nch']}ch")

# ---- いいね率4分位（稼働5ch・views>=200）
sel=[r for r in allrows if r['_ch'] in ACT5 and r['views']>=200]
sel.sort(key=lambda r:r['likes']/r['views'])
n=len(sel); q=n//4
out['like_quartiles']=[]
for i in range(4):
    part=sel[i*q:(i+1)*q if i<3 else n]
    out['like_quartiles'].append(dict(A(part),q=f"Q{i+1}"))
qs=[x['sp'] for x in out['like_quartiles']]
out['like_q_ratio']=qs[3]/qs[0] if qs[0] else 0
out['like_q_monotone']=all(qs[i]<=qs[i+1] for i in range(3))

# ---- ch内対照（いいね率 / 維持率 中央値二分）4スナップショットで再測
out['within_ch']={}
for snapd in ['2026-09-08','2026-09-13','2026-09-14','2026-09-15']:
    res={}
    for ch in ACT5:
        s=[r for r in rows_at(ch,snapd) if r['views']>=200]
        if len(s)<10: res[ch]=None; continue
        s2=sorted(s,key=lambda r:r['likes']/r['views']); h=len(s2)//2
        s3=sorted(s,key=lambda r:r['avg_view_percentage']); h3=len(s3)//2
        res[ch]=dict(n=len(s),
            like_lo=A(s2[:h])['sp'],like_hi=A(s2[h:])['sp'],
            ret_lo=A(s3[:h3])['sp'],ret_hi=A(s3[h3:])['sp'])
        res[ch]['like_ok']=res[ch]['like_hi']>res[ch]['like_lo']
        res[ch]['ret_ok']=res[ch]['ret_hi']>res[ch]['ret_lo']
    out['within_ch'][snapd]=res

# ---- 維持率バンド（ゆっくり8ch・views>=200）
sely=[r for r in allrows if SYS[r['_ch']]=='ゆっくり系' and r['views']>=200]
out['ret_bands']=[]
for lo,hi in [(0,30),(30,40),(40,50),(50,60),(60,70),(70,999)]:
    part=[r for r in sely if lo<=r['avg_view_percentage']<hi]
    out['ret_bands'].append(dict(A(part),band=f"{lo}-{hi if hi<999 else '+'}%"))

# ---- 公開時刻(JST)別（稼働6ch・公開08-01以降・views>=200）
ACT6=ACT5+['socio-rx']
byh={}
for r in allrows:
    if r['_ch'] not in ACT6 or r['views']<200 or not r['published_at']: continue
    if r['published_at'][:10]<'2026-08-01': continue
    dt=datetime.datetime.fromisoformat(r['published_at'].replace('Z','+00:00'))+datetime.timedelta(hours=9)
    byh.setdefault(dt.hour,[]).append(r)
out['by_hour']=sorted([dict(A(v),hour=h) for h,v in byh.items()],key=lambda x:-x['sp'])

# ---- 直近動画一覧（09-07以降公開・各ch最新スナップ）
vids=[]
for r in allrows:
    if not r['published_at'] or r['published_at'][:10]<'2026-09-07': continue
    dt=datetime.datetime.fromisoformat(r['published_at'].replace('Z','+00:00'))+datetime.timedelta(hours=9)
    vids.append(dict(ch=r['_ch'],pub_jst=dt.strftime('%Y-%m-%d %H:%M'),title=r['title'] or '',
        views=r['views'],likes=r['likes'],comments=r['comments'],subs=r['subscribers_gained'],
        avp=r['avg_view_percentage'],ctr=r['ctr'],imp=r['impressions'],
        digits=len(DG.findall(r['title'] or '')),
        state='計測済' if r['views']>0 else '未計測(ラグ)'))
vids.sort(key=lambda x:(x['ch'],x['pub_jst']))
out['videos']=vids
out['videos_zero']=sum(1 for v in vids if v['views']==0)

# ---- config 実測
out['configs']={}
for ch in ORDER:
    d=json.load(open(f'data/channels/{ch}.json'))
    ap=d.get('autopilot',{}); sch=ap.get('schedule',{}) or {}
    times=sch.get('times') or []
    tl=[f"{t.get('hour'):02d}:{t.get('minute',0):02d}" for t in times] or [f"{sch.get('hour',0):02d}:{sch.get('minute',0):02d}"]
    qn=len(ap.get('theme_queue') or [])
    hc=(d.get('title_rules') or {}).get('hard_constraints') or {}
    qv=sum(1 for t in (ap.get('theme_queue') or []) if len(DG.findall(t.get('title','')))>(hc.get('max_digit_groups') or 99))
    out['configs'][ch]=dict(enabled=bool(ap.get('enabled')),slots=tl,nslots=len(tl),queue=qn,
        stock=qn/max(len(tl),1), mdg=hc.get('max_digit_groups'), mineff=hc.get('min_effective_chars'),
        gate=bool(hc), dow=sch.get('days_of_week'), mdg_viol=qv,
        band=((d.get('optimization') or {}).get('retention_target_band') or {}).get('min'))

json.dump(out,open('reports/_orch_20260916_data.json','w'),ensure_ascii=False,indent=1)
print('OK  channels=%d videos=%d zero=%d'%(len(out['channels']),len(vids),out['videos_zero']))
print('系統倍率 %.2f倍 (%s)'%(out['system_ratio']['value'],out['system_ratio']['label']))
print('いいね率Q4/Q1 %.2f倍 単調=%s'%(out['like_q_ratio'],out['like_q_monotone']))
for sd,res in out['within_ch'].items():
    lk=sum(1 for v in res.values() if v and v['like_ok']); rt=sum(1 for v in res.values() if v and v['ret_ok'])
    tot=sum(1 for v in res.values() if v)
    print(f'  {sd}: いいね率 {lk}/{tot}ch  維持率 {rt}/{tot}ch')
