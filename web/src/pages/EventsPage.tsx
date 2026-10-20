import { useState } from "react";

import { api, ApiError } from "../api/client";
import type { EventItem } from "../api/types";

const EVENT_TYPE_LABEL: Record<EventItem["event_type"], string> = {
  promo: "营销大促",
  operation: "运营动作",
  external: "竞品动作",
  fault: "系统故障",
};

const EVENT_TYPE_STYLE: Record<EventItem["event_type"], string> = {
  promo: "danger-soft text-danger",
  operation: "bg-surface-alt text-text-secondary",
  external: "bg-amber-50 text-amber-700",
  fault: "success-soft text-success",
};

const DEMO_EVENTS: EventItem[] = [
  {
    name: "818 家电节",
    event_type: "promo",
    window_start: "2026-08-10",
    window_end: "2026-08-12",
    categories: ["家电"],
    channels: ["douyin"],
    metrics: ["gmv"],
  },
  {
    name: "竞品A百亿补贴",
    event_type: "external",
    window_start: "2026-08-12",
    window_end: "2026-08-13",
    categories: ["手机数码"],
    channels: ["douyin"],
    metrics: ["gmv"],
  },
  {
    name: "支付通道抖动 40min",
    event_type: "fault",
    window_start: "2026-08-15",
    window_end: "2026-08-15",
    categories: [],
    channels: [],
    metrics: ["pay_success_rate"],
  },
];

/** 业务事件日历（PRD 7.3 / FR-12）：维护事件并验证异动窗口匹配。 */
export function EventsPage() {
  const [events] = useState<EventItem[]>(DEMO_EVENTS);
  const [matched, setMatched] = useState<
    Array<{ name: string; overlap_days: number; is_causal: boolean; relevance: number }>
  >([]);
  const [error, setError] = useState<string | null>(null);

  const checkMatch = async () => {
    setError(null);
    try {
      const result = await api.matchEvents({
        window_start: "2026-08-12",
        window_end: "2026-08-18",
        categories: ["家电", "手机数码"],
        channels: ["douyin"],
        metric_code: "gmv",
        events,
      });
      setMatched(result.matched);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "匹配失败");
    }
  };

  return (
    <div className="h-full overflow-auto p-5">
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">业务事件日历</h1>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={checkMatch}>
              校验与异动窗口匹配
            </button>
            <button className="btn-primary">新建事件</button>
          </div>
        </div>

        <div className="card divide-y divide-surface-alt">
          {events.map((event) => (
            <div key={event.name} className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="w-20 font-mono text-xs text-text-secondary">
                  {event.window_start.slice(5)}
                </span>
                <span className={`chip ${EVENT_TYPE_STYLE[event.event_type]}`}>
                  {EVENT_TYPE_LABEL[event.event_type]}
                </span>
                <div>
                  <p className="text-sm font-medium">{event.name}</p>
                  <p className="text-xs text-text-tertiary">
                    {event.categories.join(" / ") || "全品类"} ·{" "}
                    {event.metrics.join(" / ") || "全部指标"}
                  </p>
                </div>
              </div>
              <span className="text-xs text-text-tertiary">
                {event.window_start} ~ {event.window_end}
              </span>
            </div>
          ))}
        </div>

        {error && <p className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">{error}</p>}

        {matched.length > 0 && (
          <div className="card p-4">
            <h2 className="mb-2 text-sm font-semibold">匹配结果（异动窗口 08-12 ~ 08-18 ±3 日）</h2>
            <ul className="space-y-1.5">
              {matched.map((item) => (
                <li key={item.name} className="flex items-center justify-between text-sm">
                  <span>{item.name}</span>
                  <span className="flex items-center gap-3 text-xs">
                    <span className="text-text-secondary">重合 {item.overlap_days} 天</span>
                    <span className={item.is_causal ? "text-danger" : "text-text-tertiary"}>
                      {item.is_causal ? "进入因果链" : "仅时间重合"}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
