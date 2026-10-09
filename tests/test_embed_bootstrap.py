#!/usr/bin/env python3
"""Embedding 向量库引导：遍历所有有图物品，登记主图向量到服务端共享库。
服务端按图片内容哈希缓存向量，重复运行不产生模型调用费。"""
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
fails = []


def check(name, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()
        page.goto(BASE + "/", wait_until="load", timeout=30000)
        page.wait_for_selector("input[type=password]", timeout=15000)
        ui = page.query_selector("input[type=email], input[name=username], input[type=text]")
        if ui:
            ui.fill(os.environ["HB_USER"])
        page.fill("input[type=password]", os.environ["HB_PASS"])
        (page.query_selector("form button[type=submit]") or page.query_selector("button:has-text('登录')")).click()
        page.wait_for_timeout(3000)

        # 页面会话内逐个登记（浏览器取图字节，POST 给后端算向量）
        out = page.evaluate(
            """async () => {
              const d = await (await fetch('/api/v1/ledger')).json();
              const items = (d.items || []).filter(x => x.thumb || x.imageId || x.thumbnailId);
              let ok = 0, bad = 0;
              const errs = [];
              for (const it of items) {
                const aid = it.thumb || it.imageId || it.thumbnailId;
                try {
                  const blob = await (await fetch(`/api/v1/entities/${it.id}/attachments/${aid}`)).blob();
                  const r = await fetch(`/api/v1/gx/embed-register?item=${it.id}&att=${aid}`, { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: blob });
                  if (r.ok) ok++; else { bad++; if (errs.length < 3) errs.push(it.name + ': ' + r.status); }
                } catch (e) { bad++; if (errs.length < 3) errs.push(it.name + ': ' + e); }
              }
              const st = await (await fetch('/api/v1/gx/embed-status')).json();
              return { items: items.length, ok, bad, errs, status: st };
            }"""
        )
        print(f"有图物品 {out['items']}，登记成功 {out['ok']}，失败 {out['bad']}", out.get("errs") or "")
        check("全量向量登记", out["bad"] == 0 and out["ok"] == out["items"], f"{out['ok']}/{out['items']}")
        check("服务端向量库", out["status"].get("total", 0) >= out["ok"], f"total={out['status'].get('total')} model={out['status'].get('model')}")
        browser.close()
        return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
