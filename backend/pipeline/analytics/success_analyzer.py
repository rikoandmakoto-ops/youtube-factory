"""
成功パターン分析エンジン — チャンネルの「伸びた動画」の共通パターンを抽出。

入力: analytics SQLite の video_metrics（直近スナップショット）
出力: data/analytics/success_patterns.json（チャンネル別）

「成功動画」の定義:
  1. データ十分（>= 8 件）: CTR が上位 25% かつ avg_view_percentage が上位 25%
  2. データ少（4..7 件）: views 上位 33%
  3. データ極小（< 4 件）: 全件を success として扱う（ヒント程度のフィードバック）

GPT-4o で以下をまとめる:
  - title_patterns: タイトル構成の傾向（疑問形 / 数字 / 文字数 / 共通フレーズ）
  - theme_trends: テーマ・カテゴリ傾向
  - description_traits: 説明文の特徴（不明なら省略）
  - posting_time: 投稿時間帯の傾向

OPENAI_API_KEY 未設定なら GPT 部分はスキップし、ルールベース集計のみ返す。
"""

from __future__ import annotations

import json
import os
import re
import statistics
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import store as analytics_store


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "analytics"
OUTPUT_PATH = OUTPUT_DIR / "success_patterns.json"

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
GPT_MODEL = "gpt-4o"


# ---------------------------------------------------------------------
# Success picker
# ---------------------------------------------------------------------

def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = max(0, min(len(sorted_vals) - 1, int(round((pct / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def _classify(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """video_metrics 行リストを success / others に分類。

    フォールバック戦略は冒頭の docstring 参照。
    """
    n = len(items)
    if n == 0:
        return {"success": [], "others": []}

    if n < 4:
        return {"success": list(items), "others": []}

    if n < 8:
        # views ベースの上位 33%
        sorted_items = sorted(items, key=lambda x: int(x.get("views") or 0), reverse=True)
        cutoff = max(1, n // 3)
        return {"success": sorted_items[:cutoff], "others": sorted_items[cutoff:]}

    ctrs = [float(it.get("ctr") or 0.0) for it in items]
    retentions = [float(it.get("avg_view_percentage") or 0.0) for it in items]
    ctr_cut = _percentile(ctrs, 75)
    ret_cut = _percentile(retentions, 75)

    success: List[Dict[str, Any]] = []
    others: List[Dict[str, Any]] = []
    for it in items:
        ctr = float(it.get("ctr") or 0.0)
        ret = float(it.get("avg_view_percentage") or 0.0)
        if ctr >= ctr_cut and ret >= ret_cut:
            success.append(it)
        else:
            others.append(it)

    # 上 25% × 上 25% は理論上 ~6% しか残らない。0件なら views フォールバックに切替。
    if not success:
        sorted_items = sorted(items, key=lambda x: int(x.get("views") or 0), reverse=True)
        cutoff = max(1, n // 4)
        success = sorted_items[:cutoff]
        others = sorted_items[cutoff:]
    return {"success": success, "others": others}


# ---------------------------------------------------------------------
# Rule-based feature extraction（GPT が無くても返せる素材）
# ---------------------------------------------------------------------

_QUESTION_MARKS = ("？", "?", "なぜ", "なんで", "どうして", "知ってる", "本当に")
_NUMBER_RE = re.compile(r"[0-9０-９]+")


def _title_features(titles: List[str]) -> Dict[str, Any]:
    if not titles:
        return {
            "count": 0,
            "avg_length": 0.0,
            "question_ratio": 0.0,
            "number_ratio": 0.0,
            "samples": [],
        }
    lengths = [len(t) for t in titles]
    q = sum(1 for t in titles if any(k in t for k in _QUESTION_MARKS))
    nums = sum(1 for t in titles if _NUMBER_RE.search(t))
    return {
        "count": len(titles),
        "avg_length": round(statistics.fmean(lengths), 1),
        "median_length": int(statistics.median(lengths)),
        "question_ratio": round(q / len(titles), 2),
        "number_ratio": round(nums / len(titles), 2),
        "samples": titles[:10],
    }


def _posting_time_features(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    hours: List[int] = []
    weekdays: List[int] = []
    for it in items:
        pub = it.get("published_at")
        if not pub:
            continue
        try:
            # ISO形式（YouTubeは "Z" 付き）
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            continue
        hours.append(dt.hour)
        weekdays.append(dt.weekday())

    def _top(values: List[int]) -> Optional[int]:
        if not values:
            return None
        counts: Dict[int, int] = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        return max(counts.items(), key=lambda kv: kv[1])[0]

    return {
        "top_hour_utc": _top(hours),
        "top_weekday": _top(weekdays),  # 0=Mon
        "n": len(hours),
    }


def _avg_metrics(items: List[Dict[str, Any]]) -> Dict[str, float]:
    if not items:
        return {"views": 0.0, "ctr": 0.0, "avg_view_percentage": 0.0}
    return {
        "views": round(statistics.fmean(int(it.get("views") or 0) for it in items), 1),
        "ctr": round(statistics.fmean(float(it.get("ctr") or 0.0) for it in items), 4),
        "avg_view_percentage": round(
            statistics.fmean(float(it.get("avg_view_percentage") or 0.0) for it in items), 2
        ),
    }


# ---------------------------------------------------------------------
# GPT layer
# ---------------------------------------------------------------------

_GPT_SYSTEM = (
    "あなたは YouTube 動画分析の専門家です。"
    "成功した動画群と通常動画群のメトリクス・タイトルを比較し、"
    "次回の動画制作で再現すべき具体的なパターンを JSON で抽出します。"
    "推測を最小化し、与えられた素材のみに基づいて結論を述べてください。"
)


def _call_openai(messages: List[Dict[str, str]], *, model: str = GPT_MODEL) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
    )
    req = urllib.request.Request(
        OPENAI_CHAT_URL,
        data=payload.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"⚠️ success_analyzer GPT call failed: {e}")
        return None


def _gpt_summarize(
    channel_id: str,
    success: List[Dict[str, Any]],
    others: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """GPT-4o に成功 vs 通常を比較させて構造化サマリを返してもらう。"""
    success_block = json.dumps(
        [
            {
                "title": it.get("title"),
                "views": it.get("views"),
                "ctr": round(float(it.get("ctr") or 0), 4),
                "avg_view_percentage": round(float(it.get("avg_view_percentage") or 0), 2),
                "published_at": it.get("published_at"),
            }
            for it in success[:15]
        ],
        ensure_ascii=False,
    )
    others_block = json.dumps(
        [
            {
                "title": it.get("title"),
                "views": it.get("views"),
                "ctr": round(float(it.get("ctr") or 0), 4),
            }
            for it in others[:15]
        ],
        ensure_ascii=False,
    )

    user_msg = f"""# チャンネル: {channel_id}
# 成功動画（CTR & 視聴維持率が上位、または再生数上位）
{success_block}

# 通常動画
{others_block}

# 出力 JSON スキーマ（必須・他のキーは入れない）
{{
  "title_patterns": ["具体的なタイトル構成の特徴（数字・疑問形・文字数など）", "..."],
  "theme_trends": ["伸びているテーマ・カテゴリの傾向", "..."],
  "description_traits": ["説明文に共通する特徴。情報不足ならその旨を1要素だけ"],
  "posting_time_insight": "投稿時間帯の傾向を1行で（不明ならその旨を書く）",
  "actionable_recommendations": ["次回のシナリオ生成時に守るべき具体ルール（命令形・3〜6個）", "..."]
}}
"""
    return _call_openai(
        [
            {"role": "system", "content": _GPT_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
    )


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def analyze_channel(
    channel_id: str,
    *,
    limit: int = 200,
    use_gpt: bool = True,
) -> Dict[str, Any]:
    """指定チャンネルの成功パターンを抽出して JSON に保存。

    SQLite に動画メトリクスが 1 件も無ければ skipped を返す。
    """
    items = analytics_store.list_video_metrics(
        channel_id, limit=limit, latest_per_video=True
    )
    if not items:
        result = {
            "channel_id": channel_id,
            "skipped": True,
            "reason": "no video_metrics in store — run /api/analytics/sync first",
            "generated_at": int(time.time()),
        }
        _save(channel_id, result)
        return result

    buckets = _classify(items)
    success_titles = [it.get("title") for it in buckets["success"] if it.get("title")]
    others_titles = [it.get("title") for it in buckets["others"] if it.get("title")]

    result: Dict[str, Any] = {
        "channel_id": channel_id,
        "generated_at": int(time.time()),
        "sample_size": {
            "total": len(items),
            "success": len(buckets["success"]),
            "others": len(buckets["others"]),
        },
        "metrics": {
            "success_avg": _avg_metrics(buckets["success"]),
            "others_avg": _avg_metrics(buckets["others"]),
        },
        "title_features": {
            "success": _title_features(success_titles),
            "others": _title_features(others_titles),
        },
        "posting_time": _posting_time_features(buckets["success"]),
        "success_videos": [
            {
                "video_id": it.get("video_id"),
                "title": it.get("title"),
                "views": it.get("views"),
                "ctr": it.get("ctr"),
                "avg_view_percentage": it.get("avg_view_percentage"),
            }
            for it in buckets["success"][:20]
        ],
    }

    gpt = _gpt_summarize(channel_id, buckets["success"], buckets["others"]) if use_gpt else None
    if gpt:
        result["gpt_insights"] = gpt
    else:
        result["gpt_insights"] = None
        if use_gpt and not os.environ.get("OPENAI_API_KEY", "").strip():
            result["gpt_skipped_reason"] = "OPENAI_API_KEY 未設定"

    _save(channel_id, result)
    return result


def _save(channel_id: str, payload: Dict[str, Any]) -> None:
    """channel_id ごとの結果を success_patterns.json にマージ保存。"""
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


def load_patterns(channel_id: str) -> Optional[Dict[str, Any]]:
    """保存済みの成功パターンを返す。未生成なら None。"""
    if not OUTPUT_PATH.exists():
        return None
    try:
        data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data.get(channel_id)
