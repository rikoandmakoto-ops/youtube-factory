import Header from '@/components/Header';
import HistoryView from './HistoryView';
import {
  listChannels,
  listHistory,
  getCostSummary,
  ApiError,
  redirectIfUnauthorized,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function HistoryPage() {
  const results = await Promise.allSettled([
    listChannels(),
    listHistory({ limit: 200 }),
    getCostSummary(),
  ]);
  redirectIfUnauthorized(results, '/history');
  const [chRes, hisRes, costRes] = results;
  const channels = chRes.status === 'fulfilled' ? chRes.value : [];
  const history = hisRes.status === 'fulfilled' ? hisRes.value.history : [];
  const cost = costRes.status === 'fulfilled' ? costRes.value : null;
  const error =
    hisRes.status === 'rejected'
      ? hisRes.reason instanceof ApiError
        ? hisRes.reason.message
        : '履歴取得に失敗'
      : null;

  return (
    <main className="pb-10">
      <Header
        title="📊 履歴・コスト"
        back={{ href: '/', label: 'ダッシュボードに戻る' }}
      />
      {error && (
        <div className="mx-5 mb-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {error}
        </div>
      )}
      <HistoryView channels={channels} initialHistory={history} initialCost={cost} />
    </main>
  );
}
