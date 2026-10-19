"""sandbox-runner 服务入口（端口 7400）。

仅接受 insight-agent 调用：所有请求须携带内部令牌 ``X-Internal-Token``。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from cause_trace.config import get_settings
from cause_trace.errors import CauseTraceError
from cause_trace.sandbox.quota import QuotaManager
from cause_trace.sandbox.runner import DockerPythonRunner, ExecutionRequest, SqlRunner

app = FastAPI(title="cause_trace sandbox-runner", version="0.1.0")

_settings = get_settings()
_quota = QuotaManager(_settings)
_python_runner = DockerPythonRunner(_settings)
_sql_runner = SqlRunner(_settings)


@app.exception_handler(CauseTraceError)
async def _cause_trace_error_handler(_: Request, exc: CauseTraceError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "sandbox-runner"}


@app.post("/v1/execute")
def execute(payload: dict, x_internal_token: Annotated[str, Header()] = "") -> dict:
    if x_internal_token != _settings.sandbox_internal_token:
        raise HTTPException(status_code=403, detail="invalid internal token")

    exec_type = payload.get("exec_type")
    code = payload.get("code")
    if exec_type not in {"sql", "python"} or not isinstance(code, str):
        raise HTTPException(status_code=400, detail="exec_type 必须为 sql/python 且 code 为字符串")

    user_id = payload.get("user_id")
    timeout_s, max_rows = _quota.resolve(
        timeout_s=payload.get("timeout_s"), max_rows=payload.get("max_rows")
    )

    request = ExecutionRequest(
        exec_type=exec_type,
        code=code,
        user_id=user_id,
        timeout_s=timeout_s,
        max_rows=max_rows,
        allowed_tables=payload.get("allowed_tables"),
        params=payload.get("params") or {},
    )

    _quota.acquire(user_id)
    try:
        if exec_type == "sql":
            result = _sql_runner.run(request, timeout_s=timeout_s, max_rows=max_rows)
        else:
            result = _python_runner.run(request, timeout_s=timeout_s)
    finally:
        _quota.release(user_id)

    return result.as_dict()
