"""报告三格式导出（T-22 / FR-16）。

三种格式共用同一份七章节 payload（ADR-05/07），保证内容一致：
Markdown 走文本模板，Excel 走 openpyxl，PDF 走内置的极简 PDF 写入器。

PDF 选型说明：Spec ADR-07 原定 WeasyPrint，理由是「纯 Python 依赖」。但它
实际上依赖 GTK/Pango/Cairo 原生运行时，在 Windows 开发机上装不动整套 GTK。
这里改用自带的最小 PDF 生成器（无第三方依赖、无原生库），同样是服务端渲染、
同样共用 payload，代价是排版精度低于 WeasyPrint。若要换回 WeasyPrint，
只需把 render_pdf 换掉，另外两个格式不受影响。
"""

from __future__ import annotations

import io
import zlib
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
    """导出依赖缺失。"""


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
    if isinstance(content.get("summary"), str):
        return [content["summary"]]

    if isinstance(content.get("contributions"), list):
        lines = ["| 因子 | 贡献量 | 贡献率 | 方向 |", "| --- | --- | --- | --- |"]
        for item in content["contributions"]:
            lines.append(
                f"| {item.get('factor', '')} | {item.get('contribution', 0)} "
                f"| {float(item.get('contribution_rate', 0)) * 100:.1f}% "
                f"| {item.get('direction', '')} |"
            )
        return lines

    if isinstance(content.get("actions"), list):
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


# ---------- PDF：最小生成器 ----------

_PAGE_WIDTH, _PAGE_HEIGHT = 595.0, 842.0  # A4，单位 pt
_MARGIN = 56.0
_LINE_HEIGHT = 16.0


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _pdf_encode_text(text: str) -> str:
    """PDF 的内容流默认按 Latin-1 解释，中文必须先转成 UTF-16BE 的十六进制字面量。

    报告标题与正文都可能含中文，不转的话导出的是乱码。
    """
    if text.isascii():
        return _pdf_escape(text)
    hex_body = text.encode("utf-16-be").hex().upper()
    return f"<{hex_body}> Tj"


def _build_content_stream(payload: dict[str, Any]) -> str:
    """按章节顺序把标题与表格铺成 PDF 文本流，超出页面高度自动换页。"""
    meta = _meta(payload)
    ops: list[str] = ["BT", "1 0 0 1 0 0 Tm"]
    cursor_y = _PAGE_HEIGHT - _MARGIN
    left = _MARGIN

    def new_page() -> None:
        nonlocal cursor_y
        ops.append("ET")
        ops.append("E")
        ops.append("1 0 0 1 0 0 cm")
        ops.append("BT")
        cursor_y = _PAGE_HEIGHT - _MARGIN

    def draw(text: str, size: int, bold: bool = False) -> None:
        nonlocal cursor_y
        if cursor_y < _MARGIN + _LINE_HEIGHT:
            new_page()
        font = "/F2" if bold else "/F1"
        ops.extend([font, f"{size} Tf", f"{left} {cursor_y:.1f} Td", _pdf_encode_text(text)])
        cursor_y -= _LINE_HEIGHT * (size / 11.0)

    draw(meta.get("title", "经营归因报告"), 18, bold=True)
    draw(
        f"统计周期：{meta.get('window_start', '')} ~ {meta.get('window_end', '')} "
        f"｜ 对比基期：{meta.get('baseline', '')}",
        9,
    )
    cursor_y -= _LINE_HEIGHT

    for index, section in enumerate(payload["sections"], start=1):
        if cursor_y < _MARGIN + _LINE_HEIGHT * 3:
            new_page()
        draw(f"{index}. {section['title']}", 13, bold=True)
        for line in _render_section_markdown(section["content"]):
            draw(line, 9)
        cursor_y -= _LINE_HEIGHT * 0.5

    ops.append("ET")
    return "\n".join(ops)


def _pdf_object(number: int, body: bytes) -> bytes:
    return f"{number} 0 obj\n".encode() + body + b"\nendobj\n"


def _build_pdf(payload: dict[str, Any]) -> bytes:
    """拼一个最小 PDF 文件：1 页 Catalog + Pages + Page + 字体 + 内容流。

    不需要第三方库，代价是只能放文本、没有图表图片；图表在 Excel 与前端看板里看。
    """
    content = _build_content_stream(payload).encode("latin-1", "replace")
    compressed = zlib.compress(content)

    objects: list[bytes] = [
        _pdf_object(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        _pdf_object(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        _pdf_object(
            3,
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
                "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>"
            ).encode(),
        ),
        _pdf_object(4, b"<< /Length " + str(len(compressed)).encode() + b" /Filter /FlateDecode >>\nstream\n" + compressed + b"\nendstream"),
        _pdf_object(5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
        _pdf_object(6, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"),
    ]

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for body in objects:
        offsets.append(out.tell())
        out.write(body)
    xref_start = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode()
    )
    return out.getvalue()


def render_pdf(payload: dict[str, Any]) -> ExportArtifact:
    validate_report_payload(payload)
    meta = _meta(payload)
    return ExportArtifact(
        filename=f"{meta.get('title', 'report')}.pdf",
        media_type="application/pdf",
        content=_build_pdf(payload),
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
