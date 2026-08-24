"""
theme_dedup — テーマ（動画ネタ）の重複検出ユーティリティ。

2 段構え:
  1. **語彙的（lexical）** — 表記揺れ・言い換え・句読点違いを正規化し、文字 bigram の
     Jaccard と SequenceMatcher で類似度を出す。LLM 不要・即時・無料。
     例: 「なぜ水たまりの色が変わるのか」 ≈ 「なぜ水たまりはできるのか？ — 水の挙動」
  2. **意味的（semantic）** — 語彙が違うのに実質同義のもの（例: 「アイスで頭がキーン」 vs
     「冷たい飲み物で頭が痛くなる」）は語彙だけでは弾けない。LLM に「実質同じか」を
     バッチ判定させる。呼び出し側が LLM 関数を注入する（generator が GPT→Claude
     フォールバック付きで提供）ので、ここ自体は LLM 依存を持たない。

設計方針:
  - generator / theme_queue / autopilot のどこからでも import できるよう、依存は標準ライブラリのみ。
  - 過去テーマの読み出し（data/scenarios/<id>/*.json）もここに集約し、各所での重複実装を無くす。
"""

from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

# 語彙類似度の既定しきい値。これ以上なら「実質同じ言い回し」とみなす。
# 既知の重複群（自分の声/録音・水たまり・夢 等）が拾える最小値に合わせて調整済み。
DEFAULT_LEXICAL_THRESHOLD = 0.55

# 正規化時に削る「話題を持たない」構造語・定型句。両側に同じ処理をかけるので
# 削りすぎても比較の公平性は保たれる（むしろ話題語だけを残せて精度が上がる）。
_FILLER_WORDS = [
    "本当の理由", "という現象", "について", "とは何か", "とは", "の科学", "の謎",
    "の秘密", "を解説", "を深掘り", "深掘り", "メカニズム", "仕組み", "理由",
    "なぜか", "なぜ", "どうして", "実は", "まとめ", "入門", "現象",
    "のだろうか", "のだろう", "のか", "こと", "もの", "ある", "する", "なる",
    "今すぐ", "衝撃", "驚愕", "閲覧注意",
]

_BRACKET_RE = re.compile(r"[【】\[\]（）()「」『』〈〉《》]")
_PUNCT_RE = re.compile(r"[。、，．\.・…—\-‐―〜~!！?？:：;；/／\\｜|　\s]+")

# 全角英数 → 半角
_ZEN2HAN = {c: chr(ord(c) - 0xFEE0) for c in
            [chr(o) for o in range(0xFF01, 0xFF5F)]}


def normalize_title(title: str) -> str:
    """タイトルを比較用に正規化する。

    手順: 全角→半角・小文字化 → 括弧/装飾除去 → 句読点・空白除去 → 定型句除去。
    残るのは「話題を表す中身の文字列」だけになる。
    """
    if not title:
        return ""
    t = str(title).strip()
    t = "".join(_ZEN2HAN.get(ch, ch) for ch in t).lower()
    t = _BRACKET_RE.sub("", t)
    t = _PUNCT_RE.sub("", t)
    for w in _FILLER_WORDS:
        t = t.replace(w, "")
    return t


def _bigrams(s: str) -> Set[str]:
    if len(s) >= 2:
        return {s[i:i + 2] for i in range(len(s) - 1)}
    return {s} if s else set()


# 話題語（漢字連・カタカナ連・英数連）の抽出。助詞・活用語尾は平仮名なので自然に区切れる。
_CONTENT_TOKEN_RE = re.compile(r"[一-龥々〆ヵヶ]+|[ァ-ヶー]+|[a-z0-9]+")


# チャンネル定型語（識別子プレフィックスや頻出ジャンル語）。話題を区別しないので
# キーワード一致から除外する（番号付き識別子は _identifiers 側で別途扱う）。
_BOILERPLATE_TOKENS = {
    "scp", "goc", "gow", "anomaly", "item", "財団",
    # 全動画のタイトルに付く定型語。話題を全く区別しないのに 2〜4 文字あるため
    # _keyword_overlap の重み（文字数の2乗）で強く効いてしまい、無関係な
    # 2 本が「ショート」の共有だけで 0.76 まで跳ね上がる誤検出が出ていた。
    "ショート", "shorts", "short", "ゆっくり", "解説", "考察", "研究",
    "一口", "分科学", "ファイル", "まとめ",
}


def _content_tokens(title: str) -> List[str]:
    """正規化済みタイトルから話題を表すトークン（漢字/カタカナ/英数の連なり）を抽出。

    1 文字の漢字（声・夢・指 等の話題核）は残し、1 文字の平仮名・記号は捨てる。
    定型語（scp/財団 等）は話題を区別しないので除外する。
    """
    out: List[str] = []
    for tok in _CONTENT_TOKEN_RE.findall(normalize_title(title)):
        if tok in _BOILERPLATE_TOKENS:
            continue
        if len(tok) >= 2 or re.match(r"[一-龥々]", tok):
            out.append(tok)
    return out


def _keyword_overlap(a: str, b: str) -> float:
    """話題語の重なり [0.0, 1.0]。長く特徴的な語（録音・水たまり・スマホ等）を重く評価する。

    重み = 文字数² で、短い／長いタイトル間でも「核となる固有語の共有」を強く拾う。
    分母は短い方の総重み（包含関係を取りこぼさないため min を採る）。
    """
    sa, sb = set(_content_tokens(a)), set(_content_tokens(b))
    if not sa or not sb:
        return 0.0
    shared = sa & sb
    if not shared:
        return 0.0
    w = lambda s: sum(len(x) ** 2 for x in s)
    inter = w(shared)
    # 共有語がすべて 1 文字語のとき（止・手・脳 のような頻出漢字・動詞語幹）は
    # 偶然一致になりやすい。特に平仮名主体の title（例:「なぜしゃっくりは止まらない」→
    # 抽出語が「止」だけ）が語の豊富な無関係 title に薄く一致すると、min 分母では
    # 誤って 1.0 まで跳ね上がる。分母を max（対称）にして減衰させ、この誤検出を防ぐ。
    # 双方が短く 1 文字語中心の title 同士（声/夢 のような話題核の共有）では
    # 依然として中程度のスコアが残る。
    if all(len(x) == 1 for x in shared):
        den = max(w(sa), w(sb))
    else:
        den = min(w(sa), w(sb))
    return (inter / den) if den else 0.0


# 作品識別子（SCP-682 等）。この種のタイトルでは番号こそが同一性の核。
# 共有プレフィックス（"SCP-"）で語彙類似度が誤って跳ね上がるのを抑える。
_ID_RE = re.compile(r"\b(scp|goc|gow|anomaly|item)[\s\-_#]*([0-9]{1,5})\b", re.IGNORECASE)


def _identifiers(title: str) -> Set[str]:
    """タイトルから作品識別子（例: scp682）を抽出。"""
    return {f"{m.group(1).lower()}{int(m.group(2))}" for m in _ID_RE.finditer(title or "")}


def similarity(a: str, b: str) -> float:
    """2 つのタイトルの語彙類似度 [0.0, 1.0]。

    3 つの信号の最大値を採る:
      - 文字 bigram Jaccard（語順違い・部分一致）
      - SequenceMatcher ratio（編集距離ベース）
      - 話題語オーバーラップ（共有する固有名詞・核キーワード）
    どれか一つでも強ければ重複候補として拾う（取りこぼし < 誤検出 を優先しつつ、
    最終判定は意味判定 LLM に委ねる前提なので語彙段は再現率寄り）。

    ただし作品識別子（SCP-XXXX 等）を含む場合は番号を同一性の核として優先:
      - 双方に識別子があり共有なし → 別作品とみなし弱い類似度に抑える（誤検出防止）
      - 同じ識別子を共有 → 確実に重複（1.0）
    """
    # 識別子ベースの早期判定（SCP-XXXX 等）
    ida, idb = _identifiers(a), _identifiers(b)
    if ida and idb:
        if ida & idb:
            return 1.0
        # 番号が完全に食い違う別作品。語彙が似ていても重複ではない。
        return 0.0

    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # 短い方が長い方に丸ごと含まれる（部分文字列）→ ほぼ同義とみなす
    if len(na) >= 3 and len(nb) >= 3 and (na in nb or nb in na):
        return 0.9
    ba, bb = _bigrams(na), _bigrams(nb)
    union = ba | bb
    jac = (len(ba & bb) / len(union)) if union else 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    kw = _keyword_overlap(a, b)
    return max(jac, seq, kw)


def find_lexical_duplicate(
    title: str,
    existing: Sequence[str],
    *,
    threshold: float = DEFAULT_LEXICAL_THRESHOLD,
) -> Optional[Tuple[str, float]]:
    """existing の中で title と語彙的に最も近いものを返す（しきい値以上のみ）。"""
    best: Optional[Tuple[str, float]] = None
    for ex in existing:
        if not ex:
            continue
        s = similarity(title, ex)
        if s >= threshold and (best is None or s > best[1]):
            best = (ex, s)
    return best


def is_lexical_duplicate(
    title: str,
    existing: Sequence[str],
    *,
    threshold: float = DEFAULT_LEXICAL_THRESHOLD,
) -> bool:
    return find_lexical_duplicate(title, existing, threshold=threshold) is not None


def dedupe_titles(
    titles: Sequence[str],
    *,
    threshold: float = DEFAULT_LEXICAL_THRESHOLD,
) -> List[str]:
    """リスト内の語彙的重複を畳んで、ユニークなタイトルだけ順序保持で返す。"""
    kept: List[str] = []
    for t in titles:
        if not t:
            continue
        if not is_lexical_duplicate(t, kept, threshold=threshold):
            kept.append(t)
    return kept


# ---------------------------------------------------------------------------
# 過去テーマの読み出し（data/scenarios/<id>/*.json）
# ---------------------------------------------------------------------------

def _scenarios_dir(channel_id: str) -> Path:
    # theme_dedup.py → auto_scenario → pipeline → backend → repo_root
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "scenarios" / channel_id


def past_theme_titles(channel_id: str, *, limit: Optional[int] = None,
                      within_days: Optional[int] = None) -> List[str]:
    """過去に生成済みの scenario JSON からテーマタイトルを新しい順に集める。

    Args:
        limit: 最大件数（None なら全件）。
        within_days: 指定すると mtime がこの日数以内のものだけ。
    """
    base = _scenarios_dir(channel_id)
    if not base.exists():
        return []
    cutoff = (time.time() - within_days * 86400) if within_days else None
    files = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    titles: List[str] = []
    seen: Set[str] = set()
    for f in files:
        try:
            if cutoff is not None and f.stat().st_mtime < cutoff:
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        th = data.get("theme") if isinstance(data, dict) else None
        title = ""
        if isinstance(th, dict):
            title = (th.get("title") or "").strip()
        if not title and isinstance(data, dict):
            title = (data.get("title") or "").strip()
        if not title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        titles.append(title)
        if limit and len(titles) >= limit:
            break
    return titles


# ---------------------------------------------------------------------------
# 意味的（semantic）重複: LLM バッチ判定
# ---------------------------------------------------------------------------

def build_semantic_prompt(candidates: Sequence[str], existing: Sequence[str]) -> str:
    """候補が既存テーマと「実質同じ（言い換え/同一トピック）」かを LLM に判定させるプロンプト。"""
    cand_block = "\n".join(f"{i}. {t}" for i, t in enumerate(candidates))
    exist_block = "\n".join(f"- {t}" for t in existing) if existing else "(なし)"
    return f"""次の「候補テーマ」のうち、「既存テーマ」のいずれかと**実質的に同じ内容**
（語彙が違っても扱う題材・結論・視聴者が得る情報が同じ）のものを特定せよ。

判定基準:
- 言い回し・語順・装飾だけ違うが同じ題材 → 重複(true)。
  例: 「アイスで頭がキーンとする理由」と「冷たい飲み物で頭が痛くなる仕組み」は同じ題材 → 重複。
- 同じ対象を扱うが切り口・問い・結論が明確に異なる → 重複ではない(false)。
  例: 「なぜ空は青いのか」と「なぜ夕焼けは赤いのか」は別テーマ → 非重複。

# 候補テーマ
{cand_block}

# 既存テーマ
{exist_block}

# 出力（JSONのみ・候補ごとに1要素）
[
  {{"index": 0, "duplicate": true, "matched": "最も近い既存テーマのタイトル"}},
  {{"index": 1, "duplicate": false, "matched": null}}
]
"""


def parse_semantic_response(raw: str, candidates: Sequence[str]) -> Dict[int, str]:
    """build_semantic_prompt の応答から {候補index: matched既存タイトル} を返す（duplicate=true のみ）。"""
    text = (raw or "").strip()
    if "```" in text:
        # コードフェンス除去
        m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL | re.IGNORECASE)
        if m:
            text = m.group(1)
    # 最初の JSON 配列を拾う
    if not text.startswith("["):
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            text = m.group(0)
    try:
        arr = json.loads(text)
    except Exception:
        return {}
    out: Dict[int, str] = {}
    if isinstance(arr, list):
        for el in arr:
            if not isinstance(el, dict):
                continue
            if not el.get("duplicate"):
                continue
            idx = el.get("index")
            if isinstance(idx, int) and 0 <= idx < len(candidates):
                out[idx] = str(el.get("matched") or "")
    return out


def semantic_filter(
    candidates: Sequence[Dict[str, Any]],
    existing: Sequence[str],
    llm_call: Callable[[List[Dict[str, str]]], str],
    *,
    title_key: str = "title",
) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]]:
    """候補 dict 列から、既存と意味的に重複するものを LLM 判定で除外する。

    Args:
        candidates: {title: ...} を含む dict のリスト。
        existing: 既存（過去 + キュー内）タイトル。
        llm_call: messages 配列を受けて応答テキストを返す関数。例外時は呼び出し側で握りつぶす想定。
    Returns:
        (kept, dropped) — dropped は (候補, matched既存タイトル)。
        LLM 呼び出しが失敗/空なら全件 kept（語彙フィルタで既に弾けているため安全側）。
    """
    cand_titles = [str(c.get(title_key) or "").strip() for c in candidates]
    pairs = [(c, t) for c, t in zip(candidates, cand_titles) if t]
    if not pairs or not existing:
        return list(candidates), []
    titles_only = [t for _, t in pairs]
    prompt = build_semantic_prompt(titles_only, list(existing))
    messages = [
        {"role": "system", "content": "重複判定器。JSON配列のみ出力。"},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = llm_call(messages)
    except Exception as e:
        print(f"  ⚠️ semantic dedup LLM call failed: {e} — keeping all (lexical filter already applied)")
        return list(candidates), []
    dup_map = parse_semantic_response(raw, titles_only)
    kept: List[Dict[str, Any]] = []
    dropped: List[Tuple[Dict[str, Any], str]] = []
    for i, (cand, _t) in enumerate(pairs):
        if i in dup_map:
            dropped.append((cand, dup_map[i]))
        else:
            kept.append(cand)
    return kept, dropped
