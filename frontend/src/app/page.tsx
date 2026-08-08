import { Suspense } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import SystemStatusGrid from '@/components/SystemStatus';
import ChannelCard, { NewChannelCard } from '@/components/ChannelCard';
import ActiveJobs from '@/components/ActiveJobs';
import UpcomingSchedules from '@/components/UpcomingSchedules';
import MonthlyCostSummary from '@/components/MonthlyCostSummary';
import HeaderCostBadge from '@/components/HeaderCostBadge';
import {
  getSystemStatus,
  listChannels,
  listActiveJobs,
  ApiError,
  redirectIfUnauthorized,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

/** Placeholder that reserves a card's height so streaming-in doesn't shift layout. */
function CardSkeleton({ label }: { label: string }) {
  return (
    <section aria-label={label} className="mx-5 mt-4 card">
      <div className="h-4 w-32 rounded bg-bg-elev animate-pulse" />
      <div className="mt-3 h-3 w-full rounded bg-bg-elev animate-pulse" />
      <div className="mt-2 h-3 w-2/3 rounded bg-bg-elev animate-pulse" />
    </section>
  );
}

export default async function DashboardPage() {
  const results = await Promise.allSettled([
    getSystemStatus(),
    listChannels(),
    listActiveJobs(),
  ]);
  redirectIfUnauthorized(results, '/');
  const [statusRes, channelsRes, jobsRes] = results;

  const status = statusRes.status === 'fulfilled' ? statusRes.value : null;
  const channels = channelsRes.status === 'fulfilled' ? channelsRes.value : [];
  const jobs = jobsRes.status === 'fulfilled' ? jobsRes.value : [];

  const backendError =
    statusRes.status === 'rejected' && statusRes.reason instanceof ApiError
      ? statusRes.reason.message
      : statusRes.status === 'rejected'
      ? 'バックエンドに接続できません'
      : null;

  return (
    <main className="pb-10">
      <Header
        showNav
        actions={
          <div className="flex items-center gap-2">
            {/* Cost/schedule panels each cost a backend round-trip. Streaming
                them keeps the dashboard shell off their critical path. */}
            <Suspense
              fallback={
                <div className="h-9 w-24 rounded-md bg-bg-elev animate-pulse" />
              }
            >
              <HeaderCostBadge />
            </Suspense>
            <Link href="/settings" className="btn-secondary py-2 px-3 text-sm">
              ⚙️
            </Link>
          </div>
        }
      />

      {backendError && (
        <div className="mx-5 mb-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {backendError}
        </div>
      )}

      <SystemStatusGrid status={status} />

      <section
        aria-label="チャンネル一覧"
        className="px-5 mt-4 grid grid-cols-2 gap-3"
      >
        {channels.map((ch) => (
          <ChannelCard key={ch.id} channel={ch} />
        ))}
        <NewChannelCard />
      </section>

      <div className="px-5 my-4">
        <Link href="/generate" className="btn-primary w-full">
          ＋ 新規動画を生成
        </Link>
      </div>

      <ActiveJobs initial={jobs} />

      <Suspense fallback={<CardSkeleton label="次回スケジュール" />}>
        <UpcomingSchedules />
      </Suspense>
      <Suspense fallback={<CardSkeleton label="今月のコスト" />}>
        <MonthlyCostSummary />
      </Suspense>
    </main>
  );
}
