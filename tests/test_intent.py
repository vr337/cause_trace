"""T-06：意图解析与降级假设模板。"""

from __future__ import annotations

import pytest

from cause_trace.errors import InvalidIntentError
from cause_trace.orchestration.intent import (
    fallback_hypotheses,
    parse_intent,
    resolve_window,
)


def test_parse_intent_normalizes_baseline_aliases():
    intent = parse_intent(metric_code="gmv", baseline="日环比", window_start="2026-08-01", window_end="2026-08-08")
    assert intent.baseline == "dod"
    assert intent.metric_code == "gmv"


def test_parse_intent_rejects_unknown_metric():
    with pytest.raises(InvalidIntentError) as exc_info:
        parse_intent(metric_code="unknown", baseline="dod", known_metrics=["gmv", "profit"])
    assert exc_info.value.code == "BIZ_INVALID_INTENT"


def test_parse_intent_requires_baseline():
    with pytest.raises(InvalidIntentError):
        parse_intent(metric_code="gmv", baseline=None)


def test_parse_intent_rejects_inverted_window():
    with pytest.raises(InvalidIntentError):
        resolve_window("2026-08-08", "2026-08-01")


def test_resolve_window_defaults_to_reference_minus_days():
    start, end = resolve_window(None, None, fallback_days=7, reference=_dt("2026-08-08"))
    assert (end - start).days == 7


def test_resolve_window_accepts_slash_format():
    start, end = resolve_window("2026/08/01", "2026/08/08")
    assert start.year == 2026 and start.month == 8 and start.day == 1


def test_fallback_hypotheses_match_keywords():
    hits = fallback_hypotheses("为什么转化率下降，是不是低转化渠道占比提升")
    assert any("渠道" in h for h in hits)


def test_fallback_hypotheses_returns_default_when_no_match():
    hits = fallback_hypotheses("随便看看")
    assert len(hits) >= 2


def test_fallback_hypotheses_respects_max_count():
    hits = fallback_hypotheses("转化率 断货 退款 价格 竞品", limit=5)
    assert len(hits) <= 5


def _dt(text: str):
    from datetime import datetime

    return datetime.strptime(text, "%Y-%m-%d")
