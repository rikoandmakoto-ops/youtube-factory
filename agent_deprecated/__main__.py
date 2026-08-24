"""CLI エントリーポイント。

  python -m agent run youtube-growth            # ループ実行（既定30分間隔）
  python -m agent run youtube-growth --once     # 1サイクルだけ
  python -m agent run youtube-growth --dry-run  # 生成/投稿せず観測と判断だけ
  python -m agent run youtube-growth --max-cycles 3 --interval 600
  python -m agent status                        # 記憶（学習/タスク/直近ログ）を表示
"""

from __future__ import annotations

import argparse
import sys

from . import config as cfg


def _build_agent(args):
    from .core import AutonomousAgent
    from .memory import Memory
    from .objectives import youtube_growth

    if args.objective != "youtube-growth":
        print(f"未知の objective: {args.objective}（現在は youtube-growth のみ）")
        sys.exit(2)

    conf = cfg.AgentConfig(dry_run=args.dry_run)
    if args.interval is not None:
        conf.interval_seconds = args.interval
    if args.model:
        conf.model = args.model

    memory = Memory(cfg.STATE_DIR)
    tools = youtube_growth.build_tools(memory)
    return AutonomousAgent(conf, youtube_growth.OBJECTIVE, tools, memory), memory


def cmd_run(args):
    agent, _ = _build_agent(args)
    agent.run_loop(once=args.once, max_cycles=args.max_cycles)


def cmd_status(args):
    from .memory import Memory

    memory = Memory(cfg.STATE_DIR)
    print("=== 学習した知見 ===")
    for k, v in (memory.learnings() or {}).items():
        print(f"- {k}: {v}")
    print("\n=== タスク ===")
    for k, v in (memory.tasks() or {}).items():
        print(f"- [{v.get('status')}] {k}: {v.get('note','')}")
    print("\n=== 直近の行動ログ ===")
    for a in memory.recent_actions(25):
        print(f"- {a.get('ts')} [{a.get('kind')}] {str(a.get('summary',''))[:160]}")


def main(argv=None):
    cfg.bootstrap()

    parser = argparse.ArgumentParser(prog="agent", description="自律 AI オーケストレーター")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="エージェントを実行")
    p_run.add_argument("objective", nargs="?", default="youtube-growth")
    p_run.add_argument("--once", action="store_true", help="1サイクルだけ実行")
    p_run.add_argument("--dry-run", action="store_true", help="生成/投稿せず観測と判断のみ")
    p_run.add_argument("--max-cycles", type=int, default=None, help="最大サイクル数")
    p_run.add_argument("--interval", type=int, default=None, help="サイクル間隔（秒）")
    p_run.add_argument("--model", default=None, help="使用する Claude モデル名")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="記憶を表示")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
