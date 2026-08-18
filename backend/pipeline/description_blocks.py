"""
説明文ブロック生成 — 登録者増加に効く共通パーツ

video_generator.generate_descriptions から呼ばれ、説明文を次の順で組み立てるための
部品を提供する:

    1. 検索キーワード入りリード（冒頭150文字が検索・関連動画に効く）
    2. 本文（チャンネル別 description_template）
    3. チャンネル登録CTA（?sub_confirmation=1 付きリンク）
    4. 関連動画への誘導（同チャンネルの人気動画 / ショート / 任意の固定リンク）
    5. クロスプロモーション（姉妹チャンネルへの誘導）
    6. ハッシュタグ（3〜5個に正規化）

チャンネルURLは data/channels/*.json の youtube_channel_id から解決する。
未設定のチャンネルはリンクを出さずスキップする（存在しないURLを載せない）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"

# YouTube は説明文のハッシュタグが 15 個を超えると全て無視する。
# 実際に効くのはタイトル上に表示される先頭3個なので 3〜5 個に絞る。
HASHTAG_MIN = 3
HASHTAG_MAX = 5

# ハッシュタグに使えない文字（YouTube 側で分割されてしまう）
_HASHTAG_STRIP = re.compile(r"[\s#＃/\\,、。！？!?（）()「」『』【】\[\]{}:;・\"'’”]+")


# =====================================================================
# クロスプロモーション定義
# =====================================================================
# 「このチャンネルの視聴者が次に見そうな順」に並べる。
# チャンネル JSON 側で description_template.cross_promote を指定すると上書きできる。
DEFAULT_CROSS_PROMO: Dict[str, List[str]] = {
    "daily-science": ["scp-lab", "akashic-librarian"],
    "scp-lab": ["akashic-librarian", "yokai-watch"],
    "akashic-librarian": ["scp-lab", "yokai-watch"],
    "yokai-watch": ["pokemon-lab", "scp-lab"],
    "pokemon-lab": ["yokai-watch", "daily-science"],
    "2ch-matome": ["company-facts", "daily-science"],
    "company-facts": ["2ch-matome", "daily-science"],
    "clip-lab": ["daily-science", "scp-lab"],
}

# 姉妹チャンネル紹介の一言（無い場合は concept を使う）
CROSS_PROMO_PITCH: Dict[str, str] = {
    "daily-science": "身近な「なんで？」を科学で即解決",
    "scp-lab": "SCP財団の異常存在を考察",
    "akashic-librarian": "都市伝説・未解明ミステリーの記録",
    "yokai-watch": "妖怪の元ネタ・伝承を徹底調査",
    "pokemon-lab": "ポケモンの裏設定・図鑑の謎を考察",
    "2ch-matome": "くだらない名スレを30秒で",
    "company-facts": "企業の年収・ホンネを丸裸に",
    "clip-lab": "解説動画のおいしいとこ切り抜き",
}


# =====================================================================
# チャンネルレジストリ
# =====================================================================

_registry_cache: Optional[Dict[str, Dict[str, Any]]] = None


def _load_registry(force: bool = False) -> Dict[str, Dict[str, Any]]:
    """data/channels/*.json を読んで {channel_id: {...}} を返す（プロセス内キャッシュ）。"""
    global _registry_cache
    if _registry_cache is not None and not force:
        return _registry_cache

    registry: Dict[str, Dict[str, Any]] = {}
    if CHANNELS_DIR.exists():
        for f in sorted(CHANNELS_DIR.glob("*.json")):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            cid = raw.get("id")
            if not cid:
                continue
            registry[cid] = {
                "id": cid,
                "name": raw.get("name", cid),
                "concept": raw.get("concept", ""),
                "youtube_channel_id": raw.get("youtube_channel_id") or "",
            }
    _registry_cache = registry
    return registry


def reset_registry_cache() -> None:
    """チャンネル JSON を編集した後に呼ぶ（テスト・設定更新用）。"""
    global _registry_cache
    _registry_cache = None


def channel_url(channel_id: str) -> Optional[str]:
    """チャンネルのトップURL。youtube_channel_id 未設定なら None。"""
    info = _load_registry().get(channel_id) or {}
    ucid = (info.get("youtube_channel_id") or "").strip()
    if not ucid.startswith("UC"):
        return None
    return f"https://www.youtube.com/channel/{ucid}"


def subscribe_url(channel_id: str) -> Optional[str]:
    """ワンクリックで登録確認ダイアログが出るURL。"""
    base = channel_url(channel_id)
    return f"{base}?sub_confirmation=1" if base else None


def _channel_id_of(channel_dict: Optional[Dict[str, Any]]) -> str:
    return str((channel_dict or {}).get("id") or "")


def _desc_cfg(channel_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return (channel_dict or {}).get("description_template") or {}


# =====================================================================
# ハッシュタグ / 検索キーワード
# =====================================================================

def _shorten(text: str, limit: int) -> str:
    """文を limit 文字に収める。句点で切れるならそこで閉じる。"""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) <= limit:
        return t
    head = t[:limit]
    for sep in ("。", "！", "？", "、"):
        idx = head.rfind(sep)
        if idx >= limit // 2:
            return head[:idx].rstrip("、")
    return head.rstrip("、。") + "…"


def _clean_tag(tag: str) -> str:
    """'#ゆっくり解説' や ' 科学 ' を 'ゆっくり解説' / '科学' に正規化する。"""
    return _HASHTAG_STRIP.sub("", str(tag or "")).strip()


def normalize_hashtags(
    raw: Any,
    *,
    required: Optional[List[str]] = None,
    limit: int = HASHTAG_MAX,
) -> str:
    """ハッシュタグ文字列/リストを重複なしの `#a #b #c` 形式（最大 limit 個）に整える。

    required（例: shorts）は必ず先頭に来る。YouTube は 15 個超で全無視、
    表示されるのは先頭3個なので既定で 5 個に絞る。
    """
    if isinstance(raw, str):
        items = raw.split()
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = []

    ordered: List[str] = []
    seen = set()
    for tag in list(required or []) + items:
        t = _clean_tag(tag)
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        ordered.append(t)
        if len(ordered) >= max(1, limit):
            break

    return " ".join(f"#{t}" for t in ordered)


def search_keywords(
    channel_dict: Optional[Dict[str, Any]],
    title: str = "",
    *,
    limit: int = 8,
) -> List[str]:
    """検索に引っかけたいキーワード列。タグ設定＋タイトル語から作る。"""
    cd = channel_dict or {}
    vf_tags = ((cd.get("video_format") or {}).get("youtube") or {}).get("default_tags") or []
    default_tags = (cd.get("defaults") or {}).get("hashtags") or []

    words: List[str] = []
    seen = set()
    for tag in list(vf_tags) + list(default_tags):
        t = _clean_tag(tag)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            words.append(t)

    # タイトルからも固有名詞っぽい塊を拾う（記号で割っただけの素朴な抽出）
    for chunk in re.split(r"[\s、。！？!?・「」『』【】（）()\-—〜～:：]+", title or ""):
        c = chunk.strip()
        if len(c) >= 2 and c.lower() not in seen:
            seen.add(c.lower())
            words.append(c)

    return words[:limit]


def build_keyword_lead(
    channel_dict: Optional[Dict[str, Any]],
    title: str,
    *,
    hook: str = "",
    tagline: str = "",
) -> List[str]:
    """説明文冒頭の要約ブロック。検索キーワードを含む1〜3行。

    YouTube は説明文の冒頭が検索・関連動画の判定に効くので、ここに
    「何の動画か」＋「キーワード」を素の文章で置く。
    """
    cd = channel_dict or {}
    channel_name = cd.get("name") or ""
    concept = cd.get("concept") or ""

    summary = (hook or "").strip() or (title or "").strip()
    lead = f"{summary}"
    if tagline:
        lead += f" {tagline.strip()}"

    # 冒頭で概要を長々と繰り返すと肝心のキーワードが下に押し出されるので、
    # コンセプトは一文に切り詰めて載せる（全文はチャンネル情報セクションに出る）。
    intro = ""
    if channel_name:
        # 「解説」が似合わないチャンネル（まとめ・実況系）は
        # description_template.lead_template で言い回しを差し替えられる。
        lead_tmpl = _desc_cfg(cd).get("lead_template") or "『{title}』を{channel}が解説します。"
        try:
            intro = lead_tmpl.format(title=title, channel=channel_name)
        except Exception:
            intro = f"『{title}』を{channel_name}が解説します。"
        short_concept = _shorten(concept, 60)
        if short_concept:
            intro += short_concept

    lines = [line for line in [lead.strip(), intro.strip()] if line]

    kws = search_keywords(cd, title, limit=8)
    if kws:
        lines.append(f"🔍 {' / '.join(kws)}")

    return lines


# =====================================================================
# CTA / 関連動画 / クロスプロモ
# =====================================================================

def build_subscribe_block(
    channel_dict: Optional[Dict[str, Any]],
    *,
    compact: bool = False,
) -> List[str]:
    """チャンネル登録誘導。ワンクリック登録URLが取れる場合はそれも載せる。"""
    cid = _channel_id_of(channel_dict)
    sub = subscribe_url(cid) if cid else None

    if compact:
        lines = ["🔔 チャンネル登録＆高評価で応援お願いします！"]
        if sub:
            lines.append(f"👉 {sub}")
        return lines

    lines = [
        "🔔 チャンネル登録・高評価をぜひお願いします！",
        "   新しい動画を見逃さないよう通知をONにしてね",
    ]
    if sub:
        lines.append(f"👉 ワンクリックで登録: {sub}")
    return lines


def build_related_block(
    channel_dict: Optional[Dict[str, Any]],
    *,
    is_short: bool = False,
) -> List[str]:
    """同チャンネルの他動画への誘導リンク。

    生成時点では個別動画IDが確定しないので、確実に生きているチャンネル内タブ
    （人気順・ショート一覧・再生リスト）へ誘導する。チャンネル JSON に
    description_template.related_links = [{"title": ..., "url": ...}] があれば
    そちらを優先して固定リンクを出す。
    """
    cd = channel_dict or {}
    cid = _channel_id_of(cd)
    cfg = _desc_cfg(cd)

    fixed = cfg.get("related_links")
    lines: List[str] = []
    if isinstance(fixed, list) and fixed:
        lines.append("▼ 関連動画")
        for item in fixed[:3]:
            if not isinstance(item, dict):
                continue
            t = str(item.get("title") or "").strip()
            u = str(item.get("url") or "").strip()
            if u:
                lines.append(f"・{t} {u}".strip())
        return lines if len(lines) > 1 else []

    base = channel_url(cid) if cid else None
    if not base:
        return []

    lines.append("▼ このチャンネルの他の動画")
    lines.append(f"🔥 人気の動画: {base}/videos?view=0&sort=p")
    if is_short:
        lines.append(f"🎬 解説シリーズ一覧: {base}/videos")
    else:
        lines.append(f"⚡ ショートまとめ: {base}/shorts")
    lines.append(f"📚 再生リスト: {base}/playlists")
    return lines


def build_cross_promo_block(
    channel_dict: Optional[Dict[str, Any]],
    *,
    limit: int = 2,
) -> List[str]:
    """姉妹チャンネルへの誘導ブロック。

    優先順:
        description_template.cross_promote (チャンネルIDのリスト)
        → DEFAULT_CROSS_PROMO
    description_template.disable_cross_promo が true なら何も出さない。
    """
    cd = channel_dict or {}
    cid = _channel_id_of(cd)
    cfg = _desc_cfg(cd)
    if cfg.get("disable_cross_promo"):
        return []

    targets = cfg.get("cross_promote")
    if not isinstance(targets, list) or not targets:
        targets = DEFAULT_CROSS_PROMO.get(cid, [])

    registry = _load_registry()
    lines: List[str] = []
    promoted = 0
    for tid in targets:
        if not isinstance(tid, str) or tid == cid or promoted >= limit:
            continue
        info = registry.get(tid)
        url = channel_url(tid)
        if not info or not url:
            continue
        pitch = _shorten(CROSS_PROMO_PITCH.get(tid) or info.get("concept") or "", 40)
        lines.append(f"・{info['name']} — {pitch}".rstrip(" —"))
        lines.append(f"  👉 {url}?sub_confirmation=1")
        promoted += 1

    if not lines:
        return []
    return ["▼ 姉妹チャンネルもどうぞ", *lines]


# =====================================================================
# アップロード用タグ
# =====================================================================

def build_upload_tags(
    channel_dict: Optional[Dict[str, Any]],
    *,
    extra: Optional[List[str]] = None,
    is_short: bool = False,
    max_chars: int = 450,
) -> List[str]:
    """videos.insert の snippet.tags 用リスト。

    video_format.youtube.default_tags（検索用の広いセット）と
    defaults.hashtags（表示用の少数）をマージして重複を除く。
    YouTube のタグ合計は 500 文字上限なので余裕をみて 450 で打ち切る。
    """
    cd = channel_dict or {}
    vf_tags = ((cd.get("video_format") or {}).get("youtube") or {}).get("default_tags") or []
    hash_tags = (cd.get("defaults") or {}).get("hashtags") or []

    ordered: List[str] = []
    seen = set()
    head = ["Shorts"] if is_short else []
    for tag in head + list(vf_tags) + list(hash_tags) + list(extra or []):
        t = _clean_tag(tag)
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        ordered.append(t)

    out: List[str] = []
    total = 0
    for t in ordered:
        # カンマ区切りで送られるので区切り文字1文字分を加算して見積もる
        cost = len(t) + 1
        if total + cost > max_chars:
            break
        out.append(t)
        total += cost
    return out
