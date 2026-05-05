'use client';

import { useEffect, useMemo, useState } from 'react';
import type { Channel, CostSummary, HistoryEntry } from '@/lib/api';

const STATUSES = ['', 'pending', 'running', 'completed', 'failed', 'cancelled'];

const USD_TO_JPY = 155; // 概算レート（コストは推定値として表示）

function formatJPY(usd: number): string {
  return `¥${Math.round(usd * USD_TO_JPY).toLocaleString('ja-JP')}`;
}

function formatDate(s: string | null): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('ja-JP', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return s;
  }
}

function formatDuration(sec: number | null): string {
  if (sec == null) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  if (m === 0) return `${s}秒`;
  return `${m}分${s}秒`;
}

export default function HistoryView({
  channels,
  initialHistory,
  initialCost,
}: {
  channels: Channel[];
  initialHistory: HistoryEntry[];
  initialCost: CostSummary | null;
}) {
  const [history, setHistory] = useState(initialHistory);
  const [cost, setCost] = useState(initialCost);
  const [filterChannel, setFilterChannel] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [loading, setLoading] = useState(false);

  const reload = async () => {
    setLoading(true);
    try {
      const q = new URLSearchParams();
      if (filterChannel) q.set('channel_id', filterChannel);
      if (filterStatus) q.set('status', filterStatus);
      if (since) q.set('since', since);
      if (until) q.set('until', until);
      q.set('limit', '300');
      const [h, c] = await Promise.all([
        fetch(`/api/history?${q}`, { cache: 'no-store' }).then((r) => r.json()),
        fetch('/api/history/cost-summary', { cache: 'no-store' }).then((r) =>
          r.json()
        ),
      ]);
      setHistory(h.history || []);
      setCost(c);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterChannel, filterStatus, since, until]);

  const monthsForChart = useMemo(() => {
    if (!cost || !cost.by_month) return [];
    return cost.by_month.slice(0, 6).reverse();
  }, [cost]);

  const maxMonthCost = useMemo(
    () => Math.max(0.0001, ...monthsForChart.map((m) => m.cost_usd || 0)),
    [monthsForChart]
  );

  const channelName = (id: string): string =>
    channels.find((c) => c.id === id)?.name || id;

  return (
    <div className="px-5 space-y-4">
      {/* コストサマリ */}
      {cost && (
        <section className="card">
          <h2 className="font-bold mb-3">💰 コストサマリ（推定）</h2>
          <div className="grid grid-cols-3 gap-2 text-center mb-4">
            <SummaryTile
              label="今日"
              value={formatJPY(cost.today.cost_usd)}
              sub={`${cost.today.calls}回`}
            />
            <SummaryTile
              label="今月"
              value={formatJPY(cost.this_month.cost_usd)}
              sub={`${cost.this_month.calls}回`}
              highlight
            />
            <SummaryTile
              label="累計"
              value={formatJPY(cost.total.cost_usd)}
              sub={`${cost.total.calls}回`}
            />
          </div>

          {monthsForChart.length > 0 && (
            <div>
              <h3 className="text-xs text-slate-400 mb-2">月別推移</h3>
              <div className="flex items-end gap-2 h-32">
                {monthsForChart.map((m) => {
                  const h = Math.max(
                    4,
                    ((m.cost_usd || 0) / maxMonthCost) * 100
                  );
                  return (
                    <div
                      key={m.month}
                      className="flex-1 flex flex-col items-center gap-1 min-w-0"
                    >
                      <span className="text-[10px] text-slate-300 font-bold whitespace-nowrap">
                        {formatJPY(m.cost_usd || 0)}
                      </span>
                      <div
                        className="w-full bg-gradient-to-t from-accent to-purple-500 rounded-t"
                        style={{ height: `${h}%` }}
                        aria-label={`${m.month}: ${formatJPY(m.cost_usd)}`}
                      />
                      <span className="text-[10px] text-slate-500 whitespace-nowrap">
                        {m.month.slice(5)}月
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {cost.by_channel && Object.keys(cost.by_channel).length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs text-slate-400 mb-2">チャンネル別</h3>
              <ul className="space-y-1 text-sm">
                {Object.entries(cost.by_channel).map(([id, m]) => (
                  <li key={id} className="flex justify-between">
                    <span className="text-slate-300 truncate">{channelName(id)}</span>
                    <span className="text-slate-400 tabular-nums">
                      {formatJPY(m.cost_usd)} ({m.calls}回)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* フィルター */}
      <section className="card space-y-3">
        <h2 className="font-bold">🔍 フィルター</h2>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">チャンネル</label>
            <select
              className="input"
              value={filterChannel}
              onChange={(e) => setFilterChannel(e.target.value)}
            >
              <option value="">すべて</option>
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">ステータス</label>
            <select
              className="input"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s || 'すべて'}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">開始日</label>
            <input
              type="date"
              className="input"
              value={since}
              onChange={(e) => setSince(e.target.value)}
            />
          </div>
          <div>
            <label className="label">終了日</label>
            <input
              type="date"
              className="input"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
            />
          </div>
        </div>
      </section>

      {/* 履歴一覧 */}
      <section className="card">
        <h2 className="font-bold mb-3">
          📋 ジョブ履歴 {loading && <span className="text-xs text-slate-500 ml-2">読込中…</span>}
        </h2>
        {history.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-6">
            該当する履歴がありません
          </p>
        ) : (
          <ul className="space-y-2">
            {history.map((h) => (
              <li
                key={h.job_id}
                className="bg-bg-elev/60 rounded-lg p-3 border border-border/40"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-slate-100 truncate">
                      {h.title || '(無題)'}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      📺 {channelName(h.channel_id)} · {formatDate(h.created_at)}
                    </p>
                    <p className="text-[10px] text-slate-500 mt-0.5">
                      所要: {formatDuration(h.duration_seconds)}
                      {' · '}ID: <code>{h.job_id?.slice(0, 8)}</code>
                    </p>
                    {h.error && (
                      <p className="text-[10px] text-red-400 mt-1 truncate">
                        ⚠️ {h.error}
                      </p>
                    )}
                  </div>
                  <StatusBadge status={h.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SummaryTile({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-lg p-3 ${
        highlight
          ? 'bg-accent/15 border border-accent/40'
          : 'bg-bg-elev border border-border/40'
      }`}
    >
      <div className="text-[10px] text-slate-400 uppercase">{label}</div>
      <div className="text-base font-bold tabular-nums mt-1">{value}</div>
      <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    completed: { label: '✅ 完了', cls: 'bg-emerald-700/40 text-emerald-300' },
    running: { label: '⚙️ 実行中', cls: 'bg-accent/30 text-accent' },
    pending: { label: '⏳ 待機', cls: 'bg-slate-700/40 text-slate-300' },
    failed: { label: '❌ 失敗', cls: 'bg-red-700/40 text-red-300' },
    cancelled: { label: '⛔ 中断', cls: 'bg-slate-700/40 text-slate-400' },
  };
  const m = map[status] || { label: status, cls: 'bg-bg-elev text-slate-400' };
  return (
    <span className={`badge shrink-0 ${m.cls}`}>{m.label}</span>
  );
}
