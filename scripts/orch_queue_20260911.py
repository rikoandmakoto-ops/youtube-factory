#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-11 pokemon-lab の theme_queue 補充（枯渇 0 本 → 20 本）.

当chは 08-25 を境に 登録/千再生 0.26→0.20 と6ch中唯一悪化し、
browse/suggested CTR も 0.69% で最下位。原因の一つがキュー枯渇による
テーマ品質の低下と判断した。実測で効いた型（二人称 0.45 vs 0.15）に
全件を揃えて補充する。「なぜ」開始は当chでは 0.00(n=9) のため使わない。

投入前に backend/pipeline/title_constraints.check() で全件を機械検証する。
"""
import json, os, shutil, sys, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from backend.pipeline import title_constraints as tc  # noqa: E402

STAMP = "20260911_orch"
CH = "pokemon-lab"

THEMES = [
    ("君が知らないメタモンの変身の正体", "へんしん後も HP だけ元のまま。対戦で最初に破綻する数値を軸に"),
    ("あなたが選ばない御三家の本当の強さ", "初手で選ばれにくい草タイプの対面性能。選択率と勝率のズレ"),
    ("君が見落とすラッキーの体力設定の理由", "HP は最上位なのに防御が最低クラス。役割集中の設計思想"),
    ("あなたが勝てないカビゴンの起きるわけ", "ねむる＋カゴのみ。起床タイミングが読み合いになる仕組み"),
    ("君が知らないイーブイ進化条件の実態", "石・なつき・場所・時間と条件系統がバラバラな理由"),
    ("あなたが誤解するタイプ相性の真相", "等倍に見えて実は特性で無効化される組み合わせ"),
    ("君が気づかないギャラドスの種族値の裏側", "コイキングからの伸び幅が全ポケモン屈指。配分の意図"),
    ("あなたが使わないソーナンスの本当の役割", "自分から攻撃できない設計が対戦環境で刺さる条件"),
    ("君が知らないポケセン無料の理由", "世界観上の費用負担の設定。ゲーム体験を切らさない設計意図"),
    ("あなたが忘れる初代バグ技の正体", "セレクトバグの仕組みと、以降の作品で塞がれた経緯"),
    ("君が読めないミミッキュの中身の真相", "ばけのかわの耐久換算。中身の描写が公式でどこまで語られたか"),
    ("あなたが避けるヌメルゴン特防の実態", "特防が飛び抜けて高い代わりに何を捨てているか"),
    ("君が知らないマスターボール1個の理由", "入手が1個に制限される設計。難易度曲線の作り方"),
    ("あなたが倒せないケッキング怠けの裏側", "種族値670に対する特性デメリットの釣り合わせ方"),
    ("君が驚くコイキングの進化前設定の正体", "弱さを演出として仕込んだ設計。はねるしか覚えない意味"),
    ("あなたが選ぶ御三家は水が多いわけ", "序盤ジムとの相性で水が有利になる構造"),
    ("君が知らないレベル100上限の理由", "経験値テーブルと対戦バランスの都合"),
    ("あなたが気づかない色違い確率の実態", "作品ごとに変わる抽選方式と、体感とのズレ"),
    ("君が勘違いするラプラス図鑑説明の真相", "乱獲の記述が作品ごとに書き換えられている点"),
    ("あなたが使えないニンフィア進化の本当の条件", "フェアリー技＋なつき。他の進化系統と条件の質が違う理由"),
]


def main():
    orch_p = os.path.join(ROOT, "data", "channels_orchestrator", f"{CH}.json")
    d = json.load(open(orch_p, encoding="utf-8"))

    # --- 機械検証（backend と同じゲート） ---
    ng = []
    for t, _ in THEMES:
        r = tc.check(t, d)
        if not r["ok"]:
            ng.append((t, tc.violation_summary(r)))
    if ng:
        print("❌ 制約違反があるため中止:")
        for t, v in ng:
            print(f"   {t} -> {v}")
        return 1
    print(f"✅ {len(THEMES)} 件すべて hard_constraints を通過")

    items = []
    for t, a in THEMES:
        items.append({"id": "p20260911" + hashlib.md5(t.encode()).hexdigest()[:6],
                      "title": t, "angle": a})

    for base in ("channels_orchestrator", "channels"):
        p = os.path.join(ROOT, "data", base, f"{CH}.json")
        b = f"{p}.bak_queue_{STAMP}"
        if not os.path.exists(b):
            shutil.copy2(p, b)
        cfg = json.load(open(p, encoding="utf-8"))
        ap = cfg.setdefault("autopilot", {})
        q = ap.setdefault("theme_queue", [])
        have = {str(i.get("title")) for i in q if isinstance(i, dict)}
        added = [i for i in items if i["title"] not in have]
        q.extend(added)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  {base}/{CH}.json: +{len(added)} → 計 {len(q)} 本")
    return 0


if __name__ == "__main__":
    sys.exit(main())
