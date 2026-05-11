'use client';

import { useEffect, useState } from 'react';
import type { ActiveJob } from '@/lib/api';

async function fetchActiveJobs(): Promise<ActiveJob[]> {
  const res = await fetch('/api/jobs/active', { cache: 'no-store' });
  if (!res.ok) return [];
  const data = await res.json();
  return data.jobs ?? [];
}

export default function ActiveJobs({
  initial,
}: {
  initial: ActiveJob[];
}) {
  const [jobs, setJobs] = useState<ActiveJob[]>(initial);
  const [cancelling, setCancelling] = useState<Record<string, boolean>>({});
  const [cancelled, setCancelled] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      const j = await fetchActiveJobs();
      if (stopped) return;
      setJobs(j);
      // ポーリングで消えたジョブの「中断しました」表示は2サイクルほど残してからクリア
      setCancelled((prev) => {
        const next: Record<string, boolean> = {};
        for (const id of Object.keys(prev)) {
          if (j.some((x) => x.job_id === id)) next[id] = true;
        }
        return next;
      });
    };
    const id = setInterval(tick, 3000);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, []);

  const onCancel = async (jobId: string) => {
    if (cancelling[jobId]) return;
    setCancelling((p) => ({ ...p, [jobId]: true }));
    try {
      const res = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/cancel`,
        { method: 'POST', cache: 'no-store' }
      );
      if (res.ok) {
        setCancelled((p) => ({ ...p, [jobId]: true }));
      }
    } finally {
      setCancelling((p) => ({ ...p, [jobId]: false }));
    }
  };

  if (jobs.length === 0) return null;

  return (
    <section aria-label="生成ジョブ" className="px-5 space-y-2">
      {jobs.map((j) => {
        const isCancelled = cancelled[j.job_id];
        const isCancelling = cancelling[j.job_id];
        return (
          <div key={j.job_id} className="card">
            <div className="flex justify-between items-center mb-2 gap-2">
              <h4 className="font-semibold text-sm truncate pr-2">
                {isCancelled ? '🛑 中断しました: ' : '⚙️ 生成中: '}
                {j.title}
              </h4>
              <span className="text-xs text-slate-400 shrink-0">
                {Math.round(j.progress)}%
              </span>
            </div>
            <div className="h-2 rounded bg-bg-elev overflow-hidden">
              <div
                className={`h-full transition-all ${
                  isCancelled
                    ? 'bg-slate-500'
                    : 'bg-gradient-to-r from-accent to-purple-500'
                }`}
                style={{ width: `${Math.max(2, j.progress)}%` }}
              />
            </div>
            <div className="flex justify-between items-center mt-2 gap-2">
              <p className="text-xs text-slate-400 truncate">
                {isCancelled
                  ? '中断しました'
                  : `${j.step}. ${j.step_label}`}
              </p>
              {!isCancelled && (
                <button
                  type="button"
                  onClick={() => onCancel(j.job_id)}
                  disabled={isCancelling}
                  className="text-xs px-2 py-1 rounded bg-red-500/10 border border-red-500/30 text-red-300 hover:bg-red-500/20 disabled:opacity-50 shrink-0"
                >
                  {isCancelling ? '中断中...' : '中断'}
                </button>
              )}
            </div>
          </div>
        );
      })}
    </section>
  );
}
