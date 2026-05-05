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

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const j = await fetchActiveJobs();
      if (!cancelled) setJobs(j);
    };
    const id = setInterval(tick, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (jobs.length === 0) return null;

  return (
    <section aria-label="生成ジョブ" className="px-5 space-y-2">
      {jobs.map((j) => (
        <div key={j.job_id} className="card">
          <div className="flex justify-between items-center mb-2">
            <h4 className="font-semibold text-sm truncate pr-2">
              ⚙️ 生成中: {j.title}
            </h4>
            <span className="text-xs text-slate-400 shrink-0">
              {Math.round(j.progress)}%
            </span>
          </div>
          <div className="h-2 rounded bg-bg-elev overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-accent to-purple-500 transition-all"
              style={{ width: `${Math.max(2, j.progress)}%` }}
            />
          </div>
          <p className="text-xs text-slate-400 mt-2">
            {j.step}. {j.step_label}
          </p>
        </div>
      ))}
    </section>
  );
}
