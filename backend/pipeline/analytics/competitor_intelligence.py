"""
CompetitorIntelligence — competitor_analyses テーブルに溜まっている週次の競合分析を
シナリオ生成・ネタ選定に注入できる形に集約する。

設計方針:
  - DB に新しいデータは作らない。`competitor_analyzer.latest_analyses()` を読むだけ。
  - 全ての関数は competitor_analyses が空でも安全に動く（空の dict / None / 空文字列）。
  - 既存の ScenarioGenerator（プロンプト addendum 方式 / scenario_feedback.py 参照）と
    同じパターンで `build_competitor_addendum()` を提供する。

公開関数:
  - build_competitor_context(channel_id) -> dict
  - build_competitor_addendum(channel_id) -> Optional[str]
  - competitor_video_titles(channel_id) -> List[str]
  - theme_overlap_score(title, competitor_titles) -> float
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple


_MAX_KEYWORDS = 12
_MAX_HOOKS = 6
_MAX_HOT_TOPICS = 10
_MAX_DIFF = 8
_MAX_SUGGESTIONS = 8
_MAX_GAP = 6
_MAX_THUMB_PATTERNS = 8
_MAX_TRAITS = 8


def _latest_analyses(channel_id: str) -> List[Dict[str, Any]]:
    try:
        from . import competitor_analyzer
        return competitor_analyzer.latest_analyses(channel_id) or []
    except Exception:
        return []


def _channel_seeds(channel_id: str) -> List[str]:
    """ChannelManager から theme_seeds の title を集める。失敗時は空。"""
    try:
        from main import channel_manager  # type: ignore
    except Exception:
        return []
    if channel_manager is None:
        return []
    try:
        ch = channel_manager.get(channel_id)
    except Exception:
        return []
    if ch is None:
        return []
    out: List[str] = []
    for s in getattr(ch, "theme_seeds", []) or []:
        if isinstance(s, dict):
            t = (s.get("title") or s.get("keyword") or s.get("angle") or "").strip()
            if t:
                out.append(t)
        elif isinstance(s, str):
            s2 = s.strip()
            if s2:
                out.append(s2)
    return out


def _tokens(text: str) -> List[str]:
    try:
        from pipeline.trend_fetcher import _tokens as _impl
    except Exception:
        return []
    try:
        return _impl(text or "")
    except Exception:
        return []


def theme_overlap_score(title: str, competitor_titles: List[str]) -> float:
    """テーマと競合動画タイトル群の語彙重なり度（0.0〜1.0）。

    1 タイトルあたりの最大 Jaccard 風スコアの最大値を返す。
    """
    if not title or not competitor_titles:
        return 0.0
    base = set(_tokens(title))
    if not base:
        return 0.0
    best = 0.0
    for c in competitor_titles:
        ct = set(_tokens(c or ""))
        if not ct:
            continue
        overlap = base & ct
        if not overlap:
            continue
        score = len(overlap) / len(base)
        if score > best:
            best = score
    return round(best, 3)


def _aggregate_title_patterns(
    analyses: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """各競合の insights.title_patterns を平均/集計。"""
    q_ratios: List[float] = []
    n_ratios: List[float] = []
    e_ratios: List[float] = []
    lengths: List[int] = []
    keyword_counter: Counter = Counter()
    hook_counter: Counter = Counter()

    for a in analyses:
        insights = a.get("insights_json") or {}
        tp = insights.get("title_patterns") or {}
        if not isinstance(tp, dict):
            continue
        for src, dst in (
            ("question_form_ratio", q_ratios),
            ("number_usage_ratio", n_ratios),
            ("exclamation_usage_ratio", e_ratios),
        ):
            v = tp.get(src)
            try:
                if v is not None:
                    dst.append(float(v))
            except Exception:
                pass
        tlen = tp.get("typical_length_chars")
        try:
            if tlen is not None:
                lengths.append(int(tlen))
        except Exception:
            pass
        for kw in tp.get("common_keywords") or []:
            k = str(kw).strip()
            if k:
                keyword_counter[k] += 1
        for hk in tp.get("hook_styles") or []:
            h = str(hk).strip()
            if h:
                hook_counter[h] += 1

    def _avg(xs: List[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "question_form_ratio_avg": _avg(q_ratios),
        "number_usage_ratio_avg": _avg(n_ratios),
        "exclamation_usage_ratio_avg": _avg(e_ratios),
        "typical_length_chars_avg": int(sum(lengths) / len(lengths)) if lengths else None,
        "common_keywords": [k for k, _ in keyword_counter.most_common(_MAX_KEYWORDS)],
        "hook_styles": [h for h, _ in hook_counter.most_common(_MAX_HOOKS)],
        "competitors_observed": len(analyses),
    }


def _competitor_hot_topics(
    analyses: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """各競合の top_videos_json から再生数上位を横断的に集める。"""
    candidates: List[Dict[str, Any]] = []
    for a in analyses:
        comp_title = a.get("competitor_title") or a.get("competitor_id")
        avg_views = a.get("avg_views") or 0
        for v in a.get("top_videos_json") or []:
            if not isinstance(v, dict):
                continue
            title = (v.get("title") or "").strip()
            if not title:
                continue
            views = int(v.get("views") or 0)
            # 競合の平均超え動画を「ホット」とみなす（平均がなければ全部入れる）
            if avg_views and views < avg_views:
                continue
            candidates.append({
                "title": title,
                "views": views,
                "competitor": comp_title,
                "published_at": v.get("published_at"),
            })
    candidates.sort(key=lambda x: x.get("views") or 0, reverse=True)
    # 同一タイトルは1件に
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for c in candidates:
        key = c["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= _MAX_HOT_TOPICS:
            break
    return out


def _aggregate_string_list(
    analyses: List[Dict[str, Any]],
    field: str,
    *,
    limit: int,
) -> List[str]:
    """insights.<field> 配列を全競合から集めて頻度上位を返す（重複排除）。"""
    counter: Counter = Counter()
    for a in analyses:
        insights = a.get("insights_json") or {}
        items = insights.get(field) or []
        if not isinstance(items, list):
            continue
        for it in items:
            t = str(it).strip()
            if t:
                counter[t] += 1
    return [k for k, _ in counter.most_common(limit)]


def _gap_topics(
    seeds: List[str],
    competitor_titles: List[str],
) -> List[str]:
    """seed テーマのうち、競合動画タイトルとの重なりが弱いもの = 競合がカバーしてない領域。

    全く語彙が被らない seed を優先的に返す。
    """
    if not seeds:
        return []
    out: List[Tuple[str, float]] = []
    for s in seeds:
        score = theme_overlap_score(s, competitor_titles)
        out.append((s, score))
    # スコア低い順 = 競合との被りが少ない順
    out.sort(key=lambda x: x[1])
    gaps = [t for t, sc in out if sc < 0.2]
    return gaps[:_MAX_GAP]


def get_competitor_thumbnail_samples(
    channel_id: str,
    max_images: int = 6,
) -> List[str]:
    """Return local file paths of cached competitor thumbnails for Vision input.

    Picks the highest-viewed videos across the latest analysis of each registered
    competitor and interleaves them so multiple competitors are represented.
    If a thumbnail isn't in the local cache yet, this triggers an on-the-fly
    download as a fallback. Returns an empty list when nothing is available.
    """
    if max_images <= 0:
        return []
    try:
        from . import competitor_thumbnails as ct
    except Exception:
        return []

    analyses = _latest_analyses(channel_id)
    if not analyses:
        return []

    by_comp: Dict[str, List[Tuple[int, str, str, Optional[str]]]] = {}
    for a in analyses:
        comp_id = (a.get("competitor_id") or "").strip()
        if not comp_id:
            continue
        for v in a.get("top_videos_json") or []:
            if not isinstance(v, dict):
                continue
            vid = v.get("video_id")
            if not vid:
                continue
            by_comp.setdefault(comp_id, []).append((
                int(v.get("views") or 0),
                comp_id,
                str(vid),
                v.get("thumbnail_url"),
            ))

    # Sort each competitor's videos by views desc.
    for comp_id in list(by_comp.keys()):
        by_comp[comp_id].sort(key=lambda x: x[0], reverse=True)

    # Round-robin so multiple competitors are represented.
    queues = list(by_comp.values())
    interleaved: List[Tuple[int, str, str, Optional[str]]] = []
    while queues:
        next_queues = []
        for q in queues:
            if q:
                interleaved.append(q.pop(0))
                if q:
                    next_queues.append(q)
        queues = next_queues

    out: List[str] = []
    for _views, comp_id, vid, url in interleaved:
        p = ct.ensure_cached(comp_id, vid, thumbnail_url=url)
        if p is not None and p.exists():
            out.append(str(p))
        if len(out) >= max_images:
            break
    return out


def competitor_video_titles(channel_id: str) -> List[str]:
    """全競合の最近動画タイトルをまとめて返す（類似度判定に使う）。"""
    titles: List[str] = []
    for a in _latest_analyses(channel_id):
        for v in a.get("top_videos_json") or []:
            if not isinstance(v, dict):
                continue
            t = (v.get("title") or "").strip()
            if t:
                titles.append(t)
    return titles


def build_competitor_context(channel_id: str) -> Dict[str, Any]:
    """competitor_analyses から集約されたインテリジェンスを返す。

    Returns:
        {
            "available": bool,
            "competitors_observed": int,
            "title_patterns_summary": {...},
            "competitor_hot_topics": [{"title", "views", "competitor", "published_at"}, ...],
            "differentiation_points": [str, ...],
            "improvement_suggestions": [str, ...],
            "gap_topics": [str, ...],
            "competitor_video_titles": [str, ...],
        }

    competitor_analyses が空なら `available=False` で他は空の構造体を返す。
    """
    analyses = _latest_analyses(channel_id)
    if not analyses:
        return {
            "available": False,
            "competitors_observed": 0,
            "title_patterns_summary": {},
            "competitor_hot_topics": [],
            "differentiation_points": [],
            "improvement_suggestions": [],
            "thumbnail_patterns": [],
            "top_videos_common_traits": [],
            "gap_topics": [],
            "competitor_video_titles": [],
        }

    title_patterns = _aggregate_title_patterns(analyses)
    hot_topics = _competitor_hot_topics(analyses)
    differentiation = _aggregate_string_list(analyses, "own_channel_diff", limit=_MAX_DIFF)
    suggestions = _aggregate_string_list(
        analyses, "improvement_suggestions", limit=_MAX_SUGGESTIONS
    )
    thumb_patterns = _aggregate_string_list(
        analyses, "thumbnail_patterns", limit=_MAX_THUMB_PATTERNS
    )
    common_traits = _aggregate_string_list(
        analyses, "top_videos_common_traits", limit=_MAX_TRAITS
    )
    titles = competitor_video_titles(channel_id)
    seeds = _channel_seeds(channel_id)
    gaps = _gap_topics(seeds, titles)

    return {
        "available": True,
        "competitors_observed": title_patterns.get("competitors_observed", 0),
        "title_patterns_summary": title_patterns,
        "competitor_hot_topics": hot_topics,
        "differentiation_points": differentiation,
        "improvement_suggestions": suggestions,
        "thumbnail_patterns": thumb_patterns,
        "top_videos_common_traits": common_traits,
        "gap_topics": gaps,
        "competitor_video_titles": titles,
    }


def _format_title_patterns(tp: Dict[str, Any]) -> List[str]:
    if not tp:
        return []
    out: List[str] = []
    q = tp.get("question_form_ratio_avg")
    n = tp.get("number_usage_ratio_avg")
    e = tp.get("exclamation_usage_ratio_avg")
    length = tp.get("typical_length_chars_avg")
    ratios = []
    if q is not None:
        ratios.append(f"疑問形 {int(q * 100)}%")
    if n is not None:
        ratios.append(f"数字訴求 {int(n * 100)}%")
    if e is not None:
        ratios.append(f"感嘆符 {int(e * 100)}%")
    if length:
        ratios.append(f"平均 {length} 字")
    if ratios:
        out.append(f"  - タイトル傾向: {' / '.join(ratios)}")
    hooks = tp.get("hook_styles") or []
    if hooks:
        out.append(f"  - 多用フック: {', '.join(hooks[:_MAX_HOOKS])}")
    keywords = tp.get("common_keywords") or []
    if keywords:
        out.append(f"  - 頻出キーワード: {', '.join(keywords[:_MAX_KEYWORDS])}")
    return out


def build_thumbnail_competitor_block(channel_id: str) -> Optional[str]:
    """サムネ生成プロンプトに足す競合サムネ傾向の短い日本語テキスト。

    `competitor_intelligence.thumbnail_patterns` と improvement_suggestions の
    うち「サムネ」「thumb」「タイトル」「フォント」「色」「文字」関連のみを
    抽出して、design_brief() の system/user に注入できる形にする。

    競合データが空、または抽出すべき情報がなければ None。
    """
    ctx = build_competitor_context(channel_id)
    if not ctx.get("available"):
        return None

    sections: List[str] = []

    thumb_patterns = ctx.get("thumbnail_patterns") or []
    if thumb_patterns:
        block = ["**競合サムネに頻出する要素（差別化しつつ効果的なものは取り入れる）**:"]
        for p in thumb_patterns[:_MAX_THUMB_PATTERNS]:
            block.append(f"  - {p}")
        sections.append("\n".join(block))

    tp = ctx.get("title_patterns_summary") or {}
    hooks = tp.get("hook_styles") or []
    if hooks:
        sections.append(
            "**競合タイトルの多用フック**: " + ", ".join(hooks[:_MAX_HOOKS])
            + "\n  - 同じ要素を line1/line2/line3_badge に取り入れてよいが、丸パクリは禁止。"
        )

    suggestions = ctx.get("improvement_suggestions") or []
    thumb_keywords = ("サムネ", "thumb", "タイトル", "文字", "フォント", "色", "バッジ", "顔")
    thumb_related = [
        s for s in suggestions
        if any(k in s for k in thumb_keywords)
    ]
    if thumb_related:
        block = ["**競合分析から導かれたサムネ/タイトル改善提案（反映必須）**:"]
        for s in thumb_related[:_MAX_SUGGESTIONS]:
            block.append(f"  - {s}")
        sections.append("\n".join(block))

    if not sections:
        return None

    header = "## 競合サムネ分析からの方針（必ず反映する）"
    footer = (
        "\n上記の競合パターンを参考にしつつ、自チャンネルの個性を必ず加味して、"
        "競合と一目で見分けがつく独自のサムネを作る。"
    )
    return header + "\n\n" + "\n\n".join(sections) + footer


def build_illustration_competitor_hint(channel_id: str) -> Optional[str]:
    """イラスト生成 DALL-E プロンプトに軽く差し込む英語ヒント。

    過度に競合に寄せないため最大 1〜2 行に留め、教育的図解の方向性に対する
    軽いトーン指示にする。何も抽出できなければ None。
    """
    ctx = build_competitor_context(channel_id)
    if not ctx.get("available"):
        return None

    traits = ctx.get("top_videos_common_traits") or []
    illust_keywords = ("図解", "イラスト", "ビジュアル", "図", "データ", "比較", "矢印", "解説")
    illust_related = [t for t in traits if any(k in t for k in illust_keywords)]

    suggestions = ctx.get("improvement_suggestions") or []
    illust_related_suggestions = [
        s for s in suggestions if any(k in s for k in illust_keywords)
    ]

    hints: List[str] = []
    if illust_related:
        joined = " / ".join(illust_related[:3])
        hints.append(
            f"Competitor educational videos in this niche tend to favor: {joined}. "
            "Subtly echo that visual sensibility while keeping the illustration "
            "distinct and channel-original."
        )
    if illust_related_suggestions:
        joined = " / ".join(illust_related_suggestions[:2])
        hints.append(
            f"Apply this illustration-related guidance from competitor analysis: {joined}."
        )

    if not hints:
        return None
    return " ".join(hints)


def build_competitor_addendum(channel_id: str) -> Optional[str]:
    """ScenarioGenerator のプロンプトに足す競合インテリジェンスのテキスト。

    競合データが空なら None を返す。
    """
    ctx = build_competitor_context(channel_id)
    if not ctx.get("available"):
        return None

    sections: List[str] = []

    tp = ctx.get("title_patterns_summary") or {}
    tp_lines = _format_title_patterns(tp)
    if tp_lines:
        block = ["**競合チャンネルのタイトル傾向**:"]
        block.extend(tp_lines)
        block.append(
            "  - 上記の強い要素（疑問形 / 数字 / 具体的なフック）は積極的に取り込む一方、"
            "競合と全く同じ言い回しの量産は避け、独自のひねりを必ず加える。"
        )
        sections.append("\n".join(block))

    hot = ctx.get("competitor_hot_topics") or []
    if hot:
        block = ["**競合の最近の人気動画（テーマ被りを避けつつ切り口で差別化）**:"]
        for h in hot[:_MAX_HOT_TOPICS]:
            views = h.get("views") or 0
            comp = h.get("competitor") or ""
            block.append(f"  - 「{h['title']}」（{comp} / {views:,} 再生）")
        block.append(
            "  - 上記のテーマをそのまま扱う場合は、必ず別角度・別データ・別の意外な事実で差別化する。"
        )
        sections.append("\n".join(block))

    gaps = ctx.get("gap_topics") or []
    if gaps:
        block = ["**競合がまだカバーしていない可能性が高いテーマ（自チャンネルseedsとの差分）**:"]
        for g in gaps[:_MAX_GAP]:
            block.append(f"  - {g}")
        block.append("  - これらは差別化チャンスなので、扱うなら独自視点を最大限活かす。")
        sections.append("\n".join(block))

    diffs = ctx.get("differentiation_points") or []
    if diffs:
        block = ["**自チャンネルが競合と差別化できているポイント（強みは伸ばす）**:"]
        for d in diffs[:_MAX_DIFF]:
            block.append(f"  - {d}")
        sections.append("\n".join(block))

    thumb_patterns = ctx.get("thumbnail_patterns") or []
    if thumb_patterns:
        block = ["**競合サムネに頻出する要素（thumb_info に反映する材料として参照）**:"]
        for p in thumb_patterns[:_MAX_THUMB_PATTERNS]:
            block.append(f"  - {p}")
        block.append(
            "  - 効果的な要素（数字訴求 / 疑問形 / 強調バッジ 等）は thumb_info.hook_lines や "
            "subtitle / tagline に積極的に取り入れる。ただし丸パクリは禁止、独自のひねりを必ず加える。"
        )
        sections.append("\n".join(block))

    traits = ctx.get("top_videos_common_traits") or []
    if traits:
        block = ["**競合の高再生動画に共通する特徴（中身の方向性として参考）**:"]
        for t in traits[:_MAX_TRAITS]:
            block.append(f"  - {t}")
        sections.append("\n".join(block))

    suggestions = ctx.get("improvement_suggestions") or []
    if suggestions:
        block = ["**競合分析から導かれた改善提案（必ず反映）**:"]
        for s in suggestions[:_MAX_SUGGESTIONS]:
            block.append(f"  - {s}")
        sections.append("\n".join(block))

    if not sections:
        return None

    header = "## 競合チャンネル分析からの方針（必ず守る）"
    footer = (
        f"\n上記は登録された競合 {ctx.get('competitors_observed')} 社の週次スキャン結果から導出された方針です。"
        "title / thumb_info / 冒頭フックに反映し、競合と同じテーマでも切り口で必ず差別化すること。"
    )
    return header + "\n\n" + "\n\n".join(sections) + footer
