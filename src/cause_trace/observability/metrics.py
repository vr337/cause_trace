"""Prometheus 指标（T-28 / Spec 17.2）。

不引入 prometheus_client，按其文本暴露格式手写序列化：指标数量固定且不多，
省掉一个依赖，也让测试能直接断言输出内容。

守恒校验失败计数 > 0 必须立即告警——这是 PRD 的硬验收项，不允许静默。
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict

LABEL_SEPARATOR = ","


class Counter:
    def __init__(self, name: str, help_text: str, labels: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help = help_text
        self.labels = labels
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[key] += amount

    def value(self, **labels: str) -> float:
        key = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        with self._lock:
            items = sorted(self._values.items())
        for key, value in items:
            lines.append(f"{self.name}{_format_labels(self.labels, key)} {_float(value)}")
        if not items:
            lines.append(f"{self.name} 0")
        return lines


class Gauge:
    def __init__(self, name: str, help_text: str, labels: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help = help_text
        self.labels = labels
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[key] = value

    def value(self, **labels: str) -> float:
        key = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} gauge"]
        with self._lock:
            items = sorted(self._values.items())
        for key, value in items:
            lines.append(f"{self.name}{_format_labels(self.labels, key)} {_float(value)}")
        if not items:
            lines.append(f"{self.name} 0")
        return lines


class Histogram:
    """固定桶的耗时直方图，输出 _bucket / _sum / _count 三组序列。"""

    DEFAULT_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, math.inf)

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: tuple[str, ...] = (),
        buckets: tuple[float, ...] = DEFAULT_BUCKETS,
    ) -> None:
        self.name = name
        self.help = help_text
        self.labels = labels
        self.buckets = buckets
        self._counts: dict[tuple[str, ...], list[int]] = defaultdict(lambda: [0] * len(buckets))
        self._sums: dict[tuple[str, ...], float] = defaultdict(float)
        self._totals: dict[tuple[str, ...], int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            counts = self._counts[key]
            for index, bound in enumerate(self.buckets):
                if value <= bound:
                    counts[index] += 1
            self._sums[key] += value
            self._totals[key] += 1

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        with self._lock:
            items = sorted(self._counts.items())
            for key, counts in items:
                for index, bound in enumerate(self.buckets):
                    bound_label = "+Inf" if math.isinf(bound) else _float(bound)
                    labels = _format_labels(self.labels, key, extra=("le", bound_label))
                    lines.append(f"{self.name}_bucket{labels} {counts[index]}")
                lines.append(f"{self.name}_sum{_format_labels(self.labels, key)} {_float(self._sums[key])}")
                lines.append(f"{self.name}_count{_format_labels(self.labels, key)} {self._totals[key]}")
        return lines


def _format_labels(labels: tuple[str, ...], values: tuple[str, ...], extra: tuple[str, str] | None = None) -> str:
    pairs = [f'{label}="{value}"' for label, value in zip(labels, values, strict=True)]
    if extra:
        pairs.append(f'{extra[0]}="{extra[1]}"')
    return "{" + LABEL_SEPARATOR.join(pairs) + "}" if pairs else ""


def _float(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.6f}".rstrip("0").rstrip(".")


SESSION_TOTAL = Counter("cause_session_total", "归因会话创建总数", ("status",))
SESSION_ACTIVE = Gauge("cause_session_active", "当前活跃会话数")
STAGE_DURATION = Histogram("cause_stage_duration_seconds", "各阶段耗时", ("stage",))
SANDBOX_TASK_TOTAL = Counter("sandbox_task_total", "沙箱任务总数", ("status",))
SANDBOX_TASK_DURATION = Histogram("sandbox_task_duration_seconds", "沙箱任务耗时")
SANDBOX_QUEUE_SIZE = Gauge("sandbox_task_queue_size", "沙箱任务排队数")
LLM_CALL_TOTAL = Counter("llm_call_total", "LLM 调用总数", ("model", "status"))
LLM_CALL_DURATION = Histogram("llm_call_duration_seconds", "LLM 调用延迟")
LLM_CALL_TOKENS = Counter("llm_call_tokens_total", "LLM token 消耗", ("model",))
CONSERVATION_CHECK_FAILED = Counter("conservation_check_failed_total", "守恒校验失败次数")
REPORT_EXPORT_TOTAL = Counter("report_export_total", "报告导出次数", ("format",))
REPORT_EXPORT_DURATION = Histogram("report_export_duration_seconds", "报告导出耗时", ("format",))

_ALL: tuple[Counter | Gauge | Histogram, ...] = (
    SESSION_TOTAL,
    SESSION_ACTIVE,
    STAGE_DURATION,
    SANDBOX_TASK_TOTAL,
    SANDBOX_TASK_DURATION,
    SANDBOX_QUEUE_SIZE,
    LLM_CALL_TOTAL,
    LLM_CALL_DURATION,
    LLM_CALL_TOKENS,
    CONSERVATION_CHECK_FAILED,
    REPORT_EXPORT_TOTAL,
    REPORT_EXPORT_DURATION,
)


def render_prometheus() -> str:
    lines: list[str] = []
    for metric in _ALL:
        lines.extend(metric.render())
    return "\n".join(lines) + "\n"


def reset_metrics() -> None:
    """测试用：清空所有指标，避免用例之间相互污染。"""
    for metric in _ALL:
        if isinstance(metric, Counter | Gauge):
            metric._values.clear()  # noqa: SLF001 - 测试辅助
        else:
            metric._counts.clear()  # noqa: SLF001
            metric._sums.clear()  # noqa: SLF001
            metric._totals.clear()  # noqa: SLF001
