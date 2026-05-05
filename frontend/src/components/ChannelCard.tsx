import Link from 'next/link';
import type { Channel } from '@/lib/api';

const ICONS: Record<string, string> = {
  'daily-science': '🧪',
};

function fmtNumber(n: number | undefined): string {
  if (n === undefined || n === null) return '—';
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export default function ChannelCard({ channel }: { channel: Channel }) {
  const icon = ICONS[channel.id] ?? '📺';
  return (
    <Link
      href={`/channels/${encodeURIComponent(channel.id)}`}
      className="card flex flex-col gap-2 active:scale-[.99] transition"
    >
      <div className="flex items-center gap-2">
        <span aria-hidden className="text-base">
          {icon}
        </span>
        <h3 className="font-bold text-slate-100 truncate">{channel.name}</h3>
      </div>
      <div className="text-xs text-slate-500">{channel.id}</div>
      <dl className="grid grid-cols-3 gap-2 mt-2">
        <div>
          <dd className="font-bold text-lg">{fmtNumber(channel.video_count)}</dd>
          <dt className="text-xs text-slate-400">動画</dt>
        </div>
        <div>
          <dd className="font-bold text-lg">{fmtNumber(channel.total_views)}</dd>
          <dt className="text-xs text-slate-400">再生</dt>
        </div>
        <div>
          <dd className="font-bold text-lg">{fmtNumber(channel.subscribers)}</dd>
          <dt className="text-xs text-slate-400">登録</dt>
        </div>
      </dl>
    </Link>
  );
}

export function NewChannelCard() {
  return (
    <Link
      href="/channels/new"
      className="card border-dashed text-center text-slate-500 hover:text-slate-300 flex flex-col items-center justify-center min-h-[150px] active:scale-[.99] transition"
    >
      <div className="text-2xl">＋</div>
      <div className="text-sm mt-1">新規チャンネル</div>
    </Link>
  );
}
