"""切り抜き区間の「映像の中身」を見て、公開してはいけない区間を落とす。

字幕（発話）だけで区間を選ぶと、**発話は面白いのに映像が静止画** という区間を
掴むことがある。実測 2026-08-24: ひろゆき配信『左ききのエレン』回の 9558s〜9588s は
発話としては最高スコアだったが、映像は 30 秒間ずっと **原作マンガのページを
画面共有している** コマだった。

これは 2 つの意味で公開できない:

  1. 権利。allowlist の許諾は「その配信者の配信」に対するもので、配信内で
     映している第三者の著作物（マンガ・映画・スライド）には及ばない。
     切り抜き先が丸ごと他人の作品になると、許諾の範囲外を公開することになる。
  2. 質。ショートで 30 秒間 1 枚絵が動かないのは離脱の直行便。

判定は ffmpeg だけで完結させる（OpenCV も顔検出も要らない）。64x36 のグレー
スケールに落として毎秒 2 フレーム抜き、隣り合うフレームの平均絶対差を見る。
トーキングヘッドは黙っていても常に微動するので差分が立つが、画面共有の
静止画はゼロに張り付く。

実測値（同じ配信・同じ画質設定の 9 区間）:

    区間                       中央値   静止率(<1.0)   判定
    naVkgtFmRvg_3821_3858       7.13      0.00        OK（本人が喋っている）
    _o8W_QKNHEo_6651_6697       2.30      0.23        OK（引きの画・動きが少ない回）
    naVkgtFmRvg_9554_9591       0.02      1.00        NG（マンガの画面共有）

良判定の最悪値（静止率 0.23）と悪判定（1.00）の間が広いので、閾値は
真ん中よりだいぶ悪側に置いてある。誤って良い区間を落とす方が、他人の
著作物を無人で公開するより安い、という優先順位ではない点に注意。ここは
「明らかな静止画だけを落とす」ゲートで、微妙なものは通す。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

#: サンプリング解像度。小さいほど速く、圧縮ノイズにも強い
SAMPLE_W = 64
SAMPLE_H = 36

#: 毎秒何フレーム抜くか
SAMPLE_FPS = 2.0

#: この値未満のフレーム間差分を「静止」とみなす（0〜255 スケール）
STATIC_DIFF_THRESHOLD = 1.0

#: 静止フレームがこの割合を超えたら不採用
MAX_STATIC_RATIO = 0.70

#: 差分の中央値がこれを下回ったら不採用（全編べったり静止のケース）
MIN_MEDIAN_DIFF = 0.5


@dataclass
class VisualVerdict:
    ok: bool
    reason: str
    median_diff: float
    static_ratio: float
    sampled_frames: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "median_diff": round(self.median_diff, 3),
            "static_ratio": round(self.static_ratio, 3),
            "sampled_frames": self.sampled_frames,
        }


def _sample_gray(path: Path, *, start: float, duration: float) -> Optional["Any"]:
    """区間を 64x36 グレースケールで抜いて (n, H, W) の配列にする。"""
    try:
        import numpy as np
    except Exception:
        return None

    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", f"{max(0.0, start):.3f}",
        "-t", f"{max(0.1, duration):.3f}",
        "-i", str(path),
        "-vf", f"fps={SAMPLE_FPS},scale={SAMPLE_W}:{SAMPLE_H}",
        "-pix_fmt", "gray", "-f", "rawvideo", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    frame_bytes = SAMPLE_W * SAMPLE_H
    n = len(proc.stdout) // frame_bytes
    if n < 3:
        return None
    buf = np.frombuffer(proc.stdout, dtype=np.uint8)[: n * frame_bytes]
    return buf.reshape(n, SAMPLE_H, SAMPLE_W).astype(np.int16)


def inspect(
    path: Path,
    *,
    start: float,
    duration: float,
    cfg: Optional[Dict[str, Any]] = None,
) -> VisualVerdict:
    """区間の映像を検査する。

    判定できないとき（ffmpeg 失敗・numpy 無し・フレームが少なすぎる）は
    **通す**。ゲートが壊れて全部落ちると autopilot がその日を丸ごと落とすので、
    確信を持って落とせるときだけ落とす。
    """
    cfg = cfg or {}
    max_static = float(cfg.get("max_static_ratio", MAX_STATIC_RATIO))
    min_median = float(cfg.get("min_median_diff", MIN_MEDIAN_DIFF))
    thresh = float(cfg.get("static_diff_threshold", STATIC_DIFF_THRESHOLD))

    frames = _sample_gray(path, start=start, duration=duration)
    if frames is None:
        return VisualVerdict(True, "判定不能（サンプリング失敗）のため通過", 0.0, 0.0, 0)

    import numpy as np

    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    median = float(np.median(diffs))
    static_ratio = float((diffs < thresh).mean())
    n = int(frames.shape[0])

    if static_ratio >= max_static or median < min_median:
        return VisualVerdict(
            False,
            f"映像がほぼ静止（静止率 {static_ratio:.0%} / 中央値 {median:.2f}）。"
            "画面共有・資料・マンガなど第三者の著作物を映している可能性が高い",
            median, static_ratio, n,
        )
    return VisualVerdict(
        True, f"動きあり（静止率 {static_ratio:.0%} / 中央値 {median:.2f}）",
        median, static_ratio, n,
    )


def is_enabled(clip_cfg: Dict[str, Any]) -> bool:
    cfg = (clip_cfg or {}).get("visual_guard")
    if cfg is None:
        return True
    return bool(cfg.get("enabled", True))


def config(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return dict((clip_cfg or {}).get("visual_guard") or {})
