"""OpenAI API を直接叩いてよいかを一箇所で決める。

方針（2026-09-04 ユーザー指示）:

  * **画像生成は API 直叩き禁止。** ChatGPT のブラウザスレッド経由
    （`chatgpt_image_bridge`）だけを使う。ユーザーが同じスレッドを開いて
    横からプロンプトを直せることが必須要件で、API ではその会話が消える。
  * **テキスト生成は Claude が本命。** OpenAI は Claude が使えないときの
    最後の退避口としてのみ残す。`ANTHROPIC_API_KEY` を入れたら
    `OPENAI_TEXT=0` にして完全に切る。

呼び出し側は分岐の前にこのモジュールを見る。環境変数で上書きできる:

  IMAGE_BRIDGE=0     ブリッジを止める（この場合だけ画像 API 直叩きを許可）
  OPENAI_IMAGE=1     画像 API 直叩きを明示的に許可（緊急時のみ）
  OPENAI_TEXT=0      テキストの OpenAI 退避口も塞ぐ
"""

from __future__ import annotations

import os


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def direct_image_api_allowed() -> bool:
    """画像生成で `api.openai.com/v1/images/generations` を叩いてよいか。

    既定は **不可**。ブリッジ自体を止めている（IMAGE_BRIDGE=0）ときだけ、
    画像が一切出なくなるのを避けるために許可する。
    """
    if _flag("OPENAI_IMAGE", False):
        return True
    from pipeline import chatgpt_image_bridge
    return not chatgpt_image_bridge.is_enabled()


def direct_text_api_allowed() -> bool:
    """テキスト生成で OpenAI Chat Completions を叩いてよいか。

    既定は可（現時点で `ANTHROPIC_API_KEY` が未設定のため。これを塞ぐと
    台本生成が全チャンネルで止まる）。キーを入れたら `OPENAI_TEXT=0` にする。
    """
    return _flag("OPENAI_TEXT", True)


def image_policy_note() -> str:
    """ログ用の一行説明。"""
    if direct_image_api_allowed():
        return "画像: OpenAI API 直叩き（ブリッジ無効 or OPENAI_IMAGE=1）"
    return "画像: ChatGPT ブラウザスレッド経由のみ（API 直叩き禁止）"
