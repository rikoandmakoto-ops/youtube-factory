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
  by_channel: Record<string, Metrics>;
  by_model: Record<string, Metrics>;
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
};

export type SampleIllustrationResponse = {
  sample_id: string;
  url: string;
  prompt: string;
  style: IllustrationStyle;
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
