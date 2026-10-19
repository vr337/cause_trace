"""T-19/T-20：异动注入、ground truth 与场景闭环。"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from cause_trace.dbmock import (
    ECOMMERCE_GMV,
    FMCG_MARGIN,
    SCENARIOS,
    InjectionSpec,
    compare_with_truth,
    detect_anomaly,
    generate_daily_rows,
    inject_values,
    persist_injection,
)
from cause_trace.db.models.governance import InjectionTruth


def test_injection_only_touches_target_window_and_dimension():
    rows = [
        {"dt": "2026-08-11", "channel": "douyin", "value": 100.0},
        {"dt": "2026-08-12", "channel": "douyin", "value": 100.0},
        {"dt": "2026-08-15", "channel": "douyin", "value": 100.0},
        {"dt": "2026-08-15", "channel": "search", "value": 100.0},
        {"dt": "2026-08-25", "channel": "douyin", "value": 100.0},
    ]
    spec = InjectionSpec(
        scenario_code="test",
        metric_id=1,
        dimension_code="channel",
        dimension_values=("douyin",),
        window_start=date(2026, 8, 12),
        window_end=date(2026, 8, 18),
        amplitude=-0.5,
    )
    result = inject_values(rows, spec, dimension_field="channel")

    assert result.rows_affected == 2
    assert rows[0]["value"] == 100.0  # 窗口外不动
    assert rows[3]["value"] == 100.0  # 维度不命中不动
    assert rows[4]["value"] == 100.0
    assert 40.0 <= rows[1]["value"] <= 60.0  # 命中行落在 ±10% 抖动内


def test_injection_is_reproducible_with_same_seed():
    def run(seed: int) -> list[float]:
        rows = [{"dt": "2026-08-12", "channel": "douyin", "value": 100.0}]
        spec = InjectionSpec(
            scenario_code="test",
            metric_id=1,
            dimension_code="channel",
            dimension_values=("douyin",),
            window_start=date(2026, 8, 12),
            window_end=date(2026, 8, 18),
            amplitude=-0.3,
            seed=seed,
        )
        inject_values(rows, spec, dimension_field="channel")
        return [row["value"] for row in rows]

    assert run(42) == run(42)
    assert run(42) != run(7)


def test_injection_accepts_datetime_and_date_objects():
    rows = [
        {"dt": date(2026, 8, 13), "value": 100.0},
        {"dt": "not-a-date", "value": 100.0},
    ]
    spec = InjectionSpec(
        scenario_code="test",
        metric_id=1,
        dimension_code="channel",
        dimension_values=("douyin",),
        window_start=date(2026, 8, 12),
        window_end=date(2026, 8, 18),
        amplitude=-0.2,
    )
    result = inject_values(rows, spec)
    assert result.rows_affected == 1


def test_persist_injection_writes_config_and_truth(session: Session):
    rows = [{"dt": "2026-08-12", "channel": "douyin", "value": 100.0}]
    result = inject_values(rows, ECOMMERCE_GMV.injection, dimension_field="channel")
    config = persist_injection(session, ECOMMERCE_GMV.injection, result)

    truths = list(session.query(InjectionTruth).filter_by(config_id=config.id))
    assert config.scenario_code == "ecommerce_gmv_drop"
    assert truths[0].dimension_value == "douyin"


def test_persist_injection_is_idempotent(session: Session):
    for _ in range(2):
        rows = [{"dt": "2026-08-12", "channel": "douyin", "value": 100.0}]
        result = inject_values(rows, ECOMMERCE_GMV.injection, dimension_field="channel")
        persist_injection(session, ECOMMERCE_GMV.injection, result)
    session.commit()

    assert session.query(InjectionTruth).count() == 1


def test_compare_with_truth_reports_missed_and_false_positive(session: Session):
    rows = [{"dt": "2026-08-12", "channel": "douyin", "value": 100.0}]
    result = inject_values(rows, ECOMMERCE_GMV.injection, dimension_field="channel")
    config = persist_injection(session, ECOMMERCE_GMV.injection, result)
    truths = list(session.query(InjectionTruth).filter_by(config_id=config.id))

    comparison = compare_with_truth(
        [{"dimension_value": "douyin"}, {"dimension_value": "wechat"}], truths
    )
    assert comparison["matched"] == ["douyin"]
    assert comparison["missed"] == []
    assert comparison["false_positive"] == ["wechat"]
    assert comparison["hit_rate"] == 1.0


def test_ecommerce_scenario_end_to_end_detects_injected_channel():
    # 注入窗固定在 08-12~08-18，检测也必须按这个窗口比，否则跌幅会被稀释
    rows = generate_daily_rows(ECOMMERCE_GMV, start=date(2026, 8, 1), days=30)
    inject_values(rows, ECOMMERCE_GMV.injection, dimension_field="channel")

    detected = detect_anomaly(
        rows,
        dimension_field="channel",
        window=(ECOMMERCE_GMV.injection.window_start, ECOMMERCE_GMV.injection.window_end),
    )
    assert [item["dimension_value"] for item in detected] == ["douyin"]


def test_fmcg_scenario_is_registered_and_additive():
    assert SCENARIOS["fmcg_margin_shift"] is FMCG_MARGIN
    assert FMCG_MARGIN.algebra == "additive"
    rows = generate_daily_rows(FMCG_MARGIN, start=date(2026, 8, 1), days=30, dimension_field="region")
    assert {row["region"] for row in rows} == {"east_china", "south", "north"}


def test_detect_anomaly_ignores_stable_dimensions():
    rows = [
        {"dt": f"2026-08-{day:02d}", "channel": "stable", "value": 100.0 + (day % 3)}
        for day in range(1, 21)
    ]
    assert detect_anomaly(rows) == []


@pytest.mark.parametrize("scenario", list(SCENARIOS.values()))
def test_all_scenarios_have_injection_window(scenario):
    assert scenario.injection.window_start <= scenario.injection.window_end
    assert scenario.injection.amplitude < 0
