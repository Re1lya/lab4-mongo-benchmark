#!/bin/bash
# 实验四服务器端编排用（CDWY4）：内网 SSH，只用专用密钥 lab4_orch_ed25519；测试全部完成后与密钥一起删除。
# 用法：lab-ssh-internal.sh <cdwy1..cdwy5> '<远程命令>'
set -euo pipefail
case "${1:-}" in
  cdwy1) h=172.31.1.202 ;;
  cdwy2) h=172.31.8.46 ;;
  cdwy3) h=172.31.12.156 ;;
  cdwy4) h=172.31.1.19 ;;
  cdwy5) h=172.31.13.151 ;;
  *) echo "未知主机：${1:-}" >&2; exit 2 ;;
esac
shift
exec ssh -F /dev/null -i /root/.ssh/lab4_orch_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
  -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/root/lab4/known_hosts_internal \
  -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=8 "root@$h" "$@"
