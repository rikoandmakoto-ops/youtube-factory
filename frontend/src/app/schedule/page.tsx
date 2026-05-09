import Header from '@/components/Header';
import ScheduleManager from './ScheduleManager';
import {
  listChannels,
  listSchedules,
  ApiError,
  redirectIfUnauthorized,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function SchedulePage() {
  const results = await Promise.allSettled([listChannels(), listSchedules()]);
  redirectIfUnauthorized(results, '/schedule');
  const [chRes, schRes] = results;
  const channels = chRes.status === 'fulfilled' ? chRes.value : [];
  const schedules = schRes.status === 'fulfilled' ? schRes.value.schedules : [];
  const schedulerAvailable =
    schRes.status === 'fulfilled' ? schRes.value.scheduler_available : false;
  const error =
    chRes.status === 'rejected'
      ? chRes.reason instanceof ApiError
        ? chRes.reason.message
        : 'チャンネル取得に失敗'
      : schRes.status === 'rejected'
      ? schRes.reason instanceof ApiError
        ? schRes.reason.message
        : 'スケジュール取得に失敗'
      : null;

  return (
    <main className="pb-10">
      <Header
        title="⏰ スケジュール投稿"
        back={{ href: '/', label: 'ダッシュボードに戻る' }}
      />
      {error && (
        <div className="mx-5 mb-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {error}
        </div>
      )}
      {!schedulerAvailable && (
        <div className="mx-5 mb-3 rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-xs text-amber-300">
          ⚠️ APScheduler 未インストール: <code>pip install apscheduler</code>
          を実行してサーバを再起動してください
        </div>
      )}
      <ScheduleManager initialSchedules={schedules} channels={channels} />
    </main>
  );
}
