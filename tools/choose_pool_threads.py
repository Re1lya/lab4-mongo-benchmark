#!/usr/bin/env python3
"""连接池调优用哪个并发量：按固定规则从并发量调优结果中自动选择（服务器上无人值守时使用）。

规则（组员方案“吞吐接近最高、P95/P99 更低且结果稳定”的量化）：
  1. 每种实现取各档吞吐量的最大值；
  2. 候选档位：两种实现的吞吐量都不低于各自最大值的 95%；
  3. 候选中选两种实现 P95 平均值最小的档位；相同时选线程数较少的。
数据：<结果目录>/sweep 与 <结果目录>/m1（主对比第 1 轮提供 50 线程查询、100 线程写入），统计第 60～240 秒。
逐行流式读取 JTL，只保存区间内的响应时间，内存占用小。兼容 Python 3.6。

用法：python3 choose_pool_threads.py /root/lab4/results   → 输出 read=<线程> write=<线程>，并写 pool/choice.txt
"""
import array
import csv
import math
import os
import re
import sys

W0, W1 = 60000, 240000
NAME = re.compile(r"^(jpa|mongo)-(read|write)-(sweep|main)-t(\d+)$")


def stats(jtl):
    t0 = None
    with open(jtl, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        i_ts = next(r).index("timeStamp")
        for row in r:
            ts = int(row[i_ts])
            t0 = ts if t0 is None or ts < t0 else t0
    vals = array.array("i")
    with open(jtl, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        hdr = next(r)
        i_ts, i_el = hdr.index("timeStamp"), hdr.index("elapsed")
        for row in r:
            dt = int(row[i_ts]) - t0
            if W0 <= dt < W1:
                vals.append(int(row[i_el]))
    s = sorted(vals)
    p95 = s[max(1, int(math.ceil(0.95 * len(s)))) - 1] if s else float("nan")
    return len(s) / ((W1 - W0) / 1000.0), p95


def main():
    root = sys.argv[1]
    data = {}
    for group in ("sweep", "m1"):
        gdir = os.path.join(root, group)
        if not os.path.isdir(gdir):
            continue
        for d in sorted(os.listdir(gdir)):
            m = NAME.match(d)
            jtl = os.path.join(gdir, d, "samples.jtl")
            if m and os.path.exists(os.path.join(gdir, d, "end.txt")) and os.path.exists(jtl):
                data[(m.group(2), m.group(1), int(m.group(4)))] = stats(jtl)
    lines = ["连接池调优并发量的自动选择（统计第 60～240 秒）", "规则：两种实现吞吐量都≥各自最大值的 95% 的档位中，选 P95 平均值最小者", ""]
    choice = {}
    for op in ("read", "write"):
        levels = sorted({t for (o, _, t) in data if o == op})
        best_tps = {i: max(data[(op, i, t)][0] for t in levels if (op, i, t) in data) for i in ("jpa", "mongo")}
        cands = []
        for t in levels:
            if (op, "jpa", t) not in data or (op, "mongo", t) not in data:
                continue
            (tj, pj), (tm, pm) = data[(op, "jpa", t)], data[(op, "mongo", t)]
            ok = tj >= 0.95 * best_tps["jpa"] and tm >= 0.95 * best_tps["mongo"]
            lines.append("%s t=%-4d MySQL %.0f/s P95 %sms | MongoDB %.0f/s P95 %sms %s" % (
                op, t, tj, pj, tm, pm, "候选" if ok else ""))
            if ok:
                cands.append(((pj + pm) / 2.0, t))
        choice[op] = min(cands)[1] if cands else (50 if op == "read" else 100)
        lines.append("%s 选择 %d 线程" % (op, choice[op]))
        lines.append("")
    os.makedirs(os.path.join(root, "pool"), exist_ok=True)
    with open(os.path.join(root, "pool", "choice.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("read=%d write=%d" % (choice["read"], choice["write"]))


if __name__ == "__main__":
    main()
