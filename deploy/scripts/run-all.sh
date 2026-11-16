#!/bin/bash
# 实验四第二阶段：在 CDWY4 上无人值守执行全部测试（客户端可关机）。
# 已完成的测试自动跳过；中途出错则 60 秒后从断点继续，最多 3 次。
# 全部完成后删除本次专用的内网密钥（5 台服务器 authorized_keys 中注释为 lab4-orch-20261116 的那一行，以及 CDWY4 上的密钥文件）。
export LAB_SSH=/root/lab4/lab-ssh-internal.sh
TAG=lab4-orch-20261116
ts() { date '+%m-%d %H:%M:%S'; }
echo "$(ts) 服务器端编排开始（CDWY4，pid $$）"
ok=""
for i in 1 2 3; do
  if bash /root/lab4/repo/deploy/scripts/run-suite-v2.sh all; then ok=1; break; fi
  echo "$(ts) !! 第 $i 次执行中断，60 秒后从断点继续"
  sleep 60
done
if [ -z "$ok" ]; then echo "$(ts) SUITE-FAILED（保留内网密钥，等待人工处理）"; exit 1; fi
for h in cdwy1 cdwy2 cdwy3 cdwy5; do
  n=$("$LAB_SSH" "$h" "sed -i '/ $TAG\$/d' /root/.ssh/authorized_keys; grep -c ' $TAG\$' /root/.ssh/authorized_keys" 2>/dev/null)
  echo "$(ts)   $h 剩余专用密钥行：${n:-?}"
done
sed -i "/ $TAG\$/d" /root/.ssh/authorized_keys
rm -f /root/.ssh/lab4_orch_ed25519 /root/.ssh/lab4_orch_ed25519.pub
echo "$(ts)   cdwy4 剩余专用密钥行：$(grep -c " $TAG\$" /root/.ssh/authorized_keys)"
echo "$(ts) SUITE-DONE（内网专用密钥已删除）"
