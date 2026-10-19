import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import { useWhatIfStore } from "../store/whatIfStore";
import { SensitivityChart } from "./charts/SensitivityChart";

interface Props {
  sessionId: number | null;
  baselineValue: number;
  elasticities: Record<string, number>;
}

const THROTTLE_MS = 200;

/** What-If 面板：滑块本地即时反馈，服务端重算按 200ms 节流（Spec 15.2）。 */
export function WhatIfPanel({ sessionId, baselineValue, elasticities }: Props) {
  const { factors, scenarios, sensitivityCurve, pending, setFactor, applyResult, setPending } =
    useWhatIfStore();
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abort = useRef<AbortController | null>(null);

  const factorNames = Object.keys(elasticities);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    abort.current?.abort();
  }, []);

  const scheduleRecompute = () => {
    if (!sessionId) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      abort.current?.abort();
      abort.current = new AbortController();
      setPending(true);
      setError(null);
      try {
        // 新请求发出即取消旧请求，避免滑块快速拖动时结果乱序回写
        const result = await api.simulate(sessionId, {
          baseline_value: baselineValue,
          factor_adjustments: useWhatIfStore.getState().factors,
          elasticities,
        });
        applyResult(result);
      } catch (err) {
        setPending(false);
        setError(err instanceof ApiError ? err.message : "推演失败");
      }
    }, THROTTLE_MS);
  };

  if (factorNames.length === 0) {
    return (
      <p className="py-4 text-center text-xs text-ink-400">
        归因结论锁定可干预因子后，可在此调节情景参数
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {factorNames.map((name) => (
        <label key={name} className="block">
          <span className="flex items-center justify-between text-xs text-ink-600">
            <span>{name}</span>
            <span className="font-mono text-ink-900">
              ×{(factors[name] ?? 1).toFixed(2)}
            </span>
          </span>
          <input
            type="range"
            min={0.5}
            max={1.5}
            step={0.05}
            value={factors[name] ?? 1}
            className="mt-1 w-full accent-ink-900"
            onChange={(event) => {
              setFactor(name, Number(event.target.value));
              scheduleRecompute();
            }}
          />
        </label>
      ))}

      {sensitivityCurve.map((curve) => (
        <SensitivityChart
          key={curve.factor}
          factor={curve.factor}
          ratios={curve.ratios}
          metricValues={curve.metric_values}
          baselineValue={baselineValue}
        />
      ))}

      <div className="space-y-1.5">
        {scenarios.map((scenario) => (
          <div
            key={scenario.scenario_name}
            className="flex items-center justify-between rounded border border-ink-200 px-2 py-1.5 text-xs"
          >
            <span className="text-ink-600">{scenario.scenario_name}</span>
            <span className={scenario.delta < 0 ? "text-fall" : "text-rise"}>
              {(scenario.delta_rate * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>

      {pending && <p className="text-xs text-ink-400">重算中…</p>}
      {error && <p className="text-xs text-amber-600">{error}</p>}
    </div>
  );
}
