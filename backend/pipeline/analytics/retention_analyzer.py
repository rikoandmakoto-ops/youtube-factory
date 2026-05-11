"""
視聴維持率カーブ分析エンジン — 各動画の retention カーブから離脱ポイントを検出し、
シナリオの該当シーンを推定して Claude (Sonnet 4) に改善提案を作らせる。

入力: analytics SQLite の retention_curve / video_metrics
出力: data/analytics/retention_insights.json（チャンネル別）

「離脱ポイント」の定義:
  - audience_watch_ratio の前→後の差分（負の傾き）の大きさで降順ソート
  - 上位 N 個 (N=3) を「主要離脱点」として返す
  - 連続したポイント間（intro/early/middle/late/ending）にバケット分け

シナリオとの照合:
  - video_metrics.title と data/scenarios/{channel_id}/*.json の title を緩く突合
  - マッチしたら full_scenario のうち drop_ratio に対応する行を抽出

Claude は集約サマリから「冒頭フック強化」「中盤テンポ」「結論前倒し」等の具体提案を JSON で返す。
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


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "analytics"
OUTPUT_PATH = OUTPUT_DIR / "retention_insights.json"
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"


# ---------------------------------------------------------------------
# Curve math
# ---------------------------------------------------------------------

def _bucket_for(ratio: float) -> str:
    if ratio < 0.15:
        return "intro"        # 冒頭フック領域
    if ratio < 0.40:
        return "early"        # 前半（導入→本題）
    if ratio < 0.70:
        return "middle"       # 中盤
    if ratio < 0.90:
        return "late"         # 終盤・まとめ前
    return "ending"           # ラスト（CTA 近辺）


def _detect_drop_points(
    curve: List[Dict[str, float]],
    *,
    top_n: int = 3,
    min_drop: float = 0.02,
) -> List[Dict[str, Any]]:
    """カーブの連続点間の負の差分のうち、降下幅が大きい順に top_n 件返す。

    return: [{"ratio_from","ratio_to","drop","bucket"}]
    """
    if len(curve) < 2:
        return []
    drops: List[Dict[str, Any]] = []
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
        delta = v0 - v1
        if delta < min_drop:
            continue
        drops.append(
            {
                "ratio_from": round(r0, 4),
                "ratio_to": round(r1, 4),
                "drop": round(delta, 4),
                "bucket": _bucket_for(r0),
                "audience_after": round(v1, 4),
            }
        )
    drops.sort(key=lambda x: x["drop"], reverse=True)
    return drops[:top_n]


def _avg_drop_by_bucket(curve: List[Dict[str, float]]) -> Dict[str, float]:
    """バケットごとの平均離脱率（v0 - v1）。"""
    bucket_drops: Dict[str, List[float]] = {}
    if len(curve) < 2:
        return {}
    for i in range(1, len(curve)):
        a = curve[i - 1]
        b = curve[i]
        try:
            r0 = float(a.get("ratio") or 0.0)
            v0 = float(a.get("audience_watch_ratio") or 0.0)
            v1 = float(b.get("audience_watch_ratio") or 0.0)
        except Exception:
            continue
        bucket = _bucket_for(r0)
        bucket_drops.setdefault(bucket, []).append(v0 - v1)
    return {b: round(sum(vs) / len(vs), 4) for b, vs in bucket_drops.items() if vs}


# ---------------------------------------------------------------------
# Scenario matching
# ---------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[ぁ-んァ-ン一-龥A-Za-z0-9]+")


def _normalize(s: str) -> str:
    if not s:
        return ""
    return "".join(_TOKEN_RE.findall(s)).lower()


def _find_scenario_for(channel_id: str, video_title: Optional[str]) -> Optional[Dict[str, Any]]:
    """video の title から data/scenarios/{channel_id}/*.json を緩くマッチして返す。"""
    if not video_title:
        return None
    base = SCENARIOS_DIR / channel_id
    if not base.exists():
        return None
    target = _normalize(video_title)
    if not target:
        return None

    best: Optional[Tuple[float, Path]] = None
    for f in base.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        cand_title = ""
        if isinstance(data, dict):
            cand_title = data.get("title") or ""
        cand = _normalize(cand_title)
        if not cand:
            continue
        # Jaccard 風スコア（共通文字種の長さ / max長）
        shared = 0
        for n in range(3, min(len(target), len(cand)) + 1):
            if target[:n] in cand or cand[:n] in target:
                shared = n
        score = shared / max(len(target), len(cand), 1)
        if score >= 0.4 and (best is None or score > best[0]):
            best = (score, f)

    if not best:
        return None
    try:
        return json.loads(best[1].read_text(encoding="utf-8"))
    except Exception:
        return None


def _scene_at_ratio(scenario: Dict[str, Any], ratio: float) -> Optional[Dict[str, Any]]:
    """ratio (0..1) に対応する full_scenario の行を均等割で推定して返す。

    return: {"index": int, "speaker": str?, "text": str, "mood": str?}
    """
    if not isinstance(scenario, dict):
        return None
    lines = scenario.get("full_scenario") or []
    text_lines = [l for l in lines if isinstance(l, dict) and l.get("text")]
    if not text_lines:
        return None
    idx = max(0, min(len(text_lines) - 1, int(round(ratio * (len(text_lines) - 1)))))
    line = text_lines[idx]
    return {
        "index": idx,
        "speaker": line.get("speaker"),
        "text": (line.get("text") or "")[:120],
        "mood": line.get("mood"),
    }


# ---------------------------------------------------------------------
# LLM layer (Claude)
# ---------------------------------------------------------------------

_LLM_SYSTEM = (
    "あなたは YouTube 動画の視聴維持率を改善するコンサルタントです。"
    "離脱点の発生位置と該当シーンのテキストから、次回シナリオで適用すべき"
    "具体的な改善ルールを JSON で返してください。"
    "推測ではなく与えられた素材に基づいて回答してください。"
)


def _llm_suggest(channel_id: str, per_video: List[Dict[str, Any]], aggregate: Dict[str, float]) -> Optional[Dict[str, Any]]:
    user_msg = f"""# チャンネル: {channel_id}
# バケット別の平均離脱率（v0-v1 の平均）
{json.dumps(aggregate, ensure_ascii=False)}

# 動画ごとの上位離脱点（最大10動画）
{json.dumps(per_video[:10], ensure_ascii=False)}

# 出力 JSON スキーマ（必須・他キー禁止）
{{
  "diagnosis": ["どのバケットで離脱が大きいかの所見。3〜5個", "..."],
  "retention_tips": ["次回シナリオに反映する具体的なルール（命令形・3〜6個）", "..."],
  "priority_section": "intro|early|middle|late|ending のいずれか1つ。最も改善優先度が高いバケット"
}}
"""
    return claude_client.call_claude_json(
        system=_LLM_SYSTEM,
        user=user_msg,
        temperature=0.3,
        max_tokens=2000,
        channel_id=channel_id,
        purpose="retention_analysis",
    )


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def analyze_channel(
    channel_id: str,
    *,
    max_videos: int = 20,
    use_gpt: bool = True,
) -> Dict[str, Any]:
    """指定チャンネルの維持率カーブを分析して JSON に保存。"""
    metrics = analytics_store.list_video_metrics(
        channel_id, limit=max_videos, latest_per_video=True
    )
    if not metrics:
        result = {
            "channel_id": channel_id,
            "skipped": True,
            "reason": "no video_metrics — run /api/analytics/sync first",
            "generated_at": int(time.time()),
        }
        _save(channel_id, result)
        return result

    per_video: List[Dict[str, Any]] = []
    aggregate_drops: Dict[str, List[float]] = {}
    for m in metrics:
        vid = m.get("video_id")
        if not vid:
            continue
        ret = analytics_store.get_retention(vid)
        if not ret:
            continue
        curve = ret.get("curve") or []
        if len(curve) < 3:
            continue
        drops = _detect_drop_points(curve)
        bucket_avg = _avg_drop_by_bucket(curve)
        for b, v in bucket_avg.items():
            aggregate_drops.setdefault(b, []).append(v)

        scenario = _find_scenario_for(channel_id, m.get("title"))
        annotated_drops: List[Dict[str, Any]] = []
        for d in drops:
            entry = dict(d)
            if scenario:
                scene = _scene_at_ratio(scenario, (d["ratio_from"] + d["ratio_to"]) / 2.0)
                if scene:
                    entry["scenario_line"] = scene
            annotated_drops.append(entry)

        per_video.append(
            {
                "video_id": vid,
                "title": m.get("title"),
                "avg_view_percentage": m.get("avg_view_percentage"),
                "drops": annotated_drops,
                "matched_scenario_title": scenario.get("title") if scenario else None,
            }
        )

    aggregate = {
        b: round(sum(vs) / len(vs), 4) for b, vs in aggregate_drops.items() if vs
    }

    if not per_video:
        result = {
            "channel_id": channel_id,
            "skipped": True,
            "reason": "no retention curves saved — sync with fetch_retention_for > 0",
            "generated_at": int(time.time()),
        }
        _save(channel_id, result)
        return result

    result: Dict[str, Any] = {
        "channel_id": channel_id,
        "generated_at": int(time.time()),
        "analyzed_videos": len(per_video),
        "aggregate_drops_by_bucket": aggregate,
        "per_video": per_video,
    }

    llm = _llm_suggest(channel_id, per_video, aggregate) if use_gpt else None
    if llm:
        result["gpt_insights"] = llm  # 既存フィールド名を維持（中身は Claude による生成）
    else:
        result["gpt_insights"] = None
        if use_gpt and not claude_client.has_api_key():
            result["gpt_skipped_reason"] = "ANTHROPIC_API_KEY 未設定"

    _save(channel_id, result)
    return result


def _save(channel_id: str, payload: Dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    current: Dict[str, Any] = {}
    if OUTPUT_PATH.exists():
        try:
            current = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            if not isinstance(current, dict):
                current = {}
        except Exception:
            current = {}
    current[channel_id] = payload
    OUTPUT_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_insights(channel_id: str) -> Optional[Dict[str, Any]]:
    if not OUTPUT_PATH.exists():
        return None
    try:
        data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data.get(channel_id)
