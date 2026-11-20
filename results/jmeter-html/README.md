# JMeter HTML 报告（主对比、j:true 与持续压测）

用 JMeter 5.6.3 自带的报告生成器（`jmeter -g`）生成的网页报告，共 9 份：

| 目录 | 内容 |
| --- | --- |
| `n1/` | 主对比：查询 50 线程、写入 100 线程，以及 MongoDB j:true 写入 100 线程 |
| `x1/` | 最多线程数下的持续压测：查询 400 线程、写入 2000 线程 |

GitHub、Gitee 的网页不会直接显示这些页面：下载或克隆仓库后，用浏览器打开本目录的 `index.html`（汇总表，可点开每一份），或直接打开 `<组>/<测试名>/index.html`。

## 统计口径

- 每份只包含该测试统计区间（第 60～240 秒）内开始的请求，与实验报告相同。逐份核对：样本数、错误数、平均、P50/P90/P95/P99、最大响应时间与 `results/统计与图表/jtl-summary-*.csv` 一致；吞吐量相差不超过 0.5%，因为 JMeter 用“第一个请求开始到最后一个请求结束”作时间跨度（本组按 180 秒计算），高并发时单个请求耗时接近 1 秒，差别略大。
- 百分位用全部请求计算（`jmeter.reportgenerator.statistic_window=-1`，默认只用最后 2 万个请求）；随时间变化的曲线按 1 秒取点（`overall_granularity=1000`，默认 1 分钟）。
- JTL 为了减小体积没有保存 threadName、responseMessage、sentBytes 等列。生成时只在临时副本里补上 threadName（“查询线程组 1-1”或“写入线程组 1-1”，活跃线程数曲线的数值来自 grpThreads）和 responseMessage（按状态码填 OK/Created），原始 JTL 未改动。JTL 没有发送字节数，所以 Sent KB/sec 显示为 0。
- 完整的原始数据（含升压和降压）见各测试目录的 `samples.jtl.gz`。

报告中引用的截图由 `python3 tools/jmeter_html_shots.py` 生成（需要 Google Chrome）：首页 Dashboard 存为 `results/统计与图表/charts/jmeter-<组>-<测试名>.png`，Response Time Percentiles 图存为 `jmeter-<组>-<测试名>-percentiles.png`。

## 重新生成

需要 JMeter 5.6（`jmeter` 在 PATH 中）和 Python 3.6 以上，本组在 CDWY3 上运行：

```bash
items=()
for r in jpa-read-main-t50 mongo-read-main-t50 jpa-write-main-t100 mongo-write-main-t100 mongoj-write-main-t100; do items+=("n1/$r"); done
for r in jpa-read-maxload-t400 mongo-read-maxload-t400 jpa-write-maxload-t2000 mongo-write-maxload-t2000; do items+=("x1/$r"); done
python3 tools/jmeter_html.py --results results --summaries results/统计与图表 --out results/jmeter-html "${items[@]}"
```
