'use client';

import { useSyncExternalStore } from 'react';
import type { ActiveJob } from './api';

/**
 * Shared poller for `/api/jobs/active`.
 *
 * `GlobalProgressBar` lives in the root layout and `ActiveJobs` renders on the
 * dashboard, so both were running their own 3s interval against the same
 * endpoint — two requests every three seconds, forever, on a route that reaches
 * the backend through a tunnel. This module keeps a single interval shared by
 * every subscriber and adds two things the per-component timers lacked:
 *
 *  - it backs off to `IDLE_INTERVAL_MS` when nothing is running, and
 *  - it stops entirely while the tab is hidden, catching up on the next
 *    `visibilitychange`.
 */
const ACTIVE_INTERVAL_MS = 3000;
const IDLE_INTERVAL_MS = 15000;

let jobs: ActiveJob[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let inFlight = false;
const subscribers = new Set<() => void>();

function emit() {
  for (const fn of subscribers) fn();
}

async function fetchActiveJobs(): Promise<ActiveJob[]> {
  try {
    const res = await fetch('/api/jobs/active', { cache: 'no-store' });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.jobs) ? data.jobs : [];
  } catch {
    return [];
  }
}

function schedule() {
  if (timer !== null) clearTimeout(timer);
  if (subscribers.size === 0) {
    timer = null;
    return;
  }
  const delay = jobs.length > 0 ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS;
  timer = setTimeout(tick, delay);
}

async function tick() {
  // A hidden tab can't show progress; skip the round-trip and wait for the
  // visibilitychange handler to resume us.
  if (typeof document !== 'undefined' && document.hidden) {
    schedule();
    return;
  }
  if (inFlight) {
    schedule();
    return;
  }
  inFlight = true;
  try {
    const next = await fetchActiveJobs();
    // Only notify when something actually changed, so idle polling doesn't
    // re-render every subscriber on a timer.
    if (!sameJobs(jobs, next)) {
      jobs = next;
      emit();
    }
  } finally {
    inFlight = false;
  }
  schedule();
}

function sameJobs(a: ActiveJob[], b: ActiveJob[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i].job_id !== b[i].job_id) return false;
    if (a[i].progress !== b[i].progress) return false;
    if (a[i].status !== b[i].status) return false;
  }
  return true;
}

function onVisibilityChange() {
  if (!document.hidden && subscribers.size > 0) void tick();
}

function subscribe(onStoreChange: () => void): () => void {
  const first = subscribers.size === 0;
  subscribers.add(onStoreChange);
  if (first) {
    document.addEventListener('visibilitychange', onVisibilityChange);
    void tick();
  }
  return () => {
    subscribers.delete(onStoreChange);
    if (subscribers.size === 0) {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    }
  };
}

const EMPTY: ActiveJob[] = [];

function noopSubscribe(): () => void {
  return () => {};
}

/**
 * Subscribe to the shared active-jobs poll.
 *
 * `initial` seeds the store on first mount so a server-rendered list doesn't
 * flash empty before the first fetch lands. Pass `enabled: false` on routes
 * that shouldn't poll at all (e.g. the logged-out `/login` screen) — the hook
 * still runs, it just never joins the subscriber set.
 */
export function useActiveJobs(
  initial?: ActiveJob[],
  enabled = true
): ActiveJob[] {
  if (enabled && initial && initial.length > 0 && jobs.length === 0) {
    jobs = initial;
  }
  return useSyncExternalStore(
    enabled ? subscribe : noopSubscribe,
    () => (enabled ? jobs : EMPTY),
    () => (enabled ? initial ?? EMPTY : EMPTY)
  );
}

/** Force an immediate refresh — use after mutating a job (e.g. cancel). */
export function refreshActiveJobs(): void {
  void tick();
}
