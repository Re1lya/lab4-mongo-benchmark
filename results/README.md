# 实验数据

## 目录

| 位置 | 内容 |
| --- | --- |
| `00-环境与一致性/` | 部署后的接口检查（两种实现各 22 项及逐项比较）、两库预置数据的生成摘要与导出摘要 |
| `r1/` | 第 1 轮：梯度探索（10～400 线程，每档 60 秒），36 次测试 |
| `m1/`、`m2/`、`m3/` | 第二阶段主对比第 1～3 轮：查询 50 线程、写入 100 线程，每次 240 秒；另含 MongoDB j:true 写入（`mongoj-write-main-t100`） |
| `sweep/` | 并发量调优：查询 25/75/100/150、写入 25/50/75/150 线程（查询 50、写入 100 线程见 `m1/`～`m3/`） |
| `pool/` | 连接池调优：连接池 25、50；`choice.txt` 是所选并发量的依据 |
| `overload/` | 过载与恢复：600/800/1000 线程（JMeter 在 CDWY4），每档之后的 10 线程恢复检查；MySQL 版查询 800 线程为测试结束后的重测（预热汇总在 `warmups-rerun.log`） |
| `overload/invalid/` | 作废的一次测试（压测机自身成了瓶颈），原始数据与说明，不参与统计 |
| `n1/` | 第三阶段（11-19，按老师更新的监控配置）复测的主对比 1 轮与 j:true 1 次，参数同第二阶段 |
| `probe/` | 第三阶段最多同时运行线程数：查询、写入各自 400～2000 线程逐级加压；`probe.log` 是每一级的判定，`choice.txt` 是选出的线程数 |
| `x1/` | 第三阶段在选出的线程数下持续压测（查询 400、写入 2000 线程，240 秒）及之后的 10 线程恢复检查 |
| `r1/prometheus-r1.txt.gz` | 第 1 轮测试时段（2026-11-15 12:38–13:38 UTC）的 Prometheus 原始样本 |
| `prometheus-phase2.txt.gz` | 第二阶段测试时段（2026-11-16 03:20–14:40 UTC）的 Prometheus 原始样本 |
| `prometheus-phase3.txt.gz` | 第三阶段测试时段（2026-11-19 11:10–13:30 UTC）的 Prometheus 原始样本：节点每 1 秒、应用每 2 秒，含记录规则 `node:cpu_usage_percent`（2 秒平均） |
| `统计与图表/` | 由原始数据计算出的统计表和图表 |

目录名格式：`<实现>-<读写>-<阶段>-t<线程数>`。实现：`jpa` = MySQL 版，`mongo` = MongoDB 版（默认写关注 w:1），`mongoj` = MongoDB 版且写关注 w:1 + j:true。阶段：第 1 轮有 `warmup`（预热，不参与比较）、`load`、`stress`、`recovery`；第二阶段有 `main`、`sweep`、`pool25`/`pool50`（连接池上限）、`overload`、`recovery600`/`recovery800`/`recovery1000`（该档过载之后的恢复检查）；第三阶段有 `main`（复测）、`probe`（逐级加压）、`maxload`（最多线程数下持续压测）、`recovery`（之后的恢复检查）。

## 每次测试目录中的文件

| 文件 | 内容 |
| --- | --- |
| `samples.jtl.gz` | **JMeter 原始 JTL**（CSV 格式，每个请求一行），gzip 压缩；`gunzip -k samples.jtl.gz` 得到原文件 |
| `params.txt` | 测试计划、目标端口、线程数、升压/持续秒数、JMeter 堆设置 |
| `start.txt` / `end.txt` | 测试开始、结束时间（UTC），用于对应 Prometheus 监控时间段 |
| `db-rows.txt` | 仅写入测试：测试前后数据库行数与新增行数（应等于 HTTP 201 的请求数） |
| `monitor.json` | 该次测试的监控时间序列：各服务器 CPU、应用 CPU、JVM 线程、连接池占用与等待 |

第二、三阶段各组目录下的 `warmups.log` 是每次正式测试前预热的 JMeter 汇总行（预热的 JTL 不保留）。

## 统计与图表

| 文件 | 内容 |
| --- | --- |
| `jtl-summary-<组>.csv` / `.md` | 每次测试的样本数、错误数、区间吞吐量、平均/P50/P90/P95/P99/最大响应时间、入库核对；另有同时运行线程数最大值 `max_threads`、平均响应大小 `bytes_avg`、压测机自检 `client_gap_ms` |
| `prom-summary-<组>.csv` | 每次测试统计区间内的各服务器 CPU/iowait/内存、数据库磁盘写入、JVM 与连接池、服务端每秒请求数、每请求 CPU 时间；第三阶段另有 `CDWYx_cpu2s_avg`/`_max`（2 秒平均 CPU 的均值与最大值）。逐级加压中未通过的级别没有“全部线程都在运行”的时段，按整次测试统计，`window` 列为 `full-run` |
| `main-rounds.csv` / `.md` | 主对比 3 轮汇总：均值、最小、最大、变异系数 |
| `charts/*.png` | 报告中的图：`main-comparison`、`phase3-resources`、`sweep`、`pool`、`overload`、`maxload-cpu`；`main-resources`（第二阶段资源）与第 1 轮的图（`read-overview` 等）保留备查 |

## 重新计算

```bash
# 第 1 轮：统计“所有线程都在运行”的时段
python3 tools/analyze_jtl.py results/r1 --out results/统计与图表 --name r1
python3 tools/analyze_prom.py results/r1/prometheus-r1.txt.gz results/统计与图表/jtl-summary-r1.csv results/r1 --out results/统计与图表 --name r1
# 第二阶段：240 秒测试固定统计第 60～240 秒
for g in m1 m2 m3 sweep pool overload; do
  python3 tools/analyze_jtl.py results/$g --out results/统计与图表 --name $g --fixed-window 60:240
  python3 tools/analyze_prom.py results/prometheus-phase2.txt.gz results/统计与图表/jtl-summary-$g.csv results/$g --out results/统计与图表 --name $g
done
python3 tools/aggregate_rounds.py results/统计与图表/jtl-summary-m{1,2,3}.csv --out results/统计与图表/main-rounds
# 第三阶段：复测与持续压测固定统计第 60～240 秒；逐级加压统计全部线程都在运行的时段
python3 tools/analyze_jtl.py results/n1 --out results/统计与图表 --name n1 --fixed-window 60:240
python3 tools/analyze_jtl.py results/probe --out results/统计与图表 --name probe
python3 tools/analyze_jtl.py results/x1 --out results/统计与图表 --name x1 --fixed-window 60:240
for g in n1 probe x1; do
  python3 tools/analyze_prom.py results/prometheus-phase3.txt.gz results/统计与图表/jtl-summary-$g.csv results/$g --out results/统计与图表 --name $g
done
python3 tools/make_charts_v2.py results/统计与图表      # 需要 matplotlib
python3 tools/build_report.py                           # 需要 python-docx 与 Google Chrome
```
