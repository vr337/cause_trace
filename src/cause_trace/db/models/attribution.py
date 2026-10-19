"""归因会话、假设、证据、因果链、仿真与报告模型（Spec 5.1）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cause_trace.db.base import Base


class AttributionSession(Base):
    """ATTRIBUTION_SESSION：归因会话主表。

    `conversation_id` 指向 chat 库，按 Spec 5.4 仅作逻辑外键，不建物理外键。
    """

    __tablename__ = "attribution_session"
    __table_args__ = (
        Index("ix_attribution_session_user_status", "user_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    domain_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("metric_domain.id"), nullable=False
    )
    metric_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("metric.id"), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    baseline: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Hypothesis(Base):
    """HYPOTHESIS：候选假设及其生命周期状态。"""

    __tablename__ = "hypothesis"
    __table_args__ = (Index("ix_hypothesis_session_status", "session_id", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("attribution_session.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(String(1024), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="llm")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    exclude_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Evidence(Base):
    """EVIDENCE：沙箱验证产出，全量留痕满足审计回溯。"""

    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_hypothesis", "hypothesis_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hypothesis_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hypothesis.id"), nullable=False
    )
    exec_type: Mapped[str] = mapped_column(String(16), nullable=False)
    exec_code: Mapped[str] = mapped_column(Text, nullable=False)
    exec_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    p_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 8), nullable=True)
    contribution: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    runner_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class BusinessEvent(Base):
    """BUSINESS_EVENT：业务事件日历，用于异动窗口前后 3 日匹配。"""

    __tablename__ = "business_event"
    __table_args__ = (Index("ix_business_event_window", "window_start", "window_end"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    related_metric_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class CausalLink(Base):
    """CAUSAL_LINK：因果链条目（内部因子或外部事件）。"""

    __tablename__ = "causal_link"
    __table_args__ = (Index("ix_causal_link_session", "session_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("attribution_session.id"), nullable=False
    )
    event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("business_event.id"), nullable=True
    )
    hypothesis_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hypothesis.id"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    contribution: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class Simulation(Base):
    """SIMULATION：What-If 推演参数与多情景结果。"""

    __tablename__ = "simulation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("attribution_session.id"), nullable=False
    )
    factor_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scenarios: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Report(Base):
    """REPORT：七章节结构化报告。"""

    __tablename__ = "report"
    __table_args__ = (Index("ix_report_session", "session_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("attribution_session.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
