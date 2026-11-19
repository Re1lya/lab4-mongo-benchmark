#!/usr/bin/env python3
"""生成实验四报告（Word + PDF）。正文以组员 11-17 的修改稿为底稿，表格和正文中的数字全部从统计结果读取。

用法：python3 tools/build_report.py
需要 results/统计与图表/ 下的统计文件：
  第一、二阶段 jtl-summary-{r1,m1,m2,m3,sweep,pool,overload}.csv、对应的 prom-summary-*.csv、main-rounds.csv、results/pool/choice.txt；
  第三阶段（11-19 按老师更新后的 Prometheus 配置）jtl/prom-summary-{n1,x1}.csv、jtl-summary-probe.csv、results/probe/probe.log。
图表由 tools/make_charts_v2.py 生成（charts/ 目录）。依赖：python-docx（Word）、Google Chrome（HTML 打印为 PDF），见 report_render.py。
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


def span(vals, fmt="%.0f%%"):
    """数值范围的文字：相同时只写一个值。"""
    a, b = fmt % min(vals), fmt % max(vals)
    return a if a == b else a + "～" + b


def db_host(impl):
    return "CDWY2" if impl == "jpa" else "CDWY5"


def pool_choice():
    path = os.path.join(REPO, "results", "pool", "choice.txt")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    out = {}
    for line in text.splitlines():
        for op in ("read", "write"):
            if line.startswith(op + " 选择 "):
                out[op] = int(line.split()[2])
    return out


def probe_rows():
    """results/probe/probe.log：每一级一行，含是否通过。"""
    path = os.path.join(REPO, "results", "probe", "probe.log")
    rows = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"(\w+) (read|write) (t=.*)$", line.strip())
        if not m:
            continue
        kv = dict(x.split("=", 1) for x in m.group(3).split() if "=" in x)
        rows.append(dict(kv, impl=m.group(1), op=m.group(2)))
    return rows


def probe_choice():
    path = os.path.join(REPO, "results", "probe", "choice.txt")
    return {k: int(v) for k, v in (line.strip().split("=") for line in open(path, encoding="utf-8") if "=" in line)}


def build():
    R1 = table("r1")
    MJ = {r: table("m%d" % r) for r in (1, 2, 3)}
    MP = {r: table("m%d" % r, "prom") for r in (1, 2, 3)}
    AGG = {(r["op"], r["impl"]): r for r in csv.DictReader(open(os.path.join(STATS, "main-rounds.csv"), encoding="utf-8"))}
    SJ, SP = table("sweep"), table("sweep", "prom")
    PJ, PP = table("pool"), table("pool", "prom")
    OJ, OP = table("overload"), table("overload", "prom")
    NJ, NP = table("n1"), table("n1", "prom")          # 第三阶段：新监控配置下复测的主对比 1 轮（含 j:true）
    QJ, QP = table("probe"), table("probe", "prom")    # 第三阶段：最多同时运行线程数逐级加压（未通过的一级按整次测试统计监控）
    XJ, XP = table("x1"), table("x1", "prom")          # 第三阶段：最多线程数下持续压测 1 轮
    PR, NMAX = probe_rows(), probe_choice()
    choice = pool_choice()

    all_j = [R1, MJ[1], MJ[2], MJ[3], SJ, PJ, OJ, NJ, QJ, XJ]
    tests = sum(len(t) for t in all_j)
    total = sum(int(r["full_samples"]) for t in all_j for r in t.values())
    errors = sum(int(r["full_errors"]) for t in all_j for r in t.values())
    probe_err = sum(int(r["full_errors"]) for r in QJ.values())
    writes = [r for t in all_j for k, r in t.items() if k[0] == "write" and r["db_check"]]
    writes_n = sum(1 for t in all_j for k in t if k[0] == "write")
    writes_ok = sum(1 for r in writes if r["db_check"] == "一致")
    pairs = [(MJ[r], MP[r]) for r in (1, 2, 3)] + [(SJ, SP), (PJ, PP), (OJ, OP), (NJ, NP), (XJ, XP)]
    devs = [abs(f(p[k], "server_tps") - f(j[k], "steady_throughput")) / f(j[k], "steady_throughput")
            for j, pp in pairs for p in [pp] for k in p if k in j and p[k]["server_tps"]]

    # 第二阶段三轮主对比
    tps = lambda op, impl: f(AGG[(op, impl)], "steady_throughput_mean")
    agg = lambda op, impl, k: f(AGG[(op, impl)], k)
    ratio = lambda op, impl="mongo": tps(op, impl) / tps(op, "jpa")
    r1 = lambda op, ph, t, i: f(R1[(op, ph, t, i)], "steady_throughput")
    # 第三阶段复测（新监控配置）
    nj = lambda op, impl, k="steady_throughput": f(NJ[(op, "main", MAIN_T[op], impl)], k)
    npm = lambda op, impl, k: f(NP[(op, "main", MAIN_T[op], impl)], k)

    def kb_insert_n(impl):
        r = NP[("write", "main", 100, impl)]
        return f(r, db_host(impl) + "_disk_write_mb_s") * 1024 / f(r, "server_tps")

    B = []
    add = B.append
    add(("title", TITLE))
    add(("author", AUTHORS))
    nr, nw = NMAX.get("read"), NMAX.get("write")
    # j:true：第二阶段 3 次均值与第三阶段复测 1 次
    jt = [pct(tps("write", "mongoj"), tps("write", "mongo")), pct(nj("write", "mongoj"), nj("write", "mongo"))]
    jr = [ratio("write", "mongoj"), nj("write", "mongoj") / nj("write", "jpa")]
    # 最多线程数下持续压测：平均响应时间相对正式对比复测的倍数
    xr = [f(XJ[(op, "maxload", NMAX[op], i)], "steady_avg_ms") / nj(op, i, "steady_avg_ms") for op in ("read", "write") for i in ("jpa", "mongo")]
    add(("abstract",
         "摘  要：本实验在相同日志模型、REST 接口、业务逻辑和请求数据下，比较 Spring Data JPA/MySQL 9.2 与 Spring Data "
         "MongoDB/MongoDB 7.0 两条日志读写链路。系统部署于 5 台 2 核服务器，使用 JMeter 施加负载、Prometheus 采集资源指标。"
         "先进行 10～400 线程梯度探索，再以查询 50 线程、写入 100 线程完成 3 轮正式对比，并开展写关注、并发量、连接池和 600～1000 "
         "线程过载测试。课程将 Prometheus 的 CPU 使用率由 5 分钟平均改为 2 秒平均（每 1 秒采集、每 2 秒计算）后，本组按新配置复测"
         "正式对比与 j:true 各 1 次，并借鉴其他组的做法逐级加压，找出两种实现都能让全部线程同时运行且零错误的最高线程数（查询 %d、"
         "写入 %d；查询受 2 核压测机限制），再在该线程数下持续压测。%d 次测试共处理 %s 个请求，%s。正式对比中，MongoDB 版查询"
         "吞吐量为 MySQL 版的 %.2f 倍，写入为 %.2f 倍；查询 P99 的三轮均值分别为 %.1f ms 和 %.1f ms。MongoDB 启用 j:true 后，写入"
         "吞吐量为默认配置的 %s，仍为 MySQL 版的 %s 倍。按 2 秒平均的 CPU 使用率，查询时 MySQL 版数据库服务器 CPU 为 %.0f%%，"
         "MongoDB 版应用服务器 CPU 为 %.0f%%。增加并发量后，吞吐量进入平台或下降，响应时间继续增加；最高线程数下两种实现仍处理了"
         "全部请求，但吞吐量没有提高，平均响应时间升至正式对比的 %.0f～%.0f 倍。"
         % (nr, nw, tests, n(total),
            "错误数为 0" if errors == 0 else "除逐级加压中未通过的一级外，错误数为 0" if errors == probe_err else "错误数为 %s" % n(errors),
            ratio("read"), ratio("write"), agg("read", "mongo", "steady_p99_ms_mean"), agg("read", "jpa", "steady_p99_ms_mean"),
            span(jt), span(jr, "%.2f"), npm("read", "jpa", "CDWY2_cpu2s_avg"), npm("read", "mongo", "CDWY1_cpu2s_avg"),
            min(xr), max(xr))))
    add(("keywords", "关键词：MySQL；MongoDB；Spring Data JPA；Spring Data MongoDB；JMeter；Prometheus；写关注；负载测试；压力测试"))

    # 1
    add(("h1", "1 实验目的"))
    add(("p", "（1）掌握 Spring Data JPA 访问 MySQL、Spring Data MongoDB 访问 MongoDB 的基本方法，分别完成日志数据的写入和条件分页查询。"))
    add(("p", "（2）使用同一套日志业务模型、接口定义、请求数据和测试方法，对照实现 JPA/MySQL 与 Spring Data MongoDB/MongoDB 两条日志读写链路。"))
    add(("p", "（3）使用 JMeter 和 Prometheus 对两种方案进行负载测试和压力测试，比较吞吐量、响应时间、错误率和各服务器资源使用，并找出各自的瓶颈。"))

    # 2
    add(("h1", "2 实验环境"))
    add(("table", "表1  服务器分工与软件版本", ["指导书角色", "本组服务器", "私网地址", "本实验内容"], [
        ["A 编译、JMeter", "CDWY3", "172.31.12.156", "JDK 21、Maven 3.9.16、JMeter 5.6.3（堆 400 MB；过载、逐级加压与持续压测 768 MB）"],
        ["B MySQL", "CDWY2", "172.31.8.46", "MySQL 9.2.0，库 lab4_log；缓冲池 128 MB（默认）"],
        ["C MongoDB 7.0", "CDWY5", "172.31.13.151", "MongoDB 7.0.48；WiredTiger 缓存 0.25 GB"],
        ["D Prometheus", "CDWY4", "172.31.1.19", "Prometheus 3.7.3，第三阶段每 1 秒采集（此前每 2 秒）；第二阶段过载测试时兼作压测机"],
        ["E 两套日志服务", "CDWY1", "172.31.1.202", "MySQL 版 :8081、MongoDB 版 :8082"],
    ], [2.6, 1.9, 2.5, 8.5]))
    add(("p", "5 台服务器均为 Ubuntu 18.04、2 核 CPU、约 1.8 GB 内存、Docker 20.10.21，组成 Docker Swarm 集群并通过私网通信。"
               "两套服务使用 Spring Boot 3.3.4、Java 21，JVM 堆均为 384 MB，Tomcat 最多 200 个工作线程，数据库连接池上限均为 100，"
               "取连接最长等待 10 秒。每次只对一种实现施压。第二阶段 CDWY3 运行其他服务后可用内存约 550 MB，600～1000 线程测试改由 "
               "CDWY4 运行 JMeter，堆上限设为 768 MB；第三阶段测试前暂停了 CDWY3 上课程以外的 rbac 服务，可用内存约 1.3 GB，"
               "全部测试回到 CDWY3 发压。"))

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
               "写入请求不带 createdAt，由服务端生成当前时间；新增日志落在查询时间范围之外，查询始终面向预置数据。"))
    add(("h2", "4.2 测试设计"))
    add(("table", "表5  三个阶段的测试（每项都对两种实现、按需对读写分别进行）", ["部分", "线程数", "Ramp-up / 总时长", "次数", "目的"], [
        ["梯度探索（第一阶段）", "10、25、50、100；200、300、400", "10～20 s / 60 s", "1", "找吞吐量拐点，确定主对比参数"],
        ["主对比", "查询 50，写入 100", "20 s / 240 s", "3 轮", "固定参数的正式对比，检验可重复性"],
        ["持久性对照", "写入 100，MongoDB j:true", "20 s / 240 s", "3 次", "比较等待 journal 持久化后的写入性能"],
        ["并发量调优", "25、50、75、100、150", "20 s / 240 s", "1", "找吞吐高、尾延迟低的并发量"],
        ["连接池调优", "连接池 25、50、100（并发量固定）", "20 s / 240 s", "1", "检验连接池大小的影响"],
        ["过载与恢复", "600、800、1000；之后 10 线程", "40 s / 240 s；2 s / 60 s", "1", "观察过载时的退化与撤压后的恢复"],
        ["复测主对比（第三阶段）", "查询 50，写入 100；j:true 写入 100", "20 s / 240 s", "1", "按新的监控配置取得 CPU 数据"],
        ["最多同时运行线程数", "400、800、1200、1600、2000 逐级", "线程数/20 s / 再加 90 s", "1", "找全部线程同时运行且零错误的最高一级"],
        ["最多线程数下持续压测", "上一项选出的线程数；之后 10 线程", "不超过 60 s / 240 s；2 s / 60 s", "1", "最高并发下的吞吐、延迟、资源与恢复"],
    ], [3.0, 4.1, 3.0, 1.1, 4.3]))
    add(("p", "第一阶段按 10、25、50、100、200、300、400 线程依次测试，每档持续 60 秒，最后以 10 线程检查撤压后的服务表现。"
               "第二阶段固定查询 50 线程、写入 100 线程，Ramp-up 为 20 秒，总持续时间为 240 秒，完成 3 轮主对比。Tomcat 工作线程上限"
               "保持 200，数据库连接池上限保持 100，连接池调优时再改变后者。正式测试前单独预热 120 秒，并发量调优与过载测试按每种实现"
               "预热一次。测试间脚本等待 30 秒。主对比奇数轮先测 MySQL 版，偶数轮先测 MongoDB 版；每次写入测试前将两库重置为同一份 "
               "10 万条数据。j:true 对照在主对比之后连续进行 3 次。"))
    add(("p", "查询测试沿用当时的数据库状态。主对比中，MySQL 第 3 轮和 MongoDB 第 2 轮保留了前次写入数据，其余查询轮次为 10 万条预置"
               "数据。并发量与连接池调优时，MongoDB 保留前次写入数据，MySQL 为预置数据；过载查询时则相反，重测的 MySQL 800 线程为预置"
               "数据。额外日志虽不进入查询结果，仍会增加索引规模并改变缓存内容。并发量与连接池分析因此选用状态相同的主对比记录作为复用档位。"))
    add(("p", "第三阶段在课程更新 Prometheus 配置后进行（4.3 节），JMeter 全部在 CDWY3 上运行，并且每一项测试前都把两库"
               "重置为预置数据（查询测试也重置），避免了上面的数据库状态差异。正式对比与 j:true 各复测 1 次，参数与第二阶段相同。"
               "随后借鉴其他组的做法，先找“最多同时运行的线程数”：两种实现的查询、写入各自从 400 线程起逐级加到 2000 线程，"
               "Ramp-up 按每秒启动 20 个线程计，全部线程启动后再运行 90 秒；某一级同时满足“JMeter 的活跃线程数达到设定值、零错误、"
               "压测机自检正常（4.3 节）”才算通过，不通过即停止加压。每种操作取两种实现都通过的最高一级，再在该线程数下持续压测 240 秒"
               "（Ramp-up 不超过 60 秒，统计第 60～240 秒），之后间隔 30 秒做 10 线程、60 秒的恢复检查。"))
    add(("h2", "4.3 指标与监控"))
    add(("p", "JMeter 线程组的 Duration 包含 Ramp-up。20 秒 Ramp-up 表示在约 20 秒内陆续启动全部线程，已启动线程随即发送请求；"
               "主对比的总时长约为 240 秒。第二、三阶段以首条请求的开始时间为起点，选取第 60 秒至第 240 秒之前开始的请求，吞吐量为该区间"
               "样本数除以 180 秒。平均响应时间和 P95、P99 均由这些请求的 elapsed 计算，百分位采用最近秩法。第一阶段、逐级加压与 60 秒"
               "恢复检查选取所有线程均已启动的时段。三轮汇总取各轮指标的算术平均，表中的 P95、P99 为各轮百分位的均值；吞吐量波动以变异"
               "系数 CV 描述。elapsed 表示客户端记录的请求耗时，包含连接、网络传输和服务端处理时间。"))
    add(("p", "Prometheus 抓取服务的 /actuator/prometheus 和各节点的 node-exporter，记录请求计数、JVM、连接池以及 CPU、内存、磁盘和"
               "网络指标。11-19 课程更新了 CPU 使用率的计算：记录规则 node:cpu_usage_percent 由 5 分钟平均改为 2 秒平均，即 "
               "(1 − Σrate(node_cpu_seconds_total{mode=\"idle\"}[2s]) ÷ Σrate(node_cpu_seconds_total[2s])) × 100%，node-exporter 每 1 秒"
               "采集、规则每 2 秒计算一次。5 分钟平均会把一次几分钟的测试与前后的空闲、准备时段混在一起，无法反映测试期间的 CPU。"
               "本组按新配置更新后进行第三阶段，第三阶段的 CPU 使用率取统计区间内该规则（2 秒平均）的均值与最大值。第一、二阶段为每 2 秒"
               "采集，CPU 使用率按统计区间内 CPU 时间计数器的增量计算，即统计区间的平均值，不受 5 分钟平均的影响。"))
    add(("p", "每请求 CPU 时间按“2 核 × 节点 CPU 使用率 ÷ 服务端每秒请求数”计算，反映节点资源开销。第二、三阶段 %d 次测试的服务端与 "
               "JMeter 吞吐量偏差均不超过 %.1f%%。压测端同时检查 CPU、可用内存和线程启动情况，并用“线程数 ÷ 吞吐量 − 平均响应时间”"
               "辅助观察发压间隙（压测机自检）。%d 次有效测试包括 %d 次写入测试，其中 %d 次保存了入库数量核对结果，成功请求数均等于新增记录数。"
               % (len(devs), 100 * max(devs), tests, writes_n, len(writes))))

    # 5
    add(("h1", "5 结果与分析"))
    add(("h2", "5.1 第一阶段梯度探索"))
    rows = []
    for ph, t in R1_LEVELS:
        g = lambda op, i: n(R1[(op, ph, t, i)]["steady_throughput"])
        rows.append([PHASE_CN[ph], t, g("read", "jpa"), g("read", "mongo"), g("write", "jpa"), g("write", "mongo")])
    add(("table", "表6  第 1 轮各档的吞吐量（次/秒，所有线程都在运行的时段；全部请求成功）",
         ["阶段", "线程", "查询 MySQL", "查询 MongoDB", "写入 MySQL", "写入 MongoDB"], rows, [1.6, 1.4, 3.0, 3.0, 3.0, 3.0]))
    lv = lambda op, i, ts: [r1(op, ph, t, i) for ph, t in R1_LEVELS if t in ts]
    add(("p", "10～50 线程时，MySQL 版查询吞吐量为 %s～%s 次/秒，MongoDB 版为 %s～%s 次/秒，均已接近这一阶段的高位。MySQL 版在 "
               "200～400 线程下降至 %s～%s 次/秒。写入方面，MySQL 版从 10 线程的 %s 次/秒升至 100 线程的 %s 次/秒，MongoDB 版各档为 "
               "%s～%s 次/秒。由此选取查询 50 线程、写入 100 线程作为固定对比条件，再通过三轮较长测试比较吞吐量和响应时间。"
               % (n(min(lv("read", "jpa", (10, 25, 50)))), n(max(lv("read", "jpa", (10, 25, 50)))),
                  n(min(lv("read", "mongo", (10, 25, 50)))), n(max(lv("read", "mongo", (10, 25, 50)))),
                  n(min(lv("read", "jpa", (200, 300, 400)))), n(max(lv("read", "jpa", (200, 300, 400)))),
                  n(r1("write", "load", 10, "jpa")), n(r1("write", "load", 100, "jpa")),
                  n(min(r1("write", ph, t, "mongo") for ph, t in R1_LEVELS)), n(max(r1("write", ph, t, "mongo") for ph, t in R1_LEVELS)))))

    add(("h2", "5.2 三轮主对比"))
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
    add(("table", "表7  主对比结果（三轮指标均值；吞吐括号为最小～最大；查询 50 线程、写入 100 线程）",
         ["操作", "实现", "吞吐（次/秒）", "吞吐 CV", "平均(ms)", "P95(ms)", "P99(ms)", "相对 MySQL"], rows,
         [1.1, 2.6, 3.4, 1.5, 1.5, 1.5, 1.5, 1.8]))
    cvs = [f(r, "steady_throughput_cv_pct") for r in AGG.values()]
    wcvs = [f(AGG[("write", i)], "steady_throughput_cv_pct") for i in ("jpa", "mongo", "mongoj")]
    rmin = {i: min((f(MJ[r][("read", "main", 50, i)], "steady_throughput"), r) for r in (1, 2, 3)) for i in ("jpa", "mongo")}
    add(("p", "MongoDB 版查询平均吞吐量为 %s 次/秒，MySQL 版为 %s 次/秒，前者高 %.0f%%；平均响应时间分别为 %.1f ms 和 %.1f ms，"
               "P95 均值为 %.1f ms 和 %.1f ms，P99 均值为 %.1f ms 和 %.1f ms。差距在尾部响应时间上更明显。写入平均吞吐量分别为 %s 次/秒和 "
               "%s 次/秒，MongoDB 版为 MySQL 版的 %.2f 倍；平均响应时间分别为 %.1f ms 和 %.1f ms。各组吞吐量 CV 为 %s，"
               "三轮均呈现相同的性能排序。"
               % (n(tps("read", "mongo")), n(tps("read", "jpa")), 100 * (ratio("read") - 1),
                  agg("read", "mongo", "steady_avg_ms_mean"), agg("read", "jpa", "steady_avg_ms_mean"),
                  agg("read", "mongo", "steady_p95_ms_mean"), agg("read", "jpa", "steady_p95_ms_mean"),
                  agg("read", "mongo", "steady_p99_ms_mean"), agg("read", "jpa", "steady_p99_ms_mean"),
                  n(tps("write", "mongo")), n(tps("write", "jpa")), ratio("write"),
                  agg("write", "mongo", "steady_avg_ms_mean"), agg("write", "jpa", "steady_avg_ms_mean"), span(cvs, "%.1f%%"))))
    add(("p", "保留前次写入数据的两轮查询恰好是各自吞吐量最低的一轮：MySQL 第 %d 轮为 %s 次/秒，MongoDB 第 %d 轮为 %s 次/秒。"
               "查询结果相同而数据库状态不同，解释轮间表现时需要结合这一条件。写入测试每次重置数据库，三轮吞吐量 CV 为 %s，低于查询组。"
               % (rmin["jpa"][1], n(rmin["jpa"][0]), rmin["mongo"][1], n(rmin["mongo"][0]), span(wcvs, "%.1f%%"))))
    dev = max(abs(pct(nj(op, i), tps(op, i)) - 100) for op in ("read", "write") for i in ("jpa", "mongo"))
    add(("p", "第三阶段按新监控配置、且查询前也重置数据库复测 1 次：查询 MySQL 版 %s、MongoDB 版 %s 次/秒（%.2f 倍），写入 MySQL 版 %s、"
               "MongoDB 版 %s 次/秒（%.2f 倍），与三轮均值相差均在 %.1f%% 以内，性能排序不变；MongoDB j:true 为 %s 次/秒，比三轮均值"
               "低 %.1f%%（5.4 节）。"
               % (n(nj("read", "jpa")), n(nj("read", "mongo")), nj("read", "mongo") / nj("read", "jpa"),
                  n(nj("write", "jpa")), n(nj("write", "mongo")), nj("write", "mongo") / nj("write", "jpa"), dev,
                  n(nj("write", "mongoj")), 100 - pct(nj("write", "mongoj"), tps("write", "mongoj")))))

    add(("h2", "5.3 资源使用与瓶颈"))
    add(("figure", os.path.join(CHARTS, "phase3-resources.png"), "图2  第三阶段复测的资源开销（CPU 使用率为 2 秒平均）", 15.4))
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
    add(("table", "表8  主对比复测的资源使用（第三阶段；CPU 为 2 秒平均在统计区间内的均值，括号为最大值；CPU 时间 = 2 核 × 使用率 ÷ 服务端每秒请求数）",
         ["操作", "实现", "应用服务器 CPU", "数据库服务器 CPU", "应用端 ms/请求", "数据库端 ms/请求", "磁盘写操作 次/秒", "磁盘写入 KB/条"],
         rows, [1.1, 2.4, 2.2, 2.3, 1.9, 2.0, 1.9, 1.7]))
    rj, rm = ("read", "jpa"), ("read", "mongo")
    add(("p", "查询时，MySQL 数据库节点 CPU 为 %.0f%%，应用节点为 %.0f%%；MongoDB 应用节点为 %.0f%%，数据库节点为 %.0f%%。"
               "每请求数据库节点 CPU 时间分别为 %.2f ms 和 %.2f ms，应用节点则接近，为 %.2f ms 和 %.2f ms。MySQL 版查询首先达到数据库 CPU "
               "上限，MongoDB 版首先达到应用 CPU 上限。MongoDB 数据库节点较低的单位请求开销，使应用能够处理更多请求后才到达饱和状态。"
               "2 秒平均的最大值显示，饱和的一端在统计区间内持续处于 %s 附近，而不是偶发的尖峰。"
               % (npm(*rj, "CDWY2_cpu2s_avg"), npm(*rj, "CDWY1_cpu2s_avg"), npm(*rm, "CDWY1_cpu2s_avg"), npm(*rm, "CDWY5_cpu2s_avg"),
                  npm(*rj, "db_host_cpu2s_ms_per_req"), npm(*rm, "db_host_cpu2s_ms_per_req"),
                  npm(*rj, "app_host_cpu2s_ms_per_req"), npm(*rm, "app_host_cpu2s_ms_per_req"),
                  span([npm(*rj, "CDWY2_cpu2s_avg"), npm(*rm, "CDWY1_cpu2s_avg")]))))
    wj, wm = ("write", "jpa"), ("write", "mongo")
    add(("p", "写入时，MySQL 数据库节点 CPU 为 %.0f%%，iowait 为 %.0f%%，磁盘写操作约 %s 次/秒，折算写入量为每条日志 %.1f KB。"
               "其 innodb_flush_log_at_trx_commit=1、sync_binlog=1，使事务提交需要满足 redo log 和 binlog 的同步要求。MongoDB 默认 "
               "w:1 下，数据库节点 CPU 为 %.0f%%，磁盘写操作约 %s 次/秒，每条日志 %.1f KB，应用节点 CPU 达 %.0f%%。两者在持久化确认"
               "方式和磁盘写入负担上存在差异，因此进一步用 j:true 观察等待日志持久化后的表现。表 8 的写盘次数来自节点块设备计数，"
               "写入量同时包含日志、数据页及索引等写入。"
               % (npm(*wj, "CDWY2_cpu2s_avg"), npm(*wj, "CDWY2_iowait_pct"), n(npm(*wj, "CDWY2_disk_write_iops")), kb_insert_n("jpa"),
                  npm(*wm, "CDWY5_cpu2s_avg"), n(npm(*wm, "CDWY5_disk_write_iops")), kb_insert_n("mongo"), npm(*wm, "CDWY1_cpu2s_avg"))))

    add(("h2", "5.4 MongoDB 写关注对照"))
    wjj = ("write", "mongoj")
    mp = lambda impl, k: [f(MP[r][("write", "main", 100, impl)], k) for r in (1, 2, 3)]   # 第二阶段三轮的监控值
    per_op = lambda tpsv, iops: tpsv / iops                                               # 每次写盘对应的写入条数
    p2_per_op = mean(per_op(f(MP[r][("write", "main", 100, "mongoj")], "server_tps"), f(MP[r][("write", "main", 100, "mongoj")], "CDWY5_disk_write_iops"))
                     for r in (1, 2, 3))
    p3_per_op = per_op(npm(*wjj, "server_tps"), npm(*wjj, "CDWY5_disk_write_iops"))
    add(("p", "默认 w:1 确认 MongoDB 已接受写入，不要求在返回前等待 journal 持久化；w:1 + j:true 增加这一等待。第二阶段在 100 线程下连续进行 "
               "3 次 j:true 测试，平均吞吐量 %s 次/秒，为默认配置的 %.0f%%，是 MySQL 版的 %.2f 倍；平均响应时间为 %.1f ms，P95、P99 均值为 "
               "%.1f ms、%.1f ms。这 3 次测试中数据库磁盘写操作约 %s 次/秒（默认配置约 %s 次/秒），应用节点 CPU 仍为 %s，吞吐量主要受"
               "接近满载的应用节点限制，因此下降不多。"
               % (n(tps(*wjj)), pct(tps(*wjj), tps(*wm)), ratio("write", "mongoj"), agg(*wjj, "steady_avg_ms_mean"),
                  agg(*wjj, "steady_p95_ms_mean"), agg(*wjj, "steady_p99_ms_mean"),
                  "%s～%s" % (n(min(mp("mongoj", "CDWY5_disk_write_iops")), 0), n(max(mp("mongoj", "CDWY5_disk_write_iops")))),
                  n(mean(mp("mongo", "CDWY5_disk_write_iops"))),
                  span(mp("mongoj", "CDWY1_cpu_pct")))))
    add(("p", "第三阶段复测 1 次为 %s 次/秒，为同阶段默认配置的 %.0f%%，是 MySQL 版的 %.2f 倍。启用 j:true 后数据库磁盘写操作由 %s 次/秒增至 "
               "%s 次/秒，每条日志的节点写入量由 %.1f KB 增至 %.1f KB，应用节点 CPU 则由 %.0f%% 降至 %.0f%%（2 秒平均），不再满载，说明请求有"
               "更多时间花在等待 journal 落盘上。按写盘次数折算，这次平均每次写盘对应约 %.0f 条写入（第二阶段约 %.0f 条），即每次落盘耗时"
               "更长、合并的请求更多。j:true 的代价因此与当时的磁盘写入延迟有关：应用节点接近满载时吞吐量下降约 %.0f%%，落盘等待成为主要"
               "限制时下降约 %.0f%%。"
               % (n(nj(*wjj)), pct(nj(*wjj), nj(*wm)), nj(*wjj) / nj("write", "jpa"),
                  n(npm(*wm, "CDWY5_disk_write_iops")), n(npm(*wjj, "CDWY5_disk_write_iops")), kb_insert_n("mongo"), kb_insert_n("mongoj"),
                  npm(*wm, "CDWY1_cpu2s_avg"), npm(*wjj, "CDWY1_cpu2s_avg"), p3_per_op, p2_per_op,
                  100 - pct(tps(*wjj), tps(*wm)), 100 - pct(nj(*wjj), nj(*wm)))))

    add(("h2", "5.5 并发量调优"))
    add(("figure", os.path.join(CHARTS, "sweep.png"), "图3  并发量调优：吞吐量与 P95 随线程数的变化", 15.2))

    def lvl(op, impl, t):  # 并发量调优缺少的两档取主对比：查询 50 线程取第 2 轮（数据库状态相同），写入 100 线程取第 1 轮
        return SJ.get((op, "sweep", t, impl)) or MJ[2 if op == "read" else 1].get((op, "main", t, impl))

    def plvl(op, impl, t):
        return SP.get((op, "sweep", t, impl)) or MP[2 if op == "read" else 1].get((op, "main", t, impl))

    rows = []
    for t in SWEEP:
        row = [t]
        for op in ("read", "write"):
            for impl in ("jpa", "mongo"):
                r = lvl(op, impl, t)
                row.append("%s / %s" % (n(r["steady_throughput"]), r["steady_p95_ms"]) if r else "—")
        rows.append(row)
    add(("table", "表9  并发量调优（吞吐 次/秒 / P95 ms；查询 50 线程复用主对比第 2 轮，写入 100 线程复用第 1 轮）",
         ["线程", "查询 MySQL", "查询 MongoDB", "写入 MySQL", "写入 MongoDB"], rows, [1.5, 3.5, 3.5, 3.5, 3.5]))
    B.extend(sweep_text(lvl, plvl, choice))

    add(("h2", "5.6 连接池调优"))
    pool_blocks = pool_section(PJ, PP, lvl, choice)
    B.append(pool_blocks[0])
    add(("figure", os.path.join(CHARTS, "pool.png"), "图4  连接池调优：固定并发量，连接池上限 25 / 50 / 100", 15.2))
    B.extend(pool_blocks[1:])

    add(("h2", "5.7 过载与恢复"))
    add(("figure", os.path.join(CHARTS, "overload.png"), "图5  过载测试：600～1000 线程（JMeter 在 CDWY4）", 15.2))
    B.extend(overload_section(OJ, OP, R1))

    add(("h2", "5.8 最多同时运行线程数（第三阶段）"))
    B.extend(probe_section(PR, QJ, QP, XJ, XP, NMAX))

    add(("h2", "5.9 最多线程数下持续压测（第三阶段）"))
    add(("figure", os.path.join(CHARTS, "maxload-cpu.png"), "图6  最多线程数下持续压测：各服务器 CPU 使用率（2 秒平均）", 15.2))
    B.extend(maxload_section(XJ, XP, NJ, NP, NMAX, R1))

    # 6
    add(("h1", "6 结论"))
    add(("p", "（1）两套日志服务完成了相同模型、接口和请求数据下的写入与条件分页查询。22 项接口检查结果一致，10 万条预置数据内容摘要一致；"
               "%d 次有入库核对记录的写入测试中，成功请求数均等于新增记录数。" % len(writes)))
    add(("p", "（2）三轮主对比中，MongoDB 版查询吞吐量高 %.0f%%，P99 均值为 MySQL 版的约 %.0f%%；数据库节点单位请求 CPU 开销更低。"
               "MySQL 版查询的主要饱和点在数据库 CPU，MongoDB 版在应用 CPU；按课程更新后的 2 秒平均 CPU 复测，结论不变。"
               % (100 * (ratio("read") - 1), pct(agg("read", "mongo", "steady_p99_ms_mean"), agg("read", "jpa", "steady_p99_ms_mean")))))
    add(("p", "（3）MongoDB 默认配置的写入吞吐量是 MySQL 版的 %.2f 倍。增加 j:true 后为 %.2f 倍（第三阶段复测 %.2f 倍），仍保留较大吞吐"
               "优势。j:true 使数据库磁盘写操作增加一个数量级，100 线程下吞吐量下降 %.0f%%～%.0f%%：应用 CPU 接近满载时下降较少，"
               "落盘等待成为主要限制时下降较多。"
               % (ratio("write"), ratio("write", "mongoj"), nj(*wjj) / nj("write", "jpa"),
                  100 - pct(tps(*wjj), tps(*wm)), 100 - pct(nj(*wjj), nj(*wm)))))
    add(("p", "（4）并发量调优中，查询 25 线程兼顾了高吞吐量与低 P95。MySQL 写入 75～100 线程吞吐接近，75 线程尾延迟更低；MongoDB 写入在 "
               "150 线程取得本组最高吞吐量，25 线程则有更低延迟。连接池 50 在已测组合中提供了较高查询吞吐量，并取得两种实现各自最高的单次"
               "写入吞吐量；连接池 100 的写入 P95 更低。"))
    B.extend(conclusion_tail(XJ, XP, NJ, NMAX))

    add(("h1", "参考资料"))
    for ref in ("[1] 实验四：Mongo 的读写性能测试，课程实验指导书。",
                "[2] Spring Data JPA Reference Documentation；Spring Data MongoDB Reference Documentation。",
                "[3] MySQL 9.2 Reference Manual：innodb_flush_log_at_trx_commit、sync_binlog、Group Commit。",
                "[4] MongoDB 7.0 Manual：Write Concern、Journaling（storage.journal.commitIntervalMs）。",
                "[5] Apache JMeter User's Manual：Thread Group、CSV Data Set Config。",
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
        ["Prometheus 配置", "deploy/prometheus/prometheus.yml、rules/recording.yml（11-19 更新后的 2 秒平均 CPU 规则）"],
        ["%d 次有效测试原始 JTL" % tests, "results/ 下 r1、m1～m3、sweep、pool、overload（第一、二阶段），n1、probe、x1（第三阶段）"
                                        "各测试目录的 samples.jtl.gz；第二阶段作废的一次另存于 overload/invalid/"],
        ["监控数据", "results/r1/prometheus-r1.txt.gz、results/prometheus-phase2.txt.gz、results/prometheus-phase3.txt.gz；各测试的 monitor.json"],
        ["请求与监控统计、图表", "results/统计与图表/ 下 jtl-summary-*、prom-summary-*、main-rounds 和 charts/"],
        ["接口及预置数据检查", "results/00-环境与一致性/"],
    ], [4.0, 11.5]))
    return B


def warmup_tps(path, name):
    if not os.path.exists(path):
        return None
    for line in open(path, encoding="utf-8"):
        if line.startswith(name + " "):
            return float(line.split("=")[2].split("/s")[0])
    return None


def sweep_text(lvl, plvl, choice):
    """并发量调优：沿用组员修改稿的写法，数字从统计结果读取（第二阶段数据）。"""
    out = []
    g = lambda op, impl, t, k="steady_throughput": f(lvl(op, impl, t), k)
    pk = {(op, i): max(SWEEP, key=lambda t: g(op, i, t)) for op in ("read", "write") for i in ("jpa", "mongo")}
    out.append(("p", "MySQL 版查询在 %d 线程达到本组最高吞吐量 %s 次/秒，25 线程为 %s 次/秒，达到该高值的 %.0f%%，P95 则由 %.0f ms 降至 "
                     "%.0f ms。继续增至 75、100、150 线程，吞吐量依次降为 %s、%s、%s 次/秒，P95 升至 %.0f、%.0f、%.0f ms。MongoDB 版在 25 "
                     "线程达到 %s 次/秒，P95 为 %.0f ms；150 线程时为 %s 次/秒，P95 达 %.0f ms。查询选择 25 线程，可以在两种实现上取得较高"
                     "吞吐量和更低尾延迟。"
                     % (pk[("read", "jpa")], n(g("read", "jpa", pk[("read", "jpa")])), n(g("read", "jpa", 25)),
                        pct(g("read", "jpa", 25), g("read", "jpa", pk[("read", "jpa")])),
                        g("read", "jpa", 50, "steady_p95_ms"), g("read", "jpa", 25, "steady_p95_ms"),
                        n(g("read", "jpa", 75)), n(g("read", "jpa", 100)), n(g("read", "jpa", 150)),
                        g("read", "jpa", 75, "steady_p95_ms"), g("read", "jpa", 100, "steady_p95_ms"), g("read", "jpa", 150, "steady_p95_ms"),
                        n(g("read", "mongo", 25)), g("read", "mongo", 25, "steady_p95_ms"),
                        n(g("read", "mongo", 150)), g("read", "mongo", 150, "steady_p95_ms"))))
    pr = lambda t, k: f(plvl("read", "jpa", t), k)
    hi = (75, 100, 150)
    out.append(("p", "MySQL 版查询在 25～50 线程时，数据库节点 CPU 约为 %s；75～150 线程时，数据库节点 CPU 为 %s，应用节点为 %s。"
                     "每请求应用节点 CPU 时间从 %.2f ms 增至 %.2f～%.2f ms，数据库节点保持在 %.2f～%.2f ms。100、150 线程时，连接池等待请求数"
                     "峰值为 %s～%s；75、100 线程的实际连接数曾降至 %s。高并发下，应用端单位请求开销和连接等待增加，与吞吐量下降、尾延迟上升"
                     "同时出现（第二阶段监控数据，CPU 为统计区间平均值）。"
                     % (span([pr(t, "CDWY2_cpu_pct") for t in (25, 50)]), span([pr(t, "CDWY2_cpu_pct") for t in hi]),
                        span([pr(t, "CDWY1_cpu_pct") for t in hi]),
                        pr(25, "app_host_cpu_ms_per_req"), min(pr(t, "app_host_cpu_ms_per_req") for t in hi),
                        max(pr(t, "app_host_cpu_ms_per_req") for t in hi),
                        min(pr(t, "db_host_cpu_ms_per_req") for t in hi), max(pr(t, "db_host_cpu_ms_per_req") for t in hi),
                        n(min(pr(t, "pool_waiting_max") for t in (100, 150))), n(max(pr(t, "pool_waiting_max") for t in (100, 150))),
                        n(pr(75, "pool_size_min")))))
    out.append(("p", "写入方面，MySQL 版在 100 线程达到 %s 次/秒，75 线程为 %s 次/秒，两档吞吐接近，P95 分别为 %.0f ms 和 %.0f ms；150 线程时"
                     "吞吐降至 %s 次/秒，P95 升至 %.0f ms。MongoDB 版在 25～100 线程为 %s～%s 次/秒，150 线程达到本组最高值 %s 次/秒，但 P95 "
                     "从 25 线程的 %.0f ms 升至 %.0f ms。MongoDB 的最高吞吐档位高于 MySQL；若优先降低响应时间，较低线程数更有利。"
                     % (n(g("write", "jpa", 100)), n(g("write", "jpa", 75)), g("write", "jpa", 100, "steady_p95_ms"),
                        g("write", "jpa", 75, "steady_p95_ms"), n(g("write", "jpa", 150)), g("write", "jpa", 150, "steady_p95_ms"),
                        n(min(g("write", "mongo", t) for t in (25, 50, 75, 100))), n(max(g("write", "mongo", t) for t in (25, 50, 75, 100))),
                        n(g("write", "mongo", 150)), g("write", "mongo", 25, "steady_p95_ms"), g("write", "mongo", 150, "steady_p95_ms"))))
    wt = choice.get("write", 100)
    best_w = {i: max(g("write", i, t) for t in SWEEP) for i in ("jpa", "mongo")}
    out.append(("p", "连接池测试需要为两种实现采用相同并发量。选择规则是：先保留两者吞吐量均达到各自观测高值 95%% 的档位，再选择两者 P95 平均值"
                     "最低的一档。查询选为 %d 线程；写入 %d 线程时，MySQL、MongoDB 分别达到各自高值的 %.0f%% 和约 %.1f%%，选为共同测试档位。"
                     % (choice.get("read", 25), wt, pct(g("write", "jpa", wt), best_w["jpa"]), pct(g("write", "mongo", wt), best_w["mongo"]))))
    return out


def pool_section(PJ, PP, lvl, choice):
    out = []
    rt, wt = choice.get("read", 50), choice.get("write", 100)

    def tp(op, impl, size, k="steady_throughput"):
        t = rt if op == "read" else wt
        r = PJ.get((op, "pool%d" % size, t, impl)) if size != 100 else lvl(op, impl, t)
        return f(r, k)

    rows = []
    for size in POOLS:
        row = [size]
        for op in ("read", "write"):
            for impl in ("jpa", "mongo"):
                row.append("%s / %.0f" % (n(tp(op, impl, size)), tp(op, impl, size, "steady_p95_ms")))
        rows.append(row)
    out.append(("table", "表10  连接池调优（吞吐 次/秒 / P95 ms；查询 %d 线程、写入 %d 线程；连接池 100 取并发量调优的同档结果）" % (rt, wt),
                ["连接池上限", "查询 MySQL", "查询 MongoDB", "写入 MySQL", "写入 MongoDB"], rows, [2.3, 3.3, 3.3, 3.3, 3.3]))
    pp = lambda op, impl, size, k: f(PP[(op, "pool%d" % size, rt if op == "read" else wt, impl)], k)
    out.append(("p", "查询固定 %d 线程时，连接池 25、50、100 对应的 MySQL 吞吐量为 %s、%s、%s 次/秒，P95 为 %.0f、%.0f、%.0f ms，三档表现接近。"
                     "MongoDB 对应吞吐量为 %s、%s、%s 次/秒，P95 为 %.0f、%.0f、%.0f ms；连接池 50 已达到 100 的约 %.0f%% 吞吐量。连接池 25 时，"
                     "MongoDB 最多借出 %s 个连接，等待请求峰值为 %s，吞吐下降没有伴随大量连接等待。"
                     % (rt, n(tp("read", "jpa", 25)), n(tp("read", "jpa", 50)), n(tp("read", "jpa", 100)),
                        tp("read", "jpa", 25, "steady_p95_ms"), tp("read", "jpa", 50, "steady_p95_ms"), tp("read", "jpa", 100, "steady_p95_ms"),
                        n(tp("read", "mongo", 25)), n(tp("read", "mongo", 50)), n(tp("read", "mongo", 100)),
                        tp("read", "mongo", 25, "steady_p95_ms"), tp("read", "mongo", 50, "steady_p95_ms"),
                        tp("read", "mongo", 100, "steady_p95_ms"), pct(tp("read", "mongo", 50), tp("read", "mongo", 100)),
                        n(pp("read", "mongo", 25, "pool_in_use_max")), n(pp("read", "mongo", 25, "pool_waiting_max")))))
    out.append(("p", "写入固定 %d 线程时，MySQL 连接池从 25 增至 50，吞吐量由 %s 升至 %s 次/秒，P95 从 %.0f 降至 %.0f ms；连接池 100 为 %s 次/秒，"
                     "P95 为 %.0f ms。MongoDB 三档吞吐量为 %s、%s、%s 次/秒，P95 为 %.0f、%.0f、%.0f ms。连接池 50 在这组单次测试中取得两种实现"
                     "各自最高写入吞吐量；连接池 100 的写入 P95 更低。连接池大小的选择因此应结合吞吐量与尾延迟目标。"
                     % (wt, n(tp("write", "jpa", 25)), n(tp("write", "jpa", 50)), tp("write", "jpa", 25, "steady_p95_ms"),
                        tp("write", "jpa", 50, "steady_p95_ms"), n(tp("write", "jpa", 100)), tp("write", "jpa", 100, "steady_p95_ms"),
                        n(tp("write", "mongo", 25)), n(tp("write", "mongo", 50)), n(tp("write", "mongo", 100)),
                        tp("write", "mongo", 25, "steady_p95_ms"), tp("write", "mongo", 50, "steady_p95_ms"),
                        tp("write", "mongo", 100, "steady_p95_ms"))))
    return out


def overload_section(OJ, OP, R1):
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
    out.append(("table", "表11  过载与恢复（过载统计第 60～240 秒；恢复为随后 10 线程检查的满线程时段；括号为相对第一阶段 10 线程吞吐量）",
                ["操作", "实现", "线程", "吞吐(次/秒)", "平均(ms)", "P95(ms)", "P99(ms)", "错误率", "恢复检查吞吐"], rows,
                [1.1, 1.7, 1.2, 1.9, 1.6, 1.6, 1.6, 1.6, 3.2]))
    o = lambda op, impl, t, k: f(OJ[(op, "overload", t, impl)], k)
    op_ = lambda op, impl, t, k: f(OP[(op, "overload", t, impl)], k)
    gen_cpu = [f(r, "CDWY4_cpu_pct") for k, r in OP.items() if k[1] == "overload"]
    gen_mem = [f(r, "CDWY4_mem_avail_min_mb") for k, r in OP.items() if k[1] == "overload" and r["CDWY4_mem_avail_min_mb"]]
    rec = [pct(f(OJ[(op, "recovery%d" % t, 10, i)], "steady_throughput"), f(R1[(op, "load", 10, i)], "steady_throughput"))
           for op in ("read", "write") for i in ("jpa", "mongo") for t in OVER if (op, "recovery%d" % t, 10, i) in OJ]
    rec_avg = [f(OJ[(op, "recovery%d" % t, 10, i)], "steady_avg_ms")
               for op in ("read", "write") for i in ("jpa", "mongo") for t in OVER if (op, "recovery%d" % t, 10, i) in OJ]
    errs = sum(int(r["full_errors"]) for k, r in OJ.items() if k[1] == "overload")
    nov = sum(1 for k in OJ if k[1] == "overload")
    out.append(("p", "600～1000 线程时，%d 次有效过载测试的错误率均为 %s。吞吐量没有随线程数成比例增长，响应时间明显增加。MongoDB 写入从 600 线程的 "
                     "%s 次/秒降至 1000 线程的 %s 次/秒，平均响应时间从 %.0f ms 增至 %.0f ms，P95 从 %.0f ms 增至 %.0f ms；MongoDB 查询同期由 "
                     "%s 降至 %s 次/秒，平均响应时间从 %.0f ms 增至 %.0f ms。MySQL 写入保持在 %s～%s 次/秒，平均响应时间从 %.0f ms 升至 %.0f ms。"
                     "此时 Tomcat 最多 200 个工作线程，连接池最多 100 个连接，增加客户端并发主要延长了请求等待时间。"
                     % (nov, "0" if errs == 0 else "不全为 0",
                        n(o("write", "mongo", 600, "steady_throughput")), n(o("write", "mongo", 1000, "steady_throughput")),
                        o("write", "mongo", 600, "steady_avg_ms"), o("write", "mongo", 1000, "steady_avg_ms"),
                        o("write", "mongo", 600, "steady_p95_ms"), o("write", "mongo", 1000, "steady_p95_ms"),
                        n(o("read", "mongo", 600, "steady_throughput")), n(o("read", "mongo", 1000, "steady_throughput")),
                        o("read", "mongo", 600, "steady_avg_ms"), o("read", "mongo", 1000, "steady_avg_ms"),
                        n(min(o("write", "jpa", t, "steady_throughput") for t in OVER)), n(max(o("write", "jpa", t, "steady_throughput") for t in OVER)),
                        o("write", "jpa", 600, "steady_avg_ms"), o("write", "jpa", 1000, "steady_avg_ms"))))
    out.append(("p", "有效过载测试中，压测节点 CPU 为 %.0f%%～%.0f%%，可用内存至少约 %s MB；服务端吞吐量与客户端结果相符。MySQL 800 线程查询的首次运行中，"
                     "压测节点 CPU 满载且线程启动延迟，吞吐量仅 839 次/秒，该记录及其恢复检查另存于 overload/invalid，表 11 采用重测结果。"
                     "恢复检查平均响应时间为 %.1f～%.1f ms，吞吐量为第一阶段同线程结果的 %.0f%%～%.0f%%；第一阶段使用 CDWY3 发压，过载与恢复使用 CDWY4。"
                     "撤压后的这次检查中，两种服务均继续成功处理请求。"
                     % (min(gen_cpu), max(gen_cpu), n(min(gen_mem)), min(rec_avg), max(rec_avg), min(rec), max(rec))))
    out.append(("p", "MySQL 查询在 600、1000 线程分别为 %s、%s 次/秒，数据库节点 CPU 为 %.0f%%、%.0f%%；800 线程重测为 %s 次/秒，应用节点 CPU 为 "
                     "%.0f%%，每请求应用节点 CPU 时间由 600 线程的 %.2f ms 增至 %.2f ms。三档未形成单调曲线，与并发量测试中观察到的两种资源饱和"
                     "状态一致。600、1000 线程时库中保留前次写入数据，800 线程重测时为预置数据；600 线程时实际连接数还曾降至 %s。这些记录表明，"
                     "查询吞吐量同时随应用开销、连接池运行状态和数据库状态变化，线程数本身不足以解释各档差异。"
                     % (n(o("read", "jpa", 600, "steady_throughput")), n(o("read", "jpa", 1000, "steady_throughput")),
                        op_("read", "jpa", 600, "CDWY2_cpu_pct"), op_("read", "jpa", 1000, "CDWY2_cpu_pct"),
                        n(o("read", "jpa", 800, "steady_throughput")), op_("read", "jpa", 800, "CDWY1_cpu_pct"),
                        op_("read", "jpa", 600, "app_host_cpu_ms_per_req"), op_("read", "jpa", 800, "app_host_cpu_ms_per_req"),
                        n(op_("read", "jpa", 600, "pool_size_min")))))
    return out


def probe_section(PR, QJ, QP, XJ, XP, NMAX):
    out = []
    status = {(r["op"], r["impl"], int(r["t"])): r.get("pass") == "1" for r in PR}
    rows = []
    for op in ("read", "write"):
        for impl in ("jpa", "mongo"):
            for r in [x for x in PR if x["op"] == op and x["impl"] == impl]:
                has = r.get("window_s", "0") != "0"   # 未通过的级别没有“全部线程同时运行”的时段
                rows.append([OP_CN[op], IMPL_CN[impl], r["t"], r.get("max_threads", "—"), n(r["tps"]) if has else "—",
                             r["avg_ms"] if has else "—", r.get("errors", "—"), r["gap_ms"] if has else "—",
                             "通过" if status[(op, impl, int(r["t"]))] else "不通过"])
    out.append(("table", "表12  最多同时运行线程数逐级加压（吞吐与平均响应取全部线程同时运行的时段，未通过的级别没有这一时段；"
                         "压测机自检 = 线程数 ÷ 吞吐量 − 平均响应时间）",
                ["操作", "实现", "设定线程", "同时运行", "吞吐(次/秒)", "平均(ms)", "错误数", "自检(ms)", "结果"], rows,
                [1.1, 1.8, 1.6, 1.6, 2.0, 1.6, 1.4, 1.6, 1.4]))
    q = lambda op, impl, t, k: f(QJ[(op, "probe", t, impl)], k)
    best = {}
    for (op, impl, t), ok in status.items():
        if ok:
            best[(op, impl)] = max(best.get((op, impl), 0), t)

    # 写入：各级都通过时的饱和表现
    wt = {i: sorted(t for (op, im, t), ok in status.items() if op == "write" and im == i and ok) for i in ("jpa", "mongo")}
    wtps = {i: [q("write", i, t, "steady_throughput") for t in wt[i]] for i in ("jpa", "mongo")}
    top = max(wt["mongo"])
    out.append(("p", "写入两种实现在 %d～%d 线程各级都通过：MySQL 版吞吐量为 %s～%s 次/秒，MongoDB 版为 %s～%s 次/秒，基本不随线程数变化；"
                     "平均响应时间与线程数成正比增加，约等于“线程数 ÷ 吞吐量”（%d 线程时 MongoDB 版为 %.0f ms，MySQL 版为 %.0f ms）。"
                     "服务已经饱和，多出的线程只是在排队。%d 线程是本组设定的最高一级，写入实际能同时运行的线程数可能更多。"
                     % (min(wt["jpa"]), max(wt["jpa"]), n(min(wtps["jpa"])), n(max(wtps["jpa"])), n(min(wtps["mongo"])), n(max(wtps["mongo"])),
                        top, q("write", "mongo", top, "steady_avg_ms"), q("write", "jpa", top, "steady_avg_ms"), top)))

    # 查询：未通过的级别，原因在压测机
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

    # MongoDB 查询 400 线程一级吞吐量偏低：与 800 线程一级和持续压测的 400 线程对照
    k400, k800, kx = ("read", "probe", 400, "mongo"), ("read", "probe", 800, "mongo"), ("read", "maxload", 400, "mongo")
    if k400 in QJ and k800 in QJ and kx in XJ and k800 in QP and k400 in QP and kx in XP:
        a, b, c = f(QJ[k400], "steady_throughput"), f(QJ[k800], "steady_throughput"), f(XJ[kx], "steady_throughput")
        if a < 0.8 * min(b, c):
            ma, mb, mc = (f(QP[k400], "app_host_cpu2s_ms_per_req"), f(QP[k800], "app_host_cpu2s_ms_per_req"),
                          f(XP[kx], "app_host_cpu2s_ms_per_req"))
            out.append(("p", "MongoDB 查询 400 线程这一级的吞吐量为 %s 次/秒，低于随后 800 线程的 %s 次/秒和 5.9 节同为 400 线程的 %s 次/秒。"
                             "这一级应用服务器 CPU 已达 %.0f%%，每请求应用端 CPU 时间为 %.2f ms，是后两者的 %.1f～%.1f 倍。它距 j:true 测试后"
                             "重启 MongoDB 日志服务约 11 分钟，测前只预热了 60 秒，推测服务尚未充分预热。逐级加压只判断全部线程能否同时运行，"
                             "这一级通过，不影响线程数的选择；吞吐量的比较以 5.9 节为准。"
                             % (n(a), n(b), n(c), f(QP[k400], "CDWY1_cpu2s_avg"), ma, ma / max(mb, mc), ma / min(mb, mc))))
    out.append(("p", "按 4.2 节的规则，查询取两种实现都通过的最高一级 %d 线程、写入取 %d 线程进行持续压测（各实现通过的最高一级：%s）。"
                     % (NMAX.get("read", 0), NMAX.get("write", 0),
                        "，".join("%s %s %d" % (IMPL_CN[i], OP_CN[op], best.get((op, i), 0)) for op in ("read", "write") for i in ("jpa", "mongo")))))
    return out


def maxload_section(XJ, XP, NJ, NP, NMAX, R1):
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
    out.append(("table", "表13  最多线程数下持续压测（统计第 60～240 秒%s；CPU 为 2 秒平均在统计区间内的均值；恢复检查为随后 10 线程 60 秒的"
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
    out.append(("p", "在查询 %d、写入 %d 线程下持续压测 240 秒，%s；压测机 CPU 为 %s，压测机自检不超过 %.2f ms，发压端没有成为瓶颈。与同阶段"
                     "正式对比复测（查询 50、写入 100 线程）相比，查询吞吐量 MySQL 版为 %s 次/秒（正式对比 %s），MongoDB 版为 %s 次/秒（%s）；"
                     "写入 MySQL 版 %s（%s）、MongoDB 版 %s（%s）。吞吐量没有因线程增多而提高，平均响应时间升至 %.0f～%.0f ms，为正式对比的 "
                     "%.0f～%.0f 倍：超出 Tomcat 200 个工作线程和 100 个数据库连接的请求都在排队。MongoDB 版仍保持较高吞吐量，查询为 MySQL 版的 "
                     "%.2f 倍，写入为 %.2f 倍。"
                     % (NMAX["read"], NMAX["write"], "全部请求成功" if errs == 0 else "出现 %s 个错误" % n(errs), span(gen), gap,
                        n(x("read", "jpa", "steady_throughput")), n(nm("read", "jpa")),
                        n(x("read", "mongo", "steady_throughput")), n(nm("read", "mongo")),
                        n(x("write", "jpa", "steady_throughput")), n(nm("write", "jpa")),
                        n(x("write", "mongo", "steady_throughput")), n(nm("write", "mongo")),
                        min(x(op, i, "steady_avg_ms") for op, i in imps), max(x(op, i, "steady_avg_ms") for op, i in imps), min(xr), max(xr),
                        x("read", "mongo", "steady_throughput") / x("read", "jpa", "steady_throughput"),
                        x("write", "mongo", "steady_throughput") / x("write", "jpa", "steady_throughput"))))
    hot = [xp("read", "jpa", "CDWY1_cpu2s_avg"), xp("read", "mongo", "CDWY1_cpu2s_avg"), xp("write", "mongo", "CDWY1_cpu2s_avg")]
    out.append(("p", "图 6 为 2 秒平均的 CPU 使用率曲线。四组测试中负载最高的都是应用服务器 CDWY1：MySQL 查询、MongoDB 查询和 MongoDB 写入时"
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
    rec_rel = [pct(f(XJ[(op, "recovery", 10, i)], "steady_throughput"), f(R1[(op, "load", 10, i)], "steady_throughput")) for op, i in recs]
    out.append(("p", "撤压后 10 线程恢复检查的平均响应时间为 %.1f～%.1f ms，吞吐量为第一阶段 10 线程结果的 %.0f%%～%.0f%%，%s，两种服务都"
                     "立即恢复。"
                     % (min(rec_avg), max(rec_avg), min(rec_rel), max(rec_rel), "全部请求成功" if rec_err == 0 else "出现 %s 个错误" % n(rec_err))))
    return out


def conclusion_tail(XJ, XP, NJ, NMAX):
    imps = [(op, i) for op in ("read", "write") for i in ("jpa", "mongo")]
    x = lambda op, impl, k: f(XJ[(op, "maxload", NMAX[op], impl)], k)
    nm = lambda op, impl, k: f(NJ[(op, "main", MAIN_T[op], impl)], k)
    xr = [x(op, i, "steady_avg_ms") / nm(op, i, "steady_avg_ms") for op, i in imps]
    return [
        ("p", "（5）600～1000 线程的有效测试中，系统均成功完成请求，但增加线程未提高吞吐量，主要表现为响应时间上升，MongoDB 在 1000 线程时还出现"
              "吞吐下降。撤压后的低并发检查中，响应时间降至几毫秒。现有数据中的高效运行区间远早于最高线程数，评价性能应同时观察吞吐量、"
              "尾延迟和资源饱和位置。"),
        ("p", "（6）按课程更新后的 Prometheus 配置（每 1 秒采集，CPU 使用率取 2 秒平均）复测，主对比的吞吐量、延迟和瓶颈位置与此前一致。"
              "逐级加压时两种实现都能让 %d 个写入线程同时运行且零错误；查询两种实现都通过的最高一级为 %d 线程，更高一级先到达 2 核压测机的"
              "上限。在这一线程数下，吞吐量停留在饱和水平，平均响应时间升至正式对比的 %.0f～%.0f 倍，应用服务器成为负载最高的一台；"
              "MySQL 查询的饱和点也由数据库转到应用服务器，吞吐量比 50 线程时低 %.0f%%。"
              % (NMAX["write"], NMAX["read"], min(xr), max(xr),
                 100 - pct(x("read", "jpa", "steady_throughput"), nm("read", "jpa", "steady_throughput")))),
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
