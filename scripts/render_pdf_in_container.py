"""在容器内渲染一份带 CSS 与图表的 PDF，供 E2E 校验。

由 scripts/e2e_pdf_container.sh 调用；也可单独执行：
    docker run --rm -v "$(pwd)/exports:/app/exports" cause-trace-api:test \
        python /app/scripts/render_pdf_in_container.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/app/src")

from cause_trace.export import render  # noqa: E402
from cause_trace.report import empty_section_payload  # noqa: E402


def build_payload() -> dict:
    return empty_section_payload(
        {
            "title": "容器化 PDF 渲染验收报告",
            "domain_id": 1,
            "metric_id": 1,
            "window_start": "2026-08-12",
            "window_end": "2026-08-18",
            "baseline": "dod",
        },
        {
            "background": {
                "summary": "GMV 日环比 -12.3%，差异额 -1,432 万；抖音渠道转化率由 2.40% 跌至 1.51%。"
            },
            "factor_contribution": {
                "contributions": [
                    {
                        "factor": "抖音·转化率",
                        "contribution": -10865445.83,
                        "contribution_rate": -0.47,
                        "direction": "down",
                    },
                    {
                        "factor": "抖音·访客数",
                        "contribution": -6311242.50,
                        "contribution_rate": -0.27,
                        "direction": "down",
                    },
                    {
                        "factor": "搜索·访客数",
                        "contribution": -6001120.17,
                        "contribution_rate": -0.26,
                        "direction": "down",
                    },
                ]
            },
            "conclusion": {"summary": "主因：抖音渠道转化率下滑；外因：竞品补贴分流。"},
            "action_plan": {
                "actions": [
                    {
                        "factor": "抖音渠道转化优化",
                        "role": "渠道运营负责人",
                        "period_days": 14,
                        "expected_recovery": 10865445.83,
                    }
                ]
            },
        },
    )


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/exports/container-report.pdf")
    artifact = render("pdf", build_payload())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(artifact.content)
    print(f"PDF_BYTES={len(artifact.content)}")
    print(f"PDF_PATH={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
