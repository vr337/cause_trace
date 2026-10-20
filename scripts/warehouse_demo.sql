-- 演示用最小 warehouse：只为验证沙箱 SQL 白名单与只读账号链路。
-- 真实 warehouse 由 dbmock 生成（不在本仓库），这里造同构的一张小表即可跑通 E2E。
--
-- 用法：
--   docker exec -i cause-mysql mysql -uroot -prootpass < scripts/warehouse_demo.sql

CREATE DATABASE IF NOT EXISTS warehouse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE warehouse;

DROP TABLE IF EXISTS dwd_fact_channel_daily;
CREATE TABLE dwd_fact_channel_daily (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  dt DATE NOT NULL,
  channel VARCHAR(32) NOT NULL,
  visitors BIGINT NOT NULL,
  orders BIGINT NOT NULL,
  gmv DECIMAL(18, 2) NOT NULL,
  KEY ix_dt_channel (dt, channel)
) ENGINE = InnoDB;

-- 08-12 起抖音渠道转化率下滑约 35%，与 ECOMMERCE_GMV 场景的注入配置一致
INSERT INTO dwd_fact_channel_daily (dt, channel, visitors, orders, gmv) VALUES
  ('2026-08-08', 'douyin', 100000, 2400, 480000.00),
  ('2026-08-09', 'douyin', 102000, 2450, 490000.00),
  ('2026-08-10', 'douyin',  98000, 2350, 470000.00),
  ('2026-08-11', 'douyin', 101000, 2420, 484000.00),
  ('2026-08-12', 'douyin', 103000, 1560, 312000.00),
  ('2026-08-13', 'douyin', 105000, 1590, 318000.00),
  ('2026-08-14', 'douyin',  99000, 1500, 300000.00),
  ('2026-08-08', 'search',  40000,  960, 192000.00),
  ('2026-08-09', 'search',  41000,  985, 197000.00),
  ('2026-08-10', 'search',  39000,  935, 187000.00),
  ('2026-08-11', 'search',  40500,  970, 194000.00),
  ('2026-08-12', 'search',  42000, 1010, 202000.00),
  ('2026-08-13', 'search',  43000, 1035, 207000.00),
  ('2026-08-14', 'search',  39500,  950, 190000.00);

-- T-02：只读专用账号，沙箱 SQL 一律走它；密码由部署侧环境变量注入
CREATE USER IF NOT EXISTS 'cause_ro'@'%' IDENTIFIED BY 'readonly_pass';
GRANT SELECT ON warehouse.* TO 'cause_ro'@'%';
ALTER USER 'cause_ro'@'%' WITH MAX_USER_CONNECTIONS 20;
FLUSH PRIVILEGES;
