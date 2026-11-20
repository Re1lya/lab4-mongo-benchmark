#!/usr/bin/env python3
"""用 JMeter 自带的报告生成器（jmeter -g）为指定测试生成 HTML 报告。

统计区间与实验报告一致：只取 jtl-summary-<组>.csv 里该测试的统计区间（第 60～240 秒）内开始的请求，
所以网页里的样本数、吞吐量、平均与百分位响应时间和报告的表格对得上（百分位算法略有不同，可能差 1 ms）。

JTL 为了减小体积没有保存 threadName、responseMessage 等列，而报告生成器要用到它们。
这里只在临时副本里补上：threadName 填“<线程组名> 1-1”（“活跃线程数随时间变化”图按线程组汇总，数值来自 grpThreads），
responseMessage 按状态码填 OK/Created。原始 JTL 不改动。

用法（需要 JMeter 5.6，Python 3.6 以上）：
  python3 tools/jmeter_html.py --results results --summaries results/统计与图表 --out results/jmeter-html \\
      n1/jpa-read-main-t50 n1/mongo-read-main-t50 ...
输出：<out>/<组>/<测试名>/index.html，以及汇总页 <out>/index.html。
"""
import argparse
import csv
import gzip
import html
import os
import re
import shutil
import subprocess
import sys

NAME_RE = re.compile(r"^(jpa|mongo|mongoj)-(read|write)-([a-z]+\d*)-t(\d+)$")
IMPL = {"jpa": "MySQL 版", "mongo": "MongoDB 版", "mongoj": "MongoDB 版（j:true）"}
OP = {"read": "查询", "write": "写入"}
GROUP_TEXT = {"n1": "主对比", "x1": "最多线程数下持续压测"}
THREAD_GROUP = {"read": "查询线程组", "write": "写入线程组"}
MESSAGE = {"200": "OK", "201": "Created"}


def open_jtl(run_dir):
    path = os.path.join(run_dir, "samples.jtl")
    if os.path.exists(path):
        return open(path, newline="", encoding="utf-8")
    return gzip.open(path + ".gz", "rt", newline="", encoding="utf-8")


def summary_row(summaries, group, impl, op, phase, threads):
    path = os.path.join(summaries, "jtl-summary-%s.csv" % group)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r["impl"], r["op"], r["phase"], r["threads"]) == (impl, op, phase, str(threads)):
                return r
    raise SystemExit("%s 中没有 %s-%s-%s-t%d" % (path, impl, op, phase, threads))


def write_window_csv(run_dir, dst, s0, s1, op):
    """把统计区间内开始的请求写成报告生成器可读的 CSV，缺的列补上。返回行数。"""
    n = 0
    with open_jtl(run_dir) as fin, open(dst, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        fields = list(reader.fieldnames)
        extra = [c for c in ("responseMessage", "threadName") if c not in fields]
        out_fields = fields[:fields.index("responseCode") + 1] + extra + fields[fields.index("responseCode") + 1:]
        w = csv.DictWriter(fout, fieldnames=out_fields, lineterminator="\n")
        w.writeheader()
        for row in reader:
            ts = int(row["timeStamp"])
            if not (s0 <= ts < s1):
                continue
            if "responseMessage" in extra:
                row["responseMessage"] = MESSAGE.get(row["responseCode"], "")
            if "threadName" in extra:
                row["threadName"] = THREAD_GROUP[op] + " 1-1"
            w.writerow(row)
            n += 1
    return n


def escape_props(text):
    """.properties 按 ISO-8859-1 读取：非 ASCII 字符一律写成 \\uXXXX。"""
    return "".join(c if 32 <= ord(c) < 127 and c != "\\" else "\\u%04x" % ord(c) for c in text)


def generate(args, item):
    group, name = item.split("/", 1)
    m = NAME_RE.match(name)
    if not m:
        raise SystemExit("测试名格式不对：" + item)
    impl, op, phase, threads = m.group(1), m.group(2), m.group(3), int(m.group(4))
    r = summary_row(args.summaries, group, impl, op, phase, threads)
    s0, s1 = int(float(r["steady_start_ms"])), int(float(r["steady_end_ms"]))
    run_dir = os.path.join(args.results, group, name)
    work = os.path.join(args.work, group)
    os.makedirs(work, exist_ok=True)
    src = os.path.join(work, name + ".csv")
    rows = write_window_csv(run_dir, src, s0, s1, op)
    if rows != int(r["steady_samples"]):
        raise SystemExit("%s：区间内 %d 行，与统计表的 %s 不一致" % (item, rows, r["steady_samples"]))
    secs = (s1 - s0) / 1000.0
    title = "实验四 %s%s %d 线程 · %s（第 %d～%d 秒）" % (
        IMPL[impl], OP[op], threads, GROUP_TEXT.get(group, group),
        round((s0 - int(r["start_ms"])) / 1000.0), round((s1 - int(r["start_ms"])) / 1000.0))
    props = os.path.join(work, name + ".properties")
    with open(props, "w", encoding="ascii") as f:
        f.write("jmeter.reportgenerator.report_title=%s\n" % escape_props(title))
        f.write("jmeter.reportgenerator.overall_granularity=1000\n")   # 曲线按 1 秒取点（默认 1 分钟）
        f.write("jmeter.reportgenerator.statistic_window=-1\n")        # 百分位用全部请求计算（默认只用最后 2 万个）
        f.write("jmeter.save.saveservice.print_field_names=true\n")
    out = os.path.join(args.out, group, name)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    log = os.path.join(work, name + ".log")
    p = subprocess.run([args.jmeter, "-g", src, "-o", out, "-q", props, "-j", log],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    if p.returncode != 0 or not os.path.exists(os.path.join(out, "index.html")):
        sys.stdout.write(p.stdout)
        raise SystemExit("%s：JMeter 生成失败，日志 %s" % (item, log))
    if not args.keep:
        os.remove(src)
    print("%-32s %8d 个请求 / %.0f 秒 → %s" % (item, rows, secs, out), flush=True)
    return {"group": group, "name": name, "impl": impl, "op": op, "threads": threads, "summary": r, "title": title}


def write_index(out_dir, done):
    rows = []
    for d in done:
        r = d["summary"]
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%s</td><td>%.1f</td><td>%s</td><td>%s</td>"
                    "<td><a href='%s/%s/index.html'>打开</a></td></tr>"
                    % (html.escape(GROUP_TEXT.get(d["group"], d["group"])), html.escape(IMPL[d["impl"]]), OP[d["op"]], d["threads"],
                       "{:,.0f}".format(float(r["steady_throughput"])), float(r["steady_avg_ms"]), r["steady_p95_ms"], r["steady_p99_ms"],
                       d["group"], d["name"]))
    page = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>实验四 JMeter HTML 报告</title>
<style>
body {{ font: 14px/1.6 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 24px; color: #222; }}
table {{ border-collapse: collapse; }} th, td {{ border-bottom: 1px solid #ddd; padding: 6px 10px; text-align: center; }}
th {{ background: #f4f4f4; }} p {{ max-width: 860px; }}
</style></head><body>
<h2>实验四 JMeter HTML 报告（主对比、j:true 与持续压测）</h2>
<p>由 JMeter 5.6.3 的报告生成器（<code>jmeter -g</code>）生成。每份只包含该测试统计区间（第 60～240 秒）内开始的请求，
与实验报告的统计口径相同；下表的吞吐量与响应时间取自 <code>results/统计与图表/jtl-summary-*.csv</code>。完整的原始数据见各测试目录的
<code>samples.jtl.gz</code>。</p>
<table><tr><th>测试</th><th>实现</th><th>操作</th><th>线程</th><th>吞吐（次/秒）</th><th>平均（ms）</th><th>P95（ms）</th><th>P99（ms）</th><th>HTML 报告</th></tr>
{rows}
</table></body></html>
""".format(rows="\n".join(rows))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("items", nargs="+", help="<组>/<测试名>，如 m1/jpa-read-main-t50")
    p.add_argument("--results", required=True, help="含 <组>/<测试名>/samples.jtl[.gz] 的目录")
    p.add_argument("--summaries", required=True, help="含 jtl-summary-<组>.csv 的目录")
    p.add_argument("--out", required=True)
    p.add_argument("--work", default="/tmp/jmeter-html-work", help="临时 CSV 与 JMeter 日志")
    p.add_argument("--jmeter", default="jmeter")
    p.add_argument("--keep", action="store_true", help="保留临时 CSV")
    p.add_argument("--no-index", action="store_true")
    args = p.parse_args()
    done = [generate(args, item) for item in args.items]
    if not args.no_index:
        write_index(args.out, done)


if __name__ == "__main__":
    main()
