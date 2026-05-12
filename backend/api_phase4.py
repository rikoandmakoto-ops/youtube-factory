"""
YouTube Factory — Phase 4 API

5 features:
1. スケジュール投稿 — APSchedulerで曜日/時間指定の自動生成+投稿
2. 動画テンプレート — 生成フォーム設定の保存/再利用
3. 生成履歴・コスト管理 — 履歴一覧 + 月別コストサマリ
4. A/Bテスト — サムネ/タイトルの複数パターン生成
5. 通知 — LINE Notify / Slack Webhook / SMTP メール

すべて `/api/*` 配下、`require_session` で認証する。
スケジュール・テンプレート・通知設定・A/Bテスト結果は SQLite (data/phase4.db) に永続化。
"""

from __future__ import annotations

import json
import os
import smtplib
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_phase1 import _state, require_session

# ── APScheduler は遅延 import（未インストール時の起動失敗を避ける） ──
try:
    from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
    from apscheduler.triggers.cron import CronTrigger  # type: ignore
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    BackgroundScheduler = None  # type: ignore
    CronTrigger = None  # type: ignore


router = APIRouter(prefix="/api", tags=["phase4"])

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
DB_PATH = DATA_DIR / "phase4.db"

# JST 曜日マップ (フロントは sun=0 ... sat=6 を使う)
DOW_NAMES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]


# =====================================================================
# DB
# =====================================================================

_db_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _db_lock:
        conn = _db()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    days_of_week TEXT NOT NULL,   -- JSON array of int 0..6 (sun=0)
                    hour INTEGER NOT NULL,
                    minute INTEGER NOT NULL,
                    theme_mode TEXT NOT NULL,     -- 'manual' | 'auto'
                    theme TEXT,                   -- manualのとき
                    duration_minutes INTEGER NOT NULL DEFAULT 12,
                    auto_publish INTEGER NOT NULL DEFAULT 0,
                    publish_offset_minutes INTEGER,  -- 自動投稿時に「生成完了から N 分後」に公開する。NULL=即時
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at TEXT,
                    last_run_status TEXT,
                    last_run_job_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    line_token TEXT,
                    slack_webhook_url TEXT,
                    smtp_host TEXT,
                    smtp_port INTEGER,
                    smtp_user TEXT,
                    smtp_password TEXT,
                    smtp_from TEXT,
                    smtp_to TEXT,
                    notify_on_generate_done INTEGER NOT NULL DEFAULT 1,
                    notify_on_upload_done INTEGER NOT NULL DEFAULT 1,
                    notify_on_schedule_run INTEGER NOT NULL DEFAULT 1,
                    notify_on_error INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS ab_variants (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    kind TEXT NOT NULL,           -- 'thumbnail' | 'title'
                    variant_index INTEGER NOT NULL,
                    content TEXT NOT NULL,        -- text or path
                    selected INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ab_variants_job ON ab_variants(job_id);
                """
            )
            # 既存DB向けの軽量マイグレーション（CREATE TABLE IF NOT EXISTS では追加されないため）
            try:
                conn.execute("ALTER TABLE schedules ADD COLUMN publish_offset_minutes INTEGER")
            except sqlite3.OperationalError:
                pass  # 既にカラムが存在
            conn.commit()
        finally:
            conn.close()


_init_db()


# =====================================================================
# 1. スケジュール投稿
# =====================================================================

class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    channel_id: str = Field(min_length=1)
    days_of_week: List[int] = Field(min_length=1)  # 0=sun .. 6=sat
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    theme_mode: str = Field(default="auto")  # 'manual' | 'auto'
    theme: Optional[str] = None
    duration_minutes: int = Field(default=12, ge=1, le=60)
    auto_publish: bool = False
    # 自動投稿時に「生成完了時点から N 分後」に YouTube 上で公開する。
    # None または 0 以下 = 即時公開（既存挙動）。最大 30 日まで。
    publish_offset_minutes: Optional[int] = Field(default=None, ge=0, le=60 * 24 * 30)
    enabled: bool = True


class ScheduleOut(ScheduleIn):
    id: str
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    last_run_job_id: Optional[str] = None
    next_run_at: Optional[str] = None
    created_at: str
    updated_at: str


def _row_to_schedule(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["days_of_week"] = json.loads(d["days_of_week"])
    except Exception:
        d["days_of_week"] = []
    d["auto_publish"] = bool(d["auto_publish"])
    d["enabled"] = bool(d["enabled"])
    # 旧スキーマで存在しない場合のフォールバック
    if "publish_offset_minutes" not in d:
        d["publish_offset_minutes"] = None
    return d


def _validate_dow(days: List[int]) -> None:
    for d in days:
        if not (0 <= d <= 6):
            raise HTTPException(status_code=400, detail=f"Invalid day_of_week: {d}")


def _save_schedule(s: ScheduleIn, schedule_id: str, created_at: str) -> Dict[str, Any]:
    _validate_dow(s.days_of_week)
    if s.theme_mode not in ("manual", "auto"):
        raise HTTPException(status_code=400, detail="theme_mode must be 'manual' or 'auto'")
    if s.theme_mode == "manual" and not (s.theme and s.theme.strip()):
        raise HTTPException(status_code=400, detail="manualモードはthemeが必須です")

    now = datetime.now().isoformat()
    with _db_lock:
        conn = _db()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO schedules
                (id, name, channel_id, days_of_week, hour, minute,
                 theme_mode, theme, duration_minutes, auto_publish,
                 publish_offset_minutes, enabled,
                 last_run_at, last_run_status, last_run_job_id,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        (SELECT last_run_at FROM schedules WHERE id = ?),
                        (SELECT last_run_status FROM schedules WHERE id = ?),
                        (SELECT last_run_job_id FROM schedules WHERE id = ?),
                        ?, ?)
                """,
                (
                    schedule_id, s.name, s.channel_id,
                    json.dumps(sorted(set(s.days_of_week))),
                    s.hour, s.minute,
                    s.theme_mode, s.theme, s.duration_minutes,
                    1 if s.auto_publish else 0,
                    s.publish_offset_minutes,
                    1 if s.enabled else 0,
                    schedule_id, schedule_id, schedule_id,
                    created_at, now,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        finally:
            conn.close()
    _refresh_scheduler_job(schedule_id)
    return _row_to_schedule(row)


def _list_schedules() -> List[Dict[str, Any]]:
    with _db_lock:
        conn = _db()
        try:
            rows = conn.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall()
        finally:
            conn.close()
    return [_row_to_schedule(r) for r in rows]


def _get_schedule(schedule_id: str) -> Optional[Dict[str, Any]]:
    with _db_lock:
        conn = _db()
        try:
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        finally:
            conn.close()
    return _row_to_schedule(row) if row else None


def _delete_schedule(schedule_id: str) -> bool:
    with _db_lock:
        conn = _db()
        try:
            cur = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
        finally:
            conn.close()
    _remove_scheduler_job(schedule_id)
    return cur.rowcount > 0


# ── APScheduler ──

_scheduler: Optional["BackgroundScheduler"] = None


def _ensure_scheduler() -> Optional["BackgroundScheduler"]:
    global _scheduler
    if not HAS_APSCHEDULER:
        return None
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
        _scheduler.start()
    return _scheduler


def _refresh_scheduler_job(schedule_id: str) -> None:
    sch = _ensure_scheduler()
    if sch is None:
        return
    s = _get_schedule(schedule_id)
    if not s:
        return
    job_id = f"sched:{schedule_id}"
    try:
        sch.remove_job(job_id)
    except Exception:
        pass
    if not s["enabled"]:
        return
    try:
        trigger = CronTrigger(
            day_of_week=",".join(DOW_NAMES[d] for d in s["days_of_week"]),
            hour=s["hour"],
            minute=s["minute"],
            timezone="Asia/Tokyo",
        )
        sch.add_job(_run_schedule, trigger=trigger, id=job_id, args=[schedule_id], replace_existing=True)
    except Exception as e:
        print(f"⚠️ Failed to schedule {schedule_id}: {e}")


def _remove_scheduler_job(schedule_id: str) -> None:
    sch = _ensure_scheduler()
    if sch is None:
        return
    try:
        sch.remove_job(f"sched:{schedule_id}")
    except Exception:
        pass


def _next_run_at(schedule_id: str) -> Optional[str]:
    sch = _ensure_scheduler()
    if sch is None:
        return None
    job = sch.get_job(f"sched:{schedule_id}")
    if not job or not job.next_run_time:
        return None
    return job.next_run_time.isoformat()


def _restore_all_schedules() -> None:
    """起動時に DB の有効スケジュールを APScheduler に復元する。"""
    sch = _ensure_scheduler()
    if sch is None:
        return
    for s in _list_schedules():
        if s["enabled"]:
            _refresh_scheduler_job(s["id"])


def _attach_auto_publish_marker(
    queue,
    job_id: str,
    schedule_id: str,
    auto_publish: bool,
    publish_offset_minutes: Optional[int] = None,
) -> None:
    """ジョブの scenario_data に auto_publish フラグを刻む。
    on_job_complete フックが完了時にこのマーカーを見て pair publish を起こす。
    publish_offset_minutes が正値なら「生成完了時点 + N 分」で予約公開する。
    """
    try:
        with queue._lock:
            j = queue._jobs.get(job_id)
            if j:
                opts = dict(j.scenario_data.get("_options") or {})
                opts.update({
                    "auto_publish": bool(auto_publish),
                    "schedule_id": schedule_id,
                    "publish_offset_minutes": publish_offset_minutes,
                })
                j.scenario_data["_options"] = opts
    except Exception:
        pass


def _compute_publish_at_from_offset(offset_minutes: Optional[int]) -> Optional[str]:
    """生成完了時点から N 分後の YouTube publishAt 文字列 (RFC3339 UTC)。

    None / 0 / 負値の場合は None（即時公開）を返す。
    """
    if not offset_minutes or offset_minutes <= 0:
        return None
    publish_dt = datetime.now(timezone.utc) + timedelta(minutes=int(offset_minutes))
    return publish_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def on_generation_complete(job) -> None:
    """JobQueue.on_job_complete フック。auto_publish=True ならペア公開を起動。

    入力: queue 内部の Job オブジェクト（to_dict でなく raw）
    """
    try:
        opts = (job.scenario_data or {}).get("_options") or {}
    except Exception:
        opts = {}

    if not opts.get("auto_publish"):
        # auto_publish=False でも生成完了通知は出す
        try:
            _send_event_notification(
                "generate_done",
                f"🎬 動画生成完了: {job.title} (job: {job.id})",
            )
        except Exception:
            pass
        return

    cm = _state.get("channel_manager")
    ch = cm.get(job.channel_id) if cm else None

    publish_settings = ch.get_publish_settings() if ch else {}
    youtube_channel_id = ch.youtube_channel_id if ch else None

    # ペア公開トリガー（YouTube 連携必須）
    try:
        from pipeline import youtube_oauth as yt_oauth
        from pipeline import youtube_pair_publisher as pair_pub
    except Exception as e:
        _send_event_notification(
            "error",
            f"⚠️ 自動公開失敗 ({job.id}): YouTube モジュール未利用可: {e}",
        )
        return

    if not yt_oauth.is_connected_for(job.channel_id):
        _send_event_notification(
            "error",
            f"⚠️ 自動公開スキップ ({job.id}): チャンネル '{job.channel_id}' が YouTube 未連携です",
        )
        return

    # スケジュール公開: マーカーに publish_offset_minutes が乗っていれば
    # 「生成完了時点 + N 分」を YouTube の publishAt として渡す
    publish_offset = opts.get("publish_offset_minutes")
    main_publish_at = _compute_publish_at_from_offset(publish_offset)

    result = job.result or {}
    paths = pair_pub._resolve_paths_from_result(result)

    if not paths.get("main_video") or not paths.get("short_video"):
        # short が無い時は main 単体だけ公開（オフセット指定があればスケジュール公開）
        if paths.get("main_video"):
            _start_single_main_publish(
                job=job,
                main_video=paths["main_video"],
                main_thumb=paths.get("main_thumb"),
                main_desc_file=paths.get("main_desc_file"),
                publish_settings=publish_settings,
                youtube_channel_id=youtube_channel_id,
                tags=ch.get_hashtags() if ch else [],
                category_id=ch.get_category() if ch else "27",
                publish_at=main_publish_at,
            )
        else:
            _send_event_notification(
                "error",
                f"⚠️ 自動公開失敗 ({job.id}): 動画ファイルパス未解決",
            )
        return

    main_d = pair_pub._read_desc(paths.get("main_desc_file"))
    short_d = pair_pub._read_desc(paths.get("short_desc_file"))

    pair_job_id = pair_pub.create_pair_job()

    def _on_pair_done(pj: Dict[str, Any]) -> None:
        main = pj.get("main") or {}
        short = pj.get("short") or {}
        msg = (
            f"🚀 自動公開完了 [{job.title}]\n"
            f"メイン: {main.get('url', '?')}\n"
            f"ショート: {short.get('url', '?')} (公開予定: {short.get('publish_at', '?')})"
        )
        _send_event_notification("upload_done", msg)
        # video_status DB 永続化
        try:
            from api_phase3 import _record_pair_status_to_db
            _record_pair_status_to_db(job.id, job.channel_id, main, short)
        except Exception:
            pass
        # サムネ AB テスト登録（メイン動画のみ）
        try:
            main_vid = main.get("video_id")
            if main_vid:
                from pipeline.analytics import thumbnail_ab_test as _tat
                _tat.register_test(
                    video_id=main_vid,
                    channel_id=job.channel_id,
                    video_title=main.get("title") or job.title,
                    original_thumbnail_path=paths.get("main_thumb"),
                )
        except Exception as e:
            print(f"⚠️ thumbnail_ab_test register failed for {job.id}: {e}")

    privacy = publish_settings.get("default_privacy") or "public"
    delay = int(publish_settings.get("short_delay_minutes") or 10)
    template = publish_settings.get("short_description_template")
    raw_tags = ch.get_hashtags() if ch else []
    tags = [t.lstrip("#") for t in raw_tags]
    category_id = ch.get_category() if ch else "27"

    threading.Thread(
        target=pair_pub.run_pair_publish,
        kwargs={
            "job_id": pair_job_id,
            "main_video_path": paths["main_video"],
            "short_video_path": paths["short_video"],
            "main_title": main_d.get("title") or job.title,
            "short_title": short_d.get("title") or (job.title + "【ショート】"),
            "main_description": main_d.get("body") or "",
            "short_description": short_d.get("body") or "",
            "tags": tags,
            "category_id": category_id,
            "privacy": privacy,
            "short_delay_minutes": delay,
            "short_description_template": template,
            "youtube_channel_id": youtube_channel_id,
            "main_thumbnail_path": paths.get("main_thumb"),
            "short_thumbnail_path": paths.get("short_thumb"),
            "on_complete": _on_pair_done,
            "auth_channel_id": job.channel_id,
            "main_publish_at": main_publish_at,
        },
        daemon=True,
    ).start()
    _send_event_notification(
        "schedule_run",
        f"🚀 自動公開開始 [{job.title}] (job: {job.id} → pair: {pair_job_id})",
    )


def _start_single_main_publish(
    *,
    job,
    main_video: str,
    main_thumb: Optional[str],
    main_desc_file: Optional[str],
    publish_settings: Dict[str, Any],
    youtube_channel_id: Optional[str],
    tags: List[str],
    category_id: str,
    publish_at: Optional[str] = None,
) -> None:
    """ショート不在ジョブの fallback: メイン単体を公開（publish_at 指定時はスケジュール公開）。"""
    try:
        from pipeline import youtube_pair_publisher as pair_pub
        from googleapiclient.discovery import build
        from pipeline import youtube_oauth as yt_oauth
    except Exception as e:
        _send_event_notification("error", f"⚠️ 自動公開失敗 ({job.id}): {e}")
        return

    creds = yt_oauth.get_credentials_for(job.channel_id) or yt_oauth.get_credentials()
    if not creds:
        _send_event_notification("error", f"⚠️ 自動公開失敗 ({job.id}): 未連携")
        return

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    main_d = pair_pub._read_desc(main_desc_file)
    privacy = publish_settings.get("default_privacy") or "public"

    def _do():
        try:
            res = pair_pub._upload_one(
                youtube,
                video_path=main_video,
                title=main_d.get("title") or job.title,
                description=main_d.get("body") or "",
                tags=[t.lstrip("#") for t in (tags or [])],
                category_id=category_id or "27",
                privacy=privacy,
                is_short=False,
                youtube_channel_id=youtube_channel_id,
                publish_at=publish_at,
                thumbnail_path=main_thumb,
            )
            _send_event_notification(
                "upload_done",
                f"🚀 メイン自動公開完了 [{job.title}]: {res.get('url')}",
            )
        except Exception as e:
            _send_event_notification("error", f"⚠️ 自動公開失敗 ({job.id}): {e}")

    threading.Thread(target=_do, daemon=True).start()


def _run_schedule(schedule_id: str) -> None:
    """スケジュール発火: シナリオ生成→キュー投入→必要なら自動投稿。"""
    s = _get_schedule(schedule_id)
    if not s:
        return
    cm = _state.get("channel_manager")
    sg = _state.get("scenario_generator")
    queue = _state.get("job_queue")
    now = datetime.now().isoformat()

    def _update_run(status: str, job_id: Optional[str]) -> None:
        with _db_lock:
            conn = _db()
            try:
                conn.execute(
                    "UPDATE schedules SET last_run_at=?, last_run_status=?, last_run_job_id=? WHERE id=?",
                    (now, status, job_id, schedule_id),
                )
                conn.commit()
            finally:
                conn.close()

    if not (cm and sg and queue):
        _update_run("failed:not_initialized", None)
        _send_event_notification("error", f"スケジュール『{s['name']}』失敗: pipeline 未初期化")
        return

    ch = cm.get(s["channel_id"])
    if not ch:
        _update_run("failed:channel_not_found", None)
        _send_event_notification("error", f"スケジュール『{s['name']}』失敗: チャンネル {s['channel_id']} なし")
        return
    if not getattr(sg, "api_key", None):
        _update_run("failed:no_api_key", None)
        _send_event_notification("error", f"スケジュール『{s['name']}』失敗: OpenAI APIキー未設定")
        return

    try:
        theme_override = None
        if s["theme_mode"] == "manual" and s.get("theme"):
            theme_override = {"title": s["theme"], "angle": "スケジュール指定テーマ"}
        scenario = sg.generate(
            ch,
            theme_override=theme_override,
            target_duration=max(60, s["duration_minutes"] * 60),
        )
        try:
            sg.save_scenario(scenario)
        except Exception:
            pass
        job_id = queue.submit(
            channel_id=s["channel_id"],
            scenario_data=scenario,
            priority=5,
            gen_type="both",
        )
        _attach_auto_publish_marker(
            queue,
            job_id,
            schedule_id,
            s["auto_publish"],
            publish_offset_minutes=s.get("publish_offset_minutes"),
        )
        _update_run("queued", job_id)
        _send_event_notification(
            "schedule_run",
            f"スケジュール『{s['name']}』実行開始: {scenario.get('title', '')} (job: {job_id})",
        )
    except Exception as e:
        _update_run(f"failed:{str(e)[:120]}", None)
        _send_event_notification("error", f"スケジュール『{s['name']}』失敗: {e}")


@router.get("/schedules")
async def list_schedules(_=Depends(require_session)) -> Dict[str, Any]:
    items = _list_schedules()
    for it in items:
        it["next_run_at"] = _next_run_at(it["id"])
    return {"schedules": items, "scheduler_available": HAS_APSCHEDULER}


@router.get("/scheduler/jobs")
async def list_scheduler_jobs(_=Depends(require_session)) -> Dict[str, Any]:
    """診断用: APScheduler に現在登録されている全ジョブを返す。

    「autopilot 設定したのに動かない」という時の一次切り分けに使う。
    `sched:*` は /api/schedules 由来、`autopilot:*` は per-channel autopilot。
    リストが空、または期待した autopilot:<channel_id> がいない場合は、
    設定が保存されていない or restore に失敗した可能性が高い。
    """
    if not HAS_APSCHEDULER:
        return {"scheduler_available": False, "jobs": []}
    sch = _ensure_scheduler()
    if sch is None:
        return {"scheduler_available": False, "jobs": []}
    jobs_out: List[Dict[str, Any]] = []
    try:
        for j in sch.get_jobs():
            jobs_out.append({
                "id": j.id,
                "name": j.name,
                "next_run_at": j.next_run_time.isoformat() if j.next_run_time else None,
                "trigger": str(j.trigger),
                "kind": (
                    "autopilot" if j.id.startswith("autopilot:")
                    else "schedule" if j.id.startswith("sched:")
                    else "other"
                ),
            })
    except Exception as e:
        return {"scheduler_available": True, "jobs": [], "error": str(e)}
    return {
        "scheduler_available": True,
        "running": getattr(sch, "running", None),
        "jobs": jobs_out,
    }


@router.post("/schedules", status_code=201)
async def create_schedule(req: ScheduleIn, _=Depends(require_session)) -> Dict[str, Any]:
    sid = "sch_" + uuid.uuid4().hex[:10]
    created = datetime.now().isoformat()
    item = _save_schedule(req, sid, created)
    item["next_run_at"] = _next_run_at(sid)
    return item


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str, req: ScheduleIn, _=Depends(require_session)
) -> Dict[str, Any]:
    existing = _get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    item = _save_schedule(req, schedule_id, existing["created_at"])
    item["next_run_at"] = _next_run_at(schedule_id)
    return item


class ScheduleToggleRequest(BaseModel):
    enabled: bool


@router.patch("/schedules/{schedule_id}/toggle")
async def toggle_schedule(
    schedule_id: str, req: ScheduleToggleRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    existing = _get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    now = datetime.now().isoformat()
    with _db_lock:
        conn = _db()
        try:
            conn.execute(
                "UPDATE schedules SET enabled=?, updated_at=? WHERE id=?",
                (1 if req.enabled else 0, now, schedule_id),
            )
            conn.commit()
        finally:
            conn.close()
    _refresh_scheduler_job(schedule_id)
    item = _get_schedule(schedule_id)
    if item:
        item["next_run_at"] = _next_run_at(schedule_id)
    return item or {}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, _=Depends(require_session)) -> Dict[str, str]:
    if not _delete_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted"}


@router.get("/schedules/upcoming")
async def upcoming_schedules(
    limit: int = 10, _=Depends(require_session)
) -> Dict[str, Any]:
    """次回実行予定（先 N 件）"""
    items: List[Dict[str, Any]] = []
    for s in _list_schedules():
        if not s["enabled"]:
            continue
        nxt = _next_run_at(s["id"])
        if not nxt:
            continue
        items.append({
            "id": s["id"],
            "name": s["name"],
            "channel_id": s["channel_id"],
            "next_run_at": nxt,
            "theme_mode": s["theme_mode"],
            "theme": s.get("theme"),
        })
    items.sort(key=lambda x: x["next_run_at"])
    return {"upcoming": items[:limit]}


@router.post("/schedules/{schedule_id}/run-now")
async def run_schedule_now(schedule_id: str, _=Depends(require_session)) -> Dict[str, str]:
    """テスト実行: 即座に1回発火"""
    if not _get_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    threading.Thread(target=_run_schedule, args=(schedule_id,), daemon=True).start()
    return {"status": "triggered"}


# =====================================================================
# 2. 動画テンプレート
# =====================================================================

def _ensure_templates_dir() -> Path:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return TEMPLATES_DIR


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    channel_id: str = Field(min_length=1)
    theme: Optional[str] = ""
    duration_minutes: int = Field(default=12, ge=1, le=60)
    generate_short: bool = True
    generate_thumbnail: bool = True
    copy_to_icloud: bool = False
    ab_test: bool = False
    notes: Optional[str] = ""


class TemplateOut(TemplateIn):
    id: str
    created_at: str
    updated_at: str


def _template_path(template_id: str) -> Path:
    safe = "".join(c for c in template_id if c.isalnum() or c in "_-")[:64]
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid template id")
    return _ensure_templates_dir() / f"{safe}.json"


def _read_template(p: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/templates")
async def list_templates(_=Depends(require_session)) -> Dict[str, Any]:
    base = _ensure_templates_dir()
    out: List[Dict[str, Any]] = []
    for f in sorted(base.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        data = _read_template(f)
        if data:
            out.append(data)
    return {"templates": out}


@router.post("/templates", status_code=201)
async def create_template(req: TemplateIn, _=Depends(require_session)) -> Dict[str, Any]:
    tid = "tpl_" + uuid.uuid4().hex[:10]
    now = datetime.now().isoformat()
    payload = {**req.dict(), "id": tid, "created_at": now, "updated_at": now}
    _template_path(tid).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str, req: TemplateIn, _=Depends(require_session)
) -> Dict[str, Any]:
    p = _template_path(template_id)
    existing = _read_template(p)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    now = datetime.now().isoformat()
    payload = {
        **req.dict(),
        "id": template_id,
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, _=Depends(require_session)) -> Dict[str, str]:
    p = _template_path(template_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    p.unlink()
    return {"status": "deleted"}


# =====================================================================
# 3. 生成履歴・コスト管理
# =====================================================================

def _job_cost_estimate(events: List[Dict[str, Any]]) -> float:
    """API使用ログから推定（USD）"""
    return round(sum(e.get("cost_usd", 0.0) for e in events), 4)


def _job_duration_seconds(j: Dict[str, Any]) -> Optional[float]:
    s = j.get("started_at")
    e = j.get("completed_at")
    if not s or not e:
        return None
    try:
        return (datetime.fromisoformat(e) - datetime.fromisoformat(s)).total_seconds()
    except Exception:
        return None


def _list_all_jobs() -> List[Dict[str, Any]]:
    queue = _state.get("job_queue")
    if not queue:
        return []
    try:
        return queue.list_jobs()
    except Exception:
        return []


@router.get("/history")
async def list_history(
    channel_id: Optional[str] = None,
    status: Optional[str] = None,
    since: Optional[str] = None,   # YYYY-MM-DD
    until: Optional[str] = None,
    limit: int = 200,
    _=Depends(require_session),
) -> Dict[str, Any]:
    """全生成ジョブの履歴一覧（推定コスト付き）"""
    jobs = _list_all_jobs()
    # 安全に絞り込み
    out: List[Dict[str, Any]] = []
    for j in jobs:
        if channel_id and j.get("channel_id") != channel_id:
            continue
        if status and j.get("status") != status:
            continue
        ts = (j.get("created_at") or "")[:10]
        if since and ts and ts < since:
            continue
        if until and ts and ts > until:
            continue
        out.append({
            "job_id": j.get("id"),
            "channel_id": j.get("channel_id"),
            "title": j.get("title"),
            "status": j.get("status"),
            "created_at": j.get("created_at"),
            "started_at": j.get("started_at"),
            "completed_at": j.get("completed_at"),
            "duration_seconds": _job_duration_seconds(j),
            "error": j.get("error"),
        })
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"history": out[:limit], "total": len(out)}


@router.get("/history/cost-summary")
async def cost_summary(_=Depends(require_session)) -> Dict[str, Any]:
    """月別コスト + チャンネル別 + 全体集計（既存 api_usage を再加工）"""
    try:
        from pipeline import api_usage as au
        summary = au.get_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Usage tracker error: {e}")

    # by_day → by_month に集計（フロントの月別チャート用）
    by_month: Dict[str, Dict[str, float]] = {}
    for day, m in (summary.get("by_day") or {}).items():
        month = day[:7]  # YYYY-MM
        slot = by_month.setdefault(month, {"calls": 0, "cost_usd": 0.0, "images": 0})
        slot["calls"] += m.get("calls", 0)
        slot["cost_usd"] = round(slot["cost_usd"] + m.get("cost_usd", 0.0), 4)
        slot["images"] += m.get("images", 0)
    months = sorted(by_month.keys(), reverse=True)

    # 日別を直近14日分の昇順配列に整形（フロントの日次チャート用）
    by_day_map = summary.get("by_day") or {}
    by_day_sorted = sorted(by_day_map.keys())[-14:]
    by_day_series = [
        {
            "date": d,
            "calls": by_day_map[d].get("calls", 0),
            "cost_usd": by_day_map[d].get("cost_usd", 0.0),
            "images": by_day_map[d].get("images", 0),
        }
        for d in by_day_sorted
    ]

    return {
        "total": summary.get("total"),
        "today": summary.get("today"),
        "this_month": summary.get("this_month"),
        "by_month": [{"month": m, **by_month[m]} for m in months],
        "by_day": by_day_series,
        "by_channel": summary.get("by_channel"),
        "by_model": summary.get("by_model"),
        "by_provider": summary.get("by_provider"),
        "by_purpose": summary.get("by_purpose"),
        "pricing": summary.get("pricing"),
    }


# =====================================================================
# 4. A/Bテスト（サムネ/タイトル複数パターン）
# =====================================================================

class ABGenerateRequest(BaseModel):
    job_id: str = Field(min_length=1)
    title_count: int = Field(default=3, ge=1, le=5)
    thumbnail_count: int = Field(default=3, ge=1, le=5)


def _record_variants(
    job_id: str, kind: str, contents: List[str]
) -> List[Dict[str, Any]]:
    now = datetime.now().isoformat()
    saved: List[Dict[str, Any]] = []
    with _db_lock:
        conn = _db()
        try:
            # 既存の同 kind を消す
            conn.execute(
                "DELETE FROM ab_variants WHERE job_id = ? AND kind = ?", (job_id, kind)
            )
            for i, c in enumerate(contents):
                vid = "var_" + uuid.uuid4().hex[:10]
                conn.execute(
                    "INSERT INTO ab_variants (id, job_id, kind, variant_index, content, selected, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?)",
                    (vid, job_id, kind, i, c, now),
                )
                saved.append({
                    "id": vid, "job_id": job_id, "kind": kind,
                    "variant_index": i, "content": c, "selected": False,
                    "created_at": now,
                })
            conn.commit()
        finally:
            conn.close()
    return saved


def _list_variants(job_id: str) -> Dict[str, List[Dict[str, Any]]]:
    with _db_lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM ab_variants WHERE job_id = ? ORDER BY kind, variant_index",
                (job_id,),
            ).fetchall()
        finally:
            conn.close()
    out: Dict[str, List[Dict[str, Any]]] = {"title": [], "thumbnail": []}
    for r in rows:
        d = dict(r)
        d["selected"] = bool(d["selected"])
        out.setdefault(d["kind"], []).append(d)
    return out


@router.post("/videos/{job_id}/ab-generate")
async def ab_generate(
    job_id: str, req: ABGenerateRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    """既存ジョブに対して、タイトル/サムネを複数パターン生成して保存。

    動画本体には影響しない。フロントで採用パターンを選んだあと、
    通常の publish フローで title/thumbnail を差し替えて使う。
    """
    queue = _state.get("job_queue")
    if not queue:
        raise HTTPException(status_code=503, detail="Job queue not ready")
    j = queue.get_status(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")

    base_title = j.get("title") or "(untitled)"

    # ── タイトル ──
    titles: List[str] = []
    try:
        from pipeline.title_generator import generate_titles
        scenario_text = ""
        try:
            scenario_text = json.dumps(j.get("scenario_data") or {}, ensure_ascii=False)[:4000]
        except Exception:
            pass
        titles = generate_titles(scenario_text or base_title, num_suggestions=req.title_count) or []
    except Exception as e:
        # フォールバック: バリエーションを軽く作る
        titles = [base_title] + [f"{base_title}（パターン{i+1}）" for i in range(req.title_count - 1)]
    titles = titles[: req.title_count]

    # ── サムネ ──
    # DALL-E を呼ぶと高コストになるため、まずは「サムネ生成プロンプト」のバリエーションをテキストで作る。
    # 実画像生成は採用パターン決定後に行う想定（今回は記録のみ）。
    thumb_prompts: List[str] = []
    try:
        # 既存サムネがあれば1枚目に
        result = j.get("result") or {}
        existing_thumb = result.get("thumbnail_path") if isinstance(result, dict) else None
        if existing_thumb:
            thumb_prompts.append(str(existing_thumb))
        # 残りはバリエーション説明テキスト（フロントで「案」として表示）
        styles = ["インパクト強め・赤背景", "やわらかい・パステル", "クール・青基調", "ミニマル・白背景", "ドラマチック・写真風"]
        for i in range(req.thumbnail_count - len(thumb_prompts)):
            thumb_prompts.append(f"案{i+1}: {styles[i % len(styles)]} — 「{base_title}」")
    except Exception:
        thumb_prompts = [f"案{i+1}: 「{base_title}」" for i in range(req.thumbnail_count)]
    thumb_prompts = thumb_prompts[: req.thumbnail_count]

    title_variants = _record_variants(job_id, "title", titles)
    thumb_variants = _record_variants(job_id, "thumbnail", thumb_prompts)

    return {
        "status": "generated",
        "job_id": job_id,
        "title": title_variants,
        "thumbnail": thumb_variants,
    }


@router.get("/videos/{job_id}/variants")
async def get_variants(job_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    return {"job_id": job_id, "variants": _list_variants(job_id)}


class SelectVariantRequest(BaseModel):
    variant_id: str


@router.post("/videos/{job_id}/variants/select")
async def select_variant(
    job_id: str, req: SelectVariantRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    """採用パターンを決定（同 kind 内の他は selected=0）"""
    with _db_lock:
        conn = _db()
        try:
            row = conn.execute(
                "SELECT kind FROM ab_variants WHERE id = ? AND job_id = ?",
                (req.variant_id, job_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Variant not found")
            kind = row["kind"]
            conn.execute(
                "UPDATE ab_variants SET selected = 0 WHERE job_id = ? AND kind = ?",
                (job_id, kind),
            )
            conn.execute(
                "UPDATE ab_variants SET selected = 1 WHERE id = ?", (req.variant_id,)
            )
            conn.commit()
        finally:
            conn.close()
    return {"status": "selected", "variant_id": req.variant_id, "kind": kind}


# =====================================================================
# 5. 通知 (LINE Notify / Slack Webhook / SMTP)
# =====================================================================

class NotificationSettingsIn(BaseModel):
    line_token: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_to: Optional[str] = None
    notify_on_generate_done: bool = True
    notify_on_upload_done: bool = True
    notify_on_schedule_run: bool = True
    notify_on_error: bool = True


def _mask(s: Optional[str], head: int = 4) -> str:
    if not s:
        return ""
    if len(s) <= head + 4:
        return "***"
    return f"{s[:head]}...{s[-3:]}"


def _get_notification_settings_row() -> Optional[sqlite3.Row]:
    with _db_lock:
        conn = _db()
        try:
            return conn.execute(
                "SELECT * FROM notification_settings WHERE id = 1"
            ).fetchone()
        finally:
            conn.close()


def _save_notification_settings(s: NotificationSettingsIn) -> None:
    now = datetime.now().isoformat()
    with _db_lock:
        conn = _db()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO notification_settings
                (id, line_token, slack_webhook_url, smtp_host, smtp_port,
                 smtp_user, smtp_password, smtp_from, smtp_to,
                 notify_on_generate_done, notify_on_upload_done,
                 notify_on_schedule_run, notify_on_error, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s.line_token, s.slack_webhook_url,
                    s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password,
                    s.smtp_from, s.smtp_to,
                    1 if s.notify_on_generate_done else 0,
                    1 if s.notify_on_upload_done else 0,
                    1 if s.notify_on_schedule_run else 0,
                    1 if s.notify_on_error else 0,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()


@router.get("/settings/notifications")
async def get_notification_settings(_=Depends(require_session)) -> Dict[str, Any]:
    row = _get_notification_settings_row()
    if not row:
        return {
            "configured": False,
            "line_token_preview": "",
            "slack_webhook_preview": "",
            "smtp_host": "",
            "smtp_port": None,
            "smtp_user": "",
            "smtp_from": "",
            "smtp_to": "",
            "notify_on_generate_done": True,
            "notify_on_upload_done": True,
            "notify_on_schedule_run": True,
            "notify_on_error": True,
        }
    d = dict(row)
    return {
        "configured": True,
        "line_token_preview": _mask(d.get("line_token")),
        "line_token_set": bool(d.get("line_token")),
        "slack_webhook_preview": _mask(d.get("slack_webhook_url"), head=20),
        "slack_webhook_set": bool(d.get("slack_webhook_url")),
        "smtp_host": d.get("smtp_host") or "",
        "smtp_port": d.get("smtp_port"),
        "smtp_user": d.get("smtp_user") or "",
        "smtp_password_set": bool(d.get("smtp_password")),
        "smtp_from": d.get("smtp_from") or "",
        "smtp_to": d.get("smtp_to") or "",
        "notify_on_generate_done": bool(d.get("notify_on_generate_done")),
        "notify_on_upload_done": bool(d.get("notify_on_upload_done")),
        "notify_on_schedule_run": bool(d.get("notify_on_schedule_run")),
        "notify_on_error": bool(d.get("notify_on_error")),
        "updated_at": d.get("updated_at"),
    }


@router.put("/settings/notifications")
async def update_notification_settings(
    req: NotificationSettingsIn, _=Depends(require_session)
) -> Dict[str, Any]:
    # 既存値を保持しつつ、空文字 / None は「変更なし」扱い
    existing = _get_notification_settings_row()
    if existing:
        e = dict(existing)
        merged = NotificationSettingsIn(
            line_token=req.line_token if req.line_token is not None and req.line_token != "" else e.get("line_token"),
            slack_webhook_url=req.slack_webhook_url if req.slack_webhook_url is not None and req.slack_webhook_url != "" else e.get("slack_webhook_url"),
            smtp_host=req.smtp_host if req.smtp_host is not None else e.get("smtp_host"),
            smtp_port=req.smtp_port if req.smtp_port is not None else e.get("smtp_port"),
            smtp_user=req.smtp_user if req.smtp_user is not None else e.get("smtp_user"),
            smtp_password=req.smtp_password if req.smtp_password is not None and req.smtp_password != "" else e.get("smtp_password"),
            smtp_from=req.smtp_from if req.smtp_from is not None else e.get("smtp_from"),
            smtp_to=req.smtp_to if req.smtp_to is not None else e.get("smtp_to"),
            notify_on_generate_done=req.notify_on_generate_done,
            notify_on_upload_done=req.notify_on_upload_done,
            notify_on_schedule_run=req.notify_on_schedule_run,
            notify_on_error=req.notify_on_error,
        )
        _save_notification_settings(merged)
    else:
        _save_notification_settings(req)
    return {"status": "ok"}


def _send_line(token: str, message: str) -> Dict[str, Any]:
    data = urllib.parse.urlencode({"message": message[:900]}).encode("utf-8")
    req = urllib.request.Request(
        "https://notify-api.line.me/api/notify",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return {"channel": "line", "status": r.status, "ok": 200 <= r.status < 300}


def _send_slack(webhook: str, message: str) -> Dict[str, Any]:
    body = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return {"channel": "slack", "status": r.status, "ok": 200 <= r.status < 300}


def _send_email(host: str, port: int, user: Optional[str], password: Optional[str],
                sender: str, recipient: str, subject: str, body: str) -> Dict[str, Any]:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)
    use_tls = (port == 465)
    if use_tls:
        with smtplib.SMTP_SSL(host, port, timeout=10) as s:
            if user and password:
                s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port or 587, timeout=10) as s:
            try:
                s.starttls()
            except Exception:
                pass
            if user and password:
                s.login(user, password)
            s.send_message(msg)
    return {"channel": "email", "ok": True}


def _dispatch_notification(message: str, subject: str = "YouTube Factory") -> List[Dict[str, Any]]:
    """設定済みの全チャンネルに送信。例外はチャンネル単位で握りつぶす。"""
    row = _get_notification_settings_row()
    if not row:
        return []
    d = dict(row)
    results: List[Dict[str, Any]] = []
    if d.get("line_token"):
        try:
            results.append(_send_line(d["line_token"], message))
        except Exception as e:
            results.append({"channel": "line", "ok": False, "error": str(e)})
    if d.get("slack_webhook_url"):
        try:
            results.append(_send_slack(d["slack_webhook_url"], message))
        except Exception as e:
            results.append({"channel": "slack", "ok": False, "error": str(e)})
    if d.get("smtp_host") and d.get("smtp_to") and d.get("smtp_from"):
        try:
            results.append(_send_email(
                d["smtp_host"], int(d.get("smtp_port") or 587),
                d.get("smtp_user"), d.get("smtp_password"),
                d["smtp_from"], d["smtp_to"], subject, message,
            ))
        except Exception as e:
            results.append({"channel": "email", "ok": False, "error": str(e)})
    return results


def _send_event_notification(event: str, message: str) -> None:
    """イベント種別ごとに on_xxx フラグをチェックしてから送信。スレッドセーフ。

    通知チャンネル (LINE/Slack/Email) を設定していなくても、診断用に
    すべてのイベントを backend.log にエコーする。Autopilot/Schedule が
    本当に発火したか・成功したかをユーザーが確認できるようにするため。
    """
    # 通知設定 (LINE/Slack/Email) があってもなくても、まず stdout に残す
    icon = {"generate_done": "🎬", "upload_done": "🚀", "schedule_run": "📅", "error": "⚠️"}.get(event, "ℹ️")
    print(f"{icon} [{event}] {message}")
    row = _get_notification_settings_row()
    if not row:
        return
    d = dict(row)
    flag_map = {
        "generate_done": d.get("notify_on_generate_done", 1),
        "upload_done": d.get("notify_on_upload_done", 1),
        "schedule_run": d.get("notify_on_schedule_run", 1),
        "error": d.get("notify_on_error", 1),
    }
    if not flag_map.get(event, 1):
        return
    try:
        _dispatch_notification(message)
    except Exception as e:
        print(f"⚠️ Notification dispatch failed: {e}")


class TestNotificationRequest(BaseModel):
    channel: Optional[str] = None  # 'line' | 'slack' | 'email' | None=all
    message: Optional[str] = None


@router.post("/notifications/test")
async def test_notification(
    req: TestNotificationRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    msg = req.message or "🎬 YouTube Factory: 通知テストです"
    row = _get_notification_settings_row()
    if not row:
        raise HTTPException(status_code=400, detail="通知設定が未保存です")
    d = dict(row)

    results: List[Dict[str, Any]] = []
    target = req.channel
    if target in (None, "line") and d.get("line_token"):
        try:
            results.append(_send_line(d["line_token"], msg))
        except Exception as e:
            results.append({"channel": "line", "ok": False, "error": str(e)})
    if target in (None, "slack") and d.get("slack_webhook_url"):
        try:
            results.append(_send_slack(d["slack_webhook_url"], msg))
        except Exception as e:
            results.append({"channel": "slack", "ok": False, "error": str(e)})
    if target in (None, "email") and d.get("smtp_host") and d.get("smtp_to") and d.get("smtp_from"):
        try:
            results.append(_send_email(
                d["smtp_host"], int(d.get("smtp_port") or 587),
                d.get("smtp_user"), d.get("smtp_password"),
                d["smtp_from"], d["smtp_to"],
                "[YouTube Factory] テスト通知", msg,
            ))
        except Exception as e:
            results.append({"channel": "email", "ok": False, "error": str(e)})
    if not results:
        raise HTTPException(status_code=400, detail="送信可能なチャンネルが設定されていません")
    return {"status": "ok", "results": results}


# =====================================================================
# 起動時セットアップ（main.py から呼ぶ）
# =====================================================================

def setup_on_startup() -> None:
    """main.py の startup から呼ぶ。スケジューラ起動 + 既存スケジュールの復元。"""
    if not HAS_APSCHEDULER:
        print("⚠️ APScheduler 未インストール — /api/schedules は使用不可")
        return
    _ensure_scheduler()
    _restore_all_schedules()
    _register_thumbnail_ab_check_job()
    _register_trend_scanner_job()
    _register_competitor_scan_job()
    _register_competitor_discovery_job()
    print(f"⏰ Scheduler started — {len(_list_schedules())} schedule(s) restored")


def _register_thumbnail_ab_check_job() -> None:
    """サムネ AB テストの定期チェックジョブ（1h ごと）を登録。"""
    sch = _ensure_scheduler()
    if sch is None:
        return
    try:
        from pipeline.analytics import thumbnail_ab_test  # type: ignore
    except Exception as e:
        print(f"⚠️ thumbnail_ab_test import failed: {e}")
        return
    job_id = "thumbnail_ab_test:check_all"
    try:
        sch.remove_job(job_id)
    except Exception:
        pass

    def _runner() -> None:
        try:
            res = thumbnail_ab_test.check_pending()
            checked = res.get("checked", 0)
            if checked:
                print(f"🖼️ Thumbnail AB check: {checked} test(s) evaluated")
        except Exception as e:
            print(f"⚠️ thumbnail_ab_test.check_pending failed: {e}")

    try:
        trigger = CronTrigger(minute=0, timezone="Asia/Tokyo")  # 毎時 0 分
        sch.add_job(_runner, trigger=trigger, id=job_id, replace_existing=True)
        print("🖼️ Thumbnail AB test periodic check scheduled (every hour)")
    except Exception as e:
        print(f"⚠️ Failed to register thumbnail AB check job: {e}")


def _register_trend_scanner_job() -> None:
    """トレンドスキャンの定期実行ジョブ（6h ごと）を登録。"""
    sch = _ensure_scheduler()
    if sch is None:
        return
    try:
        from pipeline.analytics import trend_scanner  # type: ignore
    except Exception as e:
        print(f"⚠️ trend_scanner import failed: {e}")
        return
    job_id = "trend_scanner:scan_all"
    try:
        sch.remove_job(job_id)
    except Exception:
        pass

    def _runner() -> None:
        try:
            res = trend_scanner.scan_all_channels(auto_queue=True)
            if res.get("ok"):
                total_detected = sum(
                    int(r.get("detected", 0) or 0) for r in (res.get("results") or [])
                )
                total_queued = sum(
                    int(r.get("auto_queued", 0) or 0) for r in (res.get("results") or [])
                )
                print(
                    f"🔭 Trend scan: {total_detected} detected, "
                    f"{total_queued} auto-queued across {len(res.get('results') or [])} channel(s)"
                )
            else:
                print(f"⚠️ Trend scan failed: {res.get('error')}")
        except Exception as e:
            print(f"⚠️ trend_scanner.scan_all_channels failed: {e}")

    try:
        # 6 時間ごと（JST 0:30, 6:30, 12:30, 18:30）
        trigger = CronTrigger(hour="0,6,12,18", minute=30, timezone="Asia/Tokyo")
        sch.add_job(_runner, trigger=trigger, id=job_id, replace_existing=True)
        print("🔭 Trend scanner periodic scan scheduled (every 6 hours)")
    except Exception as e:
        print(f"⚠️ Failed to register trend scanner job: {e}")


def _register_competitor_scan_job() -> None:
    """競合チャンネル分析の週次ジョブ（日曜深夜 JST 03:00）を登録。"""
    sch = _ensure_scheduler()
    if sch is None:
        return
    try:
        from pipeline.analytics import competitor_analyzer  # type: ignore
    except Exception as e:
        print(f"⚠️ competitor_analyzer import failed: {e}")
        return
    job_id = "competitor_analyzer:scan_all"
    try:
        sch.remove_job(job_id)
    except Exception:
        pass

    def _runner() -> None:
        try:
            res = competitor_analyzer.scan_all_channels()
            if res.get("ok"):
                total = sum(int(r.get("count") or 0) for r in (res.get("results") or []))
                print(
                    f"🕵️ Competitor scan: {total} competitor(s) analyzed across "
                    f"{len(res.get('results') or [])} channel(s)"
                )
            else:
                print(f"⚠️ Competitor scan failed: {res.get('error')}")
        except Exception as e:
            print(f"⚠️ competitor_analyzer.scan_all_channels failed: {e}")

    try:
        # 毎週日曜 03:00 JST（深夜）
        trigger = CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="Asia/Tokyo")
        sch.add_job(_runner, trigger=trigger, id=job_id, replace_existing=True)
        print("🕵️ Competitor analyzer weekly scan scheduled (Sun 03:00 JST)")
    except Exception as e:
        print(f"⚠️ Failed to register competitor scan job: {e}")


def _register_competitor_discovery_job() -> None:
    """競合チャンネル自動検出の月次ジョブ（毎月 1 日 04:00 JST）を登録。"""
    sch = _ensure_scheduler()
    if sch is None:
        return
    try:
        from pipeline.analytics import competitor_discovery  # type: ignore
    except Exception as e:
        print(f"⚠️ competitor_discovery import failed: {e}")
        return
    job_id = "competitor_discovery:discover_all"
    try:
        sch.remove_job(job_id)
    except Exception:
        pass

    def _runner() -> None:
        try:
            res = competitor_discovery.discover_all_channels()
            if res.get("ok"):
                total = sum(int(r.get("count") or 0) for r in (res.get("results") or []))
                print(
                    f"🔎 Competitor discovery: {total} candidate(s) detected across "
                    f"{len(res.get('results') or [])} channel(s)"
                )
            else:
                print(f"⚠️ Competitor discovery failed: {res.get('error')}")
        except Exception as e:
            print(f"⚠️ competitor_discovery.discover_all_channels failed: {e}")

    try:
        # 毎月 1 日 04:00 JST
        trigger = CronTrigger(day=1, hour=4, minute=0, timezone="Asia/Tokyo")
        sch.add_job(_runner, trigger=trigger, id=job_id, replace_existing=True)
        print("🔎 Competitor discovery monthly scan scheduled (1st of month 04:00 JST)")
    except Exception as e:
        print(f"⚠️ Failed to register competitor discovery job: {e}")


def shutdown_scheduler() -> None:
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass


# 公開ヘルパ（他モジュールから通知送信したい場合用）
def notify_event(event: str, message: str) -> None:
    """外部モジュールから呼び出し可能な通知関数。"""
    _send_event_notification(event, message)
