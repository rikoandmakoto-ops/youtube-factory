import Header from '@/components/Header';
import PdcaReportView from './PdcaReportView';
import {
  listChannels,
  getPdcaReport,
  ApiError,
  redirectIfUnauthorized,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

const DEFAULT_CHANNEL_ID = 'daily-science';
const DEFAULT_DAYS = 30;

export default async function PdcaReportPage({
  searchParams,
}: {
  searchParams?: { channel?: string; days?: string };
}) {
  const channelId = searchParams?.channel || DEFAULT_CHANNEL_ID;
  const daysRaw = Number(searchParams?.days || DEFAULT_DAYS);
  const days = Number.isFinite(daysRaw) && daysRaw > 0 ? daysRaw : DEFAULT_DAYS;

  const results = await Promise.allSettled([
    listChannels(),
    getPdcaReport(channelId, days),
  ]);
  redirectIfUnauthorized(results, `/analytics/pdca?channel=${channelId}`);
  const [chRes, reportRes] = results;

  const channels = chRes.status === 'fulfilled' ? chRes.value : [];
  const report = reportRes.status === 'fulfilled' ? reportRes.value : null;
  const error =
    reportRes.status === 'rejected'
      ? reportRes.reason instanceof ApiError
        ? reportRes.reason.message
        : '取得に失敗しました'
      : null;

  return (
    <main className="pb-10">
      <Header
        title="📊 PDCA レポート (ショート vs メイン)"
        back={{ href: '/analytics', label: '分析に戻る' }}
      />
      <PdcaReportView
        channels={channels}
        channelId={channelId}
        days={days}
        initialReport={report}
        initialError={error}
      />
    </main>
  );
}
