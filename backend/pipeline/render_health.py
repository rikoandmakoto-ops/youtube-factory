"""render_health — 「エラーは出ないが遅い」を数字にする。

背景（2026-09-09）:
    投稿が21本→1本に落ちた。ジョブは失敗していない。例外も出ていない。
    ただ **1フレーム 20〜162 秒**（平常時は毎秒約40フレーム）かかっていて、
    ワーカー2本がそれぞれ 11時間21分 / 16時間51分 のジョブに占有され、
    22件が処理されないまま日付をまたいだ。ERROR ログは 0 件だったので、
    例外を見る監視には一切かからなかった。

    翌日の実測でホスト側の資源が枯れていたことが分かった:

        load average      68.04（8コア = 1コアあたり 8.5）
        swap              20,146 MB / 21,504 MB 使用（94%）
        空きページ         1,480 × 16KB = 約 24 MB
        Image.alpha_composite(1080x1920)  670 ms（健全なら 10〜20ms）
        backend の CPU 時間  90秒の実時間に対して 7.1 秒（＝走れていない）

    つまり「コードが遅くなった」のではなく「走らせてもらえていない」。
    この状態はレンダのログを見ても *遅い* としか分からないので、
    **PDCA レポートに毎日出す**ことにした。欠測検知（analytics/freshness.py）と
    同じ扱いで、0本を「実績0」と読ませないための節である。

使い方:
    from pipeline import render_health
    snap = render_health.probe()          # 較正ベンチを1回だけ回す（約0.1〜1秒）
    print(render_health.format_section(snap))
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["probe", "classify", "format_section", "measure_composite_ms"]


# ---------------------------------------------------------------------
# 判定のしきい値
# ---------------------------------------------------------------------
# composite_ms は「1080x1920 の RGBA 合成 + RGB 変換」1回の実測。
# 健全な Mac mini (M系) で 10〜20ms。ショート1本 700 フレームなので、
# 60ms を超えると 1本 40 秒超（それ自体は許容）、200ms を超えると
# 1本で2分半を超え、枠の間隔（90分）に対して現実的でなくなる。
_COMPOSITE_DEGRADED_MS = 60.0
_COMPOSITE_CRITICAL_MS = 200.0

_LOAD_DEGRADED = 2.0      # 1コアあたりの実行待ち
_LOAD_CRITICAL = 4.0

_SWAP_DEGRADED = 0.50     # swap 使用率
_SWAP_CRITICAL = 0.85

_FREE_DEGRADED_MB = 512.0
_FREE_CRITICAL_MB = 128.0

_RANK = {"ok": 0, "degraded": 1, "critical": 2}


# ---------------------------------------------------------------------
# 実測
# ---------------------------------------------------------------------

def measure_composite_ms(repeat: int = 3) -> Optional[float]:
    """1080x1920 の合成1回にかかるミリ秒。レンダ速度の代理指標。

    レンダの `make_frame` が毎フレームやっているのと同じ演算なので、
    これが跳ねていればレンダも同じだけ跳ねている。
    """
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        return None
    try:
        bg = Image.new("RGBA", (1080, 1920), (20, 20, 20, 255))
        ov = Image.new("RGBA", (1080, 1920), (200, 100, 50, 128))
        np.array(Image.alpha_composite(bg, ov).convert("RGB"))  # warm-up
        t0 = time.perf_counter()
        for _ in range(max(1, repeat)):
            np.array(Image.alpha_composite(bg, ov).convert("RGB"))
        return (time.perf_counter() - t0) / max(1, repeat) * 1000.0
    except Exception:
        return None


def _load_per_core() -> Optional[float]:
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        return None
    cores = os.cpu_count() or 1
    return load1 / cores


def _swap_used_ratio() -> Optional[float]:
    """macOS: `sysctl vm.swapusage`。Linux: /proc/meminfo。"""
    try:
        out = subprocess.run(["sysctl", "-n", "vm.swapusage"],
                             capture_output=True, text=True, timeout=5).stdout
        total = re.search(r"total\s*=\s*([\d.]+)M", out)
        used = re.search(r"used\s*=\s*([\d.]+)M", out)
        if total and used:
            t = float(total.group(1))
            return (float(used.group(1)) / t) if t > 0 else 0.0
    except Exception:
        pass
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            info = {}
            for line in fh:
                k, _, v = line.partition(":")
                info[k.strip()] = float(v.strip().split()[0])
        total = info.get("SwapTotal", 0.0)
        if total > 0:
            return (total - info.get("SwapFree", 0.0)) / total
    except Exception:
        pass
    return None


def _free_mb() -> Optional[float]:
    """すぐに使える物理メモリ（MB）。macOS は free + speculative。"""
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
        page = re.search(r"page size of (\d+) bytes", out)
        page_size = int(page.group(1)) if page else 4096
        pages = 0
        for label in ("Pages free", "Pages speculative"):
            m = re.search(rf"{label}:\s+(\d+)", out)
            if m:
                pages += int(m.group(1))
        if pages:
            return pages * page_size / 1024.0 / 1024.0
    except Exception:
        pass
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------

def classify(load_per_core: Optional[float],
             swap_used_ratio: Optional[float],
             free_mb: Optional[float],
             composite_ms: Optional[float]) -> Tuple[str, List[str]]:
    """4つの実測から総合判定と理由を返す。読めなかった指標は無視する。

    どれか1つでも critical なら critical。指標が全滅なら "ok"（＝判定不能を
    異常と言わない。存在しない障害を毎日レポートに出す方が有害）。
    """
    verdict = "ok"
    reasons: List[str] = []

    def bump(level: str, reason: str) -> None:
        nonlocal verdict
        reasons.append(reason)
        if _RANK[level] > _RANK[verdict]:
            verdict = level

    if composite_ms is not None:
        if composite_ms >= _COMPOSITE_CRITICAL_MS:
            bump("critical",
                 f"1080x1920 の合成に {composite_ms:.0f}ms"
                 f"（健全 10〜20ms・上限 {_COMPOSITE_CRITICAL_MS:.0f}ms）")
        elif composite_ms >= _COMPOSITE_DEGRADED_MS:
            bump("degraded", f"1080x1920 の合成に {composite_ms:.0f}ms（健全 10〜20ms）")

    if load_per_core is not None:
        if load_per_core >= _LOAD_CRITICAL:
            bump("critical", f"load average が 1コアあたり {load_per_core:.1f}")
        elif load_per_core >= _LOAD_DEGRADED:
            bump("degraded", f"load average が 1コアあたり {load_per_core:.1f}")

    if swap_used_ratio is not None:
        if swap_used_ratio >= _SWAP_CRITICAL:
            bump("critical", f"swap 使用率 {swap_used_ratio*100:.0f}%")
        elif swap_used_ratio >= _SWAP_DEGRADED:
            bump("degraded", f"swap 使用率 {swap_used_ratio*100:.0f}%")

    if free_mb is not None:
        if free_mb <= _FREE_CRITICAL_MB:
            bump("critical", f"空きメモリ {free_mb:.0f}MB")
        elif free_mb <= _FREE_DEGRADED_MB:
            bump("degraded", f"空きメモリ {free_mb:.0f}MB")

    return verdict, reasons


def probe(calibrate: bool = True) -> Dict[str, Any]:
    """ホストの状態を1回だけ測って返す。

    calibrate=False なら合成ベンチを省く（起動経路など、数百ミリ秒でも
    惜しい場所から呼ぶとき用）。
    """
    composite_ms = measure_composite_ms() if calibrate else None
    load_per_core = _load_per_core()
    swap_used_ratio = _swap_used_ratio()
    free_mb = _free_mb()
    verdict, reasons = classify(load_per_core, swap_used_ratio, free_mb, composite_ms)
    return {
        "load_per_core": load_per_core,
        "swap_used_ratio": swap_used_ratio,
        "free_mb": free_mb,
        "composite_ms": composite_ms,
        "cores": os.cpu_count(),
        "verdict": verdict,
        "reasons": reasons,
    }


def _fmt(value: Optional[float], suffix: str, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}{suffix}"


def format_section(snap: Optional[Dict[str, Any]] = None) -> str:
    """PDCA レポート用の Markdown 節。"""
    s = snap if snap is not None else probe()
    mark = {"ok": "✅", "degraded": "⚠️", "critical": "🚨"}[s["verdict"]]
    swap = s["swap_used_ratio"]
    swap_label = "—" if swap is None else f"{swap * 100:.0f}%"
    lines = [
        "### レンダリング環境の健全性",
        "",
        "| 指標 | 実測 | 健全域 |",
        "|---|---|---|",
        f"| 1080x1920 合成 1回 | {_fmt(s['composite_ms'], 'ms', 0)} "
        f"| < {_COMPOSITE_DEGRADED_MS:.0f}ms |",
        f"| load average / コア | {_fmt(s['load_per_core'], '')} "
        f"| < {_LOAD_DEGRADED:.1f} |",
        f"| swap 使用率 | {swap_label} | < {_SWAP_DEGRADED*100:.0f}% |",
        f"| 空きメモリ | {_fmt(s['free_mb'], 'MB', 0)} | > {_FREE_DEGRADED_MB:.0f}MB |",
        "",
        f"{mark} 判定: **{s['verdict']}**",
    ]
    if s["reasons"]:
        lines.append("")
        for r in s["reasons"]:
            lines.append(f"- {r}")
        lines.append("")
        lines.append(
            "> レンダが遅いときの症状は「ジョブが失敗する」ではなく"
            "**「1本が何時間もワーカーを占有し、他が全部キューで待つ」**である。"
            "例外を見る監視には一生かからないので、ここの数字で判断すること。")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    print(format_section())
