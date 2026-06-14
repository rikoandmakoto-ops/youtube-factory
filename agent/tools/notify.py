"""ユーザー通知ツール。

エージェントが自力で対処できない問題だけをユーザーに上げる。MVP では
state/notifications.log に追記しつつ標準出力にも出す。SLACK_WEBHOOK_URL /
LINE_NOTIFY_TOKEN が環境にあればそこにも送る（任意）。
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from ..config import STATE_DIR
from .base import Tool

NOTIFY_LOG = STATE_DIR / "notifications.log"


def _send_slack(text: str) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:  # noqa: BLE001
        return False


def _send_line(text: str) -> bool:
    token = os.environ.get("LINE_NOTIFY_TOKEN")
    if not token:
        return False
    try:
        req = urllib.request.Request(
            "https://notify-api.line.me/api/notify",
            data=urllib.parse.urlencode({"message": text}).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}"},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:  # noqa: BLE001
        return False


def _notify_user(message: str, level: str = "warning") -> dict:
    line = f"[{level.upper()}] {message}"
    try:
        with NOTIFY_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass
    print(f"\n🔔 NOTIFY {line}\n")

    channels = []
    if _send_slack(line):
        channels.append("slack")
    if _send_line(line):
        channels.append("line")
    return {"ok": True, "delivered_to": channels or ["log"], "message": message}


NOTIFY_TOOL = Tool(
    name="notify_user",
    description=(
        "自力で解決できない問題だけをユーザーに通知する。例: トークンが完全失効しUI再認証が必要、"
        "APIキー枯渇、原因不明の繰り返し失敗。通常運用の成功/失敗はログに記録すればよく、通知は不要。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "ユーザーへのメッセージ（何が起きて何が必要か）"},
            "level": {"type": "string", "enum": ["info", "warning", "critical"]},
        },
        "required": ["message"],
    },
    func=_notify_user,
    safe_in_dry_run=True,
)
