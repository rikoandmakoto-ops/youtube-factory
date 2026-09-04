"""optimization_policy — 「何を改善指標にするか」を1箇所で決める。

背景（2026-09-04 のユーザー決定）:
    改善の判断軸が **維持率（retention）・高評価率・再生数** に分散していて、
    どの施策も「別の指標では良くなった」と言い訳ができる状態だった。実測では

      - 維持率と登録転換の関係は ch ごとに符号が逆（yokai 3.00倍 / scp 0.95倍）
      - 2ch-matome は維持率52.7%＝2位・平均再生912＝3位なのに登録/千 0.16 で最下位
      - clip-lab は平均再生4,136で断トツ首位なのに登録0人

    つまり維持率・再生数は**それ単体では事業の良し悪しを表さない**。
    判断軸を **登録者/1000再生（subs_per_1000_views）** に一本化し、
    維持率は「見るだけ・判断には使わない」参考値へ降格する。

チャンネル JSON のスキーマ:

    "optimization": {
      "primary_metric": "subs_per_1000_views",
      "decision_metrics": ["subs_per_1000_views"],
      "reference_only_metrics": ["retention", "avg_view_percentage", "views"]
    }

    未設定のチャンネルは既定（下の DEFAULT_POLICY）が適用される。
    ＝ 新しいチャンネルを足しても、写し忘れで勝手に維持率駆動へ戻らない。

使い方:
    if not optimization_policy.is_decision_metric(ch_raw, "retention"):
        # 維持率をシナリオ書き換えの根拠に使わない
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PRIMARY_METRIC = "subs_per_1000_views"

# 未設定チャンネルに適用される既定。ここが「一本化」の実体。
DEFAULT_POLICY: Dict[str, Any] = {
    "primary_metric": PRIMARY_METRIC,
    "decision_metrics": [PRIMARY_METRIC],
    "reference_only_metrics": [
        "retention", "avg_view_percentage", "views", "avg_views",
        "watch_time", "ctr", "impressions",
    ],
}

# 表記ゆれの吸収。呼び出し側が "維持率" でも "avg_view_percentage" でも通るように。
_ALIASES = {
    "retention": "retention",
    "retention_rate": "retention",
    "avg_view_percentage": "retention",
    "average_view_percentage": "retention",
    "維持率": "retention",
    "視聴維持率": "retention",
    "subs_per_1000_views": PRIMARY_METRIC,
    "subs_per_1k": PRIMARY_METRIC,
    "subscribers_per_1000_views": PRIMARY_METRIC,
    "登録/1000再生": PRIMARY_METRIC,
    "登録転換": PRIMARY_METRIC,
    "views": "views",
    "再生数": "views",
    "like_rate": "like_rate",
    "高評価率": "like_rate",
}


def canonical(metric: str) -> str:
    m = str(metric or "").strip()
    return _ALIASES.get(m, _ALIASES.get(m.lower(), m.lower()))


def policy_of(channel_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """チャンネルの optimization ポリシー（未設定なら既定）。"""
    raw = (channel_dict or {}).get("optimization")
    if not isinstance(raw, dict):
        return dict(DEFAULT_POLICY)
    merged = dict(DEFAULT_POLICY)
    merged.update({k: v for k, v in raw.items() if v is not None})
    return merged


def primary_metric(channel_dict: Optional[Dict[str, Any]] = None) -> str:
    return canonical(policy_of(channel_dict).get("primary_metric") or PRIMARY_METRIC)


def decision_metrics(channel_dict: Optional[Dict[str, Any]] = None) -> List[str]:
    raw = policy_of(channel_dict).get("decision_metrics") or [PRIMARY_METRIC]
    if isinstance(raw, str):
        raw = [raw]
    return [canonical(m) for m in raw]


def is_decision_metric(channel_dict: Optional[Dict[str, Any]], metric: str) -> bool:
    """`metric` をコンフィグ変更・シナリオ書き換えの根拠に使ってよいか。"""
    return canonical(metric) in decision_metrics(channel_dict)


def subs_per_1000_views(subscribers_gained: Any, views: Any) -> Optional[float]:
    """登録者/1000再生。再生が0なら None（0.0 ではない — 未計測と0は違う）。"""
    try:
        v = float(views or 0)
        s = float(subscribers_gained or 0)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return round(s * 1000.0 / v, 3)


def load_channel_raw(channel_id: str) -> Dict[str, Any]:
    """data/channels/<id>.json を読む（channel_dict を持てない呼び出し元向け）。"""
    if not channel_id:
        return {}
    path = (Path(__file__).resolve().parent.parent.parent
            / "data" / "channels" / f"{channel_id}.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def channel_uses_metric(channel_id: str, metric: str) -> bool:
    """channel_id だけ分かっている場所から判断軸を問い合わせる。"""
    return is_decision_metric(load_channel_raw(channel_id), metric)


def reference_note(metric: str) -> str:
    """レポートに書く注記。判断に使わない指標であることを明示する。"""
    return (f"（{metric} は参考値。判断軸は "
            f"{PRIMARY_METRIC}＝登録者/1000再生 に一本化）")
