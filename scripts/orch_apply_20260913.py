#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Factory 指揮者 Phase 3 — コンフィグ更新 (2026-09-13)

本日の前提:
  2026-09-09 以降、全チャンネルで OAuth リフレッシュトークンが失効しており
  公開が 1 本も成立していない（生成は継続、公開のみ停止）。
  したがって **コホートは 09-08 時点で凍結** しており、成績を根拠にした
  新規の投稿枠 / voice_style / スタイルルールの変更は行わない。
  （同一データで二重に意思決定しない、という運用ルールに従う）

本日実施するのは以下の 2 種類のみ:
  A. テーマキューの残量補充（運用継続のための在庫管理。成績判断ではない）
  B. pokemon-lab のキュー構成是正（n=33 の実測で裏付けのある新規知見）

--- B の根拠（pokemon-lab, 公開 2026-07-20 以降 / views>=150 / n=33） ---
  数値提示型        n=16  平均 874 再生  登録/千 0.429  維持 34.3%
  その他            n=10  平均 944 再生  登録/千 0.212  維持 44.6%
  対決(どっちが)型   n= 7  平均1493 再生  登録/千 0.191  維持 53.7%

  → 対決型は再生を 1.7 倍稼ぐが、登録変換は数値提示型の 1/2.2。
    pokemon-lab は登録/千 0.277 で moviepy 6ch 中ワースト2 であり、
    にもかかわらず現行キューの先頭が対決型で占められていた。
    対決型を禁止はしない（再生の絶対値は出る）が、キュー構成比を
    数値提示型 >= 70% になるよう入れ替える。検証は復旧後コホートで行う。

使い方:  python3 scripts/orch_apply_20260913.py [--dry-run]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CH_DIR = ROOT / "data" / "channels"
ORCH_DIR = ROOT / "data" / "channels_orchestrator"
SUFFIX = ".bak_pdca_20260913_orch"
DRY = "--dry-run" in sys.argv

# 1日あたりの枠数（キュー残日数の計算に使う）
SLOTS_PER_DAY = {
    "daily-science": 3,
    "scp-lab": 3,
    "2ch-matome": 3,
    "pokemon-lab": 3,
    "yokai-watch": 3,
    "company-facts": 4,
}
TARGET_DAYS = 7  # 復旧後に即枯れないよう 7 日分の在庫を確保する

# ---------------------------------------------------------------------------
# A. 補充テーマ（各 ch の実測トップの型をそのまま踏襲して作る）
# ---------------------------------------------------------------------------

# scp-lab 勝ち型: 「SCP番号 + 具体的な数字/時間 + 消失・途絶の未解決な問い」
#   実測トップ: 1283-JP踏切で消えた(3.03) / 096記録消失(2.20) / 1987 24時間ごと(2.10)
#               4335 観測記録途絶(2.08) / 2399 72時間(1.88) / 6121 毎晩1cm・14日目(1.84)
SCP_THEMES = [
    ("SCP-1440 なぜ追跡班は7日目に報告をやめたのか", "到達点のない徘徊。7日という区切りで報告が途切れた事実だけを提示する"),
    ("SCP-3008 なぜ在庫リストだけが毎晩12行増えるのか", "閉じた空間の帳簿が増え続ける。12行という具体数を軸に"),
    ("SCP-2718 閲覧記録が31分で全消去された理由", "閲覧した人間ではなく記録の側が消える。31分の一致を扱う"),
    ("SCP-1471 通知が届いた48時間後に何が起きたのか", "端末越しの接触。48時間後の共通点を並べる"),
    ("SCP-055 なぜ記述だけが3回書き直されたのか", "対象ではなく記述が保たない。書き直し3回という記録を軸に"),
    ("SCP-3999 観測員の記録が9行目で途切れる理由", "9行目という一致点。以降の記録が存在しない"),
    ("SCP-1983 扉の向こうで捜索隊が消えた記録", "踏切型（実測1位 3.03）の再現。境界を越えた側の記録だけが無い"),
    ("SCP-2000 なぜ再起動は6回目で止まったのか", "回数という区切り。6回目以降の記録欠落"),
    ("SCP-4666 訪問が確認された家だけ記録が2日ずれる", "時刻のずれ。2日という具体差を軸に"),
    ("SCP-093 なぜ帰還者だけ証言が15分短いのか", "証言時間の差。15分という欠落を扱う"),
    ("SCP-1730 探索隊が4層で引き返した本当の理由", "層という区切り。4層以降の映像が無い"),
    ("SCP-3288 なぜ記録係だけが毎回交代させられるのか", "対象ではなく観測側が保たない構造"),
]

# daily-science 勝ち型: 「身体で毎日起きる感覚 + 具体的な倍率/秒数」
#   実測トップ: 座ると腰だけ痛い 圧力1.4倍(3.47) / 濡れた紙は3倍破れやすい(2.42)
#               満月と睡眠 月齢29.5日(1.23) / 甘い物のあと塩気 3分(1.16)
DS_THEMES = [
    ("なぜ寝起きは身長が2cm高いのか", "椎間板の水分。朝と夜で測ると差が出る具体数を軸に"),
    ("なぜ片足立ちは目を閉じた瞬間に3倍ぐらつくのか", "視覚が担う姿勢制御の割合を倍率で示す"),
    ("なぜ熱い風呂のあとだけ指紋が消えるのか", "角質の吸水。戻るまでの分数を出す"),
    ("なぜ長く歩いたあと数分だけ指がむくむのか", "腕を下げた姿勢と血流。分単位の変化を扱う"),
    ("なぜ紙で切った傷だけ痛みが2倍長引くのか", "切創の断面と神経密度。痛みの持続を倍率で"),
    ("なぜ立ち上がった3秒後に目の前が暗くなるのか", "起立性の血圧変動。3秒という具体秒数を軸に"),
    ("なぜ味噌汁は冷めると2倍しょっぱく感じるのか", "温度と塩味受容。温度差と感度の関係"),
    ("なぜ左右の耳で聞こえる音程が違うのか", "有毛細胞の左右差。Hz の差を提示する"),
    ("なぜ長電話のあと耳だけ熱くなるのか", "接触と血流。何分で戻るかを出す"),
    ("なぜ重い荷物を下ろした直後に腕が浮くのか", "筋紡錘の残効。秒単位で消える現象"),
]

# company-facts 勝ち型: 「企業名 + 具体年収/金額 + 実は/本当はどこに」
#   実測トップ: Netflix 月額1,590円どこに消える(1.98) / サントリー年収1,000万・残業19.5h(1.89)
#               OLC 年収536万・離職率2.1%(1.78) / トヨタ 年収982万(1.66)
CF_THEMES = [
    ("任天堂の平均年収986万円、実は開発職と販売職で差が出る", ""),
    ("ニトリの平均年収864万円、離職率と配置転換の実態", ""),
    ("味の素の平均年収1,065万円、本当はどこまで手当か", ""),
    ("ファーストリテイリングの年収1,012万円、店長職の労働時間", ""),
    ("伊藤忠商事の年収1,753万円、実は何年目から届くのか", ""),
    ("JR東日本の平均年収698万円、本当はどこに消えるのか", ""),
    ("Amazonの配送料、本当はどこに消えているのか", ""),
    ("スターバックスのラテ550円、原価はどこに消えるか", ""),
    ("リクルートの平均年収1,138万円、実は等級で倍近く違う", ""),
    ("日本電産の平均年収817万円、残業時間の実態", ""),
]

# pokemon-lab 勝ち型: 「種族値など具体数値の提示」（対決型ではない）
#   実測トップ: ハピナスHP255・特防なのに防御(1.06) / ヌメルゴンvsバンギラス 特防(1.05)
#               シェイミ2形態の正体127(1.16) / 初代図鑑けつばん(0.98)
PK_THEMES = [
    ("ツボツボの防御230・特防230という極端な設計の理由", "攻撃10に対して両受け230。数値の非対称をそのまま提示する"),
    ("ケッキングの攻撃160に なまけ が付いた理由", "種族値670に対する特性の重り。数値で成立を説明"),
    ("ヌケニンのHP1という設計が通った理由", "HP1固定と特性の組み合わせ。数値の極端さを軸に"),
    ("ラッキーの防御5・HP250という配分の意味", "実測1位型（ハピナス 1.06）の再現。防御の数値を主語にする"),
    ("メタモンの全種族値48という並びの理由", "全能力が同値。48という数字そのものを扱う"),
    ("デオキシスの攻撃180・防御20が同居する理由", "フォルム設計の数値差を提示"),
    ("コイキングの攻撃10が進化後155になる理由", "進化前後の数値差を主語にする"),
    ("アーケオスの攻撃140に よわきー が付いた理由", "高種族値に対する制約特性を数値で"),
    ("ハピナスの特防135とラッキー95の差の意味", "進化での数値変化。差分を提示する"),
    ("ソーナンスのHP190に攻撃技が無い理由", "耐久数値と技構成の設計意図"),
    ("シャンデラの特攻145が炎ゴーストに置かれた理由", "タイプと数値配分の関係"),
    ("ヨワシの単独時HP45が群れで倍以上になる理由", "フォルム差を数値で提示"),
]

REFILL = {
    "scp-lab": SCP_THEMES,
    "daily-science": DS_THEMES,
    "company-facts": CF_THEMES,
    "pokemon-lab": PK_THEMES,
}

NOTE_KEY = "_pdca_note_20260913_orch"
NOTE_TEXT = (
    "【2026-09-13 指揮者】09-09 以降 OAuth 失効で全ch公開停止中（生成は継続）。"
    "コホートが 09-08 で凍結しているため、投稿枠・voice_style・スタイルルールは一切変更しない"
    "（同一データでの二重意思決定を避ける）。本日の変更はテーマキュー在庫の補充のみ。"
)
PK_NOTE_KEY = "_queue_rationale_20260913_orch"
PK_NOTE_TEXT = (
    "【2026-09-13 実測 n=33 / 公開07-20以降 / views>=150】"
    "数値提示型 登録/千 0.429(n=16) > その他 0.212(n=10) > 対決(どっちが)型 0.191(n=7)。"
    "対決型は平均1493再生と再生では1.7倍稼ぐが、登録変換は数値提示型の1/2.2。"
    "pokemon-lab は登録/千 0.277 で 6ch 中ワースト2 なのに、キュー先頭が対決型で占められていた。"
    "対決型は禁止せず（再生の絶対値は出るため）キュー構成比を数値提示型>=70%へ是正し、"
    "対決型は末尾へ回した。検証は公開復旧後の新規コホート（n>=20/ch）で行う。"
)


def title_of(item) -> str:
    return item if isinstance(item, str) else (item.get("title") or "")


def is_versus(item) -> bool:
    t = title_of(item)
    return ("どっちが" in t) or ("どっちが勝つ" in t)


def make_item(idx: int, ch: str, title: str, angle: str) -> dict:
    return {
        "id": f"orch20260913{ch[:2]}{idx:03d}",
        "title": title,
        "angle": angle,
        "source": "orchestrator_20260913",
    }


def apply_channel(ch: str, report: list) -> None:
    path = CH_DIR / f"{ch}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    ap = data.setdefault("autopilot", {})
    queue = ap.get("theme_queue") or []
    before = len(queue)

    # --- B: pokemon-lab のみキュー構成を是正（対決型を末尾へ） ---
    reordered = False
    if ch == "pokemon-lab":
        versus = [q for q in queue if is_versus(q)]
        rest = [q for q in queue if not is_versus(q)]
        if versus and queue[: len(rest)] != rest:
            queue = rest + versus
            reordered = True
        ap[PK_NOTE_KEY] = PK_NOTE_TEXT

    # --- A: 在庫補充 ---
    target = SLOTS_PER_DAY[ch] * TARGET_DAYS
    existing = {title_of(q) for q in queue}
    added = 0
    for i, (title, angle) in enumerate(REFILL.get(ch, [])):
        if len(queue) >= target:
            break
        if title in existing:
            continue
        # pokemon-lab は補充分（数値提示型）を対決型より前に入れる
        item = make_item(i, ch, title, angle)
        if ch == "pokemon-lab":
            head = [q for q in queue if not is_versus(q)]
            tail = [q for q in queue if is_versus(q)]
            queue = head + [item] + tail
        else:
            queue.append(item)
        existing.add(title)
        added += 1

    ap["theme_queue"] = queue
    ap.setdefault(NOTE_KEY, NOTE_TEXT)

    days_before = round(before / SLOTS_PER_DAY[ch], 1)
    days_after = round(len(queue) / SLOTS_PER_DAY[ch], 1)
    report.append(
        {
            "channel": ch,
            "queue_before": before,
            "queue_after": len(queue),
            "added": added,
            "runway_days_before": days_before,
            "runway_days_after": days_after,
            "versus_reordered": reordered,
        }
    )

    if DRY:
        print(f"  [dry-run] {ch}: {before} -> {len(queue)} (+{added}) "
              f"runway {days_before}d -> {days_after}d reorder={reordered}")
        return

    # 書き込み（バックエンドが読む channels/ と 指揮者用 channels_orchestrator/ の両方）
    #
    # ★重要★ data/channels_orchestrator/{ch}.json は ../channels/{ch}.json への
    #   **シンボリックリンク**（git 上も mode 120000）。ここに tmp.replace() で書くと
    #   シンボリックリンクが実体ファイルに置き換わり、以後 2 つのディレクトリが乖離する。
    #   リンクである限り channels/ 側を書けば自動的に反映されるので、触らないこと。
    for target_dir in (CH_DIR, ORCH_DIR):
        tgt = target_dir / f"{ch}.json"
        if not tgt.exists():
            continue
        if tgt.is_symlink():
            # リンク先（= CH_DIR 側）を書けば反映される。リンクは破壊しない。
            continue
        shutil.copy2(tgt, tgt.with_name(tgt.name + SUFFIX))
        if target_dir is CH_DIR:
            payload = data
        else:
            payload = json.loads(tgt.read_text(encoding="utf-8"))
            payload.setdefault("autopilot", {})["theme_queue"] = queue
            payload["autopilot"].setdefault(NOTE_KEY, NOTE_TEXT)
            if ch == "pokemon-lab":
                payload["autopilot"][PK_NOTE_KEY] = PK_NOTE_TEXT
        tmp = tgt.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(tgt)
    print(f"  ✅ {ch}: queue {before} -> {len(queue)} (+{added}) "
          f"runway {days_before}d -> {days_after}d reorder={reordered}")


def main() -> None:
    print("=== Phase 3: コンフィグ更新 2026-09-13 ===")
    print("方針: 投稿枠/voice_style/スタイルは変更しない（コホートが09-08で凍結中）")
    print("      本日はテーマキュー在庫補充 + pokemon-lab のキュー構成是正のみ\n")
    report = []
    for ch in SLOTS_PER_DAY:
        apply_channel(ch, report)
    out = ROOT / "reports" / "orch_config_changes_20260913.json"
    if not DRY:
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n変更サマリ: {out}")
    print("\n完了")


if __name__ == "__main__":
    main()
