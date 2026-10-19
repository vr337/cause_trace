"""T-01：七章节报告 payload schema 单测。"""

from __future__ import annotations

import pytest

from cause_trace.errors import ReportPayloadError
from cause_trace.report import (
    SECTION_DEFINITIONS,
    empty_section_payload,
    validate_report_payload,
)

META = {
    "title": "8 月 GMV 下滑归因报告",
    "domain_id": 1,
    "metric_id": 2,
    "window_start": "2026-08-12T00:00:00",
    "window_end": "2026-08-18T23:59:59",
    "baseline": "dod",
}


def test_empty_payload_with_seven_sections_is_valid():
    payload = empty_section_payload(META)
    assert validate_report_payload(payload) is payload
    assert [s["id"] for s in payload["sections"]] == [s for s, _ in SECTION_DEFINITIONS]


def test_missing_section_is_rejected():
    payload = empty_section_payload(META)
    payload["sections"].pop()
    with pytest.raises(ReportPayloadError):
        validate_report_payload(payload)


def test_wrong_section_order_is_rejected():
    payload = empty_section_payload(META)
    payload["sections"][0], payload["sections"][1] = payload["sections"][1], payload["sections"][0]
    with pytest.raises(ReportPayloadError):
        validate_report_payload(payload)


def test_invalid_baseline_is_rejected():
    payload = empty_section_payload({**META, "baseline": "week"})
    with pytest.raises(ReportPayloadError):
        validate_report_payload(payload)


def test_missing_meta_field_is_rejected():
    meta = dict(META)
    meta.pop("metric_id")
    with pytest.raises(ReportPayloadError):
        validate_report_payload(empty_section_payload(meta))
