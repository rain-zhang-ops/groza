#!/usr/bin/env python3
"""pHash 多尺度指纹验证：full + 中心80% + 中心60% 三段指纹，取两两最小距离。
看「鼠标」变体的召回提升，以及「鼠标 vs 鼠标垫」是否保持安全距离（不误报）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(HERE, "smoke.env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

BASE = "https://127.0.0.1:5036"
MOUSE = "/api/v1/entities/774c7b33-9320-4fdd-8b32-8aef1a50c835/attachments/76cb19f2-6232-49ef-8864-d9269ddf21d2"
PAD = "/api/v1/entities/e0c078ee-01ce-44e5-88b3-eef2304f223c/attachments/4e686054-f56f-470c-a1ed-6c238b016ac6"

JS = r"""
async ([mouseUrl, padUrl]) => {
  const PH_SIZE = 32, PH_LOW = 8;
  const cos = [];
  for (let i = 0; i < PH_SIZE; i++) {
    const row = [];
    for (let u = 0; u < PH_LOW; u++) row.push(Math.cos(((2 * i + 1) * u * Math.PI) / (2 * PH_SIZE)));
    cos.push(row);
  }
  async function phashBitmap(bmp, w, h, sx, sy, sw, sh) {
    const cv = document.createElement('canvas');
    cv.width = PH_SIZE; cv.height = PH_SIZE;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(bmp, sx, sy, sw, sh, 0, 0, PH_SIZE, PH_SIZE);
    const px = ctx.getImageData(0, 0, PH_SIZE, PH_SIZE).data;
    const gray = new Float64Array(PH_SIZE * PH_SIZE);
    for (let i = 0; i < gray.length; i++) {
      const o = i * 4;
      gray[i] = 0.299 * px[o] + 0.587 * px[o + 1] + 0.114 * px[o + 2];
    }
    const vals = [];
    for (let u = 0; u < PH_LOW; u++) for (let v = 0; v < PH_LOW; v++) {
      let sum = 0;
      for (let i = 0; i < PH_SIZE; i++) {
        const ci = cos[i][u], base = i * PH_SIZE;
        for (let j = 0; j < PH_SIZE; j++) sum += ci * cos[j][v] * gray[base + j];
      }
      vals.push(sum);
    }
    const rest = vals.slice(1).sort((a, b) => a - b);
    const med = rest[Math.floor(rest.length / 2)];
    let hex = '';
    for (let n = 0; n < 16; n++) {
      let nib = 0;
      for (let b = 0; b < 4; b++) if (vals[n * 4 + b] > med) nib |= 1 << (3 - b);
      hex += nib.toString(16);
    }
    return hex;
  }
  // 三段指纹：full / 中心80% / 中心60%
  async function finger(bmp) {
    const w = bmp.width, h = bmp.height;
    const parts = [];
    parts.push(await phashBitmap(bmp, w, h, 0, 0, w, h));
    for (const s of [0.8, 0.6]) {
      const sw = Math.round(w * s), sh = Math.round(h * s);
      parts.push(await phashBitmap(bmp, w, h, Math.round((w - sw) / 2), Math.round((h - sh) / 2), sw, sh));
    }
    return parts.join('');
  }
  const POP = [0,1,1,2,1,2,2,3,1,2,2,3,2,3,3,4];
  const ham16 = (a, b) => { let d = 0; for (let i = 0; i < 16; i++) d += POP[parseInt(a[i],16) ^ parseInt(b[i],16)]; return d; };
  const fingerDist = (a, b) => {
    let best = 65;
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {
      const d = ham16(a.slice(i * 16, i * 16 + 16), b.slice(j * 16, j * 16 + 16));
      if (d < best) best = d;
    }
    return best;
  };

  const mouse = await createImageBitmap(await (await fetch(mouseUrl)).blob());
  const pad = await createImageBitmap(await (await fetch(padUrl)).blob());
  const fm = await finger(mouse);
  const fp = await finger(pad);

  async function variant(fn) {
    const cv = document.createElement('canvas');
    cv.width = mouse.width; cv.height = mouse.height;
    const ctx = cv.getContext('2d');
    fn(ctx, cv);
    const blob = await new Promise(r => cv.toBlob(r, 'image/jpeg', 0.85));
    return await finger(await createImageBitmap(blob));
  }
  const out = { crossDist: fingerDist(fm, fp), dists: {} };
  out.dists['原图重编码'] = fingerDist(fm, await variant((c) => c.drawImage(mouse, 0, 0)));
  out.dists['裁掉10%边缘'] = fingerDist(fm, await variant((c, cv2) => {
    const m = Math.round(mouse.width * 0.05), my = Math.round(mouse.height * 0.05);
    c.drawImage(mouse, m, my, mouse.width - 2 * m, mouse.height - 2 * my, 0, 0, cv2.width, cv2.height);
  }));
  out.dists['裁掉25%边缘'] = fingerDist(fm, await variant((c, cv2) => {
    const m = Math.round(mouse.width * 0.125), my = Math.round(mouse.height * 0.125);
    c.drawImage(mouse, m, my, mouse.width - 2 * m, mouse.height - 2 * my, 0, 0, cv2.width, cv2.height);
  }));
  out.dists['提亮30%'] = fingerDist(fm, await variant((c) => { c.filter = 'brightness(1.3)'; c.drawImage(mouse, 0, 0); }));
  out.dists['旋转8度'] = fingerDist(fm, await variant((c, cv2) => {
    c.translate(cv2.width / 2, cv2.height / 2); c.rotate(8 * Math.PI / 180);
    c.drawImage(mouse, -mouse.width / 2, -mouse.height / 2);
  }));
  out.dists['旋转20度'] = fingerDist(fm, await variant((c, cv2) => {
    c.translate(cv2.width / 2, cv2.height / 2); c.rotate(20 * Math.PI / 180);
    c.drawImage(mouse, -mouse.width / 2, -mouse.height / 2);
  }));
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
        print(f"误报对照：鼠标 vs 鼠标垫 最小距离 = {out['crossDist']}（应远大于阈值）")
        for k, d in out["dists"].items():
            verdict = "强命中" if d <= 8 else ("弱提示" if d <= 14 else "漏网")
            print(f"  {k:<10} 最小距离 {d:>2}  → {verdict}")
        b.close()


if __name__ == "__main__":
    sys.exit(main())
