#!/bin/bash
# 在压测机（服务器 A，CDWY3）上执行一次 JMeter 非 GUI 测试，结果放在独立目录：
#   samples.jtl（原始 JTL，CSV 格式；不保存 URL 等无关字段以控制体积）、jmeter.log、console.log、start.txt/end.txt（UTC，用于对应 Prometheus 时间段）、
#   params.txt（本次参数）、report/（JMeter HTML 报告）
#
# 用法：bash run-test.sh <ReadLog|WriteLog> <主机> <端口> <线程数> <升压秒数> <持续秒数> <输出目录>
# 例：  bash run-test.sh ReadLog 172.31.1.202 8081 100 10 60 /root/lab4/results/jpa-read-load-t100
set -euo pipefail
cd "$(dirname "$0")"
PLAN=$1; HOST=$2; PORT=$3; THREADS=$4; RAMP=$5; DURATION=$6; OUT=$7
mkdir -p "$OUT"

# CDWY3 只有约 550MB 可用内存，JMeter 默认要 1GB 堆会启动失败，这里显式限制
export HEAP="${JMETER_HEAP:--Xms256m -Xmx400m -XX:MaxMetaspaceSize=128m}"
export JVM_ARGS="${JMETER_JVM_ARGS:--Xss256k}"

printf 'plan=%s\nhost=%s\nport=%s\nthreads=%s\nrampTime=%s\nduration=%s\nheap=%s\njvm_args=%s\n' \
  "$PLAN" "$HOST" "$PORT" "$THREADS" "$RAMP" "$DURATION" "$HEAP" "$JVM_ARGS" > "$OUT/params.txt"
date -u +%Y-%m-%dT%H:%M:%S.%3NZ > "$OUT/start.txt"
jmeter -n -t "$PLAN.jmx" \
  -Jhostname="$HOST" -Jport="$PORT" -Jthread="$THREADS" -JrampTime="$RAMP" -Jduration="$DURATION" -JdataDir=data \
  -Jjmeter.save.saveservice.output_format=csv \
  -Jjmeter.save.saveservice.url=false -Jjmeter.save.saveservice.data_type=false \
  -Jjmeter.save.saveservice.idle_time=false \
  -l "$OUT/samples.jtl" -j "$OUT/jmeter.log" > "$OUT/console.log" 2>&1
date -u +%Y-%m-%dT%H:%M:%S.%3NZ > "$OUT/end.txt"

# HTML 报告（压测结束后生成，不占用测试期间的 CPU）；图表粒度 1 秒。
# statistic_window=-1：百分位用全部样本计算（默认只用最后 2 万个样本，P95/P99 不准）
jmeter -g "$OUT/samples.jtl" -o "$OUT/report" -Jjmeter.reportgenerator.overall_granularity=1000 \
  -Jjmeter.reportgenerator.statistic_window=-1 \
  -j "$OUT/report.log" >> "$OUT/console.log" 2>&1 || echo "report generation failed" >> "$OUT/console.log"
grep -E 'summary =|failed' "$OUT/console.log" | tail -2 || true
