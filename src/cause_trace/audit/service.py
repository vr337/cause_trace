"""审计治理（T-23 / FR-18）。

审计表只允许 INSERT（Spec 18.3），因此本模块不提供更新与删除入口；
查询与导出按用户/时间/操作类型过滤，request_id 贯穿前后端。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from cause_trace.db.models.governance import AuditLog

DEFAULT_RETENTION_DAYS = 365
EXPORT_LIMIT = 10_000


@dataclass(frozen=True)
class AuditEntry:
    action: str
    user_id: int | None = None
    target_type: str | None = None
    target_id: int | None = None
    request_id: str | None = None
    detail: dict[str, Any] | None = None


def record(session: Session, entry: AuditEntry) -> AuditLog:
    log = AuditLog(
        user_id=entry.user_id,
        action=entry.action,
        target_type=entry.target_type,
        target_id=entry.target_id,
        request_id=entry.request_id,
        detail=entry.detail,
    )
    session.add(log)
    session.flush()
    return log


def record_sandbox(
    session: Session,
    *,
    user_id: int | None,
    session_id: int,
    hypothesis_id: int | None,
    status: str,
    task_id: str,
    request_id: str | None = None,
    duration_ms: int | None = None,
) -> AuditLog:
    """沙箱执行留痕：失败与拦截同样要记，否则无法回溯是谁触发了什么。"""
    return record(
        session,
        AuditEntry(
            action=f"sandbox.{status}",
            user_id=user_id,
            target_type="hypothesis",
            target_id=hypothesis_id,
            request_id=request_id,
            detail={"session_id": session_id, "task_id": task_id, "duration_ms": duration_ms},
        ),
    )


def query(
    session: Session,
    *,
    user_id: int | None = None,
    action: str | None = None,
    request_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    stmt: Select = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if request_id is not None:
        stmt = stmt.where(AuditLog.request_id == request_id)
    if start is not None:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end is not None:
        stmt = stmt.where(AuditLog.created_at <= end)
    return list(session.scalars(stmt.limit(min(limit, EXPORT_LIMIT)).offset(offset)))


def export_csv(session: Session, **filters: Any) -> str:
    """把查询结果导成 CSV 字符串；批量上限 EXPORT_LIMIT，避免一次拉爆内存。"""
    rows = query(session, **filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "user_id", "action", "target_type", "target_id", "request_id", "detail", "created_at"])
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.user_id,
                row.action,
                row.target_type,
                row.target_id,
                row.request_id,
                row.detail,
                row.created_at.isoformat() if row.created_at else "",
            ]
        )
    return buffer.getvalue()


def retention_cutoff(now: datetime | None = None, days: int = DEFAULT_RETENTION_DAYS) -> datetime:
    """保留期截止时间：早于该时间的记录可归档到冷存储。"""
    from datetime import timedelta

    reference = now or datetime.now()  # noqa: DTZ005
    return reference - timedelta(days=days)
