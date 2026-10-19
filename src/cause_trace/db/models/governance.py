"""治理与资产域模型（Spec 5.2）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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


class ReportVersion(Base):
    """REPORT_VERSION：报告发布时的完整 payload 快照。"""

    __tablename__ = "report_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("report.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class ReportAnnotation(Base):
    """REPORT_ANNOTATION：绑定报告版本的批注。"""

    __tablename__ = "report_annotation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("report.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    mention_user_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AuditLog(Base):
    """AUDIT_LOG：审计留痕（只允许 INSERT）。"""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_request", "request_id"),
        Index("ix_audit_log_user_time", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class SandboxQuota(Base):
    """SANDBOX_QUOTA：沙箱资源配额（global/role/user 三级）。"""

    __tablename__ = "sandbox_quota"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cpu_core: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    memory_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AnomalyThreshold(Base):
    """ANOMALY_THRESHOLD：按指标配置的异动阈值。"""

    __tablename__ = "anomaly_threshold"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("metric.id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(16), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    alarm_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notify_channels: Mapped[list | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Subscription(Base):
    """SUBSCRIPTION：周期简报订阅（FR-19，P2）。"""

    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="enabled")


class InjectionConfig(Base):
    """INJECTION_CONFIG：异动仿真注入配置（由 dbmock 写入）。"""

    __tablename__ = "injection_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scenario_code: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dimension_code: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    amplitude: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="enabled")


class InjectionTruth(Base):
    """INJECTION_TRUTH：注入异动的 ground truth 标记。"""

    __tablename__ = "injection_truth"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("injection_config.id"), nullable=False
    )
    dimension_value: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_effect: Mapped[str | None] = mapped_column(String(255), nullable=True)
