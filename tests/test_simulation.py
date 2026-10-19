"""T-10：弹性拟合、多情景重算与策略四要素。"""

from __future__ import annotations

import pytest

from cause_trace.engine.formula import Contribution
from cause_trace.simulation import (
    ElasticityFit,
    fit_elasticity,
    generate_strategies,
    sensitivity_curve,
    simulate,
    validate_strategy,
)


def _log_series(slope: float, n: int = 30) -> tuple[list[float], list[float]]:
    """构造 ln Y = slope × ln X 的干净样本，用于验证弹性可被还原。"""
    x = [10 + i for i in range(n)]
    y = [20 * (v / 10) ** slope for v in x]
    return y, x


def test_regression_recovers_known_elasticity():
    fit = fit_elasticity("douyin_budget", *_log_series(1.2))
    assert fit.method == "regression"
    assert fit.elasticity == pytest.approx(1.2, abs=1e-3)
    assert fit.r_squared > 0.99


def test_low_r_squared_falls_back_to_empirical():
    y = [100, 90, 130, 80, 140, 60, 150, 50]
    x = [10, 11, 12, 13, 14, 15, 16, 17]
    fit = fit_elasticity("price", y, x, empirical=0.8)
    assert fit.method == "empirical"
    assert fit.elasticity == 0.8


def test_non_positive_values_fall_back_to_empirical():
    fit = fit_elasticity("price", [100, 0, 120], [10, 11, 12], empirical=0.5)
    assert fit.method == "empirical"
    assert fit.elasticity == 0.5


def test_insufficient_samples_fall_back_to_empirical():
    fit = fit_elasticity("price", [100, 110], [10, 11], empirical=1.0)
    assert fit.method == "empirical"


def test_simulate_applies_elasticity_to_baseline():
    fits = {"douyin_budget": ElasticityFit("douyin_budget", elasticity=1.2, r_squared=0.9, method="regression", sample_size=30)}
    outcome = simulate(1_000_000.0, {"douyin_budget": 1.2}, fits)
    scenario = outcome.scenarios[0]

    assert scenario.delta_rate == pytest.approx(0.24)
    assert scenario.metric_value == pytest.approx(1_240_000.0)
    assert scenario.confidence_interval[0] < scenario.metric_value < scenario.confidence_interval[1]


def test_simulate_skips_unknown_factor():
    outcome = simulate(1000.0, {"unknown": 1.5}, {})
    assert outcome.scenarios == []


def test_simulate_handles_zero_baseline_without_dividing_by_zero():
    outcome = simulate(0.0, {"x": 1.2}, {"x": ElasticityFit("x", 1.0, 0.9, "regression", 30)})
    assert outcome.scenarios[0].metric_value > 0


def test_sensitivity_curve_spans_ratio_grid():
    fit = ElasticityFit("budget", elasticity=2.0, r_squared=0.9, method="regression", sample_size=30)
    curve = sensitivity_curve(1000.0, "budget", fit)
    assert curve["ratios"] == [0.8, 0.9, 1.0, 1.1, 1.2]
    assert curve["metric_values"][2] == pytest.approx(1000.0)
    assert curve["metric_values"][0] == pytest.approx(600.0)


def test_strategies_only_generated_for_significant_factors():
    contributions = [
        Contribution("转化率", 0.02, 0.018, -0.002, -64.0, -0.64, "down"),
        Contribution("客单价", 186.0, 186.0, 0.0, 0.0, 0.0, "flat"),
    ]
    strategies = generate_strategies(contributions, contributions_threshold=0.05)
    assert len(strategies) == 1
    assert strategies[0]["factor"] == "转化率"
    assert strategies[0]["role"] == "渠道运营负责人"
    assert validate_strategy(strategies[0])


def test_strategy_four_elements_are_mandatory():
    strategies = generate_strategies([Contribution("a", 1, 2, 1, 10.0, 0.5, "up")])
    for strategy in strategies:
        assert validate_strategy(strategy)
        assert strategy["period_days"] > 0
        assert strategy["expected_recovery"] > 0


def test_strategy_period_scales_with_contribution():
    big = generate_strategies([Contribution("a", 1, 2, 1, 100.0, 0.9, "up")])[0]
    small = generate_strategies([Contribution("a", 1, 2, 1, 5.0, 0.1, "up")])[0]
    assert big["period_days"] > small["period_days"]


def test_empty_contributions_yield_no_strategy():
    assert generate_strategies([]) == []
