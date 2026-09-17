#!/usr/bin/env python3
"""2026-09-17 指揮者 Phase3-b: require_any_of に「のか」を追加（ゲートを実測に合わせる）。

本日の最大の実測: 疑問型（なぜ/のか/？）は ch内対照で 4/4ch すべて自ch平均超。
ところが answer-marker ゲートの許容語に「のか」が無く、
「…は何だったのか」「…どこに消えるのか」型＝実測最良パターンが違反扱いで再生成に回されていた。
ゲートを緩める方向の変更なので publish_blocked は増えない（減る）。
"""
import json, re, shutil, os, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DG = re.compile(r"[0-9０-９]+(?:[,，.．\-−―ー/／:：][0-9０-９]+)*")

# 疑問型が ch内対照で検証できた4ch + 同系統の company-facts（外挿・要検証）
TARGETS = {
    'scp-lab':       'ch内対照で検証済（疑問型 1.13 vs 非該当 0.93）',
    'daily-science': 'ch内対照で検証済（疑問型 1.23 vs 非該当 0.20＝6.2倍）',
    'yokai-watch':   'ch内対照で検証済（疑問型 1.58 vs 非該当 0.75）',
    '2ch-matome':    'ch内対照で検証済（疑問型 1.41 vs 非該当 0.78）',
    'company-facts': '⚠️ 外挿。当chは疑問型/非該当のどちらかが n<3 で ch内対照が取れなかった。'
                     'プール実測（0.708(n=65) vs 0.499(n=118)）と同系統4chの一致のみを根拠に適用。09-24 に再判定。',
}
RSN = ('【2026-09-17 指揮者・実測】疑問型（なぜ/のか/？）を含むタイトルは ch内対照で 4/4ch すべて自ch平均超'
       '（scp-lab 1.13 / daily-science 1.23 / yokai-watch 1.58 / 2ch-matome 1.41、いずれも非該当を上回る）。'
       'プールでも 0.708(n=65) vs 0.499(n=118)。ch内一致が測定できた全chで取れたタイトル指標はこれが初めてで、'
       '「正体/真相」1/4ch・「実は」2/3ch・「理由/わけ」2/3ch はいずれも一致しない。'
       'にもかかわらず require_any_of.words に「のか」が無く、'
       '「SCP-記録に残る「19分の空白」は何だったのか」「JR東日本の平均年収698万円、本当はどこに消えるのか」'
       'のような実測最良パターンが answer-marker 違反として再生成に回されていた'
       '（「本当の」は登録済みだが「本当は」は語形が違うため不一致）。'
       '許容語を増やす＝ゲートを緩める方向なので publish_blocked は増えない。'
       '09-15 に scp-lab が規約未解消で1枠を失っているため、churn を減らす側に倒す。')

changes = {}
for ch, why in TARGETS.items():
    p = os.path.join(BASE, 'data', 'channels', f'{ch}.json')
    shutil.copy2(p, p + '.bak_pdca_20260917_orchb')
    d = json.load(open(p, encoding='utf-8'))
    ra = d['title_rules']['hard_constraints']['require_any_of']
    if 'のか' in ra['words']:
        continue
    before = list(ra['words'])
    ra['words'] = before + ['のか']
    ra['note_20260917_orch'] = RSN + f'  / 当chの根拠: {why}'
    # 効果検証のため、適用前のキュー違反数を記録しておく
    hc = d['title_rules']['hard_constraints']
    q = d['autopilot'].get('theme_queue') or []
    def viol(words):
        return sum(1 for t in q
                   if len(DG.findall(t.get('title', ''))) > hc.get('max_digit_groups', 99)
                   or not any(w in t.get('title', '') for w in words))
    d['title_rules']['_gate_effect_20260917_orch'] = {
        'queue_violations_before': viol(before),
        'queue_violations_after': viol(ra['words']),
        'queue_size': len(q),
        'evaluate_on': '2026-09-24',
        'metric': 'backend.log の「🚫 タイトル規約違反」「⛔ publish_blocked」件数が減るか',
    }
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    changes[ch] = {'words': f"{len(before)} → {len(ra['words'])}（+のか）",
                   'queue_violations': f"{viol(before)} → {viol(ra['words'])} / {len(q)}件",
                   'evidence': why}

print(json.dumps(changes, ensure_ascii=False, indent=2))

# 既存の変更記録へ追記
f = os.path.join(BASE, 'reports', 'orch_config_changes_20260917.json')
rec = json.load(open(f, encoding='utf-8'))
for ch, v in changes.items():
    rec['channels'].setdefault(ch, []).append(
        f"title_rules.require_any_of.words に「のか」を追加（{v['words']} / キュー違反 {v['queue_violations']}）")
rec['phase3b_generated_at'] = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
json.dump(rec, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
