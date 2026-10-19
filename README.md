# cause_trace

经营归因分析系统。需求见 `docs/prd/`，技术设计见 `docs/spec/`，协作约束见 `CLAUDE.md`。

## 本地启动

```bash
cp .env.example .env          # 填数据库与只读数仓连接串
uv sync --dev                 # 安装依赖
docker compose -f docker-compose.dev.yml up -d   # MySQL + Redis
make migrate                  # 建 cause 库表（Alembic）
make test                     # 单元测试（含守恒性硬校验）
```

## 服务

| 服务 | 端口 | 启动命令 |
|------|------|---------|
| insight-agent 归因主服务 | 7300 | `uv run uvicorn cause_trace.main:app --port 7300` |
| sandbox-runner 沙箱执行器 | 7400 | `uv run uvicorn cause_trace.sandbox.service:app --port 7400` |

沙箱 Python 执行需要 Docker 与镜像：`make sandbox-image`。未安装 Docker 时 `/v1/execute`
返回 `SBX_UNAVAILABLE`，不影响 SQL 白名单与分解接口。

## 组1 已完成范围（T-01~T-04）

- **T-01 数据层**：`cause` 库 20 张表 ORM 模型 + Alembic 迁移 `0001_init_cause_schema`，
  七章节报告 payload JSON Schema。
- **T-02 数仓只读整改**：`scripts/warehouse_readonly.sql`（只读账号 + 连接数上限），
  data-agent 侧需把连接账号替换为 `cause_ro`。
- **T-03 sandbox-runner**：SQL AST 白名单（写操作/DDL/系统库/危险函数拦截、强制 LIMIT）、
  Docker 隔离执行 Python、CPU/内存/超时/行数/并发配额、内部令牌鉴权。
- **T-04 公式引擎**：差额分析 / LMDI / Shapley / 杜邦，输出前强制守恒校验，
  偏差超过 `1e-9` 抛 `BIZ_CONSERVATION_FAILED`。

## 已知前提

存量四工程（auth / data-agent / dbmock / insight-agent）不在本仓库内。T-02 的
data-agent 改造、T-19 的 dbmock 注入需要拿到对应代码库后落地；当前仓库先提供
可独立验证的 schema、算法与沙箱边界。
