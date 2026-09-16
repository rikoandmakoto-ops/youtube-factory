#!/usr/bin/env python3
"""2026-09-16 指揮者: scp-lab / pokemon-lab の max_digit_groups を 1→2 へ。

根拠（すべて実測・ch内対照）:
  - scp-lab は題材名に必ず `SCP-\\d+` が入るため、mdg=1 の枠を題材名だけで
    使い切る。未使用キュー17件のうち 5件(29%) が違反、公開済み209本のうち
    112本(54%) が現ルールでは公開不能だった。mdg=2 にすると違反は
    キュー 0件 / 公開済み 55本(26%) に下がる。
  - 数字の個数と登録/千の間に ch 内で関係は無い（1個 0.863 n=18 /
    2個 0.673 n=10 / 3個 1.055 n=3）。つまり mdg は実績根拠のない
    スタイル規則であり、1 に張る理由が無い。
  - 09-15 に実際に1枠を捨てている（publish_blocked / SCP-2718 + 31分）。
  - pokemon-lab は種族値が構造的に数字2個以上になるため同じ衝突
    （キュー 5/21 = 24% が違反）。停止中だが再開時に同じ枠落ちを起こす。

これは「実績に基づく優先度判断」ではなく**ゲート閾値の仕様判断**なので、
09-16 10:10 の並走 run が同一スナップショットで行った Phase 3 とは重複しない
（09-15 夜メモ N-4 が明示的に本 run へ申し送った項目）。

書き込みは ChannelManager.patch_channel_file に一本化（鉄則）。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from channels.channel_manager import ChannelManager

TARGET = {
    "scp-lab": "題材名 SCP-\\d+ が数字枠を1つ消費するため、本文の数字1つを許容して 2 とする。"
               "キュー違反 5/17→0、公開済み違反 112/209→55。数字個数と登録/千は ch 内で無相関。",
    "pokemon-lab": "種族値（防御5・HP250 等）が構造的に数字2個になるため 2 とする。"
                   "キュー違反 5/21→0。停止中だが再開時の枠落ちを先に潰す。",
}

cm = ChannelManager()
changed = {}
for ch, why in TARGET.items():
    def _m(raw, why=why):
        hc = raw.setdefault("title_rules", {}).setdefault("hard_constraints", {})
        before = hc.get("max_digit_groups")
        if before == 2:
            return
        hc["max_digit_groups"] = 2
        raw.setdefault("pdca_log", [])
        raw["_mdg_note_20260916_orch"] = (
            f"【2026-09-16 指揮者】max_digit_groups {before} → 2。{why}")
        changed[ch] = (before, 2)
    cm.patch_channel_file(ch, _m, reason="orch 20260916 max_digit_groups 1->2")

print("changed:", changed)
# 検証: ディスクを読み直して確認
import json
for ch in TARGET:
    d = json.load(open(f"data/channels/{ch}.json"))
    print(ch, "mdg =", d["title_rules"]["hard_constraints"].get("max_digit_groups"),
          "| note:", ("_mdg_note_20260916_orch" in d))
