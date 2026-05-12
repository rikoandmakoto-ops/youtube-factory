'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import type {
  ABTest,
  AbReconciliationResponse,
  AnalyticsOverview,
  AnalyticsVideoMetric,
  Channel,
  EvaluationsListResponse,
  ImprovementEntry,
  ImprovementsListResponse,
  ModelPerformanceResponse,
  ScenarioEvaluation,
  TrendsResponse,
} from '@/lib/api';

type SectionError = { section: string; message: string };

type Props = {
  channels: Channel[];
  channelId: string;
  initialOverview: AnalyticsOverview | null;
  initialVideos: AnalyticsVideoMetric[];
  initialTrends: TrendsResponse | null;
  initialABTests: ABTest[];
  initialEvaluations: EvaluationsListResponse | null;
  initialAbReconciliation: AbReconciliationResponse | null;
  initialImprovements: ImprovementsListResponse | null;
  initialModelPerformance: ModelPerformanceResponse | null;
  initialErrors: SectionError[];
};

type TabId = 'overview' | 'evaluations' | 'reconciliation' | 'improvements';

type SyncState =
  | { phase: 'idle' }
  | { phase: 'running'; startedAt: number }
  | { phase: 'success'; finishedAt: number; summary: string }
  | { phase: 'error'; finishedAt: number; message: string };

function formatNumber(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—';
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString('ja-JP');
}

function formatPercent(p: number | undefined | null, digits = 1): string {
  if (p == null || Number.isNaN(p)) return '—';
  // Backend may emit either a 0–1 ratio or already a percentage. Treat
  // anything <= 1 as a ratio and convert; otherwise assume it is %.
  const pct = Math.abs(p) <= 1 ? p * 100 : p;
  return `${pct.toFixed(digits)}%`;
}

function formatMinutes(min: number | undefined | null): string {
  if (min == null || Number.isNaN(min)) return '—';
  if (min >= 60) {
    const h = Math.floor(min / 60);
    const m = Math.round(min - h * 60);
    return `${h}h ${m}m`;
  }
  return `${Math.round(min)}m`;
}

function formatSeconds(sec: number | undefined | null): string {
  if (sec == null || Number.isNaN(sec)) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec - m * 60);
  if (m === 0) return `${s}秒`;
  return `${m}分${s.toString().padStart(2, '0')}秒`;
}

function formatDateTime(s: string | null | undefined): string {
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

export default function AnalyticsView({
  channels,
  channelId,
  initialOverview,
  initialVideos,
  initialTrends,
  initialABTests,
  initialEvaluations,
  initialAbReconciliation,
  initialImprovements,
  initialModelPerformance,
  initialErrors,
}: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [overview, setOverview] = useState(initialOverview);
  const [videos, setVideos] = useState(initialVideos);
  const [trends, setTrends] = useState(initialTrends);
  const [abTests, setABTests] = useState(initialABTests);
  const [evaluations, setEvaluations] =
    useState<EvaluationsListResponse | null>(initialEvaluations);
  const [abReconciliation, setAbReconciliation] =
    useState<AbReconciliationResponse | null>(initialAbReconciliation);
  const [improvements, setImprovements] =
    useState<ImprovementsListResponse | null>(initialImprovements);
  const [modelPerformance, setModelPerformance] =
    useState<ModelPerformanceResponse | null>(initialModelPerformance);
  const [errors, setErrors] = useState<SectionError[]>(initialErrors);
  const [tab, setTab] = useState<TabId>(() => {
    const t = searchParams.get('tab') as TabId | null;
    if (t === 'evaluations' || t === 'reconciliation' || t === 'improvements')
      return t;
    return 'overview';
  });

  const [sync, setSync] = useState<SyncState>({ phase: 'idle' });
  const [refreshing, setRefreshing] = useState(false);

  const channel = useMemo(
    () => channels.find((c) => c.id === channelId) || null,
    [channels, channelId]
  );

  const handleChannelChange = (id: string) => {
    const sp = new URLSearchParams(searchParams.toString());
    sp.set('channel', id);
    router.push(`/analytics?${sp.toString()}`);
  };

  const switchTab = (next: TabId) => {
    setTab(next);
    const sp = new URLSearchParams(searchParams.toString());
    sp.set('tab', next);
    router.replace(`/analytics?${sp.toString()}`);
  };

  const reload = async () => {
    setRefreshing(true);
    setErrors([]);
    const collect = (section: string, message: string) =>
      setErrors((prev) => [...prev, { section, message }]);

    const [ov, vid, tr, ab, ev, rc, im, mp] = await Promise.allSettled([
      fetch(`/api/analytics/channel/${encodeURIComponent(channelId)}/overview?days=30`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/analytics/videos/${encodeURIComponent(channelId)}?limit=50`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/trends/${encodeURIComponent(channelId)}?count=5`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/ab-test?channel_id=${encodeURIComponent(channelId)}&limit=20`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/evaluations/${encodeURIComponent(channelId)}?limit=100`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/ab-reconciliation/${encodeURIComponent(channelId)}?limit=200`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/improvements/${encodeURIComponent(channelId)}?limit=100`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/model-performance/${encodeURIComponent(channelId)}?recent_runs=20`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
    ]);

    if (ov.status === 'fulfilled') setOverview(ov.value as AnalyticsOverview);
    else collect('概要', '取得に失敗しました');
    if (vid.status === 'fulfilled') setVideos((vid.value as { items: AnalyticsVideoMetric[] }).items || []);
    else collect('動画一覧', '取得に失敗しました');
    if (tr.status === 'fulfilled') setTrends(tr.value as TrendsResponse);
    else collect('トレンド', '取得に失敗しました');
    if (ab.status === 'fulfilled') setABTests((ab.value as { items: ABTest[] }).items || []);
    else collect('AB テスト', '取得に失敗しました');
    if (ev.status === 'fulfilled')
      setEvaluations(ev.value as EvaluationsListResponse);
    else collect('シナリオ評価', '取得に失敗しました');
    if (rc.status === 'fulfilled')
      setAbReconciliation(rc.value as AbReconciliationResponse);
    else collect('AB 答え合わせ', '取得に失敗しました');
    if (im.status === 'fulfilled')
      setImprovements(im.value as ImprovementsListResponse);
    else collect('改善キュー', '取得に失敗しました');
    if (mp.status === 'fulfilled')
      setModelPerformance(mp.value as ModelPerformanceResponse);
    else collect('AIモデル比較', '取得に失敗しました');

    setRefreshing(false);
  };

  const triggerEvaluations = async () => {
    try {
      const res = await fetch(
        `/api/evaluations/${encodeURIComponent(channelId)}/run`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: 'シナリオ評価',
          message: e instanceof Error ? e.message : '評価実行に失敗',
        },
      ]);
    }
  };

  const triggerReconciliation = async () => {
    try {
      const res = await fetch(
        `/api/ab-reconciliation/${encodeURIComponent(channelId)}/run`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: 'AB 答え合わせ',
          message: e instanceof Error ? e.message : '実行に失敗',
        },
      ]);
    }
  };

  const triggerImprovementDetect = async () => {
    try {
      const res = await fetch(
        `/api/improvements/${encodeURIComponent(channelId)}/run`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: '改善キュー',
          message: e instanceof Error ? e.message : '実行に失敗',
        },
      ]);
    }
  };

  const regenerateForVideo = async (videoId: string) => {
    try {
      const res = await fetch(
        `/api/improvements/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/regenerate`,
        { method: 'POST' }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: '改善キュー',
          message: e instanceof Error ? e.message : '再生成に失敗',
        },
      ]);
    }
  };

  const setEntryStatus = async (
    videoId: string,
    status: 'pending' | 'applied' | 'dismissed'
  ) => {
    try {
      const res = await fetch(
        `/api/improvements/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/status`,
        {
          method: 'PUT',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ status }),
        }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: '改善キュー',
          message: e instanceof Error ? e.message : 'ステータス更新に失敗',
        },
      ]);
    }
  };

  const handleSync = async () => {
    setSync({ phase: 'running', startedAt: Date.now() });
    try {
      const res = await fetch(
        `/api/analytics/sync/${encodeURIComponent(channelId)}`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({ error: `${res.status}` }));
        throw new Error(body.error || `同期失敗 (${res.status})`);
      }
      const data = await res.json();
      const videoCount =
        (data?.videos?.count as number | undefined) ??
        (Array.isArray(data?.videos?.items) ? data.videos.items.length : 0);
      const commentCount = Array.isArray(data?.comments)
        ? data.comments.length
        : 0;
      setSync({
        phase: 'success',
        finishedAt: Date.now(),
        summary: `動画 ${videoCount} 件 / コメント分析 ${commentCount} 件`,
      });
      await reload();
    } catch (e) {
      setSync({
        phase: 'error',
        finishedAt: Date.now(),
        message: e instanceof Error ? e.message : String(e),
      });
    }
  };

  // 自動的にエラーバナーを消したり再読み込みしたりはしない。
  // ユーザーが明示的にボタンを押すまで初期状態を保持する。

  // 同期中はバックエンド側で重い処理が走るので、ボタンは無効化のみ。
  // ポーリングは行わない（完了レスポンスを待つ）。
  useEffect(() => {
    if (sync.phase !== 'success') return;
    const t = setTimeout(() => setSync({ phase: 'idle' }), 8000);
    return () => clearTimeout(t);
  }, [sync]);

  return (
    <div className="px-5 space-y-4">
      {/* チャンネル選択 + 同期 */}
      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-bold">🎛️ チャンネル</h2>
          <button
            className="btn-secondary py-1.5 px-3 text-xs"
            onClick={reload}
            disabled={refreshing}
            aria-busy={refreshing}
          >
            {refreshing ? '更新中…' : '↻ 表示を更新'}
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
          <div>
            <label className="label">対象チャンネル</label>
            <select
              className="input"
              value={channelId}
              onChange={(e) => handleChannelChange(e.target.value)}
            >
              {channels.length === 0 && (
                <option value={channelId}>{channelId}</option>
              )}
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.id})
                </option>
              ))}
            </select>
            {channel && (
              <p className="text-xs text-slate-500 mt-1 truncate">
                {channel.concept || '—'}
              </p>
            )}
          </div>
          <div className="flex flex-col items-stretch gap-2">
            <button
              className="btn-primary py-2 px-4 text-sm"
              onClick={handleSync}
              disabled={sync.phase === 'running'}
              aria-busy={sync.phase === 'running'}
            >
              {sync.phase === 'running'
                ? '🔄 同期中…'
                : '🔄 Analytics を同期'}
            </button>
            <SyncStatusLine state={sync} />
          </div>
        </div>
      </section>

      {errors.length > 0 && (
        <section className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300 space-y-0.5">
          {errors.map((err, i) => (
            <p key={i}>
              ⚠️ <strong>{err.section}</strong>: {err.message}
            </p>
          ))}
          <p className="text-xs text-red-300/70 mt-1">
            初回は「Analytics を同期」を押してデータを取り込んでください。
          </p>
        </section>
      )}

      <TabBar tab={tab} onChange={switchTab} />

      {tab === 'overview' && (
        <>
          <OverviewSection overview={overview} />
          <VideosSection videos={videos} />
          <TrendsSection trends={trends} />
          <ABTestsSection items={abTests} />
        </>
      )}

      {tab === 'evaluations' && (
        <EvaluationsTab
          data={evaluations}
          modelPerformance={modelPerformance}
          onRun={triggerEvaluations}
        />
      )}

      {tab === 'reconciliation' && (
        <ReconciliationTab
          data={abReconciliation}
          onRun={triggerReconciliation}
        />
      )}

      {tab === 'improvements' && (
        <ImprovementsTab
          data={improvements}
          onRun={triggerImprovementDetect}
          onRegenerate={regenerateForVideo}
          onSetStatus={setEntryStatus}
        />
      )}
    </div>
  );
}

function TabBar({
  tab,
  onChange,
}: {
  tab: TabId;
  onChange: (next: TabId) => void;
}) {
  const items: { id: TabId; label: string }[] = [
    { id: 'overview', label: '概要' },
    { id: 'evaluations', label: 'シナリオ評価' },
    { id: 'reconciliation', label: 'AB 実績' },
    { id: 'improvements', label: '改善キュー' },
  ];
  return (
    <div className="flex gap-1 overflow-x-auto -mx-1 px-1">
      {items.map((it) => (
        <button
          key={it.id}
          onClick={() => onChange(it.id)}
          className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-xs font-semibold border ${
            tab === it.id
              ? 'bg-accent/20 border-accent/60 text-accent'
              : 'bg-bg-elev/40 border-border/40 text-slate-300 hover:text-slate-100'
          }`}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

function SyncStatusLine({ state }: { state: SyncState }) {
  if (state.phase === 'idle') {
    return (
      <span className="text-[11px] text-slate-500 text-right">
        YouTube Analytics API から最新値を取得
      </span>
    );
  }
  if (state.phase === 'running') {
    return (
      <span className="text-[11px] text-accent text-right">
        … 最大 1 分ほどかかります
      </span>
    );
  }
  if (state.phase === 'success') {
    return (
      <span className="text-[11px] text-emerald-300 text-right">
        ✅ 同期完了 — {state.summary}
      </span>
    );
  }
  return (
    <span className="text-[11px] text-red-300 text-right">
      ❌ {state.message}
    </span>
  );
}

function OverviewSection({ overview }: { overview: AnalyticsOverview | null }) {
  const totals = overview?.totals;
  const daily = overview?.daily || [];

  // Daily metrics may carry impressions / ctr / avg_view_duration. Compute
  // weighted averages where possible; fall back to simple means otherwise.
  const impressionsSum = daily.reduce(
    (acc, d) => acc + (Number(d.impressions) || 0),
    0
  );
  const weightedCtr =
    impressionsSum > 0
      ? daily.reduce(
          (acc, d) =>
            acc + (Number(d.ctr) || 0) * (Number(d.impressions) || 0),
          0
        ) / impressionsSum
      : null;

  const viewsSum = totals?.views ?? 0;
  const watchTimeMinutes = totals?.watch_time_minutes ?? 0;
  const avgViewSeconds =
    viewsSum > 0 ? (watchTimeMinutes * 60) / viewsSum : null;

  return (
    <section className="card">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="font-bold">📊 直近 30 日の概要</h2>
        <span className="text-[10px] text-slate-500">
          {daily.length > 0
            ? `${daily[0].date} 〜 ${daily[daily.length - 1].date}`
            : '同期前'}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <KpiCard label="視聴数" value={formatNumber(viewsSum)} sub="views" />
        <KpiCard
          label="インプレッション"
          value={impressionsSum > 0 ? formatNumber(impressionsSum) : '—'}
          sub="impressions"
        />
        <KpiCard
          label="CTR"
          value={weightedCtr != null ? formatPercent(weightedCtr) : '—'}
          sub="click-through rate"
        />
        <KpiCard
          label="視聴時間"
          value={formatMinutes(watchTimeMinutes)}
          sub="watch time"
        />
        <KpiCard
          label="平均視聴時間"
          value={formatSeconds(avgViewSeconds)}
          sub="per view"
        />
        <KpiCard
          label="登録者 純増"
          value={
            totals
              ? `${totals.net_subscribers >= 0 ? '+' : ''}${formatNumber(
                  totals.net_subscribers
                )}`
              : '—'
          }
          sub={`+${formatNumber(totals?.subscribers_gained ?? 0)} / -${formatNumber(
            totals?.subscribers_lost ?? 0
          )}`}
        />
      </div>

      {daily.length > 1 && <DailyViewsChart points={daily} />}
    </section>
  );
}

function KpiCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
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
      <div className="text-[10px] text-slate-400 uppercase tracking-wide">
        {label}
      </div>
      <div className="text-base font-bold tabular-nums mt-1 truncate">
        {value}
      </div>
      {sub && (
        <div className="text-[10px] text-slate-500 mt-0.5 truncate">{sub}</div>
      )}
    </div>
  );
}

function DailyViewsChart({
  points,
}: {
  points: AnalyticsOverview['daily'];
}) {
  const recent = points.slice(-30);
  const max = Math.max(1, ...recent.map((p) => Number(p.views) || 0));
  return (
    <div className="mt-4">
      <h3 className="text-xs text-slate-400 mb-2">日別 視聴数</h3>
      <div className="flex items-end gap-1 h-24">
        {recent.map((p) => {
          const v = Number(p.views) || 0;
          const h = Math.max(2, (v / max) * 100);
          return (
            <div
              key={p.date}
              className="flex-1 bg-gradient-to-t from-accent to-purple-500 rounded-t min-w-[3px]"
              style={{ height: `${h}%` }}
              title={`${p.date}: ${formatNumber(v)} views`}
            />
          );
        })}
      </div>
    </div>
  );
}

function VideosSection({ videos }: { videos: AnalyticsVideoMetric[] }) {
  const sorted = useMemo(
    () =>
      [...videos].sort(
        (a, b) => (Number(b.views) || 0) - (Number(a.views) || 0)
      ),
    [videos]
  );

  return (
    <section className="card">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="font-bold">🎞️ 動画別パフォーマンス</h2>
        <span className="text-[10px] text-slate-500">
          {sorted.length} 本
        </span>
      </div>
      {sorted.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">
          まだ動画メトリクスがありません。「Analytics を同期」を実行してください。
        </p>
      ) : (
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase text-slate-500">
              <tr className="border-b border-border/40">
                <th className="text-left font-semibold py-2 pr-2">タイトル</th>
                <th className="text-right font-semibold py-2 px-2 tabular-nums">
                  視聴
                </th>
                <th className="text-right font-semibold py-2 px-2 tabular-nums">
                  CTR
                </th>
                <th className="text-right font-semibold py-2 px-2 tabular-nums">
                  平均視聴
                </th>
                <th className="text-right font-semibold py-2 pl-2 tabular-nums">
                  維持率
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((v) => (
                <tr
                  key={v.video_id}
                  className="border-b border-border/20 hover:bg-bg-elev/40"
                >
                  <td className="py-2 pr-2">
                    <div className="text-slate-100 truncate max-w-[14rem]">
                      {v.title || v.video_id}
                    </div>
                    <div className="text-[10px] text-slate-500 truncate">
                      {v.published_at
                        ? formatDateTime(v.published_at)
                        : v.video_id}
                    </div>
                  </td>
                  <td className="text-right tabular-nums py-2 px-2">
                    {formatNumber(v.views)}
                  </td>
                  <td className="text-right tabular-nums py-2 px-2">
                    {formatPercent(v.ctr)}
                  </td>
                  <td className="text-right tabular-nums py-2 px-2">
                    {formatSeconds(v.average_view_duration_seconds)}
                  </td>
                  <td className="text-right tabular-nums py-2 pl-2">
                    {formatPercent(v.average_view_percentage)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function TrendsSection({ trends }: { trends: TrendsResponse | null }) {
  const keywords = trends?.trends?.keywords ?? [];
  const related = trends?.trends?.related_keywords ?? [];
  const trendingVideos = trends?.trends?.trending_videos ?? [];
  const themes = trends?.themes ?? [];

  return (
    <section className="card">
      <h2 className="font-bold mb-3">🔥 トレンド</h2>
      {keywords.length === 0 &&
      related.length === 0 &&
      trendingVideos.length === 0 &&
      themes.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">
          トレンドデータが取得できませんでした。
        </p>
      ) : (
        <div className="space-y-4">
          {keywords.length > 0 && (
            <KeywordCloud title="急上昇キーワード" items={keywords} />
          )}
          {related.length > 0 && (
            <KeywordCloud title="チャンネル関連語" items={related} />
          )}
          {themes.length > 0 && (
            <div>
              <h3 className="text-xs text-slate-400 mb-2">提案テーマ</h3>
              <ul className="space-y-2">
                {themes.map((t, i) => (
                  <li
                    key={i}
                    className="bg-bg-elev/60 rounded-lg p-2.5 border border-border/40"
                  >
                    <p className="text-sm font-semibold text-slate-100">
                      {String(t.title ?? '(無題)')}
                    </p>
                    {t.angle ? (
                      <p className="text-xs text-slate-400 mt-0.5">
                        {String(t.angle)}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {trendingVideos.length > 0 && (
            <div>
              <h3 className="text-xs text-slate-400 mb-2">急上昇動画</h3>
              <ul className="space-y-1.5">
                {trendingVideos.slice(0, 8).map((v, i) => (
                  <li
                    key={(v.video_id || '') + i}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <a
                      href={v.url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-200 hover:text-accent truncate"
                    >
                      {v.title || v.video_id}
                    </a>
                    <span className="text-slate-500 tabular-nums shrink-0">
                      {formatNumber(v.view_count)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function KeywordCloud({
  title,
  items,
}: {
  title: string;
  items: Array<{ keyword: string; score?: number; source?: string }>;
}) {
  return (
    <div>
      <h3 className="text-xs text-slate-400 mb-2">{title}</h3>
      <div className="flex flex-wrap gap-1.5">
        {items.slice(0, 24).map((k, i) => (
          <span
            key={`${k.keyword}-${i}`}
            className="badge bg-bg-elev border border-border/40 text-slate-200"
            title={k.source ? `source: ${k.source}` : undefined}
          >
            {k.keyword}
          </span>
        ))}
      </div>
    </div>
  );
}

function ABTestsSection({ items }: { items: ABTest[] }) {
  return (
    <section className="card">
      <h2 className="font-bold mb-3">🧪 AB テスト結果</h2>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">
          このチャンネルの AB テストはまだありません。
        </p>
      ) : (
        <ul className="space-y-3">
          {items.slice(0, 10).map((t) => (
            <ABTestCard key={t.id || t.test_id} test={t} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ABTestCard({ test }: { test: ABTest }) {
  const variants = test.variants || [];
  const bestIdx = test.best_variant_index;
  return (
    <li className="bg-bg-elev/60 rounded-lg p-3 border border-border/40">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">
            {test.theme_title || '(テーマ未設定)'}
          </p>
          {test.theme_angle && (
            <p className="text-[11px] text-slate-400 truncate">
              {test.theme_angle}
            </p>
          )}
        </div>
        <span className="text-[10px] text-slate-500 shrink-0">
          {formatDateTime(test.created_at)}
        </span>
      </div>
      {variants.length > 0 && (
        <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2">
          {variants.map((v, i) => {
            const isBest = bestIdx === i;
            return (
              <div
                key={i}
                className={`rounded-lg p-2 border ${
                  isBest
                    ? 'bg-accent/10 border-accent/50'
                    : 'bg-bg-card border-border/40'
                }`}
              >
                <div className="flex items-center justify-between gap-1 mb-1">
                  <span className="text-[10px] text-slate-400">
                    Variant {String.fromCharCode(65 + i)}
                  </span>
                  <span
                    className={`text-[10px] tabular-nums ${
                      isBest ? 'text-accent font-bold' : 'text-slate-500'
                    }`}
                  >
                    {v.ctr_score != null
                      ? `CTR ${Number(v.ctr_score).toFixed(2)}`
                      : '—'}
                  </span>
                </div>
                {v.title && (
                  <p className="text-xs text-slate-100 leading-snug">
                    {v.title}
                  </p>
                )}
                {v.catchcopy && (
                  <p className="text-[11px] text-slate-300 mt-1 leading-snug">
                    {v.catchcopy}
                  </p>
                )}
                {v.thumbnail_text && (
                  <p className="text-[10px] text-slate-400 mt-1">
                    🖼️ {v.thumbnail_text}
                  </p>
                )}
                {isBest && (
                  <p className="text-[10px] text-accent mt-1 font-bold">
                    ★ ベスト
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </li>
  );
}

// ============================================================
// Phase D: Evaluations Tab
// ============================================================

const EVAL_AXES: { key: keyof ScenarioEvaluation; label: string }[] = [
  { key: 'hook_strength', label: 'フック' },
  { key: 'specificity', label: '具体性' },
  { key: 'pacing', label: 'テンポ' },
  { key: 'cta_effectiveness', label: 'CTA' },
  { key: 'wording_quality', label: '言回し' },
  { key: 'overall', label: '総合' },
];

function EvaluationsTab({
  data,
  modelPerformance,
  onRun,
}: {
  data: EvaluationsListResponse | null;
  modelPerformance: ModelPerformanceResponse | null;
  onRun: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const items = data?.items ?? [];
  const weak = data?.weak_patterns;

  const handleRun = async () => {
    setBusy(true);
    try {
      await onRun();
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <ModelComparisonSection data={modelPerformance} />

      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold">🧠 シナリオ評価</h2>
          <button
            className="btn-secondary py-1.5 px-3 text-xs"
            onClick={handleRun}
            disabled={busy}
            aria-busy={busy}
          >
            {busy ? '実行中…' : '🤖 未評価の動画を評価'}
          </button>
        </div>

        {weak && weak.count > 0 && weak.averages && (
          <div className="rounded-lg bg-bg-elev/60 border border-border/40 p-3">
            <h3 className="text-xs text-slate-400 mb-2">
              直近 {weak.count} 本の平均スコア
            </h3>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
              {EVAL_AXES.map((ax) => (
                <ScoreBar
                  key={ax.key}
                  label={ax.label}
                  value={Number(weak.averages?.[ax.key] ?? 0)}
                />
              ))}
            </div>
            {weak.weak_sections && weak.weak_sections.length > 0 && (
              <div className="mt-3 text-xs text-slate-300">
                <span className="text-slate-400">頻発する弱点セクション:</span>{' '}
                {weak.weak_sections
                  .slice(0, 4)
                  .map(
                    (w) =>
                      `${w.section} (${Math.round(
                        (w.frequency_ratio || 0) * 100
                      )}%)`
                  )
                  .join(' / ')}
              </div>
            )}
            {weak.recent_suggestions && weak.recent_suggestions.length > 0 && (
              <div className="mt-3">
                <div className="text-xs text-slate-400 mb-1">
                  直近の改善提案ピックアップ:
                </div>
                <ul className="space-y-1 text-xs text-slate-200">
                  {weak.recent_suggestions.slice(0, 3).map((s, i) => (
                    <li key={i}>• {s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {items.length === 0 ? (
        <section className="card">
          <p className="text-sm text-slate-500 text-center py-6">
            まだ評価データがありません。同期後に「未評価の動画を評価」を実行してください。
          </p>
        </section>
      ) : (
        <ul className="space-y-3">
          {items.map((ev) => (
            <EvaluationCard key={ev.video_id} ev={ev} />
          ))}
        </ul>
      )}
    </>
  );
}

function ModelComparisonSection({
  data,
}: {
  data: ModelPerformanceResponse | null;
}) {
  if (!data) {
    return null;
  }
  const { performance, strategy, recent_runs } = data;
  const gpt = performance.by_model.gpt;
  const claude = performance.by_model.claude;
  const totalCompare = performance.blind_compare_runs;
  const totalScenarios = gpt.scenario_count + claude.scenario_count;

  const winRatePct = (n: number) => `${(n * 100).toFixed(1)}%`;
  const fmtCtr = (n: number) => (n > 0 ? `${(n * 100).toFixed(2)}%` : '—');
  const fmtRet = (n: number) => (n > 0 ? `${(n * 100).toFixed(1)}%` : '—');

  const stratLabel =
    strategy.mode === 'prefer_gpt'
      ? '📊 GPT 優先（実績バイアス）'
      : strategy.mode === 'prefer_claude'
      ? '📊 Claude 優先（実績バイアス）'
      : '🥊 ブラインド評価で都度判定';

  return (
    <section className="card space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-bold">🤖 AI モデル比較 (GPT vs Claude)</h2>
        <span className="text-[11px] text-slate-400">
          コンペ回数: {totalCompare} / 候補シナリオ: {totalScenarios}
        </span>
      </div>

      <div className="text-xs text-slate-300 bg-bg-elev/60 border border-border/40 rounded-md p-2">
        次回の採用方針: <span className="font-semibold text-slate-100">{stratLabel}</span>
        <span className="text-slate-500"> — {strategy.reason}</span>
      </div>

      {totalCompare === 0 ? (
        <p className="text-sm text-slate-500 py-4 text-center">
          まだコンペデータがありません。両方の API キー（OpenAI + Anthropic）が設定されていれば、次回のシナリオ生成時にデュアル生成が走ります。
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <ModelStatCard
              label="GPT-4o"
              accent="bg-emerald-400/15 border-emerald-400/40"
              isLeader={performance.leader === 'gpt'}
              stats={gpt}
              winRatePct={winRatePct}
              fmtCtr={fmtCtr}
              fmtRet={fmtRet}
            />
            <ModelStatCard
              label="Claude Sonnet 4"
              accent="bg-violet-400/15 border-violet-400/40"
              isLeader={performance.leader === 'claude'}
              stats={claude}
              winRatePct={winRatePct}
              fmtCtr={fmtCtr}
              fmtRet={fmtRet}
            />
          </div>

          {recent_runs && recent_runs.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">
                直近 {recent_runs.length} 回のコンペ内訳を見る
              </summary>
              <ul className="mt-2 space-y-2">
                {recent_runs.map((run) => {
                  const g = run.candidates.gpt;
                  const c = run.candidates.claude;
                  const winnerLabel =
                    g?.selected
                      ? 'GPT'
                      : c?.selected
                      ? 'Claude'
                      : '—';
                  return (
                    <li
                      key={run.run_id}
                      className="text-[11px] text-slate-300 bg-bg-elev/40 border border-border/30 rounded-md p-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-slate-500">
                          {formatDateTime(
                            new Date((run.created_at || 0) * 1000).toISOString()
                          )}
                        </span>
                        <span className="font-semibold text-slate-100">
                          採用: {winnerLabel}
                          {g?.selected_by ? ` (${g.selected_by})` : ''}
                          {c?.selected_by ? ` (${c.selected_by})` : ''}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 mt-1">
                        <div>
                          <div className="text-slate-400">
                            GPT: {g?.title || '—'}
                          </div>
                          <div className="text-slate-500">
                            blind: {g?.blind_overall?.toFixed(1) ?? '—'}{' '}
                            {g?.won_blind_eval ? '🏆' : ''}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-400">
                            Claude: {c?.title || '—'}
                          </div>
                          <div className="text-slate-500">
                            blind: {c?.blind_overall?.toFixed(1) ?? '—'}{' '}
                            {c?.won_blind_eval ? '🏆' : ''}
                          </div>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function ModelStatCard({
  label,
  accent,
  isLeader,
  stats,
  winRatePct,
  fmtCtr,
  fmtRet,
}: {
  label: string;
  accent: string;
  isLeader: boolean;
  stats: ModelPerformanceResponse['performance']['by_model']['gpt'];
  winRatePct: (n: number) => string;
  fmtCtr: (n: number) => string;
  fmtRet: (n: number) => string;
}) {
  return (
    <div
      className={`rounded-lg border p-3 ${accent} ${
        isLeader ? 'ring-1 ring-amber-300/60' : ''
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-slate-100">{label}</span>
        {isLeader && (
          <span className="text-[10px] text-amber-300 font-bold">
            👑 LEADER
          </span>
        )}
      </div>
      <dl className="grid grid-cols-2 gap-y-1 text-[11px] text-slate-300">
        <dt className="text-slate-400">ブラインド勝率</dt>
        <dd className="text-right tabular-nums">
          {winRatePct(stats.win_rate)}{' '}
          <span className="text-slate-500">
            ({stats.win_count}/{stats.compare_runs})
          </span>
        </dd>
        <dt className="text-slate-400">平均 blind 総合</dt>
        <dd className="text-right tabular-nums">
          {stats.avg_blind_overall > 0
            ? stats.avg_blind_overall.toFixed(1)
            : '—'}
        </dd>
        <dt className="text-slate-400">採用本数</dt>
        <dd className="text-right tabular-nums">{stats.selected_count}</dd>
        <dt className="text-slate-400">実 CTR (平均)</dt>
        <dd className="text-right tabular-nums">{fmtCtr(stats.avg_ctr)}</dd>
        <dt className="text-slate-400">維持率 (平均)</dt>
        <dd className="text-right tabular-nums">
          {fmtRet(stats.avg_retention)}
        </dd>
        <dt className="text-slate-400">サンプル数</dt>
        <dd className="text-right tabular-nums">
          {stats.samples_with_metrics}
        </dd>
        <dt className="text-slate-400">実績スコア</dt>
        <dd className="text-right tabular-nums font-semibold text-slate-100">
          {(stats.perf_score * 100).toFixed(2)}
        </dd>
      </dl>
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(10, Number(value) || 0));
  const pct = (v / 10) * 100;
  const color =
    v >= 8 ? 'bg-emerald-400' : v >= 6 ? 'bg-amber-300' : 'bg-rose-400';
  return (
    <div className="text-center">
      <div className="text-[10px] text-slate-400">{label}</div>
      <div className="h-1.5 mt-1 bg-bg-card rounded-full overflow-hidden">
        <div className={`${color} h-full`} style={{ width: `${pct}%` }} />
      </div>
      <div className="text-[11px] tabular-nums mt-0.5">{v.toFixed(1)}</div>
    </div>
  );
}

function EvaluationCard({ ev }: { ev: ScenarioEvaluation }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <li className="card space-y-2">
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        className="w-full text-left"
      >
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm font-semibold text-slate-100 truncate">
            {ev.video_title || ev.video_id}
          </p>
          <span className="text-[10px] text-slate-500 shrink-0">
            {formatDateTime(new Date(ev.evaluated_at * 1000).toISOString())}
          </span>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-2">
          {EVAL_AXES.map((ax) => (
            <ScoreBar key={ax.key} label={ax.label} value={Number(ev[ax.key] ?? 0)} />
          ))}
        </div>
      </button>

      {expanded && (
        <div className="space-y-3 pt-2 border-t border-border/30">
          {ev.weak_sections && ev.weak_sections.length > 0 && (
            <div>
              <h4 className="text-xs text-slate-400 mb-1">⚠️ 弱点セクション</h4>
              <ul className="space-y-1">
                {ev.weak_sections.map((w, i) => (
                  <li
                    key={i}
                    className="text-xs text-slate-200 rounded bg-rose-500/10 border border-rose-500/30 px-2 py-1.5"
                  >
                    <span className="font-bold">{w.section || '?'}</span>
                    {typeof w.drop_percent === 'number' && (
                      <span className="ml-1 text-rose-300 tabular-nums">
                        ({w.drop_percent.toFixed(1)}% 離脱)
                      </span>
                    )}
                    {w.issue && (
                      <div className="text-slate-400 mt-1">{w.issue}</div>
                    )}
                    {w.sample_text && (
                      <div className="text-slate-500 mt-1 italic">
                        “{w.sample_text}”
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ev.improvement_suggestions && ev.improvement_suggestions.length > 0 && (
            <div>
              <h4 className="text-xs text-slate-400 mb-1">💡 改善提案</h4>
              <ul className="space-y-1">
                {ev.improvement_suggestions.map((s, i) => (
                  <li
                    key={i}
                    className="text-xs text-slate-100 rounded bg-emerald-500/10 border border-emerald-500/30 px-2 py-1.5"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ev.comment_feedback && ev.comment_feedback.length > 0 && (
            <div>
              <h4 className="text-xs text-slate-400 mb-1">
                💬 コメントフィードバック
              </h4>
              <ul className="space-y-1">
                {ev.comment_feedback.slice(0, 5).map((c, i) => (
                  <li
                    key={i}
                    className="text-xs rounded bg-bg-elev/60 border border-border/40 px-2 py-1.5"
                  >
                    {c.comment && (
                      <div className="text-slate-200">“{c.comment}”</div>
                    )}
                    {(c.section || c.action) && (
                      <div className="text-slate-500 mt-1">
                        {c.section ? `[${c.section}] ` : ''}
                        {c.action || ''}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

// ============================================================
// Phase D: AB Reconciliation Tab
// ============================================================

function ReconciliationTab({
  data,
  onRun,
}: {
  data: AbReconciliationResponse | null;
  onRun: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const items = data?.items ?? [];
  const insights = data?.pattern_insights;
  const handleRun = async () => {
    setBusy(true);
    try {
      await onRun();
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold">🎯 AB テスト実績</h2>
          <button
            className="btn-secondary py-1.5 px-3 text-xs"
            onClick={handleRun}
            disabled={busy}
          >
            {busy ? '実行中…' : '🔁 7日経過分の答え合わせ'}
          </button>
        </div>

        {insights && insights.patterns && insights.patterns.length > 0 && (
          <div className="rounded-lg bg-bg-elev/60 border border-border/40 p-3">
            <h3 className="text-xs text-slate-400 mb-2">
              パターン別実績（n={insights.total_samples}）
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {insights.patterns.map((p) => (
                <div
                  key={p.pattern_type}
                  className="rounded bg-bg-card border border-border/40 p-2"
                >
                  <div className="text-xs font-semibold text-slate-100">
                    {labelForPattern(p.pattern_type)} (n={p.samples})
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">
                    実 CTR 平均:{' '}
                    <span className="text-emerald-300 tabular-nums">
                      {p.actual_ctr_percent_avg != null
                        ? `${p.actual_ctr_percent_avg.toFixed(2)}%`
                        : '—'}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400">
                    予測スコア平均:{' '}
                    <span className="text-slate-100 tabular-nums">
                      {p.predicted_score_avg != null
                        ? p.predicted_score_avg.toFixed(2)
                        : '—'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            {insights.overall_actual_ctr_avg != null && (
              <p className="text-[11px] text-slate-500 mt-2">
                全体平均実 CTR:{' '}
                {(insights.overall_actual_ctr_avg * 100).toFixed(2)}%
              </p>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h3 className="font-bold text-sm mb-2">予測 vs 実 CTR (個別)</h3>
        {items.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-6">
            紐付け済みの AB テストがまだありません。
          </p>
        ) : (
          <div className="overflow-x-auto -mx-4 px-4">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase text-slate-500">
                <tr className="border-b border-border/40">
                  <th className="text-left py-2 pr-2">test_id</th>
                  <th className="text-left py-2 pr-2">パターン</th>
                  <th className="text-right py-2 px-2">予測</th>
                  <th className="text-right py-2 px-2">実 CTR</th>
                  <th className="text-right py-2 px-2">imp</th>
                  <th className="text-right py-2 pl-2">差分</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => {
                  const ctrPct =
                    r.actual_ctr != null ? r.actual_ctr * 100 : null;
                  // simple delta: actual_ctr% vs (predicted_score gives target like 5 = 5%)
                  const delta =
                    ctrPct != null && r.predicted_score != null
                      ? ctrPct - r.predicted_score
                      : null;
                  return (
                    <tr
                      key={`${r.test_id}-${r.variant_index}`}
                      className="border-b border-border/20"
                    >
                      <td className="py-1.5 pr-2 truncate max-w-[10rem]">
                        {r.test_id.slice(-12)}
                      </td>
                      <td className="py-1.5 pr-2">
                        {labelForPattern(r.pattern_type)}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {r.predicted_score != null
                          ? r.predicted_score.toFixed(2)
                          : '—'}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {ctrPct != null ? `${ctrPct.toFixed(2)}%` : '—'}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {r.actual_impressions != null
                          ? formatNumber(r.actual_impressions)
                          : '—'}
                      </td>
                      <td className="py-1.5 pl-2 text-right tabular-nums">
                        {delta != null ? (
                          <span
                            className={
                              delta >= 0 ? 'text-emerald-300' : 'text-rose-300'
                            }
                          >
                            {delta >= 0 ? '+' : ''}
                            {delta.toFixed(2)}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function labelForPattern(p?: string | null): string {
  if (!p) return '—';
  return (
    { question: '疑問形', number: '数字入り', surprise: '意外性' } as Record<
      string,
      string
    >
  )[p] || p;
}

// ============================================================
// Phase D: Improvement Queue Tab
// ============================================================

function ImprovementsTab({
  data,
  onRun,
  onRegenerate,
  onSetStatus,
}: {
  data: ImprovementsListResponse | null;
  onRun: () => void;
  onRegenerate: (videoId: string) => Promise<void>;
  onSetStatus: (
    videoId: string,
    status: 'pending' | 'applied' | 'dismissed'
  ) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const items = data?.items ?? [];
  const avg = data?.channel_avg_ctr;
  const handleRun = async () => {
    setBusy(true);
    try {
      await onRun();
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <section className="card space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold">🛠 改善キュー</h2>
          <button
            className="btn-secondary py-1.5 px-3 text-xs"
            onClick={handleRun}
            disabled={busy}
          >
            {busy ? '検出中…' : '🔍 低 CTR 動画を再検出'}
          </button>
        </div>
        <p className="text-xs text-slate-400">
          チャンネル平均 CTR{' '}
          <span className="text-slate-100 tabular-nums">
            {avg != null ? `${(avg * 100).toFixed(2)}%` : '—'}
          </span>{' '}
          の 80% 未満を要改善として検出します。
        </p>
      </section>

      {items.length === 0 ? (
        <section className="card">
          <p className="text-sm text-slate-500 text-center py-6">
            改善キューはまだ空です。
          </p>
        </section>
      ) : (
        <ul className="space-y-3">
          {items.map((it) => (
            <ImprovementCard
              key={it.video_id}
              entry={it}
              onRegenerate={onRegenerate}
              onSetStatus={onSetStatus}
            />
          ))}
        </ul>
      )}
    </>
  );
}

function ImprovementCard({
  entry,
  onRegenerate,
  onSetStatus,
}: {
  entry: ImprovementEntry;
  onRegenerate: (videoId: string) => Promise<void>;
  onSetStatus: (
    videoId: string,
    status: 'pending' | 'applied' | 'dismissed'
  ) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const ctrPct = entry.current_ctr != null ? entry.current_ctr * 100 : null;
  const avgPct =
    entry.channel_avg_ctr != null ? entry.channel_avg_ctr * 100 : null;
  const ratio =
    ctrPct != null && avgPct != null && avgPct > 0 ? ctrPct / avgPct : null;

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <li
      className={`card space-y-3 ${
        entry.status === 'applied'
          ? 'border-emerald-500/40'
          : entry.status === 'dismissed'
          ? 'opacity-60'
          : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">
            {entry.current_title || entry.video_id}
          </p>
          <p className="text-[11px] text-slate-500 truncate">
            {entry.video_id}
          </p>
        </div>
        <span
          className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded shrink-0 ${
            entry.status === 'applied'
              ? 'bg-emerald-500/20 text-emerald-300'
              : entry.status === 'dismissed'
              ? 'bg-slate-500/20 text-slate-400'
              : 'bg-amber-500/20 text-amber-300'
          }`}
        >
          {entry.status}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded bg-bg-elev/60 border border-border/40 p-2">
          <div className="text-slate-400">現状 CTR</div>
          <div className="text-rose-300 tabular-nums">
            {ctrPct != null ? `${ctrPct.toFixed(2)}%` : '—'}
          </div>
        </div>
        <div className="rounded bg-bg-elev/60 border border-border/40 p-2">
          <div className="text-slate-400">チャンネル平均</div>
          <div className="text-slate-100 tabular-nums">
            {avgPct != null ? `${avgPct.toFixed(2)}%` : '—'}
          </div>
        </div>
        <div className="rounded bg-bg-elev/60 border border-border/40 p-2">
          <div className="text-slate-400">平均比</div>
          <div className="text-amber-300 tabular-nums">
            {ratio != null ? `${(ratio * 100).toFixed(0)}%` : '—'}
          </div>
        </div>
      </div>

      {entry.suggested_catchcopies && entry.suggested_catchcopies.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs text-slate-400">
            ✨ 新キャッチコピー提案
            {entry.predicted_improvement != null
              ? ` — 期待改善 +${entry.predicted_improvement.toFixed(0)}%`
              : ''}
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {entry.suggested_catchcopies.map((c, i) => (
              <div
                key={i}
                className="rounded bg-bg-card border border-border/40 p-2"
              >
                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                  <span>{labelForPattern(c.pattern)}</span>
                  {c.score != null && (
                    <span className="text-slate-200 tabular-nums">
                      ★ {c.score}
                    </span>
                  )}
                </div>
                {c.title && (
                  <p className="text-xs text-slate-100 leading-snug">
                    {c.title}
                  </p>
                )}
                {Array.isArray(c.thumb_copy) && c.thumb_copy.length > 0 && (
                  <p className="text-[11px] text-slate-300 mt-1 leading-snug">
                    🖼 {c.thumb_copy.join(' / ')}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          className="btn-secondary py-1 px-3 text-xs"
          onClick={() => wrap(() => onRegenerate(entry.video_id))}
          disabled={busy}
        >
          🔁 再生成
        </button>
        <button
          className="btn-primary py-1 px-3 text-xs"
          onClick={() => wrap(() => onSetStatus(entry.video_id, 'applied'))}
          disabled={busy || entry.status === 'applied'}
        >
          ✅ 適用済みにする
        </button>
        <button
          className="btn-secondary py-1 px-3 text-xs"
          onClick={() => wrap(() => onSetStatus(entry.video_id, 'dismissed'))}
          disabled={busy || entry.status === 'dismissed'}
        >
          ✖ 却下
        </button>
        {entry.status !== 'pending' && (
          <button
            className="btn-secondary py-1 px-3 text-xs"
            onClick={() => wrap(() => onSetStatus(entry.video_id, 'pending'))}
            disabled={busy}
          >
            ↺ 戻す
          </button>
        )}
      </div>
    </li>
  );
}
