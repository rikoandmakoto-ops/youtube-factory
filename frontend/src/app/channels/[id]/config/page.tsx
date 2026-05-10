import { notFound } from 'next/navigation';
import Header from '@/components/Header';
import ConfigEditor from './ConfigEditor';
import {
  getChannelConfig,
  listChannels,
  listAssets,
  ApiError,
  redirectIfUnauthorized,
  type AssetsResponse,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function ChannelConfigPage({
  params,
}: {
  params: { id: string };
}) {
  let config: Record<string, unknown> | null = null;
  let channels: Awaited<ReturnType<typeof listChannels>> = [];
  let assets: AssetsResponse = { assets: {} };
  let backendError: string | null = null;

  try {
    [config, channels, assets] = await Promise.all([
      getChannelConfig(params.id),
      listChannels(),
      listAssets(params.id),
    ]);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    redirectIfUnauthorized(e, `/channels/${params.id}/config`);
    backendError =
      e instanceof ApiError ? e.message : 'バックエンドに接続できません';
  }

  if (backendError || !config) {
    return (
      <main className="pb-20">
        <Header
          title="⚙️ チャンネル設定"
          back={{ href: `/channels/${params.id}`, label: 'チャンネル詳細に戻る' }}
        />
        <div className="mx-5 mt-3 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {backendError ?? '設定を取得できませんでした'}
        </div>
      </main>
    );
  }

  return (
    <main className="pb-20">
      <Header
        title={`⚙️ ${(config as any).name || params.id}`}
        back={{ href: `/channels/${params.id}`, label: 'チャンネル詳細に戻る' }}
      />
      <ConfigEditor
        channelId={params.id}
        initialConfig={config}
        channels={channels}
        initialAssets={assets.assets}
      />
    </main>
  );
}
