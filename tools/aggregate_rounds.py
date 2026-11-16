#!/usr/bin/env python3
"""主对比多轮汇总：同一组测试（实现、读写、阶段、线程数相同）在各轮的结果求均值、最小、最大和变异系数。

用法：python3 tools/aggregate_rounds.py results/统计与图表/jtl-summary-m1.csv m2.csv m3.csv --out results/统计与图表/main-rounds
输出 <out>.csv 与 <out>.md。变异系数 CV = 标准差 / 均值，用来判断三轮结果是否稳定（一般 <5% 可认为稳定）。
"""
import argparse
import csv
import math
import os
from collections import defaultdict

METRICS = [("steady_throughput", "吞吐(次/秒)"), ("steady_avg_ms", "平均(ms)"), ("steady_p95_ms", "P95(ms)"),
           ("steady_p99_ms", "P99(ms)"), ("full_error_pct", "错误率(%)")]
IMPL_CN = {"jpa": "MySQL", "mongo": "MongoDB", "mongoj": "MongoDB j:true"}
OP_CN = {"read": "查询", "write": "写入"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("summaries", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--phase", default="main")
    args = p.parse_args()
    groups = defaultdict(list)
    for path in args.summaries:
        rnd = os.path.basename(path).replace("jtl-summary-", "").replace(".csv", "")
        for r in csv.DictReader(open(path, encoding="utf-8")):
            if r["phase"] == args.phase:
                groups[(r["op"], r["impl"], int(r["threads"]))].append((rnd, r))
    rows = []
    for (op, impl, t), items in sorted(groups.items(), key=lambda kv: (kv[0][0], ["jpa", "mongo", "mongoj"].index(kv[0][1]))):
        row = {"op": op, "impl": impl, "threads": t, "rounds": len(items),
               "db_check": "一致" if all(r.get("db_check", "") in ("一致", "") for _, r in items) else "不一致"}
        for key, _ in METRICS:
            vals = [float(r[key]) for _, r in items]
            mean = sum(vals) / len(vals)
            sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0.0
            row[key + "_mean"] = round(mean, 2)
            row[key + "_min"] = round(min(vals), 2)
            row[key + "_max"] = round(max(vals), 2)
            row[key + "_cv_pct"] = round(100 * sd / mean, 2) if mean else 0.0
            row[key + "_rounds"] = " / ".join("%g" % v for v in vals)
        rows.append(row)
    with open(args.out + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    lines = ["# 主对比 %d 轮汇总" % max(r["rounds"] for r in rows), "",
             "统计区间：每次测试开始后第 60～240 秒。数值为各轮均值，括号内为最小～最大；CV 为变异系数。", "",
             "| 操作 | 实现 | 线程 | 吞吐(次/秒) | 吞吐 CV | 平均(ms) | P95(ms) | P99(ms) | 错误率 | 入库核对 |",
             "| --- | --- | ---: | --- | ---: | --- | --- | --- | ---: | --- |"]
    for r in rows:
        rng = lambda k, d=0: ("%.*f（%.*f～%.*f）" % (d, r[k + "_mean"], d, r[k + "_min"], d, r[k + "_max"]))
        lines.append("| %s | %s | %d | %s | %.1f%% | %s | %s | %s | %.2f%% | %s |" % (
            OP_CN[r["op"]], IMPL_CN[r["impl"]], r["threads"], rng("steady_throughput"), r["steady_throughput_cv_pct"],
            rng("steady_avg_ms", 1), rng("steady_p95_ms"), rng("steady_p99_ms"), r["full_error_pct_mean"],
            r["db_check"] if r["op"] == "write" else "—"))
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", args.out + ".csv/.md", len(rows), "groups")


if __name__ == "__main__":
    main()
