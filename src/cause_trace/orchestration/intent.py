"""意图理解：把自然语言归因需求解析为结构化意图（T-06 / FR-09）。

LLM 只负责抽取，规则负责兜底。指标编码、时间范围、基期三项中任一无法确定
时抛 ``BIZ_INVALID_INTENT``，由上层弹出表单让用户手动确认（Spec 13.2 降级路径）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from cause_trace.errors import InvalidIntentError

BASELINES = ("dod", "yoy", "target")

# LLM 返回的别名归一：模型对「日环比」「同比」的表述不统一
_BASELINE_ALIASES = {
    "dod": "dod",
    "day_over_day": "dod",
    "日环比": "dod",
    "环比": "dod",
    "yoy": "yoy",
    "year_over_year": "yoy",
    "同比": "yoy",
    "target": "target",
    "目标差": "target",
    "目标": "target",
}

_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


@dataclass(frozen=True)
class Intent:
    """解析后的归因意图。"""

    metric_code: str
    window_start: datetime
    window_end: datetime
    baseline: str
    dimensions: tuple[str, ...] = ()
    raw_query: str = ""


def _normalize_baseline(value: str | None) -> str:
    key = (value or "").strip().lower()
    normalized = _BASELINE_ALIASES.get(key)
    if normalized is None:
        raise InvalidIntentError(f"无法识别的对比基期：{value!r}，可选 {list(BASELINES)}")
    return normalized


def _parse_datetime(value: str | None, field: str) -> datetime:
    text = (value or "").strip()
    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern)  # noqa: DTZ007 - 经营数据按本地时间解释
        except ValueError:
            continue
    raise InvalidIntentError(f"{field} 格式无法解析：{value!r}")


def resolve_window(
    start: str | None,
    end: str | None,
    *,
    fallback_days: int = 7,
    reference: datetime | None = None,
) -> tuple[datetime, datetime]:
    """时间窗口归一：缺省时取参考时刻往前 fallback_days 天。

    结束日期只给到「日」时补到当天 23:59:59，让「08-16 到 08-16」这类单日
    窗口可用——业务事件日历里大量故障和运营动作都是单日的。
    """
    reference = reference or datetime.now()  # noqa: DTZ005
    window_start = (
        _parse_datetime(start, "window_start") if start else reference - timedelta(days=fallback_days)
    )
    if end:
        window_end = _parse_datetime(end, "window_end")
        if _is_date_only(end):
            window_end = window_end.replace(hour=23, minute=59, second=59)
    else:
        window_end = reference
    if window_start >= window_end:
        raise InvalidIntentError("统计周期起点必须早于终点")
    return window_start, window_end


def _is_date_only(text: str) -> bool:
    return len(text.strip()) == 10


def parse_intent(
    *,
    metric_code: str | None,
    baseline: str | None,
    window_start: str | None = None,
    window_end: str | None = None,
    dimensions: list[str] | None = None,
    raw_query: str = "",
    known_metrics: list[str] | None = None,
) -> Intent:
    """校验并组装意图。known_metrics 提供时校验指标编码是否在字典内。"""
    code = (metric_code or "").strip()
    if not code:
        raise InvalidIntentError("缺少目标指标编码")
    if known_metrics and code not in known_metrics:
        raise InvalidIntentError(f"指标 {code} 不在指标字典内")

    start, end = resolve_window(window_start, window_end)
    return Intent(
        metric_code=code,
        window_start=start,
        window_end=end,
        baseline=_normalize_baseline(baseline),
        dimensions=tuple(dimensions or ()),
        raw_query=raw_query,
    )


# 预置假设模板（Spec 13.2 降级路径）：LLM 不可用时按因子异动特征套用
FALLBACK_HYPOTHESIS_TEMPLATES: dict[str, str] = {
    "channel": "流量结构变化：低转化渠道占比提升，拉低整体转化率",
    "stock": "品类断货：部分 SKU 缺货导致可成交订单减少、客单价下滑",
    "refund": "退款率上升：售后问题或活动凑单导致净销售额下降",
    "price": "价格调整：促销折扣加深导致客单价下降",
    "external": "外部事件冲击：竞品动作或平台活动分流用户",
}

_HYPOTHESIS_TRIGGERS = {
    "channel": ("转化率", "流量", "渠道"),
    "stock": ("断货", "缺货", "库存"),
    "refund": ("退款", "售后"),
    "price": ("价格", "客单价", "折扣"),
    "external": ("竞品", "大促", "活动"),
}


def fallback_hypotheses(query: str, limit: int = 5) -> list[str]:
    """LLM 降级时的规则模板生成：命中关键词即产出对应假设。"""
    text = (query or "").lower()
    hits = [
        template
        for key, template in FALLBACK_HYPOTHESIS_TEMPLATES.items()
        if any(word in text for word in _HYPOTHESIS_TRIGGERS[key])
    ]
    if not hits:
        hits = [
            FALLBACK_HYPOTHESIS_TEMPLATES["channel"],
            FALLBACK_HYPOTHESIS_TEMPLATES["price"],
        ]
    return hits[:limit]


__all__ = [
    "BASELINES",
    "FALLBACK_HYPOTHESIS_TEMPLATES",
    "Intent",
    "fallback_hypotheses",
    "parse_intent",
    "resolve_window",
]
