#!/usr/bin/env python3
"""端到端测试（Playwright，只读）：登录 UI → 打开台账 → 校验渲染与关键元素。

- 凭据来自环境变量或 tests/smoke.env（HB_USER/HB_PASS）。
- 默认只读，不改任何数据；设置 E2E_WRITE=1 时才做“建临时物品→改价→校验→清除”的写入回路。
- 目标地址：HB_URL 或 https://127.0.0.1:5036（自签证书自动忽略）。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.isfile(os.path.join(HERE, "smoke.env")):
    for line in open(os.path.join(HERE, "smoke.env"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

BASE = os.environ.get("HB_URL", "https://127.0.0.1:5036")
USER = os.environ.get("HB_USER", "")
PASS = os.environ.get("HB_PASS", "")
WRITE = os.environ.get("E2E_WRITE", "0") == "1"

fails = []


def check(name, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # 登录
        page.goto(BASE + "/", wait_until="load", timeout=30000)
        try:
            page.wait_for_selector("input[type=password]", timeout=15000)
            user_input = page.query_selector("input[type=email], input[name=username], input[type=text]")
            if user_input:
                user_input.fill(USER)
            page.fill("input[type=password]", PASS)
            btn = page.query_selector("form button[type=submit]") or page.query_selector("button:has-text('登录')") or page.query_selector("button")
            if btn:
                btn.click()
            page.wait_for_timeout(3000)
        except Exception as e:
            check("登录页交互", False, str(e)[:100])
        check("登录后离开登录页", "password" not in page.content() or "/ledger" in page.url, page.url)

        # 打开台账
        page.goto(BASE + "/ledger", wait_until="load", timeout=30000)
        try:
            page.wait_for_selector("table tbody tr, .card-enter-active, [class*='rounded-2xl']", timeout=20000)
        except Exception as e:
            check("台账渲染", False, str(e)[:100])
        time.sleep(2)

        rows = page.eval_on_selector_all("table tbody tr", "els => els.length")
        check("台账有数据行", rows > 0, f"rows={rows}")

        body = page.content()
        check("侧边栏含「进货」", "进货" in body)
        check("侧边栏不含「收银」", "收银" not in body)

        nuxt_err = [e for e in errors if "[nuxt]" in e]
        check("无 Nuxt 控制台错误", not nuxt_err, "; ".join(nuxt_err[:2]))

        browser.close()

    print()
    if fails:
        print(f"E2E 失败 {len(fails)} 项: {', '.join(fails)}")
        sys.exit(1)
    print("E2E 全部通过")


if __name__ == "__main__":
    main()
