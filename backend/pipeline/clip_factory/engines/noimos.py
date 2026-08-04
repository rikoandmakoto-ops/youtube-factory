"""NoimosAI（SaaS）のクリエイティブエージェントに切り抜きを任せるエンジン。

■ 調査結果（2026-08-04 時点）

NoimosAI には *動画生成用の公開 REST API は無い*。
docs.noimosai.com が公開している OpenAPI 仕様（/api-reference/openapi.json）は
Mintlify のサンプル（Plant Store）のままで、実体が無い。
プログラムから触れる口は次の2つだけ:

  - CLI  : `@agos-labs/noimosai-cli`（npm）
  - MCP  : `@agos-labs/noimosai-mcp` / https://mcp.noimosai.com/mcp

そしてどちらも公開ツールは `chat` / `list_workspaces` / `list_integrations` /
`post` の4つのみで、**素材動画をアップロードするAPI・切り抜きジョブを起動する
API・完成MP4をダウンロードするAPI は用意されていない**
（CLI 0.0.9 の内部 API クライアントにも media upload エンドポイントは無く、
チャット要求の `mediaPaths` パラメータは CLI から常に空で送られる）。

唯一の自動化経路は「チャットに元動画のURLを渡し、エージェントが生成した成果物の
メディアURLを受け取る」形になる。NoimosPostJson の media[].url にファイルURLが
載るため、CLI の `chat -o json` 出力からURLを拾ってダウンロードする実装にしてある。
ただしこの経路は **有料アカウント（$99/月〜）と API キーが無いと検証できない**。
NOIMOS_API_KEY が設定されるまでこのエンジンは明示的に失敗し、呼び出し側が
clip.fallback_engine（既定 local）へ落とす。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..sources import SourceVideo


class NoimosUnavailable(RuntimeError):
    """NoimosAI を無人実行できない（キー未設定 / CLI 未導入 / 動画が公開されていない）。"""


def _cli_bin(clip_cfg: Dict[str, Any]) -> Optional[str]:
    name = str(((clip_cfg.get("noimos") or {}).get("cli_bin")) or "noimosai")
    return shutil.which(name)


def _api_key() -> str:
    return (os.environ.get("NOIMOS_API_KEY") or "").strip()


def preflight(clip_cfg: Dict[str, Any]) -> Optional[str]:
    """使えない理由を返す。使えるなら None。"""
    if not _api_key():
        return ("NOIMOS_API_KEY が未設定です。NoimosAI の team settings → API タブで "
                "キーを発行し backend/.env に NOIMOS_API_KEY として追加してください "
                "（有料プラン $99/月〜が必要）。")
    if not _cli_bin(clip_cfg):
        return ("noimosai CLI が見つかりません。`npm i -g @agos-labs/noimosai-cli` を "
                "実行してください。")
    return None


def _run_cli(args: List[str], *, timeout: int) -> Dict[str, Any]:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"noimosai CLI failed ({proc.returncode}): {proc.stderr[-800:]}")
    try:
        return json.loads(proc.stdout)
    except Exception as e:
        raise RuntimeError(f"noimosai CLI の JSON 出力を解釈できません: {e}\n{proc.stdout[:500]}")


def _collect_media_urls(payload: Dict[str, Any]) -> List[str]:
    """NoimosPostJson から動画とみなせる media URL を拾う。"""
    urls: List[str] = []
    for post in payload.get("posts") or []:
        for media in post.get("media") or []:
            url = str(media.get("url") or "").strip()
            mime = str(media.get("mimeType") or "")
            if not url:
                continue
            if mime.startswith("video/") or url.lower().split("?")[0].endswith((".mp4", ".mov", ".webm")):
                urls.append(url)
    return urls


def _download(url: str, dest: Path, *, timeout: int = 600) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "youtube-factory/clip_factory"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    if dest.stat().st_size < 10_000:
        raise RuntimeError(f"ダウンロードしたファイルが小さすぎます: {dest} ({dest.stat().st_size} bytes)")
    return dest


def generate(
    *,
    source: SourceVideo,
    clip_cfg: Dict[str, Any],
    channel_raw: Dict[str, Any],
    source_channel_raw: Dict[str, Any],
    out_dir: Path,
    count: int = 1,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """NoimosAI に切り抜きを依頼し、返ってきた MP4 を取り込む。"""
    reason = preflight(clip_cfg)
    if reason:
        raise NoimosUnavailable(reason)

    source_url = source.source_url()
    if not source_url:
        raise NoimosUnavailable(
            f"元動画の YouTube URL が特定できません（{source.title}）。"
            "NoimosAI はローカルファイルを受け取れないため、公開済み動画のみ依頼できます。"
        )

    noimos_cfg = clip_cfg.get("noimos") or {}
    timeout = int(noimos_cfg.get("timeout_sec") or 900)
    template = str(noimos_cfg.get("prompt_template") or
                   "{source_url} から縦型ショートを{clips}本切り抜いてください。")
    prompt = template.format(
        source_url=source_url,
        source_title=source.video_title,
        clips=count,
        target_sec=int(clip_cfg.get("target_duration_sec") or 50),
    )

    if dry_run:
        return [{
            "clip_id": f"noimos_dryrun_{int(time.time())}",
            "engine": "noimos",
            "prompt": prompt,
            "video_path": None,
            "hook": "",
            "segment": {"start": 0, "end": 0},
        }]

    args = [_cli_bin(clip_cfg), "chat", "-p", prompt, "-o", "json"]
    workspace = str(noimos_cfg.get("workspace_id") or os.environ.get("NOIMOS_WORKSPACE_ID") or "")
    if workspace:
        args += ["-w", workspace]

    print(f"  ☁️ NoimosAI に切り抜きを依頼中（timeout {timeout}s）…")
    payload = _run_cli(args, timeout=timeout)
    urls = _collect_media_urls(payload)
    if not urls:
        raise RuntimeError(
            "NoimosAI から動画メディアが返りませんでした。"
            "クリエイティブエージェントの成果物はチャット応答に添付されない場合があります"
            f"（応答: {str(payload.get('output'))[:300]}）"
        )

    results: List[Dict[str, Any]] = []
    for n, url in enumerate(urls[:count]):
        clip_id = f"noimos_{source.source_channel_id}_{int(time.time())}_{n}"
        dest = out_dir / f"{clip_id}.mp4"
        _download(url, dest)
        results.append({
            "clip_id": clip_id,
            "engine": "noimos",
            "video_path": str(dest),
            "thumbnail_path": None,
            "hook": "",
            "source_media_url": url,
            "segment": {"start": 0.0, "end": 0.0, "duration": 0.0},
        })
    print(f"  ☁️ NoimosAI から {len(results)} 本取り込み完了")
    return results
