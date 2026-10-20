"""在容器内验证 PDF 渲染的关键断言（与 tests/test_export.py 保持一致）。

CI 的 GitHub Runner 有 Pango 但缺中文字体，本地 Windows 有字体但缺 Pango，
两边都不能完整跑 PDF 用例。这个脚本在带 Pango + 中文字体的容器里执行，
把「页数 >= 1、文本层 > 100 字符」这两条断言真正验一遍。

用法：
    docker run --rm -v "$(pwd)/scripts:/app/scripts:ro" cause-trace-api:test \
        python /app/scripts/verify_pdf_assertions.py
"""

from __future__ import annotations

import io
import sys

sys.path.insert(0, "/app/src")

from cause_trace.export import render_pdf  # noqa: E402
from cause_trace.report import empty_section_payload  # noqa: E402


def main() -> int:
    payload = empty_section_payload(
        {
            "title": "8 月 GMV 下滑归因报告",
            "domain_id": 1,
            "metric_id": 1,
            "window_start": "2026-08-12",
            "window_end": "2026-08-18",
            "baseline": "dod",
        },
        {
            "background": {"summary": "GMV 日环比 -12.3%，抖音渠道转化率由 2.40% 跌至 1.51%。"},
            "factor_contribution": {
                "contributions": [
                    {
                        "factor": "抖音·转化率",
                        "contribution": -10865445.83,
                        "contribution_rate": -0.47,
                        "direction": "down",
                    }
                ]
            },
        },
    )

    artifact = render_pdf(payload)
    assert artifact.content.startswith(b"%PDF-"), "不是合法 PDF"

    try:
        from pypdf import PdfReader
    except ImportError:
        print("SKIP: 容器内无 pypdf，只校验了 PDF 头与体积")
        print(f"PDF_BYTES={len(artifact.content)}")
        return 0

    reader = PdfReader(io.BytesIO(artifact.content))
    text = "".join((page.extract_text() or "") for page in reader.pages)
    print(f"PAGES={len(reader.pages)}")
    print(f"TEXT_CHARS={len(text)}")
    print(f"PDF_BYTES={len(artifact.content)}")

    assert len(reader.pages) >= 1, "PDF 无页面"
    assert len(text) > 100, f"文本层过短（{len(text)}），字体可能未正确嵌入"
    print("PASS: 页数与文本层断言通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
