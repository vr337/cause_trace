"""T-20/T-21：两个预置场景的全链路闭环（不含数据库）。"""

from __future__ import annotations

from datetime import date

import pytest

from cause_trace.causal import BusinessEventInput, build_causal_links, match_events
from cause_trace.dbmock import ECOMMERCE_GMV, FMCG_MARGIN, detect_anomaly, generate_daily_rows, inject_values
from cause_trace.engine import Factor, additive_decompose, lmdi_decompose
from cause_trace.simulation import ElasticityFit, generate_strategies, simulate


@pytest.mark.parametrize("scenario", [ECOMMERCE_GMV, FMCG_MARGIN], ids=["ecommerce", "fmcg"])
def test_scenario_closure_end_to_end(scenario):
    """场景闭环：生成数据 → 注入异动 → 检测 → 分解 → 因果 → 仿真 → 策略。"""
    fields = "channel" if scenario is ECOMMERCE_GMV else "region"
    rows = generate_daily_rows(
        scenario, start=date(2026, 8, 1), days=30, dimension_field=fields
    )
    inject_values(rows, scenario.injection, dimension_field=fields)

    window = (scenario.injection.window_start, scenario.injection.window_end)
    detected = detect_anomaly(rows, dimension_field=fields, window=window)
    assert detected, "注入后必须能检出异动"
    assert detected[0]["dimension_value"] == scenario.injection.dimension_values[0]

    inside = [row["value"] for row in rows if window[0] <= date.fromisoformat(str(row["dt"])) <= window[1]]
    outside = [row["value"] for row in rows if not (window[0] <= date.fromisoformat(str(row["dt"])) <= window[1])]
    current = sum(inside) / len(inside)
    base = sum(outside) / len(outside)

    if scenario.algebra == "multiplicative":
        result = lmdi_decompose(
            [Factor(name, value, value * current / base) for name, value in scenario.factors]
        )
    else:
        (revenue_name, revenue), (cost_name, cost) = scenario.factors
        result = additive_decompose(
            [
                Factor(revenue_name, revenue, revenue * current / base),
                Factor(cost_name, cost, cost * 1.05, sign=-1),
            ]
        )

    assert result.conserved, "场景闭环必须满足守恒"

    events = [
        BusinessEventInput(
            name="平台大促",
            event_type="promo",
            window_start=scenario.injection.window_start,
            window_end=scenario.injection.window_end,
            categories=scenario.categories,
            channels=scenario.channels,
        )
    ]
    matched = match_events(
        scenario.injection.window_start,
        scenario.injection.window_end,
        events,
        categories=scenario.categories,
    )
    links = build_causal_links(matched)
    assert links and links[0]["role"] == "external"

    fits = {
        scenario.factors[0][0]: ElasticityFit(
            factor=scenario.factors[0][0], elasticity=1.1, r_squared=0.86, method="regression", sample_size=30
        )
    }
    outcome = simulate(abs(result.total_current), {scenario.factors[0][0]: 1.2}, fits)
    assert outcome.scenarios[0].delta_rate == pytest.approx(0.22)

    strategies = generate_strategies(result.contributions, contributions_threshold=0.01)
    assert strategies, "贡献超过阈值的因子必须产出策略"
    assert all({"factor", "role", "period_days", "expected_recovery"} <= set(s) for s in strategies)
