"""自律エージェントのコア。

observe → think → act → check を Claude の tool-use ループとして実装する。
1 サイクル = 「目的＋記憶＋現在状況」を Claude に渡し、Claude が観測系/行動系ツールを
使い切って end_turn するまで回す。終わったら記憶を更新し、次サイクルまで待つ。

このクラスは YouTube に依存しない汎用部分。目的とツールを差し替えれば他プロジェクトに
転用できる。
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass
from datetime import datetime

from .config import AgentConfig
from .memory import Memory
from .tools.base import Tool, ToolRegistry


@dataclass
class Objective:
    """エージェントの目的。プロジェクトごとに定義する。"""

    name: str          # 例: "youtube-growth"
    mission: str       # 何を達成したいか（長文可）
    guidance: str      # 運用ルール・判断基準


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- プロンプトキャッシュ --------------------------------------------------
# リクエストは tools → system → messages の順にレンダリングされる。system の最後の
# ブロックに breakpoint を置くと tools + system がまとめてキャッシュされ、サイクルを
# またいで再利用される。会話履歴側は _roll_cache_breakpoint で 1 個だけ前進させる。
CACHE_CONTROL = {"type": "ephemeral"}


def _roll_cache_breakpoint(messages: list[dict], blocks: list[dict]) -> None:
    """履歴の breakpoint を最新の tool_result 群の末尾へ前進させる。

    breakpoint は 1 リクエスト 4 個まで。ステップごとに付け足すと上限に当たるので、
    既存のものを外してから最新ブロックに 1 つだけ付け直す。
    """
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    b.pop("cache_control", None)
    if blocks:
        blocks[-1]["cache_control"] = dict(CACHE_CONTROL)


class AutonomousAgent:
    def __init__(
        self,
        config: AgentConfig,
        objective: Objective,
        tools: list[Tool],
        memory: Memory,
    ):
        self.config = config
        self.objective = objective
        self.registry = ToolRegistry(tools)
        self.memory = memory

        import anthropic  # 遅延 import（bootstrap 後）

        api_key = config.anthropic_api_key()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY が未設定です（backend/.env を確認）")
        self.client = anthropic.Anthropic(api_key=api_key)

    # --- system prompt --------------------------------------------------
    def _system_prompt(self) -> str:
        tool_names = ", ".join(self.registry.names())
        dry = ("\n【重要】現在は DRY-RUN モードです。動画生成やアップロードなど実際に外部へ"
               "影響する操作は実行されず、何をする予定だったかだけが返ります。観測と判断は通常通り行ってください。"
               if self.config.dry_run else "")
        return f"""あなたは自律的に動く運用エージェントです。人間の代わりに「状況を見て、考えて、行動して、結果を確認する」ループを回します。

# 目的
{self.objective.mission}

# 運用ルール
{self.objective.guidance}

# 使えるツール
{tool_names}

# 動き方
1. まず観測ツールで現在の状況を把握する（憶測で動かない）。
2. 目的とルールに照らして、このサイクルで取るべき行動を決める。
3. ツールで実行し、結果を確認する。失敗したら原因を考え、fallback や再試行を自分で試みる。
4. 重要な知見は remember で、継続する作業は set_task で記録する。
5. 自力で解決できない問題（要・人間の対応）だけ notify_user で通知する。通常の成功/失敗はログに残るので通知不要。
6. このサイクルでやるべきことが無ければ、無理に行動せず「今回は対応不要」と述べて終了する。

簡潔に、要点だけテキストで説明しながらツールを使ってください。{dry}"""

    # --- ツール実行 -----------------------------------------------------
    def _execute_tool(self, name: str, tool_input: dict) -> dict:
        tool = self.registry.get(name)
        if tool is None:
            return {"error": f"unknown tool: {name}"}

        if self.config.dry_run and not tool.safe_in_dry_run:
            return {"dry_run": True,
                    "note": f"[DRY-RUN] {name} は実行されませんでした",
                    "would_call_with": tool_input}
        try:
            result = tool.func(**tool_input)
            return result if isinstance(result, dict) else {"result": result}
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc()[-1500:]}

    # --- 1 サイクル -----------------------------------------------------
    def run_cycle(self) -> dict:
        print(f"\n{'=' * 72}\n🤖 サイクル開始 {_now_iso()}  目的: {self.objective.name}"
              f"{'  [DRY-RUN]' if self.config.dry_run else ''}\n{'=' * 72}")

        context = self.memory.recent_context()
        messages = [{
            "role": "user",
            "content": (
                "新しいサイクルを開始します。下記はこれまでの記憶です。\n\n"
                f"{context}\n\n"
                "現在の状況を観測し、目的とルールに沿って必要な行動を取ってください。"
            ),
        }]

        tool_calls = 0
        actions: list[dict] = []
        final_text = ""

        for step in range(self.config.max_steps_per_cycle):
            try:
                resp = self.client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    # 最後の system ブロックの breakpoint が tools + system を丸ごとキャッシュする
                    system=[{"type": "text",
                             "text": self._system_prompt(),
                             "cache_control": dict(CACHE_CONTROL)}],
                    tools=self.registry.specs(),
                    messages=messages,
                )
            except Exception as e:  # noqa: BLE001
                err = f"Claude API error: {type(e).__name__}: {e}"
                print(f"❌ {err}")
                self.memory.log_action("cycle_error", {"summary": err}, ts=_now_iso())
                return {"ok": False, "error": err}

            # アシスタントのテキストを表示
            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    print(f"\n💭 {block.text.strip()}")
                    final_text = block.text.strip()

            messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                break  # end_turn: このサイクル終了

            # tool_use ブロックを実行して結果を返す
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                tool_calls += 1
                print(f"\n🔧 {block.name}({json.dumps(block.input, ensure_ascii=False)[:300]})")
                result = self._execute_tool(block.name, block.input)
                ok = not result.get("error")
                print(f"   {'✅' if ok else '⚠️ '} {json.dumps(result, ensure_ascii=False, default=str)[:400]}")

                actions.append({"tool": block.name, "input": block.input, "ok": ok})
                self.memory.log_action(
                    "tool_call",
                    {"summary": f"{block.name} -> {'ok' if ok else result.get('error')}",
                     "tool": block.name, "input": block.input, "result": result},
                    ts=_now_iso(),
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

            # 次リクエストで履歴全体がキャッシュヒットするよう breakpoint を前進させる
            _roll_cache_breakpoint(messages, tool_results)
            messages.append({"role": "user", "content": tool_results})
        else:
            print("\n⚠️  max_steps に到達。サイクルを打ち切ります。")

        self.memory.log_action(
            "cycle_done",
            {"summary": final_text[:240] or "(no summary)",
             "tool_calls": tool_calls},
            ts=_now_iso(),
        )
        print(f"\n✅ サイクル終了（ツール呼び出し {tool_calls} 回）")
        return {"ok": True, "tool_calls": tool_calls, "actions": actions, "summary": final_text}

    # --- ループ ---------------------------------------------------------
    def run_loop(self, once: bool = False, max_cycles: int | None = None) -> None:
        cycle = 0
        while True:
            cycle += 1
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                print("\n👋 中断されました。")
                return
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self.memory.log_action("cycle_crash", {"summary": str(e)}, ts=_now_iso())

            if once or (max_cycles is not None and cycle >= max_cycles):
                return

            wait = self.config.interval_seconds
            print(f"\n⏳ 次のサイクルまで {wait} 秒待機… (Ctrl-C で終了)")
            try:
                time.sleep(wait)
            except KeyboardInterrupt:
                print("\n👋 終了します。")
                return
