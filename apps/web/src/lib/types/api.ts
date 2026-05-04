/** Типы ответов/запросов FastAPI v1 (синхрон с backend `app/schemas/intelligence.py`). */

export type SearchChannelsRequest = {
  topic: string;
  count?: number;
  min_subscribers?: number | null;
  max_subscribers?: number | null;
  channel_type?: "new_only" | "all";
  language?: string | null;
  region_country?: string | null;
  extra_conditions?: string | null;
  /** Локальный каталог (SQLite) или фоновый поиск в Telegram (Telethon). */
  search_source?: "saved_catalog" | "telegram_live";
};

export type BackgroundSearchJob = {
  job_id: string;
  kind: "telegram_channel_discovery";
  status: "queued" | "running" | "completed" | "failed";
  detail: string;
  /** Заполняется при опросе GET /orchestration/jobs/{job_id} */
  stage?: string | null;
  stage_label?: string | null;
  updated_at?: string | null;
};

/** GET /api/v1/orchestration/jobs/{job_id} */
export type OrchestrationJobStatus = {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed";
  detail: string;
  stage: string | null;
  stage_label: string | null;
  created_at: string;
  updated_at: string;
};

export type ManualReviewFlags = {
  needs_review: boolean;
  reason: string;
  hints: string[];
};

export type ChannelCard = {
  id: number;
  telegram_id: number;
  username: string | null;
  title: string | null;
  description: string | null;
  subscriber_count: number | null;
  posts_per_week_estimate: number | null;
  last_post_at: string | null;
  primary_topic: string | null;
  invite_slug: string | null;
  language_hint: string | null;
  region_country: string | null;
};

export type SearchChannelsResponse = {
  channels: ChannelCard[];
  manual_review: ManualReviewFlags | null;
  normalized_filters: Record<string, unknown>;
  background_job?: BackgroundSearchJob | null;
};

export type ChannelDetail = ChannelCard & {
  is_public_accessible: boolean | null;
  sync_status: string | null;
  last_sync_at: string | null;
};

export type AnalyzeChannelResponse = {
  analysis_id: number;
  channel_id: number;
  status: string;
  message: string;
};

export type SummarizePostsRequest = { post_limit: number };
export type SummarizePostsResponse = {
  channel_id: number;
  posts_used: number;
  summary: string;
  stored_analysis_hint: string | null;
};

export type SemanticSearchRequest = {
  query: string;
  limit?: number;
  content_type?: "post" | "summary" | "profile" | null;
  channel_id?: number | null;
};

export type SemanticSearchHit = {
  point_id: string;
  score: number | null;
  channel_id: number | null;
  post_id: number | null;
  content_type: string | null;
  text_preview: string | null;
};

export type SemanticSearchResponse = {
  query: string;
  hits: SemanticSearchHit[];
  synthesis_placeholder: string | null;
};

export type SimilarChannelItem = {
  channel_id: number;
  score: number | null;
  title: string | null;
  username: string | null;
};

export type SimilarChannelsResponse = {
  seed_channel_id: number;
  similar: SimilarChannelItem[];
};

export type CompareChannelsRequest = { channel_ids: number[] };

export type CompareChannelRow = {
  channel_id: number;
  title: string | null;
  username: string | null;
  subscriber_count: number | null;
  posts_per_week_estimate: number | null;
  primary_topic: string | null;
};

export type CompareChannelsResponse = {
  rows: CompareChannelRow[];
  comparison_notes: string | null;
};

export type HealthResponse = {
  status: string;
  environment: string;
};

/** GET /api/v1/telegram/status */
export type TelegramIntegrationStatus = {
  api_configured: boolean;
  session_ready: boolean;
  interactive_login_enabled: boolean;
  interactive_login_available: boolean;
  startup_failure: string | null;
};

export type TelegramAuthStartResponse = {
  flow_id: string;
  expires_in_seconds: number;
};

export type TelegramAuthCodeResponse =
  | { status: "authorized"; telegram_session: string; hint: string }
  | { status: "needs_password"; flow_id: string };
