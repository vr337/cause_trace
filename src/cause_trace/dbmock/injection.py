"""异动仿真注入（T-19 / FR-23）。

dbmock 按「时间窗 × 维度 × 指标 × 幅度」改写数仓数值，并同步写入
INJECTION_CONFIG / INJECTION_TRUTH 作为 ground truth。seed 固定可复现，
保证演示复盘时同样的配置注入出同样的数据。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cause_trace.db.models.governance import InjectionConfig, InjectionTruth


@dataclass(frozen=True)
class InjectionSpec:
    scenario_code: str
    metric_id: int
    dimension_code: str
    dimension_values: tuple[str, ...]
    window_start: date
    window_end: date
    amplitude: float  # 负数表示下滑，如 -0.35
    seed: int = 42


@dataclass
class InjectionResult:
    config_id: int
    rows_scanned: int = 0
    rows_affected: int = 0
    truth: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "config_id": self.config_id,
            "rows_scanned": self.rows_scanned,
            "rows_affected": self.rows_affected,
            "truth": self.truth,
        }


def _in_window(value: date, start: date, end: date) -> bool:
    return start <= value <= end


def inject_values(
    rows: list[dict],
    spec: InjectionSpec,
    *,
    value_field: str = "value",
    date_field: str = "dt",
    dimension_field: str | None = None,
) -> InjectionResult:
    """对内存中的行数据注入异动，返回受影响行数与 ground truth。

    dimension_field 为空表示整窗注入；否则只改命中维度取值的行——这正是
    「某渠道转化率下跌」这类场景的注入方式。
    """
    rng = random.Random(spec.seed)
    truth: list[dict] = []
    affected = 0

    for row in rows:
        raw_dt = row.get(date_field)
        try:
            if isinstance(raw_dt, str):
                row_date = datetime.strptime(raw_dt, "%Y-%m-%d").date()
            elif isinstance(raw_dt, datetime):
                row_date = raw_dt.date()
            elif isinstance(raw_dt, date):
                row_date = raw_dt
            else:
                continue
        except ValueError:
            # 脏数据跳过即可，不值得为一行坏日期中断整批注入
            continue

        if not _in_window(row_date, spec.window_start, spec.window_end):
            continue
        if dimension_field and row.get(dimension_field) not in spec.dimension_values:
            continue

        original = float(row.get(value_field, 0) or 0)
        # 每个维度值加一点随机扰动，避免注入后所有渠道跌幅完全一致、一眼假
        jitter = rng.uniform(0.9, 1.1)
        row[value_field] = original * (1 + spec.amplitude * jitter)
        affected += 1

    for value in spec.dimension_values:
        truth.append(
            {
                "dimension_value": value,
                "expected_effect": f"{spec.window_start}~{spec.window_end} {spec.amplitude:+.0%}",
            }
        )

    return InjectionResult(config_id=0, rows_scanned=len(rows), rows_affected=affected, truth=truth)


def persist_injection(session: Session, spec: InjectionSpec, result: InjectionResult) -> InjectionConfig:
    """把注入配置与 ground truth 落库；同一场景重复注入时复用配置行。"""
    config = session.scalar(
        select(InjectionConfig).where(
            InjectionConfig.scenario_code == spec.scenario_code,
            InjectionConfig.dimension_code == spec.dimension_code,
        )
    )
    if config is None:
        config = InjectionConfig(
            scenario_code=spec.scenario_code,
            metric_id=spec.metric_id,
            dimension_code=spec.dimension_code,
            window_start=datetime.combine(spec.window_start, datetime.min.time()),
            window_end=datetime.combine(spec.window_end, datetime.min.time()),
            amplitude=Decimal(str(spec.amplitude)),
            seed=spec.seed,
            status="enabled",
        )
        session.add(config)
        session.flush()
    else:
        config.amplitude = Decimal(str(spec.amplitude))
        config.seed = spec.seed
        config.window_start = datetime.combine(spec.window_start, datetime.min.time())
        config.window_end = datetime.combine(spec.window_end, datetime.min.time())
        session.flush()

    for item in result.truth:
        existing = session.scalar(
            select(InjectionTruth).where(
                InjectionTruth.config_id == config.id,
                InjectionTruth.dimension_value == item["dimension_value"],
            )
        )
        if existing is None:
            session.add(
                InjectionTruth(
                    config_id=config.id,
                    dimension_value=item["dimension_value"],
                    expected_effect=item["expected_effect"],
                )
            )
    session.flush()
    return config


def compare_with_truth(
    detected: list[dict], truth: list[InjectionTruth]
) -> dict:
    """验收对照：检出项与 ground truth 的交集、漏检与误报。"""
    truth_values = {item.dimension_value for item in truth}
    detected_values = {item.get("dimension_value") for item in detected if item.get("dimension_value")}

    matched = sorted(truth_values & detected_values)
    return {
        "matched": matched,
        "missed": sorted(truth_values - detected_values),
        "false_positive": sorted(detected_values - truth_values),
        "hit_rate": len(matched) / len(truth_values) if truth_values else 1.0,
    }
