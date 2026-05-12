'use client';

import { useEffect, useMemo, useState } from 'react';
import type { Channel, CostSummary, HistoryEntry } from '@/lib/api';

const STATUSES = ['', 'pending', 'running', 'completed', 'failed', 'cancelled'];

const USD_TO_JPY = 155; // 概算レート（コストは推定値として表示）

function formatJPY(usd: number): string {
  return `¥${Math.round(usd * USD_TO_JPY).toLocaleString('ja-JP')}`;
}

const PROVIDER_META: Record<string, { label: string; from: string; to: string; tint: string }> = {
  openai:    { label: 'OpenAI (GPT / DALL·E)', from: 'from-emerald-500',  to: 'to-teal-400',  tint: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300' },
  anthropic: { label: 'Anthropic (Claude)',     from: 'from-orange-500',  to: 'to-amber-400', tint: 'bg-orange-500/15 border-orange-500/30 text-orange-300' },
  other:     { label: 'その他',                  from: 'from-slate-500',   to: 'to-slate-400', tint: 'bg-slate-500/15 border-slate-500/30 text-slate-300' },
};

const PURPOSE_LABELS: Record<string, string> = {
  scenario:                   'シナリオ生成',
  scenario_claude:            'シナリオ生成 (Claude)',
  scenario_evaluation:        'シナリオ評価',
  comment_analysis:           'コメント分析',
  comment_demand_extraction:  'コメント需要抽出',
  trend_relevance:            'トレンド分析',
  competitor_analysis:        '競合分析',
  success_pattern:            '成功パターン分析',
  retention_analysis:         'リテンション分析',
  ab_test:                    'A/Bテスト',
  ab_test_generate:           'A/B 生成',
  ab_test_score:              'A/B 採点',
  illustration:               '画像生成',
  series_suggest:             'シリーズ提案',
  blind_compare:              'モデル比較',
  '(unspecified)':            'その他/未分類',
};

function purposeLabel(key: string): string {
  return PURPOSE_LABELS[key] || key;
}

function providerOfModel(model: string): 'openai' | 'anthropic' | 'other' {
  const m = model.toLowerCase();
  if (m.startsWith('claude')) return 'anthropic';
  if (m.startsWith('gpt') || m.startsWith('dall-e') || m.startsWith('dalle')) return 'openai';
  return 'other';
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

  // 日別チャート: バックエンドが直近14日昇順で返す。無ければ by_day(オブジェクト) 互換でフォールバック。
  const daysForChart = useMemo(() => {
    if (!cost) return [] as Array<{ date: string; cost_usd: number; calls: number }>;
    if (Array.isArray(cost.by_day)) return cost.by_day.slice(-14);
    return [];
  }, [cost]);

  const maxDayCost = useMemo(
    () => Math.max(0.0001, ...daysForChart.map((d) => d.cost_usd || 0)),
    [daysForChart]
  );

  // プロバイダー別 (OpenAI vs Anthropic): バックエンド優先、無ければ by_model から導出
  const providerBreakdown = useMemo(() => {
    if (!cost) return [] as Array<{ key: string; label: string; cost: number; calls: number; tokens: number; from: string; to: string; tint: string }>;
    const acc: Record<string, { cost: number; calls: number; tokens: number }> = {};
    if (cost.by_provider && Object.keys(cost.by_provider).length > 0) {
      for (const [k, m] of Object.entries(cost.by_provider)) {
        acc[k] = { cost: m.cost_usd || 0, calls: m.calls || 0, tokens: (m.prompt_tokens || 0) + (m.completion_tokens || 0) };
      }
    } else if (cost.by_model) {
      for (const [model, m] of Object.entries(cost.by_model)) {
        const p = providerOfModel(model);
        const slot = acc[p] || (acc[p] = { cost: 0, calls: 0, tokens: 0 });
        slot.cost += m.cost_usd || 0;
        slot.calls += m.calls || 0;
        slot.tokens += (m.prompt_tokens || 0) + (m.completion_tokens || 0);
      }
    }
    return Object.entries(acc)
      .map(([k, v]) => {
        const meta = PROVIDER_META[k] || PROVIDER_META.other;
        return { key: k, label: meta.label, cost: v.cost, calls: v.calls, tokens: v.tokens, from: meta.from, to: meta.to, tint: meta.tint };
      })
      .sort((a, b) => b.cost - a.cost);
  }, [cost]);

  const totalProviderCost = useMemo(
    () => Math.max(0.0001, providerBreakdown.reduce((s, p) => s + p.cost, 0)),
    [providerBreakdown]
  );

  // 用途別
  const purposeBreakdown = useMemo(() => {
    if (!cost || !cost.by_purpose) return [] as Array<{ key: string; label: string; cost: number; calls: number }>;
    return Object.entries(cost.by_purpose)
      .map(([k, m]) => ({ key: k, label: purposeLabel(k), cost: m.cost_usd || 0, calls: m.calls || 0 }))
      .sort((a, b) => b.cost - a.cost);
  }, [cost]);

  const totalPurposeCost = useMemo(
    () => Math.max(0.0001, purposeBreakdown.reduce((s, p) => s + p.cost, 0)),
    [purposeBreakdown]
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

          {providerBreakdown.length > 0 && (
            <div className="mb-4">
              <h3 className="text-xs text-slate-400 mb-2">プロバイダー別 (OpenAI vs Anthropic)</h3>
              <div className="flex h-2 w-full rounded-full overflow-hidden bg-bg-elev mb-2">
                {providerBreakdown.map((p) => {
                  const w = (p.cost / totalProviderCost) * 100;
                  if (w <= 0) return null;
                  return (
                    <div
                      key={p.key}
                      className={`bg-gradient-to-r ${p.from} ${p.to}`}
                      style={{ width: `${w}%` }}
                      aria-label={`${p.label}: ${formatJPY(p.cost)}`}
                    />
                  );
                })}
              </div>
              <ul className="space-y-1 text-sm">
                {providerBreakdown.map((p) => {
                  const pct = (p.cost / totalProviderCost) * 100;
                  return (
                    <li key={p.key} className="flex items-center justify-between gap-2">
                      <span className={`badge text-[10px] ${p.tint}`}>{p.label}</span>
                      <span className="text-slate-400 tabular-nums text-xs">
                        {formatJPY(p.cost)} ({pct.toFixed(0)}% / {p.calls}回)
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

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

          {daysForChart.length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs text-slate-400 mb-2">日別推移 (直近14日)</h3>
              <div className="flex items-end gap-1 h-24">
                {daysForChart.map((d) => {
                  const h = Math.max(2, ((d.cost_usd || 0) / maxDayCost) * 100);
                  return (
                    <div
                      key={d.date}
                      className="flex-1 flex flex-col items-center gap-0.5 min-w-0"
                      title={`${d.date}: ${formatJPY(d.cost_usd)} / ${d.calls}回`}
                    >
                      <div
                        className="w-full bg-gradient-to-t from-emerald-500 to-orange-400 rounded-t"
                        style={{ height: `${h}%` }}
                        aria-label={`${d.date}: ${formatJPY(d.cost_usd)}`}
                      />
                      <span className="text-[9px] text-slate-500 whitespace-nowrap">
                        {d.date.slice(8)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {purposeBreakdown.length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs text-slate-400 mb-2">用途別</h3>
              <ul className="space-y-1.5 text-sm">
                {purposeBreakdown.slice(0, 10).map((p) => {
                  const pct = (p.cost / totalPurposeCost) * 100;
                  return (
                    <li key={p.key} className="space-y-0.5">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-300 truncate">{p.label}</span>
                        <span className="text-slate-400 tabular-nums">
                          {formatJPY(p.cost)} ({p.calls}回)
                        </span>
                      </div>
                      <div className="h-1 w-full bg-bg-elev rounded overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-accent to-purple-500"
                          style={{ width: `${Math.max(2, pct)}%` }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
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

          {cost.by_model && Object.keys(cost.by_model).length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs text-slate-400 mb-2">モデル別</h3>
              <ul className="space-y-1 text-sm">
                {Object.entries(cost.by_model)
                  .sort((a, b) => (b[1].cost_usd || 0) - (a[1].cost_usd || 0))
                  .map(([model, m]) => {
                    const p = providerOfModel(model);
                    const meta = PROVIDER_META[p];
                    return (
                      <li key={model} className="flex justify-between items-center gap-2">
                        <span className="text-slate-300 truncate flex items-center gap-1.5">
                          <span className={`badge text-[9px] ${meta.tint}`}>{p === 'anthropic' ? 'Claude' : p === 'openai' ? 'GPT' : '?'}</span>
                          <code className="text-xs text-slate-400">{model}</code>
                        </span>
                        <span className="text-slate-400 tabular-nums text-xs">
                          {formatJPY(m.cost_usd)} ({m.calls}回)
                        </span>
                      </li>
                    );
                  })}
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
