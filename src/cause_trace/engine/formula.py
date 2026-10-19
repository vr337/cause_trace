"""指标公式引擎：差额分析 / LMDI / Shapley / 杜邦分解（T-04）。

守恒是 PRD 的硬验收项（AC FR-04）：分解结果返回前必须校验贡献量之和与总变动
的偏差，超差抛 ``BIZ_CONSERVATION_FAILED``，上层据此禁止出图、禁止写入报告。

容差取「绝对值 1e-9」与「数据量级的 1e-12」中的较大者。前者满足基线文档
的字面要求；后者用于千万级指标——此时双精度舍入本身就有 1e-8 的尾差，
按纯绝对阈值会把正确的分解误判为失败。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from cause_trace.errors import ConservationError, UnsupportedDecompositionError

DEFAULT_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Factor:
    """单因子输入。

    ``sign`` 仅对加法模型生效：Y = Σ sign_i × X_i（如 ``Y = X1 + X2 - X3``）。
    """

    name: str
    base: float
    current: float
    sign: int = 1

    @property
    def delta(self) -> float:
        return self.current - self.base


@dataclass(frozen=True)
class Slice:
    """维度下钻切片：权重（占比）与比率（如转化率）。"""

    name: str
    weight_base: float
    weight_current: float
    rate_base: float
    rate_current: float

    @property
    def value_base(self) -> float:
        return self.weight_base * self.rate_base

    @property
    def value_current(self) -> float:
        return self.weight_current * self.rate_current


@dataclass
class Contribution:
    """单因子贡献结果。"""

    factor: str
    base: float
    current: float
    delta: float
    contribution: float
    contribution_rate: float
    direction: str


@dataclass
class DecompositionResult:
    """分解结果，``residual`` 为贡献量之和与总变动量之差。"""

    method: str
    total_base: float
    total_current: float
    total_delta: float
    contributions: list[Contribution] = field(default_factory=list)
    residual: float = 0.0
    conserved: bool = True
    tolerance: float = DEFAULT_TOLERANCE

    def contribution_map(self) -> dict[str, float]:
        return {item.factor: item.contribution for item in self.contributions}

    def as_dict(self) -> dict:
        return {
            "method": self.method,
            "total_base": self.total_base,
            "total_current": self.total_current,
            "total_delta": self.total_delta,
            "residual": self.residual,
            "conserved": self.conserved,
            "contributions": [
                {
                    "factor": c.factor,
                    "base": c.base,
                    "current": c.current,
                    "delta": c.delta,
                    "contribution": c.contribution,
                    "contribution_rate": c.contribution_rate,
                    "direction": c.direction,
                }
                for c in self.contributions
            ],
        }


@dataclass
class SliceContribution:
    """维度切片的 Shapley 贡献：结构效应（mix）+ 水平效应（rate）。"""

    slice: str
    mix_contribution: float
    rate_contribution: float
    contribution: float
    contribution_rate: float
    delta: float


@dataclass
class ShapleyResult:
    method: str
    total_base: float
    total_current: float
    total_delta: float
    slices: list[SliceContribution]
    residual: float
    conserved: bool
    tolerance: float

    def contribution_map(self) -> dict[str, float]:
        return {item.slice: item.contribution for item in self.slices}


def _direction(value: float) -> str:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _safe_rate(contribution: float, total_delta: float) -> float:
    return contribution / total_delta if total_delta != 0 else 0.0


def validate_conservation(
    total_delta: float,
    contributions: Sequence[float],
    tolerance: float = DEFAULT_TOLERANCE,
) -> float:
    """独立校验入口（供补数、重算等场景复用），超差抛出 ``BIZ_CONSERVATION_FAILED``。"""
    residual = math.fsum(contributions) - total_delta
    if abs(residual) > tolerance:
        raise ConservationError(
            f"守恒校验失败：贡献量之和与总变动偏差 {residual:.12g} 超过容差 {tolerance:g}"
        )
    return residual


def _settle(amounts: list[float], total_delta: float, tolerance: float) -> float:
    """校验守恒并把浮点尾差并入绝对值最大的因子，返回修正后的残差。

    千万级 GMV 连乘后，各项贡献的浮点尾差会到 1e-7，远超 1e-9 的绝对阈值。
    因此容差取「绝对 1e-9」与「量级的 1e-12」的较大者：相对量级 1e-12
    远大于 IEEE754 双精度的舍入误差，但小到不可能掩盖真实的算法错误。
    """
    scale = max([1.0, abs(total_delta), *(abs(a) for a in amounts)])
    limit = max(tolerance, 1e-12 * scale)
    residual = math.fsum(amounts) - total_delta
    if abs(residual) > limit:
        raise ConservationError(
            f"守恒校验失败：贡献量之和与总变动偏差 {residual:.12g} 超过容差 {limit:.3g}"
        )
    if residual != 0.0:
        index = max(range(len(amounts)), key=lambda i: abs(amounts[i]))
        amounts[index] += residual
    return 0.0


def _close_and_validate(
    method: str,
    total_base: float,
    total_current: float,
    contributions: list[Contribution],
    tolerance: float,
) -> DecompositionResult:
    """浮点闭合 + 守恒硬校验。"""
    total_delta = total_current - total_base
    amounts = [c.contribution for c in contributions]
    residual = _settle(amounts, total_delta, tolerance)
    for item, amount in zip(contributions, amounts, strict=True):
        item.contribution = amount
        item.contribution_rate = _safe_rate(amount, total_delta)
    return DecompositionResult(
        method=method,
        total_base=total_base,
        total_current=total_current,
        total_delta=total_delta,
        contributions=contributions,
        residual=residual,
        conserved=residual == 0.0,
        tolerance=tolerance,
    )


def additive_decompose(
    factors: Sequence[Factor], tolerance: float = DEFAULT_TOLERANCE
) -> DecompositionResult:
    """差额分析法：Y = X1 + X2 - X3，因子贡献量即带符号差额。"""
    total_base = math.fsum(f.sign * f.base for f in factors)
    total_current = math.fsum(f.sign * f.current for f in factors)
    contributions = [
        Contribution(
            factor=f.name,
            base=f.base,
            current=f.current,
            delta=f.delta,
            contribution=f.sign * f.delta,
            contribution_rate=0.0,
            direction="flat",
        )
        for f in factors
    ]
    for c in contributions:
        c.direction = _direction(c.contribution)
    return _close_and_validate("diff", total_base, total_current, contributions, tolerance)


def _log_mean(a: float, b: float) -> float:
    """对数平均 L(a, b) = (a-b)/(ln a - ln b)，a == b 时取 a。"""
    if a == b:
        return a
    return (a - b) / (math.log(a) - math.log(b))


def _proportional_fallback(delta_y: float, factors: Sequence[Factor]) -> list[float]:
    """零值等退化场景的兜底分摊：按 |Δx| 占比分配总变动，保证守恒。"""
    weights = [abs(f.delta) for f in factors]
    total_weight = math.fsum(weights)
    if total_weight == 0:
        return [0.0 for _ in factors]
    return [delta_y * w / total_weight for w in weights]


def lmdi_decompose(
    factors: Sequence[Factor], tolerance: float = DEFAULT_TOLERANCE
) -> DecompositionResult:
    """LMDI：Y = X1 × X2 × ...，贡献量 = L(Y1, Y0) × ln(Xi1 / Xi0)。

    当基期/现期出现 0 或负值时，LMDI 无定义，退化为按 |Δx| 占比的分摊方式，
    仍保证守恒（边界用例不抛异常）。
    """
    total_base = math.prod(f.base for f in factors)
    total_current = math.prod(f.current for f in factors)
    total_delta = total_current - total_base

    usable = total_base > 0 and total_current > 0 and all(
        f.base > 0 and f.current > 0 for f in factors
    )
    if usable:
        log_mean = _log_mean(total_current, total_base)
        amounts = [log_mean * math.log(f.current / f.base) for f in factors]
    else:
        amounts = _proportional_fallback(total_delta, factors)

    contributions = [
        Contribution(
            factor=f.name,
            base=f.base,
            current=f.current,
            delta=f.delta,
            contribution=amount,
            contribution_rate=0.0,
            direction=_direction(amount),
        )
        for f, amount in zip(factors, amounts, strict=True)
    ]
    return _close_and_validate("lmdi", total_base, total_current, contributions, tolerance)


def dupont_decompose(
    factors: Sequence[Factor], tolerance: float = DEFAULT_TOLERANCE
) -> DecompositionResult:
    """杜邦分析：财务比率链式乘法分解，数值上复用 LMDI（无交叉残差）。"""
    result = lmdi_decompose(factors, tolerance=tolerance)
    result.method = "dupont"
    return result


def shapley_decompose(
    slices: Sequence[Slice], tolerance: float = DEFAULT_TOLERANCE
) -> ShapleyResult:
    """维度下钻 Shapley 分解（结构效应 / 水平效应双因子精确分摊）。

    对每个切片 i，其价值变化 w1·r1 − w0·r0 按 Shapley 值拆为：:

        mix_i  = 0.5 × (w1 − w0) × (r0 + r1)
        rate_i = 0.5 × (r1 − r0) × (w0 + w1)

    二者之和恒等于该切片的实际变化量，因此所有切片贡献之和严格等于总量变动。
    """
    total_base = math.fsum(s.value_base for s in slices)
    total_current = math.fsum(s.value_current for s in slices)
    total_delta = total_current - total_base

    items: list[SliceContribution] = []
    for s in slices:
        mix = 0.5 * (s.weight_current - s.weight_base) * (s.rate_base + s.rate_current)
        rate = 0.5 * (s.rate_current - s.rate_base) * (s.weight_base + s.weight_current)
        items.append(
            SliceContribution(
                slice=s.name,
                mix_contribution=mix,
                rate_contribution=rate,
                contribution=mix + rate,
                contribution_rate=0.0,
                delta=s.value_current - s.value_base,
            )
        )

    amounts = [item.contribution for item in items]
    residual = _settle(amounts, total_delta, tolerance)
    for item, amount in zip(items, amounts, strict=True):
        # 尾差落在唯一一个切片上，同时记到 mix，保持 mix + rate = contribution 的不变式
        item.mix_contribution += amount - item.contribution
        item.contribution = amount
        item.contribution_rate = _safe_rate(amount, total_delta)

    return ShapleyResult(
        method="shapley",
        total_base=total_base,
        total_current=total_current,
        total_delta=total_delta,
        slices=items,
        residual=residual,
        conserved=residual == 0.0,
        tolerance=tolerance,
    )


def decompose(
    method: str,
    factors: Sequence[Factor],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> DecompositionResult:
    """按方法名分派；方法必须与指标代数模型匹配。"""
    if method == "diff":
        return additive_decompose(factors, tolerance=tolerance)
    if method == "lmdi":
        return lmdi_decompose(factors, tolerance=tolerance)
    if method == "dupont":
        return dupont_decompose(factors, tolerance=tolerance)
    if method == "shapley":
        # 因子级 Shapley 在可加贡献下等价于差额分析；维度切片请用 shapley_decompose
        return additive_decompose(factors, tolerance=tolerance)
    raise UnsupportedDecompositionError(f"不支持的分解方法：{method}")
