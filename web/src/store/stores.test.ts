import { beforeEach, describe, expect, it } from "vitest";

import { useDashboardStore } from "./dashboardStore";
import { useSessionStore } from "./sessionStore";
import { useStreamStore } from "./streamStore";
import { useWhatIfStore } from "./whatIfStore";

const decomposition = {
  method: "lmdi" as const,
  total_base: 100,
  total_current: 120,
  total_delta: 20,
  residual: 0,
  conserved: true,
  contributions: [],
};

describe("dashboardStore", () => {
  beforeEach(() => useDashboardStore.getState().reset());

  it("守恒结果正常时允许出图", () => {
    useDashboardStore.getState().setDecomposition(decomposition);
    expect(useDashboardStore.getState().conservationFailed).toBe(false);
  });

  it("守恒失败时置位拦截标记", () => {
    useDashboardStore
      .getState()
      .setDecomposition({ ...decomposition, conserved: false, residual: 0.5 });
    expect(useDashboardStore.getState().conservationFailed).toBe(true);
  });
});

describe("streamStore", () => {
  beforeEach(() => useStreamStore.getState().reset());

  it("同一假设的后续更新覆盖旧卡片", () => {
    const { ingest } = useStreamStore.getState();
    ingest({
      event_type: "hypothesis_card",
      stage: "hypothesis_gen",
      payload: { content: "渠道结构恶化", status: "pending", confidence: 0.4 },
      trace_id: "t",
      ts: "",
    });
    ingest({
      event_type: "hypothesis_card",
      stage: "sandbox_verify",
      payload: { content: "渠道结构恶化", status: "verified", confidence: 0.87 },
      trace_id: "t",
      ts: "",
    });

    const hypotheses = useStreamStore.getState().hypotheses;
    expect(hypotheses).toHaveLength(1);
    expect(hypotheses[0].status).toBe("verified");
  });

  it("阶段进度与错误都能落到 currentStep", () => {
    const { ingest } = useStreamStore.getState();
    ingest({
      event_type: "stage_progress",
      stage: "decompose",
      payload: { status: "done", message: "拆解完成" },
      trace_id: "t",
      ts: "",
    });
    expect(useStreamStore.getState().currentStep?.stage).toBe("decompose");

    ingest({
      event_type: "error",
      stage: "sandbox_verify",
      payload: { message: "沙箱超时" },
      trace_id: "t",
      ts: "",
    });
    expect(useStreamStore.getState().currentStep?.status).toBe("failed");
  });
});

describe("whatIfStore", () => {
  beforeEach(() => useWhatIfStore.getState().reset());

  it("滑块写入不覆盖其他因子", () => {
    const { setFactor } = useWhatIfStore.getState();
    setFactor("渠道预算", 1.2);
    setFactor("价格", 0.9);
    expect(useWhatIfStore.getState().factors).toEqual({ 渠道预算: 1.2, 价格: 0.9 });
  });

  it("结果回写后清除 pending", () => {
    const { setPending, applyResult } = useWhatIfStore.getState();
    setPending(true);
    applyResult({ baseline: { metric_value: 100, scenario_name: "基准" }, scenarios: [], sensitivity_curve: [] });
    expect(useWhatIfStore.getState().pending).toBe(false);
  });
});

describe("sessionStore", () => {
  beforeEach(() => useSessionStore.getState().reset());

  it("设置会话后阶段重置到意图解析", () => {
    const { setSession, setStage } = useSessionStore.getState();
    setStage("report");
    setSession({
      sessionId: 42,
      domainId: 1,
      metricId: 1,
      baseline: "dod",
      windowStart: "2026-08-12",
      windowEnd: "2026-08-18",
    });

    const state = useSessionStore.getState();
    expect(state.sessionId).toBe(42);
    expect(state.stage).toBe("intent_parse");
    expect(state.history[0].sessionId).toBe(42);
  });

  it("历史记录最多保留 20 条", () => {
    const { setSession } = useSessionStore.getState();
    for (let index = 1; index <= 25; index += 1) {
      setSession({
        sessionId: index,
        domainId: 1,
        metricId: 1,
        baseline: "dod",
        windowStart: "2026-08-12",
        windowEnd: "2026-08-18",
      });
    }
    expect(useSessionStore.getState().history).toHaveLength(20);
  });
});
