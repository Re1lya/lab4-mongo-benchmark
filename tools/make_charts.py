#!/usr/bin/env python3
"""实验四图表：读/写的吞吐量与 P95、各服务器 CPU、数据库磁盘写入、400 线程压力与恢复的时间曲线。

用法：python3 tools/make_charts.py <统计目录> <轮次目录> --name r1
  <统计目录> 中需要 jtl-summary-<name>.csv、prom-summary-<name>.csv；图片输出到 <统计目录>/charts/。
需要 matplotlib（报告构建环境安装即可，服务器上不需要）。
"""
import argparse
import csv
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# 配色与版式（dataviz 参考色板，已用 validate_palette.js 校验：蓝/橙两色全部通过）
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BAND = "#f3f2ee"
SERIES = {"jpa": "#2a78d6", "mongo": "#eb6834"}
LABEL = {"jpa": "MySQL（Spring Data JPA）", "mongo": "MongoDB（Spring Data MongoDB）"}
SHORT = {"jpa": "MySQL", "mongo": "MongoDB"}
LEVELS = [10, 25, 50, 100, 200, 300, 400]

plt.rcParams.update({
    "font.family": ["PingFang SC", "Hiragino Sans GB", "Arial Unicode MS"],
    "font.size": 10,
    "axes.facecolor": SURFACE, "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
    "legend.frameon": False, "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": INK,
})


def read_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def level_series(rows, op, impl, key):
    """负载 + 压力两种阶段，按线程数排列（恢复检查、预热不在这里）。"""
    vals = {}
    for r in rows:
        if r["op"] == op and r["impl"] == impl and r["phase"] in ("load", "stress"):
            vals[int(r["threads"])] = fnum(r[key])
    return [vals.get(t) for t in LEVELS]


def style_levels(ax):
    """x 轴用等距的线程档位；压力测试区间加浅色底，并在上方标注。"""
    ax.set_xticks(range(len(LEVELS)))
    ax.set_xticklabels([str(t) for t in LEVELS])
    ax.set_xlabel("JMeter 线程数")
    split = LEVELS.index(200) - 0.5
    ax.axvspan(split, len(LEVELS) - 0.5, color=BAND, zorder=0, lw=0)
    ax.set_xlim(-0.5, len(LEVELS) - 0.5)
    y1 = ax.get_ylim()[1]
    ax.text(split / 2 - 0.25, y1, "负载测试", ha="center", va="bottom", color=MUTED, fontsize=9)
    ax.text((split + len(LEVELS) - 0.5) / 2, y1, "压力测试", ha="center", va="bottom", color=MUTED, fontsize=9)
    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0)


def plot_lines(ax, xs_by_impl, ys_by_impl, end_label=True, fmt="{:.0f}"):
    for impl in ("jpa", "mongo"):
        xs, ys = xs_by_impl[impl], ys_by_impl[impl]
        pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
        if not pts:
            continue
        px, py = zip(*pts)
        ax.plot(px, py, color=SERIES[impl], lw=2, solid_capstyle="round", solid_joinstyle="round",
                marker="o", ms=8, mfc=SERIES[impl], mec=SURFACE, mew=2, label=LABEL[impl], zorder=3)
        if end_label:
            ax.annotate(SHORT[impl] + " " + fmt.format(py[-1]), (px[-1], py[-1]), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8.5, color=INK2)


def level_chart(ax, rows, op, key, title, ylabel, fmt="{:.0f}", ymin0=True):
    xs = list(range(len(LEVELS)))
    plot_lines(ax, {"jpa": xs, "mongo": xs},
               {impl: level_series(rows, op, impl, key) for impl in ("jpa", "mongo")}, fmt=fmt)
    if ymin0:
        ax.set_ylim(bottom=0)
    ax.set_ylim(top=ax.get_ylim()[1] * 1.12)
    ax.set_title(title, loc="left")
    ax.set_ylabel(ylabel)
    style_levels(ax)


def save(fig, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("wrote", path)


def overview(jtl, op, out_dir, op_title):
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9))
    level_chart(axes[0], jtl, op, "steady_throughput", "稳态吞吐量", "次/秒")
    level_chart(axes[1], jtl, op, "steady_p95_ms", "稳态 P95 响应时间", "毫秒")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.06), fontsize=9.5, labelcolor=INK)
    fig.suptitle(op_title, x=0.01, y=1.13, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout(w_pad=3)
    save(fig, out_dir, "%s-overview.png" % op)


def cpu_overview(prom, out_dir):
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.6), sharey=True)
    cols = [("CDWY1_cpu_pct", "应用服务器 CDWY1"), ("DB", "数据库服务器（CDWY2 / CDWY5）"), ("CDWY3_cpu_pct", "压测机 CDWY3")]
    for r_i, (op, op_name) in enumerate((("read", "查询"), ("write", "写入"))):
        for c_i, (key, name) in enumerate(cols):
            ax = axes[r_i][c_i]
            ys = {}
            for impl in ("jpa", "mongo"):
                k = key if key != "DB" else ("CDWY2_cpu_pct" if impl == "jpa" else "CDWY5_cpu_pct")
                ys[impl] = level_series(prom, op, impl, k)
            xs = list(range(len(LEVELS)))
            plot_lines(ax, {"jpa": xs, "mongo": xs}, ys, fmt="{:.0f}%")
            ax.set_ylim(0, 112)
            ax.set_yticks([0, 25, 50, 75, 100])
            ax.set_title("%s · %s" % (op_name, name), loc="left", fontsize=10)
            if c_i == 0:
                ax.set_ylabel("CPU 使用率（%）")
            style_levels(ax)
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.04), fontsize=9.5, labelcolor=INK)
    fig.tight_layout(h_pad=2.5, w_pad=2)
    save(fig, out_dir, "cpu-overview.png")


def disk_chart(prom, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9))
    for ax, (suffix, title, unit, fmt) in zip(axes, (("disk_write_iops", "数据库服务器磁盘写入次数", "次/秒", "{:.0f}"),
                                                   ("disk_write_mb_s", "数据库服务器磁盘写入量", "MB/秒", "{:.1f}"))):
        ys = {impl: level_series(prom, "write", impl, ("CDWY2_" if impl == "jpa" else "CDWY5_") + suffix)
              for impl in ("jpa", "mongo")}
        xs = list(range(len(LEVELS)))
        plot_lines(ax, {"jpa": xs, "mongo": xs}, ys, fmt=fmt)
        ax.set_ylim(bottom=0)
        ax.set_ylim(top=ax.get_ylim()[1] * 1.12)
        ax.set_title(title, loc="left")
        ax.set_ylabel(unit)
        style_levels(ax)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.06), fontsize=9.5, labelcolor=INK)
    fig.suptitle("写入测试：数据库服务器的磁盘写入", x=0.01, y=1.13, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout(w_pad=3)
    save(fig, out_dir, "write-disk.png")


def per_second(jtl_path):
    """JTL → 每秒请求数和平均响应时间（按样本时间戳取整到秒）。"""
    cnt = defaultdict(int)
    tot = defaultdict(int)
    t0 = None
    with open(jtl_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = int(row["timeStamp"])
            t0 = ts if t0 is None else min(t0, ts)
            sec = ts // 1000
            cnt[sec] += 1
            tot[sec] += int(row["elapsed"])
    base = t0 // 1000
    secs = sorted(cnt)
    return [s - base for s in secs], [cnt[s] for s in secs], [tot[s] / cnt[s] for s in secs]


def stress_timeline(round_dir, op, out_dir, op_title):
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9))
    for impl in ("jpa", "mongo"):
        xs_all, tps_all, lat_all = [], [], []
        offset = 0
        for phase, t in (("stress", 400), ("recovery", 10)):
            path = os.path.join(round_dir, "%s-%s-%s-t%d" % (impl, op, phase, t), "samples.jtl")
            if not os.path.exists(path):
                continue
            xs, tps, lat = per_second(path)
            xs_all += [x + offset for x in xs]
            tps_all += tps
            lat_all += lat
            offset = xs_all[-1] + 25  # 两次测试之间约 20 秒冷却，画图时留出间隔
        for ax, ys in ((axes[0], tps_all), (axes[1], lat_all)):
            ax.plot(xs_all, ys, color=SERIES[impl], lw=1.6, label=LABEL[impl], solid_joinstyle="round")
    axes[0].set_title("每秒完成的请求数", loc="left")
    axes[0].set_ylabel("次/秒")
    axes[1].set_title("每秒平均响应时间", loc="left")
    axes[1].set_ylabel("毫秒")
    for ax in axes:
        ax.set_ylim(bottom=0)
        ax.set_xlabel("时间（秒）：左段为 400 线程压力测试，右段为紧接着的 10 线程恢复检查")
        ax.tick_params(length=0)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.06), fontsize=9.5, labelcolor=INK)
    fig.suptitle(op_title, x=0.01, y=1.13, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout(w_pad=3)
    save(fig, out_dir, "%s-stress-recovery.png" % op)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stats_dir")
    p.add_argument("round_dir")
    p.add_argument("--name", required=True)
    args = p.parse_args()
    out = os.path.join(args.stats_dir, "charts")
    jtl = read_csv(os.path.join(args.stats_dir, "jtl-summary-%s.csv" % args.name))
    overview(jtl, "read", out, "查询 GET /api/logs：负载与压力测试")
    overview(jtl, "write", out, "写入 POST /api/logs：负载与压力测试")
    prom_path = os.path.join(args.stats_dir, "prom-summary-%s.csv" % args.name)
    if os.path.exists(prom_path):
        prom = read_csv(prom_path)
        cpu_overview(prom, out)
        disk_chart(prom, out)
    stress_timeline(args.round_dir, "read", out, "查询：400 线程压力测试与恢复")
    stress_timeline(args.round_dir, "write", out, "写入：400 线程压力测试与恢复")


if __name__ == "__main__":
    main()
