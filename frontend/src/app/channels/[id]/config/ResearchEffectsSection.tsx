'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Section } from '@/components/Field';
import {
  applyEffectsResearch,
  getLatestEffectsResearch,
  getResearchJob,
  startEffectsResearch,
  type EffectsConfig,
  type EffectsResearchRecord,
  type ResearchJobStatus,
} from '@/lib/api';

const POLL_INTERVAL_MS = 3000;

function formatRelative(epoch?: number | null): string {
  if (!epoch) return '—';
  const ms = epoch * 1000;
  const diff = Date.now() - ms;
  const min = Math.floor(diff / 60000);
  if (min < 1) return 'たった今';
  if (min < 60) return `${min}分前`;
  const hr = Math.floor(min / 60);
  if (hr < 48) return `${hr}時間前`;
  return new Date(ms).toLocaleString('ja-JP', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function PatternBlock({
  title,
  obj,
}: {
  title: string;
  obj: unknown;
}) {
  if (!obj || (typeof obj === 'object' && Object.keys(obj as object).length === 0))
    return null;
  return (
    <details className="bg-slate-800/50 rounded p-3 border border-slate-700">
      <summary className="cursor-pointer text-sm font-semibold text-slate-200">
        {title}
      </summary>
      <pre className="mt-2 text-xs text-slate-300 overflow-x-auto whitespace-pre-wrap">
        {JSON.stringify(obj, null, 2)}
      </pre>
    </details>
  );
}

export default function ResearchEffectsSection({
  channelId,
}: {
  channelId: string;
}) {
  const [latest, setLatest] = useState<EffectsResearchRecord | null>(null);
  const [loadingLatest, setLoadingLatest] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [job, setJob] = useState<ResearchJobStatus | null>(null);
  const [applying, setApplying] = useState(false);
  const [starting, setStarting] = useState(false);
  const [autoApply, setAutoApply] = useState(false);
  const [targetChannels, setTargetChannels] = useState(7);
  const [videosPerChannel, setVideosPerChannel] = useState(2);
  const pollTimer = useRef<number | null>(null);

  const flash = (msg: string) => {
    setInfo(msg);
    window.setTimeout(() => setInfo((m) => (m === msg ? null : m)), 3500);
  };

  const refreshLatest = useCallback(async () => {
    setLoadingLatest(true);
    try {
      const r = await getLatestEffectsResearch(channelId);
      setLatest(r.latest);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
    } finally {
      setLoadingLatest(false);
    }
  }, [channelId]);

  useEffect(() => {
    refreshLatest();
  }, [refreshLatest]);

  // Poll active job
  useEffect(() => {
    if (!job || job.status === 'done' || job.status === 'failed') {
      if (pollTimer.current) {
        window.clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
      return;
    }
    if (pollTimer.current) return;
    pollTimer.current = window.setInterval(async () => {
      try {
        const upd = await getResearchJob(channelId, job.job_id);
        setJob(upd);
        if (upd.status === 'done') {
          flash('✅ リサーチ完了');
          refreshLatest();
        } else if (upd.status === 'failed') {
          setError(upd.error || 'research failed');
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'poll failed');
      }
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollTimer.current) {
        window.clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
    };
  }, [job, channelId, refreshLatest]);

  const onStart = async () => {
    setError(null);
    setStarting(true);
    try {
      const r = await startEffectsResearch(channelId, {
        target_channels: targetChannels,
        videos_per_channel: videosPerChannel,
        auto_apply: autoApply,
        run_in_background: true,
      });
      setJob({ job_id: r.job_id, status: 'queued', channel_id: channelId });
      flash('🚀 リサーチを起動しました（数分かかります）');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
    } finally {
      setStarting(false);
    }
  };

  const onApply = async (rec: EffectsResearchRecord) => {
    const effects = rec.suggested_effects;
    if (!effects) {
      setError('適用可能な effects 設定がありません');
      return;
    }
    if (!confirm(`この演出設定を ${channelId} の channel JSON に書き込みます。よろしいですか？`))
      return;
    setApplying(true);
    setError(null);
    try {
      await applyEffectsResearch(channelId, rec.id, effects);
      flash('✅ channel JSON に適用しました');
      refreshLatest();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
    } finally {
      setApplying(false);
    }
  };

  const showRunning = job && (job.status === 'queued' || job.status === 'running');

  return (
    <Section title="🔬 競合演出リサーチ" defaultOpen={false}>
      <div className="space-y-3 text-sm text-slate-300">
        <p className="text-slate-400">
          このチャンネルのジャンルに近い人気 YouTube
          チャンネルを自動検索し、サムネ＋ランダムフレーム＋字幕を
          Claude Vision で分析して画面演出パターンを抽出します。結果は
          <code className="bg-slate-800 px-1 mx-1 rounded">video_format.effects</code>
          に反映可能です。
        </p>

        {/* Controls */}
        <div className="flex flex-wrap gap-3 items-end p-3 bg-slate-800/40 rounded border border-slate-700">
          <label className="flex flex-col text-xs text-slate-400">
            分析チャンネル数
            <input
              type="number"
              min={1}
              max={15}
              value={targetChannels}
              onChange={(e) => setTargetChannels(Math.max(1, Math.min(15, Number(e.target.value) || 7)))}
              className="mt-1 w-20 px-2 py-1 rounded bg-slate-900 border border-slate-700 text-slate-100"
              disabled={!!showRunning || starting}
            />
          </label>
          <label className="flex flex-col text-xs text-slate-400">
            1ch あたり動画数
            <input
              type="number"
              min={1}
              max={5}
              value={videosPerChannel}
              onChange={(e) => setVideosPerChannel(Math.max(1, Math.min(5, Number(e.target.value) || 2)))}
              className="mt-1 w-20 px-2 py-1 rounded bg-slate-900 border border-slate-700 text-slate-100"
              disabled={!!showRunning || starting}
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={autoApply}
              onChange={(e) => setAutoApply(e.target.checked)}
              disabled={!!showRunning || starting}
            />
            完了したら自動で JSON に反映
          </label>
          <button
            type="button"
            onClick={onStart}
            disabled={!!showRunning || starting}
            className="px-4 py-2 rounded bg-accent text-white text-sm font-semibold disabled:opacity-50"
          >
            {starting
              ? '起動中…'
              : showRunning
                ? job?.status === 'running'
                  ? `分析中… (${job.progress?.done ?? 0}/${job.progress?.total ?? '?'})`
                  : '実行中…'
                : '🔬 競合演出リサーチ実行'}
          </button>
        </div>

        {info && <div className="text-emerald-300 text-xs">{info}</div>}
        {error && <div className="text-rose-400 text-xs">⚠ {error}</div>}

        {/* Live job progress */}
        {showRunning && job && (
          <div className="p-3 bg-slate-900/60 rounded border border-slate-700">
            <div className="text-xs text-slate-400">ジョブ {job.job_id}</div>
            <div className="text-sm text-slate-200 mt-1">
              ステータス: {job.status}
              {job.progress && (
                <span className="ml-2 text-slate-400">
                  {job.progress.done}/{job.progress.total} — {job.progress.label}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Latest result */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-slate-200">最新リサーチ結果</h4>
            <button
              type="button"
              onClick={refreshLatest}
              className="text-xs text-slate-400 hover:text-slate-200"
            >
              再読み込み
            </button>
          </div>

          {loadingLatest ? (
            <div className="text-slate-500 text-xs">読み込み中…</div>
          ) : !latest ? (
            <div className="text-slate-500 text-xs">
              まだリサーチ実行履歴がありません。
            </div>
          ) : (
            <div className="space-y-3 p-3 bg-slate-900/40 rounded border border-slate-700">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                <span>レコード #{latest.id}</span>
                <span>ジャンル: {latest.genre || '—'}</span>
                <span>実行: {formatRelative(latest.finished_at)}</span>
                <span>対象: {latest.channels_analyzed?.length ?? 0} チャンネル</span>
                <span className={latest.applied ? 'text-emerald-300' : 'text-amber-300'}>
                  {latest.applied ? '✅ 適用済み' : '⚠ 未適用'}
                </span>
              </div>

              {latest.error && (
                <div className="text-rose-300 text-xs">エラー: {latest.error}</div>
              )}

              {/* Channels analyzed */}
              {latest.channels_analyzed && latest.channels_analyzed.length > 0 && (
                <details className="bg-slate-800/50 rounded p-2 border border-slate-700">
                  <summary className="cursor-pointer text-xs text-slate-200">
                    分析した競合チャンネル ({latest.channels_analyzed.length})
                  </summary>
                  <ul className="mt-2 space-y-1 text-xs text-slate-300">
                    {latest.channels_analyzed.map((c) => (
                      <li key={c.channel_id}>
                        <span className="text-slate-100">{c.channel_title}</span>
                        <span className="text-slate-500"> — {c.videos?.length ?? c.video_ids?.length ?? 0} 本</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {/* Suggested effects */}
              {latest.suggested_effects && (
                <div className="bg-slate-800/70 rounded p-3 border border-emerald-700/40">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-semibold text-emerald-300">
                      提案された演出設定 (effects)
                    </div>
                    <button
                      type="button"
                      onClick={() => onApply(latest)}
                      disabled={applying}
                      className="px-3 py-1 rounded bg-emerald-600 text-white text-xs disabled:opacity-50"
                    >
                      {applying ? '適用中…' : '🎬 この設定を適用'}
                    </button>
                  </div>
                  <pre className="text-xs text-slate-200 overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(latest.suggested_effects, null, 2)}
                  </pre>
                </div>
              )}

              {/* Aggregated patterns */}
              {latest.aggregated_patterns && (
                <PatternBlock
                  title="📊 集約された画面演出パターン"
                  obj={latest.aggregated_patterns}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </Section>
  );
}
