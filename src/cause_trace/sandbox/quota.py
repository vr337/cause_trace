"""沙箱配额（Spec 14.4）：并发前置校验 + 参数归一。"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from cause_trace.config import Settings, get_settings
from cause_trace.errors import SandboxPolicyError


@dataclass(frozen=True)
class QuotaLimits:
    timeout_s: int = 30
    max_rows: int = 100_000
    max_concurrent: int = 3
    memory_mb: int = 512
    cpu_core: float = 1.0


class QuotaManager:
    """进程内并发计数；多副本部署时由 Redis INCR 版本替换（key 见 Spec 5.5）。"""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.defaults = QuotaLimits(
            timeout_s=settings.sandbox_default_timeout_s,
            max_rows=settings.sandbox_default_max_rows,
        )
        self._active: dict[int, int] = {}
        self._lock = threading.Lock()

    def resolve(
        self, *, timeout_s: int | None, max_rows: int | None
    ) -> tuple[int, int]:
        resolved_timeout = min(
            timeout_s or self.defaults.timeout_s, self.defaults.timeout_s
        )
        resolved_rows = min(max_rows or self.defaults.max_rows, self.defaults.max_rows)
        return max(1, resolved_timeout), max(1, resolved_rows)

    def acquire(self, user_id: int | None) -> None:
        key = user_id or 0
        with self._lock:
            current = self._active.get(key, 0)
            if current >= self.defaults.max_concurrent:
                raise SandboxPolicyError(
                    f"沙箱并发超限（用户 {key}，上限 {self.defaults.max_concurrent}）",
                    code="SBX_QUOTA_EXCEEDED",
                )
            self._active[key] = current + 1

    def release(self, user_id: int | None) -> None:
        key = user_id or 0
        with self._lock:
            current = self._active.get(key, 0)
            if current <= 1:
                self._active.pop(key, None)
            else:
                self._active[key] = current - 1
