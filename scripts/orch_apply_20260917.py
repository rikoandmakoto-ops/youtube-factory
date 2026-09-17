#!/usr/bin/env python3
"""2026-09-17 指揮者 Phase3: 実測に基づく config 適用。

根拠はすべて 2026-09-16 スナップショット（video_metrics・稼働5ch・views>=200・公開08-01以降）。
ch固定効果（各ch自身の平均sp=1.0 に正規化した比）で時刻を評価し、
シンプソンのパラドックスを避けるため「ch内で自ch平均を割っているか」だけを判断材料にした。
"""
import json, re, shutil, datetime, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = '20260917_orch'
Q = re.compile(r'なぜ|のか|？|\?')
DG = re.compile(r"[0-9０-９]+(?:[,，.．\-−―ー/／:：][0-9０-９]+)*")
changes = {}


def load(ch):
    p = os.path.join(BASE, 'data', 'channels', f'{ch}.json')
    shutil.copy2(p, p + f'.bak_pdca_{MARK}')
    return p, json.load(open(p, encoding='utf-8'))


def save(p, d):
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


def log(ch, msg):
    changes.setdefault(ch, []).append(msg)


# ─────────────────────────────────────────────────────────────
# 1. scp-lab : 13:00 枠を 12:45 へ / theme_queue を疑問型優先へ
# ─────────────────────────────────────────────────────────────
p, d = load('scp-lab')
sch = d['autopilot']['schedule']
RSN_13 = ('【2026-09-17 指揮者・実測】13時枠は ch固定効果で 3/3ch すべてが自ch平均を割った'
          '（scp-lab 0.55(n=11) / daily-science 0.50(n=3) / company-facts 0.00(n=4)、'
          '中央値 0.50・views加重 0.42）＝測定できた全時刻で最下位。'
          '当ch内でも 13時 0.437(n=11) は 17時 1.322(n=4)・19時 1.025(n=10) の半分以下。'
          '振替先の12時は 3ch中2ch が自ch平均超（yokai 1.60(n=11) / 2ch 1.24(n=10)）で中央値 1.24。'
          '当ch自身の12時は 0.803(n=2) と薄いが自ch平均 0.791 と同水準。'
          '12:45 にしたのは、12時台を維持しつつ生成開始(45分前=12:00)を '
          'yokai 11:15 / 2ch 11:30 / company-facts 11:45 と衝突させないため。')
for t in sch.get('times', []):
    if t.get('hour') == 13:
        t['hour'], t['minute'] = 12, 45
if sch.get('hour') == 13:
    sch['hour'], sch['minute'] = 12, 45
sch['_times_comment'] = RSN_13
d['autopilot'].setdefault('_schedule_changes', []).append({
    'date': '2026-09-17', 'from': '13:00', 'to': '12:45', 'reason': RSN_13,
    'evaluate_on': '2026-09-24',
    'kill_criterion': '09-24 時点で 12時台枠の 登録/千 が ch平均×0.8 未満（n>=5）なら 16:00 へ再振替',
})
q = d['autopilot'].get('theme_queue') or []
before = [t.get('title', '') for t in q[:3]]
q.sort(key=lambda t: 0 if Q.search(t.get('title', '')) else 1)
d['autopilot']['theme_queue'] = q
d['autopilot']['_queue_rationale_20260917_orch'] = (
    '【2026-09-17 実測】疑問型（なぜ/のか/？）を含むタイトルは ch内対照で 4/4ch すべて自ch平均超'
    '（scp-lab 1.13 vs 非該当0.93 / daily-science 1.23 vs 0.20 / yokai-watch 1.58 vs 0.75 / '
    '2ch-matome 1.41 vs 0.78）。プールでも 0.708(n=65) vs 0.499(n=118)。'
    'ch内一致が全chで取れたタイトル指標は今回が初めて（「正体/真相」は 1/4ch、「実は」は 2/3ch にとどまる）。'
    f'当chのキューは疑問型 {sum(1 for t in q if Q.search(t.get("title","")))}/{len(q)} 件だが'
    f'先頭3件が非疑問型だった（{before}）ため、疑問型を前方へ安定ソートした。'
    '内容・件数は変更していない（並び替えのみ）。')
save(p, d)
log('scp-lab', '投稿枠 13:00 → 12:45（13時は3/3chで自ch平均割れ・全時刻中最下位）')
log('scp-lab', f'theme_queue を疑問型優先に並べ替え（{len(q)}件・内容変更なし）')

# ─────────────────────────────────────────────────────────────
# 2. daily-science : 07:30 枠を 16:30 へ
# ─────────────────────────────────────────────────────────────
p, d = load('daily-science')
sch = d['autopilot']['schedule']
RSN_DS = ('【2026-09-17 指揮者・実測】当chの時間帯ブロック別 登録/千再生は '
          '早朝6-10時 0.240(n=4) / 昼11-15時 0.368(n=14) / 夕16-19時 0.926(n=20) で、'
          '夕は早朝の 3.9倍。早朝ブロックは稼働5ch中4chで最下位ブロック'
          '（プール 早朝0.299(n=23) vs 夕0.695(n=89)）。'
          '当chの 7時は 0.240(n=4)＝自ch平均 0.628 の 0.38倍。'
          '一方 17時は 1.164(n=14)＝自ch平均の 1.85倍で当ch唯一の強い時刻、'
          '17時は稼働5ch全部で測定でき中央値 1.67倍と全時刻中最良。'
          '16:30 は実証済みピーク 17時の直前に置き、生成開始(15:45)を '
          'yokai 15:15 / company-facts 14:15 と衝突させない位置。'
          '⚠️ 当ch自身の16時台は実績ゼロ＝「16時が17時に似る」側への賭けである点は明記しておく。'
          '18時は当ch 0.228(n=6) と弱く、3/3chで自ch平均割れなので選ばなかった。')
for t in sch.get('times', []):
    if t.get('hour') == 7:
        t['hour'], t['minute'] = 16, 30
if sch.get('hour') == 7:
    sch['hour'], sch['minute'] = 16, 30
sch['_times_comment'] = RSN_DS
d['autopilot'].setdefault('_schedule_changes', []).append({
    'date': '2026-09-17', 'from': '07:30', 'to': '16:30', 'reason': RSN_DS,
    'evaluate_on': '2026-09-24',
    'kill_criterion': '09-24 時点で 16時台枠の 登録/千 が ch平均×0.8 未満（n>=5）なら 12:00 ではなく '
                      '19:00 を次候補にする（12時は当ch 0.24 と実測で悪い）',
})
save(p, d)
log('daily-science', '投稿枠 07:30 → 16:30（早朝ブロックは当ch 0.240 vs 夕 0.926＝3.9倍差）')

# ─────────────────────────────────────────────────────────────
# 3. 2ch-matome : theme_queue を疑問型優先へ（枠・フラグは触らない）
# ─────────────────────────────────────────────────────────────
p, d = load('2ch-matome')
q = d['autopilot'].get('theme_queue') or []
nq = sum(1 for t in q if Q.search(t.get('title', '')))
q.sort(key=lambda t: 0 if Q.search(t.get('title', '')) else 1)
d['autopilot']['theme_queue'] = q
d['autopilot']['_queue_rationale_20260917_orch'] = (
    f'【2026-09-17 実測】疑問型 ch内対照 4/4ch 一致（当ch 1.41 vs 非該当 0.78）。'
    f'当chのキューは疑問型 {nq}/{len(q)} 件＝5ch中で最も疑問型比率が低かったため前方へ安定ソート。'
    '内容・件数は変更していない。'
    '⚠️ 投稿枠・autopilot フラグは本日は一切変更していない。'
    '09-16 に enabled を true へ戻したが 09-16 の3枠・09-17 07:30 枠とも '
    'スケジューラが1度も発火しておらず（backend.log に "Autopilot fired for 2ch-matome" が皆無）、'
    '効果測定が成立していない。原因はディスク再読込で config は反映されたが '
    'APScheduler へジョブが再登録されないこと。バックエンド再起動が先。')
save(p, d)
log('2ch-matome', f'theme_queue を疑問型優先に並べ替え（{len(q)}件・疑問型{nq}件・内容変更なし）')
log('2ch-matome', '投稿枠・autopilotフラグは変更なし（09-16の変更が未発火で効果測定が未成立のため）')

# ─────────────────────────────────────────────────────────────
# 4. company-facts : publish_blocked 予防（キュー内のタイトル規約違反を修正）
# ─────────────────────────────────────────────────────────────
p, d = load('company-facts')
hc = d['title_rules']['hard_constraints']
maxg = hc.get('max_digit_groups', 99)
words = hc['require_any_of']['words']
fixed = []
FIXMAP = {
    'セブン-イレブンの日販68万円、24時間営業の採算':
        'セブン-イレブンの日販68万円が維持できる本当の理由',
}
for t in (d['autopilot'].get('theme_queue') or []):
    ttl = t.get('title', '')
    bad_dg = len(DG.findall(ttl)) > maxg
    bad_w = not any(w in ttl for w in words)
    if (bad_dg or bad_w) and ttl in FIXMAP:
        t['title'] = FIXMAP[ttl]
        t['_fix_20260917_orch'] = (
            f'規約違反を事前修復: 数字グループ {len(DG.findall(ttl))}→'
            f'{len(DG.findall(t["title"]))}（上限{maxg}）/ 答え提示語あり。'
            '09-15 に scp-lab が同種の違反で publish_blocked となり1枠を失っている'
            '（SCP-2718・数字2個）ため、公開前にキュー側で潰す。')
        fixed.append((ttl, t['title']))
if fixed:
    d['autopilot']['_queue_fix_20260917_orch'] = [
        {'from': a, 'to': b} for a, b in fixed]
save(p, d)
for a, b in fixed:
    log('company-facts', f'キュー内タイトルの規約違反を事前修正: 「{a}」→「{b}」')
log('company-facts', '投稿枠は変更なし（auto_optimize_schedule=true でバックエンドが枠を自動最適化しているため'
                    '手動変更は上書きされる。16-19時ブロックが当ch最良 0.741(n=18) である点はメモリに記録）')

# ─────────────────────────────────────────────────────────────
# 5. 変更しなかった ch の理由を明示（後続runが同じ判断を蒸し返さないため）
# ─────────────────────────────────────────────────────────────
p, d = load('yokai-watch')
d.setdefault('optimization', {})['_no_change_note_20260917_orch'] = (
    '【2026-09-17 指揮者】投稿枠を変更しなかった。当chは稼働5ch中で唯一 '
    '昼11-15時 1.068(n=12) > 夕16-19時 0.507(n=17) と全体傾向の逆を行く ch で、'
    '17時も 0.65倍（5ch中唯一の平均割れ）。最弱枠は 19時 0.347(n=8)＝自ch平均の 0.49倍だが、'
    '振替候補がいずれも根拠不足: 18時は n=3 かつ 3/3ch で平均割れ、'
    '13時は全時刻中最下位、11時/14時は当ch実績なし。'
    '当chの昼ブロックの強さは実質 12時(n=11) 単独で、13-15時へ外挿できない。'
    '09-14 新設の 16:00 枠が n>=5 に達する 09-24 に再判定する。')
save(p, d)
log('yokai-watch', '変更なし（理由をconfigに明記: 19時が最弱だが振替先に根拠のある時刻がない）')

p, d = load('socio-rx')
d.setdefault('optimization', {})['_no_change_note_20260917_orch'] = (
    '【2026-09-17 指揮者】変更なし。直近スナップショットは 5本・1,091再生・登録0人で、'
    '登録/千再生を推定できる母数に達していない（他chの判断基準は views>=200 かつ ch内 n>=10）。'
    'auto_optimize_schedule=true のため枠はバックエンド側が持つ。'
    'n>=10 に達するまで実績ベースの変更はしない。')
save(p, d)
log('socio-rx', '変更なし（n=5・登録0で母数不足）')

# ─────────────────────────────────────────────────────────────
out = {
    'generated_at': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
    'marker': 'orch_20260917',
    'snapshot_used': '2026-09-16',
    'note': 'このファイルが存在する日は、後続の指揮者 run は Phase3(config適用) をスキップすること（09-15 メモ §9-4 の既定手順）。',
    'channels': changes,
    'untouched': {
        'pokemon-lab / fake-paper / akashic-librarian / clip-lab / clip-fukada / clip-kaneko / clip-animal':
            'OAuth 失効で 09-06〜09-08 からスナップショットが凍結。同一データでの二重意思決定を避けるため変更しない。',
    },
}
json.dump(out, open(os.path.join(BASE, 'reports', 'orch_config_changes_20260917.json'), 'w',
                    encoding='utf-8'), ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
