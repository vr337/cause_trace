"""告警规则求值（T-28 / Spec 17.3）。

规则以纯函数表达，输入是窗口内的指标快照，输出是否需要告警。这样同一套
规则既能被 Prometheus 抓取，也能在服务内做自检。
"""

from __future__ import annotations

from dataclasses import dataclass

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"


@dataclass(frozen=True)
class AlertRule:
    name: str
    description: str
    severity: str
    threshold: float
    comparison: str  # gt / lt

    def evaluate(self, value: float) -> bool:
        if self.comparison == "gt":
            return value > self.threshold
        return value < self.threshold


@dataclass(frozen=True)
class AlertSnapshot:
    """一次评估所需的指标快照，字段名与 Spec 17.2 的指标一一对应。"""

    conservation_check_failed: float = 0.0
    sandbox_timeout_rate: float = 0.0
    sandbox_quota_exceeded_rate: float = 0.0
    llm_failure_rate: float = 0.0
    llm_p95_seconds: float = 0.0
    service_up: float = 1.0
    session_failed_rate: float = 0.0
    report_export_failure_rate: float = 0.0


RULES: tuple[AlertRule, ...] = (
    AlertRule(
        "ConservationCheckFailed",
        "守恒校验失败，暂停相关会话出图",
        SEVERITY_CRITICAL,
        0.0,
        "gt",
    ),
    AlertRule(
        "SandboxTimeoutRate",
        "沙箱超时率超过 5%，检查数仓负载",
        SEVERITY_WARNING,
        0.05,
        "gt",
    ),
    AlertRule(
        "SandboxQuotaExceededRate",
        "沙箱配额拒绝率超过 10%，评估配额调整",
        SEVERITY_WARNING,
        0.10,
        "gt",
    ),
    AlertRule("LlmFailureRate", "LLM 失败率超过 10%", SEVERITY_WARNING, 0.10, "gt"),
    AlertRule("LlmP95Latency", "LLM P95 延迟超过 30s", SEVERITY_WARNING, 30.0, "gt"),
    AlertRule("ServiceDown", "服务不可用", SEVERITY_CRITICAL, 1.0, "lt"),
    AlertRule("SessionFailedRate", "会话失败率超过 5%", SEVERITY_WARNING, 0.05, "gt"),
    AlertRule("ReportExportFailureRate", "报告导出失败率超过 10%", SEVERITY_WARNING, 0.10, "gt"),
)

_FIELD_BY_RULE = {
    "ConservationCheckFailed": "conservation_check_failed",
    "SandboxTimeoutRate": "sandbox_timeout_rate",
    "SandboxQuotaExceededRate": "sandbox_quota_exceeded_rate",
    "LlmFailureRate": "llm_failure_rate",
    "LlmP95Latency": "llm_p95_seconds",
    "ServiceDown": "service_up",
    "SessionFailedRate": "session_failed_rate",
    "ReportExportFailureRate": "report_export_failure_rate",
}


def evaluate_alerts(snapshot: AlertSnapshot) -> list[dict]:
    """返回触发中的告警；顺序按「critical 优先」保持稳定，便于通知去重。"""
    fired: list[dict] = []
    for rule in RULES:
        value = getattr(snapshot, _FIELD_BY_RULE[rule.name])
        if rule.evaluate(value):
            fired.append(
                {
                    "name": rule.name,
                    "description": rule.description,
                    "severity": rule.severity,
                    "value": value,
                    "threshold": rule.threshold,
                }
            )
    fired.sort(key=lambda item: (item["severity"] != SEVERITY_CRITICAL, item["name"]))
    return fired


def prometheus_rules() -> str:
    """生成 Prometheus 告警规则 YAML，供部署侧直接挂到 Alertmanager。"""
    lines = ["groups:", "  - name: cause_trace", "    rules:"]
    expr_by_rule = {
        "ConservationCheckFailed": "increase(conservation_check_failed_total[5m]) > 0",
        "SandboxTimeoutRate": "rate(sandbox_task_total{status=\"timeout\"}[10m]) "
        "/ rate(sandbox_task_total[10m]) > 0.05",
        "SandboxQuotaExceededRate": "rate(sandbox_task_total{status=\"quota_exceeded\"}[10m]) "
        "/ rate(sandbox_task_total[10m]) > 0.10",
        "LlmFailureRate": "rate(llm_call_total{status=\"failed\"}[10m]) "
        "/ rate(llm_call_total[10m]) > 0.10",
        "LlmP95Latency": "histogram_quantile(0.95, rate(llm_call_duration_seconds_bucket[10m])) > 30",
        "ServiceDown": "up == 0",
        "SessionFailedRate": "rate(cause_session_total{status=\"failed\"}[10m]) "
        "/ rate(cause_session_total[10m]) > 0.05",
        "ReportExportFailureRate": "rate(report_export_total{status=\"failed\"}[10m]) "
        "/ rate(report_export_total[10m]) > 0.10",
    }
    for rule in RULES:
        lines.extend(
            [
                f"      - alert: {rule.name}",
                f"        expr: {expr_by_rule[rule.name]}",
                "        for: 5m",
                "        labels:",
                f"          severity: {rule.severity}",
                "        annotations:",
                f"          summary: {rule.description}",
            ]
        )
    return "\n".join(lines) + "\n"
