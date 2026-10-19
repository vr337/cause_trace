"""初始化 cause 库（Spec 5.1 + 5.2 全部表与关键索引）。

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_domain",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("biz_line", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="enabled"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "data_source",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("db_type", sa.String(32), nullable=False, server_default="mysql"),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="3306"),
        sa.Column("db_name", sa.String(128), nullable=False),
        sa.Column("account", sa.String(128), nullable=False),
        # ADR-06：只存密钥引用键名
        sa.Column("secret_ref", sa.String(255), nullable=False),
        sa.Column("table_scope", sa.JSON(), nullable=True),
        sa.Column("is_readonly", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "metric",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("domain_id", sa.BigInteger(), sa.ForeignKey("metric_domain.id"), nullable=False),
        sa.Column("data_source_id", sa.BigInteger(), sa.ForeignKey("data_source.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("metric_type", sa.String(32), nullable=False),
        sa.Column("algebra", sa.String(32), nullable=False),
        sa.Column("formula", sa.String(512), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("elasticity", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="enabled"),
    )

    op.create_table(
        "decomp_rule",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metric_id", sa.BigInteger(), sa.ForeignKey("metric.id"), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("default_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("params", sa.JSON(), nullable=True),
    )

    op.create_table(
        "metric_tree_node",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metric_id", sa.BigInteger(), sa.ForeignKey("metric.id"), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), sa.ForeignKey("metric_tree_node.id"), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "attribution_session",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        # chat 库表，逻辑外键不建物理约束
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("domain_id", sa.BigInteger(), sa.ForeignKey("metric_domain.id"), nullable=False),
        sa.Column("metric_id", sa.BigInteger(), sa.ForeignKey("metric.id"), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("baseline", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_attribution_session_user_status",
        "attribution_session",
        ["user_id", "status", "created_at"],
    )

    op.create_table(
        "hypothesis",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id", sa.BigInteger(), sa.ForeignKey("attribution_session.id"), nullable=False
        ),
        sa.Column("content", sa.String(1024), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False, server_default="llm"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("exclude_reason", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hypothesis_session_status", "hypothesis", ["session_id", "status"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hypothesis_id", sa.BigInteger(), sa.ForeignKey("hypothesis.id"), nullable=False),
        sa.Column("exec_type", sa.String(16), nullable=False),
        sa.Column("exec_code", sa.Text(), nullable=False),
        sa.Column("exec_result", sa.JSON(), nullable=True),
        sa.Column("p_value", sa.Numeric(10, 8), nullable=True),
        sa.Column("contribution", sa.Numeric(10, 6), nullable=True),
        sa.Column("runner_task_id", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_evidence_hypothesis", "evidence", ["hypothesis_id"])

    op.create_table(
        "business_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("related_metric_ids", sa.JSON(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_business_event_window", "business_event", ["window_start", "window_end"])

    op.create_table(
        "causal_link",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id", sa.BigInteger(), sa.ForeignKey("attribution_session.id"), nullable=False
        ),
        sa.Column("event_id", sa.BigInteger(), sa.ForeignKey("business_event.id"), nullable=True),
        sa.Column("hypothesis_id", sa.BigInteger(), sa.ForeignKey("hypothesis.id"), nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("contribution", sa.Numeric(10, 6), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_causal_link_session", "causal_link", ["session_id"])

    op.create_table(
        "simulation",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id", sa.BigInteger(), sa.ForeignKey("attribution_session.id"), nullable=False
        ),
        sa.Column("factor_params", sa.JSON(), nullable=True),
        sa.Column("scenarios", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "report",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id", sa.BigInteger(), sa.ForeignKey("attribution_session.id"), nullable=False
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_report_session", "report", ["session_id"])

    op.create_table(
        "report_version",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("report_id", sa.BigInteger(), sa.ForeignKey("report.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "report_annotation",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("report_id", sa.BigInteger(), sa.ForeignKey("report.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("anchor", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mention_user_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_request", "audit_log", ["request_id"])
    op.create_index("ix_audit_log_user_time", "audit_log", ["user_id", "created_at"])

    op.create_table(
        "sandbox_quota",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("cpu_core", sa.Numeric(6, 2), nullable=True),
        sa.Column("memory_mb", sa.Integer(), nullable=True),
        sa.Column("timeout_s", sa.Integer(), nullable=True),
        sa.Column("max_concurrent", sa.Integer(), nullable=True),
        sa.Column("max_rows", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "anomaly_threshold",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metric_id", sa.BigInteger(), sa.ForeignKey("metric.id"), nullable=False),
        sa.Column("rule_type", sa.String(16), nullable=False),
        sa.Column("threshold_value", sa.Numeric(10, 6), nullable=False),
        sa.Column("alarm_level", sa.String(16), nullable=True),
        sa.Column("notify_channels", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "subscription",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("frequency", sa.String(32), nullable=True),
        sa.Column("channel", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled"),
    )

    op.create_table(
        "injection_config",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scenario_code", sa.String(64), nullable=False),
        sa.Column("metric_id", sa.BigInteger(), nullable=False),
        sa.Column("dimension_code", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("amplitude", sa.Numeric(10, 6), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled"),
    )

    op.create_table(
        "injection_truth",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "config_id", sa.BigInteger(), sa.ForeignKey("injection_config.id"), nullable=False
        ),
        sa.Column("dimension_value", sa.String(128), nullable=False),
        sa.Column("expected_effect", sa.String(255), nullable=True),
    )
