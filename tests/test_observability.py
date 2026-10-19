"""T-28：结构化日志、Prometheus 指标与告警规则。"""

from __future__ import annotations

import json

import pytest

from cause_trace.observability import (
    CONSERVATION_CHECK_FAILED,
    REPORT_EXPORT_TOTAL,
    SANDBOX_TASK_DURATION,
    SESSION_ACTIVE,
    SESSION_TOTAL,
    STAGE_DURATION,
    LogContext,
    audit_payload,
    configure_logging,
    log_event,
    render_prometheus,
    reset_logging_for_tests,
    reset_metrics,
)
from cause_trace.observability.alerts import AlertSnapshot, evaluate_alerts, prometheus_rules


@pytest.fixture(autouse=True)
def _clean_metrics():
    reset_metrics()
    yield
    reset_metrics()


def test_counter_renders_prometheus_format():
    SESSION_TOTAL.inc(status="running")
    SESSION_TOTAL.inc(status="running")
    SESSION_TOTAL.inc(status="done")

    text = render_prometheus()
    assert "# TYPE cause_session_total counter" in text
    assert 'cause_session_total{status="running"} 2' in text
    assert 'cause_session_total{status="done"} 1' in text


def test_gauge_sets_absolute_value():
    SESSION_ACTIVE.set(7)
    SESSION_ACTIVE.set(3)
    assert 'cause_session_active 3' in render_prometheus()


def test_histogram_buckets_are_cumulative():
    for value in (0.05, 0.3, 1.5, 12.0):
        SANDBOX_TASK_DURATION.observe(value)

    text = render_prometheus()
    assert 'sandbox_task_duration_seconds_bucket{le="0.1"} 1' in text
    assert 'sandbox_task_duration_seconds_bucket{le="0.5"} 2' in text
    assert 'sandbox_task_duration_seconds_bucket{le="2"} 3' in text
    assert 'sandbox_task_duration_seconds_bucket{le="+Inf"} 4' in text
    assert "sandbox_task_duration_seconds_count 4" in text


def test_labeled_histogram_keeps_groups_separate():
    STAGE_DURATION.observe(1.0, stage="decompose")
    STAGE_DURATION.observe(5.0, stage="sandbox_verify")
    text = render_prometheus()

    assert 'stage="decompose"' in text
    assert 'stage="sandbox_verify"' in text


def test_export_counter_records_format():
    REPORT_EXPORT_TOTAL.inc(format="pdf")
    assert 'report_export_total{format="pdf"} 1' in render_prometheus()


def test_conservation_failure_counter_is_exposed():
    CONSERVATION_CHECK_FAILED.inc()
    assert "conservation_check_failed_total 1" in render_prometheus()


def test_log_context_drops_empty_fields():
    context = LogContext(request_id="req-1", session_id=None, stage="decompose")
    assert context.as_record() == {"request_id": "req-1", "stage": "decompose"}


def test_audit_payload_contains_trace_fields():
    payload = audit_payload(
        context=LogContext(request_id="req-2", session_id=42, hypothesis_id=9),
        duration_ms=320,
        status="success",
    )
    assert payload["request_id"] == "req-2"
    assert payload["session_id"] == 42
    assert payload["duration_ms"] == 320


def test_json_logging_writes_structured_record(tmp_path):
    reset_logging_for_tests()
    sink = tmp_path / "app.log"
    configure_logging(level="INFO", sink=str(sink))
    try:
        log_event("INFO", "sandbox task completed", LogContext(request_id="req-3", module="sandbox"))
    finally:
        from loguru import logger

        logger.complete()
        reset_logging_for_tests()

    content = sink.read_text(encoding="utf-8").strip()
    record = json.loads(content.splitlines()[-1])
    assert record["record"]["message"] == "sandbox task completed"
    assert record["record"]["extra"]["request_id"] == "req-3"


def test_no_alerts_for_healthy_snapshot():
    assert evaluate_alerts(AlertSnapshot()) == []


def test_conservation_failure_alerts_immediately():
    fired = evaluate_alerts(AlertSnapshot(conservation_check_failed=1))
    assert fired[0]["name"] == "ConservationCheckFailed"
    assert fired[0]["severity"] == "critical"


def test_alert_ordering_puts_critical_first():
    fired = evaluate_alerts(
        AlertSnapshot(
            service_up=0,
            sandbox_timeout_rate=0.2,
            llm_failure_rate=0.5,
        )
    )
    assert fired[0]["severity"] == "critical"
    assert {item["name"] for item in fired} == {
        "ServiceDown",
        "SandboxTimeoutRate",
        "LlmFailureRate",
    }


def test_prometheus_rules_cover_all_alerts():
    yaml_text = prometheus_rules()
    assert "ConservationCheckFailed" in yaml_text
    assert "expr: increase(conservation_check_failed_total[5m]) > 0" in yaml_text
    assert yaml_text.count("- alert:") == 8
