# 存量四工程接入指南

> 面向对象：即将把 `auth` / `data-agent` / `dbmock` / `insight-agent` 旧代码拷入本仓库的开发者
>
> 编写日期：2026-10-20　｜　对应基线：Spec v0.3.1、PRD v1.2
>
> **本文档描述的是当前代码的真实状态，不是设计意图。** 凡是「尚未实现」的地方都明确标注，
> 避免按错误预期改配置。

---

## 0. 一页速览

| 对接点 | 当前实现 | 接入旧工程要做什么 | 工作量 |
|--------|---------|-------------------|--------|
| **鉴权** | 读 `X-User-Id` / `X-Scopes` 请求头，**无 introspection** | 新增 introspection 客户端，替换 `require_scope` 的实现 | 中 |
| **取数** | SQL 直连 MySQL，**无 HTTP 客户端** | 新增 `data-agent` HTTP 适配层 | 中 |
| **数仓** | 只读连接串 `CAUSE_WAREHOUSE_READONLY_URL` | 改连接串即可，无需改代码 | 小 |
| **会话存储** | 本仓库 `cause` 库自有表 | 需与旧 `chat` 库三表做映射 | 中 |
| **LLM** | 无调用实现（仅规则模板降级） | 接入旧 `insight-agent` 的 deepagents | 大 |
| **前端** | 独立 `web/` | 可保留，或迁入旧 `insight-agent/web` | 中 |

**关键结论：当前代码与旧工程之间是「协议兼容、实现独立」的关系。** 没有一行代码真的在调用旧服务，
需要新增适配层。

---

## 1. 接入清单：归因主服务的所有对接口子

### 1.1 环境变量（唯一配置入口）

全部配置集中在 [`src/cause_trace/config.py`](../src/cause_trace/config.py)，使用 `CAUSE_` 前缀。
**这是接入时唯一需要改的地方**，其余代码都通过 `get_settings()` 读取。

| 环境变量 | 当前值 | 用途 | 接入时是否需改 |
|---------|--------|------|--------------|
| `CAUSE_DATABASE_URL` | `mysql+pymysql://cause:causepass@127.0.0.1:3306/cause` | 归因业务库 | 若并入 chat 库则改（Spec Q-D） |
| `CAUSE_WAREHOUSE_READONLY_URL` | 空 | 沙箱 SQL 的只读数仓连接 | **必改**，指向真实 warehouse |
| `CAUSE_SANDBOX_INTERNAL_TOKEN` | `dev-internal-token` | 沙箱内部鉴权 | **必改**，生产用强随机值 |
| `CAUSE_SANDBOX_IMAGE` | `cause-trace-sandbox:latest` | 沙箱镜像 | 通常不改 |
| `CAUSE_SANDBOX_DEFAULT_TIMEOUT_S` | `30` | 沙箱超时 | 按配额调 |
| `CAUSE_SANDBOX_DEFAULT_MAX_ROWS` | `100000` | 结果集上限 | 按配额调 |
| `CAUSE_SANDBOX_MAX_OUTPUT_BYTES` | `1048576` | stdout 截断 | 通常不改 |
| `CAUSE_SQL_CONSERVATION_TOLERANCE` | `1e-9` | 守恒容差 | **不要改**，硬验收项 |

> 注：`.env.example` 里列了前 4 项，其余用代码默认值。

### 1.2 需要新增的配置项（当前不存在）

接入旧工程时，需要在 `Settings` 里补上这些字段——**现在代码里没有，别去找**：

```python
# 建议新增，命名遵循现有 CAUSE_ 前缀约定
auth_introspect_url: str | None = None      # 例如 http://auth:7100/oauth/introspect
auth_client_id: str | None = None
auth_client_secret: str | None = None       # 走环境变量，禁明文
data_agent_base_url: str | None = None      # 例如 http://data-agent:8000
data_agent_timeout_s: int = 30
chat_database_url: str | None = None        # 旧 chat 库三表
```

### 1.3 数据访问入口（按文件）

| 文件 | 作用 | 接入影响 |
|------|------|---------|
| [`db/base.py`](../src/cause_trace/db/base.py) | Engine 与 Session 工厂，读 `CAUSE_DATABASE_URL` | 若并入 chat 库，改这里 |
| [`sandbox/runner.py`](../src/cause_trace/sandbox/runner.py) `SqlRunner` | 沙箱 SQL 执行，读 `CAUSE_WAREHOUSE_READONLY_URL` | 只改连接串 |
| [`sandbox/runner.py`](../src/cause_trace/sandbox/runner.py) `DockerPythonRunner` | Docker 内跑 Python | 不改 |
| [`dictionary/service.py`](../src/cause_trace/dictionary/service.py) | 指标字典仓储 | 可从旧 `meta` 库迁数据 |
| [`session/service.py`](../src/cause_trace/session/service.py) | 会话与报告仓储 | 需与旧 chat 三表映射 |

### 1.4 对外 API 全清单（32 个端点）

**归因主服务 `:7300`**（[`main.py`](../src/cause_trace/main.py)）：

| 类别 | 端点 | 当前是否鉴权 |
|------|------|-------------|
| 健康与指标 | `GET /healthz`、`GET /metrics` | 否 |
| 会话 | `POST /api/v1/sessions` | **否** ⚠️ |
| 会话 | `GET /api/v1/sessions/{id}` | **否** ⚠️ |
| 会话 | `POST /api/v1/sessions/{id}/followup` | **否** ⚠️ |
| 会话 | `POST /api/v1/sessions/{id}/simulate` | **否** ⚠️ |
| 会话 | `POST /api/v1/sessions/{id}/report` | **否** ⚠️ |
| 指标 | `POST /api/v1/metrics/decomposition` | 否（纯计算） |
| 指标 | `POST /api/v1/metrics/decomposition/shapley` | 否（纯计算） |
| 指标 | `GET/POST /api/v1/metrics` | **否** ⚠️ |
| 指标 | `POST /api/v1/metrics/{id}/decomp-rule` | **否** ⚠️ |
| 指标 | `POST /api/v1/metric-tree` | **否** ⚠️ |
| 字典 | `GET /api/v1/domains`、`/api/v1/data-sources` | **否** ⚠️ |
| 假设 | `POST /api/v1/hypotheses/evaluate` | 否（纯计算） |
| 事件 | `POST /api/v1/events/match` | 否（纯计算） |
| 报告 | `GET /api/v1/report/schema`、`POST /validate` | 否（纯计算） |
| 报告 | `POST /api/v1/reports/export` | 否（会写审计） |
| 报告协同 | `GET/POST /api/v1/reports/{id}/annotations` | GET 否 / POST 是 |
| 报告协同 | `GET /api/v1/reports/{id}/versions[/diff]` | 否 |
| 治理 | `GET /api/v1/admin/audit[/export]` | 是（`admin:cause`） |
| 治理 | `PUT /api/v1/admin/sandbox-quota` | 是 |
| 治理 | `GET /api/v1/admin/sandbox-quota/resolve` | 否 |
| 治理 | `POST/GET /api/v1/anomaly-thresholds` | POST 是 / GET 是 |
| 治理 | `POST /api/v1/anomaly/check` | 否（纯计算） |

**沙箱 `:7400`**（[`sandbox/service.py`](../src/cause_trace/sandbox/service.py)）：
`GET /healthz`、`POST /v1/execute`（`X-Internal-Token` 校验）。

> ⚠️ **接入 auth 时的重要缺口**：带 ⚠️ 的接口目前完全不校验身份。接入后必须逐个补
> `Depends(require_scope(...))`，否则旧 auth 再严也保护不到这些接口。

---

## 2. 鉴权：当前是 Mock Token，不是 OAuth2

### 2.1 现状（如实说明）

[`security.py`](../src/cause_trace/security.py) **只做了请求头解析**，没有调用 auth 服务：

```python
def require_scope(scope: str):
    def dependency(
        x_user_id: str | None = Header(default=None),
        x_scopes: str | None = Header(default=None),
    ) -> Principal:
        if not x_user_id:
            raise HTTPException(status_code=401, detail="未认证：缺少 X-User-Id")
        scopes = frozenset(item.strip() for item in (x_scopes or "").split(",") if item.strip())
        principal = Principal(user_id=int(x_user_id), scopes=scopes)
        principal.require(scope)
        return principal
    return dependency
```

**这意味着任何人都能伪造 `X-User-Id: 1` + `X-Scopes: admin:cause` 拿到管理员权限。**
当前只适合本地开发，生产前必须替换。

已实现的部分：
- `Principal` 数据类与 `require()` 权限判断（`admin:cause` 通配）
- 三个 scope 常量：`admin:cause`、`read:insight-agent`、`write:insight-agent`
- 6 个治理接口已挂 `Depends(require_scope(...))`

未实现的部分：
- ❌ 没有 token 解析
- ❌ 没有 introspection 调用
- ❌ 没有 token 缓存
- ❌ 没有 401 的 `WWW-Authenticate` 头

### 2.2 接入 auth 的改造步骤

**第 1 步：加配置**（`config.py`）

```python
auth_introspect_url: str | None = None
auth_client_id: str | None = None
auth_client_secret: str | None = None
auth_introspect_cache_ttl_s: int = 60
```

**第 2 步：新增 introspection 客户端**（建议新建 `src/cause_trace/auth/introspection.py`）

```python
"""OAuth2 令牌内省（RFC 7662）。

旧 auth 服务的令牌是 opaque token，必须走内省端点；JWT 自校验在这里不适用。
结果按 token 哈希缓存 60 秒，避免每个请求都打 auth。
"""

async def introspect(token: str) -> Principal | None:
    # POST {auth_introspect_url}
    # body: token=<token>&client_id=...&client_secret=...
    # 期望响应: {"active": true, "sub": "7", "scope": "read:insight-agent ..."}
    ...
```

**第 3 步：替换 `require_scope` 的 dependency**

```python
def require_scope(scope: str):
    async def dependency(authorization: str | None = Header(default=None)) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "未认证", headers={"WWW-Authenticate": "Bearer"})
        principal = await introspect(authorization[7:])
        if principal is None:
            raise HTTPException(401, "令牌无效或已过期")
        principal.require(scope)
        return principal
    return dependency
```

**第 4 步：给 1.4 表中标 ⚠️ 的接口补上依赖**

**第 5 步：兼容开关**（建议）

```python
auth_mode: str = "header"   # header（开发）| introspection（生产）
```

本地开发保留 `header` 模式，避免每次都要起 auth 服务；生产强制 `introspection`，
并在启动时校验 `auth_introspect_url` 非空。

### 2.3 验证方式

```bash
# 无令牌 → 401
curl -i -X POST http://127.0.0.1:7300/api/v1/sessions -d '{}'
# 伪造头 → 生产模式下应 401（当前 header 模式下仍会通过）
curl -i -H "X-User-Id: 1" -H "X-Scopes: admin:cause" http://127.0.0.1:7300/api/v1/admin/audit
```

---

## 3. 取数：当前直连 MySQL，没有 HTTP 客户端

### 3.1 现状（如实说明）

**代码里没有任何 HTTP 客户端**（`httpx` / `requests` / `aiohttp` 均未使用）。
所有取数走 SQLAlchemy 直连：

| 路径 | 代码位置 | 连接串 |
|------|---------|--------|
| 归因业务表读写 | `db/base.py` | `CAUSE_DATABASE_URL` |
| 沙箱 SQL 取数 | `sandbox/runner.py::SqlRunner` | `CAUSE_WAREHOUSE_READONLY_URL` |

沙箱 SQL 的执行链路是：

```
LLM/模板生成 SQL
  → policy.validate_sql()（sqlglot AST 白名单）
  → SqlRunner.run()（只读账号 + 会话级超时 + 行数截断）
  → MySQL
```

**完全没有经过 data-agent 的 Text2SQL 链路。**

### 3.2 为什么不能直接改 base_url

旧 `data-agent` 是 Text2SQL Agent（自然语言 → SQL → 执行），而本仓库的调用方
**已经有 SQL 了**（沙箱生成或模板拼装）。两者的接口语义不同：

| 需求 | data-agent 提供 | 本仓库需要 |
|------|----------------|-----------|
| 自然语言 → SQL | ✅ 12 节点 LangGraph | 需要（意图解析后的取数） |
| 已生成 SQL → 执行结果 | 需确认其是否暴露 | 需要（沙箱验证） |
| 元数据召回 | ✅ Qdrant + ES | 需要（指标字典） |

### 3.3 建议的接入方式

**方案 A（推荐）：data-agent 只承担 Text2SQL，SQL 执行仍走沙箱**

```
意图解析 → 调 data-agent /v1/text2sql 拿到 SQL
        → 沙箱 SqlRunner 执行（复用现有白名单与配额）
```

新增 `src/cause_trace/data_agent/client.py`：

```python
class DataAgentClient:
    def __init__(self, base_url: str, timeout_s: int = 30): ...

    async def text_to_sql(self, question: str, metric_code: str) -> str:
        """调用 data-agent 生成 SQL；返回的 SQL 仍要过沙箱白名单。"""

    async def recall_metadata(self, query: str) -> list[dict]:
        """指标/表/列召回，供指标字典与意图解析使用。"""
```

配置项：`CAUSE_DATA_AGENT_BASE_URL=http://data-agent:8000`

**方案 B：全部走 data-agent 执行**

需要确认旧 data-agent 是否暴露「给定 SQL 直接执行」的端点。若没有，不建议为其新增端点——
沙箱的只读账号、AST 白名单、配额、审计是 Spec 的安全硬约束，绕过它等于放弃这些保障。

### 3.4 需要确认的接口契约

拷入旧代码后，请先确认这几点再动手：

1. data-agent 的 Text2SQL 端点路径、请求/响应结构
2. 是否支持「只生成 SQL 不执行」模式
3. 返回的 SQL 方言是否与 MySQL 一致
4. 元数据召回的端点与返回字段
5. 是否有内部鉴权（本仓库调用时要带什么）

---

## 4. dbmock：从最小 demo 切到完整数仓

### 4.1 现状

本仓库只有 [`scripts/warehouse_demo.sql`](../scripts/warehouse_demo.sql)：一张
`dwd_fact_channel_daily`（14 行），用于跑通 E2E。

旧 `dbmock` 生成的是 24 张 DWD 表、100 万订单、240 万行为事件、SCD2 拉链、大促加权。

### 4.2 切换步骤

**不需要改任何代码**，只需换连接串：

```bash
# 1. 用旧 dbmock 生成数据（具体命令以其 README 为准）
#    它会写入 warehouse 库

# 2. 确认只读账号能访问新表
docker exec cause-mysql mysql -ucause_ro -preadonly_pass \
  -e "SHOW TABLES FROM warehouse;" | head -30

# 3. 更新沙箱的表白名单
#    DATA_SOURCE.table_scope 或 ExecutionRequest.allowed_tables
```

**关键：表白名单必须同步更新。** 沙箱默认拒绝未登记的表：

```python
# sandbox/runner.py 的 ExecutionRequest.allowed_tables
allowed_tables=["dwd_fact_channel_daily"]   # ← 现在是硬编码的 demo 表
```

接入完整数仓后，建议改为从 `DATA_SOURCE.table_scope` 动态读取，而不是继续硬编码。

### 4.3 连接串切换

```bash
# 最小 demo（当前）
CAUSE_WAREHOUSE_READONLY_URL="mysql+pymysql://cause_ro:readonly_pass@127.0.0.1:3306/warehouse?charset=utf8mb4"

# 完整数仓（接入后）
CAUSE_WAREHOUSE_READONLY_URL="mysql+pymysql://<只读账号>:<口令>@<host>:3306/warehouse?charset=utf8mb4"
```

只读账号创建脚本见 [`scripts/warehouse_readonly.sql`](../scripts/warehouse_readonly.sql)。

### 4.4 异动注入

本仓库的注入实现在 [`dbmock/injection.py`](../src/cause_trace/dbmock/injection.py)，作用于
**内存中的行数据**并写 `injection_config` / `injection_truth` 表。

旧 dbmock 若要在**物理表**上注入异动，需要把 `inject_values()` 的改写逻辑接到其生成流程里，
或者生成后用 UPDATE 批量改写（注意：这需要写权限，与只读账号冲突，应使用独立的生成账号）。

---

## 5. 接入顺序建议

按依赖关系，建议分四步走，每步都能独立验证：

```
第 1 步：dbmock 数仓
  ├─ 生成完整 warehouse
  ├─ 只读账号授权
  ├─ 更新表白名单
  └─ 验证：沙箱 SQL 能查到新表
       ↓
第 2 步：auth 鉴权
  ├─ 新增 introspection 客户端
  ├─ 替换 require_scope
  ├─ 给 1.4 表中标 ⚠️ 的接口补依赖
  └─ 验证：无令牌 401、伪造头 401、真实令牌 200
       ↓
第 3 步：data-agent 取数
  ├─ 新增 DataAgentClient
  ├─ 意图解析后接 Text2SQL
  ├─ 生成的 SQL 仍走沙箱
  └─ 验证：自然语言 → SQL → 结果
       ↓
第 4 步：insight-agent 会话与 LLM
  ├─ chat 三表映射
  ├─ deepagents 接入
  ├─ WS 流式对接
  └─ 验证：多轮追问上下文保持
```

**为什么不先接 auth**：auth 只影响鉴权，不阻塞数据链路。先把数据跑通，能更早发现
schema 与方言问题。

---

## 6. 接入前的自检清单

拷入旧代码后，先跑一遍这些检查：

```bash
# 1. 现有测试仍全绿
uv run pytest

# 2. 服务能起（需要 MySQL）
docker compose -f docker-compose.dev.yml up -d mysql redis
make migrate-reset

# 3. 全链路 E2E 仍通过
bash scripts/e2e_pdf_container.sh

# 4. 检查是否有端口冲突
#    auth 7100 / data-agent 8000 / insight-agent 7300 / sandbox 7400
netstat -ano | findstr "7100 7300 7400 8000"
```

### 已知的冲突点

| 冲突 | 说明 | 处理 |
|------|------|------|
| 端口 7300 | 旧 insight-agent 与本仓库主服务都用 7300 | 二选一：合并代码，或改其中一个端口 |
| `chat` 库三表 | 旧 insight-agent 已有 conversation/message/context_compaction | 决定复用还是新建（Spec Q-D） |
| 前端 | 旧 `insight-agent/web` vs 本仓库 `web/` | 决定保留哪个（建议保留本仓库的，已对齐原型） |
| LLM Key | 旧工程配置里有明文 Key | 按 ADR-06 迁到环境变量 |
| `sandbox-runner` | 旧工程没有此服务 | 新增部署单元，无需合并 |

---

## 7. 尚未实现、别误以为有的能力

避免接入时踩空，这里明确列出：

| 能力 | 状态 | 说明 |
|------|------|------|
| OAuth2 introspection | ❌ 未实现 | 只有 Header 解析 |
| data-agent HTTP 客户端 | ❌ 未实现 | 无任何 HTTP 调用 |
| LLM 调用 | ❌ 未实现 | `intent.py` 只有规则模板降级 |
| WebSocket 服务端 | ❌ 未实现 | 前端有客户端代码，后端无 `/ws` 端点 |
| 沙箱并行验证 | ❌ 未实现 | `DockerPythonRunner` 是串行调用 |
| chat 三表集成 | ❌ 未实现 | 本仓库用自己的 `attribution_session` |
| 定时任务（简报订阅） | ❌ 未实现 | 表结构有，无调度器 |
| Redis 集成 | ❌ 未实现 | 配置与 key 规范有，代码未接入 |

---

## 附：相关文件索引

| 主题 | 文件 |
|------|------|
| 配置 | [`src/cause_trace/config.py`](../src/cause_trace/config.py)、[`.env.example`](../.env.example) |
| 鉴权 | [`src/cause_trace/security.py`](../src/cause_trace/security.py) |
| 数据层 | [`src/cause_trace/db/base.py`](../src/cause_trace/db/base.py) |
| 沙箱 | [`src/cause_trace/sandbox/runner.py`](../src/cause_trace/sandbox/runner.py)、[`policy.py`](../src/cause_trace/sandbox/policy.py) |
| 注入 | [`src/cause_trace/dbmock/injection.py`](../src/cause_trace/dbmock/injection.py) |
| 会话 | [`src/cause_trace/session/service.py`](../src/cause_trace/session/service.py) |
| 部署 | [`docker-compose.dev.yml`](../docker-compose.dev.yml)、[`Dockerfile`](../Dockerfile) |
| 演示数据 | [`scripts/warehouse_demo.sql`](../scripts/warehouse_demo.sql)、[`seed_demo.sql`](../scripts/seed_demo.sql) |
