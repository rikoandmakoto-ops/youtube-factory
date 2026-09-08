"""cross_channel_gate — 同じ日に全チャンネル横断で同じキーワードが並ぶのを防ぐゲート。

背景（2026-09-04）:
    `theme_dedup` はチャンネル**内**の重複しか見ていない。ところが 09-03 の
    タイトル分析で「正体」を強語として全チャンネルの `theme_priority` に入れた結果、
    同じ日に **5ch が同時に「正体」入りのタイトル**を投稿した。1chずつ見れば重複
    ではないので既存ゲートは全部素通りする。視聴者から見ると同じ運営の別チャンネルが
    同じ日に同じ煽り文句を並べている状態で、ショートのフィードでは共食いになる。

設計:
    - 判定単位は「日付（ローカル）× キーワード」。同日中に同一キーワードは
      **既定 2 本まで**（`KEYWORD_DAILY_LIMIT`）。3本目以降は候補を落とす。
    - キーワードの抽出は `theme_dedup._content_tokens` を再利用する（漢字連・
      カタカナ連・英数連のみ。助詞や定型語は落ちる）。ここで新しい正規化を
      作ると重複判定と基準がズレるため、必ず同じ関数を通す。
    - 状態は `data/analytics/cross_channel_keywords.json` に置く。日付が変われば
      中身は捨てる（履歴として残す必要がない。溜めても判断に使わない）。
    - 「予約（reserve）」は実際にテーマを取り出した瞬間に行う。生成に失敗しても
      枠が1つ消えるだけで、翌日にはリセットされるので実害は無い。

【2026-09-08】1本の動画が枠を2つ食っていた:
    1本の生成につき予約が **2回** 走る。テーマ取り出し時（`_pop_or_refill_theme`）が
    キューの題名で、最終タイトル確定時（`generator._enforce_cross_channel_keywords`）が
    LLM が書き直した題名で予約する。リトライ除外は (channel, title) の完全一致だったので、
    書き直しで文字列が変われば別物として積まれる。実測（09-08 の状態ファイル）:

        正体   daily-science 06:45「…喉が鉄の味になる正体は血液ではない」
               daily-science 06:47「…あなたの肺で何が？0.1%の正体」  ← 同じ1本

    上限2に対して1本で2枠なので、**その日の最初の1本が全chの「正体」を締め出す**。
    09-07 に横断ゲートが114回発動したのはこれが主因で、キーワードが人気だからではない。
    対策として予約に `key`（＝1本の生成を指す識別子。既定はテーマ題名）を持たせ、
    同じ `key` の再予約は追記ではなく**置き換え**にした。

使い方:
    ok, hit = check_and_reserve("scp-lab", "収容違反の正体", key="scp-lab:収容違反")
    if not ok:  # hit == ("正体", 2)
        次の候補へ
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# data/analytics/cross_channel_keywords.json
_STATE_PATH = (Path(__file__).resolve().parent.parent.parent.parent
               / "data" / "analytics" / "cross_channel_keywords.json")

# 同一日に同じキーワードを使ってよい本数。3本目からブロックする。
KEYWORD_DAILY_LIMIT = 2

# 【2026-09-08】「答え提示語」は話題語と別枠にする。
# 09-08 の実測で、この9語のいずれかを含むタイトルは 登録/千再生 0.57、
# 含まないものは 0.31（1.84倍・n=196）だったため、全6ch・全枠でどれか1語を
# 入れる方針になった。ところが 6ch × 3枠 = 18本/日 に対し、話題語と同じ上限2で
# 数えると 9語 × 2 = 18 で **余裕がゼロ**になる。1語でも偏れば必ずブロックが出る
# （09-07 に横断ゲートが114回発動した二次要因）。
# 語そのものは共食いの原因ではない（共食いするのは題材）ので、上限を分けて緩める。
# 偏り自体はチャンネルごとに主軸の語を割り振ることで抑える
# （→ 各ch の theme_priority.title_style「答え提示語の割り当て」）。
ANSWER_MARKER_KEYWORDS = {
    "理由", "正体", "本当の", "実は", "わけ", "なぜ", "真相", "裏側", "実態",
}
ANSWER_MARKER_DAILY_LIMIT = 3

# キーワードとして数えない語。
#   - チャンネル名・シリーズ名に必ず入る語（話題を区別しない）
#   - 「ショート」のような媒体語（theme_dedup で過去に偽陽性を出した実績あり）
#   - 単独では話題にならない汎用名詞
# ここに無い語でも 1 文字なら数えない（偶然一致が多すぎるため）。
STOP_KEYWORDS = {
    "ショート", "解説", "ゆっくり", "動画", "今回", "紹介", "雑学", "豆知識",
    "scp", "財団", "異常", "収容",          # scp-lab の定型
    "妖怪", "伝承", "民話",                  # yokai-watch の定型
    "ポケモン", "ポケ", "図鑑",              # pokemon-lab の定型
    "企業", "会社", "社員",                  # company-facts の定型
    "論文", "研究", "実験",                  # fake-paper の定型
    "科学", "日常",                          # daily-science の定型
    "まとめ", "スレ",                        # 2ch-matome の定型
    "司書", "書庫",                          # akashic-librarian の定型
    "切り抜き",
}

# 抽出したキーワードのうち、これ以上の長さのものだけを対象にする。
# 「正体」「真実」「末路」のような 2 文字の煽り語を拾うのが本来の目的なので 2。
MIN_KEYWORD_LEN = 2

_DIGITS_ONLY = re.compile(r"^[0-9]+$")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def extract_keywords(title: str) -> List[str]:
    """タイトルから横断チェック対象のキーワードを抽出する。

    `theme_dedup._content_tokens` と同じ正規化を通すので、重複判定と語の切り方が
    ズレない。数字だけの語とストップワードは落とす。

    ただし**答え提示語だけは自分で拾い直す**。theme_dedup 側は 09-08 に
    これらを「定型句」として正規化で落とすようにした（型が話題語として重み付け
    され、題材の違う2本を重複と誤判定していたため）。その処理をそのまま通すと
    「正体」がキーワードでなくなり、09-03 に5chが同時に『正体』を出した件への
    ゲート（09-04 に入れたこのモジュールの存在理由）が**無言で消える**。
    重複判定で落とすことと、横断で本数を数えることは目的が違うので、ここで戻す。
    """
    try:
        from pipeline.auto_scenario import theme_dedup as _td
        tokens = _td._content_tokens(title or "")
    except Exception:
        return []
    raw = (title or "")
    tokens = list(tokens) + [m for m in ANSWER_MARKER_KEYWORDS if m in raw]
    out: List[str] = []
    seen = set()
    for tok in tokens:
        t = tok.strip().lower()
        if len(t) < MIN_KEYWORD_LEN:
            continue
        if t in STOP_KEYWORDS or _DIGITS_ONLY.match(t):
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _load() -> Dict[str, Any]:
    """状態を読む。日付が変わっていれば空にして返す。"""
    today = _today()
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict) or data.get("date") != today:
        return {"date": today, "used": {}}
    if not isinstance(data.get("used"), dict):
        data["used"] = {}
    return data


def _save(data: Dict[str, Any]) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ cross_channel_gate: 状態を保存できません: {e}")


def _limit(limit: Optional[int]) -> int:
    try:
        v = int(limit) if limit is not None else KEYWORD_DAILY_LIMIT
    except (TypeError, ValueError):
        v = KEYWORD_DAILY_LIMIT
    return max(0, v)


def _limit_for(keyword: str, base: int) -> int:
    """語ごとの上限。答え提示語だけ別枠（→ ANSWER_MARKER_DAILY_LIMIT）。

    チャンネル側で `cross_channel_keyword_limit` を base より高く指定していれば、
    そちらを尊重して下げない。
    """
    if keyword in ANSWER_MARKER_KEYWORDS:
        return max(base, ANSWER_MARKER_DAILY_LIMIT)
    return base


def _is_own(entry: Dict[str, Any], channel_id: str, norm_title: str,
            key: Optional[str]) -> bool:
    """この予約が「自分自身（同じ1本の生成）」のものか。

    `key` があれば key だけで判定する。1本の生成はテーマ取り出し時と最終タイトル
    確定時で **題名が変わる** ので、題名の一致で自分自身を見分けることはできない。
    key を持たない古い予約と、key を渡さない呼び出しのために題名一致も残す。
    """
    if entry.get("channel") != channel_id:
        return False
    if key and entry.get("key"):
        return entry.get("key") == key
    return entry.get("title") == norm_title


def blocking_keyword(channel_id: str, title: str,
                     *, limit: Optional[int] = None,
                     key: Optional[str] = None) -> Optional[Tuple[str, int]]:
    """上限に達しているキーワードがあれば (keyword, count) を返す。無ければ None。

    同じチャンネルが今日すでに使った分も数える（同一chの連投も抑えたいため）。
    ただし **同じ1本の生成** による再試行は数えない（`key`。生成リトライや
    最終タイトルの書き直しで自分自身にブロックされるのを防ぐ）。
    """
    cap = _limit(limit)
    if cap <= 0:
        return None
    data = _load()
    used = data.get("used") or {}
    norm_title = (title or "").strip()
    for kw in extract_keywords(title):
        entries = [
            e for e in (used.get(kw) or [])
            if not _is_own(e, channel_id, norm_title, key)
        ]
        if len(entries) >= _limit_for(kw, cap):
            return (kw, len(entries))
    return None


def reserve(channel_id: str, title: str, *, key: Optional[str] = None) -> List[str]:
    """このタイトルのキーワードを今日の使用済みとして記録する。記録した語を返す。

    同じ `key` の予約が既にあれば**置き換える**（追記しない）。1本の生成が
    上限の枠を2つ食う事故を防ぐための中核。
    """
    kws = extract_keywords(title)
    data = _load()
    used = data.setdefault("used", {})
    stamp = time.strftime("%H:%M:%S")
    norm_title = (title or "").strip()

    if key:
        # 題名が書き換わると語の集合も変わる。古い語の予約を先に取り消してから
        # 積み直さないと、書き直しで捨てたはずの語が枠を握ったまま残る。
        for kw, entries in list(used.items()):
            kept = [e for e in entries
                    if not (e.get("channel") == channel_id and e.get("key") == key)]
            if kept:
                used[kw] = kept
            else:
                used.pop(kw, None)

    if not kws:
        _save(data)
        return []

    for kw in kws:
        entries = used.setdefault(kw, [])
        if any(_is_own(e, channel_id, norm_title, key) for e in entries):
            continue
        entry: Dict[str, Any] = {"channel": channel_id, "title": norm_title, "at": stamp}
        if key:
            entry["key"] = key
        entries.append(entry)
    _save(data)
    return kws


def reservation_key(channel_id: str, theme_title: str) -> str:
    """1本の生成を指す予約キー。テーマ題名は書き直されないのでこれを軸にする。"""
    return f"{channel_id}::{(theme_title or '').strip()}"


def check_and_reserve(channel_id: str, title: str,
                      *, limit: Optional[int] = None,
                      key: Optional[str] = None
                      ) -> Tuple[bool, Optional[Tuple[str, int]]]:
    """通れば予約して (True, None)、ブロックなら (False, (keyword, count))。"""
    hit = blocking_keyword(channel_id, title, limit=limit, key=key)
    if hit is not None:
        return False, hit
    reserve(channel_id, title, key=key)
    return True, None


def snapshot() -> Dict[str, Any]:
    """今日の使用状況（デバッグ・レポート用）。"""
    data = _load()
    used = data.get("used") or {}
    return {
        "date": data.get("date"),
        "limit": KEYWORD_DAILY_LIMIT,
        "answer_marker_limit": ANSWER_MARKER_DAILY_LIMIT,
        "keywords": {
            kw: {
                "limit": _limit_for(kw, KEYWORD_DAILY_LIMIT),
                "used": [f"{e.get('channel')}: {e.get('title')}" for e in entries],
            }
            for kw, entries in sorted(used.items(), key=lambda kv: -len(kv[1]))
            if len(entries) >= 2
        },
    }
