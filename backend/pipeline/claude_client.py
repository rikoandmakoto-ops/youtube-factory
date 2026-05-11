"""
Claude API (Anthropic) クライアントラッパ — 分析・評価・採点・判断系の処理で共有して使う。

GPT-4o を使っていた `chat/completions` 互換のヘルパを Claude Messages API に置き換えるための薄い層。
ANTHROPIC_API_KEY 未設定時 / SDK 未導入時 / 呼び出し失敗時は None を返し、
呼び出し側はルールベースのフォールバックに切り替える前提。

JSON 出力:
  Anthropic Messages API には OpenAI の response_format に相当する厳密な JSON モードが無いため、
  system プロンプトに「JSON のみ返す」旨を補強した上で、応答テキストから JSON オブジェクトを
  ロバストに抽出する（前置きやコードフェンスを除去）。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

try:
    from anthropic import Anthropic  # type: ignore
except Exception:  # pragma: no cover - SDK 未導入時のフォールバック
    Anthropic = None  # type: ignore

try:
    from pipeline import api_usage  # type: ignore
except Exception:  # pragma: no cover
    api_usage = None  # type: ignore


CLAUDE_MODEL = "claude-sonnet-4-20250514"

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def has_api_key() -> bool:
    """ANTHROPIC_API_KEY が設定され、SDK が import 可能か。"""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()) and Anthropic is not None


def _extract_json(content: str) -> Optional[Dict[str, Any]]:
    """Claude が稀に前置き／```json で包んだコードフェンスを返すケースに耐性のある JSON 抽出。"""
    if not content:
        return None
    # まずそのまま
    try:
        return json.loads(content)
    except Exception:
        pass
    # コードフェンス
    m = _JSON_FENCE_RE.search(content)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 中括弧の最大マッチ
    m2 = _JSON_OBJECT_RE.search(content)
    if not m2:
        return None
    try:
        return json.loads(m2.group(0))
    except Exception:
        return None


def call_claude_json(
    *,
    system: str,
    user: str,
    model: str = CLAUDE_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    channel_id: Optional[str] = None,
    purpose: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Claude を呼び JSON dict を返す。失敗時 / 未設定時は None。

    呼び出し側は None を受けたらルールベースにフォールバックする。
    """
    if not has_api_key():
        return None
    api_key = os.environ["ANTHROPIC_API_KEY"].strip()
    system_full = (
        system.rstrip()
        + "\n\n出力は JSON オブジェクト1つのみを返してください。"
          "前置き・後置き・コードブロック（```）は禁止です。"
    )
    try:
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_full,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:
        print(f"⚠️ claude_client call failed ({purpose or model}): {e}")
        return None

    # 使用量を記録（OpenAI と同じ JSONL ストアに溜める）
    if api_usage is not None:
        try:
            usage = getattr(resp, "usage", None)
            in_t = int(getattr(usage, "input_tokens", 0) or 0)
            out_t = int(getattr(usage, "output_tokens", 0) or 0)
            api_usage.record_chat_usage(
                model=model,
                prompt_tokens=in_t,
                completion_tokens=out_t,
                channel_id=channel_id,
                purpose=purpose,
            )
        except Exception:
            pass

    # content blocks (TextBlock) を結合
    try:
        text_parts: List[str] = []
        for block in getattr(resp, "content", []) or []:
            t = getattr(block, "text", None)
            if t:
                text_parts.append(t)
        return _extract_json("".join(text_parts))
    except Exception:
        return None


def call_claude_json_from_messages(
    messages: List[Dict[str, str]],
    *,
    model: str = CLAUDE_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    channel_id: Optional[str] = None,
    purpose: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """OpenAI 形式の `[{role: system|user, content}]` を受けて Claude を呼ぶ互換ヘルパ。

    既存の _call_openai 風コードからの最小差分での移行用。
    """
    system_parts: List[str] = []
    user_parts: List[str] = []
    for m in messages or []:
        role = (m.get("role") or "").lower()
        content = m.get("content") or ""
        if role == "system":
            system_parts.append(content)
        else:
            user_parts.append(content)
    return call_claude_json(
        system="\n\n".join(p for p in system_parts if p) or "あなたは優秀なアシスタントです。",
        user="\n\n".join(p for p in user_parts if p),
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        channel_id=channel_id,
        purpose=purpose,
    )
