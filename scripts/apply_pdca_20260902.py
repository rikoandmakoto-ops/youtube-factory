#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDCA適用スクリプト 2026-09-02（指揮者タスク Phase 3）

全て data/analytics/analytics.db の実測に基づく。根拠は各変更の RATIONALE を参照。

主要な実測所見（published_at>=2026-08-10, views>150, n=138）
  1. AVP（平均視聴維持率）が再生数の最大ドライバ
       AVP 60%+ → 中央値再生 1438 / AVP 30-45% → 942
  2. 尺は交絡していない。company-facts は推定尺52.3sでAVP 65.2%、
     他5chは推定尺39.8-56.0sでAVP 31.4-40.4%。→ 差は「尺」ではなく「保持力」
  3. 読み上げ速度が唯一の構造的差分
       company-facts speed=1.2 → AVP 65.2% / 平均視聴34.5s
       他5ch        speed=1.3-1.35 → AVP 31.4-40.4% / 平均視聴13.8-17.0s
  4. ナンバリング型タイトル(#NN：)は AVP 33.3% vs 自然文 52.3%
     → 08-31適用済みルールは有効に機能（08-31公開分 0/7本）。維持。
  5. 登録転換率（登録者/再生）が全社的なボトルネック
       company-facts 0.072% / scp-lab 0.070% / daily-science 0.066%
       pokemon-lab 0.030% / yokai-watch 0.031% / 2ch-matome 0.011%（最低）
  6. インプレッションはビュー数の1/10以下しか計上されない
     （例 08-28 scp-lab: imp 2,611 に対し実再生は数千規模）
     → 流入のほぼ全てがショートフィード。サムネCTRは全体の数%しか動かさない。
       改善原資はサムネではなくフック/維持率/CTAに配分すべき。
  7. scp-lab の theme_queue が 0 本 → 制作停止リスク（最優先修正）
"""
import json, os, shutil, uuid, datetime, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORCH = os.path.join(ROOT, "data", "channels_orchestrator")
STAMP = "20260902"
TODAY = "2026-09-02"

CHANNELS = ["daily-science", "scp-lab", "2ch-matome",
            "pokemon-lab", "yokai-watch", "company-facts"]

# ---------------------------------------------------------------- 1. 読み上げ速度
# 唯一 speed=1.2 の company-facts が AVP 65.2%（他は1.3-1.35でAVP 31-40%）。
# 単一変数として速度を下げ、翌日のコホートで検証する。
SPEED_NEW = {
    "daily-science": 1.2,
    "scp-lab":       1.2,
    "pokemon-lab":   1.2,
    "yokai-watch":   1.2,
    "2ch-matome":    1.25,   # 掲示板ノリはテンポも味なので中間値
    # company-facts は 1.2 のまま（対照群）
}

# ---------------------------------------------------------------- 2. テーマキュー補充
# 目標: 各ch 12本以上。scp-lab は 0 本のため最優先。
REFILL = {
    "scp-lab": [
        ("収容違反後に職員だけが増えていた記録", "人員名簿の齟齬から異常を提示。実体の描写は最後まで伏せる"),
        ("開けてはいけない扉に貼られた3枚目の札", "札の枚数という具体数で不穏さを作る"),
        ("財団が回収した『音の出ない録音テープ』", "再生した職員の証言だけが残る構成"),
        ("なぜSafe指定だったのに死者が出たのか", "分類ミスの記録。答えは最終行まで伏せる"),
        ("Dクラス職員が同じ夢を見た7日間の記録", "日数を核の数字にする"),
        ("収容室から毎晩1cmずつ動いていた椅子", "微小な変化の積み上げで恐怖を作る"),
        ("記録係が全員同じ一文を書き残した理由", "文面は最後に出す"),
        ("財団の監視カメラに14秒だけ映らない区画", "秒数を核にした異常"),
        ("持ち出された報告書が3日後に戻ってきた話", "戻ってきた理由を伏せる"),
        ("SCP-055を誰も説明できない理由", "反ミーム。既知オブジェクトで検索流入を狙う"),
        ("職員の点呼が毎回1人多く終わる施設", "数の齟齬という一点突破"),
        ("なぜ収容違反の記録だけ日付が飛んでいるのか", "抹消された日付を最終行で示唆"),
    ],
    "daily-science": [
        ("なぜ階段を降りるときだけ一段踏み外すのか", "予測歩行と実際の段差のズレ。身体の自動化"),
        ("なぜ人の顔だけ壁のシミにも見えるのか", "パレイドリア。検出の閾値を数字で出す"),
        ("なぜ寝る直前だけ足がビクッと跳ねるのか", "入眠時ミオクローヌス。発生率を数字で"),
        ("なぜ好きな曲だけ鳥肌が立つのか", "フリソン。反応する人の割合を核にする"),
        ("なぜ書いた字を見続けると別の字に見えるのか", "ゲシュタルト崩壊。秒数を核にする"),
        ("なぜ人は暗い場所で音に敏感になるのか", "感覚代替。閾値の変化量を出す"),
        ("なぜ痛いところを自分でさすると痛みが減るのか", "ゲートコントロール理論"),
        ("なぜ他人のあくびだけうつるのか", "伝染性あくび。うつる割合を数字で"),
    ],
    "pokemon-lab": [
        ("ミミッキュの中身はなぜ公式に描かれないのか", "図鑑テキストの記述だけで構成。答えは最終行"),
        ("ヌケニンのHP1は本当に弱点なのか", "特性と数値の噛み合わせを比較で見せる"),
        ("ケッキングの特性なまけは何を失わせているのか", "実質種族値に換算した数字を核にする"),
        ("なぜコイキングは進化するとあれほど強くなるのか", "種族値の増加量を具体数で"),
        ("シェイミの2つのフォルムはどこで差がつくのか", "素早さの差を核にする"),
    ],
    "yokai-watch": [
        ("座敷童子が去った家に何が起きたと記録されているのか", "遠野物語の記述を出典として明示"),
        ("なぜ天狗は山伏の姿で描かれるようになったのか", "修験道との接続。年代を核にする"),
        ("犬神憑きが家系ごと記録された理由", "四国の憑き物筋。記録の残り方を提示"),
        ("なぜ河童は相撲を挑むと伝えられるのか", "水神信仰の零落。地域名を明示"),
    ],
    "company-facts": [
        ("キーエンスの平均年収2000万円台、その内訳", "残業と評価制度まで踏み込む"),
        ("任天堂の年収と離職率、実際の数字", "ゲーム業界比較で意味づけ"),
        ("ニトリの平均年収、実は製造小売だから高いのか", "SPAモデルと人件費の関係"),
        ("JR東海の年収が他のJRより高い理由", "新幹線収益構造を数字で"),
        ("伊藤忠商事の朝型勤務、年収への影響は", "働き方改革の実数値"),
        ("サイゼリヤの原価率と社員年収の関係", "原価率という具体数を核にする"),
        ("ソニーグループの年収1100万円台、部門別の差", "部門差を数字で"),
        ("日本郵政の平均年収、実は職種で倍違う", "職種間格差を核にする"),
    ],
}

# ------------------------------------------------- 3. 維持率改善（低AVPチャンネル）
# scp-lab (AVP 31.6%) / pokemon-lab (AVP 31.4%) が最下位。
# 両chとも3行目で核心を出し切る構成で、以降を見る理由が消えている。
# company-facts（AVP 65.2%）はタイトルで出した問いの答えを最後まで引っ張る。
RETENTION_RULE = {
    "scp-lab": "**答えの遅延（2026-09-02追加・維持率対策）**: "
               "1行目のフックで提示した『何が起きたのか』の核心は、5行目まで明かしてはならない。"
               "3行目・4行目では被害の規模と状況だけを積み上げ、"
               "『では何がそれをやったのか』を伏せたまま進める。"
               "実測でscp-labの平均維持率は31.6%（最下位）。3行目で答えを出し切る構成が原因。",
    "pokemon-lab": "**答えの遅延（2026-09-02追加・維持率対策）**: "
                   "1行目で提示した『どっちが勝つ』『なぜそうなる』の結論は5行目まで出さない。"
                   "3行目・4行目は数値と条件の提示に留め、勝敗や理由を断定しない。"
                   "実測でpokemon-labの平均維持率は31.4%（最下位）。"
                   "対照的に高維持率の動画は結論を最後まで引っ張っている。",
    "daily-science": "**答えの遅延（2026-09-02追加・維持率対策）**: "
                     "1行目の疑問に対する『正体』の一語は5行目まで温存する。"
                     "3行目は現象の規模（数字）だけを出し、機序の名前を先に言わない。",
    "yokai-watch": "**答えの遅延（2026-09-02追加・維持率対策）**: "
                   "1行目で匂わせた原典の恐怖の核心は5行目まで明かさない。"
                   "3行目は出典と年代の提示に留める。",
}

# ---------------------------------------------------------- 4. 登録CTA強化（2ch-matome）
# 2ch-matome は登録転換率 0.011%（他chの1/3〜1/6）。
# 参加型お題でコメントには誘導できているが、登録動線が存在しない。
CTA_2CH = {
    "enabled": True,
    "duration": 1.8,
    "headline": "続きのスレはこっち →",
    "sub": "毎日18時に新スレ",
    "cta": "登録しとかんと明日のスレ流れるで",
}

BACKUP_SUFFIX = f".bak_pdca_{STAMP}"


def load(ch):
    p = os.path.join(ORCH, f"{ch}.json")
    real = os.path.realpath(p)
    with open(real, encoding="utf-8") as f:
        return real, json.load(f)


def backup(real):
    dst = real + BACKUP_SUFFIX
    if not os.path.exists(dst):
        shutil.copy2(real, dst)
    return dst


def save(real, data):
    tmp = real + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    json.load(open(tmp, encoding="utf-8"))  # 妥当性検証
    os.replace(tmp, real)


def main():
    changes = []
    for ch in CHANNELS:
        real, d = load(ch)
        backup(real)
        ch_changes = []

        # --- 1. 読み上げ速度 ---
        if ch in SPEED_NEW:
            old = d.setdefault("defaults", {}).get("speed")
            new = SPEED_NEW[ch]
            if old != new:
                d["defaults"]["speed"] = new
                ch_changes.append(f"speed {old} -> {new}")

        # --- 2. テーマキュー補充 ---
        ap = d.setdefault("autopilot", {})
        q = ap.setdefault("theme_queue", [])
        existing = {t.get("title") for t in q}
        added = 0
        for title, angle in REFILL.get(ch, []):
            if title in existing:
                continue
            q.append({
                "id": uuid.uuid4().hex[:8],
                "title": title,
                "angle": angle,
                "source": f"orchestrator_pdca_{STAMP}",
            })
            added += 1
        if added:
            ch_changes.append(f"theme_queue +{added} (計{len(q)}本)")

        # --- 3. 維持率ルール ---
        if ch in RETENTION_RULE:
            sf = d.setdefault("short_format", {})
            struct = sf.setdefault("structure", [])
            rule = RETENTION_RULE[ch]
            if not any("答えの遅延" in s for s in struct):
                struct.append(rule)
                ch_changes.append("short_format.structure に『答えの遅延』ルール追加")

        # --- 4. CTA強化 ---
        if ch == "2ch-matome":
            cur = d.setdefault("defaults", {}).get("short_endcard", {})
            if cur.get("cta") != CTA_2CH["cta"]:
                d["defaults"]["short_endcard"] = CTA_2CH
                ch_changes.append("short_endcard を登録訴求型に変更")

        # --- 5. 変更根拠の記録 ---
        d.setdefault("pdca_log", []).append({
            "date": TODAY,
            "source": "orchestrator",
            "changes": ch_changes,
            "evidence": {
                "window": "published_at>=2026-08-10, views>150, n=138",
                "avp_by_channel": {
                    "daily-science": 38.9, "scp-lab": 31.6, "2ch-matome": 40.4,
                    "pokemon-lab": 31.4, "yokai-watch": 37.9, "company-facts": 65.2,
                },
                "sub_conversion_pct": {
                    "company-facts": 0.072, "scp-lab": 0.070, "daily-science": 0.066,
                    "yokai-watch": 0.031, "pokemon-lab": 0.030, "2ch-matome": 0.011,
                },
                "hypothesis": "speed=1.2 の company-facts のみ AVP 65.2%。"
                              "読み上げ速度を1.2へ揃え、翌日コホートで検証する（company-factsは対照群）。",
            },
        })

        save(real, d)
        changes.append((ch, ch_changes))

    print(f"=== PDCA {TODAY} 適用結果 ===")
    for ch, cl in changes:
        print(f"\n[{ch}]")
        if not cl:
            print("  変更なし")
        for c in cl:
            print(f"  - {c}")
    print("\nバックアップ: *" + BACKUP_SUFFIX)


if __name__ == "__main__":
    main()
