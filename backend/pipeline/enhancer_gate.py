"""Round6〜8 の台本エンハンサーをチャンネル単位で止めるためのゲート。

Round6/7/8 のエンハンサーは、生成済みの short_scenario を **その場で書き換える**。
どれも「ゆっくり解説の煽り系ショート」を前提にした既定テンプレートを持っているため、
語り口を厳密に定義したチャンネル（1人語り・常体・煽り語禁止など）に当てると

  - voice_style.forbidden の語（「衝撃」「ヤバい」）が本文に注入される
  - 正規表現置換が文中で発火して係り受けが壊れる
    （「読めた者の記録がない」→「読めた者の人類が触れてはいけない記録がない」）
  - short_format で決めた行あたり文字数・総尺を大きく超える

という壊れ方をする。チャンネル JSON 側で個別に落とせるようにする:

    "script_enhancers": {
      "enabled": true,                       // false で全モジュール停止
      "disabled": ["power_word_amplifier"]   // モジュール名で個別停止
    }

未設定のチャンネルは全モジュール有効（従来どおり・挙動不変）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _settings(channel_dict: Optional[Dict[str, Any]]) -> Any:
    return (channel_dict or {}).get("script_enhancers")


def is_enabled(channel_dict: Optional[Dict[str, Any]], module_name: str) -> bool:
    """`module_name` のエンハンサーを走らせてよいか。未設定なら True。"""
    cfg = _settings(channel_dict)
    if cfg is None:
        return True
    if cfg is False:
        return False
    if not isinstance(cfg, dict):
        return True
    if cfg.get("enabled") is False:
        return False
    disabled = cfg.get("disabled") or []
    if isinstance(disabled, (list, tuple, set)) and module_name in disabled:
        return False
    # {"power_word_amplifier": false} 形式の直接指定も受ける
    if cfg.get(module_name) is False:
        return False
    return True


def skipped(module_name: str, channel_id: str = "") -> Dict[str, Any]:
    """停止したモジュールが返す結果（呼び出し側の results に入れる）。"""
    return {"skipped": True, "reason": f"script_enhancers disabled for {channel_id or 'channel'}"}
