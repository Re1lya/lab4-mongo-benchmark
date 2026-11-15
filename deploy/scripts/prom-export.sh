#!/bin/bash
# 在 Prometheus 服务器（服务器 D，CDWY4）上执行：导出一段时间内实验四相关的监控数据。
# 用法：bash prom-export.sh <起始UTC，如 2026-11-15T12:39:00Z> <结束UTC> <输出文件.txt.gz>
#
# 现有 Prometheus 开启了 basic auth。这里不经过 HTTP API，而是：
#   1) 复制与时间段重叠的 TSDB 数据块、WAL（预写日志）和 head 块到快照目录（不改动正在运行的 Prometheus）；
#   2) 用同一镜像里的 promtool 离线读取快照：promtool tsdb dump；
#   3) 删除快照。
# 输出每行一个样本：{标签...} 值 时间戳(毫秒)。
set -euo pipefail
FROM=$1; TO=$2; OUT=$3
SRC=/var/lib/docker/volumes/lab_lab3-prometheus-data/_data
SNAP=/root/lab4/promsnap
IMG=lab3/prometheus:20261017
from_ms=$(( $(date -d "$FROM" +%s) * 1000 ))
to_ms=$(( $(date -d "$TO" +%s) * 1000 ))

rm -rf "$SNAP"; mkdir -p "$SNAP"
for b in "$SRC"/01*/; do
  [ -f "$b/meta.json" ] || continue
  if python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m["maxTime"] >= int(sys.argv[2]) and m["minTime"] <= int(sys.argv[3]) else 1)' \
      "$b/meta.json" "$from_ms" "$to_ms"; then
    cp -a "$b" "$SNAP/"
  fi
done
cp -a "$SRC/wal" "$SRC/chunks_head" "$SNAP/"
mkdir -p "$SNAP/.sandbox"   # promtool 回放 WAL 用的临时目录，必须事先存在

NODE='{__name__=~"node_cpu_seconds_total|node_memory_MemAvailable_bytes|node_memory_MemTotal_bytes|node_load1|node_disk_written_bytes_total|node_disk_read_bytes_total|node_disk_writes_completed_total|node_disk_io_time_seconds_total|node_network_receive_bytes_total|node_network_transmit_bytes_total",job="node"}'
APP='{__name__=~"up|process_cpu_usage|system_cpu_usage|jvm_threads_live_threads|jvm_memory_used_bytes|jvm_gc_pause_seconds_sum|jvm_gc_pause_seconds_count|hikaricp_connections_active|hikaricp_connections_pending|hikaricp_connections|mongodb_driver_pool_checkedout|mongodb_driver_pool_waitqueuesize|mongodb_driver_pool_size|tomcat_threads_busy_threads|tomcat_threads_current_threads|http_server_requests_seconds_count|http_server_requests_seconds_sum",job=~"lab4-.*"}'

# 镜像默认以 nobody 运行，快照目录属于 root，这里用 root 运行临时容器（只读写快照副本）
docker run --rm --user 0:0 --memory 768m -v "$SNAP":/data --entrypoint /bin/promtool "$IMG" \
  tsdb dump --sandbox-dir-root=/data/.sandbox --min-time="$from_ms" --max-time="$to_ms" \
  --match="$NODE" --match="$APP" /data | gzip > "$OUT"
rm -rf "$SNAP"
echo "exported $(zcat "$OUT" | wc -l) samples to $OUT"
