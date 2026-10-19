#!/usr/bin/env bash
# 本地依赖安装与测试入口，等价于 README 中的命令。
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --dev
uv run ruff check src tests
uv run pytest
