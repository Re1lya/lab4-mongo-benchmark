# 实验数据

按课程 11-19 更新的 Prometheus 配置（每 1 秒采集，CPU 使用率取 2 秒平均）所做的全部测试。

## 目录

| 位置 | 内容 |
| --- | --- |
| `00-环境与一致性/` | 部署后的接口检查（两种实现各 22 项及逐项比较）、两库预置数据的生成摘要与导出摘要 |
| `n1/` | 主对比：查询 50 线程、写入 100 线程，每次 240 秒；另含 MongoDB j:true 写入（`mongoj-write-main-t100`） |
| `probe/` | 最多同时运行线程数：查询、写入各自 400～2000 线程逐级加压；`probe.log` 是每一级的判定，`choice.txt` 是选出的线程数 |
| `x1/` | 在选出的线程数下持续压测（查询 400、写入 2000 线程，240 秒）及之后的 10 线程恢复检查 |
| `prometheus-phase3.txt.gz` | 测试时段（2026-11-19 11:10–13:30 UTC）的 Prometheus 原始样本：节点每 1 秒、应用每 2 秒，含记录规则 `node:cpu_usage_percent`（2 秒平均） |
| `jmeter-html/` | 主对比、j:true 与持续压测的 JMeter HTML 报告（`jmeter -g` 生成，9 份）：只含统计区间（第 60～240 秒）内的请求，与报告口径相同。下载后用浏览器打开 `jmeter-html/index.html`，说明见 `jmeter-html/README.md` |
| `统计与图表/` | 由原始数据计算出的统计表和图表 |

目录名格式：`<实现>-<读写>-<阶段>-t<线程数>`。实现：`jpa` = MySQL 版，`mongo` = MongoDB 版（默认写关注 w:1），`mongoj` = MongoDB 版且写关注 w:1 + j:true。阶段：`main` 主对比、`probe` 逐级加压、`maxload` 最多线程数下持续压测、`recovery` 之后的 10 线程恢复检查。

11-15、11-16 两个阶段（旧监控配置下的梯度探索、三轮主对比、调优与过载）的数据已从当前版本移除，需要时可在 git 历史中找到（GitHub 提交 `88ac83b`、Gitee 提交 `5c98a9d` 仍包含它们）。

## 每次测试目录中的文件

| 文件 | 内容 |
| --- | --- |
| `samples.jtl.gz` | **JMeter 原始 JTL**（CSV 格式，每个请求一行），gzip 压缩；`gunzip -k samples.jtl.gz` 得到原文件 |
| `params.txt` | 测试计划、目标端口、线程数、升压/持续秒数、JMeter 堆设置 |
| `start.txt` / `end.txt` | 测试开始、结束时间（UTC），用于对应 Prometheus 监控时间段 |
| `db-rows.txt` | 仅写入测试：测试前后数据库行数与新增行数（应等于 HTTP 201 的请求数） |
| `monitor.json` | 该次测试的监控时间序列：各服务器 CPU（2 秒平均）、应用 CPU、JVM 线程、连接池占用与等待 |

各组目录下的 `warmups.log` 是每次正式测试前预热的 JMeter 汇总行（预热的 JTL 不保留）。

## 统计与图表

| 文件 | 内容 |
| --- | --- |
| `jtl-summary-<组>.csv` / `.md` | 每次测试的样本数、错误数、区间吞吐量、平均/P50/P90/P95/P99/最大响应时间、入库核对；另有同时运行线程数最大值 `max_threads`、平均响应大小 `bytes_avg`、压测机自检 `client_gap_ms` |
| `prom-summary-<组>.csv` | 每次测试统计区间内的各服务器 CPU（`CDWYx_cpu2s_avg`/`_max` 为 2 秒平均 CPU 的均值与最大值）、iowait、内存、数据库磁盘写入、JVM 与连接池、服务端每秒请求数、每请求 CPU 时间。逐级加压中未通过的级别没有“全部线程都在运行”的时段，按整次测试统计，`window` 列为 `full-run` |
| `charts/*.png` | 报告中的图：`main-comparison`（主对比）、`main-resources`（主对比的资源开销）、`probe`（逐级加压）、`maxload-cpu`（持续压测时的 CPU 曲线）、`jmeter-<组>-<测试名>`（9 份 JMeter HTML 报告的统计表截图，`tools/jmeter_html_shots.py` 生成） |

## 重新计算

```bash
# 主对比与持续压测固定统计第 60～240 秒；逐级加压统计全部线程都在运行的时段
python3 tools/analyze_jtl.py results/n1 --out results/统计与图表 --name n1 --fixed-window 60:240
python3 tools/analyze_jtl.py results/probe --out results/统计与图表 --name probe
python3 tools/analyze_jtl.py results/x1 --out results/统计与图表 --name x1 --fixed-window 60:240
for g in n1 probe x1; do
  python3 tools/analyze_prom.py results/prometheus-phase3.txt.gz results/统计与图表/jtl-summary-$g.csv results/$g --out results/统计与图表 --name $g
done
python3 tools/make_charts.py results/统计与图表      # 需要 matplotlib
python3 tools/build_report.py                         # 需要 python-docx 与 Google Chrome
# JMeter HTML 报告：见 jmeter-html/README.md（需要 JMeter 5.6）
```
