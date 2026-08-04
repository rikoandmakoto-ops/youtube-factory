"""長尺のどこを切り抜くかを決める。

スコアは2系統:

  1. 台本スコア — 数字・断定・種明かしの語彙が濃い区間を高く見る。台本 JSON が
     手元にあるので、字幕を起こし直さずに内容で判断できる。
  2. 視聴維持率 — YouTube Analytics の audienceWatchRatio カーブ。実際に
     視聴者が食いついた区間そのものなので、取れるときは台本スコアより信頼できる。

Claude が使えるときは最終ランキングとフック文生成を任せ、使えないときは
ヒューリスティックだけで完結する（API クレジット切れでも止まらないこと優先）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .align import LineTiming

# 「引きの強さ」に効く語彙。競合分析（data/research/clip_shorts_visual_analysis.json）
# で確認した「意外な数字 / 常識の否定 / 一言オチ」に対応させている。
_HOOK_WORDS = {
    "実は": 3.0, "正体": 2.5, "本当は": 2.5, "驚": 2.0, "衝撃": 2.5,
    "判明": 2.0, "証明": 1.5, "理由": 1.5, "だった": 1.2, "なんと": 2.5,
    "危険": 1.8, "致命": 2.0, "禁止": 1.8, "失敗": 1.2, "違う": 1.5,
    "知らない": 2.5, "誤解": 2.0, "逆": 1.5, "できない": 1.5, "ヤバ": 2.0,
}
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|％|倍|人|年|万|億|秒|分|時間|度|回|種|割)")
_QUESTION_RE = re.compile(r"[?？]")

# 導入の挨拶・エンディングのCTAは切り抜かない（channel JSON の avoid_categories と対応）
_EXCLUDE_RE = re.compile(
    r"(チャンネル登録|高評価|ご視聴|今日のテーマ|それでは|よろしくお願い|次回|コメント欄)"
)


@dataclass
class Segment:
    """切り抜き候補の1区間。"""

    start: float
    end: float
    line_indices: List[int]
    lines: List[LineTiming]
    score: float
    hook: str = ""
    reason: str = ""
    retention: Optional[float] = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    def text(self) -> str:
        return "".join(l.text for l in self.lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "duration": round(self.duration, 2),
            "score": round(self.score, 3),
            "retention": round(self.retention, 4) if self.retention is not None else None,
            "hook": self.hook,
            "reason": self.reason,
            "line_indices": self.line_indices,
            "lines": [l.to_dict() for l in self.lines],
        }


# ---------------------------------------------------------------------
# スコアリング
# ---------------------------------------------------------------------

def _line_score(text: str) -> float:
    score = 0.0
    for word, w in _HOOK_WORDS.items():
        if word in text:
            score += w
    score += 2.0 * len(_NUMBER_RE.findall(text))
    if _QUESTION_RE.search(text):
        score += 0.8
    if _EXCLUDE_RE.search(text):
        score -= 6.0
    return score


def _retention_at(curve: Sequence[Dict[str, float]], start_ratio: float, end_ratio: float) -> Optional[float]:
    pts = [p for p in curve if start_ratio <= float(p.get("ratio", -1)) <= end_ratio]
    if not pts:
        return None
    vals = [float(p.get("audience_watch_ratio") or 0.0) for p in pts]
    return sum(vals) / len(vals) if vals else None


def fetch_retention_curve(source_channel_id: str, video_id: Optional[str]) -> List[Dict[str, float]]:
    """視聴維持率カーブを取る。取れなければ空リスト（スコアは台本のみになる）。"""
    if not video_id:
        return []
    try:
        from pipeline import youtube_analytics as ya  # type: ignore
        res = ya.fetch_retention(source_channel_id, video_id)
    except Exception as e:
        print(f"  ⚠️ retention 取得失敗（台本スコアのみで続行）: {e}")
        return []
    if not res.get("ok"):
        print(f"  ℹ️ retention なし: {res.get('error')}")
        return []
    curve = res.get("curve") or []
    print(f"  📈 retention curve: {len(curve)} points")
    return curve


# ---------------------------------------------------------------------
# 候補生成
# ---------------------------------------------------------------------

def build_candidates(
    timings: Sequence[LineTiming],
    *,
    total_duration: float,
    min_sec: float,
    max_sec: float,
    exclude_head_sec: float,
    exclude_tail_sec: float,
    retention_curve: Sequence[Dict[str, float]] = (),
    retention_weight: float = 0.5,
    script_weight: float = 0.5,
) -> List[Segment]:
    """連続する行の窓を全部作ってスコアを付ける。"""
    usable = [t for t in timings
              if t.start >= exclude_head_sec and t.end <= total_duration - exclude_tail_sec]
    if not usable:
        usable = list(timings)

    line_scores = {t.index: _line_score(t.text) for t in usable}
    candidates: List[Segment] = []
    for i in range(len(usable)):
        for j in range(i, len(usable)):
            start = usable[i].start
            end = usable[j].end
            dur = end - start
            if dur < min_sec:
                continue
            if dur > max_sec:
                break
            window = usable[i:j + 1]
            raw = sum(line_scores[t.index] for t in window)
            # 尺あたりのスコア。長く取れば有利になるのを避ける
            script = raw / max(1.0, dur / 10.0)
            # 先頭行が強いほど「冒頭2秒で結論」に近い（競合分析の共通パターン）
            script += line_scores[window[0].index] * 0.8

            ret = None
            if retention_curve and total_duration > 0:
                ret = _retention_at(retention_curve, start / total_duration, end / total_duration)

            if ret is not None:
                score = script_weight * script + retention_weight * (ret * 20.0)
            else:
                score = script

            candidates.append(Segment(
                start=start, end=end,
                line_indices=[t.index for t in window],
                lines=list(window),
                score=score,
                retention=ret,
            ))
    candidates.sort(key=lambda s: s.score, reverse=True)
    return candidates


def pick_segments(
    candidates: Sequence[Segment],
    *,
    count: int,
    min_gap_sec: float,
    used_segments: Sequence[Dict[str, Any]] = (),
) -> List[Segment]:
    """スコア順に、既出区間と重ならないものを選ぶ。"""
    chosen: List[Segment] = []
    blocked: List[tuple] = [
        (float(u.get("start", 0)) - min_gap_sec, float(u.get("end", 0)) + min_gap_sec)
        for u in used_segments
    ]
    for cand in candidates:
        if len(chosen) >= count:
            break
        if any(cand.start < b_end and cand.end > b_start for b_start, b_end in blocked):
            continue
        chosen.append(cand)
        blocked.append((cand.start - min_gap_sec, cand.end + min_gap_sec))
    return chosen


# ---------------------------------------------------------------------
# フック文
# ---------------------------------------------------------------------

# フック帯は 13文字 × 3行（renderer.ClipLayout）。読み切れる上限として 32 に置く。
HOOK_CHAR_LIMIT = 32

# 語尾の丁寧表現・終助詞。落として体言止めに寄せるとフック帯で締まる。
# キャラの口調（〜だわ / 〜なのよ / 〜だったの）がそのまま残るとフックが緩むので、
# 記号 → 終助詞 → 説明の「の/ん」→ 丁寧表現 の順に繰り返し剥がす。
_TRAILING_STEPS = [
    re.compile(r"[。．！!？?、，…]+$"),
    re.compile(r"(なのだ|なんだ|んだ|のだ|なの|なん)$"),
    re.compile(r"(よ|ね|わ|さ|ぞ|ぜ|かな|かしら)$"),
    # 動詞・形容詞の終止形＋説明の「の/ん」（『〜続くの』『〜だったの』）
    re.compile(r"(?<=[うくぐすずつづぬふぶぷむゆるたいだきしちにひみりえけせてねへめれん])[のん]$"),
    re.compile(r"(ですね|ですよ|でしょう|でしょ|ますよ|ました|ます|です)$"),
]
# 冒頭の接続詞。フックには不要
_LEADING_RE = re.compile(r"^(でも|しかも|そして|だから|つまり|ところが|ちなみに|さらに|また|ただ|しかし)[、,]?")
# これで終わる断片は文が途中で切れて見える（『〜として』『〜によると』など）。
# 単独の格助詞（で・に・を…）はここに入れない——『月1回まで』の「で」のように
# 語の一部を削ってしまうため、切り詰めた場合だけ _trim_dangling_particle で処理する。
_DANGLING_RE = re.compile(
    r"(として|について|における|によって|によると|により|ために|ながら|つつ|"
    r"して|されて|られて|くて|けど|けれど)$"
)
# 「ので」「から」は接続助詞にも名詞＋助詞にもなる（『飲み込んだもので』『口から』）。
# 直前が用言の活用語尾のときだけ接続助詞とみなして落とす。
_DANGLING_CONJ_RE = re.compile(r"(?<=[うくぐすずつづぬふぶぷむゆるたいだな])(ので|から)$")
# 途中で切った結果として残る助詞。切り詰め時のみ適用する
_CUT_PARTICLE_RE = re.compile(r"[はがをにでとへもやのという、]+$")
# 出典・前置きだけの節。数字を持たないなら捨てる
_ATTRIBUTION_RE = re.compile(r"(研究|実験|調査|報告|論文|大学|チーム)(では|で|によると|によれば|が)?$")


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[。！？!?])", text)
    return [p.strip() for p in parts if p.strip()]


def _clauses(sentence: str) -> List[str]:
    parts = re.split(r"[、，]", sentence)
    return [p.strip() for p in parts if p.strip()]


def _strip_trailing(text: str) -> str:
    t = text
    for _ in range(4):
        before = t
        for pattern in _TRAILING_STEPS:
            if len(t) > 6:
                t = pattern.sub("", t)
        if t == before:
            break
    return t


def _tidy(text: str) -> str:
    t = _LEADING_RE.sub("", text.strip())
    t = _strip_trailing(t)
    # 末尾が接続助詞で終わるなら落とす（最大2回まで）
    for _ in range(2):
        m = _DANGLING_RE.search(t) or _DANGLING_CONJ_RE.search(t)
        if not m or len(t) - len(m.group(0)) < 6:
            break
        t = t[: m.start()]
    return t.strip()


_DATE_ONLY_RE = re.compile(r"^[\d０-９年月日時分秒:：/／\-〜~\s]+$")


def _clause_score(clause: str, *, is_first: bool) -> float:
    score = _line_score(clause)
    # 日付だけの節（『1998年3月12日』）は数字が多くても引きにならない
    if _DATE_ONLY_RE.match(clause):
        return score - 8.0
    # 数字はフックの主役。_line_score より重く見る
    score += 3.0 * len(_NUMBER_RE.findall(clause))
    if _ATTRIBUTION_RE.search(clause) and not _NUMBER_RE.search(clause):
        score -= 5.0
    # 「2011年の◯◯大学の研究では、」のような前置き節より後続の結論節を優先
    if is_first:
        score -= 1.5
    length = len(clause)
    if length < 6:
        score -= 3.0
    elif length > HOOK_CHAR_LIMIT + 8:
        score -= 2.0
    return score


def heuristic_hook(segment: Segment, limit: int = HOOK_CHAR_LIMIT) -> str:
    """Claude なしでフック文を作る。

    文ではなく *節* を単位にする。解説台本の「2011年の◯◯大学の研究では、家族間の
    あくび伝染率は約50%だった」のような文は、前半が出典・後半が結論という形が多く、
    文ごと詰めると必ず前半で文字数を使い切って『〜研究で』のような尻切れになる。
    結論側の節を選べば、そのままフックとして成立する。
    """
    # 収まる節（fitting）と、切り詰めが要る節（overflow）を分けて集める。
    # 日本語を文字数で切ると『〜に達す』『異常存』のように語の途中で切れるので、
    # 収まる節が1つでもあればそちらを必ず優先する。
    fitting: List[tuple] = []
    overflow: List[tuple] = []
    for line in segment.lines:
        head_bonus = 1.0 if line.index == segment.line_indices[0] else 0.0
        for sent in _sentences(line.text):
            clauses = _clauses(sent)
            for i, clause in enumerate(clauses):
                tidy = _tidy(clause)
                if not tidy:
                    continue
                score = _clause_score(tidy, is_first=(i == 0)) + head_bonus
                # 短すぎる結論節は次の節と繋いで意味を通す
                if len(tidy) < 12 and i + 1 < len(clauses):
                    merged = _tidy(clause + "、" + clauses[i + 1])
                    if len(merged) <= limit:
                        tidy, score = merged, score + 1.0
                if len(tidy) <= limit:
                    fitting.append((score, tidy))
                else:
                    trimmed = _CUT_PARTICLE_RE.sub("", _tidy(tidy[:limit]))
                    if len(trimmed) >= limit * 0.6:
                        overflow.append((score - 2.0, trimmed))

    pool = fitting or overflow
    if pool:
        return max(pool, key=lambda x: x[0])[1]
    if segment.lines:
        return _tidy(segment.lines[0].text)[:limit]
    return ""


def refine_with_claude(
    segments: Sequence[Segment],
    *,
    source_title: str,
    channel_id: str,
) -> bool:
    """Claude が使えるならフック文と採用順を上書きする。使えなければ False。"""
    if not segments:
        return False
    try:
        from pipeline import claude_client  # type: ignore
        if not claude_client.has_api_key():
            return False
    except Exception:
        return False

    payload = [
        {
            "id": i,
            "start": round(s.start, 1),
            "duration": round(s.duration, 1),
            "text": s.text()[:600],
        }
        for i, s in enumerate(segments)
    ]
    user = (
        f"長尺解説動画『{source_title}』から切り抜きショートを作ります。\n"
        "以下は候補区間です。各区間について、YouTube ショートとして成立するかを判定し、"
        "画面最上部に常時表示する『フック文』を作ってください。\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "フック文の条件:\n"
        "- 全角28文字以内。2行に割って読める長さ。\n"
        "- 区間の『結論・意外な事実』を言い切る。疑問形にしない。\n"
        "- 元動画のタイトルをそのまま使わない。\n"
        "- 台本にない主張を足さない。\n\n"
        "次の JSON のみを返す:\n"
        '{"ranked": [{"id": 0, "hook": "", "reason": "", "usable": true}]}'
    )
    res = claude_client.call_claude_json(
        system="あなたは切り抜きチャンネルの編集者。区間の引きの強さを見極めてフック文を書く。",
        user=user,
        temperature=0.5,
        max_tokens=1500,
        channel_id=channel_id,
        purpose="clip_segment_hook",
    )
    ranked = (res or {}).get("ranked") or []
    if not ranked:
        return False
    order: List[Segment] = []
    for item in ranked:
        try:
            seg = segments[int(item.get("id"))]
        except Exception:
            continue
        if item.get("usable") is False:
            continue
        hook = str(item.get("hook") or "").strip()
        if hook:
            seg.hook = hook[:32]
        seg.reason = str(item.get("reason") or "")
        order.append(seg)
    if not order:
        return False
    # Claude の順序を score に反映して呼び出し側の並びを揃える
    for rank, seg in enumerate(order):
        seg.score += (len(order) - rank) * 100.0
    return True


def finalize_hooks(segments: Sequence[Segment]) -> None:
    """フック文が空の区間をヒューリスティックで埋める。"""
    for seg in segments:
        if not seg.hook:
            seg.hook = heuristic_hook(seg)
