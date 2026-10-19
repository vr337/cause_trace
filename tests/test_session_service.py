"""T-11：会话、报告组装、版本与批注（SQLite 内存库）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from cause_trace.db.models.attribution import AttributionSession
from cause_trace.db.models.domain import DataSource, Metric, MetricDomain
from cause_trace.dictionary import register_tree_guards
from cause_trace.errors import ReportPayloadError
from cause_trace.report import empty_section_payload
from cause_trace.session import (
    SessionInput,
    SessionValidationError,
    add_annotation,
    assemble_report,
    create_session,
    finish_session,
    list_annotations,
    list_versions,
    persist_evidence,
    persist_hypotheses,
    publish_report,
    session_snapshot,
    update_stage,
)

register_tree_guards()


@pytest.fixture
def domain(session: Session) -> MetricDomain:
    entity = MetricDomain(name="电商经营域", biz_line="电商")
    session.add(entity)
    session.flush()
    return entity


@pytest.fixture
def source(session: Session) -> DataSource:
    entity = DataSource(
        name="warehouse", host="127.0.0.1", port=3306, db_name="warehouse",
        account="cause_ro", secret_ref="WH_PASSWORD",
    )
    session.add(entity)
    session.flush()
    return entity


@pytest.fixture
def metric(session: Session, domain: MetricDomain, source: DataSource) -> Metric:
    entity = Metric(
        code="gmv", name="GMV", metric_type="composite", algebra="multiplicative",
        domain_id=domain.id, data_source_id=source.id,
    )
    session.add(entity)
    session.flush()
    return entity


@pytest.fixture
def attribution_session(session: Session, domain: MetricDomain, metric: Metric) -> AttributionSession:
    now = datetime(2026, 8, 15, 12, 0, 0)
    entity = create_session(
        session,
        SessionInput(
            user_id=7,
            domain_id=domain.id,
            metric_id=metric.id,
            window_start=now - timedelta(days=7),
            window_end=now,
            baseline="dod",
        ),
    )
    session.flush()
    return entity


def _report_payload(metric_id: int) -> dict:
    return empty_section_payload(
        {
            "title": "8 月 GMV 下滑归因报告",
            "domain_id": 1,
            "metric_id": metric_id,
            "window_start": "2026-08-08T00:00:00",
            "window_end": "2026-08-15T00:00:00",
            "baseline": "dod",
        }
    )


def test_create_session_defaults_to_running(attribution_session: AttributionSession):
    assert attribution_session.status == "running"
    assert attribution_session.current_stage == "intent_parse"


def test_create_session_rejects_inverted_window(session: Session, domain: MetricDomain, metric: Metric):
    now = datetime(2026, 8, 15)
    with pytest.raises(SessionValidationError):
        create_session(
            session,
            SessionInput(
                user_id=1,
                domain_id=domain.id,
                metric_id=metric.id,
                window_start=now,
                window_end=now - timedelta(days=1),
                baseline="dod",
            ),
        )


def test_stage_advances_and_session_finishes(session: Session, attribution_session):
    update_stage(session, attribution_session.id, "decompose")
    finished = finish_session(session, attribution_session.id, status="done")

    assert finished.status == "done"
    assert finished.current_stage == "report"


def test_finish_session_rejects_unknown_status(session: Session, attribution_session):
    with pytest.raises(SessionValidationError):
        finish_session(session, attribution_session.id, status="weird")


def test_hypotheses_and_evidence_persist(session: Session, attribution_session):
    entities = persist_hypotheses(
        session,
        attribution_session.id,
        [{"content": "渠道结构恶化", "confidence": 0.87, "status": "verified"}],
    )
    persist_evidence(
        session,
        entities[0].id,
        {
            "exec_type": "sql",
            "exec_code": "SELECT channel, sum(gmv) FROM dwd_fact_trade GROUP BY channel",
            "exec_result": {"rows": 12},
            "p_value": 0.001,
            "contribution": -0.32,
            "runner_task_id": "sbx-20261019-abcd",
            "duration_ms": 320,
        },
    )
    session.commit()

    snapshot = session_snapshot(session, attribution_session.id)
    assert snapshot["hypotheses"][0]["status"] == "verified"
    assert snapshot["hypotheses"][0]["confidence"] == 0.87


def test_assemble_report_requires_valid_payload(session: Session, attribution_session, metric):
    invalid = _report_payload(metric.id)
    invalid["sections"].pop()

    with pytest.raises(ReportPayloadError):
        assemble_report(session, attribution_session.id, "无效报告", invalid)


def test_assemble_report_creates_version_snapshot(session: Session, attribution_session, metric):
    report = assemble_report(
        session, attribution_session.id, "GMV 下滑归因", _report_payload(metric.id)
    )
    versions = list_versions(session, report.id)

    assert len(versions) == 1
    assert versions[0].version == 2
    assert report.current_version == 2
    assert versions[0].payload == report.payload


def test_repeated_assembly_increments_version(session: Session, attribution_session, metric):
    assemble_report(session, attribution_session.id, "v1", _report_payload(metric.id))
    assemble_report(session, attribution_session.id, "v2", _report_payload(metric.id))
    session.flush()

    assert [v.version for v in list_versions(session, 1)] == [2, 3]


def test_publish_report_sets_metadata(session: Session, attribution_session, metric):
    report = assemble_report(
        session, attribution_session.id, "GMV 下滑归因", _report_payload(metric.id)
    )
    published = publish_report(session, report.id, user_id=7)

    assert published.status == "published"
    assert published.created_by == 7
    assert published.published_at is not None


def test_annotation_binds_to_version(session: Session, attribution_session, metric):
    report = assemble_report(
        session, attribution_session.id, "GMV 下滑归因", _report_payload(metric.id)
    )
    add_annotation(
        session,
        report.id,
        anchor="section_2#120",
        content="这里的贡献率口径需要和财务对齐",
        version=report.current_version,
        user_id=7,
        mention_user_ids=[9],
    )
    session.commit()

    annotations = list_annotations(session, report.id)
    assert annotations[0].version == report.current_version
    assert annotations[0].mention_user_ids == [9]
