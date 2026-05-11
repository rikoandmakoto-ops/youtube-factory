"""
シナリオ自動評価エンジン (Phase D — A2)

各動画のシナリオ原文を Claude (Sonnet 4) で 6 軸採点し、離脱カーブ・コメント分析を
突き合わせて「弱点セクション」と「具体的な改善提案」を生成する。

入力:
  - analytics.db: video_metrics, retention_curve, comment_analysis
  - data/scenarios/<channel_id>/{archive/*.md, *.json}: 過去シナリオ

出力:
  - analytics.db.scenario_evaluations 行を upsert
  - 戻り値として評価 dict を返す

採点軸:
  - hook_strength: 冒頭フックの力
  - specificity:   具体的な数字・固有名詞の密度
  - pacing:        テンポ・展開の良さ
  - cta_effectiveness: CTAの訴求力
  - wording_quality: 言い回し・表現の質
  - overall:        総合

ANTHROPIC_API_KEY 未設定時は Claude 部分をスキップしてルールベースの推定スコアを返す。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import store as analytics_store
from .. import claude_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"

# 弱点判定の閾値
WEAK_SCORE_THRESHOLD = 6.0
WEAK_DROP_THRESHOLD = 0.05  # 5%


# ---------------------------------------------------------------------
# Scenario lookup
# ---------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[ぁ-んァ-ン一-龥A-Za-z0-9]+")


def _normalize(s: str) -> str:
    if not s:
        return ""
    return "".join(_TOKEN_RE.findall(s)).lower()


def _find_scenario_json(channel_id: str, title: Optional[str]) -> Optional[Tuple[Path, Dict[str, Any]]]:
    """data/scenarios/<channel_id>/*.json から title 緩マッチ。"""
    if not title:
        return None
    base = SCENARIOS_DIR / channel_id
    if not base.exists():
        return None
    target = _normalize(title)
    if not target:
        return None
    best: Optional[Tuple[float, Path, Dict[str, Any]]] = None
    for f in base.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        cand_titles = [
            data.get("video_title"),
            data.get("title"),
        ]
        for ct in cand_titles:
            cand = _normalize(ct or "")
            if not cand:
                continue
            shared = 0
            for n in range(3, min(len(target), len(cand)) + 1):
                if target[:n] in cand or cand[:n] in target:
                    shared = n
            score = shared / max(len(target), len(cand), 1)
            if score >= 0.4 and (best is None or score > best[0]):
                best = (score, f, data)
                break
    if not best:
        return None
    return (best[1], best[2])


def _bucket_for(ratio: float) -> str:
    if ratio < 0.05:
        return "フック"
    if ratio < 0.20:
        return "導入"
    if ratio < 0.45:
        return "展開1"
    if ratio < 0.70:
        return "展開2"
    if ratio < 0.90:
        return "展開3 / オチ"
    return "CTA / クロージング"


def _scenario_sections(full_scenario: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """シナリオを位置ベースでバケット化。"""
    total = len(full_scenario)
    sections: Dict[str, List[Dict[str, Any]]] = {}
    section_ratios: Dict[str, Tuple[float, float]] = {}
    for i, line in enumerate(full_scenario):
        ratio = i / max(total - 1, 1)
        bucket = _bucket_for(ratio)
        sections.setdefault(bucket, []).append(line)
        prev = section_ratios.get(bucket)
        if prev is None:
            section_ratios[bucket] = (ratio, ratio)
        else:
            section_ratios[bucket] = (prev[0], ratio)
    out: List[Dict[str, Any]] = []
    for name, lines in sections.items():
        rng = section_ratios.get(name, (0.0, 1.0))
        out.append({"section": name, "ratio_from": round(rng[0], 3), "ratio_to": round(rng[1], 3), "lines": lines})
    return out


def _drops_for_video(video_id: str) -> List[Dict[str, float]]:
    ret = analytics_store.get_retention(video_id) or {}
    curve = ret.get("curve") or []
    if len(curve) < 2:
        return []
    drops: List[Dict[str, float]] = []
    for i in range(1, len(curve)):
        a = curve[i - 1]
        b = curve[i]
        try:
            r0 = float(a.get("ratio") or 0.0)
            r1 = float(b.get("ratio") or 0.0)
            v0 = float(a.get("audience_watch_ratio") or 0.0)
            v1 = float(b.get("audience_watch_ratio") or 0.0)
        except Exception:
            continue
        drop = v0 - v1
        if drop < WEAK_DROP_THRESHOLD:
            continue
        drops.append({
            "ratio_from": round(r0, 4),
            "ratio_to": round(r1, 4),
            "drop": round(drop, 4),
        })
    drops.sort(key=lambda d: d["drop"], reverse=True)
    return drops[:5]


def _weak_sections_from_drops(
    drops: List[Dict[str, float]],
    sections: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not drops or not sections:
        return []
    out: List[Dict[str, Any]] = []
    for d in drops:
        mid = (d["ratio_from"] + d["ratio_to"]) / 2
        # 含むセクションを探す
        match = None
        for s in sections:
            if s["ratio_from"] <= mid <= s["ratio_to"] + 1e-6:
                match = s
                break
        if not match:
            continue
        # 該当行の最初の1行をサンプリング
        sample_lines = match["lines"][:2]
        sample_text = " / ".join(
            (ln.get("text") or "")[:60]
            for ln in sample_lines
            if isinstance(ln, dict)
        )
        out.append({
            "section": match["section"],
            "ratio_from": match["ratio_from"],
            "ratio_to": match["ratio_to"],
            "drop_rate": d["drop"],
            "drop_percent": round(d["drop"] * 100, 1),
            "sample_text": sample_text,
        })
    # セクション重複を集約
    by_section: Dict[str, Dict[str, Any]] = {}
    for it in out:
        key = it["section"]
        if key not in by_section or it["drop_rate"] > by_section[key]["drop_rate"]:
            by_section[key] = it
    return list(by_section.values())


# ---------------------------------------------------------------------
# LLM layer (Claude)
# ---------------------------------------------------------------------

_SYSTEM = (
    "あなたは YouTube ゆっくり解説/教育系チャンネルのシナリオ評価コンサルタント。"
    "シナリオ原文を読み、6 軸を 1〜10 で採点した上で、"
    "離脱データとコメントを踏まえて具体的な改善提案を出してください。"
    "提案は『3 行目の導入が抽象的。〇〇のように具体数字を入れるべき』レベルまで踏み込む。"
)


def _llm_evaluate(
    video_title: str,
    sections: List[Dict[str, Any]],
    weak_sections: List[Dict[str, Any]],
    comment_summary: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    # シナリオを軽量化してプロンプトに乗せる
    section_brief: List[Dict[str, Any]] = []
    for s in sections:
        sample = []
        for ln in (s.get("lines") or [])[:6]:
            if isinstance(ln, dict):
                sp = ln.get("speaker") or ""
                tx = (ln.get("text") or "")[:100]
                sample.append({"speaker": sp, "text": tx})
        section_brief.append({
            "section": s["section"],
            "ratio_from": s["ratio_from"],
            "ratio_to": s["ratio_to"],
            "sample_lines": sample,
            "line_count": len(s.get("lines") or []),
        })

    requests_top = [
        r.get("text", "")[:120]
        for r in (comment_summary.get("requests") or [])[:8]
    ]
    sentiment = comment_summary.get("sentiment") or {}

    user = f"""# 動画タイトル
{video_title}

# セクション別シナリオ（位置: 0=冒頭, 1=ラスト）
{json.dumps(section_brief, ensure_ascii=False, indent=2)}

# 離脱が大きいセクション（retention 分析）
{json.dumps(weak_sections, ensure_ascii=False, indent=2)}

# コメント分析
- sentiment 分布: {json.dumps(sentiment, ensure_ascii=False)}
- 視聴者の要望/質問トップ: {json.dumps(requests_top, ensure_ascii=False)}

# 出力 JSON スキーマ（必須・他キー禁止）
{{
  "scores": {{
    "hook_strength": 1〜10,
    "specificity": 1〜10,
    "pacing": 1〜10,
    "cta_effectiveness": 1〜10,
    "wording_quality": 1〜10,
    "overall": 1〜10
  }},
  "weak_sections": [
    {{"section": "...", "issue": "離脱の根本原因（1〜2文）", "drop_percent": 数値}}, ...
  ],
  "improvement_suggestions": [
    "具体的な書き換え案を命令形で3〜6個。例: '導入3行目の「実はね」を、「実は人間の指は水中で5分でシワになる」のように具体数値で言い換える'", ...
  ],
  "comment_feedback": [
    {{"comment": "コメント原文", "section": "該当セクション", "action": "次回シナリオでどう取り込むか"}}, ...
  ]
}}
"""
    return claude_client.call_claude_json(
        system=_SYSTEM,
        user=user,
        temperature=0.3,
        max_tokens=2000,
        purpose="scenario_evaluation",
    )


# ---------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------

def _fallback_scores(full_scenario: List[Dict[str, Any]], weak_sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """ANTHROPIC_API_KEY が無い／呼び出し失敗時の簡易採点。具体性などをルールで評価する。"""
    if not full_scenario:
        return {
            "hook_strength": 0,
            "specificity": 0,
            "pacing": 0,
            "cta_effectiveness": 0,
            "wording_quality": 0,
            "overall": 0,
        }
    total_text = "".join(
        (ln.get("text") or "")
        for ln in full_scenario
        if isinstance(ln, dict)
    )
    nums = len(re.findall(r"\d", total_text))
    char_count = len(total_text) or 1
    specificity = min(10.0, 4.0 + nums / max(char_count / 200.0, 1.0) * 0.8)

    first_lines = " ".join(
        (ln.get("text") or "")
        for ln in full_scenario[:3]
        if isinstance(ln, dict)
    )
    hook = 5.0
    if "なぜ" in first_lines or "実は" in first_lines or "?" in first_lines or "？" in first_lines:
        hook += 1.5
    if re.search(r"\d", first_lines):
        hook += 1.0
    hook = min(10.0, hook)

    pacing = max(1.0, 10.0 - 5.0 * (len(weak_sections) / max(len(full_scenario) / 10.0, 1.0)))
    cta_lines = " ".join(
        (ln.get("text") or "")
        for ln in full_scenario[-5:]
        if isinstance(ln, dict)
    )
    cta = 5.0
    for kw in ("登録", "コメント", "高評価", "通知", "あなたは"):
        if kw in cta_lines:
            cta += 1.0
    cta = min(10.0, cta)

    wording = 6.0  # 文章の質はルールでは判断しにくい
    overall = round((hook * 0.25 + specificity * 0.2 + pacing * 0.2 + cta * 0.15 + wording * 0.2), 2)
    return {
        "hook_strength": round(hook, 2),
        "specificity": round(specificity, 2),
        "pacing": round(pacing, 2),
        "cta_effectiveness": round(cta, 2),
        "wording_quality": wording,
        "overall": overall,
    }


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def evaluate_video(
    *,
    video_id: str,
    channel_id: str,
    use_gpt: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """指定動画のシナリオを評価して analytics.db に保存する。

    既に評価済みで force=False ならスキップ。
    """
    if not force:
        existing = analytics_store.get_scenario_evaluation(video_id)
        if existing:
            return {"video_id": video_id, "skipped": True, "reason": "already_evaluated", "evaluation": existing}

    metrics_list = analytics_store.list_video_metrics(channel_id, limit=200)
    metric = next((m for m in metrics_list if m.get("video_id") == video_id), None)
    if not metric:
        return {"video_id": video_id, "skipped": True, "reason": "no_metric"}

    video_title = metric.get("title") or ""

    sc_match = _find_scenario_json(channel_id, video_title)
    if not sc_match:
        return {"video_id": video_id, "skipped": True, "reason": "no_scenario_match", "video_title": video_title}
    sc_path, sc_data = sc_match
    full_scenario = sc_data.get("full_scenario") or sc_data.get("full") or []
    if not full_scenario:
        return {"video_id": video_id, "skipped": True, "reason": "empty_scenario"}

    sections = _scenario_sections(full_scenario)
    drops = _drops_for_video(video_id)
    weak = _weak_sections_from_drops(drops, sections)

    comment_summary = analytics_store.comment_summary_for_video(video_id)

    scores: Optional[Dict[str, Any]] = None
    improvement: List[str] = []
    comment_feedback: List[Dict[str, Any]] = []
    weak_sections_final = weak[:]
    llm_used = False

    if use_gpt and claude_client.has_api_key():
        llm = _llm_evaluate(video_title, sections, weak, comment_summary)
        if llm:
            llm_used = True
            scores = llm.get("scores") or {}
            if llm.get("weak_sections"):
                weak_sections_final = llm["weak_sections"]
            improvement = llm.get("improvement_suggestions") or []
            comment_feedback = llm.get("comment_feedback") or []

    if scores is None:
        scores = _fallback_scores(full_scenario, weak)

    # 上書きストア
    def _g(k: str) -> float:
        try:
            return float(scores.get(k) or 0)
        except Exception:
            return 0.0

    record = analytics_store.upsert_scenario_evaluation(
        video_id=video_id,
        channel_id=channel_id,
        hook_strength=_g("hook_strength"),
        specificity=_g("specificity"),
        pacing=_g("pacing"),
        cta_effectiveness=_g("cta_effectiveness"),
        wording_quality=_g("wording_quality"),
        overall=_g("overall"),
        weak_sections=weak_sections_final,
        improvement_suggestions=improvement,
        comment_feedback=comment_feedback,
        scenario_path=str(sc_path),
        video_title=video_title,
    )
    record["gpt_used"] = llm_used  # backward-compatible flag (now indicates Claude usage)
    record["llm_used"] = llm_used
    return record


def evaluate_channel(
    channel_id: str,
    *,
    max_videos: int = 20,
    use_gpt: bool = True,
    only_new: bool = True,
) -> Dict[str, Any]:
    """チャンネルの動画を順次評価。`only_new=True` なら既存評価をスキップ。"""
    metrics = analytics_store.list_video_metrics(channel_id, limit=max_videos)
    results: List[Dict[str, Any]] = []
    evaluated = 0
    skipped = 0
    for m in metrics:
        vid = m.get("video_id")
        if not vid:
            continue
        try:
            res = evaluate_video(
                video_id=vid,
                channel_id=channel_id,
                use_gpt=use_gpt,
                force=not only_new,
            )
            if res.get("skipped"):
                skipped += 1
            else:
                evaluated += 1
            results.append(res)
        except Exception as e:
            results.append({"video_id": vid, "error": str(e)})
            skipped += 1
    return {
        "channel_id": channel_id,
        "evaluated": evaluated,
        "skipped": skipped,
        "results": results,
        "ran_at": int(time.time()),
    }


def aggregate_weak_patterns(channel_id: str, *, recent: int = 10) -> Dict[str, Any]:
    """直近 N 件の評価から弱点パターンを集計する。
    `scenario_feedback.build_analytics_addendum` から呼ばれる想定。"""
    evals = analytics_store.list_scenario_evaluations(channel_id, limit=recent)
    if not evals:
        return {"count": 0}
    avg: Dict[str, float] = {k: 0.0 for k in (
        "hook_strength", "specificity", "pacing",
        "cta_effectiveness", "wording_quality", "overall",
    )}
    n = 0
    weak_section_counter: Dict[str, int] = {}
    suggestions_pool: List[str] = []
    for e in evals:
        n += 1
        for k in avg:
            try:
                avg[k] += float(e.get(k) or 0)
            except Exception:
                pass
        for w in (e.get("weak_sections") or []):
            sec = w.get("section") if isinstance(w, dict) else None
            if sec:
                weak_section_counter[sec] = weak_section_counter.get(sec, 0) + 1
        for s in (e.get("improvement_suggestions") or [])[:2]:
            if isinstance(s, str):
                suggestions_pool.append(s.strip())
    if n == 0:
        return {"count": 0}
    for k in avg:
        avg[k] = round(avg[k] / n, 2)
    weak_sorted = sorted(weak_section_counter.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "count": n,
        "averages": avg,
        "weak_sections": [
            {"section": s, "frequency": c, "frequency_ratio": round(c / n, 2)}
            for s, c in weak_sorted[:5]
        ],
        "recent_suggestions": suggestions_pool[:6],
    }
