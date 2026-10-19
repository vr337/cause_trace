/** 仿真域：因子参数、情景对比与敏感度曲线。拖动滑块立即写入本地，请求防抖在组件层。 */

import { create } from "zustand";

import type { SimulationResult } from "../api/types";

interface WhatIfState {
  factors: Record<string, number>;
  scenarios: SimulationResult["scenarios"];
  sensitivityCurve: SimulationResult["sensitivity_curve"];
  pending: boolean;
  setFactor: (name: string, value: number) => void;
  applyResult: (result: SimulationResult) => void;
  setPending: (pending: boolean) => void;
  reset: () => void;
}

export const useWhatIfStore = create<WhatIfState>((set) => ({
  factors: {},
  scenarios: [],
  sensitivityCurve: [],
  pending: false,

  setFactor: (name, value) => set((state) => ({ factors: { ...state.factors, [name]: value } })),
  applyResult: (result) =>
    set({ scenarios: result.scenarios, sensitivityCurve: result.sensitivity_curve, pending: false }),
  setPending: (pending) => set({ pending }),
  reset: () => set({ factors: {}, scenarios: [], sensitivityCurve: [], pending: false }),
}));
