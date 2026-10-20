import type { HypothesisCard } from "../api/types";

interface Props {
  hypotheses: HypothesisCard[];
  threshold?: number;
}

const STATUS_LABEL: Record<HypothesisCard["status"], string> = {
  pending: "待验证",
  verified: "已验证",
  excluded: "已排除",
  failed: "验证失败",
};

const STATUS_STYLE: Record<HypothesisCard["status"], string> = {
  pending: "bg-surface-alt text-text-secondary",
  verified: "bg-emerald-50 text-emerald-700",
  excluded: "bg-surface-alt text-text-secondary line-through",
  failed: "bg-amber-50 text-amber-700",
};

/** 假设卡片流：低置信度自动排除的结论要在卡片上直接可见，而不是藏在详情里。 */
export function HypothesisBoard({ hypotheses, threshold = 0.6 }: Props) {
  if (hypotheses.length === 0) {
    return <p className="py-6 text-center text-xs text-text-tertiary">尚未生成候选假设</p>;
  }

  return (
    <ul className="space-y-2">
      {hypotheses.map((hypothesis) => (
        <li key={hypothesis.content} className="rounded-md border border-border bg-white p-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm text-text-primary">{hypothesis.content}</p>
            <span className={`chip shrsurface ${STATUS_STYLE[hypothesis.status]}`}>
              {STATUS_LABEL[hypothesis.status]}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-3 text-xs text-text-secondary">
            {hypothesis.confidence !== null && (
              <ConfidenceBar value={hypothesis.confidence} threshold={threshold} />
            )}
            <span>{hypothesis.origin === "rule" ? "规则模板" : "LLM 生成"}</span>
          </div>
          {hypothesis.exclude_reason && (
            <p className="mt-1 text-xs text-text-tertiary">{hypothesis.exclude_reason}</p>
          )}
        </li>
      ))}
    </ul>
  );
}

function ConfidenceBar({ value, threshold }: { value: number; threshold: number }) {
  const percent = Math.round(value * 100);
  const below = value < threshold;
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-alt">
        <span
          className={`block h-full ${below ? "bg-amber-400" : "bg-emerald-500"}`}
          style={{ width: `${percent}%` }}
        />
      </span>
      <span className={below ? "text-amber-600" : "text-emerald-700"}>{percent}%</span>
    </span>
  );
}
