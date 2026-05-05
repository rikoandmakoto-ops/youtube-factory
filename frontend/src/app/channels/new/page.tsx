import Header from '@/components/Header';
import NewChannelForm from './NewChannelForm';
import { listChannels, ApiError } from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function NewChannelPage() {
  let templates: Awaited<ReturnType<typeof listChannels>> = [];
  let error: string | null = null;
  try {
    templates = await listChannels();
  } catch (e) {
    error = e instanceof ApiError ? e.message : 'チャンネル一覧を取得できません';
  }
  return (
    <main className="pb-10">
      <Header
        title="🆕 新規チャンネル"
        back={{ href: '/', label: 'ダッシュボードに戻る' }}
      />
      {error && (
        <div className="mx-5 mb-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {error}
        </div>
      )}
      <NewChannelForm templates={templates} />
    </main>
  );
}
