"""insight-agent 归因主服务入口（端口 7300）。

组2 补齐 Spec 6.1 的核心 API：会话创建与查询、多轮追问、指标字典、事件窗口
匹配、假设阈值判定、What-If 推演与报告组装。

依赖 MySQL 的接口在数据库不可用时返回 503，不阻塞公式引擎、沙箱白名单等
纯计算能力。
"""

from __future__ import annotations

import json

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from cause_trace import __version__
from cause_trace.causal import BusinessEventInput, build_causal_links, match_events
from cause_trace.dictionary import (
    MetricInput,
    MetricValidationError,
    create_metric,
    list_data_sources,
    list_domains,
    list_metrics,
    register_tree_guards,
    set_decomp_rule,
    upsert_tree_node,
)
from cause_trace.db import get_engine, get_session_factory
from cause_trace.engine import Factor, Slice, decompose, shapley_decompose
from cause_trace.errors import CauseTraceError, InvalidIntentError, ReportPayloadError
from cause_trace.orchestration import (
    AnalysisPlan,
    Hypothesis,
    apply_threshold,
    board,
    clamp_hypotheses,
    parse_intent,
)
from cause_trace.orchestration.intent import fallback_hypotheses, resolve_window
from cause_trace.report.schema import schema_json, validate_report_payload
from cause_trace.session import (
    SessionInput,
    SessionValidationError,
    assemble_report,
    create_session,
    session_snapshot,
)
from cause_trace.simulation import ElasticityFit, simulate

app = FastAPI(title="cause_trace insight-agent", version=__version__)

register_tree_guards()


@app.exception_handler(CauseTraceError)
async def _cause_trace_error_handler(_: Request, exc: CauseTraceError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


def get_db() -> Session:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _ensure_db() -> None:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail=f"数据库不可用：{exc.__class__.__name__}"
        ) from exc


# ---------- Spec 6.1/6.2 API-01 创建归因会话 ----------


class WindowIn(BaseModel):
    start: str | None = None
    end: str | None = None


class SessionCreateIn(BaseModel):
    domain_id: int
    metric_id: int
    baseline: str = Field(pattern="^(dod|yoy|target)$")
    window: WindowIn | None = None
    query: str = ""
    from_dashboard: bool = False


@app.post("/api/v1/sessions", status_code=201)
def create_attribution_session(payload: SessionCreateIn, db: Session = Depends(get_db)) -> dict:
    _ensure_db()
    try:
        intent = parse_intent(
            metric_code=str(payload.metric_id),
            baseline=payload.baseline,
            window_start=payload.window.start if payload.window else None,
            window_end=payload.window.end if payload.window else None,
            raw_query=payload.query,
        )
        entity = create_session(
            db,
            SessionInput(
                user_id=0,
                domain_id=payload.domain_id,
                metric_id=payload.metric_id,
                window_start=intent.window_start,
                window_end=intent.window_end,
                baseline=intent.baseline,
            ),
        )
    except (InvalidIntentError, SessionValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()

    return {
        "session_id": entity.id,
        "intent": {
            "metric": str(payload.metric_id),
            "time_range": [intent.window_start.isoformat(), intent.window_end.isoformat()],
            "baseline": intent.baseline,
        },
        "ws_url": f"/ws/v1/sessions/{entity.id}",
        "plan": AnalysisPlan.default().as_dict(),
    }


# ---------- Spec 6.1 API-02 / API-03 ----------


@app.get("/api/v1/sessions/{session_id}")
def get_session_detail(session_id: int, db: Session = Depends(get_db)) -> dict:
    _ensure_db()
    try:
        return session_snapshot(db, session_id)
    except SessionValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class FollowupIn(BaseModel):
    query: str = Field(min_length=1)


@app.post("/api/v1/sessions/{session_id}/followup")
def followup(session_id: int, payload: FollowupIn, db: Session = Depends(get_db)) -> dict:
    """追问沿用已锁定的异动切片：继承上下文，并给出新的候选假设。"""
    _ensure_db()
    try:
        snapshot = session_snapshot(db, session_id)
    except SessionValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    hypotheses = clamp_hypotheses(fallback_hypotheses(payload.query), origin="rule")
    return {
        "session_id": session_id,
        "inherited": snapshot,
        "hypotheses": [h.content for h in hypotheses],
    }


# ---------- Spec 6.1 API-05 指标分解 ----------


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
    factors = [
        Factor(name=f.name, base=f.base, current=f.current, sign=f.sign) for f in payload.factors
    ]
    return decompose(payload.method, factors).as_dict()


@app.post("/api/v1/metrics/decomposition/shapley")
def decomposition_shapley(payload: ShapleyRequest) -> dict:
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


# ---------- 假设阈值判定 ----------


class HypothesisIn(BaseModel):
    content: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ThresholdIn(BaseModel):
    hypotheses: list[HypothesisIn] = Field(min_length=1)
    threshold: float = Field(default=0.6, ge=0.0, le=1.0)


@app.post("/api/v1/hypotheses/evaluate")
def evaluate_hypotheses(payload: ThresholdIn) -> dict:
    """置信度低于阈值的假设自动标记已排除，不进入最终结论。"""
    hypotheses = [Hypothesis(content=item.content) for item in payload.hypotheses]
    for hypothesis, item in zip(hypotheses, payload.hypotheses, strict=True):
        if item.confidence is not None:
            hypothesis.verify(item.confidence)
    return board(apply_threshold(hypotheses, threshold=payload.threshold))


# ---------- Spec 6.1 API-08 事件窗口匹配 ----------


class EventIn(BaseModel):
    name: str
    event_type: str = Field(pattern="^(promo|operation|external|fault)$")
    window_start: str
    window_end: str
    categories: list[str] = []
    channels: list[str] = []
    metrics: list[str] = []


class EventMatchIn(BaseModel):
    """异动窗口 + 待匹配的候选事件，二者分开传，避免同一个模型身兼两职。"""

    window_start: str
    window_end: str
    categories: list[str] = []
    channels: list[str] = []
    metric_code: str = ""
    events: list[EventIn] = []


@app.post("/api/v1/events/match")
def match_business_events(payload: EventMatchIn) -> dict:
    """异动窗口前后 3 日的业务事件匹配（FR-12 计算内核）。"""
    anomaly_start, anomaly_end = resolve_window(payload.window_start, payload.window_end)
    candidates = [
        BusinessEventInput(
            name=e.name,
            event_type=e.event_type,
            window_start=resolve_window(e.window_start, e.window_end)[0],
            window_end=resolve_window(e.window_start, e.window_end)[1],
            categories=tuple(e.categories),
            channels=tuple(e.channels),
            metrics=tuple(e.metrics),
        )
        for e in payload.events
    ]
    matched = match_events(
        anomaly_start,
        anomaly_end,
        candidates,
        categories=tuple(payload.categories),
        channels=tuple(payload.channels),
        metric_code=payload.metric_code,
    )
    return {
        "matched": [
            {
                "name": m.event.name,
                "event_type": m.event.event_type,
                "overlap_days": m.overlap_days,
                "relevance": m.relevance,
                "is_causal": m.is_causal,
            }
            for m in matched
        ],
        "causal_links": build_causal_links(matched),
    }


# ---------- Spec 6.1 API-06 What-If 推演 ----------


class SimulateIn(BaseModel):
    baseline_value: float = Field(gt=0)
    factor_adjustments: dict[str, float]
    elasticities: dict[str, float]


@app.post("/api/v1/sessions/{session_id}/simulate")
def what_if(session_id: int, payload: SimulateIn) -> dict:
    """基于弹性系数的多情景重算；落库由会话服务层负责。"""
    fits = {
        name: ElasticityFit(
            factor=name,
            elasticity=value,
            r_squared=0.0,
            method="empirical",
            sample_size=0,
        )
        for name, value in payload.elasticities.items()
    }
    outcome = simulate(payload.baseline_value, payload.factor_adjustments, fits)
    return {"session_id": session_id, **outcome.as_dict()}


# ---------- Spec 6.1 API-07 报告组装 ----------


class ReportIn(BaseModel):
    title: str = Field(min_length=1)
    payload: dict


@app.post("/api/v1/sessions/{session_id}/report")
def build_report(session_id: int, payload: ReportIn, db: Session = Depends(get_db)) -> dict:
    _ensure_db()
    try:
        report = assemble_report(db, session_id, payload.title, payload.payload)
    except ReportPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SessionValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {"report_id": report.id, "version": report.current_version, "status": report.status}


@app.get("/api/v1/report/schema")
def report_schema() -> dict:
    return json.loads(schema_json())


@app.post("/api/v1/report/validate")
def report_validate(payload: dict) -> dict:
    try:
        validate_report_payload(payload)
    except ReportPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"valid": True}


# ---------- 指标字典（T-05） ----------


class MetricIn(BaseModel):
    code: str
    name: str
    metric_type: str = Field(pattern="^(atomic|derived|composite)$")
    algebra: str = Field(pattern="^(additive|multiplicative)$")
    domain_id: int
    data_source_id: int
    formula: str | None = None
    unit: str | None = None
    elasticity: float | None = None


@app.get("/api/v1/metrics")
def metrics(domain_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    _ensure_db()
    return {
        "metrics": [
            {
                "id": m.id,
                "code": m.code,
                "name": m.name,
                "type": m.metric_type,
                "algebra": m.algebra,
            }
            for m in list_metrics(db, domain_id=domain_id)
        ]
    }


@app.post("/api/v1/metrics", status_code=201)
def add_metric(payload: MetricIn, db: Session = Depends(get_db)) -> dict:
    _ensure_db()
    try:
        metric = create_metric(db, MetricInput(**payload.model_dump()))
    except MetricValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"id": metric.id, "code": metric.code}


@app.get("/api/v1/domains")
def domains(db: Session = Depends(get_db)) -> dict:
    _ensure_db()
    return {
        "domains": [
            {"id": d.id, "name": d.name, "biz_line": d.biz_line} for d in list_domains(db)
        ]
    }


@app.get("/api/v1/data-sources")
def data_sources(db: Session = Depends(get_db)) -> dict:
    _ensure_db()
    # secret_ref 只返回引用键名，绝不下发任何凭据内容
    return {
        "data_sources": [
            {"id": s.id, "name": s.name, "db_name": s.db_name, "secret_ref": s.secret_ref}
            for s in list_data_sources(db)
        ]
    }


@app.post("/api/v1/metrics/{metric_id}/decomp-rule")
def upsert_decomp_rule(
    metric_id: int,
    method: str = Query(pattern="^(diff|lmdi|shapley|dupont)$"),
    default_level: int = Query(default=1, ge=1, le=5),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_db()
    try:
        rule = set_decomp_rule(db, metric_id, method, default_level=default_level)
    except MetricValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {
        "id": rule.id,
        "metric_id": rule.metric_id,
        "method": rule.method,
        "level": rule.default_level,
    }


@app.post("/api/v1/metric-tree", status_code=201)
def mount_metric_tree(
    metric_id: int = Query(),
    parent_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_db()
    try:
        node = upsert_tree_node(db, metric_id, parent_id=parent_id)
    except MetricValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {
        "node_id": node.id,
        "metric_id": node.metric_id,
        "parent_id": node.parent_id,
        "level": node.level,
    }
