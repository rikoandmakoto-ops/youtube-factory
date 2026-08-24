"""動画生成ツール。

既存パイプライン（run_short_only.run_for）をそのまま呼ぶ。台本生成→動画生成までを
1 コールで行い、生成物のパス（short mp4 / サムネ / 説明文）を返す。
VOICEVOX の死活確認と再起動もここに置く。
"""

from __future__ import annotations

import subprocess
import urllib.request

from .base import Tool

VOICEVOX_URL = "http://localhost:50021"


def _voicevox_alive() -> bool:
    try:
        urllib.request.urlopen(f"{VOICEVOX_URL}/speakers", timeout=2)
        return True
    except Exception:  # noqa: BLE001
        return False


def _check_voicevox() -> dict:
    return {"alive": _voicevox_alive(), "url": VOICEVOX_URL}


def _restart_voicevox() -> dict:
    """macOS の VOICEVOX.app を起動して立ち上がるまで待つ。"""
    if _voicevox_alive():
        return {"alive": True, "action": "noop", "note": "すでに起動中"}
    try:
        subprocess.run(["open", "-a", "VOICEVOX"], capture_output=True, text=True, timeout=20)
    except Exception as e:  # noqa: BLE001
        return {"alive": False, "action": "open_failed", "error": str(e)}

    import time

    for _ in range(30):  # 最大 ~60 秒待つ
        time.sleep(2)
        if _voicevox_alive():
            return {"alive": True, "action": "started"}
    return {"alive": False, "action": "started_but_not_responding",
            "note": "open は実行したが 60 秒以内に応答なし"}


def _generate_short(channel_id: str) -> dict:
    """既存の run_short_only パイプラインでショート動画を生成する。"""
    if not _voicevox_alive():
        return {"ok": False,
                "error": "VOICEVOX が応答しません。restart_voicevox を先に試してください。"}

    # backend は config.bootstrap() で sys.path に入っている前提
    import run_short_only  # type: ignore

    out = run_short_only.run_for(channel_id)
    if not out or out.get("error"):
        return {"ok": False, "error": (out or {}).get("error", "unknown error")}

    return {
        "ok": True,
        "channel_id": channel_id,
        "theme": (out.get("_theme") or {}).get("title"),
        "output_dir": out.get("output_dir"),
        "short_video": out.get("short"),
        "short_thumbnail": out.get("short_thumbnail"),
        "thumbnail": out.get("thumbnail"),
        "short_title": out.get("short_title"),
        "short_description": out.get("short_description"),
        "scenario_path": out.get("_scenario_path"),
    }


GENERATE_SHORT_TOOL = Tool(
    name="generate_short",
    description=(
        "指定チャンネルのショート動画を 1 本生成する（台本生成→音声→動画→サムネ→説明文）。"
        "テーマは autopilot.theme_queue 等から自動選択される。生成物のファイルパスを返す。"
        "アップロードは行わない。生成後 upload_to_youtube を呼ぶこと。"
        "数分かかる重い処理。VOICEVOX が必要。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "channel_id": {"type": "string", "enum": ["scp-lab", "daily-science"]},
        },
        "required": ["channel_id"],
    },
    func=_generate_short,
)

CHECK_VOICEVOX_TOOL = Tool(
    name="check_voicevox",
    description="VOICEVOX(localhost:50021) が起動しているか確認する。",
    input_schema={"type": "object", "properties": {}},
    func=_check_voicevox,
    safe_in_dry_run=True,
)

RESTART_VOICEVOX_TOOL = Tool(
    name="restart_voicevox",
    description="VOICEVOX が停止していれば VOICEVOX.app を起動し、応答するまで待つ。",
    input_schema={"type": "object", "properties": {}},
    func=_restart_voicevox,
)
