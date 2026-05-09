import Header from '@/components/Header';
import SettingsForm from './SettingsForm';
import { getSettings, ApiError, redirectIfUnauthorized } from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function SettingsPage() {
  let settings = null;
  let error: string | null = null;
  try {
    settings = await getSettings();
  } catch (e) {
    redirectIfUnauthorized(e, '/settings');
    error = e instanceof ApiError ? e.message : '設定を取得できませんでした';
  }
  return (
    <main className="pb-10">
      <Header
        title="⚙️ 設定"
        back={{ href: '/', label: 'ダッシュボードに戻る' }}
      />
      {error && (
        <div className="mx-5 mb-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {error}
        </div>
      )}
      {settings && <SettingsForm initial={settings} />}
    </main>
  );
}
