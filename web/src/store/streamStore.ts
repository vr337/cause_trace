/** 流式域：WS 消息队列、阶段进度、工具调用与假设卡片。 */

import { create } from "zustand";

import type { HypothesisCard, Stage } from "../api/types";
import type { StageProgress, ToolRun, WsMessage } from "../ws/protocol";
import { toHypothesisCard } from "../ws/protocol";

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
}

interface StreamState {
  messages: AssistantMessage[];
  currentStep: StageProgress | null;
  toolRuns: ToolRun[];
  hypotheses: HypothesisCard[];
  connection: string;
  appendMessage: (message: Omit<AssistantMessage, "id" | "createdAt">) => void;
  ingest: (message: WsMessage) => void;
  setConnection: (state: string) => void;
  reset: () => void;
}

let sequence = 0;
const nextId = () => `msg-${Date.now()}-${(sequence += 1)}`;

export const useStreamStore = create<StreamState>((set, get) => ({
  messages: [],
  currentStep: null,
  toolRuns: [],
  hypotheses: [],
  connection: "idle",

  appendMessage: (message) =>
    set({
      messages: [
        ...get().messages,
        { ...message, id: nextId(), createdAt: new Date().toISOString() },
      ],
    }),

  setConnection: (connection) => set({ connection }),

  ingest: (message) => {
    switch (message.event_type) {
      case "stage_progress":
        set({
          currentStep: {
            stage: message.stage as Stage,
            status: (message.payload.status as StageProgress["status"]) ?? "running",
            message: (message.payload.message as string) ?? "",
          },
        });
        break;
      case "tool_run":
        set({
          toolRuns: [
            ...get().toolRuns,
            {
              tool_name: (message.payload.tool_name as string) ?? "tool",
              status: (message.payload.status as ToolRun["status"]) ?? "running",
              duration_ms: (message.payload.duration_ms as number) ?? 0,
            },
          ],
        });
        break;
      case "hypothesis_card": {
        const card = toHypothesisCard(message.payload);
        if (!card) return;
        const existing = get().hypotheses.filter((item) => item.content !== card.content);
        set({ hypotheses: [...existing, card] });
        break;
      }
      case "error":
        set({
          currentStep: {
            stage: message.stage as Stage,
            status: "failed",
            message: (message.payload.message as string) ?? "分析失败",
          },
        });
        break;
      default:
        break;
    }
  },

  reset: () =>
    set({ messages: [], currentStep: null, toolRuns: [], hypotheses: [], connection: "idle" }),
}));
