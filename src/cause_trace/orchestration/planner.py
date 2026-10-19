"""规划调度：把一次归因拆成可追踪的阶段序列（T-06 / FR-09）。

Spec ADR-04 要求分析链路服务端编排，不依赖提示词自由发挥。这里的阶段即
Spec 12.3 WS 协议里的 stage 枚举，前端思维链直接按顺序渲染。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Stage(str, Enum):
    INTENT_PARSE = "intent_parse"
    DECOMPOSE = "decompose"
    DRILLDOWN = "drilldown"
    HYPOTHESIS_GEN = "hypothesis_gen"
    SANDBOX_VERIFY = "sandbox_verify"
    CAUSAL_LINK = "causal_link"
    SIMULATION = "simulation"
    REPORT = "report"


STAGE_SEQUENCE: tuple[Stage, ...] = (
    Stage.INTENT_PARSE,
    Stage.DECOMPOSE,
    Stage.DRILLDOWN,
    Stage.HYPOTHESIS_GEN,
    Stage.SANDBOX_VERIFY,
    Stage.CAUSAL_LINK,
    Stage.SIMULATION,
    Stage.REPORT,
)


@dataclass
class PlanStep:
    stage: Stage
    description: str
    status: str = "pending"

    def as_dict(self) -> dict:
        return {"stage": self.stage.value, "description": self.description, "status": self.status}


@dataclass
class AnalysisPlan:
    """一次归因会话的执行计划，断点恢复依赖 current_index。"""

    steps: list[PlanStep] = field(default_factory=list)
    current_index: int = 0

    @classmethod
    def default(cls) -> AnalysisPlan:
        return cls(
            steps=[
                PlanStep(Stage.INTENT_PARSE, "解析目标指标、统计周期与对比基期"),
                PlanStep(Stage.DECOMPOSE, "读取指标树，完成一级因子拆解与守恒校验"),
                PlanStep(Stage.DRILLDOWN, "按渠道/区域/品类多维交叉下钻，定位异动集中维度"),
                PlanStep(Stage.HYPOTHESIS_GEN, "生成 3~5 条候选归因假设"),
                PlanStep(Stage.SANDBOX_VERIFY, "并行执行沙箱验证，核算置信度"),
                PlanStep(Stage.CAUSAL_LINK, "匹配异动窗口前后 3 日的业务事件"),
                PlanStep(Stage.SIMULATION, "What-If 多情景重算与策略四要素生成"),
                PlanStep(Stage.REPORT, "组装七章节结构化报告"),
            ]
        )

    @property
    def current_stage(self) -> Stage:
        if self.current_index >= len(self.steps):
            return Stage.REPORT
        return self.steps[self.current_index].stage

    def advance(self) -> Stage | None:
        if self.current_index >= len(self.steps):
            return None
        self.steps[self.current_index].status = "done"
        self.current_index += 1
        return self.current_stage if self.current_index < len(self.steps) else None

    def mark_running(self) -> PlanStep:
        step = self.steps[self.current_index]
        step.status = "running"
        return step

    def as_dict(self) -> dict:
        return {
            "current_stage": self.current_stage.value,
            "current_index": self.current_index,
            "steps": [s.as_dict() for s in self.steps],
        }
