# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

**cause_trace 经营归因分析系统**：前端三栏交互式归因工作台 + 后端统计检验与代码沙箱执行器 + 示例数仓数据集 + 多格式报告导出。

**当前仓库状态：只有需求与设计文档，无任何源码、无 git 仓库，属立项阶段。** 不要自行创建源码目录、package.json、pyproject.toml 等文件，除非用户明确要求进入开发阶段。

## 文档基线（最重要）

一切开发以两份基线文档为准，历史版本一律只进归档、不改。

| 文档 | 路径 | 版本 | 状态 |
|------|------|------|------|
| PRD（需求规格） | `docs/prd/cause_trace_PRD_v1.2.md` | v1.2 | 确认基线 |
| 设计规格 | `docs/spec/cause_trace_技术设计规格说明书_v0.3.1.md` | v0.3.1 | 基线冻结 |

**文档目录结构**：

```
docs/
├── prd/
│   ├── cause_trace_PRD_v1.2.md          # 当前基线
│   └── archive/
│       ├── cause_trace_PRD_v1.0.md
│       └── cause_trace_PRD_v1.1.md
├── spec/
│   ├── cause_trace_技术设计规格说明书_v0.3.1.md   # 当前基线
│   └── archive/
│       ├── cause_trace_技术设计规格说明书_v0.1.md
│       ├── cause_trace_技术设计规格说明书_v0.2.md
│       └── cause_trace_技术设计规格说明书_v0.3.md
├── 需求参考.md
└── prototype/
    └── images/
```

**文档迭代规则**：

- 新版本 PRD / Spec 正文放 `docs/prd/` 与 `docs/spec/` 根目录，旧版本移入对应 `archive/` 子目录，文件名带版本号。
- 文档升级必须更新「变更记录」表；Spec 需与 PRD 编号（FR / AC / Q）保持可回溯。
- 不擅自修改冻结基线的内容。如需修改，先向用户确认，再升版本号（如 v0.3.1 → v0.3.2）。

**关键信息速查**：

- 功能需求池 FR-01~FR-24（PRD 第 4 章），P0 覆盖「发起→拆解→下钻→假设→验证→因果→仿真→报告」全链路。
- **守恒性为硬验收**：加法差额 / LMDI / Shapley 分解后各因子贡献量之和与总变动偏差必须为 0（浮点误差 ≤ 1e-9），失败抛 `BIZ_CONSERVATION_FAILED`，禁止出图与入报告。
- 服务拓扑：auth(7100) / insight-agent 归因主服务(7300) / sandbox-runner(7400 新增) / data-agent(8000) / web 前端；**存量四工程（auth / data-agent / dbmock / insight-agent）必须复用，不推倒重来**。
- 待确认问题：PRD 第 12 章 Q1~Q12、Spec 第 11 章 Q-A~Q-M，评审拍板前不得擅自改默认方案。

## 原型设计任务（pencil MCP）

- 原型 `.pen` 文件在 `docs/spec/cause_trace_prototype.pen`，**加密文件，只能用 pencil MCP 工具访问，禁止用 Read / Grep 读取**。
- 原型导出图片目标目录：`docs/prototype/images/`。
- 绘制原型以 **PRD 第 7 章「关键页面原型说明」**（7.1~7.5：指标异动大盘、归因工作台、业务事件日历、指标字典、报告归档导出）与 **Spec 第 12 章前端组件设计**为准。
- 三栏宽度参考 Spec 12.2 建议：`280px / 1fr / 480px`，折叠状态存 localStorage。

## 构建与测试

- 暂无构建、测试、运行命令（无源码、无 package.json / pyproject.toml）。
- 后续按 Spec 第 10 章任务分解 T-01~T-29 立项后补充：
  - 后端：Python 3.12 + uv + FastAPI + SQLAlchemy + Alembic
  - 前端：React 19 + Vite 7 + TypeScript + Tailwind + zustand + ECharts + TanStack Table
  - CI 阻塞规则：T-04 守恒性单测（偏差 > 1e-9 即失败）

## 阶段交付与 Git 管理

阶段粒度以 **Spec 第 10 章任务分解的分组（T-01~T-29 的分组里程碑）** 为准，而非单条任务。分组如下：

| 组 | 任务范围 | 模块 |
|----|---------|------|
| 组1 | T-01 ~ T-04 | 数据层 + 沙箱基础 |
| 组2 | T-05 ~ T-11 | 核心分析引擎 |
| 组3 | T-12 ~ T-18 | 前端工作台 |
| 组4 | T-19 ~ T-25 | 数据资产与集成 |
| 组5 | T-26 ~ T-29 | 可观测性与安全加固 |

每完成一个任务分组，按以下约束收尾：

- **自动调用 `git-ship` skill**：分组内任务全部完成后，调用 `git-ship` 完成「暂存 → commit → 本地整理 → 准备 push/PR」。`git-ship` 在真正执行 push 与创建 PR 前须暂停，转入下一条的确认流程。
- **Git 仓库管理交由 `github-ops` skill**：分支、PR、Issue、Actions、Release 等远程仓库操作统一通过 `github-ops` 进行，不绕过该插件直接操作。二者串联关系：`git-ship` 准备完成 → 用户确认 → `github-ops` 执行远程动作。
- **推送 / 建 PR 前必须向用户确认**：全局安全红线优先。`git-ship` 可自动完成本地 commit 与代码整理，但执行 **push 与创建 PR** 前须暂停并向用户确认，待用户明确同意后再继续；不得因本规则而覆盖安全红线。
- **约束自检**：本规则仅改变「何时调用 git-ship / 谁管理远程仓库」，**不豁免安全红线**中的「删除、改密钥、强推、公开发布须先询问」等要求。

## 通用行为约束

- 修改任何冻结基线的文档前，先向用户确认；确认后升版本号并补变更记录。
- 遇到 PRD / Spec 中标记为「待确认」的 Q 项时，不得擅自选择默认方案，须提请用户拍板。
- 引用文档编号时必须与当前基线一致：FR-01~FR-24、AC（含 AC-OVERALL）、PRD Q1~Q12、Spec Q-A~Q-M、ADR-01~ADR-11、T-01~T-29。
- 不主动创建源码、脚本、配置文件；仅在用户明确进入开发阶段后按 Spec T-01~T-29 立项。