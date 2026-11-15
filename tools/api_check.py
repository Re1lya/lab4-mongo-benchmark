#!/usr/bin/env python3
"""实验四接口一致性检查：对一个日志服务执行同一组请求，输出每项检查的结果（JSON）。

对两种实现分别运行，再比较两份输出，即可证明“同一套接口、同样的行为”：
  python3 api_check.py --base http://172.31.1.202:8081 --name jpa   --window 2036-01-01T00:00:00Z > check-jpa.json
  python3 api_check.py --base http://172.31.1.202:8082 --name mongo --window 2036-01-01T00:00:00Z > check-mongo.json
  python3 api_check.py --compare check-jpa.json check-mongo.json

检查数据写在 --window 指定的 1 小时窗口内（默认 2036 年），不会混入实验数据集（2026-10）的查询范围。
同一数据库上重复运行时，请换一个窗口，否则上次写入的数据会出现在分页结果里。
只用标准库，兼容 Python 3.6。
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


def iso_ms(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "{:03d}Z".format(dt.microsecond // 1000)


def call(base, method, path, body=None, params=None):
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json;charset=UTF-8"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:200]}


def strip_ids(obj):
    """去掉服务端生成的 id，便于比较两种实现的输出。"""
    if isinstance(obj, dict):
        return {k: strip_ids(v) for k, v in obj.items() if k != "id"}
    if isinstance(obj, list):
        return [strip_ids(v) for v in obj]
    return obj


def run(base, name, window):
    t0 = datetime.strptime(window, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    w_from, w_to = iso_ms(t0), iso_ms(t0 + timedelta(hours=1))
    results = []

    def check(title, method, path, expect_status, expect_errno, body=None, params=None, extra=None, record=True):
        status, resp = call(base, method, path, body, params)
        ok = status == expect_status and resp.get("errno") == expect_errno
        detail = None
        if ok and extra:
            ok, detail = extra(resp)
        shown_body = body
        if isinstance(body, dict) and len(json.dumps(body)) > 300:
            shown_body = dict(body, message="(%d 个字符)" % len(body["message"]))
        item = {"check": title, "request": {"method": method, "path": path, "params": params, "body": shown_body},
                "status": status, "errno": resp.get("errno"), "errmsg": resp.get("errmsg"),
                "pass": ok, "detail": detail,
                "data": strip_ids(resp.get("data")) if method == "GET" else None}
        if record:
            results.append(item)
        return item

    base_log = {"traceId": "a" * 32, "level": "INFO", "source": "api-check", "message": "接口检查 hello",
                "clientIp": "10.0.0.1"}

    # 1 正常写入：带 +08:00 偏移的时间换算为 UTC，并截断到毫秒
    local = (t0 + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S") + ".123456+08:00"
    expected_created = iso_ms(t0 + timedelta(milliseconds=123))

    def created_ok(resp):
        d = resp["data"]
        return len(d["id"]) == 26 and d["createdAt"] == expected_created, \
            {"idLength": len(d["id"]), "sent": local, "createdAt": d["createdAt"]}
    check("写入：合法日志，+08:00 时间换算为 UTC 毫秒", "POST", "/api/logs", 201, 1,
          body=dict(base_log, createdAt=local), extra=created_ok)
    # 2 校验失败返回 400
    check("写入：缺少 level", "POST", "/api/logs", 400, 3, body={k: v for k, v in base_log.items() if k != "level"})
    check("写入：level=FATAL 不在取值范围", "POST", "/api/logs", 400, 3, body=dict(base_log, level="FATAL"))
    check("写入：source 为空", "POST", "/api/logs", 400, 3, body=dict(base_log, source=""))
    check("写入：traceId 超过 64 字符", "POST", "/api/logs", 400, 3, body=dict(base_log, traceId="x" * 65))
    check("写入：clientIp 非法", "POST", "/api/logs", 400, 3, body=dict(base_log, clientIp="300.1.1.1"))
    check("写入：message 4097 个字符", "POST", "/api/logs", 400, 3, body=dict(base_log, message="日" * 4097))
    check("写入：请求体不是 JSON 对象", "POST", "/api/logs", 400, 3, body="not-json")
    # 3 边界值可以写入
    check("写入：message 正好 4096 个字符（emoji）", "POST", "/api/logs", 201, 1,
          body=dict(base_log, message="😀" * 4096, createdAt=iso_ms(t0 + timedelta(seconds=1))))
    check("写入：IPv6 地址（含嵌入 IPv4）", "POST", "/api/logs", 201, 1,
          body=dict(base_log, clientIp="2001:db8::ffff:192.168.1.1", createdAt=iso_ms(t0 + timedelta(seconds=2))))
    # 4 写入 30 条已知数据（WARN/ERROR/INFO 轮流，时间递增），再核对过滤、排序和分页
    prep_ok = True
    for i in range(30):
        created = t0 + timedelta(minutes=10, seconds=i, milliseconds=i)
        item = check("准备查询数据", "POST", "/api/logs", 201, 1, record=False,
                     body=dict(base_log, level=["WARN", "ERROR", "INFO"][i % 3], message="paging-%02d" % i,
                               createdAt=iso_ms(created)))
        prep_ok = prep_ok and item["pass"]
    results.append({"check": "写入：准备 30 条查询数据", "status": 201, "errno": 1, "pass": prep_ok})

    def at(i):
        return iso_ms(t0 + timedelta(minutes=10, seconds=i, milliseconds=i))

    def page_ok(expected):
        def f(resp):
            msgs = [x["message"] for x in resp["data"]["list"]]
            return msgs == expected, {"messages": msgs}
        return f
    warn = ["paging-%02d" % i for i in range(29, -1, -1) if i % 3 == 0]  # 时间倒序
    check("查询：WARN 第1页 size=4（时间倒序）", "GET", "/api/logs", 200, 0,
          params={"level": "WARN", "from": w_from, "to": w_to, "page": 1, "size": 4}, extra=page_ok(warn[0:4]))
    check("查询：WARN 第3页 size=4（最后一页不足4条）", "GET", "/api/logs", 200, 0,
          params={"level": "WARN", "from": w_from, "to": w_to, "page": 3, "size": 4}, extra=page_ok(warn[8:12]))
    check("查询：超出最后一页返回空列表", "GET", "/api/logs", 200, 0,
          params={"level": "WARN", "from": w_from, "to": w_to, "page": 9, "size": 4}, extra=page_ok([]))
    check("查询：时间范围 [from,to) 含 from、不含 to", "GET", "/api/logs", 200, 0,
          params={"level": "ERROR", "from": at(1), "to": at(7), "page": 1, "size": 10},
          extra=page_ok(["paging-04", "paging-01"]))
    check("查询：不指定 level 时查所有级别", "GET", "/api/logs", 200, 0,
          params={"from": at(0), "to": at(3), "page": 1, "size": 10},
          extra=page_ok(["paging-02", "paging-01", "paging-00"]))
    check("查询：level 非法", "GET", "/api/logs", 400, 3, params={"level": "FATAL"})
    check("查询：from 格式错误", "GET", "/api/logs", 400, 3, params={"from": "2036/01/01"})
    check("查询：from 不早于 to", "GET", "/api/logs", 400, 3, params={"from": w_to, "to": w_from})
    check("查询：page=0", "GET", "/api/logs", 400, 3, params={"page": 0})
    check("查询：size=101 超过上限", "GET", "/api/logs", 400, 3, params={"size": 101})
    check("查询：page 不是数字", "GET", "/api/logs", 400, 3, params={"page": "abc"})

    passed = sum(1 for r in results if r["pass"])
    return {"name": name, "base": base, "window": [w_from, w_to], "passed": passed, "total": len(results),
            "results": results}


def compare(a_path, b_path):
    a = json.load(open(a_path, encoding="utf-8"))
    b = json.load(open(b_path, encoding="utf-8"))
    rows = []
    same_all = len(a["results"]) == len(b["results"])
    for x, y in zip(a["results"], b["results"]):
        keys = ("check", "status", "errno", "errmsg", "data", "pass")
        same = all(x.get(k) == y.get(k) for k in keys)
        same_all = same_all and same
        rows.append("| {} | {} | {} | {} | {} |".format(
            x["check"], x.get("status", ""), "通过" if x["pass"] else "失败", "通过" if y["pass"] else "失败",
            "一致" if same else "不一致"))
    print("| 检查项 | HTTP 状态 | {} | {} | 状态码/errno/errmsg/查询结果 |".format(a["name"], b["name"]))
    print("| --- | --- | --- | --- | --- |")
    print("\n".join(rows))
    print("\n{}：{}/{} 通过；{}：{}/{} 通过；两种实现逐项比较：{}".format(
        a["name"], a["passed"], a["total"], b["name"], b["passed"], b["total"], "全部一致" if same_all else "存在差异"))
    return 0 if same_all and a["passed"] == a["total"] and b["passed"] == b["total"] else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", help="服务地址，如 http://172.31.1.202:8081")
    p.add_argument("--name", default="service")
    p.add_argument("--window", default="2036-01-01T00:00:00Z", help="检查数据所在 1 小时窗口的起点（UTC）")
    p.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"))
    args = p.parse_args()
    if args.compare:
        sys.exit(compare(*args.compare))
    if not args.base:
        p.error("--base is required")
    out = run(args.base, args.name, args.window)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out["passed"] == out["total"] else 1)


if __name__ == "__main__":
    main()
