#!/bin/bash
# 实验四第三阶段测试编排（11-19，Prometheus 按老师的新要求：每 1 秒采集、每 2 秒计算，CPU 使用率取 2 秒平均）：
# 重测主对比 3 轮与 MongoDB j:true，借鉴其他组的做法先找“最多同时运行的线程数”，再在该线程数下持续压测 3 轮。
# 与第二阶段相比：JMeter 全部在 CDWY3（rbac 已暂停，内存够用）；每项测试前都把两个数据库重置为同一份 10 万条预置数据（查询也重置）。
# LAB_SSH 用法：$LAB_SSH <cdwy1..cdwy5> '<远程命令>'。
#
#   bash run-suite-v3.sh all                  依次执行下面全部（可重复执行：已完成的测试自动跳过）
#   bash run-suite-v3.sh short                约 2 小时方案（11-19 实际执行）：main 1、journal 1、probe、maxload 1
#   bash run-suite-v3.sh main <轮次...>       主对比：查询 50、写入 100 线程，升压 20 秒、持续 240 秒，统计第 60～240 秒（结果目录 n<轮次>）
#   bash run-suite-v3.sh journal <轮次...>    MongoDB 改为 j:true 后写入 100 线程（结果放入对应的 n<轮次>）
#   bash run-suite-v3.sh probe                最多同时运行线程数：400/800/1200/1600/2000 线程逐级加压，
#                                             全部线程同时运行、零错误、压测机自检正常才算通过；某一级不通过就停止
#   bash run-suite-v3.sh maxload <轮次...>    在 probe 选出的线程数下持续压测 240 秒（统计第 60～240 秒），
#                                             之后间隔 30 秒做 10 线程 60 秒恢复检查（结果目录 x<轮次>）
set -euo pipefail
: "${LAB_SSH:?请设置 LAB_SSH（SSH 辅助命令）}"
APP_HOST=172.31.1.202
GEN=cdwy3
RESULTS=${RESULTS:-/root/lab4/results}
RAMP=${RAMP:-20}; DURATION=${DURATION:-240}; WARMUP=${WARMUP:-120}; COOLDOWN=${COOLDOWN:-30}
PROBE_LEVELS=${PROBE_LEVELS:-"400 800 1200 1600 2000"}
# 试运行时可缩短：PROBE_HOLD（每级全部线程同时运行的秒数）、SHORT_WARMUP（probe/maxload 的预热秒数）、RECOVERY（恢复检查秒数）
PROBE_HOLD=${PROBE_HOLD:-90}; SHORT_WARMUP=${SHORT_WARMUP:-60}; RECOVERY=${RECOVERY:-60}
BIG_HEAP='-Xms512m -Xmx768m -XX:MaxMetaspaceSize=128m'

s() { "$LAB_SSH" "$@" 2>/dev/null; }
log() { printf '%s %s\n' "$(date '+%m-%d %H:%M:%S')" "$*"; }
port_of() { [ "$1" = jpa ] && echo 8081 || echo 8082; }
plan_of() { [ "$1" = read ] && echo ReadLog || echo WriteLog; }
JENV='source /etc/profile.d/lab3-tools.sh'

done_run() { s "$GEN" "test -s '$1/end.txt' && test -s '$1/samples.jtl'"; }

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

set_env() { # $1=service $2=VAR=value → 已是该值则不重启
  local cur
  cur=$(s cdwy1 "docker service inspect $1 --format '{{range .Spec.TaskTemplate.ContainerSpec.Env}}{{println .}}{{end}}'" | grep -x "$2" || true)
  [ -n "$cur" ] && return 0
  s cdwy1 "docker service update --quiet --env-add $2 $1 >/dev/null 2>&1"
  wait_health "$([ "$1" = lab4_logjpa ] && echo 8081 || echo 8082)"
  log "  $1 已设置 $2：$(s cdwy1 "docker logs \$(docker ps -q --filter name=$1 | head -1) 2>&1 | grep -o 'logdemo-[a-z]* settings.*' | tail -1")"
}

defaults() {
  set_env lab4_logjpa LOGDEMO_POOL_MAXSIZE=100
  set_env lab4_logmongo LOGDEMO_POOL_MAXSIZE=100
  set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=false
}

jm() { # $1=输出目录 $2=plan $3=impl $4=线程 $5=升压 $6=持续 [$7=JMETER_HEAP]
  local heap=${7:-}
  s "$GEN" "$JENV; ${heap:+JMETER_HEAP='$heap'} bash /root/lab4/jmeter/run-test.sh $2 $APP_HOST $(port_of "$3") $4 $5 $6 '$1'" | sed 's/^/    /'
}

warmup() { # $1=组 $2=op $3=impl $4=线程 $5=秒数 [$6=heap]
  local dir="$RESULTS/$1/_warmup/$3-$2-t$4"
  log "  预热 $3 $2 t=$4 ${5}s"
  jm "$dir" "$(plan_of "$2")" "$3" "$4" 10 "$5" "${6:-}" > /dev/null || true
  s "$GEN" "{ printf '%s ' '$3-$2-t$4'; grep 'summary =' '$dir/console.log' | tail -1; } >> '$RESULTS/$1/warmups.log'; rm -rf '$dir'; rmdir '$RESULTS/$1/_warmup' 2>/dev/null || true"
}

measure() { # $1=组 $2=op $3=impl $4=阶段 $5=线程 $6=升压 $7=持续 [$8=heap] → 测前重置数据库；写入测试核对入库行数
  local dir="$RESULTS/$1/$3-$2-$4-t$5" before after
  reset_db
  [ "$2" = write ] && before=$(count_rows "$3")
  log "▶ $3 $2 $4 t=$5（升压 ${6}s，持续 ${7}s）"
  jm "$dir" "$(plan_of "$2")" "$3" "$5" "$6" "$7" "${8:-}"
  if [ "$2" = write ]; then
    after=$(count_rows "$3"); before=${before:-0}; after=${after:-0}
    s "$GEN" "printf 'rows_before=%s\nrows_after=%s\ninserted=%s\n' $before $after $((after - before)) > '$dir/db-rows.txt'"
    log "  入库行数 $before → $after（新增 $((after - before))）"
  fi
}

main_round() { # $1=轮次
  local r=$1 order spec impl
  [ $((r % 2)) -eq 1 ] && order="jpa mongo" || order="mongo jpa"
  s "$GEN" "mkdir -p '$RESULTS/n$r'"
  log "== 主对比第 $r 轮（顺序：$order）"
  defaults
  for spec in "read 50" "write 100"; do
    set -- $spec
    for impl in $order; do
      if done_run "$RESULTS/n$r/$impl-$1-main-t$2"; then log "  跳过（已完成）n$r/$impl-$1-main-t$2"; continue; fi
      warmup "n$r" "$1" "$impl" "$2" "$WARMUP"; sleep 10
      measure "n$r" "$1" "$impl" main "$2" "$RAMP" "$DURATION"; sleep "$COOLDOWN"
    done
  done
}

journal_rounds() {
  local r todo=""
  for r in "$@"; do done_run "$RESULTS/n$r/mongoj-write-main-t100" || todo="$todo $r"; done
  if [ -n "$todo" ]; then
    log "== MongoDB j:true（写入 100 线程，轮次$todo）"
    set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=true
    for r in $todo; do
      s "$GEN" "mkdir -p '$RESULTS/n$r'"
      warmup "n$r" write mongoj 100 "$WARMUP"; sleep 10
      measure "n$r" write mongoj main 100 "$RAMP" "$DURATION"; sleep "$COOLDOWN"
    done
  fi
  set_env lab4_logmongo LOGDEMO_MONGO_JOURNAL=false
}

probe_ramp() { echo $(( $1 / 20 )); }   # 每秒启动 20 个线程

probe() {
  local op impl t ramp dir line choice=""
  s "$GEN" "mkdir -p '$RESULTS/probe'"
  log "== 最多同时运行线程数（逐级：$PROBE_LEVELS）"
  defaults
  for op in read write; do
    for impl in jpa mongo; do
      warmup probe "$op" "$impl" 50 "$SHORT_WARMUP" "$BIG_HEAP"; sleep 10
      for t in $PROBE_LEVELS; do
        dir="$RESULTS/probe/$impl-$op-probe-t$t"
        if ! done_run "$dir"; then
          ramp=$(probe_ramp "$t")
          measure probe "$op" "$impl" probe "$t" "$ramp" $((ramp + PROBE_HOLD)) "$BIG_HEAP" || true
          sleep 20
        fi
        line=$(s "$GEN" "python3 /root/lab4/tools/probe_check.py '$dir' $t" || echo "t=$t pass=0 (无结果)")
        log "  $impl $op $line"
        s "$GEN" "echo '$impl $op $line' >> '$RESULTS/probe/probe.log'"
        case "$line" in *pass=1*) ;; *) break ;; esac
      done
    done
  done
  # 每种操作取两种实现都通过的最高一级，写入 probe/choice.txt（maxload 读取）
  s "$GEN" "python3 /root/lab4/tools/probe_check.py --choose '$RESULTS/probe'" | sed 's/^/  /'
}

maxload() { # $@=轮次
  local r op t ramp order impl dir
  s "$GEN" "test -s '$RESULTS/probe/choice.txt'" || { log "!! 缺少 probe/choice.txt，先执行 probe"; return 1; }
  defaults
  for r in "$@"; do
    [ $((r % 2)) -eq 1 ] && order="jpa mongo" || order="mongo jpa"
    s "$GEN" "mkdir -p '$RESULTS/x$r'"
    log "== 最多线程数下持续压测第 $r 轮（顺序：$order）"
    for op in read write; do
      t=$(s "$GEN" "sed -n 's/^$op=//p' '$RESULTS/probe/choice.txt'")
      ramp=$(probe_ramp "$t"); [ "$ramp" -gt 60 ] && ramp=60
      for impl in $order; do
        dir="$RESULTS/x$r/$impl-$op-recovery-t10"
        if done_run "$dir"; then log "  跳过（已完成）x$r/$impl-$op 持续压测 + 恢复"; continue; fi
        warmup "x$r" "$op" "$impl" 50 "$SHORT_WARMUP" "$BIG_HEAP"; sleep 10
        measure "x$r" "$op" "$impl" maxload "$t" "$ramp" "$DURATION" "$BIG_HEAP"
        sleep "$COOLDOWN"
        log "▶ $impl $op recovery t=10（持续压测 $t 之后）"
        jm "$dir" "$(plan_of "$op")" "$impl" 10 2 "$RECOVERY" "$BIG_HEAP"
        sleep "$COOLDOWN"
      done
    done
  done
}

case "${1:-}" in
  all) main_round 1; main_round 2; main_round 3; journal_rounds 1 2 3; probe; maxload 1 2 3 ;;
  short) main_round 1; journal_rounds 1; probe; maxload 1 ;;   # 11-19 采用的约 2 小时方案
  main) shift; for r in "$@"; do main_round "$r"; done ;;
  journal) shift; journal_rounds "$@" ;;
  probe) probe ;;
  maxload) shift; maxload "$@" ;;
  *) sed -n '2,17p' "$0"; exit 2 ;;
esac
reset_db
log "完成：$*"
