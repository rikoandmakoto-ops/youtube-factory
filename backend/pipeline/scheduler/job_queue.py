"""
JobQueue — マルチチャンネル動画生成の並列ジョブ管理

Features:
- 複数ワーカーによる並列生成（デフォルト2並列: VOICEVOXがボトルネック）
- チャンネル別優先度
- ジョブ状態管理（pending → running → completed/failed）
- 自動リトライ（1回）
- ジョブ履歴・統計

Usage:
    queue = JobQueue(max_workers=2)
    queue.start()

    job_id = queue.submit(
        channel_id="daily-science",
        scenario_data={...},  # ScenarioGenerator output
        priority=1,
    )

    status = queue.get_status(job_id)
    queue.stop()
"""

import json
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from queue import PriorityQueue


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCancelled(Exception):
    """ユーザー操作によるジョブ中断。リトライしない。"""
    pass


@dataclass
class Job:
    """1つの動画生成ジョブ"""
    id: str
    channel_id: str
    title: str
    style: str
    scenario_data: Dict[str, Any]
    priority: int = 5  # 1=highest, 10=lowest
    status: JobStatus = JobStatus.PENDING
    progress: str = ""
    result: Optional[Dict] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 1
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # ユーザーが中断ボタンを押したフラグ。実行ループ内の各ステップ間でチェックされる
    cancel_requested: bool = False
    # Generation options
    gen_type: str = "both"
    output_dir: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "title": self.title,
            "style": self.style,
            "status": self.status.value,
            "progress": self.progress,
            "priority": self.priority,
            "gen_type": self.gen_type,
            "result": self.result,
            "error": self.error,
            "retries": self.retries,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def to_persist_dict(self) -> Dict:
        """ディスク永続化用 — scenario_data など API には載せない情報も含む"""
        d = self.to_dict()
        d.update({
            "scenario_data": self.scenario_data,
            "max_retries": self.max_retries,
            "cancel_requested": self.cancel_requested,
            "output_dir": self.output_dir,
        })
        return d

    @classmethod
    def from_persist_dict(cls, d: Dict) -> "Job":
        return cls(
            id=d["id"],
            channel_id=d["channel_id"],
            title=d.get("title", ""),
            style=d.get("style", "yukkuri"),
            scenario_data=d.get("scenario_data") or {},
            priority=d.get("priority", 5),
            status=JobStatus(d.get("status", "pending")),
            progress=d.get("progress", ""),
            result=d.get("result"),
            error=d.get("error"),
            retries=d.get("retries", 0),
            max_retries=d.get("max_retries", 1),
            created_at=d.get("created_at") or datetime.now().isoformat(),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            cancel_requested=bool(d.get("cancel_requested", False)),
            gen_type=d.get("gen_type", "both"),
            output_dir=d.get("output_dir"),
        )

    def __lt__(self, other):
        """PriorityQueue用比較"""
        return self.priority < other.priority


class JobQueue:
    """
    並列動画生成ジョブキュー

    Args:
        max_workers: 同時実行ワーカー数（デフォルト2）
        on_job_complete: ジョブ完了時コールバック
        on_job_failed: ジョブ失敗時コールバック
    """

    # 既定の永続化先 — <repo-root>/data/job_queue.json
    DEFAULT_PERSIST_PATH = (
        Path(__file__).parent.parent.parent.parent / "data" / "job_queue.json"
    )

    def __init__(
        self,
        max_workers: int = 2,
        on_job_complete: Optional[Callable] = None,
        on_job_failed: Optional[Callable] = None,
        persist_path: Optional[Path] = None,
    ):
        self.max_workers = max_workers
        self._jobs: Dict[str, Job] = {}
        self._queue: PriorityQueue = PriorityQueue()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self.on_job_complete = on_job_complete
        self.on_job_failed = on_job_failed

        # Pipeline function — set by main.py after import
        self._generate_fn: Optional[Callable] = None
        self._channel_manager = None

        # 永続化先 (None を渡すと完全に無効化)
        self._persist_path: Optional[Path] = (
            persist_path if persist_path is not None else self.DEFAULT_PERSIST_PATH
        )
        self._load()

    # ────────────────────────────────────────────────────────────────
    # 永続化
    # ────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        """全ジョブ状態をディスクに書き出す。失敗してもキューは継続"""
        if self._persist_path is None:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = [j.to_persist_dict() for j in self._jobs.values()]
            payload = {"version": 1, "jobs": snapshot}
            tmp = self._persist_path.with_suffix(self._persist_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
            tmp.replace(self._persist_path)
        except Exception as e:
            print(f"⚠️ JobQueue persist failed: {e}")

    def _load(self) -> None:
        """起動時: 永続化ファイルからジョブを復元。

        - PENDING: そのままキューに再投入
        - RUNNING: プロセス停止中に走っていた扱いとして FAILED に確定
          (途中状態の動画が残っている可能性があるため自動リトライしない)
        - その他 (completed/failed/cancelled): 履歴として保持
        """
        if self._persist_path is None or not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text())
        except Exception as e:
            print(f"⚠️ JobQueue load failed: {e}")
            return

        restored_pending = 0
        marked_interrupted = 0
        for d in raw.get("jobs", []):
            try:
                job = Job.from_persist_dict(d)
            except Exception as e:
                print(f"⚠️ JobQueue skip malformed job: {e}")
                continue

            if job.status == JobStatus.RUNNING:
                job.status = JobStatus.FAILED
                prev_err = (job.error or "").strip()
                job.error = (prev_err + " " if prev_err else "") + "[interrupted by restart]"
                job.completed_at = job.completed_at or datetime.now().isoformat()
                job.progress = "中断 (プロセス停止)"
                marked_interrupted += 1

            self._jobs[job.id] = job
            if job.status == JobStatus.PENDING:
                self._queue.put((job.priority, job.id))
                restored_pending += 1

        if restored_pending or marked_interrupted or self._jobs:
            print(
                f"📂 JobQueue restored from {self._persist_path.name}: "
                f"total={len(self._jobs)} pending_requeued={restored_pending} "
                f"interrupted_marked_failed={marked_interrupted}"
            )
        # 中断ジョブの状態を確定させるため一度書き戻す
        if marked_interrupted:
            self._save()

    def set_pipeline(self, generate_fn: Callable, channel_manager=None):
        """パイプライン関数とチャンネルマネージャーを設定"""
        self._generate_fn = generate_fn
        self._channel_manager = channel_manager

    def start(self):
        """ワーカープール開始"""
        if self._running:
            return
        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._worker_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._worker_thread.start()
        print(f"🚀 JobQueue started ({self.max_workers} workers)")

    def stop(self):
        """ワーカープール停止"""
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=False)
        print("🛑 JobQueue stopped")

    def submit(
        self,
        channel_id: str,
        scenario_data: Dict[str, Any],
        priority: int = 5,
        gen_type: str = "both",
        output_dir: Optional[str] = None,
    ) -> str:
        """ジョブをキューに投入"""
        job_id = str(uuid.uuid4())[:8]
        job = Job(
            id=job_id,
            channel_id=channel_id,
            title=scenario_data.get("title", "untitled"),
            style=scenario_data.get("style", "yukkuri"),
            scenario_data=scenario_data,
            priority=priority,
            gen_type=gen_type,
            output_dir=output_dir,
        )

        with self._lock:
            self._jobs[job_id] = job
            self._queue.put((priority, job_id))
        self._save()

        print(f"📥 Job queued: [{job_id}] {job.title} (ch: {channel_id}, priority: {priority})")
        return job_id

    def cancel(self, job_id: str) -> bool:
        """ジョブをキャンセル。

        - pending: 即座に CANCELLED に切り替え
        - running: cancel_requested フラグを立て、各ステップ間でフラグが
          チェックされた時点で JobCancelled が送出され、安全に停止する
        """
        changed = False
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                job.cancel_requested = True
                job.completed_at = datetime.now().isoformat()
                job.progress = "中断しました"
                changed = True
            elif job.status == JobStatus.RUNNING:
                job.cancel_requested = True
                job.progress = "中断要求を受信..."
                changed = True
        if changed:
            self._save()
            return True
        return False

    def is_cancel_requested(self, job_id: str) -> bool:
        """ジョブがキャンセル要求済みかチェック（パイプラインから呼ぶ）"""
        job = self._jobs.get(job_id)
        return bool(job and job.cancel_requested)

    def get_status(self, job_id: str) -> Optional[Dict]:
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def list_jobs(self, channel_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
        """ジョブ一覧（フィルタ可能）"""
        jobs = list(self._jobs.values())
        if channel_id:
            jobs = [j for j in jobs if j.channel_id == channel_id]
        if status:
            jobs = [j for j in jobs if j.status.value == status]
        # 最新順
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs]

    def get_stats(self) -> Dict:
        """ジョブ統計"""
        with self._lock:
            all_jobs = list(self._jobs.values())
        counts = {}
        for s in JobStatus:
            counts[s.value] = sum(1 for j in all_jobs if j.status == s)
        # チャンネル別
        channel_counts = {}
        for j in all_jobs:
            if j.channel_id not in channel_counts:
                channel_counts[j.channel_id] = {"total": 0, "completed": 0, "failed": 0}
            channel_counts[j.channel_id]["total"] += 1
            if j.status == JobStatus.COMPLETED:
                channel_counts[j.channel_id]["completed"] += 1
            elif j.status == JobStatus.FAILED:
                channel_counts[j.channel_id]["failed"] += 1

        return {
            "total": len(all_jobs),
            "by_status": counts,
            "by_channel": channel_counts,
            "workers": self.max_workers,
            "running": self._running,
        }

    def _dispatch_loop(self):
        """キューからジョブを取り出してワーカーに投入"""
        while self._running:
            try:
                if not self._queue.empty():
                    _priority, job_id = self._queue.get(timeout=1)
                    job = self._jobs.get(job_id)
                    if job and job.status == JobStatus.PENDING:
                        future = self._executor.submit(self._execute_job, job)
                        self._futures[job_id] = future
                    elif job and job.status == JobStatus.CANCELLED:
                        pass  # skip cancelled
                else:
                    time.sleep(0.5)
            except Exception:
                time.sleep(1)

    def _execute_job(self, job: Job):
        """1ジョブの実行"""
        # ワーカー投入後にキャンセルされていた場合はここで打ち切る
        if job.cancel_requested:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now().isoformat()
            job.progress = "中断しました"
            self._save()
            print(f"🛑 Job cancelled before start: [{job.id}] {job.title}")
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now().isoformat()
        job.progress = "動画生成を開始..."
        self._save()

        # generate_all 内で各ステップ間で呼ばれる中断チェック
        def _cancel_check() -> None:
            if job.cancel_requested:
                raise JobCancelled(f"Job {job.id} cancelled by user")

        try:
            if not self._generate_fn:
                raise RuntimeError("Pipeline generate function not set")

            # チャンネルプロファイル取得
            channel = None
            if self._channel_manager:
                channel = self._channel_manager.get(job.channel_id)

            sd = job.scenario_data
            # チャンネル固定フォーマット＆キャラ設定を渡す
            ch_format = channel.video_format.to_dict() if channel else None
            ch_chars = channel.char_config() if channel else None
            ch_dict = channel.to_dict() if channel else None
            # フォームのスライダー値（_options.bgm_volume）でチャンネル既定を上書き
            options = sd.get("_options") or {}
            bgm_volume_override = options.get("bgm_volume")
            # generate_all() 呼び出し
            result = self._generate_fn(
                title=sd.get("title", job.title),
                prefix=job.channel_id,
                short_scenario=sd.get("short_scenario", []),
                full_scenario=sd.get("full_scenario"),
                output_dir=job.output_dir,
                gen_type=job.gen_type,
                bg_video_path=channel.get_bg_video_path() if channel else None,
                bg_type=channel.get_bg_type() if channel else "auto",
                thumb_info=sd.get("thumb_info"),
                speed=channel.get_speed() if channel else 1.3,
                target_duration=channel.get_target_duration() if channel else 720,
                style=job.style,
                use_illustrations=channel.get_use_illustrations() if channel else True,
                channel_format=ch_format,
                char_config=ch_chars,
                channel_dict=ch_dict,
                bgm_volume=bgm_volume_override,
                image_mode=channel.get_image_mode() if channel else "generate",
                image_collect_settings=channel.get_image_collect_settings() if channel else None,
                cancel_check=_cancel_check,
                scenario_meta={
                    "theme": sd.get("theme"),
                    "applied_feedback": sd.get("applied_feedback"),
                    "prompt_hash": sd.get("prompt_hash"),
                    "video_title": sd.get("video_title"),
                    # facts_overlay の背景/ロゴ検索キー
                    "company_name": sd.get("company_name"),
                    "generated_by": sd.get("generated_by"),
                    "compete": sd.get("compete"),
                },
            )

            # generate_all から戻った後にも中断要求が立っていたら CANCELLED で確定
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.result = result
                job.completed_at = datetime.now().isoformat()
                job.progress = "中断しました"
                self._save()
                print(f"🛑 Job cancelled after pipeline: [{job.id}] {job.title}")
                return

            job.status = JobStatus.COMPLETED
            job.result = result
            job.completed_at = datetime.now().isoformat()
            job.progress = "完了"
            self._save()
            print(f"✅ Job completed: [{job.id}] {job.title}")

            if self.on_job_complete:
                self.on_job_complete(job)

        except JobCancelled as e:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now().isoformat()
            job.progress = "中断しました"
            self._save()
            print(f"🛑 Job cancelled: [{job.id}] {job.title} — {e}")

        except Exception as e:
            # 例外は str(e) だけだと発生箇所が分からない（KeyError なら
            # キー名しか出ない）。ログに完全なトレースバックを残す。
            print(f"💥 Job exception: [{job.id}] {job.title} — {type(e).__name__}: {e}")
            traceback.print_exc()

            # キャンセル要求中にステップが例外を吐いた場合もリトライしない
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now().isoformat()
                job.progress = "中断しました"
                self._save()
                print(f"🛑 Job cancelled (during exception): [{job.id}] {job.title} — {e}")
                return

            if job.retries < job.max_retries:
                job.retries += 1
                job.status = JobStatus.PENDING
                job.progress = f"リトライ {job.retries}/{job.max_retries}..."
                with self._lock:
                    self._queue.put((job.priority, job.id))
                self._save()
                print(f"🔄 Job retry: [{job.id}] {job.title} (attempt {job.retries})")
            else:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.now().isoformat()
                job.progress = "失敗"
                self._save()
                print(f"❌ Job failed: [{job.id}] {job.title} — {e}")

                if self.on_job_failed:
                    self.on_job_failed(job)
