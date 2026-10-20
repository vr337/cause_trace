"""业务全链路闭环与 E2E 验收。

在真实 MySQL 上跑完「异动注入 → 检测 → LMDI 拆解 → 假设 → 因果 → 仿真 → 策略
→ 报告组装」整条链路，并验证守恒性在真实浮点数据下绝对闭环。

跳过条件同 test_integration_mysql.py：需要 CAUSE_TEST_MYSQL=1 与独立库。
"""

from __future__ import annotations

import json
import math
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from cause_trace.db.base import Base

pytestmark = pytest.mark.skipif(
    os.environ.get("CAUSE_TEST_MYSQL") != "1",
    reason="需要设置 CAUSE_TEST_MYSQL=1 并指向真实 MySQL",
)


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("CAUSE_DATABASE_URL")
    assert url, "CAUSE_TEST_MYSQL=1 时必须提供 CAUSE_DATABASE_URL"
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def schema(engine):
    from cause_trace.db import models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(schema) -> Session:
    connection = schema.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="module")
def client(schema):
    """指向同一引擎的 API 客户端，让 E2E 走真实 HTTP 层而不是直接调函数。"""
    from cause_trace import main
    from cause_trace.db import base

    main.get_engine.cache_clear() if hasattr(main.get_engine, "cache_clear") else None
    original = base.get_engine
    base.get_engine = lambda: schema
    main.get_engine = lambda: schema
    try:
        yield TestClient(main.app)
    finally:
        base.get_engine = original
        main.get_engine = original


@pytest.fixture(scope="module")
def seeded(schema):
    """灌入指标域、数据源、指标、拆解规则，全链路共用。"""
    from cause_trace.db import models  # noqa: F401

    session = sessionmaker(bind=schema, expire_on_commit=False)()
    session.execute(
        text("INSERT INTO metric_domain (name, biz_line, status) VALUES ('电商域', '电商', 'enabled')")
    )
    session.execute(
        text(
            "INSERT INTO data_source (name, db_type, host, port, db_name, account, secret_ref, is_readonly) "
            "VALUES ('wh', 'mysql', '127.0.0.1', 3306, 'warehouse', 'cause_ro', 'P', 1)"
        )
    )
    for code, name, mtype, algebra in (
        ("gmv", "GMV", "composite", "multiplicative"),
        ("visitors", "访客数", "atomic", "additive"),
        ("cvr", "转化率", "derived", "multiplicative"),
        ("aov", "客单价", "derived", "multiplicative"),
    ):
        session.execute(
            text(
                "INSERT INTO metric (domain_id, data_source_id, code, name, metric_type, algebra, status) "
                "VALUES (1, 1, :c, :n, :t, :a, 'enabled')"
            ),
            {"c": code, "n": name, "t": mtype, "a": algebra},
        )
    session.execute(text("INSERT INTO decomp_rule (metric_id, method, default_level) VALUES (1, 'lmdi', 2)"))
    session.commit()
    session.close()
    return schema


# ---------- 任务一：真实异动注入与全链路 ----------


def test_injection_writes_ground_truth_to_mysql(db: Session):
    from cause_trace.dbmock import ECOMMERCE_GMV, inject_values, persist_injection

    rows = [
        {"dt": "2026-08-11", "channel": "douyin", "value": 0.024},
        {"dt": "2026-08-12", "channel": "douyin", "value": 0.024},
        {"dt": "2026-08-12", "channel": "search", "value": 0.024},
    ]
    result = inject_values(rows, ECOMMERCE_GMV.injection, dimension_field="channel")
    config = persist_injection(db, ECOMMERCE_GMV.injection, result)

    stored = db.execute(
        text("SELECT amplitude, seed FROM injection_config WHERE id = :id"), {"id": config.id}
    ).one()
    assert float(stored[0]) == pytest.approx(-0.35)
    assert stored[1] == 42

    truth_count = db.execute(
        text("SELECT COUNT(*) FROM injection_truth WHERE config_id = :id"), {"id": config.id}
    ).scalar_one()
    assert truth_count == 1


def test_detection_locates_injected_channel():
    from cause_trace.dbmock import ECOMMERCE_GMV, detect_anomaly, generate_daily_rows, inject_values

    rows = generate_daily_rows(ECOMMERCE_GMV, start=date(2026, 8, 1), days=30)
    inject_values(rows, ECOMMERCE_GMV.injection, dimension_field="channel")

    detected = detect_anomaly(
        rows,
        dimension_field="channel",
        window=(ECOMMERCE_GMV.injection.window_start, ECOMMERCE_GMV.injection.window_end),
    )
    assert [item["dimension_value"] for item in detected] == ["douyin"]


def test_conservation_holds_on_real_float_data():
    """守恒性硬验收：千万级 GMV 连乘后，残差必须严格为 0。"""
    from cause_trace.engine import Factor, lmdi_decompose

    # 真实量级的 GMV 分解：访客数 1 千万级 × 转化率 × 客单价
    result = lmdi_decompose(
        [
            Factor("visitors", 10_482_311.0, 9_236_774.0),
            Factor("cvr", 0.0231, 0.0187),
            Factor("aov", 185.42, 191.08),
        ]
    )

    assert result.conserved
    assert result.residual == 0.0
    # 千万级数据下双精度本身的表示精度约 1e-9 相对量，即 1e-2 绝对值；
    # 用相对容差判断，否则会把浮点表示极限误判成算法误差。
    assert math.fsum(c.contribution for c in result.contributions) == pytest.approx(
        result.total_delta, rel=1e-12
    )
    assert math.isfinite(result.total_base)


def test_conservation_rejects_deliberately_broken_data():
    """反例：人为制造残差必须被拦下，禁止出图与入报告。"""
    from cause_trace.engine import validate_conservation
    from cause_trace.errors import ConservationError

    with pytest.raises(ConservationError) as exc_info:
        validate_conservation(total_delta=1_000_000.0, contributions=[600_000.0, 399_000.0])
    assert exc_info.value.code == "BIZ_CONSERVATION_FAILED"


def test_api_decomposition_conserves(client: TestClient, seeded):
    response = client.post(
        "/api/v1/metrics/decomposition",
        json={
            "method": "lmdi",
            "factors": [
                {"name": "visitors", "base": 10_482_311, "current": 9_236_774},
                {"name": "cvr", "base": 0.0231, "current": 0.0187},
                {"name": "aov", "base": 185.42, "current": 191.08},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conserved"] is True
    assert body["residual"] == 0.0


def test_full_chain_session_to_report(client: TestClient, seeded, db: Session):
    """真实 HTTP 层跑：建会话 → 查详情 → 组装报告 → 查版本 → 对比版本。"""
    created = client.post(
        "/api/v1/sessions",
        json={
            "domain_id": 1,
            "metric_id": 1,
            "baseline": "dod",
            "window": {"start": "2026-08-12", "end": "2026-08-18"},
            "query": "为什么上周 GMV 下滑",
        },
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]
    assert len(created.json()["plan"]["steps"]) == 8

    detail = client.get(f"/api/v1/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["current_stage"] == "intent_parse"

    def payload(title: str, summary: str) -> dict:
        from cause_trace.report import empty_section_payload

        return empty_section_payload(
            {
                "title": title,
                "domain_id": 1,
                "metric_id": 1,
                "window_start": "2026-08-12",
                "window_end": "2026-08-18",
                "baseline": "dod",
            },
            {"background": {"summary": summary}},
        )

    first = client.post(
        f"/api/v1/sessions/{session_id}/report",
        json={"title": "GMV 下滑归因 v1", "payload": payload("GMV 下滑归因 v1", "GMV 日环比 -12.3%")},
    )
    assert first.status_code == 200, first.text
    report_id = first.json()["report_id"]

    second = client.post(
        f"/api/v1/sessions/{session_id}/report",
        json={"title": "GMV 下滑归因 v2", "payload": payload("GMV 下滑归因 v2", "定位到抖音渠道转化率 -35%")},
    )
    assert second.status_code == 200

    versions = client.get(f"/api/v1/reports/{report_id}/versions").json()["versions"]
    assert [item["version"] for item in versions] == [2, 3]

    diff = client.get(
        f"/api/v1/reports/{report_id}/versions/diff",
        params={"from": 2, "to": 3},
    ).json()
    assert diff["changed"] == ["background"]
    assert diff["title_changed"] is True


def test_external_event_enters_causal_chain(client: TestClient, seeded, db: Session):
    """大事件日历里注入窗内的事件必须进因果链。"""
    db.execute(
        text(
            "INSERT INTO business_event (name, event_type, window_start, window_end, scope, related_metric_ids) "
            "VALUES ('竞品A百亿补贴', 'external', '2026-08-12 00:00:00', '2026-08-13 23:59:59', "
            "'{\"categories\": [\"手机数码\"], \"channels\": [\"douyin\"]}', '[1]')"
        )
    )
    db.flush()

    response = client.post(
        "/api/v1/events/match",
        json={
            "window_start": "2026-08-12",
            "window_end": "2026-08-18",
            "categories": ["手机数码"],
            "channels": ["douyin"],
            "metric_code": "gmv",
            "events": [
                {
                    "name": "竞品A百亿补贴",
                    "event_type": "external",
                    "window_start": "2026-08-12",
                    "window_end": "2026-08-13",
                    "categories": ["手机数码"],
                    "channels": ["douyin"],
                    "metrics": ["gmv"],
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["matched"][0]["is_causal"] is True
    assert body["causal_links"][0]["role"] == "external"


# ---------- 任务二：三格式导出 ----------


def test_three_formats_export_via_api(client: TestClient, seeded):
    from cause_trace.report import empty_section_payload

    payload = empty_section_payload(
        {
            "title": "E2E 归因报告",
            "domain_id": 1,
            "metric_id": 1,
            "window_start": "2026-08-12",
            "window_end": "2026-08-18",
            "baseline": "dod",
        },
        {"background": {"summary": "GMV 日环比 -12.3%，差异额 -1,432 万"}},
    )

    expected = {"markdown": b"# E2E", "excel": b"PK", "pdf": b"%PDF-"}
    for fmt, magic in expected.items():
        response = client.post("/api/v1/reports/export", json={"format": fmt, "payload": payload})
        assert response.status_code == 200, f"{fmt}: {response.text}"
        assert response.content.startswith(magic), fmt
        assert len(response.content) > 400, f"{fmt} 产物过小，疑似空白文件"
        assert "attachment" in response.headers["content-disposition"]


# ---------- 任务三：报告协同 ----------


def test_collaboration_annotation_and_mention(client: TestClient, seeded, db: Session):
    """A 发布报告，B 批注并 @A，验证 report_annotation 落库与版本对比 API。"""
    created = client.post(
        "/api/v1/sessions",
        json={
            "domain_id": 1,
            "metric_id": 1,
            "baseline": "dod",
            "window": {"start": "2026-08-12", "end": "2026-08-18"},
        },
    )
    session_id = created.json()["session_id"]

    from cause_trace.report import empty_section_payload

    report = client.post(
        f"/api/v1/sessions/{session_id}/report",
        json={
            "title": "协同测试报告",
            "payload": empty_section_payload(
                {
                    "title": "协同测试报告",
                    "domain_id": 1,
                    "metric_id": 1,
                    "window_start": "2026-08-12",
                    "window_end": "2026-08-18",
                    "baseline": "dod",
                }
            ),
        },
    ).json()
    report_id = report["report_id"]

    # 用户 B（id=99）批注并 @用户 A（id=7）
    annotated = client.post(
        f"/api/v1/reports/{report_id}/annotations",
        json={
            "anchor": "section_2#120",
            "content": "这里的贡献率口径需要和财务对齐 @分析师A",
            "version": report["version"],
            "user_id": 99,
            "mention_user_ids": [7],
        },
        headers={"X-User-Id": "99", "X-Scopes": "read:insight-agent"},
    )
    assert annotated.status_code == 201, annotated.text

    row = db.execute(
        text(
            "SELECT content, version, created_by, mention_user_ids, status "
            "FROM report_annotation WHERE id = :id"
        ),
        {"id": annotated.json()["id"]},
    ).one()
    assert "贡献率口径" in row[0]
    assert row[1] == report["version"]
    assert row[2] == 99
    # 原生连接把 JSON 列当字符串返回，ORM 才会反序列化成 list
    mentions = json.loads(row[3]) if isinstance(row[3], str) else row[3]
    assert 7 in (mentions or [])
    assert row[4] == "open"

    listed = client.get(f"/api/v1/reports/{report_id}/annotations").json()["annotations"]
    assert len(listed) == 1
    assert listed[0]["mention_user_ids"] == [7]


def test_version_diff_reports_missing_version(client: TestClient, seeded):
    created = client.post(
        "/api/v1/sessions",
        json={"domain_id": 1, "metric_id": 1, "baseline": "dod"},
    )
    session_id = created.json()["session_id"]

    from cause_trace.report import empty_section_payload

    report_id = client.post(
        f"/api/v1/sessions/{session_id}/report",
        json={
            "title": "版本对比",
            "payload": empty_section_payload(
                {
                    "title": "版本对比",
                    "domain_id": 1,
                    "metric_id": 1,
                    "window_start": "2026-08-12",
                    "window_end": "2026-08-18",
                    "baseline": "dod",
                }
            ),
        },
    ).json()["report_id"]

    missing = client.get(
        f"/api/v1/reports/{report_id}/versions/diff", params={"from": 2, "to": 99}
    )
    assert missing.status_code == 404
