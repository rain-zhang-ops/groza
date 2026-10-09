#!/usr/bin/env python3
"""定向刷新验证：
1. 本页改数量 → 4 秒内不得出现 GET /api/v1/ledger（WS 回声被抑制），列表 DOM 不重建
2. 外部客户端改另一字段 → 页面静默增量刷新（有 GET /api/v1/ledger 但骨架屏不出现、DOM 不重建）
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(HERE, "smoke.env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

BASE = os.environ.get("HB_URL", "https://127.0.0.1:5036")
NOISE = ("Failed to set theme", "SSL certificate", "WebSocket", "beforeinstallprompt", "404")
fails = []


def check(name, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 393, "height": 852}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE + "/", wait_until="load", timeout=30000)
        page.wait_for_selector("input[type=password]", timeout=15000)
        ui = page.query_selector("input[type=email], input[name=username], input[type=text]")
        if ui:
            ui.fill(os.environ["HB_USER"])
        page.fill("input[type=password]", os.environ["HB_PASS"])
        (page.query_selector("form button[type=submit]") or page.query_selector("button:has-text('登录')")).click()
        page.wait_for_timeout(3000)
        page.goto(BASE + "/ledger", wait_until="load", timeout=30000)
        page.wait_for_timeout(5000)

        # 基线：监听整表聚合请求；记录首屏 DOM 元素引用
        ledger_gets = []
        page.on("request", lambda r: ledger_gets.append(r.url) if r.method == "GET" and "/api/v1/ledger" in r.url else None)
        page.evaluate("() => { const el = document.querySelector('input[inputmode=numeric]'); window.__anchor = el ? el.closest('div') : null; }")
        qty0 = page.evaluate("() => { const el = document.querySelector('input[inputmode=numeric]'); return el ? Number(el.value) : null; }")
        check("找到数量输入框", qty0 is not None, f"qty={qty0}")

        # 1. 本页点 + 步进器
        page.evaluate("() => { const el = document.querySelector('input[inputmode=numeric]'); const btns = el.parentElement.querySelectorAll('button'); btns[btns.length - 1].click(); }")
        page.wait_for_timeout(4500)  # 超过旧逻辑 1.5s 的刷新窗口
        qty1 = page.evaluate("() => Number(document.querySelector('input[inputmode=numeric]').value)")
        check("本页改数量生效", qty1 == (qty0 or 0) + 1, f"{qty0} → {qty1}")
        check("本页编辑未触发整表刷新", len(ledger_gets) == 0, f"GET /ledger x{len(ledger_gets)}")
        alive = page.evaluate("() => window.__anchor ? document.contains(window.__anchor) : false")
        check("列表 DOM 未重建", alive)
        page.wait_for_timeout(3000)  # 越过 6s 本地编辑抑制窗口，再模拟外部编辑

        # 2. 外部客户端改同一物品（cookie 共享的 request 上下文）
        target = page.evaluate("""async () => {
          const r = await fetch('/api/v1/ledger');
          const d = await r.json();
          const it = (d.items || [])[0];
          return it ? { id: it.id, qty: it.quantity ?? 0 } : null;
        }""")
        ledger_gets.clear()
        if target:
            resp = ctx.request.patch(f"{BASE}/api/v1/entities/{target['id']}", data={"quantity": target["qty"] + 5})
            check("外部 PATCH 成功", resp.ok, str(resp.status))
            page.wait_for_timeout(3000)  # WS 广播 → 800ms 防抖 → 静默刷新
            check("外部编辑触发静默增量刷新", len(ledger_gets) >= 1, f"GET /ledger x{len(ledger_gets)}")
            alive2 = page.evaluate("() => window.__anchor ? document.contains(window.__anchor) : false")
            check("静默刷新未重建列表 DOM", alive2)
            # 恢复原数量，避免污染数据
            ctx.request.patch(f"{BASE}/api/v1/entities/{target['id']}", data={"quantity": target["qty"]})
            page.wait_for_timeout(1500)

        real_errors = [e for e in errors if not any(n in e for n in NOISE)]
        check("无新增控制台错误", not real_errors, "; ".join(real_errors[:3])[:160])
        browser.close()
        return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
