"""T-01：ORM 元数据与 Spec 5.1/5.2 表清单的一致性。"""

from __future__ import annotations

from cause_trace.db import models  # noqa: F401 - 触发模型注册
from cause_trace.db.base import Base

EXPECTED_TABLES = {
    # 5.1 核心归因域
    "metric_domain",
    "data_source",
    "metric",
    "decomp_rule",
    "metric_tree_node",
    "attribution_session",
    "hypothesis",
    "evidence",
    "business_event",
    "causal_link",
    "simulation",
    "report",
    # 5.2 治理与资产域
    "report_version",
    "report_annotation",
    "audit_log",
    "sandbox_quota",
    "anomaly_threshold",
    "subscription",
    "injection_config",
    "injection_truth",
}


def test_all_spec_tables_are_registered():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_metric_has_elasticity_column():
    # v0.3.1 修正项 N-01：经验弹性系数必须可空
    column = Base.metadata.tables["metric"].c.elasticity
    assert column.nullable is True


def test_data_source_secret_ref_is_reference_only():
    # ADR-06：secret_ref 只存引用键名，禁明文，长度限制防止塞入整段密文
    column = Base.metadata.tables["data_source"].c.secret_ref
    assert column.nullable is False
    assert column.type.length == 255


def test_critical_indexes_exist():
    session_indexes = {
        index.name for index in Base.metadata.tables["attribution_session"].indexes
    }
    assert "ix_attribution_session_user_status" in session_indexes
    assert "ix_hypothesis_session_status" in {
        index.name for index in Base.metadata.tables["hypothesis"].indexes
    }
    assert "ix_audit_log_request" in {
        index.name for index in Base.metadata.tables["audit_log"].indexes
    }
