"""
AI モデル間コンペ — GPT-4o と Claude Sonnet 4 が同じテーマで競合し、
ブラインド評価で勝者を決め、長期的な実績で補正する仕組み。

主な機能:
  - blind_compare(scenario_a, scenario_b, ...) — A/B ランダム化したまま Claude に採点させる
  - aggregate_performance(channel_id) — モデル別のブラインド勝率 + 実 CTR/維持率を集計
  - decide_selection_strategy(channel_id) — 実績差が大きければ「performance 補正」モードに切替え

ANTHROPIC_API_KEY 未設定時 / 呼び出し失敗時は blind_compare が None を返すので、
呼び出し側は両方を生成できていれば GPT を採用、片方しかなければそのまま採用、
という素朴な分岐に倒す。
"""

from __future__ import annotations

import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from .. import claude_client
from . import store as analytics_store


# 実績ベース補正の閾値
MIN_SAMPLES_FOR_BIAS = 5     # この本数を両モデルが満たさないと補正をかけない
BIAS_THRESHOLD = 0.10        # 実績スコアの差がこの比率を超えたらバイアスをかける

WEIGHT_CTR = 0.4
WEIGHT_RETENTION = 0.4
WEIGHT_WINRATE = 0.2


# ---------------------------------------------------------------------
# Blind compare (方式 3)
# ---------------------------------------------------------------------

_BLIND_SYSTEM = (
    "あなたは YouTube ゆっくり解説 / 教育系チャンネルのシナリオ評価の上級コンサルタントです。"
    "シナリオ A とシナリオ B を読み比べ、6 軸（hook_strength / specificity / pacing / "
    "cta_effectiveness / wording_quality / overall、1〜10）で両方に採点したうえで、"
    "視聴維持・CTR の観点でどちらが優れているかを判定してください。"
    "片方に肩入れしない中立な評価をしてください。"
)


def _scenario_brief(scenario: Dict[str, Any], *, max_lines: int = 30) -> Dict[str, Any]:
    """プロンプトに乗せる軽量シナリオダイジェスト。冒頭 + 末尾の行を抜粋する。"""
    title = scenario.get("title") or ""
    full = scenario.get("full_scenario") or []
    short = scenario.get("short_scenario") or []
    thumb = scenario.get("thumb_info") or {}

    def _trim(line: Any) -> Dict[str, Any]:
        if not isinstance(line, dict):
            return {"text": str(line)[:120]}
        return {
            "speaker": line.get("speaker") or "",
            "text": (line.get("text") or "")[:140],
            "mood": line.get("mood") or "",
        }

    head = [_trim(l) for l in full[: max_lines // 2]]
    tail = [_trim(l) for l in full[-max_lines // 2 :]] if len(full) > max_lines else []
    short_brief = [_trim(l) for l in short[:8]]
    return {
        "title": title,
        "thumb_hook_lines": thumb.get("hook_lines") or [],
        "short_scenario": short_brief,
        "full_scenario_head": head,
        "full_scenario_tail": tail,
        "full_scenario_total_lines": len(full),
        "full_scenario_total_chars": sum(
            len((l.get("text") or "")) for l in full if isinstance(l, dict)
        ),
    }


def blind_compare(
    scenario_a: Dict[str, Any],
    scenario_b: Dict[str, Any],
    *,
    channel_id: Optional[str] = None,
    model_a: str = "gpt",
    model_b: str = "claude",
) -> Optional[Dict[str, Any]]:
    """2 シナリオをブラインドで比較。`winner` は "A" or "B"。

    戻り値:
        {
          "winner": "A" | "B",
          "winner_model": "gpt" | "claude",
          "reason": "...",
          "scores_a": {6軸},
          "scores_b": {6軸},
          "mapping": {"A": model_x, "B": model_y},
        }

    Claude 未設定時は None。
    """
    if not claude_client.has_api_key():
        return None

    # A/B と (gpt/claude) のマッピングをランダム化して、Claude にどちらか伏せる
    mapping: Dict[str, str]
    if random.random() < 0.5:
        mapping = {"A": model_a, "B": model_b}
        a_src, b_src = scenario_a, scenario_b
    else:
        mapping = {"A": model_b, "B": model_a}
        a_src, b_src = scenario_b, scenario_a

    brief_a = _scenario_brief(a_src)
    brief_b = _scenario_brief(b_src)

    user = f"""# 評価対象
## シナリオ A
{json.dumps(brief_a, ensure_ascii=False, indent=2)}

## シナリオ B
{json.dumps(brief_b, ensure_ascii=False, indent=2)}

# 出力 JSON スキーマ（他キー禁止・1〜10 の数値）
{{
  "scores_a": {{
    "hook_strength": 1〜10,
    "specificity": 1〜10,
    "pacing": 1〜10,
    "cta_effectiveness": 1〜10,
    "wording_quality": 1〜10,
    "overall": 1〜10
  }},
  "scores_b": {{
    "hook_strength": 1〜10,
    "specificity": 1〜10,
    "pacing": 1〜10,
    "cta_effectiveness": 1〜10,
    "wording_quality": 1〜10,
    "overall": 1〜10
  }},
  "winner": "A" または "B",
  "reason": "勝者が優れている根拠を 1〜2 文で。具体的にどの軸で差があったか触れる"
}}
"""

    resp = claude_client.call_claude_json(
        system=_BLIND_SYSTEM,
        user=user,
        temperature=0.2,
        max_tokens=1500,
        channel_id=channel_id,
        purpose="blind_compare",
    )
    if not resp or "winner" not in resp:
        return None

    winner = str(resp.get("winner") or "").strip().upper()
    if winner not in ("A", "B"):
        # たまに "Aの方が..." みたいに返ることがあるので拾う
        text = json.dumps(resp, ensure_ascii=False)
        m = re.search(r"\b(A|B)\b", text)
        winner = m.group(1).upper() if m else "A"

    return {
        "winner": winner,
        "winner_model": mapping[winner],
        "reason": resp.get("reason") or "",
        "scores_a": resp.get("scores_a") or {},
        "scores_b": resp.get("scores_b") or {},
        "mapping": mapping,
    }


# ---------------------------------------------------------------------
# 実績集計 + 補正 (方式 4)
# ---------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[ぁ-んァ-ン一-龥A-Za-z0-9]+")


def _slug(s: Optional[str]) -> str:
    if not s:
        return ""
    return "".join(_TOKEN_RE.findall(s)).lower()


def _match_video_metrics(records: List[Dict[str, Any]], metrics: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """selected な model_scenario_records と video_metrics を title slug で緩マッチ。

    既に video_id が埋まっているレコードはそちら優先。
    戻り値: record_id -> matched_metric
    """
    matched: Dict[int, Dict[str, Any]] = {}
    by_video_id = {m.get("video_id"): m for m in metrics if m.get("video_id")}
    used_video_ids: set = set()
    for r in records:
        rid = int(r.get("id") or 0)
        if not rid:
            continue
        vid = r.get("video_id")
        if vid and vid in by_video_id:
            matched[rid] = by_video_id[vid]
            used_video_ids.add(vid)
            continue
        target = _slug(r.get("title"))
        if not target:
            continue
        best: Optional[Tuple[float, Dict[str, Any]]] = None
        for m in metrics:
            mvid = m.get("video_id")
            if mvid in used_video_ids:
                continue
            cand = _slug(m.get("title"))
            if not cand:
                continue
            shared = 0
            for n in range(3, min(len(target), len(cand)) + 1):
                if target[:n] in cand or cand[:n] in target:
                    shared = n
            score = shared / max(len(target), len(cand), 1)
            if score >= 0.4 and (best is None or score > best[0]):
                best = (score, m)
        if best:
            matched[rid] = best[1]
            used_video_ids.add(best[1].get("video_id"))
    return matched


def _avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def aggregate_performance(channel_id: str) -> Dict[str, Any]:
    """gpt / claude のブラインド勝率 + 実 CTR / 維持率を集計。

    戻り値:
      {
        "channel_id": ...,
        "by_model": {
          "gpt":   {"scenario_count": N, "win_count": W, "win_rate": ratio,
                    "avg_views": V, "avg_ctr": C, "avg_retention": R,
                    "avg_blind_overall": O, "perf_score": float, "samples_with_metrics": M},
          "claude": {...},
        },
        "leader": "gpt" | "claude" | None,
        "leader_margin": float,   # perf_score の比率差 (leader / other - 1)
        "blind_compare_runs": int,
        "selected_counts": {"blind_eval": ..., "performance": ..., "only_one": ...},
      }
    """
    records = analytics_store.list_model_scenario_records(channel_id, limit=2000)
    metrics = analytics_store.list_video_metrics(channel_id, limit=500)
    matched = _match_video_metrics([r for r in records if r.get("selected")], metrics)

    by_model: Dict[str, Dict[str, Any]] = {
        "gpt": {"records": [], "matched_metrics": [], "wins": 0},
        "claude": {"records": [], "matched_metrics": [], "wins": 0},
    }
    selected_counts: Dict[str, int] = {"blind_eval": 0, "performance": 0, "only_one": 0}

    run_ids_with_compare: set = set()
    for r in records:
        model = r.get("model_name")
        if model not in by_model:
            continue
        by_model[model]["records"].append(r)
        if r.get("won_blind_eval"):
            by_model[model]["wins"] += 1
        if r.get("blind_overall") is not None:
            run_ids_with_compare.add(r.get("run_id"))
        if r.get("selected"):
            sb = r.get("selected_by") or "only_one"
            selected_counts[sb] = selected_counts.get(sb, 0) + 1
            mm = matched.get(int(r.get("id") or 0))
            if mm:
                by_model[model]["matched_metrics"].append(mm)

    out_models: Dict[str, Dict[str, Any]] = {}
    for model, agg in by_model.items():
        records_m = agg["records"]
        mm_list = agg["matched_metrics"]
        wins = agg["wins"]
        # ブラインド比較が走った件数のみで勝率を計算
        compare_runs_for_model = sum(
            1 for r in records_m if r.get("blind_overall") is not None
        )
        win_rate = (wins / compare_runs_for_model) if compare_runs_for_model > 0 else 0.0
        views = [float(m.get("views") or 0) for m in mm_list]
        # CTR は 0..1 と 0..100 が混在しうるので 0..1 系に正規化
        ctr_raw = [float(m.get("ctr") or 0) for m in mm_list if m.get("ctr") is not None]
        ctr_norm = [c if c <= 1 else c / 100.0 for c in ctr_raw]
        retention = [float(m.get("avg_view_percentage") or 0) for m in mm_list]
        retention_norm = [r if r <= 1 else r / 100.0 for r in retention]
        avg_blind = _avg([
            float(r.get("blind_overall") or 0) for r in records_m if r.get("blind_overall") is not None
        ])

        # perf_score: avg_ctr*0.4 + avg_retention*0.4 + win_rate*0.2 を 0..1 に揃える
        avg_ctr_norm = _avg(ctr_norm)
        avg_ret_norm = _avg(retention_norm)
        perf_score = (
            avg_ctr_norm * WEIGHT_CTR
            + avg_ret_norm * WEIGHT_RETENTION
            + win_rate * WEIGHT_WINRATE
        )

        out_models[model] = {
            "scenario_count": len(records_m),
            "selected_count": sum(1 for r in records_m if r.get("selected")),
            "win_count": wins,
            "compare_runs": compare_runs_for_model,
            "win_rate": round(win_rate, 4),
            "samples_with_metrics": len(mm_list),
            "avg_views": round(_avg(views), 2),
            "avg_ctr": round(avg_ctr_norm, 4),
            "avg_retention": round(avg_ret_norm, 4),
            "avg_blind_overall": round(avg_blind, 2),
            "perf_score": round(perf_score, 4),
        }

    # leader 判定
    leader: Optional[str] = None
    leader_margin = 0.0
    g = out_models["gpt"]
    c = out_models["claude"]
    if (
        g["samples_with_metrics"] >= MIN_SAMPLES_FOR_BIAS
        and c["samples_with_metrics"] >= MIN_SAMPLES_FOR_BIAS
        and (g["perf_score"] > 0 or c["perf_score"] > 0)
    ):
        if g["perf_score"] > c["perf_score"]:
            base = c["perf_score"] if c["perf_score"] > 0 else g["perf_score"]
            leader_margin = (g["perf_score"] / base - 1) if base > 0 else 0.0
            if leader_margin >= BIAS_THRESHOLD:
                leader = "gpt"
        elif c["perf_score"] > g["perf_score"]:
            base = g["perf_score"] if g["perf_score"] > 0 else c["perf_score"]
            leader_margin = (c["perf_score"] / base - 1) if base > 0 else 0.0
            if leader_margin >= BIAS_THRESHOLD:
                leader = "claude"

    return {
        "channel_id": channel_id,
        "by_model": out_models,
        "leader": leader,
        "leader_margin": round(leader_margin, 4),
        "blind_compare_runs": len(run_ids_with_compare),
        "selected_counts": selected_counts,
        "min_samples_for_bias": MIN_SAMPLES_FOR_BIAS,
        "bias_threshold": BIAS_THRESHOLD,
    }


def decide_selection_strategy(channel_id: str) -> Dict[str, Any]:
    """次回の採用判断方針を返す。

    戻り値:
      {"mode": "blind" | "prefer_gpt" | "prefer_claude", "reason": "...",
       "leader": ..., "margin": ...}
    """
    perf = aggregate_performance(channel_id)
    leader = perf.get("leader")
    if leader == "gpt":
        return {
            "mode": "prefer_gpt",
            "reason": f"GPT が実績スコアで {perf['leader_margin']*100:.1f}% 優位",
            "leader": leader,
            "margin": perf["leader_margin"],
        }
    if leader == "claude":
        return {
            "mode": "prefer_claude",
            "reason": f"Claude が実績スコアで {perf['leader_margin']*100:.1f}% 優位",
            "leader": leader,
            "margin": perf["leader_margin"],
        }
    return {
        "mode": "blind",
        "reason": (
            "実績データが閾値未満、または差が誤差レベル"
            if perf["by_model"]["gpt"]["samples_with_metrics"] < MIN_SAMPLES_FOR_BIAS
            or perf["by_model"]["claude"]["samples_with_metrics"] < MIN_SAMPLES_FOR_BIAS
            else "両モデルの実績スコアが拮抗"
        ),
        "leader": None,
        "margin": perf["leader_margin"],
    }
