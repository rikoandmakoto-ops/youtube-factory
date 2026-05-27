'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useState } from 'react';
import type {
  Channel,
  PdcaBucketSummary,
  PdcaReport,
  PdcaVideoSample,
} from '@/lib/api';

type Props = {
  channels: Channel[];
  channelId: string;
  days: number;
  initialReport: PdcaReport | null;
  initialError: string | null;
};

const DAY_OPTIONS = [7, 14, 30, 60, 90];

function fmtNumber(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toLocaleString('ja-JP');
}

function fmtPercent(p: number | null | undefined, digits = 2): string {
  if (p == null || Number.isNaN(p)) return '—';
  return `${(p * 100).toFixed(digits)}%`;
}

function fmtUsd(v: number | null | undefined, digits = 4): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `$${v.toFixed(digits)}`;
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleDateString('ja-JP', {
      month: '2-digit',
      day: '2-digit',
    });
  } catch {
    return s;
  }
}

function fmtRatio(r: number | null | undefined): string {
  if (r == null || Number.isNaN(r)) return '—';
  return `${r.toFixed(2)}x`;
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-slate-700 bg-slate-900/50 px-3 py-2">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-lg font-semibold text-slate-100">{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function BucketCard({
  title,
  emoji,
  bucket,
  costPerVideo,
}: {
  title: string;
  emoji: string;
  bucket: PdcaBucketSummary;
  costPerVideo: number;
}) {
  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
      <h3 className="text-base font-semibold mb-3">
        {emoji} {title}
        <span className="ml-2 text-sm text-slate-400">
          ({bucket.count}本)
        </span>
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <StatCard label="合計再生" value={fmtNumber(bucket.total_views)} />
        <StatCard
          label="平均再生 / 本"
          value={fmtNumber(Math.round(bucket.avg_views))}
        />
        <StatCard
          label="中央値再生"
          value={fmtNumber(bucket.median_views)}
        />
        <StatCard label="合計いいね" value={fmtNumber(bucket.total_likes)} />
        <StatCard
          label="平均いいね / 本"
          value={fmtNumber(Math.round(bucket.avg_likes))}
        />
        <StatCard
          label="平均いいね率"
          value={fmtPercent(bucket.avg_like_rate)}
        />
        <StatCard
          label="合計コメント"
          value={fmtNumber(bucket.total_comments)}
        />
        <StatCard
          label="平均コメント / 本"
          value={fmtNumber(Math.round(bucket.avg_comments))}
        />
        <StatCard
          label="推定コスト / 本"
          value={fmtUsd(costPerVideo)}
          sub="期間内合計の均等按分"
        />
      </div>

      {bucket.top_videos.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-slate-400 mb-1">トップ5（再生数）</div>
          <div className="space-y-1">
            {bucket.top_videos.map((v) => (
              <VideoRow key={v.video_id} v={v} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function VideoRow({ v }: { v: PdcaVideoSample }) {
  const url = `https://youtube.com/watch?v=${v.video_id}`;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center justify-between gap-2 rounded border border-slate-800 bg-slate-950/60 px-2 py-1.5 text-sm hover:bg-slate-900"
    >
      <span className="truncate flex-1 text-slate-200">{v.title}</span>
      <span className="shrink-0 text-xs text-slate-400 tabular-nums">
        {fmtDate(v.published_at)} · {fmtNumber(v.views)} 再生 ·{' '}
        {fmtNumber(v.likes)} 👍
      </span>
    </a>
  );
}

export default function PdcaReportView({
  channels,
  channelId,
  days,
  initialReport,
  initialError,
}: Props) {
  const router = useRouter();
  const [report, setReport] = useState<PdcaReport | null>(initialReport);
  const [error, setError] = useState<string | null>(initialError);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(
    async (nextChannel: string, nextDays: number) => {
      setLoading(true);
      setError(null);
      try {
        const qs = new URLSearchParams({
          channel_id: nextChannel,
          days: String(nextDays),
        });
        const r = await fetch(`/api/analytics/pdca-report?${qs.toString()}`, {
          cache: 'no-store',
        });
        if (!r.ok) {
          let msg = `${r.status} ${r.statusText}`;
          try {
            const j = await r.json();
            if (j && typeof j === 'object' && 'error' in j) msg = String(j.error);
          } catch {
            /* ignore */
          }
          throw new Error(msg);
        }
        const data = (await r.json()) as PdcaReport;
        setReport(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : '取得に失敗');
        setReport(null);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const switchChannel = (id: string) => {
    const qs = new URLSearchParams({ channel: id, days: String(days) });
    router.replace(`/analytics/pdca?${qs.toString()}`);
    reload(id, days);
  };

  const switchDays = (d: number) => {
    const qs = new URLSearchParams({ channel: channelId, days: String(d) });
    router.replace(`/analytics/pdca?${qs.toString()}`);
    reload(channelId, d);
  };

  const knownChannels = channels.length
    ? channels
    : [
        { id: 'daily-science', name: 'daily-science', concept: '', style: '' },
        { id: 'scp-lab', name: 'scp-lab', concept: '', style: '' },
      ];

  return (
    <div className="px-4">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="flex flex-wrap gap-1">
          {knownChannels.map((c) => (
            <button
              key={c.id}
              onClick={() => switchChannel(c.id)}
              className={`px-3 py-1 rounded text-sm border ${
                c.id === channelId
                  ? 'bg-accent text-slate-900 border-accent'
                  : 'bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700'
              }`}
            >
              {c.name || c.id}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1 ml-auto">
          {DAY_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => switchDays(d)}
              className={`px-3 py-1 rounded text-sm border ${
                d === days
                  ? 'bg-accent text-slate-900 border-accent'
                  : 'bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700'
              }`}
            >
              {d}日
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="mb-3 text-sm text-slate-400">読み込み中…</div>
      )}
      {error && (
        <div className="mb-3 rounded border border-red-800 bg-red-900/30 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      )}

      {report && (
        <>
          <section className="mb-4 rounded-lg border border-slate-700 bg-slate-900/40 p-4">
            <div className="flex flex-wrap items-baseline gap-3">
              <h2 className="text-lg font-semibold">
                {report.channel_stats.youtube_title || report.channel_id}
              </h2>
              <span className="text-sm text-slate-400">
                {fmtDate(report.window.start)} 〜 {fmtDate(report.window.end)}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatCard
                label="現在の登録者"
                value={fmtNumber(report.channel_stats.subscriber_count)}
                sub={
                  report.channel_stats.subscriber_hidden ? '非公開設定' : undefined
                }
              />
              <StatCard
                label="期間内の純増"
                value={fmtNumber(report.subscribers.net_in_window)}
                sub={`+${report.subscribers.gained_in_window} / -${report.subscribers.lost_in_window}`}
              />
              <StatCard
                label="期間内の総再生"
                value={fmtNumber(
                  report.shorts.total_views + report.main.total_views
                )}
              />
              <StatCard
                label="期間内の公開本数"
                value={fmtNumber(
                  report.shorts.count + report.main.count
                )}
                sub={`ショート ${report.shorts.count} / メイン ${report.main.count}`}
              />
            </div>
            {report.subscribers.daily.length === 0 && (
              <p className="mt-2 text-xs text-amber-300">
                登録者の日次推移は YouTube Analytics 同期が必要です（
                <span className="font-mono">/api/analytics/sync</span> を実行）。
              </p>
            )}
            {report.errors.youtube_fetch && (
              <p className="mt-2 text-xs text-amber-300">
                ⚠️ {report.errors.youtube_fetch}
              </p>
            )}
            <p className="mt-2 text-xs text-slate-500">
              DB 公開済み: {report.totals.published_in_db} 本 / YouTube 取得:{' '}
              {report.totals.fetched_from_youtube} 本 / 期間内: {report.totals.in_window} 本
            </p>
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <BucketCard
              title="ショート"
              emoji="📱"
              bucket={report.shorts}
              costPerVideo={report.cost.cost_per_short_usd}
            />
            <BucketCard
              title="メイン動画"
              emoji="🎬"
              bucket={report.main}
              costPerVideo={report.cost.cost_per_main_usd}
            />
          </div>

          <section className="mt-4 rounded-lg border border-slate-700 bg-slate-900/40 p-4">
            <h3 className="text-base font-semibold mb-3">⚖️ ショート vs メイン</h3>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <StatCard
                label="平均再生 比 (ショート / メイン)"
                value={fmtRatio(report.comparison.avg_views_short_vs_main)}
              />
              <StatCard
                label="平均いいね 比"
                value={fmtRatio(report.comparison.avg_likes_short_vs_main)}
              />
              <StatCard
                label="いいね率 比"
                value={fmtRatio(report.comparison.avg_like_rate_short_vs_main)}
              />
            </div>
          </section>

          <section className="mt-4 rounded-lg border border-slate-700 bg-slate-900/40 p-4">
            <h3 className="text-base font-semibold mb-3">💰 API コスト</h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatCard
                label="期間内総コスト"
                value={fmtUsd(report.cost.total_cost_usd, 2)}
                sub={`${report.cost.events} イベント`}
              />
              <StatCard
                label="1本あたり (均等按分)"
                value={fmtUsd(report.cost.cost_per_video_usd)}
              />
              <StatCard
                label="ショート 1本"
                value={fmtUsd(report.cost.cost_per_short_usd)}
              />
              <StatCard
                label="メイン 1本"
                value={fmtUsd(report.cost.cost_per_main_usd)}
              />
            </div>
            <p className="mt-2 text-xs text-slate-500">{report.cost.note}</p>
            {Object.keys(report.cost.by_purpose).length > 0 && (
              <details className="mt-3">
                <summary className="cursor-pointer text-sm text-slate-300">
                  内訳を表示
                </summary>
                <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <div className="text-xs text-slate-400 mb-1">用途別</div>
                    <ul className="text-sm space-y-0.5">
                      {Object.entries(report.cost.by_purpose)
                        .sort(([, a], [, b]) => b - a)
                        .map(([k, v]) => (
                          <li
                            key={k}
                            className="flex justify-between border-b border-slate-800 py-0.5"
                          >
                            <span className="text-slate-300">{k}</span>
                            <span className="tabular-nums">
                              {fmtUsd(v, 4)}
                            </span>
                          </li>
                        ))}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 mb-1">モデル別</div>
                    <ul className="text-sm space-y-0.5">
                      {Object.entries(report.cost.by_model)
                        .sort(([, a], [, b]) => b - a)
                        .map(([k, v]) => (
                          <li
                            key={k}
                            className="flex justify-between border-b border-slate-800 py-0.5"
                          >
                            <span className="text-slate-300">{k}</span>
                            <span className="tabular-nums">
                              {fmtUsd(v, 4)}
                            </span>
                          </li>
                        ))}
                    </ul>
                  </div>
                </div>
              </details>
            )}
          </section>

          {report.subscribers.daily.length > 0 && (
            <section className="mt-4 rounded-lg border border-slate-700 bg-slate-900/40 p-4">
              <h3 className="text-base font-semibold mb-3">📈 登録者推移</h3>
              <div className="overflow-x-auto">
                <table className="text-sm min-w-full">
                  <thead className="text-xs text-slate-400">
                    <tr>
                      <th className="px-2 py-1 text-left">日付</th>
                      <th className="px-2 py-1 text-right">獲得</th>
                      <th className="px-2 py-1 text-right">解除</th>
                      <th className="px-2 py-1 text-right">純増</th>
                      <th className="px-2 py-1 text-right">累積</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.subscribers.daily.slice(-30).map((d) => (
                      <tr
                        key={d.date}
                        className="border-t border-slate-800 tabular-nums"
                      >
                        <td className="px-2 py-1 text-slate-300">
                          {fmtDate(d.date)}
                        </td>
                        <td className="px-2 py-1 text-right text-emerald-300">
                          +{d.gained}
                        </td>
                        <td className="px-2 py-1 text-right text-red-300">
                          -{d.lost}
                        </td>
                        <td
                          className={`px-2 py-1 text-right ${
                            d.net >= 0 ? 'text-emerald-200' : 'text-red-200'
                          }`}
                        >
                          {d.net >= 0 ? `+${d.net}` : d.net}
                        </td>
                        <td className="px-2 py-1 text-right text-slate-300">
                          {d.cumulative_net >= 0
                            ? `+${d.cumulative_net}`
                            : d.cumulative_net}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
