"""敏感性模拟与建议引擎（T-10 / FR-13、FR-17）。

弹性系数拟合遵循 Spec 15.1：默认走历史回归，拟合优度不足时降级到指标字典
配置的经验弹性（方法二）。分段弹性（方法三）不在本次范围。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from cause_trace.engine.formula import Contribution

DEFAULT_MIN_R_SQUARED = 0.6
DEFAULT_ELASTICITY = 1.0
DEFAULT_CONFIDENCE_Z = 1.96  # 95% 置信水平


@dataclass
class ElasticityFit:
    factor: str
    elasticity: float
    r_squared: float
    method: str  # regression / empirical
    sample_size: int
    residual_std: float = 0.0

    def as_dict(self) -> dict:
        return {
            "factor": self.factor,
            "elasticity": self.elasticity,
            "r_squared": round(self.r_squared, 4),
            "method": self.method,
            "sample_size": self.sample_size,
            "residual_std": round(self.residual_std, 6),
        }


@dataclass
class Scenario:
    name: str
    metric_value: float
    delta: float
    delta_rate: float
    confidence_interval: tuple[float, float] = (0.0, 0.0)

    def as_dict(self) -> dict:
        return {
            "scenario_name": self.name,
            "metric_value": round(self.metric_value, 4),
            "delta": round(self.delta, 4),
            "delta_rate": round(self.delta_rate, 6),
            "confidence_interval": [
                round(self.confidence_interval[0], 4),
                round(self.confidence_interval[1], 4),
            ],
        }


@dataclass
class SimulationOutcome:
    baseline_value: float
    scenarios: list[Scenario] = field(default_factory=list)
    sensitivity_curve: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "baseline": {"metric_value": round(self.baseline_value, 4), "scenario_name": "基准情景"},
            "scenarios": [s.as_dict() for s in self.scenarios],
            "sensitivity_curve": self.sensitivity_curve,
        }


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def fit_elasticity(
    factor_name: str,
    y: list[float],
    x: list[float],
    *,
    empirical: float | None = None,
    min_r_squared: float = DEFAULT_MIN_R_SQUARED,
) -> ElasticityFit:
    """对数-对数 OLS：ln Y = α + β·ln X，β 即弹性系数。

    基期/现期出现 0 或负数时对数无定义，直接降级到经验弹性，避免为异常数据
    硬凑一个回归结果。
    """
    n = len(y)
    if n != len(x) or n < 3:
        return _empirical_fit(factor_name, empirical, n)

    if any(v <= 0 for v in y) or any(v <= 0 for v in x):
        return _empirical_fit(factor_name, empirical, n)

    ly = [math.log(v) for v in y]
    lx = [math.log(v) for v in x]
    mx, my = _mean(lx), _mean(ly)
    sxx = math.fsum((a - mx) ** 2 for a in lx)
    if sxx <= 0:
        return _empirical_fit(factor_name, empirical, n)

    sxy = math.fsum((a - mx) * (b - my) for a, b in zip(lx, ly, strict=True))
    beta = sxy / sxx
    alpha = my - beta * mx

    ss_res = math.fsum((b - (alpha + beta * a)) ** 2 for a, b in zip(lx, ly, strict=True))
    ss_tot = math.fsum((b - my) ** 2 for b in ly)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    if r_squared < min_r_squared:
        return _empirical_fit(factor_name, empirical, n)

    residual_std = math.sqrt(ss_res / (n - 2)) if n > 2 else 0.0
    return ElasticityFit(
        factor=factor_name,
        elasticity=round(beta, 6),
        r_squared=round(max(r_squared, 0.0), 6),
        method="regression",
        sample_size=n,
        residual_std=round(residual_std, 6),
    )


def _empirical_fit(factor_name: str, empirical: float | None, sample_size: int) -> ElasticityFit:
    """降级到指标字典的经验弹性；未配置时按线性 1.0 处理并在 UI 标注「经验值」。"""
    return ElasticityFit(
        factor=factor_name,
        elasticity=empirical if empirical is not None else DEFAULT_ELASTICITY,
        r_squared=0.0,
        method="empirical",
        sample_size=sample_size,
    )


def simulate(
    baseline_value: float,
    factor_adjustments: dict[str, float],
    fits: dict[str, ElasticityFit],
) -> SimulationOutcome:
    """多情景重算：ΔY/Y = Σ β_i × ΔX_i/X_i，按弹性系数线性外推。

    每个因子生成一个独立情景，便于前端做情景对比；区间由弹性残差决定，
    没有残差信息时按 5% 相对误差给一个保守区间。
    """
    if baseline_value == 0:
        baseline_value = 1.0

    outcome = SimulationOutcome(baseline_value=baseline_value)
    for factor_name, ratio in factor_adjustments.items():
        fit = fits.get(factor_name)
        if fit is None:
            continue
        delta_rate = fit.elasticity * (ratio - 1.0)
        metric_value = baseline_value * (1.0 + delta_rate)
        delta = metric_value - baseline_value

        relative_uncertainty = max(fit.residual_std * abs(delta_rate), 0.05 * abs(delta_rate), 0.01)
        half_width = abs(metric_value) * relative_uncertainty
        outcome.scenarios.append(
            Scenario(
                name=f"{factor_name} 调整至 {ratio:.2f}",
                metric_value=metric_value,
                delta=delta,
                delta_rate=delta_rate,
                confidence_interval=(
                    metric_value - DEFAULT_CONFIDENCE_Z * half_width,
                    metric_value + DEFAULT_CONFIDENCE_Z * half_width,
                ),
            )
        )
    return outcome


def sensitivity_curve(
    baseline_value: float,
    factor_name: str,
    fit: ElasticityFit,
    ratios: tuple[float, ...] = (0.8, 0.9, 1.0, 1.1, 1.2),
) -> dict:
    """敏感度曲线：按固定比例网格重算，供前端滑块实时渲染。"""
    values = [baseline_value * (1.0 + fit.elasticity * (ratio - 1.0)) for ratio in ratios]
    return {
        "factor": factor_name,
        "ratios": list(ratios),
        "metric_values": [round(v, 4) for v in values],
    }


def generate_strategies(
    contributions: list[Contribution],
    contributions_threshold: float = 0.05,
) -> list[dict]:
    """策略四要素强校验（FR-17）：因子、角色、周期、金额缺一即视为不通过。

    只有贡献率超过阈值的因子才生成策略——对总变动影响微弱的因子不值得占用
    业务方的执行资源。
    """
    role_by_direction = {"up": "品类运营负责人", "down": "渠道运营负责人", "flat": "数据分析师"}
    strategies: list[dict] = []

    for item in contributions:
        if abs(item.contribution_rate) < contributions_threshold:
            continue
        recovery_amount = abs(item.contribution)
        strategies.append(
            {
                "factor": item.factor,
                "role": role_by_direction[item.direction],
                "period_days": 14 if abs(item.contribution_rate) >= 0.2 else 7,
                "expected_recovery": round(recovery_amount, 4),
                "direction": item.direction,
                "contribution_rate": round(item.contribution_rate, 6),
            }
        )

    strategies.sort(key=lambda s: -s["expected_recovery"])
    return strategies


def validate_strategy(strategy: dict) -> bool:
    """四要素齐全才允许进入报告（Spec 1.3 策略可执行性）。"""
    required = ("factor", "role", "period_days", "expected_recovery")
    return all(strategy.get(key) is not None for key in required)
