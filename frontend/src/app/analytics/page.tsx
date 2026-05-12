import Header from '@/components/Header';
import AnalyticsView from './AnalyticsView';
import {
  listChannels,
  getAnalyticsOverview,
  getAnalyticsVideos,
  getTrends,
  listABTests,
  listEvaluations,
  listAbReconciliation,
  listImprovements,
  getModelPerformance,
  listTrendDetections,
  listSeriesSuggestions,
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
    listEvaluations(channelId, 100),
    listAbReconciliation(channelId, 200),
    listImprovements(channelId, { limit: 100 }),
    getModelPerformance(channelId, 20),
    listTrendDetections(channelId, { limit: 50 }),
    listSeriesSuggestions(channelId, { limit: 100 }),
  ]);
  redirectIfUnauthorized(results, '/analytics');
  const [
    chRes,
    ovRes,
    vidRes,
    trRes,
    abRes,
    evalRes,
    reconRes,
    impRes,
    perfRes,
    trDetRes,
    seriesRes,
  ] = results;

  const channels = chRes.status === 'fulfilled' ? chRes.value : [];
  const overview = ovRes.status === 'fulfilled' ? ovRes.value : null;
  const videos = vidRes.status === 'fulfilled' ? vidRes.value.items : [];
  const trends = trRes.status === 'fulfilled' ? trRes.value : null;
  const abTests = abRes.status === 'fulfilled' ? abRes.value.items : [];
  const evaluations = evalRes.status === 'fulfilled' ? evalRes.value : null;
  const abReconciliation =
    reconRes.status === 'fulfilled' ? reconRes.value : null;
  const improvements = impRes.status === 'fulfilled' ? impRes.value : null;
  const modelPerformance =
    perfRes.status === 'fulfilled' ? perfRes.value : null;
  const trendDetections =
    trDetRes.status === 'fulfilled' ? trDetRes.value : null;
  const seriesSuggestions =
    seriesRes.status === 'fulfilled' ? seriesRes.value : null;

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
  collect('シナリオ評価', evalRes);
  collect('AB 答え合わせ', reconRes);
  collect('改善キュー', impRes);
  collect('AIモデル比較', perfRes);
  collect('トレンド検出', trDetRes);
  collect('シリーズ候補', seriesRes);

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
        initialEvaluations={evaluations}
        initialAbReconciliation={abReconciliation}
        initialImprovements={improvements}
        initialModelPerformance={modelPerformance}
        initialTrendDetections={trendDetections}
        initialSeriesSuggestions={seriesSuggestions}
        initialErrors={sectionErrors}
      />
    </main>
  );
}
