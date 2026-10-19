"""insight-agent 归因主服务入口（端口 7300）。

组1 仅落地健康检查、保守恒校验的分解接口与报告 payload schema 接口，
会话编排等能力在组2（T-05~T-11）扩展。
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cause_trace import __version__
from cause_trace.engine import Factor, Slice, decompose, shapley_decompose
from cause_trace.errors import CauseTraceError
from cause_trace.report.schema import schema_json, validate_report_payload

app = FastAPI(title="cause_trace insight-agent", version=__version__)


@app.exception_handler(CauseTraceError)
async def _cause_trace_error_handler(_: Request, exc: CauseTraceError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


class FactorIn(BaseModel):
    name: str
    base: float
    current: float
    sign: int = 1


class DecomposeRequest(BaseModel):
    method: str = Field(default="diff", pattern="^(diff|lmdi|dupont|shapley)$")
    factors: list[FactorIn] = Field(min_length=1)


class SliceIn(BaseModel):
    name: str
    weight_base: float
    weight_current: float
    rate_base: float
    rate_current: float


class ShapleyRequest(BaseModel):
    slices: list[SliceIn] = Field(min_length=1)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/api/v1/metrics/decomposition")
def decomposition(payload: DecomposeRequest) -> dict:
    """因子级分解（API-05 的计算内核）；守恒失败返回 BIZ_CONSERVATION_FAILED。"""
    factors = [
        Factor(name=f.name, base=f.base, current=f.current, sign=f.sign) for f in payload.factors
    ]
    return decompose(payload.method, factors).as_dict()


@app.post("/api/v1/metrics/decomposition/shapley")
def decomposition_shapley(payload: ShapleyRequest) -> dict:
    """维度下钻 Shapley 分解，返回 mix / rate 双效应。"""
    slices = [
        Slice(
            name=s.name,
            weight_base=s.weight_base,
            weight_current=s.weight_current,
            rate_base=s.rate_base,
            rate_current=s.rate_current,
        )
        for s in payload.slices
    ]
    result = shapley_decompose(slices)
    return {
        "method": result.method,
        "total_base": result.total_base,
        "total_current": result.total_current,
        "total_delta": result.total_delta,
        "residual": result.residual,
        "conserved": result.conserved,
        "slices": [
            {
                "slice": s.slice,
                "mix_contribution": s.mix_contribution,
                "rate_contribution": s.rate_contribution,
                "contribution": s.contribution,
                "contribution_rate": s.contribution_rate,
                "delta": s.delta,
            }
            for s in result.slices
        ],
    }


@app.get("/api/v1/report/schema")
def report_schema() -> dict:
    return json.loads(schema_json())


@app.post("/api/v1/report/validate")
def report_validate(payload: dict) -> dict:
    validate_report_payload(payload)
    return {"valid": True}
