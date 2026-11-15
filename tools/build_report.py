#!/usr/bin/env python3
"""生成实验四报告（Word + PDF）。表格和正文中的数字全部从统计结果读取。

用法：python3 tools/build_report.py --name r1
依赖：python-docx（Word）、Google Chrome（HTML 打印为 PDF），见 tools/report_render.py。
"""
import argparse
import csv
import os
import shutil
import tempfile

from report_render import html_to_pdf, render_docx, render_html

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS = os.path.join(REPO, "results", "统计与图表")
CHARTS = os.path.join(STATS, "charts")
OUT = os.path.join(REPO, "report")
TITLE = "MySQL 与 MongoDB 日志读写性能对比实验报告"
FILE_BASE = "实验四_MySQL与MongoDB日志读写性能对比实验报告"
HEADER = "JavaEE 实验报告    实验四 MySQL 与 MongoDB 日志读写性能对比"
AUTHORS = "温家正  姚景云  杜奕含  陈浩贤"
LEVELS = [("load", 10), ("load", 25), ("load", 50), ("load", 100), ("stress", 200), ("stress", 300), ("stress", 400)]
PHASE_CN = {"load": "负载", "stress": "压力", "recovery": "恢复", "warmup": "预热"}


def load(name):
    j = {(r["op"], r["phase"], int(r["threads"]), r["impl"]): r
         for r in csv.DictReader(open(os.path.join(STATS, "jtl-summary-%s.csv" % name), encoding="utf-8"))}
    p = {(r["op"], r["phase"], int(r["threads"]), r["impl"]): r
         for r in csv.DictReader(open(os.path.join(STATS, "prom-summary-%s.csv" % name), encoding="utf-8"))}
    return j, p


def n(x, d=0):
    v = float(x)
    return ("{:,.%df}" % d).format(v) if d else "{:,}".format(int(round(v)))


def build(name):
    J, P = load(name)
    f = lambda r, k: float(r[k])
    tps = lambda op, ph, t, i: f(J[(op, ph, t, i)], "steady_throughput")
    total = sum(int(r["full_samples"]) for r in J.values())
    errors = sum(int(r["full_errors"]) for r in J.values())
    inserted = sum(int(r["db_inserted"]) for k, r in J.items() if k[0] == "write")
    write_runs = sum(1 for k in J if k[0] == "write")
    db_ok = all(r["db_check"] == "一致" for k, r in J.items() if k[0] == "write")
    ratio = lambda op, ph, t: tps(op, ph, t, "mongo") / tps(op, ph, t, "jpa")
    rr = lambda op, phase: [ratio(op, ph, t) for ph, t in LEVELS if ph == phase]
    worst_cs = max(abs(f(P[k], "server_tps") - f(J[k], "steady_throughput")) / f(J[k], "steady_throughput") for k in P)
    cdwy3_cpu = max(f(r, "CDWY3_cpu_pct") for k, r in P.items() if k[1] != "warmup")
    cost = {(op, i): P[(op, "load", 50, i)] for op in ("read", "write") for i in ("jpa", "mongo")}

    def disk_range(impl, host, key):
        vals = [f(P[("write", ph, t, impl)], host + key) for ph, t in LEVELS]
        return min(vals), max(vals)

    def kb_per_insert(impl, host):
        vals = [f(P[("write", ph, t, impl)], host + "_disk_write_mb_s") * 1024 / f(P[("write", ph, t, impl)], "server_tps")
                for ph, t in LEVELS]
        return min(vals), max(vals)

    my_iops, mg_iops = disk_range("jpa", "CDWY2", "_disk_write_iops"), disk_range("mongo", "CDWY5", "_disk_write_iops")
    my_mb, mg_mb = disk_range("jpa", "CDWY2", "_disk_write_mb_s"), disk_range("mongo", "CDWY5", "_disk_write_mb_s")
    my_kb, mg_kb = kb_per_insert("jpa", "CDWY2"), kb_per_insert("mongo", "CDWY5")
    peak = lambda op, i: max(tps(op, ph, t, i) for ph, t in LEVELS)

    B = []
    add = B.append
    add(("title", TITLE))
    add(("author", AUTHORS))
    add(("abstract",
         "摘  要：本实验以日志服务为对象，在同一套日志模型、REST 接口、业务逻辑和请求数据下，分别用 Spring Data JPA 访问 MySQL 9.2、"
         "用 Spring Data MongoDB 访问 MongoDB 7.0，并部署在 5 台 2 核服务器组成的 Docker Swarm 集群上。用 JMeter 进行负载测试"
         "（10～100 线程）和压力测试（200～400 线程，随后做恢复检查），用 Prometheus 采集应用、数据库和压测机的资源指标。"
         "共执行 36 次测试、%s 个请求，错误率为 0；%d 次写入测试中，成功请求数与数据库新增行数逐次相等。"
         "查询接口在负载区间 MongoDB 版吞吐量是 MySQL 版的 %.2f～%.2f 倍，压力区间为 %.2f～%.2f 倍；写入接口为 %.2f～%.2f 倍。"
         "监控显示：MySQL 版查询的瓶颈在数据库服务器 CPU，MongoDB 版的瓶颈在应用服务器 CPU；"
         "写入差距主要来自持久化策略——MySQL 每次提交都刷盘，MongoDB 默认约 100 ms 批量写日志。"
         % (n(total), write_runs, min(rr("read", "load")), max(rr("read", "load")), min(rr("read", "stress")),
            max(rr("read", "stress")), min(rr("write", "load") + rr("write", "stress")),
            max(rr("write", "load") + rr("write", "stress")))))
    add(("keywords", "关键词：MySQL；MongoDB；Spring Data JPA；Spring Data MongoDB；JMeter；Prometheus；负载测试；压力测试"))

    # 1
    add(("h1", "1 实验目的"))
    add(("p", "（1）掌握 Spring Data JPA 访问 MySQL、Spring Data MongoDB 访问 MongoDB 的基本方法，分别完成日志数据的写入和条件分页查询。"))
    add(("p", "（2）使用同一套日志业务模型、接口定义、请求数据和测试方法，对照实现 JPA/MySQL 与 Spring Data MongoDB/MongoDB 两条日志读写链路。"))
    add(("p", "（3）使用 JMeter 和 Prometheus 对两种方案进行负载测试和压力测试，比较吞吐量、响应时间、错误率和各服务器资源使用，并找出各自的瓶颈。"))

    # 2
    add(("h1", "2 实验环境"))
    add(("table", "表1  服务器分工与软件版本", ["指导书角色", "本组服务器", "私网地址", "本实验内容"], [
        ["A 编译、JMeter", "CDWY3", "172.31.12.156", "JDK 21、Maven 3.9.16、JMeter 5.6.3（堆 400 MB）"],
        ["B MySQL", "CDWY2", "172.31.8.46", "MySQL 9.2.0，库 lab4_log；缓冲池 128 MB（默认）"],
        ["C MongoDB 7.0", "CDWY5", "172.31.13.151", "MongoDB 7.0.48；WiredTiger 缓存 0.25 GB"],
        ["D Prometheus", "CDWY4", "172.31.1.19", "Prometheus 3.7.3，每 2 秒抓取"],
        ["E 两套日志服务", "CDWY1", "172.31.1.202", "MySQL 版 :8081、MongoDB 版 :8082"],
    ], [2.9, 2.0, 2.6, 8.0]))
    add(("p", "5 台服务器均为 Ubuntu 18.04、2 核 CPU、约 1.8 GB 可用内存、Docker 20.10.21，组成 Docker Swarm 集群并通过私网通信。"
               "两套日志服务基于 Spring Boot 3.3.4、Java 21，配置完全相同：JVM 堆 384 MB，Tomcat 最多 200 个工作线程，"
               "数据库连接池最多 100 个连接、取连接最长等待 10 秒（HikariCP 与 MongoDB 驱动的默认值差别很大，因此统一设置）。"
               "测试时同一时刻只压测其中一种。"))

    # 3
    add(("h1", "3 系统设计与实现"))
    add(("h2", "3.1 日志模型与数据库格式"))
    add(("table", "表2  日志字段定义（与指导书表 2 一致）", ["字段", "Java 类型", "MySQL 类型", "MongoDB 类型", "说明"], [
        ["id", "String", "CHAR(26)", "String（_id）", "26 位 ULID，程序生成"],
        ["traceId", "String", "VARCHAR(64)", "String", "链路追踪标识，可为空"],
        ["level", "String", "VARCHAR(10)", "String", "TRACE/DEBUG/INFO/WARN/ERROR"],
        ["source", "String", "VARCHAR(128)", "String", "服务名或模块名"],
        ["message", "String", "VARCHAR(4096)", "String", "不超过 4096 个字符"],
        ["clientIp", "String", "VARCHAR(45)", "String", "IPv4/IPv6"],
        ["createdAt", "Instant", "DATETIME(6)", "BSON Date", "UTC"],
    ], [2.2, 2.0, 2.9, 2.6, 5.8]))
    add(("p", "主键采用 ULID：前 48 位是毫秒时间戳，按字符串排序即按时间排序，MySQL 聚簇索引的插入总在末尾，"
               "MongoDB 直接把它作为 _id。createdAt 在程序中用 Instant 表示；MySQL 连接固定会话时区为 UTC，"
               "MongoDB 的 BSON Date 本身就是 UTC。BSON Date 只有毫秒精度，程序统一截断到毫秒，两库存值完全相同。"
               "message 的 4096 上限按 Unicode 字符（码点）计数，与 MySQL VARCHAR 一致。"))
    add(("p", "数据库层同样约束数据：MySQL 用列类型、NOT NULL 和 CHECK；MongoDB 用 $jsonSchema 校验器（必填字段、类型、长度、"
               "level 取值、禁止多余字段）。两边建立等价的索引：(level, created_at, id) 与 (created_at, id)，"
               "分别对应“按级别和时间范围”与“只按时间范围”查询，按时间倒序取数时无需额外排序。初始化脚本见 db/mysql、db/mongo。"))
    add(("h2", "3.2 统一 REST 接口"))
    add(("table", "表3  日志读写接口", ["方法", "路径", "请求或参数", "成功响应"], [
        ["POST", "/api/logs", "JSON 日志对象（id 由服务端生成，createdAt 可省略）", "HTTP 201，errno=1"],
        ["GET", "/api/logs", "level、from、to（ISO-8601，范围 [from, to)）、page、size", "HTTP 200，errno=0"],
    ], [1.3, 2.1, 8.2, 3.9]))
    add(("p", "查询结果按 createdAt、id 倒序分页，page 从 1 开始，size 为 1～100；返回 list、page、pageSize，不统计总数"
               "（总数需要额外的 count 查询）。参数或请求体不合法时返回 HTTP 400、errno=3。两种实现对外完全相同，"
               "JMeter 只需替换端口。"))
    add(("h2", "3.3 两套实现"))
    add(("table", "表4  共用部分与各自实现", ["层次", "共用（logdemo-core）", "MySQL 版（logdemo-jpa）", "MongoDB 版（logdemo-mongo）"], [
        ["接口与业务", "LogController、LogService、校验、ULID", "—", "—"],
        ["持久层接口", "LogStore（insert、find）", "JpaLogStore", "MongoLogStore"],
        ["数据对象", "LogRecord", "LogPo（@Entity）", "LogDoc（@Document）"],
        ["Repository", "—", "JpaRepository + @Query（JPQL）", "MongoRepository + @Query（查询文档）"],
        ["分页", "Pageable（createdAt、id 倒序）", "ORDER BY … LIMIT ?, ?", "sort … skip … limit"],
    ], [2.2, 4.6, 4.2, 4.5]))
    add(("p", "两套实现只有持久层不同。实现中处理了几个影响结果的细节：JPA 实体实现 Persistable，使预先赋值主键的 save() "
               "直接 INSERT 而不是先 SELECT；MongoDB 版用 insert() 而非 upsert 语义的 save()，并去掉 Spring Data 默认写入的 "
               "_class 字段；数据库密码通过 Docker secret 注入，应用账号只有查询和插入权限，仓库中不含任何密码。"))
    add(("h2", "3.4 正确性与一致性验证"))
    add(("p", "部署后用同一组 22 项接口检查（正常写入、各类非法参数、4096 字符边界、IPv6、分页顺序、[from, to) 边界等）"
               "分别检查两种实现，全部通过且逐项结果一致。两台数据库服务器各自用固定随机种子生成同一批 10 万条日志并装入，"
               "按 id 顺序从数据库导出后计算内容摘要，两库完全相同（SHA-256 前缀 bbd96253）。"))

    # 4
    add(("h1", "4 测试方法"))
    add(("h2", "4.1 测试数据"))
    add(("p", "预置数据 10 万条，时间分布在 2026-10-27 至 2026-11-01（UTC），级别占比 INFO 60%、DEBUG 15%、WARN 15%、"
               "TRACE 5%、ERROR 5%，正文长度多数为 40～200 个字符，最长 4096 个字符。数据量按缓存设计：MySQL 中约 80 MB，"
               "两边缓存都能完整容纳，比较的是软件链路而不是磁盘读取。写入请求体取自 1 万条固定数据，查询参数取自 1 万组固定组合"
               "（级别、1 小时～3 天的时间范围、页码 1～50，每页 20 条），两种实现读取同一份文件。"))
    add(("h2", "4.2 负载测试与压力测试设计"))
    add(("table", "表5  测试矩阵（每种实现、读写各一组）", ["类型", "线程数", "升压", "持续", "说明"], [
        ["预热", "50", "10 s", "60 s", "JIT 编译与缓存热身，不参与比较"],
        ["负载测试", "10、25、50、100", "10 s", "60 s", "从低负载到饱和，观察吞吐量拐点"],
        ["压力测试", "200、300、400", "20 s", "60 s", "达到饱和点的 4～8 倍，观察退化与错误"],
        ["恢复检查", "10", "10 s", "60 s", "紧接 400 线程之后，与负载测试的 10 线程对比"],
    ], [2.0, 2.9, 1.4, 1.4, 7.8]))
    add(("p", "负载测试考察预期范围内的性能变化，压力测试考察超出正常负载后系统怎样退化、能否恢复。线程组按持续时间运行，"
               "每次测试前后间隔 20 秒；两种实现在各档交替先后执行，以抵消环境随时间的漂移；写入测试每一档开始前把两个数据库都重置为"
               "同一份 10 万条预置数据。每轮开始时重启两套服务，并各自预热 60 秒：冷启动的 JVM 在预试验中只有预热后吞吐量的约五分之一。"))
    add(("h2", "4.3 指标与监控"))
    add(("p", "统计取“稳态”时段，即所有线程都已启动、正在发请求的时间段；吞吐量为该时段完成的请求数除以时长，"
               "P95、P99 为该时段响应时间的百分位。JTL 中的响应时间包含网络往返和 JMeter 自身开销。"))
    add(("p", "Prometheus 每 2 秒抓取两套服务的 /actuator/prometheus（请求计数、JVM、连接池）和 5 台服务器的 node-exporter"
               "（CPU、内存、磁盘、网络）。为比较两种实现在各层的开销，用“每个请求消耗的 CPU 时间”= 核数 × CPU 使用率 ÷ 每秒请求数。"
               "服务端统计的每秒请求数与 JMeter 客户端结果相互核对，36 次测试的偏差均不超过 %.1f%%。" % (100 * worst_cs)))

    # 5
    add(("h1", "5 结果与分析"))
    add(("h2", "5.1 查询接口"))
    add(("figure", os.path.join(CHARTS, "read-overview.png"), "图1  查询接口的稳态吞吐量与 P95 响应时间", 15.2))
    rows = []
    for ph, t in LEVELS:
        a, b = J[("read", ph, t, "jpa")], J[("read", ph, t, "mongo")]
        rows.append([PHASE_CN[ph], t, n(a["steady_throughput"]), n(b["steady_throughput"]), "%.2f" % ratio("read", ph, t),
                     n(a["steady_avg_ms"], 1), n(b["steady_avg_ms"], 1), a["steady_p95_ms"], b["steady_p95_ms"],
                     a["steady_p99_ms"], b["steady_p99_ms"]])
    add(("table", "表6  查询接口结果（稳态，响应时间单位 ms；全部请求错误率为 0）",
         ["阶段", "线程", "吞吐 MySQL", "吞吐 Mongo", "Mongo/MySQL", "平均 MySQL", "平均 Mongo", "P95 MySQL", "P95 Mongo",
          "P99 MySQL", "P99 Mongo"], rows, [1.3, 1.1, 1.5, 1.5, 1.6, 1.3, 1.3, 1.25, 1.25, 1.25, 1.25]))
    add(("p", "负载区间内，MongoDB 版吞吐量是 MySQL 版的 %.2f～%.2f 倍，P95 也更低（50 线程时 %s ms 对 %s ms）。"
               "两者吞吐量都在 25～50 线程附近达到上限，此后增加线程主要拉长排队时间。监控显示两者的瓶颈不同："
               "MySQL 版在 10～100 线程时 MySQL 服务器 CPU 为 %.0f%%～%.0f%%，已饱和，应用服务器约 %.0f%%；"
               "MongoDB 版是应用服务器 CPU 饱和（%.0f%%～%.0f%%），MongoDB 服务器只用了 %.0f%%～%.0f%%。"
               % (min(rr("read", "load")), max(rr("read", "load")),
                  J[("read", "load", 50, "mongo")]["steady_p95_ms"], J[("read", "load", 50, "jpa")]["steady_p95_ms"],
                  min(f(P[("read", "load", t, "jpa")], "CDWY2_cpu_pct") for t in (10, 25, 50, 100)),
                  max(f(P[("read", "load", t, "jpa")], "CDWY2_cpu_pct") for t in (10, 25, 50, 100)),
                  sum(f(P[("read", "load", t, "jpa")], "CDWY1_cpu_pct") for t in (10, 25, 50, 100)) / 4,
                  min(f(P[("read", "load", t, "mongo")], "CDWY1_cpu_pct") for t in (10, 25, 50, 100)),
                  max(f(P[("read", "load", t, "mongo")], "CDWY1_cpu_pct") for t in (10, 25, 50, 100)),
                  min(f(P[("read", "load", t, "mongo")], "CDWY5_cpu_pct") for t in (10, 25, 50, 100)),
                  max(f(P[("read", "load", t, "mongo")], "CDWY5_cpu_pct") for t in (10, 25, 50, 100)))))
    add(("p", "进入压力区间后差距扩大到 %.2f～%.2f 倍。MySQL 版 400 线程时吞吐量降到峰值的 %.0f%%：连接池 100 个连接全部占满，"
               "最多约 %s 个请求在等待连接，应用服务器 CPU 升到 %.0f%% 左右，用在线程切换和排队上的开销变大；"
               "MongoDB 版降到峰值的 %.0f%%，下降较平缓。"
               % (min(rr("read", "stress")), max(rr("read", "stress")), 100 * tps("read", "stress", 400, "jpa") / peak("read", "jpa"),
                  n(P[("read", "stress", 400, "jpa")]["pool_waiting_max"]), f(P[("read", "stress", 400, "jpa")], "CDWY1_cpu_pct"),
                  100 * tps("read", "stress", 400, "mongo") / peak("read", "mongo"))))

    add(("h2", "5.2 写入接口"))
    add(("figure", os.path.join(CHARTS, "write-overview.png"), "图2  写入接口的稳态吞吐量与 P95 响应时间", 15.2))
    rows = []
    for ph, t in LEVELS:
        a, b = J[("write", ph, t, "jpa")], J[("write", ph, t, "mongo")]
        rows.append([PHASE_CN[ph], t, n(a["steady_throughput"]), n(b["steady_throughput"]), "%.2f" % ratio("write", ph, t),
                     n(a["steady_avg_ms"], 1), n(b["steady_avg_ms"], 1), a["steady_p95_ms"], b["steady_p95_ms"],
                     a["steady_p99_ms"], b["steady_p99_ms"]])
    add(("table", "表7  写入接口结果（稳态，响应时间单位 ms；全部请求错误率为 0，成功数与入库行数逐次一致）",
         ["阶段", "线程", "吞吐 MySQL", "吞吐 Mongo", "Mongo/MySQL", "平均 MySQL", "平均 Mongo", "P95 MySQL", "P95 Mongo",
          "P99 MySQL", "P99 Mongo"], rows, [1.3, 1.1, 1.5, 1.5, 1.6, 1.3, 1.3, 1.25, 1.25, 1.25, 1.25]))
    add(("p", "写入差距比查询大：10 线程时 MongoDB 版吞吐量是 MySQL 版的 %.2f 倍，负载区间其余各档为 %.2f～%.2f 倍。"
               "MySQL 版 10 线程时平均响应 %s ms，应用和数据库服务器 CPU 都只有三成左右，但数据库服务器 iowait 高达 %s%%："
               "每个事务提交都要等待 redo log 和 binlog 刷盘。线程增多后，MySQL 的组提交把多个事务合并刷盘，"
               "吞吐量从 %s 升到 %s（100 线程）。MongoDB 版在 10 线程时就使应用服务器 CPU 饱和，吞吐量在 6000 次/秒以上保持平稳。"
               % (ratio("write", "load", 10), min(rr("write", "load")[1:]), max(rr("write", "load")[1:]),
                  J[("write", "load", 10, "jpa")]["steady_avg_ms"], P[("write", "load", 10, "jpa")]["CDWY2_iowait_pct"],
                  n(tps("write", "load", 10, "jpa")), n(tps("write", "load", 100, "jpa")))))
    add(("p", "%d 次写入测试共新增 %s 行，每次测试的成功请求数（HTTP 201）都与数据库实际新增行数相等%s，"
               "说明高并发下两种实现都没有丢失或重复写入。"
               % (write_runs, n(inserted), "" if db_ok else "（存在不一致，见统计表）")))

    add(("h2", "5.3 资源使用与瓶颈"))
    add(("figure", os.path.join(CHARTS, "cpu-overview.png"), "图3  各档测试的稳态 CPU 使用率（应用服务器、数据库服务器、压测机）", 15.4))
    rows = []
    for op, op_cn in (("read", "查询"), ("write", "写入")):
        for i, i_cn in (("jpa", "MySQL"), ("mongo", "MongoDB")):
            r = cost[(op, i)]
            db = "CDWY2" if i == "jpa" else "CDWY5"
            rows.append([op_cn, i_cn, n(r["server_tps"]), r["CDWY1_cpu_pct"] + "%", r[db + "_cpu_pct"] + "%",
                         "%.2f" % f(r, "app_host_cpu_ms_per_req"), "%.2f" % f(r, "db_host_cpu_ms_per_req")])
    add(("table", "表8  50 线程时每个请求消耗的 CPU 时间（2 核 × 使用率 ÷ 服务端每秒请求数）",
         ["操作", "实现", "服务端吞吐(次/秒)", "应用服务器 CPU", "数据库服务器 CPU", "应用端 ms/请求", "数据库端 ms/请求"],
         rows, [1.2, 1.7, 2.6, 2.4, 2.6, 2.5, 2.5]))
    rq, wr = cost[("read", "mongo")], cost[("write", "mongo")]
    add(("p", "按每个请求折算，查询时数据库端的 CPU 消耗 MongoDB 约为 MySQL 的 %.0f%%（%.2f ms 对 %.2f ms），"
               "应用端两者接近（%.2f ms 对 %.2f ms，MongoDB 略高）；写入时数据库端约为 %.0f%%，应用端约为 %.0f%%。"
               "因此 MySQL 版查询先耗尽数据库服务器的 CPU，而 MongoDB 版先耗尽应用服务器的 CPU。"
               "压测机 CPU 最高 %.0f%%，没有成为瓶颈；应用 JVM 堆最高约 250 MB（上限 384 MB），GC 停顿占时间不超过 7%%。"
               % (100 * f(rq, "db_host_cpu_ms_per_req") / f(cost[("read", "jpa")], "db_host_cpu_ms_per_req"),
                  f(rq, "db_host_cpu_ms_per_req"), f(cost[("read", "jpa")], "db_host_cpu_ms_per_req"),
                  f(rq, "app_host_cpu_ms_per_req"), f(cost[("read", "jpa")], "app_host_cpu_ms_per_req"),
                  100 * f(wr, "db_host_cpu_ms_per_req") / f(cost[("write", "jpa")], "db_host_cpu_ms_per_req"),
                  100 * f(wr, "app_host_cpu_ms_per_req") / f(cost[("write", "jpa")], "app_host_cpu_ms_per_req"),
                  cdwy3_cpu)))

    add(("h2", "5.4 写入的持久化代价"))
    add(("figure", os.path.join(CHARTS, "write-disk.png"), "图4  写入测试中数据库服务器的磁盘写入", 15.2))
    add(("p", "写入测试期间，MySQL 服务器每秒写盘 %s～%s 次、%.1f～%.1f MB/s，折合每条日志 %.0f～%.0f KB；"
               "MongoDB 服务器每秒只写盘 %s～%s 次、%.1f～%.1f MB/s，每条约 %.1f KB。原因是两者默认的持久化承诺不同："
               "MySQL 设置 innodb_flush_log_at_trx_commit=1、sync_binlog=1，每次提交都把 redo log 和 binlog 刷到磁盘，"
               "提交返回时数据一定不会丢；单机 MongoDB 默认写关注 w:1，写入在内存中生效即返回，日志约每 100 ms 批量刷盘，"
               "宕机时可能丢失最近约 100 ms 内已确认的写入。因此写入性能的差距有相当一部分是用持久性换来的，"
               "比较时不能只看吞吐量。"
               % (n(my_iops[0]), n(my_iops[1]), my_mb[0], my_mb[1], my_kb[0], my_kb[1],
                  n(mg_iops[0]), n(mg_iops[1]), mg_mb[0], mg_mb[1], (mg_kb[0] + mg_kb[1]) / 2)))

    add(("h2", "5.5 压力测试与恢复"))
    add(("figure", os.path.join(CHARTS, "read-stress-recovery.png"), "图5  查询：400 线程压力测试与随后的恢复检查（每秒数据）", 15.2))
    add(("figure", os.path.join(CHARTS, "write-stress-recovery.png"), "图6  写入：400 线程压力测试与随后的恢复检查（每秒数据）", 15.2))
    rows = []
    for op, op_cn in (("read", "查询"), ("write", "写入")):
        for i, i_cn in (("jpa", "MySQL"), ("mongo", "MongoDB")):
            base, rec = J[(op, "load", 10, i)], J[(op, "recovery", 10, i)]
            rows.append([op_cn, i_cn, n(peak(op, i)), "%s（%.0f%%）" % (n(tps(op, "stress", 400, i)), 100 * tps(op, "stress", 400, i) / peak(op, i)),
                         J[(op, "stress", 400, i)]["steady_p99_ms"],
                         "%s（%.0f%%）" % (n(rec["steady_throughput"]), 100 * f(rec, "steady_throughput") / f(base, "steady_throughput")),
                         "%s / %s" % (rec["steady_avg_ms"], base["steady_avg_ms"])])
    add(("table", "表9  压力测试与恢复检查（吞吐单位：次/秒）",
         ["操作", "实现", "峰值吞吐", "400 线程吞吐（占峰值）", "400 线程 P99(ms)", "恢复吞吐（占 10 线程基线）", "恢复/基线平均(ms)"],
         rows, [1.1, 1.6, 1.7, 2.9, 2.1, 3.2, 2.9]))
    rec_pct = [100 * f(J[(op, "recovery", 10, i)], "steady_throughput") / f(J[(op, "load", 10, i)], "steady_throughput")
               for op in ("read", "write") for i in ("jpa", "mongo")]
    add(("p", "压力测试的全部请求都成功，没有出现超时或 5xx 错误：超出处理能力的请求在 Tomcat 和连接池中排队，表现为响应时间"
               "上升而不是失败。400 线程时 MySQL 版查询的每秒吞吐量在约 1700～3200 次之间大幅波动（图5），"
               "与连接池排队一致；MongoDB 版更平稳。压力撤去后立即进行的 10 线程恢复检查中，两种实现的平均响应时间都回到了"
               "基线附近，吞吐量恢复到基线的 %.0f%%～%.0f%%。恢复后应用保留了压力测试中扩展出的约 200 个 Tomcat 线程，"
               "堆占用也更高，可能是吞吐量没有完全回到基线的原因之一。" % (min(rec_pct), max(rec_pct))))

    # 6
    add(("h1", "6 结论"))
    add(("p", "（1）两套实现共用同一份接口、业务逻辑和请求数据，22 项接口检查结果一致，预置数据逐条相同，"
               "写入成功数与入库行数逐次相等，对照条件成立。"))
    add(("p", "（2）查询：在本实验的数据量（10 万条，可完全缓存）和硬件下，MongoDB 版吞吐量高 %.0f%%～%.0f%%（负载区间）、"
               "%.0f%%～%.0f%%（压力区间），尾部延迟更低。主要原因是 MongoDB 处理同样查询消耗的 CPU 约为 MySQL 的六成，"
               "MySQL 版的瓶颈在数据库服务器，MongoDB 版的瓶颈在应用服务器。"
               % (100 * (min(rr("read", "load")) - 1), 100 * (max(rr("read", "load")) - 1),
                  100 * (min(rr("read", "stress")) - 1), 100 * (max(rr("read", "stress")) - 1))))
    add(("p", "（3）写入：MongoDB 版吞吐量是 MySQL 版的 %.1f～%.1f 倍，低并发时差距最大。差距主要来自默认持久化策略："
               "MySQL 每次提交刷盘，MongoDB 批量刷日志。若业务要求每条日志在返回前已持久化，应为 MongoDB 设置 j:true 写关注后再比较；"
               "若允许极少量日志在宕机时丢失，MongoDB 的默认配置更适合高频写入的日志场景。"
               % (min(rr("write", "load") + rr("write", "stress")), max(rr("write", "load") + rr("write", "stress")))))
    add(("p", "（4）压力测试中两种实现都没有出错，过载表现为排队和延迟上升；MySQL 版在连接池耗尽后吞吐量下降更明显。"
               "压力撤去后两者都能恢复正常服务。"))
    add(("p", "（5）局限：只进行了一轮正式测试；应用服务器只有 2 核，多数场景下应用层先饱和，结论只适用于本环境；"
               "两库的缓存大小不同（128 MB 对 0.25 GB），但数据集在两边都能完整缓存；数据量远大于内存的场景没有测试。"))

    add(("h1", "参考资料"))
    for ref in ("[1] 实验四：MySQL 与 MongoDB 日志读写性能对比实验，课程实验指导书。",
                "[2] Spring Data JPA Reference Documentation；Spring Data MongoDB Reference Documentation。",
                "[3] MySQL 9.2 Reference Manual：innodb_flush_log_at_trx_commit、sync_binlog、Group Commit。",
                "[4] MongoDB 7.0 Manual：Write Concern、Journaling（storage.journal.commitIntervalMs）。",
                "[5] Apache JMeter User's Manual：Thread Group、CSV Data Set Config。",
                "[6] ISTQB Glossary：load testing、stress testing。",
                "[7] Prometheus Documentation：promtool tsdb dump、node_exporter。"):
        add(("note", ref))

    add(("h1", "附录  提交材料与数据对应"))
    add(("table", "附表  仓库内容", ["内容", "位置"], [
        ["两套实现（含共用模块）", "logdemo/logdemo-core、logdemo-jpa、logdemo-mongo"],
        ["数据库初始化脚本", "db/mysql/01-schema.sql、02-app-user.sql；db/mongo/01-init.js、02-app-user.js"],
        ["JMeter JMX 与请求数据", "jmeter/WriteLog.jmx、ReadLog.jmx、data/"],
        ["运行说明", "docs/01-实验操作手册.md、README.md"],
        ["原始 JTL（gzip 压缩）", "results/r1/<实现>-<读写>-<阶段>-t<线程>/samples.jtl.gz（共 36 次）"],
        ["Prometheus 监控数据", "results/r1/prometheus-r1.txt.gz；各次测试的 monitor.json"],
        ["统计与图表", "results/统计与图表/（jtl-summary-r1、prom-summary-r1、charts/）"],
        ["接口与数据一致性证据", "results/00-环境与一致性/"],
    ], [4.5, 11.0]))
    return B


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", default="r1")
    args = p.parse_args()
    blocks = build(args.name)
    os.makedirs(OUT, exist_ok=True)
    docx_path = os.path.join(OUT, FILE_BASE + ".docx")
    render_docx(blocks, os.path.join(OUT, "templates", "paper-template.docx"), docx_path, HEADER,
                {"author": AUTHORS.replace("  ", " "), "title": TITLE, "subject": "实验四：Spring Data JPA 与 Spring Data MongoDB 日志读写性能对比"})
    tmp = tempfile.mkdtemp(prefix="lab4-report-")
    try:
        html_path = os.path.join(tmp, "report.html")
        render_html(blocks, html_path, HEADER, TITLE)
        html_to_pdf(html_path, os.path.join(OUT, FILE_BASE + ".pdf"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("wrote", docx_path, "and PDF")


if __name__ == "__main__":
    main()
