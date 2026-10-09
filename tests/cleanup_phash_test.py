#!/usr/bin/env python3
"""清理 pHash 验证副作用（页面会话内 fetch，复用登录 cookie）：
B5横线活页替芯 数量回 0，删除并入时沉淀的 ai.jpg 附件。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(HERE, "smoke.env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

BASE = "https://127.0.0.1:5036"


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
        btn = page.query_selector("form button[type=submit]") or page.query_selector("button:has-text('登录')")
        if btn:
            btn.click()
        page.wait_for_timeout(3000)

        out = page.evaluate(
            """async () => {
              const j = async (r) => r.ok ? r.json() : { __err: r.status + ' ' + (await r.text()).slice(0, 120) };
              const ledger = await j(await fetch('/api/v1/ledger'));
              if (ledger.__err) return { err: 'ledger: ' + ledger.__err };
              const it = (ledger.items || []).find(x => x.name === 'B5横线活页替芯');
              if (!it) return { err: 'item not found' };
              const ent = await j(await fetch(`/api/v1/entities/${it.id}`));
              if (ent.__err) return { err: 'entity: ' + ent.__err };
              const atts = ent.attachments || [];
              const extra = atts.filter(a => a.name === 'ai.jpg' && !a.primary);
              const removed = [];
              for (const a of extra) {
                const dr = await fetch(`/api/v1/entities/${it.id}/attachments/${a.id}`, { method: 'DELETE' });
                removed.push({ id: a.id.slice(0, 8), ok: dr.ok });
              }
              const pr = await fetch(`/api/v1/entities/${it.id}`, {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ quantity: 0 }),
              });
              return { id: it.id, qtyWas: ent.quantity, atts: atts.map(a => [a.id.slice(0, 8), a.name, !!a.primary]), removed, qtyReset: pr.ok };
            }"""
        )
        print(out)
        browser.close()
        return 0 if out.get("qtyReset") and all(r.get("ok") for r in out.get("removed", [])) else 1


if __name__ == "__main__":
    sys.exit(main())
