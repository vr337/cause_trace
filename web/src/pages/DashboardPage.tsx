import { useNavigate } from "react-router-dom";

import type { Baseline } from "../api/types";
import { useSessionStore } from "../store/sessionStore";

interface MetricCard {
  name: string;
  value: string;
  change: string;
  abnormal: boolean;
  baseline: Baseline;
}

const METRICS: MetricCard[] = [
  { name: "GMV", value: "¥1,024万", change: "-12.3%", abnormal: true, baseline: "dod" },
  { name: "转化率", value: "2.31%", change: "-0.4pct", abnormal: true, baseline: "dod" },
  { name: "客单价", value: "¥186", change: "-3.1%", abnormal: false, baseline: "dod" },
  { name: "利润率", value: "5.2%", change: "+0.3pct", abnormal: false, baseline: "dod" },
];

const ANOMALIES = [
  { metric: "GMV", change: "-12.3%", startedAt: "08-12 14:00", metricId: 1 },
  { metric: "搜索流量", change: "-18.7%", startedAt: "08-12 09:00", metricId: 2 },
  { metric: "支付成功率", change: "-2.1pct", startedAt: "08-15 10:30", metricId: 3 },
];

/** 指标异动大盘（PRD 7.1 / FR-08）：异常指标突出标识，一键发起归因。 */
export function DashboardPage() {
  const navigate = useNavigate();
  const setSession = useSessionStore((state) => state.setSession);

  const startAttribution = (metricId: number) => {
    // 大盘只负责发起，真正的会话创建在工作台完成，避免这里重复请求
    setSession({
      sessionId: 0,
      domainId: 1,
      metricId,
      baseline: "dod",
      windowStart: "2026-08-12",
      windowEnd: "2026-08-18",
    });
    navigate("/workbench");
  };

  return (
    <div className="h-full overflow-auto p-5">
      <div className="mx-auto max-w-7xl space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">指标异动大盘</h1>
          <div className="flex gap-2 text-xs">
            <select className="rounded border border-ink-200 bg-white px-2 py-1.5">
              <option>电商经营域</option>
              <option>快消经营域</option>
            </select>
            <select className="rounded border border-ink-200 bg-white px-2 py-1.5">
              <option>近 7 天</option>
              <option>近 30 天</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3">
          {METRICS.map((metric) => (
            <div key={metric.name} className="card p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-ink-500">{metric.name}</span>
                {metric.abnormal && (
                  <span className="chip bg-rise/10 text-rise">异动</span>
                )}
              </div>
              <p className="metric-value mt-2">{metric.value}</p>
              <p
                className={`mt-1 text-xs ${metric.change.startsWith("-") ? "text-fall" : "text-rise"}`}
              >
                日环比 {metric.change}
              </p>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="flex items-center justify-between border-b border-ink-200 px-4 py-3">
            <span className="card-title">异动指标列表</span>
            <span className="text-xs text-ink-400">按跌幅降序</span>
          </div>
          <ul>
            {ANOMALIES.map((item) => (
              <li
                key={item.metric}
                className="flex items-center justify-between border-b border-ink-100 px-4 py-3 last:border-0"
              >
                <div className="flex items-center gap-4">
                  <span className="w-24 text-sm font-medium">{item.metric}</span>
                  <span className="text-xs text-fall">日环比 {item.change}</span>
                  <span className="text-xs text-ink-400">异动开始 {item.startedAt}</span>
                </div>
                <button className="btn-primary" onClick={() => startAttribution(item.metricId)}>
                  发起智能归因
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="card-title">异常指标趋势（近 30 天）</span>
            <span className="text-xs text-ink-400">红点标记异动发生日</span>
          </div>
          <div className="flex h-32 items-end gap-1">
            {Array.from({ length: 30 }).map((_, index) => {
              const height = 40 + Math.sin(index / 3) * 18 + (index === 21 ? -30 : 0);
              return (
                <div
                  key={index}
                  className={`flex-1 rounded-t ${index === 21 ? "bg-rise" : "bg-ink-200"}`}
                  style={{ height: `${Math.max(height, 8)}%` }}
                />
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
