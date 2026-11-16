#!/bin/bash
# 实验四第二阶段测试编排：主对比（3 轮）、MongoDB j:true 对照、并发量调优、过载与恢复、连接池调优。
# 可在客户端或任一服务器上执行（本组放在 CDWY4 后台运行，客户端关机不影响）；
# LAB_SSH 用法：$LAB_SSH <cdwy1..cdwy5> '<远程命令>'。
#
#   bash run-suite-v2.sh all                     依次执行下面全部（可重复执行：已完成的测试自动跳过）
#   bash run-suite-v2.sh main <轮次...>          主对比：查询 50 线程、写入 100 线程，两种实现（结果目录 m<轮次>）
#   bash run-suite-v2.sh journal <轮次...>       MongoDB 开 j:true 后测写入 100 线程（结果放入对应的 m<轮次>）
#   bash run-suite-v2.sh sweep                   并发量调优：25/50/75/100/150 线程（50/100 复用主对比第 1 轮）
#   bash run-suite-v2.sh overload                过载与恢复：600/800/1000 线程，JMeter 在 CDWY4，每档后接 10 线程恢复检查
#   bash run-suite-v2.sh pool auto|<查询线程> <写入线程>  连接池调优：两种实现连接池依次设为 25、50（100 复用已有结果）；
#                                                auto = 按 tools/choose_pool_threads.py 的规则从并发量调优结果中选
#
# 统一参数：升压 20 秒，每个线程持续 240 秒，统计第 60～240 秒；测前用相同线程数单独预热 120 秒
# （预热只保留汇总行到 warmups.log）；写入测试前把两个数据库都重置为同一份 10 万条预置数据。
set -euo pipefail
: "${LAB_SSH:?请设置 LAB_SSH（SSH 辅助命令）}"
APP_HOST=172.31.1.202
RESULTS=${RESULTS:-/root/lab4/results}
# 可用环境变量覆盖（试运行时缩短）：RAMP DURATION WARMUP COOLDOWN
RAMP=${RAMP:-20}; DURATION=${DURATION:-240}; WARMUP=${WARMUP:-120}; COOLDOWN=${COOLDOWN:-30}
OVERLOAD_HEAP='-Xms512m -Xmx768m -XX:MaxMetaspaceSize=128m'

s() { "$LAB_SSH" "$@" 2>/dev/null; }
log() { printf '%s %s\n' "$(date '+%m-%d %H:%M:%S')" "$*"; }
port_of() { [ "$1" = jpa ] && echo 8081 || echo 8082; }
plan_of() { [ "$1" = read ] && echo ReadLog || echo WriteLog; }
JENV='if [ -f /root/lab4/jmeter-env.sh ]; then source /root/lab4/jmeter-env.sh; else source /etc/profile.d/lab3-tools.sh; fi'

done_run() { # $1=压测机 $2=测试目录 → 已完成（有 end.txt 且 JTL 非空）返回 0
  s "$1" "test -s '$2/end.txt' && test -s '$2/samples.jtl'"
}

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

set_env() { # $1=service $2=VAR=value → 滚动重启该服务并等待健康（已是该值则不重启）
  local cur
  cur=$(s cdwy1 "docker service inspect $1 --format '{{range .Spec.TaskTemplate.ContainerSpec.Env}}{{println .}}{{end}}'" | grep -x "$2" || true)
  if [ -n "$cur" ]; then return 0; fi
  s cdwy1 "docker service update --quiet --env-add $2 $1 >/dev/null 2>&1"
  wait_health "$([ "$1" = lab4_logjpa ] && echo 8081 || echo 8082)"
  log "  $1 已设置 $2：$(s cdwy1 "docker logs \$(docker ps -q --filter name=$1 | head -1) 2>&1 | grep -o 'logdemo-[a-z]* settings.*' | tail -1")"
}

defaults() { # 每个阶段开始前确认两种实现为默认配置（连接池 100、MongoDB j:false）；已是默认则不重启
  set_env lab4_logjpa LOGDEMO_POOL_MAXSIZE=100
  set_env lab4_logmongo LOGDEMO_POOL_MAXSIZE=100
  set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=false
}

jm() { # $1=压测机 $2=输出目录 $3=plan $4=impl $5=线程 $6=升压 $7=持续 [$8=JMETER_HEAP]
  local heap=${8:-}
  s "$1" "$JENV; ${heap:+JMETER_HEAP='$heap'} bash /root/lab4/jmeter/run-test.sh $3 $APP_HOST $(port_of "$4") $5 $6 $7 '$2'" | sed 's/^/    /'
}

warmup() { # $1=压测机 $2=组 $3=op $4=impl $5=线程 [$6=heap]
  local dir="$RESULTS/$2/_warmup/$4-$3-t$5"
  log "  预热 $4 $3 t=$5 ${WARMUP}s"
  jm "$1" "$dir" "$(plan_of "$3")" "$4" "$5" 10 "$WARMUP" "${6:-}" > /dev/null
  s "$1" "{ printf '%s ' '$4-$3-t$5'; grep 'summary =' '$dir/console.log' | tail -1; } >> '$RESULTS/$2/warmups.log'; rm -rf '$dir'; rmdir '$RESULTS/$2/_warmup' 2>/dev/null || true"
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
    s "$gen" "printf 'rows_before=%s\nrows_after=%s\ninserted=%s\n' $before $after $((after - before)) > '$dir/db-rows.txt'"
    log "  入库行数 $before → $after（新增 $((after - before))）"
  fi
  sleep "$COOLDOWN"
}

measure_once() { # $1=预热线程数（0=不预热），其余同 measure；已完成则跳过
  local wt=$1; shift
  if done_run "$1" "$RESULTS/$2/$4-$3-$5-t$6"; then log "  跳过（已完成）$2/$4-$3-$5-t$6"; return 0; fi
  [ "$wt" = 0 ] || warmup "$1" "$2" "$3" "$4" "$wt" "${9:-}"
  measure "$@"
}

main_round() { # $1=轮次
  local r=$1 order spec impl
  [ $((r % 2)) -eq 1 ] && order="jpa mongo" || order="mongo jpa"
  s cdwy3 "mkdir -p '$RESULTS/m$r'"
  log "== 主对比第 $r 轮（顺序：$order）"
  defaults
  for spec in "read 50" "write 100"; do
    set -- $spec
    for impl in $order; do measure_once "$2" cdwy3 "m$r" "$1" "$impl" main "$2"; done
  done
}

journal_rounds() { # $@=轮次
  local r todo=""
  for r in "$@"; do done_run cdwy3 "$RESULTS/m$r/mongoj-write-main-t100" || todo="$todo $r"; done
  if [ -n "$todo" ]; then
    log "== MongoDB j:true 对照（写入 100 线程，轮次$todo）"
    set_env lab4_logmongo LOGDEMO_POOL_MAXSIZE=100
    set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=true
    for r in $todo; do
      s cdwy3 "mkdir -p '$RESULTS/m$r'"
      measure_once 100 cdwy3 "m$r" write mongoj main 100
    done
  else
    log "== MongoDB j:true 对照：已全部完成，跳过"
  fi
  set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=false
}

sweep() {
  local spec op i t order impl
  s cdwy3 "mkdir -p '$RESULTS/sweep'"
  log "== 并发量调优"
  defaults
  for spec in "read 25 75 100 150" "write 25 50 75 150"; do
    set -- $spec; op=$1; shift
    for impl in jpa mongo; do  # 每种实现在本组开始时预热一次（若本组还有未完成的测试）
      for t in "$@"; do
        if ! done_run cdwy3 "$RESULTS/sweep/$impl-$op-sweep-t$t"; then warmup cdwy3 sweep "$op" "$impl" 50; break; fi
      done
    done
    i=0
    for t in "$@"; do
      if [ $((i % 2)) -eq 0 ]; then order="jpa mongo"; else order="mongo jpa"; fi
      i=$((i + 1))
      for impl in $order; do measure_once 0 cdwy3 sweep "$op" "$impl" sweep "$t"; done
    done
  done
}

prepare_cdwy4() { # 把 CDWY3 上的 JDK 与 JMeter 经内网复制到 CDWY4（只做一次），并同步 JMeter 计划与数据
  local v
  if ! s cdwy4 'test -x /opt/apache-jmeter-5.6.3/bin/jmeter && test -x /opt/jdk-21/bin/java'; then
    log "  向 CDWY4 复制 JDK 21 与 JMeter 5.6.3（内网）"
    # CDWY3 上的 /opt/jdk-21 是指向 /opt/java/amazon-corretto-... 的符号链接：链接和实际目录都要复制
    s cdwy3 'tar -czf - -C /opt java jdk-21 apache-jmeter-5.6.3' | s cdwy4 'tar -xzf - -C /opt'
  fi
  s cdwy4 'mkdir -p /root/lab4 && printf "%s\n" "export JAVA_HOME=/opt/jdk-21" "export JMETER_HOME=/opt/apache-jmeter-5.6.3" "export PATH=\$JAVA_HOME/bin:\$JMETER_HOME/bin:\$PATH" > /root/lab4/jmeter-env.sh'
  s cdwy3 'tar -czf - -C /root/lab4 jmeter' | s cdwy4 'rm -rf /root/lab4/jmeter.new && mkdir /root/lab4/jmeter.new && tar -xzf - -C /root/lab4/jmeter.new && rm -rf /root/lab4/jmeter && mv /root/lab4/jmeter.new/jmeter /root/lab4/jmeter && rmdir /root/lab4/jmeter.new'
  v=$(s cdwy4 'source /root/lab4/jmeter-env.sh; HEAP="-Xms128m -Xmx256m" jmeter --version 2>/dev/null | grep -o "5\.[0-9.]*" | head -1' || true)
  log "  CDWY4 JMeter：${v:-不可用}"
  [ -n "$v" ] || { log "!! CDWY4 上的 JMeter 不可用"; return 1; }
}

overload() {
  local op i t order impl dir pending
  log "== 过载与恢复（JMeter 在 CDWY4）"
  defaults
  prepare_cdwy4
  s cdwy4 "mkdir -p '$RESULTS/overload'"
  for op in read write; do
    pending=""
    for impl in jpa mongo; do for t in 600 800 1000; do
      done_run cdwy4 "$RESULTS/overload/$impl-$op-recovery$t-t10" || pending=1
    done; done
    [ -n "$pending" ] || { log "  $op 过载已全部完成，跳过"; continue; }
    for impl in jpa mongo; do warmup cdwy4 overload "$op" "$impl" 50 "$OVERLOAD_HEAP"; done
    i=0
    for t in 600 800 1000; do
      if [ $((i % 2)) -eq 0 ]; then order="jpa mongo"; else order="mongo jpa"; fi
      i=$((i + 1))
      for impl in $order; do
        dir="$RESULTS/overload/$impl-$op-recovery$t-t10"
        if done_run cdwy4 "$dir"; then log "  跳过（已完成）$impl $op 过载 $t + 恢复"; continue; fi
        measure cdwy4 overload "$op" "$impl" overload "$t" 40 "$DURATION" "$OVERLOAD_HEAP"
        # 恢复检查：紧接过载之后 10 线程 60 秒（写入不重置数据，保留过载后的状态）
        log "▶ $impl $op recovery t=10（过载 $t 之后）"
        jm cdwy4 "$dir" "$(plan_of "$op")" "$impl" 10 2 60 "$OVERLOAD_HEAP"
        sleep "$COOLDOWN"
      done
    done
  done
}

pool() { # $1=查询线程 $2=写入线程
  local read_t=$1 write_t=$2 size spec impl todo
  s cdwy3 "mkdir -p '$RESULTS/pool'"
  log "== 连接池调优（查询 $read_t 线程、写入 $write_t 线程）"
  set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=false
  for size in 25 50; do
    todo=""
    for spec in "read $read_t" "write $write_t"; do
      set -- $spec
      for impl in jpa mongo; do done_run cdwy3 "$RESULTS/pool/$impl-$1-pool$size-t$2" || todo=1; done
    done
    [ -n "$todo" ] || { log "  连接池 $size 已全部完成，跳过"; continue; }
    set_env lab4_logjpa "LOGDEMO_POOL_MAXSIZE=$size"
    set_env lab4_logmongo "LOGDEMO_POOL_MAXSIZE=$size"
    for spec in "read $read_t" "write $write_t"; do
      set -- $spec
      for impl in jpa mongo; do measure_once "$2" cdwy3 pool "$1" "$impl" "pool$size" "$2"; done
    done
  done
  defaults
}

pool_auto() {
  local c rt wt
  c=$(s cdwy3 "python3 /root/lab4/tools/choose_pool_threads.py '$RESULTS'")
  rt=$(printf '%s' "$c" | sed -n 's/.*read=\([0-9]*\).*/\1/p'); wt=$(printf '%s' "$c" | sed -n 's/.*write=\([0-9]*\).*/\1/p')
  log "连接池调优的并发量（按规则自动选择，依据见 $RESULTS/pool/choice.txt）：查询 ${rt:-50}、写入 ${wt:-100}"
  pool "${rt:-50}" "${wt:-100}"
}

case "${1:-}" in
  all) main_round 1; main_round 2; main_round 3; journal_rounds 1 2 3; sweep; overload; pool_auto ;;
  main) shift; for r in "$@"; do main_round "$r"; done ;;
  journal) shift; journal_rounds "$@" ;;
  sweep) sweep ;;
  overload) overload ;;
  pool) if [ "${2:-}" = auto ]; then pool_auto; else pool "$2" "$3"; fi ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
reset_db
log "完成：$*"
