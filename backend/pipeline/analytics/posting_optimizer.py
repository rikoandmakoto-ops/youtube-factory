"""
投稿タイミング最適化 — 過去動画の公開時刻と再生数から最適投稿スロットを算出。

YouTube Analytics API は "視聴者のオンライン時間帯" を直接返さないため、
公開済み動画の (曜日 × 時間帯) ごとの平均再生数を分析して最適スロットを推定する。
データソースは `video_metrics` テーブル（既存）+ チャンネル別 published_at。

公開関数:
  - build_heatmap(channel_id, days=30): {grid:[[v...]*24]*7, total, channel_avg}
  - recommend_slot(channel_id, days=30): 最適 (dow, hour) + 期待ブースト率
  - apply_to_autopilot(channel_id): 推奨スロットを autopilot.schedule に書き戻す
  - get_status(channel_id): UI 用の {current_schedule, recommended, heatmap, ...}

JST 基準 (Asia/Tokyo)。`day_of_week` は 0=日曜, 6=土曜（フロント/autopilot と同じ）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "analytics" / "analytics.db"

JST = timezone(timedelta(hours=9))

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_cache_table() -> None:
    with _lock:
        c = _conn()
        try:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS posting_optimizer_cache (
                    channel_id TEXT PRIMARY KEY,
                    heatmap_json TEXT NOT NULL,
                    recommendation_json TEXT NOT NULL,
                    computed_at INTEGER NOT NULL
                );
                """
            )
            c.commit()
        finally:
            c.close()


_init_cache_table()


def _empty_grid() -> List[List[float]]:
    return [[0.0 for _ in range(24)] for _ in range(7)]


def _parse_published_at(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # ISO 8601 (YouTube returns 2024-01-01T12:34:56Z)
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(JST)
    except Exception:
        return None


def _load_video_samples(channel_id: str, since_days: int) -> List[Dict[str, Any]]:
    """video_metrics から (published_at, views, ctr) を抽出。
    same video_id は最新スナップショット 1 件。"""
    cutoff = int(time.time()) - since_days * 86400
    with _lock:
        c = _conn()
        try:
            rows = c.execute(
                """
                SELECT m.video_id, m.published_at, m.views, m.ctr, m.avg_view_percentage
                FROM video_metrics m
                INNER JOIN (
                    SELECT video_id, MAX(date) AS max_date
                    FROM video_metrics WHERE channel_id = ?
                    GROUP BY video_id
                ) latest
                ON m.video_id = latest.video_id AND m.date = latest.max_date
                WHERE m.channel_id = ?
                """,
                (channel_id, channel_id),
            ).fetchall()
        finally:
            c.close()

    out: List[Dict[str, Any]] = []
    for r in rows:
        pub = _parse_published_at(r["published_at"])
        if not pub:
            continue
        # since_days 内に公開された動画に絞る（古すぎる傾向は信頼性低）
        if pub.timestamp() < cutoff:
            continue
        out.append(
            {
                "video_id": r["video_id"],
                "published_jst": pub,
                "views": int(r["views"] or 0),
                "ctr": float(r["ctr"] or 0),
                "retention": float(r["avg_view_percentage"] or 0),
            }
        )
    return out


def build_heatmap(channel_id: str, *, days: int = 30) -> Dict[str, Any]:
    """過去 `days` 日の公開動画について、(dow=0..6, hour=0..23) スロットの平均再生数を返す。

    Returns:
        {
          "grid":    [[avg_views per hour for dow]*24]*7,    # avg views per video
          "samples": [[count]*24]*7,
          "channel_avg_views": float,
          "channel_total_videos": int,
          "data_days": int,
        }
    """
    samples = _load_video_samples(channel_id, since_days=days)
    grid = _empty_grid()
    counts = [[0 for _ in range(24)] for _ in range(7)]
    total_views = 0
    for v in samples:
        pub: datetime = v["published_jst"]
        # python の weekday: Mon=0..Sun=6. UI 側は Sun=0..Sat=6 なので変換。
        dow_py = pub.weekday()
        dow = (dow_py + 1) % 7
        hour = pub.hour
        grid[dow][hour] += v["views"]
        counts[dow][hour] += 1
        total_views += v["views"]
    # 平均化
    avg_grid: List[List[float]] = _empty_grid()
    for d in range(7):
        for h in range(24):
            if counts[d][h] > 0:
                avg_grid[d][h] = grid[d][h] / counts[d][h]
    channel_avg = (total_views / len(samples)) if samples else 0.0
    return {
        "grid": avg_grid,
        "samples": counts,
        "channel_avg_views": channel_avg,
        "channel_total_videos": len(samples),
        "data_days": days,
    }


def recommend_slot(channel_id: str, *, days: int = 30) -> Dict[str, Any]:
    """最高スロット (dow, hour) と期待ブースト率を返す。

    1 サンプルしかないスロットは bias がかかるので 2 件以上のスロットを優先。
    候補が無ければ、サンプル 1 件でも採用。
    全く実績が無ければ JST 18:00 火・木をデフォルト推奨。
    """
    hm = build_heatmap(channel_id, days=days)
    grid = hm["grid"]
    counts = hm["samples"]
    channel_avg = hm["channel_avg_views"] or 0.0

    candidates: List[Tuple[int, int, float, int]] = []  # (dow, hour, avg_views, n)
    for d in range(7):
        for h in range(24):
            n = counts[d][h]
            v = grid[d][h]
            if n >= 1:
                candidates.append((d, h, v, n))

    # スコア = 平均再生 × min(n,3)/3 で 1 件しか無いスロットを少しディスカウント
    def _score(c: Tuple[int, int, float, int]) -> float:
        d, h, v, n = c
        return v * (min(n, 3) / 3.0)

    candidates.sort(key=_score, reverse=True)
    top3: List[Dict[str, Any]] = []
    for c in candidates[:3]:
        d, h, v, n = c
        boost = ((v - channel_avg) / channel_avg * 100.0) if channel_avg > 0 else 0.0
        top3.append({
            "day_of_week": d,
            "hour": h,
            "minute": 0,
            "avg_views": round(v, 1),
            "sample_size": n,
            "boost_percent": round(boost, 1),
        })

    if not top3:
        # フォールバック：火曜 (2) / 木曜 (4) 18:00 JST
        return {
            "recommended": {
                "day_of_week": 2,
                "hour": 18,
                "minute": 0,
                "avg_views": 0.0,
                "sample_size": 0,
                "boost_percent": 0.0,
                "is_fallback": True,
            },
            "alternatives": [],
            "channel_avg_views": channel_avg,
            "data_days": days,
            "note": "実績データ不足のためデフォルト (火曜 18:00 JST) を推奨。",
        }

    best = top3[0]
    return {
        "recommended": best,
        "alternatives": top3[1:],
        "channel_avg_views": channel_avg,
        "data_days": days,
        "note": None,
    }


def _save_cache(channel_id: str, heatmap: Dict[str, Any], recommendation: Dict[str, Any]) -> None:
    now = int(time.time())
    with _lock:
        c = _conn()
        try:
            c.execute(
                """
                INSERT OR REPLACE INTO posting_optimizer_cache
                (channel_id, heatmap_json, recommendation_json, computed_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    channel_id,
                    json.dumps(heatmap, ensure_ascii=False),
                    json.dumps(recommendation, ensure_ascii=False),
                    now,
                ),
            )
            c.commit()
        finally:
            c.close()


def get_cached(channel_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM posting_optimizer_cache WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
        finally:
            c.close()
    if not row:
        return None
    try:
        return {
            "heatmap": json.loads(row["heatmap_json"]),
            "recommendation": json.loads(row["recommendation_json"]),
            "computed_at": row["computed_at"],
        }
    except Exception:
        return None


def compute(channel_id: str, *, days: int = 30) -> Dict[str, Any]:
    """ヒートマップと推奨スロットを計算してキャッシュ。"""
    heatmap = build_heatmap(channel_id, days=days)
    rec = recommend_slot(channel_id, days=days)
    _save_cache(channel_id, heatmap, rec)
    return {"heatmap": heatmap, "recommendation": rec, "computed_at": int(time.time())}


# ---------------------------------------------------------------------
# 現在の autopilot 設定と比較 + 自動適用
# ---------------------------------------------------------------------

def _read_current_autopilot_schedule(channel_id: str) -> Optional[Dict[str, Any]]:
    """data/channels/{channel_id}.json の autopilot.schedule を読む。"""
    ch_path = PROJECT_ROOT / "data" / "channels" / f"{channel_id}.json"
    if not ch_path.exists():
        return None
    try:
        data = json.loads(ch_path.read_text(encoding="utf-8"))
        ap = data.get("autopilot") or {}
        sched = ap.get("schedule") or {}
        return {
            "days_of_week": list(sched.get("days_of_week") or []),
            "hour": int(sched.get("hour", 18)),
            "minute": int(sched.get("minute", 0)),
            "enabled": bool(ap.get("enabled")),
        }
    except Exception:
        return None


def get_status(channel_id: str, *, days: int = 30, recompute: bool = False) -> Dict[str, Any]:
    """UI 用のサマリ。"""
    cached = None if recompute else get_cached(channel_id)
    if cached is None:
        cached = compute(channel_id, days=days)
    current = _read_current_autopilot_schedule(channel_id)
    return {
        "channel_id": channel_id,
        "current_schedule": current,
        "recommendation": cached["recommendation"],
        "heatmap": cached["heatmap"],
        "computed_at": cached["computed_at"],
    }


def apply_to_autopilot(channel_id: str, *, days: int = 30) -> Dict[str, Any]:
    """推奨スロット (曜日/時) を data/channels/{id}.json の autopilot.schedule に書き戻す。

    days_of_week は推奨1+代替1〜2の中から最大3つを採用（重複曜日は1つに集約）。
    時刻は最も実績の良い hour を採用する。
    """
    status = get_status(channel_id, days=days, recompute=True)
    rec = status["recommendation"]["recommended"]
    alts = status["recommendation"].get("alternatives") or []

    # 採用曜日リスト：best + alternatives（重複除外、最大3）
    dow_set: List[int] = []
    for slot in [rec] + list(alts):
        d = int(slot.get("day_of_week", -1))
        if 0 <= d <= 6 and d not in dow_set:
            dow_set.append(d)
        if len(dow_set) >= 3:
            break
    hour = int(rec.get("hour", 18))
    minute = int(rec.get("minute", 0))

    ch_path = PROJECT_ROOT / "data" / "channels" / f"{channel_id}.json"
    if not ch_path.exists():
        return {"ok": False, "error": f"channel file not found: {channel_id}"}

    data = json.loads(ch_path.read_text(encoding="utf-8"))
    ap = dict(data.get("autopilot") or {})
    sched = dict(ap.get("schedule") or {})
    old = {
        "days_of_week": list(sched.get("days_of_week") or []),
        "hour": int(sched.get("hour", 18)),
        "minute": int(sched.get("minute", 0)),
    }
    sched["days_of_week"] = sorted(dow_set) if dow_set else old["days_of_week"]
    sched["hour"] = hour
    sched["minute"] = minute
    ap["schedule"] = sched
    data["autopilot"] = ap
    ch_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # autopilot のスケジューラジョブを再同期（循環 import 回避のため遅延 import）
    try:
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "backend"))
        import api_channel_autopilot  # type: ignore
        api_channel_autopilot._refresh_channel_job(channel_id)
    except Exception as e:
        print(f"⚠️ posting_optimizer.apply: scheduler refresh failed for {channel_id}: {e}")

    return {
        "ok": True,
        "channel_id": channel_id,
        "previous": old,
        "applied": {
            "days_of_week": sched["days_of_week"],
            "hour": sched["hour"],
            "minute": sched["minute"],
        },
        "recommendation": status["recommendation"],
    }


# ---------------------------------------------------------------------
# autopilot 統合: 投稿前に "本当に今が最適か" を簡易検査
# ---------------------------------------------------------------------

def slot_is_optimal_enough(
    channel_id: str,
    *,
    dow: Optional[int] = None,
    hour: Optional[int] = None,
    tolerance_percent: float = 30.0,
    days: int = 30,
) -> Dict[str, Any]:
    """現在のスロットが推奨スロットの -tolerance% 以内かを返す。

    autopilot の fire 時に "もっと良い時間に再スケジュールすべきか" 判断するのに使う。
    今のスロットが推奨スロットより低く、差が tolerance を超えていれば apply 推奨。
    """
    now = datetime.now(JST)
    if dow is None:
        dow = (now.weekday() + 1) % 7
    if hour is None:
        hour = now.hour
    hm = build_heatmap(channel_id, days=days)
    rec = recommend_slot(channel_id, days=days)
    best = rec["recommended"]
    grid = hm["grid"]
    current_avg = float(grid[dow][hour]) if 0 <= dow < 7 and 0 <= hour < 24 else 0.0
    best_avg = float(best.get("avg_views") or 0)
    if best_avg <= 0:
        return {"is_optimal_enough": True, "current_avg": current_avg, "best_avg": best_avg, "delta_percent": 0.0}
    delta = ((best_avg - current_avg) / best_avg) * 100.0
    return {
        "is_optimal_enough": delta <= tolerance_percent,
        "current_avg": current_avg,
        "best_avg": best_avg,
        "delta_percent": round(delta, 1),
        "best_slot": best,
    }
