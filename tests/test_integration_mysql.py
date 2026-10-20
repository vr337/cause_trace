"""真实 MySQL 集成测试。

默认跳过；本地起了 MySQL 后显式开启：

    CAUSE_TEST_MYSQL=1 \
    CAUSE_DATABASE_URL="mysql+pymysql://cause:causepass@127.0.0.1:3306/cause_it?charset=utf8mb4" \
    uv run pytest tests/test_integration_mysql.py

覆盖 SQLite 测不到的部分：bigint 自增、JSON 列、迁移脚本与 ORM 元数据是否一致、
以及种子数据下的完整会话链路。库表用 Base.metadata 直接建，跑完整库 drop，
不碰开发用的 cause 库。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from cause_trace.db.base import Base

pytestmark = pytest.mark.skipif(
    os.environ.get("CAUSE_TEST_MYSQL") != "1",
    reason="需要设置 CAUSE_TEST_MYSQL=1 并指向真实 MySQL",
)


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("CAUSE_DATABASE_URL")
    assert url, "CAUSE_TEST_MYSQL=1 时必须提供 CAUSE_DATABASE_URL"
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def schema(engine):
    """建一次库表，全部用例共用；结束后整库 drop。"""
    from cause_trace.db import models  # noqa: F401 - 注册元数据

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def session(schema) -> Session:
    """每个用例独立事务，结束回滚，数据不跨用例残留。"""
    connection = schema.connect()
    transaction = connection.begin()
    db = sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _seed(db: Session) -> tuple[int, int, int]:
    """插入指标域、数据源与指标，返回三者 id。"""
    db.execute(
        text("INSERT INTO metric_domain (name, biz_line, status) VALUES (:n, :b, 'enabled')"),
        {"n": "集成测试域", "b": "电商"},
    )
    domain_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
    db.execute(
        text(
            "INSERT INTO data_source (name, db_type, host, port, db_name, account, secret_ref, is_readonly) "
            "VALUES ('wh', 'mysql', '127.0.0.1', 3306, 'warehouse', 'cause_ro', 'WH_PASS', 1)"
        )
    )
    source_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
    db.execute(
        text(
            "INSERT INTO metric (domain_id, data_source_id, code, name, metric_type, algebra, formula, elasticity, status) "
            "VALUES (:d, :s, 'gmv_it', 'GMV', 'composite', 'multiplicative', 'a*b*c', 1.2, 'enabled')"
        ),
        {"d": domain_id, "s": source_id},
    )
    metric_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
    db.flush()
    return domain_id, source_id, metric_id


def test_bigint_autoincrement_works(session: Session):
    domain_id, source_id, metric_id = _seed(session)
    assert all(isinstance(value, int) and value > 0 for value in (domain_id, source_id, metric_id))


def test_json_column_roundtrip(session: Session):
    domain_id, _, metric_id = _seed(session)
    now = datetime(2026, 8, 15, 12, 0, 0)
    session.execute(
        text(
            "INSERT INTO attribution_session (user_id, domain_id, metric_id, window_start, window_end, baseline, status) "
            "VALUES (7, :d, :m, :s, :e, 'dod', 'running')"
        ),
        {"d": domain_id, "m": metric_id, "s": now - timedelta(days=7), "e": now},
    )
    session_id = session.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()

    session.execute(
        text(
            "INSERT INTO report (session_id, title, payload, status, current_version) "
            "VALUES (:sid, :t, :p, 'draft', 1)"
        ),
        {"sid": session_id, "t": "集成报告", "p": '{"meta": {"title": "集成报告"}, "sections": []}'},
    )
    session.flush()

    payload = session.execute(
        text("SELECT payload FROM report WHERE title = '集成报告'")
    ).scalar_one()
    # PyMySQL 原生连接把 JSON 列当字符串返回，ORM 才会自动反序列化
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["meta"]["title"] == "集成报告"


def test_decimal_columns_keep_precision(session: Session):
    _, _, metric_id = _seed(session)
    session.execute(
        text("UPDATE metric SET elasticity = :e WHERE id = :id"),
        {"e": "1.234567", "id": metric_id},
    )
    session.flush()

    stored = session.execute(
        text("SELECT elasticity FROM metric WHERE id = :id"), {"id": metric_id}
    ).scalar_one()
    assert float(stored) == pytest.approx(1.234567, abs=1e-6)


def test_orm_metadata_matches_migration_tables(schema):
    """迁移建的库与 ORM 声明的表/列必须一致，防止「改了模型忘改迁移」。"""
    inspector = inspect(schema)
    existing = set(inspector.get_table_names())

    assert set(Base.metadata.tables) <= existing

    for table in Base.metadata.sorted_tables:
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        declared = {column.name for column in table.columns}
        assert declared <= actual, f"{table.name} 缺列：{declared - actual}"


def test_composite_index_exists(schema):
    inspector = inspect(schema)
    names = {index["name"] for index in inspector.get_indexes("attribution_session")}
    assert "ix_attribution_session_user_status" in names

    audit_names = {index["name"] for index in inspector.get_indexes("audit_log")}
    assert {"ix_audit_log_request", "ix_audit_log_user_time"} <= audit_names


def test_full_session_chain_on_mysql(session: Session):
    """会话 → 假设 → 证据 → 因果链 → 报告版本快照，在 MySQL 上完整跑一遍。"""
    domain_id, _, metric_id = _seed(session)
    now = datetime(2026, 8, 15, 12, 0, 0)

    session.execute(
        text(
            "INSERT INTO attribution_session (user_id, domain_id, metric_id, window_start, window_end, baseline, status, current_stage) "
            "VALUES (7, :d, :m, :s, :e, 'dod', 'running', 'decompose')"
        ),
        {"d": domain_id, "m": metric_id, "s": now - timedelta(days=7), "e": now},
    )
    session_id = session.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()

    session.execute(
        text(
            "INSERT INTO hypothesis (session_id, content, origin, status, confidence) "
            "VALUES (:sid, '渠道结构恶化', 'llm', 'verified', 0.87)"
        ),
        {"sid": session_id},
    )
    hypothesis_id = session.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()

    session.execute(
        text(
            "INSERT INTO evidence (hypothesis_id, exec_type, exec_code, exec_result, p_value, contribution, runner_task_id, duration_ms) "
            "VALUES (:hid, 'sql', 'SELECT 1', :r, 0.001, -0.32, 'sbx-it-1', 320)"
        ),
        {"hid": hypothesis_id, "r": '{"rows": 12}'},
    )
    session.execute(
        text(
            "INSERT INTO causal_link (session_id, hypothesis_id, role, contribution, summary) "
            "VALUES (:sid, :hid, 'internal', -0.32, '渠道结构恶化')"
        ),
        {"sid": session_id, "hid": hypothesis_id},
    )
    session.execute(
        text(
            "INSERT INTO report (session_id, title, payload, status, current_version) "
            "VALUES (:sid, 'MySQL 集成报告', :p, 'draft', 1)"
        ),
        {"sid": session_id, "p": '{"meta": {}, "sections": []}'},
    )
    report_id = session.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
    session.execute(
        text(
            "INSERT INTO report_version (report_id, version, payload, created_by) "
            "VALUES (:rid, 2, :p, 7)"
        ),
        {"rid": report_id, "p": '{"meta": {}, "sections": []}'},
    )
    session.flush()

    counts = {
        table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        for table in (
            "attribution_session",
            "hypothesis",
            "evidence",
            "causal_link",
            "report_version",
        )
    }
    assert all(count == 1 for count in counts.values()), counts
