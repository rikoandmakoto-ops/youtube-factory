"""メモリ操作ツール。

Claude が「この知見を覚えておく」「このタスクを進行中にする」を自分で行えるようにする。
Memory インスタンスに束ねるためファクトリ関数で生成する。
"""

from __future__ import annotations

from ..memory import Memory
from .base import Tool


def build_memory_tools(memory: Memory) -> list[Tool]:
    def remember(key: str, value: str) -> dict:
        memory.remember(key, value)
        return {"ok": True, "remembered": {key: value}}

    def set_task(task_id: str, status: str, note: str = "") -> dict:
        memory.set_task(task_id, status, note)
        return {"ok": True, "task": {task_id: {"status": status, "note": note}}}

    return [
        Tool(
            name="remember",
            description=(
                "学んだ知見を永続メモリに保存する。例: 'voicevox_restart' -> "
                "'open -a VOICEVOX で復旧する'。次サイクル以降の判断に使われる。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
            func=remember,
            safe_in_dry_run=True,
        ),
        Tool(
            name="set_task",
            description=(
                "進行中タスクの状態を記録/更新する。status は in_progress/blocked/done など。"
                "サイクルをまたいで継続する作業の追跡に使う。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "status": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["task_id", "status"],
            },
            func=set_task,
            safe_in_dry_run=True,
        ),
    ]
