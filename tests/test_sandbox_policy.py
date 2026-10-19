"""T-03：沙箱 SQL 白名单与配额单测。"""

from __future__ import annotations

import pytest

from cause_trace.errors import SandboxPolicyError
from cause_trace.sandbox import QuotaManager, validate_sql


def test_select_is_allowed_and_gets_limit():
    sql = validate_sql("SELECT channel, sum(gmv) FROM dwd_fact_trade GROUP BY channel", max_rows=100)
    assert "LIMIT 100" in sql.upper()


def test_existing_smaller_limit_is_kept():
    sql = validate_sql("SELECT * FROM dwd_fact_trade LIMIT 10", max_rows=100)
    assert "LIMIT 10" in sql.upper()


def test_larger_limit_is_truncated_to_max_rows():
    sql = validate_sql("SELECT * FROM dwd_fact_trade LIMIT 999999", max_rows=100)
    assert "LIMIT 100" in sql.upper()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE dwd_fact_trade SET gmv = 0",
        "DELETE FROM dwd_fact_trade",
        "DROP TABLE dwd_fact_trade",
        "TRUNCATE TABLE dwd_fact_trade",
        "INSERT INTO dwd_fact_trade (gmv) VALUES (1)",
        "CREATE TABLE evil (id INT)",
        "ALTER TABLE dwd_fact_trade ADD COLUMN x INT",
        "GRANT ALL ON *.* TO 'x'@'%'",
        "SELECT 1; DROP TABLE dwd_fact_trade",
    ],
)
def test_write_operations_are_blocked(sql: str):
    with pytest.raises(SandboxPolicyError) as exc_info:
        validate_sql(sql)
    assert exc_info.value.code in {"SBX_WRITE_BLOCKED", "SBX_POLICY_VIOLATION"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM information_schema.tables",
        "SELECT LOAD_FILE('/etc/passwd')",
        "SELECT * FROM dwd_fact_trade INTO OUTFILE '/tmp/x.csv'",
    ],
)
def test_dangerous_access_is_blocked(sql: str):
    with pytest.raises(SandboxPolicyError):
        validate_sql(sql)


def test_table_whitelist_blocks_unknown_table():
    with pytest.raises(SandboxPolicyError) as exc_info:
        validate_sql(
            "SELECT * FROM secret_table", allowed_tables=["dwd_fact_trade"]
        )
    assert "白名单" in exc_info.value.message


def test_table_whitelist_allows_registered_table():
    sql = validate_sql(
        "SELECT order_id FROM warehouse.dwd_fact_trade",
        allowed_tables=["warehouse.dwd_fact_trade"],
    )
    assert "LIMIT" in sql.upper()


def test_empty_sql_is_rejected():
    with pytest.raises(SandboxPolicyError):
        validate_sql("   ")


def test_quota_enforces_user_concurrency():
    manager = QuotaManager()
    for _ in range(manager.defaults.max_concurrent):
        manager.acquire(user_id=7)
    with pytest.raises(SandboxPolicyError) as exc_info:
        manager.acquire(user_id=7)
    assert exc_info.value.code == "SBX_QUOTA_EXCEEDED"

    manager.release(user_id=7)
    manager.acquire(user_id=7)


def test_quota_clamps_requested_values():
    manager = QuotaManager()
    timeout_s, max_rows = manager.resolve(timeout_s=9999, max_rows=10**7)
    assert timeout_s == manager.defaults.timeout_s
    assert max_rows == manager.defaults.max_rows
