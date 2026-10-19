"""T-05：指标字典与指标树的仓储层测试（SQLite 内存库）。"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from cause_trace.db.models.domain import DataSource, MetricDomain
from cause_trace.dictionary import (
    MetricInput,
    MetricValidationError,
    build_tree,
    create_metric,
    get_metric_by_code,
    list_metrics,
    register_tree_guards,
    set_decomp_rule,
    upsert_tree_node,
)

register_tree_guards()


@pytest.fixture
def domain_and_source(session: Session) -> tuple[int, int]:
    domain = MetricDomain(name="电商经营域", biz_line="电商")
    session.add(domain)
    session.flush()
    source = DataSource(
        name="warehouse",
        host="127.0.0.1",
        port=3306,
        db_name="warehouse",
        account="cause_ro",
        secret_ref="WAREHOUSE_RO_PASSWORD",
    )
    session.add(source)
    session.flush()
    return domain.id, source.id


def _metric_payload(domain_id: int, source_id: int, **overrides) -> MetricInput:
    base = {
        "code": "gmv",
        "name": "GMV",
        "metric_type": "composite",
        "algebra": "multiplicative",
        "domain_id": domain_id,
        "data_source_id": source_id,
        "formula": "visitors*cvr*aov",
        "unit": "元",
    }
    base.update(overrides)
    return MetricInput(**base)


def test_create_metric_persists(session: Session, domain_and_source):
    domain_id, source_id = domain_and_source
    metric = create_metric(session, _metric_payload(domain_id, source_id))
    session.commit()

    assert metric.id is not None
    assert get_metric_by_code(session, "gmv").id == metric.id


def test_duplicate_metric_code_is_rejected(session: Session, domain_and_source):
    domain_id, source_id = domain_and_source
    create_metric(session, _metric_payload(domain_id, source_id))
    session.flush()

    with pytest.raises(MetricValidationError) as exc_info:
        create_metric(session, _metric_payload(domain_id, source_id))
    assert "已存在" in str(exc_info.value)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"metric_type": "unknown"}, "指标类型"),
        ({"algebra": "weird"}, "代数模型"),
        ({"formula": None}, "复合指标必须提供公式"),
    ],
)
def test_invalid_metric_payload_is_rejected(session: Session, domain_and_source, overrides, expected):
    domain_id, source_id = domain_and_source
    with pytest.raises(MetricValidationError) as exc_info:
        create_metric(session, _metric_payload(domain_id, source_id, **overrides))
    assert expected in str(exc_info.value)


def test_list_metrics_filters_by_domain(session: Session, domain_and_source):
    domain_id, source_id = domain_and_source
    other_domain = MetricDomain(name="快消经营域", biz_line="快消")
    session.add(other_domain)
    session.flush()

    create_metric(session, _metric_payload(domain_id, source_id))
    create_metric(
        session,
        _metric_payload(other_domain.id, source_id, code="profit", name="利润", algebra="additive"),
    )
    session.commit()

    assert {m.code for m in list_metrics(session, domain_id=domain_id)} == {"gmv"}
    assert len(list_metrics(session)) == 2


def test_decomp_rule_upsert_is_idempotent(session: Session, domain_and_source):
    domain_id, source_id = domain_and_source
    metric = create_metric(session, _metric_payload(domain_id, source_id))
    session.flush()

    set_decomp_rule(session, metric.id, "lmdi", default_level=2)
    rule = set_decomp_rule(session, metric.id, "lmdi", default_level=3)
    session.commit()

    assert rule.default_level == 3
    assert len(list(session.query(type(rule)).filter_by(metric_id=metric.id))) == 1


def test_decomp_rule_rejects_unknown_method(session: Session, domain_and_source):
    domain_id, source_id = domain_and_source
    metric = create_metric(session, _metric_payload(domain_id, source_id))
    session.flush()

    with pytest.raises(MetricValidationError):
        set_decomp_rule(session, metric.id, "regression")


def test_tree_builds_nested_structure(session: Session, domain_and_source):
    domain_id, source_id = domain_and_source
    gmv = create_metric(session, _metric_payload(domain_id, source_id))
    visitors = create_metric(
        session,
        _metric_payload(domain_id, source_id, code="visitors", name="访客数", metric_type="atomic"),
    )
    cvr = create_metric(
        session,
        _metric_payload(domain_id, source_id, code="cvr", name="转化率", metric_type="derived"),
    )
    session.flush()

    root = upsert_tree_node(session, gmv.id, parent_id=None, level=1)
    upsert_tree_node(session, visitors.id, parent_id=root.id)
    upsert_tree_node(session, cvr.id, parent_id=root.id)
    session.commit()

    tree = build_tree(session)
    assert len(tree) == 1
    assert tree[0]["metric_code"] == "gmv"
    assert {child["metric_code"] for child in tree[0]["children"]} == {"visitors", "cvr"}
    assert all(child["level"] == 2 for child in tree[0]["children"])


def test_duplicate_metric_under_same_parent_is_rejected(session: Session, domain_and_source):
    domain_id, source_id = domain_and_source
    gmv = create_metric(session, _metric_payload(domain_id, source_id))
    visitors = create_metric(
        session,
        _metric_payload(domain_id, source_id, code="visitors", name="访客数", metric_type="atomic"),
    )
    session.flush()

    root = upsert_tree_node(session, gmv.id)
    upsert_tree_node(session, visitors.id, parent_id=root.id)
    session.flush()

    with pytest.raises(MetricValidationError) as exc_info:
        upsert_tree_node(session, visitors.id, parent_id=root.id)
    assert "同一个父节点" in str(exc_info.value)


def test_tree_rejects_cycle(session: Session, domain_and_source):
    domain_id, source_id = domain_and_source
    gmv = create_metric(session, _metric_payload(domain_id, source_id))
    visitors = create_metric(
        session,
        _metric_payload(domain_id, source_id, code="visitors", name="访客数", metric_type="atomic"),
    )
    session.flush()

    root = upsert_tree_node(session, gmv.id)
    child = upsert_tree_node(session, visitors.id, parent_id=root.id)
    session.flush()

    with pytest.raises(MetricValidationError):
        # 把父节点挂到自己的子节点下，构成环
        root.parent_id = child.id
        session.flush()
