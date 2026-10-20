# insight-agent 归因主服务镜像。
#
# PDF 导出依赖 WeasyPrint，它需要 Pango/Cairo 等原生库。Windows 开发机装这套
# 依赖很痛苦，所以 PDF 渲染统一在这个容器里做：本地开发无需安装 GTK，
# 只要 docker compose 起服务即可。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# WeasyPrint 的系统级依赖：Pango 负责文本排版与换行，Cairo 负责光栅化。
# 保留官方源（python:3.12-slim 基于 Debian trixie，国内镜像的索引未必同步），
# 加重试避免网络抖动导致构建失败。
RUN apt-get update \
    && for attempt in 1 2 3; do \
         apt-get install -y --no-install-recommends \
           libpango-1.0-0 \
           libpangoft2-1.0-0 \
           libcairo2 \
           libgdk-pixbuf-2.0-0 \
           libffi8 \
           shared-mime-info \
         && break || { echo "apt 安装失败，第 $attempt 次重试"; sleep 5; }; \
       done \
    && rm -rf /var/lib/apt/lists/*

# 中文字体单独装：字体包体积大、镜像源偶尔抽风。失败时降级为系统默认字体，
# 不能因此让整个镜像构建失败（PDF 仍能生成，只是字形不理想）。
RUN apt-get update \
    && (apt-get install -y --no-install-recommends fonts-noto-cjk \
        || echo "WARN: fonts-noto-cjk 安装失败，PDF 中文可能使用回退字体") \
    && rm -rf /var/lib/apt/lists/*

# 国内构建走清华镜像；构建时可用 --build-arg 覆盖
ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_DEFAULT_INDEX=${UV_INDEX_URL}

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# 导出产物目录：compose 会把它挂到宿主机 exports/，镜像里先建好避免挂载点被覆盖
RUN mkdir -p /app/exports

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 7300

# 默认起归因主服务；PDF 渲染由同一进程内的 WeasyPrint 完成
CMD ["uvicorn", "cause_trace.main:app", "--host", "0.0.0.0", "--port", "7300"]
