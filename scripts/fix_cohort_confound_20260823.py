#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コホート交絡の是正と既存PDCAメモリとの突合 2026-08-23（Phase 6・2次修正）

data/pdca-memory/known_findings.json（08-22 23:40 の夜間ラン）と本日の結論を突合したところ、
本日の主要結論のうち2件が誤りだったことが判明したため撤回する。

【撤回1】scp-lab の全角ダッシュ「—」禁止
  本日は CTR 0.72倍（95%CI 0.62-0.85）を根拠に禁止したが、これは全期間集計での値。
  登録者指標と同じ「直近60日公開」コホートに揃えると CTR 0.97倍（95%CI 0.81-1.16）、
  1本あたり登録者 0.74倍（95%CI 0.47-1.18）で、どちらも有意差なし。
  差は61日以上前の動画によって生じた期間交絡だった。
  夜間ランの知見 scp-dash-effect-not-reproduced（CTR 1.32% vs 1.35%、登録/1k 11.75 vs 11.38）
  とも一致する。
  → 前日の「必ず維持する」も本日の「使用禁止」も、どちらも根拠がない。中立に戻す。
     ただし既に書き換えたキュータイトルはそのまま使う（害がないため元に戻す必要もない）。

【撤回2】daily-science の「99%が知らない」禁止
  本日は「効果が確認できない」として前日からの禁止を継続したが、登録者ベースで測ると
  1本あたり登録者 0.417 vs 0.265（1.57倍）、登録/1000再生 0.47 vs 0.29、CTR 1.53% vs 1.28% と
  3指標すべてで正。夜間ランの知見 title-numbers-lower-views-higher-subs とも一致する。
  再生数が伸びないことを理由に禁止していたが、至上目標は登録者であるため禁止は誤り。
  → 禁止を解除する（95%CI 0.76-3.26 と有意ではないため、必須化もしない）。

【追加】yokai-watch は「妖怪ウォッチ作品ネタ」が最大の勝ち筋
  作品名・キャラ名を含む10本は 1本あたり登録者 0.700 vs 0.286（2.45倍）、
  登録/1000再生 0.55 vs 0.19（2.9倍）、CTR 1.96% vs 1.47%。
  伝承のみの回は平均再生では上回る（1543 vs 1281）が登録に繋がらない。
  夜間ランの yokai-ip-beats-folklore と一致するため、title_style の第一条に格上げする。
"""
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT / "data" / "channels", ROOT / "data" / "channels_orchestrator"]
STAMP = "bak_cohort_20260823"

SCP_DASH_OLD = re.compile(
    r"①全角ダッシュ「—」による二段構成は使用禁止。.*?区切りが必要なときは読点「、」を使う。", re.S
)
SCP_DASH_NEW = (
    "①全角ダッシュ「—」の有無はどちらでもよい。前日の「必ず維持する」も、本日一度採用した"
    "「使用禁止」も、どちらも根拠がなかったため撤回する。登録者指標と同じ直近60日コホートで比較すると "
    "CTR 0.97倍（95%CI 0.81-1.16）、1本あたり登録者 0.74倍（95%CI 0.47-1.18）でいずれも有意差がない。"
    "全期間集計で見えた0.72倍は61日以上前の動画による期間交絡だった。"
    "見た目の統一のため当面は読点「、」で揃えるが、これは成績を根拠とした指示ではない。"
)

DS_99_OLD = re.compile(
    r"④「99%が知らない」「9割が勘違い」などの希少性ワードは効果が確認できないため使わない（前日から継続）。"
)
DS_99_NEW = (
    "④「99%が知らない」の禁止を解除する。登録者ベースで測ると1本あたり登録者 0.417 vs 0.265（1.57倍）、"
    "登録/1000再生 0.47 vs 0.29、CTR 1.53% vs 1.28% と3指標すべてで正だった。"
    "前日は再生数0.94倍を理由に禁止していたが、至上目標は登録者であるため判断が誤っていた。"
    "ただし95%CI 0.76-3.26 と有意ではないため必須化もしない。多用せず、内容が伴う回にのみ使う。"
    "なお「9割が勘違い」は該当4本・実登録1人と少数で判定できないため、当面は使わない。"
)

YOKAI_IP = (
    "⓪【最優先】妖怪ウォッチの作品ネタ（作品名・キャラ名・ゲーム内仕様）を必ず扱う。"
    "作品ネタを含む10本は1本あたり登録者 0.700 vs 伝承のみ0.286（2.45倍）、"
    "登録/1000再生 0.55 vs 0.19（2.9倍）、CTR 1.96% vs 1.47% と3指標で上回る。"
    "伝承のみの回は平均再生では上回る（1543 vs 1281）が登録に繋がらない。"
    "伝承・原典は『作品のキャラの元ネタ』として扱い、伝承単体のテーマにはしない。"
    "※95%CI 0.72-8.37 と有意ではないが、夜間PDCAの独立分析でも同じ結論が出ており方向は一貫している。"
)


def main():
    for base in DIRS:
        # --- scp-lab: ダッシュ規則を中立化 ---
        p = base / "scp-lab.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        ts = d["theme_priority"]["title_style"]
        new = SCP_DASH_OLD.sub(SCP_DASH_NEW, ts)
        changed = []
        if new != ts:
            d["theme_priority"]["title_style"] = new
            changed.append("title_style: ダッシュ禁止を撤回し中立化")
        rules = d["voice_style"]["style_rules"]
        for i, r in enumerate(rules):
            if "全角ダッシュ「—」" in r:
                rules[i] = (
                    "【タイトル実測・08-23 2次修正】全角ダッシュ「—」については、前日の「必ず維持する」も"
                    "本日一度出した「使用禁止」も撤回する。直近60日コホートで CTR 0.97倍（95%CI 0.81-1.16）、"
                    "1本あたり登録者 0.74倍（95%CI 0.47-1.18）でいずれも有意差がない。"
                    "全期間で見えた0.72倍は期間交絡だった。ダッシュの有無は成績に影響しないものとして扱う。"
                    "一方「怖」「恐」は1本あたり登録者 0.923 vs 0.612（1.51倍）で正のため、引き続き推奨する"
                    "（ただしCTR単体では有意ではない）。"
                )
                changed.append("style_rules: ダッシュ規則を中立化")
                break
        if changed:
            shutil.copy2(p, p.with_suffix(f".json.{STAMP}"))
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{p.relative_to(ROOT)}: {', '.join(changed)}")

        # --- daily-science: 99%が知らない の禁止を解除 ---
        p = base / "daily-science.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        ts = d["theme_priority"]["title_style"]
        new = DS_99_OLD.sub(DS_99_NEW, ts)
        changed = []
        if new != ts:
            d["theme_priority"]["title_style"] = new
            changed.append("title_style: 99%が知らない の禁止を解除")
        rules = d["voice_style"]["style_rules"]
        for i, r in enumerate(rules):
            if "99%が知らない" in r and "【タイトル実測" in r:
                rules[i] = rules[i].replace(
                    "「99%が知らない」は引き続き効果が確認できないため使わない。",
                    "「99%が知らない」の禁止は解除する。1本あたり登録者 0.417 vs 0.265（1.57倍）、"
                    "登録/1000再生 0.47 vs 0.29、CTR 1.53% vs 1.28% と3指標で正だった。"
                    "前日は再生数のみを見て禁止していた誤り。ただし有意ではないため多用はしない。",
                )
                changed.append("style_rules: 99%規則を更新")
                break
        if changed:
            shutil.copy2(p, p.with_suffix(f".json.{STAMP}"))
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{p.relative_to(ROOT)}: {', '.join(changed)}")

        # --- yokai-watch: 作品ネタ優先を第一条に ---
        p = base / "yokai-watch.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        ts = d["theme_priority"]["title_style"]
        if "⓪【最優先】" not in ts:
            marker = "【2026-08-23 実測により変更】"
            d["theme_priority"]["title_style"] = ts.replace(marker, marker + YOKAI_IP, 1)
            rules = d["voice_style"]["style_rules"]
            rules.insert(0, (
                "【テーマ選定・08-23】妖怪ウォッチの作品ネタ（作品名・キャラ名・ゲーム内仕様）を最優先で扱う。"
                "作品ネタ10本は1本あたり登録者 0.700 vs 伝承のみ0.286（2.45倍）、登録/1000再生 2.9倍、CTR 1.96% vs 1.47%。"
                "伝承のみの回は平均再生では上回る（1543 vs 1281）が登録に繋がらない。"
                "伝承・原典は必ず『作品に登場するキャラの元ネタ』という入り口から語り、伝承単体のテーマにはしない。"
            ))
            shutil.copy2(p, p.with_suffix(f".json.{STAMP}"))
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{p.relative_to(ROOT)}: title_style/style_rules に作品ネタ最優先を追加")

    # 検証
    print()
    for base in DIRS:
        for ch in ["scp-lab", "daily-science", "yokai-watch"]:
            d = json.loads((base / f"{ch}.json").read_text(encoding="utf-8"))
            ts = d["theme_priority"]["title_style"]
            flag = []
            if ch == "scp-lab" and "使用禁止" in ts:
                flag.append("ダッシュ禁止が残存")
            if ch == "daily-science" and "希少性ワードは効果が確認できないため使わない" in ts:
                flag.append("99%禁止が残存")
            if ch == "yokai-watch" and "⓪【最優先】" not in ts:
                flag.append("作品ネタ規則が未反映")
            print(f"  {base.name}/{ch}: {'NG ' + ','.join(flag) if flag else 'OK'}")


if __name__ == "__main__":
    main()
