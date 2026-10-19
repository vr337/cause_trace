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

## 已知前提

存量四工程（auth / data-agent / dbmock / insight-agent）不在本仓库内。T-02 的
data-agent 改造、T-19 的 dbmock 注入需要拿到对应代码库后落地；当前仓库先提供
可独立验证的 schema、算法与沙箱边界。
