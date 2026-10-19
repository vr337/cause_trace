"""配额与阈值配置（T-24 / FR-21、FR-24）。

优先级 global < role < user：用户级配额覆盖角色级，角色级覆盖全局；
任何未配置的字段落到进程默认值，避免管理员漏配后任务直接跑满。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cause_trace.db.models.governance import AnomalyThreshold, SandboxQuota

QUOTA_SCOPES = {"global", "role", "user"}
THRESHOLD_RULES = {"dod", "yoy", "target"}
ALARM_LEVELS = {"info", "warning", "critical"}


class GovernanceValidationError(ValueError):
    """治理配置输入不合法。"""


@dataclass(frozen=True)
class QuotaInput:
    scope_type: str
    scope_id: str
    cpu_core: float | None = None
    memory_mb: int | None = None
    timeout_s: int | None = None
    max_concurrent: int | None = None
    max_rows: int | None = None
    enabled: bool = True


def _validate_quota(payload: QuotaInput) -> None:
    if payload.scope_type not in QUOTA_SCOPES:
        raise GovernanceValidationError(f"配额范围必须是 {sorted(QUOTA_SCOPES)} 之一")
    for field_name, value in (
        ("cpu_core", payload.cpu_core),
        ("memory_mb", payload.memory_mb),
        ("timeout_s", payload.timeout_s),
        ("max_concurrent", payload.max_concurrent),
        ("max_rows", payload.max_rows),
    ):
        if value is not None and value <= 0:
            raise GovernanceValidationError(f"{field_name} 必须为正数")


def upsert_quota(session: Session, payload: QuotaInput) -> SandboxQuota:
    _validate_quota(payload)
    quota = session.scalar(
        select(SandboxQuota).where(
            SandboxQuota.scope_type == payload.scope_type, SandboxQuota.scope_id == payload.scope_id
        )
    )
    if quota is None:
        quota = SandboxQuota(scope_type=payload.scope_type, scope_id=payload.scope_id)
        session.add(quota)

    quota.cpu_core = Decimal(str(payload.cpu_core)) if payload.cpu_core is not None else None
    quota.memory_mb = payload.memory_mb
    quota.timeout_s = payload.timeout_s
    quota.max_concurrent = payload.max_concurrent
    quota.max_rows = payload.max_rows
    quota.enabled = payload.enabled
    session.flush()
    return quota


@dataclass(frozen=True)
class ResolvedQuota:
    cpu_core: float
    memory_mb: int
    timeout_s: int
    max_concurrent: int
    max_rows: int
    source: str

    def as_dict(self) -> dict:
        return {
            "cpu_core": self.cpu_core,
            "memory_mb": self.memory_mb,
            "timeout_s": self.timeout_s,
            "max_concurrent": self.max_concurrent,
            "max_rows": self.max_rows,
            "source": self.source,
        }


DEFAULT_QUOTA = ResolvedQuota(
    cpu_core=1.0, memory_mb=512, timeout_s=30, max_concurrent=3, max_rows=100_000, source="default"
)


def resolve_quota(session: Session, *, user_id: str | None = None, role: str | None = None) -> ResolvedQuota:
    """按 user > role > global > default 逐级覆盖。"""
    chain: list[tuple[str, str]] = []
    if user_id is not None:
        chain.append(("user", user_id))
    if role is not None:
        chain.append(("role", role))
    chain.append(("global", "default"))

    resolved = DEFAULT_QUOTA
    for scope_type, scope_id in chain:
        quota = session.scalar(
            select(SandboxQuota).where(
                SandboxQuota.scope_type == scope_type,
                SandboxQuota.scope_id == scope_id,
                SandboxQuota.enabled.is_(True),
            )
        )
        if quota is None:
            continue
        resolved = ResolvedQuota(
            cpu_core=float(quota.cpu_core) if quota.cpu_core is not None else resolved.cpu_core,
            memory_mb=quota.memory_mb or resolved.memory_mb,
            timeout_s=quota.timeout_s or resolved.timeout_s,
            max_concurrent=quota.max_concurrent or resolved.max_concurrent,
            max_rows=quota.max_rows or resolved.max_rows,
            source=f"{scope_type}:{scope_id}",
        )
        break
    return resolved


@dataclass(frozen=True)
class ThresholdInput:
    metric_id: int
    rule_type: str
    threshold_value: float
    alarm_level: str = "warning"
    notify_channels: tuple[str, ...] = ()
    enabled: bool = True


def upsert_threshold(session: Session, payload: ThresholdInput) -> AnomalyThreshold:
    if payload.rule_type not in THRESHOLD_RULES:
        raise GovernanceValidationError(f"阈值规则必须是 {sorted(THRESHOLD_RULES)} 之一")
    if payload.alarm_level not in ALARM_LEVELS:
        raise GovernanceValidationError(f"告警级别必须是 {sorted(ALARM_LEVELS)} 之一")
    if payload.threshold_value == 0:
        raise GovernanceValidationError("阈值不能为 0")

    threshold = session.scalar(
        select(AnomalyThreshold).where(
            AnomalyThreshold.metric_id == payload.metric_id,
            AnomalyThreshold.rule_type == payload.rule_type,
        )
    )
    if threshold is None:
        threshold = AnomalyThreshold(metric_id=payload.metric_id, rule_type=payload.rule_type)
        session.add(threshold)

    threshold.threshold_value = Decimal(str(payload.threshold_value))
    threshold.alarm_level = payload.alarm_level
    threshold.notify_channels = list(payload.notify_channels)
    threshold.enabled = payload.enabled
    session.flush()
    return threshold


def is_anomalous(change_rate: float, threshold_value: float) -> bool:
    """跌幅超过阈值判定异动；阈值按绝对值配置，如 -0.10 表示跌超 10%。"""
    return change_rate < threshold_value


def list_thresholds(session: Session, metric_id: int | None = None) -> list[AnomalyThreshold]:
    stmt = select(AnomalyThreshold).order_by(AnomalyThreshold.metric_id)
    if metric_id is not None:
        stmt = stmt.where(AnomalyThreshold.metric_id == metric_id)
    return list(session.scalars(stmt))
