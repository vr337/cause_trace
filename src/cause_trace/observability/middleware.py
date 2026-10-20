"""请求追踪中间件（T-28 / FR-18）。

request_id 贯穿前后端：调用方带了就沿用（跨服务串联），没带就生成；
响应头回写，方便前端把错误提示与日志对上。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from cause_trace.observability.logging import LogContext, log_event
from cause_trace.observability.metrics import STAGE_DURATION

REQUEST_ID_HEADER = "X-Request-Id"
SKIP_PATHS = {"/healthz", "/metrics"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or f"req-{uuid.uuid4().hex[:16]}"
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id

        if request.url.path not in SKIP_PATHS:
            elapsed = getattr(request.state, "duration_seconds", None)
            if elapsed is not None:
                STAGE_DURATION.observe(elapsed, stage=request.url.path)
            log_event(
                "INFO",
                "http_request",
                LogContext(request_id=request_id, module="http"),
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=getattr(request.state, "duration_ms", None),
            )
        return response
