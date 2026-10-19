"""T-04：维度下钻 Shapley 分解的守恒性单测。"""

from __future__ import annotations

import pytest

from cause_trace.engine import Slice, shapley_decompose


@pytest.mark.parametrize(
    "slices",
    [
        # 三条渠道：有的靠流量结构变化，有的靠转化率变化
        [
            Slice("douyin", 0.5, 0.6, 0.04, 0.035),
            Slice("wechat", 0.3, 0.2, 0.05, 0.05),
            Slice("search", 0.2, 0.2, 0.03, 0.028),
        ],
        # 四切片，结构变化与水平变化同时存在
        [
            Slice("north", 0.4, 0.35, 0.02, 0.022),
            Slice("south", 0.3, 0.3, 0.025, 0.024),
            Slice("east", 0.2, 0.25, 0.03, 0.031),
            Slice("west", 0.1, 0.1, 0.018, 0.02),
        ],
        # 仅转化率变化，结构不变
        [
            Slice("app", 0.6, 0.6, 0.05, 0.045),
            Slice("web", 0.4, 0.4, 0.03, 0.033),
        ],
    ],
)
def test_shapley_conservation(slices: list[Slice]):
    result = shapley_decompose(slices)

    assert result.conserved
    assert abs(result.residual) <= 1e-9
    assert abs(sum(s.contribution for s in result.slices) - result.total_delta) <= 1e-9
    # mix + rate 双效应之和必须等于该切片的实际变化量
    for item in result.slices:
        assert item.mix_contribution + item.rate_contribution == pytest.approx(
            item.delta, abs=1e-9
        )


def test_shapley_mix_effect_isolates_structure_shift():
    # 只有一个切片的结构占比上升、转化率不变，贡献应全部来自 mix
    result = shapley_decompose(
        [Slice("a", 0.5, 0.7, 0.02, 0.02), Slice("b", 0.5, 0.3, 0.02, 0.02)]
    )
    a = result.slices[0]
    assert a.mix_contribution > 0
    assert a.rate_contribution == pytest.approx(0.0)
