#!/usr/bin/env python3
"""daily-science のテーマキューを、修正済み dedup パイプライン経由で 10件以上に手動補充する。

- suggest_themes（429→Claudeフォールバック + 語彙/意味 dedup 込み）で新ネタを生成
- autopilot.theme_queue（ライブの自動投稿が読むキュー）と
  data/channels/daily-science/theme_queue.json（モジュール側キュー）の両方を更新
- 既存キュー内の「過去テーマと実質重複」アイテムは除去してから補充
"""
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).parent
sys.path.insert(0, str(BACKEND))
for line in (BACKEND / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from channels import ChannelManager
from pipeline.auto_scenario import ScenarioGenerator
from pipeline.auto_scenario import theme_dedup as td
from pipeline.auto_scenario import theme_queue as tq

import sys as _sys
CHANNEL_ID = _sys.argv[1] if len(_sys.argv)>1 else "daily-science"
TARGET = int(_sys.argv[2]) if len(_sys.argv)>2 else 12
REPO = BACKEND.parent

cm = ChannelManager()
ch = cm.get(CHANNEL_ID)
sg = ScenarioGenerator()

past = td.past_theme_titles(CHANNEL_ID)
print(f"📚 past themes: {len(past)}")

# --- 1. 既存キューの dup 掃除 ---------------------------------------------
raw_path = REPO / "data" / "channels" / f"{CHANNEL_ID}.json"
raw = json.loads(raw_path.read_text(encoding="utf-8"))
ap = raw.get("autopilot") or {}
from pipeline.auto_scenario.generator import GPT_MODEL_LIGHT
_llm = lambda m: sg._call_text_with_fallback(m, temperature=0.0, max_tokens=1500, gpt_model=GPT_MODEL_LIGHT)


def _is_past_dup(title):
    """語彙 → 意味 の順で過去テーマとの実質重複を判定。"""
    hit = td.find_lexical_duplicate(title, past)
    if hit:
        return hit[0], hit[1]
    _, dropped = td.semantic_filter([{"title": title}], past, llm_call=_llm)
    if dropped:
        return dropped[0][1], "semantic"
    return None


old_q = list(ap.get("theme_queue") or [])
clean_q = []
for it in old_q:
    title = (it.get("title") or "").strip()
    dup = _is_past_dup(title) if title else None
    if dup:
        print(f"  🗑️ drop existing autopilot dup: '{title}' ≈ '{dup[0]}' ({dup[1]})")
    elif title:
        clean_q.append(it)
print(f"autopilot.theme_queue: {len(old_q)} → {len(clean_q)} after dup cleanup")

# --- 2. 新ネタ生成（dedup 込み） -------------------------------------------
print("🧠 generating fresh themes (429→Claude fallback + dedup)...")
suggested = sg.suggest_themes(ch, count=TARGET + 4, include_trends=True) or []
print(f"  suggest_themes returned {len(suggested)} themes (already deduped)")

# 既存clean_qタイトルとの語彙重複も最終チェックして追加
existing_titles = [i["title"] for i in clean_q] + past
added = []
for s in suggested:
    if not isinstance(s, dict) or not (s.get("title") or "").strip():
        continue
    title = s["title"].strip()
    if td.find_lexical_duplicate(title, existing_titles + [a["title"] for a in added]):
        continue
    added.append({"id": uuid.uuid4().hex[:8], "title": title, "angle": (s.get("angle") or "").strip()})

new_autopilot_q = clean_q + added
ap["theme_queue"] = new_autopilot_q
raw["autopilot"] = ap
raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✅ autopilot.theme_queue now {len(new_autopilot_q)} items (+{len(added)} new)")

# --- 3. モジュール側キューも同じネタで補充 ---------------------------------
mod = tq.load_queue(CHANNEL_ID)
mod_clean = []
for it in mod.get("items", []):
    title = (it.get("title") or "").strip()
    dup = _is_past_dup(title) if title else None
    if dup:
        print(f"  🗑️ drop module-queue dup: '{title}' ≈ '{dup[0]}' ({dup[1]})")
    elif title:
        mod_clean.append(it)
mod["items"] = mod_clean
mod["last_error"] = None
tq.save_queue(CHANNEL_ID, mod)
for a in added:
    tq.add_item(CHANNEL_ID, {"title": a["title"], "angle": a["angle"]}, source="manual")
final_mod = tq.get_status(CHANNEL_ID)
print(f"✅ module theme_queue now {final_mod['stock']} items")

print("\n=== FINAL autopilot.theme_queue ===")
for i, it in enumerate(new_autopilot_q, 1):
    print(f"  {i:2}. {it['title']}")
