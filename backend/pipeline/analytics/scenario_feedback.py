"""
シナリオ生成プロンプトへの分析フィードバック注入。

success_analyzer / retention_analyzer / コメントの top requests を読み取り、
ScenarioGenerator が GPT に渡す追加指示テキストを組み立てる。

データ未生成・空のセクションは黙って省略する（プロンプトを汚さない）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import retention_analyzer, store as analytics_store, success_analyzer


_MAX_BULLETS = 6


def _bullets(items: List[Any], *, prefix: str = "  - ", limit: int = _MAX_BULLETS) -> List[str]:
    out: List[str] = []
    for it in items[:limit]:
        if not it:
            continue
        text = str(it).strip()
        if text:
            out.append(f"{prefix}{text}")
    return out


def _collect_top_requests(channel_id: str, *, max_videos: int = 10, top_n: int = 5) -> List[str]:
    """直近動画のコメント分析から「リクエスト」テキストを集めて上位を返す。"""
    metrics = analytics_store.list_video_metrics(
        channel_id, limit=max_videos, latest_per_video=True
    )
    seen: Dict[str, int] = {}
    for m in metrics:
        vid = m.get("video_id")
        if not vid:
            continue
        summary = analytics_store.comment_summary_for_video(vid)
        for req in summary.get("requests") or []:
            text = (req.get("text") or "").strip()
            if not text:
                continue
            # 80字に丸めて重複を抑える
            key = text[:80]
            seen[key] = seen.get(key, 0) + 1
    ranked = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in ranked[:top_n]]


def build_analytics_addendum(channel_id: str) -> Optional[str]:
    """ScenarioGenerator に追加する「分析フィードバック」テキストを返す。

    全セクションが空なら None を返し、generator 側で no-op になる。
    """
    sections: List[str] = []

    patterns = success_analyzer.load_patterns(channel_id)
    if patterns and not patterns.get("skipped"):
        gpt = patterns.get("gpt_insights") or {}
        block: List[str] = []
        if gpt.get("actionable_recommendations"):
            block.append("**過去の成功パターン（必ず取り込む）**:")
            block.extend(_bullets(gpt["actionable_recommendations"]))
        elif gpt.get("title_patterns") or gpt.get("theme_trends"):
            if gpt.get("title_patterns"):
                block.append("**過去の成功タイトル傾向**:")
                block.extend(_bullets(gpt["title_patterns"]))
            if gpt.get("theme_trends"):
                block.append("**伸びているテーマ傾向**:")
                block.extend(_bullets(gpt["theme_trends"]))
        else:
            # GPT 未実行でもタイトル特徴量だけは入れる
            tf = (patterns.get("title_features") or {}).get("success") or {}
            samples = tf.get("samples") or []
            if samples:
                block.append("**過去の成功動画タイトル例**:")
                block.extend(_bullets(samples, limit=4))
        if block:
            sections.append("\n".join(block))

    insights = retention_analyzer.load_insights(channel_id)
    if insights and not insights.get("skipped"):
        gpt = insights.get("gpt_insights") or {}
        block = []
        if gpt.get("retention_tips"):
            block.append("**視聴維持率の改善方針（必ず取り込む）**:")
            block.extend(_bullets(gpt["retention_tips"]))
            prio = gpt.get("priority_section")
            if prio:
                block.append(f"  - 最優先強化バケット: **{prio}**（このバケットの離脱を減らす構成にすること）")
        else:
            agg = insights.get("aggregate_drops_by_bucket") or {}
            if agg:
                worst = max(agg.items(), key=lambda kv: kv[1])
                block.append(
                    f"**視聴維持率の弱点**: 最も離脱が大きいバケットは `{worst[0]}` "
                    f"(平均離脱 {worst[1]:.3f})。該当区間の構成を強化すること。"
                )
        if block:
            sections.append("\n".join(block))

    try:
        requests = _collect_top_requests(channel_id)
    except Exception:
        requests = []
    if requests:
        block = ["**視聴者からのリクエスト（コメント分析より）**:"]
        block.extend(_bullets(requests, limit=5))
        block.append("  - 上記に該当するテーマ・切り口を可能な範囲で本シナリオに反映すること。")
        sections.append("\n".join(block))

    # Phase D (A4): 直近のシナリオ評価から弱点パターンを抽出
    try:
        from . import scenario_evaluator
        weak = scenario_evaluator.aggregate_weak_patterns(channel_id, recent=5)
    except Exception:
        weak = {"count": 0}
    if weak.get("count", 0) > 0:
        avg = weak.get("averages") or {}
        block = ["**直近シナリオ評価から判明した弱点（必ず克服）**:"]
        # スコアが低い軸を抽出（10段階で 6.0 未満）
        low_axes = sorted(
            ((k, v) for k, v in avg.items() if k != "overall" and v < 6.0),
            key=lambda kv: kv[1],
        )
        if low_axes:
            label_map = {
                "hook_strength": "冒頭フック",
                "specificity": "具体性（数字・固有名詞）",
                "pacing": "テンポ・展開",
                "cta_effectiveness": "CTA訴求力",
                "wording_quality": "言い回し",
            }
            for k, v in low_axes[:3]:
                label = label_map.get(k, k)
                block.append(
                    f"  - 過去{weak['count']}本で {label} のスコアが平均{v:.1f}/10。"
                    f"今回必ず改善する。"
                )
                if k == "specificity":
                    block.append("    - 各展開セクションに具体数字・固有名詞・年号を最低1つずつ含めること")
                elif k == "hook_strength":
                    block.append("    - 冒頭5秒に意外な事実・数字・問いかけを必ず置く")
                elif k == "pacing":
                    block.append("    - 同じトピックを8行以上引き伸ばさず、3〜5行で次に進む")
                elif k == "cta_effectiveness":
                    block.append("    - 結びで具体的なアクション（コメントで問う／類似動画予告）を明示")
                elif k == "wording_quality":
                    block.append("    - 抽象語（『すごい』『面白い』）を避け、感覚を呼び起こす描写に置き換える")
        weak_sections = weak.get("weak_sections") or []
        if weak_sections:
            block.append(
                "  - 頻繁に離脱が出ているセクション: "
                + " / ".join(
                    f"**{w['section']}** ({int(w['frequency_ratio'] * 100)}%)"
                    for w in weak_sections[:3]
                )
            )
            block.append("    - 該当区間は構成を圧縮し、新しい刺激（問い／意外な事実／場面転換）を入れる")
        suggestions = weak.get("recent_suggestions") or []
        if suggestions:
            block.append("  - 直近の改善提案を反映:")
            block.extend(_bullets(suggestions, prefix="    - ", limit=4))
        sections.append("\n".join(block))

    if not sections:
        return None

    header = "## 分析データに基づく改善指示（必ず守る）"
    footer = (
        "\n上記は YouTube Analytics + コメント分析の実データから抽出された方針です。"
        "title / thumb_info / full_scenario の冒頭5行に明確に反映してください。"
    )
    return header + "\n\n" + "\n\n".join(sections) + footer
