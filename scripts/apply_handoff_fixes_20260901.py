#!/usr/bin/env python3
"""2026-09-01 引き継ぎ課題のチャンネル設定反映。

対象は **data/channels/ のみ**。data/channels_orchestrator/ は同日から
data/channels/ への symlink になったので、片側に書けば両方に効く
（docs/CHANNEL_CONFIG_SOURCE_OF_TRUTH.md）。

適用内容:

  A. 2ch-matome — 08-31 の PDCA 変更が orchestrator 側にしか当たっていなかった
     ものを master に反映（theme_blacklist +4件 / 公開済みと重複する
     theme_seeds 5件を削除）。data/pdca-memory/applied_changes.json の
     2026-08-31 "seed-pollution-recurred-on-2ch" に記録された変更そのもの。

  B. analytics 未同期の解消 — video_format.analytics ブロックが無いために
     run_daily_pdca._enabled_channels() から漏れていたチャンネルに
     analytics.enabled=true を入れる（company-facts / clip-lab / clip-fukada /
     clip-kaneko / clip-animal）。akashic-librarian は旧スキーマの
     enabled=false だったので現行スキーマに揃えて有効化する。

  C. fake-paper — 再生4,178で登録0の是正。
  D. yokai-watch — 登録効率(0.28/1000再生)の是正。
  E. pokemon-lab — auto_optimize_schedule を false に戻す（08-22 の決定）。

実行:
    python3 scripts/apply_handoff_fixes_20260901.py [--dry-run]

バックアップは <file>.bak_handoff_20260901 に取る。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNELS = ROOT / "data" / "channels"
BAK_SUFFIX = ".bak_handoff_20260901"

DRY = "--dry-run" in sys.argv

_changes: list = []


def log(channel: str, what: str) -> None:
    _changes.append((channel, what))
    print(f"  [{channel}] {what}")


def load(cid: str) -> dict:
    return json.loads((CHANNELS / f"{cid}.json").read_text(encoding="utf-8"))


def save(cid: str, data: dict) -> None:
    path = CHANNELS / f"{cid}.json"
    if DRY:
        return
    bak = path.with_name(path.name + BAK_SUFFIX)
    if not bak.exists():
        shutil.copy2(path, bak)
    # symlink 先（master 実体）を書き換えるため、rename ではなく上書きする。
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# =====================================================================
# A. 2ch-matome — 08-31 の変更が master に当たっていなかった分
# =====================================================================

# 08-31 に「最短語ルール」で追加されたブラックリスト語。
_2CH_BLACKLIST_ADD = ["県名", "いらん商品", "画面チカチカ", "彼女いない歴"]

# 既に公開済み（うち3件は上位15本）で、seeds に残ったままだと再投稿される題材。
# 末尾1件は seeds 内部の重複（合コン系が2本あった）。
_2CH_SEED_DROP = [
    "実際には存在しないけどありそうな県名あげてけ",
    "コンビニで一番いらん商品あげてけ",
    "なんかPCの画面チカチカするんやが",
    "ワイ、彼女いない歴＝年齢やけど質問ある？",
    "合コンで言ったら終わる一言あげてけ",
]


def apply_2ch_matome() -> None:
    d = load("2ch-matome")
    bl = list(d.get("theme_blacklist") or [])
    added = [w for w in _2CH_BLACKLIST_ADD if w not in bl]
    if added:
        bl.extend(added)
        d["theme_blacklist"] = bl
        log("2ch-matome", f"theme_blacklist に追加: {added}")

    seeds = d.get("theme_seeds") or []
    before = len(seeds)
    kept = [s for s in seeds if (s.get("title") or "") not in _2CH_SEED_DROP]
    if len(kept) != before:
        d["theme_seeds"] = kept
        log("2ch-matome", f"theme_seeds {before} → {len(kept)} 件（公開済み/重複を削除）")
    save("2ch-matome", d)


# =====================================================================
# B. analytics 未同期の解消
# =====================================================================

_ANALYTICS_BLOCK = {
    "enabled": True,
    "fetch_retention_for": 5,
    "performance_threshold": {
        "min_ctr": 4,
        "min_retention": 40,
        "min_views_7d": 1000,
    },
}

_ANALYTICS_TARGETS = [
    "company-facts",
    "clip-lab",
    "clip-fukada",
    "clip-kaneko",
    "clip-animal",
    "akashic-librarian",
]


def apply_analytics() -> None:
    for cid in _ANALYTICS_TARGETS:
        path = CHANNELS / f"{cid}.json"
        if not path.exists():
            print(f"  [!] {cid}.json が無いのでスキップ")
            continue
        d = load(cid)
        vf = d.setdefault("video_format", {})
        cur = vf.get("analytics") or {}
        if cur.get("enabled") is True and "fetch_retention_for" in cur:
            continue
        # akashic-librarian / socio-rx は旧スキーマ（track_metrics / auto_adjust）。
        # AnalyticsConfig は両方受けるので、既存キーを残したまま現行キーを足す。
        merged = dict(cur)
        merged.update(_ANALYTICS_BLOCK)
        vf["analytics"] = merged
        log(cid, "video_format.analytics.enabled=true（日次PDCAの同期対象に入る）")
        save(cid, d)


# =====================================================================
# C. fake-paper
# =====================================================================

_FAKE_PAPER_STRUCTURE = [
    "1行目=**3秒フック(最重要)**: 論文の結論そのものを断定で置き、『——という論文があります』で締める。この言い回しは冒頭フック判定に使われるので必ず含める。挨拶・前置き・テーマ予告は禁止。",
    "2行目=**リスナー(タクミ)の食いつき**: 『え、そんな研究あるんですか』『それは知らなかった』と素直に驚く1行だけを置く。ここは全チャンネル共通の離脱地点（再生位置20%）なので、架空の固有名詞を並べず、人間の反応で引っ張る。解説を始めない。",
    "3行目=**出典＋手法（転換ワード必須）**: 『しかも』『さらに』『ところが』のいずれかで始め、架空の掲載誌名・研究機関名と、被験者数か追跡期間のどちらかを1行にまとめる。実在の学術誌・大学・研究者名は絶対に使わない。この転換ワードは中盤フック判定に使われるので省略しない。",
    "4行目=**衝撃の結果①**: 主要な結果を数字付きの断定で置く（『〇%』『〇日早い』『有意差が出ています』）。ここが一番もっともらしい行。",
    "5行目=**追い打ち**: 『しかも』『さらに』で二つ目の結果を重ね、信じ込ませ切る。ここまで一切ネタばらししない。",
    "6行目=**オチ＝ネタばらし(必須)**: 『なお、この論文は存在しません』『掲載誌ごと架空です』と明示的に言い切る。ほのめかしで終わらせない。ネタばらし後に『でも本当かも』と揺り戻すのも禁止。1行目の題材語（例:『論文』『ゴロゴロ音』）を1語以上再登場させてループ感を作る。",
    "7行目=**高評価CTA+登録CTA**: **必ず高評価を先に求める**。『面白かったら高評価をお願いします。チャンネル登録で、存在しない次の論文をお届けします』。『高評価』と『チャンネル登録』の語をそのまま含める。",
]

_FAKE_PAPER_LIKE_RULE = (
    "**7行目には必ず『高評価』の語を入れ、登録より先に置く。そのうえで同じ行に必ず"
    "『チャンネル登録』も入れる。** 成熟動画 n=322 の高評価率4分位と登録転換の実測: "
    "0-0.2%→0.17 / 0.2-0.4%→0.32 / 0.4-0.8%→0.53 / 0.8%以上→1.07（登録/1000再生）。"
    "最下位群の6.3倍で、途中に反転のない単調増加。fake-paper は 08-22〜08-31 の公開6本で"
    "高評価率0.43%（他chと同水準）ながら登録0人で、7行目に『高評価』の語が一度も"
    "入っていなかった唯一のチャンネルだった。pipeline/cta_enforcer.py が最終行を機械的に"
    "補正するが、補正文は定型なので台本側で自然に書くほうが常に良い。"
)

_FAKE_PAPER_EXTRA_RULES = [
    "1〜5行目は徹底して真顔で積み上げる。笑わせにいかない・煽らない・感嘆符を連打しない。",
    "もっともらしさは具体的な数字で作る。サンプル数・追跡期間・変化率・有意水準のうち最低2つを本文全体で使う。",
    "固有名詞（学術誌名・研究機関名・研究者名）はすべて架空のものを新規に作る。実在の名称は一切使わない。",
    "1行目に『という論文があります』、3行目の頭に転換ワード、7行目に『高評価』＋『チャンネル登録』——この4つは構造バリデータが直接見ているので必ず入れる。",
    "6行目のネタばらしは省略・後回し・次回送りにしない。1本の中で必ず完結させる。",
    "解説役(ミサキ編集長)は学術発表の丁寧語。リスナー役(タクミ)は素直に信じ込み、6行目で崩れる。",
    "読んだ人が行動に移せてしまう嘘（治療法・投薬・自己診断・危険行為）は作らない。",
]

_FAKE_PAPER_LENGTH_RATIONALE = (
    "【2026-09-01 実測により 190〜235字 → 170〜210字】08-22〜08-31 の公開6本の"
    "平均視聴維持率は 27.6% で、他5ch（38.3〜57.2%）を大きく下回る全ch最下位。"
    "実台本の総字数は 228〜302字（中央値 265字）で、設定していた 190〜235字の帯を"
    "常に超えていた。08-25 の回帰（維持率 = 89.0 - 0.1612×字数、r=-0.849）では"
    "265字→46.3%、190字→58.4% であり、実測 27.6% はさらに低い。"
    "7行のアブストラクト構成は維持したまま1行あたりを 28字→24字 に締め、"
    "shorts_length_guard.enforce_band() が効く帯に入れる。"
    "あわせて2行目の『架空の掲載誌名＋研究機関名』を3行目へ畳んだ。"
    "全ch共通の離脱地点である再生位置20%（7行なら2行目）に、"
    "視聴者にとって何の報酬もない架空の固有名詞が並んでいたため。"
)


def apply_fake_paper() -> None:
    d = load("fake-paper")
    sf = d["short_format"]

    sf["structure"] = _FAKE_PAPER_STRUCTURE
    log("fake-paper", "short_format.structure: 2行目を『リスナーの食いつき』に、出典を3行目へ / 7行目を高評価→登録CTAに")

    rules = list(_FAKE_PAPER_EXTRA_RULES)
    rules.insert(0, _FAKE_PAPER_LIKE_RULE)
    sf["extra_rules"] = rules
    log("fake-paper", "short_format.extra_rules: 高評価を登録より先に置くルールを先頭に追加")

    # cta_enforcer は short_format.cta_fallback を最優先で読む。他6chは持っていて
    # fake-paper だけ持っていなかったため、機械補正の文言がチャンネル JSON 側から
    # 制御できなかった。
    sf["cta_fallback"] = {
        "like": "面白かったら高評価をお願いします。",
        "subscribe": "チャンネル登録で、存在しない次の論文をお届けします。",
    }
    log("fake-paper", "short_format.cta_fallback を追加（cta_enforcer が使う）")

    sf["total_chars_min"] = 170
    sf["total_chars_max"] = 210
    sf["line_chars"] = "1〜6行目は20〜26字（目標24字）、7行目のみ36〜48字を許容"
    sf["line_min_chars"] = 16
    sf["line_max_chars"] = 48
    sf["length_rationale"] = _FAKE_PAPER_LENGTH_RATIONALE
    log("fake-paper", "short_format 尺: 190〜235字 → 170〜210字（維持率27.6%＝全ch最下位の是正）")

    defaults = d.setdefault("defaults", {})
    # タイトルは「架空論文ファイル：」＋本体＋ハッシュタグ。オチ（嘘であること）を
    # タイトルで先に割るとフックが死ぬ。content_policy が求めるフィクション明示は
    # 「本編のネタばらし・概要欄冒頭・サムネのバッジ『架空論文』」の3箇所で、
    # タイトルはそこに含まれない。
    defaults["short_title_hashtags"] = "#shorts #架空論文"
    log("fake-paper", "defaults.short_title_hashtags: '#フィクション' を外す（オチの先出しを避ける）")
    # シリーズ名(9字)＋ハッシュタグ(16字)を差し引くと本体に使える幅が狭い。
    # フィードで途中省略されるとスワイプが止まらないので本体を明示的に詰める。
    defaults["short_title_core_max"] = 26
    log("fake-paper", "defaults.short_title_core_max=26（シリーズ名＋タグ込みでフィードに収める）")

    save("fake-paper", d)


# =====================================================================
# D. yokai-watch
# =====================================================================

# 30日以内に同じ題材を再投稿し、年齢を揃えた公開3日目の再生で明確に負けたもの。
#   コマさん   08-01 1,082 → 08-26   123
#   エンマ大王 08-04 1,462 → 08-28   152
_YOKAI_BLACKLIST_ADD = ["コマさん", "エンマ大王"]


def apply_yokai() -> None:
    d = load("yokai-watch")
    bl = list(d.get("theme_blacklist") or [])
    added = [w for w in _YOKAI_BLACKLIST_ADD if w not in bl]
    if added:
        bl.extend(added)
        d["theme_blacklist"] = bl
        log("yokai-watch", f"theme_blacklist に追加: {added}（30日以内の再投稿が公開3日目で1/8〜1/10に沈んだ題材）")

    sf = d["short_format"]
    # 高評価率 0.365% は6ch中5位（scp-lab 0.464 / daily-science 0.457）。
    # 実測の四分位表では 0.2-0.4% 帯の登録転換は 0.32/1000再生、0.4-0.8% 帯は 0.53。
    # 「ゾッとしたら」という条件を付けると怖がらなかった視聴者が全員こぼれるので、
    # 条件を外して誰でも押せる言い方にする。
    sf["cta_fallback"] = {
        "like": "よかったら高評価だけ置いていってね。",
        "subscribe": "チャンネル登録すれば、次の妖怪の原典も調べて持ってくるよ。",
    }
    log("yokai-watch", "short_format.cta_fallback.like: 『ゾッとしたら』の条件を外す（高評価率0.365%＝6ch中5位）")

    structure = list(sf.get("structure") or [])
    if structure:
        structure[-1] = (
            "6行目=**高評価CTA+登録CTA**: **必ず高評価を先に求める**。"
            "『よかったら高評価だけ置いていってね。"
            "チャンネル登録すれば、次の妖怪の原典も調べて持ってくるよ』。"
            "『ゾッとしたら』のように高評価を条件付きにしない（条件を付けると"
            "怖がらなかった視聴者が全員こぼれる）。"
        )
        sf["structure"] = structure
        log("yokai-watch", "short_format.structure 6行目: 高評価を無条件の言い方に")

    save("yokai-watch", d)


# =====================================================================
# E. pokemon-lab — auto_optimize_schedule の戻し
# =====================================================================

def apply_pokemon() -> None:
    d = load("pokemon-lab")
    ap = d.get("autopilot") or {}
    if ap.get("auto_optimize_schedule") is not False:
        ap["auto_optimize_schedule"] = False
        d["autopilot"] = ap
        log(
            "pokemon-lab",
            "autopilot.auto_optimize_schedule=false（08-22 に全5chで false 固定した決定。"
            "channels 側だけ true に戻っていた）",
        )
        save("pokemon-lab", d)


def main() -> None:
    print(f"チャンネル設定の反映{'（dry-run）' if DRY else ''}")
    apply_2ch_matome()
    apply_analytics()
    apply_fake_paper()
    apply_yokai()
    apply_pokemon()
    print(f"\n変更 {len(_changes)} 件")
    if DRY:
        print("dry-run のため書き込んでいません")
    else:
        print("⚠️ 稼働中バックエンドは channel JSON をメモリに保持している。")
        print("   反映するには: launchctl kickstart -k gui/$(id -u)/com.youtube-factory.backend")


if __name__ == "__main__":
    main()
