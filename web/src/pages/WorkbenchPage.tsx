import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { HypothesisCard } from "../api/types";
import { DupontTree } from "../components/charts/DupontTree";
import { WaterfallChart } from "../components/charts/WaterfallChart";
import { HypothesisBoard } from "../components/HypothesisBoard";
import { PivotTable, type PivotRow } from "../components/PivotTable";
import { WhatIfPanel } from "../components/WhatIfPanel";
import { useDashboardStore } from "../store/dashboardStore";
import { useSessionStore } from "../store/sessionStore";
import { useStreamStore } from "../store/streamStore";

const STAGE_LABELS: Record<string, string> = {
  intent_parse: "意图解析",
  decompose: "指标拆解",
  drilldown: "维度下钻",
  hypothesis_gen: "假设生成",
  sandbox_verify: "沙箱验证",
  causal_link: "事件关联",
  simulation: "What-If 推演",
  report: "报告组装",
};

/** 三栏归因工作台（PRD 7.2 / Spec 12.2）：280px / 1fr / 480px。 */
export function WorkbenchPage() {
  const { metricId, domainId, baseline, stage, setSession } = useSessionStore();
  const { messages, hypotheses, appendMessage, reset: resetStream } = useStreamStore();
  const { decomposition, shapley, conclusions, causalLinks, setDecomposition, setShapley } =
    useDashboardStore();

  const [query, setQuery] = useState("为什么上周 GMV 下滑？");
  const [collapsed, setCollapsed] = useState(() =>
    localStorage.getItem("ct-left-collapsed") === "1",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem("ct-left-collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  const runAnalysis = async () => {
    if (!metricId || !domainId) {
      setError("请先在大盘选择一个异常指标");
      return;
    }
    setBusy(true);
    setError(null);
    resetStream();
    appendMessage({ role: "user", content: query });

    try {
      const created = await api.createSession({
        domain_id: domainId,
        metric_id: metricId,
        baseline,
        query,
        window: { start: "2026-08-12", end: "2026-08-18" },
      });
      setSession({
        sessionId: created.session_id,
        domainId,
        metricId,
        baseline,
        windowStart: created.intent.time_range[0],
        windowEnd: created.intent.time_range[1],
      });
      appendMessage({
        role: "assistant",
        content: `已解析意图：指标 ${created.intent.metric}，基期 ${created.intent.baseline}。分析计划共 ${created.plan.steps.length} 个阶段。`,
      });

      // 用当前会话的演示数据驱动看板；真实数据接入由 WS 流式下发覆盖
      const demo = await api.decompose("lmdi", [
        { name: "访客数", base: 10000, current: 9000 },
        { name: "转化率", base: 0.02, current: 0.018 },
        { name: "客单价", base: 100, current: 105 },
      ]);
      setDecomposition(demo);

      const slices = await api.shapley([
        { name: "抖音", weight_base: 0.45, weight_current: 0.55, rate_base: 0.024, rate_current: 0.019 },
        { name: "微信", weight_base: 0.25, weight_current: 0.22, rate_base: 0.026, rate_current: 0.023 },
        { name: "搜索", weight_base: 0.30, weight_current: 0.23, rate_base: 0.018, rate_current: 0.016 },
      ]);
      setShapley(slices);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "分析失败");
    } finally {
      setBusy(false);
    }
  };

  const pivotRows: PivotRow[] =
    shapley?.slices.map((slice) => ({
      id: slice.slice,
      dimension: slice.slice,
      contribution: slice.contribution,
      contributionRate: slice.contribution_rate,
      delta: slice.delta,
    })) ?? [];

  const hypothesesView: HypothesisCard[] = hypotheses;

  return (
    <div
      className="grid h-full gap-3 p-3"
      style={{ gridTemplateColumns: collapsed ? "0px 1fr 480px" : "280px 1fr 480px" }}
    >
      {/* 左栏：会话与指标导航 */}
      {!collapsed && (
        <aside className="card flex flex-col gap-4 overflow-auto p-3">
          <button className="btn-primary w-full" onClick={() => setCollapsed(true)}>
            + 新建分析
          </button>

          <section>
            <h2 className="mb-2 text-xs font-medium text-ink-500">会话列表</h2>
            <ul className="space-y-1 text-sm">
              <li className="rounded bg-ink-100 px-2 py-1.5 font-medium">GMV 下滑归因</li>
              <li className="rounded px-2 py-1.5 text-ink-600 hover:bg-ink-50">利润率异动</li>
            </ul>
          </section>

          <section>
            <h2 className="mb-2 text-xs font-medium text-ink-500">当前指标拆解树</h2>
            <DupontTree
              root={{
                name: "GMV",
                value: "1,024万",
                children: [
                  { name: "访客数", value: "9,000" },
                  { name: "转化率", value: "1.80%" },
                  { name: "客单价", value: "105" },
                ],
              }}
            />
          </section>

          <p className="mt-auto rounded bg-ink-50 px-2 py-1.5 text-xs text-ink-500">
            各因子贡献之和与总变动偏差 ≤ 1e-9
          </p>
        </aside>
      )}

      {collapsed && (
        <button
          className="flex h-full w-6 items-center justify-center rounded bg-ink-200 text-xs text-ink-600"
          onClick={() => setCollapsed(false)}
          aria-label="展开左栏"
        >
          ›
        </button>
      )}

      {/* 中栏：对话与探索 */}
      <section className="card flex min-h-0 flex-col">
        <header className="flex items-center justify-between border-b border-ink-200 px-4 py-2.5">
          <span className="card-title">归因分析</span>
          <span className="text-xs text-ink-400">当前阶段：{STAGE_LABELS[stage] ?? stage}</span>
        </header>

        <div className="flex-1 space-y-3 overflow-auto p-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={
                message.role === "user"
                  ? "ml-auto max-w-[80%] rounded-lg bg-ink-900 px-3 py-2 text-sm text-white"
                  : "max-w-[85%] rounded-lg bg-ink-50 px-3 py-2 text-sm text-ink-800"
              }
            >
              {message.content}
            </div>
          ))}

          {hypothesesView.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-medium text-ink-500">假设看板</h3>
              <HypothesisBoard hypotheses={hypothesesView} />
            </div>
          )}

          {error && <p className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">{error}</p>}
        </div>

        <div className="border-t border-ink-200 p-3">
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && !busy && runAnalysis()}
              className="flex-1 rounded-md border border-ink-200 px-3 py-2 text-sm outline-none focus:border-ink-400"
              placeholder="描述你的归因需求…"
            />
            <button className="btn-primary" disabled={busy} onClick={runAnalysis}>
              {busy ? "分析中…" : "发送"}
            </button>
          </div>
        </div>
      </section>

      {/* 右栏：动态归因看板 */}
      <aside className="flex min-h-0 flex-col gap-3 overflow-auto">
        <div className="card p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="card-title">归因结论</span>
            <span className="chip bg-ink-100 text-ink-500">实时</span>
          </div>
          <ul className="space-y-1.5 text-sm">
            <li className="flex justify-between">
              <span className="text-ink-600">主因</span>
              <span className="font-medium">{conclusions?.primary ?? "渠道结构恶化 68%"}</span>
            </li>
            <li className="flex justify-between">
              <span className="text-ink-600">次因</span>
              <span className="font-medium">{conclusions?.secondary ?? "转化率下降 22%"}</span>
            </li>
            <li className="flex justify-between">
              <span className="text-ink-600">外因</span>
              <span className="font-medium">{conclusions?.external ?? "竞品大促（事件 #12）"}</span>
            </li>
          </ul>
        </div>

        <div className="card p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="card-title">因子贡献瀑布图</span>
            {decomposition && (
              <span className="text-xs text-ink-400">
                残差 {decomposition.residual.toExponential(1)}
              </span>
            )}
          </div>
          {decomposition ? (
            <WaterfallChart
              contributions={decomposition.contributions}
              totalDelta={decomposition.total_delta}
            />
          ) : (
            <p className="py-8 text-center text-xs text-ink-400">发起分析后生成</p>
          )}
        </div>

        <div className="card p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="card-title">下钻透视表</span>
            <span className="text-xs text-ink-400">按渠道</span>
          </div>
          {pivotRows.length > 0 ? (
            <PivotTable rows={pivotRows} />
          ) : (
            <p className="py-4 text-center text-xs text-ink-400">暂无下钻数据</p>
          )}
        </div>

        <div className="card p-3">
          <span className="card-title">What-If 仿真</span>
          <div className="mt-2">
            <WhatIfPanel
              sessionId={useSessionStore.getState().sessionId}
              baselineValue={decomposition?.total_current ?? 10_240_000}
              elasticities={{ "渠道预算·抖音": 1.2, "价格·品类A": -0.8 }}
            />
          </div>
        </div>

        <div className="card p-3">
          <span className="card-title">因果证据链</span>
          <ul className="mt-2 space-y-1 text-xs">
            {causalLinks.length === 0 && <li className="text-ink-400">暂无外生事件</li>}
            {causalLinks.map((link) => (
              <li key={link.name} className="flex justify-between gap-2">
                <span className="text-ink-600">{link.name}</span>
                <span className={link.role === "external" ? "text-amber-600" : "text-ink-900"}>
                  {(link.contribution * 100).toFixed(1)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
