#!/usr/bin/env python3
"""homebox-cn 构建后冒烟测试（SMOKE=0 可跳过）。

凭据优先级：环境变量 > 同目录 smoke.env（KEY=VALUE 每行一条）。
  HB_URL            默认 http://127.0.0.1:5037
  HB_TOKEN          可选：直接给 JWT（不带 Bearer 前缀）
  HB_USER/HB_PASS   可选：用它自动登录取 token

入库测试会创建「冒烟测试」物品并入一笔库，测试后回滚入库单并删除测试物品。
"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENVF = os.path.join(HERE, "smoke.env")
if os.path.isfile(ENVF):
    for line in open(ENVF, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

BASE = os.environ.get("HB_URL", "http://127.0.0.1:5037")
fails = []

def check(name, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)

def req(path, token=None, method="GET", body=None, headers=None):
    r = urllib.request.Request(BASE + path, method=method)
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if headers:
        for k, v in headers.items():
            r.add_header(k, v)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, data, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

st, _ = req("/")
check("服务响应", st in (200, 302, 307), f"HTTP {st}")

token = os.environ.get("HB_TOKEN", "")
if not token and os.environ.get("HB_USER"):
    st, b = req("/api/v1/users/login", method="POST", body={
        "username": os.environ["HB_USER"], "password": os.environ.get("HB_PASS", "")})
    if st == 200:
        token = json.loads(b).get("token", "").replace("Bearer ", "")
    else:
        print(f"  登录 HTTP {st}: {b[:120]!r}")
check("获取 token", bool(token), "" if token else "未配置 HB_TOKEN/HB_USER，鉴权检查跳过")

if token:
    st, b = req("/api/v1/ledger", token)
    items = []
    if st == 200:
        d = json.loads(b)
        items = d.get("items", [])
        check("聚合接口 /ledger", isinstance(items, list),
              f"items={len(items)} locations={len(d.get('locations', []))} tags={len(d.get('tags', []))}")
    else:
        check("聚合接口 /ledger", False, f"HTTP {st}")

    st, b = req("/api/v1/trash2", token)
    check("回收站 /trash2", st == 200 and b"entries" in b, f"HTTP {st}")

    st, b = req("/api/v1/ui-options", token)
    check("选项接口 /ui-options", st == 200, f"HTTP {st}")

    if items:
        it = items[0]
        st, _ = req(f"/api/v1/ledger/{it['id']}", token, "PATCH",
                    {"fields": {"尺寸": "A5"}, "updatedAt": it.get("updatedAt")})
        check("字段PATCH /ledger/{id}", st in (200, 409), f"HTTP {st}")
        st, _ = req(f"/api/v1/ledger/{it['id']}", token, "PATCH",
                    {"fields": {"尺寸": "A4"}, "updatedAt": "2000-01-01T00:00:00Z"})
        check("乐观锁应 409", st == 409, f"HTTP {st}")
    else:
        check("字段PATCH（无数据跳过）", True)

    # ---------- 进销存 ----------
    tree_status, tree_b = req("/api/v1/entities/tree", token)
    loc_id = None
    if tree_status == 200:
        try:
            loc_id = json.loads(tree_b)[0]["id"]
        except Exception:
            pass
    eid = None
    if loc_id:
        st, b = req("/api/v1/entities", token, "POST",
                    {"name": "冒烟测试物品", "parentId": loc_id, "quantity": 5})
        if st in (200, 201):
            eid = json.loads(b).get("id")
    check("创建测试物品", bool(eid), "" if eid else "跳过进销存业务测试")

    if eid:
        ikey = "smoke-" + eid
        ibody = {"supplier": "冒烟供应商", "note": "冒烟测试-入库",
                 "items": [{"entityId": eid, "count": 3, "cost": 5}]}
        st, b = req("/api/v1/biz/intake", token, "POST", ibody, headers={"Idempotency-Key": ikey})
        intake_id = json.loads(b).get("intake", {}).get("id") if st == 200 else None
        check("入库 /biz/intake", st == 200 and bool(intake_id), f"HTTP {st}")

        st, b = req("/api/v1/biz/intake", token, "POST", ibody, headers={"Idempotency-Key": ikey})
        replayed = st == 200 and json.loads(b).get("intake", {}).get("id") == intake_id
        check("幂等重放 /biz/intake", replayed, f"HTTP {st}")

        st, b = req("/api/v1/biz/intakes", token)
        ok = st == 200 and any(it.get("id") == intake_id for it in json.loads(b))
        check("入库单列表 /biz/intakes", ok, f"HTTP {st}")

        st, b = req("/api/v1/biz/intake/rollback", token, "POST", {"intakeId": intake_id})
        check("入库回滚", st == 200 and json.loads(b).get("intake", {}).get("rolledBack"), f"HTTP {st}")

        # 出库（纯库存：扣减/回滚/超量拒绝）
        st, b = req("/api/v1/biz/outbound", token, "POST",
                    {"reason": "冒烟测试", "items": [{"entityId": eid, "count": 2}]})
        ob_id = json.loads(b).get("outbound", {}).get("id") if st == 200 else None
        check("出库 /biz/outbound", st == 200 and bool(ob_id), f"HTTP {st}")

        st, b = req("/api/v1/biz/outbounds", token)
        ok = st == 200 and any(o.get("id") == ob_id for o in json.loads(b))
        check("出库单列表 /biz/outbounds", ok, f"HTTP {st}")

        st, _ = req("/api/v1/biz/outbound", token, "POST",
                    {"reason": "超量", "items": [{"entityId": eid, "count": 9999}]})
        check("超量出库应被拒", st == 400, f"HTTP {st}")

        st, b = req("/api/v1/biz/outbound/rollback", token, "POST", {"outboundId": ob_id})
        check("出库回滚", st == 200 and json.loads(b).get("outbound", {}).get("rolledBack"), f"HTTP {st}")

        # 标记删除 -> 回收站清除（覆盖 trash2 + purge + 审计）
        st, _ = req("/api/v1/trash2", token, "PUT", {"ids": [eid]})
        check("标记删除 /trash2", st == 200, f"HTTP {st}")

        st, b = req("/api/v1/trash2/purge", token, "POST", {"confirm": True, "ids": [eid]})
        ok = st == 200 and eid in json.loads(b).get("purged", [])
        check("回收站清除 /trash2/purge", ok, f"HTTP {st}")

        st, b = req("/api/v1/audit?limit=50", token)
        try:
            arr = json.loads(b)
        except Exception:
            arr = None
        check("审计日志 /audit", st == 200 and isinstance(arr, list), f"HTTP {st}")

        st, b = req("/api/v1/metrics", token)
        try:
            met = json.loads(b)
        except Exception:
            met = {}
        check("指标 /metrics", st == 200 and "items" in met, f"HTTP {st}")

print()
if fails:
    print(f"冒烟测试失败 {len(fails)} 项: {', '.join(fails)}")
    sys.exit(1)
print("冒烟测试全部通过")
