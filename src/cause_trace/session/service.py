"""会话与报告管理（T-11 / FR-07、FR-16、FR-22）。

报告 payload 入库前必须过七章节 JSON Schema 校验（Spec 5.3），因此这里只
提供「先校验再落库」的组装入口，不提供绕过校验的后门。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cause_trace.db.models.attribution import (
    AttributionSession,
    CausalLink,
    Evidence,
    Hypothesis,
    Report,
    Simulation,
)
from cause_trace.db.models.governance import ReportAnnotation, ReportVersion
from cause_trace.orchestration.hypothesis import HypothesisStatus
from cause_trace.report.schema import validate_report_payload

VALID_BASELINES = {"dod", "yoy", "target"}
VALID_SESSION_STATUS = {"running", "done", "failed"}


class SessionValidationError(ValueError):
    """会话/报告输入不合法，由接口层转成 400。"""


@dataclass(frozen=True)
class SessionInput:
    user_id: int
    domain_id: int
    metric_id: int
    window_start: datetime
    window_end: datetime
    baseline: str
    conversation_id: int | None = None


def create_session(session: Session, payload: SessionInput) -> AttributionSession:
    if payload.baseline not in VALID_BASELINES:
        raise SessionValidationError(f"对比基期必须是 {sorted(VALID_BASELINES)} 之一")
    if payload.window_start >= payload.window_end:
        raise SessionValidationError("统计周期起点必须早于终点")

    entity = AttributionSession(
        user_id=payload.user_id,
        domain_id=payload.domain_id,
        metric_id=payload.metric_id,
        window_start=payload.window_start,
        window_end=payload.window_end,
        baseline=payload.baseline,
        conversation_id=payload.conversation_id,
        status="running",
        current_stage="intent_parse",
    )
    session.add(entity)
    session.flush()
    return entity


def update_stage(session: Session, session_id: int, stage: str) -> AttributionSession:
    """推进分析阶段，前端断点恢复依赖这个字段（Spec 12.4）。"""
    entity = session.get(AttributionSession, session_id)
    if entity is None:
        raise SessionValidationError(f"归因会话 {session_id} 不存在")
    entity.current_stage = stage
    session.flush()
    return entity


def finish_session(session: Session, session_id: int, status: str = "done") -> AttributionSession:
    if status not in VALID_SESSION_STATUS:
        raise SessionValidationError(f"会话状态必须是 {sorted(VALID_SESSION_STATUS)} 之一")
    entity = update_stage(session, session_id, "report")
    entity.status = status
    session.flush()
    return entity


def persist_hypotheses(session: Session, session_id: int, hypotheses: list[dict]) -> list[Hypothesis]:
    """假设批量落库；status 由上层状态机给定，这里不二次判断。"""
    entities = [
        Hypothesis(
            session_id=session_id,
            content=item["content"],
            origin=item.get("origin", "llm"),
            status=item.get("status", HypothesisStatus.PENDING.value),
            confidence=item.get("confidence"),
            exclude_reason=item.get("exclude_reason"),
        )
        for item in hypotheses
    ]
    session.add_all(entities)
    session.flush()
    return entities


def persist_evidence(session: Session, hypothesis_id: int, payload: dict) -> Evidence:
    """证据全量留痕：exec_code 原样入库，满足审计回溯要求。"""
    entity = Evidence(
        hypothesis_id=hypothesis_id,
        exec_type=payload["exec_type"],
        exec_code=payload["exec_code"],
        exec_result=payload.get("exec_result"),
        p_value=payload.get("p_value"),
        contribution=payload.get("contribution"),
        runner_task_id=payload.get("runner_task_id"),
        duration_ms=payload.get("duration_ms"),
    )
    session.add(entity)
    session.flush()
    return entity


def persist_simulation(session: Session, session_id: int, payload: dict) -> Simulation:
    entity = Simulation(
        session_id=session_id,
        factor_params=payload.get("factor_params"),
        scenarios=payload.get("scenarios"),
    )
    session.add(entity)
    session.flush()
    return entity


def persist_causal_links(session: Session, session_id: int, links: list[dict]) -> list[CausalLink]:
    entities = [
        CausalLink(
            session_id=session_id,
            hypothesis_id=link.get("hypothesis_id"),
            event_id=link.get("event_id"),
            role=link["role"],
            contribution=link.get("contribution"),
            summary=link.get("summary"),
        )
        for link in links
    ]
    session.add_all(entities)
    session.flush()
    return entities


def assemble_report(session: Session, session_id: int, title: str, payload: dict) -> Report:
    """组装七章节报告：先过 Schema 校验，再落库，最后写版本快照。"""
    validate_report_payload(payload)

    report = session.scalar(select(Report).where(Report.session_id == session_id))
    if report is None:
        report = Report(session_id=session_id, title=title, payload=payload, status="draft")
        session.add(report)
        session.flush()
    else:
        report.title = title
        report.payload = payload

    _write_version(session, report)
    session.flush()
    return report


def _write_version(session: Session, report: Report) -> ReportVersion:
    """每次组装都生成一个版本快照，版本号单调递增，支撑后续 diff。"""
    next_version = report.current_version + 1
    report.current_version = next_version
    version = ReportVersion(
        report_id=report.id, version=next_version, payload=report.payload, created_by=report.created_by
    )
    session.add(version)
    session.flush()
    return version


def publish_report(session: Session, report_id: int, user_id: int) -> Report:
    report = session.get(Report, report_id)
    if report is None:
        raise SessionValidationError(f"报告 {report_id} 不存在")
    report.status = "published"
    report.created_by = user_id
    report.published_at = datetime.now()  # noqa: DTZ005 - 经营数据按本地时间归档
    session.flush()
    return report


def add_annotation(
    session: Session,
    report_id: int,
    anchor: str,
    content: str,
    version: int,
    user_id: int,
    mention_user_ids: list[int] | None = None,
) -> ReportAnnotation:
    """批注绑定具体版本：正文更新后旧批注不自动失效，但可标记为过期。"""
    entity = ReportAnnotation(
        report_id=report_id,
        anchor=anchor,
        content=content,
        version=version,
        created_by=user_id,
        mention_user_ids=mention_user_ids,
    )
    session.add(entity)
    session.flush()
    return entity


def list_annotations(session: Session, report_id: int) -> list[ReportAnnotation]:
    stmt = (
        select(ReportAnnotation)
        .where(ReportAnnotation.report_id == report_id)
        .order_by(ReportAnnotation.created_at.desc())
    )
    return list(session.scalars(stmt))


def list_versions(session: Session, report_id: int) -> list[ReportVersion]:
    stmt = (
        select(ReportVersion).where(ReportVersion.report_id == report_id).order_by(ReportVersion.version)
    )
    return list(session.scalars(stmt))


def session_snapshot(session: Session, session_id: int) -> dict[str, Any]:
    """会话断点快照：阶段 + 假设 + 证据链摘要，写入 Redis（key 见 Spec 5.5）。"""
    entity = session.get(AttributionSession, session_id)
    if entity is None:
        raise SessionValidationError(f"归因会话 {session_id} 不存在")

    hypotheses = list(
        session.scalars(select(Hypothesis).where(Hypothesis.session_id == session_id))
    )
    return {
        "session_id": session_id,
        "status": entity.status,
        "current_stage": entity.current_stage,
        "baseline": entity.baseline,
        "window": {"start": entity.window_start.isoformat(), "end": entity.window_end.isoformat()},
        "hypotheses": [
            {
                "id": h.id,
                "content": h.content,
                "status": h.status,
                "confidence": float(h.confidence) if h.confidence is not None else None,
                "exclude_reason": h.exclude_reason,
            }
            for h in hypotheses
        ],
    }
