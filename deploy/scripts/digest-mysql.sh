#!/bin/bash
# 在 MySQL 服务器（CDWY2）上执行：按 id 顺序导出 log_record，计算内容摘要（与 digest-mongo.sh 的结果比较）。
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
CID=$(docker ps -q --filter name=lab_mysql | head -1)
docker exec "$CID" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B lab4_log -e "
  SET time_zone = \"+00:00\";
  SELECT id, IFNULL(trace_id, \"\"), level, source, message, client_ip,
         CAST(ROUND(UNIX_TIMESTAMP(created_at) * 1000) AS UNSIGNED)
  FROM log_record ORDER BY id"' | python3 "$REPO/tools/db_digest.py" --format mysql
