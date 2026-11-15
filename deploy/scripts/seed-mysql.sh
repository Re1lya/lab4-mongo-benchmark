#!/bin/bash
# 在 MySQL 服务器（CDWY2）上执行：清空 lab4_log.log_record 并装入预置数据集（默认 10 万条）。
# 用法：bash deploy/scripts/seed-mysql.sh [行数]
# 数据由 tools/gen_data.py 按固定随机种子生成，与 seed-mongo.sh 装入 MongoDB 的是同一批记录。
set -euo pipefail
ROWS=${1:-100000}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
WORK=/root/lab4/seed
mkdir -p "$WORK"
python3 "$REPO/tools/gen_data.py" seed --rows "$ROWS" --mysql-tsv "$WORK/seed.tsv" > "$WORK/seed-mysql-summary.json"
CID=$(docker ps -q --filter name=lab_mysql | head -1)
# secure_file_priv=/var/lib/mysql-files/：LOAD DATA INFILE 只能读这个目录
docker cp "$WORK/seed.tsv" "$CID:/var/lib/mysql-files/lab4-seed.tsv"
docker exec "$CID" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot lab4_log -e "
  TRUNCATE TABLE log_record;
  LOAD DATA INFILE \"/var/lib/mysql-files/lab4-seed.tsv\" INTO TABLE log_record
    CHARACTER SET utf8mb4 FIELDS TERMINATED BY \"\t\" LINES TERMINATED BY \"\n\"
    (id, trace_id, level, source, message, client_ip, created_at);
  ANALYZE TABLE log_record;"' > /dev/null
docker exec "$CID" rm -f /var/lib/mysql-files/lab4-seed.tsv
cat "$WORK/seed-mysql-summary.json"
