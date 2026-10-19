"""组5 接口：/metrics 暴露与 request_id 贯穿。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from cause_trace.main import app
from cause_trace.observability import REQUEST_ID_HEADER, reset_metrics

client = TestClient(app)


def test_metrics_endpoint_exposes_prometheus_text():
    reset_metrics()
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "# TYPE cause_session_total counter" in response.text
    assert "conservation_check_failed_total" in response.text


def test_request_id_is_generated_when_absent():
    response = client.get("/healthz")
    assert response.headers[REQUEST_ID_HEADER].startswith("req-")


def test_request_id_is_propagated_when_provided():
    response = client.get("/healthz", headers={REQUEST_ID_HEADER: "req-trace-123"})
    assert response.headers[REQUEST_ID_HEADER] == "req-trace-123"


def test_decomposition_failure_still_returns_request_id():
    # 业务异常与成功请求一样要能按 request_id 串起来
    response = client.post(
        "/api/v1/metrics/decomposition",
        json={"method": "regression", "factors": [{"name": "a", "base": 1, "current": 2}]},
        headers={REQUEST_ID_HEADER: "req-fail-1"},
    )
    assert response.status_code == 422
    assert response.headers[REQUEST_ID_HEADER] == "req-fail-1"
