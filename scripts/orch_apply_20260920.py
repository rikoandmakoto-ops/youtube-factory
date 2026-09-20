#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026-09-20 指揮者 Phase3: コンフィグ更新

本日の唯一の変更: short_endcard の A/B（OFF群 3ch / 対照ON群 2ch）

根拠（すべて analytics.db の実測・09-19 スナップショット）:
  リーチ天井が降りた 08-19 に、動画の「末尾」を変えるコミットが同日入っている。
    ddff8f8 feat(growth) ... backend/pipeline/short_endcard.py を新設し
    video_generator.py の末尾に無音・静止画のエンドカード(1.6〜1.8s)を焼き込み。
    全6ch で defaults.short_endcard.enabled=true。以後 32日間 一度も検証されていない。

  維持曲線をコホート分解すると、壊れている区間が末尾に寄っている:
    ゆっくり系5ch audience_watch_ratio 中央値
      再生位置      0%     10%    15%    20%    50%    80%   100%
      ①〜08-18   116.7  111.1  107.2   90.8   48.2   33.8   17.2
      ③08-31〜   109.8  107.7  102.6   77.6   32.8   18.7   11.2
      ④09-12〜   109.9  107.7   99.6   74.7   31.8   19.2    9.8
    → 0〜10% は ① と ③④ でほぼ同一。冒頭フックは壊れていない。
      差は 15% 以降で開き、末尾ほど拡大する。100%地点は 17.2 → 9.8 とほぼ半減。

  ループ率(0%地点)と完走率(95-100%)は 08-19 に全5ch同時に落ち、戻っていない:
      ch              ループ①→③④      完走①→③④        再生中央①→③④
      daily-science   114.5 → 110.0    15.6 →  12.1     1076 →  872
      scp-lab         113.5 → 106.4    16.0 →   7.5     1098 →  909
      yokai-watch     119.6 → 110.7    20.7 →  11.7     1492 →  981
      2ch-matome      118.3 → 109.4    19.9 →   9.4     1236 →  873
      pokemon-lab     120.4 → 107.1    22.1 →   8.6     1588 → (停止)
    ch個別の台本改訂では 5ch が同時に同じ日に落ちる説明がつかない。
    08-19 の全ch一斉デプロイ由来と考えるのが自然。

  09-18 の指揮者が「長尺事故」(786d314 で尺を30-45秒帯へ)を戻して推定尺は
  ①28.9s → ④34.0s 相当まで復帰したが、完走率と再生は戻らなかった。
  08-19 に入って **今も戻していない唯一の末尾変更がエンドカード**である。

  かつエンドカードは至上目標を稼いでいない。登録/千再生(6ch合計):
      ①〜08-18(カード無) 0.512 → ②0.510 → ③0.730 → ④0.436
    導入で跳ねていない。一方で完走率は半減している。

設計（交絡を避ける）:
  OFF群 : daily-science / yokai-watch / 2ch-matome
  対照ON: scp-lab / company-facts
  除外  : pokemon-lab（OAuth失効で停止中。条件が揃わない）

  09-19 に台本修正を入れた daily-science と scp-lab を OFF群/ON群 に1本ずつ割ったので、
  「台本修正あり × カード有無」の対照が取れる。
  読む指標も分離する:
    - 09-19 の台本修正 → 20%地点の維持率（動画の前半）
    - 本日のカード撤去 → 完走率95-100% と ループ率0%（動画の末尾）
  測定位置が動画の逆端なので同時に走らせても読み分けできる。

判定: 2026-09-27（09-20〜09-26 公開分が d3 に到達したのち）
  主指標 完走率(95-100%) OFF群が ③④水準 11.5% → 16% 以上へ回復するか
  副指標 ループ率(0%) 110% → 114% 以上 / 再生中央値 d3 / 登録/千再生
  回復しなければ撤回してカードを戻す（登録導線としての価値は残るため）。
"""

import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH_DIR = os.path.join(ROOT, "data", "channels")
STAMP = "bak_endcard_ab_20260920_orch"
TODAY = "2026-09-20"

OFF = ["daily-science", "yokai-watch", "2ch-matome"]
CONTROL = ["scp-lab", "company-facts"]

NOTE_OFF = (
    "【2026-09-20 指揮者・エンドカードA/B（OFF群）】08-19 に全6ch同時投入された無音静止画の"
    "エンドカード(1.6〜1.8s)を本日 enabled=false にする。根拠: 維持曲線をコホート分解すると "
    "0〜10%地点は 08-19 前後で同一（116.7→109.9 はループ差、10%地点 111.1→107.7）であり冒頭は"
    "壊れていない。差は15%以降で開き末尾ほど拡大し、100%地点は 17.2%→9.8% とほぼ半減した。"
    "完走率(95-100%)とループ率(0%)は 5ch が 08-19 に同時に落ち、以後戻っていない"
    "（完走: daily-science 15.6→12.1 / scp-lab 16.0→7.5 / yokai-watch 20.7→11.7 / "
    "2ch-matome 19.9→9.4 / pokemon-lab 22.1→8.6）。ch個別の台本改訂では5ch同時・同日の落ちを"
    "説明できない。09-18 に長尺事故(786d314)を戻しても完走率と再生は戻らず、08-19 に入って"
    "今も戻していない末尾変更はエンドカードだけである。加えて至上目標を稼いでいない"
    "（登録/千再生 6ch合計 ①0.512→②0.510→③0.730→④0.436 で導入による跳ねが無い）。"
    "Shorts はループ再生されるため、末尾1.6秒の無音静止画はループ復帰の直前に"
    "『終わった』合図を置くことになり、ループと完走の双方を削る経路がある。"
    "対照は scp-lab / company-facts（enabled=true のまま）。"
    "判定 2026-09-27: 主指標 完走率95-100% が 11.5%→16%以上、"
    "副指標 ループ率0% 110→114%以上・再生中央値d3・登録/千再生。回復しなければ撤回して戻す。"
)

NOTE_CONTROL = (
    "【2026-09-20 指揮者・エンドカードA/B（対照群・変更なし）】daily-science / yokai-watch / "
    "2ch-matome で enabled=false にしたエンドカードを、当chでは意図的に true のまま残す。"
    "08-19 の全ch一斉デプロイが完走率半減の原因かを判定するための対照であり、"
    "2026-09-27 まで当chの defaults.short_endcard を触らないこと。"
    "なお当ch(company-facts)は完走率19.3〜31.6%・再生中央1059〜1714 を維持している唯一のchで、"
    "対照として最も情報量が大きい。scp-lab は 09-19 の台本修正を受けた ch なので、"
    "OFF群の daily-science（同じく台本修正あり）との対で『台本修正 × カード有無』が読める。"
)


def load(ch):
    p = os.path.join(CH_DIR, f"{ch}.json")
    assert not os.path.islink(p), f"{p} is a symlink — 書き込み先が違う"
    with open(p, encoding="utf-8") as f:
        return p, json.load(f)


def backup(path):
    dst = f"{path}.{STAMP}"
    if not os.path.exists(dst):
        with open(path, encoding="utf-8") as s, open(dst, "w", encoding="utf-8") as d:
            d.write(s.read())
    return dst


def add_pdca(d, text):
    log = d.get("pdca_log")
    if not isinstance(log, list):
        log = []
        d["pdca_log"] = log
    log.append({"date": TODAY, "by": "orchestrator", "change": text})


def main():
    changed = []
    for ch in OFF:
        p, d = load(ch)
        backup(p)
        ec = (d.setdefault("defaults", {})).setdefault("short_endcard", {})
        before = ec.get("enabled", True)
        ec["_enabled_before_20260920"] = before
        ec["enabled"] = False
        ec["_ab_note_20260920"] = NOTE_OFF
        ec["_ab_arm_20260920"] = "off"
        ec["_ab_verdict_date"] = "2026-09-27"
        add_pdca(d, "short_endcard.enabled = false（エンドカードA/B OFF群・判定 09-27）")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")
        changed.append((ch, "OFF", before, False))

    for ch in CONTROL:
        p, d = load(ch)
        backup(p)
        ec = (d.setdefault("defaults", {})).setdefault("short_endcard", {})
        before = ec.get("enabled", True)
        ec["enabled"] = True
        ec["_ab_note_20260920"] = NOTE_CONTROL
        ec["_ab_arm_20260920"] = "control_on"
        ec["_ab_verdict_date"] = "2026-09-27"
        add_pdca(d, "short_endcard は true のまま維持（エンドカードA/B 対照群・09-27まで変更禁止）")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")
        changed.append((ch, "CONTROL", before, True))

    print("=== 適用結果 ===")
    for ch, arm, b, a in changed:
        print(f"  {ch:15s} {arm:8s} enabled: {b} -> {a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
