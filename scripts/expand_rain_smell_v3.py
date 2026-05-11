"""残りの 88 字未満の行だけを狙い撃ちで再拡張する v3。

別プロンプト（最低 95 字、補強の方向性を明示）で 2 回まで再試行。
v2 結果を上書きする。
"""
import os
import json
import time
import urllib.request
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
ENV_PATH = Path("/Users/ayukiyamazaki/Developer/youtube-factory/backend/.env")
for line in ENV_PATH.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
API_KEY = os.environ["OPENAI_API_KEY"]

SCENARIO_PATH = (
    WORKTREE / "data" / "scenarios" / "daily-science"
    / "雨の匂いの正体とはペトリコールの科学を解明.json"
)
scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
full = scenario["full_scenario"]


def call_gpt(messages, max_tokens=600, temperature=0.85):
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
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def parse_text(raw):
    s = raw.strip()
    if "```" in s:
        i = s.find("```")
        s = s[i + 3:]
        if s.startswith("json"):
            s = s[4:]
        j = s.find("```")
        if j >= 0:
            s = s[:j]
    s = s.strip()
    try:
        return json.loads(s).get("text", "").strip()
    except Exception:
        return ""


def reexpand(orig_text, speaker, prev2):
    sys_msg = (
        "あなたはゆっくり解説対話の脚本ライターです。"
        "次のセリフを 100〜115 字に書き直してください。出力は必ず {\"text\":\"...\"} の JSON のみ。"
    )
    prev_ctx = " / ".join(prev2) if prev2 else "（先頭）"
    user_msg = (
        f"# 元のセリフ ({speaker}, {len(orig_text)} 字)\n"
        f"「{orig_text}」\n\n"
        f"# 直前の流れ\n{prev_ctx}\n\n"
        f"# 書き直しの方向\n"
        f"- 必ず 100〜115 字（99 字以下も 116 字以上も NG）\n"
        f"- 元の主旨・話者の口調はそのまま\n"
        f"- 化学・気象学・生態学の常識的な範囲で具体例・数字・例え話を 1 つ加える\n"
        f"- 文末「〜だね」「〜なんだ」「〜だよ」など対話らしさを残す\n"
        f"- 人名はカタカナ「リコ」「マコト」のみ（漢字禁止）\n"
        f"- 改行・記号・絵文字なし、自然な 1〜2 文に\n"
    )
    last = orig_text
    for attempt in range(3):
        raw = call_gpt(
            [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ]
        )
        t = parse_text(raw)
        if 95 <= len(t) <= 130:
            return t, attempt + 1
        if len(t) > len(last):
            last = t
    return last, 3


prev_pool = [e["text"] for e in full]
under_idx = [i for i, e in enumerate(full) if len(e["text"]) < 88]
print(f"🎯 short lines to re-expand: {len(under_idx)}")
print(f"   before: total {sum(len(e['text']) for e in full)} chars, "
      f"avg {sum(len(e['text']) for e in full)/len(full):.1f}/line")

for k, i in enumerate(under_idx):
    entry = full[i]
    orig = entry["text"]
    prev2 = prev_pool[max(0, i - 2):i]
    new_text, tries = reexpand(orig, entry["speaker"], prev2)
    n = len(new_text)
    flag = "✅" if 95 <= n <= 130 else "⚠️"
    print(f"  {flag} [{k+1:2d}/{len(under_idx)}] (line {i+1:2d}) {entry['speaker']}: "
          f"{len(orig)}→{n} 字 (try {tries})")
    full[i]["text"] = new_text
    time.sleep(0.3)

total = sum(len(e["text"]) for e in full)
avg = total / len(full)
under = sum(1 for e in full if len(e["text"]) < 88)
print(f"\n📊 after v3: {len(full)} lines, {total} chars, avg {avg:.1f}/line, "
      f"{under} still under 88")
print(f"   estimated duration @7.5c/s: {total/7.5/60 + 0.3*len(full)/60:.1f} min")

scenario["full_scenario"] = full
SCENARIO_PATH.write_text(
    json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"💾 saved: {SCENARIO_PATH.name}")
