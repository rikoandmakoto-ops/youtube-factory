"""ツールの抽象。

`Tool` は Claude の tool-use に渡せる JSON schema と、それを実行する Python
callable を 1 つにまとめたもの。`func(**input) -> dict|str` を実装する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    func: Callable[..., Any]
    # True の場合 dry_run でも実行してよい（読み取り専用・安全な観測系）
    safe_in_dry_run: bool = False

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def specs(self) -> list[dict[str, Any]]:
        return [t.to_anthropic() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)
