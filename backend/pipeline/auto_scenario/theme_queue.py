"""
ThemeQueue — チャンネル別の「動画ネタストック」を持続化し、消費に応じて自動補充する。

設計:
  - data/channels/<channel_id>/theme_queue.json にキューを保存（チャンネル設定本体は汚さない）
  - 既定で target_size=10 / min_threshold=5
  - consume(): 先頭を1件取り出す
  - replenish(): ScenarioGenerator.suggest_themes() を使って Claude/GPT に新ネタを提案させる
  - ensure_stock(): 在庫が閾値以下なら target まで補充
  - 補充ロジックは ScenarioGenerator が既に持っている「除外リスト・過去テーマ・競合・トレンド」を
    そのまま使うので、ここではキュー内アイテムも除外対象に追加するだけでよい。

スレッドセーフ性:
  - 単一プロセス内ではファイル単位ロック（_LOCKS）で直列化
  - 補充は数十秒掛かることがあるので、ロック取得は短時間の "load/append/save" のみで
    LLM 呼び出しはロック外で行う
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TARGET_SIZE = 10
DEFAULT_MIN_THRESHOLD = 5
# 補充呼び出しでLLMに一度に依頼する件数の上限（極端な暴走を防ぐ）
MAX_REPLENISH_BATCH = 20


def _data_root() -> Path:
    # backend/pipeline/auto_scenario/theme_queue.py → repo_root
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "channels"


def queue_path(channel_id: str) -> Path:
    return _data_root() / channel_id / "theme_queue.json"


_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()


def _lock_for(channel_id: str) -> threading.Lock:
    with _LOCKS_LOCK:
        lk = _LOCKS.get(channel_id)
        if lk is None:
            lk = threading.Lock()
            _LOCKS[channel_id] = lk
        return lk


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _empty_queue(channel_id: str) -> Dict[str, Any]:
    return {
        "channel_id": channel_id,
        "target_size": DEFAULT_TARGET_SIZE,
        "min_threshold": DEFAULT_MIN_THRESHOLD,
        "items": [],
        "last_replenished_at": None,
        "last_checked_at": None,
        "last_error": None,
    }


def load_queue(channel_id: str) -> Dict[str, Any]:
    """ファイルから読み込み。なければ空のキューを返す（書き込みはしない）。"""
    p = queue_path(channel_id)
    if not p.exists():
        return _empty_queue(channel_id)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_queue(channel_id)
        # 後方互換 / 欠損補完
        base = _empty_queue(channel_id)
        base.update(data)
        base["channel_id"] = channel_id
        if not isinstance(base.get("items"), list):
            base["items"] = []
        return base
    except Exception as e:
        print(f"⚠️ theme_queue load failed for {channel_id}: {e}")
        return _empty_queue(channel_id)


def save_queue(channel_id: str, queue: Dict[str, Any]) -> None:
    p = queue_path(channel_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Item normalization
# ---------------------------------------------------------------------------

def _make_item(theme: Dict[str, Any], source: str = "auto") -> Optional[Dict[str, Any]]:
    """LLM の theme 出力を保存用アイテムに正規化。タイトル無しは None。"""
    if not isinstance(theme, dict):
        return None
    title = (theme.get("title") or "").strip()
    if not title:
        return None
    return {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "angle": (theme.get("angle") or "").strip(),
        "parent_title": theme.get("parent_title"),
        "is_trending": bool(theme.get("is_trending", False)),
        "trend_match": theme.get("trend_match"),
        "trend_score": theme.get("trend_score"),
        "source": source,
        "created_at": datetime.now().isoformat(),
    }


def _existing_title_keys(items: List[Dict[str, Any]]) -> set:
    return {(it.get("title") or "").strip().lower() for it in items if it.get("title")}


def _dup_reference_titles(channel_id: str, items: List[Dict[str, Any]]) -> List[str]:
    """重複判定の参照集合: キュー内タイトル + 過去に生成済みのテーマタイトル。"""
    titles = [(it.get("title") or "").strip() for it in items if it.get("title")]
    try:
        from pipeline.auto_scenario import theme_dedup as _td
        titles = titles + _td.past_theme_titles(channel_id)
    except Exception as e:
        print(f"⚠️ past theme load for dedup failed ({channel_id}): {e}")
    return [t for t in titles if t]


# ---------------------------------------------------------------------------
# Public ops
# ---------------------------------------------------------------------------

def get_status(channel_id: str) -> Dict[str, Any]:
    """フロント向けの軽量サマリ + items"""
    q = load_queue(channel_id)
    items = q.get("items", [])
    return {
        "channel_id": channel_id,
        "stock": len(items),
        "target_size": q.get("target_size", DEFAULT_TARGET_SIZE),
        "min_threshold": q.get("min_threshold", DEFAULT_MIN_THRESHOLD),
        "below_threshold": len(items) < q.get("min_threshold", DEFAULT_MIN_THRESHOLD),
        "last_replenished_at": q.get("last_replenished_at"),
        "last_checked_at": q.get("last_checked_at"),
        "last_error": q.get("last_error"),
        "items": items,
    }


def update_settings(
    channel_id: str,
    *,
    target_size: Optional[int] = None,
    min_threshold: Optional[int] = None,
) -> Dict[str, Any]:
    """target_size / min_threshold を更新。"""
    with _lock_for(channel_id):
        q = load_queue(channel_id)
        if target_size is not None:
            q["target_size"] = max(1, min(50, int(target_size)))
        if min_threshold is not None:
            q["min_threshold"] = max(0, min(int(min_threshold), q.get("target_size", DEFAULT_TARGET_SIZE)))
        save_queue(channel_id, q)
    return get_status(channel_id)


def consume(channel_id: str) -> Optional[Dict[str, Any]]:
    """先頭1件を取り出して返す。空なら None。"""
    with _lock_for(channel_id):
        q = load_queue(channel_id)
        items = q.get("items", [])
        if not items:
            return None
        item = items.pop(0)
        q["items"] = items
        save_queue(channel_id, q)
    print(f"🍴 ThemeQueue consume: [{channel_id}] {item.get('title')} (remaining: {len(items)})")
    return item


def add_item(channel_id: str, theme: Dict[str, Any], *, source: str = "manual",
             allow_near_dup: bool = False) -> Optional[Dict[str, Any]]:
    """手動で1件追加。完全一致／言い回し違い／過去テーマと実質同じなら無視（None）。

    allow_near_dup=True で語彙的な近似重複チェックを飛ばし、完全一致のみ拒否する。
    """
    new = _make_item(theme, source=source)
    if not new:
        return None
    with _lock_for(channel_id):
        q = load_queue(channel_id)
        keys = _existing_title_keys(q.get("items", []))
        if new["title"].lower() in keys:
            return None
        if not allow_near_dup:
            try:
                from pipeline.auto_scenario import theme_dedup as _td
                refs = _dup_reference_titles(channel_id, q.get("items", []))
                hit = _td.find_lexical_duplicate(new["title"], refs)
                if hit is not None:
                    print(f"  ♻️ add_item skipped near-dup: '{new['title']}' ≈ '{hit[0]}' ({hit[1]:.2f})")
                    return None
            except Exception as e:
                print(f"⚠️ add_item dedup check failed: {e}")
        q.setdefault("items", []).append(new)
        save_queue(channel_id, q)
    return new


def remove_item(channel_id: str, item_id: str) -> bool:
    with _lock_for(channel_id):
        q = load_queue(channel_id)
        before = len(q.get("items", []))
        q["items"] = [it for it in q.get("items", []) if it.get("id") != item_id]
        removed = len(q["items"]) < before
        if removed:
            save_queue(channel_id, q)
    return removed


def clear_queue(channel_id: str) -> int:
    with _lock_for(channel_id):
        q = load_queue(channel_id)
        n = len(q.get("items", []))
        q["items"] = []
        save_queue(channel_id, q)
    return n


def reorder(channel_id: str, ordered_ids: List[str]) -> Dict[str, Any]:
    """指定 ID 順に並べ替え（未指定 ID は末尾に保持）。"""
    with _lock_for(channel_id):
        q = load_queue(channel_id)
        items = q.get("items", [])
        by_id = {it.get("id"): it for it in items}
        new_order: List[Dict[str, Any]] = []
        seen = set()
        for iid in ordered_ids:
            it = by_id.get(iid)
            if it and iid not in seen:
                new_order.append(it)
                seen.add(iid)
        for it in items:
            if it.get("id") not in seen:
                new_order.append(it)
        q["items"] = new_order
        save_queue(channel_id, q)
    return get_status(channel_id)


def prioritize_trending(channel_id: str) -> Dict[str, Any]:
    """トレンドテーマをキュー先頭に移動する。

    競合分析の結果、トレンドに乗ったコンテンツは初動 1〜3 時間の
    リーチが通常の 2〜3 倍になる。FIFO では高スコアのトレンドテーマが
    非トレンドの後ろで待たされるため、トレンドスコア順にソートする。

    ソート順:
    1. is_trending=True のアイテム（trend_score 降順）
    2. is_trending=False のアイテム（元の順序を維持）

    replenish 完了時に自動で呼ばれる。
    """
    with _lock_for(channel_id):
        q = load_queue(channel_id)
        items = q.get("items", [])
        if not items:
            return get_status(channel_id)

        trending = [it for it in items if it.get("is_trending")]
        non_trending = [it for it in items if not it.get("is_trending")]

        # trend_score 降順（None は 0 扱い）
        trending.sort(key=lambda x: float(x.get("trend_score") or 0), reverse=True)

        q["items"] = trending + non_trending
        save_queue(channel_id, q)
        if trending:
            print(
                f"  🔥 ThemeQueue [{channel_id}] prioritized {len(trending)} trending themes "
                f"(top: {trending[0].get('title')}, score={trending[0].get('trend_score')})"
            )
    return get_status(channel_id)


# ---------------------------------------------------------------------------
# Replenish (LLM-driven)
# ---------------------------------------------------------------------------

def replenish(
    channel,
    scenario_generator,
    *,
    count: Optional[int] = None,
) -> Dict[str, Any]:
    """キューを target_size まで補充する。

    Args:
        channel: ChannelProfile
        scenario_generator: ScenarioGenerator インスタンス（api_key 必須）
        count: 補充件数を明示指定。None なら "target_size - 現在ストック" を使う。

    Returns:
        get_status() の結果 + "added": [...]
    """
    channel_id = channel.id

    # ロック外で必要件数を確定
    q = load_queue(channel_id)
    target = q.get("target_size", DEFAULT_TARGET_SIZE)
    current = len(q.get("items", []))
    if count is not None:
        need = max(1, min(MAX_REPLENISH_BATCH, int(count)))
    else:
        need = max(0, target - current)
    if need <= 0:
        return {**get_status(channel_id), "added": [], "skipped_reason": "already_full"}

    # 競合・トレンド情報込みで LLM に提案させる。
    # キュー内の未消費ストック・タイトルも extra_excluded として渡し、重複を防ぐ。
    print(f"  🧺 Replenishing theme queue [{channel_id}]: need {need} (target {target}, have {current})")
    err: Optional[str] = None
    suggestions: List[Dict[str, Any]] = []
    queued_titles = [it.get("title") for it in q.get("items", []) if it.get("title")]
    try:
        ask = min(MAX_REPLENISH_BATCH, need + 2)
        t0 = time.time()
        suggestions = scenario_generator.suggest_themes(
            channel,
            count=ask,
            include_trends=True,
            extra_excluded=queued_titles,
        ) or []
        print(f"  💡 suggest_themes returned {len(suggestions)} themes in {time.time()-t0:.1f}s")
    except Exception as e:
        err = str(e)
        print(f"  ❌ Replenish suggest_themes failed for {channel_id}: {e}")

    added: List[Dict[str, Any]] = []
    with _lock_for(channel_id):
        q = load_queue(channel_id)
        keys = _existing_title_keys(q.get("items", []))
        # 言い回し違い / 過去テーマとの実質重複も弾くための参照集合
        try:
            from pipeline.auto_scenario import theme_dedup as _td
        except Exception:
            _td = None  # type: ignore
        dup_refs = _dup_reference_titles(channel_id, q.get("items", []))
        for s in suggestions:
            if len(added) >= need:
                break
            item = _make_item(s, source="auto")
            if not item:
                continue
            if item["title"].lower() in keys:
                continue
            if _td is not None:
                hit = _td.find_lexical_duplicate(item["title"], dup_refs)
                if hit is not None:
                    print(f"  ♻️ replenish skipped near-dup: '{item['title']}' ≈ '{hit[0]}' ({hit[1]:.2f})")
                    continue
            q.setdefault("items", []).append(item)
            keys.add(item["title"].lower())
            dup_refs.append(item["title"])
            added.append(item)
        q["last_replenished_at"] = datetime.now().isoformat()
        q["last_checked_at"] = q["last_replenished_at"]
        if err and not added:
            q["last_error"] = err
        elif added:
            q["last_error"] = None
        save_queue(channel_id, q)

    # トレンドテーマを先頭に移動（補充直後に並べ替え）
    if added:
        prioritize_trending(channel_id)

    status = get_status(channel_id)
    status["added"] = added
    if err and not added:
        status["error"] = err
    print(f"  ✅ Queue [{channel_id}] now has {status['stock']}/{status['target_size']} (added {len(added)})")
    return status


def ensure_stock(
    channel,
    scenario_generator,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """在庫が閾値以下なら target まで補充。閾値より上なら何もしない（force=True で強制）。

    切り抜きチャンネル（style="clip"）はテーマから台本を作らず、既存長尺動画を
    素材にするのでテーマ在庫という概念が無い。巡回補充の対象から外す。
    """
    if getattr(channel, "style", "") == "clip":
        return {**get_status(channel.id), "added": [], "skipped_reason": "clip_channel"}
    q = load_queue(channel.id)
    current = len(q.get("items", []))
    threshold = q.get("min_threshold", DEFAULT_MIN_THRESHOLD)
    # last_checked_at は補充しなくても更新する（"確認した時刻" 用）
    if current >= threshold and not force:
        with _lock_for(channel.id):
            q2 = load_queue(channel.id)
            q2["last_checked_at"] = datetime.now().isoformat()
            save_queue(channel.id, q2)
        return {**get_status(channel.id), "added": [], "skipped_reason": "above_threshold"}
    return replenish(channel, scenario_generator)


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

def replenish_async(channel, scenario_generator) -> None:
    """非同期（別スレッド）で replenish。消費直後に呼ぶ用途。"""
    def _run():
        try:
            ensure_stock(channel, scenario_generator)
        except Exception as e:
            print(f"⚠️ replenish_async failed for {channel.id}: {e}")
    threading.Thread(target=_run, daemon=True, name=f"theme-queue-replenish:{channel.id}").start()


def check_all_channels(channel_manager, scenario_generator) -> Dict[str, Any]:
    """全チャンネルを巡回して在庫が閾値以下なら補充する。スケジューラから呼ぶ用途。"""
    results: Dict[str, Any] = {}
    for ch in channel_manager.list_channels():
        try:
            res = ensure_stock(ch, scenario_generator)
            results[ch.id] = {
                "stock": res.get("stock"),
                "added": len(res.get("added", [])),
                "skipped_reason": res.get("skipped_reason"),
            }
        except Exception as e:
            results[ch.id] = {"error": str(e)}
    return {"checked_at": datetime.now().isoformat(), "by_channel": results}
