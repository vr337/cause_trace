"""T-09：事件窗口匹配与因果链组装。"""

from __future__ import annotations

from datetime import datetime

from cause_trace.causal import BusinessEventInput, build_causal_links, match_events


def _dt(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d")


def test_event_within_three_day_window_is_matched():
    events = [
        BusinessEventInput(
            name="竞品A百亿补贴",
            event_type="external",
            window_start=_dt("2026-08-12"),
            window_end=_dt("2026-08-13"),
            categories=("手机数码",),
            channels=("douyin",),
            metrics=("gmv",),
        )
    ]
    matched = match_events(
        _dt("2026-08-15"),
        _dt("2026-08-18"),
        events,
        categories=("手机数码",),
        channels=("douyin",),
        metric_code="gmv",
    )
    assert len(matched) == 1
    assert matched[0].is_causal
    assert matched[0].relevance == 1.0


def test_event_outside_window_is_ignored():
    events = [
        BusinessEventInput(
            name="上周活动",
            event_type="promo",
            window_start=_dt("2026-07-01"),
            window_end=_dt("2026-07-02"),
        )
    ]
    matched = match_events(_dt("2026-08-15"), _dt("2026-08-18"), events)
    assert matched == []


def test_time_only_overlap_does_not_enter_causal_chain():
    # 时间重合但品类/渠道/指标都不重合，不算外生解释变量
    events = [
        BusinessEventInput(
            name="无关活动",
            event_type="operation",
            window_start=_dt("2026-08-16"),
            window_end=_dt("2026-08-17"),
            categories=("生鲜",),
        )
    ]
    matched = match_events(
        _dt("2026-08-15"), _dt("2026-08-18"), events, categories=("手机数码",), metric_code="gmv"
    )
    assert len(matched) == 1
    assert not matched[0].is_causal
    assert matched[0].relevance < 1.0


def test_events_sorted_by_relevance():
    events = [
        BusinessEventInput(
            name="仅时间重合",
            event_type="operation",
            window_start=_dt("2026-08-16"),
            window_end=_dt("2026-08-16"),
        ),
        BusinessEventInput(
            name="时间+品类重合",
            event_type="promo",
            window_start=_dt("2026-08-15"),
            window_end=_dt("2026-08-16"),
            categories=("手机数码",),
        ),
    ]
    matched = match_events(
        _dt("2026-08-15"), _dt("2026-08-18"), events, categories=("手机数码",)
    )
    assert [m.event.name for m in matched] == ["时间+品类重合", "仅时间重合"]


def test_no_dimension_filter_yields_base_time_relevance():
    # 未提供品类/渠道/指标条件时只按时间重合计分，不应拿到维度加分
    events = [
        BusinessEventInput(
            name="平台故障",
            event_type="fault",
            window_start=_dt("2026-08-15"),
            window_end=_dt("2026-08-15"),
            categories=("手机",),
        )
    ]
    matched = match_events(_dt("2026-08-15"), _dt("2026-08-18"), events)
    assert len(matched) == 1
    assert matched[0].overlap_days > 0
    assert matched[0].relevance == 0.4


def test_causal_links_combine_internal_and_external():
    events = [
        BusinessEventInput(
            name="818家电节",
            event_type="promo",
            window_start=_dt("2026-08-12"),
            window_end=_dt("2026-08-14"),
            categories=("家电",),
        )
    ]
    matched = match_events(_dt("2026-08-15"), _dt("2026-08-18"), events, categories=("家电",))
    links = build_causal_links(
        matched,
        internal_factors=[{"name": "转化率下降", "contribution_rate": -0.32, "summary": "渠道结构恶化"}],
    )

    roles = {link["role"] for link in links}
    assert roles == {"internal", "external"}
    # 只给了品类条件，事件命中品类，重合度 = 0.4 基础分 + 0.25 品类分
    assert links[0]["contribution"] == 0.65
    assert any(link["name"] == "转化率下降" for link in links)


def test_causal_links_skips_non_causal_events():
    events = [
        BusinessEventInput(
            name="无关",
            event_type="operation",
            window_start=_dt("2026-08-16"),
            window_end=_dt("2026-08-16"),
            categories=("生鲜",),
        )
    ]
    matched = match_events(_dt("2026-08-15"), _dt("2026-08-18"), events, categories=("家电",))
    assert build_causal_links(matched) == []
