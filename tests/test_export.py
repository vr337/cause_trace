"""T-22：三格式导出共用同一份 payload，内容必须一致。"""

from __future__ import annotations

import io
import zlib

import pytest
from openpyxl import load_workbook

from cause_trace.export import render, render_excel, render_markdown, render_pdf
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


def test_pdf_has_valid_header_and_non_trivial_size():
    artifact = render_pdf(_payload())
    assert artifact.content.startswith(b"%PDF-")
    assert artifact.content.rstrip().endswith(b"%%EOF")
    # 空白 PDF 只有几百字节，真实报告必须远超这个量级
    assert len(artifact.content) > 800


def test_pdf_contains_chinese_text_as_utf16_hex():
    """中文必须先转 UTF-16BE 十六进制，否则 PDF 里是乱码。

    内容流被 zlib 压缩过，所以先解压再断言。
    """
    artifact = render_pdf(_payload())
    stream = artifact.content.split(b"stream\n", 1)[1].rsplit(b"\nendstream", 1)[0]
    decompressed = zlib.decompress(stream)

    title = "8 月 GMV 下滑归因报告"
    hex_literal = f"<{title.encode('utf-16-be').hex().upper()}> Tj".encode()
    assert hex_literal in decompressed


def test_render_dispatches_all_three_formats():
    expected_extension = {"markdown": ".md", "excel": ".xlsx", "pdf": ".pdf"}
    for name, extension in expected_extension.items():
        artifact = render(name, _payload())
        assert artifact.content
        assert artifact.filename.endswith(extension)


def test_unknown_format_is_rejected():
    with pytest.raises(ValueError):
        render("docx", _payload())


def test_pdf_escaping_prevents_injection():
    payload = _payload()
    payload["meta"]["title"] = "<script>alert(1)</script>"
    artifact = render_pdf(payload)
    # 括号与反斜杠在 PDF 内容流里是语法字符，必须转义
    assert b"(alert" not in artifact.content.split(b"stream")[-1]
