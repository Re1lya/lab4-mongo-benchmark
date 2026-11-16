#!/usr/bin/env python3
"""把 Prometheus 导出的监控数据（deploy/scripts/prom-export.sh 生成）按每次测试的稳态时间段汇总。

输入：promtool tsdb dump 文本（.gz）+ analyze_jtl.py 生成的 jtl-summary-<轮次>.csv（提供每次测试的稳态起止时间）。
输出：
  prom-summary-<轮次>.csv / .md  每次测试一行：各服务器 CPU、内存、磁盘，应用 JVM/线程/连接池，服务端请求数核对；
  <轮次目录>/<测试名>/monitor.json  该次测试的监控时间序列（每 2 秒一个点），便于画图和复核。

用法：python3 tools/analyze_prom.py <dump.txt.gz> <jtl-summary.csv> <轮次目录> --out <输出目录>
"""
import argparse
import csv
import gzip
import json
import os
import re
from collections import defaultdict

LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')
HOSTS = {
    "172.31.1.202:9100": "CDWY1",   # 服务器 E：两套日志服务
    "172.31.8.46:9100": "CDWY2",    # 服务器 B：MySQL
    "172.31.12.156:9100": "CDWY3",  # 服务器 A：JMeter
    "172.31.1.19:9100": "CDWY4",    # 服务器 D：Prometheus（过载实验时兼作压测机）
    "172.31.13.151:9100": "CDWY5",  # 服务器 C：MongoDB
}
JOB = {"jpa": "lab4-logjpa", "mongo": "lab4-logmongo", "mongoj": "lab4-logmongo"}  # mongoj = MongoDB 版且 j:true
CORES = 2  # 5 台服务器都是 2 核


def parse_dump(path):
    series = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("{"):
                continue
            close = line.rindex("}")
            labels = dict(LABEL_RE.findall(line[1:close]))
            parts = line[close + 1:].split()
            name = labels.pop("__name__")
            series[(name, tuple(sorted(labels.items())))].append((int(parts[1]), float(parts[0])))
    for pts in series.values():
        pts.sort()
    return series


def select(series, name, **match):
    out = []
    for (n, labels), pts in series.items():
        if n != name:
            continue
        d = dict(labels)
        if all((d.get(k) == v) if not v.startswith("~") else re.fullmatch(v[1:], d.get(k, "")) for k, v in match.items()):
            out.append((d, pts))
    return out


def merged(series, name, **match):
    """同一指标的所有序列合并为一组点。Mongo 驱动指标带 cluster_id 标签，服务每重启一次换一个值，会拆成多条序列。"""
    pts = []
    for _, p in select(series, name, **match):
        pts.extend(p)
    return sorted(pts)


def window(pts, t0, t1):
    return [(t, v) for t, v in pts if t0 <= t <= t1]


def increase(pts, t0, t1):
    """计数器在 [t0,t1] 内的增量（处理计数器重置）。"""
    return increase_span(pts, t0, t1)[0]


def increase_span(pts, t0, t1):
    """返回（增量，覆盖秒数）。增量只覆盖窗口内第一个到最后一个样本之间，算速率时要除以这段时长，
    不能除以整个窗口长度（否则会因 2 秒抓取间隔的边界而偏低几个百分点）。"""
    w = window(pts, t0, t1)
    inc = 0.0
    for (_, a), (_, b) in zip(w, w[1:]):
        inc += b - a if b >= a else b
    span = (w[-1][0] - w[0][0]) / 1000.0 if len(w) >= 2 else 0.0
    return inc, span


def rate(pts, t0, t1):
    inc, span = increase_span(pts, t0, t1)
    return inc / span if span > 0 else None


def gauge_stats(pts, t0, t1):
    vals = [v for _, v in window(pts, t0, t1)]
    if not vals:
        return None, None
    return sum(vals) / len(vals), max(vals)


def host_cpu(series, host, t0, t1):
    total = idle = iowait = 0.0
    for d, pts in select(series, "node_cpu_seconds_total", instance=host):
        inc = increase(pts, t0, t1)
        total += inc
        if d.get("mode") == "idle":
            idle += inc
        elif d.get("mode") == "iowait":
            iowait += inc
    if total <= 0:
        return None, None
    return round(100 * (1 - (idle + iowait) / total), 1), round(100 * iowait / total, 1)


def cpu_timeseries(series, host, t0, t1):
    """每个抓取间隔的 CPU 使用率（%）。"""
    per_ts = defaultdict(lambda: [0.0, 0.0])  # ts -> [total, idle+iowait] 增量
    for d, pts in select(series, "node_cpu_seconds_total", instance=host):
        w = window(pts, t0 - 5000, t1)
        for (ta, a), (tb, b) in zip(w, w[1:]):
            inc = b - a if b >= a else b
            per_ts[tb][0] += inc
            if d.get("mode") in ("idle", "iowait"):
                per_ts[tb][1] += inc
    return [[t, round(100 * (1 - i / tot), 1)] for t, (tot, i) in sorted(per_ts.items()) if tot > 0 and t >= t0]


def summarize_run(series, run):
    impl, t0, t1 = run["impl"], int(run["steady_start_ms"]), int(run["steady_end_ms"])
    secs = (t1 - t0) / 1000.0
    job = JOB[impl]
    row = {k: run[k] for k in ("impl", "op", "phase", "threads")}
    row["steady_s"] = round(secs, 1)
    for host, name in HOSTS.items():  # CDWY4 在过载实验中兼作压测机
        busy, iow = host_cpu(series, host, t0, t1)
        row[name + "_cpu_pct"] = busy
        row[name + "_iowait_pct"] = iow
        mem = select(series, "node_memory_MemAvailable_bytes", instance=host)
        row[name + "_mem_avail_min_mb"] = round(min(v for _, v in window(mem[0][1], t0, t1)) / 1048576) if mem and window(mem[0][1], t0, t1) else None
    for name in ("CDWY2", "CDWY5"):  # 数据库服务器的磁盘写入
        host = [h for h, n in HOSTS.items() if n == name][0]
        wb = select(series, "node_disk_written_bytes_total", instance=host, device="vda")
        wc = select(series, "node_disk_writes_completed_total", instance=host, device="vda")
        io = select(series, "node_disk_io_time_seconds_total", instance=host, device="vda")
        row[name + "_disk_write_mb_s"] = round(rate(wb[0][1], t0, t1) / 1048576, 2) if wb else None
        row[name + "_disk_write_iops"] = round(rate(wc[0][1], t0, t1), 1) if wc else None
        row[name + "_disk_util_pct"] = round(100 * rate(io[0][1], t0, t1), 1) if io else None
    # 应用（JVM）指标
    pc_avg, _ = gauge_stats(merged(series, "process_cpu_usage", job=job), t0, t1)
    row["app_process_cpu_pct"] = round(100 * pc_avg, 1) if pc_avg is not None else None
    _, th_max = gauge_stats(merged(series, "jvm_threads_live_threads", job=job), t0, t1)
    row["app_live_threads_max"] = int(th_max) if th_max is not None else None
    heap_by_ts = defaultdict(float)
    for d, pts in select(series, "jvm_memory_used_bytes", job=job, area="heap"):
        for t, v in window(pts, t0, t1):
            heap_by_ts[t] += v
    row["app_heap_used_max_mb"] = round(max(heap_by_ts.values()) / 1048576) if heap_by_ts else None
    gc = sum(rate(p, t0, t1) or 0 for _, p in select(series, "jvm_gc_pause_seconds_sum", job=job))
    row["app_gc_pause_pct"] = round(100 * gc, 2)
    if impl == "jpa":
        act = merged(series, "hikaricp_connections_active", job=job)
        pend = merged(series, "hikaricp_connections_pending", job=job)
    else:
        act = merged(series, "mongodb_driver_pool_checkedout", job=job)
        pend = merged(series, "mongodb_driver_pool_waitqueuesize", job=job)
    avg, mx = gauge_stats(act, t0, t1)
    row["pool_in_use_avg"] = round(avg, 1) if avg is not None else None
    row["pool_in_use_max"] = mx
    row["pool_waiting_max"] = gauge_stats(pend, t0, t1)[1]
    # 服务端视角的请求数与平均处理时间（与 JMeter 客户端结果核对）
    method = "GET" if run["op"] == "read" else "POST"
    cnt = select(series, "http_server_requests_seconds_count", job=job, uri="/api/logs", method=method)
    sm = select(series, "http_server_requests_seconds_sum", job=job, uri="/api/logs", method=method)
    c = sum(increase(p, t0, t1) for _, p in cnt)
    s = sum(increase(p, t0, t1) for _, p in sm)
    tps = sum(rate(p, t0, t1) or 0 for _, p in cnt)
    row["server_tps"] = round(tps, 1) if tps else None
    row["server_avg_ms"] = round(1000 * s / c, 2) if c else None
    # 每个请求消耗的 CPU 时间（毫秒）= 核数 × 使用率 ÷ 每秒请求数；比较两种实现在各层的开销
    db = "CDWY2" if impl == "jpa" else "CDWY5"
    if tps:
        row["app_host_cpu_ms_per_req"] = round(CORES * row["CDWY1_cpu_pct"] / 100 * 1000 / tps, 3)
        row["db_host_cpu_ms_per_req"] = round(CORES * row[db + "_cpu_pct"] / 100 * 1000 / tps, 3)
    return row


def timeseries(series, run):
    impl, t0, t1 = run["impl"], int(run["start_ms"]), int(run["end_ms"])
    job = JOB[impl]
    out = {"run": "%s-%s-%s-t%s" % (impl, run["op"], run["phase"], run["threads"]),
           "window_utc_ms": [t0, t1], "steady_utc_ms": [int(run["steady_start_ms"]), int(run["steady_end_ms"])],
           "note": "cpu_pct 为每个抓取间隔（2 秒）的整机 CPU 使用率；其余为 Prometheus 原始样本", "series": {}}
    for host, name in HOSTS.items():
        out["series"][name + "_cpu_pct"] = cpu_timeseries(series, host, t0, t1)
    for metric, key in (("process_cpu_usage", "app_process_cpu"), ("jvm_threads_live_threads", "app_live_threads"),
                        ("hikaricp_connections_active" if impl == "jpa" else "mongodb_driver_pool_checkedout", "pool_in_use"),
                        ("hikaricp_connections_pending" if impl == "jpa" else "mongodb_driver_pool_waitqueuesize", "pool_waiting")):
        pts = merged(series, metric, job=job)
        if pts:
            out["series"][key] = [[t, v] for t, v in window(pts, t0, t1)]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dump")
    p.add_argument("jtl_summary")
    p.add_argument("round_dir")
    p.add_argument("--out", required=True)
    p.add_argument("--name", required=True)
    args = p.parse_args()
    series = parse_dump(args.dump)
    runs = list(csv.DictReader(open(args.jtl_summary, encoding="utf-8")))
    rows = []
    for run in runs:
        if not run["steady_start_ms"]:
            continue
        rows.append(summarize_run(series, run))
        run_dir = os.path.join(args.round_dir, "%s-%s-%s-t%s" % (run["impl"], run["op"], run["phase"], run["threads"]))
        if os.path.isdir(run_dir):
            with open(os.path.join(run_dir, "monitor.json"), "w", encoding="utf-8") as f:
                json.dump(timeseries(series, run), f, ensure_ascii=False)
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with open(os.path.join(args.out, "prom-summary-%s.csv" % args.name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("wrote %d runs" % len(rows))


if __name__ == "__main__":
    main()
