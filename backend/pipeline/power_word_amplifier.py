"""Power Word Amplifier — パワーワード注入によるエンゲージメント増幅（Round 7）。

狙い:
    2026年のショートアルゴリズムはエンゲージメント（いいね・コメント・シェア）を
    完走率と並ぶ重要シグナルとして評価。視聴者がリアクションしたくなる
    「パワーワード」を戦略的に配置することでエンゲージメント率を向上させる。

    本モジュールは:
    1. 既存の行に対して単語レベルでの強化を適用（行追加ではない）
    2. チャンネル別のパワーワード辞書を管理
    3. 弱い表現を強い表現にアップグレード
    4. 2ch-matome は軽いエロ・下ネタ系語彙を優先的に強化

既存モジュールとの違い:
    - swipe_stop_injector: 行と行の"間"にリフック"行を追加"
    - viral_score_gate: バイラル度を"スコアリング"するだけ（変更しない）
    - hook_ab_selector: 冒頭フック行を"選択"（他行は対象外）
    - 本モジュール: 既存行の"単語レベル"で表現をアップグレード
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

# =====================================================================
# パワーワード変換辞書（弱い表現→強い表現）
# =====================================================================

# 汎用パワーワード変換
#
# 【2026-08-31 修正】従来は裸の部分文字列パターンだったため、形態素境界を無視して
# 語の内部にヒットし、日本語として壊れた台本が本番投稿されていた。実害例:
#   「寝つきが悪くなる」→ r"変" が「変わる」に誤ヒット →「寝つきが闇が深いわる」
#   （daily-science #101 / 08-30 03:17 の1行目＝3秒フックがこの状態で公開された）
# さらに「多い」→「膨大な」のような 形容詞→連体句 の置換は述語位置で文法破綻する
#   （「事例が多い。」→「事例が膨大な。」）。
#
# 実測影響（台本アーカイブ616本と実績の突合 n=214）:
#   破損あり  n=14  AVP 32.2% / 平均再生 694
#   破損なし  n=200 AVP 53.7% / 平均再生 1000   ＝ 維持率 1.67倍、再生 1.44倍の差
#
# 対策は2段構え:
#   (1) 各パターンに前後の否定先読み／後読みを付け、活用語尾・複合語の内部で
#       マッチしないようにする。
#   (2) 連体形でしか使えない置換候補には mode="attributive" を付け、
#       _amplify_line() 側で「直後が名詞的か」を検証してから適用する。
#
# エントリ形式: (パターン, [置換候補], mode)  mode: "free" | "attributive"

_UNIVERSAL_UPGRADES: List[Tuple[str, List[str], str]] = [
    # (元の表現パターン, [強化候補リスト], mode)
    (r"すごい", ["ヤバすぎる", "えぐい", "とんでもない"], "free"),
    (r"大きい", ["桁違いの", "規格外の", "モンスター級の"], "attributive"),
    (r"小さい", ["極小の", "ミクロの"], "attributive"),
    (r"多い", ["膨大な", "異常な数の", "想像を絶する量の"], "attributive"),
    (r"少ない", ["ごくわずかな", "数えるほどしかない"], "attributive"),
    # 「変」は裸だと 変わる/変化/変換/大変/異変 に誤ヒットする。連体の「変な」限定。
    (r"変な(?=[ぁ-ん一-龥ァ-ヶ])", ["異常な", "不気味な", "ゾッとする"], "free"),
    (r"面白い", ["狂ってる", "天才すぎる"], "free"),
    (r"危ない", ["致命的に危険な", "命に関わる"], "attributive"),
    (r"古い", ["太古の", "伝説の"], "attributive"),
    (r"強い", ["最強の", "化け物級の", "規格外の"], "attributive"),
    (r"高い", ["天文学的な", "ぶっ飛んだ"], "attributive"),
    (r"有名な", ["伝説の", "誰もが知る"], "free"),
    # 「普通」は「普通の/普通に」等で述語にも連体にもなるため連体限定に絞る
    (r"普通の(?=[ぁ-ん一-龥ァ-ヶ])", ["一見なんの変哲もない", "どこにでもある"], "free"),
    # 「し」まで消費する。ゼロ幅先読みにすると「びっくりする」→「度肝を抜かれする」と壊れる。
    (r"びっくりし(?=[てたま])", ["度肝を抜かれ", "言葉を失っ"], "free"),
    (r"怖い", ["ガチで恐ろしい", "背筋が凍る"], "free"),
    (r"不思議な", ["科学では説明できない", "人類未解明の"], "free"),
]

# =====================================================================
# チャンネル別パワーワード辞書
# =====================================================================

_CHANNEL_UPGRADES: Dict[str, List[Tuple[str, List[str], str]]] = {
    # 【2026-08-31】チャンネル辞書も汎用辞書と同じ形態素境界の問題を持っていたため
    # 否定先読み／後読みを追加。特に 2ch-matome の r"女" は「彼女」より前に置かれて
    # いたため「彼女」→「彼美女」を量産していた（複合語の内部にヒットしていた）。
    "daily-science": [
        (r"(?<![大追])研究(?![者所室])", ["衝撃の研究", "ノーベル賞級の研究"], "free"),
        (r"(?<![再])発見(?![者])", ["世紀の大発見", "人類史を変える発見"], "free"),
        (r"(?<![実追])実験(?![者室台])", ["狂気の実験", "禁断の実験"], "free"),
        (r"(?<![小])宇宙(?![人船飛])", ["宇宙の果て", "人類が到達できない宇宙の深淵"], "free"),
    ],
    "scp-lab": [
        (r"危険(?![性物視])", ["XKクラスシナリオ級に危険", "世界が終わるレベル"], "free"),
        (r"異常な(?=[ぁ-ん一-龥ァ-ヶ])", ["認識災害レベルの", "財団すら手を焼く"], "free"),
        (r"(?<![実])実験(?![者室台])", ["倫理違反の実験", "Dクラス被験者による実験"], "free"),
        (r"怪物", ["収容不可能な存在", "人類の天敵"], "free"),
    ],
    "2ch-matome": [
        # エロ面白系優先。※長い語を先に置くこと（短い語が先だと複合語内で先に食う）
        (r"彼女(?![ら達])", ["ドスケベ彼女", "ヤバすぎる彼女"], "free"),
        (r"(?<![彼少王魔美処侍長次三])女(?!性|子|優|装|神|王|史|の子|っぽ)", ["美女", "とんでもない女"], "free"),
        (r"体験(?![談者])", ["夜の体験", "禁断の体験", "人に言えない体験"], "free"),
        (r"友達(?![ら])", ["ヤバい友達", "クレイジーな友達"], "free"),
        (r"(?<![女])先生(?![方])", ["とんでもない先生", "伝説の先生"], "free"),
        (r"上司(?![ら達])", ["クソ上司", "サイコパス上司"], "free"),
        (r"(?<![会電世神童実逸昔対])話(?![すしせそさ題法者術中])", ["ドン引きする話", "人に言えない話"], "free"),
        (r"(?<![珍])事件(?![簿])", ["放送事故レベルの事件", "伝説の事件"], "free"),
        (r"(?<![大])失敗(?![作])", ["大事故", "人生終了レベルの失敗"], "free"),
        # 置換候補は名詞なので、動詞活用（バレる/バレた/バレて…）には適用しない
        (r"バレ(?![エるらりれろたてなくまばよ])", ["全バレ", "修羅場", "地獄絵図"], "free"),
    ],
    "company-facts": [
        (r"(?<![純営粗])利益(?![率])", ["ぶっ壊れ利益", "異次元の利益"], "free"),
        (r"倒産(?![者])", ["一夜にして消滅", "地獄の倒産劇"], "free"),
        (r"(?<![副])社長(?![室])", ["独裁社長", "伝説の社長", "狂気の社長"], "free"),
        (r"ブラック(?![ボリ])", ["ガチのブラック", "人権無視の"], "free"),
        (r"年収(?![入])", ["ぶっ飛んだ年収", "信じられない年収"], "free"),
    ],
    "pokemon-lab": [
        (r"(?<![のこ])ポケモン(?![センリ])", ["伝説のポケモン", "ヤバすぎるポケモン"], "free"),
        (r"(?<![初仮再期定])設定(?![値画])", ["闇設定", "子供に見せられない設定"], "free"),
        (r"(?<![未])進化(?![論形])", ["禁断の進化", "ヤバすぎる進化"], "free"),
        (r"図鑑(?![番])", ["トラウマ図鑑", "闇すぎる図鑑"], "free"),
    ],
    "yokai-watch": [
        (r"妖怪(?![ウ])", ["最恐の妖怪", "出会ったら終わりの妖怪"], "free"),
        (r"(?<![都])伝説(?![的上])", ["語られない伝説", "封印された伝説"], "free"),
        # 裸の「村」は 村人/農村/山村/中村(人名) の内部に食い込むため単独名詞のみ
        (r"(?<![農山漁市町中西東北南木野])村(?![人長民役里])", ["絶対に行ってはいけない村", "呪われた村"], "free"),
        (r"(?<![百])怪談(?![師会])", ["実話怪談", "ガチの怪談"], "free"),
    ],
    "akashic-librarian": [
        (r"(?<![新])記録(?![者係])", ["封印された記録", "人類が触れてはいけない記録"], "free"),
        (r"真実(?![味])", ["隠された真実", "歴史が書き換わる真実"], "free"),
        (r"(?<![黒裏])歴史(?![家的上])", ["消された歴史", "教科書に載らない歴史"], "free"),
    ],
}

# =====================================================================
# 感嘆表現の強化
# =====================================================================

_EXCLAMATION_UPGRADES: List[Tuple[str, str]] = [
    (r"([^。！？!?]+)。$", r"\1！"),       # 「〜。」→「〜！」（文末の句点を感嘆に）
    # ↑ 全行ではなく、パワーワードが含まれる行のみに適用
]


# =====================================================================
# 適用ロジック
# =====================================================================

def _should_amplify(line: str) -> bool:
    """この行にパワーワード強化を適用すべきか判定。"""
    # 既に十分パワフルな行はスキップ
    if re.search(r"(ヤバ|えぐ|衝撃|最強|伝説|禁断|狂気)", line):
        return False
    # 短すぎる行はスキップ
    if len(line) < 8:
        return False
    # 相槌行はスキップ
    if re.match(r"^(うん|ああ|へー|なるほど|そう[だな])", line):
        return False
    return True


# 名詞の先頭になりうる文字（連体修飾が成立するか判定するのに使う）
_NOUN_HEAD = re.compile(r"[一-龥ァ-ヶA-Za-z0-9０-９]")

# 置換後に現れたら文法破綻とみなすパターン（保険）
#
# 【2026-08-31 修正】当初 `(?:った|って|わる|…)(?<![ぁ-ん])` と書いていたが、
# 後読みが見るのは「いま自分がマッチした語の末尾文字」であり、これらは全て
# ひらがな終わりなので後読みが必ず失敗し、8分岐中6分岐が沈黙して死んでいた。
# 用言への食い込み検出は正規表現ではなく _breaks_conjugation() で行う。
# ここは「連体形の直後に終止・活用が来る」破綻だけを見る。
_BROKEN_AFTER_REPLACE = re.compile(
    r"(?:の|な)(?:[。、！？!?…]|です|でし|だっ|ます|ました|ない|なる|なっ|する|し[た て]|$)"
)

# 用言の活用語尾。置換語の直後にこれが来る場合、元の語は名詞ではなく
# 用言の語幹だったことになるため（例:「変」が「変わる」に食い込む）、置換を差し戻す。
_CONJUGATION_TAIL = re.compile(
    r"^(?:った|って|わる|わっ|われ|わり|える|えっ|えて|える|きる|きた|して|した|"
    r"らる|られ|りる|りた|れる|れた|ろう|なる|なっ|ない|ます|ました)"
)


def _breaks_conjugation(text: str, insert_end: int) -> bool:
    """置換語の直後が用言の活用語尾になっていないかを見る。

    「寝つきが悪くなる」の「悪」に相当する位置へ名詞句を差し込むと
    「寝つきが闇が深いわる」のような破綻が生じる。挿入直後の文字列が
    活用語尾で始まっていれば、元の語は用言の語幹だったと判断する。
    """
    return bool(_CONJUGATION_TAIL.match(text[insert_end:]))


def _is_attributive_position(text: str, end: int) -> bool:
    """マッチ直後が名詞的か＝連体修飾として置換して良い位置かを判定する。

    「事例が多い。」のような述語位置で「多い」→「膨大な」と置換すると
    「事例が膨大な。」になって壊れるため、連体候補はここで弾く。
    """
    if end >= len(text):
        return False
    return bool(_NOUN_HEAD.match(text[end]))


def _amplify_line(
    line: str,
    channel_upgrades: List[Tuple[str, List[str], str]],
    universal_upgrades: List[Tuple[str, List[str], str]],
    max_replacements: int = 1,
) -> Tuple[str, List[str]]:
    """1行に対してパワーワード変換を適用。

    【2026-08-31】置換前に (a) 連体候補は連体位置かを検証し、(b) 置換後の文字列に
    文法破綻パターンが出たら差し戻す、という二重チェックを追加した。
    これがないと「変」→「闇が深い」が「変わる」に食い込むような破損が本番に流れる。
    """
    changes: List[str] = []
    result = line
    replacements_done = 0

    # チャンネル固有の変換を先に試行
    all_upgrades = list(channel_upgrades) + list(universal_upgrades)

    for entry in all_upgrades:
        if replacements_done >= max_replacements:
            break

        # 旧形式の2要素タプルにも後方互換で対応
        if len(entry) == 3:
            pattern, replacements, mode = entry
        else:
            pattern, replacements = entry  # type: ignore[misc]
            mode = "free"

        match = re.search(pattern, result)
        if not match:
            continue

        # 連体候補は「直後が名詞」でなければ適用しない
        if mode == "attributive" and not _is_attributive_position(result, match.end()):
            continue

        old_word = match.group(0)
        new_word = random.choice(replacements)
        # 同じ言葉への置換を避ける
        if new_word == old_word or new_word in result:
            continue

        candidate = result[: match.start()] + new_word + result[match.end():]

        # 保険1: 置換語の直後が活用語尾＝元の語は用言の語幹だった → 差し戻す
        if _breaks_conjugation(candidate, match.start() + len(new_word)):
            continue

        # 保険2: 置換によって連体形の終止という破綻が新たに生じたら採用しない
        if len(_BROKEN_AFTER_REPLACE.findall(candidate)) > len(
            _BROKEN_AFTER_REPLACE.findall(result)
        ):
            continue

        result = candidate
        changes.append(f"「{old_word}」→「{new_word}」")
        replacements_done += 1

    return result, changes


# =====================================================================
# メインエントリポイント
# =====================================================================

def amplify_power_words(
    short_scenario: List[Dict[str, Any]],
    *,
    channel_id: str = "",
    max_amplifications: int = 3,
) -> Dict[str, Any]:
    """シナリオ内の弱い表現をパワーワードにアップグレードする。

    Args:
        short_scenario: シナリオ行リスト（in-place で変更される）。
        channel_id: チャンネルID。
        max_amplifications: 最大変換数（過剰にならないよう制限）。

    Returns:
        {
            "amplified": int,        # 変換した箇所数
            "changes": [...],        # 変換の詳細
            "lines_modified": int,   # 変更した行数
        }
    """
    if not short_scenario:
        return {"amplified": 0, "changes": [], "lines_modified": 0}

    channel_upgrades = _CHANNEL_UPGRADES.get(channel_id, [])
    all_changes: List[str] = []
    lines_modified = 0
    total_amplifications = 0

    # 【2026-08-31 追加】字数の増加量に上限を設ける。
    # 置換候補は元の語より長い（例: 「妖怪」→「出会ったら終わりの妖怪」で +9字）ため、
    # 3箇所置換すると1本で +27字 になる。台本の字数は維持率に直結し
    # （実測 n=214、維持率 = 92.6 - 0.1720×字数）、この増分だけで維持率 -4.6pt に相当する。
    # 強調の効果と尺のコストが釣り合う範囲として +20字 を上限にする。
    max_added_chars = 20
    added_chars = 0

    for entry in short_scenario:
        if total_amplifications >= max_amplifications or added_chars >= max_added_chars:
            break

        text_key = "text" if "text" in entry else "line"
        text = entry.get(text_key, "")
        if not text or not _should_amplify(text):
            continue

        # パワーワード変換
        new_text, changes = _amplify_line(
            text,
            channel_upgrades,
            _UNIVERSAL_UPGRADES,
            max_replacements=1,
        )

        if changes:
            delta = len(new_text) - len(text)
            # 1置換で字数上限を超えるなら、この置換は見送る
            if added_chars + delta > max_added_chars:
                continue
            entry[text_key] = new_text
            added_chars += delta
            all_changes.extend(changes)
            lines_modified += 1
            total_amplifications += len(changes)

    # ログ
    if all_changes:
        print(
            f"  💪 PowerWord [{channel_id}]: "
            f"{total_amplifications}箇所を強化"
        )
        for change in all_changes[:3]:
            print(f"     ⚡ {change}")
    else:
        print(
            f"  ➡️ PowerWord [{channel_id}]: "
            "既にパワフルな表現 — 変更なし"
        )

    return {
        "amplified": total_amplifications,
        "changes": all_changes,
        "lines_modified": lines_modified,
    }
