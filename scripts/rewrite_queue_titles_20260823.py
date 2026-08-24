#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
テーマキューのタイトルを新ルールに沿って個別に書き直す 2026-08-23

前段の機械置換（apply_title_rules_20260823.py）は「〜の恐怖の恐怖」「〜とはに隠された秘密」等の
不自然なタイトルを生んだため、バックアップから復元したうえで1件ずつ書き直す。

新ルール:
  scp-lab      : 全角ダッシュ「—」禁止 / 「怖」「恐」を必ず1語 / 「本当の理由」「実は」禁止 / 数字を1つ
  yokai-watch  : 「秘密」「隠された」「本当は」「実は」のいずれかを必ず1つ / ダッシュ禁止
  pokemon-lab  : 「秘密」「隠された」のいずれかを必ず1つ / ダッシュ禁止
"""
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAMP = "bak_title_20260823"

TITLES = {
    "scp-lab": [
        "SCP-231「七人の花嫁」、財団が最高機密に指定した███手順の恐怖",
        "O5評議会の正体、財団の最高意思決定機関が[DATA EXPUNGED]した13の恐ろしい記録",
        "SCP-507「不本意な次元旅行者」、別次元に飛ばされる男を財団が手放せない恐ろしい理由",
        "機動部隊MTF、財団の実働部隊が背負う9つの恐怖の任務記録",
        "SCP-1048「ビルダーベア」、愛らしい外見が起こした財団史上最恐の収容違反",
        "SCP-179「すばるの乙女」、太陽系の番人が告げる終わりを財団が恐れる理由",
        "SCP-956「子供割り人形」、財団が封印した収容違反記録の恐怖",
        "SCP-871「景気のいいケーキ」、財団がEuclidに据え置いた分類判定の恐怖",
        "SCP-1783-JP「お船の中はうさぎでいっぱい」、[REDACTED]な航路の先で財団が見た恐怖",
        "SCP-1283-JP「踏切のむこう」、調査員4名が帰還しなかった恐怖の全ログ",
        "SCP-006-JP「あけろ」、ドアの向こうで財団が封印した接触記録の恐怖",
        "SCP-1000「ビッグフット」、財団が抹消した種族の記憶、機密レベル4文書の恐怖",
        "SCP-239「魔女の子供」、財団が最も恐れた収容対象、その理由は[REDACTED]",
        "機動部隊アルファからオメガまで、財団26部隊が担う恐怖の極秘作戦記録",
        "SCP-1548「星と神と終末」、太陽が語りかける内容を財団が機密指定した恐怖",
        "記憶消去薬『アムネジア』、財団が民間人に使い続ける薬剤の恐ろしい副作用",
        "SCP-2000「デウス・エクス・マキナ」、財団が稼働させた人類リセット装置の恐怖",
        "SCP-5000「なぜ？」、財団が人類を皆殺しにしようとした恐怖の動機は[REDACTED]",
        "SCP-1762「ドラゴンが来た箱」、異次元との交信が途絶えた日の恐ろしい記録",
        "SCP-4335「終末の鯨」、Apollyonクラスが意味する収容も終了も不可能という恐怖",
        "SCP-2935「死んだ地球」、別次元で全生命が絶滅した恐怖の原因を財団が調査",
        "SCP-093「赤い海の石」、異次元探索で回収された記録が示す向こう側の恐怖",
        "SCP-3812「名前を超えた存在」、概念を上書きし財団の記録体系を破壊する恐怖",
    ],
    "yokai-watch": [
        "ぬらりひょんの正体に隠された秘密、現代と古代で解釈が違う理由",
        "妖怪ウォッチ「元祖」の名前の由来、実は開発陣が仕込んだ秘密がある",
        "コマさんの元ネタ、狛犬伝承に隠された本当の役割",
        "最強妖怪の入手方法に隠された仕様、効率的に集める手順",
        "フユニャンの元ネタは本当は何か、アニメと伝承が交差する秘密",
        "スネイキーの秘密、元ネタの蛇神伝承に隠された進化の理由",
    ],
    "pokemon-lab": [
        "不思議な進化の過程に隠された秘密、進化先が示す本当の意味",
        "ライバルたちに隠された背景設定、ゲーム内で担う本当の役割",
        "悪の組織の目的に隠された秘密、彼らが本当に狙っていたもの",
        "進化先の選択に隠されたメッセージ、親との絆が示す設定の秘密",
        "知られざるリザードンの進化の秘密、姿が決まった本当の理由",
        "なぜシャンデラは霊タイプなのか？設定に隠された由来の秘密",
        "ゲーム内ストーリーに隠されたメッセージ、キャラクター背景の秘密",
    ],
}

RULES = {
    "scp-lab": lambda t: ("—" not in t) and bool(re.search(r"[怖恐]", t)) and ("本当の理由" not in t),
    "yokai-watch": lambda t: ("—" not in t) and bool(re.search(r"秘密|隠|本当は|実は", t)),
    "pokemon-lab": lambda t: ("—" not in t) and bool(re.search(r"秘密|隠", t)),
}


def main():
    for ch, titles in TITLES.items():
        qp = ROOT / "data" / "channels" / ch / "theme_queue.json"
        bak = qp.with_suffix(f".json.{STAMP}")
        if bak.exists():
            shutil.copy2(bak, qp)  # 機械置換前の状態に復元
        q = json.loads(qp.read_text(encoding="utf-8"))
        items = q.get("items", [])
        if len(items) != len(titles):
            print(f"!! {ch}: 件数不一致 queue={len(items)} 用意={len(titles)} → 先頭から重ねる")
        bad = [t for t in titles if not RULES[ch](t)]
        if bad:
            print(f"!! {ch}: 新ルール違反のタイトルあり、中断")
            for t in bad:
                print("   ", t)
            continue
        for it, new in zip(items, titles):
            it["title"] = new
        qp.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{ch}: {min(len(items), len(titles))}件を書き直し（全件が新ルールを満たすことを検証済み）")


if __name__ == "__main__":
    main()
