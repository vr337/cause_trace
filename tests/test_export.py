"""T-22：三格式导出共用同一份 payload，内容必须一致。"""

from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from cause_trace.export import ExportUnavailableError, render, render_excel, render_markdown, render_pdf
from cause_trace.report import SECTION_DEFINITIONS, empty_section_payload

META = {
    "title": "8 月 GMV 下滑归因报告",
    "domain_id": 1,
    "metric_id": 1,
    "window_start": "2026-08-12",
    "window_end": "2026-08-18",
    "baseline": "dod",
}

CONTENTS = {
    "background": {"summary": "GMV 日环比 -12.3%，差异额 -1,432 万"},
    "factor_contribution": {
        "contributions": [
            {"factor": "访客数", "contribution": -320.0, "contribution_rate": -0.45, "direction": "down"},
            {"factor": "转化率", "contribution": -228.0, "contribution_rate": -0.32, "direction": "down"},
        ]
    },
    "action_plan": {
        "actions": [
            {"factor": "渠道预算重配", "role": "渠道运营负责人", "period_days": 7, "expected_recovery": 286.0}
        ]
    },
}


def _payload() -> dict:
    return empty_section_payload(META, CONTENTS)


def test_markdown_contains_all_sections():
    artifact = render_markdown(_payload())
    text = artifact.content.decode("utf-8")

    assert artifact.filename.endswith(".md")
    for index, (_, title) in enumerate(SECTION_DEFINITIONS, start=1):
        assert f"## {index}. {title}" in text
    assert "-1,432 万" in text


def test_markdown_renders_contribution_table():
    text = render_markdown(_payload()).content.decode("utf-8")
    assert "| 因子 | 贡献量 | 贡献率 | 方向 |" in text
    assert "| 访客数 | -320.0 | -45.0% | down |" in text


def test_markdown_renders_action_table():
    text = render_markdown(_payload()).content.decode("utf-8")
    assert "| 渠道预算重配 | 渠道运营负责人 | 7 | 286.0 |" in text


def test_excel_has_one_sheet_per_section_plus_overview():
    artifact = render_excel(_payload())
    workbook = load_workbook(io.BytesIO(artifact.content))

    assert workbook.sheetnames[0] == "报告概览"
    assert len(workbook.sheetnames) == 8
    assert workbook["报告概览"]["A1"].value == "报告标题"
    assert workbook["2 因子拆解"]["A1"].value == "因子贡献率拆解"


def test_excel_writes_contribution_rows():
    workbook = load_workbook(io.BytesIO(render_excel(_payload()).content))
    sheet = workbook["2 因子拆解"]
    values = [cell.value for cell in sheet[3]]
    assert values == ["factor", "contribution", "contribution_rate", "direction"]


def test_invalid_payload_is_rejected_before_export():
    payload = _payload()
    payload["sections"].pop()
    with pytest.raises(Exception) as exc_info:
        render_markdown(payload)
    assert "payload" in str(exc_info.value) or "章节" in str(exc_info.value)


def test_pdf_reports_missing_dependency_clearly():
    # WeasyPrint 未安装时应给出可操作提示，而不是静默产出损坏文件
    try:
        artifact = render_pdf(_payload())
    except ExportUnavailableError as exc:
        assert "weasyprint" in str(exc).lower()
    else:
        assert artifact.content.startswith(b"%PDF")


def test_render_dispatches_by_format():
    for name in ("markdown", "excel"):
        assert render(name, _payload()).content


def test_unknown_format_is_rejected():
    with pytest.raises(ValueError):
        render("docx", _payload())


def test_html_escaping_prevents_template_injection():
    payload = _payload()
    payload["meta"]["title"] = "<script>alert(1)</script>"
    try:
        artifact = render_pdf(payload)
    except ExportUnavailableError:
        pytest.skip("WeasyPrint 未安装")
    assert b"<script>" not in artifact.content
