#!/bin/bash
# 把压测机上一组测试的原始结果下载到本地 results/<组名>/（默认 CDWY3；过载实验在 CDWY4：HOST=cdwy4）。
# 每次测试只保留：samples.jtl.gz（原始 JTL，gzip -9 压缩，解压即得原文件）、params.txt（参数）、
# start.txt/end.txt（UTC 起止时间，用于对应 Prometheus 监控时间段）、db-rows.txt（写测试的入库行数核对），
# 以及组目录下的 warmups.log（预热汇总）、choice.txt（连接池调优并发量的选择依据）。
# 用法：LAB_SSH=/path/to/lab-ssh.sh [HOST=cdwy4] bash deploy/scripts/collect-results.sh <组名> [本地目录]
set -euo pipefail
: "${LAB_SSH:?请设置 LAB_SSH（SSH 辅助命令）}"
ROUND=${1:?组名}
HOST=${HOST:-cdwy3}
DEST=${2:-results/$ROUND}
mkdir -p "$DEST"

"$LAB_SSH" "$HOST" "cd /root/lab4/results/$ROUND && for d in */; do [ -f \"\$d/samples.jtl\" ] && gzip -9 -k -f \"\$d/samples.jtl\"; done; \
  tar -cf - */samples.jtl.gz */params.txt */start.txt */end.txt \$(ls */db-rows.txt warmups.log choice.txt probe.log 2>/dev/null)" 2>/dev/null \
  | tar -xf - -C "$DEST"
echo "collected into $DEST: $(ls -d "$DEST"/*/ | wc -l | tr -d ' ') runs, $(du -sh "$DEST" | cut -f1)"
