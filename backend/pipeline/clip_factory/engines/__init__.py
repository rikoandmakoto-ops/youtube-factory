"""切り抜きエンジンの差し替え口。

- local  : 本リポジトリ内で完結する内製エンジン（既定）
- noimos : NoimosAI SaaS のクリエイティブエージェントに投げる
- viral  : 海外バイラル動画を Whisper で書き起こし、Claude で日本語化して焼く

チャンネル JSON の clip.engine で選ぶ。noimos が失敗したら
clip.fallback_engine（既定 local）に落ちる。
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from .local import generate as generate_local
from .noimos import generate as generate_noimos
from .viral import generate as generate_viral

ENGINES: Dict[str, Callable[..., Any]] = {
    "local": generate_local,
    "noimos": generate_noimos,
    "viral": generate_viral,
}


def get_engine(name: str) -> Callable[..., Any]:
    return ENGINES.get((name or "local").strip().lower(), generate_local)


__all__ = ["ENGINES", "get_engine", "generate_local", "generate_noimos",
           "generate_viral"]
