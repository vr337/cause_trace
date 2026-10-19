"""T-07：假设状态机的生命周期与阈值自动排除。"""

from __future__ import annotations

import pytest

from cause_trace.orchestration.hypothesis import (
    Hypothesis,
    HypothesisStatus,
    apply_threshold,
    board,
    clamp_hypotheses,
)


def test_clamp_hypotheses_keeps_three_to_five():
    hypotheses = clamp_hypotheses([f"假设{i}" for i in range(8)])
    assert len(hypotheses) == 5
    assert all(h.status == HypothesisStatus.PENDING for h in hypotheses)


def test_clamp_hypotheses_drops_empty_text():
    hypotheses = clamp_hypotheses(["有效假设", "  ", ""])
    assert len(hypotheses) == 1


def test_verify_sets_confidence_and_evidence():
    h = Hypothesis(content="渠道结构恶化")
    h.verify(0.87, {"fact": "低转化渠道占比 +8pct"})
    assert h.status == HypothesisStatus.VERIFIED
    assert h.confidence == 0.87
    assert h.evidence[0]["fact"] == "低转化渠道占比 +8pct"


def test_threshold_excludes_low_confidence_hypothesis():
    hypotheses = [
        Hypothesis(content="H1"),
        Hypothesis(content="H2"),
    ]
    hypotheses[0].verify(0.91)
    hypotheses[1].verify(0.34)
    apply_threshold(hypotheses, threshold=0.6)

    assert hypotheses[0].status == HypothesisStatus.VERIFIED
    assert hypotheses[1].status == HypothesisStatus.EXCLUDED
    assert "伪相关" in (hypotheses[1].exclude_reason or "")


def test_threshold_leaves_unverified_pending():
    hypotheses = [Hypothesis(content="尚未验证")]
    apply_threshold(hypotheses)
    assert hypotheses[0].status == HypothesisStatus.PENDING


def test_failed_hypothesis_does_not_block_session():
    h = Hypothesis(content="沙箱执行失败")
    h.mark_failed("SBX_TIMEOUT")
    assert h.status == HypothesisStatus.FAILED
    assert h.exclude_reason == "SBX_TIMEOUT"


def test_board_aggregates_status_counts():
    verified = Hypothesis(content="a")
    verified.verify(0.9)
    excluded = Hypothesis(content="b")
    excluded.exclude("置信度不足")
    summary = board([verified, excluded, Hypothesis(content="c")])

    assert summary == {
        "total": 3,
        "pending": 1,
        "verified": 1,
        "excluded": 1,
        "failed": 0,
        "hypotheses": summary["hypotheses"],
    }


@pytest.mark.parametrize("confidence,expected", [(0.6, "verified"), (0.59, "excluded")])
def test_threshold_boundary(confidence: float, expected: str):
    # 置信度等于阈值时保留，低于阈值才排除
    h = Hypothesis(content="边界")
    h.verify(confidence)
    apply_threshold([h], threshold=0.6)
    assert h.status.value == expected
