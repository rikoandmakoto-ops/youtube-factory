#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
autopilot.theme_queue の是正 2026-08-23（Phase 6・3次修正）

【判明した問題】
テーマキューが2系統あり、本日修正したのは実際には使われない方だった。

  - data/channels/<id>/theme_queue.json ... /factory/run（手動実行）が消費
  - <channel>.json の autopilot.theme_queue ... APScheduler の autopilot が消費
    （backend/api_channel_autopilot.py:_pop_or_refill_theme が ap["theme_queue"] を読む）

定時投稿は後者を使うため、本日 theme_queue.json に対して行った40件の書き直しは
実際の制作には反映されない。voice_style.style_rules を直したつもりが
theme_priority を直す必要があったのと同じ取り違えを、キューでも繰り返していた。

【対応】
精査済みの theme_queue.json の内容を autopilot.theme_queue へ反映し、両者を一致させる。
併せて新ルール適合を機械検証する。

反映前の autopilot.theme_queue の状態（新ルール違反）:
  scp-lab      7件すべてに「怖/恐」なし
  yokai-watch  10件すべてが全角ダッシュ使用、かつ10件すべてが伝承のみで作品ネタなし
               （本日の最有力知見「作品ネタは1本あたり登録者2.45倍」と正面から矛盾）
  pokemon-lab  12件中5件が対決型（新ルールは1バッチ1本まで）、11件が「秘密/隠」なし
  daily-science 10件すべて適合のため変更なし
  2ch-matome / company-facts 新ルールの対象外のため変更なし
"""
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT / "data" / "channels", ROOT / "data" / "channels_orchestrator"]
STAMP = "bak_apqueue_20260823"
TARGETS = ["scp-lab", "yokai-watch", "pokemon-lab"]

RULES = {
    "scp-lab": lambda t: "—" not in t and re.search(r"[怖恐]", t) and "本当の理由" not in t,
    "yokai-watch": lambda t: "—" not in t and re.search(r"秘密|隠|本当|実は", t),
    "pokemon-lab": lambda t: "—" not in t and re.search(r"秘密|隠", t),
}
DUEL = re.compile(r"どっち|対決")


def main():
    problems = []
    for ch in TARGETS:
        qp = ROOT / "data" / "channels" / ch / "theme_queue.json"
        items = json.loads(qp.read_text(encoding="utf-8"))["items"]

        # 検証してから反映する
        bad = [i["title"] for i in items if not RULES[ch](i["title"])]
        if bad:
            problems.append((ch, "ルール違反", bad))
            continue
        duels = [i["title"] for i in items if DUEL.search(i["title"])]
        if ch == "pokemon-lab" and len(duels) > 1:
            problems.append((ch, "対決型が2件以上", duels))
            continue

        new_q = [
            {"id": i["id"], "title": i["title"], "angle": i.get("angle") or "自由"}
            for i in items
        ]
        for base in DIRS:
            p = base / f"{ch}.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            old = d["autopilot"].get("theme_queue") or []
            shutil.copy2(p, p.with_suffix(f".json.{STAMP}"))
            d["autopilot"]["theme_queue"] = new_q
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{p.relative_to(ROOT)}: autopilot.theme_queue {len(old)}件 -> {len(new_q)}件")

    if problems:
        print("\n!! 反映を中止したチャンネル:")
        for ch, why, xs in problems:
            print(f"   {ch}: {why}")
            for x in xs:
                print("      ", x)

    # 最終検証
    print("\n=== 最終検証: autopilot.theme_queue（バックエンドが消費する方）===")
    for ch in ["scp-lab", "yokai-watch", "pokemon-lab", "daily-science"]:
        d = json.loads((ROOT / "data" / "channels" / f"{ch}.json").read_text(encoding="utf-8"))
        q = d["autopilot"].get("theme_queue") or []
        chk = RULES.get(ch)
        nbad = sum(1 for i in q if chk and not chk(i["title"])) if chk else 0
        nduel = sum(1 for i in q if DUEL.search(i["title"]))
        ndash = sum(1 for i in q if "—" in i["title"])
        fq = json.loads((ROOT / "data" / "channels" / ch / "theme_queue.json").read_text(encoding="utf-8"))["items"]
        same = [i["title"] for i in q] == [i["title"] for i in fq]
        print(f"  {ch:14s} {len(q):2d}件 違反{nbad} ダッシュ{ndash} 対決型{nduel} "
              f"ファイル側キューと一致:{same}")


if __name__ == "__main__":
    main()
