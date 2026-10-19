import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { MetricItem } from "../api/types";
import { DupontTree } from "../components/charts/DupontTree";

const DEMO_TREE = {
  name: "GMV（复合 · 乘法）",
  children: [
    { name: "访客数（原子）" },
    { name: "转化率（派生）" },
    { name: "客单价（派生）" },
  ],
};

const DEMO_METRICS: MetricItem[] = [
  { id: 1, code: "gmv", name: "GMV", type: "composite", algebra: "multiplicative" },
  { id: 2, code: "visitors", name: "访客数", type: "atomic", algebra: "additive" },
  { id: 3, code: "cvr", name: "转化率", type: "derived", algebra: "multiplicative" },
  { id: 4, code: "aov", name: "客单价", type: "derived", algebra: "multiplicative" },
];

/** 指标字典配置（PRD 7.4 / FR-03）：左侧树 + 右侧编辑面板。 */
export function DictionaryPage() {
  const [metrics, setMetrics] = useState<MetricItem[]>(DEMO_METRICS);
  const [selected, setSelected] = useState<MetricItem>(DEMO_METRICS[0]);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api
      .listMetrics()
      .then((result) => {
        if (result.metrics.length > 0) {
          setMetrics(result.metrics);
          setSelected(result.metrics[0]);
        }
      })
      .catch((err: unknown) => {
        // 数据库未就绪时用演示数据撑住页面，不让字典页整体不可用
        if (err instanceof ApiError && err.status === 503) setOffline(true);
      });
  }, []);

  return (
    <div className="grid h-full grid-cols-[320px_1fr] gap-3 p-3">
      <aside className="card flex flex-col overflow-auto p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="card-title">指标树</span>
          <span className="text-xs text-ink-400">可拖拽调整层级</span>
        </div>
        <DupontTree root={DEMO_TREE} />
        <div className="mt-3 flex gap-2">
          <button className="btn-ghost flex-1 text-xs">+ 新增指标</button>
          <button className="btn-ghost flex-1 text-xs">+ 新增维度</button>
        </div>
      </aside>

      <section className="card overflow-auto p-4">
        <h1 className="mb-4 text-base font-semibold">指标编辑</h1>
        {offline && (
          <p className="mb-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">
            后端数据库未就绪，当前展示演示数据
          </p>
        )}
        <form className="grid max-w-xl grid-cols-2 gap-4 text-sm" onSubmit={(e) => e.preventDefault()}>
          <Field label="指标名称">
            <input defaultValue={selected.name} className="input" />
          </Field>
          <Field label="指标编码">
            <input defaultValue={selected.code} className="input font-mono" />
          </Field>
          <Field label="指标类型">
            <select className="input" defaultValue={selected.type}>
              <option value="atomic">原子指标</option>
              <option value="derived">派生指标</option>
              <option value="composite">复合指标</option>
            </select>
          </Field>
          <Field label="代数模型">
            <select className="input" defaultValue={selected.algebra}>
              <option value="multiplicative">乘法模型</option>
              <option value="additive">加法模型</option>
            </select>
          </Field>
          <Field label="公式表达式" wide>
            <input defaultValue="访客数 × 转化率 × 客单价" className="input font-mono" />
          </Field>
          <Field label="分解方法">
            <select className="input" defaultValue="lmdi">
              <option value="diff">差额分析</option>
              <option value="lmdi">LMDI</option>
              <option value="shapley">Shapley</option>
              <option value="dupont">杜邦分析</option>
            </select>
          </Field>
          <Field label="默认拆解层级">
            <input type="number" defaultValue={2} min={1} max={5} className="input" />
          </Field>
        </form>

        <div className="mt-6">
          <h2 className="mb-2 text-sm font-semibold">指标清单</h2>
          <div className="flex flex-wrap gap-2">
            {metrics.map((metric) => (
              <button
                key={metric.id}
                onClick={() => setSelected(metric)}
                className={`rounded border px-2.5 py-1 text-xs ${
                  metric.id === selected.id
                    ? "border-ink-900 bg-ink-900 text-white"
                    : "border-ink-200 text-ink-600 hover:bg-ink-50"
                }`}
              >
                {metric.name}
                <span className="ml-1.5 opacity-60">{metric.code}</span>
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <label className={`flex flex-col gap-1 ${wide ? "col-span-2" : ""}`}>
      <span className="text-xs text-ink-500">{label}</span>
      {children}
    </label>
  );
}
