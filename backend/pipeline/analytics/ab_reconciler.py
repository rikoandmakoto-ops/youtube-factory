"""
AB テスト答え合わせ (Phase D — B)

仕組み:
  1. data/ab_tests/*.json を走査し、actual_metrics が未紐付けの test を抽出
  2. test.theme + variants の title を YouTube に公開された動画タイトルと照合
  3. 公開後 7 日以上経過したものについて、analytics.db.video_metrics から
     実 CTR / impressions / views を取り、test JSON と analytics.db.ab_test_reconciliation
     の両方に書き込む
  4. パターン別（疑問形/数字入り/意外性フック）の予測 vs 実績差分を集計

公開エントリ:
  - reconcile_channel(channel_id, *, min_age_days=7) -> dict
  - build_ab_learning_addendum(channel_id) -> Optional[str]   ← ab_test_generator が利用
  - pattern_insights(channel_id) -> dict   ← ダッシュボード用
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import store as analytics_store

try:
    from pipeline import ab_test_generator
except Exception:  # pragma: no cover — running as a script
    ab_test_generator = None  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
AB_DIR = PROJECT_ROOT / "data" / "ab_tests"


_TOKEN_RE = re.compile(r"[ぁ-んァ-ン一-龥A-Za-z0-9]+")


def _normalize(s: str) -> str:
    if not s:
        return ""
    return "".join(_TOKEN_RE.findall(s)).lower()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _age_days(generated_at: Optional[str], published_at: Optional[str]) -> Optional[float]:
    ref = _parse_iso(published_at) or _parse_iso(generated_at)
    if not ref:
        return None
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - ref).total_seconds() / 86400.0


def _match_video(test: Dict[str, Any], metrics: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], int, Dict[str, Any]]]:
    """test の variants と video_metrics を照合して、最も近い video と variant index を返す。

    Returns: (video_metric, variant_index, variant) or None
    """
    variants = test.get("variants") or []
    if not variants:
        return None
    theme_title = ((test.get("theme") or {}).get("title") or "")
    norm_theme = _normalize(theme_title)
    norm_variants = [
        (i, v, _normalize(v.get("title") or ""))
        for i, v in enumerate(variants)
    ]
    best: Optional[Tuple[float, Dict[str, Any], int, Dict[str, Any]]] = None
    for m in metrics:
        cand = _normalize(m.get("title") or "")
        if not cand:
            continue
        # variant のタイトルに対する最大 Jaccard 風スコア
        for i, v, n in norm_variants:
            if not n:
                continue
            shared = 0
            for k in range(3, min(len(cand), len(n)) + 1):
                if cand[:k] in n or n[:k] in cand:
                    shared = k
            score = shared / max(len(cand), len(n), 1)
            if score >= 0.45 and (best is None or score > best[0]):
                best = (score, m, i, v)
        # テーマ自体ともマッチを試す
        if norm_theme:
            shared = 0
            for k in range(3, min(len(cand), len(norm_theme)) + 1):
                if cand[:k] in norm_theme or norm_theme[:k] in cand:
                    shared = k
            score = shared / max(len(cand), len(norm_theme), 1)
            if score >= 0.6 and (best is None or score > best[0]):
                # variants の中で best_pattern があればそれを採用
                bi = (test.get("best") or {}).get("pattern")
                idx = 0
                for i, v in enumerate(variants):
                    if v.get("pattern") == bi:
                        idx = i
                        break
                best = (score, m, idx, variants[idx])
    if not best:
        return None
    return (best[1], best[2], best[3])


def reconcile_channel(channel_id: str, *, min_age_days: float = 7.0) -> Dict[str, Any]:
    """channel_id に紐づく AB test と video_metrics を照合して、実 CTR を紐付ける。"""
    if not AB_DIR.exists():
        return {"channel_id": channel_id, "reconciled": 0, "items": [], "reason": "no_ab_tests_dir"}
    files = sorted(AB_DIR.glob("abt_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    metrics = analytics_store.list_video_metrics(channel_id, limit=200)
    metric_by_id = {m.get("video_id"): m for m in metrics if m.get("video_id")}

    out_items: List[Dict[str, Any]] = []
    reconciled_count = 0

    for f in files:
        try:
            test = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if test.get("channel_id") != channel_id:
            continue
        # 既に reconciled の項目もパターンサマリは要るので拾う
        existing_actual = test.get("actual_metrics") or {}
        generated_at = test.get("generated_at")
        age = _age_days(generated_at, existing_actual.get("published_at"))
        age_ok = age is not None and age >= min_age_days

        matched = _match_video(test, metrics)
        if not matched:
            out_items.append({
                "test_id": test.get("test_id"),
                "status": "no_match",
                "age_days": age,
            })
            continue
        metric, variant_idx, variant = matched
        video_id = metric.get("video_id")
        published_at = metric.get("published_at")
        # 公開済みの published_at で再計算
        age2 = _age_days(generated_at, published_at)
        if age2 is not None:
            age = age2
            age_ok = age >= min_age_days

        if not age_ok:
            out_items.append({
                "test_id": test.get("test_id"),
                "status": "too_young",
                "age_days": age,
                "matched_video_id": video_id,
            })
            continue

        actual_ctr = metric.get("ctr")
        actual_imp = metric.get("impressions")
        actual_views = metric.get("views")
        predicted_score = None
        try:
            predicted_score = float(variant.get("score") or 0.0)
        except Exception:
            predicted_score = None

        # 1) ab_test json に書き戻し
        if ab_test_generator is not None:
            try:
                ab_test_generator.attach_actual_metrics(
                    test["test_id"],
                    {
                        "video_id": video_id,
                        "matched_variant_index": variant_idx,
                        "pattern": variant.get("pattern"),
                        "ctr": actual_ctr,
                        "impressions": actual_imp,
                        "views": actual_views,
                        "published_at": published_at,
                    },
                )
            except Exception as e:
                print(f"⚠️ attach_actual_metrics failed: {e}")

        # 2) analytics.db.ab_test_reconciliation に upsert
        try:
            analytics_store.upsert_ab_reconciliation(
                test_id=test["test_id"],
                variant_index=variant_idx,
                channel_id=channel_id,
                video_id=video_id,
                pattern_type=variant.get("pattern"),
                predicted_score=predicted_score,
                actual_ctr=actual_ctr,
                actual_impressions=actual_imp,
                actual_views=actual_views,
            )
        except Exception as e:
            print(f"⚠️ upsert_ab_reconciliation failed: {e}")
            continue

        reconciled_count += 1
        out_items.append({
            "test_id": test.get("test_id"),
            "status": "reconciled",
            "matched_video_id": video_id,
            "pattern_type": variant.get("pattern"),
            "predicted_score": predicted_score,
            "actual_ctr": actual_ctr,
            "actual_impressions": actual_imp,
            "age_days": age,
        })

    return {
        "channel_id": channel_id,
        "reconciled": reconciled_count,
        "items": out_items,
        "ran_at": int(time.time()),
    }


def pattern_insights(channel_id: str) -> Dict[str, Any]:
    """パターン別の予測 vs 実 CTR 集計。"""
    rows = analytics_store.list_ab_reconciliations(channel_id, limit=500)
    by_pattern: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        p = r.get("pattern_type") or "unknown"
        bucket = by_pattern.setdefault(p, {
            "pattern_type": p,
            "samples": 0,
            "predicted_avg": 0.0,
            "actual_ctr_avg": 0.0,
            "_pred_sum": 0.0,
            "_pred_n": 0,
            "_ctr_sum": 0.0,
            "_ctr_n": 0,
        })
        bucket["samples"] += 1
        if r.get("predicted_score") is not None:
            bucket["_pred_sum"] += float(r["predicted_score"])
            bucket["_pred_n"] += 1
        if r.get("actual_ctr") is not None:
            bucket["_ctr_sum"] += float(r["actual_ctr"])
            bucket["_ctr_n"] += 1
    insights: List[Dict[str, Any]] = []
    for p, b in by_pattern.items():
        pred_avg = b["_pred_sum"] / b["_pred_n"] if b["_pred_n"] else None
        ctr_avg = b["_ctr_sum"] / b["_ctr_n"] if b["_ctr_n"] else None
        insights.append({
            "pattern_type": p,
            "samples": b["samples"],
            "predicted_score_avg": round(pred_avg, 2) if pred_avg is not None else None,
            "actual_ctr_avg": round(ctr_avg, 4) if ctr_avg is not None else None,
            "actual_ctr_percent_avg": round(ctr_avg * 100, 2) if ctr_avg is not None else None,
        })
    # overall (across all patterns)
    all_ctr = [float(r["actual_ctr"]) for r in rows if r.get("actual_ctr") is not None]
    overall_ctr_avg = sum(all_ctr) / len(all_ctr) if all_ctr else None
    return {
        "channel_id": channel_id,
        "total_samples": len(rows),
        "overall_actual_ctr_avg": overall_ctr_avg,
        "patterns": insights,
    }


def build_ab_learning_addendum(channel_id: Optional[str]) -> Optional[str]:
    """ab_test_generator のプロンプトに注入する「過去の予測 vs 実績」サマリ。

    パターン別に実 CTR がどう乖離したか／どのパターンが好成績だったかを伝える。
    """
    if not channel_id:
        return None
    try:
        insights = pattern_insights(channel_id)
    except Exception:
        return None
    if insights.get("total_samples", 0) == 0:
        return None

    overall_avg = insights.get("overall_actual_ctr_avg")
    pat_rows = insights.get("patterns") or []
    if not pat_rows:
        return None

    lines: List[str] = []
    lines.append("# 過去の AB テスト実績（このチャンネル）")
    if overall_avg is not None:
        lines.append(f"- 全パターン平均実 CTR: {overall_avg*100:.2f}%")
    label = {"question": "疑問形", "number": "数字入り", "surprise": "意外性フック"}
    # ベンチマークとして overall_avg を使う
    for r in pat_rows:
        p = r["pattern_type"]
        nm = label.get(p, p)
        ctr_pct = r.get("actual_ctr_percent_avg")
        pred = r.get("predicted_score_avg")
        if ctr_pct is None:
            continue
        delta_txt = ""
        if overall_avg is not None and overall_avg > 0:
            delta = ctr_pct - overall_avg * 100
            sign = "+" if delta >= 0 else ""
            delta_txt = f"（全体平均比 {sign}{delta:.2f}pt）"
        pred_txt = f" / 予測スコア平均 {pred:.1f}" if pred is not None else ""
        lines.append(
            f"- {nm}（n={r['samples']}）: 実 CTR 平均 {ctr_pct:.2f}%{delta_txt}{pred_txt}"
        )

    lines.append(
        "\n# 学習指示\n"
        "- 上記実績を考慮し、実 CTR が伸びやすいパターンの題材選びを優先する。\n"
        "- 予測スコアが高くても実 CTR が低かったパターンは慎重にコピーを設計する。"
    )
    return "\n".join(lines)
