"""T-08：相关性、显著性与置信度合成。"""

from __future__ import annotations

import math

import pytest

from cause_trace.orchestration.statistics import (
    confidence_from_evidence,
    pearson_correlation,
)


def test_perfect_positive_correlation():
    result = pearson_correlation([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
    assert result.coefficient == pytest.approx(1.0)
    assert result.p_value == 0.0


def test_negative_correlation():
    result = pearson_correlation([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
    assert result.coefficient == pytest.approx(-1.0)


def test_constant_series_is_not_significant():
    # 指标没有波动时相关性无定义，应判为不相关而非抛异常
    result = pearson_correlation([5, 5, 5, 5], [1, 2, 3, 4])
    assert result.coefficient == 0.0
    assert result.p_value == 1.0


def test_sample_size_too_small_is_rejected():
    with pytest.raises(ValueError):
        pearson_correlation([1, 2], [3, 4])


def test_mismatched_lengths_are_rejected():
    with pytest.raises(ValueError):
        pearson_correlation([1, 2, 3], [1, 2])


def test_p_value_decreases_with_correlation_strength():
    weak = pearson_correlation([1, 2, 3, 4, 5, 6, 7, 8], [1, 3, 2, 5, 4, 7, 6, 9])
    strong = pearson_correlation([1, 2, 3, 4, 5, 6, 7, 8], [2, 4, 6, 8, 10, 12, 14, 16])
    assert weak.p_value > strong.p_value
    assert 0.0 < weak.p_value < 1.0


def test_p_value_matches_known_t_distribution():
    # n=10, r=0.8 → t≈4.0, df=8，双尾 p 应在 0.002~0.005 之间
    result = pearson_correlation(range(10), [0, 1, 2, 3, 5, 5, 6, 7, 8, 9])
    assert 0.0 < result.p_value < 0.01


def test_confidence_combines_all_evidence():
    result = confidence_from_evidence(correlation=0.9, p_value=0.01, contribution_rate=0.8)
    assert result.confidence > 0.8
    assert result.basis == "相关性+显著性+贡献率"


def test_confidence_without_evidence_is_zero():
    result = confidence_from_evidence()
    assert result.confidence == 0.0
    assert result.basis == "无证据"


def test_confidence_ignores_p_value_above_threshold():
    # p > 0.05 视为不显著，显著性项记 0 分但不扣分
    high = confidence_from_evidence(correlation=0.5, p_value=0.9, contribution_rate=0.5)
    low = confidence_from_evidence(correlation=0.5, p_value=0.01, contribution_rate=0.5)
    assert high.confidence < low.confidence


def test_confidence_is_capped_at_one():
    result = confidence_from_evidence(correlation=1.0, p_value=0.0, contribution_rate=1.0)
    assert result.confidence == 1.0
    assert math.isfinite(result.confidence)
