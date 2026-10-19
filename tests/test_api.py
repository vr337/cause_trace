"""接口层冒烟测试：分解、假设判定、事件匹配、What-If 与报告校验。

这些接口不依赖数据库；依赖 MySQL 的会话/字典接口由各自的仓储测试覆盖，
并在数据库缺失时统一返回 503。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from cause_trace.main import app
from cause_trace.report import empty_section_payload

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_additive_decomposition_endpoint():
    response = client.post(
        "/api/v1/metrics/decomposition",
        json={
            "method": "diff",
            "factors": [
                {"name": "revenue", "base": 100, "current": 130},
                {"name": "cost", "base": 50, "current": 40, "sign": -1},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conserved"] is True
    assert body["total_delta"] == 40


def test_shapley_endpoint():
    response = client.post(
        "/api/v1/metrics/decomposition/shapley",
        json={
            "slices": [
                {
                    "name": "douyin",
                    "weight_base": 0.5,
                    "weight_current": 0.6,
                    "rate_base": 0.04,
                    "rate_current": 0.035,
                },
                {
                    "name": "wechat",
                    "weight_base": 0.5,
                    "weight_current": 0.4,
                    "rate_base": 0.04,
                    "rate_current": 0.035,
                },
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["conserved"] is True


def test_invalid_method_returns_422():
    response = client.post(
        "/api/v1/metrics/decomposition",
        json={"method": "regression", "factors": [{"name": "a", "base": 1, "current": 2}]},
    )
    assert response.status_code == 422


def test_hypotheses_evaluate_excludes_low_confidence():
    response = client.post(
        "/api/v1/hypotheses/evaluate",
        json={
            "hypotheses": [
                {"content": "渠道结构恶化", "confidence": 0.87},
                {"content": "大促退款率上升", "confidence": 0.34},
            ],
            "threshold": 0.6,
        },
    )
    assert response.status_code == 200
    body = response.json()
    statuses = {h["content"]: h["status"] for h in body["hypotheses"]}
    assert statuses["渠道结构恶化"] == "verified"
    assert statuses["大促退款率上升"] == "excluded"
    assert body["excluded"] == 1


def test_event_match_endpoint_finds_causal_event():
    response = client.post(
        "/api/v1/events/match",
        json={
            "window_start": "2026-08-15",
            "window_end": "2026-08-18",
            "categories": ["家电"],
            "metric_code": "gmv",
            "events": [
                {
                    "name": "818家电节",
                    "event_type": "promo",
                    "window_start": "2026-08-12",
                    "window_end": "2026-08-14",
                    "categories": ["家电"],
                    "metrics": ["gmv"],
                },
                {
                    "name": "无关的支付抖动",
                    "event_type": "fault",
                    "window_start": "2026-08-16",
                    "window_end": "2026-08-16",
                    "categories": ["生鲜"],
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert [m["name"] for m in body["matched"]] == ["818家电节", "无关的支付抖动"]
    assert body["matched"][0]["is_causal"] is True
    assert body["matched"][1]["is_causal"] is False
    assert [link["name"] for link in body["causal_links"]] == ["818家电节"]


def test_event_match_endpoint_with_no_candidates():
    response = client.post(
        "/api/v1/events/match",
        json={"window_start": "2026-08-15", "window_end": "2026-08-18", "events": []},
    )
    assert response.status_code == 200
    assert response.json() == {"matched": [], "causal_links": []}


def test_what_if_endpoint_applies_elasticity():
    response = client.post(
        "/api/v1/sessions/1/simulate",
        json={
            "baseline_value": 1_000_000,
            "factor_adjustments": {"douyin_budget": 1.2},
            "elasticities": {"douyin_budget": 1.2},
        },
    )
    assert response.status_code == 200
    scenario = response.json()["scenarios"][0]
    assert scenario["delta_rate"] == 0.24
    assert scenario["metric_value"] == 1_240_000


def test_what_if_rejects_non_positive_baseline():
    response = client.post(
        "/api/v1/sessions/1/simulate",
        json={"baseline_value": 0, "factor_adjustments": {}, "elasticities": {}},
    )
    assert response.status_code == 422


def test_report_validate_accepts_seven_sections():
    payload = empty_section_payload(
        {
            "title": "GMV 下滑归因",
            "domain_id": 1,
            "metric_id": 1,
            "window_start": "2026-08-08",
            "window_end": "2026-08-15",
            "baseline": "dod",
        }
    )
    assert client.post("/api/v1/report/validate", json=payload).json() == {"valid": True}


def test_report_validate_rejects_missing_section():
    payload = empty_section_payload(
        {
            "title": "GMV 下滑归因",
            "domain_id": 1,
            "metric_id": 1,
            "window_start": "2026-08-08",
            "window_end": "2026-08-15",
            "baseline": "dod",
        }
    )
    payload["sections"].pop()
    response = client.post("/api/v1/report/validate", json=payload)
    assert response.status_code == 422


def test_session_endpoints_return_503_without_database():
    # 未配置 MySQL 时应给出明确提示，而不是把连接异常透传给前端
    response = client.post(
        "/api/v1/sessions",
        json={"domain_id": 1, "metric_id": 1, "baseline": "dod"},
    )
    assert response.status_code == 503
    assert "数据库不可用" in response.json()["detail"]
