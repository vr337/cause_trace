/** 与后端接口一一对应的类型定义，字段名保持 snake_case 避免两侧翻译。 */

export type Baseline = "dod" | "yoy" | "target";

export type Stage =
  | "intent_parse"
  | "decompose"
  | "drilldown"
  | "hypothesis_gen"
  | "sandbox_verify"
  | "causal_link"
  | "simulation"
  | "report";

export interface PlanStep {
  stage: Stage;
  description: string;
  status: "pending" | "running" | "done";
}

export interface SessionCreateRequest {
  domain_id: number;
  metric_id: number;
  baseline: Baseline;
  window?: { start?: string; end?: string };
  query?: string;
  from_dashboard?: boolean;
}

export interface SessionCreateResponse {
  session_id: number;
  intent: { metric: string; time_range: [string, string]; baseline: Baseline };
  ws_url: string;
  plan: { current_stage: Stage; current_index: number; steps: PlanStep[] };
}

export interface HypothesisCard {
  content: string;
  origin: "llm" | "rule";
  status: "pending" | "verified" | "excluded" | "failed";
  confidence: number | null;
  exclude_reason: string | null;
}

export interface SessionSnapshot {
  session_id: number;
  status: "running" | "done" | "failed";
  current_stage: Stage | null;
  baseline: Baseline;
  window: { start: string; end: string };
  hypotheses: Array<HypothesisCard & { id: number }>;
}

export interface Contribution {
  factor: string;
  base: number;
  current: number;
  delta: number;
  contribution: number;
  contribution_rate: number;
  direction: "up" | "down" | "flat";
}

export interface DecompositionResult {
  method: "diff" | "lmdi" | "dupont" | "shapley";
  total_base: number;
  total_current: number;
  total_delta: number;
  residual: number;
  conserved: boolean;
  contributions: Contribution[];
}

export interface SliceContribution {
  slice: string;
  mix_contribution: number;
  rate_contribution: number;
  contribution: number;
  contribution_rate: number;
  delta: number;
}

export interface ShapleyResult {
  method: string;
  total_base: number;
  total_current: number;
  total_delta: number;
  residual: number;
  conserved: boolean;
  slices: SliceContribution[];
}

export interface SimulationResult {
  session_id?: number;
  baseline: { metric_value: number; scenario_name: string };
  scenarios: Array<{
    scenario_name: string;
    metric_value: number;
    delta: number;
    delta_rate: number;
    confidence_interval: [number, number];
  }>;
  sensitivity_curve: Array<{ factor: string; ratios: number[]; metric_values: number[] }>;
}

export interface EventItem {
  name: string;
  event_type: "promo" | "operation" | "external" | "fault";
  window_start: string;
  window_end: string;
  categories: string[];
  channels: string[];
  metrics: string[];
}

export interface MetricItem {
  id: number;
  code: string;
  name: string;
  type: "atomic" | "derived" | "composite";
  algebra: "additive" | "multiplicative";
}

export interface DomainItem {
  id: number;
  name: string;
  biz_line: string;
}
