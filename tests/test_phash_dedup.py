#!/usr/bin/env python3
"""AI 拍照滤重（pHash）端到端验证：
1. 台账加载后后台建指纹索引（localStorage hb.phash.v1）
2. 取一个已有物品的封面图，走 AI 新增入口再拍一次 → 应出现「疑似已有物品」拦截条
3. 点「并入库存 +1」→ 队列显示并入，物品数量 +1
"""
import base64
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
        ctx = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 393, "height": 852},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
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
            btn = page.query_selector("form button[type=submit]") or page.query_selector("button:has-text('登录')")
            if btn:
                btn.click()
            page.wait_for_timeout(3000)
        except Exception as e:
            check("登录", False, str(e)[:100])

        # 打开台账（移动卡片视图）
        page.goto(BASE + "/ledger", wait_until="load", timeout=30000)
        page.wait_for_timeout(4000)

        # 1. 等待后台指纹索引建立
        n_hash = 0
        deadline = time.time() + 120
        while time.time() < deadline:
            raw = page.evaluate("() => localStorage.getItem('hb.phash.v1') || '{}'")
            try:
                n_hash = len(json.loads(raw).get("h", {}))
            except Exception:
                n_hash = 0
            if n_hash >= 3:
                break
            page.wait_for_timeout(3000)
        check("指纹索引建立", n_hash >= 3, f"已索引 {n_hash} 张")

        # 2. 取一个已有物品的封面字节
        cand = page.evaluate(
            """async () => {
              const r = await fetch('/api/v1/ledger');
              const d = await r.json();
              const it = (d.items || []).find(x => x.thumb || x.imageId || x.thumbnailId);
              if (!it) return null;
              const aid = it.thumb || it.imageId || it.thumbnailId;
              const ir = await fetch(`/api/v1/entities/${it.id}/attachments/${aid}`);
              const buf = await ir.arrayBuffer();
              let bin = '';
              const bytes = new Uint8Array(buf);
              for (let i = 0; i < bytes.length; i += 8192) bin += String.fromCharCode(...bytes.subarray(i, i + 8192));
              return { id: it.id, name: it.name, qty: it.quantity ?? 0, b64: btoa(bin) };
            }"""
        )
        check("拿到候选物品封面", bool(cand), (cand or {}).get("name", ""))
        if not cand:
            browser.close()
            return 1
        img_path = "/tmp/phash-test.jpg"
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(cand["b64"]))

        # 3. 走 AI 新增入口（直接喂文件到隐藏 input）
        inputs = page.query_selector_all("input[multiple]")
        check("找到 AI 文件入口", len(inputs) >= 1, f"{len(inputs)} 个 multiple input")
        inputs[-1].set_input_files(img_path)

        # 等 AI 识别 + 确认框
        try:
            page.wait_for_selector("text=AI 识别结果确认", timeout=90000)
        except Exception as e:
            page.screenshot(path="/tmp/phash-ai-timeout.png", full_page=True)
            check("AI 确认框出现", False, str(e)[:120])
            browser.close()
            return 1
        page.wait_for_timeout(800)
        page.screenshot(path="/tmp/phash-confirm.png", full_page=True)

        content = page.content()
        check("强命中拦截条（疑似已有物品）", "疑似已有物品" in content)
        check("并入按钮出现", "并入库存 +1" in content)
        check("定位按钮出现", "定位查看" in content)
        check("仍要新增降级", "仍要新增" in content)

        # 4. 点「并入库存 +1」
        btn = page.query_selector("button:has-text('并入库存 +1')")
        if btn:
            btn.click()
            page.wait_for_timeout(4000)
            page.screenshot(path="/tmp/phash-merged.png", full_page=True)
            check("队列显示并入", "并入" in page.content())
            qty_now = page.evaluate(
                """async (id) => {
                  const r = await fetch(`/api/v1/entities/${id}`);
                  const d = await r.json();
                  return d.quantity;
                }""",
                cand["id"],
            )
            check("库存 +1", qty_now == (cand["qty"] or 0) + 1, f"{cand['qty']} → {qty_now}")
        else:
            check("并入按钮可点", False)

        real_errors = [e for e in errors if not any(n in e for n in NOISE)]
        check("无新增控制台错误", not real_errors, "; ".join(real_errors[:3])[:160])
        browser.close()
        return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
