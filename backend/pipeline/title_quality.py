"""タイトルの CTR 品質スコアリング — 検索・ブラウズ面でのクリック率を上げる最終ゲート。

背景:
    タイトルの書き方はプロンプト（`generator._title_rule_block`）で指示しているが、
    LLM は指示を落とすことがある。実際に投稿済みタイトルを見ると
    「〇〇について解説」「〇〇とは」のような説明型や、数字・感情ワードが
    ゼロの平板なタイトルが一定割合で混ざっている。プロンプトは"お願い"であって
    保証ではないので、生成後に決定論的な採点を通して弱いタイトルを弾く。

    テーマ重複ゲート（`generator._reject_duplicate_title`）と同じ設計で、
    落第したらタイトルだけ作り直す（シナリオ本体は再利用）。

採点の根拠（PDCA の上位動画・一般的な YouTube CTR 研究に共通する要素）:
    加点
      - 具体的な数字（「99%」「3秒」「5つ」）— 情報量が確定して見えるとクリックされる
      - 感情・好奇心ワード（実は / なぜ / 知らない / ヤバい / 閲覧注意 …）
      - 好奇心ギャップ（疑問形・「本当の理由」など答えを伏せる型）
      - 二人称（あなた / 君）— 自分ゴト化
    減点
      - 説明語尾（〜について / 〜とは / 〜を解説 / 〜まとめ）— 最も CTR を殺す型
      - 先頭の【】プレフィックス（ショートのフィードで文字数を食うだけ）
      - 長すぎ / 短すぎ

`score_title` は 0〜100 を返す。`PASS_SCORE` 未満を「作り直し対象」とする。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# このスコア未満のタイトルは作り直しの対象にする。
# 60 = 「数字か感情ワードのどちらか + 好奇心ギャップ」でぎりぎり届く水準。
# これ以上上げると再生成のたびに LLM を叩くコストが跳ねるので、実運用の
# 落第率が 2〜3 割に収まる値として 60 を採用する。
PASS_SCORE = 60

# 「タイトルとして自然に読める」文字数帯。ショートは投稿時に末尾ハッシュタグと
# シリーズ名が付くので、ここでは本体だけを見る。
IDEAL_MIN = 18
IDEAL_MAX = 48
HARD_MAX = 70


# ---------------------------------------------------------------------
# 語彙テーブル
# ---------------------------------------------------------------------

# 感情・好奇心を動かす語。`_title_rule_block` がプロンプトで要求している語を
# 実際に採点でも見る（プロンプトと採点の基準がズレないよう同じ語彙に揃える）。
POWER_WORDS: List[str] = [
    "実は", "なぜ", "なんで", "どうして", "本当は", "本当の理由", "正体", "真実",
    "知らない", "知らなすぎ", "勘違い", "誤解", "やめて", "危険", "閲覧注意",
    "ヤバい", "やばい", "衝撃", "驚愕", "とんでもない", "恐ろしい", "怖い",
    "全員", "9割", "99%", "ほとんどの人", "損", "禁止", "裏側", "裏設定",
    "だけ", "しかない", "たった", "まさかの", "異常", "非常識", "禁断",
]

# 説明型の語尾・言い回し。CTR を最も落とすので減点する。
EXPLAINER_PATTERNS: List[str] = [
    "について", "とは何", "を解説", "の解説", "を紹介", "の紹介",
    "まとめてみた", "を説明", "の説明", "を調べてみた",
]

# 好奇心ギャップ（答えを伏せている）を示すサイン。
CURIOSITY_PATTERNS: List[str] = [
    "?", "？", "なぜ", "なんで", "どうして", "理由",
    "正体", "真実", "秘密", "裏", "実は", "だった", "結果",
]

# 「発言引用 → 結果」型（2ch まとめ・企業ファクト系の勝ちパターン）。
# 疑問形ではないが「→ の先が気になる」ので好奇心ギャップとして同格に扱う。
# これを見ないと、チャンネルの勝ち書式そのものが低スコアで作り直しにされる。
_QUOTE_RESULT = re.compile(r"[「『].+[」』].*[→⇒]|[→⇒].*[「『].+[」』]")

# 「A と B、どっちが勝つ?」型（pokemon-lab の勝ちパターン）。
# 二者を並べて勝敗を伏せる形は、疑問形と同じだけの好奇心ギャップを作る。
# 数字が入りにくい書式なので、format シグナルとして別枠で加点する。
_MATCHUP = re.compile(
    r"どっち|どちら|勝つ|勝てる|強いのは|[ぁ-んァ-ヶ一-龠A-Za-z]{2,}\s*(?:vs|VS|ＶＳ|対)\s*[ぁ-んァ-ヶ一-龠A-Za-z]{2,}"
)

SECOND_PERSON: List[str] = ["あなた", "君", "きみ", "お前", "あなたの", "日本人", "人類"]

# 全角数字・漢数字も「数字」として扱う。「一般」「一部」のような
# 数量でない漢数字を拾わないよう、助数詞・単位が続くものだけを数字とみなす。
_ARABIC_NUM = re.compile(r"[0-9０-９]")
_KANJI_COUNT = re.compile(
    r"[一二三四五六七八九十百千万]+(?=[つ個人年秒分時日回本種類％%割倍段階選])"
)

_BRACKET_PREFIX = re.compile(r"^[【\[［]")


def has_number(title: str) -> bool:
    """具体的な数字（アラビア数字 or 助数詞付きの漢数字）を含むか。"""
    t = title or ""
    return bool(_ARABIC_NUM.search(t) or _KANJI_COUNT.search(t))


def _hit_any(title: str, needles: List[str]) -> List[str]:
    t = title or ""
    return [n for n in needles if n in t]


def score_title(
    title: str,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """タイトルを 0〜100 で採点し、内訳と改善指示を返す。

    Returns:
        {
          "score": int,               # 0..100
          "passed": bool,             # score >= PASS_SCORE
          "signals": {...},           # 各シグナルの検出結果
          "reasons": [str, ...],      # 減点・加点の理由（ログ用）
          "advice": [str, ...],       # 再生成プロンプトに渡す改善指示
        }
    """
    t = (title or "").strip()
    reasons: List[str] = []
    advice: List[str] = []

    if not t:
        return {
            "score": 0,
            "passed": False,
            "signals": {},
            "reasons": ["タイトルが空"],
            "advice": ["タイトルを生成すること"],
        }

    # チャンネル JSON で語彙を追加できる（例: SCP なら「収容違反」を強語として扱う）
    extra_power: List[str] = []
    if channel_dict:
        tp = (channel_dict.get("theme_priority") or {})
        raw_extra = tp.get("title_power_words")
        if isinstance(raw_extra, list):
            extra_power = [str(w) for w in raw_extra if str(w).strip()]

    power_hits = _hit_any(t, POWER_WORDS + extra_power)
    curiosity_hits = _hit_any(t, CURIOSITY_PATTERNS)
    if _QUOTE_RESULT.search(t):
        curiosity_hits.append("引用→結果型")
    # 対決型は数字が入りにくいので、format 自体を強いシグナルとして power 側で見る。
    if _MATCHUP.search(t):
        power_hits.append("対決型")
    person_hits = _hit_any(t, SECOND_PERSON)
    explainer_hits = _hit_any(t, EXPLAINER_PATTERNS)
    numeric = has_number(t)
    length = len(t)

    score = 40  # ベース（何のシグナルも無い平板なタイトル）

    # ── 加点 ──
    if numeric:
        score += 18
        reasons.append("数字あり(+18)")
    else:
        advice.append(
            "「99%」「3秒」「5つ」のような具体的な数字を1つ入れる"
            "（体感できる小さい数字ほど強い）"
        )

    if power_hits:
        # 語を積むほど強いわけではないので 2 個で頭打ちにする
        gain = 12 if len(power_hits) == 1 else 20
        score += gain
        reasons.append(f"感情ワード{power_hits[:3]}(+{gain})")
    else:
        advice.append(
            "「実は」「なぜ」「本当は」「知らない」「やめて」のような"
            "感情を動かす語を必ず1つ入れる"
        )

    if curiosity_hits:
        score += 12
        reasons.append(f"好奇心ギャップ{curiosity_hits[:2]}(+12)")
    else:
        advice.append("答えを伏せた疑問型（「なぜ〇〇なのか」「〇〇の本当の理由」）にする")

    if person_hits:
        score += 6
        reasons.append(f"二人称{person_hits[:1]}(+6)")

    # ── 減点 ──
    if explainer_hits:
        score -= 30
        reasons.append(f"説明語尾{explainer_hits}(-30)")
        advice.append(
            f"説明型の言い回し（{' / '.join(explainer_hits)}）を消す。"
            "タイトルは『説明』ではなく『衝動』を作る"
        )

    if _BRACKET_PREFIX.search(t):
        score -= 10
        reasons.append("先頭の【】プレフィックス(-10)")
        advice.append("先頭のカギ括弧プレフィックス（【ゆっくり解説】等）を外す")

    if length < IDEAL_MIN:
        score -= 12
        reasons.append(f"短すぎ({length}字 < {IDEAL_MIN})(-12)")
        advice.append(f"{IDEAL_MIN}〜{IDEAL_MAX}字まで具体を足して情報量を上げる")
    elif length > HARD_MAX:
        score -= 15
        reasons.append(f"長すぎ({length}字 > {HARD_MAX})(-15)")
        advice.append(f"{IDEAL_MAX}字前後まで削る（フィードで途中省略される）")
    elif length > IDEAL_MAX:
        score -= 5
        reasons.append(f"やや長い({length}字)(-5)")

    score = max(0, min(100, score))

    return {
        "score": score,
        "passed": score >= PASS_SCORE,
        "signals": {
            "has_number": numeric,
            "power_words": power_hits,
            "curiosity": curiosity_hits,
            "second_person": person_hits,
            "explainer": explainer_hits,
            "length": length,
        },
        "reasons": reasons,
        "advice": advice,
    }


def best_of(
    candidates: List[str],
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """候補タイトルの中から最高スコアのものを選ぶ。

    Returns:
        {"title": str, "score": int, "detail": {...}}。候補が空なら title="".
    """
    best: Optional[Dict[str, Any]] = None
    for cand in candidates:
        c = (cand or "").strip()
        if not c:
            continue
        detail = score_title(c, channel_dict)
        if best is None or detail["score"] > best["score"]:
            best = {"title": c, "score": detail["score"], "detail": detail}
    return best or {"title": "", "score": 0, "detail": score_title("", channel_dict)}
