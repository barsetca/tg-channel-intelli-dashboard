/** Типы ответов/запросов FastAPI v1 (синхрон с backend `app/schemas/intelligence.py`). */

export type SearchChannelsRequest = {
  topic: string;
  count?: number | null;
  offset?: number;
  min_subscribers?: number | null;
  max_subscribers?: number | null;
  channel_type?: "new_only" | "all";
  live_channel_mode?: "new" | "saved";
  language?: string | null;
  region_country?: string | null;
  username_query?: string | null;
  selected_channel_ids?: number[];
  last_post_from?: string | null;
  last_post_to?: string | null;
  extra_conditions?: string | null;
  /** Локальный каталог (SQLite) или фоновый поиск в Telegram (Telethon). */
  search_source?: "saved_catalog" | "telegram_live";
  sort_by?: "subscriber_count" | "last_sync_at";
  sort_order?: "asc" | "desc";
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
  planner_output?: Record<string, unknown> | null;
};

/** GET /api/v1/orchestration/jobs/{job_id} */
export type OrchestrationJobStatus = {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed";
  detail: string;
  stage: string | null;
  stage_label: string | null;
  planner_output?: Record<string, unknown> | null;
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
  last_sync_at: string | null;
  primary_topic: string | null;
  topic_search: string | null;
  invite_slug: string | null;
  language_hint: string | null;
  region_country: string | null;
};

export type SearchChannelsResponse = {
  channels: ChannelCard[];
  manual_review: ManualReviewFlags | null;
  normalized_filters: Record<string, unknown>;
  background_job?: BackgroundSearchJob | null;
  has_more?: boolean;
};

export type SearchTopicOptionsResponse = {
  items: string[];
};

export type DataShowcaseItem = {
  audit_run_id: number;
  item_id: number;
  created_at: string | null;
  source: string | null;
  record_json: Record<string, unknown> | unknown[] | null;
};

export type DataShowcaseResponse = {
  limit: number;
  items: DataShowcaseItem[];
};

export type ManualReviewJournalItem = {
  source: "audit" | "search" | "analyze" | "semantic";
  reference_id: number;
  created_at: string | null;
  reason: string;
  status: string | null;
  details: Record<string, unknown> | unknown[] | null;
};

export type ManualReviewJournalResponse = {
  limit: number;
  source_filter: "all" | "audit" | "search" | "analyze" | "semantic";
  items: ManualReviewJournalItem[];
};

export type ChannelDetail = ChannelCard & {
  is_public_accessible: boolean | null;
  sync_status: string | null;
  last_sync_at: string | null;
};

export type ContentStrategyReport = {
  goals: string;
  main_topics: string;
  formats: string;
  cadence: string;
  rubricator: string;
  target_audience: string;
  seo_focus: string;
  engagement: string;
};

export type ToneOfVoiceReport = {
  style: string;
  lexicon: string;
  emotions: string;
  distance: string;
  consistency: string;
  vs_positioning: string;
};

export type ChannelAnalysisReport = {
  channel_description: string;
  topic: string;
  subscribers_count?: number | null;
  channel_url?: string | null;
  channel_created_display?: string | null;
  channel_age_display?: string | null;
  posts_last_30_days?: number | null;
  total_posts_filtered?: number | null;
  report_created_at?: string | null;
  publication_frequency: string;
  avg_post_length: number | null;
  posts_summary: string;
  content_strategy: ContentStrategyReport;
  tone_of_voice: ToneOfVoiceReport;
  strengths: string[];
  risks: string[];
  recommendations: string[];
};

export type AnalyzeChannelResponse = {
  analysis_id: number;
  channel_id: number;
  status: string;
  message: string;
  manual_review?: ManualReviewFlags | null;
  report?: ChannelAnalysisReport | null;
  /** @username, ссылка или запасной идентификатор с бэкенда */
  channel_display_ref?: string | null;
};

export type ChannelAnalysisHistoryItem = {
  id: number;
  channel_id: number | null;
  channel_display_ref?: string | null;
  status: string;
  analyzer_id: string;
  created_at: string;
};

export type SavedChannelAnalysisDetail = {
  analysis_id: number;
  channel_id: number;
  status: string;
  message: string;
  created_at: string;
  report: ChannelAnalysisReport | null;
  channel_display_ref?: string | null;
};

export type AnalyzeChannelByHandleRequest = {
  channel_ref: string;
  user_intent?: string;
  post_limit?: number;
};

export type SummarizeChannelByHandleRequest = {
  channel_ref: string;
  post_limit?: number;
};

export type SummarizePostsRequest = { post_limit: number };
export type SummarizePostsResponse = {
  channel_id: number;
  channel_display_ref?: string | null;
  posts_used: number;
  summary: string;
  per_post_summaries?: string[];
  stored_analysis_hint: string | null;
};

export type SemanticSearchRequest = {
  query: string;
  limit?: number;
  channel_username?: string | null;
};

export type SemanticSearchHit = {
  point_id: string;
  score: number | null;
  channel_id: number | null;
  channel_username: string | null;
  post_id: number | null;
  published_at: string | null;
  source_url: string | null;
  content_type: string | null;
  text_preview: string | null;
};

export type SemanticSearchResponse = {
  needs_review: boolean;
  reason: string | null;
  query: string;
  mode: "post_search" | "channel_search" | "question_answering_over_posts" | null;
  answer: string | null;
  results: Array<{
    channel_username: string | null;
    title: string | null;
    relevance_reason: string | null;
    source_url: string | null;
    score: number | null;
  }>;
  sources: Array<{
    channel_username: string | null;
    message_id: number | null;
    source_url: string | null;
    score: number | null;
    summary: string | null;
  }>;
  hits: SemanticSearchHit[];
  synthesis_placeholder: string | null;
  gate_matched_topics?: string[] | null;
};

export type SimilarChannelItem = {
  channel_id: number;
  channel_username: string | null;
  title: string | null;
  score: number;
  reasons: string[];
  supporting_topics: string[];
  supporting_signals: {
    topic_overlap: number;
    style_similarity: number;
    frequency_similarity: number;
  };
  missing_data: string[];
};

export type SimilarChannelsResponse = {
  needs_review: boolean;
  reason: string | null;
  mode: "similar_channels" | null;
  source_channel: {
    channel_id: number;
    channel_username: string | null;
  } | null;
  results: SimilarChannelItem[];
  quality_notes: string[];
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
  comparison_window_days: number;
  generated_at: string | null;
  insights: Array<{
    channel_id: number;
    username: string | null;
    strengths: string[];
    recommendations: string[];
    evidence_urls: string[];
    metrics: {
      posts_in_window: number;
      posting_frequency_per_week: number;
      avg_views: number;
      median_views: number;
      p75_views: number;
      avg_forwards: number;
      er_forward_rate_mean: number;
      er_forward_rate_p75: number;
      weekly_stability_score: number;
      views_trend_slope: number;
      tone_label: string;
      topic_labels: string[];
      commercial_intent_share: number;
      normalized_score: number;
    };
  }>;
};

export type ChannelDatasetItem = {
  id: number;
  telegram_id: number;
  username: string | null;
  title: string | null;
  description: string | null;
  topic_search: string | null;
  created_at: string | null;
  sync_status: string | null;
  extra_conditions: string | null;
};

export type ChannelDatasetListResponse = {
  total: number;
  limit: number;
  offset: number;
  items: ChannelDatasetItem[];
};

export type ChannelCollectRequest = {
  channel_ref?: string | null;
  topic?: string | null;
  extra_conditions?: string | null;
};

export type ChannelCollectResponse = {
  status: string;
  message: string;
  channel_id: number;
  created_new_channel: boolean;
  background_job_id: string | null;
  needs_review: boolean;
  reason: string | null;
  hints: string[];
};

export type ChannelCreateResult = {
  id: number;
  username: string | null;
  sync_status: string | null;
  already_exists: boolean;
  message: string;
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

export type PublishingOutputMode = "post_with_image" | "infographic_only";

export type PublishableChannel = {
  telegram_channel_id: number;
  username: string | null;
  title: string | null;
};

export type GeneratePostRequest = {
  topic: string;
  char_count: number;
  extra_info?: string | null;
  output_mode: PublishingOutputMode;
  image_size?: string | null;
  image_quality?: string | null;
  custom_image_description?: string | null;
  /** Для AI-поста по умолчанию true — актуальные факты из интернета */
  use_web_search?: boolean;
  /** false — только текст и промпт картинки, без OpenAI Images */
  generate_image?: boolean;
  media_base64?: string | null;
  media_filename?: string | null;
};

export type PublishingImageOptions = {
  model: string;
  family: "gpt-image" | "dall-e-3" | "dall-e-2";
  sizes: string[];
  qualities: string[];
  default_size: string;
  default_quality: string;
};

export type GeneratedPostResponse = {
  topic: string;
  target_char_count: number;
  actual_char_count: number;
  output_mode: string;
  post_text: string | null;
  image_prompt_used: string;
  image_model: string | null;
  image_base64: string | null;
  image_generated: boolean;
};

export type PublishGeneratedRequest = GeneratePostRequest & {
  channel_ref: string;
};

export type PublishResultResponse = {
  telegram_message_id: number;
  peer_ref: string;
  published_at_utc: string;
  had_image: boolean;
  had_text: boolean;
  had_media?: boolean;
};

export type PublishGeneratedResponse = {
  generated: GeneratedPostResponse;
  published: PublishResultResponse;
};

export type PublishManualRequest = {
  channel_ref: string;
  text?: string | null;
  image_base64?: string | null;
  media_base64?: string | null;
  media_filename?: string | null;
};

export type SendChatMessageRequest = {
  chat_ref: string;
  text?: string | null;
  media_base64?: string | null;
  media_filename?: string | null;
};
