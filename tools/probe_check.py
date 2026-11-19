#!/usr/bin/env python3
"""“最多同时运行线程数”逐级加压的判定（在压测机上运行，兼容 Python 3.6，逐行读取 JTL）。

  python3 probe_check.py <测试目录> <设定线程数>
      输出一行：t=… max_threads=… samples=… errors=… window_s=… tps=… avg_ms=… gap_ms=… pass=0|1
      通过条件：测试正常结束；JMeter 的活跃线程数达到设定值（全部线程同时在运行）；零错误；
      全部线程同时运行的时段不少于 30 秒；压测机自检正常（线程数 ÷ 吞吐量 − 平均响应时间 < 5 ms，
      即 JMeter 自身没有成为瓶颈）。
  python3 probe_check.py --choose <probe 目录>
      读 probe.log，每种操作取两种实现都通过的最高一级，写入 choice.txt（read=… / write=…）。
"""
import csv
import gzip
import os
import re
import sys

MAX_GAP_MS = 5.0
MIN_WINDOW_S = 30.0


def open_jtl(run_dir):
    p = os.path.join(run_dir, "samples.jtl")
    if os.path.exists(p):
        return open(p, newline="", encoding="utf-8")
    return gzip.open(p + ".gz", "rt", newline="", encoding="utf-8")


def check(run_dir, t):
    if not os.path.exists(os.path.join(run_dir, "end.txt")):
        return "t=%d pass=0 (测试没有正常结束)" % t
    max_threads, first, last = 0, None, None
    with open_jtl(run_dir) as f:
        r = csv.reader(f)
        h = next(r)
        i_ts, i_all = h.index("timeStamp"), h.index("allThreads")
        for row in r:
            n = int(row[i_all])
            max_threads = max(max_threads, n)
            if n >= t:
                ts = int(row[i_ts])
                first = ts if first is None else first
                last = ts
    samples = errors = 0
    total_el = 0
    in_win = 0
    with open_jtl(run_dir) as f:
        r = csv.reader(f)
        h = next(r)
        i_ts, i_el, i_ok = h.index("timeStamp"), h.index("elapsed"), h.index("success")
        for row in r:
            samples += 1
            if row[i_ok] != "true":
                errors += 1
            ts = int(row[i_ts])
            if first is not None and first <= ts <= last:
                in_win += 1
                total_el += int(row[i_el])
    window_s = (last - first) / 1000.0 if first is not None else 0.0
    tps = in_win / window_s if window_s > 0 else 0.0
    avg = total_el / in_win if in_win else float("nan")
    gap = t / tps * 1000 - avg if tps > 0 else float("nan")
    ok = (max_threads >= t and errors == 0 and window_s >= MIN_WINDOW_S and gap == gap and gap < MAX_GAP_MS)
    return "t=%d max_threads=%d samples=%d errors=%d window_s=%.0f tps=%.1f avg_ms=%.1f gap_ms=%.2f pass=%d" % (
        t, max_threads, samples, errors, window_s, tps, avg, gap, 1 if ok else 0)


def choose(probe_dir):
    best = {}
    for line in open(os.path.join(probe_dir, "probe.log"), encoding="utf-8"):
        m = re.match(r"(\w+) (read|write) t=(\d+) .*pass=([01])", line.strip())
        if m and m.group(4) == "1":
            k = (m.group(2), m.group(1))
            best[k] = max(best.get(k, 0), int(m.group(3)))
    out = []
    for op in ("read", "write"):
        vals = [best.get((op, i), 0) for i in ("jpa", "mongo")]
        out.append("%s=%d" % (op, min(vals) if min(vals) > 0 else 400))
    with open(os.path.join(probe_dir, "choice.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(" ".join(out), "（每种操作取两种实现都通过的最高一级；MySQL/MongoDB 各自最高：%s）" % (
        ", ".join("%s %s=%d" % (op, i, best.get((op, i), 0)) for op in ("read", "write") for i in ("jpa", "mongo"))))


if __name__ == "__main__":
    if sys.argv[1] == "--choose":
        choose(sys.argv[2])
    else:
        print(check(sys.argv[1], int(sys.argv[2])))
