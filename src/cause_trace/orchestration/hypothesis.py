"""假设状态机（T-07 / FR-10）：pending → verified / excluded 的生命周期。

置信度低于阈值的假设一律自动标记 excluded，不进入最终结论；这是 PRD 1.3
「假设闭环」成功标准的落地方式。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DEFAULT_CONFIDENCE_THRESHOLD = 0.6
MIN_HYPOTHESES = 3
MAX_HYPOTHESES = 5


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    EXCLUDED = "excluded"
    FAILED = "failed"


@dataclass
class Hypothesis:
    """候选假设。origin 区分 LLM 生成与规则模板生成，便于降级追溯。"""

    content: str
    origin: str = "llm"
    status: HypothesisStatus = HypothesisStatus.PENDING
    confidence: float | None = None
    exclude_reason: str | None = None
    evidence: list[dict] | None = None

    def verify(self, confidence: float, evidence: dict | None = None) -> HypothesisStatus:
        self.confidence = confidence
        if evidence is not None:
            self.evidence = [*(self.evidence or []), evidence]
        self.status = HypothesisStatus.VERIFIED
        return self.status

    def exclude(self, reason: str) -> HypothesisStatus:
        self.status = HypothesisStatus.EXCLUDED
        self.exclude_reason = reason
        return self.status

    def mark_failed(self, reason: str) -> HypothesisStatus:
        """沙箱执行失败：不中断会话，仅标记该假设验证失败（Spec 8 高可用）。"""
        self.status = HypothesisStatus.FAILED
        self.exclude_reason = reason
        return self.status

    def as_dict(self) -> dict:
        return {
            "content": self.content,
            "origin": self.origin,
            "status": self.status.value,
            "confidence": self.confidence,
            "exclude_reason": self.exclude_reason,
            "evidence": self.evidence or [],
        }


def clamp_hypotheses(items: list[str], origin: str = "llm") -> list[Hypothesis]:
    """把 LLM/模板产出的文本收敛到 3~5 条，保证假设看板有可比较的规模。"""
    cleaned = [text.strip() for text in items if text and text.strip()]
    if len(cleaned) > MAX_HYPOTHESES:
        cleaned = cleaned[:MAX_HYPOTHESES]
    return [Hypothesis(content=text, origin=origin) for text in cleaned]


def apply_threshold(
    hypotheses: list[Hypothesis],
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> list[Hypothesis]:
    """置信度低于阈值自动排除。

    已验证的假设同样要过这道闸：沙箱给出低置信度说明该假设虽被执行过，
    但不构成有效解释，必须从结论中剔除，否则就是伪相关漏网。
    """
    for item in hypotheses:
        if item.status not in (HypothesisStatus.PENDING, HypothesisStatus.VERIFIED):
            continue
        if item.confidence is None:
            continue
        if item.confidence < threshold:
            item.exclude(f"置信度 {item.confidence:.2f} 低于阈值 {threshold:.2f}，判定为伪相关")
    return hypotheses


def board(hypotheses: list[Hypothesis]) -> dict:
    """假设看板聚合视图，供 WS 推送与接口复用。"""
    return {
        "total": len(hypotheses),
        "pending": sum(1 for h in hypotheses if h.status == HypothesisStatus.PENDING),
        "verified": sum(1 for h in hypotheses if h.status == HypothesisStatus.VERIFIED),
        "excluded": sum(1 for h in hypotheses if h.status == HypothesisStatus.EXCLUDED),
        "failed": sum(1 for h in hypotheses if h.status == HypothesisStatus.FAILED),
        "hypotheses": [h.as_dict() for h in hypotheses],
    }
