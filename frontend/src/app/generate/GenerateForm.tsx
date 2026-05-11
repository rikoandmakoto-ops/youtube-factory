'use client';

import { useEffect, useRef, useState } from 'react';
import type {
  Channel,
  GenerateStatus,
  SampleIllustrationResponse,
  Template,
  ThumbnailGenerateResponse,
  Variant,
} from '@/lib/api';

const DURATIONS = [8, 12, 15] as const;
type Duration = (typeof DURATIONS)[number];

const STEPS = [
  { id: 1, label: 'シナリオ', short: '1.シナリオ' },
  { id: 2, label: 'イラスト', short: '2.イラスト' },
  { id: 3, label: 'TTS', short: '3.TTS' },
  { id: 4, label: 'エンコード', short: '4.エンコ' },
  { id: 5, label: '出力', short: '5.出力' },
];

/**
 * fetch() がネットワーク層で失敗したかどうか。Safari は "Load failed"、
 * Chromium は "Failed to fetch" を投げる。ユーザーが別タブに移動して
 * 戻ってきた直後によく発生する一過性のエラーで、画面に出すとパニックの元。
 */
function isNetworkError(e: unknown): boolean {
  if (e instanceof DOMException && e.name === 'AbortError') return true;
  if (e instanceof TypeError) {
    const msg = e.message || '';
    return (
      msg.includes('Load failed') ||
      msg.includes('Failed to fetch') ||
      msg.includes('NetworkError') ||
      msg.includes('network')
    );
  }
  return false;
}

function networkErrorMessage(e: unknown, fallback: string): string {
  if (isNetworkError(e)) {
    return '通信が一時的に切れました。タブを開いたまま、もう一度お試しください。';
  }
  return e instanceof Error ? e.message : fallback;
}

export default function GenerateForm({
  channels,
  initialChannelId,
}: {
  channels: Channel[];
  initialChannelId?: string;
}) {
  const [channelId, setChannelId] = useState(
    initialChannelId || channels[0]?.id || ''
  );
  const [theme, setTheme] = useState('');
  const [duration, setDuration] = useState<Duration>(12);
  const [generateShort, setGenerateShort] = useState(true);
  const [generateThumbnail, setGenerateThumbnail] = useState(true);
  const [autoPublish, setAutoPublish] = useState(false);
  const [publishMode, setPublishMode] = useState<'immediate' | 'scheduled'>(
    'immediate'
  );
  // <input type="datetime-local"> 用 (例 "2026-05-15T19:30")。空文字=未指定
  const [scheduledAt, setScheduledAt] = useState('');
  const [copyToIcloud, setCopyToIcloud] = useState(true);
  const [abTest, setAbTest] = useState(false);
  // BGM音量: UIは0-100%, バックエンドへは0..1で送る
  const [bgmVolumePct, setBgmVolumePct] = useState(30);

  // BGMプレビュー
  const [bgmPreviewUrl, setBgmPreviewUrl] = useState<string | null>(null);
  const [bgmPreviewLoading, setBgmPreviewLoading] = useState(false);
  const [bgmPreviewError, setBgmPreviewError] = useState<string | null>(null);
  const [bgmPreviewMeta, setBgmPreviewMeta] = useState<{
    bgm_filename: string | null;
    voicevox_used: boolean;
  } | null>(null);

  const [suggesting, setSuggesting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<GenerateStatus | null>(null);
  const [publishMsg, setPublishMsg] = useState<string | null>(null);
  const [ytConnected, setYtConnected] = useState<boolean | null>(null);

  // Templates
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [templateSaveName, setTemplateSaveName] = useState('');
  const [showTemplatePanel, setShowTemplatePanel] = useState(false);
  const [templateMsg, setTemplateMsg] = useState<string | null>(null);

  // A/B variants
  const [variants, setVariants] = useState<{
    title: Variant[];
    thumbnail: Variant[];
  } | null>(null);
  const [variantsLoading, setVariantsLoading] = useState(false);

  // サンプル画像（本生成前の承認ゲート）
  const [sample, setSample] = useState<SampleIllustrationResponse | null>(null);
  const [sampling, setSampling] = useState(false);
  const [sampleApproved, setSampleApproved] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);
  // フィードバック履歴（古い→新しい順）。「ここをこう直して」の入力。
  const [sampleFeedback, setSampleFeedback] = useState<string[]>([]);
  const [sampleFeedbackDraft, setSampleFeedbackDraft] = useState('');
  // 非同期ジョブID — start → poll の流れでタブ移動に強くする。
  const [sampleJobId, setSampleJobId] = useState<string | null>(null);

  // サムネイルプレビュー（HTML+Playwright パイプライン）
  const [thumb, setThumb] = useState<ThumbnailGenerateResponse | null>(null);
  const [thumbBusy, setThumbBusy] = useState<'fresh' | 'reuse' | null>(null);
  const [thumbError, setThumbError] = useState<string | null>(null);
  const [thumbFeedback, setThumbFeedback] = useState<string[]>([]);
  const [thumbFeedbackDraft, setThumbFeedbackDraft] = useState('');
  // 非同期ジョブID — start → poll の流れでタブ移動に強くする。
  const [thumbJobId, setThumbJobId] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoPublishedRef = useRef(false);
  const abAutoTriggeredRef = useRef(false);
  // 走行中ジョブを再接続したばかりかを示すフラグ。
  // 直後に走る channel/theme 変更リセット効果が sampleApproved を上書きするのを防ぐ。
  const justAttachedRef = useRef(false);
  // サムネ生成が reuse モードで完了したら、旧 thumbnail_id を消す。
  // polling 完了側で使えるよう、コンポーネントトップで保持する。
  const pendingReuseDeleteRef = useRef<string | null>(null);

  // ページ移動から戻ったときに、サーバ側で走っているジョブに自動で再接続。
  // /api/jobs/active が pending/running のジョブを返すので、最初の1件を採用する。
  // 既に jobId がある場合（同セッション内で開始済み）は何もしない。
  useEffect(() => {
    if (jobId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/jobs/active', { cache: 'no-store' });
        if (!res.ok) return;
        const data = await res.json();
        const active = (data?.jobs ?? []) as Array<{
          job_id: string;
          channel_id?: string | null;
        }>;
        if (cancelled || active.length === 0) return;
        // 同じチャンネルの走行ジョブを優先（複数チャンネルに対応）。
        const match =
          active.find((j) => j.channel_id && j.channel_id === channelId) ||
          active[0];
        justAttachedRef.current = true;
        setJobId(match.job_id);
        if (match.channel_id && match.channel_id !== channelId) {
          setChannelId(match.channel_id);
        }
        // 走行中はサンプル承認ゲートをスキップ（既に本生成に進んでいるため）。
        setSampleApproved(true);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // マウント時に一度だけ

  // YouTube 接続状態
  useEffect(() => {
    fetch('/api/youtube/status', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setYtConnected(!!d?.connected))
      .catch(() => setYtConnected(false));
  }, []);

  // テンプレート一覧取得
  useEffect(() => {
    fetch('/api/templates', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : { templates: [] }))
      .then((d) => setTemplates(d.templates || []))
      .catch(() => setTemplates([]));
  }, []);

  // チャンネル/テーマが変わったらサンプルの承認を取り消す（前提が変わるため）
  useEffect(() => {
    // 走行中ジョブへ再接続した直後はリセットしない（サンプル承認を維持）
    if (justAttachedRef.current) {
      justAttachedRef.current = false;
      return;
    }
    setSampleApproved(false);
    // 前提が変われば修正履歴も流す
    setSampleFeedback([]);
    setSampleFeedbackDraft('');
    // 走っているサンプル生成ジョブも捨てる（古い前提の結果を上書きしないように）。
    setSampleJobId(null);
    setSampling(false);
    setSampleError(null);
    // サムネプレビューも前提が変わるので消す
    setThumb(null);
    setThumbError(null);
    setThumbFeedback([]);
    setThumbFeedbackDraft('');
    setThumbJobId(null);
    setThumbBusy(null);
    pendingReuseDeleteRef.current = null;
  }, [channelId, theme]);

  // チャンネルが変わったらBGMプレビューもクリア（別BGMファイルになる可能性）
  useEffect(() => {
    setBgmPreviewUrl(null);
    setBgmPreviewMeta(null);
    setBgmPreviewError(null);
  }, [channelId]);

  useEffect(() => {
    if (!jobId) return;

    const triggerAutoPublish = async (s: GenerateStatus) => {
      if (autoPublishedRef.current) return;
      autoPublishedRef.current = true;
      try {
        const r = (s.result || {}) as Record<string, any>;
        // generate_all() の戻り値は `full` (= メイン動画パス, 文字列) と
        // `short` (= ショート動画パス, 文字列) を持つ。dict のときは
        // value.video_path / path も見る（古い形にも一応対応）。
        const pickPath = (v: unknown): string | null => {
          if (typeof v === 'string' && v) return v;
          if (v && typeof v === 'object') {
            const obj = v as Record<string, unknown>;
            for (const k of ['video_path', 'path', 'output', 'main_video_path', 'full_video_path']) {
              const cand = obj[k];
              if (typeof cand === 'string' && cand) return cand;
            }
          }
          return null;
        };
        // メイン動画優先（ない場合はショートで代用）。
        const videoPath =
          pickPath(r.full) ||
          pickPath(r.main) ||
          (typeof r.full_video_path === 'string' ? r.full_video_path : null) ||
          (typeof r.main_video_path === 'string' ? r.main_video_path : null) ||
          (typeof r.video_path === 'string' ? r.video_path : null) ||
          pickPath(r.short);
        const thumbnailPath =
          (typeof r.thumbnail === 'string' ? r.thumbnail : null) ||
          (typeof r.thumbnail_path === 'string' ? r.thumbnail_path : null);
        if (!videoPath) {
          // 何が来てるか分かるよう、キーをメッセージに含めて切り分けを楽にする。
          const keys = Object.keys(r).join(', ') || '（空）';
          setPublishMsg(
            `⚠️ 動画パスが取得できず、自動投稿をスキップしました（result keys: ${keys}）`,
          );
          return;
        }
        // スケジュール公開: datetime-local ("YYYY-MM-DDTHH:MM") をそのまま投げる。
        // バックエンドの _normalize_publish_at がローカルタイムゾーン未指定として
        // パースした上で UTC RFC3339 に正規化する。
        const useSchedule = publishMode === 'scheduled' && !!scheduledAt;
        const res = await fetch('/api/youtube/publish', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            video_path: videoPath,
            thumbnail_path: thumbnailPath,
            title: s.title || 'Untitled',
            privacy: 'private',
            ...(useSchedule ? { scheduled_at: scheduledAt } : {}),
          }),
        });
        if (!res.ok) {
          setPublishMsg(`⚠️ 自動投稿失敗: ${await res.text()}`);
          return;
        }
        const data: { job_id: string } = await res.json();
        setPublishMsg(
          useSchedule
            ? `📤 スケジュール公開を予約しました (公開予定: ${scheduledAt} / job: ${data.job_id})`
            : `📤 自動投稿を開始しました (job: ${data.job_id})`
        );
      } catch (err) {
        setPublishMsg(
          err instanceof Error ? `⚠️ ${err.message}` : '⚠️ 自動投稿に失敗しました'
        );
      }
    };

    const triggerVariantsGeneration = async () => {
      if (abAutoTriggeredRef.current || !abTest) return;
      abAutoTriggeredRef.current = true;
      setVariantsLoading(true);
      try {
        const res = await fetch(
          `/api/videos/${encodeURIComponent(jobId)}/ab-generate`,
          {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ title_count: 3, thumbnail_count: 3 }),
          }
        );
        if (res.ok) {
          const d = await res.json();
          setVariants({ title: d.title || [], thumbnail: d.thumbnail || [] });
        }
      } finally {
        setVariantsLoading(false);
      }
    };

    const poll = async () => {
      const res = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/status`,
        { cache: 'no-store' }
      );
      if (!res.ok) return;
      const s: GenerateStatus = await res.json();
      setStatus(s);
      if (s.status === 'completed' || s.status === 'failed' || s.status === 'cancelled') {
        if (pollRef.current) clearInterval(pollRef.current);
        if (s.status === 'completed' && autoPublish && ytConnected) {
          await triggerAutoPublish(s);
        }
        if (s.status === 'completed' && abTest) {
          await triggerVariantsGeneration();
        }
      }
    };

    poll();
    pollRef.current = setInterval(poll, 2500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [jobId, autoPublish, ytConnected, abTest, publishMode, scheduledAt]);

  // サンプル画像ジョブのポーリング。タブ移動で fetch が TypeError を投げても
  // 黙って次のポーリングまで待つ（done/error を返してきた時だけ UI を更新）。
  useEffect(() => {
    if (!sampleJobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const prevSampleId = sample?.sample_id;

    const poll = async () => {
      if (cancelled) return;
      try {
        const res = await fetch(
          `/api/illustrations/sample/job/${encodeURIComponent(sampleJobId)}`,
          { cache: 'no-store' },
        );
        if (cancelled) return;
        if (!res.ok) {
          // 404 (job 期限切れ) や 5xx の場合はリトライしてもムダなので終了
          if (res.status === 404 || res.status >= 500) {
            const text = await res.text().catch(() => '');
            setSampleError(text || 'サンプル生成の状態を取得できませんでした');
            setSampling(false);
            setSampleJobId(null);
            return;
          }
          // それ以外はポーリングを継続
          timer = setTimeout(poll, 2000);
          return;
        }
        const data: {
          state: 'running' | 'done' | 'error';
          result?: SampleIllustrationResponse | null;
          error?: string | null;
        } = await res.json();
        if (cancelled) return;
        if (data.state === 'done' && data.result) {
          if (prevSampleId && prevSampleId !== data.result.sample_id) {
            fetch(
              `/api/illustrations/sample/${encodeURIComponent(prevSampleId)}`,
              { method: 'DELETE' },
            ).catch(() => {});
          }
          setSample(data.result);
          setSampling(false);
          setSampleJobId(null);
          return;
        }
        if (data.state === 'error') {
          setSampleError(data.error || 'サンプル生成に失敗しました');
          setSampling(false);
          setSampleJobId(null);
          return;
        }
        timer = setTimeout(poll, 2000);
      } catch (e) {
        // TypeError "Load failed" 等の一過性ネットワークエラーは捨てて
        // 次のポーリングに賭ける。バックエンドは独立して仕事を続けている。
        if (cancelled) return;
        if (isNetworkError(e)) {
          timer = setTimeout(poll, 2000);
          return;
        }
        setSampleError(networkErrorMessage(e, 'サンプル生成に失敗しました'));
        setSampling(false);
        setSampleJobId(null);
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sampleJobId]);

  // サムネジョブのポーリング。サンプル画像と同じ作り。
  useEffect(() => {
    if (!thumbJobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      if (cancelled) return;
      try {
        const res = await fetch(
          `/api/thumbnails/job/${encodeURIComponent(thumbJobId)}`,
          { cache: 'no-store' },
        );
        if (cancelled) return;
        if (!res.ok) {
          if (res.status === 404 || res.status >= 500) {
            const text = await res.text().catch(() => '');
            setThumbError(text || 'サムネ生成の状態を取得できませんでした');
            setThumbBusy(null);
            setThumbJobId(null);
            pendingReuseDeleteRef.current = null;
            return;
          }
          timer = setTimeout(poll, 2000);
          return;
        }
        const data: {
          state: 'running' | 'done' | 'error';
          result?: ThumbnailGenerateResponse | null;
          error?: string | null;
        } = await res.json();
        if (cancelled) return;
        if (data.state === 'done' && data.result) {
          const toDelete = pendingReuseDeleteRef.current;
          pendingReuseDeleteRef.current = null;
          if (toDelete && toDelete !== data.result.thumbnail_id) {
            fetch(`/api/thumbnails/${encodeURIComponent(toDelete)}`, {
              method: 'DELETE',
            }).catch(() => {});
          }
          setThumb(data.result);
          setThumbBusy(null);
          setThumbJobId(null);
          return;
        }
        if (data.state === 'error') {
          setThumbError(data.error || 'サムネ生成に失敗しました');
          setThumbBusy(null);
          setThumbJobId(null);
          pendingReuseDeleteRef.current = null;
          return;
        }
        timer = setTimeout(poll, 2000);
      } catch (e) {
        if (cancelled) return;
        if (isNetworkError(e)) {
          timer = setTimeout(poll, 2000);
          return;
        }
        setThumbError(networkErrorMessage(e, 'サムネ生成に失敗しました'));
        setThumbBusy(null);
        setThumbJobId(null);
        pendingReuseDeleteRef.current = null;
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thumbJobId]);

  const onSuggest = async () => {
    if (!channelId) return;
    setError(null);
    setSuggesting(true);
    try {
      const res = await fetch('/api/themes/suggest', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ channel_id: channelId }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: { themes: { title: string; angle: string }[] } = await res.json();
      const first = data.themes?.[0];
      if (first) {
        setTheme(`${first.title} — ${first.angle}`);
      } else {
        setError('提案を取得できませんでした');
      }
    } catch (e) {
      setError('AI提案に失敗しました');
    } finally {
      setSuggesting(false);
    }
  };

  const onApplyTemplate = (id: string) => {
    setSelectedTemplateId(id);
    if (!id) return;
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    if (t.channel_id) setChannelId(t.channel_id);
    setTheme(t.theme || '');
    if ([8, 12, 15].includes(t.duration_minutes)) {
      setDuration(t.duration_minutes as Duration);
    }
    setGenerateShort(t.generate_short);
    setGenerateThumbnail(t.generate_thumbnail);
    setCopyToIcloud(t.copy_to_icloud);
    setAbTest(t.ab_test);
    setTemplateMsg(`📋 テンプレート「${t.name}」を適用しました`);
  };

  const onSaveTemplate = async () => {
    if (!templateSaveName.trim()) {
      setTemplateMsg('⚠️ テンプレート名を入力してください');
      return;
    }
    try {
      const res = await fetch('/api/templates', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          name: templateSaveName.trim(),
          channel_id: channelId,
          theme,
          duration_minutes: duration,
          generate_short: generateShort,
          generate_thumbnail: generateThumbnail,
          copy_to_icloud: copyToIcloud,
          ab_test: abTest,
          notes: '',
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const created: Template = await res.json();
      setTemplates((prev) => [created, ...prev]);
      setTemplateSaveName('');
      setTemplateMsg(`✅ 「${created.name}」を保存しました`);
    } catch (e) {
      setTemplateMsg(`⚠️ 保存失敗: ${e instanceof Error ? e.message : ''}`);
    }
  };

  const onDeleteTemplate = async (id: string, name: string) => {
    if (!confirm(`テンプレート「${name}」を削除しますか？`)) return;
    const res = await fetch(`/api/templates/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    if (res.ok) {
      setTemplates((prev) => prev.filter((t) => t.id !== id));
      if (selectedTemplateId === id) setSelectedTemplateId('');
    }
  };

  // `extraFeedback` — 「修正リクエスト」テキストエリアから今回新たに送る一行。
  //   undefined の場合は履歴に追加せず、既存履歴だけで再生成する（純粋な regenerate）。
  // `clearFeedback` — true の場合は履歴をリセットしてゼロから生成する。
  //
  // start → poll のフローを使う。`fetch` が一発で完走する従来方式だと、
  // タブを切り替えた瞬間に Safari/Vercel がコネクションを切って
  // "Load failed" 表示になっていた。/start で job_id を貰ったあとは
  // 短い GET ポーリングだけになるので、途中で接続が切れても次の
  // ポーリングが拾い直す。
  const onGenerateSample = async (
    extraFeedback?: string,
    clearFeedback?: boolean,
  ) => {
    if (!channelId || !theme.trim() || sampling) return;
    setSampleError(null);
    setSampling(true);
    setSampleApproved(false);

    const trimmedExtra = (extraFeedback ?? '').trim();
    const nextFeedback = clearFeedback
      ? []
      : trimmedExtra
        ? [...sampleFeedback, trimmedExtra]
        : sampleFeedback;
    // 履歴は start 時点で確定させる（draft クリアもここで）。
    // 結果は polling 側で setSample する。
    setSampleFeedback(nextFeedback);
    setSampleFeedbackDraft('');

    try {
      const res = await fetch('/api/illustrations/sample/start', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          channel_id: channelId,
          topic: theme.trim(),
          ...(nextFeedback.length ? { feedback: nextFeedback } : {}),
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || 'サンプル生成の開始に失敗しました');
      }
      const data: { job_id: string } = await res.json();
      setSampleJobId(data.job_id);
      // sampling は polling effect の done/error で false に戻す
    } catch (e) {
      // ここに来るのは start に失敗したケース（バックエンドが落ちている等）。
      // タブ切り替えでの一時的なネットワークエラー (TypeError "Load failed") も
      // ここで拾えるが、その場合はユーザーが再試行できるよう状態をリセットする。
      setSampleError(networkErrorMessage(e, 'サンプル生成に失敗しました'));
      setSampling(false);
    }
  };

  const onApproveSample = () => {
    if (!sample) return;
    setSampleApproved(true);
  };

  // サムネ生成も start → poll パターンで実装。サンプル画像と同じ理由
  // （タブ移動でコネクションが切れる）から、長い POST 1 本を持続させない。
  // mode='reuse' は背景を再利用してテキストだけ作り直す軽量ルート。
  // 旧サムネの削除は polling 完了側で行う（thumb.thumbnail_id を保持する都合）。
  const onGenerateThumbnail = async (
    mode: 'fresh' | 'reuse',
    extraFeedback?: string,
    clearFeedback?: boolean,
  ) => {
    if (!channelId || !theme.trim() || thumbBusy) return;
    if (mode === 'reuse' && !thumb) return;
    setThumbError(null);
    setThumbBusy(mode);

    const trimmedExtra = (extraFeedback ?? '').trim();
    const nextFeedback = clearFeedback
      ? []
      : trimmedExtra
        ? [...thumbFeedback, trimmedExtra]
        : thumbFeedback;
    setThumbFeedback(nextFeedback);
    setThumbFeedbackDraft('');

    // reuse モードのときだけ、旧サムネ(現在の thumb_id)を完了時に消す。
    // fresh モードは背景もまるごと別になるので残しても害はない（TTLで掃除される）。
    pendingReuseDeleteRef.current =
      mode === 'reuse' && thumb ? thumb.thumbnail_id : null;

    try {
      const res = await fetch('/api/thumbnails/start', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          channel_id: channelId,
          title: theme.trim(),
          reuse_background_id:
            mode === 'reuse' && thumb ? thumb.background_id : undefined,
          ...(nextFeedback.length ? { feedback: nextFeedback } : {}),
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || 'サムネ生成の開始に失敗しました');
      }
      const data: { job_id: string } = await res.json();
      setThumbJobId(data.job_id);
    } catch (e) {
      setThumbError(networkErrorMessage(e, 'サムネ生成に失敗しました'));
      setThumbBusy(null);
      pendingReuseDeleteRef.current = null;
    }
  };

  const onPreviewBgm = async () => {
    if (!channelId || bgmPreviewLoading) return;
    setBgmPreviewError(null);
    setBgmPreviewLoading(true);
    setBgmPreviewUrl(null);
    setBgmPreviewMeta(null);
    try {
      const res = await fetch('/api/bgm-preview', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          channel_id: channelId,
          bgm_volume: bgmVolumePct / 100,
          duration_seconds: 5,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || 'プレビュー生成に失敗しました');
      }
      const data: {
        url: string;
        bgm_filename: string | null;
        voicevox_used: boolean;
      } = await res.json();
      setBgmPreviewUrl(data.url);
      setBgmPreviewMeta({
        bgm_filename: data.bgm_filename,
        voicevox_used: data.voicevox_used,
      });
    } catch (e) {
      setBgmPreviewError(
        e instanceof Error ? e.message : 'プレビュー生成に失敗しました'
      );
    } finally {
      setBgmPreviewLoading(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!channelId || !theme.trim() || submitting) return;
    if (!sampleApproved) {
      setError('先にサンプル画像を生成・承認してください');
      return;
    }
    setError(null);
    setSubmitting(true);
    setVariants(null);
    abAutoTriggeredRef.current = false;
    try {
      const res = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          channel_id: channelId,
          theme: theme.trim(),
          duration_minutes: duration,
          generate_short: generateShort,
          generate_thumbnail: generateThumbnail,
          copy_to_icloud: copyToIcloud,
          bgm_volume: bgmVolumePct / 100,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || 'failed');
      }
      const data: { job_id: string } = await res.json();
      setJobId(data.job_id);
      setStatus(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '生成開始に失敗しました');
    } finally {
      setSubmitting(false);
    }
  };

  const onCancel = async () => {
    if (!jobId || cancelling) return;
    setCancelling(true);
    try {
      const res = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/cancel`,
        { method: 'POST', cache: 'no-store' }
      );
      if (res.ok) {
        const s: GenerateStatus = await res.json();
        setStatus(s);
        if (s.status === 'cancelled') {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      }
    } catch {
      /* ポーリングが続くので画面はやがて更新される */
    } finally {
      setCancelling(false);
    }
  };

  const onSelectVariant = async (variantId: string, kind: 'title' | 'thumbnail') => {
    if (!jobId) return;
    const res = await fetch(
      `/api/videos/${encodeURIComponent(jobId)}/variants/select`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ variant_id: variantId }),
      }
    );
    if (res.ok) {
      setVariants((prev) =>
        prev
          ? {
              ...prev,
              [kind]: prev[kind].map((v) => ({
                ...v,
                selected: v.id === variantId,
              })),
            }
          : prev
      );
    }
  };

  const isRunning =
    status &&
    status.status !== 'completed' &&
    status.status !== 'failed' &&
    status.status !== 'cancelled';
  const currentStep = status?.step ?? 1;
  const progress = status?.progress ?? 0;

  return (
    <form onSubmit={onSubmit} className="px-5 space-y-5">
      {/* テンプレート */}
      <section className="card space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-100">📋 テンプレート</h3>
          <button
            type="button"
            onClick={() => setShowTemplatePanel((v) => !v)}
            className="text-xs text-accent hover:underline"
          >
            {showTemplatePanel ? '閉じる' : '管理'}
          </button>
        </div>
        <select
          value={selectedTemplateId}
          onChange={(e) => onApplyTemplate(e.target.value)}
          className="input"
        >
          <option value="">テンプレート未選択</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({t.duration_minutes}分)
            </option>
          ))}
        </select>
        {showTemplatePanel && (
          <div className="space-y-2 border-t border-border pt-3">
            <div className="flex gap-2">
              <input
                className="input flex-1"
                value={templateSaveName}
                onChange={(e) => setTemplateSaveName(e.target.value)}
                placeholder="新規テンプレート名"
              />
              <button
                type="button"
                onClick={onSaveTemplate}
                className="btn-secondary text-xs px-3 py-2 shrink-0"
              >
                💾 現在の設定を保存
              </button>
            </div>
            {templates.length > 0 && (
              <ul className="space-y-1 text-xs">
                {templates.map((t) => (
                  <li
                    key={t.id}
                    className="flex items-center justify-between bg-bg-elev/60 rounded px-2 py-1"
                  >
                    <span className="truncate text-slate-300">{t.name}</span>
                    <button
                      type="button"
                      onClick={() => onDeleteTemplate(t.id, t.name)}
                      className="text-red-400 hover:underline text-[10px]"
                    >
                      削除
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {templateMsg && (
          <p className="text-xs text-slate-400">{templateMsg}</p>
        )}
      </section>

      <div>
        <label htmlFor="channel" className="label">チャンネル</label>
        <select
          id="channel"
          value={channelId}
          onChange={(e) => setChannelId(e.target.value)}
          className="input"
          required
        >
          {channels.length === 0 && <option value="">チャンネルなし</option>}
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="theme" className="label">テーマ</label>
        <div className="flex gap-2">
          <input
            id="theme"
            type="text"
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            placeholder="例: なぜ空は青いのか？"
            className="input flex-1"
            required
          />
          <button
            type="button"
            onClick={onSuggest}
            disabled={suggesting || !channelId}
            className="btn shrink-0 bg-purple-600 hover:bg-purple-700 text-white px-3"
          >
            {suggesting ? '…' : '✨ AI提案'}
          </button>
        </div>
      </div>

      <div>
        <span className="label">尺の目安</span>
        <div role="radiogroup" className="grid grid-cols-3 gap-2">
          {DURATIONS.map((d) => (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={duration === d}
              onClick={() => setDuration(d)}
              className={`btn py-3 ${
                duration === d
                  ? 'bg-accent text-white'
                  : 'bg-bg-elev text-slate-300 border border-border'
              }`}
            >
              {d}分
            </button>
          ))}
        </div>
      </div>

      <fieldset className="grid grid-cols-2 gap-y-2 gap-x-4">
        <legend className="sr-only">出力オプション</legend>
        <Toggle
          checked={generateShort}
          onChange={setGenerateShort}
          label="ショート生成"
        />
        <Toggle
          checked={generateThumbnail}
          onChange={setGenerateThumbnail}
          label="サムネイル生成"
        />
        <label
          className={`flex items-center gap-2 select-none text-sm ${
            ytConnected ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
          }`}
          title={!ytConnected ? 'YouTube未連携 — 設定画面で連携' : undefined}
        >
          <input
            type="checkbox"
            checked={autoPublish && !!ytConnected}
            disabled={!ytConnected}
            onChange={(e) => setAutoPublish(e.target.checked)}
            className="w-4 h-4 accent-accent"
          />
          <span>
            自動投稿
            {!ytConnected && (
              <span className="text-[10px] text-slate-500 ml-1">未連携</span>
            )}
          </span>
        </label>
        <Toggle
          checked={copyToIcloud}
          onChange={setCopyToIcloud}
          label="iCloudコピー"
        />
        <label className="flex items-center gap-2 select-none cursor-pointer text-sm col-span-2">
          <input
            type="checkbox"
            checked={abTest}
            onChange={(e) => setAbTest(e.target.checked)}
            className="w-4 h-4 accent-accent"
          />
          <span>
            🧪 A/Bテスト
            <span className="text-[10px] text-slate-500 ml-1">
              タイトル・サムネを複数パターン生成
            </span>
          </span>
        </label>
      </fieldset>

      <section className="card space-y-3" aria-label="BGM音量">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-100">🎵 BGM音量</h3>
          <span className="text-xs tabular-nums text-slate-300">
            {bgmVolumePct}%
          </span>
        </div>
        <input
          aria-label="BGM音量"
          type="range"
          min={0}
          max={100}
          step={1}
          value={bgmVolumePct}
          onChange={(e) => setBgmVolumePct(Number(e.target.value))}
          className="w-full accent-accent"
        />
        <p className="text-xs text-slate-500 leading-relaxed">
          サンプルでナレーションとBGMを重ねて再生確認できます（5秒）。
          本生成時もこの値が反映されます。
        </p>
        <button
          type="button"
          onClick={onPreviewBgm}
          disabled={!channelId || bgmPreviewLoading}
          className="btn-secondary w-full"
        >
          {bgmPreviewLoading ? 'プレビュー生成中…' : '▶️ プレビューを再生'}
        </button>
        {bgmPreviewUrl && (
          <div className="space-y-2">
            <audio
              key={bgmPreviewUrl}
              src={bgmPreviewUrl}
              controls
              autoPlay
              className="w-full"
            />
            {bgmPreviewMeta && (
              <p className="text-[10px] text-slate-500">
                BGM: {bgmPreviewMeta.bgm_filename || '（なし — ナレーションのみ）'}
                {!bgmPreviewMeta.voicevox_used && ' · ⚠️ Mock TTS'}
              </p>
            )}
          </div>
        )}
        {bgmPreviewError && (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
            ⚠️ {bgmPreviewError}
          </p>
        )}
      </section>

      {autoPublish && ytConnected && (
        <fieldset className="card space-y-3">
          <legend className="text-sm font-bold text-slate-100 px-1">
            📅 公開タイミング
          </legend>
          <div role="radiogroup" className="grid grid-cols-2 gap-2">
            {(
              [
                { v: 'immediate', label: '即時公開' },
                { v: 'scheduled', label: 'スケジュール公開' },
              ] as const
            ).map((opt) => (
              <button
                key={opt.v}
                type="button"
                role="radio"
                aria-checked={publishMode === opt.v}
                onClick={() => setPublishMode(opt.v)}
                className={`py-2 rounded-lg text-sm font-semibold ${
                  publishMode === opt.v
                    ? 'bg-accent text-white'
                    : 'bg-bg-elev text-slate-400 border border-border'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {publishMode === 'scheduled' && (
            <div>
              <label htmlFor="scheduled-at" className="label">
                公開日時
              </label>
              <input
                id="scheduled-at"
                type="datetime-local"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
                className="input"
              />
              <p className="text-[10px] text-slate-500 mt-1 leading-relaxed">
                指定した日時に YouTube 上で自動公開されます (YouTube ネイティブの予約公開機能)。
                未来の日時を指定してください。
              </p>
            </div>
          )}
        </fieldset>
      )}

      <p className="text-center text-xs text-slate-500">
        💡 推定コスト: ¥850〜1,200（GPT-4o + DALL-E 3 × 38枚）
        {abTest && <span className="block mt-1">🧪 A/Bテスト: +¥120〜200</span>}
      </p>

      {error && (
        <p
          role="alert"
          className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
        >
          {error}
        </p>
      )}

      <section className="card space-y-3" aria-label="サンプル画像確認">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-100">
            🖼️ サンプル画像で確認
          </h3>
          {sampleApproved && (
            <span className="badge bg-emerald-700/60 text-white text-[10px]">
              ✓ 承認済み
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 leading-relaxed">
          先にサンプルを1枚だけ生成して、スタイルが意図通りか確認します。
          OKを押すまで本生成（〜24枚）は走りません。
        </p>

        {!sample && !sampling && (
          <button
            type="button"
            onClick={() => onGenerateSample()}
            disabled={!channelId || !theme.trim()}
            className="btn-secondary w-full"
          >
            ✨ サンプル画像を1枚だけ生成
          </button>
        )}

        {sampling && (
          <div className="text-xs text-slate-400 text-center py-6">
            DALL-E でサンプル生成中… (10〜20秒)
          </div>
        )}

        {sample && !sampling && (
          <div className="space-y-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={sample.url}
              alt="サンプルイラスト"
              className="w-full rounded-lg border border-border bg-bg-elev"
            />

            {/* フィードバック履歴（n回目の修正の証跡） */}
            {sampleFeedback.length > 0 && (
              <div className="rounded-lg border border-border bg-bg-elev/40 p-2 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-300">
                    📝 修正履歴 ({sampleFeedback.length}回)
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setSampleFeedback([]);
                    }}
                    className="text-[10px] text-slate-500 hover:text-slate-300 underline"
                    title="履歴をリセットして次回はゼロから生成"
                  >
                    履歴クリア
                  </button>
                </div>
                <ol className="text-[11px] text-slate-400 leading-snug list-decimal list-inside space-y-0.5">
                  {sampleFeedback.map((f, i) => (
                    <li key={i} className="break-words">
                      {f}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {!sampleApproved ? (
              <>
                {/* 修正リクエスト入力欄 */}
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-300 block">
                    修正リクエスト（任意）
                  </label>
                  <textarea
                    value={sampleFeedbackDraft}
                    onChange={(e) => setSampleFeedbackDraft(e.target.value)}
                    placeholder="例: もっと明るい色で / 真ん中のキャラを小さく / 背景を青空に"
                    rows={2}
                    className="w-full rounded-lg bg-bg-elev border border-border text-xs text-slate-200 px-2 py-2 resize-y placeholder:text-slate-600"
                    disabled={sampling}
                  />
                  <p className="text-[10px] text-slate-500 leading-snug">
                    入力して「修正して再生成」を押すと、これまでの修正指示すべてに加えて反映します。
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-2">
                  <button
                    type="button"
                    onClick={() => onGenerateSample(sampleFeedbackDraft)}
                    disabled={!sampleFeedbackDraft.trim()}
                    className="btn bg-accent hover:bg-accent/80 text-white py-3 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    ✏️ 修正して再生成
                  </button>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => onGenerateSample()}
                      className="btn bg-bg-elev text-slate-200 border border-border py-3 text-xs"
                      title={
                        sampleFeedback.length
                          ? `これまでの${sampleFeedback.length}件の修正指示を保ったまま再生成`
                          : '同じ条件でもう1枚生成'
                      }
                    >
                      🔁 再生成（履歴維持）
                    </button>
                    <button
                      type="button"
                      onClick={onApproveSample}
                      className="btn bg-emerald-600 hover:bg-emerald-700 text-white py-3 text-xs"
                    >
                      ✅ OK 進む
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setSampleApproved(false);
                  onGenerateSample();
                }}
                className="btn bg-bg-elev text-slate-200 border border-border w-full py-2 text-xs"
              >
                🔁 再生成して別のサンプルを試す
              </button>
            )}
          </div>
        )}

        {sampleError && (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
            ⚠️ {sampleError}
          </p>
        )}
      </section>

      {/* HTML+Playwright サムネイルプレビュー */}
      {generateThumbnail && (
        <section className="card space-y-3" aria-label="サムネプレビュー">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-100">
              🖼️ サムネイル プレビュー
            </h3>
            <span className="text-[10px] text-slate-500">
              GPT-4o + DALL-E 3 + HTML
            </span>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            タイトルから3行構成のサムネを生成。背景を再利用すれば
            DALL-E を再呼び出しせず文字レイアウトだけ作り直せます。
          </p>

          {!thumb && !thumbBusy && (
            <button
              type="button"
              onClick={() => onGenerateThumbnail('fresh')}
              disabled={!channelId || !theme.trim()}
              className="btn-secondary w-full"
            >
              ✨ サムネを生成（背景＋文字）
            </button>
          )}

          {thumbBusy && (
            <div className="text-xs text-slate-400 text-center py-6">
              {thumbBusy === 'fresh'
                ? 'GPT-4o + DALL-E + Playwright で生成中…(20〜40秒)'
                : '背景を再利用して文字だけ再描画中…(5〜10秒)'}
            </div>
          )}

          {thumb && !thumbBusy && (
            <div className="space-y-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={thumb.thumbnail_url}
                alt="生成サムネイル"
                className="w-full rounded-lg border border-border bg-bg-elev"
              />

              {/* フィードバック履歴 */}
              {thumbFeedback.length > 0 && (
                <div className="rounded-lg border border-border bg-bg-elev/40 p-2 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-slate-300">
                      📝 修正履歴 ({thumbFeedback.length}回)
                    </span>
                    <button
                      type="button"
                      onClick={() => setThumbFeedback([])}
                      className="text-[10px] text-slate-500 hover:text-slate-300 underline"
                      title="履歴をリセットして次回はゼロから生成"
                    >
                      履歴クリア
                    </button>
                  </div>
                  <ol className="text-[11px] text-slate-400 leading-snug list-decimal list-inside space-y-0.5">
                    {thumbFeedback.map((f, i) => (
                      <li key={i} className="break-words">
                        {f}
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {/* 修正リクエスト入力欄 */}
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-300 block">
                  修正リクエスト（任意）
                </label>
                <textarea
                  value={thumbFeedbackDraft}
                  onChange={(e) => setThumbFeedbackDraft(e.target.value)}
                  placeholder="例: 1行目をもっと短く / 赤バッジを「衝撃」に / 黄色強調を強く"
                  rows={2}
                  className="w-full rounded-lg bg-bg-elev border border-border text-xs text-slate-200 px-2 py-2 resize-y placeholder:text-slate-600"
                  disabled={!!thumbBusy}
                />
                <p className="text-[10px] text-slate-500 leading-snug">
                  入力して送ると、これまでの修正指示すべてと合わせて GPT-4o に渡し、
                  ブリーフを作り直して再描画します。
                </p>
              </div>

              <div className="grid grid-cols-1 gap-2">
                <button
                  type="button"
                  onClick={() => onGenerateThumbnail('reuse', thumbFeedbackDraft)}
                  disabled={!thumbFeedbackDraft.trim()}
                  className="btn bg-accent hover:bg-accent/80 text-white py-3 disabled:opacity-40 disabled:cursor-not-allowed"
                  title="DALL-Eをスキップして文字だけ修正"
                >
                  ✏️ 修正して文字だけ作り直す
                </button>
                <button
                  type="button"
                  onClick={() => onGenerateThumbnail('fresh', thumbFeedbackDraft)}
                  disabled={!thumbFeedbackDraft.trim()}
                  className="btn bg-purple-600 hover:bg-purple-700 text-white py-3 text-xs disabled:opacity-40 disabled:cursor-not-allowed"
                  title="背景もDALL-Eで作り直す（コスト高）"
                >
                  ✏️ 修正して背景ごと作り直す
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => onGenerateThumbnail('reuse')}
                    className="btn bg-bg-elev text-slate-200 border border-border py-3 text-xs"
                    title="DALL-Eをスキップして文字だけ再生成（履歴維持）"
                  >
                    🔁 文字だけ作り直す
                  </button>
                  <button
                    type="button"
                    onClick={() => onGenerateThumbnail('fresh')}
                    className="btn bg-bg-elev text-slate-200 border border-border py-3 text-xs"
                    title="背景もDALL-Eで作り直す（履歴維持）"
                  >
                    🎨 背景ごと作り直す
                  </button>
                </div>
              </div>

              {thumb.brief && (
                <details className="text-[11px] text-slate-400">
                  <summary className="cursor-pointer hover:text-slate-200">
                    GPT-4o デザインブリーフを見る
                  </summary>
                  <pre className="mt-2 whitespace-pre-wrap break-words bg-bg-elev/60 rounded p-2 text-[10px] leading-relaxed">
                    {JSON.stringify(thumb.brief, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          )}

          {thumbError && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              ⚠️ {thumbError}
            </p>
          )}
        </section>
      )}

      <button
        type="submit"
        disabled={
          !channelId ||
          !theme.trim() ||
          submitting ||
          !!isRunning ||
          !sampleApproved
        }
        className="btn-primary w-full"
        title={!sampleApproved ? 'サンプル承認後に有効になります' : undefined}
      >
        {submitting
          ? '開始中…'
          : isRunning
          ? '生成中…'
          : sampleApproved
          ? '🚀 本生成を開始'
          : '🔒 サンプル承認待ち'}
      </button>

      {(status || isRunning) && (
        <section aria-label="進捗" className="card mt-2">
          <div className="flex items-center justify-between mb-3 gap-2">
            <h3 className="font-semibold text-sm">進捗</h3>
            {isRunning && jobId && (
              <button
                type="button"
                onClick={onCancel}
                disabled={cancelling}
                className="text-xs px-3 py-1 rounded bg-red-500/10 border border-red-500/30 text-red-300 hover:bg-red-500/20 disabled:opacity-50"
              >
                {cancelling ? '中断中…' : '🛑 中断'}
              </button>
            )}
          </div>
          <div className="grid grid-cols-5 gap-1 mb-3">
            {STEPS.map((step) => {
              const isPast = step.id < currentStep;
              const isCurrent = step.id === currentStep;
              return (
                <div
                  key={step.id}
                  className={`text-center py-2 px-1 rounded text-[10px] font-semibold ${
                    status?.status === 'cancelled'
                      ? 'bg-bg-elev text-slate-500'
                      : isCurrent
                      ? 'bg-accent text-white'
                      : isPast
                      ? 'bg-emerald-700/60 text-white'
                      : 'bg-bg-elev text-slate-500'
                  }`}
                >
                  {step.short}
                </div>
              );
            })}
          </div>
          <div className="h-2 rounded bg-bg-elev overflow-hidden">
            <div
              className={`h-full transition-all ${
                status?.status === 'cancelled'
                  ? 'bg-slate-500'
                  : 'bg-gradient-to-r from-accent to-purple-500'
              }`}
              style={{ width: `${Math.max(2, progress)}%` }}
            />
          </div>
          <p className="text-xs text-slate-400 mt-2">
            {status?.status === 'cancelled'
              ? '🛑 中断しました'
              : status?.status === 'failed'
              ? `❌ 失敗: ${status.error || 'unknown error'}`
              : status?.status === 'completed'
              ? '✅ 完了'
              : status?.log || '初期化中…'}
          </p>
          {publishMsg && (
            <p className="text-xs text-slate-300 mt-2">{publishMsg}</p>
          )}
        </section>
      )}

      {/* A/B Test Variants */}
      {(variants || variantsLoading) && (
        <section aria-label="A/Bテスト" className="card space-y-4">
          <h3 className="font-semibold text-sm">🧪 A/Bテストパターン</h3>
          {variantsLoading && (
            <p className="text-xs text-slate-400">パターンを生成中…</p>
          )}
          {variants && (
            <>
              <VariantsBlock
                title="タイトル"
                items={variants.title}
                onSelect={(id) => onSelectVariant(id, 'title')}
              />
              <VariantsBlock
                title="サムネイル"
                items={variants.thumbnail}
                onSelect={(id) => onSelectVariant(id, 'thumbnail')}
              />
            </>
          )}
        </section>
      )}
    </form>
  );
}

function VariantsBlock({
  title,
  items,
  onSelect,
}: {
  title: string;
  items: Variant[];
  onSelect: (id: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs text-slate-400 mb-2">{title}</h4>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {items.map((v, i) => (
          <button
            key={v.id}
            type="button"
            onClick={() => onSelect(v.id)}
            className={`text-left p-3 rounded-lg border transition ${
              v.selected
                ? 'border-accent bg-accent/10'
                : 'border-border bg-bg-elev hover:bg-slate-700'
            }`}
          >
            <div className="text-[10px] text-slate-500 mb-1">
              案 {i + 1} {v.selected && '✓ 採用'}
            </div>
            <div className="text-xs text-slate-200 line-clamp-3 break-words">
              {v.content}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (b: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 select-none cursor-pointer text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 accent-accent"
      />
      <span>{label}</span>
    </label>
  );
}
