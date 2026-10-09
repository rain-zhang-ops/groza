// 图片感知指纹（多尺度 pHash）：AI 新增滤重专用。
// 原理：32×32 灰度 → DCT → 低频 8×8 与中位数比较 → 64 位段。
// 每张图算 3 段：全图 + 中心 80% + 中心 60%（共 48 个 hex 字符），比对时取两两最小距离——
// 重拍时的取景差异（缩放/平移/裁剪）由中心段兜住（实测裁 25% 距离 0、提亮 2、旋转 8° 14）。
// 全部在浏览器 canvas 内完成，保证同一图片的指纹唯一来源、结果一致。

const PH_SIZE = 32;
const PH_LOW = 8;
const PH_SCALES = [1, 0.8, 0.6];

let phCos: number[][] | null = null;
function phCosTable(): number[][] {
  if (phCos) return phCos;
  phCos = [];
  for (let i = 0; i < PH_SIZE; i++) {
    const row: number[] = [];
    for (let u = 0; u < PH_LOW; u++) row.push(Math.cos(((2 * i + 1) * u * Math.PI) / (2 * PH_SIZE)));
    phCos.push(row);
  }
  return phCos;
}

async function phLoadSource(src: Blob | string): Promise<{ img: ImageBitmap | HTMLImageElement; w: number; h: number }> {
  if (typeof src !== "string") {
    const bmp = await createImageBitmap(src);
    return { img: bmp, w: bmp.width, h: bmp.height };
  }
  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const el = new Image();
    el.onload = () => resolve(el);
    el.onerror = () => reject(new Error("image load failed"));
    el.src = src;
  });
  return { img, w: img.naturalWidth, h: img.naturalHeight };
}

function phashRegion(img: ImageBitmap | HTMLImageElement, sx: number, sy: number, sw: number, sh: number): string {
  const cv = document.createElement("canvas");
  cv.width = PH_SIZE;
  cv.height = PH_SIZE;
  const ctx = cv.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("no canvas 2d");
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, PH_SIZE, PH_SIZE);
  const px = ctx.getImageData(0, 0, PH_SIZE, PH_SIZE).data;
  const gray = new Float64Array(PH_SIZE * PH_SIZE);
  for (let i = 0; i < gray.length; i++) {
    const o = i * 4;
    gray[i] = 0.299 * px[o] + 0.587 * px[o + 1] + 0.114 * px[o + 2];
  }
  const cos = phCosTable();
  const vals: number[] = [];
  for (let u = 0; u < PH_LOW; u++) {
    for (let v = 0; v < PH_LOW; v++) {
      let sum = 0;
      for (let i = 0; i < PH_SIZE; i++) {
        const ci = cos[i][u];
        const base = i * PH_SIZE;
        for (let j = 0; j < PH_SIZE; j++) sum += ci * cos[j][v] * gray[base + j];
      }
      vals.push(sum);
    }
  }
  const rest = vals.slice(1).sort((a, b) => a - b);
  const med = rest[Math.floor(rest.length / 2)];
  let hex = "";
  for (let n = 0; n < 16; n++) {
    let nib = 0;
    for (let b = 0; b < 4; b++) if (vals[n * 4 + b] > med) nib |= 1 << (3 - b);
    hex += nib.toString(16);
  }
  return hex;
}

// 计算多尺度指纹（48 hex = 3 段 × 16）；失败抛错（调用方自行兜底）
export async function computePhash(src: Blob | string): Promise<string> {
  const { img, w, h } = await phLoadSource(src);
  try {
    let out = "";
    for (const s of PH_SCALES) {
      const sw = Math.max(1, Math.round(w * s));
      const sh = Math.max(1, Math.round(h * s));
      out += phashRegion(img, Math.round((w - sw) / 2), Math.round((h - sh) / 2), sw, sh);
    }
    return out;
  } finally {
    if (img instanceof ImageBitmap) img.close();
  }
}

const PH_POP = [0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4];

function phHam16(a: string, b: string): number {
  let d = 0;
  for (let i = 0; i < 16; i++) {
    const x = parseInt(a[i], 16) ^ parseInt(b[i], 16);
    if (Number.isNaN(x)) return 65;
    d += PH_POP[x];
  }
  return d;
}

// 两个指纹的距离（0~64，越小越像）：等长多段取两两最小；新旧格式混比只比全图段；非法输入 65
export function phashHamming(a: string, b: string): number {
  if (!a || !b) return 65;
  const sa = Math.floor(a.length / 16);
  const sb = Math.floor(b.length / 16);
  if (!sa || !sb) return 65;
  if (sa !== sb) return phHam16(a.slice(0, 16), b.slice(0, 16));
  let best = 65;
  for (let i = 0; i < sa; i++) {
    for (let j = 0; j < sb; j++) {
      const d = phHam16(a.slice(i * 16, i * 16 + 16), b.slice(j * 16, j * 16 + 16));
      if (d < best) best = d;
    }
  }
  return best;
}
