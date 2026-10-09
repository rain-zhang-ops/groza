#!/usr/bin/env python3
"""全量建指纹引导：登录 → 打开台账 → 等后台索引稳定（本地建完会自动回推服务端）
→ 校验 GET /api/v1/gx/phashes 总数 → 换一个全新浏览器上下文验证拉取共享库。"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(HERE, "smoke.env", ), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

BASE = os.environ.get("HB_URL", "https://127.0.0.1:5036")
fails = []


def check(name, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def login(page):
    page.goto(BASE + "/", wait_until="load", timeout=30000)
    page.wait_for_selector("input[type=password]", timeout=15000)
    ui = page.query_selector("input[type=email], input[name=username], input[type=text]")
    if ui:
        ui.fill(os.environ["HB_USER"])
    page.fill("input[type=password]", os.environ["HB_PASS"])
    btn = page.query_selector("form button[type=submit]") or page.query_selector("button:has-text('登录')")
    if btn:
        btn.click()
    page.wait_for_timeout(3000)


def local_count(page):
    raw = page.evaluate("() => localStorage.getItem('hb.phash.v2') || '{}'")
    try:
        return len(json.loads(raw).get("h", {}))
    except Exception:
        return 0


def server_total(page):
    out = page.evaluate(
        """async () => {
          const r = await fetch('/api/v1/gx/phashes');
          if (!r.ok) return { err: r.status };
          const d = await r.json();
          return { total: Object.keys(d.h || {}).length, updatedAt: d.updatedAt || '' };
        }"""
    )
    return out


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 393, "height": 852})
        page = ctx.new_page()
        login(page)
        page.goto(BASE + "/ledger", wait_until="load", timeout=30000)
        page.wait_for_timeout(5000)

        # 等本地索引稳定（连续两次计数不变且 >0）
        last, stable = -1, 0
        deadline = time.time() + 300
        while time.time() < deadline and stable < 3:
            n = local_count(page)
            print(f"  本地索引: {n}")
            if n == last and n > 0:
                stable += 1
            else:
                stable = 0
            last = n
            page.wait_for_timeout(5000)
        check("本地全量索引稳定", last > 0 and stable >= 3, f"{last} 张")

        page.wait_for_timeout(4000)  # 等防抖回推
        srv = server_total(page)
        check("服务端指纹库已写入", srv.get("total", 0) >= last * 0.9, f"server={srv}")

        # 全新上下文（模拟另一台设备）：应直接拉到共享库，本地无需重算
        ctx2 = browser.new_context(ignore_https_errors=True, viewport={"width": 393, "height": 852})
        page2 = ctx2.new_page()
        login(page2)
        page2.goto(BASE + "/ledger", wait_until="load", timeout=30000)
        # 拉取在 load 完成后发生；轮询本地 localStorage
        n2 = 0
        deadline = time.time() + 60
        while time.time() < deadline:
            n2 = local_count(page2)
            if n2 >= srv.get("total", 1) * 0.9:
                break
            page2.wait_for_timeout(2000)
        check("新设备直接拉到共享指纹库", n2 >= srv.get("total", 1) * 0.9, f"{n2}/{srv.get('total')}")

        browser.close()
        return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
