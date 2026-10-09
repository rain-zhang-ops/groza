#!/usr/bin/env python3
"""真实场景回归：把「鼠标」主图裁掉 15% 边缘（模拟重拍取景差异）后走 AI 新增，
embedding 向量应命中拦截条（阈值标定：裁 15% 余弦 0.965，阈值 0.90）。点「拒绝」不留副作用。"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(HERE, "smoke.env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

BASE = os.environ.get("HB_URL", "https://127.0.0.1:5036")
MOUSE_IMG = "/api/v1/entities/774c7b33-9320-4fdd-8b32-8aef1a50c835/attachments/76cb19f2-6232-49ef-8864-d9269ddf21d2"
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
        page.wait_for_timeout(6000)  # 等共享指纹库拉取

        # 页面内裁 15% 生成「重拍」图
        b64 = page.evaluate(
            """async (url) => {
              const bmp = await createImageBitmap(await (await fetch(url)).blob());
              const cv = document.createElement('canvas');
              cv.width = bmp.width; cv.height = bmp.height;
              const ctx = cv.getContext('2d');
              const m = Math.round(bmp.width * 0.075), my = Math.round(bmp.height * 0.075);
              ctx.drawImage(bmp, m, my, bmp.width - 2 * m, bmp.height - 2 * my, 0, 0, cv.width, cv.height);
              const blob = await new Promise(r => cv.toBlob(r, 'image/jpeg', 0.85));
              const buf = new Uint8Array(await blob.arrayBuffer());
              let bin = '';
              for (let i = 0; i < buf.length; i += 8192) bin += String.fromCharCode(...buf.subarray(i, i + 8192));
              return btoa(bin);
            }""",
            MOUSE_IMG,
        )
        with open("/tmp/phash-recrop.jpg", "wb") as f:
            f.write(base64.b64decode(b64))

        inputs = page.query_selector_all("input[multiple]")
        inputs[-1].set_input_files("/tmp/phash-recrop.jpg")
        try:
            page.wait_for_selector("text=AI 识别结果确认", timeout=90000)
        except Exception as e:
            page.screenshot(path="/tmp/phash-recrop-timeout.png", full_page=True)
            check("AI 确认框出现", False, str(e)[:120])
            browser.close()
            return 1
        page.wait_for_timeout(800)
        page.screenshot(path="/tmp/phash-recrop.png", full_page=True)
        content = page.content()
        strong = "疑似已有物品" in content
        weak = "有相似物品" in content
        check("重拍变体触发滤重提示", strong or weak, "强拦截" if strong else ("弱提示" if weak else "漏网"))
        check("指向鼠标", "鼠标" in content)

        btn = page.query_selector("button:has-text('拒绝')")
        if btn:
            btn.click()
            page.wait_for_timeout(800)

        real_errors = [e for e in errors if not any(n in e for n in NOISE)]
        check("无新增控制台错误", not real_errors, "; ".join(real_errors[:3])[:160])
        browser.close()
        return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
