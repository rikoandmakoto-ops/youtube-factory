'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import type {
  ABTest,
  AbReconciliationResponse,
  AnalyticsOverview,
  AnalyticsVideoMetric,
  Channel,
  CommentDemand,
  CommentDemandsResponse,
  CompetitorAnalysis,
  CompetitorCandidate,
  CompetitorOverview,
  EvaluationsListResponse,
  ImprovementEntry,
  ImprovementsListResponse,
  ModelPerformanceResponse,
  OptimalPostingStatus,
  ScenarioEvaluation,
  SeriesSuggestion,
  SeriesSuggestionsResponse,
  ThumbnailTest,
  ThumbnailTestsResponse,
  TrendDetection,
  TrendDetectionsResponse,
  TrendsResponse,
} from '@/lib/api';

// Client-side fetches reuse the existing pattern (raw `fetch` to /api/...).
// We don't import the wrapped functions from '@/lib/api' here because that
// module transitively pulls in `next/headers`, which isn't allowed in
// client components.
async function clientGet<T>(path: string): Promise<T> {
  const r = await fetch(path, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}
async function clientPost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: 'no-store',
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (j && typeof j === 'object' && 'detail' in j) msg = String(j.detail);
      else if (j && typeof j === 'object' && 'error' in j) msg = String(j.error);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

type SectionError = { section: string; message: string };

type Props = {
  channels: Channel[];
  channelId: string;
  initialOverview: AnalyticsOverview | null;
  initialVideos: AnalyticsVideoMetric[];
  initialTrends: TrendsResponse | null;
  initialABTests: ABTest[];
  initialEvaluations: EvaluationsListResponse | null;
  initialAbReconciliation: AbReconciliationResponse | null;
  initialImprovements: ImprovementsListResponse | null;
  initialModelPerformance: ModelPerformanceResponse | null;
  initialTrendDetections: TrendDetectionsResponse | null;
  initialSeriesSuggestions: SeriesSuggestionsResponse | null;
  initialErrors: SectionError[];
};

type TabId =
  | 'overview'
  | 'evaluations'
  | 'reconciliation'
  | 'improvements'
  | 'posting'
  | 'thumbnails'
  | 'trends'
  | 'series'
  | 'competitors'
  | 'voices';

type SyncState =
  | { phase: 'idle' }
  | { phase: 'running'; startedAt: number }
  | { phase: 'success'; finishedAt: number; summary: string }
  | { phase: 'error'; finishedAt: number; message: string };

function formatNumber(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—';
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString('ja-JP');
}

function formatPercent(p: number | undefined | null, digits = 1): string {
  if (p == null || Number.isNaN(p)) return '—';
  // Backend may emit either a 0–1 ratio or already a percentage. Treat
  // anything <= 1 as a ratio and convert; otherwise assume it is %.
  const pct = Math.abs(p) <= 1 ? p * 100 : p;
  return `${pct.toFixed(digits)}%`;
}

function formatMinutes(min: number | undefined | null): string {
  if (min == null || Number.isNaN(min)) return '—';
  if (min >= 60) {
    const h = Math.floor(min / 60);
    const m = Math.round(min - h * 60);
    return `${h}h ${m}m`;
  }
  return `${Math.round(min)}m`;
}

function formatSeconds(sec: number | undefined | null): string {
  if (sec == null || Number.isNaN(sec)) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec - m * 60);
  if (m === 0) return `${s}秒`;
  return `${m}分${s.toString().padStart(2, '0')}秒`;
}

function formatDateTime(s: string | null | undefined): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('ja-JP', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return s;
  }
}

export default function AnalyticsView({
  channels,
  channelId,
  initialOverview,
  initialVideos,
  initialTrends,
  initialABTests,
  initialEvaluations,
  initialAbReconciliation,
  initialImprovements,
  initialModelPerformance,
  initialTrendDetections,
  initialSeriesSuggestions,
  initialErrors,
}: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [overview, setOverview] = useState(initialOverview);
  const [videos, setVideos] = useState(initialVideos);
  const [trends, setTrends] = useState(initialTrends);
  const [abTests, setABTests] = useState(initialABTests);
  const [evaluations, setEvaluations] =
    useState<EvaluationsListResponse | null>(initialEvaluations);
  const [abReconciliation, setAbReconciliation] =
    useState<AbReconciliationResponse | null>(initialAbReconciliation);
  const [improvements, setImprovements] =
    useState<ImprovementsListResponse | null>(initialImprovements);
  const [modelPerformance, setModelPerformance] =
    useState<ModelPerformanceResponse | null>(initialModelPerformance);
  const [errors, setErrors] = useState<SectionError[]>(initialErrors);
  const [trendDetections, setTrendDetections] =
    useState<TrendDetectionsResponse | null>(initialTrendDetections);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [trendNotice, setTrendNotice] = useState<string | null>(null);

  const [seriesData, setSeriesData] =
    useState<SeriesSuggestionsResponse | null>(initialSeriesSuggestions);
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [seriesNotice, setSeriesNotice] = useState<string | null>(null);

  const [competitorData, setCompetitorData] =
    useState<CompetitorOverview | null>(null);
  const [competitorLoading, setCompetitorLoading] = useState(false);
  const [competitorError, setCompetitorError] = useState<string | null>(null);
  const [competitorNotice, setCompetitorNotice] = useState<string | null>(null);

  const [demandData, setDemandData] =
    useState<CommentDemandsResponse | null>(null);
  const [demandLoading, setDemandLoading] = useState(false);
  const [demandError, setDemandError] = useState<string | null>(null);
  const [demandNotice, setDemandNotice] = useState<string | null>(null);

  const [tab, setTab] = useState<TabId>(() => {
    const t = searchParams.get('tab') as TabId | null;
    if (
      t === 'evaluations' ||
      t === 'reconciliation' ||
      t === 'improvements' ||
      t === 'posting' ||
      t === 'thumbnails' ||
      t === 'trends' ||
      t === 'series' ||
      t === 'competitors' ||
      t === 'voices'
    )
      return t;
    return 'overview';
  });

  const [postingStatus, setPostingStatus] =
    useState<OptimalPostingStatus | null>(null);
  const [postingLoading, setPostingLoading] = useState(false);
  const [postingError, setPostingError] = useState<string | null>(null);
  const [postingNotice, setPostingNotice] = useState<string | null>(null);

  const [thumbnailTests, setThumbnailTests] =
    useState<ThumbnailTestsResponse | null>(null);
  const [thumbnailLoading, setThumbnailLoading] = useState(false);
  const [thumbnailError, setThumbnailError] = useState<string | null>(null);
  const [thumbnailNotice, setThumbnailNotice] = useState<string | null>(null);

  const loadPostingStatus = useCallback(
    async (recompute = false) => {
      setPostingLoading(true);
      setPostingError(null);
      try {
        const qs = new URLSearchParams({ days: '30' });
        if (recompute) qs.set('recompute', 'true');
        const r = await fetch(
          `/api/optimal-posting-time/${encodeURIComponent(channelId)}?${qs.toString()}`,
          { cache: 'no-store' }
        );
        if (!r.ok) throw new Error(`status ${r.status}`);
        const data = (await r.json()) as OptimalPostingStatus;
        setPostingStatus(data);
      } catch (e) {
        setPostingError(e instanceof Error ? e.message : '取得に失敗');
      } finally {
        setPostingLoading(false);
      }
    },
    [channelId]
  );

  const applyPosting = async () => {
    setPostingError(null);
    setPostingNotice(null);
    try {
      const r = await fetch(
        `/api/optimal-posting-time/${encodeURIComponent(channelId)}/apply`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ days: 30 }),
        }
      );
      if (!r.ok) throw new Error(`status ${r.status}`);
      const res = (await r.json()) as {
        applied: { days_of_week: number[]; hour: number; minute: number };
      };
      setPostingNotice(
        `✅ 推奨スロットを適用しました（${res.applied.days_of_week
          .map((d) => DOW_LABEL[d])
          .join('・')} ${res.applied.hour
          .toString()
          .padStart(2, '0')}:${res.applied.minute.toString().padStart(2, '0')}）`
      );
      await loadPostingStatus(true);
    } catch (e) {
      setPostingError(e instanceof Error ? e.message : '適用に失敗');
    }
  };

  const loadThumbnailTests = useCallback(async () => {
    setThumbnailLoading(true);
    setThumbnailError(null);
    try {
      const r = await fetch(
        `/api/thumbnail-tests/${encodeURIComponent(channelId)}?limit=100`,
        { cache: 'no-store' }
      );
      if (!r.ok) throw new Error(`status ${r.status}`);
      const data = (await r.json()) as ThumbnailTestsResponse;
      setThumbnailTests(data);
    } catch (e) {
      setThumbnailError(e instanceof Error ? e.message : '取得に失敗');
    } finally {
      setThumbnailLoading(false);
    }
  }, [channelId]);

  const postThumbnailAction = async (path: string): Promise<unknown> => {
    const r = await fetch(path, { method: 'POST' });
    if (!r.ok) throw new Error(`status ${r.status}`);
    return r.json();
  };

  const runThumbnailCheckOne = async (videoId: string) => {
    setThumbnailNotice(null);
    setThumbnailError(null);
    try {
      await postThumbnailAction(
        `/api/thumbnail-tests/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/check`
      );
      setThumbnailNotice('✅ CTR チェック完了');
      await loadThumbnailTests();
    } catch (e) {
      setThumbnailError(e instanceof Error ? e.message : 'チェック失敗');
    }
  };

  const runThumbnailSwitch = async (videoId: string) => {
    setThumbnailNotice(null);
    setThumbnailError(null);
    try {
      await postThumbnailAction(
        `/api/thumbnail-tests/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/switch`
      );
      setThumbnailNotice('✅ 次のサムネに切替えました');
      await loadThumbnailTests();
    } catch (e) {
      setThumbnailError(e instanceof Error ? e.message : '切替失敗');
    }
  };

  const runThumbnailStop = async (videoId: string) => {
    setThumbnailNotice(null);
    setThumbnailError(null);
    try {
      await postThumbnailAction(
        `/api/thumbnail-tests/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/stop`
      );
      setThumbnailNotice('✅ テストを停止しました');
      await loadThumbnailTests();
    } catch (e) {
      setThumbnailError(e instanceof Error ? e.message : '停止失敗');
    }
  };

  const runThumbnailCheckAll = async () => {
    setThumbnailNotice(null);
    setThumbnailError(null);
    try {
      const res = (await postThumbnailAction(
        `/api/thumbnail-tests/${encodeURIComponent(channelId)}/check-all`
      )) as { checked: number };
      setThumbnailNotice(`✅ ${res.checked} 件チェック完了`);
      await loadThumbnailTests();
    } catch (e) {
      setThumbnailError(e instanceof Error ? e.message : 'チェック失敗');
    }
  };

  const loadTrendDetections = useCallback(async () => {
    setTrendLoading(true);
    setTrendError(null);
    try {
      const r = await clientGet<TrendDetectionsResponse>(
        `/api/trend-scanner/${encodeURIComponent(channelId)}?limit=50`
      );
      setTrendDetections(r);
    } catch (e) {
      setTrendError(e instanceof Error ? e.message : 'トレンド取得失敗');
    } finally {
      setTrendLoading(false);
    }
  }, [channelId]);

  const handleRunTrendScan = async () => {
    setTrendNotice(null);
    setTrendError(null);
    setTrendLoading(true);
    try {
      const r = await clientPost<{
        detected?: number;
        auto_queued?: number;
        errors?: Record<string, string>;
      }>(`/api/trend-scanner/${encodeURIComponent(channelId)}/scan`, {
        auto_queue: true,
      });
      const errCount = Object.keys(r.errors || {}).length;
      setTrendNotice(
        `✅ ${r.detected ?? 0} 件検出 / ${r.auto_queued ?? 0} 件キュー自動投入${
          errCount ? ` (${errCount} ソースエラー)` : ''
        }`
      );
      await loadTrendDetections();
    } catch (e) {
      setTrendError(e instanceof Error ? e.message : 'スキャン失敗');
    } finally {
      setTrendLoading(false);
    }
  };

  const handleQueueTrend = async (detectionId: string) => {
    setTrendNotice(null);
    setTrendError(null);
    try {
      const r = await clientPost<{
        ok: boolean;
        theme_id?: string;
        title?: string;
        error?: string;
      }>(
        `/api/trend-scanner/${encodeURIComponent(channelId)}/queue/${encodeURIComponent(detectionId)}`
      );
      if (!r.ok) {
        setTrendError(r.error || 'キュー投入失敗');
        return;
      }
      setTrendNotice(`✅ 「${r.title || detectionId}」をキューに投入`);
      await loadTrendDetections();
    } catch (e) {
      setTrendError(e instanceof Error ? e.message : 'キュー投入失敗');
    }
  };

  const handleDismissTrend = async (detectionId: string) => {
    setTrendNotice(null);
    setTrendError(null);
    try {
      await clientPost(
        `/api/trend-scanner/${encodeURIComponent(channelId)}/dismiss/${encodeURIComponent(detectionId)}`
      );
      await loadTrendDetections();
    } catch (e) {
      setTrendError(e instanceof Error ? e.message : '却下失敗');
    }
  };

  const loadSeriesData = useCallback(async () => {
    setSeriesLoading(true);
    setSeriesError(null);
    try {
      const r = await clientGet<SeriesSuggestionsResponse>(
        `/api/series/${encodeURIComponent(channelId)}?limit=100`
      );
      setSeriesData(r);
    } catch (e) {
      setSeriesError(e instanceof Error ? e.message : 'シリーズ取得失敗');
    } finally {
      setSeriesLoading(false);
    }
  }, [channelId]);

  const handleRunSeriesDetect = async () => {
    setSeriesNotice(null);
    setSeriesError(null);
    setSeriesLoading(true);
    try {
      const r = await clientPost<{
        viral_count?: number;
        suggestions_added?: number;
      }>(`/api/series/${encodeURIComponent(channelId)}/detect`);
      setSeriesNotice(
        `✅ バズ動画 ${r.viral_count ?? 0} 本 / 続編候補 ${r.suggestions_added ?? 0} 件追加`
      );
      await loadSeriesData();
    } catch (e) {
      setSeriesError(e instanceof Error ? e.message : '検出失敗');
    } finally {
      setSeriesLoading(false);
    }
  };

  const handleApproveSeries = async (suggestionId: string) => {
    setSeriesNotice(null);
    setSeriesError(null);
    try {
      const r = await clientPost<{
        ok: boolean;
        theme_id?: string;
        title?: string;
        error?: string;
      }>(
        `/api/series/${encodeURIComponent(channelId)}/approve/${encodeURIComponent(suggestionId)}`
      );
      if (!r.ok) {
        setSeriesError(r.error || '承認失敗');
        return;
      }
      setSeriesNotice(`✅ 「${r.title || suggestionId}」をキューに追加`);
      await loadSeriesData();
    } catch (e) {
      setSeriesError(e instanceof Error ? e.message : '承認失敗');
    }
  };

  const handleRejectSeries = async (suggestionId: string) => {
    setSeriesNotice(null);
    setSeriesError(null);
    try {
      await clientPost(
        `/api/series/${encodeURIComponent(channelId)}/reject/${encodeURIComponent(suggestionId)}`
      );
      await loadSeriesData();
    } catch (e) {
      setSeriesError(e instanceof Error ? e.message : '却下失敗');
    }
  };

  const loadCompetitorData = useCallback(async () => {
    setCompetitorLoading(true);
    setCompetitorError(null);
    try {
      const r = await clientGet<CompetitorOverview>(
        `/api/competitors/${encodeURIComponent(channelId)}?limit=50`
      );
      setCompetitorData(r);
    } catch (e) {
      setCompetitorError(e instanceof Error ? e.message : '競合一覧の取得失敗');
    } finally {
      setCompetitorLoading(false);
    }
  }, [channelId]);

  const handleRunCompetitorScan = async () => {
    setCompetitorNotice(null);
    setCompetitorError(null);
    setCompetitorLoading(true);
    try {
      const r = await clientPost<{ count?: number; competitors?: unknown[] }>(
        `/api/competitors/${encodeURIComponent(channelId)}/scan`,
        {}
      );
      setCompetitorNotice(`✅ ${r.count ?? 0} 件の競合チャンネルを分析しました`);
      await loadCompetitorData();
    } catch (e) {
      setCompetitorError(e instanceof Error ? e.message : 'スキャン失敗');
    } finally {
      setCompetitorLoading(false);
    }
  };

  const handleAddCompetitor = async (input: string) => {
    setCompetitorNotice(null);
    setCompetitorError(null);
    try {
      const r = await clientPost<{
        ok: boolean;
        competitor_id?: string;
        note?: string;
        error?: string;
      }>(`/api/competitors/${encodeURIComponent(channelId)}/add`, {
        competitor_channel_id: input,
      });
      if (!r.ok) {
        setCompetitorError(r.error || '追加失敗');
        return false;
      }
      setCompetitorNotice(
        r.note === 'already registered'
          ? `すでに登録済みです (${r.competitor_id})`
          : `✅ 「${r.competitor_id}」を追加しました`
      );
      await loadCompetitorData();
      return true;
    } catch (e) {
      setCompetitorError(e instanceof Error ? e.message : '追加失敗');
      return false;
    }
  };

  const handleRemoveCompetitor = async (competitorId: string) => {
    setCompetitorNotice(null);
    setCompetitorError(null);
    try {
      const r = await fetch(
        `/api/competitors/${encodeURIComponent(channelId)}/remove/${encodeURIComponent(competitorId)}`,
        { method: 'DELETE' }
      );
      if (!r.ok) {
        let msg = `${r.status}`;
        try {
          const j = await r.json();
          if (j?.error) msg = String(j.error);
        } catch {
          /* ignore */
        }
        throw new Error(msg);
      }
      setCompetitorNotice(`削除しました (${competitorId})`);
      await loadCompetitorData();
    } catch (e) {
      setCompetitorError(e instanceof Error ? e.message : '削除失敗');
    }
  };

  const handleRunCompetitorDiscovery = async () => {
    setCompetitorNotice(null);
    setCompetitorError(null);
    setCompetitorLoading(true);
    try {
      const r = await clientPost<{
        ok?: boolean;
        count?: number;
        matched_keywords?: string[];
        error?: string;
        note?: string;
      }>(`/api/competitors/${encodeURIComponent(channelId)}/discover`, {});
      if (r.ok === false && r.error) {
        setCompetitorError(r.error);
      } else {
        const kw = (r.matched_keywords || []).slice(0, 5).join('、');
        setCompetitorNotice(
          `🔎 ${r.count ?? 0} 件の競合候補を検出${kw ? ` (検索キーワード: ${kw})` : ''}`
        );
      }
      await loadCompetitorData();
    } catch (e) {
      setCompetitorError(e instanceof Error ? e.message : '自動検出失敗');
    } finally {
      setCompetitorLoading(false);
    }
  };

  const handleApproveCandidate = async (competitorId: string) => {
    setCompetitorNotice(null);
    setCompetitorError(null);
    try {
      const r = await clientPost<{
        ok: boolean;
        competitor_id?: string;
        error?: string;
      }>(
        `/api/competitors/${encodeURIComponent(channelId)}/candidates/${encodeURIComponent(competitorId)}/approve`
      );
      if (!r.ok) {
        setCompetitorError(r.error || '承認失敗');
        return;
      }
      setCompetitorNotice(`✅ 「${r.competitor_id}」を競合に追加しました`);
      await loadCompetitorData();
    } catch (e) {
      setCompetitorError(e instanceof Error ? e.message : '承認失敗');
    }
  };

  const handleDismissCandidate = async (competitorId: string) => {
    setCompetitorNotice(null);
    setCompetitorError(null);
    try {
      const r = await clientPost<{ ok: boolean; error?: string }>(
        `/api/competitors/${encodeURIComponent(channelId)}/candidates/${encodeURIComponent(competitorId)}/dismiss`
      );
      if (!r.ok) {
        setCompetitorError(r.error || '却下失敗');
        return;
      }
      setCompetitorNotice(`却下しました (${competitorId})`);
      await loadCompetitorData();
    } catch (e) {
      setCompetitorError(e instanceof Error ? e.message : '却下失敗');
    }
  };

  const loadDemandData = useCallback(async () => {
    setDemandLoading(true);
    setDemandError(null);
    try {
      const r = await clientGet<CommentDemandsResponse>(
        `/api/comment-demands/${encodeURIComponent(channelId)}?limit=200`
      );
      setDemandData(r);
    } catch (e) {
      setDemandError(e instanceof Error ? e.message : '視聴者需要の取得失敗');
    } finally {
      setDemandLoading(false);
    }
  }, [channelId]);

  const handleRunDemandScan = async () => {
    setDemandNotice(null);
    setDemandError(null);
    setDemandLoading(true);
    try {
      const r = await clientPost<{
        demands_saved?: number;
        auto_queued?: number;
        request_comments_considered?: number;
      }>(`/api/comment-demands/${encodeURIComponent(channelId)}/scan`, {
        auto_queue: true,
      });
      setDemandNotice(
        `✅ コメント ${r.request_comments_considered ?? 0} 件から ${r.demands_saved ?? 0} 件の需要を抽出 / ${r.auto_queued ?? 0} 件キュー投入`
      );
      await loadDemandData();
    } catch (e) {
      setDemandError(e instanceof Error ? e.message : 'スキャン失敗');
    } finally {
      setDemandLoading(false);
    }
  };

  const handleQueueDemand = async (demandId: string) => {
    setDemandNotice(null);
    setDemandError(null);
    try {
      const r = await clientPost<{
        ok: boolean;
        theme_id?: string;
        title?: string;
        error?: string;
      }>(
        `/api/comment-demands/${encodeURIComponent(channelId)}/queue/${encodeURIComponent(demandId)}`
      );
      if (!r.ok) {
        setDemandError(r.error || 'キュー投入失敗');
        return;
      }
      setDemandNotice(`✅ 「${r.title || demandId}」をキューに追加`);
      await loadDemandData();
    } catch (e) {
      setDemandError(e instanceof Error ? e.message : 'キュー投入失敗');
    }
  };

  const handleDismissDemand = async (demandId: string) => {
    setDemandNotice(null);
    setDemandError(null);
    try {
      await clientPost(
        `/api/comment-demands/${encodeURIComponent(channelId)}/dismiss/${encodeURIComponent(demandId)}`
      );
      await loadDemandData();
    } catch (e) {
      setDemandError(e instanceof Error ? e.message : '却下失敗');
    }
  };

  useEffect(() => {
    if (tab === 'posting' && !postingStatus && !postingLoading) {
      void loadPostingStatus(false);
    }
    if (tab === 'thumbnails' && !thumbnailTests && !thumbnailLoading) {
      void loadThumbnailTests();
    }
    if (tab === 'trends' && !trendDetections && !trendLoading) {
      void loadTrendDetections();
    }
    if (tab === 'series' && !seriesData && !seriesLoading) {
      void loadSeriesData();
    }
    if (tab === 'competitors' && !competitorData && !competitorLoading) {
      void loadCompetitorData();
    }
    if (tab === 'voices' && !demandData && !demandLoading) {
      void loadDemandData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, channelId]);

  const [sync, setSync] = useState<SyncState>({ phase: 'idle' });
  const [refreshing, setRefreshing] = useState(false);

  const channel = useMemo(
    () => channels.find((c) => c.id === channelId) || null,
    [channels, channelId]
  );

  const handleChannelChange = (id: string) => {
    const sp = new URLSearchParams(searchParams.toString());
    sp.set('channel', id);
    router.push(`/analytics?${sp.toString()}`);
  };

  const switchTab = (next: TabId) => {
    setTab(next);
    const sp = new URLSearchParams(searchParams.toString());
    sp.set('tab', next);
    router.replace(`/analytics?${sp.toString()}`);
  };

  const reload = async () => {
    setRefreshing(true);
    setErrors([]);
    const collect = (section: string, message: string) =>
      setErrors((prev) => [...prev, { section, message }]);

    const [ov, vid, tr, ab, ev, rc, im, mp] = await Promise.allSettled([
      fetch(`/api/analytics/channel/${encodeURIComponent(channelId)}/overview?days=30`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/analytics/videos/${encodeURIComponent(channelId)}?limit=50`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/trends/${encodeURIComponent(channelId)}?count=5`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/ab-test?channel_id=${encodeURIComponent(channelId)}&limit=20`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/evaluations/${encodeURIComponent(channelId)}?limit=100`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/ab-reconciliation/${encodeURIComponent(channelId)}?limit=200`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/improvements/${encodeURIComponent(channelId)}?limit=100`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`/api/model-performance/${encodeURIComponent(channelId)}?recent_runs=20`, {
        cache: 'no-store',
      }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
    ]);

    if (ov.status === 'fulfilled') setOverview(ov.value as AnalyticsOverview);
    else collect('概要', '取得に失敗しました');
    if (vid.status === 'fulfilled') setVideos((vid.value as { items: AnalyticsVideoMetric[] }).items || []);
    else collect('動画一覧', '取得に失敗しました');
    if (tr.status === 'fulfilled') setTrends(tr.value as TrendsResponse);
    else collect('トレンド', '取得に失敗しました');
    if (ab.status === 'fulfilled') setABTests((ab.value as { items: ABTest[] }).items || []);
    else collect('AB テスト', '取得に失敗しました');
    if (ev.status === 'fulfilled')
      setEvaluations(ev.value as EvaluationsListResponse);
    else collect('シナリオ評価', '取得に失敗しました');
    if (rc.status === 'fulfilled')
      setAbReconciliation(rc.value as AbReconciliationResponse);
    else collect('AB 答え合わせ', '取得に失敗しました');
    if (im.status === 'fulfilled')
      setImprovements(im.value as ImprovementsListResponse);
    else collect('改善キュー', '取得に失敗しました');
    if (mp.status === 'fulfilled')
      setModelPerformance(mp.value as ModelPerformanceResponse);
    else collect('AIモデル比較', '取得に失敗しました');

    setRefreshing(false);
  };

  const triggerEvaluations = async () => {
    try {
      const res = await fetch(
        `/api/evaluations/${encodeURIComponent(channelId)}/run`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: 'シナリオ評価',
          message: e instanceof Error ? e.message : '評価実行に失敗',
        },
      ]);
    }
  };

  const triggerReconciliation = async () => {
    try {
      const res = await fetch(
        `/api/ab-reconciliation/${encodeURIComponent(channelId)}/run`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: 'AB 答え合わせ',
          message: e instanceof Error ? e.message : '実行に失敗',
        },
      ]);
    }
  };

  const triggerImprovementDetect = async () => {
    try {
      const res = await fetch(
        `/api/improvements/${encodeURIComponent(channelId)}/run`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: '改善キュー',
          message: e instanceof Error ? e.message : '実行に失敗',
        },
      ]);
    }
  };

  const regenerateForVideo = async (videoId: string) => {
    try {
      const res = await fetch(
        `/api/improvements/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/regenerate`,
        { method: 'POST' }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: '改善キュー',
          message: e instanceof Error ? e.message : '再生成に失敗',
        },
      ]);
    }
  };

  const setEntryStatus = async (
    videoId: string,
    status: 'pending' | 'applied' | 'dismissed'
  ) => {
    try {
      const res = await fetch(
        `/api/improvements/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/status`,
        {
          method: 'PUT',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ status }),
        }
      );
      if (!res.ok) throw new Error(`status ${res.status}`);
      await reload();
    } catch (e) {
      setErrors((prev) => [
        ...prev,
        {
          section: '改善キュー',
          message: e instanceof Error ? e.message : 'ステータス更新に失敗',
        },
      ]);
    }
  };

  const handleSync = async () => {
    setSync({ phase: 'running', startedAt: Date.now() });
    try {
      const res = await fetch(
        `/api/analytics/sync/${encodeURIComponent(channelId)}`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({ error: `${res.status}` }));
        throw new Error(body.error || `同期失敗 (${res.status})`);
      }
      const data = await res.json();
      const videoCount =
        (data?.videos?.count as number | undefined) ??
        (Array.isArray(data?.videos?.items) ? data.videos.items.length : 0);
      const commentCount = Array.isArray(data?.comments)
        ? data.comments.length
        : 0;
      setSync({
        phase: 'success',
        finishedAt: Date.now(),
        summary: `動画 ${videoCount} 件 / コメント分析 ${commentCount} 件`,
      });
      await reload();
    } catch (e) {
      setSync({
        phase: 'error',
        finishedAt: Date.now(),
        message: e instanceof Error ? e.message : String(e),
      });
    }
  };

  // 自動的にエラーバナーを消したり再読み込みしたりはしない。
  // ユーザーが明示的にボタンを押すまで初期状態を保持する。

  // 同期中はバックエンド側で重い処理が走るので、ボタンは無効化のみ。
  // ポーリングは行わない（完了レスポンスを待つ）。
  useEffect(() => {
    if (sync.phase !== 'success') return;
    const t = setTimeout(() => setSync({ phase: 'idle' }), 8000);
    return () => clearTimeout(t);
  }, [sync]);

  return (
    <div className="px-5 space-y-4">
      {/* チャンネル選択 + 同期 */}
      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-bold">🎛️ チャンネル</h2>
          <button
            className="btn-secondary py-1.5 px-3 text-xs"
            onClick={reload}
            disabled={refreshing}
            aria-busy={refreshing}
          >
            {refreshing ? '更新中…' : '↻ 表示を更新'}
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
          <div>
            <label className="label">対象チャンネル</label>
            <select
              className="input"
              value={channelId}
              onChange={(e) => handleChannelChange(e.target.value)}
            >
              {channels.length === 0 && (
                <option value={channelId}>{channelId}</option>
              )}
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.id})
                </option>
              ))}
            </select>
            {channel && (
              <p className="text-xs text-slate-500 mt-1 truncate">
                {channel.concept || '—'}
              </p>
            )}
          </div>
          <div className="flex flex-col items-stretch gap-2">
            <button
              className="btn-primary py-2 px-4 text-sm"
              onClick={handleSync}
              disabled={sync.phase === 'running'}
              aria-busy={sync.phase === 'running'}
            >
              {sync.phase === 'running'
                ? '🔄 同期中…'
                : '🔄 Analytics を同期'}
            </button>
            <SyncStatusLine state={sync} />
          </div>
        </div>
      </section>

      {errors.length > 0 && (
        <section className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300 space-y-0.5">
          {errors.map((err, i) => (
            <p key={i}>
              ⚠️ <strong>{err.section}</strong>: {err.message}
            </p>
          ))}
          <p className="text-xs text-red-300/70 mt-1">
            初回は「Analytics を同期」を押してデータを取り込んでください。
          </p>
        </section>
      )}

      <TabBar tab={tab} onChange={switchTab} />

      {tab === 'overview' && (
        <>
          <OverviewSection overview={overview} />
          <VideosSection videos={videos} />
          <TrendsSection trends={trends} />
          <ABTestsSection items={abTests} />
        </>
      )}

      {tab === 'evaluations' && (
        <EvaluationsTab
          data={evaluations}
          modelPerformance={modelPerformance}
          onRun={triggerEvaluations}
        />
      )}

      {tab === 'reconciliation' && (
        <ReconciliationTab
          data={abReconciliation}
          onRun={triggerReconciliation}
        />
      )}

      {tab === 'improvements' && (
        <ImprovementsTab
          data={improvements}
          onRun={triggerImprovementDetect}
          onRegenerate={regenerateForVideo}
          onSetStatus={setEntryStatus}
        />
      )}

      {tab === 'posting' && (
        <PostingOptimizerTab
          status={postingStatus}
          loading={postingLoading}
          error={postingError}
          notice={postingNotice}
          onRefresh={() => loadPostingStatus(true)}
          onApply={applyPosting}
        />
      )}

      {tab === 'thumbnails' && (
        <ThumbnailTestsTab
          data={thumbnailTests}
          loading={thumbnailLoading}
          error={thumbnailError}
          notice={thumbnailNotice}
          onRefresh={loadThumbnailTests}
          onCheckOne={runThumbnailCheckOne}
          onSwitch={runThumbnailSwitch}
          onStop={runThumbnailStop}
          onCheckAll={runThumbnailCheckAll}
        />
      )}

      {tab === 'trends' && (
        <TrendScannerTab
          data={trendDetections}
          loading={trendLoading}
          error={trendError}
          notice={trendNotice}
          onRefresh={loadTrendDetections}
          onScan={handleRunTrendScan}
          onQueue={handleQueueTrend}
          onDismiss={handleDismissTrend}
        />
      )}

      {tab === 'series' && (
        <SeriesEngineTab
          data={seriesData}
          loading={seriesLoading}
          error={seriesError}
          notice={seriesNotice}
          onRefresh={loadSeriesData}
          onDetect={handleRunSeriesDetect}
          onApprove={handleApproveSeries}
          onReject={handleRejectSeries}
        />
      )}

      {tab === 'competitors' && (
        <CompetitorsTab
          data={competitorData}
          ownChannel={channel}
          loading={competitorLoading}
          error={competitorError}
          notice={competitorNotice}
          onRefresh={loadCompetitorData}
          onScan={handleRunCompetitorScan}
          onAdd={handleAddCompetitor}
          onRemove={handleRemoveCompetitor}
          onDiscover={handleRunCompetitorDiscovery}
          onApproveCandidate={handleApproveCandidate}
          onDismissCandidate={handleDismissCandidate}
        />
      )}

      {tab === 'voices' && (
        <ViewerVoicesTab
          data={demandData}
          loading={demandLoading}
          error={demandError}
          notice={demandNotice}
          onRefresh={loadDemandData}
          onScan={handleRunDemandScan}
          onQueue={handleQueueDemand}
          onDismiss={handleDismissDemand}
        />
      )}
    </div>
  );
}

const DOW_LABEL = ['日', '月', '火', '水', '木', '金', '土'];

function TabBar({
  tab,
  onChange,
}: {
  tab: TabId;
  onChange: (next: TabId) => void;
}) {
  const items: { id: TabId; label: string }[] = [
    { id: 'overview', label: '概要' },
    { id: 'evaluations', label: 'シナリオ評価' },
    { id: 'reconciliation', label: 'AB 実績' },
    { id: 'improvements', label: '改善キュー' },
    { id: 'posting', label: '最適投稿時間' },
    { id: 'thumbnails', label: 'サムネテスト' },
    { id: 'trends', label: '🔭 トレンド' },
    { id: 'series', label: '🎬 シリーズ' },
    { id: 'competitors', label: '🕵️ 競合分析' },
    { id: 'voices', label: '🗣️ 視聴者の声' },
  ];
  return (
    <div className="flex gap-1 overflow-x-auto -mx-1 px-1">
      {items.map((it) => (
        <button
          key={it.id}
          onClick={() => onChange(it.id)}
          className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-xs font-semibold border ${
            tab === it.id
              ? 'bg-accent/20 border-accent/60 text-accent'
              : 'bg-bg-elev/40 border-border/40 text-slate-300 hover:text-slate-100'
          }`}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

function SyncStatusLine({ state }: { state: SyncState }) {
  if (state.phase === 'idle') {
    return (
      <span className="text-[11px] text-slate-500 text-right">
        YouTube Analytics API から最新値を取得
      </span>
    );
  }
  if (state.phase === 'running') {
    return (
      <span className="text-[11px] text-accent text-right">
        … 最大 1 分ほどかかります
      </span>
    );
  }
  if (state.phase === 'success') {
    return (
      <span className="text-[11px] text-emerald-300 text-right">
        ✅ 同期完了 — {state.summary}
      </span>
    );
  }
  return (
    <span className="text-[11px] text-red-300 text-right">
      ❌ {state.message}
    </span>
  );
}

function OverviewSection({ overview }: { overview: AnalyticsOverview | null }) {
  const totals = overview?.totals;
  const daily = overview?.daily || [];

  // Daily metrics may carry impressions / ctr / avg_view_duration. Compute
  // weighted averages where possible; fall back to simple means otherwise.
  const impressionsSum = daily.reduce(
    (acc, d) => acc + (Number(d.impressions) || 0),
    0
  );
  const weightedCtr =
    impressionsSum > 0
      ? daily.reduce(
          (acc, d) =>
            acc + (Number(d.ctr) || 0) * (Number(d.impressions) || 0),
          0
        ) / impressionsSum
      : null;

  const viewsSum = totals?.views ?? 0;
  const watchTimeMinutes = totals?.watch_time_minutes ?? 0;
  const avgViewSeconds =
    viewsSum > 0 ? (watchTimeMinutes * 60) / viewsSum : null;

  return (
    <section className="card">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="font-bold">📊 直近 30 日の概要</h2>
        <span className="text-[10px] text-slate-500">
          {daily.length > 0
            ? `${daily[0].date} 〜 ${daily[daily.length - 1].date}`
            : '同期前'}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <KpiCard label="視聴数" value={formatNumber(viewsSum)} sub="views" />
        <KpiCard
          label="インプレッション"
          value={impressionsSum > 0 ? formatNumber(impressionsSum) : '—'}
          sub="impressions"
        />
        <KpiCard
          label="CTR"
          value={weightedCtr != null ? formatPercent(weightedCtr) : '—'}
          sub="click-through rate"
        />
        <KpiCard
          label="視聴時間"
          value={formatMinutes(watchTimeMinutes)}
          sub="watch time"
        />
        <KpiCard
          label="平均視聴時間"
          value={formatSeconds(avgViewSeconds)}
          sub="per view"
        />
        <KpiCard
          label="登録者 純増"
          value={
            totals
              ? `${totals.net_subscribers >= 0 ? '+' : ''}${formatNumber(
                  totals.net_subscribers
                )}`
              : '—'
          }
          sub={`+${formatNumber(totals?.subscribers_gained ?? 0)} / -${formatNumber(
            totals?.subscribers_lost ?? 0
          )}`}
        />
      </div>

      {daily.length > 1 && <DailyViewsChart points={daily} />}
    </section>
  );
}

function KpiCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-lg p-3 ${
        highlight
          ? 'bg-accent/15 border border-accent/40'
          : 'bg-bg-elev border border-border/40'
      }`}
    >
      <div className="text-[10px] text-slate-400 uppercase tracking-wide">
        {label}
      </div>
      <div className="text-base font-bold tabular-nums mt-1 truncate">
        {value}
      </div>
      {sub && (
        <div className="text-[10px] text-slate-500 mt-0.5 truncate">{sub}</div>
      )}
    </div>
  );
}

function DailyViewsChart({
  points,
}: {
  points: AnalyticsOverview['daily'];
}) {
  const recent = points.slice(-30);
  const max = Math.max(1, ...recent.map((p) => Number(p.views) || 0));
  return (
    <div className="mt-4">
      <h3 className="text-xs text-slate-400 mb-2">日別 視聴数</h3>
      <div className="flex items-end gap-1 h-24">
        {recent.map((p) => {
          const v = Number(p.views) || 0;
          const h = Math.max(2, (v / max) * 100);
          return (
            <div
              key={p.date}
              className="flex-1 bg-gradient-to-t from-accent to-purple-500 rounded-t min-w-[3px]"
              style={{ height: `${h}%` }}
              title={`${p.date}: ${formatNumber(v)} views`}
            />
          );
        })}
      </div>
    </div>
  );
}

function VideosSection({ videos }: { videos: AnalyticsVideoMetric[] }) {
  const sorted = useMemo(
    () =>
      [...videos].sort(
        (a, b) => (Number(b.views) || 0) - (Number(a.views) || 0)
      ),
    [videos]
  );

  return (
    <section className="card">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="font-bold">🎞️ 動画別パフォーマンス</h2>
        <span className="text-[10px] text-slate-500">
          {sorted.length} 本
        </span>
      </div>
      {sorted.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">
          まだ動画メトリクスがありません。「Analytics を同期」を実行してください。
        </p>
      ) : (
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase text-slate-500">
              <tr className="border-b border-border/40">
                <th className="text-left font-semibold py-2 pr-2">タイトル</th>
                <th className="text-right font-semibold py-2 px-2 tabular-nums">
                  視聴
                </th>
                <th className="text-right font-semibold py-2 px-2 tabular-nums">
                  CTR
                </th>
                <th className="text-right font-semibold py-2 px-2 tabular-nums">
                  平均視聴
                </th>
                <th className="text-right font-semibold py-2 pl-2 tabular-nums">
                  維持率
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((v) => (
                <tr
                  key={v.video_id}
                  className="border-b border-border/20 hover:bg-bg-elev/40"
                >
                  <td className="py-2 pr-2">
                    <div className="text-slate-100 truncate max-w-[14rem]">
                      {v.title || v.video_id}
                    </div>
                    <div className="text-[10px] text-slate-500 truncate">
                      {v.published_at
                        ? formatDateTime(v.published_at)
                        : v.video_id}
                    </div>
                  </td>
                  <td className="text-right tabular-nums py-2 px-2">
                    {formatNumber(v.views)}
                  </td>
                  <td className="text-right tabular-nums py-2 px-2">
                    {formatPercent(v.ctr)}
                  </td>
                  <td className="text-right tabular-nums py-2 px-2">
                    {formatSeconds(v.average_view_duration_seconds)}
                  </td>
                  <td className="text-right tabular-nums py-2 pl-2">
                    {formatPercent(v.average_view_percentage)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function TrendsSection({ trends }: { trends: TrendsResponse | null }) {
  const keywords = trends?.trends?.keywords ?? [];
  const related = trends?.trends?.related_keywords ?? [];
  const trendingVideos = trends?.trends?.trending_videos ?? [];
  const themes = trends?.themes ?? [];

  return (
    <section className="card">
      <h2 className="font-bold mb-3">🔥 トレンド</h2>
      {keywords.length === 0 &&
      related.length === 0 &&
      trendingVideos.length === 0 &&
      themes.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">
          トレンドデータが取得できませんでした。
        </p>
      ) : (
        <div className="space-y-4">
          {keywords.length > 0 && (
            <KeywordCloud title="急上昇キーワード" items={keywords} />
          )}
          {related.length > 0 && (
            <KeywordCloud title="チャンネル関連語" items={related} />
          )}
          {themes.length > 0 && (
            <div>
              <h3 className="text-xs text-slate-400 mb-2">提案テーマ</h3>
              <ul className="space-y-2">
                {themes.map((t, i) => (
                  <li
                    key={i}
                    className="bg-bg-elev/60 rounded-lg p-2.5 border border-border/40"
                  >
                    <p className="text-sm font-semibold text-slate-100">
                      {String(t.title ?? '(無題)')}
                    </p>
                    {t.angle ? (
                      <p className="text-xs text-slate-400 mt-0.5">
                        {String(t.angle)}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {trendingVideos.length > 0 && (
            <div>
              <h3 className="text-xs text-slate-400 mb-2">急上昇動画</h3>
              <ul className="space-y-1.5">
                {trendingVideos.slice(0, 8).map((v, i) => (
                  <li
                    key={(v.video_id || '') + i}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <a
                      href={v.url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-200 hover:text-accent truncate"
                    >
                      {v.title || v.video_id}
                    </a>
                    <span className="text-slate-500 tabular-nums shrink-0">
                      {formatNumber(v.view_count)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function KeywordCloud({
  title,
  items,
}: {
  title: string;
  items: Array<{ keyword: string; score?: number; source?: string }>;
}) {
  return (
    <div>
      <h3 className="text-xs text-slate-400 mb-2">{title}</h3>
      <div className="flex flex-wrap gap-1.5">
        {items.slice(0, 24).map((k, i) => (
          <span
            key={`${k.keyword}-${i}`}
            className="badge bg-bg-elev border border-border/40 text-slate-200"
            title={k.source ? `source: ${k.source}` : undefined}
          >
            {k.keyword}
          </span>
        ))}
      </div>
    </div>
  );
}

function ABTestsSection({ items }: { items: ABTest[] }) {
  return (
    <section className="card">
      <h2 className="font-bold mb-3">🧪 AB テスト結果</h2>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">
          このチャンネルの AB テストはまだありません。
        </p>
      ) : (
        <ul className="space-y-3">
          {items.slice(0, 10).map((t) => (
            <ABTestCard key={t.id || t.test_id} test={t} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ABTestCard({ test }: { test: ABTest }) {
  const variants = test.variants || [];
  const bestIdx = test.best_variant_index;
  return (
    <li className="bg-bg-elev/60 rounded-lg p-3 border border-border/40">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">
            {test.theme_title || '(テーマ未設定)'}
          </p>
          {test.theme_angle && (
            <p className="text-[11px] text-slate-400 truncate">
              {test.theme_angle}
            </p>
          )}
        </div>
        <span className="text-[10px] text-slate-500 shrink-0">
          {formatDateTime(test.created_at)}
        </span>
      </div>
      {variants.length > 0 && (
        <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2">
          {variants.map((v, i) => {
            const isBest = bestIdx === i;
            return (
              <div
                key={i}
                className={`rounded-lg p-2 border ${
                  isBest
                    ? 'bg-accent/10 border-accent/50'
                    : 'bg-bg-card border-border/40'
                }`}
              >
                <div className="flex items-center justify-between gap-1 mb-1">
                  <span className="text-[10px] text-slate-400">
                    Variant {String.fromCharCode(65 + i)}
                  </span>
                  <span
                    className={`text-[10px] tabular-nums ${
                      isBest ? 'text-accent font-bold' : 'text-slate-500'
                    }`}
                  >
                    {v.ctr_score != null
                      ? `CTR ${Number(v.ctr_score).toFixed(2)}`
                      : '—'}
                  </span>
                </div>
                {v.title && (
                  <p className="text-xs text-slate-100 leading-snug">
                    {v.title}
                  </p>
                )}
                {v.catchcopy && (
                  <p className="text-[11px] text-slate-300 mt-1 leading-snug">
                    {v.catchcopy}
                  </p>
                )}
                {v.thumbnail_text && (
                  <p className="text-[10px] text-slate-400 mt-1">
                    🖼️ {v.thumbnail_text}
                  </p>
                )}
                {isBest && (
                  <p className="text-[10px] text-accent mt-1 font-bold">
                    ★ ベスト
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </li>
  );
}

// ============================================================
// Phase D: Evaluations Tab
// ============================================================

const EVAL_AXES: { key: keyof ScenarioEvaluation; label: string }[] = [
  { key: 'hook_strength', label: 'フック' },
  { key: 'specificity', label: '具体性' },
  { key: 'pacing', label: 'テンポ' },
  { key: 'cta_effectiveness', label: 'CTA' },
  { key: 'wording_quality', label: '言回し' },
  { key: 'overall', label: '総合' },
];

function EvaluationsTab({
  data,
  modelPerformance,
  onRun,
}: {
  data: EvaluationsListResponse | null;
  modelPerformance: ModelPerformanceResponse | null;
  onRun: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const items = data?.items ?? [];
  const weak = data?.weak_patterns;

  const handleRun = async () => {
    setBusy(true);
    try {
      await onRun();
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <ModelComparisonSection data={modelPerformance} />

      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold">🧠 シナリオ評価</h2>
          <button
            className="btn-secondary py-1.5 px-3 text-xs"
            onClick={handleRun}
            disabled={busy}
            aria-busy={busy}
          >
            {busy ? '実行中…' : '🤖 未評価の動画を評価'}
          </button>
        </div>

        {weak && weak.count > 0 && weak.averages && (
          <div className="rounded-lg bg-bg-elev/60 border border-border/40 p-3">
            <h3 className="text-xs text-slate-400 mb-2">
              直近 {weak.count} 本の平均スコア
            </h3>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
              {EVAL_AXES.map((ax) => (
                <ScoreBar
                  key={ax.key}
                  label={ax.label}
                  value={Number(weak.averages?.[ax.key] ?? 0)}
                />
              ))}
            </div>
            {weak.weak_sections && weak.weak_sections.length > 0 && (
              <div className="mt-3 text-xs text-slate-300">
                <span className="text-slate-400">頻発する弱点セクション:</span>{' '}
                {weak.weak_sections
                  .slice(0, 4)
                  .map(
                    (w) =>
                      `${w.section} (${Math.round(
                        (w.frequency_ratio || 0) * 100
                      )}%)`
                  )
                  .join(' / ')}
              </div>
            )}
            {weak.recent_suggestions && weak.recent_suggestions.length > 0 && (
              <div className="mt-3">
                <div className="text-xs text-slate-400 mb-1">
                  直近の改善提案ピックアップ:
                </div>
                <ul className="space-y-1 text-xs text-slate-200">
                  {weak.recent_suggestions.slice(0, 3).map((s, i) => (
                    <li key={i}>• {s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {items.length === 0 ? (
        <section className="card">
          <p className="text-sm text-slate-500 text-center py-6">
            まだ評価データがありません。同期後に「未評価の動画を評価」を実行してください。
          </p>
        </section>
      ) : (
        <ul className="space-y-3">
          {items.map((ev) => (
            <EvaluationCard key={ev.video_id} ev={ev} />
          ))}
        </ul>
      )}
    </>
  );
}

function ModelComparisonSection({
  data,
}: {
  data: ModelPerformanceResponse | null;
}) {
  if (!data) {
    return null;
  }
  const { performance, strategy, recent_runs } = data;
  const gpt = performance.by_model.gpt;
  const claude = performance.by_model.claude;
  const totalCompare = performance.blind_compare_runs;
  const totalScenarios = gpt.scenario_count + claude.scenario_count;

  const winRatePct = (n: number) => `${(n * 100).toFixed(1)}%`;
  const fmtCtr = (n: number) => (n > 0 ? `${(n * 100).toFixed(2)}%` : '—');
  const fmtRet = (n: number) => (n > 0 ? `${(n * 100).toFixed(1)}%` : '—');

  const stratLabel =
    strategy.mode === 'prefer_gpt'
      ? '📊 GPT 優先（実績バイアス）'
      : strategy.mode === 'prefer_claude'
      ? '📊 Claude 優先（実績バイアス）'
      : '🥊 ブラインド評価で都度判定';

  return (
    <section className="card space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-bold">🤖 AI モデル比較 (GPT vs Claude)</h2>
        <span className="text-[11px] text-slate-400">
          コンペ回数: {totalCompare} / 候補シナリオ: {totalScenarios}
        </span>
      </div>

      <div className="text-xs text-slate-300 bg-bg-elev/60 border border-border/40 rounded-md p-2">
        次回の採用方針: <span className="font-semibold text-slate-100">{stratLabel}</span>
        <span className="text-slate-500"> — {strategy.reason}</span>
      </div>

      {totalCompare === 0 ? (
        <p className="text-sm text-slate-500 py-4 text-center">
          まだコンペデータがありません。両方の API キー（OpenAI + Anthropic）が設定されていれば、次回のシナリオ生成時にデュアル生成が走ります。
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <ModelStatCard
              label="GPT"
              accent="bg-emerald-400/15 border-emerald-400/40"
              isLeader={performance.leader === 'gpt'}
              stats={gpt}
              winRatePct={winRatePct}
              fmtCtr={fmtCtr}
              fmtRet={fmtRet}
            />
            <ModelStatCard
              label="Claude Sonnet 4"
              accent="bg-violet-400/15 border-violet-400/40"
              isLeader={performance.leader === 'claude'}
              stats={claude}
              winRatePct={winRatePct}
              fmtCtr={fmtCtr}
              fmtRet={fmtRet}
            />
          </div>

          {recent_runs && recent_runs.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">
                直近 {recent_runs.length} 回のコンペ内訳を見る
              </summary>
              <ul className="mt-2 space-y-2">
                {recent_runs.map((run) => {
                  const g = run.candidates.gpt;
                  const c = run.candidates.claude;
                  const winnerLabel =
                    g?.selected
                      ? 'GPT'
                      : c?.selected
                      ? 'Claude'
                      : '—';
                  return (
                    <li
                      key={run.run_id}
                      className="text-[11px] text-slate-300 bg-bg-elev/40 border border-border/30 rounded-md p-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-slate-500">
                          {formatDateTime(
                            new Date((run.created_at || 0) * 1000).toISOString()
                          )}
                        </span>
                        <span className="font-semibold text-slate-100">
                          採用: {winnerLabel}
                          {g?.selected_by ? ` (${g.selected_by})` : ''}
                          {c?.selected_by ? ` (${c.selected_by})` : ''}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 mt-1">
                        <div>
                          <div className="text-slate-400">
                            GPT: {g?.title || '—'}
                          </div>
                          <div className="text-slate-500">
                            blind: {g?.blind_overall?.toFixed(1) ?? '—'}{' '}
                            {g?.won_blind_eval ? '🏆' : ''}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-400">
                            Claude: {c?.title || '—'}
                          </div>
                          <div className="text-slate-500">
                            blind: {c?.blind_overall?.toFixed(1) ?? '—'}{' '}
                            {c?.won_blind_eval ? '🏆' : ''}
                          </div>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function ModelStatCard({
  label,
  accent,
  isLeader,
  stats,
  winRatePct,
  fmtCtr,
  fmtRet,
}: {
  label: string;
  accent: string;
  isLeader: boolean;
  stats: ModelPerformanceResponse['performance']['by_model']['gpt'];
  winRatePct: (n: number) => string;
  fmtCtr: (n: number) => string;
  fmtRet: (n: number) => string;
}) {
  return (
    <div
      className={`rounded-lg border p-3 ${accent} ${
        isLeader ? 'ring-1 ring-amber-300/60' : ''
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-slate-100">{label}</span>
        {isLeader && (
          <span className="text-[10px] text-amber-300 font-bold">
            👑 LEADER
          </span>
        )}
      </div>
      <dl className="grid grid-cols-2 gap-y-1 text-[11px] text-slate-300">
        <dt className="text-slate-400">ブラインド勝率</dt>
        <dd className="text-right tabular-nums">
          {winRatePct(stats.win_rate)}{' '}
          <span className="text-slate-500">
            ({stats.win_count}/{stats.compare_runs})
          </span>
        </dd>
        <dt className="text-slate-400">平均 blind 総合</dt>
        <dd className="text-right tabular-nums">
          {stats.avg_blind_overall > 0
            ? stats.avg_blind_overall.toFixed(1)
            : '—'}
        </dd>
        <dt className="text-slate-400">採用本数</dt>
        <dd className="text-right tabular-nums">{stats.selected_count}</dd>
        <dt className="text-slate-400">実 CTR (平均)</dt>
        <dd className="text-right tabular-nums">{fmtCtr(stats.avg_ctr)}</dd>
        <dt className="text-slate-400">維持率 (平均)</dt>
        <dd className="text-right tabular-nums">
          {fmtRet(stats.avg_retention)}
        </dd>
        <dt className="text-slate-400">サンプル数</dt>
        <dd className="text-right tabular-nums">
          {stats.samples_with_metrics}
        </dd>
        <dt className="text-slate-400">実績スコア</dt>
        <dd className="text-right tabular-nums font-semibold text-slate-100">
          {(stats.perf_score * 100).toFixed(2)}
        </dd>
      </dl>
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(10, Number(value) || 0));
  const pct = (v / 10) * 100;
  const color =
    v >= 8 ? 'bg-emerald-400' : v >= 6 ? 'bg-amber-300' : 'bg-rose-400';
  return (
    <div className="text-center">
      <div className="text-[10px] text-slate-400">{label}</div>
      <div className="h-1.5 mt-1 bg-bg-card rounded-full overflow-hidden">
        <div className={`${color} h-full`} style={{ width: `${pct}%` }} />
      </div>
      <div className="text-[11px] tabular-nums mt-0.5">{v.toFixed(1)}</div>
    </div>
  );
}

function EvaluationCard({ ev }: { ev: ScenarioEvaluation }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <li className="card space-y-2">
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        className="w-full text-left"
      >
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm font-semibold text-slate-100 truncate">
            {ev.video_title || ev.video_id}
          </p>
          <span className="text-[10px] text-slate-500 shrink-0">
            {formatDateTime(new Date(ev.evaluated_at * 1000).toISOString())}
          </span>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-2">
          {EVAL_AXES.map((ax) => (
            <ScoreBar key={ax.key} label={ax.label} value={Number(ev[ax.key] ?? 0)} />
          ))}
        </div>
      </button>

      {expanded && (
        <div className="space-y-3 pt-2 border-t border-border/30">
          {ev.weak_sections && ev.weak_sections.length > 0 && (
            <div>
              <h4 className="text-xs text-slate-400 mb-1">⚠️ 弱点セクション</h4>
              <ul className="space-y-1">
                {ev.weak_sections.map((w, i) => (
                  <li
                    key={i}
                    className="text-xs text-slate-200 rounded bg-rose-500/10 border border-rose-500/30 px-2 py-1.5"
                  >
                    <span className="font-bold">{w.section || '?'}</span>
                    {typeof w.drop_percent === 'number' && (
                      <span className="ml-1 text-rose-300 tabular-nums">
                        ({w.drop_percent.toFixed(1)}% 離脱)
                      </span>
                    )}
                    {w.issue && (
                      <div className="text-slate-400 mt-1">{w.issue}</div>
                    )}
                    {w.sample_text && (
                      <div className="text-slate-500 mt-1 italic">
                        “{w.sample_text}”
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ev.improvement_suggestions && ev.improvement_suggestions.length > 0 && (
            <div>
              <h4 className="text-xs text-slate-400 mb-1">💡 改善提案</h4>
              <ul className="space-y-1">
                {ev.improvement_suggestions.map((s, i) => (
                  <li
                    key={i}
                    className="text-xs text-slate-100 rounded bg-emerald-500/10 border border-emerald-500/30 px-2 py-1.5"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ev.comment_feedback && ev.comment_feedback.length > 0 && (
            <div>
              <h4 className="text-xs text-slate-400 mb-1">
                💬 コメントフィードバック
              </h4>
              <ul className="space-y-1">
                {ev.comment_feedback.slice(0, 5).map((c, i) => (
                  <li
                    key={i}
                    className="text-xs rounded bg-bg-elev/60 border border-border/40 px-2 py-1.5"
                  >
                    {c.comment && (
                      <div className="text-slate-200">“{c.comment}”</div>
                    )}
                    {(c.section || c.action) && (
                      <div className="text-slate-500 mt-1">
                        {c.section ? `[${c.section}] ` : ''}
                        {c.action || ''}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

// ============================================================
// Phase D: AB Reconciliation Tab
// ============================================================

function ReconciliationTab({
  data,
  onRun,
}: {
  data: AbReconciliationResponse | null;
  onRun: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const items = data?.items ?? [];
  const insights = data?.pattern_insights;
  const handleRun = async () => {
    setBusy(true);
    try {
      await onRun();
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold">🎯 AB テスト実績</h2>
          <button
            className="btn-secondary py-1.5 px-3 text-xs"
            onClick={handleRun}
            disabled={busy}
          >
            {busy ? '実行中…' : '🔁 7日経過分の答え合わせ'}
          </button>
        </div>

        {insights && insights.patterns && insights.patterns.length > 0 && (
          <div className="rounded-lg bg-bg-elev/60 border border-border/40 p-3">
            <h3 className="text-xs text-slate-400 mb-2">
              パターン別実績（n={insights.total_samples}）
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {insights.patterns.map((p) => (
                <div
                  key={p.pattern_type}
                  className="rounded bg-bg-card border border-border/40 p-2"
                >
                  <div className="text-xs font-semibold text-slate-100">
                    {labelForPattern(p.pattern_type)} (n={p.samples})
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">
                    実 CTR 平均:{' '}
                    <span className="text-emerald-300 tabular-nums">
                      {p.actual_ctr_percent_avg != null
                        ? `${p.actual_ctr_percent_avg.toFixed(2)}%`
                        : '—'}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400">
                    予測スコア平均:{' '}
                    <span className="text-slate-100 tabular-nums">
                      {p.predicted_score_avg != null
                        ? p.predicted_score_avg.toFixed(2)
                        : '—'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            {insights.overall_actual_ctr_avg != null && (
              <p className="text-[11px] text-slate-500 mt-2">
                全体平均実 CTR:{' '}
                {(insights.overall_actual_ctr_avg * 100).toFixed(2)}%
              </p>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h3 className="font-bold text-sm mb-2">予測 vs 実 CTR (個別)</h3>
        {items.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-6">
            紐付け済みの AB テストがまだありません。
          </p>
        ) : (
          <div className="overflow-x-auto -mx-4 px-4">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase text-slate-500">
                <tr className="border-b border-border/40">
                  <th className="text-left py-2 pr-2">test_id</th>
                  <th className="text-left py-2 pr-2">パターン</th>
                  <th className="text-right py-2 px-2">予測</th>
                  <th className="text-right py-2 px-2">実 CTR</th>
                  <th className="text-right py-2 px-2">imp</th>
                  <th className="text-right py-2 pl-2">差分</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => {
                  const ctrPct =
                    r.actual_ctr != null ? r.actual_ctr * 100 : null;
                  // simple delta: actual_ctr% vs (predicted_score gives target like 5 = 5%)
                  const delta =
                    ctrPct != null && r.predicted_score != null
                      ? ctrPct - r.predicted_score
                      : null;
                  return (
                    <tr
                      key={`${r.test_id}-${r.variant_index}`}
                      className="border-b border-border/20"
                    >
                      <td className="py-1.5 pr-2 truncate max-w-[10rem]">
                        {r.test_id.slice(-12)}
                      </td>
                      <td className="py-1.5 pr-2">
                        {labelForPattern(r.pattern_type)}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {r.predicted_score != null
                          ? r.predicted_score.toFixed(2)
                          : '—'}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {ctrPct != null ? `${ctrPct.toFixed(2)}%` : '—'}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {r.actual_impressions != null
                          ? formatNumber(r.actual_impressions)
                          : '—'}
                      </td>
                      <td className="py-1.5 pl-2 text-right tabular-nums">
                        {delta != null ? (
                          <span
                            className={
                              delta >= 0 ? 'text-emerald-300' : 'text-rose-300'
                            }
                          >
                            {delta >= 0 ? '+' : ''}
                            {delta.toFixed(2)}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function labelForPattern(p?: string | null): string {
  if (!p) return '—';
  return (
    { question: '疑問形', number: '数字入り', surprise: '意外性' } as Record<
      string,
      string
    >
  )[p] || p;
}

// ============================================================
// Phase D: Improvement Queue Tab
// ============================================================

function ImprovementsTab({
  data,
  onRun,
  onRegenerate,
  onSetStatus,
}: {
  data: ImprovementsListResponse | null;
  onRun: () => void;
  onRegenerate: (videoId: string) => Promise<void>;
  onSetStatus: (
    videoId: string,
    status: 'pending' | 'applied' | 'dismissed'
  ) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const items = data?.items ?? [];
  const avg = data?.channel_avg_ctr;
  const handleRun = async () => {
    setBusy(true);
    try {
      await onRun();
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <section className="card space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold">🛠 改善キュー</h2>
          <button
            className="btn-secondary py-1.5 px-3 text-xs"
            onClick={handleRun}
            disabled={busy}
          >
            {busy ? '検出中…' : '🔍 低 CTR 動画を再検出'}
          </button>
        </div>
        <p className="text-xs text-slate-400">
          チャンネル平均 CTR{' '}
          <span className="text-slate-100 tabular-nums">
            {avg != null ? `${(avg * 100).toFixed(2)}%` : '—'}
          </span>{' '}
          の 80% 未満を要改善として検出します。
        </p>
      </section>

      {items.length === 0 ? (
        <section className="card">
          <p className="text-sm text-slate-500 text-center py-6">
            改善キューはまだ空です。
          </p>
        </section>
      ) : (
        <ul className="space-y-3">
          {items.map((it) => (
            <ImprovementCard
              key={it.video_id}
              entry={it}
              onRegenerate={onRegenerate}
              onSetStatus={onSetStatus}
            />
          ))}
        </ul>
      )}
    </>
  );
}

function ImprovementCard({
  entry,
  onRegenerate,
  onSetStatus,
}: {
  entry: ImprovementEntry;
  onRegenerate: (videoId: string) => Promise<void>;
  onSetStatus: (
    videoId: string,
    status: 'pending' | 'applied' | 'dismissed'
  ) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const ctrPct = entry.current_ctr != null ? entry.current_ctr * 100 : null;
  const avgPct =
    entry.channel_avg_ctr != null ? entry.channel_avg_ctr * 100 : null;
  const ratio =
    ctrPct != null && avgPct != null && avgPct > 0 ? ctrPct / avgPct : null;

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <li
      className={`card space-y-3 ${
        entry.status === 'applied'
          ? 'border-emerald-500/40'
          : entry.status === 'dismissed'
          ? 'opacity-60'
          : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">
            {entry.current_title || entry.video_id}
          </p>
          <p className="text-[11px] text-slate-500 truncate">
            {entry.video_id}
          </p>
        </div>
        <span
          className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded shrink-0 ${
            entry.status === 'applied'
              ? 'bg-emerald-500/20 text-emerald-300'
              : entry.status === 'dismissed'
              ? 'bg-slate-500/20 text-slate-400'
              : 'bg-amber-500/20 text-amber-300'
          }`}
        >
          {entry.status}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded bg-bg-elev/60 border border-border/40 p-2">
          <div className="text-slate-400">現状 CTR</div>
          <div className="text-rose-300 tabular-nums">
            {ctrPct != null ? `${ctrPct.toFixed(2)}%` : '—'}
          </div>
        </div>
        <div className="rounded bg-bg-elev/60 border border-border/40 p-2">
          <div className="text-slate-400">チャンネル平均</div>
          <div className="text-slate-100 tabular-nums">
            {avgPct != null ? `${avgPct.toFixed(2)}%` : '—'}
          </div>
        </div>
        <div className="rounded bg-bg-elev/60 border border-border/40 p-2">
          <div className="text-slate-400">平均比</div>
          <div className="text-amber-300 tabular-nums">
            {ratio != null ? `${(ratio * 100).toFixed(0)}%` : '—'}
          </div>
        </div>
      </div>

      {entry.suggested_catchcopies && entry.suggested_catchcopies.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs text-slate-400">
            ✨ 新キャッチコピー提案
            {entry.predicted_improvement != null
              ? ` — 期待改善 +${entry.predicted_improvement.toFixed(0)}%`
              : ''}
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {entry.suggested_catchcopies.map((c, i) => (
              <div
                key={i}
                className="rounded bg-bg-card border border-border/40 p-2"
              >
                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                  <span>{labelForPattern(c.pattern)}</span>
                  {c.score != null && (
                    <span className="text-slate-200 tabular-nums">
                      ★ {c.score}
                    </span>
                  )}
                </div>
                {c.title && (
                  <p className="text-xs text-slate-100 leading-snug">
                    {c.title}
                  </p>
                )}
                {Array.isArray(c.thumb_copy) && c.thumb_copy.length > 0 && (
                  <p className="text-[11px] text-slate-300 mt-1 leading-snug">
                    🖼 {c.thumb_copy.join(' / ')}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          className="btn-secondary py-1 px-3 text-xs"
          onClick={() => wrap(() => onRegenerate(entry.video_id))}
          disabled={busy}
        >
          🔁 再生成
        </button>
        <button
          className="btn-primary py-1 px-3 text-xs"
          onClick={() => wrap(() => onSetStatus(entry.video_id, 'applied'))}
          disabled={busy || entry.status === 'applied'}
        >
          ✅ 適用済みにする
        </button>
        <button
          className="btn-secondary py-1 px-3 text-xs"
          onClick={() => wrap(() => onSetStatus(entry.video_id, 'dismissed'))}
          disabled={busy || entry.status === 'dismissed'}
        >
          ✖ 却下
        </button>
        {entry.status !== 'pending' && (
          <button
            className="btn-secondary py-1 px-3 text-xs"
            onClick={() => wrap(() => onSetStatus(entry.video_id, 'pending'))}
            disabled={busy}
          >
            ↺ 戻す
          </button>
        )}
      </div>
    </li>
  );
}

// =====================================================================
// 最適投稿時間 タブ
// =====================================================================

function PostingOptimizerTab({
  status,
  loading,
  error,
  notice,
  onRefresh,
  onApply,
}: {
  status: OptimalPostingStatus | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  onRefresh: () => void;
  onApply: () => void;
}) {
  return (
    <section className="card space-y-3">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-bold">📅 最適投稿時間</h2>
          <p className="text-xs text-slate-400">
            過去 {status?.recommendation.data_days ?? 30} 日の動画パフォーマンスから (曜日 × 時間帯) ベストスロットを算出
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-secondary py-1 px-3 text-xs"
            onClick={onRefresh}
            disabled={loading}
          >
            {loading ? '計算中…' : '↻ 再計算'}
          </button>
          {status && (
            <button
              className="btn-primary py-1 px-3 text-xs"
              onClick={onApply}
              disabled={loading}
            >
              ✨ 推奨時間に変更
            </button>
          )}
        </div>
      </header>

      {error && (
        <p className="text-xs text-red-300">⚠️ {error}</p>
      )}
      {notice && (
        <p className="text-xs text-emerald-300">{notice}</p>
      )}

      {loading && !status && (
        <p className="text-xs text-slate-400">計算中…</p>
      )}

      {status && (
        <>
          <PostingComparisonCard status={status} />
          <PostingHeatmap status={status} />
          {status.recommendation.alternatives.length > 0 && (
            <div className="text-xs text-slate-400">
              <div className="font-semibold text-slate-300 mb-1">代替候補:</div>
              <ul className="space-y-0.5">
                {status.recommendation.alternatives.map((s, i) => (
                  <li key={i}>
                    {DOW_LABEL[s.day_of_week]}曜 {s.hour.toString().padStart(2, '0')}:00 — 平均 {Math.round(s.avg_views).toLocaleString()} views (n={s.sample_size})
                  </li>
                ))}
              </ul>
            </div>
          )}
          {status.recommendation.note && (
            <p className="text-xs text-amber-300">{status.recommendation.note}</p>
          )}
        </>
      )}
    </section>
  );
}

function PostingComparisonCard({ status }: { status: OptimalPostingStatus }) {
  const rec = status.recommendation.recommended;
  const current = status.current_schedule;
  const currentDow = current?.days_of_week ?? [];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div className="rounded-lg bg-bg-elev/40 border border-border/30 p-3">
        <div className="text-xs text-slate-400 mb-1">現在の設定</div>
        {current ? (
          <>
            <div className="font-mono text-lg">
              {currentDow.length > 0
                ? currentDow.map((d) => DOW_LABEL[d]).join('・')
                : '—'}{' '}
              {current.hour.toString().padStart(2, '0')}:
              {current.minute.toString().padStart(2, '0')}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">
              {current.enabled ? '🟢 autopilot 有効' : '⚪ autopilot 無効'}
            </div>
          </>
        ) : (
          <div className="text-xs text-slate-500">autopilot 未設定</div>
        )}
      </div>
      <div className="rounded-lg bg-accent/10 border border-accent/40 p-3">
        <div className="text-xs text-accent mb-1">推奨スロット</div>
        <div className="font-mono text-lg text-accent">
          {DOW_LABEL[rec.day_of_week]}曜 {rec.hour.toString().padStart(2, '0')}:
          {rec.minute.toString().padStart(2, '0')}
        </div>
        <div className="text-[11px] text-slate-300 mt-1">
          平均 {Math.round(rec.avg_views).toLocaleString()} views / n={rec.sample_size}
          {rec.boost_percent > 0 && (
            <span className="ml-2 text-emerald-300">+{rec.boost_percent}% vs 平均</span>
          )}
          {rec.is_fallback && (
            <span className="ml-2 text-amber-300">(fallback)</span>
          )}
        </div>
      </div>
    </div>
  );
}

function PostingHeatmap({ status }: { status: OptimalPostingStatus }) {
  const grid = status.heatmap.grid;
  const samples = status.heatmap.samples;
  // 最大値で正規化（fallback は 1.0）
  let max = 0;
  for (const row of grid) for (const v of row) if (v > max) max = v;
  const best = status.recommendation.recommended;
  return (
    <div className="overflow-x-auto">
      <table className="text-[10px] border-separate border-spacing-0.5">
        <thead>
          <tr>
            <th className="text-slate-500 font-normal w-10"></th>
            {Array.from({ length: 24 }, (_, h) => (
              <th
                key={h}
                className="font-normal text-slate-500 w-7 text-center"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.map((row, d) => (
            <tr key={d}>
              <th className="text-slate-400 font-normal text-right pr-1">
                {DOW_LABEL[d]}
              </th>
              {row.map((v, h) => {
                const ratio = max > 0 ? v / max : 0;
                const intensity = Math.round(ratio * 100);
                const n = samples[d][h];
                const isBest =
                  best.day_of_week === d && best.hour === h;
                return (
                  <td
                    key={h}
                    title={`${DOW_LABEL[d]}曜 ${h}:00 — 平均 ${Math.round(v).toLocaleString()} views (n=${n})`}
                    className={`w-7 h-6 text-center font-mono ${
                      isBest ? 'ring-2 ring-accent' : ''
                    }`}
                    style={{
                      backgroundColor: n
                        ? `rgba(99, 102, 241, ${0.1 + ratio * 0.65})`
                        : 'rgba(100, 116, 139, 0.07)',
                    }}
                  >
                    {n > 0 ? intensity : ''}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-[10px] text-slate-500 mt-1">
        セルの色は (曜日×時間帯) の平均再生数を最大値で正規化したもの (0–100)。空白セルは実績なし。枠線つきが推奨スロット。
      </div>
    </div>
  );
}

// =====================================================================
// サムネ AB テスト タブ
// =====================================================================

function ThumbnailTestsTab({
  data,
  loading,
  error,
  notice,
  onRefresh,
  onCheckOne,
  onSwitch,
  onStop,
  onCheckAll,
}: {
  data: ThumbnailTestsResponse | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  onRefresh: () => void;
  onCheckOne: (videoId: string) => void;
  onSwitch: (videoId: string) => void;
  onStop: (videoId: string) => void;
  onCheckAll: () => void;
}) {
  const items = data?.items ?? [];
  return (
    <section className="card space-y-3">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-bold">🖼️ サムネ AB テスト</h2>
          <p className="text-xs text-slate-400">
            投稿後 48h で CTR をチェック。チャンネル平均の 80% 未満なら次の候補に自動差し替え。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-secondary py-1 px-3 text-xs"
            onClick={onRefresh}
            disabled={loading}
          >
            {loading ? '更新中…' : '↻ 更新'}
          </button>
          <button
            className="btn-primary py-1 px-3 text-xs"
            onClick={onCheckAll}
            disabled={loading}
          >
            ⚡ 今すぐ全件チェック
          </button>
        </div>
      </header>

      {data && (
        <div className="flex flex-wrap gap-3 text-xs text-slate-400">
          <span>登録テスト: {data.summary.total_tests}</span>
          <span>監視中: {data.summary.by_status['monitoring'] ?? 0}</span>
          <span>切替済み: {data.summary.switched_tests}</span>
          <span>使い切り: {data.summary.by_status['exhausted'] ?? 0}</span>
          <span>停止: {data.summary.by_status['stopped'] ?? 0}</span>
          <span>チャンネル平均CTR: {(data.summary.channel_avg_ctr * 100).toFixed(2)}%</span>
        </div>
      )}

      {error && <p className="text-xs text-red-300">⚠️ {error}</p>}
      {notice && <p className="text-xs text-emerald-300">{notice}</p>}

      {loading && items.length === 0 && (
        <p className="text-xs text-slate-400">読み込み中…</p>
      )}

      {!loading && items.length === 0 && (
        <p className="text-xs text-slate-500">
          まだサムネ AB テストはありません。autopilot で投稿された動画は自動登録されます。
        </p>
      )}

      <ul className="space-y-3">
        {items.map((t) => (
          <ThumbnailTestRow
            key={t.video_id}
            test={t}
            onCheckOne={() => onCheckOne(t.video_id)}
            onSwitch={() => onSwitch(t.video_id)}
            onStop={() => onStop(t.video_id)}
          />
        ))}
      </ul>
    </section>
  );
}

function ThumbnailTestRow({
  test,
  onCheckOne,
  onSwitch,
  onStop,
}: {
  test: ThumbnailTest;
  onCheckOne: () => void;
  onSwitch: () => void;
  onStop: () => void;
}) {
  const statusBadge =
    test.status === 'monitoring'
      ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
      : test.status === 'exhausted'
      ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
      : 'bg-slate-500/10 text-slate-300 border-slate-500/30';
  return (
    <li className="rounded-lg bg-bg-elev/40 border border-border/30 p-3 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <a
              href={`https://youtube.com/watch?v=${encodeURIComponent(test.video_id)}`}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline truncate"
            >
              {test.video_id}
            </a>
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] border ${statusBadge}`}
            >
              {test.status}
            </span>
          </div>
          <p className="text-sm text-slate-100 truncate">{test.video_title}</p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            現在 #{test.current_variant_index} / {test.variants.length} ・ 直近CTR:{' '}
            {test.last_check_ctr != null
              ? `${(test.last_check_ctr * 100).toFixed(2)}%`
              : '—'}{' '}
            ・ 平均CTR: {(test.channel_avg_ctr * 100).toFixed(2)}% ・ 切替回数:{' '}
            {test.history.length}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            className="btn-secondary py-1 px-2 text-[11px]"
            onClick={onCheckOne}
          >
            🔍 CTR チェック
          </button>
          <button
            className="btn-primary py-1 px-2 text-[11px]"
            onClick={onSwitch}
            disabled={test.current_variant_index >= test.variants.length - 1}
          >
            🔁 次に切替
          </button>
          {test.status === 'monitoring' && (
            <button
              className="btn-secondary py-1 px-2 text-[11px]"
              onClick={onStop}
            >
              ⏸ 停止
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {test.variants.map((v) => (
          <div
            key={v.index}
            className={`rounded-md border p-1.5 ${
              v.index === test.current_variant_index
                ? 'border-accent/60 bg-accent/5'
                : 'border-border/30 bg-bg-elev/50'
            }`}
          >
            <div className="aspect-video bg-bg-elev/80 rounded mb-1 overflow-hidden flex items-center justify-center text-[10px] text-slate-500">
              {v.path ? (
                /* サムネはローカルパス。サーバから直接 fetch できないので絶対パスだけ表示 */
                <span className="truncate w-full px-1" title={v.path}>
                  {v.path.split('/').slice(-1)[0] || v.path}
                </span>
              ) : (
                <span className="text-red-300">生成失敗</span>
              )}
            </div>
            <div className="text-[10px] text-slate-300 truncate" title={v.feedback}>
              #{v.index} {v.feedback}
            </div>
          </div>
        ))}
      </div>

      {test.history.length > 0 && (
        <details className="text-[11px] text-slate-400">
          <summary className="cursor-pointer hover:text-slate-200">
            履歴 ({test.history.length} 件)
          </summary>
          <ul className="space-y-0.5 mt-1 ml-3 list-disc">
            {test.history.map((h, i) => (
              <li key={i}>
                #{h.variant_index} → #{h.switched_to} ・ CTR{' '}
                {h.ctr_at_check != null
                  ? `${(h.ctr_at_check * 100).toFixed(2)}%`
                  : '—'}{' '}
                vs 平均{' '}
                {h.channel_avg_at_check != null
                  ? `${(h.channel_avg_at_check * 100).toFixed(2)}%`
                  : '—'}{' '}
                ・ {new Date(h.switched_at * 1000).toLocaleString('ja-JP')}
                {!h.youtube_update_ok && (
                  <span className="text-red-300"> ・ 失敗: {h.youtube_update_error}</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

// =====================================================================
// Trend Scanner Tab
// =====================================================================

const SOURCE_LABEL: Record<string, string> = {
  google_trends: 'Googleトレンド',
  news_api: 'ニュース',
  youtube_trending: 'YouTube急上昇',
};

function TrendScannerTab({
  data,
  loading,
  error,
  notice,
  onRefresh,
  onScan,
  onQueue,
  onDismiss,
}: {
  data: TrendDetectionsResponse | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  onRefresh: () => void;
  onScan: () => void;
  onQueue: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const items = data?.items ?? [];
  const history = data?.history ?? [];
  const threshold = data?.auto_queue_threshold ?? 0.7;

  return (
    <section className="space-y-4 mt-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-slate-100">
            🔭 トレンドキーワード先取りエンジン
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Googleトレンド・ニュース・YouTube急上昇を6時間ごとにスキャン。
            適合度{(threshold * 100).toFixed(0)}%以上は自動でテーマキューに投入。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onScan}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent/20 border border-accent/60 text-accent hover:bg-accent/30 disabled:opacity-50"
          >
            {loading ? 'スキャン中…' : '🔄 今すぐスキャン'}
          </button>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-bg-elev/40 border border-border/40 text-slate-300 hover:text-slate-100 disabled:opacity-50"
          >
            再読込
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          {notice}
        </div>
      )}

      {data && Object.keys(data.by_source || {}).length > 0 && (
        <div className="flex gap-2 flex-wrap text-[11px] text-slate-400">
          {Object.entries(data.by_source).map(([src, n]) => (
            <span
              key={src}
              className="px-2 py-0.5 rounded bg-bg-elev/50 border border-border/40"
            >
              {SOURCE_LABEL[src] ?? src}: {n}
            </span>
          ))}
        </div>
      )}

      {items.length === 0 && !loading ? (
        <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-6 text-center text-sm text-slate-400">
          まだトレンドが検出されていません。
          <br />
          「今すぐスキャン」ボタンで初回スキャンを実行できます。
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((d) => (
            <TrendDetectionCard
              key={d.id}
              detection={d}
              onQueue={onQueue}
              onDismiss={onDismiss}
            />
          ))}
        </ul>
      )}

      {history.length > 0 && (
        <details className="rounded-lg border border-border/40 bg-bg-elev/30 p-3">
          <summary className="cursor-pointer text-xs font-semibold text-slate-300">
            スキャン履歴（直近 {history.length} 回）
          </summary>
          <ul className="mt-2 space-y-1 text-[11px] text-slate-400">
            {history.map((h) => (
              <li key={h.id}>
                {new Date(h.started_at * 1000).toLocaleString('ja-JP')} ・
                検出 {h.detected} / 自動キュー {h.auto_queued}
                {h.error && (
                  <span className="text-amber-300"> ・ {h.error}</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function TrendDetectionCard({
  detection,
  onQueue,
  onDismiss,
}: {
  detection: TrendDetection;
  onQueue: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const combined = detection.combined_score ?? 0;
  const scoreColor =
    combined >= 0.7
      ? 'text-emerald-300'
      : combined >= 0.5
        ? 'text-amber-300'
        : 'text-slate-300';
  return (
    <li className="rounded-lg border border-border/40 bg-bg-elev/40 p-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-elev/60 border border-border/40 text-slate-400">
              {SOURCE_LABEL[detection.source] ?? detection.source}
            </span>
            {detection.auto_queued && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 border border-accent/60 text-accent">
                ⚡ 自動キュー投入済み
              </span>
            )}
            {detection.status === 'queued' && !detection.auto_queued && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 border border-emerald-500/60 text-emerald-300">
                キュー投入済
              </span>
            )}
            {detection.status === 'dismissed' && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-500/20 border border-slate-500/60 text-slate-400">
                却下
              </span>
            )}
            <span className="text-[10px] text-slate-500">
              {new Date(detection.detected_at * 1000).toLocaleString('ja-JP', {
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>
          <p className="mt-1 text-sm font-semibold text-slate-100">
            {detection.suggested_title || detection.keyword}
          </p>
          {detection.suggested_angle && (
            <p className="text-xs text-slate-400 mt-1">
              切り口: {detection.suggested_angle}
            </p>
          )}
          {detection.rationale && (
            <p className="text-[11px] text-slate-500 mt-1">
              {detection.rationale}
            </p>
          )}
          <p className="text-[11px] text-slate-500 mt-1">
            キーワード:{' '}
            <span className="text-slate-400">{detection.keyword}</span>
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-lg font-bold ${scoreColor}`}>
            {(combined * 100).toFixed(0)}
          </div>
          <div className="text-[10px] text-slate-500">
            適合 {(detection.relevance_score * 100).toFixed(0)} ・ 勢い{' '}
            {(detection.trend_score * 100).toFixed(0)}
          </div>
        </div>
      </div>
      {detection.status === 'detected' && (
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => onQueue(detection.id)}
            className="px-3 py-1 rounded text-xs font-semibold bg-accent/20 border border-accent/60 text-accent hover:bg-accent/30"
          >
            ＋ キューに追加
          </button>
          <button
            onClick={() => onDismiss(detection.id)}
            className="px-3 py-1 rounded text-xs font-semibold bg-bg-elev/40 border border-border/40 text-slate-400 hover:text-slate-200"
          >
            却下
          </button>
        </div>
      )}
    </li>
  );
}

// =====================================================================
// Series Engine Tab
// =====================================================================

const SERIES_TYPE_LABEL: Record<string, string> = {
  deep_dive: '深堀り',
  contrast: '対比',
  application: '応用',
};

const SERIES_TYPE_BADGE: Record<string, string> = {
  deep_dive: 'bg-blue-500/20 border-blue-500/60 text-blue-200',
  contrast: 'bg-purple-500/20 border-purple-500/60 text-purple-200',
  application: 'bg-amber-500/20 border-amber-500/60 text-amber-200',
};

function SeriesEngineTab({
  data,
  loading,
  error,
  notice,
  onRefresh,
  onDetect,
  onApprove,
  onReject,
}: {
  data: SeriesSuggestionsResponse | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  onRefresh: () => void;
  onDetect: () => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const grouped = data?.grouped ?? [];
  const summary = data?.summary;

  return (
    <section className="space-y-4 mt-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-slate-100">
            🎬 シリーズ化エンジン
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            チャンネル平均の1.5倍以上のバズ動画から続編を自動提案。Analytics 同期後に自動実行。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onDetect}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent/20 border border-accent/60 text-accent hover:bg-accent/30 disabled:opacity-50"
          >
            {loading ? '分析中…' : '🔍 今すぐ検出'}
          </button>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-bg-elev/40 border border-border/40 text-slate-300 hover:text-slate-100 disabled:opacity-50"
          >
            再読込
          </button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
            <div className="text-slate-400">平均再生数</div>
            <div className="text-slate-100 font-semibold">
              {Math.round(summary.channel_avg_views).toLocaleString('ja-JP')}
            </div>
          </div>
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
            <div className="text-slate-400">候補総数</div>
            <div className="text-slate-100 font-semibold">
              {summary.total_suggestions}
            </div>
          </div>
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
            <div className="text-slate-400">承認済</div>
            <div className="text-emerald-300 font-semibold">
              {summary.by_status?.approved ?? 0}
            </div>
          </div>
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
            <div className="text-slate-400">公開済の続編</div>
            <div className="text-emerald-300 font-semibold">
              {summary.approved_with_video}
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          {notice}
        </div>
      )}

      {grouped.length === 0 && !loading ? (
        <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-6 text-center text-sm text-slate-400">
          まだバズ動画が検出されていません。
          <br />
          チャンネル平均の1.5倍以上の動画が出ると、続編候補がここに表示されます。
        </div>
      ) : (
        <ul className="space-y-4">
          {grouped.map((g) => (
            <ViralVideoGroup
              key={g.original_video_id}
              group={g}
              onApprove={onApprove}
              onReject={onReject}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function ViralVideoGroup({
  group,
  onApprove,
  onReject,
}: {
  group: SeriesSuggestionsResponse['grouped'][number];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  return (
    <li className="rounded-xl border border-border/40 bg-bg-elev/30 p-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-wide text-amber-300">
            🔥 バズ動画
          </div>
          <p className="text-sm font-semibold text-slate-100 truncate">
            {group.original_title || group.original_video_id}
          </p>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-amber-300">
            ×{(group.viral_ratio || 0).toFixed(2)}
          </div>
          <div className="text-[10px] text-slate-500">
            {(group.original_views || 0).toLocaleString('ja-JP')} views
          </div>
        </div>
      </div>
      <ul className="mt-3 space-y-2">
        {group.suggestions.map((s) => (
          <SeriesSuggestionCard
            key={s.id}
            suggestion={s}
            onApprove={onApprove}
            onReject={onReject}
          />
        ))}
      </ul>
    </li>
  );
}

function SeriesSuggestionCard({
  suggestion,
  onApprove,
  onReject,
}: {
  suggestion: SeriesSuggestion;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const t = suggestion.series_type || 'unknown';
  return (
    <li className="rounded-lg border border-border/40 bg-bg-elev/40 p-3">
      <div className="flex items-start gap-2 flex-wrap">
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded border ${
            SERIES_TYPE_BADGE[t] ?? 'bg-bg-elev/60 border-border/40 text-slate-300'
          }`}
        >
          {SERIES_TYPE_LABEL[t] ?? t}
        </span>
        {suggestion.status === 'approved' && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 border border-emerald-500/60 text-emerald-300">
            承認済 → キュー
          </span>
        )}
        {suggestion.status === 'rejected' && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-500/20 border border-slate-500/60 text-slate-400">
            却下
          </span>
        )}
      </div>
      <p className="mt-1 text-sm font-semibold text-slate-100">
        {suggestion.suggested_title}
      </p>
      {suggestion.suggested_angle && (
        <p className="text-xs text-slate-400 mt-1">
          切り口: {suggestion.suggested_angle}
        </p>
      )}
      {suggestion.rationale && (
        <p className="text-[11px] text-slate-500 mt-1">
          {suggestion.rationale}
        </p>
      )}
      {suggestion.status === 'pending' && (
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => onApprove(suggestion.id)}
            className="px-3 py-1 rounded text-xs font-semibold bg-accent/20 border border-accent/60 text-accent hover:bg-accent/30"
          >
            ✓ 承認してキューに追加
          </button>
          <button
            onClick={() => onReject(suggestion.id)}
            className="px-3 py-1 rounded text-xs font-semibold bg-bg-elev/40 border border-border/40 text-slate-400 hover:text-slate-200"
          >
            却下
          </button>
        </div>
      )}
    </li>
  );
}

// =====================================================================
// Competitor analysis Tab (Phase F-1)
// =====================================================================

const DOW_SHORT = ['月', '火', '水', '木', '金', '土', '日'];

type CompetitorInsights = {
  title_patterns?: {
    question_form_ratio?: number;
    number_usage_ratio?: number;
    exclamation_usage_ratio?: number;
    common_keywords?: string[];
    typical_length_chars?: number;
    hook_styles?: string[];
  };
  thumbnail_patterns?: string[];
  top_videos_common_traits?: string[];
  posting_schedule_insights?: string;
  own_channel_diff?: string[];
  improvement_suggestions?: string[];
  posting_summary?: {
    videos_observed?: number;
    posting_frequency_per_week?: number | null;
    day_of_week_counts?: Record<string, number>;
    first_published_at?: string | null;
    last_published_at?: string | null;
  };
  note?: string;
};

function CompetitorsTab({
  data,
  ownChannel,
  loading,
  error,
  notice,
  onRefresh,
  onScan,
  onAdd,
  onRemove,
  onDiscover,
  onApproveCandidate,
  onDismissCandidate,
}: {
  data: CompetitorOverview | null;
  ownChannel: Channel | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  onRefresh: () => void;
  onScan: () => void;
  onAdd: (input: string) => Promise<boolean>;
  onRemove: (competitorId: string) => void;
  onDiscover: () => void;
  onApproveCandidate: (competitorId: string) => void;
  onDismissCandidate: (competitorId: string) => void;
}) {
  const [newCompetitor, setNewCompetitor] = useState('');
  const [adding, setAdding] = useState(false);
  const [showAddHelp, setShowAddHelp] = useState(false);
  const latest = data?.latest_analyses ?? [];
  const competitorIds = data?.competitor_ids ?? [];
  const candidates = data?.pending_candidates ?? [];

  const submitAdd = async (e: FormEvent) => {
    e.preventDefault();
    if (!newCompetitor.trim()) return;
    setAdding(true);
    try {
      const ok = await onAdd(newCompetitor.trim());
      if (ok) setNewCompetitor('');
    } finally {
      setAdding(false);
    }
  };

  const avgCompFreq =
    latest
      .map((a) => a.posting_frequency_per_week)
      .filter((x): x is number => typeof x === 'number')
      .reduce((a, b, _i, arr) => a + b / arr.length, 0) || 0;

  return (
    <section className="space-y-4 mt-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-slate-100">
            🕵️ 競合チャンネル分析
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            同ジャンルの伸びているチャンネルのタイトル / サムネ / 投稿頻度を週1回 (日曜深夜) に自動分析。
            Claude が共通パターンを抽出し、自チャンネルとの差分・改善ポイントを提示します。
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={onDiscover}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-violet-500/20 border border-violet-400/60 text-violet-200 hover:bg-violet-500/30 disabled:opacity-50"
            title="YouTube 検索 API + Claude で同ジャンルのチャンネルを自動検出します"
          >
            {loading ? '検出中…' : '🔎 競合を自動検出'}
          </button>
          <button
            onClick={onScan}
            disabled={loading || competitorIds.length === 0}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent/20 border border-accent/60 text-accent hover:bg-accent/30 disabled:opacity-50"
          >
            {loading ? 'スキャン中…' : '🔄 今すぐスキャン'}
          </button>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-bg-elev/40 border border-border/40 text-slate-300 hover:text-slate-100 disabled:opacity-50"
          >
            再読込
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          {notice}
        </div>
      )}

      <form
        onSubmit={submitAdd}
        className={`rounded-lg border bg-bg-elev/40 p-4 space-y-2 ${
          competitorIds.length === 0
            ? 'border-accent/50 ring-1 ring-accent/20'
            : 'border-border/40'
        }`}
      >
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <label className="text-sm font-semibold text-slate-200">
            ＋ 競合チャンネルを追加
          </label>
          <button
            type="button"
            onClick={() => setShowAddHelp((v) => !v)}
            className="text-[11px] text-slate-400 hover:text-slate-200 underline decoration-dotted"
          >
            {showAddHelp ? 'ヘルプを閉じる' : 'チャンネルIDの調べ方'}
          </button>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center">
          <input
            type="text"
            value={newCompetitor}
            onChange={(e) => setNewCompetitor(e.target.value)}
            placeholder="UCxxxxxxxxxxxxxxxxxxxxxx  または  https://youtube.com/@handle"
            className="flex-1 input text-sm"
            autoComplete="off"
          />
          <button
            type="submit"
            disabled={adding || !newCompetitor.trim()}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-accent/30 border border-accent/60 text-accent hover:bg-accent/40 disabled:opacity-50 shrink-0"
          >
            {adding ? '追加中…' : '追加する'}
          </button>
        </div>
        {showAddHelp && (
          <div className="text-[11px] text-slate-400 leading-relaxed space-y-1 pt-1 border-t border-border/30">
            <div className="font-semibold text-slate-300">入力できる形式:</div>
            <ul className="list-disc list-inside space-y-0.5">
              <li>
                <span className="text-slate-200">UC で始まるチャンネル ID</span>（24 文字、例: <code className="text-emerald-300">UCxxxxxxxxxxxxxxxxxxxxxx</code>） — そのまま動きます
              </li>
              <li>
                <span className="text-slate-200">/channel/UC... を含む URL</span>（例: <code className="text-emerald-300">https://www.youtube.com/channel/UC...</code>）
              </li>
              <li>
                <span className="text-slate-200">@ハンドル</span>（例: <code className="text-emerald-300">@somechannel</code>）または <span className="text-slate-200">@handle 付き URL</span> — 解決に YOUTUBE_API_KEY が必要
              </li>
            </ul>
            <div className="mt-2 text-slate-500">
              💡 ハンドルから ID が解決できない場合: 対象チャンネルのページを開き <code>view-source:</code> で <code>&quot;channelId&quot;:&quot;UC...&quot;</code> を検索すると確実に取得できます。
            </div>
          </div>
        )}
      </form>

      {candidates.length > 0 && (
        <CompetitorCandidatesPanel
          candidates={candidates}
          onApprove={onApproveCandidate}
          onDismiss={onDismissCandidate}
        />
      )}

      {competitorIds.length === 0 && !loading && candidates.length === 0 && (
        <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-6 text-center text-sm text-slate-400">
          まだ競合チャンネルが登録されていません。
          <br />
          上の入力欄から YouTube チャンネル ID（UC...）または @handle を追加するか、
          <br />
          <span className="text-violet-300 font-semibold">「🔎 競合を自動検出」</span> ボタンで同ジャンルのチャンネルを自動で見つけることもできます。
        </div>
      )}

      {competitorIds.length > 0 && (
        <>
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-3">
            <h3 className="text-xs font-semibold text-slate-300 mb-2">
              登録済み競合 ({competitorIds.length})
            </h3>
            <ul className="space-y-1">
              {competitorIds.map((cid) => {
                const latestEntry = latest.find((a) => a.competitor_id === cid);
                return (
                  <li
                    key={cid}
                    className="flex items-center justify-between gap-2 text-xs text-slate-300 py-1"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold truncate">
                        {latestEntry?.competitor_title || cid}
                      </div>
                      <div className="text-[10px] text-slate-500 truncate">
                        {cid}
                        {latestEntry && (
                          <>
                            ・登録者 {formatNumber(latestEntry.subscriber_count)} ・動画{' '}
                            {formatNumber(latestEntry.video_count)} ・総再生{' '}
                            {formatNumber(latestEntry.view_count)}
                          </>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => onRemove(cid)}
                      className="px-2 py-1 rounded text-[11px] bg-bg-elev/40 border border-border/40 text-slate-400 hover:text-red-300 shrink-0"
                    >
                      削除
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {latest.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
                <div className="text-slate-400">競合数</div>
                <div className="text-slate-100 font-semibold">
                  {latest.length}
                </div>
              </div>
              <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
                <div className="text-slate-400">平均 投稿/週</div>
                <div className="text-slate-100 font-semibold">
                  {avgCompFreq ? avgCompFreq.toFixed(1) : '—'}
                </div>
              </div>
              <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
                <div className="text-slate-400">最大登録者数</div>
                <div className="text-slate-100 font-semibold">
                  {formatNumber(
                    Math.max(...latest.map((a) => a.subscriber_count || 0)) || null
                  )}
                </div>
              </div>
              <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
                <div className="text-slate-400">自チャンネル</div>
                <div className="text-slate-100 font-semibold truncate">
                  {ownChannel?.name || '—'}
                </div>
              </div>
            </div>
          )}

          {latest.length === 0 ? (
            <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-6 text-center text-sm text-slate-400">
              まだ分析結果がありません。「今すぐスキャン」で初回分析を実行してください。
              <br />
              <span className="text-[11px] text-slate-500 mt-1 inline-block">
                ※ YOUTUBE_API_KEY が設定されている必要があります
              </span>
            </div>
          ) : (
            <ul className="space-y-3">
              {latest.map((a) => (
                <CompetitorCard key={a.id} analysis={a} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function CompetitorCandidatesPanel({
  candidates,
  onApprove,
  onDismiss,
}: {
  candidates: CompetitorCandidate[];
  onApprove: (competitorId: string) => void;
  onDismiss: (competitorId: string) => void;
}) {
  return (
    <div className="rounded-xl border border-violet-400/40 bg-violet-500/[0.06] p-4 space-y-3">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold text-violet-200">
            🔎 競合候補 ({candidates.length})
          </h3>
          <p className="text-[11px] text-slate-400 mt-0.5">
            自チャンネルのテーマから YouTube 検索 + Claude スコアリングで検出した候補です。
            承認すると競合リストに追加され、以降の週次スキャンの対象になります。
          </p>
        </div>
      </div>
      <ul className="space-y-2">
        {candidates.map((c) => (
          <CompetitorCandidateRow
            key={c.id}
            candidate={c}
            onApprove={() => onApprove(c.competitor_id)}
            onDismiss={() => onDismiss(c.competitor_id)}
          />
        ))}
      </ul>
    </div>
  );
}

function CompetitorCandidateRow({
  candidate,
  onApprove,
  onDismiss,
}: {
  candidate: CompetitorCandidate;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const handle = async (fn: () => void) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };
  const score = Math.max(0, Math.min(1, candidate.relevance_score || 0));
  const scorePct = Math.round(score * 100);
  const scoreColor =
    score >= 0.7 ? 'text-emerald-300' : score >= 0.4 ? 'text-amber-300' : 'text-slate-400';
  const channelUrl = `https://www.youtube.com/channel/${candidate.competitor_id}`;
  return (
    <li className="rounded-lg border border-border/30 bg-bg-elev/40 p-3 space-y-2">
      <div className="flex items-start gap-3">
        {candidate.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={candidate.thumbnail_url}
            alt=""
            width={40}
            height={40}
            loading="lazy"
            decoding="async"
            className="w-10 h-10 rounded-full shrink-0 bg-bg-elev"
          />
        ) : (
          <div className="w-10 h-10 rounded-full bg-bg-elev shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <a
            href={channelUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-semibold text-slate-100 hover:text-violet-200 truncate block"
          >
            {candidate.competitor_title || candidate.competitor_id}
          </a>
          <div className="text-[10px] text-slate-500 truncate">
            {candidate.competitor_id}
            {candidate.subscriber_count != null && (
              <> ・登録者 {formatNumber(candidate.subscriber_count)}</>
            )}
            {candidate.video_count != null && (
              <> ・動画 {formatNumber(candidate.video_count)}</>
            )}
            {candidate.posting_frequency_per_week != null && (
              <> ・{candidate.posting_frequency_per_week.toFixed(1)} 本/週</>
            )}
          </div>
        </div>
        <div className={`text-right text-xs font-semibold shrink-0 ${scoreColor}`}>
          <div>{scorePct}%</div>
          <div className="text-[10px] text-slate-500 font-normal">関連度</div>
        </div>
      </div>
      {candidate.rationale && (
        <div className="text-[11px] text-slate-300 leading-relaxed">
          💡 {candidate.rationale}
        </div>
      )}
      {candidate.matched_keywords.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {candidate.matched_keywords.map((kw) => (
            <span
              key={kw}
              className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/15 border border-violet-400/30 text-violet-200"
            >
              {kw}
            </span>
          ))}
        </div>
      )}
      {candidate.sample_titles.length > 0 && (
        <details className="text-[11px] text-slate-400">
          <summary className="cursor-pointer hover:text-slate-200">
            最近の動画タイトル ({candidate.sample_titles.length})
          </summary>
          <ul className="mt-1 list-disc list-inside space-y-0.5 text-slate-400">
            {candidate.sample_titles.slice(0, 5).map((t, i) => (
              <li key={i} className="truncate">
                {t}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => handle(onApprove)}
          disabled={busy}
          className="flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/20 border border-emerald-500/60 text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-50"
        >
          ✅ 競合に追加
        </button>
        <button
          onClick={() => handle(onDismiss)}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-bg-elev/40 border border-border/40 text-slate-400 hover:text-red-300 disabled:opacity-50"
        >
          却下
        </button>
      </div>
    </li>
  );
}

function CompetitorCard({ analysis }: { analysis: CompetitorAnalysis }) {
  const insights = (analysis.insights_json || {}) as CompetitorInsights;
  const tp = insights.title_patterns || {};
  const ps = insights.posting_summary || {};
  const dow = ps.day_of_week_counts || {};
  const maxDow = Math.max(0, ...Object.values(dow).map((v) => Number(v) || 0));
  return (
    <li className="rounded-xl border border-border/40 bg-bg-elev/30 p-3 space-y-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">
            {analysis.competitor_title || analysis.competitor_id}
          </p>
          <p className="text-[10px] text-slate-500 truncate">
            {analysis.competitor_id}
          </p>
        </div>
        <div className="text-right shrink-0 text-[11px] text-slate-400">
          <div>登録者 {formatNumber(analysis.subscriber_count)}</div>
          <div>動画 {formatNumber(analysis.video_count)}</div>
          <div>
            最終分析{' '}
            {new Date(analysis.fetched_at * 1000).toLocaleDateString('ja-JP')}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div className="rounded-lg border border-border/40 bg-bg-elev/40 p-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            投稿頻度
          </div>
          <div className="text-slate-100 font-semibold text-base">
            {analysis.posting_frequency_per_week
              ? `${analysis.posting_frequency_per_week.toFixed(1)} 本/週`
              : '—'}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            観測 {ps.videos_observed ?? 0} 本 ・ 平均再生{' '}
            {formatNumber(analysis.avg_views)}
          </div>
        </div>
        <div className="rounded-lg border border-border/40 bg-bg-elev/40 p-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            曜日分布
          </div>
          <div className="flex items-end gap-1 mt-1 h-10">
            {DOW_SHORT.map((label, idx) => {
              const n = Number(dow[String(idx)] || 0);
              const h = maxDow > 0 ? Math.max(2, (n / maxDow) * 36) : 2;
              return (
                <div
                  key={idx}
                  className="flex-1 flex flex-col items-center gap-0.5"
                  title={`${label}: ${n}本`}
                >
                  <div
                    className="w-full bg-accent/40 rounded-t"
                    style={{ height: `${h}px` }}
                  />
                  <div className="text-[9px] text-slate-500">{label}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {(tp.question_form_ratio != null ||
        tp.number_usage_ratio != null ||
        tp.exclamation_usage_ratio != null ||
        (tp.common_keywords && tp.common_keywords.length > 0)) && (
        <div className="rounded-lg border border-border/40 bg-bg-elev/40 p-2 space-y-1">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            タイトルパターン
          </div>
          <div className="grid grid-cols-3 gap-2 text-[11px] text-slate-300">
            <div>疑問形 {formatPercent(tp.question_form_ratio, 0)}</div>
            <div>数字 {formatPercent(tp.number_usage_ratio, 0)}</div>
            <div>感嘆 {formatPercent(tp.exclamation_usage_ratio, 0)}</div>
          </div>
          {tp.typical_length_chars ? (
            <div className="text-[11px] text-slate-400">
              典型的なタイトル長: {tp.typical_length_chars} 文字
            </div>
          ) : null}
          {tp.common_keywords && tp.common_keywords.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {tp.common_keywords.slice(0, 12).map((kw) => (
                <span
                  key={kw}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-bg-elev/60 border border-border/40 text-slate-300"
                >
                  {kw}
                </span>
              ))}
            </div>
          )}
          {tp.hook_styles && tp.hook_styles.length > 0 && (
            <div className="text-[11px] text-slate-400">
              フック: {tp.hook_styles.join(' / ')}
            </div>
          )}
        </div>
      )}

      {(insights.improvement_suggestions || insights.own_channel_diff) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {insights.own_channel_diff && insights.own_channel_diff.length > 0 && (
            <div className="rounded-lg border border-border/40 bg-bg-elev/40 p-2">
              <div className="text-[10px] uppercase tracking-wide text-amber-300">
                自チャンネルとの差分
              </div>
              <ul className="text-[11px] text-slate-300 mt-1 list-disc list-inside space-y-0.5">
                {insights.own_channel_diff.slice(0, 6).map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </div>
          )}
          {insights.improvement_suggestions && insights.improvement_suggestions.length > 0 && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2">
              <div className="text-[10px] uppercase tracking-wide text-emerald-300">
                改善ポイント
              </div>
              <ul className="text-[11px] text-slate-200 mt-1 list-disc list-inside space-y-0.5">
                {insights.improvement_suggestions.slice(0, 6).map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {analysis.top_videos_json && analysis.top_videos_json.length > 0 && (
        <details className="rounded-lg border border-border/40 bg-bg-elev/40 p-2">
          <summary className="cursor-pointer text-[11px] font-semibold text-slate-300">
            高パフォーマンス動画 TOP {analysis.top_videos_json.length}
          </summary>
          <ul className="mt-2 space-y-1">
            {analysis.top_videos_json.slice(0, 10).map((v) => (
              <li
                key={v.video_id}
                className="flex items-center gap-2 text-[11px] text-slate-300"
              >
                {v.thumbnail_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={v.thumbnail_url}
                    alt=""
                    width={64}
                    height={36}
                    loading="lazy"
                    decoding="async"
                    className="w-16 h-9 object-cover rounded shrink-0"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <a
                    href={`https://www.youtube.com/watch?v=${v.video_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-slate-100 truncate block"
                  >
                    {v.title}
                  </a>
                  <span className="text-[10px] text-slate-500">
                    {formatNumber(v.views)} views ・ 👍 {formatNumber(v.likes)}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}

      {insights.note && (
        <p className="text-[10px] text-slate-500 italic">{insights.note}</p>
      )}
    </li>
  );
}

// =====================================================================
// Viewer voices Tab (Phase F-2)
// =====================================================================

function ViewerVoicesTab({
  data,
  loading,
  error,
  notice,
  onRefresh,
  onScan,
  onQueue,
  onDismiss,
}: {
  data: CommentDemandsResponse | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  onRefresh: () => void;
  onScan: () => void;
  onQueue: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const [filter, setFilter] = useState<'all' | 'request' | 'question'>('all');
  const items = (data?.items ?? []).filter(
    (d) => filter === 'all' || d.demand_type === filter
  );
  const byStatus = data?.by_status ?? {};
  const byType = data?.by_type ?? {};
  const threshold = data?.auto_queue_threshold ?? 0.7;

  return (
    <section className="space-y-4 mt-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-slate-100">
            🗣️ 視聴者の声から需要発掘
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            視聴者コメントから「○○やってほしい」「なんで○○？」を Claude が抽出。
            スコア {(threshold * 100).toFixed(0)} 以上は自動でテーマキューに投入されます。
            Analytics 同期後に自動実行。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onScan}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent/20 border border-accent/60 text-accent hover:bg-accent/30 disabled:opacity-50"
          >
            {loading ? 'スキャン中…' : '🔄 今すぐスキャン'}
          </button>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-bg-elev/40 border border-border/40 text-slate-300 hover:text-slate-100 disabled:opacity-50"
          >
            再読込
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          {notice}
        </div>
      )}

      {data && (data.count > 0 || Object.keys(byType).length > 0) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
            <div className="text-slate-400">需要総数</div>
            <div className="text-slate-100 font-semibold">{data.count}</div>
          </div>
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
            <div className="text-slate-400">リクエスト系</div>
            <div className="text-slate-100 font-semibold">
              {byType.request ?? 0}
            </div>
          </div>
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
            <div className="text-slate-400">質問系</div>
            <div className="text-slate-100 font-semibold">
              {byType.question ?? 0}
            </div>
          </div>
          <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-2">
            <div className="text-slate-400">キュー投入済</div>
            <div className="text-emerald-300 font-semibold">
              {(byStatus.queued ?? 0) + (byStatus.auto_queued ?? 0)}
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-1">
        {(['all', 'request', 'question'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-lg text-xs font-semibold border ${
              filter === f
                ? 'bg-accent/20 border-accent/60 text-accent'
                : 'bg-bg-elev/40 border-border/40 text-slate-300 hover:text-slate-100'
            }`}
          >
            {f === 'all' ? 'すべて' : f === 'request' ? 'リクエスト' : '質問'}
          </button>
        ))}
      </div>

      {items.length === 0 && !loading ? (
        <div className="rounded-lg border border-border/40 bg-bg-elev/30 p-6 text-center text-sm text-slate-400">
          まだ需要が検出されていません。
          <br />
          コメント取得 + 分析が必要です。Analytics タブから同期するか、「今すぐスキャン」を実行してください。
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((d) => (
            <CommentDemandCard
              key={d.id}
              demand={d}
              onQueue={onQueue}
              onDismiss={onDismiss}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function CommentDemandCard({
  demand,
  onQueue,
  onDismiss,
}: {
  demand: CommentDemand;
  onQueue: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const score = demand.score ?? 0;
  const scoreColor =
    score >= 0.7
      ? 'text-emerald-300'
      : score >= 0.5
        ? 'text-amber-300'
        : 'text-slate-300';
  const typeLabel = demand.demand_type === 'question' ? '質問' : 'リクエスト';
  const typeBadge =
    demand.demand_type === 'question'
      ? 'bg-blue-500/20 border-blue-500/60 text-blue-200'
      : 'bg-purple-500/20 border-purple-500/60 text-purple-200';
  return (
    <li className="rounded-lg border border-border/40 bg-bg-elev/40 p-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded border ${typeBadge}`}
            >
              {typeLabel}
            </span>
            {demand.auto_queued && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 border border-accent/60 text-accent">
                ⚡ 自動キュー投入済み
              </span>
            )}
            {demand.status === 'queued' && !demand.auto_queued && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 border border-emerald-500/60 text-emerald-300">
                キュー投入済
              </span>
            )}
            {demand.status === 'dismissed' && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-500/20 border border-slate-500/60 text-slate-400">
                却下
              </span>
            )}
            <span className="text-[10px] text-slate-500">
              頻度 {demand.frequency} ・ いいね {demand.total_likes}
            </span>
          </div>
          <p className="mt-1 text-sm font-semibold text-slate-100">
            {demand.suggested_title || demand.demand_text}
          </p>
          {demand.demand_text !== demand.suggested_title && (
            <p className="text-[11px] text-slate-400 mt-0.5">
              元: {demand.demand_text}
            </p>
          )}
          {demand.suggested_angle && (
            <p className="text-xs text-slate-400 mt-1">
              切り口: {demand.suggested_angle}
            </p>
          )}
          {demand.rationale && (
            <p className="text-[11px] text-slate-500 mt-1">{demand.rationale}</p>
          )}
          {demand.video_id && (
            <p className="text-[10px] text-slate-500 mt-1">
              元動画:{' '}
              <a
                href={`https://www.youtube.com/watch?v=${demand.video_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-slate-300"
              >
                {demand.video_id}
              </a>
            </p>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className={`text-lg font-bold ${scoreColor}`}>
            {(score * 100).toFixed(0)}
          </div>
          <div className="text-[10px] text-slate-500">
            適合 {(demand.relevance_score * 100).toFixed(0)}
          </div>
        </div>
      </div>
      {demand.status === 'pending' && (
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => onQueue(demand.id)}
            className="px-3 py-1 rounded text-xs font-semibold bg-accent/20 border border-accent/60 text-accent hover:bg-accent/30"
          >
            ＋ キューに追加
          </button>
          <button
            onClick={() => onDismiss(demand.id)}
            className="px-3 py-1 rounded text-xs font-semibold bg-bg-elev/40 border border-border/40 text-slate-400 hover:text-slate-200"
          >
            却下
          </button>
        </div>
      )}
    </li>
  );
}
