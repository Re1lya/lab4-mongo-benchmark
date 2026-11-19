#!/usr/bin/env python3
"""实验四 JTL 统计：每次测试一行，输出 CSV 和 Markdown 表。

目录约定（run-suite.sh 生成）：<轮次目录>/<实现>-<读写>-<阶段>-t<线程数>/samples.jtl(.gz)、params.txt、
db-rows.txt（写测试）。

统计区间（列名前缀 steady_）：
  持续时间 ≥ 240 秒的测试：固定取开始后第 60～240 秒（--fixed-window，排除升压和前期波动）；
  其他测试（第 1 轮 60 秒测试、恢复检查）：活跃线程数 grpThreads 等于设定线程数的时间段（所有线程都在发请求）。
  另给出“全程”口径：JTL 中全部样本（含升压、降压）。
测试名：<实现>-<读写>-<阶段>-t<线程数>，实现 jpa=MySQL 版，mongo=MongoDB 版，mongoj=MongoDB 版且写关注 j:true。
写测试另核对：成功（HTTP 201）请求数 == 数据库新增行数。

用法：python3 tools/analyze_jtl.py <轮次目录> --out <输出目录>
"""
import argparse
import csv
import gzip
import math
import os
import re
import sys
from collections import Counter

NAME_RE = re.compile(r"^(jpa|mongo|mongoj)-(read|write)-(warmup|load|stress|recovery\d*|main|sweep|overload|pool\d+|probe|maxload)-t(\d+)$")
PHASE_ORDER = {"warmup": 0, "load": 1, "main": 1, "sweep": 1, "probe": 2, "stress": 2, "overload": 2, "maxload": 2, "recovery": 3}
FIXED_WINDOW = None  # (起点秒, 终点秒)，由 --fixed-window 设置


def phase_order(phase):
    if phase.startswith("recovery"):
        return 3  # recovery600 等：过载 600 线程之后的恢复检查
    return PHASE_ORDER.get(phase, 1)


def run_duration(run_dir):
    try:
        for line in open(os.path.join(run_dir, "params.txt"), encoding="utf-8"):
            if line.startswith("duration="):
                return int(line.split("=", 1)[1])
    except (OSError, ValueError):
        pass
    return None


def percentile(sorted_values, p):
    """最近秩法（与 JMeter 报告相同的取法）：第 ceil(p/100*n) 个值。"""
    if not sorted_values:
        return float("nan")
    k = max(1, int(math.ceil(p / 100.0 * len(sorted_values))))
    return sorted_values[k - 1]


def stats(samples, window_ms):
    elapsed = sorted(s["elapsed"] for s in samples)
    n = len(samples)
    errors = sum(1 for s in samples if not s["success"])
    tps = n / (window_ms / 1000.0) if window_ms > 0 else float("nan")
    threads = sum(s["grp"] for s in samples) / n if n else float("nan")
    avg = sum(elapsed) / n if n else float("nan")
    return {
        "samples": n,
        "errors": errors,
        "error_pct": round(100.0 * errors / n, 3) if n else float("nan"),
        "throughput": round(n / (window_ms / 1000.0), 1) if window_ms > 0 else float("nan"),
        "avg_ms": round(sum(elapsed) / n, 2) if n else float("nan"),
        "p50_ms": percentile(elapsed, 50),
        "p90_ms": percentile(elapsed, 90),
        "p95_ms": percentile(elapsed, 95),
        "p99_ms": percentile(elapsed, 99),
        "max_ms": elapsed[-1] if elapsed else float("nan"),
        "window_s": round(window_ms / 1000.0, 1),
        # 压测机自检：线程数 ÷ 吞吐量 = 每个线程发一次请求的周期，减去平均响应时间就是 JMeter 自身在两次请求之间花的时间。
        # 正常时远小于 1 ms；明显变大说明压测机（CPU 等）成了瓶颈，结果不能代表被测系统。
        "threads_avg": round(threads, 1),
        "client_gap_ms": round(threads / tps * 1000 - avg, 2) if n and tps > 0 else float("nan"),
        "bytes_avg": round(sum(s["bytes"] for s in samples) / n) if n else float("nan"),  # 平均响应大小（字节）
    }


def open_jtl(run_dir):
    """优先读 samples.jtl，没有则读仓库中保存的 samples.jtl.gz。"""
    path = os.path.join(run_dir, "samples.jtl")
    if os.path.exists(path):
        return open(path, newline="", encoding="utf-8")
    return gzip.open(path + ".gz", "rt", newline="", encoding="utf-8")


def has_jtl(run_dir):
    return any(os.path.exists(os.path.join(run_dir, n)) for n in ("samples.jtl", "samples.jtl.gz"))


def load_samples(run_dir):
    out = []
    with open_jtl(run_dir) as f:
        for row in csv.DictReader(f):
            out.append({
                "ts": int(row["timeStamp"]),
                "elapsed": int(row["elapsed"]),
                "code": row["responseCode"],
                "success": row["success"] == "true",
                "message": row.get("failureMessage", "") or "",
                "grp": int(row["grpThreads"]),
                "bytes": int(row.get("bytes") or 0),
            })
    return out


def analyze_run(run_dir, name):
    m = NAME_RE.match(name)
    impl, op, phase, threads = m.group(1), m.group(2), m.group(3), int(m.group(4))
    samples = load_samples(run_dir)
    if not samples:
        return None
    t0 = min(s["ts"] for s in samples)
    t1 = max(s["ts"] for s in samples)
    full = stats(samples, t1 - t0)
    duration = run_duration(run_dir)
    if FIXED_WINDOW and duration is not None and duration >= FIXED_WINDOW[1]:
        s0, s1 = t0 + FIXED_WINDOW[0] * 1000, t0 + FIXED_WINDOW[1] * 1000
        window_name = "%d-%ds" % FIXED_WINDOW
        steady = stats([s for s in samples if s0 <= s["ts"] < s1], s1 - s0)
    else:
        window_name = "all-threads-active"
        steady_samples = [s for s in samples if s["grp"] == threads]
        if steady_samples:
            s0 = min(s["ts"] for s in steady_samples)
            s1 = max(s["ts"] for s in steady_samples)
            steady = stats([s for s in samples if s0 <= s["ts"] <= s1], s1 - s0)
        else:
            s0 = s1 = None
            steady = {k: float("nan") for k in full}
    codes = Counter(s["code"] for s in samples)
    failures = Counter(s["message"][:80] for s in samples if not s["success"])
    row = {"impl": impl, "op": op, "phase": phase, "threads": threads,
           "start_ms": t0, "end_ms": t1, "stat_window": window_name, "steady_start_ms": s0, "steady_end_ms": s1,
           "max_threads": max(s["grp"] for s in samples)}  # JMeter 同时运行的线程数最大值
    row.update({"full_" + k: v for k, v in full.items()})
    row.update({"steady_" + k: v for k, v in steady.items()})
    row["response_codes"] = " ".join("%s:%d" % kv for kv in sorted(codes.items()))
    row["top_failure"] = failures.most_common(1)[0][0] if failures else ""

    # 写测试：成功请求数与数据库新增行数核对
    rows_file = os.path.join(run_dir, "db-rows.txt")
    if op == "write" and os.path.exists(rows_file):
        kv = dict(line.strip().split("=", 1) for line in open(rows_file) if "=" in line)
        inserted = int(kv.get("inserted", "0") or 0)
        ok_201 = codes.get("201", 0)
        row["db_inserted"] = inserted
        row["db_check"] = "一致" if inserted == ok_201 else "不一致(%d vs %d)" % (inserted, ok_201)
    else:
        row["db_inserted"] = ""
        row["db_check"] = ""

    return row


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("round_dir")
    p.add_argument("--out", required=True)
    p.add_argument("--name", default=None, help="输出文件名前缀，默认用轮次目录名")
    p.add_argument("--fixed-window", default=None, help="如 60:240：持续时间不少于终点的测试固定统计这一区间（秒）")
    args = p.parse_args()
    global FIXED_WINDOW
    if args.fixed_window:
        a, b = args.fixed_window.split(":")
        FIXED_WINDOW = (int(a), int(b))
    name = args.name or os.path.basename(os.path.normpath(args.round_dir))
    rows = []
    for d in sorted(os.listdir(args.round_dir)):
        full_dir = os.path.join(args.round_dir, d)
        if os.path.isdir(full_dir) and NAME_RE.match(d) and has_jtl(full_dir):
            r = analyze_run(full_dir, d)
            if r:
                rows.append(r)
                print("analyzed %-28s samples=%-7d steady tps=%-8s p95=%s" % (
                    d, r["full_samples"], r["steady_throughput"], r["steady_p95_ms"]), file=sys.stderr)
    rows.sort(key=lambda r: (r["op"], phase_order(r["phase"]), r["phase"], r["threads"], r["impl"]))
    os.makedirs(args.out, exist_ok=True)
    fields = list(rows[0].keys())
    with open(os.path.join(args.out, "jtl-summary-%s.csv" % name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = ["# JTL 统计（%s）" % name, "",
             "统计区间：240 秒测试取第 60～240 秒，其余取所有线程都在运行的时段；全程 = 含升压/降压的全部样本。时间单位毫秒。", ""]
    for op, title in (("read", "查询 GET /api/logs"), ("write", "写入 POST /api/logs")):
        lines += ["## " + title, "",
                  "| 阶段 | 线程 | 实现 | 区间吞吐(次/秒) | 平均(ms) | P50 | P90 | P95 | P99 | 最大 | 错误率 | 全程样本 | 入库核对 |",
                  "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
        for r in rows:
            if r["op"] != op:
                continue
            lines.append("| {phase} | {threads} | {impl} | {steady_throughput} | {steady_avg_ms} | {steady_p50_ms} | "
                         "{steady_p90_ms} | {steady_p95_ms} | {steady_p99_ms} | {steady_max_ms} | {full_error_pct}% | "
                         "{full_samples} | {db_check} |".format(**r))
        lines.append("")
    with open(os.path.join(args.out, "jtl-summary-%s.md" % name), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote %d runs to %s" % (len(rows), args.out), file=sys.stderr)


if __name__ == "__main__":
    main()
