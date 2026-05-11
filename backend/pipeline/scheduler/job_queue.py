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

    def __init__(
        self,
        max_workers: int = 2,
        on_job_complete: Optional[Callable] = None,
        on_job_failed: Optional[Callable] = None,
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

        print(f"📥 Job queued: [{job_id}] {job.title} (ch: {channel_id}, priority: {priority})")
        return job_id

    def cancel(self, job_id: str) -> bool:
        """ジョブをキャンセル。

        - pending: 即座に CANCELLED に切り替え
        - running: cancel_requested フラグを立て、各ステップ間でフラグが
          チェックされた時点で JobCancelled が送出され、安全に停止する
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                job.cancel_requested = True
                job.completed_at = datetime.now().isoformat()
                job.progress = "中断しました"
                return True
            if job.status == JobStatus.RUNNING:
                job.cancel_requested = True
                job.progress = "中断要求を受信..."
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
            print(f"🛑 Job cancelled before start: [{job.id}] {job.title}")
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now().isoformat()
        job.progress = "動画生成を開始..."

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
                cancel_check=_cancel_check,
                scenario_meta={
                    "theme": sd.get("theme"),
                    "applied_feedback": sd.get("applied_feedback"),
                    "prompt_hash": sd.get("prompt_hash"),
                    "video_title": sd.get("video_title"),
                },
            )

            # generate_all から戻った後にも中断要求が立っていたら CANCELLED で確定
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.result = result
                job.completed_at = datetime.now().isoformat()
                job.progress = "中断しました"
                print(f"🛑 Job cancelled after pipeline: [{job.id}] {job.title}")
                return

            job.status = JobStatus.COMPLETED
            job.result = result
            job.completed_at = datetime.now().isoformat()
            job.progress = "完了"
            print(f"✅ Job completed: [{job.id}] {job.title}")

            if self.on_job_complete:
                self.on_job_complete(job)

        except JobCancelled as e:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now().isoformat()
            job.progress = "中断しました"
            print(f"🛑 Job cancelled: [{job.id}] {job.title} — {e}")

        except Exception as e:
            # キャンセル要求中にステップが例外を吐いた場合もリトライしない
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now().isoformat()
                job.progress = "中断しました"
                print(f"🛑 Job cancelled (during exception): [{job.id}] {job.title} — {e}")
                return

            if job.retries < job.max_retries:
                job.retries += 1
                job.status = JobStatus.PENDING
                job.progress = f"リトライ {job.retries}/{job.max_retries}..."
                with self._lock:
                    self._queue.put((job.priority, job.id))
                print(f"🔄 Job retry: [{job.id}] {job.title} (attempt {job.retries})")
            else:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.now().isoformat()
                job.progress = "失敗"
                print(f"❌ Job failed: [{job.id}] {job.title} — {e}")

                if self.on_job_failed:
                    self.on_job_failed(job)
