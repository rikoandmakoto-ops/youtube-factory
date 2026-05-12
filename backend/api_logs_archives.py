"""
YouTube Factory — Logs & Scenario Archives API

リアルタイムログ取得とシナリオアーカイブ閲覧を提供する。
- `/api/logs` : サーバーログのテール
- `/api/scenario-archives` : 過去シナリオの一覧 / 検索
- `/api/scenario-archives/{channel_id}/{file_name}` : 詳細
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api_phase1 import require_session


router = APIRouter(prefix="/api", tags=["logs-archives"])

PROJECT_ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"

# ログ候補の優先順位（最後に更新されたものを採用）
_LOG_CANDIDATES = [
    "/tmp/uvicorn.log",
    "/tmp/yt-factory-backend.log",
    "/tmp/ytf-backend.log",
    "/tmp/backend.log",
    "/tmp/uvicorn-main.log",
]


def _resolve_log_path() -> Optional[Path]:
    """環境変数 LOG_FILE を最優先、なければ候補から最新の存在ファイルを選ぶ。"""
    env_path = os.environ.get("LOG_FILE")
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists() and p.is_file():
            return p
    best: Optional[Path] = None
    best_mtime = -1.0
    for cand in _LOG_CANDIDATES:
        p = Path(cand)
        if p.exists() and p.is_file():
            mt = p.stat().st_mtime
            if mt > best_mtime:
                best_mtime = mt
                best = p
    return best


def _tail_lines(path: Path, max_lines: int) -> List[str]:
    """ファイル末尾から最大 max_lines 行を返す。バイナリ安全に読む。"""
    if max_lines <= 0:
        return []
    # ファイル末尾から逆順にチャンク読みして行数を確保する
    block = 4096
    data = bytearray()
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        remaining = end
        while remaining > 0 and data.count(b"\n") <= max_lines:
            read_size = min(block, remaining)
            remaining -= read_size
            f.seek(remaining)
            data[:0] = f.read(read_size)
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-max_lines:]


@router.get("/logs")
async def get_logs(
    lines: int = Query(default=200, ge=1, le=5000),
    filter: Optional[str] = Query(default=None, description="部分一致フィルタ"),
    level: Optional[str] = Query(
        default=None, description="error/warn/info のいずれか"
    ),
    _=Depends(require_session),
) -> Dict[str, Any]:
    """サーバーログをテールして返す。"""
    log_path = _resolve_log_path()
    if log_path is None:
        return {
            "path": None,
            "size_bytes": 0,
            "mtime": None,
            "lines": [],
            "note": "No log file found (set LOG_FILE env or write to /tmp/uvicorn.log)",
        }
    try:
        raw = _tail_lines(log_path, lines)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log: {e}")

    f_text = (filter or "").strip()
    f_level = (level or "").strip().lower()

    def _matches(line: str) -> bool:
        if f_text and f_text not in line:
            return False
        if f_level:
            low = line.lower()
            if f_level == "error" and not any(
                k in low for k in ("error", "❌", "traceback", "exception")
            ):
                return False
            if f_level == "warn" and not any(
                k in low for k in ("warn", "⚠️")
            ):
                return False
            if f_level == "info" and any(
                k in low for k in ("error", "❌", "warn", "⚠️", "traceback", "exception")
            ):
                return False
        return True

    filtered = [ln for ln in raw if _matches(ln)]
    stat = log_path.stat()
    return {
        "path": str(log_path),
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "lines": filtered,
    }


def _summarize_scenario_lines(lines: Any) -> Dict[str, Any]:
    if not isinstance(lines, list):
        return {"count": 0, "chars": 0, "avg_chars": 0}
    count = 0
    chars = 0
    for entry in lines:
        if isinstance(entry, dict):
            text = entry.get("text", "")
        elif isinstance(entry, str):
            text = entry
        else:
            text = ""
        count += 1
        chars += len(text)
    avg = round(chars / count, 1) if count else 0
    return {"count": count, "chars": chars, "avg_chars": avg}


def _scenario_summary(channel_id: str, file_path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    short_stats = _summarize_scenario_lines(data.get("short_scenario"))
    full_stats = _summarize_scenario_lines(data.get("full_scenario"))
    compete = data.get("compete") or {}
    blind = compete.get("blind_eval") if isinstance(compete, dict) else None
    cands = compete.get("candidates") if isinstance(compete, dict) else None
    stat = file_path.stat()
    return {
        "channel_id": channel_id,
        "file": file_path.name,
        "title": data.get("title") or file_path.stem,
        "theme": data.get("theme", {}),
        "style": data.get("style", "yukkuri"),
        "short": short_stats,
        "full": full_stats,
        "mtime": stat.st_mtime,
        "size_bytes": stat.st_size,
        "has_compete": bool(compete),
        "chosen_provider": (compete.get("selected_by") or None) if compete else None,
        "compete_summary": {
            "selected_by": compete.get("selected_by") if compete else None,
            "winner_model": (blind or {}).get("winner_model") if isinstance(blind, dict) else None,
            "candidates": {
                "gpt": (cands or {}).get("gpt") if isinstance(cands, dict) else None,
                "claude": (cands or {}).get("claude") if isinstance(cands, dict) else None,
            },
        } if compete else None,
    }


@router.get("/scenario-archives")
async def list_scenario_archives(
    channel_id: Optional[str] = None,
    q: Optional[str] = None,
    has_compete: Optional[bool] = None,
    limit: int = Query(default=200, ge=1, le=2000),
    _=Depends(require_session),
) -> Dict[str, Any]:
    """data/scenarios/ 配下のシナリオファイルを一覧。"""
    if not SCENARIOS_DIR.exists():
        return {"items": [], "channels": []}

    if channel_id:
        channel_dirs = [SCENARIOS_DIR / channel_id]
    else:
        channel_dirs = [d for d in SCENARIOS_DIR.iterdir() if d.is_dir()]

    channels = sorted([d.name for d in SCENARIOS_DIR.iterdir() if d.is_dir()])

    items: List[Dict[str, Any]] = []
    needle = (q or "").strip().lower()
    for ch_dir in channel_dirs:
        if not ch_dir.exists() or not ch_dir.is_dir():
            continue
        for f in ch_dir.glob("*.json"):
            summary = _scenario_summary(ch_dir.name, f)
            if not summary:
                continue
            if has_compete is True and not summary["has_compete"]:
                continue
            if has_compete is False and summary["has_compete"]:
                continue
            if needle:
                haystacks = [
                    summary["title"].lower(),
                    summary["file"].lower(),
                    json.dumps(summary.get("theme") or {}, ensure_ascii=False).lower(),
                ]
                if not any(needle in h for h in haystacks):
                    continue
            items.append(summary)

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"items": items[:limit], "channels": channels, "total": len(items)}


@router.get("/scenario-archives/{channel_id}/{file_name}")
async def get_scenario_archive(
    channel_id: str,
    file_name: str,
    _=Depends(require_session),
) -> Dict[str, Any]:
    """シナリオ詳細（フルJSON）を返す。"""
    safe_name = Path(file_name).name  # path traversal 対策
    file_path = SCENARIOS_DIR / channel_id / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Scenario not found: {channel_id}/{safe_name}")
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse scenario: {e}")
    stat = file_path.stat()
    return {
        "channel_id": channel_id,
        "file": safe_name,
        "mtime": stat.st_mtime,
        "size_bytes": stat.st_size,
        "data": data,
    }
