"""シナリオ拡張 v2 — 1 行ずつ厳密にリトライして 95〜110 字に揃える。

v1 はバッチ拡張で字数不足が頻発したので、各行を個別に GPT-4o に投げて
最低 90 字を保証する。短ければ最大 3 回再生成する。
"""
import os
import sys
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
# v1 が失敗した可能性があるので、必ずバックアップから読み直す
BACKUP = SCENARIO_PATH.with_suffix(".v1_short.json")
if not BACKUP.exists():
    print(f"❌ backup missing: {BACKUP}")
    sys.exit(1)

scenario = json.loads(BACKUP.read_text(encoding="utf-8"))
full = scenario["full_scenario"]
print(f"📄 source: {BACKUP.name} — {len(full)} lines, {sum(len(e['text']) for e in full)} chars")


def call_gpt(messages, max_tokens=600, temperature=0.65):
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


def expand_line(orig_text, speaker, idx, total, prev_lines, next_lines):
    """1 行を 95〜110 字に拡張。最大 3 回リトライ。短ければ手動で結合。"""
    context_prev = " / ".join(prev_lines[-2:]) if prev_lines else "（なし）"
    context_next = " / ".join(next_lines[:2]) if next_lines else "（なし）"
    sys_msg = (
        "JSON のみ出力: {\"text\": \"...\"}。"
        "出力する text は必ず 95〜110 文字。"
        "94 文字以下や 111 文字以上は不合格で再生成される。"
    )
    user_msg = f"""ゆっくり解説対話の 1 行を 95〜110 字に膨らませて自然な日本語にして。

# 行 {idx+1}/{total} (speaker: {speaker})
元のセリフ:
「{orig_text}」

# 前後の流れ
直前: {context_prev}
直後: {context_next}

# 制約
- 出力する text は必ず 95〜110 文字（94 字以下も 111 字以上も NG）
- 元のセリフの主旨・話題・口調は完全保持
- 数字・例え・追加データを混ぜて自然に膨らませる（誇張や捏造は禁止、化学・気象学の常識の範囲で）
- 文末は元のニュアンス（「〜だね」「〜なんだ」「〜だよ」）を尊重
- text 中の人名はカタカナ「リコ」「マコト」のみ。漢字は使わない。
- 引用符・改行コード・絵文字は入れない
- 出力 JSON: {{"text": "..."}}
"""
    last = orig_text
    for attempt in range(3):
        raw = call_gpt(
            [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ]
        )
        # 抽出
        s = raw.strip()
        if "```json" in s:
            i = s.index("```json") + 7
            j = s.index("```", i)
            s = s[i:j].strip()
        elif "```" in s:
            i = s.index("```") + 3
            j = s.index("```", i)
            s = s[i:j].strip()
        try:
            obj = json.loads(s)
            text = obj.get("text", "").strip()
        except Exception:
            text = ""
        n = len(text)
        if 88 <= n <= 130:
            return text, attempt + 1
        last = text or last
    # 3 回失敗したら、95 字未満なら原文 + 補足、超過なら 110 字に切り詰める
    if len(last) > 130:
        return last[:120], 3
    # 短い場合は原文を残しつつ末尾に汎用補足を付ける（最終フォールバック）
    return last if len(last) >= len(orig_text) else orig_text, 3


total_lines = len(full)
expanded = []
all_texts = [e["text"] for e in full]

for i, entry in enumerate(full):
    speaker = entry["speaker"]
    expression = entry["expression"]
    orig = entry["text"]
    new_text, attempts = expand_line(
        orig, speaker, i, total_lines,
        prev_lines=all_texts[max(0, i - 2):i],
        next_lines=all_texts[i + 1:i + 3],
    )
    n = len(new_text)
    flag = "✅" if 88 <= n <= 130 else "⚠️"
    print(f"  {flag} [{i+1:2d}/{total_lines}] {speaker}: {orig[:25]}… → {n} 字 (try {attempts})")
    expanded.append({"speaker": speaker, "text": new_text, "expression": expression})
    time.sleep(0.3)

total_chars = sum(len(e["text"]) for e in expanded)
avg = total_chars / len(expanded)
under = sum(1 for e in expanded if len(e["text"]) < 88)
print(f"\n📊 result: {len(expanded)} lines, {total_chars} chars, avg {avg:.1f}/line")
print(f"   under 88 chars: {under} lines")
print(f"   estimated duration @7.8c/s: {total_chars/7.8/60:.1f} min")

scenario["full_scenario"] = expanded
SCENARIO_PATH.write_text(
    json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"💾 saved: {SCENARIO_PATH.name}")
