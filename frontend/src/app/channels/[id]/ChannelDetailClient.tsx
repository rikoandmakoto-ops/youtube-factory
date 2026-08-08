'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import type { Video } from '@/lib/api';

// Only mounted once the user picks a video to publish, so keep it out of the
// route's initial chunk — it's one of the larger components in the app.
const PublishDialog = dynamic(() => import('@/components/PublishDialog'), {
  ssr: false,
});

const STATUS_STYLES: Record<Video['status'], string> = {
  published: 'bg-emerald-600 text-white',
  draft: 'bg-amber-600 text-white',
  failed: 'bg-red-600 text-white',
  pending: 'bg-slate-500 text-white',
  scheduled: 'bg-purple-600 text-white',
};

const STATUS_LABELS: Record<Video['status'], string> = {
  published: '公開済',
  draft: '下書き',
  failed: '失敗',
  pending: '生成中',
  scheduled: '予約済',
};

function fmtNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return new Intl.NumberFormat('ja-JP').format(n);
}

export default function VideoListClient({
  videos,
  channelYoutubeId,
  channelInternalId,
  defaultTags,
  youtubeConnected,
  defaultShortDelayMinutes,
  defaultPrivacy,
}: {
  videos: Video[];
  channelYoutubeId: string | null | undefined;
  channelInternalId: string;
  defaultTags: string[];
  youtubeConnected: boolean;
  defaultShortDelayMinutes?: number;
  defaultPrivacy?: 'private' | 'unlisted' | 'public';
}) {
  const [items, setItems] = useState<Video[]>(videos);
  const [publishingFor, setPublishingFor] = useState<Video | null>(null);

  const onPublished = (info: { videoId: string; url: string }) => {
    if (!publishingFor) return;
    setItems((prev) =>
      prev.map((v) =>
        v.id === publishingFor.id
          ? {
              ...v,
              status: 'published',
              youtube_url: info.url,
              youtube_video_id: info.videoId,
            }
          : v
      )
    );
  };

  if (items.length === 0) {
    return (
      <div className="card text-center text-sm text-slate-400 py-8">
        まだ動画がありません
      </div>
    );
  }

  return (
    <>
      <ul className="space-y-2">
        {items.map((v) => {
          const canPublish =
            youtubeConnected &&
            (v.status === 'draft' || v.status === 'failed') &&
            v.queue_status === 'completed';
          return (
            <li key={v.id} className="card flex flex-col gap-2">
              <div className="flex gap-3 items-center">
                <div className="w-12 h-12 shrink-0 rounded-lg bg-bg-elev flex items-center justify-center text-2xl">
                  {v.thumbnail_url ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={v.thumbnail_url}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      className="w-full h-full object-cover rounded-lg"
                    />
                  ) : (
                    <span aria-hidden>🎬</span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold truncate">{v.title}</h3>
                  <p className="text-xs text-slate-400 truncate">
                    {v.created_at} · {v.duration} · {fmtNumber(v.views)}再生
                  </p>
                </div>
                <span className={`badge ${STATUS_STYLES[v.status]}`}>
                  {STATUS_LABELS[v.status]}
                </span>
              </div>
              <div className="flex gap-2 flex-wrap">
                {v.youtube_url && (
                  <a
                    href={v.youtube_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-ghost text-xs py-1 px-2"
                  >
                    🔗 YouTubeで開く
                  </a>
                )}
                {canPublish && (
                  <button
                    type="button"
                    onClick={() => setPublishingFor(v)}
                    className="btn-primary text-xs py-1 px-3 ml-auto"
                  >
                    📤 公開
                  </button>
                )}
                {!youtubeConnected && v.queue_status === 'completed' && !v.youtube_url && (
                  <span className="text-[10px] text-slate-500 ml-auto self-center">
                    YouTube未連携
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {publishingFor && (
        <PublishDialog
          open
          onClose={() => setPublishingFor(null)}
          onPublished={onPublished}
          video={publishingFor}
          channelYoutubeId={channelYoutubeId}
          channelInternalId={channelInternalId}
          defaultTags={defaultTags}
          defaultShortDelayMinutes={defaultShortDelayMinutes}
          defaultPrivacy={defaultPrivacy}
        />
      )}
    </>
  );
}
