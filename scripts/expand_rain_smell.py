"""シナリオの full_scenario 各行を 1.5倍に膨らませて 12分台を狙う。

- speaker / expression は維持
- 各行 88〜110 字（目標 95 字）に拡張
- 既存の illustrations/ キャッシュは同じ title で再レンダーすれば自動再利用される
"""
import os
import sys
import json
import time
import urllib.request
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
MAIN_REPO_ENV = Path("/Users/ayukiyamazaki/Developer/youtube-factory/backend/.env")
WORKTREE_ENV = WORKTREE / "backend" / ".env"

ENV_PATH = WORKTREE_ENV if WORKTREE_ENV.exists() else MAIN_REPO_ENV
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

API_KEY = os.environ["OPENAI_API_KEY"]

SCENARIO_PATH = (
    WORKTREE / "data" / "scenarios" / "daily-science"
    / "雨の匂いの正体とはペトリコールの科学を解明.json"
)
BACKUP_PATH = SCENARIO_PATH.with_suffix(".v1_short.json")

scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
full = scenario["full_scenario"]

if not BACKUP_PATH.exists():
    BACKUP_PATH.write_text(SCENARIO_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"📦 backup: {BACKUP_PATH.name}")

print(f"📄 lines: {len(full)}, total: {sum(len(e['text']) for e in full)} chars")


def call_gpt(messages, max_tokens=8000, temperature=0.7):
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    })
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def extract_json(text):
    text = text.strip()
    if "```json" in text:
        i = text.index("```json") + 7
        j = text.index("```", i)
        text = text[i:j].strip()
    elif "```" in text:
        i = text.index("```") + 3
        j = text.index("```", i)
        text = text[i:j].strip()
    return json.loads(text)


# 行を 8 件ずつバッチで拡張
BATCH = 8
expanded_full = []
for start in range(0, len(full), BATCH):
    chunk = full[start:start + BATCH]
    prompt = f"""次のゆっくり解説対話の各行を、内容を膨らませて 1.5 倍程度に拡張してください。

# 制約
- 各行 88〜110 文字（目標 95 文字、最低 88 文字）
- speaker と expression は元のまま完全保持
- 行の主旨・話者・流れは変えない
- 元のセリフの内容を保ったまま、研究データ・具体的な数字・例え話・歴史エピソードを加えて自然に膨らませる
- リコ・マコトの口調はそのまま（「だね」「だよ」「〜なんだ」）
- 日本語として自然で、TTS で読み上げても違和感のない文に
- text 内のキャラ名はカタカナ（リコ・マコト）。漢字は使わない。
- 句点直後に改行 \\n は不要（pause で吸収されるので普通の文で OK）

# 入力（行 {start+1}〜{start+len(chunk)} of {len(full)}）
{json.dumps(chunk, ensure_ascii=False, indent=2)}

# 出力
入力と同じ件数・同じ順序の JSON 配列。各要素は {{"speaker":..., "text":..., "expression":...}}。JSON のみ出力。"""

    print(f"\n🤖 expanding {start+1}〜{start+len(chunk)} of {len(full)}...")
    raw = call_gpt(
        [
            {"role": "system", "content": "JSON 配列のみ出力。各行 88〜110 字。speaker / expression は元通り。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4000,
        temperature=0.7,
    )
    arr = extract_json(raw)
    if not isinstance(arr, list) or len(arr) != len(chunk):
        print(f"  ⚠️ unexpected output (got {len(arr) if isinstance(arr,list) else 'non-list'} items, expected {len(chunk)})")
        # フォールバックで元の行を保持
        expanded_full.extend(chunk)
        continue

    # speaker/expression を強制的に元のまま上書き（GPT が変えてしまった場合の保険）
    for orig, new in zip(chunk, arr):
        new["speaker"] = orig["speaker"]
        new["expression"] = orig["expression"]
        if not isinstance(new.get("text"), str) or len(new["text"]) < 60:
            print(f"  ⚠️ short line ({len(new.get('text',''))} chars) — keep original")
            new["text"] = orig["text"]
    chars = [len(x["text"]) for x in arr]
    print(f"  ✅ {len(arr)} lines, avg {sum(chars)/len(chars):.1f} chars (orig avg {sum(len(x['text']) for x in chunk)/len(chunk):.1f})")
    expanded_full.extend(arr)
    time.sleep(0.5)


total = sum(len(e["text"]) for e in expanded_full)
avg = total / len(expanded_full)
print(f"\n📊 expanded: {len(expanded_full)} lines, {total} chars, avg {avg:.1f}/line")
print(f"   estimated duration @7.8c/s: {total/7.8/60:.1f} min")

scenario["full_scenario"] = expanded_full
SCENARIO_PATH.write_text(
    json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"💾 saved: {SCENARIO_PATH.name}")
