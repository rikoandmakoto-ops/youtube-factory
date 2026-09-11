#!/usr/bin/env python3
"""2026-09-11 指揮者タスク: 実測に基づく config 反映。

根拠データ: data/analytics/analytics.db の 09-08 スナップショット
（fake-paper / akashic-librarian は 09-06。09-09 以降は analytics 停止で新規行ゼロ）。

適用する変更（すべて本日の実測 or 既存テストの RED を根拠に持つ）:

  1. theme_blacklist の退行を戻す
     - scp-lab: 09-11 朝の自動 run が 13語 → 6語 に削り、同じ run が追記した
       `_theme_blacklist_note_20260910`（「SCP-173 が上位40本中12本=30%」）と
       真逆になっていた。削られた8語を復元する。
     - daily-science: 同 run が「あくび」「自分の声」を削り、リポジトリ自身の
       回帰テスト `test_fixes_20260909.py::TestDailyScienceBlacklist::
       test_no_regression_in_duplicate_prevention` が RED（過去の重複タイトル8件が
       素通りする状態）。2語を復元してテストを GREEN に戻す。

  2. title_rules.hard_constraints.min_effective_chars = 20
     09-08 スナップショット n=330（views>0・全12ch）を実効文字数で刻むと
     登録/千再生 は 0-14字 0.242 / 15-19字 0.279 / 20-24字 0.400 /
     25-29字 0.637 / 30字以上 0.355。20字未満が全体の34%（112/330本）を占める。
     自然文の `min_effective_chars_target` は backend が読まないため、
     本日 title_constraints.py に検査を実装した上で hard_constraints へ入れる。
     ※ 切り抜き3ch は除外。タイトルが発言の引用なので、文字数を足させると
        誤引用を作りうる。別施策として扱う（レポート §改善提案）。

  3. akashic-librarian に hard_constraints を新規付与
     登録/千再生 0.570 で全11ch中3位なのに、ゲートが1つも設定されておらず
     既知の負け型（絵文字・「秘密」・短すぎるタイトル）が素通りしていた。

  4. 投稿枠: 18時JST枠を 17時JST へ寄せる
     全ch集計で 17時JST 0.590(n=51) vs 18時JST 0.219(n=50) ＝ 2.7倍。
     どちらも n≈50 で最大の2枠。該当は akashic-librarian 18:45 と clip-animal 18:00。

  5. fake-paper: 「架空論文ファイル」シリーズ接頭辞を禁止
     17本 / 7,047再生 / 登録0 で全11ch唯一の転換ゼロ。上位10本のうち5本が
     この接頭辞に9文字を使っており、実効長が本文に残らない。
     連番プレフィックスは 08-31 に全chで 0.84倍（負）と実測済み。

  6. 疑問形ルールと「末尾の疑問符」禁止の衝突を注記で解消
     yokai-watch は hard_constraints で末尾「？」を禁じつつ、09-11 朝の run が
     「なぜ〇〇なのか」を最優先にした。体言止め（末尾に？を付けない）で書く旨を明記。
"""

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH_DIR = os.path.join(ROOT, "data", "channels")
STAMP = "20260911_orch2"

# 09-11 朝の run が scp-lab から削った8語（同 run の note が「止めろ」と書いている語）
SCP_RESTORE = ["SCP-173", "視線を外", "目を離", "見るのをやめ",
               "最初の異常存在", "17名", "17年間", "担当者17"]
# daily-science から削られ、既存テストが RED になった2語
DS_RESTORE = ["あくび", "自分の声"]

# min_effective_chars を入れるチャンネル（切り抜き3ch と停止中の socio-rx は除く）
MIN_EFF_CHANNELS = ["scp-lab", "daily-science", "yokai-watch", "pokemon-lab",
                    "company-facts", "2ch-matome", "fake-paper", "akashic-librarian"]
MIN_EFF = 20

RATIONALE = (
    "【2026-09-11 実測】09-08 スナップショット n=330（views>0・全12ch）を"
    "実効文字数（ハッシュタグと【】を除いた本文）で刻むと、登録/千再生は "
    "0-14字 0.242 / 15-19字 0.279 / 20-24字 0.400 / 25-29字 0.637 / 30字以上 0.355。"
    "短すぎる側が最も弱く、25〜29字が頂点の逆U字。20字未満は全330本中112本（34%）を"
    "占めていた。title_rules.min_effective_chars_target に自然文で書かれていた"
    "「実質20字以上」は backend が読まないため1本も効いていなかったので、"
    "本日 title_constraints.py に min_effective_chars を実装して hard_constraints へ移した。"
    "下限は20字、狙いは25〜29字。機械修復はしない（水増しになるため検査と再生成のみ）。"
)

QUESTION_FORM_NOTE = (
    "【2026-09-11 補足・疑問形の書き方】「なぜ〇〇なのか」を最優先にするが、"
    "**末尾に「？」を付けない体言止めで書く**こと（例: ×「なぜ狐は人を化かすのか？」→ "
    "〇「なぜ狐は人を化かす妖怪にされたのか 江戸の記録に残る事情」）。"
    "hard_constraints.forbid_patterns で末尾の疑問符を禁止しているチャンネルがあり、"
    "疑問符付きで書くとゲートに落ちて再生成に回る。疑問形の効果は語順（なぜ〜のか）に"
    "あり、疑問符の有無ではない。"
)


def load(ch):
    with open(os.path.join(CH_DIR, f"{ch}.json"), encoding="utf-8") as f:
        return json.load(f)


def save(ch, d):
    p = os.path.join(CH_DIR, f"{ch}.json")
    shutil.copy2(p, f"{p}.bak_pdca_{STAMP}")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


changes = []


def log(ch, what):
    changes.append((ch, what))
    print(f"  ✅ {ch:20} {what}")


# ---------------------------------------------------------------------
# 1. theme_blacklist の復元
# ---------------------------------------------------------------------
print("[1] theme_blacklist の退行を戻す")
d = load("scp-lab")
bl = d.get("theme_blacklist", [])
added = [w for w in SCP_RESTORE if w not in bl]
if added:
    d["theme_blacklist"] = bl + added
    d["_theme_blacklist_note_20260911"] = (
        "09-11 朝の自動 run が theme_blacklist を 13語→6語 に削り、"
        f"同じ run が追記した _theme_blacklist_note_20260910（SCP-173 が再生上位40本中12本=30%、"
        "『視線を外/目を離』計7本、『17名/17年間/担当者17』計8本）と真逆の状態になっていた。"
        f"削られた8語 {added} を復元。note と blacklist が矛盾したら blacklist 側を note に合わせる。"
    )
    save("scp-lab", d)
    log("scp-lab", f"theme_blacklist {len(bl)}→{len(d['theme_blacklist'])}語（{added} を復元）")

d = load("daily-science")
bl = d.get("theme_blacklist", [])
added = [w for w in DS_RESTORE if w not in bl]
if added:
    d["theme_blacklist"] = bl + added
    d["_theme_blacklist_note_20260911"] = (
        f"09-11 朝の自動 run が {DS_RESTORE} を削った結果、リポジトリ自身の回帰テスト "
        "test_fixes_20260909.py::TestDailyScienceBlacklist::test_no_regression_in_duplicate_prevention "
        "が RED になっていた（旧リストが止めていた過去タイトル8件が素通り）。"
        "同 run の theme_blacklist_note 自身が「『自分の声』が上位40本中10本」と書いており、"
        "削除は note とも矛盾する。復元してテストを GREEN に戻した。"
    )
    save("daily-science", d)
    log("daily-science", f"theme_blacklist {len(bl)}→{len(d['theme_blacklist'])}語（{added} を復元）")

# ---------------------------------------------------------------------
# 2. min_effective_chars
# ---------------------------------------------------------------------
print("\n[2] hard_constraints.min_effective_chars = 20")
for ch in MIN_EFF_CHANNELS:
    d = load(ch)
    tr = d.setdefault("title_rules", {})
    hc = tr.setdefault("hard_constraints", {})
    if hc.get("min_effective_chars") == MIN_EFF:
        continue
    hc["min_effective_chars"] = MIN_EFF
    hc["rationale_min_effective_chars_20260911"] = RATIONALE
    tr["min_effective_chars_target"] = 25
    tr["min_effective_chars_migrated_to"] = "hard_constraints.min_effective_chars"
    tr["updated_at"] = "2026-09-11"
    d["title_rules"] = tr
    save(ch, d)
    log(ch, "min_effective_chars=20 / target=25 を hard_constraints へ")

# ---------------------------------------------------------------------
# 3. akashic-librarian に hard_constraints を新規付与
# ---------------------------------------------------------------------
print("\n[3] akashic-librarian に hard_constraints を新規付与")
d = load("akashic-librarian")
hc = d.setdefault("title_rules", {}).setdefault("hard_constraints", {})
before = sorted(hc.keys())
hc.setdefault("max_chars", 36)
hc.setdefault("banned_words", ["秘密"])
hc.setdefault("forbid_patterns", [
    {"pattern": r"[\U0001F300-\U0001FAFF☀-➿️]", "label": "絵文字"},
    {"pattern": r"(?:9\s*9|９\s*９)\s*[%％]", "label": "99%が知らない型の希少性ワード"},
])
hc.setdefault("require_any_of", {
    "label": "答え提示語",
    "words": ["理由", "正体", "本当の", "実は", "わけ", "なぜ", "真相", "裏側", "実態"],
    "repair_with": ["正体", "理由"],
})
d["title_rules"]["enforced_by_backend"] = True
d["title_rules"]["rationale_20260911"] = (
    "【2026-09-11】当chは登録/千再生 0.570（09-06 スナップショット・17本/5,259再生/登録3）で"
    "全11ch中3位なのに、hard_constraints が1つも設定されておらず機械ゲートが完全に無効だった。"
    "上位2本は「なぜ600年も読めない？存在しない植物だけが描かれた手稿」(1.71) と"
    "「三十八人が見ていて、誰も動かなかった夜」(0.95) で、いずれも疑問形または具体数字＋28字前後。"
    "既に他6chで実測済みの負け型（絵文字・「秘密」・99%型・答え提示語なし・短すぎる本文）を"
    "同じ形で塞ぐ。max_chars は当chの平均実効長26.5字に合わせて36。"
)
save("akashic-librarian", d)
log("akashic-librarian", f"hard_constraints 新規付与 {before} → {sorted(hc.keys())}")

# ---------------------------------------------------------------------
# 4. 18時JST枠 → 17時JST
# ---------------------------------------------------------------------
print("\n[4] 18時JST枠を17時JSTへ")
SLOT_NOTE = (
    "【2026-09-11 実測・投稿枠】09-08 スナップショット n=330 を投稿時刻(JST)別に集計すると "
    "17時 0.590(n=51) / 19時 0.470(n=53) / 9時 0.219(n=50→UTC9時=18時JST) で、"
    "**18時JST枠が最大サンプルの中で最下位**（17時の1/2.7）。18時台の枠を17時台へ寄せる。"
    "ch別では scp-lab 19時 1.28(n=14) > 13時 0.70(n=7) > 9時 0.59(n=17)、"
    "yokai-watch 12時 1.04(n=10) > 19時 0.24(n=23)、company-facts 19時 0.93(n=5) ≒ 17時 0.86(n=12)。"
)
for ch in ["akashic-librarian", "clip-animal"]:
    d = load(ch)
    sch = d.get("autopilot", {}).get("schedule", {})
    times = sch.get("times") or []
    moved = []
    for t in times:
        if t.get("hour") == 18:
            moved.append(f"{t['hour']}:{t.get('minute', 0):02d}")
            t["hour"] = 17
    if moved:
        sch[f"_times_comment_{STAMP}"] = f"{moved} を17時台へ移動。" + SLOT_NOTE
        save(ch, d)
        log(ch, f"投稿枠 {moved} → 17時台")

# 最良枠の記録（変更はせず、次回の判断材料として残す）
for ch, note in [
    ("scp-lab", "当chの最良枠は19時JST（登録/千 1.28・n=14）。9時枠は0.59(n=17)で最弱。"
                "枠の入れ替えは新規データが入ってから行う（同一データで二重に意思決定しない）。"),
    ("yokai-watch", "当chの最良枠は12時JST（1.04・n=10）。19時JSTは0.24(n=23)で最弱だが、"
                    "現行 times に19時枠は既に無い（12:00/9:30/17:00）ので変更不要。"),
]:
    d = load(ch)
    d.setdefault("autopilot", {}).setdefault("schedule", {})[f"_slot_finding_{STAMP}"] = note + " " + SLOT_NOTE
    save(ch, d)
    log(ch, "最良枠の実測を schedule に記録（枠は変更せず）")

# ---------------------------------------------------------------------
# 5. fake-paper: シリーズ接頭辞の禁止
# ---------------------------------------------------------------------
print("\n[5] fake-paper のシリーズ接頭辞を禁止")
d = load("fake-paper")
hc = d.setdefault("title_rules", {}).setdefault("hard_constraints", {})
pats = hc.setdefault("forbid_patterns", [])
if not any(isinstance(p, dict) and "架空論文ファイル" in str(p.get("pattern")) for p in pats):
    pats.append({"pattern": r"架空論文ファイル", "label": "シリーズ接頭辞『架空論文ファイル』"})
    pats.append({"pattern": r"[\U0001F300-\U0001FAFF☀-➿️]", "label": "絵文字"})
    hc["banned_words"] = sorted(set((hc.get("banned_words") or []) + ["秘密"]))
    d["title_rules"]["enforced_by_backend"] = True
    d["title_rules"]["rationale_20260911"] = (
        "【2026-09-11 実測】当chは 17本 / 7,047再生 / 登録0 で、全11ch中唯一の登録転換ゼロ。"
        "再生上位10本のうち5本が「架空論文ファイル」「架空論文ファイル：」で始まり、"
        "本文に使える実効文字が9文字分削られていた（「架空論文ファイル  — 1,248人が選んだ新形態」"
        "のように本文がほぼ残っていない例もある）。連番・シリーズ接頭辞は 08-31 に全chで"
        "0.84倍（負）と実測済み。接頭辞を禁止し、min_effective_chars=20 と併せて"
        "本文へ情報量を戻す。theme_priority.title_style 側の『シリーズ接頭辞が自動で付く』"
        "という前提も同時に撤回する。"
    )
    ts = d.get("theme_priority", {}).get("title_style", "")
    d["theme_priority"]["title_style_prev_20260911"] = ts
    d["theme_priority"]["title_style"] = (
        "──【2026-09-11 実測。以下を最優先で重ねる】──\n"
        "【禁止】「架空論文ファイル」で始めない。シリーズ接頭辞は本文の実効文字を9文字奪い、"
        "当chは登録転換0（17本/7,047再生）。接頭辞ではなく本文で論文の結論を言い切る。\n"
        "【最優先】本文だけで実質20字以上、狙いは25〜29字（全ch実測で登録/千 0.637 の最頂点）。"
        "「宇宙で選ぶあのメニュー」(11字)「最後尾だけ9%短い」(9字) のような短文は最弱帯。\n"
        "結論を断定で1行、必要なら『 — 』の後に手法や数字（人数・週数）を添える。\n"
        "例: 〇「満席の映画館では観客の瞬きが同期する — 1,248人を28日追跡した結果」\n"
        "　　×「架空論文ファイル  — 1,248人が選んだ新形態」\n"
        "煽り語（衝撃・ヤバい）は使わない。オチ（嘘であること）はタイトルに書かない。\n"
        "──────────────────────────────────────\n" + str(ts)
    )
    save("fake-paper", d)
    log("fake-paper", "「架空論文ファイル」接頭辞＋絵文字を禁止 / title_style を書き換え")

# ---------------------------------------------------------------------
# 6. 疑問形と末尾疑問符の衝突を注記
# ---------------------------------------------------------------------
print("\n[6] 疑問形の書き方を注記（末尾「？」を付けない）")
for ch in ["scp-lab", "daily-science", "yokai-watch", "2ch-matome"]:
    d = load(ch)
    tp = d.setdefault("theme_priority", {})
    if tp.get(f"question_form_note_{STAMP}"):
        continue
    tp[f"question_form_note_{STAMP}"] = QUESTION_FORM_NOTE
    save(ch, d)
    log(ch, "疑問形は体言止め（末尾？なし）で書く旨を注記")

# ---------------------------------------------------------------------
print(f"\n=== 合計 {len(changes)} 件の変更 ===")
for ch, what in changes:
    print(f"  {ch:20} {what}")

# 全ファイルが読み直せることを確認
print("\n=== JSON 整合性チェック ===")
bad = 0
for fn in sorted(os.listdir(CH_DIR)):
    if not fn.endswith(".json") or ".bak" in fn:
        continue
    try:
        json.load(open(os.path.join(CH_DIR, fn), encoding="utf-8"))
    except Exception as e:
        print(f"  ❌ {fn}: {e}")
        bad += 1
print(f"  {'✅ 全ファイル OK' if not bad else f'❌ {bad} 件不正'}")
sys.exit(1 if bad else 0)
