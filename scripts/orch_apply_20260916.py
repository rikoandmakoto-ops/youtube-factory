#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指揮者 Phase 3 — 2026-09-16 コンフィグ適用

本日の実データで確定した事実だけを反映する。

【事実 1】2026-09-09〜09-12 の 4 日間、公開がほぼ全停止していた
  video_publish.db: 09-05 33本 / 09-06 30本 / 09-07 27本 / 09-08 21本
                 → 09-09 2本 / 09-10 2本 / 09-11 0本 / 09-12 0本
  原因は OAuth リフレッシュトークンの一斉失効（backend.log に
  「自動公開スキップ — トークン失効のため要再認可」が全 ch 分）。
  09-13 に 5ch が再認可され復帰（09-13 9本 / 09-14 17本 / 09-15 12本）。

【事実 2】トークンが生きているのに autopilot=false なのは 2ch-matome だけ
  youtube_tokens.db の最終リフレッシュ成功時刻:
    daily-science 09-16 06:49 / yokai-watch・socio-rx・scp-lab・company-facts
    ・2ch-matome 09-15 22:30  ← ここまで生存
    pokemon-lab 09-10 07:43 / clip-lab・clip-kaneko・clip-fukada 09-08 23:00
    akashic-librarian 09-07 13:47 / fake-paper 09-07 10:20 / clip-animal 09-06 23:00
  → 2ch-matome は publish 可能。autopilot を戻す。pokemon-lab 他は死んだままなので触らない。

【事実 3】09-17 に予定していた評価は実行不能
  analytics の同期は 09-09〜09-12 が丸ごと欠測（video_metrics の date 列に
  2026-09-09〜09-12 が 1 行も無い）。加えて views は公開から約 2 日遅れて入る
  （09-13 公開の scp-lab は 09-15 スナップショットで初めて views>0）。
  評価対象コホート 09-10〜09-15 で views>0 なのは 6ch 合計 1 本のみ。
  → 各 ch の title_style に書かれた「2026-09-17 に評価する」を 2026-09-23 へ延期。

【事実 4】「維持率 70%以上は登録効率が最下位」は再現しなかった
  同一条件（公開 08-01 以降・200再生以上・n=298）で再集計すると
    <30 0.257 / 30-40 0.515 / 40-50 0.679 / 50-60 0.515 / 60-70 0.425 / 70+ 0.471
  40-50% が頂点であることは再現したが、70%以上帯は最下位ではない（60-70 より上）。
  → retention_target_band(40-50) は据え置くが、70%帯ペナルティを根拠にした
    追加施策はこれ以上積まない、と明記する。

変更しないもの: 投稿枠 / タイトル型ルール / voice_style / テーマキュー補充
  （枠と型は 09-14 変更後のデータが 1 本も計測されていない。同一データで二度決めない。
    キュー在庫は 28〜34 件 = 9〜11 日分あり補充不要。
    voice_style は 09-15 の決定どおり維持率を根拠に触らない。）
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CH_DIR = REPO / "data" / "channels"
REPORTS = REPO / "reports"
MARKER = "orch_20260916"
BAK_SUFFIX = ".bak_pdca_20260916_orch"

CORE = [
    "daily-science",
    "scp-lab",
    "2ch-matome",
    "pokemon-lab",
    "yokai-watch",
    "company-facts",
]

RETENTION_NOTE = (
    "【2026-09-16 指揮者・再現性チェック】09-15 に記録した「維持率 70%以上は登録/千が"
    "全帯で最下位（0.294）」は、同一条件（公開 2026-08-01 以降・200再生以上・"
    "moviepy 6ch・n=298）で再集計すると 0.471 となり再現しなかった。"
    "帯別: <30 0.257 / 30-40 0.515 / 40-50 0.679 / 50-60 0.515 / 60-70 0.425 / 70+ 0.471。"
    "頂点が 40-50% 帯であることは再現しているので retention_target_band は据え置く。"
    "ただし『維持率が高いほど登録が減る』という単調な主張は取り下げる。"
    "70%帯ペナルティを根拠にした追加施策はこれ以上積まないこと。"
    "ch内対照（維持率<50 vs >=50 の登録/千）は 6ch 中 5ch で <50 側が高い"
    "（pokemon-lab 1.70 / daily-science 1.33 / yokai-watch 1.20 / 2ch-matome 1.18 /"
    " scp-lab 1.17）が、company-facts のみ 0.83 で逆向き。company-facts は 70%以上帯が"
    "当ch最良（0.880・n=10）で、他5chと構造が違う。n が薄いので結論は出さず観測を続ける。"
    "なお最も頑健なのは依然として高評価率で、四分位が単調"
    "（Q1 0.275 → Q2 0.428 → Q3 0.515 → Q4 0.936・Q4/Q1 3.40倍・n=474）。6回目の再現。"
)

MATOME_NOTE = (
    "【2026-09-16 指揮者】autopilot を false → true に戻す。"
    "根拠: youtube_tokens.db の最終リフレッシュ成功が 2026-09-15 22:30 で、"
    "当 ch のトークンは生存している（pokemon-lab は 09-10 07:43 が最後で失効済み）。"
    "09-09〜09-12 の公開全停止は OAuth 一斉失効が原因であり、09-13 に再認可された 5ch は"
    "復帰済み。当 ch はトークンが生きているのに autopilot だけ false のまま取り残されていた。"
    "09-15 に false を維持した理由は『サムネ権限が未解決のまま生成を増やすと"
    "自動抽出サムネの動画が増える』だったが、同じサムネ 403 を抱えたまま scp-lab /"
    "company-facts / yokai-watch は公開を継続しており、当 ch にだけ適用するのは一貫しない。"
    "当 ch の登録/千は 0.253（直近14日・6ch 最下位）だが 1日3枠で約 +0.7 登録/日 の"
    "上積みになり、生成コスト以外の副作用はない。副次的に、当 ch にサムネ権限があるか"
    "どうかが明日の公開ログで判明する（現在 403 が確認できているのは scp-lab /"
    "company-facts / yokai-watch の 3ch、成功しているのは daily-science のみ）。"
    "至上目標は登録者数であり、公開枠を空けたままにする理由が無い。"
)


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    changes: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "marker": MARKER,
        "channels": {},
    }

    for ch in CORE:
        path = CH_DIR / f"{ch}.json"
        if not path.exists():
            log(f"⚠️  {ch}: {path} が無い。スキップ")
            continue

        real = path.resolve()
        raw = real.read_text(encoding="utf-8")
        data = json.loads(raw)

        # pdca_log の重複防止（同一 marker が既にあれば何もしない）
        pdca = data.setdefault("pdca_log", [])
        if isinstance(pdca, list) and any(
            isinstance(e, dict) and e.get("marker") == MARKER for e in pdca
        ):
            log(f"⏭  {ch}: marker {MARKER} が既にある。スキップ（二重適用防止）")
            continue

        shutil.copy2(real, str(real) + BAK_SUFFIX)
        ch_changes: list[str] = []

        # --- 1) 評価期日 09-17 → 09-23 -------------------------------------
        before = json.dumps(data, ensure_ascii=False)
        n_hit = before.count("2026-09-17")
        if n_hit:
            after = before.replace("2026-09-17", "2026-09-23")
            data = json.loads(after)
            pdca = data.setdefault("pdca_log", [])
            ch_changes.append(
                f"評価期日 2026-09-17 → 2026-09-23 に延期（{n_hit}箇所）"
            )

        # --- 2) 維持率メモの更新 -------------------------------------------
        opt = data.setdefault("optimization", {})
        opt["_retention_note_20260916_orch"] = RETENTION_NOTE
        band = opt.get("retention_target_band")
        if not isinstance(band, dict):
            opt["retention_target_band"] = {"min": 40, "max": 50}
            ch_changes.append("retention_target_band を 40-50 で新設")
        ch_changes.append("optimization._retention_note_20260916_orch を追加（70%帯は再現せず）")

        # --- 3) 2ch-matome だけ autopilot を復帰 ---------------------------
        if ch == "2ch-matome":
            ap = data.setdefault("autopilot", {})
            if not ap.get("enabled"):
                ap["enabled"] = True
                ap["_enabled_rationale_20260916"] = MATOME_NOTE
                ch_changes.append(
                    "autopilot.enabled false → true（トークン生存を確認・1日3枠）"
                )
            else:
                ch_changes.append("autopilot.enabled は既に true")

        # --- 4) pdca_log ---------------------------------------------------
        pdca.append(
            {
                "date": "2026-09-16",
                "marker": MARKER,
                "by": "orchestrator",
                "changes": list(ch_changes),
                "data_note": (
                    "analytics.db の最終同期は 2026-09-15 22:41。09-09〜09-12 は同期が"
                    "丸ごと欠測しており、09-13〜09-15 公開分は計測遅れで views=0。"
                    "そのため投稿枠・タイトル型ルール・voice_style は一切変更していない。"
                ),
            }
        )

        real.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changes["channels"][ch] = ch_changes
        log(f"✅ {ch}")
        for cc in ch_changes:
            log(f"     - {cc}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "orch_config_changes_20260916.json"
    out.write_text(json.dumps(changes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"\n📄 変更サマリ: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
