#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-11 指揮者 PDCA 反映.

実測根拠（analytics.db / 公開 08-10〜09-04 の成熟コホート, 主指標 = 登録者/千再生）:
  A. 絵文字: ch内対照で5/6chが悪化。scp-lab 0.32(n=12) vs 0.98(n=27)、
     yokai-watch 0.19 vs 0.46、2ch-matome 0.00 vs 0.27。
     max_emoji=0 は backend が読まないキーだったため 09-04〜09-08 も毎日1〜2本流出。
     → hard_constraints.forbid_patterns / banned_words へ移して実効化。
  B. 「なぜ」疑問形: scp-lab 1.45(n=11) vs 0.45(n=28)、yokai-watch 0.66 vs 0.20、
     daily-science 0.56 vs 0.27、2ch-matome 0.33 vs 0.18。→ 4chで最優先形に格上げ。
     ただし pokemon-lab のみ 0.00(n=9) vs 0.37(n=19) で逆効果。
  C. pokemon-lab の二人称(君/あなた): 0.45(n=10) vs 0.15(n=18)。当chだけ逆パターン。
  D. 維持率の崖: 全252本平均で 15%地点102% → 20%地点84% → 30%地点63%。
     尺は _experiments.length_20260905 により 09-12 まで変更禁止 → 構成のみ手当て。
  E. pokemon-lab の theme_queue が 0 本（枯渇）。当chだけ 08-25以降 0.26→0.20 と悪化。
"""
import json, os, shutil, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = "20260911_orch"
TODAY = "2026-09-11"
CHS = ["daily-science", "scp-lab", "2ch-matome", "pokemon-lab", "yokai-watch", "company-facts"]

EMOJI_PATTERN = "[\\U0001F300-\\U0001FAFF\\u2600-\\u27BF\\u2B00-\\u2BFF\\uFE0F]"
LEAKED_EMOJI = ["💸", "📈", "📉", "💰", "🔥", "👀", "😨", "🕵️", "🧪", "💧", "🎮", "🔍", "❓", "🎬", "✅", "⚡", "🌙", "🧠"]

WHY_FIRST = """──【{today} 実測。以下の既存方針を打ち消さず、その上に最優先で重ねる】──
【最優先】タイトルは「なぜ〇〇なのか」の疑問形を第一候補にする。
根拠: 公開 08-10〜09-04 のch内対照で、登録/千再生は
  scp-lab 1.45(n=11) vs 非「なぜ」0.45(n=28)
  yokai-watch 0.66(n=9) vs 0.20(n=19)
  daily-science 0.56(n=28) vs 0.27(n=4)
  2ch-matome 0.33(n=9) vs 0.18(n=29)
と、4ch全てで「なぜ」型が上回った。答え提示語（正体・理由・真相…）は
hard_constraints で既に必須だが、**単独では効果が確認できなかった**
（daily-science 0.44 vs 0.60 / scp-lab 0.68 vs 0.78 / yokai-watch 0.30 vs 0.52）。
したがって「なぜ〇〇なのか」＋答え提示語、の二段構えで書くこと。
【禁止】タイトルに絵文字を一切入れない。ch内対照で5/6chが悪化しており、
scp-lab は絵文字ありで登録効率が3分の1になる。
──────────────────────────────────────"""

POKE_STYLE = """──【{today} 実測。当chは他chと逆パターン。以下を最優先で重ねる】──
【最優先】タイトルに二人称（君／あなた）を必ず入れる。
根拠: 公開 08-10〜09-04 のch内対照で 登録/千再生 0.45(n=10) vs 二人称なし 0.15(n=18)。
当chの上位4本は全て二人称入り（「君は3秒で速さの壁を越えられる？」1.90 /
「君が知らないシェイミ2形態の正体」1.16 / 「特防が高いのはどっち」1.05 /
「あなたは本当の役割に気づいた？」1.02）。
【回避】「なぜ」開始の疑問形は当chでのみ逆効果。0.00(n=9) vs 非「なぜ」0.37(n=19)。
他5chでは「なぜ」が最優先だが、当chは二人称＋対比（AとB、どっちが〜）を主軸にする。
【禁止】タイトルに絵文字を一切入れない。
【注記】当chは 08-25 を境に 0.26→0.20 と6ch中唯一悪化し、
browse/suggested CTR も 0.69%（6ch最低）。サムネ改善を最優先枠として扱う。
──────────────────────────────────────"""

RETENTION_RULE = (
    "【{today} 実測・中盤の崖対策】全252本の平均維持率は 15%地点102% → 20%地点84% "
    "→ 30%地点63% と、尺の 15〜30% で一気に落ちる。6行構成なら **2行目の終わりから3行目** "
    "がこの区間にあたる。3行目には必ず『前提がひっくり返る一言』か『具体的な数字』を置き、"
    "説明を2行続けてはならない。尺そのものは _experiments.length_20260905 により "
    "09-12 まで変更しない。"
).format(today=TODAY)


def backup(path):
    b = f"{path}.bak_pdca_{STAMP}"
    if not os.path.exists(b):
        shutil.copy2(path, b)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, d):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def apply_common(d, ch):
    tr = d.setdefault("title_rules", {})
    hc = tr.setdefault("hard_constraints", {})

    # A. 絵文字を hard_constraints へ（検知は forbid_patterns、機械修復は banned_words）
    fp = hc.setdefault("forbid_patterns", [])
    if not any(isinstance(s, dict) and s.get("label") == "絵文字" for s in fp):
        fp.append({"pattern": EMOJI_PATTERN, "label": "絵文字"})
    bw = hc.setdefault("banned_words", [])
    for e in LEAKED_EMOJI:
        if e not in bw:
            bw.append(e)

    tr["rationale_20260911"] = (
        "【2026-09-11 実測・絵文字を hard_constraints へ移設】title_rules.max_emoji=0 は "
        "backend（title_constraints.py）が読まないキーで、実際 09-04〜09-08 も毎日1〜2本 "
        "絵文字入りタイトルが公開されていた。ch内対照の登録/千再生は "
        "scp-lab 絵文字あり 0.32(n=12) / なし 0.98(n=27)、yokai-watch 0.19 / 0.46、"
        "2ch-matome 0.00 / 0.27、company-facts 0.68 / 0.78 と 5/6ch で悪化。"
        "forbid_patterns で検知し、banned_words で機械修復できるようにした。"
    )
    tr["updated_at"] = TODAY

    # D. 中盤の崖対策（構成のみ。尺は実験ロック順守）
    sf = d.setdefault("short_format", {})
    er = sf.setdefault("extra_rules", [])
    if not any("中盤の崖対策" in str(r) for r in er):
        er.append(RETENTION_RULE)

    # PDCA ログ
    log = d.setdefault("pdca_log", [])
    log.append({
        "date": TODAY,
        "source": "orchestrator",
        "changes": [
            "絵文字禁止を title_rules.hard_constraints へ移設（forbid_patterns + banned_words）",
            "short_format.extra_rules に 15〜30% 地点の維持率の崖対策を追加",
        ],
        "evidence": "analytics.db 公開08-10〜09-04 成熟コホート / retention_curve n=252",
    })
    return d


def apply_why(d):
    tp = d.setdefault("theme_priority", {})
    prev = tp.get("title_style")
    if prev and not str(prev).startswith("──【2026-09-11"):
        tp["title_style_prev_20260911"] = prev
        tp["title_style"] = WHY_FIRST.format(today=TODAY) + "\n" + str(prev)
    tp["viral_hooks_note_20260911"] = (
        "【2026-09-11 実測】「なぜ〇〇なのか」疑問形が当chの最大レバー。"
        "答え提示語だけでは登録効率は上がらず、疑問形との併用で効く。"
    )
    return d


def apply_poke(d):
    tp = d.setdefault("theme_priority", {})
    prev = tp.get("title_style")
    if prev and not str(prev).startswith("──【2026-09-11"):
        tp["title_style_prev_20260911"] = prev
        tp["title_style"] = POKE_STYLE.format(today=TODAY) + "\n" + str(prev)
    tp["viral_hooks_note_20260911"] = (
        "【2026-09-11 実測】二人称（君／あなた）0.45(n=10) vs なし 0.15(n=18)。"
        "「なぜ」開始は当chのみ 0.00(n=9) で逆効果。二人称＋対比を主軸にする。"
    )
    return d


def main():
    touched = []
    for ch in CHS:
        for base in ("channels_orchestrator", "channels"):
            p = os.path.join(ROOT, "data", base, f"{ch}.json")
            if not os.path.exists(p):
                print(f"  skip (not found): {p}")
                continue
            backup(p)
            d = load(p)
            d = apply_common(d, ch)
            if ch == "pokemon-lab":
                d = apply_poke(d)
            elif ch in ("scp-lab", "yokai-watch", "daily-science", "2ch-matome"):
                d = apply_why(d)
            save(p, d)
            touched.append(p)
            print(f"  updated {base}/{ch}.json")
    print(f"\n{len(touched)} ファイル更新")


if __name__ == "__main__":
    main()
