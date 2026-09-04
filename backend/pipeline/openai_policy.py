"""OpenAI API を叩いてよいかを一箇所で決める。

方針（2026-09-04 ユーザー指示）:

  * **画像生成の OpenAI API 呼び出しは廃止した。** コードごと消えている。
    画像は `chatgpt_image_bridge` — ChatGPT の**チャンネル専用スレッド**だけで作る。
    プロンプト設計も品質判定も Claude が持ち、ChatGPT はレンダリング基盤として使う。
  * **テキスト生成は Claude が本命。** Claude が使えるならその瞬間から
    OpenAI は一切呼ばれない（下の `direct_text_api_allowed` を参照）。

`ANTHROPIC_API_KEY` が `backend/.env` で未設定の間だけ、OpenAI が退避口として残る。
ここを無条件に塞ぐと台本生成が全チャンネルで止まるため、
**Claude が使えるようになったら自動で OpenAI を使わなくなる**形にしてある。
明示的に塞ぎ切りたいときは `OPENAI_TEXT=0`。
"""

from __future__ import annotations

import os


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def claude_available() -> bool:
    try:
        from pipeline import claude_client
        return claude_client.has_api_key()
    except Exception:
        return False


def direct_text_api_allowed() -> bool:
    """テキスト生成で OpenAI Chat Completions を叩いてよいか。

    * `OPENAI_TEXT=0` → 常に不可
    * Claude が使える → 不可（Claude を使う。OpenAI に落ちる必要が無い）
    * Claude が使えない → **可**。ここを塞ぐと台本生成が全チャンネルで止まるため、
      キーが入るまでの退避口として残している。
    """
    if not _flag("OPENAI_TEXT", True):
        return False
    return not claude_available()


def policy_note() -> str:
    """ログ用の一行説明。"""
    image = "画像: ChatGPT スレッド経由のみ（OpenAI API 廃止）"
    if not _flag("OPENAI_TEXT", True):
        text = "テキスト: Claude のみ（OPENAI_TEXT=0）"
    elif claude_available():
        text = "テキスト: Claude（OpenAI は呼ばれない）"
    else:
        text = "テキスト: ⚠️ ANTHROPIC_API_KEY 未設定のため OpenAI が退避口として稼働中"
    return f"{image} / {text}"
