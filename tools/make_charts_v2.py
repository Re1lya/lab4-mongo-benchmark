#!/usr/bin/env python3
"""第二阶段图表：主对比（3 轮）、资源开销、并发量调优、连接池调优、过载与恢复。

用法：python3 tools/make_charts_v2.py results/统计与图表
需要的统计文件（同目录）：jtl-summary-m1/m2/m3.csv、main-rounds.csv、jtl-summary-sweep.csv、
jtl-summary-pool.csv、jtl-summary-overload.csv、prom-summary-m1/m2/m3.csv。缺哪个就跳过对应的图。
"""
import argparse
import csv
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"; INK = "#0b0b0b"; INK2 = "#52514e"; MUTED = "#898781"; GRID = "#e1e0d9"; AXIS = "#c3c2b7"
# 已用 validate_palette.js 校验（--pairs all 通过）；青绿色对比度不足 3:1，因此所有柱都标数值、报告另附表格
SERIES = {"jpa": "#2a78d6", "mongo": "#eb6834", "mongoj": "#1baf7a"}
LABEL = {"jpa": "MySQL（Spring Data JPA）", "mongo": "MongoDB（Spring Data MongoDB，w:1）", "mongoj": "MongoDB（w:1 + j:true）"}
SHORT = {"jpa": "MySQL", "mongo": "MongoDB", "mongoj": "MongoDB j:true"}

plt.rcParams.update({
    "font.family": ["PingFang SC", "Hiragino Sans GB", "Arial Unicode MS"], "font.size": 10,
    "axes.facecolor": SURFACE, "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
    "legend.frameon": False, "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.titlepad": 10,
})


def rows(path):
    return list(csv.DictReader(open(path, encoding="utf-8"))) if os.path.exists(path) else []


def save(fig, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(os.path.join(out_dir, name), dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("wrote", name)


def legend_top(fig, axes_with_handles, ncol=3, y=1.06):
    handles, labels = [], []
    for ax in axes_with_handles:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in labels:
                handles.append(h)
                labels.append(l)
    fig.legend(handles, labels, loc="upper center", ncol=ncol, bbox_to_anchor=(0.5, y), fontsize=9.5, labelcolor=INK)


def grouped_bars(ax, groups, series_order, value, err=None, fmt="{:.0f}", ylabel=""):
    """groups: [(组名, {impl: 数值})]；err: [(组名, {impl: (低, 高)})]；每组内按 series_order 排列。"""
    width = 0.24
    for gi, (gname, vals) in enumerate(groups):
        present = [s for s in series_order if s in vals and vals[s] is not None]
        offset0 = -(len(present) - 1) * width / 2
        for si, impl in enumerate(present):
            x = gi + offset0 + si * width
            v = vals[impl]
            ax.bar(x, v, width=width, color=SERIES[impl], edgecolor=SURFACE, linewidth=2,
                   label=LABEL[impl], zorder=3)
            top = v
            if err:
                lo, hi = err[gi][1].get(impl, (v, v))
                ax.plot([x, x], [lo, hi], color=INK2, lw=1.2, zorder=4)
                ax.plot([x - 0.04, x + 0.04], [hi, hi], color=INK2, lw=1.2, zorder=4)
                ax.plot([x - 0.04, x + 0.04], [lo, lo], color=INK2, lw=1.2, zorder=4)
                top = max(hi, v)
            ax.annotate(fmt.format(v), (x, top), xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8.5, color=INK2)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g for g, _ in groups])
    ax.tick_params(length=0)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.12)


def main_comparison(stats, out):
    agg = rows(os.path.join(stats, "main-rounds.csv"))
    if not agg:
        return
    by = {(r["op"], r["impl"]): r for r in agg}
    ops = [("read", "查询（50 线程）"), ("write", "写入（100 线程）")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    for ax, (key, title, unit, fmt) in zip(axes, (("steady_throughput", "吞吐量（3 轮均值，误差线为最小～最大）", "次/秒", "{:,.0f}"),
                                                   ("steady_p95_ms", "P95 响应时间（3 轮均值）", "毫秒", "{:.0f}"))):
        groups, errs = [], []
        for op, name in ops:
            vals, er = {}, {}
            for impl in ("jpa", "mongo", "mongoj"):
                r = by.get((op, impl))
                if r:
                    vals[impl] = float(r[key + "_mean"])
                    er[impl] = (float(r[key + "_min"]), float(r[key + "_max"]))
            groups.append((name, vals))
            errs.append((name, er))
        grouped_bars(axes[list(axes).index(ax)], groups, ["jpa", "mongo", "mongoj"], key, errs, fmt, unit)
        ax.set_title(title, loc="left")
    legend_top(fig, axes)
    fig.suptitle("主对比：两种实现在相同参数下各测 3 轮（统计第 60～240 秒）", x=0.01, y=1.14, ha="left",
                 fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout(w_pad=3)
    save(fig, out, "main-comparison.png")


def main_resources(stats, out):
    prom = []
    for r in ("m1", "m2", "m3"):
        prom += [x for x in rows(os.path.join(stats, "prom-summary-%s.csv" % r)) if x["phase"] == "main"]
    if not prom:
        return
    acc = defaultdict(list)
    for x in prom:
        db = "CDWY2" if x["impl"] == "jpa" else "CDWY5"
        acc[(x["op"], x["impl"], "app")].append(float(x["app_host_cpu_ms_per_req"]))
        acc[(x["op"], x["impl"], "db")].append(float(x["db_host_cpu_ms_per_req"]))
        acc[(x["op"], x["impl"], "iops")].append(float(x[db + "_disk_write_iops"]))
    mean = lambda k: sum(acc[k]) / len(acc[k]) if acc.get(k) else None
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.9))
    panels = (("app", "应用服务器：每个请求的 CPU 时间", "毫秒/请求", "{:.2f}", ("read", "write")),
              ("db", "数据库服务器：每个请求的 CPU 时间", "毫秒/请求", "{:.2f}", ("read", "write")),
              ("iops", "写入时数据库服务器每秒写盘次数", "次/秒", "{:,.0f}", ("write",)))
    for ax, (kind, title, unit, fmt, ops) in zip(axes, panels):
        groups = [("查询" if op == "read" else "写入", {i: mean((op, i, kind)) for i in ("jpa", "mongo", "mongoj")})
                  for op in ops]
        grouped_bars(ax, groups, ["jpa", "mongo", "mongoj"], kind, None, fmt, unit)
        ax.set_title(title, loc="left", fontsize=10)
    legend_top(fig, axes)
    fig.suptitle("主对比的资源开销（3 轮均值；CPU 时间 = 2 核 × 使用率 ÷ 每秒请求数）", x=0.01, y=1.14, ha="left",
                 fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout(w_pad=2.5)
    save(fig, out, "main-resources.png")


def phase3_resources(stats, out):
    """第三阶段复测（新监控配置）的资源开销：CPU 使用率取记录规则 node:cpu_usage_percent（2 秒平均）在统计区间内的均值。"""
    prom = [x for x in rows(os.path.join(stats, "prom-summary-n1.csv")) if x["phase"] == "main"]
    if not prom or not prom[0].get("CDWY1_cpu2s_avg"):
        return
    val = {}
    for x in prom:
        db = "CDWY2" if x["impl"] == "jpa" else "CDWY5"
        val[(x["op"], x["impl"], "app")] = float(x["CDWY1_cpu2s_avg"])
        val[(x["op"], x["impl"], "db")] = float(x[db + "_cpu2s_avg"])
        val[(x["op"], x["impl"], "iops")] = float(x[db + "_disk_write_iops"])
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.9))
    panels = (("app", "应用服务器 CPU 使用率", "%", "{:.0f}%", ("read", "write")),
              ("db", "数据库服务器 CPU 使用率", "%", "{:.0f}%", ("read", "write")),
              ("iops", "写入时数据库服务器每秒写盘次数", "次/秒", "{:,.0f}", ("write",)))
    for ax, (kind, title, unit, fmt, ops) in zip(axes, panels):
        groups = [("查询" if op == "read" else "写入", {i: val.get((op, i, kind)) for i in ("jpa", "mongo", "mongoj")})
                  for op in ops]
        grouped_bars(ax, groups, ["jpa", "mongo", "mongoj"], kind, None, fmt, unit)
        if kind != "iops":
            ax.set_ylim(0, 115)
            ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_title(title, loc="left", fontsize=10)
    legend_top(fig, axes)
    fig.suptitle("第三阶段复测的资源开销（CPU 使用率为 2 秒平均在统计区间内的均值）", x=0.01, y=1.14, ha="left",
                 fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout(w_pad=2.5)
    save(fig, out, "phase3-resources.png")


def maxload_cpu(stats, out):
    """最多线程数下持续压测时各服务器的 CPU 使用率曲线（记录规则 node:cpu_usage_percent，2 秒平均）。
    每个面板一种实现（颜色同其他图：MySQL 蓝、MongoDB 橙），服务器用线型区分并在线尾直接标注。"""
    import json
    base = os.path.join(os.path.dirname(os.path.normpath(stats)), "x1")
    if not os.path.isdir(base):
        return
    runs = {}
    for d in sorted(os.listdir(base)):
        m = __import__("re").match(r"^(jpa|mongo)-(read|write)-maxload-t(\d+)$", d)
        p = os.path.join(base, d, "monitor.json")
        if m and os.path.exists(p):
            runs[(m.group(2), m.group(1))] = (int(m.group(3)), json.load(open(p, encoding="utf-8")))
    if not runs:
        return
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.6), sharey=True)
    for ri, op in enumerate(("read", "write")):
        for ci, impl in enumerate(("jpa", "mongo")):
            ax = axes[ri][ci]
            if (op, impl) not in runs:
                ax.set_visible(False)
                continue
            t, mon = runs[(op, impl)]
            t0 = mon["window_utc_ms"][0]
            s0, s1 = [(x - t0) / 1000.0 for x in mon["steady_utc_ms"]]
            ax.axvspan(s0, s1, color=GRID, alpha=0.45, lw=0, zorder=0)
            ax.text((s0 + s1) / 2, 104, "统计区间", ha="center", va="bottom", fontsize=8, color=MUTED)
            db = "CDWY2" if impl == "jpa" else "CDWY5"
            lines = (("CDWY1_cpu2s_pct", "应用服务器", SERIES[impl], "-"),
                     (db + "_cpu2s_pct", "数据库服务器", SERIES[impl], "--"),
                     ("CDWY3_cpu2s_pct", "压测机", MUTED, ":"))
            for key, name, color, style in lines:
                pts = mon["series"].get(key) or []
                if not pts:
                    continue
                xs = [(p[0] - t0) / 1000.0 for p in pts]
                ys = [p[1] for p in pts]
                ax.plot(xs, ys, color=color, lw=2 if style != ":" else 1.6, ls=style, label=name, zorder=3)
                ax.annotate(name, (xs[-1], ys[-1]), xytext=(5, 0), textcoords="offset points", va="center",
                            fontsize=8.5, color=INK2)
            ax.set_ylim(0, 112)
            ax.set_yticks([0, 25, 50, 75, 100])
            ax.set_xlim(0, max(260, s1 + 20))
            ax.set_title("%s %s：%d 线程" % (SHORT[impl], "查询" if op == "read" else "写入", t), loc="left", fontsize=10)
            if ci == 0:
                ax.set_ylabel("CPU 使用率（%）")
            if ri == 1:
                ax.set_xlabel("测试开始后的秒数")
            ax.grid(True, axis="y")
    handles = [plt.Line2D([], [], color=INK2, lw=2, ls="-", label="应用服务器（CDWY1）"),
               plt.Line2D([], [], color=INK2, lw=2, ls="--", label="数据库服务器（MySQL 为 CDWY2，MongoDB 为 CDWY5）"),
               plt.Line2D([], [], color=MUTED, lw=1.6, ls=":", label="压测机（CDWY3）")]
    fig.legend(handles=handles, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.03), fontsize=9.5, labelcolor=INK)
    fig.suptitle("最多线程数下持续压测：各服务器 CPU 使用率（2 秒平均，颜色区分实现：MySQL 蓝、MongoDB 橙）", x=0.01, y=1.08,
                 ha="left", fontsize=12.5, fontweight="bold", color=INK)
    fig.tight_layout(h_pad=2.2, w_pad=3)
    save(fig, out, "maxload-cpu.png")


def level_lines(ax, data, levels, key, title, unit, fmt="{:.0f}"):
    xs = list(range(len(levels)))
    ends = {}
    for impl in ("jpa", "mongo"):
        ys = [data.get((impl, t), {}).get(key) for t in levels]
        pts = [(x, float(y)) for x, y in zip(xs, ys) if y not in (None, "")]
        if not pts:
            continue
        px, py = zip(*pts)
        ax.plot(px, py, color=SERIES[impl], lw=2, marker="o", ms=8, mfc=SERIES[impl], mec=SURFACE, mew=2,
                label=LABEL[impl], zorder=3)
        ends[impl] = (px[-1], py[-1])
    ax.set_xticks(xs)
    ax.set_xticklabels([str(t) for t in levels])
    ax.tick_params(length=0)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.15)
    ax.set_title(title, loc="left", fontsize=10)
    ax.set_ylabel(unit)
    y0, y1 = ax.get_ylim()
    if len(ends) < 2 or abs(ends["jpa"][1] - ends["mongo"][1]) >= 0.07 * (y1 - y0):
        for impl, (x, y) in ends.items():
            ax.annotate(SHORT[impl] + " " + fmt.format(y), (x, y), xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=8.5, color=INK2)


def sweep_like(stats, out, name, title, levels_by_op, phase_match, xlabel, extra=None):
    """并发量调优 / 连接池调优 / 过载：2×2，行 = 查询、写入；列 = 吞吐、P95。"""
    data = defaultdict(dict)
    for r in rows(os.path.join(stats, "jtl-summary-%s.csv" % name)):
        lv = phase_match(r)
        if lv is not None:
            data[(r["op"], r["impl"], lv)] = r
    for r in (extra or []):
        lv = phase_match(r)
        if lv is not None:
            data.setdefault((r["op"], r["impl"], lv), r)
    if not data:
        return
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.0))
    for ri, op in enumerate(("read", "write")):
        d = {(impl, lv): data[(op, impl, lv)] for (o, impl, lv) in data if o == op}
        levels = levels_by_op[op]
        level_lines(axes[ri][0], d, levels, "steady_throughput", "%s：吞吐量" % ("查询" if op == "read" else "写入"), "次/秒", "{:,.0f}")
        level_lines(axes[ri][1], d, levels, "steady_p95_ms", "%s：P95 响应时间" % ("查询" if op == "read" else "写入"), "毫秒")
        for ax in axes[ri]:
            ax.set_xlabel(xlabel[op] if isinstance(xlabel, dict) else xlabel)
    legend_top(fig, [axes[0][0]], ncol=2, y=1.04)
    fig.suptitle(title, x=0.01, y=1.09, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout(h_pad=2.5, w_pad=3)
    save(fig, out, "%s.png" % name)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stats_dir")
    args = p.parse_args()
    out = os.path.join(args.stats_dir, "charts")
    main_comparison(args.stats_dir, out)
    main_resources(args.stats_dir, out)
    phase3_resources(args.stats_dir, out)
    maxload_cpu(args.stats_dir, out)
    # 并发量调优缺少的两档取主对比：查询 50 线程取第 2 轮（数据库状态与并发量调优的查询测试相同：MongoDB 库中留有
    # 上一项写入的日志、MySQL 为预置数据），写入 100 线程取第 1 轮（写入测试前都会重置数据库）
    main_extra = ([r for r in rows(os.path.join(args.stats_dir, "jtl-summary-m2.csv")) if r["op"] == "read"]
                  + [r for r in rows(os.path.join(args.stats_dir, "jtl-summary-m1.csv")) if r["op"] == "write"])
    sweep_like(args.stats_dir, out, "sweep", "并发量调优：25～150 线程（统计第 60～240 秒）",
               {"read": [25, 50, 75, 100, 150], "write": [25, 50, 75, 100, 150]},
               lambda r: int(r["threads"]) if r["phase"] in ("sweep", "main") and r["impl"] in ("jpa", "mongo") else None,
               "JMeter 线程数", extra=main_extra)
    pool_rows = rows(os.path.join(args.stats_dir, "jtl-summary-pool.csv"))
    pool_t = {r["op"]: int(r["threads"]) for r in pool_rows}
    sweep_rows = rows(os.path.join(args.stats_dir, "jtl-summary-sweep.csv")) + main_extra
    extra = [dict(r, phase="pool100") for r in sweep_rows
             if r["op"] in pool_t and int(r["threads"]) == pool_t[r["op"]] and r["impl"] in ("jpa", "mongo")]
    sweep_like(args.stats_dir, out, "pool", "连接池调优：固定并发量，连接池 25 / 50 / 100",
               {"read": [25, 50, 100], "write": [25, 50, 100]},
               lambda r: int(r["phase"][4:]) if r["phase"].startswith("pool") else None,
               {op: "连接池最大连接数（%s %d 线程）" % ("查询" if op == "read" else "写入", t) for op, t in pool_t.items()}
               if pool_t else "连接池最大连接数", extra=extra)
    sweep_like(args.stats_dir, out, "overload", "过载：600 / 800 / 1000 线程（JMeter 在 CDWY4，统计第 60～240 秒）",
               {"read": [600, 800, 1000], "write": [600, 800, 1000]},
               lambda r: int(r["threads"]) if r["phase"] == "overload" else None, "JMeter 线程数")


if __name__ == "__main__":
    main()
