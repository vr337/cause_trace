"""组1 接口冒烟：健康检查、分解接口与守恒失败的错误码。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from cause_trace.main import app

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
