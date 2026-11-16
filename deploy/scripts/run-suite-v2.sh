#!/bin/bash
# 实验四第二阶段测试编排：主对比（3 轮）、MongoDB j:true 对照、并发量调优、连接池调优、过载与恢复。
# 在能免密 SSH 到 5 台服务器的客户端上执行；LAB_SSH 用法：$LAB_SSH <cdwy1..cdwy5> '<远程命令>'。
#
#   bash run-suite-v2.sh main <轮次>             主对比：查询 50 线程、写入 100 线程，两种实现（结果目录 m<轮次>）
#   bash run-suite-v2.sh journal <轮次...>       MongoDB 开 j:true 后测写入 100 线程（结果放入对应的 m<轮次>）
#   bash run-suite-v2.sh sweep                   并发量调优：25/50/75/100/150 线程（50/100 复用主对比第 1 轮）
#   bash run-suite-v2.sh pool <查询线程> <写入线程>  连接池调优：两种实现的连接池依次设为 25、50（100 复用已有结果）
#   bash run-suite-v2.sh overload                过载与恢复：600/800/1000 线程，JMeter 在 CDWY4，每档后接 10 线程恢复检查
#
# 统一参数：升压 20 秒，每个线程持续 240 秒，统计第 60～240 秒；测前用相同线程数单独预热 120 秒
# （预热只保留汇总行到 warmups.log）；写入测试前把两个数据库都重置为同一份 10 万条预置数据。
set -euo pipefail
: "${LAB_SSH:?请设置 LAB_SSH（SSH 辅助命令）}"
APP_HOST=172.31.1.202
RESULTS=${RESULTS:-/root/lab4/results}
# 可用环境变量覆盖（试运行时缩短）：RAMP DURATION WARMUP COOLDOWN
RAMP=${RAMP:-20}; DURATION=${DURATION:-240}; WARMUP=${WARMUP:-120}; COOLDOWN=${COOLDOWN:-30}

s() { "$LAB_SSH" "$@" 2>/dev/null; }
log() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*"; }
port_of() { [ "$1" = jpa ] && echo 8081 || echo 8082; }
svc_of() { [ "$1" = jpa ] && echo lab4_logjpa || echo lab4_logmongo; }
plan_of() { [ "$1" = read ] && echo ReadLog || echo WriteLog; }
JENV='if [ -f /root/lab4/jmeter-env.sh ]; then source /root/lab4/jmeter-env.sh; else source /etc/profile.d/lab3-tools.sh; fi'

count_rows() { # $1=impl
  if [ "$1" = jpa ]; then
    s cdwy2 'CID=$(docker ps -q --filter name=lab_mysql | head -1); docker exec "$CID" sh -c "MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\" mysql -uroot -N -e \"SELECT COUNT(*) FROM lab4_log.log_record\""' | tr -dc '0-9'
  else
    s cdwy5 'CID=$(docker ps -q --filter name=lab4_mongo | head -1); docker exec "$CID" sh -c "mongosh --quiet -u root -p \"\$(cat /run/secrets/lab4_mongo_root_password)\" --authenticationDatabase admin lab4_log --eval \"db.log_record.countDocuments()\""' | tr -dc '0-9'
  fi
}

reset_db() {
  s cdwy2 'bash /root/lab4/repo/deploy/scripts/seed-mysql.sh' > /dev/null &
  s cdwy5 'bash /root/lab4/repo/deploy/scripts/seed-mongo.sh' > /dev/null &
  wait
}

wait_health() { # $1=port
  for _ in $(seq 1 60); do
    s cdwy1 "curl -fs -m 2 127.0.0.1:$1/actuator/health" | grep -q UP && return 0
    sleep 3
  done
  log "!! 端口 $1 健康检查超时"; return 1
}

set_env() { # $1=service $2=VAR=value → 滚动重启该服务并等待健康
  s cdwy1 "docker service update --quiet --env-add $2 $1 >/dev/null 2>&1"
  wait_health "$([ "$1" = lab4_logjpa ] && echo 8081 || echo 8082)"
  log "  $1 已设置 $2：$(s cdwy1 "docker logs \$(docker ps -q --filter name=$1 | head -1) 2>&1 | grep -o 'logdemo-[a-z]* settings.*' | tail -1")"
}

jm() { # $1=压测机 $2=输出目录 $3=plan $4=impl $5=线程 $6=升压 $7=持续 [$8=JMETER_HEAP]
  local heap=${8:-}
  s "$1" "$JENV; ${heap:+JMETER_HEAP='$heap'} bash /root/lab4/jmeter/run-test.sh $3 $APP_HOST $(port_of "$4") $5 $6 $7 $2" | sed 's/^/    /'
}

warmup() { # $1=压测机 $2=组 $3=op $4=impl $5=线程 [$6=heap]
  local dir="$RESULTS/$2/_warmup/$4-$3-t$5"
  log "  预热 $4 $3 t=$5 ${WARMUP}s"
  jm "$1" "$dir" "$(plan_of "$3")" "$4" "$5" 10 "$WARMUP" "${6:-}" > /dev/null
  s "$1" "{ printf '%s ' '$4-$3-t$5'; grep 'summary =' $dir/console.log | tail -1; } >> $RESULTS/$2/warmups.log; rm -rf $dir; rmdir $RESULTS/$2/_warmup 2>/dev/null || true"
  [ "$3" = write ] || sleep 10
}

measure() { # $1=压测机 $2=组 $3=op $4=impl(jpa|mongo|mongoj) $5=阶段 $6=线程 [$7=升压] [$8=持续] [$9=heap]
  local gen=$1 group=$2 op=$3 impl=$4 phase=$5 t=$6 ramp=${7:-$RAMP} dur=${8:-$DURATION} heap=${9:-}
  local dir="$RESULTS/$group/$impl-$op-$phase-t$t" before after
  if [ "$op" = write ]; then reset_db; before=$(count_rows "$impl"); fi
  log "▶ $impl $op $phase t=$t（升压 ${ramp}s，持续 ${dur}s）"
  jm "$gen" "$dir" "$(plan_of "$op")" "$impl" "$t" "$ramp" "$dur" "$heap"
  if [ "$op" = write ]; then
    after=$(count_rows "$impl"); before=${before:-0}; after=${after:-0}
    s "$gen" "printf 'rows_before=%s\nrows_after=%s\ninserted=%s\n' $before $after $((after - before)) > $dir/db-rows.txt"
    log "  入库行数 $before → $after（新增 $((after - before))）"
  fi
  sleep "$COOLDOWN"
}

main_round() { # $1=轮次
  local r=$1 order
  [ $((r % 2)) -eq 1 ] && order="jpa mongo" || order="mongo jpa"
  s cdwy3 "mkdir -p $RESULTS/m$r"
  log "== 主对比第 $r 轮（顺序：$order）"
  for spec in "read 50" "write 100"; do
    set -- $spec
    for impl in $order; do
      warmup cdwy3 "m$r" "$1" "$impl" "$2"
      measure cdwy3 "m$r" "$1" "$impl" main "$2"
    done
  done
}

journal_rounds() { # $@=轮次
  log "== MongoDB j:true 对照（写入 100 线程）"
  set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=true
  for r in "$@"; do
    s cdwy3 "mkdir -p $RESULTS/m$r"
    warmup cdwy3 "m$r" write mongoj 100
    measure cdwy3 "m$r" write mongoj main 100
  done
  set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=false
}

sweep() {
  s cdwy3 "mkdir -p $RESULTS/sweep"
  log "== 并发量调优"
  for spec in "read 25 75 100 150" "write 25 50 75 150"; do
    set -- $spec; local op=$1; shift
    for impl in jpa mongo; do warmup cdwy3 sweep "$op" "$impl" 50; done
    local i=0
    for t in "$@"; do
      if [ $((i % 2)) -eq 0 ]; then order="jpa mongo"; else order="mongo jpa"; fi
      i=$((i + 1))
      for impl in $order; do measure cdwy3 sweep "$op" "$impl" sweep "$t"; done
    done
  done
}

pool() { # $1=查询线程 $2=写入线程
  local read_t=$1 write_t=$2
  s cdwy3 "mkdir -p $RESULTS/pool"
  log "== 连接池调优（查询 $read_t 线程、写入 $write_t 线程）"
  for size in 25 50; do
    set_env lab4_logjpa "LOGDEMO_POOL_MAXSIZE=$size"
    set_env lab4_logmongo "LOGDEMO_POOL_MAXSIZE=$size"
    for spec in "read $read_t" "write $write_t"; do
      set -- $spec
      for impl in jpa mongo; do
        warmup cdwy3 pool "$1" "$impl" "$2"
        measure cdwy3 pool "$1" "$impl" "pool$size" "$2"
      done
    done
  done
  set_env lab4_logjpa LOGDEMO_POOL_MAXSIZE=100
  set_env lab4_logmongo LOGDEMO_POOL_MAXSIZE=100
}

prepare_cdwy4() { # 把 CDWY3 上的 JDK 与 JMeter 经内网复制到 CDWY4（只做一次），并同步 JMeter 计划与数据
  if ! s cdwy4 'test -x /opt/apache-jmeter-5.6.3/bin/jmeter && test -x /opt/jdk-21/bin/java'; then
    log "  向 CDWY4 复制 JDK 21 与 JMeter 5.6.3（内网）"
    ( s cdwy4 'timeout 600 nc -l 172.31.1.19 15002 | tar -xzf - -C /opt' & )
    sleep 3
    s cdwy3 'tar -czf - -C /opt jdk-21 apache-jmeter-5.6.3 | nc -N 172.31.1.19 15002'
    sleep 5
  fi
  s cdwy4 'mkdir -p /root/lab4 && printf "%s\n" "export JAVA_HOME=/opt/jdk-21" "export JMETER_HOME=/opt/apache-jmeter-5.6.3" "export PATH=\$JAVA_HOME/bin:\$JMETER_HOME/bin:\$PATH" > /root/lab4/jmeter-env.sh'
  s cdwy3 'tar -czf - -C /root/lab4 jmeter' | s cdwy4 'rm -rf /root/lab4/jmeter && tar -xzf - -C /root/lab4'
  log "  CDWY4 JMeter：$(s cdwy4 'source /root/lab4/jmeter-env.sh; HEAP="-Xms128m -Xmx256m" jmeter --version 2>/dev/null | grep -o "5\.[0-9.]*" | head -1')"
}

overload() {
  local heap='-Xms512m -Xmx768m -XX:MaxMetaspaceSize=128m'
  log "== 过载与恢复（JMeter 在 CDWY4）"
  prepare_cdwy4
  s cdwy4 "mkdir -p $RESULTS/overload"
  for op in read write; do
    for impl in jpa mongo; do warmup cdwy4 overload "$op" "$impl" 50 "$heap"; done
    local i=0
    for t in 600 800 1000; do
      if [ $((i % 2)) -eq 0 ]; then order="jpa mongo"; else order="mongo jpa"; fi
      i=$((i + 1))
      for impl in $order; do
        measure cdwy4 overload "$op" "$impl" overload "$t" 40 "$DURATION" "$heap"
        # 恢复检查：紧接过载之后 10 线程 60 秒，与过载前的状态对比（写入不重置数据，保留过载后的状态）
        local dir="$RESULTS/overload/$impl-$op-recovery$t-t10"
        log "▶ $impl $op recovery t=10（过载 $t 之后）"
        jm cdwy4 "$dir" "$(plan_of "$op")" "$impl" 10 2 60 "$heap"
        sleep "$COOLDOWN"
      done
    done
  done
}

case "${1:-}" in
  main) shift; for r in "$@"; do main_round "$r"; done ;;
  journal) shift; journal_rounds "$@" ;;
  sweep) sweep ;;
  pool) pool "$2" "$3" ;;
  overload) overload ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
reset_db
log "完成：$*"
