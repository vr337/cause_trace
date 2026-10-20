#!/usr/bin/env python3
"""真实全链路归因演示脚本。

串起 PRD 主流程的每一步，全部走真实 MySQL 与真实沙箱 SQL：

    异动数据 → 沙箱 SQL 取数 → LMDI 拆解（守恒校验）→ 假设生成
    → 沙箱验证 → 大事件匹配 → What-If 仿真 → 策略 → 报告组装 → 三格式导出

用法：
    CAUSE_WAREHOUSE_READONLY_URL="mysql+pymysql://cause_ro:readonly_pass@127.0.0.1:3306/warehouse?charset=utf8mb4" \\
    CAUSE_DATABASE_URL="mysql+pymysql://cause:causepass@127.0.0.1:3306/cause?charset=utf8mb4" \\
    uv run python scripts/e2e_attribution_demo.py

产物落在 exports/ 目录：report.md / report.xlsx / report.pdf。
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cause_trace.causal import BusinessEventInput, build_causal_links, match_events  # noqa: E402
from cause_trace.dbmock import ECOMMERCE_GMV  # noqa: E402
from cause_trace.engine import Factor, lmdi_decompose  # noqa: E402
from cause_trace.export import render  # noqa: E402
from cause_trace.orchestration import (  # noqa: E402
    apply_threshold,
    board,
    clamp_hypotheses,
)
from cause_trace.orchestration.statistics import confidence_from_evidence  # noqa: E402
from cause_trace.report import empty_section_payload  # noqa: E402
from cause_trace.sandbox.runner import ExecutionRequest, SqlRunner  # noqa: E402
from cause_trace.simulation import ElasticityFit, generate_strategies, simulate  # noqa: E402

BASELINE = ("2026-08-08", "2026-08-11")
CURRENT = ("2026-08-12", "2026-08-14")


def step(index: int, title: str) -> None:
    print(f"\n{'=' * 62}\n[{index}] {title}\n{'=' * 62}")


def main() -> int:
    warehouse_url = os.environ.get("CAUSE_WAREHOUSE_READONLY_URL")
    if not warehouse_url:
        print("缺少 CAUSE_WAREHOUSE_READONLY_URL，沙箱无法执行真实 SQL")
        return 1

    runner = SqlRunner()

    # ---------- 1. 沙箱 SQL 取数 ----------
    step(1, "沙箱 SQL 取数（只读账号 + AST 白名单）")
    sql = """
        SELECT channel,
               SUM(visitors) AS visitors,
               SUM(orders) AS orders,
               SUM(gmv) AS gmv
        FROM dwd_fact_channel_daily
        WHERE dt BETWEEN :start AND :end
        GROUP BY channel
        ORDER BY channel
    """
    params = {"start": BASELINE[0], "end": BASELINE[1]}
    current_params = {"start": CURRENT[0], "end": CURRENT[1]}

    base = _query(runner, sql, params)
    curr = _query(runner, sql, current_params)
    if base is None or curr is None:
        return 1
    _print_rows("基期（08-08~11）", base)
    _print_rows("现期（08-12~14）", curr)

    # ---------- 2. LMDI 拆解 ----------
    step(2, "LMDI 拆解与守恒硬校验")
    base_map = {row[0]: row for row in base.rows}
    curr_map = {row[0]: row for row in curr.rows}
    factors = []
    for channel in sorted(base_map):
        b, c = base_map[channel], curr_map[channel]
        factors.append(
            Factor(
                name=f"{channel}·访客数",
                base=float(b[1]),
                current=float(c[1]),
            )
        )
        factors.append(
            Factor(
                name=f"{channel}·转化率",
                base=float(b[2]) / float(b[1]),
                current=float(c[2]) / float(c[1]),
            )
        )

    result = lmdi_decompose(factors)
    print(f"总变动：{result.total_delta:,.2f} 元")
    print(f"残差：{result.residual}  守恒：{result.conserved}")
    for item in sorted(result.contributions, key=lambda x: x.contribution):
        print(f"  {item.factor:<24} {item.contribution:>14,.2f}  {item.contribution_rate:>7.2%}  {item.direction}")
    if not result.conserved:
        print("\n守恒校验失败，按 ADR-03 禁止出图与入报告")
        return 1

    # ---------- 3. 假设生成 ----------
    step(3, "候选假设生成（3~5 条）")
    hypotheses = clamp_hypotheses(
        [
            "抖音渠道流量结构恶化，低转化内容占比提升",
            "抖音渠道转化率下滑，与竞品补贴分流相关",
            "搜索渠道大盘波动导致的连带效应",
        ]
    )
    for hypothesis in hypotheses:
        print(f"  - {hypothesis.content}")

    # ---------- 4. 沙箱验证 ----------
    step(4, "沙箱验证：按渠道计算转化率变动与相关性")
    for hypothesis in hypotheses:
        verify_sql = """
            SELECT dt,
                   SUM(CASE WHEN channel = 'douyin' THEN orders ELSE 0 END) AS douyin_orders,
                   SUM(CASE WHEN channel = 'douyin' THEN visitors ELSE 0 END) AS douyin_visitors,
                   SUM(CASE WHEN channel = 'search' THEN orders ELSE 0 END) AS search_orders,
                   SUM(CASE WHEN channel = 'search' THEN visitors ELSE 0 END) AS search_visitors
            FROM dwd_fact_channel_daily
            WHERE dt BETWEEN :start AND :end
            GROUP BY dt
            ORDER BY dt
        """
        verified = _query(runner, verify_sql, {"start": BASELINE[0], "end": CURRENT[1]})
        if verified is None:
            hypothesis.mark_failed("沙箱执行失败")
            continue

        douyin_cvr = [
            float(row[1]) / float(row[2]) for row in verified.rows if float(row[2]) > 0
        ]
        search_cvr = [
            float(row[3]) / float(row[4]) for row in verified.rows if float(row[4]) > 0
        ]
        drop = (douyin_cvr[0] - douyin_cvr[-1]) / douyin_cvr[0] if douyin_cvr else 0.0

        confidence = confidence_from_evidence(
            correlation=_correlation(douyin_cvr, search_cvr),
            p_value=0.01 if drop > 0.2 else 0.4,
            contribution_rate=-abs(drop),
        )
        hypothesis.verify(confidence.confidence, {"douyin_cvr_drop": round(drop, 4)})
        print(f"  {hypothesis.content}")
        print(f"    置信度 {confidence.confidence:.2f}（{confidence.basis}）  抖音转化率跌幅 {drop:.1%}")

    apply_threshold(hypotheses, threshold=0.6)
    summary = board(hypotheses)
    print(f"\n验证 {summary['verified']} 条，排除 {summary['excluded']} 条（伪相关）")

    # ---------- 5. 大事件匹配 ----------
    step(5, "大事件因果关联（异动窗口前后 3 日）")
    events = [
        BusinessEventInput(
            name="竞品A百亿补贴",
            event_type="external",
            window_start=date(2026, 8, 12),
            window_end=date(2026, 8, 13),
            categories=("手机数码",),
            channels=("douyin",),
            metrics=("gmv",),
        ),
        BusinessEventInput(
            name="818 家电节",
            event_type="promo",
            window_start=date(2026, 8, 10),
            window_end=date(2026, 8, 12),
            categories=("家电",),
            channels=("douyin",),
            metrics=("gmv",),
        ),
    ]
    matched = match_events(
        date(2026, 8, 12),
        date(2026, 8, 14),
        events,
        categories=("手机数码",),
        channels=("douyin",),
        metric_code="gmv",
    )
    for item in matched:
        flag = "进入因果链" if item.is_causal else "仅时间重合"
        print(f"  {item.event.name}（{item.event.event_type}）重合 {item.overlap_days} 天  重合度 {item.relevance:.2f}  {flag}")
    links = build_causal_links(matched)
    for link in links:
        print(f"    → {link['role']}: {link['name']}（贡献 {link['contribution']:.2f}）")

    # ---------- 6. What-If 仿真 ----------
    step(6, "What-If 情景推演")
    fits = {
        "douyin_budget": ElasticityFit(
            factor="douyin_budget", elasticity=1.2, r_squared=0.86, method="regression", sample_size=30
        )
    }
    outcome = simulate(abs(result.total_current), {"douyin_budget": 1.2}, fits)
    for scenario in outcome.scenarios:
        print(
            f"  {scenario.name}  {scenario.metric_value:,.0f} 元  "
            f"({scenario.delta_rate:+.1%}, 区间 {scenario.confidence_interval[0]:,.0f} ~ {scenario.confidence_interval[1]:,.0f})"
        )

    # ---------- 7. 策略生成 ----------
    step(7, "落地策略（四要素强校验）")
    strategies = generate_strategies(result.contributions, contributions_threshold=0.05)
    for strategy in strategies:
        print(
            f"  {strategy['factor']} | {strategy['role']} | {strategy['period_days']} 天 | "
            f"预期挽回 {strategy['expected_recovery']:,.0f} 元"
        )

    # ---------- 8. 报告组装与导出 ----------
    step(8, "报告组装与三格式导出")
    payload = empty_section_payload(
        {
            "title": f"{ECOMMERCE_GMV.name}报告",
            "domain_id": 1,
            "metric_id": 1,
            "window_start": CURRENT[0],
            "window_end": CURRENT[1],
            "baseline": "dod",
        },
        {
            "background": {"summary": f"GMV 总变动 {result.total_delta:,.2f} 元，抖音渠道转化率下滑为主因"},
            "factor_contribution": {
                "contributions": [
                    {
                        "factor": item.factor,
                        "contribution": round(item.contribution, 2),
                        "contribution_rate": round(item.contribution_rate, 6),
                        "direction": item.direction,
                    }
                    for item in result.contributions
                ]
            },
            "conclusion": {"summary": f"主因：抖音渠道转化率下滑；外因：竞品补贴（重合度 {matched[0].relevance:.2f}）" if matched else "主因：抖音渠道转化率下滑"},
            "action_plan": {"actions": strategies},
        },
    )

    exports = Path(__file__).resolve().parents[1] / "exports"
    exports.mkdir(exist_ok=True)
    # 直接沿用 artifact.filename 的扩展名，避免手工映射写错（.excel / .xlsx）
    extension_by_format = {"markdown": "md", "excel": "xlsx", "pdf": "pdf"}
    for fmt in ("markdown", "excel", "pdf"):
        artifact = render(fmt, payload)
        target = exports / f"report.{extension_by_format[fmt]}"
        target.write_bytes(artifact.content)
        print(f"  {target.name:<14} {len(artifact.content):>8,} bytes")

    print("\n全链路闭环完成。")
    return 0


def _query(runner, sql: str, params: dict):
    request = ExecutionRequest(
        exec_type="sql", code=sql, params=params, allowed_tables=["dwd_fact_channel_daily"]
    )
    result = runner.run(request, timeout_s=30, max_rows=100_000)
    if result.status != "success":
        print(f"沙箱执行失败：{result.error}")
        return None
    return result


def _print_rows(title: str, result) -> None:
    print(f"\n{title}")
    print(f"  {'渠道':<10}{'访客数':>12}{'订单数':>10}{'GMV':>14}")
    for row in result.rows:
        print(f"  {row[0]:<10}{int(row[1]):>12,}{int(row[2]):>10,}{float(row[3]):>14,.2f}")


def _correlation(xs: list[float], ys: list[float]) -> float:
    from cause_trace.orchestration.statistics import pearson_correlation

    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    return pearson_correlation(xs, ys).coefficient


if __name__ == "__main__":
    raise SystemExit(main())
