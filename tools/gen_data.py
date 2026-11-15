#!/usr/bin/env python3
"""实验四数据生成器（确定性：同一参数在任何机器上生成完全相同的数据）。

两种数据：
  seed    预置日志数据集，同一批记录同时输出为 MySQL 用的 TSV 和 MongoDB 用的 JSONL，
          并打印“内容摘要”（与输出格式无关），用于证明两个数据库装入的是同一批数据。
  jmeter  JMeter 请求数据：write-logs.tsv（写入请求体字段）、read-queries.tsv（查询参数）。

只用标准库，兼容服务器自带的 Python 3.6。随机数只用 random()/getrandbits()，
这两个函数在各 Python 3 版本中输出一致，因此不同机器生成的文件逐字节相同。

示例：
  python3 gen_data.py seed --rows 1000000 --mysql-tsv seed.tsv           # MySQL 服务器上
  python3 gen_data.py seed --rows 1000000 --mongo-jsonl seed.jsonl       # MongoDB 服务器上
  python3 gen_data.py jmeter --out ../jmeter/data
"""
import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# 数据集中各级别占比（模拟真实日志：INFO 最多，ERROR 较少）
LEVEL_WEIGHTS = [("TRACE", 0.05), ("DEBUG", 0.15), ("INFO", 0.60), ("WARN", 0.15), ("ERROR", 0.05)]
# 查询时各级别被查询的概率（排查问题时更常查 ERROR/WARN）
QUERY_LEVEL_WEIGHTS = [("TRACE", 0.10), ("DEBUG", 0.10), ("INFO", 0.25), ("WARN", 0.25), ("ERROR", 0.30)]

SOURCES = [
    "order-service", "payment-service", "product-service", "user-service", "gateway",
    "inventory-service", "shop-service", "freight-service", "coupon-service", "comment-service",
    "auth-service", "search-service", "notify-service", "aftersale-service", "share-service",
    "region-service", "log-agent", "scheduler", "admin-portal", "mobile-bff",
]
ACTIONS = [
    "create order", "pay order", "cancel order", "query product", "update stock", "login",
    "refresh token", "send sms", "calculate freight", "apply coupon", "write comment",
    "refund", "search goods", "sync region", "push message", "export report",
]
WORDS = [
    "request", "response", "user", "order", "product", "cache", "miss", "hit", "retry", "timeout",
    "connection", "pool", "query", "update", "insert", "commit", "rollback", "latency", "ms",
    "status", "ok", "failed", "accepted", "rejected", "token", "session", "shop", "region",
    "price", "amount", "quantity", "stock", "warehouse", "freight", "coupon", "payment", "refund",
    "message", "queue", "consumer", "producer", "offset", "partition", "lock", "acquire", "release",
    "订单", "商品", "库存", "支付", "退款", "用户", "登录", "缓存", "超时", "重试", "成功", "失败",
    "厦门", "福建", "物流", "优惠券", "评论", "店铺", "查询", "更新", "数据库", "连接池",
]

DEFAULT_SEED = 20261115
DEFAULT_START = "2026-10-01T00:00:00Z"
DEFAULT_DAYS = 31


def parse_utc(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def ulid(ms, rand80):
    chars = []
    t = ms
    for _ in range(10):
        chars.append(ULID_ALPHABET[t & 31])
        t >>= 5
    head = "".join(reversed(chars))
    chars = []
    r = rand80
    for _ in range(16):
        chars.append(ULID_ALPHABET[r & 31])
        r >>= 5
    return head + "".join(reversed(chars))


def pick(rng, weighted):
    x = rng.random()
    acc = 0.0
    for value, w in weighted:
        acc += w
        if x < acc:
            return value
    return weighted[-1][0]


def message_length(rng):
    """正文长度（字符数）：70% 短日志、25% 中等、约 5% 长日志，0.1% 正好 4096（上限）。"""
    x = rng.random()
    if x < 0.70:
        return 40 + int(rng.random() * 161)        # 40..200
    if x < 0.95:
        return 200 + int(rng.random() * 801)       # 200..1000
    if x < 0.999:
        return 1000 + int(rng.random() * 3001)     # 1000..4000
    return 4096


def make_message(rng, source):
    target = message_length(rng)
    head = "[{}] {} uid={} order={} cost={}ms".format(
        source, ACTIONS[int(rng.random() * len(ACTIONS))],
        int(rng.random() * 100000), int(rng.random() * 10000000), int(rng.random() * 3000))
    parts = [head]
    length = len(head)
    while length < target:
        w = WORDS[int(rng.random() * len(WORDS))]
        parts.append(w)
        length += len(w) + 1
    return " ".join(parts)[:target]


def make_ip(rng):
    if rng.random() < 0.85:
        return "{}.{}.{}.{}".format(10 + int(rng.random() * 200), int(rng.random() * 256),
                                    int(rng.random() * 256), 1 + int(rng.random() * 254))
    return "2001:db8:{:x}:{:x}::{:x}".format(rng.getrandbits(16), rng.getrandbits(16), 1 + rng.getrandbits(16))


def make_trace_id(rng):
    return "{:032x}".format(rng.getrandbits(128))


def seed_rows(rows, seed, start, days):
    """按时间先后生成日志（时间单调递增，模拟日志按时间到达）。"""
    rng = random.Random(seed)
    start_ms = int(start.timestamp() * 1000)
    span_ms = days * 24 * 3600 * 1000
    step = span_ms / rows
    for i in range(rows):
        ms = start_ms + int(i * step + rng.random() * step)
        source = SOURCES[int(rng.random() * len(SOURCES))]
        level = pick(rng, LEVEL_WEIGHTS)
        trace_id = make_trace_id(rng) if rng.random() < 0.9 else None
        client_ip = make_ip(rng)
        message = make_message(rng, source)
        log_id = ulid(ms, rng.getrandbits(80))
        yield log_id, trace_id, level, source, message, client_ip, ms


def ms_to_mysql(ms):
    dt = datetime.fromtimestamp(ms // 1000, tz=timezone.utc).replace(microsecond=(ms % 1000) * 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def ms_to_iso(ms):
    dt = datetime.fromtimestamp(ms // 1000, tz=timezone.utc).replace(microsecond=(ms % 1000) * 1000)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "{:03d}Z".format(ms % 1000)


def cmd_seed(args):
    start = parse_utc(args.start)
    digest = hashlib.sha256()
    tsv = open(args.mysql_tsv, "w", encoding="utf-8", newline="\n") if args.mysql_tsv else None
    jsonl = open(args.mongo_jsonl, "w", encoding="utf-8", newline="\n") if args.mongo_jsonl else None
    level_count = {}
    count = 0
    first_ms = last_ms = None
    for log_id, trace_id, level, source, message, client_ip, ms in seed_rows(args.rows, args.seed, start, args.days):
        # 内容摘要：与输出格式无关，两种数据库的数据集应得到相同结果
        canonical = "\x1f".join([log_id, trace_id or "", level, source, message, client_ip, str(ms)]) + "\n"
        digest.update(canonical.encode("utf-8"))
        if tsv:
            tsv.write("\t".join([log_id, trace_id or "\\N", level, source, message, client_ip, ms_to_mysql(ms)]) + "\n")
        if jsonl:
            doc = {"_id": log_id}
            if trace_id:
                doc["traceId"] = trace_id
            doc.update({"level": level, "source": source, "message": message, "clientIp": client_ip,
                        "createdAt": {"$date": ms_to_iso(ms)}})
            jsonl.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
        level_count[level] = level_count.get(level, 0) + 1
        count += 1
        if first_ms is None:
            first_ms = ms
        last_ms = ms
    for f in (tsv, jsonl):
        if f:
            f.close()
    summary = {
        "rows": count, "seed": args.seed, "start": args.start, "days": args.days,
        "firstCreatedAt": ms_to_iso(first_ms), "lastCreatedAt": ms_to_iso(last_ms),
        "levels": dict(sorted(level_count.items())), "contentSha256": digest.hexdigest(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_jmeter(args):
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed + 1)
    write_path = os.path.join(args.out, "write-logs.tsv")
    with open(write_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("traceId\tlevel\tsource\tmessage\tclientIp\n")
        for _ in range(args.write_rows):
            source = SOURCES[int(rng.random() * len(SOURCES))]
            level = pick(rng, LEVEL_WEIGHTS)
            f.write("\t".join([make_trace_id(rng), level, source, make_message(rng, source), make_ip(rng)]) + "\n")

    rng = random.Random(args.seed + 2)
    start = parse_utc(args.start)
    span_s = args.days * 24 * 3600
    windows = [(3600, 0.40), (6 * 3600, 0.30), (24 * 3600, 0.20), (7 * 24 * 3600, 0.10)]
    read_path = os.path.join(args.out, "read-queries.tsv")
    with open(read_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("level\tfrom\tto\tpage\n")
        for _ in range(args.read_rows):
            level = pick(rng, QUERY_LEVEL_WEIGHTS)
            width = pick(rng, windows)
            begin = int(rng.random() * (span_s - width))
            begin -= begin % 60  # 整分钟，便于阅读
            t0 = start + timedelta(seconds=begin)
            t1 = t0 + timedelta(seconds=width)
            x = rng.random()
            if x < 0.50:
                page = 1
            elif x < 0.85:
                page = 2 + int(rng.random() * 4)    # 2..5
            else:
                page = 6 + int(rng.random() * 45)   # 6..50
            f.write("\t".join([level, t0.strftime("%Y-%m-%dT%H:%M:%SZ"), t1.strftime("%Y-%m-%dT%H:%M:%SZ"), str(page)]) + "\n")
    for p in (write_path, read_path):
        with open(p, "rb") as f:
            print("{}  {}".format(hashlib.sha256(f.read()).hexdigest(), os.path.basename(p)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("seed", help="生成预置日志数据集")
    p.add_argument("--rows", type=int, default=1000000)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--start", default=DEFAULT_START, help="时间窗口起点（UTC）")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS)
    p.add_argument("--mysql-tsv", help="输出 MySQL LOAD DATA 用的 TSV")
    p.add_argument("--mongo-jsonl", help="输出 mongoimport 用的 JSONL")
    p = sub.add_parser("jmeter", help="生成 JMeter 请求数据")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--start", default=DEFAULT_START)
    p.add_argument("--days", type=int, default=DEFAULT_DAYS)
    p.add_argument("--write-rows", type=int, default=10000)
    p.add_argument("--read-rows", type=int, default=10000)
    args = parser.parse_args()
    if args.cmd == "seed":
        cmd_seed(args)
    elif args.cmd == "jmeter":
        cmd_jmeter(args)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
