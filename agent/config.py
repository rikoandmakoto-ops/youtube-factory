"""エージェントの設定とブートストラップ。

- repo の backend/ を import path に追加
- backend/.env を環境変数に読み込む（既存値は上書きしない）
- モデル名・ループ間隔・dry-run などの実行時設定を 1 か所に集約
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- パス ---------------------------------------------------------------
AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
DATA_DIR = REPO_ROOT / "data"
STATE_DIR = AGENT_DIR / "state"          # メモリ・ログの保存先


def bootstrap() -> None:
    """backend を import 可能にし、.env を読み込む。

    冪等。core / tools を import する前に 1 度呼べばよい。
    """
    import sys

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

    STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class AgentConfig:
    """1 回の実行（run）の振る舞いを決める設定。"""

    # Claude（考える脳）。AGENT_MODEL で上書き可。
    # リポジトリで実績のある sonnet-4 を既定にしておく。
    model: str = field(default_factory=lambda: os.environ.get(
        "AGENT_MODEL", "claude-sonnet-4-20250514"))
    max_tokens: int = 4096

    # 1 サイクル内で Claude に許す思考↔ツールの往復回数の上限（暴走防止）
    max_steps_per_cycle: int = 25

    # ループ実行時、サイクル間で待つ秒数（既定 30 分）
    interval_seconds: int = field(default_factory=lambda: int(
        os.environ.get("AGENT_INTERVAL_SECONDS", str(30 * 60))))

    # True の場合、動画生成・アップロードなど「外に出る/重い」操作を実際には行わず
    # 何をするはずだったかだけを返す。最初の動作確認に使う。
    dry_run: bool = False

    # 対象チャンネル
    channels: tuple[str, ...] = ("scp-lab", "daily-science")

    def anthropic_api_key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "")
