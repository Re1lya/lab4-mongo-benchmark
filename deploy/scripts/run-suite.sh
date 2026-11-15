#!/bin/bash
# 实验四全部压测的编排脚本（约 90 分钟）。在能免密 SSH 到 5 台服务器的客户端上执行。
#
# 需要一个 SSH 辅助命令 LAB_SSH：用法为 `$LAB_SSH <cdwy1..cdwy5> '<远程命令>'`，
# 例如一个按别名执行 `ssh root@<IP> "$@"` 的小脚本。服务器之间不需要互相免密。
#
# 用法：LAB_SSH=/path/to/lab-ssh.sh bash deploy/scripts/run-suite.sh <轮次名> [read|write|all]
# 结果：CDWY3 的 /root/lab4/results/<轮次名>/<实现>-<读写>-<阶段>-t<线程数>/
#
# 设计要点（详见 docs）：
# - 负载测试 10/25/50/100 线程，压力测试 200/300/400 线程，每档持续 60 秒；400 线程后立即用 10 线程做恢复检查。
# - 两种实现交替执行（ABBA 顺序），减少环境随时间漂移带来的偏差。
# - 每组正式测试前，先用 50 线程预热 60 秒（JIT 编译、数据库缓存），预热结果单独保存、不参与比较。
# - 写测试每一档开始前，把两个数据库都重置为同一份 10 万条预置数据；读测试不改数据，不需要重置。
set -euo pipefail
: "${LAB_SSH:?请设置 LAB_SSH（SSH 辅助命令）}"
ROUND=${1:?请给出轮次名，例如 r1}
WHAT=${2:-all}

APP_HOST=172.31.1.202
LOAD_LEVELS="10 25 50 100"
STRESS_LEVELS="200 300 400"
DURATION=60
COOLDOWN=20
OUT=/root/lab4/results/$ROUND

s() { "$LAB_SSH" "$@" 2>/dev/null; }
log() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*"; }
port_of() { [ "$1" = jpa ] && echo 8081 || echo 8082; }
ramp_of() { [ "$1" -ge 200 ] && echo 20 || echo 10; }

count_rows() { # $1=impl → 当前表/集合的行数（只保留数字）
  _count_rows "$1" | tr -dc '0-9'
}
_count_rows() {
  if [ "$1" = jpa ]; then
    s cdwy2 'CID=$(docker ps -q --filter name=lab_mysql | head -1); docker exec "$CID" sh -c "MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\" mysql -uroot -N -e \"SELECT COUNT(*) FROM lab4_log.log_record\""'
  else
    s cdwy5 'CID=$(docker ps -q --filter name=lab4_mongo | head -1); docker exec "$CID" sh -c "mongosh --quiet -u root -p \"\$(cat /run/secrets/lab4_mongo_root_password)\" --authenticationDatabase admin lab4_log --eval \"db.log_record.countDocuments()\""'
  fi
}

run() { # $1=ReadLog|WriteLog $2=impl $3=phase(warmup|load|stress|recovery) $4=threads
  local plan=$1 impl=$2 phase=$3 t=$4 op dir before after
  op=$([ "$plan" = ReadLog ] && echo read || echo write)
  dir="$OUT/$impl-$op-$phase-t$t"
  [ "$plan" = WriteLog ] && before=$(count_rows "$impl")
  log "▶ $impl $op $phase t=$t"
  s cdwy3 "source /etc/profile.d/lab3-tools.sh; bash /root/lab4/jmeter/run-test.sh $plan $APP_HOST $(port_of "$impl") $t $(ramp_of "$t") $DURATION $dir" | sed 's/^/    /'
  if [ "$plan" = WriteLog ]; then
    after=$(count_rows "$impl")
    before=${before:-0}; after=${after:-0}
    s cdwy3 "printf 'rows_before=%s\nrows_after=%s\ninserted=%s\n' $before $after $((after - before)) > $dir/db-rows.txt"
    log "  入库行数 $before → $after（新增 $((after - before))）"
  fi
  sleep "$COOLDOWN"
}

reset_db() {
  log "重置两个数据库为 10 万条预置数据"
  s cdwy2 'bash /root/lab4/repo/deploy/scripts/seed-mysql.sh' > /dev/null &
  s cdwy5 'bash /root/lab4/repo/deploy/scripts/seed-mongo.sh' > /dev/null &
  wait
}

restart_apps() {
  log "重启两套日志服务（干净的 JVM 状态）"
  s cdwy1 'docker service update --force --detach=false lab4_logjpa >/dev/null 2>&1; docker service update --force --detach=false lab4_logmongo >/dev/null 2>&1'
  for p in 8081 8082; do
    for _ in $(seq 1 30); do
      s cdwy1 "curl -fs localhost:$p/actuator/health" | grep -q UP && break
      sleep 2
    done
  done
}

series() { # $1=ReadLog|WriteLog：预热 + 负载 + 压力 + 恢复，两种实现交替
  local plan=$1 i=0 first second t
  reset_db   # 读、写两组测试都从同一份 10 万条预置数据开始
  run "$plan" jpa warmup 50
  run "$plan" mongo warmup 50
  for t in $LOAD_LEVELS $STRESS_LEVELS; do
    if [ $((i % 2)) -eq 0 ]; then first=jpa; second=mongo; else first=mongo; second=jpa; fi
    i=$((i + 1))
    [ "$plan" = WriteLog ] && reset_db
    local phase=load
    [ "$t" -ge 200 ] && phase=stress
    if [ "$t" = 400 ]; then
      # 最高压力档：每种实现压完立即做恢复检查
      run "$plan" "$first" stress 400;  run "$plan" "$first" recovery 10
      run "$plan" "$second" stress 400; run "$plan" "$second" recovery 10
    else
      run "$plan" "$first" "$phase" "$t"
      run "$plan" "$second" "$phase" "$t"
    fi
  done
}

log "轮次 $ROUND 开始（$WHAT）"
s cdwy3 "mkdir -p $OUT"
s cdwy1 'docker service ls --format "{{.Name}} {{.Replicas}} {{.Image}}"' | s cdwy3 "cat > $OUT/services-before.txt"
restart_apps
case "$WHAT" in
  read) series ReadLog ;;
  write) series WriteLog ;;
  all) series ReadLog; series WriteLog ;;
esac
reset_db
log "轮次 $ROUND 完成"
