/** 后端访问封装。错误统一转成 ApiError，页面只需处理 message。 */

import type {
  DecompositionResult,
  DomainItem,
  EventItem,
  HypothesisCard,
  MetricItem,
  SessionCreateRequest,
  SessionCreateResponse,
  SessionSnapshot,
  ShapleyResult,
  SimulationResult,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  const text = await response.text();
  const body = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : body?.message;
    throw new ApiError(detail ?? `请求失败（${response.status}）`, response.status, body?.code);
  }
  return body as T;
}

export const api = {
  createSession: (payload: SessionCreateRequest) =>
    request<SessionCreateResponse>("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getSession: (sessionId: number) => request<SessionSnapshot>(`/api/v1/sessions/${sessionId}`),

  followup: (sessionId: number, query: string) =>
    request<{ session_id: number; inherited: SessionSnapshot; hypotheses: string[] }>(
      `/api/v1/sessions/${sessionId}/followup`,
      { method: "POST", body: JSON.stringify({ query }) },
    ),

  decompose: (method: DecompositionResult["method"], factors: Array<Record<string, unknown>>) =>
    request<DecompositionResult>("/api/v1/metrics/decomposition", {
      method: "POST",
      body: JSON.stringify({ method, factors }),
    }),

  shapley: (slices: Array<Record<string, unknown>>) =>
    request<ShapleyResult>("/api/v1/metrics/decomposition/shapley", {
      method: "POST",
      body: JSON.stringify({ slices }),
    }),

  evaluateHypotheses: (hypotheses: HypothesisCard[], threshold = 0.6) =>
    request<{ hypotheses: HypothesisCard[]; verified: number; excluded: number }>(
      "/api/v1/hypotheses/evaluate",
      {
        method: "POST",
        body: JSON.stringify({
          threshold,
          hypotheses: hypotheses.map((h) => ({ content: h.content, confidence: h.confidence })),
        }),
      },
    ),

  matchEvents: (payload: {
    window_start: string;
    window_end: string;
    categories?: string[];
    channels?: string[];
    metric_code?: string;
    events: EventItem[];
  }) =>
    request<{
      matched: Array<{ name: string; event_type: string; overlap_days: number; relevance: number; is_causal: boolean }>;
      causal_links: Array<{ role: string; name: string; contribution: number; summary: string }>;
    }>("/api/v1/events/match", { method: "POST", body: JSON.stringify(payload) }),

  simulate: (
    sessionId: number,
    payload: { baseline_value: number; factor_adjustments: Record<string, number>; elasticities: Record<string, number> },
  ) =>
    request<SimulationResult>(`/api/v1/sessions/${sessionId}/simulate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listMetrics: (domainId?: number) =>
    request<{ metrics: MetricItem[] }>(
      `/api/v1/metrics${domainId ? `?domain_id=${domainId}` : ""}`,
    ),

  listDomains: () => request<{ domains: DomainItem[] }>("/api/v1/domains"),
};
