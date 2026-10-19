"""敏感性模拟与建议引擎。"""

from cause_trace.simulation.engine import (
    DEFAULT_CONFIDENCE_Z,
    DEFAULT_ELASTICITY,
    DEFAULT_MIN_R_SQUARED,
    ElasticityFit,
    Scenario,
    SimulationOutcome,
    fit_elasticity,
    generate_strategies,
    sensitivity_curve,
    simulate,
    validate_strategy,
)

__all__ = [
    "DEFAULT_CONFIDENCE_Z",
    "DEFAULT_ELASTICITY",
    "DEFAULT_MIN_R_SQUARED",
    "ElasticityFit",
    "Scenario",
    "SimulationOutcome",
    "fit_elasticity",
    "generate_strategies",
    "sensitivity_curve",
    "simulate",
    "validate_strategy",
]
