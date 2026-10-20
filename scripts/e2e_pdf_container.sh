#!/usr/bin/env bash
# 容器化 PDF 渲染 E2E。
#
# 本地 Windows 不装 GTK：在 cause-trace-api 镜像里跑 WeasyPrint，把报告渲染成
# 带 CSS 样式、分页与内联 SVG 图表的 PDF，并校验其体积与有效性。
#
# 用法：
#   bash scripts/e2e_pdf_container.sh
#
# 前置：docker build -f Dockerfile -t cause-trace-api:test .
set -euo pipefail

cd "$(dirname "$0")/.."
IMAGE="${IMAGE:-cause-trace-api:test}"
OUT_DIR="${OUT_DIR:-exports}"

mkdir -p "$OUT_DIR"

echo "==> 在容器内渲染 PDF（$IMAGE）"
# Git Bash 会把 /app/... 当成 Windows 路径改写，MSYS_NO_PATHCONV 关掉这层转换。
# 挂载脚本文件而不是 heredoc：Windows 的 docker CLI 对 stdin 透传不稳定。
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd)/exports:/app/exports" \
  -v "$(pwd)/scripts/render_pdf_in_container.py:/app/render_pdf_in_container.py:ro" \
  "$IMAGE" \
  python /app/render_pdf_in_container.py /app/exports/container-report.pdf

echo "==> 校验产物"
PDF="$OUT_DIR/container-report.pdf"
[ -f "$PDF" ] || { echo "FAIL: PDF 未生成"; exit 1; }

SIZE=$(wc -c < "$PDF" | tr -d ' ')
HEADER=$(head -c 5 "$PDF")

echo "    size   = $SIZE bytes"
echo "    header = $HEADER"

[ "$HEADER" = "%PDF-" ] || { echo "FAIL: 不是合法 PDF"; exit 1; }

# 带 CSS 与 SVG 的真实渲染体积应显著大于纯文本 PDF（后者约 1.5KB）
[ "$SIZE" -gt 10000 ] || { echo "FAIL: PDF 体积 $SIZE 过小，疑似未走 WeasyPrint 渲染"; exit 1; }

tail -c 32 "$PDF" | grep -q "%%EOF" || { echo "FAIL: 缺少 EOF 标记"; exit 1; }

echo "==> 解析 PDF 结构（页数与文本）"
# 生产镜像不带 dev 依赖，pypdf 用宿主机临时环境装，只读地检查产物
uv run --with pypdf python - "$PDF" <<'PY'
import sys
from pypdf import PdfReader

reader = PdfReader(sys.argv[1])
pages = len(reader.pages)
text = "".join((page.extract_text() or "") for page in reader.pages)
print(f"    pages      = {pages}")
print(f"    text chars = {len(text)}")
if pages < 1 or len(text) < 100:
    print("FAIL: PDF 内容为空或页数异常")
    raise SystemExit(1)
PY

echo "PASS: 容器内 WeasyPrint 渲染成功，$SIZE bytes"
