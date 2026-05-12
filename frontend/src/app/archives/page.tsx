import Header from '@/components/Header';
import ArchivesView from './ArchivesView';
import {
  listScenarioArchives,
  ApiError,
  redirectIfUnauthorized,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function ArchivesPage() {
  const results = await Promise.allSettled([listScenarioArchives({ limit: 200 })]);
  redirectIfUnauthorized(results, '/archives');
  const [r] = results;
  const initial = r.status === 'fulfilled' ? r.value : null;
  const error =
    r.status === 'rejected'
      ? r.reason instanceof ApiError
        ? r.reason.message
        : 'シナリオ取得に失敗'
      : null;

  return (
    <main className="pb-10">
      <Header
        title="📚 シナリオアーカイブ"
        back={{ href: '/', label: 'ダッシュボードに戻る' }}
      />
      {error && (
        <div className="mx-5 mb-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {error}
        </div>
      )}
      <ArchivesView initial={initial} />
    </main>
  );
}
