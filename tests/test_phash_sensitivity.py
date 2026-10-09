#!/usr/bin/env python3
"""pHash 灵敏度实验：以「鼠标」主图为基准，制造不同程度的拍摄变体，看汉明距离分布。
页面内注入与 usePhash.ts 相同的算法（用库存储的已知指纹校验一致性）。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(HERE, "smoke.env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

BASE = "https://127.0.0.1:5036"
KNOWN_HASH = "bc9143dc8e32e78a"  # 鼠标主图在服务端库里的指纹
IMG_URL = "/api/v1/entities/774c7b33-9320-4fdd-8b32-8aef1a50c835/attachments/76cb19f2-6232-49ef-8864-d9269ddf21d2"

JS = r"""
async (imgUrl) => {
  const PH_SIZE = 32, PH_LOW = 8;
  const cos = [];
  for (let i = 0; i < PH_SIZE; i++) {
    const row = [];
    for (let u = 0; u < PH_LOW; u++) row.push(Math.cos(((2 * i + 1) * u * Math.PI) / (2 * PH_SIZE)));
    cos.push(row);
  }
  async function phashOfBitmap(bmp) {
    const cv = document.createElement('canvas');
    cv.width = PH_SIZE; cv.height = PH_SIZE;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0, PH_SIZE, PH_SIZE);
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
  const POP = [0,1,1,2,1,2,2,3,1,2,2,3,2,3,3,4];
  const ham = (a, b) => { let d = 0; for (let i = 0; i < 16; i++) d += POP[parseInt(a[i],16) ^ parseInt(b[i],16)]; return d; };

  const buf = await (await fetch(imgUrl)).blob();
  const orig = await createImageBitmap(buf);
  const baseHash = await phashOfBitmap(orig);

  // 制造变体
  async function variant(fn) {
    const cv = document.createElement('canvas');
    cv.width = orig.width; cv.height = orig.height;
    const ctx = cv.getContext('2d');
    fn(ctx, cv);
    const blob = await new Promise(r => cv.toBlob(r, 'image/jpeg', 0.85));
    return await phashOfBitmap(await createImageBitmap(blob));
  }
  const variants = {};
  variants['原图重编码'] = await variant((c) => c.drawImage(orig, 0, 0));
  variants['裁掉10%边缘'] = await variant((c, cv2) => {
    const m = Math.round(orig.width * 0.05), my = Math.round(orig.height * 0.05);
    c.drawImage(orig, m, my, orig.width - 2 * m, orig.height - 2 * my, 0, 0, cv2.width, cv2.height);
  });
  variants['裁掉25%边缘'] = await variant((c, cv2) => {
    const m = Math.round(orig.width * 0.125), my = Math.round(orig.height * 0.125);
    c.drawImage(orig, m, my, orig.width - 2 * m, orig.height - 2 * my, 0, 0, cv2.width, cv2.height);
  });
  variants['提亮30%'] = await variant((c) => { c.filter = 'brightness(1.3)'; c.drawImage(orig, 0, 0); });
  variants['压暗30%'] = await variant((c) => { c.filter = 'brightness(0.7)'; c.drawImage(orig, 0, 0); });
  variants['旋转8度'] = await variant((c, cv2) => {
    c.translate(cv2.width / 2, cv2.height / 2); c.rotate(8 * Math.PI / 180);
    c.drawImage(orig, -orig.width / 2, -orig.height / 2);
  });
  variants['旋转20度'] = await variant((c, cv2) => {
    c.translate(cv2.width / 2, cv2.height / 2); c.rotate(20 * Math.PI / 180);
    c.drawImage(orig, -orig.width / 2, -orig.height / 2);
  });
  variants['水平翻转'] = await variant((c, cv2) => {
    c.translate(cv2.width, 0); c.scale(-1, 1); c.drawImage(orig, 0, 0);
  });
  return { baseHash, dists: Object.fromEntries(Object.entries(variants).map(([k, h]) => [k, ham(baseHash, h)])) };
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
        out = page.evaluate(JS, IMG_URL)
        print("基准指纹:", out["baseHash"], " 库中:", KNOWN_HASH, " 一致:", out["baseHash"] == KNOWN_HASH)
        for k, d in out["dists"].items():
            verdict = "强命中" if d <= 8 else ("弱提示" if d <= 14 else "漏网")
            print(f"  {k:<10} 距离 {d:>2}  → {verdict}")
        b.close()


if __name__ == "__main__":
    sys.exit(main())
