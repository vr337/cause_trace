"""组4 接口：导出、审计鉴权、配额与异动判定。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from cause_trace.main import app
from cause_trace.report import empty_section_payload

client = TestClient(app)

PAYLOAD = empty_section_payload(
    {
        "title": "GMV 下滑归因",
        "domain_id": 1,
        "metric_id": 1,
        "window_start": "2026-08-12",
        "window_end": "2026-08-18",
        "baseline": "dod",
    },
    {"background": {"summary": "GMV 日环比 -12.3%"}},
)


def test_export_markdown_returns_attachment():
    response = client.post("/api/v1/reports/export", json={"format": "markdown", "payload": PAYLOAD})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert "GMV 下滑归因" in response.text


def test_export_excel_returns_xlsx():
    response = client.post("/api/v1/reports/export", json={"format": "excel", "payload": PAYLOAD})
    assert response.status_code == 200
    assert response.content[:2] == b"PK"  # xlsx 本质是 zip


def test_export_rejects_invalid_payload():
    broken = dict(PAYLOAD)
    broken["sections"] = PAYLOAD["sections"][:3]
    response = client.post("/api/v1/reports/export", json={"format": "markdown", "payload": broken})
    assert response.status_code == 422


def test_export_rejects_unknown_format():
    response = client.post("/api/v1/reports/export", json={"format": "docx", "payload": PAYLOAD})
    assert response.status_code == 422


def test_audit_requires_admin_scope():
    assert client.get("/api/v1/admin/audit").status_code == 401
    assert (
        client.get("/api/v1/admin/audit", headers={"X-User-Id": "7", "X-Scopes": "read:insight-agent"}).status_code
        == 403
    )


def test_admin_scope_grants_audit_access():
    response = client.get(
        "/api/v1/admin/audit", headers={"X-User-Id": "1", "X-Scopes": "admin:cause"}
    )
    # 无数据库时返回 503，而不是鉴权失败
    assert response.status_code == 503


def test_quota_resolution_without_database_returns_503():
    response = client.get("/api/v1/admin/sandbox-quota/resolve")
    assert response.status_code == 503


def test_anomaly_check_uses_threshold():
    hit = client.post("/api/v1/anomaly/check", params={"change_rate": -0.15, "threshold_value": -0.10})
    miss = client.post("/api/v1/anomaly/check", params={"change_rate": -0.03, "threshold_value": -0.10})

    assert hit.json()["is_anomalous"] is True
    assert miss.json()["is_anomalous"] is False
