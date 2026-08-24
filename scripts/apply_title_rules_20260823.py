#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
タイトル生成規則の是正 2026-08-23（指揮者タスク Phase 3 / 根本原因対応）

背景:
  前日(08-22)のPDCAではタイトル施策を voice_style.style_rules に書き込んだが、
  テーマキュー補充のプロンプト(generator.suggest_themes)は style_rules を一切参照せず、
  theme_priority.title_style / good_examples のみを使っている。
  そのため前日のタイトル施策は生成に一切反映されておらず、
  theme_queue の全23件(scp-lab)が禁止したはずの全角ダッシュ「—」形式のままだった。

本スクリプトは実際にタイトルを決めている theme_priority を直接更新し、
併せて既存キュー内の違反タイトルと、破損していた viral_hooks を修復する。

根拠データ: data/analytics/analytics.db（video_reach_daily 41,815imp / video_metrics）
"""
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT / "data" / "channels", ROOT / "data" / "channels_orchestrator"]
STAMP = "bak_title_20260823"

TITLE_STYLE = {
    "scp-lab": (
        "タイトルは必ず具体的なSCP番号を出し、そこに「怖」「恐」を含む断定を添える形で書く"
        "（例:『SCP-XXX「〇〇」接触記録17件、生存者ゼロの恐怖』）。"
        "【2026-08-23 CTR実測により変更】"
        "①全角ダッシュ「—」による二段構成は使用禁止。インプレッション41,815件の実測で "
        "CTR 1.35% vs 非該当1.89%（0.71倍・95%CI 0.61-0.84）と有意に逆効果、1本あたり登録者も0.74倍だった。"
        "区切りが必要なときは読点「、」を使う。"
        "②「怖」「恐」のいずれかを必ず1語入れる（CTR 1.26倍・95%CI 1.01-1.59、1本あたり登録者1.51倍。"
        "CTRと登録者の両方で正だった唯一の要素）。"
        "③「本当の理由」「実は」は使わない（CTR 0.79倍・95%CI 0.66-0.95 で有意に逆効果）。"
        "④被害者数・生存率・経過時間・記録件数など報告書らしい数字を1つ以上入れる。"
        "断定調で言い切り、疑問形や『〜とは？』で濁さない。恐怖の正体そのものはタイトルに書かない。"
    ),
    "yokai-watch": (
        "タイトルは『〇〇の秘密』『〇〇に隠された〇〇』『〇〇の本当は〇〇』など、"
        "隠されているものを匂わせる形で書く。"
        "【2026-08-23 実測により変更】"
        "①「秘密」「隠された」を含む形は CTR 2.67% vs 1.34%（1.99倍・95%CI 1.32-3.02）、"
        "「本当は」「実は」を含む形は1本あたり登録者 1.00 vs 0.28（3.60倍・95%CI 1.10-11.80）。"
        "このどちらかを必ず1つ入れる。"
        "②「怖」「怖すぎる」の優先指定は撤回する。CTR 0.89倍・1本あたり登録者0.75倍で、"
        "再生数は伸びるが登録に繋がらないことが判明した（禁止ではないが優先しない）。"
        "③「なぜ〇〇なのか」型の使用制限も解除する（CTR 0.94倍・登録者1.12倍でほぼ中立）。"
        "④全角ダッシュ「—」は使わず読点「、」で繋ぐ。"
        "妖怪名は具体的に出す（検索性が高い）。答え・オチはタイトルに書かない。"
    ),
    "daily-science": (
        "タイトルは【疑問形 + 具体数字】で書く。"
        "【2026-08-23 登録者実測により変更】"
        "①疑問符「？」を含む形は1本あたり登録者 0.324 vs 0.150（2.16倍）で最も効くため、必ず疑問形にする。"
        "②「なぜ〇〇なのか」始まりは1本あたり登録者 0.400 vs 0.253（1.58倍）で有効なので積極的に使う"
        "（前日の使用抑制を撤回）。"
        "③「本当の理由」「実は」は1本あたり登録者 0.241 vs 0.344（0.70倍）で逆効果のため使わない。"
        "④「99%が知らない」「9割が勘違い」などの希少性ワードは効果が確認できないため使わない（前日から継続）。"
        "⑤「0.3秒」「30秒」「2倍」「17件」のような体感できる具体数字を1つ入れる。"
        "結論はタイトルに含めない。70字前後を目安にする。"
        "「〜について」「〜とは」「〜を解説」のような説明語尾は使わない。"
    ),
    "pokemon-lab": (
        "タイトルは『〇〇に隠された秘密』型を最優先で書く。"
        "【2026-08-23 登録者実測により変更】"
        "①「秘密」「隠された」を含むタイトルは1本あたり登録者 1.00 vs 0.32（3.17倍・95%CI 1.02-9.82）で、"
        "当チャンネルで唯一統計的に有意な正の効果。毎バッチ最低1本は必ずこの型にする。"
        "②『AとB、どっちが勝つ』の対決型は CTR 3.82%/2.87% とチャンネル最上位だが、"
        "1本あたり登録者は0.63倍で登録に繋がっていない。1バッチあたり1本までに抑える。"
        "③ランキングは必ず件数を入れる（例:『〜10選』『〜5体』）。"
        "④全角ダッシュ「—」は使わず読点「、」で繋ぐ。"
        "ポケモン名・キャラ名は具体的に出す（検索性が高い）。答え・1位の正体はタイトルに書かない。"
    ),
}

GOOD_EXAMPLES = {
    "scp-lab": [
        "SCP-5000「人類滅亡」財団が人類を殲滅する側に回った日、生存者1名という恐怖",
        "SCP-2317「世界を喰らう者」収容が破れるまでの残り時間は算出済みだった恐怖",
        "SCP-096「シャイガイ」顔を見た者の生存率0%、財団が最も恐れた記録",
        "SCP-049「ペスト医師」その『治療』を受けた患者に起きた恐ろしい変化",
        "SCP-3008「無限のIKEA」閉じ込められた1000人が辿った怖すぎる末路",
        "SCP-1471「MalO」インストールした3日後、それは部屋にいたという恐怖",
    ],
    "yokai-watch": [
        "ジバニャンに隠された秘密、『地縛霊』という名前が意味するもの",
        "ふぶき姫の元ネタは本当は雪女伝承、原典で逃げた者がどうなったか",
        "キュウビと玉藻前に隠された九尾伝承、実際に起きたとされる事件",
        "妖怪ウォッチの設定5選、実は公式が明かしていない秘密がある",
        "コマさんの元ネタ、狛犬伝承に隠された本当の役割",
    ],
    "daily-science": [
        "なぜ夢で見たことを朝には忘れてしまうのか？",
        "なぜ寝落ちの瞬間に体がビクッとなるのか？その0.5秒に起きていること",
        "くしゃみの瞬間、なぜ目の前が光る？0.5秒間に体で起きている変化",
        "なぜ食後に眠くなるのか？脳への血流が食事直後に30%減っていた",
    ],
    "pokemon-lab": [
        "種族値だけで選んだ『実は最強』ポケモン10選、1位に隠された秘密",
        "ポケモン図鑑の『怖すぎる』説明文5選、公式が隠した衝撃の一文",
        "伝説より強い一般ポケモンに隠された秘密、種族値を並べたら順位が壊れた",
        "コイキングが『史上最弱』と言われる理由に隠された数字の秘密",
    ],
}

# 既存キューの違反タイトル書き換え（ダッシュ除去 + 必須語の付与）
DASH_RE = re.compile(r"\s*—\s*")


def rewrite_title(ch: str, title: str) -> str:
    t = DASH_RE.sub("、", title).replace("、、", "、").strip("、 ")
    if ch == "scp-lab":
        t = t.replace("本当の理由", "理由").replace("の真実", "の記録").replace("実は", "")
        if not re.search(r"[怖恐]", t):
            t = t.rstrip("。 ") + "の恐怖"
    elif ch == "yokai-watch":
        if not re.search(r"秘密|隠|本当は|実は", t):
            t = t.rstrip("。 ") + "に隠された秘密"
    elif ch == "pokemon-lab":
        if not re.search(r"秘密|隠", t):
            t = t.rstrip("。 ") + "に隠された秘密"
    return re.sub(r"\s{2,}", " ", t).strip()


def fix_viral_hooks(tp: dict) -> str | None:
    """1文字ずつに分解されて壊れている viral_hooks を復元する。"""
    vh = tp.get("viral_hooks")
    if isinstance(vh, list) and len(vh) > 20 and all(isinstance(x, str) and len(x) <= 1 for x in vh):
        joined = "".join(vh)
        tp["viral_hooks"] = [joined]
        return f"{len(vh)}個の1文字要素 -> 1件に復元"
    return None


def main():
    log_all = []
    for base in DIRS:
        for ch, style in TITLE_STYLE.items():
            p = base / f"{ch}.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            tp = d.setdefault("theme_priority", {})
            log = []
            if tp.get("title_style") != style:
                tp["title_style"] = style
                log.append("title_style 更新")
            if tp.get("good_examples") != GOOD_EXAMPLES[ch]:
                tp["good_examples"] = GOOD_EXAMPLES[ch]
                log.append(f"good_examples {len(GOOD_EXAMPLES[ch])}件に差し替え")
            vfix = fix_viral_hooks(tp)
            if vfix:
                log.append(f"viral_hooks修復: {vfix}")
            if log:
                shutil.copy2(p, p.with_suffix(f".json.{STAMP}"))
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                log_all.append((str(p.relative_to(ROOT)), log))

    # 既存キューの違反タイトルを書き換え
    for ch in ["scp-lab", "yokai-watch", "pokemon-lab"]:
        qp = ROOT / "data" / "channels" / ch / "theme_queue.json"
        if not qp.exists():
            continue
        q = json.loads(qp.read_text(encoding="utf-8"))
        changed = 0
        for it in q.get("items", []):
            new = rewrite_title(ch, it.get("title", ""))
            if new != it.get("title"):
                it["title"] = new
                changed += 1
        if changed:
            shutil.copy2(qp, qp.with_suffix(f".json.{STAMP}"))
            qp.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
            log_all.append((str(qp.relative_to(ROOT)), [f"キュータイトル {changed}/{len(q['items'])}件を新ルールに書き換え"]))

    print(f"更新ファイル数: {len(log_all)}")
    for path, log in log_all:
        print(f"\n{path}")
        for x in log:
            print(f"   - {x}")


if __name__ == "__main__":
    main()
