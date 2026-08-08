'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useActiveJobs } from '@/lib/useActiveJobs';

// Routes where the banner stays hidden (auth/oauth flows).
const HIDDEN_PREFIXES = ['/login', '/oauth'];

export default function GlobalProgressBar() {
  const pathname = usePathname() || '';
  const hidden = HIDDEN_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + '/')
  );

  // Shares one interval with ActiveJobs instead of running a second identical
  // poll against the same endpoint. Stays unsubscribed on auth/oauth routes,
  // where the request would only 401.
  const jobs = useActiveJobs(undefined, !hidden);

  if (hidden || jobs.length === 0) return null;

  // 複数走ってる場合は1件目を主表示。件数バッジで補足。
  const j = jobs[0];
  const pct = Math.max(2, Math.round(j.progress));
  const onGenerate = pathname.startsWith('/generate');

  return (
    <div
      role="status"
      aria-live="polite"
      className="sticky top-0 z-50 border-b border-border bg-bg-elev/95 backdrop-blur"
    >
      <Link
        href="/generate"
        className="block px-4 py-2 hover:bg-slate-800/40 transition"
        aria-label="生成中の動画を開く"
      >
        <div className="flex items-center gap-3">
          <span className="text-base shrink-0" aria-hidden>
            ⚙️
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2 text-[11px] leading-tight">
              <span className="font-semibold text-slate-200 truncate">
                生成中: {j.title}
                {jobs.length > 1 && (
                  <span className="ml-1 text-slate-400">
                    +{jobs.length - 1}
                  </span>
                )}
              </span>
              <span className="tabular-nums text-slate-400 shrink-0">
                {Math.round(j.progress)}%
              </span>
            </div>
            <div className="mt-1 h-1.5 rounded bg-bg overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-accent to-purple-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="mt-1 text-[10px] text-slate-500 truncate">
              {j.step}. {j.step_label}
              {!onGenerate && (
                <span className="ml-2 text-slate-600">タップで詳細</span>
              )}
            </p>
          </div>
        </div>
      </Link>
    </div>
  );
}
