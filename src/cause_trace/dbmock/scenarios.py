"""预置业务场景（T-20 / T-21 / FR-20）。

每个场景给出指标树、注入配置与可复现的合成数据，供全链路演示与 AC 验收：
- 电商 GMV 下滑：08-12 起抖音渠道转化率下跌 35%
- 快消利润率异动：08-20 起华东区域成本上涨 18%
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from cause_trace.dbmock.injection import InjectionSpec


@dataclass(frozen=True)
class ScenarioDefinition:
    code: str
    name: str
    metric_code: str
    metric_name: str
    algebra: str
    factors: tuple[tuple[str, float], ...]
    injection: InjectionSpec
    categories: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()


ECOMMERCE_GMV = ScenarioDefinition(
    code="ecommerce_gmv_drop",
    name="电商 GMV 下滑归因",
    metric_code="gmv",
    metric_name="GMV",
    algebra="multiplicative",
    factors=(("visitors", 10000.0), ("cvr", 0.02), ("aov", 100.0)),
    injection=InjectionSpec(
        scenario_code="ecommerce_gmv_drop",
        metric_id=1,
        dimension_code="channel",
        dimension_values=("douyin",),
        window_start=date(2026, 8, 12),
        window_end=date(2026, 8, 18),
        amplitude=-0.35,
    ),
    categories=("手机数码", "家电"),
    channels=("douyin", "wechat", "search"),
)

FMCG_MARGIN = ScenarioDefinition(
    code="fmcg_margin_shift",
    name="快消品利润率异动归因",
    metric_code="profit",
    metric_name="利润",
    algebra="additive",
    factors=(("revenue", 1200.0), ("cost", 900.0)),
    injection=InjectionSpec(
        scenario_code="fmcg_margin_shift",
        metric_id=2,
        dimension_code="region",
        dimension_values=("east_china",),
        window_start=date(2026, 8, 20),
        window_end=date(2026, 8, 26),
        amplitude=-0.18,
        seed=7,
    ),
    categories=("洗护", "食品"),
    channels=("offline", "online"),
)

SCENARIOS: dict[str, ScenarioDefinition] = {
    ECOMMERCE_GMV.code: ECOMMERCE_GMV,
    FMCG_MARGIN.code: FMCG_MARGIN,
}


def generate_daily_rows(
    scenario: ScenarioDefinition,
    *,
    start: date,
    days: int = 30,
    dimension_field: str = "channel",
    seed: int = 42,
) -> list[dict]:
    """生成场景的日粒度明细行：每个维度每天一行，注入前数据平稳可预期。"""
    rng = random.Random(seed)
    dimensions = scenario.channels if dimension_field == "channel" else ("east_china", "south", "north")
    rows: list[dict] = []

    for offset in range(days):
        current = start + timedelta(days=offset)
        for index, dimension in enumerate(dimensions):
            base = scenario.factors[index % len(scenario.factors)][1]
            # 工作日/周末差异让序列看起来像真实经营数据
            weekday_factor = 1.12 if current.weekday() >= 5 else 1.0
            rows.append(
                {
                    "dt": current.isoformat(),
                    "channel": dimension,
                    "region": dimension,
                    "value": round(base * weekday_factor * rng.uniform(0.96, 1.04), 4),
                }
            )
    return rows


def detect_anomaly(
    rows: list[dict],
    *,
    dimension_field: str = "channel",
    window: tuple[date, date] | None = None,
    threshold: float = -0.10,
) -> list[dict]:
    """按维度对比异动窗与基准窗的均值，跌幅超过阈值即视为异动。

    window 为空时退化为前后两半对比，适合没有明确异动日的探索阶段；
    有明确窗口时必须按窗口比，否则窗口落在序列中段时跌幅会被稀释掉。
    """
    from collections import defaultdict

    by_dimension: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in rows:
        by_dimension[str(row[dimension_field])].append(
            (date.fromisoformat(str(row["dt"])), float(row["value"]))
        )

    detected: list[dict] = []
    for dimension, series in by_dimension.items():
        series.sort(key=lambda item: item[0])
        if window is not None:
            inside = [value for day, value in series if window[0] <= day <= window[1]]
            outside = [value for day, value in series if not (window[0] <= day <= window[1])]
            if not inside or not outside:
                continue
            baseline = sum(outside) / len(outside)
            recent = sum(inside) / len(inside)
        else:
            split = len(series) // 2
            baseline = sum(value for _, value in series[:split]) / max(split, 1)
            recent = sum(value for _, value in series[split:]) / max(len(series) - split, 1)

        change = (recent - baseline) / baseline if baseline else 0.0
        if change < threshold:
            detected.append({"dimension_value": dimension, "change_rate": round(change, 4)})
    return detected
