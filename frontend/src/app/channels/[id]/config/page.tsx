import { notFound } from 'next/navigation';
import Header from '@/components/Header';
import ConfigEditor from './ConfigEditor';
import {
  getChannelConfig,
  listChannels,
  listAssets,
  ApiError,
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

  try {
    [config, channels, assets] = await Promise.all([
      getChannelConfig(params.id),
      listChannels(),
      listAssets(params.id),
    ]);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  if (!config) notFound();

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
