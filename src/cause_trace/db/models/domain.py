"""指标域与指标字典模型（Spec 5.1）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cause_trace.db.base import Base


class MetricDomain(Base):
    """METRIC_DOMAIN：指标域（业务线隔离的顶层组织单元）。"""

    __tablename__ = "metric_domain"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    biz_line: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="enabled")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class DataSource(Base):
    """DATA_SOURCE：数仓数据源，只读账号 + 密钥引用。"""

    __tablename__ = "data_source"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    db_type: Mapped[str] = mapped_column(String(32), nullable=False, default="mysql")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=3306)
    db_name: Mapped[str] = mapped_column(String(128), nullable=False)
    account: Mapped[str] = mapped_column(String(128), nullable=False)
    # ADR-06：只存密钥引用键名，禁明文
    secret_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    table_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Metric(Base):
    """METRIC：原子/派生/复合指标定义。"""

    __tablename__ = "metric"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("metric_domain.id"), nullable=False
    )
    data_source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("data_source.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(32), nullable=False)
    algebra: Mapped[str] = mapped_column(String(32), nullable=False)
    formula: Mapped[str | None] = mapped_column(String(512), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Spec 5.1 / 15.1 方法二：经验弹性系数，仅降级时使用
    elasticity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="enabled")


class DecompRule(Base):
    """DECOMP_RULE：指标的拆解规则。"""

    __tablename__ = "decomp_rule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("metric.id"), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    default_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class MetricTreeNode(Base):
    """METRIC_TREE_NODE：指标树层级结构（自引用）。"""

    __tablename__ = "metric_tree_node"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("metric.id"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("metric_tree_node.id"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
