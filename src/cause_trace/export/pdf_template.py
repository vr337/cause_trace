"""报告 PDF 的 HTML/CSS 模板（ADR-07：WeasyPrint 渲染）。

模板只负责排版：页眉页脚、章节分页、表格样式、瀑布图（内联 SVG）。
所有用户内容进模板前必须转义（Spec 16.4），模板里不出现 `| safe`。
"""

from __future__ import annotations

from typing import Any

CSS = """
@page {
  size: A4;
  margin: 20mm 16mm 18mm 16mm;
  @top-left {
    content: "cause_trace 经营归因分析";
    font-size: 8pt;
    color: #94a3b8;
  }
  @top-right {
    content: string(report-title);
    font-size: 8pt;
    color: #94a3b8;
  }
  @bottom-center {
    content: "第 " counter(page) " 页 / 共 " counter(pages) " 页";
    font-size: 8pt;
    color: #94a3b8;
  }
}

body {
  font-family: "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 10pt;
  line-height: 1.6;
  color: #0f172a;
}

h1 {
  string-set: report-title content();
  font-size: 20pt;
  margin: 0 0 6pt;
  color: #0b1f4b;
}

.meta {
  color: #64748b;
  font-size: 9pt;
  border-bottom: 2pt solid #1d4ed8;
  padding-bottom: 10pt;
  margin-bottom: 18pt;
}

section {
  page-break-inside: avoid;
  margin-bottom: 16pt;
}

h2 {
  font-size: 12.5pt;
  color: #0b1f4b;
  border-left: 4pt solid #1d4ed8;
  padding-left: 8pt;
  margin: 0 0 8pt;
}

p.summary {
  background: #f1f5f9;
  border-radius: 4pt;
  padding: 8pt 10pt;
  margin: 0 0 8pt;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 9pt;
}

th {
  background: #0f172a;
  color: #ffffff;
  text-align: left;
  padding: 5pt 8pt;
  font-weight: 600;
}

td {
  border-bottom: 0.5pt solid #e2e8f0;
  padding: 5pt 8pt;
}

tr:nth-child(even) td {
  background: #f8fafc;
}

.up { color: #dc2626; }
.down { color: #059669; }

.empty {
  color: #94a3b8;
  font-style: italic;
  font-size: 9pt;
}

.chart {
  margin: 10pt 0 4pt;
}

.chart-caption {
  color: #64748b;
  font-size: 8pt;
  text-align: center;
}

.strategy {
  border: 0.5pt solid #e2e8f0;
  border-radius: 4pt;
  padding: 8pt 10pt;
  margin-bottom: 6pt;
}
"""


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _waterfall_svg(contributions: list[dict[str, Any]], total_delta: float) -> str:
    """内联 SVG 瀑布图。

    不依赖 JS 或外部图表库——WeasyPrint 不执行脚本，ECharts 那套在这里跑不起来。
    用纯 SVG 画浮动柱，贡献正负用涨红跌绿区分，与前端看板保持一致。
    """
    if not contributions:
        return ""

    width, height = 640, 220
    pad_left, pad_top, pad_bottom = 8, 12, 34
    plot_width = width - pad_left * 2
    plot_height = height - pad_top - pad_bottom

    steps: list[tuple[str, float, float]] = []
    running = 0.0
    for item in contributions:
        start = running
        running += float(item.get("contribution", 0))
        steps.append((str(item.get("factor", "")), start, running))
    steps.append(("总变动", 0.0, float(total_delta)))

    values = [0.0]
    for _, start, end in steps:
        values.extend([start, end])
    low, high = min(values), max(values)
    span = high - low or 1.0

    def y_of(value: float) -> float:
        return pad_top + (high - value) / span * plot_height

    bar_width = plot_width / max(len(steps), 1) * 0.56
    slot = plot_width / max(len(steps), 1)

    parts = [
        f'<svg class="chart" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        f'<line x1="{pad_left}" y1="{y_of(0):.1f}" x2="{width - pad_left}" y2="{y_of(0):.1f}" '
        'stroke="#cbd5e1" stroke-width="0.8"/>',
    ]
    for index, (label, start, end) in enumerate(steps):
        x = pad_left + slot * index + (slot - bar_width) / 2
        top = y_of(max(start, end))
        bottom = y_of(min(start, end))
        bar_height = max(bottom - top, 1.0)
        if label == "总变动":
            color = "#0f172a"
        else:
            color = "#dc2626" if end - start >= 0 else "#059669"
        parts.append(
            f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_height:.1f}" fill="{color}" rx="1"/>'
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{max(top - 4, 10):.1f}" '
            f'font-size="8" text-anchor="middle" fill="#475569">'
            f"{_escape(f'{end - start:,.0f}' if label != '总变动' else f'{end:,.0f}')}</text>"
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{height - 10}" font-size="8" '
            f'text-anchor="middle" fill="#64748b">{_escape(label)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _render_content(section_id: str, content: dict[str, Any]) -> str:
    """按章节 id 渲染正文；未识别的结构退化为键值表，保证信息不丢。"""
    if not content:
        return '<p class="empty">本章节暂无内容</p>'

    if isinstance(content.get("summary"), str):
        return f'<p class="summary">{_escape(content["summary"])}</p>'

    if section_id == "factor_contribution" and isinstance(content.get("contributions"), list):
        contributions = content["contributions"]
        rows = [
            [
                _escape(str(item.get("factor", ""))),
                _escape(f"{float(item.get('contribution', 0)):,.2f}"),
                _escape(f"{float(item.get('contribution_rate', 0)) * 100:.1f}%"),
                f'<span class="{_escape(str(item.get("direction", "")))}">'
                f'{_escape(str(item.get("direction", "")))}</span>',
            ]
            for item in contributions
        ]
        total_delta = float(content.get("total_delta", 0.0)) or sum(
            float(item.get("contribution", 0)) for item in contributions
        )
        chart = _waterfall_svg(contributions, total_delta)
        caption = '<p class="chart-caption">因子贡献瀑布图（涨红跌绿）</p>' if chart else ""
        return chart + caption + _table(["因子", "贡献量", "贡献率", "方向"], rows)

    if section_id == "action_plan" and isinstance(content.get("actions"), list):
        cards = []
        for action in content["actions"]:
            cards.append(
                '<div class="strategy">'
                f'<strong>{_escape(str(action.get("factor", "")))}</strong><br/>'
                f'责任岗位：{_escape(str(action.get("role", "")))} ｜ '
                f'预期周期：{_escape(str(action.get("period_days", "")))} 天 ｜ '
                f'预期挽回：{_escape(f"{float(action.get("expected_recovery", 0)):,.2f}")} 元'
                "</div>"
            )
        return "".join(cards)

    rows = [[_escape(str(key)), _escape(str(value))] for key, value in content.items()]
    return _table(["字段", "内容"], rows)


def build_report_html(payload: dict[str, Any]) -> str:
    """把七章节 payload 渲染成完整 HTML 文档。"""
    meta = payload.get("meta", {})
    sections = []
    for index, section in enumerate(payload.get("sections", []), start=1):
        sections.append(
            "<section>"
            f"<h2>{index}. {_escape(str(section.get('title', '')))}</h2>"
            f"{_render_content(str(section.get('id', '')), section.get('content') or {})}"
            "</section>"
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{_escape(str(meta.get("title", "经营归因报告")))}</title>
<style>{CSS}</style>
</head>
<body>
<h1>{_escape(str(meta.get("title", "经营归因报告")))}</h1>
<p class="meta">统计周期：{_escape(str(meta.get("window_start", "")))} ~
{_escape(str(meta.get("window_end", "")))} ｜ 对比基期：{_escape(str(meta.get("baseline", "")))}</p>
{"".join(sections)}
</body>
</html>"""
