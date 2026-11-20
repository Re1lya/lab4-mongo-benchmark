#!/usr/bin/env python3
"""生成实验四报告（Word + PDF）。正文以组员 11-17 的修改稿为底稿，只写按课程 11-19 更新的监控配置所做的测试；
表格和正文中的数字全部从统计结果读取。

用法：python3 tools/build_report.py
需要 results/统计与图表/ 下的 jtl-summary-{n1,probe,x1}.csv、prom-summary-{n1,probe,x1}.csv 和 charts/（tools/make_charts.py 生成），
以及 results/probe/probe.log、choice.txt。依赖：python-docx（Word）、Google Chrome（HTML 打印为 PDF），见 report_render.py。
"""
import csv
import os
import re
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
MAIN_T = {"read": 50, "write": 100}
IMPL_CN = {"jpa": "MySQL", "mongo": "MongoDB", "mongoj": "MongoDB j:true"}
OP_CN = {"read": "查询", "write": "写入"}


def table(name, kind="jtl"):
    path = os.path.join(STATS, "%s-summary-%s.csv" % (kind, name))
    return {(r["op"], r["phase"], int(r["threads"]), r["impl"]): r for r in csv.DictReader(open(path, encoding="utf-8"))}


def n(x, d=0):
    v = float(x)
    return ("{:,.%df}" % d).format(v) if d else "{:,}".format(int(round(v)))


def f(r, k):
    return float(r[k])


def pct(a, b):
    return 100.0 * a / b


def span(vals, fmt="%.0f%%"):
    """数值范围的文字：相同时只写一个值。"""
    a, b = fmt % min(vals), fmt % max(vals)
    return a if a == b else a + "～" + b


def has(r, k="steady_throughput"):
    return r.get(k) not in (None, "", "nan")


def db_host(impl):
    return "CDWY2" if impl == "jpa" else "CDWY5"


def probe_rows():
    """results/probe/probe.log：每一级一行，含是否通过。"""
    rows = []
    for line in open(os.path.join(REPO, "results", "probe", "probe.log"), encoding="utf-8"):
        m = re.match(r"(\w+) (read|write) (t=.*)$", line.strip())
        if m:
            kv = dict(x.split("=", 1) for x in m.group(3).split() if "=" in x)
            rows.append(dict(kv, impl=m.group(1), op=m.group(2)))
    return rows


def probe_choice():
    path = os.path.join(REPO, "results", "probe", "choice.txt")
    return {k: int(v) for k, v in (line.strip().split("=") for line in open(path, encoding="utf-8") if "=" in line)}


def html_reports():
    root = os.path.join(REPO, "results", "jmeter-html")
    return sum(1 for d, _, files in os.walk(root) if "index.html" in files and d != root)


def jmeter_figs(add, CHARTS, items, first):
    """JMeter HTML 报告截图（tools/jmeter_html_shots.py 生成）：每项测试两张，首页 Dashboard 与 Response Time Percentiles。"""
    k = first
    for group, name, text in items:
        add(("figure", os.path.join(CHARTS, "jmeter-%s-%s.png" % (group, name)),
             "图%d  JMeter 报告：%s（results/jmeter-html/%s/%s）" % (k, text, group, name), 14.5))
        add(("figure", os.path.join(CHARTS, "jmeter-%s-%s-percentiles.png" % (group, name)),
             "图%d  Response Time Percentiles：%s" % (k + 1, text), 14.5))
        k += 2


def build():
    NJ, NP = table("n1"), table("n1", "prom")          # 主对比与 j:true（查询 50、写入 100 线程）
    QJ, QP = table("probe"), table("probe", "prom")    # 最多同时运行线程数逐级加压（未通过的一级按整次测试统计监控）
    XJ, XP = table("x1"), table("x1", "prom")          # 最多线程数下持续压测与之后的恢复检查
    PR, NMAX = probe_rows(), probe_choice()

    all_j = [NJ, QJ, XJ]
    tests = sum(len(t) for t in all_j)
    total = sum(int(r["full_samples"]) for t in all_j for r in t.values())
    errors = sum(int(r["full_errors"]) for t in all_j for r in t.values())
    writes_n = sum(1 for t in all_j for k in t if k[0] == "write")
    writes = [r for t in all_j for k, r in t.items() if k[0] == "write" and r["db_check"]]
    assert all(r["db_check"] == "一致" for r in writes)
    devs = [abs(f(p[k], "server_tps") - f(j[k], "steady_throughput")) / f(j[k], "steady_throughput")
            for j, pp in ((NJ, NP), (QJ, QP), (XJ, XP)) for p in [pp] for k in p
            if k in j and has(j[k]) and p[k]["server_tps"] and p[k].get("window") != "full-run"]

    nj = lambda op, impl, k="steady_throughput": f(NJ[(op, "main", MAIN_T[op], impl)], k)
    npm = lambda op, impl, k: f(NP[(op, "main", MAIN_T[op], impl)], k)
    nraw = lambda op, impl, k: NJ[(op, "main", MAIN_T[op], impl)][k]
    ratio = lambda op, impl="mongo": nj(op, impl) / nj(op, "jpa")
    x = lambda op, impl, k: f(XJ[(op, "maxload", NMAX[op], impl)], k)
    xr = [x(op, i, "steady_avg_ms") / nj(op, i, "steady_avg_ms") for op in ("read", "write") for i in ("jpa", "mongo")]
    rj, rm = ("read", "jpa"), ("read", "mongo")
    wj, wm, wjj = ("write", "jpa"), ("write", "mongo"), ("write", "mongoj")

    def kb_insert_n(impl):
        r = NP[("write", "main", 100, impl)]
        return f(r, db_host(impl) + "_disk_write_mb_s") * 1024 / f(r, "server_tps")

    B = []
    add = B.append
    add(("title", TITLE))
    add(("author", AUTHORS))
    add(("abstract",
         "摘  要：本实验在相同日志模型、REST 接口、业务逻辑和请求数据下，比较 Spring Data JPA/MySQL 9.2 与 Spring Data "
         "MongoDB/MongoDB 7.0 两条日志读写链路。系统部署于 5 台 2 核服务器，使用 JMeter 施加负载，并按课程 11-19 更新的 Prometheus "
         "配置（每 1 秒采集，CPU 使用率取 2 秒平均）监控各服务器资源。测试包括查询 50 线程、写入 100 线程的主对比和 MongoDB j:true "
         "写关注对照；并借鉴其他组的做法，从 400 线程起逐级加压，找出两种实现都能让全部线程同时运行且零错误的最高线程数（查询 %d、"
         "写入 %d，查询受 2 核压测机限制），在该线程数下持续压测 240 秒并做恢复检查。%d 次测试共处理 %s 个请求，%s。主对比中，"
         "MongoDB 版查询吞吐量为 MySQL 版的 %.2f 倍，P99 为 %s ms 对 %s ms；写入吞吐量为 %.2f 倍。启用 j:true 后，MongoDB 写入吞吐量"
         "为默认配置的 %.0f%%，仍为 MySQL 版的 %.2f 倍。查询时 MySQL 版数据库服务器 CPU 为 %.0f%%，MongoDB 版应用服务器 CPU 为 "
         "%.0f%%，分别是两种实现的瓶颈。最高线程数下两种实现仍处理了全部请求，但吞吐量没有提高，平均响应时间升至主对比的 %.0f～%.0f 倍。"
         % (NMAX["read"], NMAX["write"], tests, n(total), "错误数为 0" if errors == 0 else "错误数为 %s" % n(errors),
            ratio("read"), nraw(*rm, "steady_p99_ms"), nraw(*rj, "steady_p99_ms"), ratio("write"),
            pct(nj(*wjj), nj(*wm)), ratio("write", "mongoj"),
            npm(*rj, "CDWY2_cpu2s_avg"), npm(*rm, "CDWY1_cpu2s_avg"), min(xr), max(xr))))
    add(("keywords", "关键词：MySQL；MongoDB；Spring Data JPA；Spring Data MongoDB；JMeter；Prometheus；写关注；负载测试；压力测试"))

    # 1
    add(("h1", "1 实验目的"))
    add(("p", "（1）掌握 Spring Data JPA 访问 MySQL、Spring Data MongoDB 访问 MongoDB 的基本方法，分别完成日志数据的写入和条件分页查询。"))
    add(("p", "（2）使用同一套日志业务模型、接口定义、请求数据和测试方法，对照实现 JPA/MySQL 与 Spring Data MongoDB/MongoDB 两条日志读写链路。"))
    add(("p", "（3）使用 JMeter 和 Prometheus 对两种方案进行负载测试和压力测试，比较吞吐量、响应时间、错误率和各服务器资源使用，并找出各自的瓶颈。"))

    # 2
    add(("h1", "2 实验环境"))
    add(("table", "表1  服务器分工与软件版本", ["指导书角色", "本组服务器", "私网地址", "本实验内容"], [
        ["A 编译、JMeter", "CDWY3", "172.31.12.156", "JDK 21、Maven 3.9.16、JMeter 5.6.3（堆 400 MB；逐级加压与持续压测 768 MB）"],
        ["B MySQL", "CDWY2", "172.31.8.46", "MySQL 9.2.0，库 lab4_log；缓冲池 128 MB（默认）"],
        ["C MongoDB 7.0", "CDWY5", "172.31.13.151", "MongoDB 7.0.48；WiredTiger 缓存 0.25 GB"],
        ["D Prometheus", "CDWY4", "172.31.1.19", "Prometheus 3.7.3；按课程 11-19 的要求每 1 秒采集、每 2 秒计算，CPU 使用率为 2 秒平均"],
        ["E 两套日志服务", "CDWY1", "172.31.1.202", "MySQL 版 :8081、MongoDB 版 :8082"],
    ], [2.6, 1.9, 2.5, 8.5]))
    add(("p", "5 台服务器均为 Ubuntu 18.04、2 核 CPU、约 1.8 GB 内存、Docker 20.10.21，组成 Docker Swarm 集群并通过私网通信。"
               "两套服务使用 Spring Boot 3.3.4、Java 21，JVM 堆均为 384 MB，Tomcat 最多 200 个工作线程，数据库连接池上限均为 100，"
               "取连接最长等待 10 秒；MySQL 版连接池每 5 分钟对空闲连接保活一次，避免 Swarm 虚拟 IP 断开空闲连接。每次只对一种实现"
               "施压。测试前暂停了 CDWY3 上课程以外的 rbac 服务，可用内存约 1.3 GB，全部测试由 CDWY3 发压。"))

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
    add(("p", "主键采用 26 位 ULID，前 48 位为毫秒时间戳，后 80 位为随机数。时间戳前缀使主键大体按生成时间排列，同一毫秒内按随机后缀排序。"
               "MySQL 使用该值作为主键，MongoDB 使用该值作为 _id。createdAt 在程序中以 Instant 表示，统一截断至毫秒；MySQL 会话时区"
               "固定为 UTC，MongoDB 存为 BSON Date。message 长度按 Unicode 码点计数，上限为 4096。"))
    add(("p", "数据库层同样约束数据：MySQL 用列类型、NOT NULL 和 CHECK；MongoDB 用 $jsonSchema 校验器（必填字段、类型、长度、"
               "level 取值、禁止多余字段）。两边建立等价的索引：(level, created_at, id) 与 (created_at, id)，"
               "分别对应“按级别和时间范围”与“只按时间范围”查询，按时间倒序取数时无需额外排序。初始化脚本见 db/mysql、db/mongo。"))
    add(("h2", "3.2 统一 REST 接口"))
    add(("table", "表3  日志读写接口", ["方法", "路径", "请求或参数", "成功响应"], [
        ["POST", "/api/logs", "JSON 日志对象（id 由服务端生成，createdAt 可省略）", "HTTP 201，errno=1"],
        ["GET", "/api/logs", "level、from、to（ISO-8601，范围 [from, to)）、page、size", "HTTP 200，errno=0"],
    ], [1.3, 2.1, 8.2, 3.9]))
    add(("p", "查询结果按 createdAt、id 倒序分页，page 从 1 开始，size 为 1～100；返回 list、page、pageSize，不统计总数"
               "（总数需要额外的 count 查询）。参数或请求体不合法时返回 HTTP 400、errno=3。两种实现对外完全相同，JMeter 只需替换端口。"))
    add(("h2", "3.3 两套实现"))
    add(("table", "表4  共用部分与各自实现", ["层次", "共用（logdemo-core）", "MySQL 版（logdemo-jpa）", "MongoDB 版（logdemo-mongo）"], [
        ["接口与业务", "LogController、LogService、校验、ULID", "—", "—"],
        ["持久层接口", "LogStore（insert、find）", "JpaLogStore", "MongoLogStore"],
        ["数据对象", "LogRecord", "LogPo（@Entity）", "LogDoc（@Document）"],
        ["Repository", "—", "JpaRepository + @Query（JPQL）", "MongoRepository + @Query（查询文档）"],
        ["分页", "Pageable（createdAt、id 倒序）", "ORDER BY … LIMIT ?, ?", "sort … skip … limit"],
    ], [2.2, 4.6, 4.2, 4.5]))
    add(("p", "两套实现共用接口与业务模块，分别实现 LogStore 持久层接口。JPA 实体实现 Persistable，使预先赋值主键的 save() 直接执行 "
               "INSERT；MongoDB 版使用 insert()，并去掉默认的 _class 字段。数据库密码通过 Docker secret 注入，应用账号具有查询和插入权限。"
               "连接池上限由 LOGDEMO_POOL_MAXSIZE 配置；MongoDB 写关注固定为 w:1，通过 LOGDEMO_MONGO_JOURNAL 控制是否增加 j:true。"
               "切换配置后，通过启动日志核对实际生效值。"))
    add(("h2", "3.4 正确性与一致性验证"))
    add(("p", "部署后用同一组 22 项接口检查（正常写入、各类非法参数、4096 字符边界、IPv6、分页顺序、[from, to) 边界等）"
               "分别检查两种实现，全部通过且逐项结果一致。两台数据库服务器各自用固定随机种子生成同一批 10 万条日志并装入，"
               "按 id 顺序从数据库导出后计算内容摘要，两库完全相同（SHA-256 前缀 bbd96253）。"))

    # 4
    add(("h1", "4 测试方法"))
    add(("h2", "4.1 测试数据"))
    add(("p", "两库预置相同的 10 万条日志，时间分布在 2026-10-27 至 2026-11-01（UTC），级别占比为 INFO 60%、DEBUG 15%、WARN 15%、"
               "TRACE 5%、ERROR 5%；正文多数为 40～200 个字符，最长 4096 个字符。MySQL 预置数据约 80 MB。写入请求取自 1 万条固定数据，"
               "查询参数取自 1 万组固定组合，覆盖级别、1 小时～3 天的时间范围、页码 1～50，每页 20 条。两种实现读取相同文件。"
               "写入请求不带 createdAt，由服务端生成当前时间；新增日志落在查询时间范围之外，查询始终面向预置数据。每项测试前都把两库"
               "重置为这份预置数据（查询测试也重置），各次测试开始时的数据库状态相同。"))
    add(("h2", "4.2 测试设计"))
    add(("table", "表5  测试内容（每项都对两种实现、按需对读写分别进行）", ["部分", "线程数", "Ramp-up / 总时长", "次数", "目的"], [
        ["主对比", "查询 50，写入 100", "20 s / 240 s", "1", "固定参数下比较两种实现"],
        ["写关注对照", "写入 100，MongoDB j:true", "20 s / 240 s", "1", "比较等待 journal 持久化后的写入性能"],
        ["最多同时运行线程数", "400、800、1200、1600、2000 逐级", "线程数÷20 s / 再加 90 s", "1", "找全部线程同时运行且零错误的最高一级"],
        ["最多线程数下持续压测", "上一项选出的线程数；之后 10 线程", "不超过 60 s / 240 s；2 s / 60 s", "1", "最高并发下的吞吐、延迟、资源与恢复"],
    ], [3.2, 4.1, 3.1, 1.1, 4.0]))
    add(("p", "主对比固定查询 50 线程、写入 100 线程（组内预试验中，两种实现在这一并发量下吞吐量已接近最高、响应时间较低），"
               "Ramp-up 为 20 秒，总持续时间为 240 秒。Tomcat 工作线程上限保持 200，数据库连接池上限保持 100。每项正式测试前用相同"
               "线程数单独预热 120 秒，测试间隔 30 秒，先测 MySQL 版、再测 MongoDB 版。j:true 对照在主对比之后进行：切换写关注后"
               "重启 MongoDB 版服务，从启动日志核对实际生效值。"))
    add(("p", "随后借鉴其他组的做法，先找“最多同时运行的线程数”：两种实现的查询、写入各自从 400 线程起逐级加到 2000 线程，Ramp-up "
               "按每秒启动 20 个线程计，全部线程启动后再运行 90 秒；某一级同时满足“JMeter 的活跃线程数达到设定值、零错误、压测机自检"
               "正常（4.3 节）”才算通过，不通过即停止加压。每种实现只在逐级加压开始前用 50 线程预热 60 秒。每种操作取两种实现都通过的"
               "最高一级，在该线程数下持续压测 240 秒（Ramp-up 不超过 60 秒，统计第 60～240 秒，测前预热 60 秒），之后间隔 30 秒做 "
               "10 线程、60 秒的恢复检查。"))
    add(("h2", "4.3 指标与监控"))
    add(("p", "JMeter 线程组的 Duration 包含 Ramp-up。20 秒 Ramp-up 表示在约 20 秒内陆续启动全部线程，已启动线程随即发送请求；"
               "主对比的总时长约为 240 秒。主对比与持续压测以首条请求的开始时间为起点，选取第 60 秒至第 240 秒之前开始的请求，吞吐量"
               "为该区间样本数除以 180 秒。平均响应时间和 P95、P99 均由这些请求的 elapsed 计算，百分位采用最近秩法。逐级加压与恢复检查"
               "选取所有线程均已启动的时段。elapsed 表示客户端记录的请求耗时，包含连接、网络传输和服务端处理时间。"))
    add(("p", "Prometheus 抓取服务的 /actuator/prometheus 和各节点的 node-exporter，记录请求计数、JVM、连接池以及 CPU、内存、磁盘和"
               "网络指标。按课程 11-19 的要求，CPU 使用率记录规则 node:cpu_usage_percent 为 2 秒平均，即 "
               "(1 − Σrate(node_cpu_seconds_total{mode=\"idle\"}[2s]) ÷ Σrate(node_cpu_seconds_total[2s])) × 100%，node-exporter 每 1 秒"
               "采集、规则每 2 秒计算一次。原来的 5 分钟平均会把一次几分钟的测试与前后的空闲、准备时段混在一起，无法反映测试期间的 CPU。"
               "各项测试的 CPU 使用率取统计区间内该规则的均值与最大值。"))
    add(("p", "每请求 CPU 时间按“2 核 × 节点 CPU 使用率 ÷ 服务端每秒请求数”计算，反映节点资源开销。%d 次测试的服务端与 JMeter "
               "吞吐量偏差均不超过 %.1f%%。压测端同时检查 CPU、可用内存和线程启动情况，并用“线程数 ÷ 吞吐量 − 平均响应时间”辅助观察"
               "发压间隙（压测机自检）。%d 次测试包括 %d 次写入测试，其中 %d 次保存了入库数量核对结果，成功请求数均等于新增记录数。"
               % (len(devs), 100 * max(devs), tests, writes_n, len(writes))))

    # 5
    add(("h1", "5 结果与分析"))
    add(("h2", "5.1 主对比"))
    add(("figure", os.path.join(CHARTS, "main-comparison.png"), "图1  主对比：吞吐量与 P95、P99 响应时间", 15.4))
    rows = []
    for op in ("read", "write"):
        for impl in ("jpa", "mongo", "mongoj"):
            if (op, "main", MAIN_T[op], impl) not in NJ:
                continue
            r = NJ[(op, "main", MAIN_T[op], impl)]
            rows.append([OP_CN[op], IMPL_CN[impl], n(r["steady_throughput"]), n(r["steady_avg_ms"], 1), r["steady_p50_ms"],
                         r["steady_p95_ms"], r["steady_p99_ms"], r["steady_max_ms"], "%.2f" % ratio(op, impl)])
    add(("table", "表6  主对比结果（统计第 60～240 秒；查询 50 线程、写入 100 线程；全部请求成功）",
         ["操作", "实现", "吞吐（次/秒）", "平均(ms)", "P50(ms)", "P95(ms)", "P99(ms)", "最大(ms)", "相对 MySQL"], rows,
         [1.1, 2.6, 2.2, 1.5, 1.5, 1.5, 1.5, 1.5, 1.9]))
    add(("p", "MongoDB 版查询吞吐量为 %s 次/秒，MySQL 版为 %s 次/秒，前者高 %.0f%%；平均响应时间分别为 %.1f ms 和 %.1f ms，P95 为 "
               "%s ms 和 %s ms，P99 为 %s ms 和 %s ms，差距在尾部响应时间上更明显。写入吞吐量分别为 %s 次/秒和 %s 次/秒，MongoDB 版为 "
               "MySQL 版的 %.2f 倍；平均响应时间分别为 %.1f ms 和 %.1f ms，P99 为 %s ms 和 %s ms。"
               % (n(nj(*rm)), n(nj(*rj)), 100 * (ratio("read") - 1), nj(*rm, "steady_avg_ms"), nj(*rj, "steady_avg_ms"),
                  nraw(*rm, "steady_p95_ms"), nraw(*rj, "steady_p95_ms"), nraw(*rm, "steady_p99_ms"), nraw(*rj, "steady_p99_ms"),
                  n(nj(*wm)), n(nj(*wj)), ratio("write"), nj(*wm, "steady_avg_ms"), nj(*wj, "steady_avg_ms"),
                  nraw(*wm, "steady_p99_ms"), nraw(*wj, "steady_p99_ms"))))
    qw = {i: [f(r, "steady_throughput") for k, r in QJ.items() if k[0] == "write" and k[3] == i and has(r)] for i in ("jpa", "mongo")}
    qdev = max(abs(pct(v, nj("write", i)) - 100) for i in ("jpa", "mongo") for v in qw[i])
    add(("p", "主对比只进行了 1 轮。逐级加压中两种实现的写入在 400～2000 线程各级都已饱和，吞吐量分别为 MySQL 版 %s～%s 次/秒、"
               "MongoDB 版 %s～%s 次/秒，与主对比的写入吞吐量相差不超过 %.0f%%（5.4 节），两种实现的差距在各次测试中保持一致。"
               % (n(min(qw["jpa"])), n(max(qw["jpa"])), n(min(qw["mongo"])), n(max(qw["mongo"])), qdev + 0.5)))

    add(("p", "图 2～图 9 是 JMeter 报告生成器对这四项测试生成的 HTML 报告：每项一张首页（测试信息、APDEX、请求成功率和统计表）和一张响应时间百分位曲线（只含第 60～240 秒内开始的请求），"
               "样本数、平均与百分位响应时间与表 6 一致；吞吐量按首尾请求的实际时间跨度计算，与表 6 相差不到 0.1%。"
               "Sent 为 0 是因为 JTL 没有保存发送字节数。"))
    jmeter_figs(add, CHARTS, [("n1", "jpa-read-main-t50", "MySQL 查询 50 线程"), ("n1", "mongo-read-main-t50", "MongoDB 查询 50 线程"),
                              ("n1", "jpa-write-main-t100", "MySQL 写入 100 线程"), ("n1", "mongo-write-main-t100", "MongoDB 写入 100 线程")], 2)

    add(("h2", "5.2 资源使用与瓶颈"))
    add(("figure", os.path.join(CHARTS, "main-resources.png"), "图10  主对比的资源开销（CPU 使用率为 2 秒平均）", 15.4))
    rows = []
    for op in ("read", "write"):
        for impl in ("jpa", "mongo", "mongoj"):
            if (op, "main", MAIN_T[op], impl) not in NP:
                continue
            db = db_host(impl)
            rows.append([OP_CN[op], IMPL_CN[impl],
                         "%.0f%%（%.0f%%）" % (npm(op, impl, "CDWY1_cpu2s_avg"), npm(op, impl, "CDWY1_cpu2s_max")),
                         "%.0f%%（%.0f%%）" % (npm(op, impl, db + "_cpu2s_avg"), npm(op, impl, db + "_cpu2s_max")),
                         "%.2f" % npm(op, impl, "app_host_cpu2s_ms_per_req"), "%.2f" % npm(op, impl, "db_host_cpu2s_ms_per_req"),
                         n(npm(op, impl, db + "_disk_write_iops")) if op == "write" else "—",
                         "%.1f" % kb_insert_n(impl) if op == "write" else "—"])
    add(("table", "表7  主对比的资源使用（CPU 为 2 秒平均在统计区间内的均值，括号为最大值；CPU 时间 = 2 核 × 使用率 ÷ 服务端每秒请求数）",
         ["操作", "实现", "应用服务器 CPU", "数据库服务器 CPU", "应用端 ms/请求", "数据库端 ms/请求", "磁盘写操作 次/秒", "磁盘写入 KB/条"],
         rows, [1.1, 2.4, 2.2, 2.3, 1.9, 2.0, 1.9, 1.7]))
    add(("p", "查询时，MySQL 数据库节点 CPU 为 %.0f%%，应用节点为 %.0f%%；MongoDB 应用节点为 %.0f%%，数据库节点为 %.0f%%。"
               "每请求数据库节点 CPU 时间分别为 %.2f ms 和 %.2f ms，应用节点则接近，为 %.2f ms 和 %.2f ms。MySQL 版查询首先达到数据库 CPU "
               "上限，MongoDB 版首先达到应用 CPU 上限。MongoDB 数据库节点较低的单位请求开销，使应用能够处理更多请求后才到达饱和状态。"
               "2 秒平均的最大值显示，饱和的一端在统计区间内持续处于 %s 附近，而不是偶发的尖峰。"
               % (npm(*rj, "CDWY2_cpu2s_avg"), npm(*rj, "CDWY1_cpu2s_avg"), npm(*rm, "CDWY1_cpu2s_avg"), npm(*rm, "CDWY5_cpu2s_avg"),
                  npm(*rj, "db_host_cpu2s_ms_per_req"), npm(*rm, "db_host_cpu2s_ms_per_req"),
                  npm(*rj, "app_host_cpu2s_ms_per_req"), npm(*rm, "app_host_cpu2s_ms_per_req"),
                  span([npm(*rj, "CDWY2_cpu2s_avg"), npm(*rm, "CDWY1_cpu2s_avg")]))))
    add(("p", "写入时，MySQL 数据库节点 CPU 为 %.0f%%，iowait 为 %.0f%%，磁盘写操作约 %s 次/秒，折算写入量为每条日志 %.1f KB。"
               "其 innodb_flush_log_at_trx_commit=1、sync_binlog=1，使事务提交需要满足 redo log 和 binlog 的同步要求。MongoDB 默认 "
               "w:1 下，数据库节点 CPU 为 %.0f%%，磁盘写操作约 %s 次/秒，每条日志 %.1f KB，应用节点 CPU 达 %.0f%%。两者在持久化确认"
               "方式和磁盘写入负担上存在差异，因此进一步用 j:true 观察等待日志持久化后的表现。表 7 的写盘次数来自节点块设备计数，"
               "写入量同时包含日志、数据页及索引等写入。"
               % (npm(*wj, "CDWY2_cpu2s_avg"), npm(*wj, "CDWY2_iowait_pct"), n(npm(*wj, "CDWY2_disk_write_iops")), kb_insert_n("jpa"),
                  npm(*wm, "CDWY5_cpu2s_avg"), n(npm(*wm, "CDWY5_disk_write_iops")), kb_insert_n("mongo"), npm(*wm, "CDWY1_cpu2s_avg"))))

    add(("h2", "5.3 MongoDB 写关注对照"))
    per_op = npm(*wjj, "server_tps") / npm(*wjj, "CDWY5_disk_write_iops")
    add(("p", "默认 w:1 确认 MongoDB 已接受写入，不要求在返回前等待 journal 持久化；w:1 + j:true 增加这一等待，持久性与 MySQL 的 "
               "innodb_flush_log_at_trx_commit=1 相当。100 线程下，启用 j:true 后写入吞吐量为 %s 次/秒，为默认配置（%s 次/秒）的 %.0f%%，"
               "是 MySQL 版的 %.2f 倍；平均响应时间为 %.1f ms，P95、P99 为 %s ms、%s ms（默认配置为 %.1f ms、%s ms、%s ms）。"
               % (n(nj(*wjj)), n(nj(*wm)), pct(nj(*wjj), nj(*wm)), ratio("write", "mongoj"), nj(*wjj, "steady_avg_ms"),
                  nraw(*wjj, "steady_p95_ms"), nraw(*wjj, "steady_p99_ms"), nj(*wm, "steady_avg_ms"),
                  nraw(*wm, "steady_p95_ms"), nraw(*wm, "steady_p99_ms"))))
    add(("p", "启用 j:true 后，数据库磁盘写操作由 %s 次/秒增至 %s 次/秒，每条日志的节点写入量由 %.1f KB 增至 %.1f KB；应用节点 CPU 则由 "
               "%.0f%% 降至 %.0f%%（2 秒平均），不再满载，说明请求有更多时间花在等待 journal 落盘上。按写盘次数折算，平均每次写盘对应约 "
               "%.0f 条写入：并发的写入共享同一次日志同步（组提交），因此吞吐量只下降 %.0f%%。j:true 的 P99 反而低于默认配置，可能是因为"
               "默认配置下应用节点 CPU 已满载，尾部请求在应用端排队更久。"
               % (n(npm(*wm, "CDWY5_disk_write_iops")), n(npm(*wjj, "CDWY5_disk_write_iops")), kb_insert_n("mongo"), kb_insert_n("mongoj"),
                  npm(*wm, "CDWY1_cpu2s_avg"), npm(*wjj, "CDWY1_cpu2s_avg"), per_op, 100 - pct(nj(*wjj), nj(*wm)))))

    add(("p", "图 11、图 12 是 j:true 这项测试的 HTML 报告首页与响应时间百分位曲线（第 60～240 秒）。"))
    jmeter_figs(add, CHARTS, [("n1", "mongoj-write-main-t100", "MongoDB j:true 写入 100 线程")], 11)

    add(("h2", "5.4 最多同时运行线程数"))
    add(("figure", os.path.join(CHARTS, "probe.png"), "图13  最多同时运行线程数：逐级加压的吞吐量与平均响应时间", 15.0))
    B.extend(probe_section(PR, QJ, QP, XJ, XP, NMAX))

    add(("h2", "5.5 最多线程数下持续压测"))
    add(("figure", os.path.join(CHARTS, "maxload-cpu.png"), "图14  最多线程数下持续压测：各服务器 CPU 使用率（2 秒平均）", 15.2))
    B.extend(maxload_section(XJ, XP, NJ, NP, NMAX))
    add(("p", "图 15～图 22 是这四项持续压测的 HTML 报告首页与响应时间百分位曲线（第 60～240 秒）。高并发下单个请求耗时接近 1 秒，JMeter 按首尾请求"
               "的实际时间跨度计算的吞吐量比表 9 低 0.2%～0.5%，其余数字一致。"))
    jmeter_figs(add, CHARTS, [("x1", "jpa-read-maxload-t400", "MySQL 查询 400 线程"), ("x1", "mongo-read-maxload-t400", "MongoDB 查询 400 线程"),
                              ("x1", "jpa-write-maxload-t2000", "MySQL 写入 2000 线程"), ("x1", "mongo-write-maxload-t2000", "MongoDB 写入 2000 线程")], 15)

    # 6
    add(("h1", "6 结论"))
    add(("p", "（1）两套日志服务完成了相同模型、接口和请求数据下的写入与条件分页查询。22 项接口检查结果一致，10 万条预置数据内容摘要一致；"
               "%d 次有入库核对记录的写入测试中，成功请求数均等于新增记录数。" % len(writes)))
    add(("p", "（2）主对比中，MongoDB 版查询吞吐量高 %.0f%%，P99 约为 MySQL 版的 %.0f%%；数据库节点单位请求 CPU 开销更低。按 2 秒平均的 "
               "CPU 使用率，MySQL 版查询的饱和点在数据库服务器（%.0f%%），MongoDB 版在应用服务器（%.0f%%）。"
               % (100 * (ratio("read") - 1), pct(nj(*rm, "steady_p99_ms"), nj(*rj, "steady_p99_ms")),
                  npm(*rj, "CDWY2_cpu2s_avg"), npm(*rm, "CDWY1_cpu2s_avg"))))
    add(("p", "（3）MongoDB 默认配置的写入吞吐量是 MySQL 版的 %.2f 倍；启用 j:true 后为 %.2f 倍，吞吐量下降 %.0f%%。j:true 使数据库磁盘"
               "写操作增加约 %.0f 倍，但并发写入共享日志同步，仍保留较大的吞吐优势。"
               % (ratio("write"), ratio("write", "mongoj"), 100 - pct(nj(*wjj), nj(*wm)),
                  npm(*wjj, "CDWY5_disk_write_iops") / npm(*wm, "CDWY5_disk_write_iops"))))
    B.extend(conclusion_tail(XJ, NJ, NMAX))

    add(("h1", "参考资料"))
    for ref in ("[1] 实验四：Mongo 的读写性能测试，课程实验指导书。",
                "[2] Spring Data JPA Reference Documentation；Spring Data MongoDB Reference Documentation。",
                "[3] MySQL 9.2 Reference Manual：innodb_flush_log_at_trx_commit、sync_binlog、Group Commit。",
                "[4] MongoDB 7.0 Manual：Write Concern、Journaling（storage.journal.commitIntervalMs）。",
                "[5] Apache JMeter User's Manual：Thread Group、CSV Data Set Config、Generating Report Dashboard。",
                "[6] HikariCP Wiki：About Pool Sizing。",
                "[7] ISTQB Glossary：load testing、stress testing。",
                "[8] Prometheus Documentation：rate()、recording rules、promtool tsdb dump、node_exporter。"):
        add(("note", ref))

    add(("h1", "附录  提交材料与数据对应"))
    add(("note", "提交仓库：https://gitee.com/W2097382371/lab4-mongo-benchmark；完整材料（含学习文档）：https://github.com/Re1lya/lab4-mongo-benchmark"))
    add(("table", "附表  仓库内容", ["内容", "位置"], [
        ["两套实现及共用模块", "logdemo/logdemo-core、logdemo-jpa、logdemo-mongo"],
        ["数据库初始化脚本", "db/mysql/、db/mongo/"],
        ["JMeter 与请求数据", "jmeter/WriteLog.jmx、ReadLog.jmx、data/"],
        ["运行说明", "README.md、docs/01-实验操作手册.md"],
        ["Prometheus 配置", "deploy/prometheus/prometheus.yml、rules/recording.yml（2 秒平均 CPU 规则）"],
        ["%d 次测试原始 JTL" % tests, "results/n1（主对比与 j:true）、results/probe（逐级加压）、results/x1（持续压测与恢复检查）"
                                    "各测试目录的 samples.jtl.gz"],
        ["JMeter HTML 报告", "results/jmeter-html/（主对比、j:true 与持续压测，共 %d 份，用浏览器打开 index.html）" % html_reports()],
        ["监控数据", "results/prometheus-phase3.txt.gz；各测试的 monitor.json"],
        ["请求与监控统计、图表", "results/统计与图表/ 下 jtl-summary-*、prom-summary-* 和 charts/"],
        ["接口及预置数据检查", "results/00-环境与一致性/"],
    ], [4.0, 11.5]))
    return B


def probe_section(PR, QJ, QP, XJ, XP, NMAX):
    out = []
    status = {(r["op"], r["impl"], int(r["t"])): r.get("pass") == "1" for r in PR}
    rows = []
    for op in ("read", "write"):
        for impl in ("jpa", "mongo"):
            for r in [x for x in PR if x["op"] == op and x["impl"] == impl]:
                ok = r.get("window_s", "0") != "0"   # 未通过的级别没有“全部线程同时运行”的时段
                rows.append([OP_CN[op], IMPL_CN[impl], r["t"], r.get("max_threads", "—"), n(r["tps"]) if ok else "—",
                             r["avg_ms"] if ok else "—", r.get("errors", "—"), r["gap_ms"] if ok else "—",
                             "通过" if status[(op, impl, int(r["t"]))] else "不通过"])
    out.append(("table", "表8  最多同时运行线程数逐级加压（吞吐与平均响应取全部线程同时运行的时段，未通过的级别没有这一时段；"
                         "压测机自检 = 线程数 ÷ 吞吐量 − 平均响应时间）",
                ["操作", "实现", "设定线程", "同时运行", "吞吐(次/秒)", "平均(ms)", "错误数", "自检(ms)", "结果"], rows,
                [1.1, 1.8, 1.6, 1.6, 2.0, 1.6, 1.4, 1.6, 1.4]))
    q = lambda op, impl, t, k: f(QJ[(op, "probe", t, impl)], k)
    best = {}
    for (op, impl, t), ok in status.items():
        if ok:
            best[(op, impl)] = max(best.get((op, impl), 0), t)
    wt = {i: sorted(t for (op, im, t), ok in status.items() if op == "write" and im == i and ok) for i in ("jpa", "mongo")}
    wtps = {i: [q("write", i, t, "steady_throughput") for t in wt[i]] for i in ("jpa", "mongo")}
    top = max(wt["mongo"])
    out.append(("p", "写入两种实现在 %d～%d 线程各级都通过：MySQL 版吞吐量为 %s～%s 次/秒，MongoDB 版为 %s～%s 次/秒，基本不随线程数变化；"
                     "平均响应时间与线程数成正比增加，约等于“线程数 ÷ 吞吐量”（%d 线程时 MongoDB 版为 %.0f ms，MySQL 版为 %.0f ms）。"
                     "服务已经饱和，多出的线程只是在排队。%d 线程是本组设定的最高一级，写入实际能同时运行的线程数可能更多。"
                     % (min(wt["jpa"]), max(wt["jpa"]), n(min(wtps["jpa"])), n(max(wtps["jpa"])), n(min(wtps["mongo"])), n(max(wtps["mongo"])),
                        top, q("write", "mongo", top, "steady_avg_ms"), q("write", "jpa", top, "steady_avg_ms"), top)))
    fr = sorted(k for k, ok in status.items() if not ok and k[0] == "read")
    if fr:
        qp = lambda k, col: f(QP[(k[0], "probe", k[2], k[1])], col)
        qj = lambda k, col: QJ[(k[0], "probe", k[2], k[1])][col]
        rb = f(QJ[("read", "probe", 400, "jpa")], "full_bytes_avg") / 1024
        wb = f(QJ[("write", "probe", 400, "jpa")], "full_bytes_avg") / 1024
        others = [f(p, "CDWY3_cpu2s_avg") for p in QP.values() if p.get("window") != "full-run"]
        out.append(("p", "查询两种实现在 400 线程都通过，%s不通过，原因在压测机而不在被测系统：这几级开始后不久，压测机 CDWY3 的 CPU（2 秒"
                         "平均）升到 100%% 并保持到结束，整级平均 %s；JMeter 每秒只发出 %s～%s 个请求，启动新线程也被拖慢，先启动的线程按时结束时"
                         "后面的线程还在陆续启动，同时运行的线程最多只有 %s，整级持续 %.0f～%.0f 秒（计划 %.0f～%.0f 秒）。同一时间应用服务器 CDWY1 "
                         "的 CPU 只有 %s。查询响应平均 %.1f KB，约为写入（%.2f KB）的 %.0f 倍，JMeter 接收和检查（断言 errno=0）查询响应的负担更重；"
                         "其余各级压测机 CPU 平均不超过 %.0f%%。本次没有记录 JMeter 自身的垃圾回收情况，CPU 被占满的具体原因未能进一步确认。"
                         "因此查询的 %d 线程是本组 2 核压测机能稳定驱动的上限，不代表 MySQL 或 MongoDB 的上限。"
                         % ("、".join("%s 版在 %d 线程" % (IMPL_CN[k[1]], k[2]) for k in fr),
                            span([qp(k, "CDWY3_cpu2s_avg") for k in fr], "%.1f%%"),
                            n(min(float(qj(k, "full_throughput")) for k in fr)), n(max(float(qj(k, "full_throughput")) for k in fr)),
                            "和 ".join("%s 个（%s %d 线程）" % (qj(k, "max_threads"), IMPL_CN[k[1]], k[2]) for k in fr),
                            min(float(qj(k, "full_window_s")) for k in fr), max(float(qj(k, "full_window_s")) for k in fr),
                            min(k[2] / 20 + 90 for k in fr), max(k[2] / 20 + 90 for k in fr),
                            span([qp(k, "CDWY1_cpu2s_avg") for k in fr]), rb, wb, rb / wb, max(others), NMAX.get("read", 0))))
    k400, k800, kx = ("read", "probe", 400, "mongo"), ("read", "probe", 800, "mongo"), ("read", "maxload", 400, "mongo")
    if all(k in QJ and k in QP for k in (k400, k800)) and kx in XJ and kx in XP:
        a, b, c = f(QJ[k400], "steady_throughput"), f(QJ[k800], "steady_throughput"), f(XJ[kx], "steady_throughput")
        if a < 0.8 * min(b, c):
            ma, mb, mc = (f(QP[k400], "app_host_cpu2s_ms_per_req"), f(QP[k800], "app_host_cpu2s_ms_per_req"),
                          f(XP[kx], "app_host_cpu2s_ms_per_req"))
            out.append(("p", "MongoDB 查询 400 线程这一级的吞吐量为 %s 次/秒，低于随后 800 线程的 %s 次/秒和 5.5 节同为 400 线程的 %s 次/秒。"
                             "这一级应用服务器 CPU 已达 %.0f%%，每请求应用端 CPU 时间为 %.2f ms，是后两者的 %.1f～%.1f 倍。它距 j:true 测试后"
                             "重启 MongoDB 日志服务约 11 分钟，测前只预热了 60 秒，推测服务尚未充分预热。逐级加压只判断全部线程能否同时运行，"
                             "这一级通过，不影响线程数的选择；吞吐量的比较以 5.5 节为准。"
                             % (n(a), n(b), n(c), f(QP[k400], "CDWY1_cpu2s_avg"), ma, ma / max(mb, mc), ma / min(mb, mc))))
    out.append(("p", "按 4.2 节的规则，查询取两种实现都通过的最高一级 %d 线程、写入取 %d 线程进行持续压测（各实现通过的最高一级：%s）。"
                     % (NMAX.get("read", 0), NMAX.get("write", 0),
                        "，".join("%s %s %d" % (IMPL_CN[i], OP_CN[op], best.get((op, i), 0)) for op in ("read", "write") for i in ("jpa", "mongo")))))
    return out


def maxload_section(XJ, XP, NJ, NP, NMAX):
    out = []
    rows = []
    for op in ("read", "write"):
        t = NMAX[op]
        for impl in ("jpa", "mongo"):
            r = XJ.get((op, "maxload", t, impl))
            p = XP.get((op, "maxload", t, impl))
            rec = XJ.get((op, "recovery", 10, impl))
            if not r:
                continue
            db = db_host(impl)
            rows.append([OP_CN[op], IMPL_CN[impl], t, n(r["steady_throughput"]), n(r["steady_avg_ms"]), r["steady_p95_ms"], r["steady_p99_ms"],
                         "%.0f%% / %.0f%%" % (f(p, "CDWY1_cpu2s_avg"), f(p, db + "_cpu2s_avg")) if p else "—",
                         "%.0f%%" % f(p, "CDWY3_cpu2s_avg") if p else "—",
                         "%s / %.1f" % (n(rec["steady_throughput"]), f(rec, "steady_avg_ms")) if rec else "—"])
    errs_all = sum(int(r["full_errors"]) for r in XJ.values())
    out.append(("table", "表9  最多线程数下持续压测（统计第 60～240 秒%s；CPU 为 2 秒平均在统计区间内的均值；恢复检查为随后 10 线程 60 秒的"
                         "吞吐 次/秒 / 平均 ms）" % ("，全部请求成功" if errs_all == 0 else ""),
                ["操作", "实现", "线程", "吞吐(次/秒)", "平均(ms)", "P95(ms)", "P99(ms)", "应用/数据库 CPU", "压测机 CPU", "恢复检查"], rows,
                [1.1, 1.7, 1.0, 1.6, 1.3, 1.3, 1.3, 2.3, 1.4, 2.4]))
    imps = [(op, i) for op in ("read", "write") for i in ("jpa", "mongo")]
    x = lambda op, impl, k: f(XJ[(op, "maxload", NMAX[op], impl)], k)
    xp = lambda op, impl, k: f(XP[(op, "maxload", NMAX[op], impl)], k)
    nm = lambda op, impl, k="steady_throughput": f(NJ[(op, "main", MAIN_T[op], impl)], k)
    npp = lambda op, impl, k: f(NP[(op, "main", MAIN_T[op], impl)], k)
    errs = sum(int(r["full_errors"]) for k, r in XJ.items() if k[1] == "maxload")
    gap = max(f(r, "steady_client_gap_ms") for k, r in XJ.items() if k[1] == "maxload")
    gen = [f(p, "CDWY3_cpu2s_avg") for k, p in XP.items() if k[1] == "maxload"]
    xr = [x(op, i, "steady_avg_ms") / nm(op, i, "steady_avg_ms") for op, i in imps]
    out.append(("p", "在查询 %d、写入 %d 线程下持续压测 240 秒，%s；压测机 CPU 为 %s，压测机自检不超过 %.2f ms，发压端没有成为瓶颈。与主对比"
                     "（查询 50、写入 100 线程）相比，查询吞吐量 MySQL 版为 %s 次/秒（主对比 %s），MongoDB 版为 %s 次/秒（%s）；写入 MySQL 版 "
                     "%s（%s）、MongoDB 版 %s（%s）。吞吐量没有因线程增多而提高，平均响应时间升至 %.0f～%.0f ms，为主对比的 %.0f～%.0f 倍："
                     "超出 Tomcat 200 个工作线程和 100 个数据库连接的请求都在排队。MongoDB 版仍保持较高吞吐量，查询为 MySQL 版的 %.2f 倍，"
                     "写入为 %.2f 倍。"
                     % (NMAX["read"], NMAX["write"], "全部请求成功" if errs == 0 else "出现 %s 个错误" % n(errs), span(gen), gap,
                        n(x("read", "jpa", "steady_throughput")), n(nm("read", "jpa")),
                        n(x("read", "mongo", "steady_throughput")), n(nm("read", "mongo")),
                        n(x("write", "jpa", "steady_throughput")), n(nm("write", "jpa")),
                        n(x("write", "mongo", "steady_throughput")), n(nm("write", "mongo")),
                        min(x(op, i, "steady_avg_ms") for op, i in imps), max(x(op, i, "steady_avg_ms") for op, i in imps), min(xr), max(xr),
                        x("read", "mongo", "steady_throughput") / x("read", "jpa", "steady_throughput"),
                        x("write", "mongo", "steady_throughput") / x("write", "jpa", "steady_throughput"))))
    hot = [xp("read", "jpa", "CDWY1_cpu2s_avg"), xp("read", "mongo", "CDWY1_cpu2s_avg"), xp("write", "mongo", "CDWY1_cpu2s_avg")]
    out.append(("p", "图 14 为 2 秒平均的 CPU 使用率曲线。四组测试中负载最高的都是应用服务器 CDWY1：MySQL 查询、MongoDB 查询和 MongoDB 写入时"
                     "在统计区间内平均为 %s，MySQL 写入时为 %.0f%%，同时 MySQL 服务器为 %.0f%%、iowait %.0f%%。与 50 线程时相比，MySQL 查询的"
                     "饱和位置发生了变化：数据库服务器 CPU 由 %.0f%% 降到 %.0f%%，应用服务器由 %.0f%% 升到 %.0f%%，每请求应用端 CPU 时间由 %.2f ms "
                     "增至 %.2f ms，垃圾回收停顿占比由 %.1f%% 升至 %.1f%%。高并发下应用端每个请求的开销增加成为限制，吞吐量因此比 50 线程时低 %.0f%%。"
                     % (span(hot), xp("write", "jpa", "CDWY1_cpu2s_avg"), xp("write", "jpa", "CDWY2_cpu2s_avg"), xp("write", "jpa", "CDWY2_iowait_pct"),
                        npp("read", "jpa", "CDWY2_cpu2s_avg"), xp("read", "jpa", "CDWY2_cpu2s_avg"),
                        npp("read", "jpa", "CDWY1_cpu2s_avg"), xp("read", "jpa", "CDWY1_cpu2s_avg"),
                        npp("read", "jpa", "app_host_cpu2s_ms_per_req"), xp("read", "jpa", "app_host_cpu2s_ms_per_req"),
                        npp("read", "jpa", "app_gc_pause_pct"), xp("read", "jpa", "app_gc_pause_pct"),
                        100 - pct(x("read", "jpa", "steady_throughput"), nm("read", "jpa")))))
    recs = [(op, i) for op, i in imps if (op, "recovery", 10, i) in XJ]
    rec_err = sum(int(XJ[(op, "recovery", 10, i)]["full_errors"]) for op, i in recs)
    rec_avg = [f(XJ[(op, "recovery", 10, i)], "steady_avg_ms") for op, i in recs]
    out.append(("p", "撤压后 10 线程恢复检查的平均响应时间为 %.1f～%.1f ms，%s，两种服务都立即恢复。"
                     % (min(rec_avg), max(rec_avg), "全部请求成功" if rec_err == 0 else "出现 %s 个错误" % n(rec_err))))
    return out


def conclusion_tail(XJ, NJ, NMAX):
    imps = [(op, i) for op in ("read", "write") for i in ("jpa", "mongo")]
    x = lambda op, impl, k: f(XJ[(op, "maxload", NMAX[op], impl)], k)
    nm = lambda op, impl, k: f(NJ[(op, "main", MAIN_T[op], impl)], k)
    xr = [x(op, i, "steady_avg_ms") / nm(op, i, "steady_avg_ms") for op, i in imps]
    return [
        ("p", "（4）逐级加压时，两种实现都能让 %d 个写入线程同时运行且零错误，写入吞吐量从 400 线程起已经饱和；查询两种实现都通过的最高一级为 "
              "%d 线程，更高一级先到达 2 核压测机的上限（压测机 CPU 占满，应用服务器只有约 30%%），不代表数据库的上限。"
              % (NMAX["write"], NMAX["read"])),
        ("p", "（5）在这一线程数下持续压测，吞吐量停留在饱和水平，平均响应时间升至主对比的 %.0f～%.0f 倍，应用服务器成为负载最高的一台；"
              "MySQL 查询的饱和点由数据库转到应用服务器，吞吐量比 50 线程时低 %.0f%%。撤压后两种服务立即恢复。评价性能应同时观察吞吐量、"
              "尾延迟和资源饱和位置。"
              % (min(xr), max(xr), 100 - pct(x("read", "jpa", "steady_throughput"), nm("read", "jpa", "steady_throughput")))),
        ("p", "（6）局限：主对比与 j:true 对照各只做了 1 轮，重复性只能从逐级加压中写入各级的结果间接看出；查询的最高并发受 2 核压测机限制，"
              "要测更高的并发需要更强的压测机或多台压测机（JMeter 分布式）。"),
    ]


def main():
    blocks = build()
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
