#!/bin/bash
# 在 MongoDB 服务器（CDWY5）上执行：按 _id 顺序导出 log_record，计算内容摘要（与 digest-mysql.sh 的结果比较）。
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
CID=$(docker ps -q --filter name=lab4_mongo | head -1)
docker exec "$CID" sh -c '
  mongoexport --quiet -u root -p "$(cat /run/secrets/lab4_mongo_root_password)" --authenticationDatabase admin \
    -d lab4_log -c log_record --sort "{_id: 1}" --jsonFormat canonical' | python3 "$REPO/tools/db_digest.py" --format mongo
