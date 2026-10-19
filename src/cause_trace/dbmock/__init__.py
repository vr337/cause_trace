"""示例数仓生成与异动注入。"""

from cause_trace.dbmock.injection import (
    InjectionResult,
    InjectionSpec,
    compare_with_truth,
    inject_values,
    persist_injection,
)
from cause_trace.dbmock.scenarios import (
    ECOMMERCE_GMV,
    FMCG_MARGIN,
    SCENARIOS,
    ScenarioDefinition,
    detect_anomaly,
    generate_daily_rows,
)

__all__ = [
    "ECOMMERCE_GMV",
    "FMCG_MARGIN",
    "SCENARIOS",
    "InjectionResult",
    "InjectionSpec",
    "ScenarioDefinition",
    "compare_with_truth",
    "detect_anomaly",
    "generate_daily_rows",
    "inject_values",
    "persist_injection",
]
