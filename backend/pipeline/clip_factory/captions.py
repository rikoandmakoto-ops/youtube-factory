"""外部動画の「どの秒に何を喋っているか」を YouTube 字幕から復元する。

自社動画は台本 JSON があるので `align.py` が映像のシーン検出で行タイムラインを
復元していた。外部動画には台本が無いので、代わりに **YouTube の字幕**を使う。
自動生成字幕でも語単位のタイムコードが付いてくるので、シーン検出より精度が高く、
ffmpeg も動かさないので速い（3時間の配信でも数秒）。

════════════════════════════════════════════════════════════════════
■ YouTube 自動字幕 VTT の癖
════════════════════════════════════════════════════════════════════

自動生成字幕は「1行ずつ下から積み上がる」表示を再現するため、同じ文が
何度も繰り返し出てくる。素朴に cue を読むと 3〜4 倍に重複する::

    00:00:03.590 --> 00:00:03.600
    えっと、おむろにクラッシュロワイヤルの      ← 確定した行

    00:00:03.600 --> 00:00:08.589
    えっと、おむろにクラッシュロワイヤルの      ← 前の行の再掲（重複）
    実況<00:00:04.080><c>的</c><00:00:04.359><c>な</c>...  ← 新しく喋っている行

重複を捨てるだけだと今度はタイムコードの粒度が cue 単位（数秒）になる。
そこで **インラインの `<00:00:04.080><c>語</c>` を読む**。これは語ごとの
発話開始時刻そのものなので、ここから語ストリームを組み立てれば
重複問題もタイムコード精度も同時に片付く。

手動字幕（`subtitles`）にはインラインタイムコードが無いので、その場合は
cue をそのまま1行として扱う（重複も起きない）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .align import LineTiming

#: `<00:00:04.080>` 形式のインラインタイムコード
_INLINE_TS_RE = re.compile(r"<(\d{2}):(\d{2}):(\d{2})\.(\d{3})>")
#: `<c>` `</c>` `<c.colorE5E5E5>` などのタグ
_TAG_RE = re.compile(r"</?c[^>]*>|</?[a-zA-Z][^>]*>")
#: cue のヘッダ行 `00:00:03.590 --> 00:00:08.589 align:start position:0%`
_CUE_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)

#: 1行の目安。renderer の字幕帯は2行なので、長すぎると読めない
DEFAULT_LINE_CHARS = 26
#: これ以上空いたら別の行として切る（間があいた＝話の区切り）
DEFAULT_GAP_SEC = 1.2
#: 行の最低尺。これ未満の行は前後に吸収させる
MIN_LINE_SEC = 0.4

#: 自動字幕に混じるノイズ。行として起こす価値がない
_NOISE_RE = re.compile(r"^[\s　]*(\[音楽\]|\[拍手\]|\[笑\]|＿+|-+)?[\s　]*$")


def _sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


# ---------------------------------------------------------------------
# 語ストリーム
# ---------------------------------------------------------------------

def _parse_cues(text: str) -> List[Tuple[float, float, str]]:
    """VTT を (start, end, raw_payload) の列にする。"""
    cues: List[Tuple[float, float, str]] = []
    start = end = 0.0
    buf: List[str] = []
    has_cue = False
    for line in text.splitlines():
        m = _CUE_RE.match(line.strip())
        if m:
            if has_cue:
                cues.append((start, end, "\n".join(buf)))
            start = _sec(*m.groups()[0:4])
            end = _sec(*m.groups()[4:8])
            buf = []
            has_cue = True
            continue
        if has_cue:
            buf.append(line)
    if has_cue:
        cues.append((start, end, "\n".join(buf)))
    return cues


def _words_from_cue(start: float, end: float, payload: str) -> List[Tuple[float, str]]:
    """cue から (時刻, 語) を取り出す。

    インラインタイムコードのある行だけを見る。自動字幕では「新しく喋っている行」
    にだけタイムコードが付くので、これを拾えば再掲行は自然に落ちる。
    """
    out: List[Tuple[float, str]] = []
    for line in payload.splitlines():
        if not _INLINE_TS_RE.search(line):
            continue
        # 先頭のタイムコード前にある部分は cue の開始時刻に属する
        pos = 0
        cursor = start
        for m in _INLINE_TS_RE.finditer(line):
            chunk = _TAG_RE.sub("", line[pos:m.start()]).strip()
            if chunk:
                out.append((cursor, chunk))
            cursor = _sec(*m.groups())
            pos = m.end()
        tail = _TAG_RE.sub("", line[pos:]).strip()
        if tail:
            out.append((cursor, tail))
    return out


def _plain_cues(cues: Sequence[Tuple[float, float, str]]) -> List[Tuple[float, float, str]]:
    """インラインタイムコードが無い字幕（手動字幕）用。重複行だけ落とす。"""
    out: List[Tuple[float, float, str]] = []
    for start, end, payload in cues:
        text = _TAG_RE.sub("", payload).replace("\n", "").strip()
        if not text or _NOISE_RE.match(text):
            continue
        if out and out[-1][2] == text:
            # 同じ文が続く＝表示継続。終了時刻だけ伸ばす
            out[-1] = (out[-1][0], end, text)
            continue
        out.append((start, end, text))
    return out


# ---------------------------------------------------------------------
# 行の組み立て
# ---------------------------------------------------------------------

_BREAK_CHARS = "。！？!?"
_SOFT_BREAK_CHARS = "、，"


def _group_words(
    words: Sequence[Tuple[float, str]],
    *,
    total_duration: float,
    line_chars: int,
    gap_sec: float,
) -> List[Tuple[float, float, str]]:
    """語ストリームを読める長さの行にまとめる。

    句点で必ず切り、読点は文字数が足りていれば切る。無音が続いたら話の
    切れ目とみなして切る（配信は間が多いので、これが無いと1行が伸びる）。
    """
    lines: List[Tuple[float, float, str]] = []
    cur: List[str] = []
    cur_start: Optional[float] = None
    prev_time: Optional[float] = None
    prev_word = ""

    def flush(end: float) -> None:
        nonlocal cur, cur_start
        text = "".join(cur).strip()
        if text and cur_start is not None and not _NOISE_RE.match(text):
            lines.append((cur_start, max(end, cur_start + MIN_LINE_SEC), text))
        cur = []
        cur_start = None

    def tail_end(next_time: float) -> float:
        """行の終了時刻。最後の語の想定尺までに抑える。

        次の語の時刻をそのまま終わりにすると、配信の「間」がまるごと行の尺に
        入って 40 秒の1行ができる。区間選定はこの尺を信用して窓を作るので、
        沈黙を含んだまま切り抜くと冒頭2秒が無音になる。
        """
        if prev_time is None:
            return next_time
        est = prev_time + max(MIN_LINE_SEC, len(prev_word) * 0.20)
        return min(next_time, est) if next_time > prev_time else est

    for i, (t, word) in enumerate(words):
        if cur_start is not None and prev_time is not None and t - prev_time > gap_sec:
            flush(tail_end(t))
        if cur_start is None:
            cur_start = t
        cur.append(word)
        prev_time = t
        prev_word = word

        joined = "".join(cur)
        nxt = words[i + 1][0] if i + 1 < len(words) else total_duration
        if joined and joined[-1] in _BREAK_CHARS:
            flush(tail_end(nxt))
        elif len(joined) >= line_chars and joined[-1] in _SOFT_BREAK_CHARS:
            flush(tail_end(nxt))
        elif len(joined) >= line_chars * 1.6:
            # 句読点が来ないまま伸び続けるケース（自動字幕では珍しくない）
            flush(tail_end(nxt))

    flush(tail_end(total_duration))
    return lines


def _to_timings(rows: Sequence[Tuple[float, float, str]],
                *, speaker: str) -> List[LineTiming]:
    """(start, end, text) を LineTiming にする。

    次行の開始を超えないように詰めるだけ（伸ばさない）。伸ばすと沈黙が
    行の尺に入り、字幕が喋り終わったあとも残る。
    """
    out: List[LineTiming] = []
    for i, (start, end, text) in enumerate(rows):
        limit = rows[i + 1][0] if i + 1 < len(rows) else end
        out.append(LineTiming(
            index=i, speaker=speaker, text=text,
            start=start, end=max(start + MIN_LINE_SEC, min(end, max(limit, start))),
        ))
    return out


def parse_vtt(
    vtt_text: str,
    *,
    total_duration: float,
    speaker: str = "",
    line_chars: int = DEFAULT_LINE_CHARS,
    gap_sec: float = DEFAULT_GAP_SEC,
) -> List[LineTiming]:
    """VTT 文字列から行タイムラインを作る（このモジュールの入口）。"""
    cues = _parse_cues(vtt_text)
    if not cues:
        return []

    words: List[Tuple[float, str]] = []
    for start, end, payload in cues:
        words.extend(_words_from_cue(start, end, payload))

    if words:
        rows = _group_words(words, total_duration=total_duration,
                            line_chars=line_chars, gap_sec=gap_sec)
    else:
        # 手動字幕（インラインタイムコードなし）
        rows = _plain_cues(cues)

    return _to_timings(rows, speaker=speaker)


def parse_vtt_file(path: Path | str, **kwargs: Any) -> List[LineTiming]:
    return parse_vtt(Path(path).read_text(encoding="utf-8"), **kwargs)


def timings_to_scenario_lines(timings: Sequence[LineTiming]) -> List[Dict[str, Any]]:
    """SourceVideo.scenario['full_scenario'] と同じ形に落とす。

    既存の区間選定（segments.py）は台本行の辞書列を前提にしているので、
    外部素材でも同じ形を渡せるようにしておく。
    """
    return [{"speaker": t.speaker, "text": t.text} for t in timings]
