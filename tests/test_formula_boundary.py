"""T-04：边界与反例用例。"""

from __future__ import annotations

import pytest

from cause_trace.engine import (
    ConservationError,
    Factor,
    Slice,
    additive_decompose,
    decompose,
    lmdi_decompose,
    shapley_decompose,
    validate_conservation,
)
from cause_trace.errors import UnsupportedDecompositionError


def test_lmdi_base_value_zero_does_not_raise():
    # 基期为 0 时对数无定义，应退化为按差额占比分摊而不是抛异常
    result = lmdi_decompose([Factor("a", 0.0, 10.0), Factor("b", 10.0, 20.0)])
    assert result.conserved
    assert abs(sum(c.contribution for c in result.contributions) - result.total_delta) <= 1e-9


def test_lmdi_current_value_zero_does_not_raise():
    result = lmdi_decompose([Factor("a", 10.0, 0.0), Factor("b", 20.0, 20.0)])
    assert result.conserved
    assert abs(sum(c.contribution for c in result.contributions) - result.total_delta) <= 1e-9


def test_single_factor_without_change_contributes_zero():
    result = additive_decompose([Factor("a", 100.0, 100.0)])
    assert result.total_delta == 0
    assert result.contributions[0].contribution == 0
    assert result.contributions[0].direction == "flat"


def test_all_zero_series_is_conserved():
    result = lmdi_decompose([Factor("a", 0.0, 0.0), Factor("b", 0.0, 0.0)])
    assert result.conserved
    assert result.total_delta == 0


def test_shapley_with_zero_rate_is_conserved():
    result = shapley_decompose([Slice("a", 0.5, 0.5, 0.0, 0.02), Slice("b", 0.5, 0.5, 0.04, 0.02)])
    assert result.conserved


def test_unsupported_method_is_rejected():
    with pytest.raises(UnsupportedDecompositionError):
        decompose("regression", [Factor("a", 1.0, 2.0)])


def test_residual_beyond_tolerance_raises_conservation_error():
    # 反例：人为制造 1e-3 的残差，必须被硬校验拦住
    with pytest.raises(ConservationError) as exc_info:
        validate_conservation(total_delta=100.0, contributions=[60.0, 40.001])
    assert exc_info.value.code == "BIZ_CONSERVATION_FAILED"


def test_residual_within_tolerance_passes():
    residual = validate_conservation(total_delta=100.0, contributions=[60.0, 40.0 + 1e-12])
    assert abs(residual) <= 1e-9
