"""投稿直後の自動コメント — 登録導線をコメント欄にもう1つ作る。

狙い:
    説明文の登録リンクは折りたたまれていて読まれない。一方コメント欄は
    ショートでは常時1件目が見えており、投稿者コメントは必ず上位に出る。
    そこへ「登録導線 + 次に見る動画 + 返信を誘う問いかけ」を置くと、
    登録率とコメント数（＝アルゴリズム上のエンゲージメント）の両方に効く。

API の制約（重要）:
    - コメント投稿は commentThreads.insert。`youtube.force-ssl` スコープが必要で、
      本プロジェクトの OAuth は既にこのスコープを取得済み（youtube_oauth.SCOPES）。
    - **コメントの「固定（ピン留め）」を行う API は YouTube Data API v3 に存在しない**。
      投稿者コメントは既定で上位に表示されるが、明示的な固定は YouTube Studio から
      手動で行う必要がある。ここでは投稿までを自動化する。
    - **非公開／予約公開中の動画にはコメントできない**（400/403 が返る）。
      予約公開のジョブはコメントを保留キューに入れ、公開時刻を過ぎてから
      `flush_pending()` が投稿する。

設定（チャンネル JSON の publish_settings.auto_comment）:
    {
      "enabled": true,
      "template": "...",             # 任意。{title}/{subscribe_url}/{main_url} を展開
      "question": "みんなはどう思う？"  # 任意。返信を誘う一言
    }
    enabled が無い場合は投稿しない（明示的なオプトイン）。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import youtube_oauth as yt_oauth
from . import description_blocks as _desc_blocks
from . import viewer_requests as _viewer_requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
PENDING_FILE = PROJECT_ROOT / "data" / "pending_comments.json"
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"

# コメント本文の上限（YouTube は 10000 文字だが、折りたたまれずに読まれるのは冒頭のみ）
MAX_COMMENT_CHARS = 900

# 予約公開の動画にコメントするまでの猶予。publishAt ちょうどだと
# まだ public に切り替わっていないことがあるので少し後ろにずらす。
PUBLISH_GRACE_SECONDS = 180

# flush で1件あたり何回まで再試行するか。使い切ったら捨てる（無限に溜めない）。
MAX_ATTEMPTS = 5

_lock = threading.Lock()


# ---------------------------------------------------------------------
# チャンネル設定
# ---------------------------------------------------------------------

def _load_channel(channel_id: str) -> Dict[str, Any]:
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _auto_comment_cfg(channel_dict: Dict[str, Any]) -> Dict[str, Any]:
    cfg = ((channel_dict or {}).get("publish_settings") or {}).get("auto_comment")
    return cfg if isinstance(cfg, dict) else {}


def is_enabled(channel_id: str, channel_dict: Optional[Dict[str, Any]] = None) -> bool:
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    return bool(_auto_comment_cfg(cd).get("enabled"))


# ---------------------------------------------------------------------
# 本文組み立て
# ---------------------------------------------------------------------

DEFAULT_QUESTION = "これ知ってた？コメントで教えて！"


def build_comment_text(
    channel_id: str,
    *,
    title: str = "",
    is_short: bool = True,
    main_url: Optional[str] = None,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> str:
    """投稿するコメント本文を組み立てる。

    既定の構成（上から読まれる順に効くものを置く）:
        1. 返信を誘う問いかけ  ← コメント数が伸びるとアルゴリズム評価が上がる
        2. ワンクリック登録リンク
        3. 関連動画への導線（長尺があるチャンネルのみ）
    """
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    cfg = _auto_comment_cfg(cd)

    sub_url = _desc_blocks.subscribe_url(channel_id) or ""
    ch_url = _desc_blocks.channel_url(channel_id) or ""
    question = str(cfg.get("question") or DEFAULT_QUESTION).strip()

    template = cfg.get("template")
    if isinstance(template, str) and template.strip():
        try:
            text = template.format(
                title=title or "",
                question=question,
                subscribe_url=sub_url,
                channel_url=ch_url,
                main_url=main_url or "",
            )
        except Exception:
            # テンプレートに未知のプレースホルダがあっても投稿は止めない
            text = template
        return text.strip()[:MAX_COMMENT_CHARS]

    lines: List[str] = []
    if question:
        lines.append(f"💬 {question}")
    # 視聴者参加型: リクエスト募集の1行。返信で来たリクエストは
    # comment_demand が拾ってテーマキューに回る。
    try:
        request_line = _viewer_requests.build_comment_line(channel_id, channel_dict=cd)
    except Exception:
        request_line = ""
    if request_line:
        lines.append(request_line)
    if sub_url:
        lines.append("")
        lines.append("🔔 毎日投稿してるので、チャンネル登録して待っててね！")
        lines.append(f"👉 {sub_url}")
    if main_url:
        lines.append("")
        lines.append(f"🎬 フル解説はこちら → {main_url}")
    elif ch_url and is_short:
        lines.append("")
        lines.append(f"⚡ 他のショートもここから → {ch_url}/shorts")

    return "\n".join(lines).strip()[:MAX_COMMENT_CHARS]


# ---------------------------------------------------------------------
# 投稿
# ---------------------------------------------------------------------

def post_comment(channel_id: str, video_id: str, text: str) -> Dict[str, Any]:
    """commentThreads.insert で投稿者コメントを1件付ける。

    Returns:
        {"ok": True, "comment_id": ...} / {"ok": False, "error": ..., "retryable": bool}
    """
    if not (video_id and (text or "").strip()):
        return {"ok": False, "error": "video_id と text は必須", "retryable": False}

    try:
        from googleapiclient.discovery import build  # type: ignore
    except Exception as e:
        return {"ok": False, "error": f"google-api-python-client 未導入: {e}", "retryable": False}

    creds = yt_oauth.get_credentials_for(channel_id)
    if not creds:
        return {"ok": False, "error": f"{channel_id} が YouTube 未連携", "retryable": False}

    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = (
            yt.commentThreads()
            .insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {"textOriginal": text[:MAX_COMMENT_CHARS]}
                        },
                    }
                },
            )
            .execute()
        )
    except Exception as e:
        msg = str(e)
        # 非公開/予約公開中・コメント無効はあとで再試行する価値がある。
        retryable = any(
            k in msg
            for k in ("forbidden", "403", "commentsDisabled", "videoNotFound", "404", "processing")
        )
        return {"ok": False, "error": msg, "retryable": retryable}

    return {"ok": True, "comment_id": resp.get("id"), "video_id": video_id}


# ---------------------------------------------------------------------
# 保留キュー（予約公開・一時エラー用）
# ---------------------------------------------------------------------

def _read_pending() -> List[Dict[str, Any]]:
    if not PENDING_FILE.exists():
        return []
    try:
        data = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_pending(items: List[Dict[str, Any]]) -> None:
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PENDING_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    os.replace(tmp, PENDING_FILE)


def enqueue(
    channel_id: str,
    video_id: str,
    text: str,
    *,
    due_at: Optional[str] = None,
) -> None:
    """公開時刻まで待ってから投稿するコメントを保留キューに積む。

    Args:
        due_at: RFC3339 UTC ("2026-08-19T10:00:00Z")。未指定なら即時対象。
    """
    with _lock:
        items = _read_pending()
        # 同じ動画への二重登録を防ぐ
        if any(i.get("video_id") == video_id for i in items):
            return
        items.append(
            {
                "channel_id": channel_id,
                "video_id": video_id,
                "text": text,
                "due_at": due_at,
                "attempts": 0,
                "queued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        _write_pending(items)
    print(f"🗒️ auto_comment queued: {channel_id}/{video_id} (due {due_at or 'now'})")


def _parse_due(due_at: Optional[str]) -> Optional[datetime]:
    if not due_at:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(due_at, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def flush_pending() -> Dict[str, Any]:
    """期限が来た保留コメントを投稿する。スケジューラから定期的に呼ぶ。"""
    with _lock:
        items = _read_pending()
    if not items:
        return {"posted": 0, "pending": 0, "dropped": 0}

    now = datetime.now(timezone.utc)
    keep: List[Dict[str, Any]] = []
    posted = 0
    dropped = 0

    for item in items:
        due = _parse_due(item.get("due_at"))
        if due is not None and now.timestamp() < due.timestamp() + PUBLISH_GRACE_SECONDS:
            keep.append(item)
            continue

        res = post_comment(
            str(item.get("channel_id") or ""),
            str(item.get("video_id") or ""),
            str(item.get("text") or ""),
        )
        if res.get("ok"):
            posted += 1
            print(f"💬 auto_comment posted: {item.get('channel_id')}/{item.get('video_id')}")
            continue

        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["last_error"] = str(res.get("error"))[:300]
        if res.get("retryable") and item["attempts"] < MAX_ATTEMPTS:
            # 次回の flush で再試行（15分後を目安に後ろ倒し）
            item["due_at"] = datetime.fromtimestamp(
                now.timestamp() + 900, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            keep.append(item)
        else:
            dropped += 1
            print(
                f"⚠️ auto_comment dropped {item.get('channel_id')}/{item.get('video_id')}: "
                f"{item.get('last_error')}"
            )

    with _lock:
        _write_pending(keep)
    return {"posted": posted, "pending": len(keep), "dropped": dropped}


# ---------------------------------------------------------------------
# 呼び出し口
# ---------------------------------------------------------------------

def post_for_video(
    channel_id: str,
    video_id: str,
    *,
    title: str = "",
    is_short: bool = True,
    main_url: Optional[str] = None,
    publish_at: Optional[str] = None,
    channel_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """アップロード完了後に呼ぶ入口。

    - チャンネルが auto_comment を有効にしていなければ何もしない。
    - 予約公開（publish_at が未来）なら保留キューへ。公開後に flush が投稿する。
    - 即時公開なら直接投稿し、失敗して再試行の価値があれば保留キューへ。
    """
    cd = channel_dict if channel_dict is not None else _load_channel(channel_id)
    if not is_enabled(channel_id, cd):
        return {"ok": False, "skipped": "disabled"}
    if not video_id:
        return {"ok": False, "skipped": "no_video_id"}

    text = build_comment_text(
        channel_id,
        title=title,
        is_short=is_short,
        main_url=main_url,
        channel_dict=cd,
    )
    if not text:
        return {"ok": False, "skipped": "empty_text"}

    due = _parse_due(publish_at)
    if due is not None and due.timestamp() > datetime.now(timezone.utc).timestamp():
        enqueue(channel_id, video_id, text, due_at=publish_at)
        return {"ok": True, "queued": True, "due_at": publish_at}

    res = post_comment(channel_id, video_id, text)
    if res.get("ok"):
        print(f"💬 auto_comment posted: {channel_id}/{video_id}")
        return res
    if res.get("retryable"):
        enqueue(channel_id, video_id, text, due_at=None)
        return {"ok": True, "queued": True, "error": res.get("error")}
    print(f"⚠️ auto_comment failed {channel_id}/{video_id}: {res.get('error')}")
    return res


def post_for_video_async(**kwargs: Any) -> None:
    """アップロードスレッドを塞がないための fire-and-forget ラッパ。"""

    def _work() -> None:
        try:
            post_for_video(**kwargs)
        except Exception as e:  # 自動コメントの失敗で公開処理を壊さない
            print(f"⚠️ auto_comment thread failed: {e}")

    threading.Thread(target=_work, name="auto-comment", daemon=True).start()
