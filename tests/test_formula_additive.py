"""T-04：加法模型差额分析的守恒性单测。"""

from __future__ import annotations

import pytest

from cause_trace.engine import Factor, additive_decompose


@pytest.mark.parametrize(
    ("base", "current"),
    [
        # 有增有减，典型利润表结构
        ((100.0, 50.0, 30.0), (120.0, 45.0, 35.0)),
        # 全线上涨
        ((10.0, 20.0, 30.0), (15.0, 25.0, 33.0)),
        # 三分量均下跌，含负贡献
        ((200.0, 80.0, 60.0), (150.0, 70.0, 55.0)),
    ],
)
def test_additive_conservation(base: tuple[float, float, float], current: tuple[float, float, float]):
    factors = [
        Factor("revenue", base[0], current[0]),
        Factor("cost", base[1], current[1], sign=-1),
        Factor("tax", base[2], current[2], sign=-1),
    ]
    result = additive_decompose(factors)

    assert result.conserved
    assert abs(result.residual) <= 1e-9
    assert abs(sum(c.contribution for c in result.contributions) - result.total_delta) <= 1e-9


def test_additive_signed_contributions():
    factors = [
        Factor("a", 100.0, 130.0),
        Factor("b", 50.0, 40.0),
        Factor("c", 20.0, 25.0, sign=-1),
    ]
    result = additive_decompose(factors)
    # Y = a + b - c：30 + (-10) - 5 = 15
    assert result.total_delta == pytest.approx(15.0)
    assert result.contribution_map() == pytest.approx({"a": 30.0, "b": -10.0, "c": -5.0})
    assert [c.direction for c in result.contributions] == ["up", "down", "down"]


def test_additive_zero_total_delta_has_zero_rates():
    # 总变动为 0 时贡献率无意义，应统一取 0 而不是除零
    result = additive_decompose([Factor("a", 10.0, 20.0), Factor("b", 20.0, 10.0)])
    assert result.total_delta == 0
    assert all(c.contribution_rate == 0 for c in result.contributions)
