"""
Channel Autopilot — per-channel フルオート自動投稿

api_phase4 のスケジューラ（APScheduler BackgroundScheduler）に相乗りで、
チャンネル単位の自動投稿ジョブを登録する。

データはチャンネル JSON (data/channels/{id}.json) の `autopilot` セクションに
永続化され、channel_manager 経由で読み書きする。

スキーマ:
    "autopilot": {
        "enabled": false,
        "schedule": {
            "days_of_week": [1, 3, 5],   # 0=sun..6=sat
            "hour": 18,                  # 単一スロット用 (times未指定時のレガシー)
            "minute": 0,
            "times": [                   # 1日複数スロットを使う場合はこちら
                {"hour": 7,  "minute": 0},
                {"hour": 17, "minute": 0}
            ]
        },
        "duration_minutes": 12,
        "gen_type": "both",             # "both" | "short" | "full"
        "theme_queue": [
            {"id": "abc12345", "title": "...", "angle": "..."},
            ...
        ]
    }

発火フロー:
    1. キュー先頭からテーマを取り出す
    2. 空なら ScenarioGenerator.suggest_themes でAI補充
    3. ScenarioGenerator.generate でシナリオ生成 → JobQueue 投入
    4. _attach_auto_publish_marker でフラグ付与 → 完了時に YouTube ペア公開
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_phase1 import _state, require_session
import api_phase4
from channels.config_validation import get_default_privacy


router = APIRouter(prefix="/api/channels", tags=["autopilot"])

# 同時編集ガード
_lock = threading.Lock()

# JST 曜日マップ (フロントは sun=0 ... sat=6 を使う) — api_phase4 と同じ
DOW_NAMES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]


# =====================================================================
# Pydantic models
# =====================================================================

class TimeSlot(BaseModel):
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    # このスロットだけ別の曜日で回したい場合に指定 (0=sun..6=sat)。
    # 未指定なら schedule.days_of_week を継承する。
    days_of_week: Optional[List[int]] = None


class ScheduleSpec(BaseModel):
    days_of_week: List[int] = Field(default_factory=list)  # 0=sun..6=sat
    hour: int = Field(default=18, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    # 1日複数回投稿する場合に使う。指定されていれば hour/minute より優先する。
    times: Optional[List[TimeSlot]] = None


class ThemeItem(BaseModel):
    id: Optional[str] = None
    title: str = Field(min_length=1)
    angle: Optional[str] = ""


# pipeline/scheduler/job_queue.submit に渡される gen_type の許容値。
# "clip" だけは台本生成を伴わない別系統で、JobQueue ではなく clip_factory が処理する。
GEN_TYPE_CHOICES = ("both", "short", "full", "clip")
CLIP_GEN_TYPE = "clip"


class AutopilotConfig(BaseModel):
    enabled: bool = False
    schedule: ScheduleSpec = Field(default_factory=ScheduleSpec)
    duration_minutes: int = Field(default=12, ge=1, le=60)
    gen_type: str = Field(default="both")
    theme_queue: List[ThemeItem] = Field(default_factory=list)


class AutopilotUpdate(BaseModel):
    enabled: Optional[bool] = None
    schedule: Optional[ScheduleSpec] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=60)
    gen_type: Optional[str] = None


class ThemeAdd(BaseModel):
    title: str = Field(min_length=1)
    angle: Optional[str] = ""


class ThemeUpdate(BaseModel):
    title: Optional[str] = None
    angle: Optional[str] = None


class ThemeReorder(BaseModel):
    queue: List[ThemeItem]


class RefillRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=10)


# =====================================================================
# Channel JSON helpers
# =====================================================================

def _default_autopilot() -> Dict[str, Any]:
    return {
        "enabled": False,
        "schedule": {"days_of_week": [], "hour": 18, "minute": 0},
        "duration_minutes": 12,
        "gen_type": "both",
        "theme_queue": [],
    }


def _load_autopilot(channel_id: str) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_id}' not found")
    raw = (ch._raw.get("autopilot") if hasattr(ch, "_raw") else None) or {}
    merged = _default_autopilot()
    merged.update({k: v for k, v in raw.items() if v is not None})
    # 入れ子のスキーマも整える
    sched = dict(_default_autopilot()["schedule"])
    raw_sched = raw.get("schedule") or {}
    sched.update(raw_sched)
    # レガシー schedule フィールドのフォールバック (JSON を書き換えずに読み替え)
    # - schedule.days: ["mon","wed","fri"] → days_of_week: [1,3,5]
    # - schedule.time: "19:30"             → hour: 19, minute: 30
    if not sched.get("days_of_week") and raw_sched.get("days"):
        _name_to_idx = {n: i for i, n in enumerate(DOW_NAMES)}
        sched["days_of_week"] = [
            _name_to_idx[d.lower()]
            for d in raw_sched["days"]
            if isinstance(d, str) and d.lower() in _name_to_idx
        ]
    if isinstance(raw_sched.get("time"), str):
        try:
            _hh, _mm = raw_sched["time"].split(":", 1)
            sched["hour"] = int(_hh)
            sched["minute"] = int(_mm)
        except (ValueError, IndexError):
            pass
    # 複数時刻スロット (1日N回投稿)
    raw_times = raw_sched.get("times")
    if isinstance(raw_times, list):
        norm_times: List[Dict[str, int]] = []
        for t in raw_times:
            if not isinstance(t, dict):
                continue
            try:
                h = int(t.get("hour"))
                m = int(t.get("minute", 0))
            except (TypeError, ValueError):
                continue
            if 0 <= h <= 23 and 0 <= m <= 59:
                slot: Dict[str, Any] = {"hour": h, "minute": m}
                raw_days = t.get("days_of_week")
                if isinstance(raw_days, list):
                    days = sorted({int(d) for d in raw_days
                                   if isinstance(d, int) and 0 <= d <= 6})
                    if days:
                        slot["days_of_week"] = days
                norm_times.append(slot)
        if norm_times:
            sched["times"] = norm_times
    merged["schedule"] = sched
    # gen_type ("both" | "short" | "full")
    gt = raw.get("gen_type")
    if isinstance(gt, str) and gt in ("both", "short", "full"):
        merged["gen_type"] = gt
    else:
        merged.setdefault("gen_type", "both")
    queue = []
    for item in (raw.get("theme_queue") or []):
        if not isinstance(item, dict) or not item.get("title"):
            continue
        queue.append({
            "id": item.get("id") or _new_theme_id(),
            "title": str(item["title"]),
            "angle": str(item.get("angle") or ""),
        })
    merged["theme_queue"] = queue
    return merged


def _save_autopilot(channel_id: str, ap: Dict[str, Any]) -> Dict[str, Any]:
    cm = _state.get("channel_manager")
    if cm is None:
        raise HTTPException(status_code=503, detail="Channel manager not ready")
    ch = cm.get(channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_id}' not found")
    # チャンネル JSON にマージ保存
    raw = ch._raw.copy()
    raw["autopilot"] = ap
    file_path = cm._data_dir / f"{channel_id}.json"
    import json as _json
    file_path.write_text(_json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    cm.reload()
    # スケジューラを再同期
    _refresh_channel_job(channel_id)
    return ap


def _new_theme_id() -> str:
    return uuid.uuid4().hex[:8]


# =====================================================================
# Scheduler — api_phase4 の BackgroundScheduler を再利用
# =====================================================================

def _job_id(channel_id: str, slot: int = 0) -> str:
    """スロット付きジョブID。1日複数回投稿のために slot 番号でジョブを分ける。"""
    return f"autopilot:{channel_id}:{slot}"


def _iter_channel_jobs(sch, channel_id: str):
    """このチャンネルに紐づく全 autopilot ジョブを列挙 (新旧両方のID形式を拾う)。"""
    legacy = f"autopilot:{channel_id}"
    prefix = f"{legacy}:"
    for job in list(sch.get_jobs()):
        if job.id == legacy or job.id.startswith(prefix):
            yield job


def _resolve_time_slots(sched: Dict[str, Any]) -> List[Dict[str, Any]]:
    """schedule から発火時刻のリストを返す。times が空なら hour/minute を単一スロットとして扱う。

    各スロットは任意で `days_of_week`（0=sun..6=sat）を持てる。指定があればそのスロットは
    その曜日にだけ発火し、無ければ schedule 直下の days_of_week を使う。
    これにより「普段は18:00、木曜だけ10:00」のような曜日別の投稿枠を表現できる
    （PDCA レポートの実績ベスト枠を曜日単位で採用するため）。
    """
    times = sched.get("times")
    slots: List[Dict[str, Any]] = []
    if isinstance(times, list):
        for t in times:
            if not isinstance(t, dict):
                continue
            try:
                h = int(t.get("hour"))
                m = int(t.get("minute", 0))
            except (TypeError, ValueError):
                continue
            if not (0 <= h <= 23 and 0 <= m <= 59):
                continue
            slot: Dict[str, Any] = {"hour": h, "minute": m}
            raw_days = t.get("days_of_week")
            if isinstance(raw_days, list):
                days = sorted({
                    int(d) for d in raw_days
                    if isinstance(d, int) or (isinstance(d, str) and d.isdigit())
                    if 0 <= int(d) <= 6
                })
                if days:
                    slot["days_of_week"] = days
            slots.append(slot)
    if not slots:
        slots.append({
            "hour": int(sched.get("hour", 18)),
            "minute": int(sched.get("minute", 0)),
        })
    return slots


def _refresh_channel_job(channel_id: str) -> None:
    sch = api_phase4._ensure_scheduler()
    if sch is None:
        print(f"⚠️ Autopilot: APScheduler 未利用 — {channel_id} はスケジュール不能")
        return

    # 既存ジョブ (新旧ID両方) をクリーンアップ
    for job in _iter_channel_jobs(sch, channel_id):
        try:
            sch.remove_job(job.id)
        except Exception:
            pass

    ap = _load_autopilot(channel_id)
    if not ap.get("enabled"):
        print(f"🚫 Autopilot for {channel_id}: disabled (enabled=false)")
        return
    sched = ap.get("schedule") or {}
    days = sched.get("days_of_week") or []
    if not days:
        print(f"🚫 Autopilot for {channel_id}: 曜日未指定 — スケジュール登録スキップ")
        return
    slots = _resolve_time_slots(sched)
    for idx, slot in enumerate(slots):
        # スロット固有の曜日指定があればそれを優先（例: 木曜だけ別時刻）。
        slot_days = slot.get("days_of_week") or days
        slot_days = [d for d in slot_days if 0 <= d <= 6]
        if not slot_days:
            print(f"🚫 Autopilot for {channel_id} slot {idx}: 有効な曜日なし — スキップ")
            continue
        days_label = "・".join(DOW_NAMES[d] for d in slot_days)
        day_of_week = ",".join(DOW_NAMES[d] for d in slot_days)
        try:
            trigger = api_phase4.CronTrigger(
                day_of_week=day_of_week,
                hour=slot["hour"],
                minute=slot["minute"],
                timezone="Asia/Tokyo",
            )
            jid = _job_id(channel_id, idx)
            sch.add_job(
                _run_autopilot,
                trigger=trigger,
                id=jid,
                args=[channel_id],
                replace_existing=True,
                misfire_grace_time=3600,
            )
            job = sch.get_job(jid)
            nxt = job.next_run_time.isoformat() if job and job.next_run_time else "?"
            print(
                f"📅 Autopilot scheduled for {channel_id} [slot {idx}]: "
                f"{days_label} {slot['hour']:02d}:{slot['minute']:02d} JST "
                f"→ next run {nxt}"
            )
        except Exception as e:
            print(f"⚠️ Failed to schedule autopilot for {channel_id} slot {idx}: {e}")


def _remove_channel_job(channel_id: str) -> None:
    sch = api_phase4._ensure_scheduler()
    if sch is None:
        return
    for job in _iter_channel_jobs(sch, channel_id):
        try:
            sch.remove_job(job.id)
        except Exception:
            pass


def _next_run_at(channel_id: str) -> Optional[str]:
    sch = api_phase4._ensure_scheduler()
    if sch is None:
        return None
    next_times = [
        job.next_run_time for job in _iter_channel_jobs(sch, channel_id) if job.next_run_time
    ]
    if not next_times:
        return None
    return min(next_times).isoformat()


def restore_all() -> None:
    """起動時: すべてのチャンネルの autopilot ジョブを復元"""
    cm = _state.get("channel_manager")
    if cm is None:
        print("⚠️ Autopilot restore skipped: channel_manager 未初期化")
        return
    sch = api_phase4._ensure_scheduler()
    if sch is None:
        print("⚠️ Autopilot restore skipped: APScheduler 未利用")
        return
    enabled_ids: List[str] = []
    for ch in cm.list_channels():
        try:
            _refresh_channel_job(ch.id)
            ap = _load_autopilot(ch.id)
            if ap.get("enabled") and ap.get("schedule", {}).get("days_of_week"):
                enabled_ids.append(ch.id)
        except Exception as e:
            print(f"⚠️ autopilot restore failed for {ch.id}: {e}")
    total = len(cm.list_channels())
    if enabled_ids:
        print(f"🤖 Autopilot restored: {len(enabled_ids)}/{total} channel(s) active — {', '.join(enabled_ids)}")
    else:
        print(f"🤖 Autopilot restored: 0/{total} channel(s) active — no scheduled jobs")


# =====================================================================
# 発火ロジック
# =====================================================================

def _pop_or_refill_theme(channel_id: str) -> Optional[Dict[str, str]]:
    """キュー先頭を取り出す。空なら AI で補充。それも失敗すれば theme_seeds で代替。"""
    with _lock:
        ap = _load_autopilot(channel_id)
        queue = list(ap.get("theme_queue") or [])

        if not queue:
            cm = _state.get("channel_manager")
            ch = cm.get(channel_id) if cm else None
            if not ch:
                return None

            sg = _state.get("scenario_generator")
            if sg and getattr(sg, "api_key", None):
                try:
                    suggested = sg.suggest_themes(ch, count=5) or []
                except Exception as e:
                    print(f"⚠️ autopilot AI refill failed for {channel_id}: {e}")
                    suggested = []
                for s in suggested:
                    if isinstance(s, dict) and s.get("title"):
                        queue.append({
                            "id": _new_theme_id(),
                            "title": str(s["title"]),
                            "angle": str(s.get("angle") or ""),
                        })

            if not queue:
                # 最終フォールバック: チャンネルJSONの theme_seeds → theme_priority.good_examples
                seeds: List[Dict[str, Any]] = list(getattr(ch, "theme_seeds", None) or [])
                if not seeds:
                    raw = getattr(ch, "_raw", {}) or {}
                    examples = (raw.get("theme_priority") or {}).get("good_examples") or []
                    seeds = [{"title": s} for s in examples if isinstance(s, str) and s.strip()]
                if seeds:
                    print(f"🪴 autopilot fallback: using {len(seeds)} theme_seeds for {channel_id}")
                for s in seeds:
                    if isinstance(s, dict) and s.get("title"):
                        queue.append({
                            "id": _new_theme_id(),
                            "title": str(s["title"]),
                            "angle": str(s.get("angle") or ""),
                        })

            if not queue:
                return None

        # 過去テーマと「実質同じ」な先頭は捨てて次へ進む（テーマ重複の最終ゲート）。
        # ここで弾かないと、run_*_short_upload / autopilot は theme_override 経由で
        # generator 内の再抽選を通らないため、重複テーマがそのまま投稿されてしまう。
        try:
            from pipeline.auto_scenario import theme_dedup as _td
            past = _td.past_theme_titles(channel_id, within_days=60)
        except Exception as e:
            print(f"⚠️ autopilot dedup gate disabled ({channel_id}): {e}")
            _td = None  # type: ignore
            past = []

        head = None
        skipped = 0
        while queue:
            cand = queue.pop(0)
            cand_title = (cand.get("title") or "").strip()
            if _td is not None and cand_title and past:
                hit = _td.find_lexical_duplicate(cand_title, past)
                if hit is not None:
                    skipped += 1
                    print(f"  ♻️ autopilot dropped dup theme: '{cand_title}' ≈ '{hit[0]}' ({hit[1]:.2f})")
                    continue
            head = cand
            break

        # 全部重複で枯渇したら、最後に取り出した候補を使う（投稿skipより重複の方がマシ）
        if head is None:
            print(f"⚠️ autopilot {channel_id}: all queued themes duplicate recent posts — using last anyway")
            head = cand  # type: ignore[possibly-undefined]

        ap["theme_queue"] = queue
        _save_autopilot(channel_id, ap)
        if skipped:
            print(f"  ℹ️ autopilot {channel_id}: skipped {skipped} duplicate theme(s) before '{head.get('title')}'")
        return {"title": head["title"], "angle": head.get("angle") or ""}


def _run_clip_autopilot(channel_id: str) -> None:
    """切り抜きチャンネルの発火。

    切り抜きは台本生成もテーマキューも使わない（素材は既存の長尺動画）。
    ScenarioGenerator / JobQueue を経由せず clip_factory を直接叩く。
    レンダリングが数十秒かかるのでスケジューラスレッドは塞がず別スレッドで回す。
    """
    def _work() -> None:
        try:
            from pipeline.clip_factory import generate_clip
        except Exception as e:
            api_phase4.notify_event("error", f"Autopilot 失敗 ({channel_id}): clip_factory を読み込めません: {e}")
            return
        cm = _state.get("channel_manager")
        ch = cm.get(channel_id) if cm else None
        raw = (ch._raw if ch is not None and hasattr(ch, "_raw") else {}) or {}
        auto_publish = bool((raw.get("publish_settings") or {}).get("auto_publish"))
        try:
            res = generate_clip(channel_id, count=1, upload=auto_publish)
        except Exception as e:
            api_phase4.notify_event("error", f"Autopilot 失敗 ({channel_id}): {e}")
            return
        if not res.get("ok"):
            api_phase4.notify_event("error", f"Autopilot 失敗 ({channel_id}): {res.get('error')}")
            return
        clips = res.get("clips") or []
        head = clips[0] if clips else {}
        source = (res.get("source") or {}).get("title", "")
        api_phase4.notify_event(
            "schedule_run",
            f"✂️ 切り抜き生成 [{(ch.name if ch else channel_id)}]: {head.get('title', '')} "
            f"（元: {source} / engine: {res.get('engine')}）",
        )

    threading.Thread(target=_work, name=f"clip-autopilot-{channel_id}", daemon=True).start()


def _run_autopilot(channel_id: str) -> None:
    """スケジュール発火: テーマ取得 → シナリオ生成 → キュー投入 → 自動公開フラグ"""
    fired_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"🤖 Autopilot fired for {channel_id} at {fired_at} JST")
    if (_load_autopilot(channel_id).get("gen_type") or "") == CLIP_GEN_TYPE:
        _run_clip_autopilot(channel_id)
        return
    # 投稿前に「今のスロットが推奨スロットと比べて極端に低い」場合は推奨スロットに移行。
    # ただしこれは schedule.days_of_week / hour を自動で上書きしてしまうため、
    # 「毎日2本・固定スロット」運用と衝突する。明示的に
    # autopilot.auto_optimize_schedule=true を設定したチャンネルだけに限定する
    # （デフォルト off）。最適時間帯の分析自体は日次 PDCA レポートに出る。
    try:
        ap_cfg = _load_autopilot(channel_id)
        if ap_cfg.get("auto_optimize_schedule"):
            from pipeline.analytics import posting_optimizer as _po
            check = _po.slot_is_optimal_enough(channel_id, tolerance_percent=50.0)
            if not check.get("is_optimal_enough"):
                print(
                    f"📅 Autopilot: current slot underperforms recommended by "
                    f"{check.get('delta_percent')}% — auto-applying recommendation"
                )
                _po.apply_to_autopilot(channel_id)
    except Exception as e:
        print(f"⚠️ posting_optimizer pre-check failed for {channel_id}: {e}")
    cm = _state.get("channel_manager")
    sg = _state.get("scenario_generator")
    queue = _state.get("job_queue")
    if not (cm and sg and queue):
        api_phase4.notify_event("error", f"Autopilot 失敗 ({channel_id}): pipeline 未初期化")
        return
    ch = cm.get(channel_id)
    if not ch:
        api_phase4.notify_event("error", f"Autopilot 失敗: チャンネル '{channel_id}' なし")
        return
    if not getattr(sg, "api_key", None):
        api_phase4.notify_event("error", f"Autopilot 失敗 ({channel_id}): OpenAI APIキー未設定")
        return

    theme = _pop_or_refill_theme(channel_id)
    if not theme:
        api_phase4.notify_event(
            "error",
            f"Autopilot スキップ ({channel_id}): テーマキューが空で AI 補充にも失敗",
        )
        return
    print(f"🤖 Autopilot {channel_id}: theme = {theme.get('title', '?')[:60]}")

    ap = _load_autopilot(channel_id)
    duration_min = int(ap.get("duration_minutes") or 12)
    gen_type = ap.get("gen_type") or "both"
    if gen_type not in GEN_TYPE_CHOICES:
        print(f"⚠️ Autopilot {channel_id}: unknown gen_type={gen_type!r} — falling back to 'both'")
        gen_type = "both"

    try:
        scenario = sg.generate(
            ch,
            theme_override=theme,
            target_duration=max(60, duration_min * 60),
        )
        try:
            sg.save_scenario(scenario)
        except Exception:
            pass
        job_id = queue.submit(
            channel_id=channel_id,
            scenario_data=scenario,
            priority=5,
            gen_type=gen_type,
        )
        # 完了時に api_phase4.on_generation_complete が拾って YouTube ペア公開する
        api_phase4._attach_auto_publish_marker(queue, job_id, f"autopilot:{channel_id}", True)
        api_phase4.notify_event(
            "schedule_run",
            f"🤖 Autopilot 実行 [{ch.name}]: {scenario.get('title', '')} (job: {job_id})",
        )
    except Exception as e:
        api_phase4.notify_event("error", f"Autopilot 失敗 ({channel_id}): {e}")


# =====================================================================
# REST endpoints
# =====================================================================

def _autopilot_response(channel_id: str) -> Dict[str, Any]:
    ap = _load_autopilot(channel_id)
    return {
        "channel_id": channel_id,
        "config": ap,
        "next_run_at": _next_run_at(channel_id),
        "scheduler_available": api_phase4.HAS_APSCHEDULER,
    }


@router.get("/{channel_id}/autopilot")
async def get_autopilot(channel_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    return _autopilot_response(channel_id)


@router.put("/{channel_id}/autopilot")
async def update_autopilot(
    channel_id: str, req: AutopilotUpdate, _=Depends(require_session)
) -> Dict[str, Any]:
    ap = _load_autopilot(channel_id)
    if req.enabled is not None:
        ap["enabled"] = bool(req.enabled)
    if req.schedule is not None:
        # 曜日バリデーション
        for d in req.schedule.days_of_week:
            if not (0 <= d <= 6):
                raise HTTPException(status_code=400, detail=f"Invalid day_of_week: {d}")
        new_sched: Dict[str, Any] = {
            "days_of_week": sorted(set(req.schedule.days_of_week)),
            "hour": req.schedule.hour,
            "minute": req.schedule.minute,
        }
        if req.schedule.times:
            # 重複・無効値は除去し、(hour, minute) でソート
            seen: set = set()
            slots: List[Dict[str, Any]] = []
            for t in req.schedule.times:
                slot_days = sorted({d for d in (t.days_of_week or []) if 0 <= d <= 6})
                # 曜日が違えば同じ時刻でも別スロットとして許容する
                key = (t.hour, t.minute, tuple(slot_days))
                if key in seen:
                    continue
                seen.add(key)
                slot: Dict[str, Any] = {"hour": t.hour, "minute": t.minute}
                if slot_days:
                    slot["days_of_week"] = slot_days
                slots.append(slot)
            slots.sort(key=lambda s: (s["hour"], s["minute"]))
            new_sched["times"] = slots
        ap["schedule"] = new_sched
    if req.duration_minutes is not None:
        ap["duration_minutes"] = req.duration_minutes
    if req.gen_type is not None:
        if req.gen_type not in GEN_TYPE_CHOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid gen_type: {req.gen_type} (allowed: {', '.join(GEN_TYPE_CHOICES)})",
            )
        ap["gen_type"] = req.gen_type
    if ap["enabled"] and not ap["schedule"].get("days_of_week"):
        raise HTTPException(
            status_code=400,
            detail="フルオートを有効化するには曜日を1つ以上選んでください",
        )
    # 整合性ガード: 非公開(private)のままフルオートを有効化させない。
    # （過去に scp-lab が default_privacy=private のまま自動投稿し、全部非公開になった事故の再発防止）
    if ap["enabled"]:
        cm = _state.get("channel_manager")
        ch = cm.get(channel_id) if cm else None
        raw = (ch._raw if ch is not None and hasattr(ch, "_raw") else {}) or {}
        privacy = get_default_privacy(raw)
        if privacy == "private":
            raise HTTPException(
                status_code=400,
                detail=(
                    "default_privacy が 'private' のためフルオートを有効化できません。"
                    "自動投稿された動画がすべて非公開になります。"
                    "先にチャンネル設定の公開ステータスを 'public' に変更してください。"
                ),
            )
    _save_autopilot(channel_id, ap)
    return _autopilot_response(channel_id)


@router.get("/{channel_id}/autopilot/queue")
async def get_queue(channel_id: str, _=Depends(require_session)) -> Dict[str, Any]:
    ap = _load_autopilot(channel_id)
    return {"channel_id": channel_id, "queue": ap.get("theme_queue", [])}


@router.post("/{channel_id}/autopilot/queue", status_code=201)
async def add_theme(
    channel_id: str, req: ThemeAdd, _=Depends(require_session)
) -> Dict[str, Any]:
    ap = _load_autopilot(channel_id)
    item = {"id": _new_theme_id(), "title": req.title.strip(), "angle": (req.angle or "").strip()}
    ap["theme_queue"] = list(ap.get("theme_queue") or []) + [item]
    _save_autopilot(channel_id, ap)
    return {"channel_id": channel_id, "queue": ap["theme_queue"], "added": item}


@router.put("/{channel_id}/autopilot/queue")
async def reorder_queue(
    channel_id: str, req: ThemeReorder, _=Depends(require_session)
) -> Dict[str, Any]:
    """キューを丸ごと差し替え（並び替え用）。"""
    ap = _load_autopilot(channel_id)
    new_queue: List[Dict[str, Any]] = []
    for it in req.queue:
        if not it.title or not it.title.strip():
            continue
        new_queue.append({
            "id": it.id or _new_theme_id(),
            "title": it.title.strip(),
            "angle": (it.angle or "").strip(),
        })
    ap["theme_queue"] = new_queue
    _save_autopilot(channel_id, ap)
    return {"channel_id": channel_id, "queue": ap["theme_queue"]}


@router.patch("/{channel_id}/autopilot/queue/{theme_id}")
async def update_theme(
    channel_id: str, theme_id: str, req: ThemeUpdate, _=Depends(require_session)
) -> Dict[str, Any]:
    ap = _load_autopilot(channel_id)
    queue = list(ap.get("theme_queue") or [])
    found = False
    for i, item in enumerate(queue):
        if item.get("id") == theme_id:
            if req.title is not None:
                if not req.title.strip():
                    raise HTTPException(status_code=400, detail="title cannot be empty")
                item["title"] = req.title.strip()
            if req.angle is not None:
                item["angle"] = req.angle.strip()
            queue[i] = item
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="theme not found")
    ap["theme_queue"] = queue
    _save_autopilot(channel_id, ap)
    return {"channel_id": channel_id, "queue": ap["theme_queue"]}


@router.delete("/{channel_id}/autopilot/queue/{theme_id}")
async def delete_theme(
    channel_id: str, theme_id: str, _=Depends(require_session)
) -> Dict[str, Any]:
    ap = _load_autopilot(channel_id)
    queue = [t for t in (ap.get("theme_queue") or []) if t.get("id") != theme_id]
    if len(queue) == len(ap.get("theme_queue") or []):
        raise HTTPException(status_code=404, detail="theme not found")
    ap["theme_queue"] = queue
    _save_autopilot(channel_id, ap)
    return {"channel_id": channel_id, "queue": ap["theme_queue"]}


@router.post("/{channel_id}/autopilot/queue/refill")
async def refill_queue(
    channel_id: str, req: RefillRequest, _=Depends(require_session)
) -> Dict[str, Any]:
    """GPT で N 件テーマを提案してキュー末尾に追加。"""
    cm = _state.get("channel_manager")
    sg = _state.get("scenario_generator")
    if not (cm and sg):
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    ch = cm.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    if not getattr(sg, "api_key", None):
        raise HTTPException(status_code=400, detail="OpenAI API key not set")
    try:
        suggested = sg.suggest_themes(ch, count=req.count) or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI suggest failed: {e}")

    ap = _load_autopilot(channel_id)
    existing_titles = {t.get("title") for t in (ap.get("theme_queue") or [])}
    added: List[Dict[str, Any]] = []
    for s in suggested:
        if not isinstance(s, dict):
            continue
        title = (s.get("title") or "").strip()
        if not title or title in existing_titles:
            continue
        item = {"id": _new_theme_id(), "title": title, "angle": (s.get("angle") or "").strip()}
        added.append(item)
        existing_titles.add(title)
    ap["theme_queue"] = list(ap.get("theme_queue") or []) + added
    _save_autopilot(channel_id, ap)
    return {"channel_id": channel_id, "queue": ap["theme_queue"], "added": added}


@router.post("/{channel_id}/autopilot/run-now")
async def run_now(channel_id: str, _=Depends(require_session)) -> Dict[str, str]:
    """テスト実行 — 即座に1回発火"""
    cm = _state.get("channel_manager")
    if cm is None or cm.get(channel_id) is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    threading.Thread(target=_run_autopilot, args=(channel_id,), daemon=True).start()
    return {"status": "triggered"}
