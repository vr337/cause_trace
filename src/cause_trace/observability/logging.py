"""结构化日志（T-28 / Spec 17.1）。

日志按 JSON 落盘，request_id / session_id / hypothesis_id 是固定字段，
全链路排查时直接按 request_id 过滤即可串起一次分析。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

_configured = False


@dataclass
class LogContext:
    """一次请求/任务的追踪上下文，为空字段不会写进日志。"""

    request_id: str | None = None
    session_id: int | None = None
    hypothesis_id: int | None = None
    stage: str | None = None
    module: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        record = {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "hypothesis_id": self.hypothesis_id,
            "stage": self.stage,
            "module": self.module,
            **self.extra,
        }
        return {key: value for key, value in record.items() if value is not None}


def configure_logging(*, level: str = "INFO", sink: Any | None = None) -> None:
    """幂等配置：重复调用不会叠加 handler。"""
    global _configured
    if _configured:
        return

    logger.remove()
    logger.add(
        sink or sys.stderr,
        level=level,
        serialize=True,
        backtrace=False,
        diagnose=False,
        enqueue=True,
    )
    _configured = True


def log_event(level: str, message: str, context: LogContext | None = None, **kwargs: Any) -> None:
    """带上下文字段的结构化日志入口。"""
    payload = {
        **(context.as_record() if context else {}),
        **kwargs,
    }
    logger.bind(**payload).log(level.upper(), message)


def audit_payload(
    *,
    context: LogContext,
    duration_ms: int,
    status: str,
    output_size: int | None = None,
) -> dict[str, Any]:
    """沙箱/LLM 调用的统一审计片段，避免各处自己拼字段名。"""
    return {
        **context.as_record(),
        "duration_ms": duration_ms,
        "status": status,
        "output_size": output_size,
        "ts": datetime.now().isoformat(),  # noqa: DTZ005 - 日志时间按本地时区写入
    }


def reset_logging_for_tests() -> None:
    global _configured
    _configured = False
