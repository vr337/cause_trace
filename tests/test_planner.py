"""T-06：分析计划的阶段推进与断点语义。"""

from __future__ import annotations

from cause_trace.orchestration.planner import STAGE_SEQUENCE, AnalysisPlan, Stage


def test_default_plan_covers_full_pipeline():
    plan = AnalysisPlan.default()
    assert [s.stage for s in plan.steps] == list(STAGE_SEQUENCE)
    assert plan.current_stage == Stage.INTENT_PARSE


def test_advance_marks_done_and_moves_forward():
    plan = AnalysisPlan.default()
    assert plan.advance() == Stage.DECOMPOSE
    assert plan.steps[0].status == "done"
    assert plan.steps[1].status == "pending"


def test_advance_stops_after_last_stage():
    plan = AnalysisPlan.default()
    for _ in range(len(plan.steps)):
        plan.advance()
    assert plan.advance() is None
    assert plan.current_stage == Stage.REPORT
    assert all(s.status == "done" for s in plan.steps)


def test_mark_running_flags_current_step():
    plan = AnalysisPlan.default()
    step = plan.mark_running()
    assert step.status == "running"
    assert step.stage == Stage.INTENT_PARSE


def test_plan_is_serializable_for_snapshot():
    plan = AnalysisPlan.default()
    payload = plan.as_dict()
    assert payload["current_index"] == 0
    assert len(payload["steps"]) == 8
