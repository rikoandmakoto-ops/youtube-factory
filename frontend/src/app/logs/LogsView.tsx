'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { LogsResponse } from '@/lib/api';

const LEVEL_OPTIONS: { value: '' | 'error' | 'warn' | 'info'; label: string }[] = [
  { value: '', label: '全て' },
  { value: 'error', label: 'エラー' },
  { value: 'warn', label: '警告' },
  { value: 'info', label: '情報' },
];

function classifyLine(line: string): 'error' | 'warn' | 'info' | 'plain' {
  const low = line.toLowerCase();
  if (
    low.includes('error') ||
    low.includes('traceback') ||
    low.includes('exception') ||
    line.includes('❌')
  )
    return 'error';
  if (low.includes('warn') || line.includes('⚠️')) return 'warn';
  if (low.startsWith('info:') || line.startsWith('INFO:')) return 'info';
  return 'plain';
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export default function LogsView({ initial }: { initial: LogsResponse | null }) {
  const [data, setData] = useState<LogsResponse | null>(initial);
  const [filter, setFilter] = useState('');
  const [level, setLevel] = useState<'' | 'error' | 'warn' | 'info'>('');
  const [lines, setLines] = useState(200);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const q = new URLSearchParams();
      q.set('lines', String(lines));
      if (filter) q.set('filter', filter);
      if (level) q.set('level', level);
      const res = await fetch(`/api/logs?${q}`, { cache: 'no-store' });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.error || 'failed');
      setData(body as LogsResponse);
    } catch (e) {
      setErr((e as Error).message || 'failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, level, lines]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, filter, level, lines]);

  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [data, autoScroll]);

  const stats = useMemo(() => {
    const out = { error: 0, warn: 0, info: 0, plain: 0 };
    (data?.lines || []).forEach((l) => {
      out[classifyLine(l)]++;
    });
    return out;
  }, [data]);

  return (
    <div className="px-5">
      <div className="rounded-xl bg-bg-elev border border-border p-3 mb-3 text-xs text-slate-300 flex flex-wrap gap-x-4 gap-y-1">
        <span>
          📂 <span className="font-mono">{data?.path || '(no log)'}</span>
        </span>
        {data?.size_bytes != null && <span>📦 {formatBytes(data.size_bytes)}</span>}
        {data?.mtime && (
          <span>
            🕒 {new Date(data.mtime * 1000).toLocaleString('ja-JP')}
          </span>
        )}
        <span className="text-red-300">❌ {stats.error}</span>
        <span className="text-amber-300">⚠️ {stats.warn}</span>
        <span className="text-sky-300">ℹ️ {stats.info}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 mb-3">
        <input
          type="text"
          placeholder="🔍 フィルタ (部分一致)"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="bg-bg-elev border border-border rounded-lg px-3 py-2 text-sm"
        />
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value as typeof level)}
          className="bg-bg-elev border border-border rounded-lg px-3 py-2 text-sm"
        >
          {LEVEL_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              レベル: {o.label}
            </option>
          ))}
        </select>
        <select
          value={lines}
          onChange={(e) => setLines(Number(e.target.value))}
          className="bg-bg-elev border border-border rounded-lg px-3 py-2 text-sm"
        >
          {[100, 200, 500, 1000, 2000].map((n) => (
            <option key={n} value={n}>
              最新 {n} 行
            </option>
          ))}
        </select>
        <div className="flex items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            自動更新
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            自動スクロール
          </label>
          <button
            onClick={load}
            className="ml-auto rounded-md bg-slate-700 hover:bg-slate-600 px-2 py-1"
            disabled={loading}
          >
            {loading ? '...' : '更新'}
          </button>
        </div>
      </div>

      {err && (
        <div className="mb-2 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {err}
        </div>
      )}

      <div
        ref={scrollRef}
        className="rounded-xl bg-black/60 border border-border h-[68vh] overflow-y-auto font-mono text-[11.5px] leading-snug"
      >
        {(data?.lines || []).length === 0 ? (
          <div className="text-slate-400 p-4">
            (ログ行はありません{data?.note ? `: ${data.note}` : ''})
          </div>
        ) : (
          (data?.lines || []).map((line, i) => {
            const kind = classifyLine(line);
            const cls =
              kind === 'error'
                ? 'text-red-300 bg-red-500/10'
                : kind === 'warn'
                ? 'text-amber-300 bg-amber-500/5'
                : kind === 'info'
                ? 'text-sky-300'
                : 'text-slate-200';
            return (
              <div
                key={i}
                className={`px-3 py-[1px] whitespace-pre-wrap break-words ${cls}`}
              >
                {line || ' '}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
