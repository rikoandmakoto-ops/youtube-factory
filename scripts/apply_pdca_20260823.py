#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDCA コンフィグ更新 2026-08-23（指揮者タスク Phase 3）

根拠: data/analytics/analytics.db（スナップショット 2026-08-22 / reach 2026-08-20）
今回はじめて impressions / CTR が取得できたため、前日まで「再生数のみ」で判定していた
タイトル施策を CTR と 1本あたり登録者で再検証し、逆効果と判明したものを撤回する。

data/channels/*.json（バックエンド読み取り）と data/channels_orchestrator/*.json の両方に反映。
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT / "data" / "channels", ROOT / "data" / "channels_orchestrator"]
STAMP = "bak_pdca_20260823"

# ---------------------------------------------------------------- タイトル規則
SCP_TITLE = (
    "【タイトル実測・08-23更新／前日ルールを撤回】インプレッション実測41,815件のCTR分析で、"
    "全角ダッシュ「—」による二段構成は CTR 1.35% vs 非該当 1.89%（0.71倍・95%CI 0.61-0.84）と"
    "統計的に有意な逆効果であり、1本あたり登録者も0.74倍だった。前日の「—二段構成を必ず維持」は"
    "再生数のみを見た誤判定のため撤回する。今後タイトルに全角ダッシュ「—」を使わない。"
    "代わりに「怖」「恐」を必ず含める（CTR 1.86% vs 1.47%＝1.26倍・95%CI 1.01-1.59、"
    "1本あたり登録者 0.923 vs 0.612＝1.51倍。CTRと登録者の両方で正だった唯一の要素）。"
    "「本当の理由」「実は」系は CTR 0.79倍（95%CI 0.66-0.95）で有意に逆効果のため使わない。"
)

SCP_LENGTH = (
    "【尺の厳守・08-23】維持率45〜70%の動画に限って比較すると、推定尺26.0秒の短い側は"
    "1本あたり登録者0.838、推定尺35.8秒の長い側は0.632だった（1.33倍）。"
    "一方 short_format の目標は22秒なのに実測の平均尺は26〜36秒あり、台本が設定を超過している。"
    "8行構成と total_chars 上限を厳守し、超えた場合は情報を足すのではなく行を削って収めること。"
)

YOKAI_TITLE = (
    "【タイトル実測・08-23更新／前日ルールを撤回】CTR実測（imp 5,005）と登録者実測で再検証した結果、"
    "「怖」を含むタイトルは CTR 0.89倍・1本あたり登録者 0.375 vs 0.500（0.75倍）で、"
    "前日の「怖を優先」ルールは支持されなかったため撤回する（再生数だけ伸びて登録に繋がらない）。"
    "「なぜ」始まりも CTR 0.94倍・登録者1.12倍とほぼ中立のため、前日の使用禁止を解除する。"
    "代わりに優先するのは (1)「秘密」「隠された」を含む形＝CTR 2.67% vs 1.34%（1.99倍・95%CI 1.32-3.02）、"
    "(2)「本当は」「実は」を含む形＝1本あたり登録者 1.00 vs 0.28（3.60倍・95%CI 1.10-11.80）。"
)

YOKAI_PROMISE = (
    "【タイトルと本編の整合・08-23】「1分妖怪ファイル：」プレフィックス型は CTR 3.15%（非該当1.58%）と"
    "最もクリックを集めているのに、1本あたり登録者は0人、平均再生も0.49倍だった。"
    "クリック後に期待が裏切られている典型パターン。タイトルで提示した謎は必ず本編で明確に回収し、"
    "タイトルに書いていない話題へ逸れないこと。プレフィックスの後に置く謎は、"
    "8行のうち6行目までに答えを出せる範囲に限定する。"
)

DAILY_TITLE = (
    "【タイトル実測・08-23更新】至上目標である登録者ベースで再評価した結果、"
    "「なぜ」始まりは1本あたり登録者 0.400 vs 0.253（1.58倍）で有効だったため、前日の使用抑制を解除する。"
    "疑問符「？」を含む形は 0.324 vs 0.150（2.16倍）で最も効く。"
    "一方「本当の理由」「実は」系は 0.241 vs 0.344（0.70倍）で逆効果のため使わない。"
    "「99%が知らない」は引き続き効果が確認できないため使わない。"
)

POKE_TITLE = (
    "【タイトル実測・08-23】「秘密」「隠された」を含むタイトルは1本あたり登録者 1.00 vs 0.32"
    "（3.17倍・95%CI 1.02-9.82）で、当チャンネルで唯一統計的に有意な正の効果。毎バッチ最低1本は必ずこの型を入れる。"
    "一方「どっちが勝つ」「対決」型は CTR 3.82%/2.87% とチャンネル最上位なのに1本あたり登録者は0.63倍で、"
    "クリックは取れても登録に繋がっていない。対決回を作る場合は勝敗の結論だけで終わらせず、"
    "「この見方は他のポケモンでも使える」と次回への期待を残し、登録動機を明示して締めること。"
)

# ---------------------------------------------------------------- 変更定義
def replace_rule(rules, needle, new_text):
    """needle を含む既存ルールを差し替え。無ければ先頭に挿入。"""
    for i, r in enumerate(rules):
        if needle in r:
            rules[i] = new_text
            return "replaced"
    rules.insert(0, new_text)
    return "inserted"


def ensure_rule(rules, marker, new_text):
    for i, r in enumerate(rules):
        if marker in r:
            rules[i] = new_text
            return "replaced"
    rules.insert(1 if len(rules) > 1 else 0, new_text)
    return "inserted"


CHANGES = []


def apply_channel(path: Path, ch: str):
    d = json.loads(path.read_text(encoding="utf-8"))
    vs = d.setdefault("voice_style", {})
    rules = vs.setdefault("style_rules", [])
    log = []

    if ch == "scp-lab":
        log.append(("title", replace_rule(rules, "全角ダッシュ「—」", SCP_TITLE)))
        log.append(("length", ensure_rule(rules, "【尺の厳守", SCP_LENGTH)))

    elif ch == "yokai-watch":
        log.append(("title", replace_rule(rules, "「怖」を含むタイトルは中央値", YOKAI_TITLE)))
        log.append(("promise", ensure_rule(rules, "【タイトルと本編の整合", YOKAI_PROMISE)))
        sf = d.setdefault("short_format", {})
        if sf:
            before = (sf.get("total_chars_min"), sf.get("total_chars_max"))
            sf["total_chars_min"] = 270
            sf["total_chars_max"] = 330
            sf["line_chars"] = "1〜7行目は27〜37字（目標32字）、8行目のみ+15字まで許容"
            log.append(("short_format", f"{before} -> (270, 330)"))

    elif ch == "daily-science":
        log.append(("title", replace_rule(rules, "「99%が知らない」は0.94倍", DAILY_TITLE)))

    elif ch == "pokemon-lab":
        log.append(("title", ensure_rule(rules, "【タイトル実測・08-23】", POKE_TITLE)))

    elif ch == "clip-lab":
        ap = d.setdefault("autopilot", {})
        if ap.get("enabled"):
            ap["enabled"] = False
            ap["disabled_reason"] = (
                "運用方針で凍結中。theme_seeds 0件・theme_queue 未作成・video_metrics 実績0件のまま"
                "平日2枠＋休日2枠がスケジュールされ空回りしていたため 2026-08-23 に停止。"
            )
            log.append(("autopilot", "enabled True -> False"))

    if any(x[1] for x in log):
        shutil.copy2(path, path.with_suffix(f".json.{STAMP}"))
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        CHANGES.append((str(path.relative_to(ROOT)), log))
    return log


def main():
    targets = ["scp-lab", "yokai-watch", "daily-science", "pokemon-lab", "clip-lab"]
    for base in DIRS:
        for ch in targets:
            p = base / f"{ch}.json"
            if p.exists():
                apply_channel(p, ch)
    print(f"更新ファイル数: {len(CHANGES)}")
    for path, log in CHANGES:
        print(f"\n{path}")
        for k, v in log:
            if v:
                print(f"   - {k}: {v}")


if __name__ == "__main__":
    main()
