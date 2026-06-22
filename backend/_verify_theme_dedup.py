#!/usr/bin/env python3
"""テーマ重複防止の検証スクリプト（LLM 不要・語彙段のみで監査）。

1. dedup ユニットテスト: 既知の重複群を正しく flag し、別テーマは flag しないか
2. キュー監査: 両チャンネルの autopilot.theme_queue / module queue に過去テーマと
   語彙的に重複するアイテムが残っていないか
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).parent
sys.path.insert(0, str(BACKEND))
REPO = BACKEND.parent

from pipeline.auto_scenario import theme_dedup as td
from pipeline.auto_scenario import theme_queue as tq

fail = 0

print("=" * 64)
print("1) DEDUP UNIT TEST")
print("=" * 64)
KNOWN_DUPS = [
    ("【衝撃】なぜ自分の声は録音だと「変」に聞こえるのか", "なぜ自分の声が録音と違うと感じるのか？"),
    ("なぜ水たまりの色が変わるのか？ — 環境における水の秘密", "なぜ水たまりはできるのか？"),
    ("なぜ音楽を聴くと気分が良くなるのか？", "なぜ人は音楽を聴くと気分が変わるのか？"),
    ("もし地球から1秒だけ酸素が消えたら", "【驚愕】もしも地球から「1秒だけ」酸素が消えたら？"),
    ("暗い部屋でスマホが目に悪い『本当の』理由", "なぜ「暗い部屋でスマホ」は目が悪くなるのか？"),
]
KNOWN_DISTINCT = [
    ("なぜ空は青いのか？", "なぜ夕焼けは赤いのか"),
    ("なぜ雨の匂いがするのか", "なぜ雨の日は特に眠くなるのか？"),
    ("なぜ星座の形は人によって異なるのか？", "なぜ星空は時折見えなくなるのか？"),
    ("なぜお腹が鳴るのか？", "なぜあくびが伝染するのか？"),
]
for a, b in KNOWN_DUPS:
    s = td.similarity(a, b)
    ok = s >= td.DEFAULT_LEXICAL_THRESHOLD
    print(f"  [{'PASS' if ok else 'FAIL'}] dup    {s:.2f}  {a[:22]} ≈ {b[:22]}")
    fail += not ok
for a, b in KNOWN_DISTINCT:
    s = td.similarity(a, b)
    ok = s < td.DEFAULT_LEXICAL_THRESHOLD
    print(f"  [{'PASS' if ok else 'FAIL'}] distinct {s:.2f}  {a[:20]} | {b[:20]}")
    fail += not ok

print()
print("=" * 64)
print("2) LIVE QUEUE AUDIT (lexical, vs past themes)")
print("=" * 64)
for cid in ("daily-science", "scp-lab"):
    past = td.past_theme_titles(cid)
    print(f"\n── {cid} (past themes: {len(past)}) ──")

    # autopilot.theme_queue
    raw = json.loads((REPO / "data" / "channels" / f"{cid}.json").read_text(encoding="utf-8"))
    ap_q = [(i.get("title") or "").strip() for i in (raw.get("autopilot") or {}).get("theme_queue") or []]
    ap_dups = [(t, td.find_lexical_duplicate(t, past)) for t in ap_q]
    ap_dups = [(t, h) for t, h in ap_dups if h]
    print(f"  autopilot.theme_queue: {len(ap_q)} items, {len(ap_dups)} past-dups")
    for t, h in ap_dups:
        print(f"     ⚠️ '{t[:30]}' ≈ '{h[0][:30]}' ({h[1]:.2f})")
    fail += len(ap_dups)

    # module queue
    mod = tq.load_queue(cid).get("items", [])
    mod_t = [(i.get("title") or "").strip() for i in mod]
    mod_dups = [(t, td.find_lexical_duplicate(t, past)) for t in mod_t]
    mod_dups = [(t, h) for t, h in mod_dups if h]
    print(f"  module theme_queue:    {len(mod_t)} items, {len(mod_dups)} past-dups")
    for t, h in mod_dups:
        print(f"     ⚠️ '{t[:30]}' ≈ '{h[0][:30]}' ({h[1]:.2f})")
    fail += len(mod_dups)

    # internal queue dup check (items dup of each other)
    internal = []
    seen = []
    for t in ap_q:
        h = td.find_lexical_duplicate(t, seen)
        if h:
            internal.append((t, h))
        seen.append(t)
    if internal:
        print(f"  ⚠️ autopilot internal dups: {len(internal)}")
        for t, h in internal:
            print(f"     '{t[:28]}' ≈ '{h[0][:28]}' ({h[1]:.2f})")
    fail += len(internal)

print()
print("=" * 64)
print(f"RESULT: {'✅ ALL CHECKS PASSED' if fail == 0 else f'❌ {fail} ISSUE(S)'}")
print("=" * 64)
sys.exit(1 if fail else 0)
