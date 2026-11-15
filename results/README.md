# 实验数据

## 目录

| 位置 | 内容 |
| --- | --- |
| `00-环境与一致性/` | 部署后的接口检查（两种实现各 22 项及逐项比较）、两库预置数据的生成摘要与导出摘要 |
| `r1/<实现>-<读写>-<阶段>-t<线程数>/` | 第 1 轮正式测试，每次测试一个目录，共 36 个 |
| `r1/prometheus-r1.txt.gz` | 测试时段（2026-11-15 12:38–13:38 UTC）的 Prometheus 原始样本 |
| `统计与图表/` | 由原始数据计算出的统计表和图表 |

目录名示例：`jpa-read-load-t50` = MySQL 版、查询、负载测试、50 线程；`mongo-write-stress-t400` = MongoDB 版、写入、压力测试、400 线程。阶段有 `warmup`（预热，不参与比较）、`load`、`stress`、`recovery`（400 线程之后的 10 线程恢复检查）。

## 每次测试目录中的文件

| 文件 | 内容 |
| --- | --- |
| `samples.jtl.gz` | **JMeter 原始 JTL**（CSV 格式，每个请求一行），gzip 压缩；`gunzip -k samples.jtl.gz` 得到原文件 |
| `params.txt` | 测试计划、目标端口、线程数、升压/持续秒数、JMeter 堆设置 |
| `start.txt` / `end.txt` | 测试开始、结束时间（UTC），用于对应 Prometheus 监控时间段 |
| `db-rows.txt` | 仅写入测试：测试前后数据库行数与新增行数（应等于 HTTP 201 的请求数） |
| `monitor.json` | 该次测试的监控时间序列：各服务器 CPU、应用 CPU、JVM 线程、连接池占用与等待 |

## 统计与图表

| 文件 | 内容 |
| --- | --- |
| `jtl-summary-r1.csv` / `.md` | 每次测试的样本数、错误数、稳态吞吐量、平均/P50/P90/P95/P99/最大响应时间、入库核对 |
| `prom-summary-r1.csv` | 每次测试稳态时段的各服务器 CPU/iowait/内存、数据库磁盘写入、JVM 与连接池、服务端每秒请求数、每请求 CPU 时间 |
| `charts/*.png` | 报告中的图 1～图 6 |

## 重新计算

```bash
python3 tools/analyze_jtl.py results/r1 --out results/统计与图表 --name r1
python3 tools/analyze_prom.py results/r1/prometheus-r1.txt.gz results/统计与图表/jtl-summary-r1.csv results/r1 --out results/统计与图表 --name r1
python3 tools/make_charts.py results/统计与图表 results/r1 --name r1      # 需要 matplotlib
```

“稳态”指所有线程都在运行的时间段（JTL 中 `grpThreads` 等于设定线程数）。
