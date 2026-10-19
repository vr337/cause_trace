import { describe, expect, it } from "vitest";

import { isWsMessage, reconcileStage, stageIndex, toHypothesisCard } from "./protocol";

describe("isWsMessage", () => {
  it("接受结构完整的消息", () => {
    expect(
      isWsMessage({
        event_type: "stage_progress",
        stage: "decompose",
        payload: {},
        trace_id: "req-1",
        ts: "2026-10-19T00:00:00Z",
      }),
    ).toBe(true);
  });

  it("拒绝缺字段的对象", () => {
    expect(isWsMessage({ event_type: "stage_progress" })).toBe(false);
    expect(isWsMessage(null)).toBe(false);
    expect(isWsMessage("stage_progress")).toBe(false);
  });
});

describe("reconcileStage", () => {
  it("服务端进度更靠前时以其为准", () => {
    expect(reconcileStage("decompose", "sandbox_verify")).toBe("sandbox_verify");
  });

  it("本地进度更靠前时保留本地，避免回退", () => {
    expect(reconcileStage("simulation", "hypothesis_gen")).toBe("simulation");
  });

  it("阶段顺序与 Spec 12.3 一致", () => {
    expect(stageIndex("intent_parse")).toBe(0);
    expect(stageIndex("report")).toBe(7);
  });
});

describe("toHypothesisCard", () => {
  it("识别已验证与已排除", () => {
    expect(toHypothesisCard({ content: "渠道结构恶化", status: "verified", confidence: 0.87 })).toEqual({
      content: "渠道结构恶化",
      origin: "llm",
      status: "verified",
      confidence: 0.87,
      exclude_reason: null,
    });
    expect(
      toHypothesisCard({ content: "退款率上升", status: "excluded", exclude_reason: "置信度不足" })
        ?.status,
    ).toBe("excluded");
  });

  it("缺少内容时返回 null，避免渲染空卡片", () => {
    expect(toHypothesisCard({ status: "verified" })).toBeNull();
  });

  it("未知状态回落到 pending", () => {
    expect(toHypothesisCard({ content: "x", status: "unknown" })?.status).toBe("pending");
  });
});
