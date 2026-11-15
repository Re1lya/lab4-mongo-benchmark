#!/usr/bin/env python3
"""计算数据库中日志数据的“内容摘要”，用于证明 MySQL 与 MongoDB 中的数据逐条相同。

两边都按 id 升序导出，逐条转换成同一种规范文本后计算 SHA-256：
  id \x1f traceId \x1f level \x1f source \x1f message \x1f clientIp \x1f createdAt(UTC 毫秒) \n

MySQL（CDWY2，mysql -N -B 的输出，见 deploy/scripts/digest-mysql.sh）：
  ... | python3 db_digest.py --format mysql
MongoDB（CDWY5，mongoexport --jsonFormat canonical 的输出，见 deploy/scripts/digest-mongo.sh）：
  ... | python3 db_digest.py --format mongo
只用标准库，兼容 Python 3.6。
"""
import argparse
import hashlib
import io
import json
import sys


def rows_mysql(stream):
    for line in stream:
        f = line.rstrip("\n").split("\t")
        trace = "" if f[1] == "NULL" else f[1]
        yield f[0], trace, f[2], f[3], f[4], f[5], int(f[6])


def rows_mongo(stream):
    for line in stream:
        d = json.loads(line)
        created = d["createdAt"]["$date"]
        ms = int(created["$numberLong"]) if isinstance(created, dict) else int(created)
        yield d["_id"], d.get("traceId", ""), d["level"], d["source"], d["message"], d.get("clientIp", ""), ms


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--format", choices=["mysql", "mongo"], required=True)
    args = p.parse_args()
    stream = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    digest = hashlib.sha256()
    count = 0
    levels = {}
    first = last = None
    reader = rows_mysql if args.format == "mysql" else rows_mongo
    for log_id, trace, level, source, message, ip, ms in reader(stream):
        digest.update(("\x1f".join([log_id, trace, level, source, message, ip, str(ms)]) + "\n").encode("utf-8"))
        count += 1
        levels[level] = levels.get(level, 0) + 1
        first = ms if first is None else min(first, ms)
        last = ms if last is None else max(last, ms)
    print(json.dumps({"format": args.format, "rows": count, "levels": dict(sorted(levels.items())),
                      "minCreatedAtMs": first, "maxCreatedAtMs": last, "sortedByIdSha256": digest.hexdigest()},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
