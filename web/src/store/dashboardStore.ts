/** 看板域：瀑布图、透视表、结论卡片与因果证据链。 */

import { create } from "zustand";

import type { Conclusion } from "../ws/protocol";
import type { DecompositionResult, SessionSnapshot, ShapleyResult } from "../api/types";

interface CausalLink {
  role: "internal" | "external";
  name: string;
  contribution: number;
  summary: string;
}

interface DashboardState {
  snapshot: SessionSnapshot | null;
  decomposition: DecompositionResult | null;
  shapley: ShapleyResult | null;
  conclusions: Conclusion | null;
  causalLinks: CausalLink[];
  conservationFailed: boolean;
  setSnapshot: (snapshot: SessionSnapshot) => void;
  setDecomposition: (result: DecompositionResult) => void;
  setShapley: (result: ShapleyResult) => void;
  setConclusions: (conclusion: Conclusion | null) => void;
  setCausalLinks: (links: CausalLink[]) => void;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  snapshot: null,
  decomposition: null,
  shapley: null,
  conclusions: null,
  causalLinks: [],
  conservationFailed: false,

  setSnapshot: (snapshot) => set({ snapshot }),
  // 守恒失败时禁止出图：后端已拦截，前端再兜一层，避免脏数据进看板
  setDecomposition: (result) =>
    set({ decomposition: result, conservationFailed: !result.conserved }),
  setShapley: (result) => set({ shapley: result, conservationFailed: !result.conserved }),
  setConclusions: (conclusions) => set({ conclusions }),
  setCausalLinks: (causalLinks) => set({ causalLinks }),
  reset: () =>
    set({
      snapshot: null,
      decomposition: null,
      shapley: null,
      conclusions: null,
      causalLinks: [],
      conservationFailed: false,
    }),
}));
