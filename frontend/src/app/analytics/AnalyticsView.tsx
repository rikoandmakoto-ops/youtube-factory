'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import type {
  ABTest,
  AnalyticsOverview,
  AnalyticsVideoMetric,
  Channel,
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
  initialErrors: SectionError[];
};

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
  initialErrors,
}: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [overview, setOverview] = useState(initialOverview);
  const [videos, setVideos] = useState(initialVideos);
  const [trends, setTrends] = useState(initialTrends);
  const [abTests, setABTests] = useState(initialABTests);
  const [errors, setErrors] = useState<SectionError[]>(initialErrors);

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

  const reload = async () => {
    setRefreshing(true);
    setErrors([]);
    const collect = (section: string, message: string) =>
      setErrors((prev) => [...prev, { section, message }]);

    const [ov, vid, tr, ab] = await Promise.allSettled([
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
    ]);

    if (ov.status === 'fulfilled') setOverview(ov.value as AnalyticsOverview);
    else collect('概要', '取得に失敗しました');
    if (vid.status === 'fulfilled') setVideos((vid.value as { items: AnalyticsVideoMetric[] }).items || []);
    else collect('動画一覧', '取得に失敗しました');
    if (tr.status === 'fulfilled') setTrends(tr.value as TrendsResponse);
    else collect('トレンド', '取得に失敗しました');
    if (ab.status === 'fulfilled') setABTests((ab.value as { items: ABTest[] }).items || []);
    else collect('AB テスト', '取得に失敗しました');

    setRefreshing(false);
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

      {/* KPI カード */}
      <OverviewSection overview={overview} />

      {/* 動画別パフォーマンス */}
      <VideosSection videos={videos} />

      {/* トレンド */}
      <TrendsSection trends={trends} />

      {/* AB テスト */}
      <ABTestsSection items={abTests} />
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
