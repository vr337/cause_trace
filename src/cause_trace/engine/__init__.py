"""指标公式引擎：分解算法与守恒硬校验。"""

from cause_trace.engine.formula import (
    DEFAULT_TOLERANCE,
    Contribution,
    DecompositionResult,
    Factor,
    ShapleyResult,
    Slice,
    SliceContribution,
    additive_decompose,
    decompose,
    dupont_decompose,
    lmdi_decompose,
    shapley_decompose,
    validate_conservation,
)
from cause_trace.errors import ConservationError, UnsupportedDecompositionError

__all__ = [
    "DEFAULT_TOLERANCE",
    "ConservationError",
    "Contribution",
    "DecompositionResult",
    "Factor",
    "ShapleyResult",
    "Slice",
    "SliceContribution",
    "UnsupportedDecompositionError",
    "additive_decompose",
    "decompose",
    "dupont_decompose",
    "lmdi_decompose",
    "shapley_decompose",
    "validate_conservation",
]
