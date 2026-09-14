#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026-09-14 指揮者 Phase 3: コンフィグ更新

根拠（すべて analytics.db の実測。1動画1行に畳んだ最新スナップショット）:

 A. 投稿枠 × 登録/千再生（公開 2026-08-15 以降・views>0・n>=3 の枠のみ）
    daily-science 17時 1.236(n=14) / 12時 0.180(n=6) / 7時 0.313(n=3) / 18時 0.228(n=6)
    scp-lab       17時 1.321(n=4)  / 19時 1.194(n=17) / 13時 0.569(n=9) / 9時 0.520(n=8)
    company-facts 17時 0.824(n=15) / 14時 0.379(n=7) / 19時 0.301(n=4) / 8時 0.235(n=4) / 13時 0.000(n=4)
    pokemon-lab   17時 0.369(n=12) / 15時 0.296(n=4) / 12時 0.269(n=4) / 18時 0.000(n=4)
    yokai-watch   16時 1.650(n=3)  / 12時 1.215(n=11) / 18時 0.574(n=3) / 17時 0.569(n=4) / 19時 0.502(n=10)
    2ch-matome    7時 0.339(n=4)   / 17時 0.279(n=3) / 12時 0.204(n=10) / 18時 0.161(n=13)
                  / 21時 0.000(n=7, 3,430再生で登録0) / 19時 0.000(n=3) / 9時 0.000(n=3)

 B. タイトル型 × 登録/千再生（公開 2026-08-01 以降・views>=200・ch内対照）
    型定義: A=疑問フレーム+数字 / B=疑問フレームのみ / C=数字のみ / D=共感・あるある
    2ch-matome     A 0.36(n=16) >> C 0.07(n=16) / D 0.09(n=10)      → A型へ寄せる
    scp-lab        A 1.00(n=25) >  C 0.49(n=26)                      → A型へ寄せる
    company-facts  C 0.66(n=31) >= A 0.55(n=4)                       → C型維持
    pokemon-lab    C 0.53(n=9)  >  B 0.35(n=6) > A 0.17(n=16)        → C型へ寄せる（疑問フレームは使わない）
    yokai-watch    B 1.37(n=9)  >  D 0.53(n=8) > C 0.39(n=8) > A 0.00(n=5) → 数字をタイトルから外す
    daily-science  A 0.59(n=30) >  C 0.00(n=3)                       → A型維持

 ※ 投稿枠は autopilot の burst guard（既定90分）を満たすよう最小90分間隔で配置した。
 ※ autopilot.enabled は一切変更していない（2ch-matome / pokemon-lab は false のまま）。理由は
    reports/orch_config_changes_20260914.json の hold_reason を参照。
"""
import json, os, shutil, uuid, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = [os.path.join(ROOT, "data", "channels_orchestrator"),
        os.path.join(ROOT, "data", "channels")]
STAMP = "20260914_orch"
TODAY = "2026-09-14"

# ---------------------------------------------------------------- 投稿枠
SCHEDULES = {
    # ch: (新 times, 根拠)
    "daily-science": ([(7, 30), (15, 0), (17, 0)],
                      "12:30枠は登録/千 0.180(n=6)、17:00枠は 1.236(n=14) で 6.9 倍。"
                      "12:30 を夕方ピーク寄りの 15:00 へ前倒し（17:00 と 120 分間隔で burst guard を満たす）。"),
    "scp-lab":       ([(13, 0), (17, 0), (19, 0)],
                      "9:00枠は登録/千 0.520(n=8) で当ch最下位。実測最良の 17時(1.321) へ移設。"
                      "19:00(1.194,n=17) と 13:00(0.569,n=9) は維持。間隔 240/120 分。"),
    "company-facts": ([(12, 30), (15, 0), (17, 0), (19, 0)],
                      "8:15枠は登録/千 0.235(n=4)。17時(0.824,n=15) を軸に夕方へ寄せ、8:15 を 15:00 へ移設。"
                      "間隔 150/120/120 分。"),
    "pokemon-lab":   ([(12, 30), (15, 0), (17, 0)],
                      "8:30枠は実測サンプルが n<3 で評価不能。測定済みで最良の 17時(0.369,n=12)・"
                      "15時(0.296,n=4)・12時(0.269,n=4) の3枠に集約。間隔 150/120 分。"),
    "yokai-watch":   ([(12, 0), (16, 0), (19, 0)],
                      "9:30枠は n<3 で評価不能。測定済み上位の 12時(1.215,n=11)・16時(1.650,n=3)・"
                      "19時(0.502,n=10) の3枠へ再配置。17時(0.569,n=4) は隣接する 16時へ統合。間隔 240/180 分。"),
    "2ch-matome":    ([(7, 30), (12, 15), (17, 30)],
                      "21:00枠は n=7・3,430再生で登録0人、9:00枠も n=3 で登録0人。"
                      "実測で唯一プラスの 7時(0.339,n=4)・17時(0.279,n=3) へ振り替え、12:15(0.204,n=10) は維持。"
                      "間隔 285/315 分。"),
}

# ---------------------------------------------------------------- 型ルール
TITLE_TYPE_RULE = {
    "2ch-matome": {
        "target_type": "A（疑問フレーム＋具体数字）",
        "rule": "タイトルは必ず『なぜ／本当の理由／正体／実は〜のか』の疑問フレームで終わらせ、"
                "本文で扱う具体的な数（品数・人数・値段・年数）を1つだけ入れる。"
                "下ネタ・エロ面白のジャンルは維持する（変えるのは型であってジャンルではない）。"
                "『〜あげてけ』『〜選手権』『質問ある？』等の大喜利・参加型の言い切りタイトルは登録に変換しないため先頭に置かない。",
        "evidence": "A型 0.36(n=16) に対し C型 0.07(n=16)・D型 0.09(n=10)。A型は他型の約4〜5倍。"
                    "実測トップは『実はマックに神メニュー3品が決まらない本当の理由とは？』(2.19)。"
                    "逆に再生上位5本（1,236〜1,815再生・維持率41.9〜81.4%）はすべて共感あるある型で登録0人。",
    },
    "scp-lab": {
        "target_type": "A（SCP番号・具体数字＋消失／途絶の未解決な問い）",
        "rule": "SCP番号または具体的な数字（時間・人数・回数）を1つ入れ、"
                "『なぜ〜のか』の未解決な問いで締める。数字のみの言い切りタイトルは先頭に置かない。",
        "evidence": "A型 1.00(n=25) に対し C型 0.49(n=26)。A型は2.0倍。",
    },
    "company-facts": {
        "target_type": "C（企業名＋具体金額・具体数字）",
        "rule": "企業名と具体的な金額・比率・年数を提示する言い切り型を優先する。疑問フレームは必須にしない。",
        "evidence": "C型 0.66(n=31) ≧ A型 0.55(n=4)。現行の型が最良のため維持。",
    },
    "pokemon-lab": {
        "target_type": "C（種族値など具体数値の提示）",
        "rule": "種族値・世代・数値を提示する言い切り型を最優先する。"
                "『なぜ〜？』の疑問フレームは当chでは登録に変換しないため使わない。",
        "evidence": "C型 0.53(n=9) > B型 0.35(n=6) > A型 0.17(n=16)。"
                    "疑問フレームを数字と併用した A型は C型の 1/3。09-13 の『数値提示型 0.429 vs 対決型 0.191』とも整合。",
    },
    "yokai-watch": {
        "target_type": "B（疑問フレームのみ・数字を入れない）",
        "rule": "『なぜ〜のか』『〜の正体』の疑問フレームのみで構成し、タイトルに数字を入れない。"
                "通し番号・体系番号も入れない。",
        "evidence": "B型 1.37(n=9) > D型 0.53(n=8) > C型 0.39(n=8) > A型 0.00(n=5)。"
                    "当chは数字を入れた瞬間に登録がゼロになる（A型 n=5 で登録0人）。",
    },
    "daily-science": {
        "target_type": "A（毎日起きる身体感覚＋具体的な倍率・秒数を1つ）",
        "rule": "身体で毎日起きる現象を疑問フレームで立て、倍率・秒数・圧力などの数字をちょうど1つ入れる。",
        "evidence": "A型 0.59(n=30) > C型 0.00(n=3)。実測トップは『圧力1.4倍』(3.48)・『3倍』(2.43)。現行の型が最良のため維持。",
    },
}

# ---------------------------------------------------------------- 補充テーマ
NEW_THEMES = {
    "daily-science": [
        {"title": "なぜ階段を下りる時だけ膝に3倍の力がかかるのか",
         "angle": "身体感覚＋倍率。下りの衝撃荷重を3行目で言い切る"},
        {"title": "なぜ熱い風呂は最初の10秒だけ痛いのか",
         "angle": "身体感覚＋秒数。温度受容体の順応を3行目で渡す"},
        {"title": "なぜ朝起きた直後だけ身長が2cm高いのか",
         "angle": "身体感覚＋具体長さ。椎間板の水分量で回収"},
        {"title": "なぜ片足立ちは目を閉じた瞬間に5秒で崩れるのか",
         "angle": "身体感覚＋秒数。視覚に依存した平衡制御を3行目で渡す"},
    ],
    "company-facts": [
        {"title": "ニトリの粗利率55%を支える自社物流の実態",
         "angle": "企業名＋具体比率の言い切り。製造物流小売一貫の取り分で締める"},
        {"title": "ドン・キホーテが1店舗で4万点を置く理由と在庫の数字",
         "angle": "企業名＋具体点数。圧縮陳列の回転率で締める"},
        {"title": "サイゼリヤが価格を据え置いた10年と原価率の実数",
         "angle": "企業名＋年数＋原価率。自社農場と為替の取り分で締める"},
        {"title": "無印良品の店舗数1,200と売上のうち衣料が占める割合",
         "angle": "企業名＋店舗数＋構成比。セグメント別の実数で締める"},
        {"title": "ユニクロのヒートテック10億枚が示す1枚あたりの取り分",
         "angle": "企業名＋累計枚数。素材メーカーとの分配で締める"},
    ],
    "2ch-matome": [
        {"title": "彼女の部屋で見つけた物3つ、なぜ黙っとくのが正解なのか",
         "angle": "軽い下ネタ。ブツは伏せたまま『黙る理由』を3行目で言い切る"},
        {"title": "なぜ温泉の脱衣所で全員が同じ2秒を止まるのか",
         "angle": "きわどい面白系。身体描写はせず、視線の行き先の理由だけ回収"},
        {"title": "合コンで即帰られた原因が1つに絞れる本当の理由",
         "angle": "失敗談。原因を1つに特定して言い切る"},
        {"title": "なぜ深夜のコンビニで3人だけ同じ棚の前に立つのか",
         "angle": "きわどい面白系。棚の中身は伏せ、行動が揃う理由を回収"},
        {"title": "ワイの検索履歴が7件で全部バレた本当の理由",
         "angle": "軽い下ネタ。履歴の中身は出さず、バレた仕組みだけ言い切る"},
    ],
}


def days_of_week():
    return [0, 1, 2, 3, 4, 5, 6]


def apply_to(path, ch, changes_log):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    ap = d.setdefault("autopilot", {})

    # --- 1. 投稿枠 -------------------------------------------------
    times, why = SCHEDULES[ch]
    old = [f"{t['hour']}:{t['minute']:02d}" for t in ap.get("schedule", {}).get("times", [])]
    sch = ap.setdefault("schedule", {})
    sch["days_of_week"] = days_of_week()
    sch["hour"], sch["minute"] = times[0]
    sch["times"] = [{"hour": h, "minute": m, "days_of_week": days_of_week()} for h, m in times]
    sch["_times_comment"] = f"{TODAY} 指揮者: {why}"
    new = [f"{h}:{m:02d}" for h, m in times]
    ap.setdefault("_schedule_changes", []).append(
        {"date": TODAY, "from": old, "to": new, "reason": why})

    # --- 2. 型ルール -----------------------------------------------
    tr = TITLE_TYPE_RULE[ch]
    tp = d.setdefault("theme_priority", {})
    tp["title_type_rule_20260914"] = tr
    d.setdefault("title_rules", {})["_title_type_note_20260914"] = (
        f"【{TODAY} 実測】最優先型 = {tr['target_type']}。{tr['rule']} 根拠: {tr['evidence']}")

    # --- 3. テーマキュー --------------------------------------------
    q = list(ap.get("theme_queue", []))
    added = 0
    if ch in NEW_THEMES:
        have = {i.get("title") for i in q}
        for t in NEW_THEMES[ch]:
            if t["title"] in have:
                continue
            q.append({"id": uuid.uuid4().hex[:8], **t, "_added": TODAY,
                      "_source": "orchestrator_20260914_type_fix"})
            added += 1

    # 型でソート（目標型を先頭へ、最下位型を末尾へ）
    import re as _re
    order_map = {"2ch-matome": "ABCD", "scp-lab": "ABCD", "company-facts": "CABD",
                 "pokemon-lab": "CBAD", "yokai-watch": "BDCA", "daily-science": "ABCD"}
    pri = {c: i for i, c in enumerate(order_map[ch])}

    def typ(t):
        hq = bool(_re.search(r"(なぜ|本当の理由|理由とは|理由$|正体|真相|どこに|とは？|のか|知ってる|わけ)", t))
        hn = bool(_re.search(r"[0-9０-９]", t))
        return ("A" if hn else "B") if hq else ("C" if hn else "D")

    before_head = [typ(i.get("title", "")) for i in q[:5]]
    q.sort(key=lambda i: pri.get(typ(i.get("title", "")), 9))
    ap["theme_queue"] = q
    ap["_queue_rationale_20260914_orch"] = (
        f"目標型 {tr['target_type']} を先頭へ再配置。並び順 {order_map[ch]}（左が先頭）。"
        f"補充 {added} 件。根拠: {tr['evidence']}")

    # --- 4. pdca_log ------------------------------------------------
    d.setdefault("pdca_log", []).append({
        "date": TODAY,
        "source": "orchestrator",
        "changes": [
            f"投稿枠を {old} → {new} に変更",
            f"タイトル型ルールを設定（目標型 {tr['target_type']}）",
            f"テーマキューを目標型順に再配置（補充 {added} 件、合計 {len(q)} 件）",
        ],
        "evidence": f"投稿枠: {why} / 型: {tr['evidence']}",
        "expected": "登録者/千再生の改善（至上目標）",
        "verify_on": "2026-09-21",
        "note": "2026-09-13 に OAuth 再認可が通り 09-13 から公開が再開したため、"
                "09-09〜09-12 に凍結していた投稿枠・型ルールの意思決定を本日再開した。",
    })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    changes_log.setdefault(ch, {}).update({
        "schedule_from": old, "schedule_to": new, "schedule_reason": why,
        "target_type": tr["target_type"], "type_evidence": tr["evidence"],
        "queue_len": len(q), "queue_added": added,
        "queue_head_type_before": before_head,
        "queue_head_type_after": [typ(i.get("title", "")) for i in q[:5]],
    })


def main():
    changes = {}
    for ch in SCHEDULES:
        # data/channels_orchestrator/*.json は data/channels/*.json への symlink であるため、
        # realpath で重複排除しないと同じファイルに二重適用され pdca_log が重複する。
        done = set()
        for dpath in DIRS:
            p = os.path.join(dpath, f"{ch}.json")
            if not os.path.exists(p):
                print(f"  SKIP (missing): {p}")
                continue
            rp = os.path.realpath(p)
            if rp in done:
                print(f"  SKIP (symlink to already-applied file): {p}")
                continue
            done.add(rp)
            shutil.copy2(p, f"{p}.bak_pdca_{STAMP}")
            apply_to(p, ch, changes)
            print(f"  OK {p}")

    changes["_hold"] = {
        "autopilot_enabled_unchanged": ["2ch-matome(false)", "pokemon-lab(false)"],
        "hold_reason":
            "この2chの autopilot.enabled は指揮者の分析の外側で人が false にした状態であり、"
            "本日の実測データはこの値を動かす根拠にならない。さらに pokemon-lab は OAuth トークンが "
            "2026-09-09 以降更新されておらず（他4chは 09-13 に再認可済み）、有効化しても公開に到達せず "
            "未公開在庫を増やすだけである。加えて全10ch中 daily-science 以外はカスタムサムネイルを "
            "1枚も設定できていない（後述）ため、この状態で生成を増やすと不適切な自動生成サムネの動画が "
            "増えるだけになる。サムネ権限の解消後に再判断する。",
    }
    out = os.path.join(ROOT, "reports", f"orch_config_changes_{TODAY.replace('-','')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)
    print(f"\n変更サマリ: {out}")


if __name__ == "__main__":
    main()
