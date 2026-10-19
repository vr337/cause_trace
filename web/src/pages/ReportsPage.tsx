import { useState } from "react";

import { useReportStore } from "../store/reportStore";

const SECTION_TITLES = [
  "异动背景与问题定义",
  "因子贡献率拆解",
  "细分维度下钻证据",
  "核心归因结论",
  "因果证据链与检验置信度",
  "What-If 情景模拟结论",
  "可落地策略行动清单",
];

const EXPORT_FORMATS = ["Markdown", "PDF", "Excel"] as const;

/** 报告归档与导出预览（PRD 7.5 / FR-16、FR-22）。 */
export function ReportsPage() {
  const { versions, annotations, addAnnotation, exportStatus, setExportStatus } = useReportStore();
  const [draft, setDraft] = useState("");
  const [activeVersion, setActiveVersion] = useState(versions.at(-1) ?? 1);

  const submitAnnotation = () => {
    if (!draft.trim()) return;
    addAnnotation({
      anchor: `section_2#${draft.length}`,
      content: draft.trim(),
      version: activeVersion,
      author: "经营分析师",
    });
    setDraft("");
  };

  return (
    <div className="h-full overflow-auto p-5">
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold">8 月 GMV 下滑归因报告</h1>
            <p className="mt-0.5 text-xs text-ink-400">状态：已发布 · 版本 v{activeVersion}</p>
          </div>
          <div className="flex gap-2">
            {versions.length > 1 && (
              <select
                className="rounded border border-ink-200 bg-white px-2 py-1.5 text-xs"
                value={activeVersion}
                onChange={(event) => setActiveVersion(Number(event.target.value))}
              >
                {versions.map((version) => (
                  <option key={version} value={version}>
                    v{version}
                  </option>
                ))}
              </select>
            )}
            <button className="btn-ghost">打印</button>
            <button
              className="btn-primary"
              onClick={() => {
                setExportStatus("rendering");
                // 导出接口在 T-22 落地，这里先给出明确的状态反馈
                setTimeout(() => setExportStatus("done"), 600);
              }}
            >
              导出
            </button>
          </div>
        </div>

        <article className="card divide-y divide-ink-100 px-5 py-4">
          {SECTION_TITLES.map((title, index) => (
            <section key={title} className="py-3">
              <h2 className="text-sm font-semibold">
                <span className="mr-2 font-mono text-ink-400">{index + 1}</span>
                {title}
              </h2>
              <p className="mt-1 text-xs text-ink-500">
                {index === 0 && "指标 GMV · 统计周期 08-12 ~ 08-18 · 基期：日环比 · 差异额 -¥1,432 万"}
                {index === 1 && "访客数 -45% · 转化率 -32% · 客单价 -18% · 合计偏差 0"}
                {index === 2 && "TOP 维度组合：抖音 / 手机数码 / 新客；转化率下滑 2.4pct"}
                {index === 3 && "主因：渠道结构恶化（低转化渠道占比 +8pct）；次因：转化率下降；外因：竞品补贴"}
                {index === 4 && "沙箱验证 5 条假设，4 条置信度 ≥ 60%，1 条判定伪相关已排除"}
                {index === 5 && "预算重配至搜索渠道，预计 GMV +6.3%（区间 +2.0% ~ +11.5%）"}
                {index === 6 && "渠道运营负责人 · 7 天 · 预期挽回 ¥286 万"}
              </p>
            </section>
          ))}
        </article>

        <div className="card p-4">
          <h2 className="mb-2 text-sm font-semibold">批注区</h2>
          <div className="flex gap-2">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && submitAnnotation()}
              placeholder="选中文本添加批注，@ 同事…"
              className="flex-1 rounded-md border border-ink-200 px-3 py-1.5 text-sm outline-none focus:border-ink-400"
            />
            <button className="btn-primary" onClick={submitAnnotation}>
              添加
            </button>
          </div>
          <ul className="mt-3 space-y-1.5 text-xs">
            {annotations.length === 0 && <li className="text-ink-400">暂无批注</li>}
            {annotations.map((annotation) => (
              <li key={annotation.id} className="rounded border border-ink-200 px-2 py-1.5">
                <span className="text-ink-500">
                  {annotation.author} · v{annotation.version} · {annotation.anchor}
                </span>
                <p className="mt-0.5 text-ink-800">{annotation.content}</p>
              </li>
            ))}
          </ul>
        </div>

        <div className="card flex items-center gap-3 p-4 text-xs">
          <span className="text-ink-500">导出格式</span>
          {EXPORT_FORMATS.map((format) => (
            <span key={format} className="rounded border border-ink-200 px-2 py-1">
              {format}
            </span>
          ))}
          <span className="ml-auto text-ink-400">
            {exportStatus === "rendering" && "正在渲染…"}
            {exportStatus === "done" && "导出完成（渲染服务在 T-22 接入）"}
            {exportStatus === "failed" && "导出失败"}
          </span>
        </div>
      </div>
    </div>
  );
}
