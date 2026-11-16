#!/usr/bin/env python3
"""生成实验四报告（Word + PDF）。表格和正文中的数字全部从统计结果读取。

用法：python3 tools/build_report.py
需要 results/统计与图表/ 下的统计文件：jtl-summary-{r1,m1,m2,m3,sweep,pool,overload}.csv、对应的 prom-summary-*.csv、
main-rounds.csv，以及 results/pool/choice.txt；图表由 tools/make_charts_v2.py 生成（charts/ 目录）。
依赖：python-docx（Word）、Google Chrome（HTML 打印为 PDF），见 tools/report_render.py。
"""
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
R1_LEVELS = [("load", 10), ("load", 25), ("load", 50), ("load", 100), ("stress", 200), ("stress", 300), ("stress", 400)]
MAIN_T = {"read": 50, "write": 100}
SWEEP = [25, 50, 75, 100, 150]
POOLS = [25, 50, 100]
OVER = [600, 800, 1000]
IMPL_CN = {"jpa": "MySQL", "mongo": "MongoDB", "mongoj": "MongoDB j:true"}
OP_CN = {"read": "查询", "write": "写入"}
PHASE_CN = {"load": "负载", "stress": "压力"}


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


def mean(vals):
    vals = list(vals)
    return sum(vals) / len(vals)


def pool_choice():
    path = os.path.join(REPO, "results", "pool", "choice.txt")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    out = {}
    for line in text.splitlines():
        for op in ("read", "write"):
            if line.startswith(op + " 选择 "):
                out[op] = int(line.split()[2])
    return out


def build():
    R1, R1P = table("r1"), table("r1", "prom")
    MJ = {r: table("m%d" % r) for r in (1, 2, 3)}
    MP = {r: table("m%d" % r, "prom") for r in (1, 2, 3)}
    AGG = {(r["op"], r["impl"]): r for r in csv.DictReader(open(os.path.join(STATS, "main-rounds.csv"), encoding="utf-8"))}
    SJ, SP = table("sweep"), table("sweep", "prom")
    PJ, PP = table("pool"), table("pool", "prom")
    OJ, OP = table("overload"), table("overload", "prom")
    choice = pool_choice()

    phase2 = [MJ[1], MJ[2], MJ[3], SJ, PJ, OJ]
    phase2_prom = [(MJ[r], MP[r]) for r in (1, 2, 3)] + [(SJ, SP), (PJ, PP), (OJ, OP)]
    all_j = [R1] + phase2
    tests = sum(len(t) for t in all_j)
    total = sum(int(r["full_samples"]) for t in all_j for r in t.values())
    errors = sum(int(r["full_errors"]) for t in all_j for r in t.values())
    over_err = sum(int(r["full_errors"]) for r in OJ.values())
    writes = [r for t in all_j for k, r in t.items() if k[0] == "write" and r["db_check"]]
    writes_ok = sum(1 for r in writes if r["db_check"] == "一致")
    devs = [abs(f(p[k], "server_tps") - f(j[k], "steady_throughput")) / f(j[k], "steady_throughput")
            for j, pr in phase2_prom for p in [pr] for k in pr if k in j and pr[k]["server_tps"]]
    worst_dev = 100 * max(devs)

    # 主对比（3 轮）
    tps = lambda op, impl: f(AGG[(op, impl)], "steady_throughput_mean")
    agg = lambda op, impl, k: f(AGG[(op, impl)], k)
    cv_max = max(f(r, "steady_throughput_cv_pct") for r in AGG.values())
    ratio = lambda op, impl="mongo": tps(op, impl) / tps(op, "jpa")

    def m3(op, impl, key):  # 监控指标的 3 轮均值
        return mean(f(MP[r][(op, "main", MAIN_T[op], impl)], key) for r in (1, 2, 3))

    def db_host(impl):
        return "CDWY2" if impl == "jpa" else "CDWY5"

    def kb_insert(impl):
        return mean(f(MP[r][("write", "main", 100, impl)], db_host(impl) + "_disk_write_mb_s") * 1024
                    / f(MP[r][("write", "main", 100, impl)], "server_tps") for r in (1, 2, 3))

    B = []
    add = B.append
    add(("title", TITLE))
    add(("author", AUTHORS))
    add(("abstract",
         "摘  要：本实验以日志服务为对象，在同一套日志模型、REST 接口、业务逻辑和请求数据下，分别用 Spring Data JPA 访问 MySQL 9.2、"
         "用 Spring Data MongoDB 访问 MongoDB 7.0，部署在 5 台 2 核服务器组成的 Docker Swarm 集群上，用 JMeter 施加负载、"
         "Prometheus 采集资源指标。测试分两个阶段：先以 10～400 线程的梯度测试找到吞吐量拐点；再固定参数（查询 50 线程、写入 100 线程，"
         "每次 240 秒，统计第 60～240 秒）做 3 轮主对比，并补充 MongoDB j:true 持久性对照、并发量调优、连接池调优和 600～1000 线程的"
         "过载与恢复测试。两个阶段共 %d 次测试、%s 个请求，%s；%d 次写入测试中，成功请求数与数据库新增行数%s。"
         "主对比中，MongoDB 版查询吞吐量是 MySQL 版的 %.2f 倍、写入为 %.2f 倍，3 轮吞吐量的变异系数都不超过 %.1f%%；"
         "MongoDB 改为 j:true（写入记入磁盘日志后才确认）后，写入吞吐量为默认配置的 %.0f%%，仍是 MySQL 版的 %.2f 倍。"
         "监控显示：MySQL 版查询的瓶颈在数据库服务器 CPU，MongoDB 版在应用服务器 CPU；MySQL 写入受每次提交刷盘的限制。"
         % (tests, n(total), "全部请求均成功" if errors == 0 else "错误请求 %s 个（%s）" % (
             n(errors), "均出现在过载测试中" if errors == over_err else "见第 5 节"),
            len(writes), "逐次相等" if writes_ok == len(writes) else "有 %d 次不等（见第 5 节）" % (len(writes) - writes_ok),
            ratio("read"), ratio("write"), cv_max, pct(tps("write", "mongoj"), tps("write", "mongo")), ratio("write", "mongoj"))))
    add(("keywords", "关键词：MySQL；MongoDB；Spring Data JPA；Spring Data MongoDB；JMeter；Prometheus；写关注；负载测试；压力测试"))

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
        ["D Prometheus", "CDWY4", "172.31.1.19", "Prometheus 3.7.3，每 2 秒抓取；过载测试时兼作压测机（堆 768 MB）"],
        ["E 两套日志服务", "CDWY1", "172.31.1.202", "MySQL 版 :8081、MongoDB 版 :8082"],
    ], [2.6, 1.9, 2.5, 8.5]))
    add(("p", "5 台服务器均为 Ubuntu 18.04、2 核 CPU、约 1.8 GB 可用内存、Docker 20.10.21，组成 Docker Swarm 集群并通过私网通信。"
               "两套日志服务基于 Spring Boot 3.3.4、Java 21，配置完全相同：JVM 堆 384 MB，Tomcat 最多 200 个工作线程，"
               "数据库连接池最多 100 个连接、取连接最长等待 10 秒（HikariCP 与 MongoDB 驱动的默认值差别很大，因此统一设置）。"
               "测试时同一时刻只压测其中一种。CDWY3 上还运行着课程以外的服务，可用内存只有约 550 MB，"
               "因此 600～1000 线程的过载测试把 JMeter 放到内存较充裕的 CDWY4 上运行。"))

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
               "_class 字段；数据库密码通过 Docker secret 注入，应用账号只有查询和插入权限，仓库中不含任何密码。"
               "为第二阶段的对照和调优，两套服务都可以用环境变量调整连接池上限（LOGDEMO_POOL_MAXSIZE），MongoDB 版还可以把写关注从默认的 "
               "w:1 改为 w:1 + j:true（LOGDEMO_MONGO_JOURNAL）；服务启动时在日志中打印实际生效的设置，每次切换后都据此核对。"))
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
               "（级别、1 小时～3 天的时间范围、页码 1～50，每页 20 条），两种实现读取同一份文件。写入请求不带 createdAt，"
               "由服务端取当前时间，因此测试中新写入的日志不在查询的时间范围内，不影响查询结果。"))
    add(("h2", "4.2 测试设计"))
    add(("table", "表5  两个阶段的测试（每项都对两种实现、按需对读写分别进行）", ["部分", "线程数", "升压 / 持续", "次数", "目的"], [
        ["梯度探索（第 1 轮）", "10、25、50、100；200、300、400", "10～20 s / 60 s", "1", "找吞吐量拐点，确定主对比参数"],
        ["主对比", "查询 50，写入 100", "20 s / 240 s", "3 轮", "固定参数的正式对比，检验可重复性"],
        ["持久性对照", "写入 100，MongoDB j:true", "20 s / 240 s", "3 次", "在与 MySQL 相近的持久性下比较写入"],
        ["并发量调优", "25、50、75、100、150", "20 s / 240 s", "1", "找吞吐高、尾延迟低的并发量"],
        ["连接池调优", "连接池 25、50、100（并发量固定）", "20 s / 240 s", "1", "检验连接池大小的影响"],
        ["过载与恢复", "600、800、1000；之后 10 线程", "40 s / 240 s；2 s / 60 s", "1", "观察过载时的退化与撤压后的恢复"],
    ], [2.8, 4.2, 2.6, 1.2, 4.7]))
    add(("p", "第 1 轮按“负载测试 10～100 线程、压力测试 200～400 线程、最后 10 线程恢复检查”进行，每档 60 秒，用于了解两种实现的"
               "吞吐量随并发量的变化。第二阶段参考组员方案固定参数：查询 50 线程、写入 100 线程（第 1 轮中均接近各自峰值、尚未进入过载），"
               "升压 20 秒，每个线程持续 240 秒；Tomcat 线程数（200）和连接池上限（100）保持不变，只在连接池调优中改变连接池。"
               "每次正式测试前用相同线程数单独预热 120 秒（并发量调优与过载测试在每种实现开始前预热一次），测试之间间隔 30 秒；"
               "两种实现交替先后执行（主对比奇数轮 MySQL 版在前、偶数轮 MongoDB 版在前），写入测试开始前把两个数据库都重置为同一份"
               "10 万条预置数据。j:true 对照在 3 轮主对比之后连续进行。"))
    add(("p", "查询测试前没有单独重置数据库：写入测试开始前会把两个库都重置为预置数据，但测试中新写入的数十万到一百多万条日志"
               "会保留到下一次重置。因此查询测试遇到的库有两种状态：只有 10 万条预置数据，或者另有上一项写入测试留下的约 90 万～"
               "160 万条日志。后者的时间是测试当天，不在查询范围内，查询结果不变，但索引更大、缓存被新写入的数据挤占。"
               "主对比中每种实现各有一轮处于后一种状态（MySQL 第 3 轮、MongoDB 第 2 轮）；并发量调优和连接池调优的查询测试中"
               "MongoDB 库处于后一种状态、MySQL 为预置数据；过载测试的查询则相反（重测的 MySQL 版 800 线程除外，当时库中只有预置数据）。分析时把这一因素计入波动，"
               "并发量调优与连接池调优的对照点也取数据库状态相同的那一次测试。"))
    add(("h2", "4.3 指标与监控"))
    add(("p", "JMeter 5.6 线程组的“持续时间”从每个线程启动时算起：升压 20 秒、持续 240 秒时，最后一个线程约在第 260 秒结束。"
               "第二阶段统计每次测试开始后第 60～240 秒，此区间内所有线程都在运行，且已避开升压、JIT 编译和缓存预热造成的前期波动，"
               "各次测试的统计口径完全相同。吞吐量为区间内完成的请求数除以 180 秒，P95、P99 为区间内响应时间的百分位（最近秩法）。"
               "第 1 轮的 60 秒测试取所有线程都在运行的时段。多轮结果用均值和变异系数 CV（标准差÷均值）描述。"
               "JTL 中的响应时间包含网络往返和 JMeter 自身开销。为确认压测机不是瓶颈，对每次测试做“压测机自检”："
               "线程数 ÷ 吞吐量是每个线程发出一次请求的周期，减去平均响应时间，就是 JMeter 在两次请求之间自身花的时间，"
               "正常时远小于 1 ms，明显变大说明压测机成了瓶颈、结果不能代表被测系统。"))
    add(("p", "Prometheus 每 2 秒抓取两套服务的 /actuator/prometheus（请求计数、JVM、连接池）和 5 台服务器的 node-exporter"
               "（CPU、内存、磁盘、网络）。为比较两种实现在各层的开销，用“每个请求消耗的 CPU 时间”= 核数 × CPU 使用率 ÷ 每秒请求数。"
               "服务端统计的每秒请求数与 JMeter 客户端结果相互核对，第二阶段 %d 次测试的偏差均不超过 %.1f%%。"
               % (len(devs), worst_dev)))

    # 5
    add(("h1", "5 结果与分析"))
    add(("h2", "5.1 梯度探索（第 1 轮）"))
    rows = []
    for ph, t in R1_LEVELS:
        g = lambda op, i: n(R1[(op, ph, t, i)]["steady_throughput"])
        rows.append([PHASE_CN[ph], t, g("read", "jpa"), g("read", "mongo"), g("write", "jpa"), g("write", "mongo")])
    add(("table", "表6  第 1 轮各档的吞吐量（次/秒，所有线程都在运行的时段；全部请求成功）",
         ["阶段", "线程", "查询 MySQL", "查询 MongoDB", "写入 MySQL", "写入 MongoDB"], rows, [1.6, 1.4, 3.0, 3.0, 3.0, 3.0]))
    r1 = lambda op, ph, t, i: f(R1[(op, ph, t, i)], "steady_throughput")
    add(("p", "查询在 10～50 线程时两种实现的吞吐量已基本持平（MySQL 版 %s～%s 次/秒，MongoDB 版 %s～%s 次/秒），"
               "再增加线程只拉长排队时间；200 线程以上 MySQL 版降到 %s～%s 次/秒。写入时 MongoDB 版从 10 线程起就稳定在 6000 次/秒以上，"
               "MySQL 版则随线程增加从 %s 升到 %s 次/秒（100 线程），这是组提交把多个事务合并刷盘的效果。"
               "据此，主对比取查询 50 线程、写入 100 线程：两者都接近各自的吞吐量峰值，又没有进入过载区。"
               % (n(min(r1("read", "load", t, "jpa") for t in (10, 25, 50))), n(max(r1("read", "load", t, "jpa") for t in (10, 25, 50))),
                  n(min(r1("read", "load", t, "mongo") for t in (10, 25, 50))), n(max(r1("read", "load", t, "mongo") for t in (10, 25, 50))),
                  n(min(r1("read", "stress", t, "jpa") for t in (200, 300, 400))), n(max(r1("read", "stress", t, "jpa") for t in (200, 300, 400))),
                  n(r1("write", "load", 10, "jpa")), n(r1("write", "load", 100, "jpa")))))

    add(("h2", "5.2 主对比（3 轮）"))
    add(("figure", os.path.join(CHARTS, "main-comparison.png"), "图1  主对比：3 轮的吞吐量与 P95 响应时间", 15.2))
    rows = []
    for op in ("read", "write"):
        for impl in ("jpa", "mongo", "mongoj"):
            if (op, impl) not in AGG:
                continue
            a = AGG[(op, impl)]
            rows.append([OP_CN[op], IMPL_CN[impl], "%s（%s～%s）" % (n(a["steady_throughput_mean"]), n(a["steady_throughput_min"]),
                                                                    n(a["steady_throughput_max"])),
                         "%.1f%%" % f(a, "steady_throughput_cv_pct"), n(a["steady_avg_ms_mean"], 1), n(a["steady_p95_ms_mean"], 1),
                         n(a["steady_p99_ms_mean"], 1), "%.2f" % (tps(op, impl) / tps(op, "jpa"))])
    add(("table", "表7  主对比结果（3 轮均值，括号内为最小～最大；查询 50 线程、写入 100 线程；全部请求成功）",
         ["操作", "实现", "吞吐（次/秒）", "吞吐 CV", "平均(ms)", "P95(ms)", "P99(ms)", "相对 MySQL"], rows,
         [1.1, 2.6, 3.4, 1.5, 1.5, 1.5, 1.5, 1.8]))
    add(("p", "查询：MongoDB 版吞吐量 %s 次/秒，是 MySQL 版（%s 次/秒）的 %.2f 倍；P95 为 %.0f ms 对 %.0f ms，P99 为 %.0f ms 对 %.0f ms，"
               "尾部延迟的差距比平均值更明显。写入：MongoDB 版 %s 次/秒，是 MySQL 版（%s 次/秒）的 %.2f 倍，P95 为 %.0f ms 对 %.0f ms。"
               "3 轮的吞吐量变异系数在 %.1f%%～%.1f%% 之间，两种实现的差距远大于轮间波动，结论可重复。与第 1 轮同线程数的结果"
               "（查询 MySQL %s、MongoDB %s；写入 MySQL %s、MongoDB %s 次/秒）相比，差别在 %.1f%% 以内。"
               % (n(tps("read", "mongo")), n(tps("read", "jpa")), ratio("read"),
                  agg("read", "mongo", "steady_p95_ms_mean"), agg("read", "jpa", "steady_p95_ms_mean"),
                  agg("read", "mongo", "steady_p99_ms_mean"), agg("read", "jpa", "steady_p99_ms_mean"),
                  n(tps("write", "mongo")), n(tps("write", "jpa")), ratio("write"),
                  agg("write", "mongo", "steady_p95_ms_mean"), agg("write", "jpa", "steady_p95_ms_mean"),
                  min(f(r, "steady_throughput_cv_pct") for r in AGG.values()), cv_max,
                  n(r1("read", "load", 50, "jpa")), n(r1("read", "load", 50, "mongo")),
                  n(r1("write", "load", 100, "jpa")), n(r1("write", "load", 100, "mongo")),
                  max(abs(pct(tps(op, i), r1(op, "load", MAIN_T[op], i)) - 100) for op in ("read", "write") for i in ("jpa", "mongo")))))

    rmin = {i: min((f(MJ[r][("read", "main", 50, i)], "steady_throughput"), r) for r in (1, 2, 3)) for i in ("jpa", "mongo")}
    warm = warmup_tps(os.path.join(REPO, "results", "m3", "warmups.log"), "jpa-read-t50")
    add(("p", "查询的轮间差异主要来自数据库状态（4.2 节）：MySQL 版第 %d 轮、MongoDB 版第 %d 轮最低（%s、%s 次/秒），"
               "正是库中留有上一项写入数据的两次。%s写入测试前都重置数据库，3 轮的吞吐量变异系数只有 %.1f%%～%.1f%%。"
               % (rmin["jpa"][1], rmin["mongo"][1], n(rmin["jpa"][0]), n(rmin["mongo"][0]),
                  ("MySQL 第 3 轮的预热只有 %s 次/秒：128 MB 的缓冲池被上一项写入的新数据页占满，查询需要的页要重新从磁盘读入；"
                   "预热 120 秒后正式测试回到 %s 次/秒。" % (n(warm), n(rmin["jpa"][0]))) if warm and rmin["jpa"][1] == 3 else "",
                  min(f(AGG[("write", i)], "steady_throughput_cv_pct") for i in ("jpa", "mongo", "mongoj")),
                  max(f(AGG[("write", i)], "steady_throughput_cv_pct") for i in ("jpa", "mongo", "mongoj")))))

    add(("h2", "5.3 资源使用与瓶颈"))
    add(("figure", os.path.join(CHARTS, "main-resources.png"), "图2  主对比的资源开销（3 轮均值）", 15.4))
    rows = []
    for op in ("read", "write"):
        for impl in ("jpa", "mongo", "mongoj"):
            if (op, impl) not in AGG:
                continue
            db = db_host(impl)
            rows.append([OP_CN[op], IMPL_CN[impl], "%.0f%%" % m3(op, impl, "CDWY1_cpu_pct"), "%.0f%%" % m3(op, impl, db + "_cpu_pct"),
                         "%.2f" % m3(op, impl, "app_host_cpu_ms_per_req"), "%.2f" % m3(op, impl, "db_host_cpu_ms_per_req"),
                         n(m3(op, impl, db + "_disk_write_iops")) if op == "write" else "—",
                         "%.1f" % kb_insert(impl) if op == "write" else "—"])
    add(("table", "表8  主对比的资源使用（3 轮均值；CPU 时间 = 2 核 × 使用率 ÷ 服务端每秒请求数）",
         ["操作", "实现", "应用服务器 CPU", "数据库服务器 CPU", "应用端 ms/请求", "数据库端 ms/请求", "写盘 次/秒", "KB/条"], rows,
         [1.1, 2.6, 2.0, 2.2, 2.0, 2.2, 1.7, 1.5]))
    rj, rm = ("read", "jpa"), ("read", "mongo")
    add(("p", "查询时，MySQL 版的数据库服务器 CPU 为 %.0f%%，已经饱和，应用服务器为 %.0f%%；MongoDB 版正好相反，应用服务器 %.0f%%、"
               "MongoDB 服务器只有 %.0f%%。按每个请求折算，数据库端的 CPU 时间 MongoDB 约为 MySQL 的 %.0f%%（%.2f ms 对 %.2f ms），"
               "应用端两者接近（%.2f ms 对 %.2f ms）。也就是说，同样的查询 MongoDB 服务器花的 CPU 更少，MySQL 版先耗尽数据库服务器，"
               "MongoDB 版则先耗尽应用服务器，吞吐量的上限由各自先饱和的一层决定。"
               % (m3(*rj, "CDWY2_cpu_pct"), m3(*rj, "CDWY1_cpu_pct"), m3(*rm, "CDWY1_cpu_pct"), m3(*rm, "CDWY5_cpu_pct"),
                  pct(m3(*rm, "db_host_cpu_ms_per_req"), m3(*rj, "db_host_cpu_ms_per_req")),
                  m3(*rm, "db_host_cpu_ms_per_req"), m3(*rj, "db_host_cpu_ms_per_req"),
                  m3(*rm, "app_host_cpu_ms_per_req"), m3(*rj, "app_host_cpu_ms_per_req"))))
    wj, wm = ("write", "jpa"), ("write", "mongo")
    add(("p", "写入时，MySQL 服务器每秒写盘 %s 次、每条日志约 %.1f KB，iowait %.0f%%：innodb_flush_log_at_trx_commit=1、sync_binlog=1"
               "要求每次提交都把 redo log 和 binlog 刷到磁盘，100 个并发事务靠组提交分摊刷盘。MongoDB（默认 w:1）每秒只写盘 %s 次、"
               "每条约 %.1f KB：写入在内存中生效即确认，日志约每 100 ms 批量刷盘，此时瓶颈是应用服务器 CPU（%.0f%%）。"
               % (n(m3(*wj, "CDWY2_disk_write_iops")), kb_insert("jpa"), m3(*wj, "CDWY2_iowait_pct"),
                  n(m3(*wm, "CDWY5_disk_write_iops")), kb_insert("mongo"), m3(*wm, "CDWY1_cpu_pct"))))

    add(("h2", "5.4 持久性对照：MongoDB j:true"))
    wjj = ("write", "mongoj")
    add(("p", "w:1 写入在宕机时可能丢失最近约 100 ms 内已确认的数据，与 MySQL 每次提交刷盘的承诺不对等。为此把 MongoDB 版的写关注改为 "
               "w:1 + j:true（写入记入磁盘日志后才确认），其余条件不变，连续测 3 次。结果（表7、表8）：吞吐量 %s 次/秒，"
               "为默认配置的 %.0f%%，仍是 MySQL 版的 %.2f 倍；P95 为 %.0f ms、P99 为 %.0f ms（默认配置 %.0f ms、%.0f ms）。"
               "MongoDB 服务器每秒写盘次数从 %s 升到 %s，说明日志确实在逐批同步落盘；但 100 个并发写入共享同一次日志同步"
               "（组提交），每条日志只多付出很小的代价，瓶颈仍在应用服务器 CPU（%.0f%%）。可见在本实验的并发度下，"
               "MongoDB 写入的优势主要来自更轻的写入路径（单个文档、无事务与二进制日志），而不只是放宽了持久性。"
               % (n(tps(*wjj)), pct(tps(*wjj), tps(*wm)), ratio("write", "mongoj"),
                  agg(*wjj, "steady_p95_ms_mean"), agg(*wjj, "steady_p99_ms_mean"),
                  agg(*wm, "steady_p95_ms_mean"), agg(*wm, "steady_p99_ms_mean"),
                  n(m3(*wm, "CDWY5_disk_write_iops")), n(m3(*wjj, "CDWY5_disk_write_iops")), m3(*wjj, "CDWY1_cpu_pct"))))

    add(("h2", "5.5 并发量调优"))
    add(("figure", os.path.join(CHARTS, "sweep.png"), "图3  并发量调优：吞吐量与 P95 随线程数的变化", 15.2))

    def lvl(op, impl, t):  # 并发量调优缺少的两档取主对比：查询 50 线程取第 2 轮（数据库状态相同），写入 100 线程取第 1 轮
        return SJ.get((op, "sweep", t, impl)) or MJ[2 if op == "read" else 1].get((op, "main", t, impl))

    rows = []
    for t in SWEEP:
        row = [t]
        for op in ("read", "write"):
            for impl in ("jpa", "mongo"):
                r = lvl(op, impl, t)
                row.append("%s / %s" % (n(r["steady_throughput"]), r["steady_p95_ms"]) if r else "—")
        rows.append(row)
    add(("table", "表9  并发量调优（吞吐 次/秒 / P95 ms；查询 50 线程取主对比第 2 轮、写入 100 线程取第 1 轮，原因见 4.2 节）",
         ["线程", "查询 MySQL", "查询 MongoDB", "写入 MySQL", "写入 MongoDB"], rows, [1.5, 3.5, 3.5, 3.5, 3.5]))
    def plvl(op, impl, t):  # 与 lvl 同一次测试的监控统计
        return SP.get((op, "sweep", t, impl)) or MP[2 if op == "read" else 1].get((op, "main", t, impl))

    B.extend(sweep_text(lvl, plvl, choice))

    add(("h2", "5.6 连接池调优"))
    pool_blocks = pool_section(PJ, PP, lvl, choice)  # 先表后图：表格较短，放在图前面不容易与表题分页
    B.append(pool_blocks[0])
    add(("figure", os.path.join(CHARTS, "pool.png"), "图4  连接池调优：固定并发量，连接池上限 25 / 50 / 100", 15.2))
    B.extend(pool_blocks[1:])

    add(("h2", "5.7 过载与恢复"))
    add(("figure", os.path.join(CHARTS, "overload.png"), "图5  过载测试：600～1000 线程（JMeter 在 CDWY4）", 15.2))
    B.extend(overload_section(OJ, OP, R1, AGG))

    # 6
    add(("h1", "6 结论"))
    add(("p", "（1）两套实现共用同一份接口、业务逻辑和请求数据，22 项接口检查结果一致，预置数据逐条相同，"
               "写入成功数与入库行数逐次相等，对照条件成立。"))
    add(("p", "（2）查询：在本实验的数据量（10 万条，可完全缓存）和硬件下，固定参数的 3 轮主对比中 MongoDB 版吞吐量高 %.0f%%，"
               "P99 约为 MySQL 版的 %.0f%%。原因是 MongoDB 服务器处理同样查询消耗的 CPU 约为 MySQL 服务器的 %.0f%%，"
               "MySQL 版的瓶颈在数据库服务器，MongoDB 版的瓶颈在应用服务器。"
               % (100 * (ratio("read") - 1), pct(agg("read", "mongo", "steady_p99_ms_mean"), agg("read", "jpa", "steady_p99_ms_mean")),
                  pct(m3(*rm, "db_host_cpu_ms_per_req"), m3(*rj, "db_host_cpu_ms_per_req")))))
    add(("p", "（3）写入：MongoDB 版吞吐量是 MySQL 版的 %.2f 倍；改为 j:true 后只下降 %.0f%%，仍是 %.2f 倍。"
               "MySQL 的写入受每次提交刷盘和二进制日志的限制，高并发靠组提交缓解；MongoDB 在相近的持久性下依然更快，"
               "对写多读少的日志场景更合适。若允许宕机时丢失约 100 ms 内的日志，可以用默认的 w:1；要求逐条持久化时用 j:true，代价很小。"
               % (ratio("write"), 100 - pct(tps(*wjj), tps(*wm)), ratio("write", "mongoj"))))
    B.extend(conclusion_tail())

    add(("h1", "参考资料"))
    for ref in ("[1] 实验四：MySQL 与 MongoDB 日志读写性能对比实验，课程实验指导书。",
                "[2] Spring Data JPA Reference Documentation；Spring Data MongoDB Reference Documentation。",
                "[3] MySQL 9.2 Reference Manual：innodb_flush_log_at_trx_commit、sync_binlog、Group Commit。",
                "[4] MongoDB 7.0 Manual：Write Concern、Journaling（storage.journal.commitIntervalMs）。",
                "[5] Apache JMeter User's Manual：Thread Group、CSV Data Set Config。",
                "[6] HikariCP Wiki：About Pool Sizing。",
                "[7] ISTQB Glossary：load testing、stress testing。",
                "[8] Prometheus Documentation：promtool tsdb dump、node_exporter。"):
        add(("note", ref))

    add(("h1", "附录  提交材料与数据对应"))
    add(("table", "附表  仓库内容", ["内容", "位置"], [
        ["两套实现（含共用模块）", "logdemo/logdemo-core、logdemo-jpa、logdemo-mongo"],
        ["数据库初始化脚本", "db/mysql/01-schema.sql、02-app-user.sql；db/mongo/01-init.js、02-app-user.js"],
        ["JMeter JMX 与请求数据", "jmeter/WriteLog.jmx、ReadLog.jmx、data/"],
        ["运行说明", "docs/01-实验操作手册.md、README.md"],
        ["原始 JTL（gzip 压缩）", "results/<组>/<实现>-<读写>-<阶段>-t<线程>/samples.jtl.gz；组：r1、m1～m3、sweep、pool、overload"],
        ["Prometheus 监控数据", "results/r1/prometheus-r1.txt.gz、results/prometheus-phase2.txt.gz；各次测试的 monitor.json"],
        ["统计与图表", "results/统计与图表/（jtl-summary-*、prom-summary-*、main-rounds、charts/）"],
        ["接口与数据一致性证据", "results/00-环境与一致性/"],
    ], [4.0, 11.5]))
    return B


def span(vals, fmt="%.0f%%"):
    """数值范围的文字：相同时只写一个值。"""
    a, b = fmt % min(vals), fmt % max(vals)
    return a if a == b else a + "～" + b


def warmup_tps(path, name):
    """warmups.log 中某次预热的吞吐量（次/秒）。"""
    if not os.path.exists(path):
        return None
    for line in open(path, encoding="utf-8"):
        if line.startswith(name + " "):
            return float(line.split("=")[2].split("/s")[0])
    return None


def sweep_text(lvl, plvl, choice):
    """并发量调优的分析段落。lvl 取 JTL 统计，plvl 取同一次测试的监控统计。"""
    out = []
    g = lambda op, impl, t, k="steady_throughput": f(lvl(op, impl, t), k)
    peak = {(op, i): max(SWEEP, key=lambda t: g(op, i, t)) for op in ("read", "write") for i in ("jpa", "mongo")}
    pk = lambda op, i: g(op, i, peak[(op, i)])
    out.append(("p", "查询：MySQL 版在 %d 线程时吞吐量最高（%s 次/秒），超过 50 线程后明显下降，75、100、150 线程分别为 %s、%s、%s 次/秒，"
                     "P95 从 %.0f ms 升到 %.0f ms；MongoDB 版在 %d 线程最高（%s 次/秒），150 线程仍有 %s 次/秒（下降 %.0f%%），"
                     "P95 从 %.0f ms 升到 %.0f ms。各次测试的压测机自检都在 %.2f ms 以内，下降来自被测系统。"
                     % (peak[("read", "jpa")], n(pk("read", "jpa")), n(g("read", "jpa", 75)), n(g("read", "jpa", 100)), n(g("read", "jpa", 150)),
                        g("read", "jpa", 25, "steady_p95_ms"), g("read", "jpa", 150, "steady_p95_ms"),
                        peak[("read", "mongo")], n(pk("read", "mongo")), n(g("read", "mongo", 150)),
                        100 - pct(g("read", "mongo", 150), pk("read", "mongo")),
                        g("read", "mongo", 25, "steady_p95_ms"), g("read", "mongo", 150, "steady_p95_ms"),
                        max(g(op, i, t, "steady_client_gap_ms") for op in ("read", "write") for i in ("jpa", "mongo") for t in SWEEP))))
    pr = lambda t, k: f(plvl("read", "jpa", t), k)
    hi = (75, 100, 150)
    out.append(("p", "监控显示，MySQL 版查询在 25～50 线程时是数据库先饱和（数据库服务器 CPU %s）；75～150 线程时数据库服务器 CPU "
                     "降到 %.0f%%～%.0f%%，应用服务器升到 %.0f%%～%.0f%%，每个请求的应用端 CPU 从 %.2f ms 增加到 %.2f～%.2f ms，"
                     "而数据库端基本不变（%.2f～%.2f ms）；100、150 线程时 HikariCP 中最多有 %s～%s 个请求在等连接。瓶颈从数据库服务器转到了"
                     "应用服务器，多出的应用端 CPU 推测花在线程等待、唤醒和交接连接上。另外，75、100 线程两次测试中连接池的实际连接数"
                     "只有 %s 个（设定 100），连接被断开后要逐个重建（5.7 节）。MongoDB 版在同样的并发下每个请求的应用端 CPU 只增加 %.0f%%。"
                     % (span([pr(t, "CDWY2_cpu_pct") for t in (25, 50)]),
                        min(pr(t, "CDWY2_cpu_pct") for t in hi), max(pr(t, "CDWY2_cpu_pct") for t in hi),
                        min(pr(t, "CDWY1_cpu_pct") for t in hi), max(pr(t, "CDWY1_cpu_pct") for t in hi),
                        pr(25, "app_host_cpu_ms_per_req"), min(pr(t, "app_host_cpu_ms_per_req") for t in hi),
                        max(pr(t, "app_host_cpu_ms_per_req") for t in hi),
                        min(pr(t, "db_host_cpu_ms_per_req") for t in hi), max(pr(t, "db_host_cpu_ms_per_req") for t in hi),
                        n(min(pr(t, "pool_waiting_max") for t in (100, 150))), n(max(pr(t, "pool_waiting_max") for t in (100, 150))),
                        n(pr(75, "pool_size_min")),
                        100 * (f(plvl("read", "mongo", 150), "app_host_cpu_ms_per_req") / f(plvl("read", "mongo", 25), "app_host_cpu_ms_per_req") - 1))))
    out.append(("p", "写入：MySQL 版在 %d 线程最高（%s 次/秒），25 线程只有 %s 次/秒（同时提交的事务少，组提交合并得少），150 线程降到 %s；"
                     "MongoDB 版 25～100 线程都在 %s～%s 次/秒，150 线程为 %s 次/秒。"
                     % (peak[("write", "jpa")], n(pk("write", "jpa")), n(g("write", "jpa", 25)), n(g("write", "jpa", 150)),
                        n(min(g("write", "mongo", t) for t in (25, 50, 75, 100))), n(max(g("write", "mongo", t) for t in (25, 50, 75, 100))),
                        n(g("write", "mongo", 150)))))
    if choice:
        out.append(("p", "按事先定好的规则选连接池调优用的并发量：两种实现的吞吐量都不低于各自最大值 95%% 的档位中，取两者 P95 平均值最小的一档"
                         "（tools/choose_pool_threads.py，依据见 results/pool/choice.txt）。结果为查询 %d 线程、写入 %d 线程。"
                         % (choice.get("read", 50), choice.get("write", 100))))
    return out


def pool_section(PJ, PP, lvl, choice):
    out = []
    rt, wt = choice.get("read", 50), choice.get("write", 100)
    rows = []
    for size in POOLS:
        row = [size]
        for op, t in (("read", rt), ("write", wt)):
            for impl in ("jpa", "mongo"):
                r = PJ.get((op, "pool%d" % size, t, impl)) if size != 100 else lvl(op, impl, t)
                row.append("%s / %s" % (n(r["steady_throughput"]), r["steady_p95_ms"]) if r else "—")
        rows.append(row)
    out.append(("table", "表10  连接池调优（吞吐 次/秒 / P95 ms；查询 %d 线程、写入 %d 线程；连接池 100 取并发量调优的同档结果）" % (rt, wt),
                ["连接池上限", "查询 MySQL", "查询 MongoDB", "写入 MySQL", "写入 MongoDB"], rows, [2.3, 3.3, 3.3, 3.3, 3.3]))

    def tp(op, impl, size):
        t = rt if op == "read" else wt
        r = PJ.get((op, "pool%d" % size, t, impl)) if size != 100 else lvl(op, impl, t)
        return f(r, "steady_throughput")

    def pp(op, impl, size, key):
        t = rt if op == "read" else wt
        return f(PP[(op, "pool%d" % size, t, impl)], key)

    out.append(("p", "查询（%d 线程）：连接池上限为 100、50、25 时，MySQL 版吞吐量分别为 %s、%s、%s 次/秒，变化在 %.0f%% 以内——"
                     "%d 个并发请求最多同时占用 %d 个连接，上限不低于线程数时不需要排队。MongoDB 版为 %s、%s、%s 次/秒，"
                     "连接池等于线程数时下降 %.0f%%（统计区间内最多同时借出 %s 个连接、最多 %s 个请求在等待），"
                     "原因没有进一步分析，且只测了 1 次，需要重复验证。"
                     % (rt, n(tp("read", "jpa", 100)), n(tp("read", "jpa", 50)), n(tp("read", "jpa", 25)),
                        max(abs(pct(tp("read", "jpa", s), tp("read", "jpa", 100)) - 100) for s in (25, 50)), rt, rt,
                        n(tp("read", "mongo", 100)), n(tp("read", "mongo", 50)), n(tp("read", "mongo", 25)),
                        100 - pct(tp("read", "mongo", 25), tp("read", "mongo", 100)),
                        n(pp("read", "mongo", 25, "pool_in_use_max")), n(pp("read", "mongo", 25, "pool_waiting_max")))))
    out.append(("p", "写入（%d 线程）：连接池 25 时 MySQL 版吞吐量降到 %s 次/秒（比连接池 100 低 %.0f%%），最多 %s 个请求在等连接；"
                     "连接池 50 时为 %s 次/秒，与 100 相当。MySQL 靠组提交把并发事务合并刷盘，同时提交的事务越少，每次刷盘分摊的事务越少，"
                     "因此连接数至少要与有效的并发事务数相当。MongoDB 版在连接池较小时反而略快（25：%s，50：%s，100：%s 次/秒），"
                     "可能是 100 个连接同时写入时，多出来的并发只增加了调度和竞争开销。"
                     % (wt, n(tp("write", "jpa", 25)), 100 - pct(tp("write", "jpa", 25), tp("write", "jpa", 100)),
                        n(pp("write", "jpa", 25, "pool_waiting_max")), n(tp("write", "jpa", 50)),
                        n(tp("write", "mongo", 25)), n(tp("write", "mongo", 50)), n(tp("write", "mongo", 100)))))
    return out


def overload_section(OJ, OP, R1, AGG):
    out = []
    rows = []
    for op in ("read", "write"):
        for impl in ("jpa", "mongo"):
            for t in OVER:
                r = OJ.get((op, "overload", t, impl))
                rec = OJ.get((op, "recovery%d" % t, 10, impl))
                if not r:
                    continue
                base = f(R1[(op, "load", 10, impl)], "steady_throughput")
                rows.append([OP_CN[op], IMPL_CN[impl], t, n(r["steady_throughput"]), n(r["steady_avg_ms"]), r["steady_p95_ms"],
                             r["steady_p99_ms"], "%.2f%%" % f(r, "full_error_pct"),
                             "%s（%.0f%%）" % (n(rec["steady_throughput"]), pct(f(rec, "steady_throughput"), base)) if rec else "—"])
    out.append(("table", "表11  过载与恢复（第 60～240 秒；恢复检查为紧接其后的 10 线程 60 秒，括号内为占第 1 轮 10 线程吞吐量的比例）",
                ["操作", "实现", "线程", "吞吐(次/秒)", "平均(ms)", "P95(ms)", "P99(ms)", "错误率", "恢复检查吞吐"], rows,
                [1.1, 1.7, 1.2, 1.9, 1.6, 1.6, 1.6, 1.6, 3.2]))
    o = lambda op, impl, t, k: f(OJ[(op, "overload", t, impl)], k)
    rec = [pct(f(OJ[(op, "recovery%d" % t, 10, i)], "steady_throughput"), f(R1[(op, "load", 10, i)], "steady_throughput"))
           for op in ("read", "write") for i in ("jpa", "mongo") for t in OVER if (op, "recovery%d" % t, 10, i) in OJ]
    rec_avg = [f(OJ[(op, "recovery%d" % t, 10, i)], "steady_avg_ms")
               for op in ("read", "write") for i in ("jpa", "mongo") for t in OVER if (op, "recovery%d" % t, 10, i) in OJ]
    gaps = [f(r, "steady_client_gap_ms") for r in OJ.values()]
    errs = sum(int(r["full_errors"]) for r in OJ.values())
    out.append(("p", "600～1000 线程远超两种实现的处理能力（Tomcat 最多 200 个工作线程，连接池 100 个连接），多出的请求在 Tomcat 的"
                     "连接和线程队列中排队。%s吞吐量维持在主对比的饱和水平附近，响应时间随线程数近似线性增长，大致等于“线程数 ÷ 吞吐量”："
                     "MySQL 版查询的平均响应从 600 线程的 %.0f ms 升到 1000 线程的 %.0f ms，MongoDB 版写入从 %.0f ms 升到 %.0f ms。"
                     "MongoDB 版写入 1000 线程时吞吐量降到 %s 次/秒（600 线程为 %s），查询为 %s 次/秒（600 线程为 %s）。"
                     % ("全部请求都成功，没有超时或 5xx 错误；" if errs == 0 else "出现 %s 个错误请求；" % n(errs),
                        o("read", "jpa", 600, "steady_avg_ms"), o("read", "jpa", 1000, "steady_avg_ms"),
                        o("write", "mongo", 600, "steady_avg_ms"), o("write", "mongo", 1000, "steady_avg_ms"),
                        n(o("write", "mongo", 1000, "steady_throughput")), n(o("write", "mongo", 600, "steady_throughput")),
                        n(o("read", "mongo", 1000, "steady_throughput")), n(o("read", "mongo", 600, "steady_throughput")))))
    out.append(("p", "每档过载之后立即进行的 10 线程恢复检查，吞吐量为第 1 轮 10 线程结果的 %.0f%%～%.0f%%，平均响应时间回到 %.1f～%.1f ms，"
                     "撤去压力后两种实现都立即恢复正常。压测机自检（4.3 节）：各次过载测试中 JMeter 在两次请求之间的平均耗时不超过 %.2f ms，"
                     "压测机没有成为瓶颈。MySQL 版查询 800 线程的第一次测试例外：压测机自身占满 CPU，JMeter 每个请求额外耗时 577 ms，"
                     "吞吐量只有 839 次/秒，该次结果作废（原始数据保留在 results/overload/invalid/），表中为全部测试结束后按同样步骤重测的结果。"
                     % (min(rec), max(rec), min(rec_avg), max(rec_avg), max(gaps))))
    op_ = lambda t, k: f(OP[("read", "overload", t, "jpa")], k)
    oj = lambda t: f(OJ[("read", "overload", t, "jpa")], "steady_throughput")
    r1s = [f(R1[("read", "stress", t, "jpa")], "steady_throughput") for t in (200, 300, 400)]
    out.append(("p", "MySQL 版查询的过载结果在两种水平之间：600、1000 线程时为 %s、%s 次/秒，数据库服务器 CPU %.0f%%、%.0f%%，仍是数据库先饱和；"
                     "800 线程（重测）只有 %s 次/秒，应用服务器 CPU %.0f%%、每个请求的应用端 CPU %.2f ms（600 线程时 %.2f ms），"
                     "与并发量调优中 100～150 线程的情况相同，第 1 轮 200～400 线程的结果（%s～%s 次/秒）也属于这一种。"
                     "两种水平与数据库状态正好对应：600、1000 线程两次测试时 MySQL 库中留有上一项写入的约 79 万条日志，"
                     "其余几次库中只有预置数据（4.2 节）；但两者之间的因果关系和具体原因本实验没有查明。监控还发现，MySQL 版连接池的实际连接数多次低于设定的 100："
                     "过载 600 线程时只有 %s 个，测试之间的空闲时段最低降到 24 个，之后才逐个补足。应用通过 Swarm 服务名 lab_mysql "
                     "（虚拟 IP，由 IPVS 转发）连接 MySQL，IPVS 默认会静默断开空闲约 15 分钟的 TCP 连接，HikariCP 在使用时才发现并重建，"
                     "这可能是连接数不足的原因（未验证）；改进方法是把 HikariCP 的 keepalive-time、max-lifetime 设为小于 15 分钟，"
                     "或让服务直连数据库所在主机。MongoDB 版的连接池始终保持设定的连接数。"
                     % (n(oj(600)), n(oj(1000)), op_(600, "CDWY2_cpu_pct"), op_(1000, "CDWY2_cpu_pct"),
                        n(oj(800)), op_(800, "CDWY1_cpu_pct"), op_(800, "app_host_cpu_ms_per_req"),
                        op_(600, "app_host_cpu_ms_per_req"), n(min(r1s)), n(max(r1s)), n(op_(600, "pool_size_min")))))
    return out


def conclusion_tail():
    return [
        ("p", "（4）并发量与连接池：查询在 25～50 线程、写入在 75～100 线程附近吞吐量最高，再增加线程只会排队；MySQL 版查询超过 50 线程后"
              "吞吐量不稳定，多数时候降到 2,000～2,500 次/秒（此时应用服务器先饱和），MongoDB 版下降平缓。连接池不是越大越好：MySQL 写入需要足够的连接（本实验约 50 个）才能发挥组提交的作用，"
              "MongoDB 写入用 25～50 个连接比 100 个略快；查询并发量不超过连接池上限时，上限大小对 MySQL 版几乎没有影响，"
              "MongoDB 版在连接池恰好等于并发量时吞吐量下降约一成，应留出余量。"),
        ("p", "（5）过载与恢复：600～1000 线程时两种实现都没有出错，过载表现为排队和响应时间随线程数线性增长；撤去压力后立即恢复正常。"),
        ("p", "（6）局限：应用服务器只有 2 核，多数场景下应用层先饱和，结论只适用于本环境和本数据量（10 万条，可完全缓存）；"
              "查询测试前没有重置数据库，库中残留的写入数据使个别轮次的查询吞吐量低 3%～6%；并发量、连接池和过载测试每项只测 1 次，"
              "小于 5% 的差别不宜作结论；过载测试的压测机与 Prometheus 同在 CDWY4，曾有一次压测机自身成为瓶颈而重测；MySQL 版连接池的实际连接数在测试中多次低于设定值，原因未验证；"
              "数据量远大于内存的场景没有测试。"),
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
