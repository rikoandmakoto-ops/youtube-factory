import Header from '@/components/Header';
import AnalyticsView from './AnalyticsView';
import {
  listChannels,
  getAnalyticsOverview,
  getAnalyticsVideos,
  getTrends,
  listABTests,
  ApiError,
  redirectIfUnauthorized,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

const DEFAULT_CHANNEL_ID = 'daily-science';

export default async function AnalyticsPage({
  searchParams,
}: {
  searchParams?: { channel?: string };
}) {
  const channelId = searchParams?.channel || DEFAULT_CHANNEL_ID;

  const results = await Promise.allSettled([
    listChannels(),
    getAnalyticsOverview(channelId, 30),
    getAnalyticsVideos(channelId, 50),
    getTrends(channelId, 5),
    listABTests(channelId, 20),
  ]);
  redirectIfUnauthorized(results, '/analytics');
  const [chRes, ovRes, vidRes, trRes, abRes] = results;

  const channels = chRes.status === 'fulfilled' ? chRes.value : [];
  const overview = ovRes.status === 'fulfilled' ? ovRes.value : null;
  const videos = vidRes.status === 'fulfilled' ? vidRes.value.items : [];
  const trends = trRes.status === 'fulfilled' ? trRes.value : null;
  const abTests = abRes.status === 'fulfilled' ? abRes.value.items : [];

  const sectionErrors: { section: string; message: string }[] = [];
  const collect = (
    section: string,
    r: PromiseSettledResult<unknown>
  ) => {
    if (r.status === 'rejected') {
      const msg =
        r.reason instanceof ApiError
          ? r.reason.message
          : '取得に失敗しました';
      sectionErrors.push({ section, message: msg });
    }
  };
  collect('概要', ovRes);
  collect('動画一覧', vidRes);
  collect('トレンド', trRes);
  collect('AB テスト', abRes);

  return (
    <main className="pb-10">
      <Header
        title="📈 分析"
        back={{ href: '/', label: 'ダッシュボードに戻る' }}
      />
      <AnalyticsView
        channels={channels}
        channelId={channelId}
        initialOverview={overview}
        initialVideos={videos}
        initialTrends={trends}
        initialABTests={abTests}
        initialErrors={sectionErrors}
      />
    </main>
  );
}
