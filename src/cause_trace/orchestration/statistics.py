"""统计检验：相关性与显著性（T-08 / FR-11 假设验证的置信度来源）。

沙箱只负责执行取数与计算，判定逻辑必须服务端固定——否则同样的数据会因
Python 版本或库实现差异得到不同的置信度。这里用纯标准库实现 t 分布，
避免为一个小函数引入 scipy 依赖。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CorrelationResult:
    coefficient: float
    p_value: float
    sample_size: int


@dataclass(frozen=True)
class ConfidenceResult:
    confidence: float
    p_value: float | None
    effect_size: float
    basis: str


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def pearson_correlation(x: list[float], y: list[float]) -> CorrelationResult:
    """皮尔逊相关系数与双尾 p 值。

    常数序列（任一端无变化）判定为不相关：此时相关性在统计上无定义，
    作为假设证据应给 0 分而不是抛异常中断整个会话。
    """
    n = len(x)
    if n != len(y):
        raise ValueError("两组序列长度必须一致")
    if n < 3:
        raise ValueError("样本量不足，至少需要 3 个观测点")

    mx, my = _mean(x), _mean(y)
    dx = [v - mx for v in x]
    dy = [v - my for v in y]
    sxy = math.fsum(a * b for a, b in zip(dx, dy, strict=True))
    sxx = math.fsum(a * a for a in dx)
    syy = math.fsum(b * b for b in dy)
    if sxx <= 0 or syy <= 0:
        return CorrelationResult(coefficient=0.0, p_value=1.0, sample_size=n)

    r = sxy / math.sqrt(sxx * syy)
    r = max(-1.0, min(1.0, r))
    return CorrelationResult(coefficient=r, p_value=_p_value_from_r(r, n), sample_size=n)


def _p_value_from_r(r: float, n: int) -> float:
    """t = r·sqrt((n-2)/(1-r²))，双尾 p 值 = P(|T_df| ≥ t)。"""
    if abs(r) >= 1.0:
        return 0.0
    df = n - 2
    t_stat = abs(r) * math.sqrt(df / (1 - r * r))
    return _regularized_incomplete_beta(df / 2.0, 0.5, df / (df + t_stat * t_stat))


def _betacf(a: float, b: float, x: float) -> float:
    """不完全 beta 的连分式展开，收敛到 1e-14 即停。"""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b)，x 落在哪一侧决定用对称性还是直接展开。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    prefactor = math.exp(ln_beta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return prefactor * _betacf(a, b, x)
    return 1.0 - prefactor * _betacf(b, a, 1.0 - x)


def confidence_from_evidence(
    correlation: float | None = None,
    p_value: float | None = None,
    contribution_rate: float | None = None,
) -> ConfidenceResult:
    """综合显著性、效应量与贡献率给出假设置信度。

    权重固定为 0.5 / 0.2 / 0.3：相关性代表假设方向成立，显著性代表不是
    噪声，贡献率代表对总变动的解释力，三者缺一置信度都应明显下降。
    """
    parts: list[float] = []
    basis: list[str] = []

    if correlation is not None:
        parts.append(0.5 * min(abs(correlation), 1.0))
        basis.append("相关性")
    if p_value is not None:
        parts.append(0.2 * (1.0 - min(p_value, 0.05) / 0.05))
        basis.append("显著性")
    if contribution_rate is not None:
        parts.append(0.3 * min(abs(contribution_rate), 1.0))
        basis.append("贡献率")

    confidence = math.fsum(parts)
    return ConfidenceResult(
        confidence=round(min(confidence, 1.0), 4),
        p_value=p_value,
        effect_size=abs(correlation) if correlation is not None else 0.0,
        basis="+".join(basis) if basis else "无证据",
    )
