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
_UNIVERSAL_UPGRADES: List[Tuple[str, List[str]]] = [
    # (元の表現パターン, [強化候補リスト])
    (r"すごい", ["ヤバすぎる", "えぐい", "とんでもない"]),
    (r"大きい", ["桁違いの", "規格外の", "モンスター級の"]),
    (r"小さい", ["極小の", "ミクロの", "信じられないほど小さい"]),
    (r"多い", ["膨大な", "異常な数の", "想像を絶する量の"]),
    (r"少ない", ["たった", "わずか", "驚くほど少ない"]),
    (r"変", ["異常", "ヤバい", "闇が深い"]),
    (r"面白い", ["ヤバすぎて草", "狂ってる", "天才すぎる"]),
    (r"危ない", ["致命的に危険", "命に関わる", "ガチでヤバい"]),
    (r"古い", ["太古の", "歴史を変えた", "伝説の"]),
    (r"強い", ["最強の", "化け物級の", "規格外の"]),
    (r"高い", ["ぶっ飛んだ", "天文学的な", "ありえない"]),
    (r"有名", ["伝説", "誰もが知る", "世界が震えた"]),
    (r"普通", ["一見普通だが…", "普通に見えるが実は"]),
    (r"びっくり", ["衝撃", "度肝を抜かれ", "言葉を失"]),
    (r"怖い", ["ガチで恐ろしい", "背筋が凍る", "夜眠れなくなる"]),
    (r"不思議", ["科学では説明できない", "謎すぎる", "人類未解明の"]),
]

# =====================================================================
# チャンネル別パワーワード辞書
# =====================================================================

_CHANNEL_UPGRADES: Dict[str, List[Tuple[str, List[str]]]] = {
    "daily-science": [
        (r"研究", ["衝撃の研究", "ノーベル賞級の研究"]),
        (r"発見", ["世紀の大発見", "人類史を変える発見"]),
        (r"実験", ["狂気の実験", "禁断の実験"]),
        (r"宇宙", ["宇宙の果て", "人類が到達できない宇宙の深淵"]),
    ],
    "scp-lab": [
        (r"危険", ["XKクラスシナリオ", "世界が終わる"]),
        (r"異常", ["認識災害レベル", "財団すら手を焼く"]),
        (r"実験", ["倫理違反の実験", "Dクラス被験者による実験"]),
        (r"怪物", ["収容不可能な存在", "人類の天敵"]),
    ],
    "2ch-matome": [
        # エロ面白系優先
        (r"女", ["美女", "爆乳の女", "とんでもない女"]),
        (r"彼女", ["ドスケベ彼女", "ヤバすぎる彼女"]),
        (r"体験", ["夜の体験", "禁断の体験", "人に言えない体験"]),
        (r"友達", ["ヤバい友達", "クレイジーな友達"]),
        (r"先生", ["とんでもない先生", "伝説の先生"]),
        (r"上司", ["クソ上司", "サイコパス上司"]),
        (r"話", ["ドン引きする話", "人に言えない話", "放送禁止レベルの話"]),
        (r"事件", ["放送事故レベルの事件", "伝説の事件"]),
        (r"失敗", ["大事故", "人生終了レベルの失敗"]),
        (r"バレ", ["全バレ", "修羅場", "地獄絵図"]),
    ],
    "company-facts": [
        (r"利益", ["ぶっ壊れ利益", "異次元の利益"]),
        (r"倒産", ["一夜にして消滅", "地獄の倒産劇"]),
        (r"社長", ["独裁社長", "伝説の社長", "狂気の社長"]),
        (r"ブラック", ["ガチのブラック", "人権無視の"]),
        (r"年収", ["ぶっ飛んだ年収", "信じられない年収"]),
    ],
    "pokemon-lab": [
        (r"ポケモン", ["伝説のポケモン", "ヤバすぎるポケモン"]),
        (r"設定", ["闇設定", "子供に見せられない設定"]),
        (r"進化", ["禁断の進化", "ヤバすぎる進化"]),
        (r"図鑑", ["トラウマ図鑑", "闇すぎる図鑑"]),
    ],
    "yokai-watch": [
        (r"妖怪", ["最恐の妖怪", "出会ったら終わりの妖怪"]),
        (r"伝説", ["語られない伝説", "封印された伝説"]),
        (r"村", ["絶対に行ってはいけない村", "呪われた村"]),
        (r"怪談", ["実話怪談", "ガチの怪談"]),
    ],
    "akashic-librarian": [
        (r"記録", ["封印された記録", "人類が触れてはいけない記録"]),
        (r"真実", ["隠された真実", "歴史が書き換わる真実"]),
        (r"歴史", ["消された歴史", "教科書に載らない歴史"]),
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


def _amplify_line(
    line: str,
    channel_upgrades: List[Tuple[str, List[str]]],
    universal_upgrades: List[Tuple[str, List[str]]],
    max_replacements: int = 1,
) -> Tuple[str, List[str]]:
    """1行に対してパワーワード変換を適用。"""
    changes: List[str] = []
    result = line
    replacements_done = 0

    # チャンネル固有の変換を先に試行
    all_upgrades = channel_upgrades + universal_upgrades

    for pattern, replacements in all_upgrades:
        if replacements_done >= max_replacements:
            break

        match = re.search(pattern, result)
        if match:
            old_word = match.group(0)
            new_word = random.choice(replacements)
            # 同じ言葉への置換を避ける
            if new_word != old_word and new_word not in result:
                result = result.replace(old_word, new_word, 1)
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

    for entry in short_scenario:
        if total_amplifications >= max_amplifications:
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
            entry[text_key] = new_text
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
