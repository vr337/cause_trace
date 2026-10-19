-- T-02：为沙箱/取数链路创建 warehouse 只读账号，替换 data-agent 现用的 root 直连。
-- 由 DBA 在 MySQL 上以管理员身份执行一次；密码通过环境变量注入，不写进仓库。
--
-- 用法：
--   mysql -uroot -p < scripts/warehouse_readonly.sql
--   （执行前把 <STRONG_PASSWORD> 换成实际口令，并同步写入 CAUSE_WAREHOUSE_READONLY_URL）

CREATE USER IF NOT EXISTS 'cause_ro'@'%' IDENTIFIED BY '<STRONG_PASSWORD>';

-- 只授予查询权限：任何 DML/DDL 在数据库侧就会失败，沙箱白名单是第一道闸，这里是第二道。
GRANT SELECT ON warehouse.* TO 'cause_ro'@'%';

-- 限制单条查询的扫描量与并发，避免异常 SQL 拖垮数仓
ALTER USER 'cause_ro'@'%' WITH MAX_USER_CONNECTIONS 20;

FLUSH PRIVILEGES;

-- 验证：以下语句应返回 1，写操作应被拒绝
-- SHOW GRANTS FOR 'cause_ro'@'%';
