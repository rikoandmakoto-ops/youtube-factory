import Header from '@/components/Header';
import LogsView from './LogsView';
import {
  getServerLogs,
  ApiError,
  redirectIfUnauthorized,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function LogsPage() {
  const results = await Promise.allSettled([getServerLogs({ lines: 200 })]);
  redirectIfUnauthorized(results, '/logs');
  const [r] = results;
  const initial = r.status === 'fulfilled' ? r.value : null;
  const error =
    r.status === 'rejected'
      ? r.reason instanceof ApiError
        ? r.reason.message
        : 'ログ取得に失敗'
      : null;

  return (
    <main className="pb-10">
      <Header
        title="📜 サーバーログ"
        back={{ href: '/', label: 'ダッシュボードに戻る' }}
      />
      {error && (
        <div className="mx-5 mb-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {error}
        </div>
      )}
      <LogsView initial={initial} />
    </main>
  );
}
