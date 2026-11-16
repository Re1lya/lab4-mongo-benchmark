# 实验四 MySQL 与 MongoDB 日志读写性能对比

基于 Spring Data JPA 与 Spring Data MongoDB 的对照实现。同一套日志模型、接口、请求数据和测试方法，分别接入 MySQL 9.2 和 MongoDB 7.0，在 5 台 2 核服务器（Docker Swarm）上用 JMeter 做负载测试和压力测试，并用 Prometheus 监控。

测试分两个阶段：第 1 轮是 10～400 线程的梯度探索；第二阶段固定参数（查询 50 线程、写入 100 线程，每次 240 秒，统计第 60～240 秒）做 3 轮主对比，并补充 MongoDB j:true 持久性对照、并发量调优、连接池调优和 600～1000 线程的过载与恢复。

> 结论见[实验报告](report/)；本页只做导航。Gitee 提交仓库：[W2097382371/lab4-mongo-benchmark](https://gitee.com/W2097382371/lab4-mongo-benchmark)（只含指导书要求的提交材料）。

## 目录

| 内容 | 位置 |
| --- | --- |
| 实验报告（PDF / 可编辑 Word） | [report/](report/) |
| 指导书要求逐条核查 | [report/实验四要求核查.md](report/实验四要求核查.md) |
| 操作手册（部署、数据、压测、监控、统计） | [docs/01-实验操作手册.md](docs/01-实验操作手册.md) |
| 知识笔记（原理与踩坑） | [docs/02-知识笔记.md](docs/02-知识笔记.md) |
| 实验过程记录（时间线、问题与解决） | [docs/03-实验过程记录.md](docs/03-实验过程记录.md) |
| 验收演示手册（改参数看曲线、现场查数据、常见问题） | [docs/04-验收演示.md](docs/04-验收演示.md) |
| 两套实现源码 | [logdemo/](logdemo/)：`logdemo-core`（共用接口与业务）、`logdemo-jpa`、`logdemo-mongo` |
| 数据库初始化脚本 | [db/mysql/](db/mysql/)、[db/mongo/](db/mongo/) |
| JMeter 测试计划与请求数据 | [jmeter/](jmeter/)：`WriteLog.jmx`、`ReadLog.jmx`、`data/` |
| 部署与测试脚本 | [deploy/](deploy/)：Swarm 部署文件、Prometheus 配置、装数/核对/压测/导出脚本 |
| 数据生成与统计工具 | [tools/](tools/) |
| 原始 JTL、Prometheus 监控数据与统计图表 | [results/](results/) |

## 接口

| 方法 | 路径 | 参数 | 成功响应 |
| --- | --- | --- | --- |
| POST | `/api/logs` | JSON 日志对象：`traceId`、`level`、`source`、`message`、`clientIp`、`createdAt`（可省略） | HTTP 201，`errno=1` |
| GET | `/api/logs` | `level`、`from`、`to`（ISO-8601，范围 [from, to)）、`page`（从 1 开始）、`size`（1–100） | HTTP 200，`errno=0` |

MySQL 版端口 8081，MongoDB 版端口 8082。JMeter 只需改 `-Jport`，JMX 文件不用修改。

## 快速复现

```bash
cd logdemo && mvn -B package                                   # 编译两套实现（含单元测试）
python3 tools/gen_data.py jmeter --out jmeter/data             # 重新生成 JMeter 请求数据（固定随机种子）
python3 tools/api_check.py --base http://<主机>:8081 --name jpa  # 接口检查，另一端口同理
```

完整步骤见[操作手册](docs/01-实验操作手册.md)。

## 说明

- 仓库不含任何账号密码：数据库和应用的密码在服务器上随机生成，保存在 Docker secret 中。
- 源码风格与返回格式沿用课程仓库 [mingqcn/spring-fundamentals](https://gitee.com/mingqcn/spring-fundamentals)（`ReturnObject`、`ReturnNo`、`PageDto`）。
- 报告成员：温家正、姚景云、杜奕含、陈浩贤。
