import Header from '@/components/Header';
import GenerateForm from './GenerateForm';
import { listChannels, ApiError, redirectIfUnauthorized } from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function GeneratePage({
  searchParams,
}: {
  searchParams: { channel?: string };
}) {
  let channels = [] as Awaited<ReturnType<typeof listChannels>>;
  let error: string | null = null;
  try {
    channels = await listChannels();
  } catch (e) {
    redirectIfUnauthorized(e, '/generate');
    error = e instanceof ApiError ? e.message : 'チャンネル一覧を取得できません';
  }

  return (
    <main className="pb-10">
      <Header
        title="🎬 動画を生成"
        back={{ href: '/', label: '戻る' }}
      />
      {error ? (
        <div className="mx-5 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {error}
        </div>
      ) : (
        <GenerateForm channels={channels} initialChannelId={searchParams?.channel} />
      )}
    </main>
  );
}
