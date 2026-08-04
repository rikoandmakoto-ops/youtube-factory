"""長尺動画の「どの秒に台本のどの行が喋られているか」を復元する。

切り抜きを作るには行単位のタイムコードが要るが、video_generator は字幕の
タイミングを保存していない。音声側から取ろうとすると BGM とノイズフロアに
負ける（実測: -45dB では 7分の動画に無音区間が 4 個しか出ない）。

代わりに *映像* を使う。yukkuri レイアウトは画面下部 20% が字幕ボックスで、
そこは行が切り替わった瞬間にだけ変化する。この帯だけを切り出してシーン検出を
かけると、行境界がほぼそのまま出る（実測: 64行の動画で境界 65個）。

検出した境界と台本行数はズレうるので、最後に「行の文字数に比例して尺が決まる」
という前提で DP アライメントを行い、境界のとりこぼし・余分をまとめて吸収する。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# 字幕ボックスの高さ比（video_format.layout.text_box_height_ratio の既定値）
DEFAULT_TEXTBOX_RATIO = 0.20
# これより近い境界は同じ切り替わり（フェード中の複数フレーム）とみなして畳む
BOUNDARY_MERGE_SEC = 0.6
# シーン検出のしきい値。字幕帯は行が変わると大きく変わるので低めで拾える
SCENE_THRESHOLD = 0.03


@dataclass
class LineTiming:
    """台本1行の再生時間帯。"""

    index: int
    speaker: str
    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "speaker": self.speaker,
            "text": self.text,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
        }


def _ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe_bin() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def probe_duration(video_path: Path | str) -> Optional[float]:
    """動画長（秒）。取得できなければ None。"""
    try:
        out = subprocess.run(
            [_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=120,
        ).stdout.strip()
        return float(out) if out else None
    except Exception:
        return None


def detect_line_boundaries(
    video_path: Path | str,
    *,
    textbox_ratio: float = DEFAULT_TEXTBOX_RATIO,
    threshold: float = SCENE_THRESHOLD,
    timeout: int = 900,
) -> List[float]:
    """字幕ボックス帯のシーン変化時刻（秒）を昇順で返す。

    先頭は必ず 0.0 に正規化する（1行目は動画開始から喋り始めている）。
    """
    vf = (
        f"crop=iw:ih*{textbox_ratio}:0:ih*(1-{textbox_ratio}),"
        "scale=240:-2,"
        f"select='gt(scene,{threshold})',showinfo"
    )
    try:
        proc = subprocess.run(
            [_ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(video_path),
             "-vf", vf, "-vsync", "0", "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as e:
        print(f"⚠️ clip_factory: scene detection failed: {e}")
        return []

    times = sorted(float(x) for x in re.findall(r"pts_time:([\d.]+)", proc.stderr))
    merged: List[float] = []
    for t in times:
        if not merged or t - merged[-1] > BOUNDARY_MERGE_SEC:
            merged.append(t)
    if not merged:
        return []
    # 冒頭のフェードインは境界ではないので 0 に寄せる
    if merged[0] < 1.5:
        merged[0] = 0.0
    else:
        merged.insert(0, 0.0)
    return merged


def _weights(lines: Sequence[Dict[str, Any]]) -> List[float]:
    """行の想定尺の重み。TTS 尺は文字数にほぼ比例する（実測 0.135±0.015 秒/字）。"""
    return [max(1.0, float(len(str(l.get("text") or "")))) for l in lines]


def align_lines(
    boundaries: Sequence[float],
    lines: Sequence[Dict[str, Any]],
    total_duration: float,
) -> List[LineTiming]:
    """境界列を台本行に単調割り当てして LineTiming を作る。

    境界から作られる区間を「連続するグループ」に分け、各グループを1行に
    対応させる。グループ尺が文字数比で期待される尺に近くなるように DP で最適化。
    境界が足りない/多い場合も、この最適化がまとめて面倒を見る。
    """
    n = len(lines)
    if n == 0:
        return []
    weights = _weights(lines)
    total_w = sum(weights)

    # 境界から区間を作る（最後の区間は動画末尾まで）
    bs = [b for b in boundaries if 0.0 <= b < total_duration]
    if len(bs) < 2:
        # 検出失敗 → 文字数比で単純按分（精度は落ちるが破綻はしない）
        return _proportional(lines, weights, total_w, 0.0, total_duration)

    edges = list(bs) + [total_duration]
    m = len(edges) - 1
    if m < n:
        # 境界が行数より少ない → 按分にフォールバック
        return _proportional(lines, weights, total_w, edges[0], total_duration)

    expected = [total_duration * w / total_w for w in weights]

    INF = float("inf")
    # dp[i][j] = 行 i..n-1 を 区間 j..m-1 に割り当てたときの最小コスト
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    choice = [[0] * (m + 1) for _ in range(n + 1)]
    dp[n][m] = 0.0
    for i in range(n - 1, -1, -1):
        remaining_lines = n - i
        for j in range(m - 1, -1, -1):
            # 残り区間数が残り行数を下回ったら割り当て不能
            if m - j < remaining_lines:
                continue
            best, best_k = INF, 1
            max_take = m - j - (remaining_lines - 1)
            for k in range(1, max_take + 1):
                nxt = dp[i + 1][j + k]
                if nxt == INF:
                    continue
                span = edges[j + k] - edges[j]
                cost = abs(span - expected[i]) + nxt
                if cost < best:
                    best, best_k = cost, k
            dp[i][j] = best
            choice[i][j] = best_k

    if dp[0][0] == INF:
        return _proportional(lines, weights, total_w, edges[0], total_duration)

    timings: List[LineTiming] = []
    j = 0
    for i in range(n):
        k = choice[i][j]
        start, end = edges[j], edges[j + k]
        timings.append(LineTiming(
            index=i,
            speaker=str(lines[i].get("speaker") or ""),
            text=str(lines[i].get("text") or ""),
            start=start,
            end=end,
        ))
        j += k
    return timings


def _proportional(
    lines: Sequence[Dict[str, Any]],
    weights: Sequence[float],
    total_w: float,
    start_at: float,
    total_duration: float,
) -> List[LineTiming]:
    """文字数比でまるごと按分するフォールバック。"""
    span = max(0.1, total_duration - start_at)
    out: List[LineTiming] = []
    cursor = start_at
    for i, line in enumerate(lines):
        d = span * weights[i] / total_w
        out.append(LineTiming(
            index=i,
            speaker=str(line.get("speaker") or ""),
            text=str(line.get("text") or ""),
            start=cursor,
            end=min(total_duration, cursor + d),
        ))
        cursor += d
    return out


def build_timeline(
    video_path: Path | str,
    lines: Sequence[Dict[str, Any]],
    *,
    textbox_ratio: float = DEFAULT_TEXTBOX_RATIO,
    duration: Optional[float] = None,
) -> List[LineTiming]:
    """動画＋台本行から行タイムラインを構築する（このモジュールの入口）。"""
    total = duration or probe_duration(video_path)
    if not total:
        raise RuntimeError(f"動画長を取得できません: {video_path}")
    boundaries = detect_line_boundaries(video_path, textbox_ratio=textbox_ratio)
    timings = align_lines(boundaries, lines, total)
    print(f"  🧭 alignment: {len(boundaries)} boundaries → {len(timings)} lines "
          f"({'scene' if len(boundaries) >= 2 else 'proportional'})")
    return timings
