# -*- coding: utf-8 -*-
"""2026-09-09 指揮者 — 実データに基づくコンフィグ反映。

判断軸は optimization.primary_metric = subs_per_1000_views（登録者/1000再生）。
母集団は video_metrics の最新スナップショット（2026-09-08 取得）のうち
公開が 2026-09-05 以前（analytics_policy.evaluation_lag.min_age_days=3）かつ
views>=200 の n=196。

channels_orchestrator/*.json は 09-08 から channels/*.json への symlink なので
書き込み先は channels/*.json 一箇所のみ（二重書き込みは不要）。
"""
import json
import os
import shutil
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHDIR = os.path.join(ROOT, 'data', 'channels')
TODAY = '2026-09-09'
SUFFIX = '.bak_pdca_20260909_orch'

CH6 = ['daily-science', 'scp-lab', '2ch-matome',
       'pokemon-lab', 'yokai-watch', 'company-facts']

# ---- 実測サマリ（本日の根拠。config へも埋める） -----------------------------
EVIDENCE_HIMITSU = ('【2026-09-09 実測】タイトルに「秘密」を含む動画は 登録/千再生 0.120 '
                    '(n=18/16,609再生/登録2) に対し、含まない動画は 0.527 '
                    '(n=178/191,590再生/登録101)＝4.4倍差。'
                    'pokemon-lab 0.122 vs 0.332 / yokai-watch 0.149 vs 0.543 / '
                    'daily-science 0.00 vs 0.497 / 2ch-matome 0.00 vs 0.209 と'
                    '出現する4ch全てで同方向。しかも「秘密」入りは公開 08-30 までで'
                    '古い＝登録を積む時間は長かった側なので、時間バイアスは逆向き。')

EVIDENCE_99 = ('【2026-09-09 実測】「99%が知らない」型の希少性ワードは 登録/千再生 0.194 '
               '(n=11) に対し非該当 0.510 (n=185)＝2.6倍の劣位。')

WORD_RANK = ('【2026-09-09 実測・答え提示語の語別ランキング（登録/千再生）】'
             '実は 0.767(n=18) > 実態 0.681(n=9) > なぜ 0.568(n=72) > '
             '正体 0.510(n=25) > 本当 0.462(n=17) > 理由 0.368(n=19)。'
             '答え提示語あり全体 0.606(n=123) vs なし 0.302(n=73)＝2.0倍で、'
             '6ch中5chが同方向（例外は pokemon-lab だが「秘密」を除くと差は消える）。'
             '語尾に足せない「実は」は repair_with には入れられないので、'
             'LLM 側の第一候補として title_style で指示する。')


def load(ch):
    p = os.path.join(CHDIR, ch + '.json')
    with open(p, encoding='utf-8') as f:
        return p, json.load(f)


def save(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def backup(path):
    b = path + SUFFIX
    if not os.path.exists(b):
        shutil.copy2(path, b)


def add_pattern(hc, pattern, label):
    pats = hc.setdefault('forbid_patterns', [])
    if not any(p.get('pattern') == pattern for p in pats):
        pats.append({'pattern': pattern, 'label': label})
        return True
    return False


def add_banned(hc, word):
    bw = hc.setdefault('banned_words', [])
    if word not in bw:
        bw.append(word)
        return True
    return False


def log(d, changes):
    d.setdefault('pdca_log', []).append({
        'date': TODAY,
        'source': 'orchestrator',
        'changes': changes,
        'evidence': ('video_metrics 最新スナップショット(2026-09-08取得)・'
                     '公開2026-09-05以前・views>=200・n=196。'
                     '判断軸 subs_per_1000_views。'),
    })


report = {}

for ch in CH6:
    path, d = load(ch)
    backup(path)
    changes = []
    hc = d.setdefault('title_rules', {}).setdefault('hard_constraints', {})

    # --- 1) 全ch: 「秘密」を機械ゲートで禁止 --------------------------------
    if add_banned(hc, '秘密'):
        changes.append('title_rules.hard_constraints.banned_words に「秘密」を追加'
                       '（登録/千 0.120 vs 0.527・出現4ch全てで同方向）')

    # --- 2) 全ch: 「99%が知らない」型を禁止 ---------------------------------
    if add_pattern(hc, r'(?:9\s*9|９\s*９)\s*[%％]', '99%が知らない型の希少性ワード'):
        changes.append('title_rules.hard_constraints.forbid_patterns に 99%型を追加'
                       '（登録/千 0.194 vs 0.510）')

    hc.setdefault('rationale_20260909', '')
    hc['rationale_20260909'] = EVIDENCE_HIMITSU + ' / ' + EVIDENCE_99

    # --- 3) 答え提示語の語別ランキングを title_style へ ----------------------
    tp = d.setdefault('theme_priority', {})
    ts = tp.get('title_style', '')
    if '2026-09-09 実測・答え提示語の語別ランキング' not in ts:
        tp['title_style_prev_20260909'] = ts
        tp['title_style'] = (WORD_RANK + '『秘密』『99%が知らない』は機械ゲートで'
                             '弾かれるので使わないこと。 ' + ts)
        changes.append('theme_priority.title_style に答え提示語の語別実測ランキングを反映'
                       '（実は > 実態 > なぜ > 正体 > 本当 > 理由）')

    report[ch] = {'path': path, 'changes': changes, 'd': d}

# --- 4) 2ch-matome 固有 -----------------------------------------------------
ch = '2ch-matome'
d = report[ch]['d']
hc = d['title_rules']['hard_constraints']
if add_pattern(hc, r'^\s*ワイ', 'ワイ始まりの2ch定型スレタイ'):
    report[ch]['changes'].append(
        'forbid_patterns に「^ワイ」を追加（ワイ/質問ある型は n=11・10,781再生で'
        '登録者 0 人。同ch内の非該当は 0.282。再生は取れるが1人も登録に変換しない）')
if add_pattern(hc, r'質問ある', '「質問ある？」型の2ch定型スレタイ'):
    report[ch]['changes'].append('forbid_patterns に「質問ある」を追加（同上・登録0）')

times = d['autopilot']['schedule']['times']
for t in times:
    if t.get('hour') == 7 and t.get('minute') == 0:
        t['hour'], t['minute'] = 9, 0
        report[ch]['changes'].append(
            '投稿枠 07:00 → 09:00（当ch内: 7時 登録/千 0.00(n=2) が最下位、'
            '9時 0.29(n=5) は12時 0.29 と並ぶ最上位）')

# --- 5) scp-lab 固有 --------------------------------------------------------
ch = 'scp-lab'
d = report[ch]['d']
hc = d['title_rules']['hard_constraints']
if add_pattern(hc, r'—\s*.*【', '「— …【ラベル】」の記録票フォーマット'):
    report[ch]['changes'].append(
        'forbid_patterns に「— …【ラベル】」型を追加（当ch内 0.227(n=14) vs 0.501(n=34)。'
        '下位3本すべてがこの型）')

sched = d['autopilot']['schedule']
old = [(t.get('hour'), t.get('minute')) for t in sched['times']]
seen, dedup = set(), []
for t in sched['times']:
    k = (t.get('hour'), t.get('minute'))
    if k not in seen:
        seen.add(k)
        dedup.append(t)
for t in dedup:
    if t.get('hour') == 17:
        t['hour'], t['minute'] = 9, 0
dedup.sort(key=lambda t: (t.get('hour'), t.get('minute')))
sched['times'] = dedup
new = [(t.get('hour'), t.get('minute')) for t in dedup]
sched['_times_comment_20260909'] = (
    f'【2026-09-09 バグ修正】times が {old} と完全重複した6枠になっていた'
    '（同一時刻が2回ずつ）。3枠へ重複解消。あわせて 17:00 は当ch内に有効データが無く'
    '（n<2）、代わりに実測のある 09:00（登録/千 0.69・n=12）へ移した。'
    '当ch内の実測は 19時 1.23(n=9) > 13時 0.83(n=6) > 9時 0.69(n=12)。')
report[ch]['changes'].append(
    f'🚨 autopilot.schedule.times の重複を解消 {old} → {new}'
    '（同一時刻が2回ずつ登録され1日6枠発火する状態だった）')
report[ch]['changes'].append(
    '投稿枠 17:00 → 09:00（17時は当ch内 n<2 でデータ無し、9時は 0.69・n=12）')

# --- 6) pokemon-lab 固有 ----------------------------------------------------
ch = 'pokemon-lab'
d = report[ch]['d']
for t in d['autopilot']['schedule']['times']:
    if t.get('hour') == 19:
        t['hour'], t['minute'] = 15, 0
        report[ch]['changes'].append(
            '投稿枠 19:00 → 15:00（当ch内: 19時は n<2 でデータ無し・隣接の18時は '
            '0.21(n=10) で最下位。15時 0.33(n=3) / 17時 0.31(n=10) が上位）')

# --- 7) daily-science 固有: 禁止語を推奨していた矛盾を解消 -------------------
ch = 'daily-science'
d = report[ch]['d']
tp = d['theme_priority']
vh = tp.get('viral_hooks', '')
if '99%' in vh or '99％' in vh:
    tp['viral_hooks_prev_20260909'] = vh
    tp['viral_hooks'] = (vh.replace('「99%が知らない」系の希少性ワード / ', '')
                           .replace('「99％が知らない」系の希少性ワード / ', ''))
    tp['viral_hooks_note_20260909'] = EVIDENCE_99 + (
        ' viral_hooks が機械ゲートで弾かれる語を推奨していたため削除。')
    report[ch]['changes'].append(
        'theme_priority.viral_hooks から「99%が知らない」系を削除'
        '（推奨と機械ゲートが矛盾していた。実測 0.194 vs 0.510）')

# --- 8) pokemon-lab theme_seeds 補充 ---------------------------------------
POKE_SEEDS = [
    {'title': 'ハピナスの防御が5しかない設計の理由',
     'angle': 'HP255・特防135に対して防御5という極端な配分が種族値設計上どう成立したのか。'
              '上位実績のあるステータス提示型（登録/千1.06）の再現。'},
    {'title': 'ヌメルゴンの特防が全ドラゴン最高になったわけ',
     'angle': '特防150の由来と、雨パでの実戦上の意味。数値を1つだけ出す型（1.05）の再現。'},
    {'title': 'けつばんが初代図鑑にだけ現れた本当の理由',
     'angle': 'マップ外エンカウントテーブルの参照ずれ。固有名詞＋答え提示語型（0.98）の再現。'},
    {'title': 'ドラパルトの素早さ142が生まれた事情',
     'angle': '600族の中で素早さに全振りされた経緯と、対面での先制ライン。'},
    {'title': 'ミミッキュの化けの皮が1回しか持たない設計の裏側',
     'angle': '実戦での耐久換算と、なぜ1回に制限されたのか。'},
    {'title': 'サンダースの素早さが初代で異常だったわけ',
     'angle': '初代の素早さと急所率の連動という仕様。'},
    {'title': 'エースバーンのリベロが1試合1回になった実態',
     'angle': '解禁時の環境データと制限の経緯。'},
    {'title': 'ロトムのフォルム変更が技1つに紐づく理由',
     'angle': 'フォルムと技の対応関係の設計。'},
    {'title': 'カビゴンの重さ460kgが技に効く仕組み',
     'angle': 'けたぐり／くさむすびの威力計算と重さの関係。'},
    {'title': 'ガブリアスが600族で唯一4倍弱点を持つ事情',
     'angle': 'ドラゴン・じめん複合の代償と、それでも採用され続けた理由。'},
]
d = report['pokemon-lab']['d']
seeds = d.setdefault('theme_seeds', [])
have = {s.get('title') for s in seeds}
added = [s for s in POKE_SEEDS if s['title'] not in have]
seeds.extend(added)
if added:
    report['pokemon-lab']['changes'].append(
        f'theme_seeds を {len(seeds)-len(added)} → {len(seeds)} 本へ補充（+{len(added)}）。'
        'theme_queue が 12本と6ch中最少だったため。'
        'theme_queue は theme_seeds から30分ごとに再生成される揮発キャッシュなので'
        'seeds 側に入れている。題材は当ch上位実績（固有名詞＋1つの数値を提示する型）に寄せ、'
        '0転換だった「どっちが勝つ？」対戦比較型は増やしていない。')

# ---- 書き出し ---------------------------------------------------------------
for ch in CH6:
    r = report[ch]
    if r['changes']:
        log(r['d'], r['changes'])
        save(r['path'], r['d'])

print('=' * 72)
for ch in CH6:
    print(f'### {ch}')
    for c in report[ch]['changes']:
        print('  -', c)
    if not report[ch]['changes']:
        print('  （変更なし）')
print('=' * 72)
