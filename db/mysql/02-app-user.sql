-- 实验四 MySQL 应用账号：lab4app 只能查询和插入 lab4_log 库（最小权限）。
-- 密码不写入仓库：执行前在同一会话里设置变量 @lab4_app_password，例如
--   mysql -uroot -p -e "SET @lab4_app_password='<随机密码>'; SOURCE 02-app-user.sql;"
-- 部署脚本 deploy/scripts/init-mysql.sh 会在服务器上生成随机密码并保存为 Docker secret。

SET @create_user = CONCAT(
  'CREATE USER IF NOT EXISTS ''lab4app''@''%'' IDENTIFIED BY ', QUOTE(@lab4_app_password));
PREPARE stmt FROM @create_user;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 重复执行时同步密码
SET @alter_user = CONCAT('ALTER USER ''lab4app''@''%'' IDENTIFIED BY ', QUOTE(@lab4_app_password));
PREPARE stmt FROM @alter_user;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

GRANT SELECT, INSERT ON lab4_log.* TO 'lab4app'@'%';
