/**
 * HTTP-клиент к FastAPI. База: `NEXT_PUBLIC_API_BASE_URL` (браузер) или `API_URL` (SSR).
 */

import type {
  AnalyzeChannelResponse,
  ChannelAnalysisHistoryItem,
  SavedChannelAnalysisDetail,
  AnalyzeChannelByHandleRequest,
  SummarizeChannelByHandleRequest,
  ChannelDetail,
  CompareChannelsRequest,
  CompareChannelsResponse,
  HealthResponse,
  SearchChannelsRequest,
  SearchChannelsResponse,
  SemanticSearchRequest,
  SemanticSearchResponse,
  SimilarChannelsResponse,
  SummarizePostsRequest,
  SummarizePostsResponse,
  TelegramAuthCodeResponse,
  TelegramAuthStartResponse,
  TelegramIntegrationStatus,
  OrchestrationJobStatus,
} from "@/lib/types/api";

export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  }
  return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = await res.text();
    try {
      const j = JSON.parse(msg) as { detail?: string | unknown };
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = JSON.stringify(j.detail);
    } catch {
      /* текст как есть */
    }
    throw new ApiError(res.status, msg || res.statusText);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return jsonFetch<HealthResponse>("/api/v1/health");
}

export async function fetchTelegramStatus(): Promise<TelegramIntegrationStatus> {
  return jsonFetch<TelegramIntegrationStatus>("/api/v1/telegram/status");
}

export async function telegramAuthStart(phone: string): Promise<TelegramAuthStartResponse> {
  return jsonFetch<TelegramAuthStartResponse>("/api/v1/telegram/auth/start", {
    method: "POST",
    body: JSON.stringify({ phone }),
  });
}

export async function telegramAuthCode(flowId: string, code: string): Promise<TelegramAuthCodeResponse> {
  return jsonFetch<TelegramAuthCodeResponse>("/api/v1/telegram/auth/code", {
    method: "POST",
    body: JSON.stringify({ flow_id: flowId, code }),
  });
}

export async function telegramAuthPassword(flowId: string, password: string): Promise<{
  status: string;
  telegram_session?: string;
  hint?: string;
}> {
  return jsonFetch("/api/v1/telegram/auth/password", {
    method: "POST",
    body: JSON.stringify({ flow_id: flowId, password }),
  });
}

export async function searchChannels(body: SearchChannelsRequest): Promise<SearchChannelsResponse> {
  return jsonFetch<SearchChannelsResponse>("/api/v1/search-channels", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchOrchestrationJobStatus(jobId: string): Promise<OrchestrationJobStatus> {
  return jsonFetch<OrchestrationJobStatus>(`/api/v1/orchestration/jobs/${encodeURIComponent(jobId)}`);
}

export async function cancelOrchestrationJob(jobId: string): Promise<OrchestrationJobStatus> {
  return jsonFetch<OrchestrationJobStatus>(
    `/api/v1/orchestration/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
  );
}

export async function getChannel(channelId: number): Promise<ChannelDetail> {
  return jsonFetch<ChannelDetail>(`/api/v1/channel/${channelId}`);
}

export async function analyzeChannel(
  channelId: number,
  userIntent?: string,
): Promise<AnalyzeChannelResponse> {
  return jsonFetch<AnalyzeChannelResponse>(`/api/v1/analyze/${channelId}`, {
    method: "POST",
    body: JSON.stringify(userIntent ? { user_intent: userIntent } : {}),
  });
}

export async function analyzeChannelByHandle(
  body: AnalyzeChannelByHandleRequest,
): Promise<AnalyzeChannelResponse> {
  return jsonFetch<AnalyzeChannelResponse>("/api/v1/analyze/by-handle", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listChannelAnalyses(channelId?: number): Promise<ChannelAnalysisHistoryItem[]> {
  const q = channelId != null ? `?channel_id=${encodeURIComponent(String(channelId))}` : "";
  return jsonFetch<ChannelAnalysisHistoryItem[]>(`/api/v1/analyses${q}`);
}

export async function getSavedChannelAnalysis(analysisId: number): Promise<SavedChannelAnalysisDetail> {
  return jsonFetch<SavedChannelAnalysisDetail>(`/api/v1/analyses/${analysisId}`);
}

export async function deleteChannelAnalysis(analysisId: number): Promise<void> {
  await jsonFetch<void>(`/api/v1/analyses/${encodeURIComponent(String(analysisId))}`, {
    method: "DELETE",
  });
}

export async function summarizeChannel(
  channelId: number,
  body: SummarizePostsRequest,
): Promise<SummarizePostsResponse> {
  return jsonFetch<SummarizePostsResponse>(`/api/v1/channel/${channelId}/summarize`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function summarizeChannelByHandle(
  body: SummarizeChannelByHandleRequest,
): Promise<SummarizePostsResponse> {
  return jsonFetch<SummarizePostsResponse>("/api/v1/analyze/by-handle/summarize", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function semanticSearch(body: SemanticSearchRequest): Promise<SemanticSearchResponse> {
  return jsonFetch<SemanticSearchResponse>("/api/v1/semantic-search", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getRecommendations(
  channelId: number,
  limit = 5,
): Promise<SimilarChannelsResponse> {
  const q = new URLSearchParams({ limit: String(limit) });
  return jsonFetch<SimilarChannelsResponse>(`/api/v1/recommendations/${channelId}?${q}`);
}

export async function compareChannels(body: CompareChannelsRequest): Promise<CompareChannelsResponse> {
  return jsonFetch<CompareChannelsResponse>("/api/v1/channels/compare", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteChannel(channelId: number): Promise<void> {
  await jsonFetch<void>(`/api/v1/channels/${channelId}`, { method: "DELETE" });
}

export function exportChannelsUrl(format: "json" | "csv"): string {
  const q = new URLSearchParams({ format, limit: "500" });
  return `${getApiBaseUrl()}/api/v1/export?${q}`;
}
