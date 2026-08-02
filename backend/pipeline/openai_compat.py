"""OpenAI Chat Completions のモデル世代差を吸収するヘルパー。

gpt-5 系 (gpt-5.6-terra / -luna / -sol など) は gpt-4 系と以下が非互換:

  * `max_tokens` を受け付けない — `max_completion_tokens` を要求する
  * `temperature` は既定値 (1) 以外を拒否する (0 も 0.9 も 400)
  * 推論(reasoning)トークンが `max_completion_tokens` を食う。既定のままだと
    上限 1500 程度では reasoning だけで枠を使い切り本文が空で返る
    (finish_reason=length / content="")。本パイプラインは尺計算を前提に
    max_tokens を積んでいるため、`reasoning_effort="none"` で無効化して
    gpt-4 系と同じ「枠 = 出力」の挙動に揃える。

呼び出し側は従来どおり temperature / max_tokens を渡し、ここでモデルに応じて
変換・除去する。gpt-4 系に戻した場合も同じ呼び出しのまま動く。
"""

from typing import Any, Dict, List, Optional


def _is_gpt5(model: str) -> bool:
    return (model or "").startswith("gpt-5")


def supports_temperature(model: str) -> bool:
    """temperature を指定できるモデルか。gpt-5 系は既定(1)固定。"""
    return not _is_gpt5(model)


def max_tokens_key(model: str) -> str:
    """出力トークン上限のパラメータ名。"""
    return "max_completion_tokens" if _is_gpt5(model) else "max_tokens"


def build_chat_payload(
    model: str,
    messages: List[Dict[str, Any]],
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """/v1/chat/completions 用の payload を組み立てる。

    temperature は非対応モデルでは黙って落とす（渡すと 400 になるため）。
    extra は response_format などをそのまま透過する（None の値は除外）。
    """
    payload: Dict[str, Any] = {"model": model, "messages": messages}
    if max_tokens is not None:
        payload[max_tokens_key(model)] = max_tokens
    if temperature is not None and supports_temperature(model):
        payload["temperature"] = temperature
    if _is_gpt5(model):
        # 呼び出し側が明示指定した場合のみ上書きを許す。
        payload["reasoning_effort"] = extra.pop("reasoning_effort", None) or "none"
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    return payload
