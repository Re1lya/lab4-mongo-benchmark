#!/bin/bash
# 在 MongoDB 服务器（CDWY5）上执行：重建 lab4_log.log_record（校验规则 + 索引）并装入预置数据集（默认 10 万条）。
# 用法：bash deploy/scripts/seed-mongo.sh [行数]
# 数据由 tools/gen_data.py 按固定随机种子生成，与 seed-mysql.sh 装入 MySQL 的是同一批记录。
set -euo pipefail
ROWS=${1:-100000}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
IMPORT=/root/lab4/mongo/import          # 挂载到容器内 /import
python3 "$REPO/tools/gen_data.py" seed --rows "$ROWS" --mongo-jsonl "$IMPORT/seed.jsonl" > "$IMPORT/seed-mongo-summary.json"
cp "$REPO/db/mongo/01-init.js" "$IMPORT/01-init.js"
CID=$(docker ps -q --filter name=lab4_mongo | head -1)
docker exec "$CID" sh -c '
  P=$(cat /run/secrets/lab4_mongo_root_password)
  mongosh --quiet -u root -p "$P" --authenticationDatabase admin lab4_log --eval "db.log_record.drop()" > /dev/null
  mongosh --quiet -u root -p "$P" --authenticationDatabase admin /import/01-init.js > /dev/null
  mongoimport --quiet -u root -p "$P" --authenticationDatabase admin -d lab4_log -c log_record \
    --file /import/seed.jsonl --numInsertionWorkers 2'
rm -f "$IMPORT/seed.jsonl"
cat "$IMPORT/seed-mongo-summary.json"
