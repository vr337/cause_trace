-- 演示用种子数据：指标域、数据源、指标、拆解规则与异动阈值。
-- 灌完后前端大盘/工作台才有可操作的数据，否则接口会因外键约束报错。
--
-- 用法：
--   docker exec -i cause-mysql mysql -ucause -pcausepass cause < scripts/seed_demo.sql
-- 或本地已装 mysql 客户端：
--   mysql -ucause -pcausepass cause < scripts/seed_demo.sql

INSERT INTO metric_domain (name, biz_line, status) VALUES ('电商经营域', '电商', 'enabled');

-- ADR-06：只存密钥引用键名，真实口令通过环境变量注入
INSERT INTO data_source (name, db_type, host, port, db_name, account, secret_ref, is_readonly)
VALUES ('warehouse', 'mysql', '127.0.0.1', 3306, 'warehouse', 'cause_ro', 'WAREHOUSE_RO_PASSWORD', 1);

-- GMV = 访客数 × 转化率 × 客单价，乘法模型走 LMDI
INSERT INTO metric (domain_id, data_source_id, code, name, metric_type, algebra, formula, unit, elasticity, status)
VALUES (1, 1, 'gmv', 'GMV', 'composite', 'multiplicative', 'visitors*cvr*aov', '元', 1.200000, 'enabled');
INSERT INTO metric (domain_id, data_source_id, code, name, metric_type, algebra, formula, unit, status)
VALUES (1, 1, 'visitors', '访客数', 'atomic', 'additive', NULL, '人', 'enabled');
INSERT INTO metric (domain_id, data_source_id, code, name, metric_type, algebra, formula, unit, status)
VALUES (1, 1, 'cvr', '转化率', 'derived', 'multiplicative', NULL, '%', 'enabled');
INSERT INTO metric (domain_id, data_source_id, code, name, metric_type, algebra, formula, unit, status)
VALUES (1, 1, 'aov', '客单价', 'derived', 'multiplicative', NULL, '元', 'enabled');

-- 利润 = 营收 - 成本 - 税费，加法模型走差额分析
INSERT INTO metric (domain_id, data_source_id, code, name, metric_type, algebra, formula, unit, status)
VALUES (1, 1, 'profit', '利润', 'composite', 'additive', 'revenue-cost-tax', '元', 'enabled');

INSERT INTO decomp_rule (metric_id, method, default_level) VALUES (1, 'lmdi', 2);
INSERT INTO decomp_rule (metric_id, method, default_level) VALUES (5, 'diff', 1);

INSERT INTO anomaly_threshold (metric_id, rule_type, threshold_value, alarm_level, notify_channels, enabled)
VALUES (1, 'dod', -0.100000, 'warning', '["wecom"]', 1);
INSERT INTO anomaly_threshold (metric_id, rule_type, threshold_value, alarm_level, notify_channels, enabled)
VALUES (3, 'dod', -0.050000, 'warning', '["wecom"]', 1);

-- 全局沙箱配额：用户级配额可在后台按 global < role < user 覆盖
INSERT INTO sandbox_quota (scope_type, scope_id, cpu_core, memory_mb, timeout_s, max_concurrent, max_rows, enabled)
VALUES ('global', 'default', 1.00, 512, 30, 3, 100000, 1);

-- 与电商 GMV 下滑场景对应的演示事件（T-19 注入窗口 2026-08-12~18）
INSERT INTO business_event (name, event_type, window_start, window_end, scope, related_metric_ids, remark)
VALUES ('竞品A百亿补贴', 'external', '2026-08-12 00:00:00', '2026-08-13 23:59:59',
        '{"categories": ["手机数码"], "channels": ["douyin"]}', '[1]', '演示数据');
INSERT INTO business_event (name, event_type, window_start, window_end, scope, related_metric_ids, remark)
VALUES ('818 家电节', 'promo', '2026-08-10 00:00:00', '2026-08-12 23:59:59',
        '{"categories": ["家电"], "channels": ["douyin"]}', '[1]', '演示数据');
