import type { EChartsOption } from "echarts";
import ReactEChartsCore from "echarts-for-react/lib/core";

import { echarts } from "./echarts";

interface Props {
  factor: string;
  ratios: number[];
  metricValues: number[];
  baselineValue: number;
}

/** 敏感度曲线：横轴为因子相对基准的倍率，纵轴为目标指标预测值。 */
export function SensitivityChart({ factor, ratios, metricValues, baselineValue }: Props) {
  const option: EChartsOption = {
    grid: { left: 8, right: 16, top: 24, bottom: 28, containLabel: true },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: ratios.map((ratio) => `×${ratio.toFixed(1)}`),
      axisLabel: { fontSize: 11, color: "#515d78" },
      axisLine: { lineStyle: { color: "#d5d9e2" } },
    },
    yAxis: {
      type: "value",
      scale: true,
      splitLine: { lineStyle: { color: "#eceef2" } },
      axisLabel: { fontSize: 11, color: "#8591ab" },
    },
    series: [
      {
        name: factor,
        type: "line",
        smooth: true,
        symbolSize: 6,
        lineStyle: { width: 2, color: "#0f172a" },
        itemStyle: { color: "#0f172a" },
        data: metricValues,
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed", color: "#b0b8c9" },
          data: [{ yAxis: baselineValue, label: { formatter: "基准", fontSize: 10 } }],
        },
      },
    ],
  };

  return (
    <ReactEChartsCore echarts={echarts} option={option} style={{ height: 180 }} notMerge lazyUpdate />
  );
}
