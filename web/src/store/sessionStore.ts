/** 会话域：当前指标、时间范围、阶段与断点恢复（Spec 12.1）。 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Baseline, Stage } from "../api/types";

interface SessionState {
  sessionId: number | null;
  domainId: number | null;
  metricId: number | null;
  baseline: Baseline;
  windowStart: string | null;
  windowEnd: string | null;
  stage: Stage;
  history: Array<{ sessionId: number; title: string; createdAt: string }>;
  setSession: (payload: {
    sessionId: number;
    domainId: number;
    metricId: number;
    baseline: Baseline;
    windowStart: string;
    windowEnd: string;
  }) => void;
  setStage: (stage: Stage) => void;
  reset: () => void;
}

const initial = {
  sessionId: null,
  domainId: null,
  metricId: null,
  baseline: "dod" as Baseline,
  windowStart: null,
  windowEnd: null,
  stage: "intent_parse" as Stage,
  history: [],
};

export const useSessionStore = create<SessionState>()(
  persist(
    (set, get) => ({
      ...initial,
      setSession: (payload) =>
        set({
          ...payload,
          stage: "intent_parse",
          history: [
            {
              sessionId: payload.sessionId,
              title: `会话 #${payload.sessionId}`,
              createdAt: new Date().toISOString(),
            },
            ...get().history.filter((item) => item.sessionId !== payload.sessionId),
          ].slice(0, 20),
        }),
      setStage: (stage) => set({ stage }),
      reset: () => set(initial),
    }),
    { name: "ct-session" },
  ),
);
