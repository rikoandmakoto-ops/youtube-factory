#!/usr/bin/env python3
"""PDCA 2026-09-01 のコンフィグ反映。

実測の根拠は reports/youtube_analysis_20260901.xlsx と pdca_summary_0901.md。

適用する変更:
  1. yokai-watch の extra_rules の「8行目」→「6行目」修正。
     structure は 1〜6行目しか定義していないため、存在しない行を指しており
     高評価CTAの指示が事実上効いていなかった（実測 高評価CTA 1/3）。
  2. 全6chの根拠数値を 2.16倍 → 6.3倍（n=322・単調）に更新し、
     「終盤維持率は登録と無相関」という否定的知見を明記する。
     これがないと後続の実行が終盤維持率の改善を追い続けてしまう。
  3. short_format.cta_fallback を追加。cta_enforcer が最終行を
     決定論的に修復する際に使うチャンネル別の語り口を持たせる。
  4. company-facts の structure 6行目を、実際に登録を求める文面へ修正。
     実測で高評価0/4・登録0/4 とCTAが皆無だった唯一のチャンネル。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUFFIX = ".bak_pdca_20260901b"

CHANNELS = [
    "daily-science",
    "scp-lab",
    "2ch-matome",
    "pokemon-lab",
    "yokai-watch",
    "company-facts",
]

# 2026-09-01 実測に置き換える根拠文（従来の 2.16倍 の記述を差し替える）
EVIDENCE = (
    "**6行目には必ず『高評価』の語を入れ、登録より先に置く。そのうえで同じ行に必ず"
    "『チャンネル登録』も入れる。** 成熟動画 n=322 の高評価率4分位と登録転換の実測: "
    "0-0.2%→0.17 / 0.2-0.4%→0.32 / 0.4-0.8%→0.53 / 0.8%以上→1.07（登録/1000再生）。"
    "最下位群の6.3倍で、途中に反転のない単調増加。"
    "一方 **終盤維持率(90-100%)は登録と無相関**（<15%:0.41 / 15-25%:0.26 / 25-40%:0.42 / 40%+:0.30）で、"
    "「最後まで見せれば登録される」は本データでは否定された。"
    "登録者を増やす観測レバーは終盤維持率ではなく高評価率である。"
    "なお 08-29〜31 の実台本32本では高評価CTA 50% / 登録CTA 38% しか無かったため、"
    "pipeline/cta_enforcer.py が最終行を機械的に補正する。"
    "ただし補正文は定型なので、台本側で自然な文言を書くほうが常に良い。"
)

# チャンネルの語り口に合わせたCTA既定句（cta_enforcer のフォールバック）
CTA_FALLBACK = {
    "scp-lab": {
        "like": "この報告書が届いたなら高評価を残せ。",
        "subscribe": "登録すれば、次の収容違反ファイルが届く。",
    },
    "daily-science": {
        "like": "今日のこれ、面白かったら高評価を押してね。",
        "subscribe": "チャンネル登録すれば、毎日ひとつ雑学が増えるよ。",
    },
    "2ch-matome": {
        "like": "共感したやつは高評価だけ置いてけw",
        "subscribe": "チャンネル登録も頼むわ、毎日投稿しとるで。",
    },
    "pokemon-lab": {
        "like": "え、マジで？ってなったら高評価を押してね。",
        "subscribe": "チャンネル登録すれば、毎日ひとつポケモンの秘密が届くよ。",
    },
    "yokai-watch": {
        "like": "ゾッとしたら高評価を押してね。",
        "subscribe": "チャンネル登録すれば、次の妖怪の原典も調べて持ってくるよ。",
    },
    "company-facts": {
        "like": "面白かったら高評価を押してね。",
        "subscribe": "チャンネル登録すれば、毎日1社の実態が届くよ。",
    },
}

COMPANY_FACTS_LINE6 = (
    "6行目=**高評価CTA+登録CTA**: 必ず高評価を先に求め、同じ行で登録も必ず求める。"
    "『面白かったら高評価を押してね。チャンネル登録すれば、毎日1社の実態が届くよ』。"
    "プロフィール誘導だけで終わらせない（実測でこのチャンネルだけ高評価0/4・登録0/4 とCTAが皆無だった）。"
)


def patch(path: Path, channel_id: str) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    changes: list[str] = []
    short_format = data.get("short_format")
    if not isinstance(short_format, dict):
        return changes

    # --- 1 & 2: extra_rules の根拠文を差し替え（8行目バグもここで消える） ---
    rules = short_format.get("extra_rules")
    if isinstance(rules, list):
        for i, rule in enumerate(rules):
            if not isinstance(rule, str):
                continue
            if "行目には必ず『高評価』" in rule:
                if "8行目" in rule:
                    changes.append("extra_rules[0]: 『8行目』→『6行目』(structureは6行までしか無い)")
                rules[i] = EVIDENCE
                changes.append("extra_rules[0]: 根拠を 2.16倍 → 6.3倍(n=322) に更新")
                break
        else:
            rules.insert(0, EVIDENCE)
            changes.append("extra_rules: 高評価CTAルールを新規追加")

    # --- 3: cta_fallback ---
    fallback = CTA_FALLBACK.get(channel_id)
    if fallback and short_format.get("cta_fallback") != fallback:
        short_format["cta_fallback"] = fallback
        changes.append("short_format.cta_fallback を追加")

    # --- 4: company-facts の6行目 ---
    if channel_id == "company-facts":
        structure = short_format.get("structure")
        if isinstance(structure, list):
            for i, line in enumerate(structure):
                if isinstance(line, str) and line.startswith("6行目"):
                    if structure[i] != COMPANY_FACTS_LINE6:
                        structure[i] = COMPANY_FACTS_LINE6
                        changes.append("structure[6行目]: 登録CTAを明示")
                    break

    if changes:
        # 2回目以降の実行でバックアップを「適用後の内容」で上書きしないこと。
        # EVIDENCE 自体が検索条件に一致するため再実行時も changes は真になり、
        # 無条件 copy2 だとロールバック先が失われる。
        backup = path.with_name(path.name + SUFFIX)
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return changes


def main() -> None:
    for directory in ("data/channels", "data/channels_orchestrator"):
        base = REPO / directory
        print(f"\n===== {directory} =====")
        for channel_id in CHANNELS:
            path = base / f"{channel_id}.json"
            if not path.exists():
                print(f"  {channel_id}: (無し・スキップ)")
                continue
            changes = patch(path, channel_id)
            if changes:
                print(f"  {channel_id}:")
                for change in changes:
                    print(f"    - {change}")
            else:
                print(f"  {channel_id}: 変更なし")


if __name__ == "__main__":
    main()
