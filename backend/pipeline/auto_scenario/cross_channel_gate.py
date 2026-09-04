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

使い方:
    ok, hit = check_and_reserve("scp-lab", "収容違反の正体")
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
    """
    try:
        from pipeline.auto_scenario import theme_dedup as _td
        tokens = _td._content_tokens(title or "")
    except Exception:
        return []
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


def blocking_keyword(channel_id: str, title: str,
                     *, limit: Optional[int] = None) -> Optional[Tuple[str, int]]:
    """上限に達しているキーワードがあれば (keyword, count) を返す。無ければ None。

    同じチャンネルが今日すでに使った分も数える（同一chの連投も抑えたいため）。
    ただし **同じチャンネル・同じタイトル** の再試行は数えない（生成リトライで
    自分自身にブロックされるのを防ぐ）。
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
            if not (e.get("channel") == channel_id and e.get("title") == norm_title)
        ]
        if len(entries) >= cap:
            return (kw, len(entries))
    return None


def reserve(channel_id: str, title: str) -> List[str]:
    """このタイトルのキーワードを今日の使用済みとして記録する。記録した語を返す。"""
    kws = extract_keywords(title)
    if not kws:
        return []
    data = _load()
    used = data.setdefault("used", {})
    stamp = time.strftime("%H:%M:%S")
    norm_title = (title or "").strip()
    for kw in kws:
        entries = used.setdefault(kw, [])
        # 同一ch・同一タイトルの二重予約はしない（リトライ対策）。
        if any(e.get("channel") == channel_id and e.get("title") == norm_title
               for e in entries):
            continue
        entries.append({"channel": channel_id, "title": norm_title, "at": stamp})
    _save(data)
    return kws


def check_and_reserve(channel_id: str, title: str,
                      *, limit: Optional[int] = None
                      ) -> Tuple[bool, Optional[Tuple[str, int]]]:
    """通れば予約して (True, None)、ブロックなら (False, (keyword, count))。"""
    hit = blocking_keyword(channel_id, title, limit=limit)
    if hit is not None:
        return False, hit
    reserve(channel_id, title)
    return True, None


def snapshot() -> Dict[str, Any]:
    """今日の使用状況（デバッグ・レポート用）。"""
    data = _load()
    used = data.get("used") or {}
    return {
        "date": data.get("date"),
        "limit": KEYWORD_DAILY_LIMIT,
        "keywords": {
            kw: [f"{e.get('channel')}: {e.get('title')}" for e in entries]
            for kw, entries in sorted(used.items(), key=lambda kv: -len(kv[1]))
            if len(entries) >= 2
        },
    }
