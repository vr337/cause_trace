# 验收证据：三格式导出样例

本目录存放由真实链路生成、可直接打开查验的报告产物，用于 AC FR-16 的验收留证。

## 文件

| 文件 | 大小 | 生成方式 | 校验结果 |
|------|------|---------|---------|
| `report.md` | 1,114 B | Jinja 风格文本模板 | 七章节齐全，含因子贡献表与策略清单 |
| `report.xlsx` | 9,546 B | openpyxl | 报告概览 + 7 个章节 sheet |
| `report.pdf` | 23,378 B | **WeasyPrint**（容器内渲染） | 2 页，1,493 字符，含页眉页脚与内联 SVG 瀑布图 |

## 生成命令

```bash
# 1. 准备最小数仓（真实数仓由 dbmock 生成）
docker exec -i cause-mysql mysql -uroot -prootpass < scripts/warehouse_demo.sql

# 2. 在容器内跑完整归因链路并导出三格式
docker run --rm \
  -v "$(pwd)/exports:/app/exports" \
  -e CAUSE_WAREHOUSE_READONLY_URL="mysql+pymysql://cause_ro:readonly_pass@host.docker.internal:3306/warehouse?charset=utf8mb4" \
  cause-trace-api:test python /app/scripts/e2e_attribution_demo.py
```

## 数据来源

演示数据对应 `ECOMMERCE_GMV` 场景：2026-08-12 起抖音渠道转化率由 2.40% 跌至 1.51%
（约 -37%），与 `src/cause_trace/dbmock/scenarios.py` 的注入配置一致。

## 校验记录

```bash
$ head -c 8 docs/evidence/report.pdf
%PDF-1.7

$ docker run --rm -v "$(pwd)/docs/evidence:/evidence:ro" cause-trace-api:test \
    python -c "from pypdf import PdfReader; r=PdfReader('/evidence/report.pdf'); \
               print(len(r.pages), sum(len(p.extract_text() or '') for p in r.pages))"
2 1493
```

`%PDF-1.7` + 对象流结构是 WeasyPrint 的特征；此前的纯文本兜底方案产出的是
`%PDF-1.4` 且只有 1 页。
