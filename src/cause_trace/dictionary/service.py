"""指标字典与指标树（T-05 / FR-03）。

指标树的父子关系直接决定分解口径，因此写入时校验：同一父节点下不允许出现
重复指标，避免一次拆解里同一因子被算两遍、破坏守恒。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cause_trace.db.models.domain import (
    DataSource,
    DecompRule,
    Metric,
    MetricDomain,
    MetricTreeNode,
)

VALID_METRIC_TYPES = {"atomic", "derived", "composite"}
VALID_ALGEBRAS = {"additive", "multiplicative"}
VALID_METHODS = {"diff", "lmdi", "shapley", "dupont"}
MAX_TREE_DEPTH = 5


class MetricValidationError(ValueError):
    """指标字典输入不合法，由接口层转成 400。"""


@dataclass(frozen=True)
class MetricInput:
    code: str
    name: str
    metric_type: str
    algebra: str
    domain_id: int
    data_source_id: int
    formula: str | None = None
    unit: str | None = None
    elasticity: float | None = None


def _validate_metric(payload: MetricInput) -> None:
    if not payload.code or not payload.code.strip():
        raise MetricValidationError("指标编码不能为空")
    if payload.metric_type not in VALID_METRIC_TYPES:
        raise MetricValidationError(f"指标类型必须是 {sorted(VALID_METRIC_TYPES)} 之一")
    if payload.algebra not in VALID_ALGEBRAS:
        raise MetricValidationError(f"代数模型必须是 {sorted(VALID_ALGEBRAS)} 之一")
    if payload.metric_type == "composite" and not payload.formula:
        raise MetricValidationError("复合指标必须提供公式表达式")


def create_metric(session: Session, payload: MetricInput) -> Metric:
    _validate_metric(payload)
    existing = session.scalar(select(Metric).where(Metric.code == payload.code))
    if existing is not None:
        raise MetricValidationError(f"指标编码 {payload.code} 已存在")

    metric = Metric(
        code=payload.code,
        name=payload.name,
        metric_type=payload.metric_type,
        algebra=payload.algebra,
        formula=payload.formula,
        unit=payload.unit,
        elasticity=payload.elasticity,
        domain_id=payload.domain_id,
        data_source_id=payload.data_source_id,
    )
    session.add(metric)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise MetricValidationError(f"指标创建失败：{exc.orig}") from exc
    return metric


def get_metric_by_code(session: Session, code: str) -> Metric | None:
    return session.scalar(select(Metric).where(Metric.code == code))


def list_metrics(session: Session, domain_id: int | None = None) -> list[Metric]:
    stmt: Select = select(Metric).order_by(Metric.id)
    if domain_id is not None:
        stmt = stmt.where(Metric.domain_id == domain_id)
    return list(session.scalars(stmt))


def set_decomp_rule(
    session: Session, metric_id: int, method: str, default_level: int = 1, params: dict | None = None
) -> DecompRule:
    if method not in VALID_METHODS:
        raise MetricValidationError(f"分解方法必须是 {sorted(VALID_METHODS)} 之一")
    if default_level < 1 or default_level > MAX_TREE_DEPTH:
        raise MetricValidationError(f"默认拆解层级需在 1~{MAX_TREE_DEPTH} 之间")

    rule = session.scalar(select(DecompRule).where(DecompRule.metric_id == metric_id))
    if rule is None:
        rule = DecompRule(metric_id=metric_id, method=method, default_level=default_level, params=params)
        session.add(rule)
    else:
        rule.method = method
        rule.default_level = default_level
        rule.params = params
    session.flush()
    return rule


def _assert_no_cycle(session: Session, node_id: int | None, parent_id: int | None) -> None:
    """向上遍历父链，自成环或超过最大深度都拒绝。"""
    depth = 0
    cursor = parent_id
    while cursor is not None:
        if cursor == node_id:
            raise MetricValidationError("指标树不允许成环")
        cursor = session.scalar(select(MetricTreeNode.parent_id).where(MetricTreeNode.id == cursor))
        depth += 1
        if depth > MAX_TREE_DEPTH:
            raise MetricValidationError(f"指标树层级超过上限 {MAX_TREE_DEPTH}")


def register_tree_guards() -> None:
    """在 flush 前拦截指标树环与层级越界。

    挂在 ORM 事件上而不是只写在 upsert 里：直接改 parent_id 的更新路径
    同样会经过 flush，那里才是唯一能兜住所有写入口的位置。
    """
    from sqlalchemy import event

    @event.listens_for(Session, "before_flush")
    def _check_tree_integrity(db: Session, _flush_context, _instances) -> None:
        for obj in db.dirty | db.new:
            if not isinstance(obj, MetricTreeNode):
                continue
            parent_id = obj.parent_id
            if parent_id is not None and parent_id == obj.id:
                raise MetricValidationError("指标树不允许成环")
            _assert_no_cycle(db, obj.id, parent_id)


def upsert_tree_node(
    session: Session, metric_id: int, parent_id: int | None = None, level: int = 1, sort_no: int = 0
) -> MetricTreeNode:
    """挂载指标到树。根节点 parent_id 为空，同一父节点下指标不可重复。"""
    if level < 1 or level > MAX_TREE_DEPTH:
        raise MetricValidationError(f"树层级需在 1~{MAX_TREE_DEPTH} 之间")

    if parent_id is not None:
        parent = session.get(MetricTreeNode, parent_id)
        if parent is None:
            raise MetricValidationError(f"父节点 {parent_id} 不存在")
        level = parent.level + 1

    duplicate = session.scalar(
        select(MetricTreeNode).where(
            MetricTreeNode.metric_id == metric_id, MetricTreeNode.parent_id == parent_id
        )
    )
    if duplicate is not None:
        raise MetricValidationError("该指标已挂载在同一个父节点下")

    node = MetricTreeNode(metric_id=metric_id, parent_id=parent_id, level=level, sort_no=sort_no)
    session.add(node)
    session.flush()
    _assert_no_cycle(session, node.id, node.parent_id)
    return node


def build_tree(session: Session, root_metric_id: int | None = None) -> list[dict]:
    """把扁平的树节点组装成嵌套结构，供前端指标字典页（PRD 7.4）渲染。"""
    nodes = list(session.scalars(select(MetricTreeNode).order_by(MetricTreeNode.level, MetricTreeNode.sort_no)))
    metrics = {m.id: m for m in session.scalars(select(Metric))}

    children_by_parent: dict[int | None, list[MetricTreeNode]] = {}
    for node in nodes:
        children_by_parent.setdefault(node.parent_id, []).append(node)

    def render(node: MetricTreeNode) -> dict:
        metric = metrics.get(node.metric_id)
        return {
            "node_id": node.id,
            "metric_id": node.metric_id,
            "metric_code": metric.code if metric else "",
            "name": metric.name if metric else "",
            "metric_type": metric.metric_type if metric else "",
            "algebra": metric.algebra if metric else "",
            "level": node.level,
            "children": [render(child) for child in children_by_parent.get(node.id, [])],
        }

    roots = children_by_parent.get(None, [])
    if root_metric_id is not None:
        roots = [n for n in roots if n.metric_id == root_metric_id] or roots
    return [render(node) for node in roots]


def metric_domain_count(session: Session, domain_id: int) -> int:
    return session.scalar(select(func.count(Metric.id)).where(Metric.domain_id == domain_id)) or 0


def list_domains(session: Session) -> list[MetricDomain]:
    return list(session.scalars(select(MetricDomain).order_by(MetricDomain.id)))


def list_data_sources(session: Session) -> list[DataSource]:
    return list(session.scalars(select(DataSource).order_by(DataSource.id)))
