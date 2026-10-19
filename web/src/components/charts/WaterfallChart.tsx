import ReactEChartsCore from "echarts-for-react/lib/core";
import type { EChartsOption } from "echarts";

import type { Contribution } from "../../api/types";
import { echarts } from "./echarts";

interface Props {
  contributions: Contribution[];
  totalDelta: number;
}

/** 因子贡献瀑布图：每个因子一根浮动柱，末位补总变动，视觉上必须严丝合缝。 */
export function WaterfallChart({ contributions, totalDelta }: Props) {
  let running = 0;
  const steps = contributions.map((item) => {
    const start = running;
    running += item.contribution;
    return { name: item.factor, start, end: running, value: item.contribution };
  });
  steps.push({ name: "总变动", start: 0, end: totalDelta, value: totalDelta });

  const option: EChartsOption = {
    grid: { left: 8, right: 8, top: 24, bottom: 32, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params) => {
        const list = params as Array<{ dataIndex: number }>;
        const step = steps[list[0].dataIndex];
        return `${step.name}<br/>贡献量：${step.value.toLocaleString()}`;
      },
    },
    xAxis: {
      type: "category",
      data: steps.map((step) => step.name),
      axisLabel: { fontSize: 11, color: "#515d78" },
      axisLine: { lineStyle: { color: "#d5d9e2" } },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#eceef2" } },
      axisLabel: { fontSize: 11, color: "#8591ab" },
    },
    series: [
      {
        type: "bar",
        stack: "waterfall",
        silent: true,
        itemStyle: { color: "transparent" },
        data: steps.map((step) => Math.min(step.start, step.end)),
      },
      {
        type: "bar",
        stack: "waterfall",
        barWidth: "52%",
        // 国内经营报表惯例：涨红跌绿
        data: steps.map((step) => ({
          value: Math.abs(step.end - step.start),
          itemStyle: {
            color:
              step.name === "总变动" ? "#0f172a" : step.value >= 0 ? "#dc2626" : "#16a34a",
          },
        })),
        label: {
          show: true,
          position: "top",
          fontSize: 11,
          formatter: (params) => {
            const item = params as { dataIndex: number };
            return steps[item.dataIndex].value.toFixed(1);
          },
        },
      },
    ],
  };

  return (
    <ReactEChartsCore echarts={echarts} option={option} style={{ height: 220 }} notMerge lazyUpdate />
  );
}
