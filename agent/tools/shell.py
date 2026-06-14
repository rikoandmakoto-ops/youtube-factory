"""シェルコマンド実行ツール。

エージェントが任意のコマンドを叩けるようにする汎用の手。VOICEVOX の再起動、
ファイル確認、補助スクリプトの起動などに使う。repo ルートを cwd にする。
"""

from __future__ import annotations

import subprocess

from ..config import REPO_ROOT
from .base import Tool


def _run_shell(command: str, timeout: int = 120) -> dict:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = proc.stdout or ""
        err = proc.stderr or ""
        # 出力が長すぎると Claude のコンテキストを圧迫するので切り詰める
        if len(out) > 4000:
            out = out[:2000] + "\n…(中略)…\n" + out[-1500:]
        if len(err) > 2000:
            err = err[-2000:]
        return {
            "exit_code": proc.returncode,
            "stdout": out,
            "stderr": err,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"timeout after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"exit_code": -1, "stdout": "", "stderr": f"{type(e).__name__}: {e}"}


SHELL_TOOL = Tool(
    name="run_shell",
    description=(
        "リポジトリルートで任意のシェルコマンドを実行する。標準出力/標準エラー/終了コードを返す。"
        "ファイルの確認、プロセスの状態確認、VOICEVOX の再起動、補助スクリプトの起動などに使う。"
        "破壊的なコマンド（rm -rf 等）は避けること。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "実行するコマンド"},
            "timeout": {"type": "integer", "description": "タイムアウト秒（既定120）"},
        },
        "required": ["command"],
    },
    func=_run_shell,
    safe_in_dry_run=False,
)
