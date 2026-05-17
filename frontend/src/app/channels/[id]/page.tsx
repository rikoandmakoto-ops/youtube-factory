import Link from 'next/link';
import { notFound } from 'next/navigation';
import Header from '@/components/Header';
import ViewsChart from '@/components/ViewsChart';
import VideoListClient from './ChannelDetailClient';
import ThemeQueuePanel from '@/components/ThemeQueuePanel';
import {
  getChannel,
  getChannelAnalytics,
  getYoutubeStatus,
  ApiError,
  redirectIfUnauthorized,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

const ICONS: Record<string, string> = {
  'daily-science': '🧪',
};

function fmtNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return new Intl.NumberFormat('ja-JP').format(n);
}

export default async function ChannelDetailPage({
  params,
}: {
  params: { id: string };
}) {
  let channel;
  let backendError: string | null = null;
  try {
    channel = await getChannel(params.id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    redirectIfUnauthorized(e, `/channels/${params.id}`);
    backendError =
      e instanceof ApiError
        ? e.message
        : 'バックエンドに接続できません';
  }

  if (!channel) {
    return (
      <main className="pb-10">
        <Header
          title="チャンネル"
          back={{ href: '/', label: 'ダッシュボードに戻る' }}
        />
        <div className="mx-5 mt-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {backendError ?? 'チャンネル情報を取得できませんでした'}
        </div>
      </main>
    );
  }

  const subResults = await Promise.allSettled([
    getChannelAnalytics(params.id),
    getYoutubeStatus(),
  ]);
  redirectIfUnauthorized(subResults, `/channels/${params.id}`);
  const [analyticsRes, ytStatusRes] = subResults;
  const analytics =
    analyticsRes.status === 'fulfilled' ? analyticsRes.value : null;
  const ytStatus =
    ytStatusRes.status === 'fulfilled' ? ytStatusRes.value : null;

  const icon = ICONS[channel.id] ?? '📺';
  // 実データ優先：analytics の metrics があれば使う
  const m = analytics?.metrics ?? channel.metrics;
  const isReal = analytics?.source === 'youtube_analytics';
  const channelYoutubeId = channel.youtube_channel_id ?? null;
  const ps = channel.publish_settings ?? null;

  return (
    <main className="pb-10">
      <Header
        title={`${icon} ${channel.name}`}
        back={{ href: '/', label: 'ダッシュボードに戻る' }}
      />

      <div className="px-5 mb-3 flex items-center gap-2">
        <span
          className={`badge ${
            isReal ? 'bg-emerald-600 text-white' : 'bg-slate-600 text-slate-200'
          }`}
        >
          {isReal ? '📊 YouTube実データ' : '🔢 推定データ'}
        </span>
        {!ytStatus?.connected && (
          <Link href="/settings" className="text-xs text-accent hover:underline">
            YouTube連携で実データに切替 →
          </Link>
        )}
      </div>

      <section
        aria-label="チャンネル統計"
        className="px-5 grid grid-cols-2 gap-3"
      >
        <Stat value={fmtNumber(m.total_views)} label="総再生数" />
        <Stat value={fmtNumber(m.subscribers)} label="登録者" />
        <Stat value={fmtNumber(m.video_count)} label="動画数" />
        <Stat value={fmtNumber(m.avg_views_per_video)} label="平均再生/本" />
      </section>

      {analytics && analytics.views_by_day.length > 0 && (
        <section className="card mx-5 mt-3">
          <h2 className="text-sm font-bold text-slate-200 mb-2">
            📈 再生数推移（過去28日）
          </h2>
          <ViewsChart data={analytics.views_by_day} />
        </section>
      )}

      {analytics && analytics.top_videos.length > 0 && (
        <section className="card mx-5 mt-3">
          <h2 className="text-sm font-bold text-slate-200 mb-2">
            🏆 人気動画 TOP 5
          </h2>
          <ol className="space-y-1.5 text-sm">
            {analytics.top_videos.map((v, i) => (
              <li
                key={v.video_id}
                className="flex items-center gap-2 py-1 border-b border-border last:border-0"
              >
                <span className="text-slate-500 w-5 text-center">{i + 1}</span>
                <span className="flex-1 truncate" title={v.title}>
                  {v.title}
                </span>
                <span className="text-xs text-slate-400">
                  {fmtNumber(v.views)}再生
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {analytics?.error && (
        <div className="mx-5 mt-3 rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-xs text-amber-300">
          ⚠️ Analytics エラー: {analytics.error}
        </div>
      )}

      <section className="px-5 mt-4 grid grid-cols-2 gap-3">
        <Link
          href={`/generate?channel=${encodeURIComponent(channel.id)}`}
          className="btn-primary"
        >
          ＋ 新規動画
        </Link>
        <Link href={`/channels/${channel.id}/config`} className="btn-secondary">
          ⚙️ チャンネル設定
        </Link>
      </section>

      <ThemeQueuePanel channelId={channel.id} channelName={channel.name} />

      <section className="px-5 mt-6">
        <h2 className="font-bold text-slate-200 mb-3">動画一覧</h2>
        <VideoListClient
          videos={channel.videos}
          channelYoutubeId={channelYoutubeId}
          channelInternalId={channel.id}
          defaultTags={[]}
          youtubeConnected={!!ytStatus?.connected}
          defaultShortDelayMinutes={ps?.short_delay_minutes}
          defaultPrivacy={ps?.default_privacy}
        />
      </section>
    </main>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="card text-center py-4">
      <div className="font-bold text-2xl text-accent">{value}</div>
      <div className="text-xs text-slate-400 mt-1">{label}</div>
    </div>
  );
}
