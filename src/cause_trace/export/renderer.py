"""报告三格式导出（T-22 / FR-16）。

三种格式共用同一份七章节 payload（ADR-05/07），保证内容一致：
Markdown 走 Jinja2，Excel 走 openpyxl，PDF 走 WeasyPrint（可选依赖，
未安装时明确报错而不是悄悄降级成别的东西）。
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from cause_trace.report.schema import validate_report_payload

SECTION_SHEET_NAMES = {
    "background": "1 异动背景",
    "factor_contribution": "2 因子拆解",
    "drilldown_evidence": "3 下钻证据",
    "conclusion": "4 归因结论",
    "evidence_chain": "5 证据链",
    "what_if": "6 What-If",
    "action_plan": "7 策略清单",
}

HEADER_FILL = PatternFill("solid", fgColor="0F172A")
HEADER_FONT = Font(color="FFFFFF", bold=True)


class ExportUnavailableError(RuntimeError):
    """导出依赖缺失（如未安装 WeasyPrint）。"""


@dataclass(frozen=True)
class ExportArtifact:
    filename: str
    media_type: str
    content: bytes


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("meta", {})


def render_markdown(payload: dict[str, Any]) -> ExportArtifact:
    validate_report_payload(payload)
    meta = _meta(payload)

    lines = [f"# {meta.get('title', '经营归因报告')}", ""]
    lines.append(
        f"> 统计周期：{meta.get('window_start', '')} ~ {meta.get('window_end', '')}  "
        f"｜ 对比基期：{meta.get('baseline', '')}"
    )
    lines.append("")

    for index, section in enumerate(payload["sections"], start=1):
        lines.append(f"## {index}. {section['title']}")
        lines.append("")
        lines.extend(_render_section_markdown(section["content"]))
        lines.append("")

    return ExportArtifact(
        filename=f"{meta.get('title', 'report')}.md",
        media_type="text/markdown; charset=utf-8",
        content="\n".join(lines).encode("utf-8"),
    )


def _render_section_markdown(content: dict[str, Any]) -> list[str]:
    """章节内容按已知键渲染；未知结构退化为 JSON 代码块，避免导出丢信息。"""
    if not content:
        return ["_本章节暂无内容_"]
    if "summary" in content and isinstance(content["summary"], str):
        return [content["summary"]]

    if "contributions" in content and isinstance(content["contributions"], list):
        lines = ["| 因子 | 贡献量 | 贡献率 | 方向 |", "| --- | --- | --- | --- |"]
        for item in content["contributions"]:
            lines.append(
                f"| {item.get('factor', '')} | {item.get('contribution', 0)} "
                f"| {float(item.get('contribution_rate', 0)) * 100:.1f}% "
                f"| {item.get('direction', '')} |"
            )
        return lines

    if "actions" in content and isinstance(content["actions"], list):
        lines = ["| 动作 | 责任岗位 | 周期（天） | 预期收益 |", "| --- | --- | --- | --- |"]
        for action in content["actions"]:
            lines.append(
                f"| {action.get('factor', '')} | {action.get('role', '')} "
                f"| {action.get('period_days', '')} | {action.get('expected_recovery', '')} |"
            )
        return lines

    return ["```json", str(content), "```"]


def render_excel(payload: dict[str, Any]) -> ExportArtifact:
    validate_report_payload(payload)
    meta = _meta(payload)

    workbook = Workbook()
    overview = workbook.active
    overview.title = "报告概览"
    overview.append(["报告标题", meta.get("title", "")])
    overview.append(["统计周期", f"{meta.get('window_start', '')} ~ {meta.get('window_end', '')}"])
    overview.append(["对比基期", meta.get("baseline", "")])
    for row in overview.iter_rows(min_row=1, max_row=3):
        row[0].font = Font(bold=True, color="FFFFFF")
        row[0].fill = HEADER_FILL

    for section in payload["sections"]:
        sheet = workbook.create_sheet(SECTION_SHEET_NAMES.get(section["id"], section["id"])[:31])
        sheet.append([section["title"]])
        sheet["A1"].font = Font(bold=True, size=13)
        sheet.append([])
        _write_section_sheet(sheet, section["content"])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return ExportArtifact(
        filename=f"{meta.get('title', 'report')}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=buffer.getvalue(),
    )


def _write_section_sheet(sheet, content: dict[str, Any]) -> None:
    if not content:
        sheet.append(["暂无内容"])
        return

    if isinstance(content.get("summary"), str):
        sheet.append([content["summary"]])
        sheet.append([])

    for key in ("contributions", "slices", "actions", "hypotheses"):
        rows = content.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        headers = list(rows[0].keys())
        sheet.append(headers)
        header_row = sheet.max_row
        for column, _ in enumerate(headers, start=1):
            cell = sheet.cell(row=header_row, column=column)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center")
        for row in rows:
            sheet.append([row.get(header, "") for header in headers])
        sheet.append([])


def render_pdf(payload: dict[str, Any]) -> ExportArtifact:
    validate_report_payload(payload)
    try:
        from weasyprint import HTML  # noqa: PLC0415 - 可选依赖，按需导入
    except ImportError as exc:
        raise ExportUnavailableError(
            "未安装 WeasyPrint，PDF 导出不可用；请执行 `uv add weasyprint`"
        ) from exc

    meta = _meta(payload)
    sections_html = []
    for index, section in enumerate(payload["sections"], start=1):
        body = _render_section_markdown(section["content"])
        sections_html.append(
            f"<section><h2>{index}. {_escape(section['title'])}</h2>"
            f"<pre>{_escape(chr(10).join(body))}</pre></section>"
        )

    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
  body {{ font-family: "Noto Sans CJK SC", sans-serif; font-size: 11pt; color: #0f172a; }}
  h1 {{ font-size: 18pt; margin-bottom: 4pt; }}
  h2 {{ font-size: 13pt; margin-top: 16pt; border-left: 3pt solid #0f172a; padding-left: 6pt; }}
  pre {{ white-space: pre-wrap; font-family: inherit; margin: 4pt 0; }}
  .meta {{ color: #515d78; font-size: 9pt; }}
</style></head><body>
<h1>{_escape(meta.get("title", "经营归因报告"))}</h1>
<p class="meta">统计周期：{_escape(str(meta.get("window_start", "")))} ~
{_escape(str(meta.get("window_end", "")))} ｜ 对比基期：{_escape(str(meta.get("baseline", "")))}</p>
{"".join(sections_html)}
</body></html>"""

    pdf_bytes = HTML(string=html).write_pdf()
    return ExportArtifact(
        filename=f"{meta.get('title', 'report')}.pdf",
        media_type="application/pdf",
        content=pdf_bytes,
    )


def _escape(text: str) -> str:
    """报告标题与内容可能含用户输入，进 HTML 前一律转义（Spec 16.4）。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


RENDERERS = {
    "markdown": (render_markdown, "text/markdown; charset=utf-8"),
    "excel": (render_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pdf": (render_pdf, "application/pdf"),
}


def render(format_name: str, payload: dict[str, Any]) -> ExportArtifact:
    if format_name not in RENDERERS:
        raise ValueError(f"不支持的导出格式：{format_name}，可选 {sorted(RENDERERS)}")
    renderer, _ = RENDERERS[format_name]
    return renderer(payload)
