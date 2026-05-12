"""OpenAI / Anthropic API 使用量トラッカー — トークン数と推定費用を記録"""

import json
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, List

# Pricing in USD per token (input/output)
GPT_PRICING = {
    "gpt-4o":          {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini":     {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4-turbo":     {"input": 10.00 / 1_000_000, "output": 30.00 / 1_000_000},
    "gpt-3.5-turbo":   {"input": 0.50 / 1_000_000, "output": 1.50 / 1_000_000},
    # Claude (Anthropic) — 分析・評価・採点系で使用
    "claude-sonnet-4-20250514":  {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-3-5-sonnet-latest":  {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000},
}

# DALL-E 3 pricing per image
DALLE3_PRICING = {
    "1024x1024_standard": 0.040,
    "1024x1024_hd":       0.080,
    "1024x1792_standard": 0.080,
    "1024x1792_hd":       0.120,
    "1792x1024_standard": 0.080,
    "1792x1024_hd":       0.120,
}


_USAGE_FILE = Path(__file__).parent.parent.parent / "data" / "api_usage.jsonl"
_lock = threading.Lock()


def _model_price(model: str) -> Dict[str, float]:
    if model in GPT_PRICING:
        return GPT_PRICING[model]
    # Claude のバージョン違いには Sonnet 価格をフォールバック
    if model.startswith("claude-"):
        if "haiku" in model:
            return GPT_PRICING["claude-haiku-4-5-20251001"]
        return GPT_PRICING["claude-sonnet-4-20250514"]
    # default fallback to gpt-4o pricing
    return GPT_PRICING["gpt-4o"]


def provider_of(model: str) -> str:
    """モデル名からプロバイダーを判定 (openai / anthropic / other)。"""
    if not model:
        return "other"
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gpt") or m.startswith("dall-e") or m.startswith("dalle"):
        return "openai"
    return "other"


def record_chat_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    channel_id: Optional[str] = None,
    purpose: Optional[str] = None,
) -> Dict:
    """Record a chat completion API call."""
    p = _model_price(model)
    cost = prompt_tokens * p["input"] + completion_tokens * p["output"]
    event = {
        "ts": datetime.now().isoformat(),
        "type": "chat",
        "model": model,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(prompt_tokens + completion_tokens),
        "cost_usd": round(cost, 6),
        "channel_id": channel_id,
        "purpose": purpose,
    }
    _append_event(event)
    return event


def record_image_usage(
    size: str = "1024x1024",
    quality: str = "standard",
    channel_id: Optional[str] = None,
    purpose: Optional[str] = None,
) -> Dict:
    """Record a DALL-E image generation."""
    key = f"{size}_{quality}"
    cost = DALLE3_PRICING.get(key, DALLE3_PRICING["1024x1024_standard"])
    event = {
        "ts": datetime.now().isoformat(),
        "type": "image",
        "model": "dall-e-3",
        "size": size,
        "quality": quality,
        "cost_usd": round(cost, 6),
        "channel_id": channel_id,
        "purpose": purpose,
    }
    _append_event(event)
    return event


def _append_event(event: Dict):
    """Append event to JSONL file. Thread-safe."""
    with _lock:
        try:
            _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _USAGE_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"⚠️ Failed to record API usage: {e}")


def _read_events() -> List[Dict]:
    if not _USAGE_FILE.exists():
        return []
    events = []
    with _lock:
        try:
            with _USAGE_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"⚠️ Failed to read API usage: {e}")
    return events


def get_summary() -> Dict:
    """Aggregate usage stats: total, today, this month, by channel, by day (last 30d)."""
    events = _read_events()
    today_str = date.today().isoformat()
    month_prefix = today_str[:7]  # YYYY-MM

    summary = {
        "total": _zero_metrics(),
        "today": _zero_metrics(),
        "this_month": _zero_metrics(),
        "by_channel": {},
        "by_day": {},  # last 30 days
        "by_model": {},
        "by_provider": {},
        "by_purpose": {},
        "voicevox_cost_usd": 0.0,
        "voicevox_note": "VOICEVOXは無料 (ローカル実行)",
        "events_count": len(events),
        "pricing": {
            "gpt-4o": {"input_per_1m": 2.50, "output_per_1m": 10.00, "currency": "USD"},
            "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60, "currency": "USD"},
            "claude-sonnet-4": {"input_per_1m": 3.00, "output_per_1m": 15.00, "currency": "USD"},
            "claude-haiku-4-5": {"input_per_1m": 1.00, "output_per_1m": 5.00, "currency": "USD"},
            "dall-e-3": {"per_image_1024_standard": 0.040, "currency": "USD"},
        },
    }

    from collections import defaultdict
    by_day = defaultdict(lambda: _zero_metrics())
    by_channel = defaultdict(lambda: _zero_metrics())
    by_model = defaultdict(lambda: _zero_metrics())
    by_provider = defaultdict(lambda: _zero_metrics())
    by_purpose = defaultdict(lambda: _zero_metrics())

    for ev in events:
        ts = ev.get("ts", "")
        day = ts[:10]  # YYYY-MM-DD
        model = ev.get("model", "unknown")
        cost = ev.get("cost_usd", 0.0)
        prompt_t = ev.get("prompt_tokens", 0)
        comp_t = ev.get("completion_tokens", 0)
        ch = ev.get("channel_id") or "(unspecified)"
        provider = provider_of(model)
        purpose = ev.get("purpose") or "(unspecified)"

        for bucket in (
            summary["total"],
            by_day[day],
            by_channel[ch],
            by_model[model],
            by_provider[provider],
            by_purpose[purpose],
        ):
            bucket["calls"] += 1
            bucket["cost_usd"] += cost
            bucket["prompt_tokens"] += prompt_t
            bucket["completion_tokens"] += comp_t
            if ev.get("type") == "image":
                bucket["images"] += 1

        if day == today_str:
            summary["today"]["calls"] += 1
            summary["today"]["cost_usd"] += cost
            summary["today"]["prompt_tokens"] += prompt_t
            summary["today"]["completion_tokens"] += comp_t
            if ev.get("type") == "image":
                summary["today"]["images"] += 1
        if day.startswith(month_prefix):
            summary["this_month"]["calls"] += 1
            summary["this_month"]["cost_usd"] += cost
            summary["this_month"]["prompt_tokens"] += prompt_t
            summary["this_month"]["completion_tokens"] += comp_t
            if ev.get("type") == "image":
                summary["this_month"]["images"] += 1

    # Sort & truncate by_day to last 30 days
    sorted_days = sorted(by_day.keys(), reverse=True)[:30]
    summary["by_day"] = {d: _round_metrics(by_day[d]) for d in sorted_days}
    summary["by_channel"] = {ch: _round_metrics(m) for ch, m in by_channel.items()}
    summary["by_model"] = {m: _round_metrics(metrics) for m, metrics in by_model.items()}
    summary["by_provider"] = {p: _round_metrics(m) for p, m in by_provider.items()}
    summary["by_purpose"] = {p: _round_metrics(m) for p, m in by_purpose.items()}
    summary["total"] = _round_metrics(summary["total"])
    summary["today"] = _round_metrics(summary["today"])
    summary["this_month"] = _round_metrics(summary["this_month"])

    return summary


def _zero_metrics() -> Dict:
    return {
        "calls": 0,
        "cost_usd": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "images": 0,
    }


def _round_metrics(m: Dict) -> Dict:
    return {
        "calls": m["calls"],
        "cost_usd": round(m["cost_usd"], 4),
        "prompt_tokens": m["prompt_tokens"],
        "completion_tokens": m["completion_tokens"],
        "images": m["images"],
    }


def reset_usage():
    """Delete the usage log (admin function)."""
    with _lock:
        if _USAGE_FILE.exists():
            _USAGE_FILE.unlink()
