"""因果知识引擎（T-09 / FR-12）：事件日历窗口匹配与因果链组装。

PRD 1.3 要求「异动窗口前后 3 日内的事件 100% 匹配，时间/品类/渠道重合的
事件进入因果链」。窗口判定按天数闭区间计算，避免边界事件因时分秒被漏掉。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

MATCH_WINDOW_DAYS = 3


@dataclass(frozen=True)
class BusinessEventInput:
    """事件输入，与业务事件日历页（PRD 7.3）字段一一对应。"""

    name: str
    event_type: str  # promo / operation / external / fault
    window_start: datetime | date
    window_end: datetime | date
    categories: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    remark: str = ""


@dataclass(frozen=True)
class MatchedEvent:
    event: BusinessEventInput
    overlap_days: int
    category_hit: bool
    channel_hit: bool
    metric_hit: bool

    @property
    def relevance(self) -> float:
        """重合度：时间重合为基础分，品类/渠道/指标各加分，封顶 1。"""
        score = 0.4
        if self.category_hit:
            score += 0.25
        if self.channel_hit:
            score += 0.2
        if self.metric_hit:
            score += 0.15
        return round(min(score, 1.0), 4)

    @property
    def is_causal(self) -> bool:
        """时间重合且至少一个维度命中，才作为外生解释变量进入因果链。"""
        return self.overlap_days > 0 and (self.category_hit or self.channel_hit or self.metric_hit)


def _as_date(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


def _intersect_days(
    a_start: datetime | date,
    a_end: datetime | date,
    b_start: datetime | date,
    b_end: datetime | date,
) -> int:
    """两个时间窗的重合天数，按闭区间计算，不重合返回 0。

    事件日历允许只给日期（单日故障很常见），会话窗口给的是 datetime，
    所以两边都统一到 date 再比。
    """
    start = max(_as_date(a_start), _as_date(b_start))
    end = min(_as_date(a_end), _as_date(b_end))
    if end < start:
        return 0
    return (end - start).days + 1


def match_events(
    anomaly_start: datetime | date,
    anomaly_end: datetime | date,
    events: list[BusinessEventInput],
    *,
    window_days: int = MATCH_WINDOW_DAYS,
    categories: tuple[str, ...] = (),
    channels: tuple[str, ...] = (),
    metric_code: str = "",
) -> list[MatchedEvent]:
    """匹配异动窗口前后 window_days 天内的业务事件，按重合度降序返回。"""
    search_start = anomaly_start - timedelta(days=window_days)
    search_end = anomaly_end + timedelta(days=window_days)

    matched: list[MatchedEvent] = []
    for event in events:
        overlap = _intersect_days(search_start, search_end, event.window_start, event.window_end)
        if overlap <= 0:
            continue
        # 维度命中按真实交集计算：调用方没给该维度条件时不计命中，避免「未筛选」被当成强相关
        category_hit = bool(categories) and bool(set(categories) & set(event.categories))
        channel_hit = bool(channels) and bool(set(channels) & set(event.channels))
        metric_hit = bool(metric_code) and metric_code in event.metrics
        matched.append(
            MatchedEvent(
                event=event,
                overlap_days=overlap,
                category_hit=category_hit,
                channel_hit=channel_hit,
                metric_hit=metric_hit,
            )
        )

    matched.sort(key=lambda m: (-m.relevance, -m.overlap_days, m.event.name))
    return matched


def build_causal_links(
    matched: list[MatchedEvent],
    internal_factors: list[dict] | None = None,
) -> list[dict]:
    """组装因果链：外部事件 + 内部因子合并，按贡献率降序。

    internal_factors 形如 [{"name": ..., "contribution_rate": ..., "summary": ...}]，
    由指标分解结果转换而来。
    """
    links: list[dict] = []

    for item in internal_factors or []:
        links.append(
            {
                "role": "internal",
                "event_id": None,
                "name": item.get("name", ""),
                "contribution": item.get("contribution_rate", 0.0),
                "summary": item.get("summary", ""),
            }
        )

    for match in matched:
        if not match.is_causal:
            continue
        links.append(
            {
                "role": "external",
                "event_id": None,
                "name": match.event.name,
                "contribution": match.relevance,
                "summary": (
                    f"{match.event.name}（{match.event.event_type}）于 {match.event.window_start:%Y-%m-%d} "
                    f"发生，与异动窗口重合 {match.overlap_days} 天"
                ),
            }
        )

    links.sort(key=lambda link: -abs(link["contribution"]))
    return links
