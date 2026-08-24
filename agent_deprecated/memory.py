"""永続メモリ。

3 種類を JSON で保持する（inspect しやすさ優先、SQLite は将来差し替え可）:

- actions  : 過去の行動と結果のログ（append-only）
- learnings: 学習した知見「このエラーにはこう対処した」を key→値で蓄積
- tasks    : 進行中タスク（id→状態）

`recent_context()` が Claude に渡す要約テキストを返す。これがエージェントの
「記憶を踏まえて考える」の核になる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Memory:
    def __init__(self, state_dir: Path):
        self.dir = state_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.actions_path = self.dir / "actions.jsonl"
        self.learnings_path = self.dir / "learnings.json"
        self.tasks_path = self.dir / "tasks.json"

    # --- actions（append-only ログ）------------------------------------
    def log_action(self, kind: str, detail: dict[str, Any], *, ts: str) -> None:
        rec = {"ts": ts, "kind": kind, **detail}
        with self.actions_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def recent_actions(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.actions_path.exists():
            return []
        lines = self.actions_path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    # --- learnings（知見）---------------------------------------------
    def _load_learnings(self) -> dict[str, Any]:
        if self.learnings_path.exists():
            try:
                return json.loads(self.learnings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def remember(self, key: str, value: str) -> None:
        d = self._load_learnings()
        d[key] = value
        self.learnings_path.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def learnings(self) -> dict[str, Any]:
        return self._load_learnings()

    # --- tasks（進行中タスク）-----------------------------------------
    def _load_tasks(self) -> dict[str, Any]:
        if self.tasks_path.exists():
            try:
                return json.loads(self.tasks_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def set_task(self, task_id: str, status: str, note: str = "") -> None:
        d = self._load_tasks()
        d[task_id] = {"status": status, "note": note}
        self.tasks_path.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def tasks(self) -> dict[str, Any]:
        return self._load_tasks()

    # --- Claude に渡すコンテキスト要約 --------------------------------
    def recent_context(self, action_limit: int = 15) -> str:
        parts: list[str] = []

        learnings = self.learnings()
        if learnings:
            parts.append("## 学習した知見（過去の対処法）")
            for k, v in learnings.items():
                parts.append(f"- {k}: {v}")

        tasks = self.tasks()
        open_tasks = {k: v for k, v in tasks.items()
                      if v.get("status") not in ("done", "completed", "cancelled")}
        if open_tasks:
            parts.append("\n## 進行中タスク")
            for k, v in open_tasks.items():
                parts.append(f"- [{v.get('status')}] {k}: {v.get('note', '')}")

        actions = self.recent_actions(action_limit)
        if actions:
            parts.append("\n## 直近の行動ログ（古い→新しい）")
            for a in actions:
                kind = a.get("kind")
                ts = a.get("ts", "")
                summary = a.get("summary") or a.get("result") or a.get("detail") or ""
                summary = str(summary)
                if len(summary) > 240:
                    summary = summary[:240] + "…"
                parts.append(f"- {ts} [{kind}] {summary}")

        if not parts:
            return "（まだ記憶はありません。これが最初のサイクルです。）"
        return "\n".join(parts)
