/** Spec 12.3 定义的 WS 消息协议与前端分发规则。 */

import type { HypothesisCard, Stage } from "../api/types";

export type WsEventType =
  | "stage_progress"
  | "hypothesis_card"
  | "tool_run"
  | "evidence"
  | "conclusion"
  | "simulation_result"
  | "report_ready"
  | "error";

export interface WsMessage {
  event_type: WsEventType;
  stage: Stage;
  payload: Record<string, unknown>;
  trace_id: string;
  ts: string;
}

export interface StageProgress {
  stage: Stage;
  status: "running" | "done" | "failed";
  message: string;
}

export interface ToolRun {
  tool_name: string;
  status: "running" | "done" | "failed";
  duration_ms: number;
}

export interface Conclusion {
  primary: string;
  secondary: string;
  external: string;
}

const STAGE_ORDER: Stage[] = [
  "intent_parse",
  "decompose",
  "drilldown",
  "hypothesis_gen",
  "sandbox_verify",
  "causal_link",
  "simulation",
  "report",
];

export function isWsMessage(value: unknown): value is WsMessage {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<WsMessage>;
  return typeof candidate.event_type === "string" && typeof candidate.stage === "string";
}

export function stageIndex(stage: Stage): number {
  return STAGE_ORDER.indexOf(stage);
}

/** 重连后按服务端快照对齐阶段，避免本地进度超前。 */
export function reconcileStage(local: Stage, remote: Stage): Stage {
  return stageIndex(remote) >= stageIndex(local) ? remote : local;
}

export function toHypothesisCard(payload: Record<string, unknown>): HypothesisCard | null {
  if (typeof payload.content !== "string") return null;
  const status = payload.status;
  return {
    content: payload.content,
    origin: payload.origin === "rule" ? "rule" : "llm",
    status:
      status === "verified" || status === "excluded" || status === "failed" ? status : "pending",
    confidence: typeof payload.confidence === "number" ? payload.confidence : null,
    exclude_reason: typeof payload.exclude_reason === "string" ? payload.exclude_reason : null,
  };
}
