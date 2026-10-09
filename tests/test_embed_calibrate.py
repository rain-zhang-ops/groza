#!/usr/bin/env python3
"""Embedding 阈值标定：以「鼠标」为基准，测原图/裁剪/旋转/提亮/其他物品的余弦相似度分布。
输出供 EMBED_STRONG / EMBED_WEAK 阈值取值参考。只读，无副作用。"""
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
MOUSE = "/api/v1/entities/774c7b33-9320-4fdd-8b32-8aef1a50c835/attachments/76cb19f2-6232-49ef-8864-d9269ddf21d2"
PAD = "/api/v1/entities/e0c078ee-01ce-44e5-88b3-eef2304f223c/attachments/4e686054-f56f-470c-a1ed-6c238b016ac6"

JS = r"""
async ([mouseUrl, padUrl]) => {
  async function getBmp(url) { return await createImageBitmap(await (await fetch(url)).blob()); }
  async function matchBlob(blob) {
    const r = await fetch('/api/v1/gx/embed-match', { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: blob });
    if (!r.ok) return [{ itemId: 'ERR', score: 0, err: r.status }];
    const d = await r.json();
    return (d.matches || []).slice(0, 3);
  }
  async function variant(bmp, fn) {
    const cv = document.createElement('canvas');
    cv.width = bmp.width; cv.height = bmp.height;
    const ctx = cv.getContext('2d');
    fn(ctx, cv);
    return await new Promise(r => cv.toBlob(r, 'image/jpeg', 0.85));
  }
  const mouse = await getBmp(mouseUrl);
  const pad = await getBmp(padUrl);
  const names = {};
  const ledger = await (await fetch('/api/v1/ledger')).json();
  for (const it of (ledger.items || [])) names[it.id] = it.name;

  const cases = {};
  const origBlob = await new Promise(r => { const cv = document.createElement('canvas'); cv.width = mouse.width; cv.height = mouse.height; cv.getContext('2d').drawImage(mouse, 0, 0); cv.toBlob(r, 'image/jpeg', 0.9); });
  cases['鼠标·原图'] = origBlob;
  cases['鼠标·裁15%'] = await variant(mouse, (c, cv2) => {
    const m = Math.round(mouse.width * 0.075), my = Math.round(mouse.height * 0.075);
    c.drawImage(mouse, m, my, mouse.width - 2 * m, mouse.height - 2 * my, 0, 0, cv2.width, cv2.height);
  });
  cases['鼠标·旋转8度'] = await variant(mouse, (c, cv2) => {
    c.translate(cv2.width / 2, cv2.height / 2); c.rotate(8 * Math.PI / 180);
    c.drawImage(mouse, -mouse.width / 2, -mouse.height / 2);
  });
  cases['鼠标·提亮30%'] = await variant(mouse, (c) => { c.filter = 'brightness(1.3)'; c.drawImage(mouse, 0, 0); });
  cases['鼠标垫·跨物品'] = await new Promise(r => { const cv = document.createElement('canvas'); cv.width = pad.width; cv.height = pad.height; cv.getContext('2d').drawImage(pad, 0, 0); cv.toBlob(r, 'image/jpeg', 0.9); });

  const out = {};
  for (const [k, blob] of Object.entries(cases)) {
    const ms = await matchBlob(blob);
    out[k] = ms.map(m => ({ name: names[m.itemId] || m.itemId, score: m.score }));
  }
  return out;
}
"""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_context(ignore_https_errors=True).new_page()
        page.goto(BASE + "/", wait_until="load", timeout=30000)
        page.wait_for_selector("input[type=password]", timeout=15000)
        ui = page.query_selector("input[type=email], input[name=username], input[type=text]")
        if ui:
            ui.fill(os.environ["HB_USER"])
        page.fill("input[type=password]", os.environ["HB_PASS"])
        (page.query_selector("form button[type=submit]") or page.query_selector("button:has-text('登录')")).click()
        page.wait_for_timeout(3000)
        out = page.evaluate(JS, [MOUSE, PAD])
        for k, ms in out.items():
            top = "; ".join(f"{m['name']}={m['score']}" for m in ms) or "(无匹配)"
            print(f"  {k:<12} → {top}")
        b.close()


if __name__ == "__main__":
    sys.exit(main())
