"""T-04：乘法模型 LMDI 与杜邦分解的守恒性单测。"""

from __future__ import annotations

import pytest

from cause_trace.engine import Factor, dupont_decompose, lmdi_decompose


@pytest.mark.parametrize(
    ("base", "current"),
    [
        # GMV = 访客数 × 转化率 × 客单价
        ((10000.0, 0.02, 100.0), (9000.0, 0.018, 105.0)),
        # 三因子同向增长
        ((1000.0, 1.5, 80.0), (1200.0, 1.6, 88.0)),
        # 单因子下滑，其余上涨
        ((5000.0, 0.03, 120.0), (4800.0, 0.035, 130.0)),
    ],
)
def test_lmdi_conservation(base: tuple[float, float, float], current: tuple[float, float, float]):
    factors = [
        Factor("visitors", base[0], current[0]),
        Factor("cvr", base[1], current[1]),
        Factor("aov", base[2], current[2]),
    ]
    result = lmdi_decompose(factors)

    assert result.conserved
    assert abs(result.residual) <= 1e-9
    assert abs(sum(c.contribution for c in result.contributions) - result.total_delta) <= 1e-9


def test_lmdi_contribution_direction_matches_factor_change():
    result = lmdi_decompose(
        [Factor("visitors", 1000.0, 1200.0), Factor("cvr", 0.02, 0.018), Factor("aov", 100.0, 100.0)]
    )
    directions = {c.factor: c.direction for c in result.contributions}
    assert directions["visitors"] == "up"
    assert directions["cvr"] == "down"
    assert directions["aov"] == "flat"


def test_dupont_reuses_lmdi_and_remains_conserved():
    factors = [
        Factor("net_margin", 0.1, 0.09),
        Factor("asset_turnover", 1.2, 1.25),
        Factor("equity_multiplier", 2.0, 2.1),
    ]
    result = dupont_decompose(factors)
    assert result.method == "dupont"
    assert result.conserved
    assert abs(sum(c.contribution for c in result.contributions) - result.total_delta) <= 1e-9
