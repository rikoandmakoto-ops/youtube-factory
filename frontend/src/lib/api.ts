import { getSessionToken } from './auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/**
 * Backend rejected the JWT (token missing, expired, or signed with a
 * rotated secret). Pages should treat this as "session no longer valid"
 * and send the user through /api/auth/clear to drop the stale cookie.
 */
export class UnauthorizedError extends ApiError {
  constructor(body: unknown, message: string) {
    super(401, body, message);
    this.name = 'UnauthorizedError';
  }
}

/**
 * Server-component helper: if any backend call failed with 401, redirect
 * through /api/auth/clear so the stale cookie is dropped before landing
 * on /login. Without this, the middleware (which only checks cookie
 * presence) would bounce the user back to / and into a loop.
 *
 * Accepts either a Promise.allSettled results array OR a single caught
 * error from a try/catch block.
 */
export function redirectIfUnauthorized(
  resultsOrError: PromiseSettledResult<unknown>[] | unknown,
  nextPath?: string
): void {
  let hasAuthFailure = false;
  if (Array.isArray(resultsOrError)) {
    hasAuthFailure = resultsOrError.some(
      (r) => r.status === 'rejected' && r.reason instanceof UnauthorizedError
    );
  } else if (resultsOrError instanceof UnauthorizedError) {
    hasAuthFailure = true;
  }
  if (!hasAuthFailure) return;
  // Lazy import to avoid pulling next/navigation into client bundles
  // that incidentally import from this module.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { redirect } = require('next/navigation') as typeof import('next/navigation');
  const target = nextPath
    ? `/api/auth/clear?next=${encodeURIComponent(nextPath)}`
    : '/api/auth/clear';
  redirect(target);
}

type FetchOpts = RequestInit & {
  /** Pass token explicitly. If omitted, reads from cookies (server only). */
  token?: string | null;
  /** Disable Next caching for dynamic data. */
  noStore?: boolean;
};

async function call<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const url = `${BACKEND_URL}${path}`;
  const headers = new Headers(opts.headers);
  // FormData は content-type をブラウザに任せる
  const isFormData =
    typeof FormData !== 'undefined' && opts.body instanceof FormData;
  if (!isFormData && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }

  const token = opts.token === undefined ? getSessionToken() : opts.token;
  if (token) {
    headers.set('authorization', `Bearer ${token}`);
  }

  const res = await fetch(url, {
    ...opts,
    headers,
    cache: opts.noStore ? 'no-store' : opts.cache,
  });

  const text = await res.text();
  let body: unknown = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* keep as text */
  }

  if (!res.ok) {
    const msg =
      typeof body === 'object' && body && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `${res.status} ${res.statusText}`;
    if (res.status === 401) {
      throw new UnauthorizedError(body, msg);
    }
    throw new ApiError(res.status, body, msg);
  }

  return body as T;
}

// ── Auth ──
export type LoginResponse = { token: string; expires_in: number };
export async function login(password: string): Promise<LoginResponse> {
  return call<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
    token: null,
  });
}

// ── System ──
export type SystemStatus = {
  voicevox: { connected: boolean; url: string };
  gpt: { connected: boolean; configured: boolean };
  disk: { free_gb: number; total_gb: number };
};
export async function getSystemStatus(): Promise<SystemStatus> {
  return call<SystemStatus>('/api/system/status', { noStore: true });
}

// ── Channels ──
export type Channel = {
  id: string;
  name: string;
  concept: string;
  style: string;
  /** Optional metric fields populated by backend. */
  video_count?: number;
  total_views?: number;
  subscribers?: number;
};
export async function listChannels(): Promise<Channel[]> {
  const data = await call<{ channels: Channel[] }>('/api/channels', {
    noStore: true,
  });
  return data.channels;
}

export type Video = {
  id: string;
  title: string;
  created_at: string;
  duration: string;
  views: number;
  status: 'published' | 'draft' | 'failed' | 'pending' | 'scheduled';
  thumbnail_url: string | null;
  /** Phase 3 — YouTube 紐付け情報 */
  youtube_url?: string | null;
  youtube_video_id?: string | null;
  scheduled_at?: string | null;
  /** Pipeline ジョブ結果（出力ファイルパス含む） */
  result?: Record<string, unknown> | null;
  /** 内部ジョブの状態（completed なら publish 可能） */
  queue_status?: string;
};

export type PublishSettings = {
  auto_publish: boolean;
  default_privacy: 'private' | 'unlisted' | 'public';
  short_delay_minutes: number;
  short_description_template: string;
};

export type ChannelDetail = Channel & {
  /** ブランドアカウントID（連携時のみ）。アップロード先の指定に使う */
  youtube_channel_id?: string | null;
  publish_settings?: PublishSettings | null;
  videos: Video[];
  metrics: {
    total_views: number;
    subscribers: number;
    video_count: number;
    avg_views_per_video: number;
  };
};
export async function getChannel(id: string): Promise<ChannelDetail> {
  return call<ChannelDetail>(`/api/channels/${encodeURIComponent(id)}`, {
    noStore: true,
  });
}

// ── Generate ──
export type GenerateRequest = {
  channel_id: string;
  theme: string;
  duration_minutes: 8 | 12 | 15;
  generate_short: boolean;
  generate_thumbnail: boolean;
  copy_to_icloud: boolean;
  /** 0..1. Omit to use the channel's default BGM volume. */
  bgm_volume?: number;
};

export type GenerateResponse = { job_id: string; status: string };
export async function startGenerate(
  req: GenerateRequest
): Promise<GenerateResponse> {
  return call<GenerateResponse>('/api/generate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export type GenerateStatus = {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  step: number; // 1..5
  step_label: string;
  progress: number; // 0..100
  log: string;
  title?: string;
  error?: string;
  result?: Record<string, unknown> | null;
  channel_id?: string;
};
export async function getGenerateStatus(
  jobId: string
): Promise<GenerateStatus> {
  return call<GenerateStatus>(
    `/api/generate/${encodeURIComponent(jobId)}/status`,
    { noStore: true }
  );
}

export async function cancelGenerate(jobId: string): Promise<GenerateStatus> {
  return call<GenerateStatus>(
    `/api/generate/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST', noStore: true }
  );
}

export type ThemeSuggestion = { title: string; angle: string };
export async function suggestTheme(
  channelId: string
): Promise<ThemeSuggestion[]> {
  const data = await call<{ themes: ThemeSuggestion[] }>(
    '/api/generate/suggest-theme',
    {
      method: 'POST',
      body: JSON.stringify({ channel_id: channelId }),
    }
  );
  return data.themes;
}

// ── Active jobs (for dashboard) ──
export type ActiveJob = {
  job_id: string;
  title: string;
  step: number;
  step_label: string;
  progress: number;
  channel_id?: string | null;
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
};
export async function listActiveJobs(): Promise<ActiveJob[]> {
  const data = await call<{ jobs: ActiveJob[] }>('/api/generate/active', {
    noStore: true,
  });
  return data.jobs;
}

// ────────────────────────────────────────────────────────────
// Phase 2 — 設定 / アセット / システム
// ────────────────────────────────────────────────────────────

/** 生のチャンネル JSON。型は緩めにし、エディタ側で詳細スキーマを扱う */
export type ChannelConfig = Record<string, any>;

export async function getChannelConfig(id: string): Promise<ChannelConfig> {
  return call<ChannelConfig>(`/api/channels/${encodeURIComponent(id)}/config`, {
    noStore: true,
  });
}

export async function updateChannelConfig(
  id: string,
  patch: Partial<ChannelConfig>
): Promise<{ status: string; config: ChannelConfig }> {
  return call(`/api/channels/${encodeURIComponent(id)}/config`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

// ── ペルソナ（ターゲット視聴者）── video_format.persona の薄いCRUD
export type ChannelPersona = {
  age_group: string;
  gender: string;
  interest_categories: string[];
  tone_style: string;
  content_depth: string;
  custom_notes: string;
};

export async function getChannelPersona(
  id: string
): Promise<{ channel_id: string; persona: ChannelPersona }> {
  return call(`/api/channels/${encodeURIComponent(id)}/persona`, {
    noStore: true,
  });
}

export async function updateChannelPersona(
  id: string,
  patch: Partial<ChannelPersona>
): Promise<{ status: string; channel_id: string; persona: ChannelPersona }> {
  return call(`/api/channels/${encodeURIComponent(id)}/persona`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export type CreateChannelPayload = {
  id: string;
  name: string;
  concept?: string;
  style?: 'yukkuri' | 'monologue';
  template?: string | null;
  characters?: Record<string, unknown>;
  thumbnail_template?: Record<string, unknown>;
  defaults?: Record<string, unknown>;
  content_policy?: Record<string, unknown>;
  theme_seeds?: Array<Record<string, unknown>>;
  video_format?: Record<string, unknown>;
};

export async function createChannel(
  payload: CreateChannelPayload
): Promise<{ status: string; channel: Channel }> {
  return call('/api/channels', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deleteChannel(id: string): Promise<{ status: string }> {
  return call(`/api/channels/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export type AssetEntry = {
  filename: string;
  size_bytes: number;
  url: string;
};

export type AssetsResponse = {
  assets: Record<string, AssetEntry[]>;
};

export const ASSET_KINDS = [
  'background',
  'character',
  'reference',
  'thumbnail',
  'bgm',
  'se',
  'intro',
  'outro',
] as const;
export type AssetKind = (typeof ASSET_KINDS)[number];

export async function listAssets(channelId: string): Promise<AssetsResponse> {
  return call<AssetsResponse>(
    `/api/channels/${encodeURIComponent(channelId)}/assets`,
    { noStore: true }
  );
}

export async function uploadAsset(
  channelId: string,
  kind: AssetKind,
  file: File | Blob,
  filename?: string
): Promise<AssetEntry & { status: string; kind: AssetKind }> {
  const fd = new FormData();
  fd.set('kind', kind);
  fd.set('file', file, filename ?? (file as File).name ?? 'upload');
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/upload`,
    {
      method: 'POST',
      body: fd,
    }
  );
}

export async function deleteAsset(
  channelId: string,
  kind: AssetKind,
  filename: string
): Promise<{ status: string }> {
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/assets/${encodeURIComponent(
      kind
    )}/${encodeURIComponent(filename)}`,
    { method: 'DELETE' }
  );
}

// ── Settings ──
export type Settings = {
  openai: { configured: boolean; preview: string };
  voicevox_url: string;
  output_dir: string;
  icloud_sync: boolean;
  youtube_oauth: { configured: boolean; client_id_preview: string; note: string };
  password_set: boolean;
};

export async function getSettings(): Promise<Settings> {
  return call<Settings>('/api/settings', { noStore: true });
}

export type SettingsUpdate = {
  openai_api_key?: string;
  voicevox_url?: string;
  output_dir?: string;
  icloud_sync?: boolean;
};

export async function updateSettings(
  patch: SettingsUpdate
): Promise<{ status: string; updated: string[] }> {
  return call('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function changePassword(
  current_password: string,
  new_password: string
): Promise<{ status: string; new_password_hash: string; instruction: string }> {
  return call('/api/auth/password', {
    method: 'PUT',
    body: JSON.stringify({ current_password, new_password }),
  });
}

// ────────────────────────────────────────────────────────────
// Phase 3 — YouTube OAuth / Publish / Analytics
// ────────────────────────────────────────────────────────────

export type YoutubeStatus = {
  connected: boolean;
  account_email: string | null;
  scopes: string[];
  client_configured: boolean;
  client_id_preview: string;
  google_libs_installed: boolean;
  crypto_installed: boolean;
  /** チャンネル別エンドポイントから返される追加情報 */
  channel_id?: string | null;
  youtube_channel_id?: string | null;
  youtube_channel_name?: string | null;
};

export async function getYoutubeStatus(): Promise<YoutubeStatus> {
  return call<YoutubeStatus>('/api/youtube/status', { noStore: true });
}

export async function setYoutubeClient(
  client_id: string,
  client_secret: string
): Promise<{ status: string }> {
  return call('/api/youtube/client', {
    method: 'POST',
    body: JSON.stringify({ client_id, client_secret }),
  });
}

export async function getYoutubeAuthUrl(
  redirect_uri: string
): Promise<{ auth_url: string; state: string }> {
  return call('/api/youtube/auth-url', {
    method: 'POST',
    body: JSON.stringify({ redirect_uri }),
  });
}

export async function youtubeCallback(
  state: string,
  code: string
): Promise<{ connected: boolean; account_email: string | null }> {
  return call('/api/youtube/callback', {
    method: 'POST',
    body: JSON.stringify({ state, code }),
  });
}

export async function youtubeDisconnect(): Promise<{ status: string }> {
  return call('/api/youtube/disconnect', { method: 'POST' });
}

// ── Per-channel YouTube OAuth ──

export async function getChannelYoutubeStatus(
  channelId: string
): Promise<YoutubeStatus> {
  return call<YoutubeStatus>(
    `/api/channels/${encodeURIComponent(channelId)}/youtube/status`,
    { noStore: true }
  );
}

export async function setChannelYoutubeClient(
  channelId: string,
  client_id: string,
  client_secret: string
): Promise<{ status: string; channel_id: string }> {
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/youtube/client`,
    {
      method: 'POST',
      body: JSON.stringify({ client_id, client_secret }),
    }
  );
}

export async function getChannelYoutubeAuthUrl(
  channelId: string,
  redirect_uri: string
): Promise<{ auth_url: string; state: string }> {
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/youtube/auth`,
    {
      method: 'POST',
      body: JSON.stringify({ redirect_uri }),
    }
  );
}

export async function channelYoutubeCallback(
  channelId: string,
  state: string,
  code: string
): Promise<{
  connected: boolean;
  channel_id: string;
  account_email: string | null;
  youtube_channel_id: string | null;
  youtube_channel_name: string | null;
}> {
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/youtube/callback`,
    {
      method: 'POST',
      body: JSON.stringify({ state, code }),
    }
  );
}

export async function channelYoutubeDisconnect(
  channelId: string
): Promise<{ status: string; channel_id: string }> {
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/youtube`,
    { method: 'DELETE' }
  );
}

export type PublishPayload = {
  video_path: string;
  title: string;
  description?: string;
  tags?: string[];
  category_id?: string;
  privacy?: 'private' | 'unlisted' | 'public';
  scheduled_at?: string | null;
  thumbnail_path?: string | null;
  is_short?: boolean;
  made_for_kids?: boolean;
  youtube_channel_id?: string | null;
};

export async function youtubePublish(
  payload: PublishPayload
): Promise<{ job_id: string; status: string }> {
  return call('/api/youtube/publish', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export type PublishJob = {
  id: string;
  status: 'queued' | 'uploading' | 'completed' | 'failed';
  progress: number;
  title: string;
  url?: string;
  video_id?: string;
  error?: string;
  thumbnail_set?: boolean;
  thumbnail_error?: string;
  started_at: string;
  completed_at?: string;
};

export async function getPublishJob(jobId: string): Promise<PublishJob> {
  return call<PublishJob>(`/api/youtube/publish/${encodeURIComponent(jobId)}`, {
    noStore: true,
  });
}

// ── Pair publish (メイン + 時差ショート) ──
export type PublishPairPayload = {
  job_id?: string;
  channel_id?: string;
  main_video_path?: string;
  short_video_path?: string;
  main_thumbnail_path?: string;
  short_thumbnail_path?: string;
  main_title?: string;
  short_title?: string;
  main_description?: string;
  short_description?: string;
  tags?: string[];
  category_id?: string;
  privacy?: 'private' | 'unlisted' | 'public';
  short_delay_minutes?: number;
  short_description_template?: string;
  youtube_channel_id?: string | null;
};

export type PairPublishJob = {
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
  started_at?: string;
  completed_at?: string;
};

export async function youtubePublishPair(
  payload: PublishPairPayload
): Promise<{ job_id: string; status: string; short_delay_minutes: number }> {
  return call('/api/youtube/publish-pair', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getPairPublishJob(
  jobId: string
): Promise<PairPublishJob> {
  return call<PairPublishJob>(
    `/api/youtube/publish-pair/${encodeURIComponent(jobId)}`,
    { noStore: true }
  );
}

export type DayPoint = { date: string; views: number };
export type TopVideo = { video_id: string; title: string; views: number };

export type AnalyticsResponse = {
  connected: boolean;
  source: 'youtube_analytics' | 'mock' | 'error';
  channel_id: string;
  youtube_channel_id?: string | null;
  metrics: {
    total_views: number;
    subscribers: number;
    video_count: number;
    avg_views_per_video: number;
  };
  views_by_day: DayPoint[];
  top_videos: TopVideo[];
  error?: string;
};

export async function getChannelAnalytics(
  channelId: string
): Promise<AnalyticsResponse> {
  return call<AnalyticsResponse>(
    `/api/channels/${encodeURIComponent(channelId)}/analytics`,
    { noStore: true }
  );
}

export type VideoStatus = 'draft' | 'published' | 'scheduled' | 'failed' | 'pending';

export async function setVideoStatus(
  jobId: string,
  status: VideoStatus,
  extra?: { video_id?: string; url?: string; scheduled_at?: string }
): Promise<{ status: string }> {
  return call(`/api/videos/${encodeURIComponent(jobId)}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status, ...(extra || {}) }),
  });
}

// ────────────────────────────────────────────────────────────
// Phase 4 — スケジュール / テンプレート / 履歴 / A/B / 通知
// ────────────────────────────────────────────────────────────

export type Schedule = {
  id: string;
  name: string;
  channel_id: string;
  days_of_week: number[]; // 0=sun..6=sat
  hour: number;
  minute: number;
  theme_mode: 'manual' | 'auto';
  theme?: string | null;
  duration_minutes: number;
  auto_publish: boolean;
  /** 自動投稿時に「生成完了から N 分後」に YouTube 上で公開。null = 即時 */
  publish_offset_minutes?: number | null;
  enabled: boolean;
  last_run_at?: string | null;
  last_run_status?: string | null;
  last_run_job_id?: string | null;
  next_run_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ScheduleInput = {
  name: string;
  channel_id: string;
  days_of_week: number[];
  hour: number;
  minute: number;
  theme_mode: 'manual' | 'auto';
  theme?: string | null;
  duration_minutes: number;
  auto_publish: boolean;
  publish_offset_minutes?: number | null;
  enabled: boolean;
};

export async function listSchedules(): Promise<{
  schedules: Schedule[];
  scheduler_available: boolean;
}> {
  return call('/api/schedules', { noStore: true });
}

export async function createSchedule(input: ScheduleInput): Promise<Schedule> {
  return call('/api/schedules', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function updateSchedule(
  id: string,
  input: ScheduleInput
): Promise<Schedule> {
  return call(`/api/schedules/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}

export async function toggleSchedule(
  id: string,
  enabled: boolean
): Promise<Schedule> {
  return call(`/api/schedules/${encodeURIComponent(id)}/toggle`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

export async function deleteSchedule(id: string): Promise<{ status: string }> {
  return call(`/api/schedules/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export type UpcomingSchedule = {
  id: string;
  name: string;
  channel_id: string;
  next_run_at: string;
  theme_mode: 'manual' | 'auto';
  theme?: string | null;
};

export async function listUpcomingSchedules(
  limit = 10
): Promise<{ upcoming: UpcomingSchedule[] }> {
  return call(`/api/schedules/upcoming?limit=${limit}`, { noStore: true });
}

export async function runScheduleNow(id: string): Promise<{ status: string }> {
  return call(`/api/schedules/${encodeURIComponent(id)}/run-now`, {
    method: 'POST',
  });
}

// ── Channel Autopilot (フルオート自動投稿) ──
export type AutopilotSchedule = {
  days_of_week: number[];
  hour: number;
  minute: number;
};

export type AutopilotTheme = {
  id: string;
  title: string;
  angle?: string;
};

export type AutopilotConfig = {
  enabled: boolean;
  schedule: AutopilotSchedule;
  duration_minutes: number;
  theme_queue: AutopilotTheme[];
};

export type AutopilotResponse = {
  channel_id: string;
  config: AutopilotConfig;
  next_run_at: string | null;
  scheduler_available: boolean;
};

export type AutopilotUpdate = {
  enabled?: boolean;
  schedule?: AutopilotSchedule;
  duration_minutes?: number;
};

export async function getAutopilot(channelId: string): Promise<AutopilotResponse> {
  return call(`/api/channels/${encodeURIComponent(channelId)}/autopilot`, {
    noStore: true,
  });
}

export async function updateAutopilot(
  channelId: string,
  patch: AutopilotUpdate
): Promise<AutopilotResponse> {
  return call(`/api/channels/${encodeURIComponent(channelId)}/autopilot`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function addAutopilotTheme(
  channelId: string,
  theme: { title: string; angle?: string }
): Promise<{ channel_id: string; queue: AutopilotTheme[]; added: AutopilotTheme }> {
  return call(`/api/channels/${encodeURIComponent(channelId)}/autopilot/queue`, {
    method: 'POST',
    body: JSON.stringify(theme),
  });
}

export async function reorderAutopilotQueue(
  channelId: string,
  queue: AutopilotTheme[]
): Promise<{ channel_id: string; queue: AutopilotTheme[] }> {
  return call(`/api/channels/${encodeURIComponent(channelId)}/autopilot/queue`, {
    method: 'PUT',
    body: JSON.stringify({ queue }),
  });
}

export async function updateAutopilotTheme(
  channelId: string,
  themeId: string,
  patch: { title?: string; angle?: string }
): Promise<{ channel_id: string; queue: AutopilotTheme[] }> {
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/autopilot/queue/${encodeURIComponent(themeId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }
  );
}

export async function deleteAutopilotTheme(
  channelId: string,
  themeId: string
): Promise<{ channel_id: string; queue: AutopilotTheme[] }> {
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/autopilot/queue/${encodeURIComponent(themeId)}`,
    { method: 'DELETE' }
  );
}

export async function refillAutopilotQueue(
  channelId: string,
  count = 5
): Promise<{ channel_id: string; queue: AutopilotTheme[]; added: AutopilotTheme[] }> {
  return call(
    `/api/channels/${encodeURIComponent(channelId)}/autopilot/queue/refill`,
    {
      method: 'POST',
      body: JSON.stringify({ count }),
    }
  );
}

export async function runAutopilotNow(
  channelId: string
): Promise<{ status: string }> {
  return call(`/api/channels/${encodeURIComponent(channelId)}/autopilot/run-now`, {
    method: 'POST',
  });
}

// ── Templates ──
export type Template = {
  id: string;
  name: string;
  channel_id: string;
  theme: string;
  duration_minutes: number;
  generate_short: boolean;
  generate_thumbnail: boolean;
  copy_to_icloud: boolean;
  ab_test: boolean;
  notes?: string;
  created_at: string;
  updated_at: string;
};

export type TemplateInput = Omit<Template, 'id' | 'created_at' | 'updated_at'>;

export async function listTemplates(): Promise<{ templates: Template[] }> {
  return call('/api/templates', { noStore: true });
}

export async function createTemplate(input: TemplateInput): Promise<Template> {
  return call('/api/templates', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function updateTemplate(
  id: string,
  input: TemplateInput
): Promise<Template> {
  return call(`/api/templates/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}

export async function deleteTemplate(id: string): Promise<{ status: string }> {
  return call(`/api/templates/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

// ── History / Cost ──
export type HistoryEntry = {
  job_id: string;
  channel_id: string;
  title: string;
  status: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error: string | null;
};

export async function listHistory(opts?: {
  channel_id?: string;
  status?: string;
  since?: string;
  until?: string;
  limit?: number;
}): Promise<{ history: HistoryEntry[]; total: number }> {
  const q = new URLSearchParams();
  if (opts?.channel_id) q.set('channel_id', opts.channel_id);
  if (opts?.status) q.set('status', opts.status);
  if (opts?.since) q.set('since', opts.since);
  if (opts?.until) q.set('until', opts.until);
  if (opts?.limit) q.set('limit', String(opts.limit));
  const qs = q.toString();
  return call(`/api/history${qs ? `?${qs}` : ''}`, { noStore: true });
}

export type Metrics = {
  calls: number;
  cost_usd: number;
  prompt_tokens: number;
  completion_tokens: number;
  images: number;
};

export type CostSummary = {
  total: Metrics;
  today: Metrics;
  this_month: Metrics;
  by_month: Array<{ month: string; calls: number; cost_usd: number; images: number }>;
  by_day?: Array<{ date: string; calls: number; cost_usd: number; images: number }>;
  by_channel: Record<string, Metrics>;
  by_model: Record<string, Metrics>;
  by_provider?: Record<string, Metrics>;
  by_purpose?: Record<string, Metrics>;
  pricing: Record<string, unknown>;
};

export async function getCostSummary(): Promise<CostSummary> {
  return call('/api/history/cost-summary', { noStore: true });
}

// ── A/B Variants ──
export type Variant = {
  id: string;
  job_id: string;
  kind: 'title' | 'thumbnail';
  variant_index: number;
  content: string;
  selected: boolean;
  created_at: string;
};

export async function generateVariants(
  jobId: string,
  opts?: { title_count?: number; thumbnail_count?: number }
): Promise<{ status: string; title: Variant[]; thumbnail: Variant[] }> {
  return call(`/api/videos/${encodeURIComponent(jobId)}/ab-generate`, {
    method: 'POST',
    body: JSON.stringify({
      job_id: jobId,
      title_count: opts?.title_count ?? 3,
      thumbnail_count: opts?.thumbnail_count ?? 3,
    }),
  });
}

export async function getVariants(
  jobId: string
): Promise<{ job_id: string; variants: { title: Variant[]; thumbnail: Variant[] } }> {
  return call(`/api/videos/${encodeURIComponent(jobId)}/variants`, {
    noStore: true,
  });
}

export async function selectVariant(
  jobId: string,
  variantId: string
): Promise<{ status: string; variant_id: string; kind: string }> {
  return call(`/api/videos/${encodeURIComponent(jobId)}/variants/select`, {
    method: 'POST',
    body: JSON.stringify({ variant_id: variantId }),
  });
}

// ── Notifications ──
export type NotificationSettings = {
  configured: boolean;
  line_token_preview: string;
  line_token_set?: boolean;
  slack_webhook_preview: string;
  slack_webhook_set?: boolean;
  smtp_host: string;
  smtp_port: number | null;
  smtp_user: string;
  smtp_password_set?: boolean;
  smtp_from: string;
  smtp_to: string;
  notify_on_generate_done: boolean;
  notify_on_upload_done: boolean;
  notify_on_schedule_run: boolean;
  notify_on_error: boolean;
  updated_at?: string;
};

export type NotificationSettingsUpdate = {
  line_token?: string;
  slack_webhook_url?: string;
  smtp_host?: string;
  smtp_port?: number | null;
  smtp_user?: string;
  smtp_password?: string;
  smtp_from?: string;
  smtp_to?: string;
  notify_on_generate_done: boolean;
  notify_on_upload_done: boolean;
  notify_on_schedule_run: boolean;
  notify_on_error: boolean;
};

export async function getNotificationSettings(): Promise<NotificationSettings> {
  return call('/api/settings/notifications', { noStore: true });
}

export async function updateNotificationSettings(
  patch: NotificationSettingsUpdate
): Promise<{ status: string }> {
  return call('/api/settings/notifications', {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function testNotification(
  channel?: 'line' | 'slack' | 'email',
  message?: string
): Promise<{ status: string; results: Array<Record<string, unknown>> }> {
  return call('/api/notifications/test', {
    method: 'POST',
    body: JSON.stringify({ channel: channel ?? null, message: message ?? null }),
  });
}

// ────────────────────────────────────────────────────────────
// Phase 5 — サンプルイラスト（生成前の確認用）
// ────────────────────────────────────────────────────────────

export type IllustrationStyle = {
  style?: 'vivid' | 'natural';
  format?: 'landscape' | 'square' | 'portrait';
  art_style?: string;
  background?: string;
  include_characters?: boolean;
  frame_style?: string;
  extra_prompt?: string;
  allow_text_labels?: boolean;
  allow_frame?: boolean;
};

export type SampleIllustrationRequest = {
  topic: string;
  channel_id?: string;
  illust_style?: IllustrationStyle;
  include_characters?: boolean;
  /**
   * Ordered list of free-text feedback strings the user has supplied across
   * previous regenerations of the same sample. Each string is one user
   * "ここをこう直して" message. Most recent items take priority.
   */
  feedback?: string[];
};

export type SampleIllustrationResponse = {
  sample_id: string;
  url: string;
  prompt: string;
  style: IllustrationStyle;
  feedback?: string[];
};

export async function generateSampleIllustration(
  req: SampleIllustrationRequest
): Promise<SampleIllustrationResponse> {
  return call<SampleIllustrationResponse>('/api/illustrations/sample', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function deleteSampleIllustration(
  sampleId: string
): Promise<{ status: string; sample_id: string }> {
  return call(`/api/illustrations/sample/${encodeURIComponent(sampleId)}`, {
    method: 'DELETE',
  });
}

// ── Async (start + poll) variants ─────────────────────────────────────
// These survive tab-switches / serverless timeouts because the heavy
// generation runs detached from any single HTTP connection. Clients POST
// to /start to obtain a job_id, then poll /job/{id} until state==='done'.

export type AsyncJobStart = { job_id: string };

export type AsyncJobStatus<T> = {
  job_id: string;
  state: 'running' | 'done' | 'error';
  kind: string;
  error?: string | null;
  result?: T | null;
};

export async function startSampleIllustrationJob(
  req: SampleIllustrationRequest
): Promise<AsyncJobStart> {
  return call<AsyncJobStart>('/api/illustrations/sample/start', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getSampleIllustrationJob(
  jobId: string
): Promise<AsyncJobStatus<SampleIllustrationResponse>> {
  return call<AsyncJobStatus<SampleIllustrationResponse>>(
    `/api/illustrations/sample/job/${encodeURIComponent(jobId)}`,
    { noStore: true }
  );
}

// ──────────────────────────────────────────────────────────────────────
// Thumbnail (HTML+CSS+Playwright pipeline)
// ──────────────────────────────────────────────────────────────────────
export type ThumbnailGenerateRequest = {
  title: string;
  channel_id: string;
  reuse_background_id?: string;
  line1?: string;
  line2?: string;
  line3_badge?: string;
  sub_text?: string;
  /**
   * Ordered list of free-text feedback strings the user has supplied across
   * previous regenerations of the same thumbnail. The backend forwards them to
   * GPT-4o so the brief is adjusted on top of the title.
   */
  feedback?: string[];
};

export type ThumbnailBrief = {
  line1?: string;
  line2?: string;
  line3_badge?: string;
  sub_text?: string;
  highlight_word?: string;
  background_concept?: string;
  color_palette?: string;
  [k: string]: unknown;
};

export type ThumbnailGenerateResponse = {
  thumbnail_id: string;
  thumbnail_url: string;
  background_id: string;
  background_url: string;
  brief: ThumbnailBrief;
  feedback?: string[];
};

export async function generateThumbnail(
  req: ThumbnailGenerateRequest
): Promise<ThumbnailGenerateResponse> {
  return call<ThumbnailGenerateResponse>('/api/thumbnails/generate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function previewThumbnail(
  req: ThumbnailGenerateRequest
): Promise<ThumbnailGenerateResponse> {
  return call<ThumbnailGenerateResponse>('/api/thumbnails/preview', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function deleteThumbnail(
  thumbnailId: string
): Promise<{ status: string; thumbnail_id: string }> {
  return call(`/api/thumbnails/${encodeURIComponent(thumbnailId)}`, {
    method: 'DELETE',
  });
}

export async function startThumbnailJob(
  req: ThumbnailGenerateRequest
): Promise<AsyncJobStart> {
  return call<AsyncJobStart>('/api/thumbnails/start', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getThumbnailJob(
  jobId: string
): Promise<AsyncJobStatus<ThumbnailGenerateResponse>> {
  return call<AsyncJobStatus<ThumbnailGenerateResponse>>(
    `/api/thumbnails/job/${encodeURIComponent(jobId)}`,
    { noStore: true }
  );
}

// ──────────────────────────────────────────────────────────────────────
// BGM Volume Preview (Phase 6)
// ──────────────────────────────────────────────────────────────────────
export type BgmPreviewRequest = {
  channel_id: string;
  /** 0..1 — same scale as channel_format.audio.bgm_volume. */
  bgm_volume: number;
  duration_seconds?: number;
};

export type BgmPreviewResponse = {
  preview_id: string;
  /** /api/bgm-preview/{id} — playable from <audio src=...>. */
  url: string;
  bgm_volume: number;
  duration_seconds: number;
  bgm_filename: string | null;
  voicevox_used: boolean;
};

export async function generateBgmPreview(
  req: BgmPreviewRequest
): Promise<BgmPreviewResponse> {
  return call<BgmPreviewResponse>('/api/bgm-preview', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ──────────────────────────────────────────────────────────────────────
// Phase D — Analytics (YouTube Analytics + Comments + Trends + AB Tests)
// ──────────────────────────────────────────────────────────────────────
//
// Backend (api_analytics.py) endpoints are mounted under `/api/analytics`:
//   GET  /api/analytics/channel/{id}/overview
//   GET  /api/analytics/videos/{channel_id}
//   GET  /api/analytics/video/{video_id}/retention
//   GET  /api/analytics/video/{video_id}/comments
//   POST /api/analytics/sync/{channel_id}
// These are intentionally distinct from the legacy
// `/api/channels/{id}/analytics` endpoint (mock/lightweight summary).

export type AnalyticsDailyPoint = {
  date: string;
  views?: number;
  watch_time_minutes?: number;
  subscribers_gained?: number;
  subscribers_lost?: number;
  impressions?: number;
  ctr?: number;
  average_view_duration_seconds?: number;
  [k: string]: unknown;
};

export type AnalyticsOverview = {
  channel_id: string;
  days_requested: number;
  totals: {
    views: number;
    watch_time_minutes: number;
    subscribers_gained: number;
    subscribers_lost: number;
    net_subscribers: number;
  };
  daily: AnalyticsDailyPoint[];
};

export async function getAnalyticsOverview(
  channelId: string,
  days = 30
): Promise<AnalyticsOverview> {
  return call<AnalyticsOverview>(
    `/api/analytics/channel/${encodeURIComponent(channelId)}/overview?days=${days}`,
    { noStore: true }
  );
}

export type AnalyticsVideoMetric = {
  video_id: string;
  title?: string;
  channel_id?: string;
  published_at?: string | null;
  views?: number;
  impressions?: number;
  ctr?: number;
  average_view_duration_seconds?: number;
  average_view_percentage?: number;
  watch_time_minutes?: number;
  likes?: number;
  comments?: number;
  subscribers_gained?: number;
  recorded_at?: string;
  thumbnail_url?: string | null;
  [k: string]: unknown;
};

export type AnalyticsVideosResponse = {
  channel_id: string;
  count: number;
  items: AnalyticsVideoMetric[];
};

export async function getAnalyticsVideos(
  channelId: string,
  limit = 100
): Promise<AnalyticsVideosResponse> {
  return call<AnalyticsVideosResponse>(
    `/api/analytics/videos/${encodeURIComponent(channelId)}?limit=${limit}`,
    { noStore: true }
  );
}

export type AnalyticsRetentionPoint = {
  elapsed_video_ratio: number;
  audience_watch_ratio?: number;
  relative_retention_performance?: number;
};

export type AnalyticsRetentionResponse = {
  video_id: string;
  recorded_at?: string;
  curve: AnalyticsRetentionPoint[];
};

export async function getAnalyticsRetention(
  videoId: string
): Promise<AnalyticsRetentionResponse> {
  return call<AnalyticsRetentionResponse>(
    `/api/analytics/video/${encodeURIComponent(videoId)}/retention`,
    { noStore: true }
  );
}

export type AnalyticsCommentSummary = {
  total?: number;
  positive?: number;
  negative?: number;
  neutral?: number;
  question?: number;
  top_topics?: Array<{ topic: string; count: number }>;
  [k: string]: unknown;
};

export type AnalyticsComment = {
  comment_id: string;
  text: string;
  author?: string | null;
  likes?: number;
  published_at?: string | null;
  sentiment?: 'positive' | 'negative' | 'neutral' | string | null;
  topic?: string | null;
  [k: string]: unknown;
};

export type AnalyticsCommentsResponse = {
  video_id: string;
  summary: AnalyticsCommentSummary | null;
  comments: AnalyticsComment[];
};

export async function getAnalyticsComments(
  videoId: string,
  limit = 200
): Promise<AnalyticsCommentsResponse> {
  return call<AnalyticsCommentsResponse>(
    `/api/analytics/video/${encodeURIComponent(videoId)}/comments?limit=${limit}`,
    { noStore: true }
  );
}

export type AnalyticsSyncOptions = {
  days?: number;
  max_videos?: number;
  fetch_retention_for?: number;
  sync_comments_for?: number;
  max_comments_per_video?: number;
  analyze_comments?: boolean;
};

export type AnalyticsSyncResponse = {
  channel?: { ok?: boolean; rows?: number; error?: string };
  videos?: { ok?: boolean; count?: number; items?: AnalyticsVideoMetric[]; error?: string };
  retention?: { ok?: boolean; count?: number; error?: string };
  comments?: Array<Record<string, unknown>>;
  [k: string]: unknown;
};

export async function syncChannelAnalytics(
  channelId: string,
  opts?: AnalyticsSyncOptions
): Promise<AnalyticsSyncResponse> {
  return call<AnalyticsSyncResponse>(
    `/api/analytics/sync/${encodeURIComponent(channelId)}`,
    {
      method: 'POST',
      body: JSON.stringify(opts ?? {}),
      noStore: true,
    }
  );
}

// ── Trends (Phase C) ──
export type TrendKeyword = {
  keyword: string;
  source?: string;
  score?: number;
  query_volume?: number | null;
  [k: string]: unknown;
};

export type TrendingVideo = {
  video_id?: string;
  title?: string;
  channel_title?: string;
  view_count?: number;
  url?: string;
  thumbnail_url?: string | null;
  [k: string]: unknown;
};

export type TrendsResponse = {
  status: string;
  channel_id: string;
  trends: {
    keywords?: TrendKeyword[];
    related_keywords?: TrendKeyword[];
    trending_videos?: TrendingVideo[];
    [k: string]: unknown;
  };
  themes?: Array<{ title?: string; angle?: string; [k: string]: unknown }>;
};

export async function getTrends(
  channelId: string,
  count = 5
): Promise<TrendsResponse> {
  return call<TrendsResponse>(
    `/api/trends/${encodeURIComponent(channelId)}?count=${count}`,
    { noStore: true }
  );
}

// ── AB Tests (Phase C) ──
export type ABTestVariant = {
  title?: string;
  catchcopy?: string;
  thumbnail_text?: string;
  reasoning?: string;
  ctr_score?: number;
  [k: string]: unknown;
};

export type ABTest = {
  id?: string;
  test_id?: string;
  channel_id?: string | null;
  theme_title?: string;
  theme_angle?: string;
  variants?: ABTestVariant[];
  best_variant_index?: number;
  created_at?: string;
  [k: string]: unknown;
};

export async function listABTests(
  channelId?: string,
  limit = 50
): Promise<{ status: string; items: ABTest[] }> {
  const q = new URLSearchParams();
  if (channelId) q.set('channel_id', channelId);
  q.set('limit', String(limit));
  return call(`/api/ab-test?${q.toString()}`, { noStore: true });
}

export async function getABTest(testId: string): Promise<ABTest> {
  return call<ABTest>(`/api/ab-test/${encodeURIComponent(testId)}`, {
    noStore: true,
  });
}

// ── Phase D: PDCA (evaluations / ab-reconciliation / improvements) ──

export type WeakSection = {
  section?: string;
  ratio_from?: number;
  ratio_to?: number;
  drop_rate?: number;
  drop_percent?: number;
  sample_text?: string;
  issue?: string;
  [k: string]: unknown;
};

export type CommentFeedbackEntry = {
  comment?: string;
  section?: string;
  action?: string;
  [k: string]: unknown;
};

export type ScenarioEvaluation = {
  video_id: string;
  channel_id: string;
  evaluated_at: number;
  hook_strength: number;
  specificity: number;
  pacing: number;
  cta_effectiveness: number;
  wording_quality: number;
  overall: number;
  weak_sections?: WeakSection[];
  improvement_suggestions?: string[];
  comment_feedback?: CommentFeedbackEntry[];
  scenario_path?: string | null;
  video_title?: string | null;
};

export type WeakPatternSummary = {
  count: number;
  averages?: Record<string, number>;
  weak_sections?: Array<{
    section: string;
    frequency: number;
    frequency_ratio: number;
  }>;
  recent_suggestions?: string[];
};

export type EvaluationsListResponse = {
  channel_id: string;
  count: number;
  items: ScenarioEvaluation[];
  weak_patterns?: WeakPatternSummary;
};

export async function listEvaluations(
  channelId: string,
  limit = 100
): Promise<EvaluationsListResponse> {
  return call<EvaluationsListResponse>(
    `/api/evaluations/${encodeURIComponent(channelId)}?limit=${limit}`,
    { noStore: true }
  );
}

export async function getEvaluation(
  channelId: string,
  videoId: string
): Promise<{ evaluation: ScenarioEvaluation; retention?: unknown; comment_summary?: unknown }> {
  return call(
    `/api/evaluations/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}`,
    { noStore: true }
  );
}

export async function runEvaluations(
  channelId: string,
  body?: { use_gpt?: boolean; only_new?: boolean; max_videos?: number }
): Promise<Record<string, unknown>> {
  return call(`/api/evaluations/${encodeURIComponent(channelId)}/run`, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
    noStore: true,
  });
}

export type AbReconciliationItem = {
  test_id: string;
  variant_index: number;
  channel_id?: string | null;
  video_id?: string | null;
  pattern_type?: string | null;
  predicted_score?: number | null;
  actual_ctr?: number | null;
  actual_impressions?: number | null;
  actual_views?: number | null;
  reconciled_at: number;
};

export type AbPatternInsight = {
  pattern_type: string;
  samples: number;
  predicted_score_avg?: number | null;
  actual_ctr_avg?: number | null;
  actual_ctr_percent_avg?: number | null;
};

export type AbReconciliationResponse = {
  channel_id: string;
  count: number;
  items: AbReconciliationItem[];
  pattern_insights?: {
    channel_id: string;
    total_samples: number;
    overall_actual_ctr_avg?: number | null;
    patterns: AbPatternInsight[];
  };
};

export async function listAbReconciliation(
  channelId: string,
  limit = 200
): Promise<AbReconciliationResponse> {
  return call<AbReconciliationResponse>(
    `/api/ab-reconciliation/${encodeURIComponent(channelId)}?limit=${limit}`,
    { noStore: true }
  );
}

export async function runAbReconciliation(
  channelId: string,
  body?: { min_age_days?: number }
): Promise<Record<string, unknown>> {
  return call(`/api/ab-reconciliation/${encodeURIComponent(channelId)}/run`, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
    noStore: true,
  });
}

export type ImprovementCatchcopy = {
  pattern?: string;
  title?: string;
  thumb_copy?: string[];
  score?: number;
  comment?: string;
  [k: string]: unknown;
};

export type ImprovementEntry = {
  video_id: string;
  channel_id: string;
  created_at: number;
  updated_at: number;
  status: 'pending' | 'applied' | 'dismissed' | string;
  current_title?: string | null;
  current_ctr?: number | null;
  channel_avg_ctr?: number | null;
  suggested_titles?: string[];
  suggested_catchcopies?: ImprovementCatchcopy[];
  predicted_improvement?: number | null;
};

export type ImprovementsListResponse = {
  channel_id: string;
  count: number;
  items: ImprovementEntry[];
  channel_avg_ctr?: number | null;
};

export async function listImprovements(
  channelId: string,
  opts?: { status?: string; limit?: number }
): Promise<ImprovementsListResponse> {
  const sp = new URLSearchParams();
  if (opts?.status) sp.set('status', opts.status);
  if (opts?.limit) sp.set('limit', String(opts.limit));
  const qs = sp.toString();
  return call<ImprovementsListResponse>(
    `/api/improvements/${encodeURIComponent(channelId)}${qs ? `?${qs}` : ''}`,
    { noStore: true }
  );
}

export async function runImprovementDetection(
  channelId: string,
  body?: { threshold_ratio?: number; max_videos?: number; regen_titles?: boolean }
): Promise<Record<string, unknown>> {
  return call(`/api/improvements/${encodeURIComponent(channelId)}/run`, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
    noStore: true,
  });
}

export async function regenerateImprovementCatchcopy(
  channelId: string,
  videoId: string
): Promise<ImprovementEntry> {
  return call<ImprovementEntry>(
    `/api/improvements/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/regenerate`,
    { method: 'POST', noStore: true }
  );
}

export async function setImprovementStatus(
  channelId: string,
  videoId: string,
  status: 'pending' | 'applied' | 'dismissed'
): Promise<{ video_id: string; status: string }> {
  return call(
    `/api/improvements/${encodeURIComponent(channelId)}/${encodeURIComponent(videoId)}/status`,
    {
      method: 'PUT',
      body: JSON.stringify({ status }),
      noStore: true,
    }
  );
}

// ── Model compete (gpt vs claude) ──
export type ModelPerformanceStats = {
  scenario_count: number;
  selected_count: number;
  win_count: number;
  compare_runs: number;
  win_rate: number;
  samples_with_metrics: number;
  avg_views: number;
  avg_ctr: number;
  avg_retention: number;
  avg_blind_overall: number;
  perf_score: number;
};

export type ModelPerformanceSummary = {
  channel_id: string;
  by_model: { gpt: ModelPerformanceStats; claude: ModelPerformanceStats };
  leader: 'gpt' | 'claude' | null;
  leader_margin: number;
  blind_compare_runs: number;
  selected_counts: Record<string, number>;
  min_samples_for_bias: number;
  bias_threshold: number;
};

export type ModelCompeteStrategy = {
  mode: 'blind' | 'prefer_gpt' | 'prefer_claude';
  reason: string;
  leader: 'gpt' | 'claude' | null;
  margin: number;
};

export type ModelCompeteRunCandidate = {
  title?: string | null;
  won_blind_eval?: boolean;
  blind_overall?: number | null;
  blind_scores?: Record<string, number>;
  selected?: boolean;
  selected_by?: string | null;
  video_id?: string | null;
};

export type ModelCompeteRun = {
  run_id: string;
  created_at: number;
  candidates: {
    gpt?: ModelCompeteRunCandidate;
    claude?: ModelCompeteRunCandidate;
  };
};

export type ModelPerformanceResponse = {
  channel_id: string;
  performance: ModelPerformanceSummary;
  strategy: ModelCompeteStrategy;
  recent_runs: ModelCompeteRun[];
};

export async function getModelPerformance(
  channelId: string,
  recentRuns = 20
): Promise<ModelPerformanceResponse> {
  return call<ModelPerformanceResponse>(
    `/api/model-performance/${encodeURIComponent(channelId)}?recent_runs=${recentRuns}`,
    { noStore: true }
  );
}

// ── Server Logs ──
export type LogsResponse = {
  path: string | null;
  size_bytes: number;
  mtime: number | null;
  lines: string[];
  note?: string;
};

export async function getServerLogs(opts: {
  lines?: number;
  filter?: string;
  level?: 'error' | 'warn' | 'info';
} = {}): Promise<LogsResponse> {
  const q = new URLSearchParams();
  if (opts.lines) q.set('lines', String(opts.lines));
  if (opts.filter) q.set('filter', opts.filter);
  if (opts.level) q.set('level', opts.level);
  const qs = q.toString();
  return call<LogsResponse>(`/api/logs${qs ? `?${qs}` : ''}`, { noStore: true });
}

// ── Scenario Archives ──
export type ScenarioCompeteSummary = {
  selected_by: string | null;
  winner_model: string | null;
  candidates: {
    gpt: { title?: string } | null;
    claude: { title?: string } | null;
  };
};

export type ScenarioArchiveItem = {
  channel_id: string;
  file: string;
  title: string;
  theme: Record<string, unknown> | null;
  style: string;
  short: { count: number; chars: number; avg_chars: number };
  full: { count: number; chars: number; avg_chars: number };
  mtime: number;
  size_bytes: number;
  has_compete: boolean;
  chosen_provider: string | null;
  compete_summary: ScenarioCompeteSummary | null;
};

export type ScenarioArchivesResponse = {
  items: ScenarioArchiveItem[];
  channels: string[];
  total?: number;
};

export async function listScenarioArchives(opts: {
  channel_id?: string;
  q?: string;
  has_compete?: boolean;
  limit?: number;
} = {}): Promise<ScenarioArchivesResponse> {
  const qp = new URLSearchParams();
  if (opts.channel_id) qp.set('channel_id', opts.channel_id);
  if (opts.q) qp.set('q', opts.q);
  if (typeof opts.has_compete === 'boolean')
    qp.set('has_compete', String(opts.has_compete));
  if (opts.limit) qp.set('limit', String(opts.limit));
  const qs = qp.toString();
  return call<ScenarioArchivesResponse>(
    `/api/scenario-archives${qs ? `?${qs}` : ''}`,
    { noStore: true }
  );
}

export type ScenarioArchiveDetail = {
  channel_id: string;
  file: string;
  mtime: number;
  size_bytes: number;
  data: Record<string, any>;
};

export async function getScenarioArchive(
  channelId: string,
  fileName: string
): Promise<ScenarioArchiveDetail> {
  return call<ScenarioArchiveDetail>(
    `/api/scenario-archives/${encodeURIComponent(channelId)}/${encodeURIComponent(
      fileName
    )}`,
    { noStore: true }
  );
}

// ── Posting Optimizer ──
export type OptimalPostingSlot = {
  day_of_week: number; // 0=Sun ... 6=Sat
  hour: number;
  minute: number;
  avg_views: number;
  sample_size: number;
  boost_percent: number;
  is_fallback?: boolean;
};

export type OptimalPostingRecommendation = {
  recommended: OptimalPostingSlot;
  alternatives: OptimalPostingSlot[];
  channel_avg_views: number;
  data_days: number;
  note?: string | null;
};

export type OptimalPostingHeatmap = {
  grid: number[][]; // [7][24] avg views
  samples: number[][]; // [7][24] counts
  channel_avg_views: number;
  channel_total_videos: number;
  data_days: number;
};

export type OptimalPostingStatus = {
  channel_id: string;
  current_schedule: {
    days_of_week: number[];
    hour: number;
    minute: number;
    enabled: boolean;
  } | null;
  recommendation: OptimalPostingRecommendation;
  heatmap: OptimalPostingHeatmap;
  computed_at: number;
};

export async function getOptimalPostingTime(
  channelId: string,
  opts: { days?: number; recompute?: boolean } = {}
): Promise<OptimalPostingStatus> {
  const q = new URLSearchParams();
  if (opts.days) q.set('days', String(opts.days));
  if (opts.recompute) q.set('recompute', 'true');
  const qs = q.toString();
  return call<OptimalPostingStatus>(
    `/api/optimal-posting-time/${encodeURIComponent(channelId)}${
      qs ? `?${qs}` : ''
    }`,
    { noStore: true }
  );
}

export async function applyOptimalPostingTime(
  channelId: string,
  days = 30
): Promise<{
  ok: boolean;
  previous: { days_of_week: number[]; hour: number; minute: number };
  applied: { days_of_week: number[]; hour: number; minute: number };
  recommendation: OptimalPostingRecommendation;
}> {
  return call(
    `/api/optimal-posting-time/${encodeURIComponent(channelId)}/apply`,
    {
      method: 'POST',
      body: JSON.stringify({ days }),
      noStore: true,
    }
  );
}

// ── Thumbnail AB Tests ──
export type ThumbnailVariant = {
  index: number;
  path: string;
  feedback: string;
  generated_at: number;
  error?: string;
};

export type ThumbnailTestHistoryEntry = {
  variant_index: number;
  ctr_at_check: number | null;
  channel_avg_at_check: number | null;
  switched_at: number;
  switched_to: number;
  youtube_update_ok: boolean;
  youtube_update_error?: string | null;
};

export type ThumbnailTest = {
  video_id: string;
  channel_id: string;
  video_title: string;
  variants: ThumbnailVariant[];
  current_variant_index: number;
  channel_avg_ctr: number;
  threshold_ratio: number;
  last_check_ctr: number | null;
  last_checked_at: number | null;
  last_switched_at: number | null;
  status: 'monitoring' | 'exhausted' | 'stopped';
  history: ThumbnailTestHistoryEntry[];
  created_at: number;
  updated_at: number;
  next_check_at: number;
};

export type ThumbnailTestsResponse = {
  channel_id: string;
  count: number;
  items: ThumbnailTest[];
  summary: {
    channel_id: string;
    total_tests: number;
    by_status: Record<string, number>;
    switched_tests: number;
    channel_avg_ctr: number;
  };
};

export async function listThumbnailTests(
  channelId: string,
  limit = 100
): Promise<ThumbnailTestsResponse> {
  return call<ThumbnailTestsResponse>(
    `/api/thumbnail-tests/${encodeURIComponent(channelId)}?limit=${limit}`,
    { noStore: true }
  );
}

export async function checkThumbnailTest(
  channelId: string,
  videoId: string
): Promise<Record<string, unknown>> {
  return call(
    `/api/thumbnail-tests/${encodeURIComponent(channelId)}/${encodeURIComponent(
      videoId
    )}/check`,
    { method: 'POST', noStore: true }
  );
}

export async function switchThumbnailTest(
  channelId: string,
  videoId: string
): Promise<Record<string, unknown>> {
  return call(
    `/api/thumbnail-tests/${encodeURIComponent(channelId)}/${encodeURIComponent(
      videoId
    )}/switch`,
    { method: 'POST', noStore: true }
  );
}

export async function stopThumbnailTest(
  channelId: string,
  videoId: string
): Promise<Record<string, unknown>> {
  return call(
    `/api/thumbnail-tests/${encodeURIComponent(channelId)}/${encodeURIComponent(
      videoId
    )}/stop`,
    { method: 'POST', noStore: true }
  );
}

export async function checkAllThumbnailTests(
  channelId: string
): Promise<{ checked: number; results: Array<Record<string, unknown>> }> {
  return call(
    `/api/thumbnail-tests/${encodeURIComponent(channelId)}/check-all`,
    { method: 'POST', noStore: true }
  );
}

// ── Trend Scanner (Phase E-1) ──
export type TrendDetection = {
  id: string;
  channel_id: string;
  keyword: string;
  source: string;
  trend_score: number;
  relevance_score: number;
  combined_score: number;
  suggested_title: string | null;
  suggested_angle: string | null;
  rationale: string | null;
  raw: Record<string, unknown>;
  detected_at: number;
  queued_at: number | null;
  auto_queued: boolean;
  queue_theme_id: string | null;
  status: 'detected' | 'queued' | 'dismissed';
};

export type TrendScanHistory = {
  id: number;
  channel_id: string;
  started_at: number;
  finished_at: number | null;
  sources: string[];
  detected: number;
  auto_queued: number;
  error: string | null;
};

export type TrendDetectionsResponse = {
  channel_id: string;
  count: number;
  items: TrendDetection[];
  history: TrendScanHistory[];
  by_source: Record<string, number>;
  auto_queue_threshold: number;
};

export async function listTrendDetections(
  channelId: string,
  opts: { status?: string; limit?: number } = {}
): Promise<TrendDetectionsResponse> {
  const q = new URLSearchParams();
  if (opts.status) q.set('status', opts.status);
  if (opts.limit) q.set('limit', String(opts.limit));
  const qs = q.toString();
  return call<TrendDetectionsResponse>(
    `/api/trend-scanner/${encodeURIComponent(channelId)}${qs ? `?${qs}` : ''}`,
    { noStore: true }
  );
}

export async function runTrendScan(
  channelId: string,
  opts: { auto_queue?: boolean; sources?: string[] } = {}
): Promise<Record<string, unknown>> {
  return call(`/api/trend-scanner/${encodeURIComponent(channelId)}/scan`, {
    method: 'POST',
    body: JSON.stringify(opts),
    noStore: true,
  });
}

export async function queueTrendDetection(
  channelId: string,
  detectionId: string
): Promise<{ ok: boolean; theme_id?: string; title?: string; error?: string }> {
  return call(
    `/api/trend-scanner/${encodeURIComponent(channelId)}/queue/${encodeURIComponent(detectionId)}`,
    { method: 'POST', noStore: true }
  );
}

export async function dismissTrendDetection(
  channelId: string,
  detectionId: string
): Promise<{ ok: boolean; error?: string }> {
  return call(
    `/api/trend-scanner/${encodeURIComponent(channelId)}/dismiss/${encodeURIComponent(detectionId)}`,
    { method: 'POST', noStore: true }
  );
}

// ── Series Engine (Phase E-2) ──
export type SeriesSuggestion = {
  id: string;
  channel_id: string;
  original_video_id: string;
  original_title: string | null;
  original_views: number;
  channel_avg_views: number;
  viral_ratio: number;
  series_type: string | null;
  suggested_title: string;
  suggested_angle: string | null;
  rationale: string | null;
  created_at: number;
  decided_at: number | null;
  status: 'pending' | 'approved' | 'rejected';
  queue_theme_id: string | null;
  queued_video_id: string | null;
};

export type ViralVideoSummary = {
  video_id: string;
  title: string | null;
  views: number;
  channel_avg: number;
  viral_ratio: number;
  published_at: string | null;
};

export type SeriesGroup = {
  original_video_id: string;
  original_title: string | null;
  original_views: number;
  viral_ratio: number;
  suggestions: SeriesSuggestion[];
};

export type SeriesSuggestionsResponse = {
  channel_id: string;
  count: number;
  items: SeriesSuggestion[];
  grouped: SeriesGroup[];
  viral_videos: ViralVideoSummary[];
  channel_avg_views: number | null;
  summary: {
    channel_id: string;
    channel_avg_views: number;
    total_suggestions: number;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
    approved_with_video: number;
  };
};

export async function listSeriesSuggestions(
  channelId: string,
  opts: { status?: string; limit?: number } = {}
): Promise<SeriesSuggestionsResponse> {
  const q = new URLSearchParams();
  if (opts.status) q.set('status', opts.status);
  if (opts.limit) q.set('limit', String(opts.limit));
  const qs = q.toString();
  return call<SeriesSuggestionsResponse>(
    `/api/series/${encodeURIComponent(channelId)}${qs ? `?${qs}` : ''}`,
    { noStore: true }
  );
}

export async function runSeriesDetection(
  channelId: string,
  opts: { threshold?: number; max_viral?: number } = {}
): Promise<Record<string, unknown>> {
  return call(`/api/series/${encodeURIComponent(channelId)}/detect`, {
    method: 'POST',
    body: JSON.stringify(opts),
    noStore: true,
  });
}

export async function approveSeriesSuggestion(
  channelId: string,
  suggestionId: string
): Promise<{ ok: boolean; theme_id?: string; title?: string; error?: string }> {
  return call(
    `/api/series/${encodeURIComponent(channelId)}/approve/${encodeURIComponent(suggestionId)}`,
    { method: 'POST', noStore: true }
  );
}

export async function rejectSeriesSuggestion(
  channelId: string,
  suggestionId: string
): Promise<{ ok: boolean; error?: string }> {
  return call(
    `/api/series/${encodeURIComponent(channelId)}/reject/${encodeURIComponent(suggestionId)}`,
    { method: 'POST', noStore: true }
  );
}

// ── Competitor Analysis (Phase F-1) ──
export type CompetitorAnalysis = {
  id: number;
  channel_id: string;
  competitor_id: string;
  competitor_title: string | null;
  subscriber_count: number | null;
  video_count: number | null;
  view_count: number | null;
  analysis_date: string;
  insights_json: Record<string, unknown>;
  top_videos_json: Array<{
    video_id: string;
    title: string;
    published_at: string | null;
    thumbnail_url: string | null;
    duration: string | null;
    views: number;
    likes: number;
    comments: number;
    tags: string[];
  }>;
  posting_frequency_per_week: number | null;
  avg_views: number | null;
  fetched_at: number;
};

export type CompetitorCandidate = {
  id: string; // `${channel_id}:${competitor_id}`
  channel_id: string;
  competitor_id: string;
  competitor_title: string | null;
  competitor_description: string | null;
  thumbnail_url: string | null;
  subscriber_count: number | null;
  video_count: number | null;
  view_count: number | null;
  posting_frequency_per_week: number | null;
  relevance_score: number;
  rationale: string | null;
  matched_keywords: string[];
  sample_titles: string[];
  status: 'pending' | 'approved' | 'dismissed';
  discovered_at: number;
  decided_at: number | null;
};

export type CompetitorOverview = {
  channel_id: string;
  competitor_ids: string[];
  latest_analyses: CompetitorAnalysis[];
  history: CompetitorAnalysis[];
  count: number;
  pending_candidates?: CompetitorCandidate[];
  pending_candidate_count?: number;
};

export async function getCompetitorOverview(
  channelId: string,
  limit = 50
): Promise<CompetitorOverview> {
  return call<CompetitorOverview>(
    `/api/competitors/${encodeURIComponent(channelId)}?limit=${limit}`,
    { noStore: true }
  );
}

export async function runCompetitorScan(
  channelId: string,
  opts: { max_videos_per_competitor?: number; max_competitors?: number } = {}
): Promise<Record<string, unknown>> {
  return call(`/api/competitors/${encodeURIComponent(channelId)}/scan`, {
    method: 'POST',
    body: JSON.stringify(opts),
    noStore: true,
  });
}

export async function addCompetitor(
  channelId: string,
  competitorChannelId: string
): Promise<{ ok: boolean; competitor_id?: string; note?: string; error?: string }> {
  return call(`/api/competitors/${encodeURIComponent(channelId)}/add`, {
    method: 'POST',
    body: JSON.stringify({ competitor_channel_id: competitorChannelId }),
    noStore: true,
  });
}

export async function removeCompetitor(
  channelId: string,
  competitorId: string
): Promise<{ ok: boolean; error?: string }> {
  return call(
    `/api/competitors/${encodeURIComponent(channelId)}/remove/${encodeURIComponent(competitorId)}`,
    { method: 'DELETE', noStore: true }
  );
}

export async function runCompetitorDiscovery(
  channelId: string,
  opts: {
    max_candidates?: number;
    min_subscribers?: number;
    relevance_threshold?: number;
  } = {}
): Promise<{
  ok: boolean;
  matched_keywords?: string[];
  candidates?: CompetitorCandidate[];
  count?: number;
  error?: string;
  note?: string;
}> {
  return call(`/api/competitors/${encodeURIComponent(channelId)}/discover`, {
    method: 'POST',
    body: JSON.stringify(opts),
    noStore: true,
  });
}

export async function listCompetitorCandidates(
  channelId: string,
  status: 'pending' | 'approved' | 'dismissed' | 'all' = 'pending',
  limit = 50
): Promise<{
  channel_id: string;
  status_filter: string | null;
  count: number;
  items: CompetitorCandidate[];
}> {
  return call(
    `/api/competitors/${encodeURIComponent(channelId)}/candidates?status=${status}&limit=${limit}`,
    { noStore: true }
  );
}

export async function approveCompetitorCandidate(
  channelId: string,
  competitorId: string
): Promise<{ ok: boolean; competitor_id?: string; note?: string; error?: string }> {
  return call(
    `/api/competitors/${encodeURIComponent(channelId)}/candidates/${encodeURIComponent(competitorId)}/approve`,
    { method: 'POST', noStore: true }
  );
}

export async function dismissCompetitorCandidate(
  channelId: string,
  competitorId: string
): Promise<{ ok: boolean; error?: string }> {
  return call(
    `/api/competitors/${encodeURIComponent(channelId)}/candidates/${encodeURIComponent(competitorId)}/dismiss`,
    { method: 'POST', noStore: true }
  );
}

// ── Comment Demand (Phase F-2) ──
export type CommentDemand = {
  id: string;
  channel_id: string;
  video_id: string | null;
  comment_ids: string[];
  demand_text: string;
  demand_type: 'request' | 'question';
  frequency: number;
  total_likes: number;
  relevance_score: number;
  score: number;
  suggested_title: string | null;
  suggested_angle: string | null;
  rationale: string | null;
  status: 'pending' | 'queued' | 'auto_queued' | 'dismissed';
  queue_theme_id: string | null;
  auto_queued: boolean;
  created_at: number;
  updated_at: number;
};

export type CommentDemandsResponse = {
  channel_id: string;
  count: number;
  items: CommentDemand[];
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  auto_queue_threshold: number;
};

export async function listCommentDemands(
  channelId: string,
  opts: { status?: string; demand_type?: string; limit?: number } = {}
): Promise<CommentDemandsResponse> {
  const q = new URLSearchParams();
  if (opts.status) q.set('status', opts.status);
  if (opts.demand_type) q.set('demand_type', opts.demand_type);
  if (opts.limit) q.set('limit', String(opts.limit));
  const qs = q.toString();
  return call<CommentDemandsResponse>(
    `/api/comment-demands/${encodeURIComponent(channelId)}${qs ? `?${qs}` : ''}`,
    { noStore: true }
  );
}

export async function runCommentDemandScan(
  channelId: string,
  opts: { since_days?: number; auto_queue?: boolean } = {}
): Promise<Record<string, unknown>> {
  return call(`/api/comment-demands/${encodeURIComponent(channelId)}/scan`, {
    method: 'POST',
    body: JSON.stringify(opts),
    noStore: true,
  });
}

export async function queueCommentDemand(
  channelId: string,
  demandId: string
): Promise<{ ok: boolean; theme_id?: string; title?: string; error?: string }> {
  return call(
    `/api/comment-demands/${encodeURIComponent(channelId)}/queue/${encodeURIComponent(demandId)}`,
    { method: 'POST', noStore: true }
  );
}

export async function dismissCommentDemand(
  channelId: string,
  demandId: string
): Promise<{ ok: boolean; error?: string }> {
  return call(
    `/api/comment-demands/${encodeURIComponent(channelId)}/dismiss/${encodeURIComponent(demandId)}`,
    { method: 'POST', noStore: true }
  );
}
