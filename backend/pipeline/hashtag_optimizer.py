"""動的ハッシュタグ最適化 — 動画ごとにコンテンツ+トレンドに基づくハッシュタグを生成。

従来は全動画に同じ静的ハッシュタグを付けていたが、競合分析の結果:
- YouTube は先頭3個のハッシュタグをタイトル上に表示する
- トレンドワードを含むタグは検索流入を 2〜3 倍にする
- 3〜5 個が最適（15 個超で全無視、多すぎると分散する）

このモジュールは:
1. チャンネルの基本タグ（1〜2個）を先頭に固定
2. タイトル・テーマから動的にキーワードタグを抽出
3. トレンドキーワードが一致すればトレンドタグを注入
4. 合計 3〜5 個に収める

description_blocks.normalize_hashtags の上位互換として使う。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 各チャンネルの「必ず入れるコアタグ」（先頭に固定、最大2個）
# shorts は別途タイトル側で付与されるのでここでは省く
CHANNEL_CORE_TAGS: Dict[str, List[str]] = {
    "daily-science": ["ゆっくり解説", "雑学"],
    "scp-lab": ["SCP", "ゆっくり解説"],
    "2ch-matome": ["2ch", "2chまとめ"],
    "company-facts": ["企業の闘", "ブラック企業"],
    "pokemon-lab": ["ポケモン", "ポケモン雑学"],
    "yokai-watch": ["妖怪", "都市伝説"],
    # 「ゆっくり解説」は voice_style.forbidden。1人語りの司書チャンネルなので付けない
    "akashic-librarian": ["都市伝説", "歴史ミステリー"],
}

# チャンネル別の拡張候補タグプール（動画内容に応じて選択される）
CHANNEL_TAG_POOL: Dict[str, List[str]] = {
    "daily-science": ["科学", "豆知識", "理科", "日常の謎", "面白い雑学"],
    "scp-lab": ["SCP解説", "SCP財団", "ホラー", "都市伝説", "怖い話"],
    "2ch-matome": ["なんJ", "面白いスレ", "修羅場", "2ch面白", "5ch"],
    "company-facts": ["企業分析", "年収", "転職", "会社の裏側", "ブラック"],
    "pokemon-lab": ["ポケモン解説", "ポケモン豆知識", "ゲーム", "任天堂"],
    "yokai-watch": ["怪談", "妖怪解説", "オカルト", "ホラー", "心霊"],
    "akashic-librarian": ["考察", "歴史", "ミステリー", "哲学"],
}

# タイトルからタグ候補を抽出するときに無視するストップワード
_STOP_WORDS = frozenset([
    "の", "は", "が", "を", "に", "で", "と", "も", "から", "まで",
    "って", "という", "する", "した", "される", "いる", "ある", "なる",
    "こと", "もの", "ため", "よう", "ない", "その", "この", "あの",
    "それ", "これ", "あれ", "なぜ", "どう", "何", "どの", "いつ",
    "知ら", "ヤバ", "すぎ", "結果", "理由", "真実", "実は",
])

_SPLIT_RE = re.compile(r"[\s、。！？!?・「」『』【】（）()\-—〜～:：#＃]+")

# 検索タグとして意味のある最大長。これを超えるものは「文」であってキーワードでない。
_KEYWORD_MAX_LEN = 12

# 固有名詞になりやすい並びだけを拾う:
#   1. SCP-XXXX / MTF-イプシロン のような英数字IDっぽい語
#   2. カタカナの連続（ポケモン名・妖怪名・外来語）
#   3. 漢字の連続（財団 / 収容違反 / 骨伝導 …）
#   4. 漢字＋ひらがな1文字＋漢字（例: 目の錯覚）は拾わない（文になりやすい）
_ENTITY_RES = [
    re.compile(r"[A-Za-z]{2,}[-‐ー]?\d{2,4}"),
    re.compile(r"[ァ-ヶー]{3,}"),
    re.compile(r"[一-龠]{2,}"),
]

# 「〜」『〜』で囲われた語は作者が固有名詞として括っているので優先的に拾う
_QUOTED_RE = re.compile(r"[「『]([^「」『』]{2,12})[」』]")

# シリーズ接頭辞・定型サフィックスは固有名詞ではないので抽出前に落とす
_PREFIX_NOISE_RE = re.compile(
    r"^(一口SCP|1分科学|1分ポケモン研究|1分妖怪ファイル|30秒スレまとめ|架空論文ファイル)"
    r"(\s*#?\d+)?\s*[：:]?\s*"
    r"|【ショート】|【ゆっくり解説】|#shorts",
    re.IGNORECASE,
)

# 単独では検索価値のない汎用語（拾っても他チャンネルと被るだけ）
_GENERIC_WORDS = frozenset([
    "本当", "理由", "真実", "衝撃", "秘密", "正体", "瞬間", "存在", "自分",
    "解説", "考察", "動画", "今回", "全員", "人間", "世界", "最強", "最恐",
    "意外", "驚愕", "話題", "紹介", "実話", "内容", "場合", "状態", "結果",
])


def _extract_title_keywords(title: str, *, min_len: int = 2, max_keywords: int = 3) -> List[str]:
    """タイトルから検索タグになる固有名詞を抽出する。

    以前は句読点で割っただけのチャンクを返しており、
    「なぜ蚊に刺されると数分後に痒くなるのか」のような文そのものがタグとして
    登録されていた（検索ボリューム 0 のタグが 450 文字のタグ枠を食う）。
    ここでは固有名詞になりやすい並び（英数字ID・カタカナ連続・漢字連続・
    カギ括弧内）だけを拾い、汎用語と長すぎる語を落とす。
    """
    text = _PREFIX_NOISE_RE.sub("", title or "")
    if not text:
        return []

    candidates: List[str] = []
    # カギ括弧の中は最優先
    for m in _QUOTED_RE.finditer(text):
        candidates.append(m.group(1))
    for rx in _ENTITY_RES:
        candidates.extend(rx.findall(text))

    keywords: List[str] = []
    seen = set()
    for c in candidates:
        c = c.strip()
        if not (min_len <= len(c) <= _KEYWORD_MAX_LEN):
            continue
        low = c.lower()
        if low in seen:
            continue
        if c in _STOP_WORDS or c in _GENERIC_WORDS:
            continue
        if len(c) <= 3 and any(sw in c for sw in _STOP_WORDS):
            continue
        seen.add(low)
        keywords.append(c)
        if len(keywords) >= max_keywords:
            break
    return keywords


def _match_trend_tags(
    title: str,
    trend_keywords: List[str],
    *,
    max_tags: int = 2,
) -> List[str]:
    """トレンドキーワードのうちタイトルに関連するものをタグとして返す。"""
    if not trend_keywords:
        return []
    title_lower = (title or "").lower()
    matched: List[str] = []
    for kw in trend_keywords:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        if kw_clean.lower() in title_lower or title_lower in kw_clean.lower():
            matched.append(kw_clean)
            if len(matched) >= max_tags:
                break
    return matched


def optimize_hashtags(
    channel_id: str,
    title: str,
    *,
    is_short: bool = True,
    trend_keywords: Optional[List[str]] = None,
    theme_info: Optional[Dict[str, Any]] = None,
    max_tags: int = 5,
) -> str:
    """動画ごとに最適化されたハッシュタグ文字列を返す。

    構成（優先度順）:
    1. チャンネルコアタグ（1〜2個、必ず先頭）
    2. トレンド一致タグ（0〜2個）
    3. タイトルから抽出したキーワードタグ（0〜2個）
    4. チャンネルプールから補充（残り枠分）

    Returns:
        "#tag1 #tag2 #tag3" 形式の文字列
    """
    core = list(CHANNEL_CORE_TAGS.get(channel_id, ["ゆっくり解説"]))
    pool = list(CHANNEL_TAG_POOL.get(channel_id, []))

    tags: List[str] = []
    seen: set = set()

    def _add(tag: str) -> bool:
        t = tag.strip().lstrip("#＃")
        if not t or t.lower() in seen or len(tags) >= max_tags:
            return False
        seen.add(t.lower())
        tags.append(t)
        return True

    # 1. コアタグ
    for t in core:
        _add(t)

    # 2. テーマのトレンドマッチ（theme_queue から来る trend_match）
    if theme_info:
        tm = theme_info.get("trend_match")
        if tm and isinstance(tm, str):
            _add(tm)

    # 3. トレンドキーワード一致
    trend_tags = _match_trend_tags(title, trend_keywords or [])
    for t in trend_tags:
        _add(t)

    # 4. タイトルキーワード
    title_kws = _extract_title_keywords(title)
    for kw in title_kws:
        _add(kw)

    # 5. プールから補充
    for t in pool:
        if len(tags) >= max_tags:
            break
        _add(t)

    return " ".join(f"#{t}" for t in tags)


def optimize_short_title_hashtags(
    channel_id: str,
    title: str,
    *,
    trend_keywords: Optional[List[str]] = None,
    theme_info: Optional[Dict[str, Any]] = None,
    max_tags: int = 3,
) -> str:
    """ショートタイトル末尾用のハッシュタグ（#shorts 込み、最大3個+shorts）。

    タイトルに付くので簡潔に。#shorts は必ず先頭。
    残り枠でコアタグ1個 + トレンド/タイトルから1個。
    """
    result_tags = ["shorts"]
    seen = {"shorts"}

    core = CHANNEL_CORE_TAGS.get(channel_id, ["ゆっくり解説"])
    if core:
        t = core[0].lstrip("#＃")
        if t.lower() not in seen:
            result_tags.append(t)
            seen.add(t.lower())

    # トレンド一致を1個
    if theme_info and theme_info.get("trend_match"):
        tm = str(theme_info["trend_match"]).strip().lstrip("#＃")
        if tm and tm.lower() not in seen and len(result_tags) < max_tags + 1:
            result_tags.append(tm)
            seen.add(tm.lower())

    trend_tags = _match_trend_tags(title, trend_keywords or [], max_tags=1)
    for t in trend_tags:
        t = t.lstrip("#＃")
        if t.lower() not in seen and len(result_tags) < max_tags + 1:
            result_tags.append(t)
            seen.add(t.lower())

    return " ".join(f"#{t}" for t in result_tags)


def optimize_upload_tags(
    channel_id: str,
    title: str,
    *,
    is_short: bool = True,
    channel_dict: Optional[Dict[str, Any]] = None,
    trend_keywords: Optional[List[str]] = None,
    theme_info: Optional[Dict[str, Any]] = None,
    max_chars: int = 450,
) -> List[str]:
    """YouTube API の snippet.tags 用リスト（動的版）。

    従来の build_upload_tags のベースタグに加え、タイトルキーワードと
    トレンドキーワードを動的に追加する。
    """
    cd = channel_dict or {}
    vf_tags = ((cd.get("video_format") or {}).get("youtube") or {}).get("default_tags") or []
    hash_tags = (cd.get("defaults") or {}).get("hashtags") or []

    ordered: List[str] = []
    seen: set = set()

    def _add(tag: str) -> None:
        t = tag.strip().lstrip("#＃")
        if not t or t.lower() in seen:
            return
        seen.add(t.lower())
        ordered.append(t)

    # Shorts タグ
    if is_short:
        _add("Shorts")

    # チャンネル設定のタグ
    for tag in list(vf_tags) + list(hash_tags):
        _add(tag)

    # テーマのトレンドマッチ
    if theme_info and theme_info.get("trend_match"):
        _add(str(theme_info["trend_match"]))

    # トレンドキーワード
    for kw in (trend_keywords or [])[:3]:
        _add(kw)

    # タイトルキーワード
    for kw in _extract_title_keywords(title, max_keywords=5):
        _add(kw)

    # 文字数制限
    out: List[str] = []
    total = 0
    for t in ordered:
        cost = len(t) + 1
        if total + cost > max_chars:
            break
        out.append(t)
        total += cost
    return out
