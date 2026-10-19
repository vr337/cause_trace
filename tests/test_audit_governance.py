"""T-23/T-24：审计留痕与配额/阈值配置。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from cause_trace.audit import AuditEntry, export_csv, query, record, record_sandbox, retention_cutoff
from cause_trace.governance import (
    DEFAULT_QUOTA,
    GovernanceValidationError,
    QuotaInput,
    ThresholdInput,
    is_anomalous,
    list_thresholds,
    resolve_quota,
    upsert_quota,
    upsert_threshold,
)


def test_record_and_query_audit(session: Session):
    record(session, AuditEntry(action="report.publish", user_id=7, request_id="req-1"))
    record(session, AuditEntry(action="sandbox.execute", user_id=8, request_id="req-2"))
    session.commit()

    assert len(query(session, user_id=7)) == 1
    assert len(query(session, action="sandbox.execute")) == 1
    assert query(session, request_id="req-2")[0].user_id == 8
    assert len(query(session)) == 2


def test_sandbox_audit_records_status_and_task(session: Session):
    record_sandbox(
        session,
        user_id=7,
        session_id=42,
        hypothesis_id=9,
        status="blocked",
        task_id="sbx-20261019-abcd",
        duration_ms=12,
    )
    session.commit()

    entry = query(session, action="sandbox.blocked")[0]
    assert entry.detail["session_id"] == 42
    assert entry.detail["task_id"] == "sbx-20261019-abcd"


def test_audit_query_filters_by_time_window(session: Session):
    record(session, AuditEntry(action="session.create", user_id=1))
    session.commit()

    future = datetime.now() + timedelta(days=1)
    assert query(session, start=future) == []
    assert len(query(session, end=future)) == 1


def test_audit_export_csv_has_header_and_rows(session: Session):
    record(session, AuditEntry(action="report.export", user_id=3, detail={"format": "pdf"}))
    session.commit()

    csv_text = export_csv(session, user_id=3)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("id,user_id,action")
    assert "report.export" in lines[1]


def test_retention_cutoff_defaults_to_one_year():
    cutoff = retention_cutoff(now=datetime(2026, 10, 19))
    assert cutoff == datetime(2025, 10, 19)


def test_quota_resolution_falls_back_to_default(session: Session):
    assert resolve_quota(session).source == DEFAULT_QUOTA.source


def test_user_quota_overrides_role_and_global(session: Session):
    upsert_quota(session, QuotaInput(scope_type="global", scope_id="default", max_concurrent=5))
    upsert_quota(session, QuotaInput(scope_type="role", scope_id="analyst", timeout_s=20))
    upsert_quota(session, QuotaInput(scope_type="user", scope_id="7", max_rows=5000))
    session.commit()

    resolved = resolve_quota(session, user_id="7", role="analyst")
    assert resolved.source == "user:7"
    assert resolved.max_rows == 5000
    # 用户级没配的字段回到进程默认，不会继承角色级——避免半套配置产生意外边界
    assert resolved.timeout_s == DEFAULT_QUOTA.timeout_s


def test_role_quota_used_when_user_quota_absent(session: Session):
    upsert_quota(session, QuotaInput(scope_type="role", scope_id="analyst", timeout_s=20))
    session.commit()

    resolved = resolve_quota(session, user_id="99", role="analyst")
    assert resolved.source == "role:analyst"
    assert resolved.timeout_s == 20


def test_disabled_quota_is_skipped(session: Session):
    upsert_quota(
        session,
        QuotaInput(scope_type="global", scope_id="default", max_concurrent=9, enabled=False),
    )
    session.commit()
    assert resolve_quota(session).source == DEFAULT_QUOTA.source


@pytest.mark.parametrize(
    "payload",
    [
        QuotaInput(scope_type="unknown", scope_id="x"),
        QuotaInput(scope_type="user", scope_id="1", timeout_s=0),
        QuotaInput(scope_type="user", scope_id="1", max_rows=-1),
    ],
)
def test_invalid_quota_is_rejected(session: Session, payload):
    with pytest.raises(GovernanceValidationError):
        upsert_quota(session, payload)


def test_threshold_upsert_is_idempotent(session: Session):
    upsert_threshold(session, ThresholdInput(metric_id=1, rule_type="dod", threshold_value=-0.10))
    threshold = upsert_threshold(
        session, ThresholdInput(metric_id=1, rule_type="dod", threshold_value=-0.15)
    )
    session.commit()

    assert float(threshold.threshold_value) == pytest.approx(-0.15)
    assert len(list_thresholds(session, metric_id=1)) == 1


def test_threshold_validation(session: Session):
    with pytest.raises(GovernanceValidationError):
        upsert_threshold(
            session, ThresholdInput(metric_id=1, rule_type="week", threshold_value=-0.1)
        )
    with pytest.raises(GovernanceValidationError):
        upsert_threshold(
            session,
            ThresholdInput(metric_id=1, rule_type="dod", threshold_value=-0.1, alarm_level="noise"),
        )
    with pytest.raises(GovernanceValidationError):
        upsert_threshold(session, ThresholdInput(metric_id=1, rule_type="dod", threshold_value=0))


def test_anomaly_detection_by_threshold():
    assert is_anomalous(-0.123, -0.10)
    assert not is_anomalous(-0.05, -0.10)
