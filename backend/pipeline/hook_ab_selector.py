"""Hook A/B Selector — 冒頭フックの最適化（Round 6）。

狙い:
    ショートの視聴継続は**最初の1秒**で決まる（2026年調査: スワイプ判断は
    3秒ではなく1秒以内に発生）。scenario_validator は冒頭フック型の
    「有無」をチェックするだけだが、このモジュールは：

    1. 生成済みフックに加えて2つの代替フックをGPT-lightで生成
    2. 5軸（好奇心ギャップ・簡潔さ・感情トリガー・スクロール停止力・ループ接続）で採点
    3. 最高スコアのフックに差し替える

    これにより冒頭1秒のスワイプ防止率を最大化する。

既存モジュールとの違い:
    - scenario_validator: フック型の有無を検証（pass/fail）→ 差し替えはしない
    - title_quality: タイトルのCTRスコア → フック（シナリオ1行目）は対象外
    - ab_test_generator: YouTubeのA/Bテスト用にタイトル/サムネを複数生成 → シナリオ本文は対象外
"""

from __future__ import annotations

import json
import os
import re
import random
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from pipeline import openai_compat
except ImportError:
    openai_compat = None  # type: ignore

try:
    from pipeline import api_usage
except ImportError:
    api_usage = None  # type: ignore

GPT_MODEL_LIGHT = "gpt-5.6-luna"

# 採点の重み（合計 100）
SCORING_WEIGHTS = {
    "curiosity_gap": 25,     # 好奇心ギャップ: 答えを知りたくさせるか
    "brevity": 15,           # 簡潔さ: 15-30字で断定的か
    "emotional_trigger": 20, # 感情トリガー: 驚き・共感・恐怖を引くか
    "scroll_stop": 25,       # スクロール停止力: 「指を止める」パワー
    "loop_connect": 15,      # ループ接続: 最終行から戻ったとき意味が変わるか
}

# チャンネル別のフック生成プロンプト追加指示
CHANNEL_HOOK_HINTS: Dict[str, str] = {
    "daily-science": "身近な疑問を突く。「え、マジで？」と思わせる日常の科学。",
    "scp-lab": "不気味さ・禁忌感を出す。「知ってはいけない」感。",
    "2ch-matome": "下ネタ・エロ面白系。「草」「ワロタ」が出る面白さ。くだけた口調。",
    "company-facts": "年収・ブラック・ホンネ。誰もが気になる企業の裏側。",
    "pokemon-lab": "裏設定・闇設定。「え、あのポケモンって…」の衝撃。",
    "yokai-watch": "実在する恐怖。「あなたの地域にもいるかも」の身近な怖さ。",
    "akashic-librarian": "未解決・未解明の謎。「この記録は、まだ閉じられていない」。",
}


# =====================================================================
# ルールベース採点（GPTフォールバック用）
# =====================================================================

def _rule_based_score(hook: str, last_line: str = "") -> Dict[str, int]:
    """GPTが使えないときのフォールバック採点。"""
    scores: Dict[str, int] = {}

    # 好奇心ギャップ: 疑問形・伏せ字・「実は」等
    curiosity = 0
    if re.search(r"[？?]", hook):
        curiosity += 15
    if re.search(r"実は|知って(た|る)|なんで|なぜ", hook):
        curiosity += 10
    if re.search(r"ヤバ|とんでもない|信じられない", hook):
        curiosity += 5
    scores["curiosity_gap"] = min(25, curiosity)

    # 簡潔さ: 15-30字が理想
    length = len(hook)
    if 15 <= length <= 30:
        scores["brevity"] = 15
    elif 10 <= length <= 40:
        scores["brevity"] = 10
    else:
        scores["brevity"] = 5

    # 感情トリガー
    emotion = 0
    if re.search(r"ヤバ|怖|驚|衝撃|闇|禁|死|草|ワロタ|エロ", hook):
        emotion += 15
    if re.search(r"あなた|君|お前|ワイ", hook):
        emotion += 5
    scores["emotional_trigger"] = min(20, emotion)

    # スクロール停止力: 数字・固有名詞・対比
    stop = 0
    if re.search(r"\d+", hook):
        stop += 10
    if re.search(r"[一-鿿]{3,}", hook):  # 3文字以上の漢字塊 = 固有名詞っぽい
        stop += 8
    if re.search(r"のに|けど|でも|なのに", hook):  # 対比
        stop += 7
    scores["scroll_stop"] = min(25, stop)

    # ループ接続: 最終行との共通ワードがあるか
    if last_line:
        hook_words = set(re.findall(r"[一-鿿゠-ヿ]{2,}", hook))
        last_words = set(re.findall(r"[一-鿿゠-ヿ]{2,}", last_line))
        overlap = hook_words & last_words
        scores["loop_connect"] = 15 if overlap else 5
    else:
        scores["loop_connect"] = 8  # 判定不可 → 中間

    return scores


def _total_score(scores: Dict[str, int]) -> int:
    return sum(scores.values())


# =====================================================================
# GPTベースのフック生成
# =====================================================================

def _call_gpt_light(
    messages: List[Dict[str, str]],
    api_key: str,
    *,
    temperature: float = 0.9,
    max_tokens: int = 1500,
) -> Optional[str]:
    """GPT-light で短い JSON を返させる軽量呼び出し。"""
    if not api_key:
        return None

    if openai_compat is None:
        return None

    url = "https://api.openai.com/v1/chat/completions"
    payload = json.dumps(openai_compat.build_chat_payload(
        GPT_MODEL_LIGHT, messages, temperature=temperature, max_tokens=max_tokens,
    ))

    req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST",
                                 headers={
                                     "Content-Type": "application/json",
                                     "Authorization": f"Bearer {api_key}",
                                 })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ hook_ab GPT-light call failed: {e}")
        return None


def _generate_alternatives(
    original_hook: str,
    theme_title: str,
    channel_id: str,
    last_line: str,
    api_key: str,
) -> List[str]:
    """GPT-lightで2つの代替フックを生成する。"""
    hint = CHANNEL_HOOK_HINTS.get(channel_id, "")
    messages = [
        {
            "role": "system",
            "content": (
                "あなたはYouTubeショートの冒頭フック専門のコピーライター。\n"
                "JSON のみ出力。余計な説明は不要。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"テーマ: {theme_title}\n"
                f"チャンネルの方向性: {hint}\n"
                f"元のフック: {original_hook}\n"
                f"最終行: {last_line}\n\n"
                "上記テーマで、元のフックとは**異なるアプローチ**の冒頭1行目を2つ生成して。\n"
                "条件:\n"
                "- 各15〜30字\n"
                "- 疑問形か驚き形で始める\n"
                "- 答えを言わない（好奇心ギャップを作る）\n"
                "- 最終行と共通するキーワードを1つ入れるとループ再生に効く\n"
                "- 視聴者を直接指す語（あなた/君/お前ら）を入れるとスクロールが止まる\n\n"
                '出力: {"hooks": ["フック1", "フック2"]}'
            ),
        },
    ]
    raw = _call_gpt_light(messages, api_key)
    if not raw:
        return []

    try:
        # JSON 抽出
        match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
        else:
            parsed = json.loads(raw)
        hooks = parsed.get("hooks", [])
        return [str(h).strip() for h in hooks if isinstance(h, str) and h.strip()][:2]
    except Exception:
        return []


# =====================================================================
# メインエントリポイント
# =====================================================================

def select_best_hook(
    short_scenario: List[Dict[str, Any]],
    *,
    theme_title: str = "",
    channel_id: str = "",
    api_key: str = "",
) -> Dict[str, Any]:
    """冒頭フックA/B選択のメインエントリポイント。

    Args:
        short_scenario: シナリオの行リスト（各行は {"speaker": ..., "text": ...}）。
        theme_title: テーマのタイトル。
        channel_id: チャンネルID。
        api_key: OpenAI API キー。

    Returns:
        {
            "modified": bool,        # フックが差し替わったか
            "original_hook": str,     # 元のフック
            "selected_hook": str,     # 選択されたフック
            "scores": [...],          # 全候補のスコア
            "reason": str,            # 選択理由
        }
    """
    if not short_scenario:
        return {"modified": False, "reason": "empty_scenario"}

    # 1行目と最終行のテキストを取得
    first_entry = short_scenario[0]
    original_hook = (first_entry.get("text") or first_entry.get("line") or "").strip()
    if not original_hook:
        return {"modified": False, "reason": "empty_first_line"}

    # 最終コンテンツ行（CTA行を除く）
    last_line = ""
    for entry in reversed(short_scenario):
        text = (entry.get("text") or entry.get("line") or "").strip()
        if text and not re.search(r"チャンネル登録|フォロー|登録.*よろしく", text):
            last_line = text
            break

    # 代替フック生成
    use_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    alternatives = _generate_alternatives(
        original_hook, theme_title, channel_id, last_line, use_key,
    )

    # 全候補を採点
    candidates = [original_hook] + alternatives
    scored: List[Dict[str, Any]] = []
    for hook in candidates:
        scores = _rule_based_score(hook, last_line)
        scored.append({
            "hook": hook,
            "scores": scores,
            "total": _total_score(scores),
        })

    # 最高スコアを選択（同点なら元のフックを優先）
    scored.sort(key=lambda x: x["total"], reverse=True)
    best = scored[0]

    if best["hook"] == original_hook:
        print(f"  ✅ HookAB [{channel_id}]: 元のフックが最高スコア ({best['total']}pt)")
        return {
            "modified": False,
            "original_hook": original_hook,
            "selected_hook": original_hook,
            "scores": scored,
            "reason": "original_is_best",
        }

    # フックを差し替え
    if "text" in first_entry:
        first_entry["text"] = best["hook"]
    elif "line" in first_entry:
        first_entry["line"] = best["hook"]

    print(
        f"  🔄 HookAB [{channel_id}]: フック差替 ({best['total']}pt > "
        f"{scored[-1]['total']}pt)\n"
        f"     旧: {original_hook[:40]}…\n"
        f"     新: {best['hook'][:40]}…"
    )

    return {
        "modified": True,
        "original_hook": original_hook,
        "selected_hook": best["hook"],
        "scores": scored,
        "reason": "better_hook_found",
    }
