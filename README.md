# cause_trace

经营归因分析系统。需求见 `docs/prd/`，技术设计见 `docs/spec/`，协作约束见 `CLAUDE.md`。

## 本地启动

```bash
cp .env.example .env          # 填数据库与只读数仓连接串
uv sync --dev                 # 安装依赖
make up                       # MySQL 8.4 + Redis 8（bind mount 到本地目录）
make migrate                  # 建 cause 库表（Alembic）
make test                     # 单元测试（含守恒性硬校验）
```

容器数据落在 `D:\Documents\Docker\volume\app\cause_trace\` 下的 `mysql/` 与 `redis/`，
删除目录即可重置，不必 `docker volume prune`。

`make migrate` 后建议灌一份种子数据（指标域、数据源、指标），否则接口会因外键
约束返回 500：

```bash
docker exec -i cause-mysql mysql -ucause -pcausepass cause < scripts/seed_demo.sql
```

**真实数据库集成测试**（需另建一个空库，跑完自动 drop，不碰 `cause` 库）：

```bash
docker exec cause-mysql mysql -uroot -prootpass -e \
  "CREATE DATABASE cause_it CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; \
   GRANT ALL PRIVILEGES ON cause_it.* TO 'cause'@'%'; FLUSH PRIVILEGES;"

CAUSE_TEST_MYSQL=1 \
CAUSE_DATABASE_URL="mysql+pymysql://cause:causepass@127.0.0.1:3306/cause_it?charset=utf8mb4" \
uv run pytest tests/test_integration_mysql.py
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

## 组2 已完成范围（T-05~T-11）

- **T-05 指标字典与指标树**：指标/拆解规则/树节点仓储层；树操作挂 ORM flush 事件，
  任何写入路径都会拦成环与重复挂载。
- **T-06 编排层**：意图解析（指标/周期/基期，含 LLM 别名归一）、八阶段规划、
  降级假设模板。
- **T-07 假设状态机**：pending → verified / excluded / failed；置信度低于阈值
  自动判定伪相关，不进入结论。
- **T-08 沙箱验证判定**：纯标准库实现 t 分布显著性检验；置信度 = 0.5·相关性
  + 0.2·显著性 + 0.3·贡献率。
- **T-09 因果知识引擎**：异动窗口前后 3 日事件匹配；时间重合 + 至少一个维度
  命中才进因果链，重合度按 0.4 基础分 + 维度加权。
- **T-10 敏感性与建议引擎**：对数-对数 OLS 拟合弹性，R² < 0.6 降级到经验弹性；
  策略四要素（因子/角色/周期/金额）缺一不可。
- **T-11 会话与报告管理**：会话创建与阶段推进、假设/证据/仿真/因果链落库、
  报告组装（先过 Schema 再落库）、版本快照、批注。

## 组3 已完成范围（T-12~T-18）

前端位于 `web/`（React 19 + Vite 7 + TypeScript + Tailwind + zustand）。

- **T-12 前端基架**：三栏工作台（280px / 1fr / 480px，折叠状态存 localStorage），
  ECharts 按需注册 + 独立分包，TanStack Table。
- **T-13 指标异动大盘**：KPI 卡片、异动列表（按跌幅降序）、一键发起归因。
- **T-14 数据可视化**：因子贡献瀑布图（正负柱 + 合计对齐）、杜邦拆解树、敏感度曲线。
- **T-15 动态透视表**：层级折叠、列头排序、差额涨跌染色。
- **T-16 What-If 仿真器**：滑块即时反馈 + 200ms 节流重算 + 旧请求取消。
- **T-17 报告组装与导出页**：七章节预览、批注、版本切换、导出状态。
- **T-18 配置页**：业务事件日历（含窗口匹配校验）、指标字典（树 + 编辑面板）。

前端状态按 Spec 12.1 分五个 store；WS 协议与重连退避在 `src/ws/`。

```bash
cd web
npm install
npm run dev     # http://localhost:5173，/api 已代理到 7300
npm run test    # 16 passed
npm run build
```

## 组4 已完成范围（T-19~T-25）

- **T-19 异动注入**：`dbmock/injection.py` 按「时间窗 × 维度 × 指标 × 幅度」注入，
  seed 固定可复现；INJECTION_CONFIG / INJECTION_TRUTH 落库作为 ground truth。
- **T-20/T-21 场景闭环**：电商 GMV 下滑（抖音转化率 -35%）与快消利润率异动
  （华东成本 -18%）两个场景，覆盖 生成 → 注入 → 检测 → 分解 → 因果 → 仿真 → 策略。
- **T-22 三格式导出**：Markdown（Jinja 风格文本）、Excel（openpyxl，每章节一个 sheet）、
  PDF（WeasyPrint，未安装时明确报 503）。
- **T-23 审计治理**：只写不改的审计表，按用户/动作/request_id/时间检索，CSV 导出。
- **T-24 配额与阈值**：global < role < user 三级配额；异动阈值按 dod/yoy/target 配置。
- **T-25 密钥与认证**：scope 依赖注入、密钥只从环境变量读取、开发默认值自检
  （完整的安全加固在组5 T-29）。

```bash
uv run pytest tests/test_injection.py tests/test_export.py tests/test_scenario_closure.py
```

## 组5 已完成范围（T-26~T-29）

- **T-26 前端状态落地**：已在组3 完成（五域 store + WS 增量渲染协议）。
- **T-27 Prompt 工程**：入口清洗（截断 + 角色标记剥离）、分隔符隔离、
  Schema 校验与规则模板降级（组2 的 `orchestration/intent.py`）。
- **T-28 可观测性**：loguru JSON 日志（request_id/session_id/hypothesis_id）、
  `/metrics` 暴露 12 组 Prometheus 指标、8 条告警规则
  （`deploy/prometheus-rules.yml`，守恒失败为 Critical）。
- **T-29 安全加固**：scope 鉴权、密钥只读环境变量、Prompt 注入清洗、
  手机/邮箱/姓名/地址脱敏、业务线越权校验、LIKE 通配符转义。

```bash
uv run pytest tests/test_observability.py tests/test_security.py
curl http://127.0.0.1:7300/metrics
```

## 已知前提

存量四工程（auth / data-agent / dbmock / insight-agent）不在本仓库内。T-02 的
data-agent 改造、T-19 的 dbmock 注入需要拿到对应代码库后落地；当前仓库先提供
可独立验证的 schema、算法与沙箱边界。
