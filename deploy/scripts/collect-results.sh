#!/bin/bash
# 把 CDWY3 上一轮测试的原始结果下载到本地 results/<轮次>/。
# 每次测试只保留：samples.jtl.gz（原始 JTL，gzip -9 压缩，解压即得原文件）、params.txt（参数）、
# start.txt/end.txt（UTC 起止时间，用于对应 Prometheus 监控时间段）、db-rows.txt（写测试的入库行数核对）。
# 用法：LAB_SSH=/path/to/lab-ssh.sh bash deploy/scripts/collect-results.sh <轮次名> [本地目录]
set -euo pipefail
: "${LAB_SSH:?请设置 LAB_SSH（SSH 辅助命令）}"
ROUND=${1:?轮次名}
DEST=${2:-results/$ROUND}
mkdir -p "$DEST"

"$LAB_SSH" cdwy3 "cd /root/lab4/results/$ROUND && for d in */; do [ -f \"\$d/samples.jtl\" ] && gzip -9 -k -f \"\$d/samples.jtl\"; done; \
  tar -czf - */samples.jtl.gz */params.txt */start.txt */end.txt \$(ls */db-rows.txt 2>/dev/null)" 2>/dev/null \
  | tar -xzf - -C "$DEST"
echo "collected into $DEST: $(ls -d "$DEST"/*/ | wc -l | tr -d ' ') runs, $(du -sh "$DEST" | cut -f1)"
