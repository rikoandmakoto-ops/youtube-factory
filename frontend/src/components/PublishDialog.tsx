'use client';

import { useEffect, useRef, useState } from 'react';
import type { PublishJob, Video } from '@/lib/api';

type Props = {
  open: boolean;
  onClose: () => void;
  onPublished: (info: { videoId: string; url: string }) => void;
  video: Video;
  channelYoutubeId?: string | null;
  channelInternalId?: string | null;
  defaultTags?: string[];
  /** チャンネル設定の publish_settings から渡す既定値 */
  defaultShortDelayMinutes?: number;
  defaultPrivacy?: 'private' | 'unlisted' | 'public';
};

type PairJob = {
  id: string;
  status:
    | 'queued'
    | 'uploading_main'
    | 'main_uploaded'
    | 'uploading_short'
    | 'completed'
    | 'failed';
  step?: string;
  progress: number;
  main?: { video_id: string; url: string; publish_at?: string | null } | null;
  short?: { video_id: string; url: string; publish_at?: string | null } | null;
  error?: string | null;
};

function getVideoPath(v: Video): string | null {
  const r = v.result as Record<string, unknown> | null | undefined;
  if (!r) return null;
  for (const key of ['full_video_path', 'video_path', 'main_video_path', 'output_path']) {
    const val = r[key];
    if (typeof val === 'string') return val;
  }
  // 各種ネスト形式に対応
  for (const key of ['main', 'full']) {
    const m = r[key] as Record<string, unknown> | undefined;
    if (typeof m === 'string') return m;
    if (m && typeof m['video_path'] === 'string') return m['video_path'] as string;
  }
  return null;
}

function getShortVideoPath(v: Video): string | null {
  const r = v.result as Record<string, unknown> | null | undefined;
  if (!r) return null;
  const s = r['short'];
  if (typeof s === 'string') return s;
  if (s && typeof s === 'object' && typeof (s as Record<string, unknown>)['video_path'] === 'string') {
    return (s as Record<string, string>)['video_path'];
  }
  if (typeof r['short_video_path'] === 'string') return r['short_video_path'] as string;
  return null;
}

function getThumbnailPath(v: Video): string | null {
  const r = v.result as Record<string, unknown> | null | undefined;
  if (!r) return null;
  for (const key of ['thumbnail_path', 'thumb_path', 'thumbnail']) {
    const val = r[key];
    if (typeof val === 'string') return val;
  }
  return null;
}

export default function PublishDialog({
  open,
  onClose,
  onPublished,
  video,
  channelYoutubeId,
  channelInternalId,
  defaultTags,
  defaultShortDelayMinutes,
  defaultPrivacy,
}: Props) {
  const [title, setTitle] = useState(video.title);
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState((defaultTags || []).join(' '));
  const [privacy, setPrivacy] = useState<'private' | 'unlisted' | 'public'>(
    defaultPrivacy ?? 'unlisted'
  );
  const [scheduled, setScheduled] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<PublishJob | null>(null);
  const [pairJob, setPairJob] = useState<PairJob | null>(null);
  const [pairMode, setPairMode] = useState(false);
  const [shortDelay, setShortDelay] = useState<number>(
    defaultShortDelayMinutes ?? 10
  );
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pairPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const hasShort = !!getShortVideoPath(video);

  useEffect(() => {
    if (!open) return;
    setTitle(video.title);
    setError(null);
    setJob(null);
    setPairJob(null);
    setPrivacy(defaultPrivacy ?? 'unlisted');
    setShortDelay(defaultShortDelayMinutes ?? 10);
    setPairMode(false);
  }, [open, video, defaultPrivacy, defaultShortDelayMinutes]);

  // ── 単発公開のポーリング ──
  useEffect(() => {
    if (!job?.id) return;
    if (job.status === 'completed' || job.status === 'failed') return;
    pollRef.current = setInterval(async () => {
      const res = await fetch(
        `/api/youtube/publish/${encodeURIComponent(job.id)}`,
        { cache: 'no-store' }
      );
      if (!res.ok) return;
      const next: PublishJob = await res.json();
      setJob(next);
      if (next.status === 'completed' || next.status === 'failed') {
        if (pollRef.current) clearInterval(pollRef.current);
        if (next.status === 'completed' && next.video_id && next.url) {
          await fetch(`/api/videos/${encodeURIComponent(video.id)}/status`, {
            method: 'PUT',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
              status: scheduled ? 'scheduled' : 'published',
              video_id: next.video_id,
              url: next.url,
              scheduled_at: scheduled || undefined,
            }),
          });
          onPublished({ videoId: next.video_id, url: next.url });
        }
      }
    }, 1500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [job?.id, video.id, scheduled, onPublished]);

  // ── ペア公開のポーリング ──
  useEffect(() => {
    if (!pairJob?.id) return;
    if (pairJob.status === 'completed' || pairJob.status === 'failed') return;
    pairPollRef.current = setInterval(async () => {
      const res = await fetch(
        `/api/youtube/publish-pair/${encodeURIComponent(pairJob.id)}`,
        { cache: 'no-store' }
      );
      if (!res.ok) return;
      const next: PairJob = await res.json();
      setPairJob(next);
      if (next.status === 'completed' || next.status === 'failed') {
        if (pairPollRef.current) clearInterval(pairPollRef.current);
        if (next.status === 'completed' && next.main?.video_id && next.main.url) {
          onPublished({ videoId: next.main.video_id, url: next.main.url });
        }
      }
    }, 1500);
    return () => {
      if (pairPollRef.current) clearInterval(pairPollRef.current);
    };
  }, [pairJob?.id, onPublished]);

  if (!open) return null;

  const videoPath = getVideoPath(video);
  const thumbnailPath = getThumbnailPath(video);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (pairMode) {
        if (!hasShort) {
          throw new Error('ショート動画がこのジョブにありません');
        }
        const payload = {
          job_id: video.id,
          channel_id: channelInternalId || undefined,
          main_title: title,
          main_description: description || undefined,
          tags: tags
            .split(/[\s,、]+/g)
            .map((t) => t.trim())
            .filter(Boolean),
          privacy,
          short_delay_minutes: Math.max(1, Math.floor(shortDelay)),
          youtube_channel_id: channelYoutubeId || null,
        };
        const res = await fetch('/api/youtube/publish-pair', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(await res.text());
        const data: { job_id: string } = await res.json();
        setPairJob({ id: data.job_id, status: 'queued', progress: 0 });
        return;
      }

      // 単発公開
      if (!videoPath) {
        throw new Error('動画ファイルパスが見つかりません（result から取得不可）');
      }
      const payload = {
        video_path: videoPath,
        thumbnail_path: thumbnailPath,
        title,
        description,
        tags: tags
          .split(/[\s,、]+/g)
          .map((t) => t.trim())
          .filter(Boolean),
        privacy,
        scheduled_at: scheduled || null,
        youtube_channel_id: channelYoutubeId || null,
      };
      const res = await fetch('/api/youtube/publish', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: { job_id: string } = await res.json();
      setJob({
        id: data.job_id,
        status: 'queued',
        progress: 0,
        title,
        started_at: new Date().toISOString(),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
    } finally {
      setSubmitting(false);
    }
  };

  const inProgress = job || pairJob;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm p-2"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="card w-full max-w-md max-h-[90vh] overflow-auto">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-bold text-lg">📤 YouTube に公開</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 text-xl"
            aria-label="閉じる"
          >
            ×
          </button>
        </div>

        {!videoPath && !pairMode && (
          <p className="text-sm text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 mb-3">
            ⚠️ 動画ファイルパスが取得できません。再生成してから公開してください。
          </p>
        )}

        {!inProgress ? (
          <form onSubmit={submit} className="space-y-3">
            {hasShort && (
              <label className="flex items-center gap-2 text-sm bg-bg-elev border border-border rounded-lg px-3 py-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={pairMode}
                  onChange={(e) => setPairMode(e.target.checked)}
                />
                <span>
                  メイン+ショートをペア公開する
                  <span className="text-xs text-slate-400 ml-2">
                    (メインを即時公開 → ショートを {shortDelay} 分後に予約公開)
                  </span>
                </span>
              </label>
            )}

            <div>
              <label className="label">
                {pairMode ? 'メイン動画のタイトル' : 'タイトル'}
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="input"
                maxLength={100}
                required
              />
              <p className="text-xs text-slate-500 mt-1">{title.length}/100</p>
            </div>

            <div>
              <label className="label">
                {pairMode ? 'メイン動画の説明' : '説明'}
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="input min-h-[120px]"
                maxLength={5000}
                placeholder={
                  pairMode
                    ? '空欄ならジョブの説明文ファイルを使います'
                    : '動画の説明文'
                }
              />
              {pairMode && (
                <p className="text-xs text-slate-500 mt-1">
                  ショートの説明欄にはメインのURLが自動で挿入されます。
                </p>
              )}
            </div>

            <div>
              <label className="label">タグ（スペース区切り）</label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                className="input"
                placeholder="ゆっくり解説 雑学 科学"
              />
            </div>

            <div>
              <label className="label">公開ステータス</label>
              <div role="radiogroup" className="grid grid-cols-3 gap-2">
                {(['private', 'unlisted', 'public'] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    role="radio"
                    aria-checked={privacy === p}
                    onClick={() => setPrivacy(p)}
                    className={`btn py-2 text-sm ${
                      privacy === p
                        ? 'bg-accent text-white'
                        : 'bg-bg-elev text-slate-300 border border-border'
                    }`}
                  >
                    {p === 'private' ? '非公開' : p === 'unlisted' ? '限定公開' : '公開'}
                  </button>
                ))}
              </div>
            </div>

            {pairMode ? (
              <div>
                <label className="label">
                  ショートをメインの何分後に公開する？
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={1}
                    max={1440}
                    value={shortDelay}
                    onChange={(e) =>
                      setShortDelay(parseInt(e.target.value, 10) || 1)
                    }
                    className="input w-28"
                  />
                  <span className="text-sm text-slate-400">分後</span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  YouTube ネイティブの予約公開機能を使うので、サーバが落ちても予定時刻に公開されます。
                </p>
              </div>
            ) : (
              <div>
                <label className="label">予約投稿（任意）</label>
                <input
                  type="datetime-local"
                  value={scheduled}
                  onChange={(e) => setScheduled(e.target.value)}
                  className="input"
                />
                <p className="text-xs text-slate-500 mt-1">
                  指定時は「非公開で予約」として扱われます
                </p>
              </div>
            )}

            {error && (
              <p
                role="alert"
                className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
              >
                {error}
              </p>
            )}

            <div className="flex gap-2 sticky bottom-0 bg-bg-card pt-2">
              <button
                type="button"
                onClick={onClose}
                className="btn-secondary flex-1"
              >
                キャンセル
              </button>
              <button
                type="submit"
                disabled={
                  submitting ||
                  !title ||
                  (!pairMode && !videoPath) ||
                  (pairMode && !hasShort)
                }
                className="btn-primary flex-1"
              >
                {submitting
                  ? '送信中…'
                  : pairMode
                  ? '🚀 ペアで公開する'
                  : '🚀 公開する'}
              </button>
            </div>
          </form>
        ) : pairJob ? (
          <PairProgress pairJob={pairJob} onClose={onClose} />
        ) : job ? (
          <SingleProgress job={job} onClose={onClose} />
        ) : null}
      </div>
    </div>
  );
}

function SingleProgress({
  job,
  onClose,
}: {
  job: PublishJob;
  onClose: () => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-300">
        ステータス:{' '}
        <b>
          {job.status === 'queued'
            ? '待機中'
            : job.status === 'uploading'
            ? 'アップロード中'
            : job.status === 'completed'
            ? '✅ 完了'
            : '❌ 失敗'}
        </b>
      </p>
      <div className="h-2 rounded bg-bg-elev overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-accent to-purple-500 transition-all"
          style={{ width: `${Math.max(2, job.progress)}%` }}
        />
      </div>
      <p className="text-xs text-slate-400">{Math.round(job.progress)}%</p>
      {job.status === 'completed' && job.url && (
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary w-full"
        >
          🔗 YouTube で開く
        </a>
      )}
      {job.status === 'failed' && (
        <p
          role="alert"
          className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
        >
          {job.error || '失敗しました'}
        </p>
      )}
      {job.thumbnail_error && (
        <p className="text-xs text-amber-400">
          ⚠️ サムネイル設定失敗: {job.thumbnail_error}
        </p>
      )}
      <button type="button" onClick={onClose} className="btn-secondary w-full">
        閉じる
      </button>
    </div>
  );
}

function PairProgress({
  pairJob,
  onClose,
}: {
  pairJob: PairJob;
  onClose: () => void;
}) {
  const label =
    pairJob.status === 'queued'
      ? '待機中'
      : pairJob.status === 'uploading_main'
      ? 'メイン動画アップロード中…'
      : pairJob.status === 'main_uploaded'
      ? 'メイン公開完了 — ショート準備中'
      : pairJob.status === 'uploading_short'
      ? 'ショート動画アップロード中…'
      : pairJob.status === 'completed'
      ? '✅ ペア公開完了'
      : '❌ 失敗';

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-300">
        ステータス: <b>{label}</b>
      </p>
      {pairJob.step && (
        <p className="text-xs text-slate-400">{pairJob.step}</p>
      )}
      <div className="h-2 rounded bg-bg-elev overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-accent to-purple-500 transition-all"
          style={{ width: `${Math.max(2, pairJob.progress)}%` }}
        />
      </div>
      <p className="text-xs text-slate-400">{Math.round(pairJob.progress)}%</p>

      {pairJob.main?.url && (
        <div className="rounded-lg bg-bg-elev border border-border px-3 py-2 text-sm">
          <p className="text-slate-400 text-xs mb-1">📺 メイン (公開済み)</p>
          <a
            href={pairJob.main.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline break-all"
          >
            {pairJob.main.url}
          </a>
        </div>
      )}
      {pairJob.short?.url && (
        <div className="rounded-lg bg-bg-elev border border-border px-3 py-2 text-sm">
          <p className="text-slate-400 text-xs mb-1">
            🎬 ショート{' '}
            {pairJob.short.publish_at
              ? `(公開予定: ${pairJob.short.publish_at})`
              : ''}
          </p>
          <a
            href={pairJob.short.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline break-all"
          >
            {pairJob.short.url}
          </a>
        </div>
      )}

      {pairJob.status === 'failed' && (
        <p
          role="alert"
          className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
        >
          {pairJob.error || '失敗しました'}
        </p>
      )}

      <button type="button" onClick={onClose} className="btn-secondary w-full">
        閉じる
      </button>
    </div>
  );
}
