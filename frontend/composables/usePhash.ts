// 图片感知哈希（pHash 64bit）：AI 新增滤重专用。
// 原理：32×32 灰度 → DCT → 取低频 8×8 与中位数比较 → 64 位指纹（16 个 hex 字符）。
// 全部在浏览器 canvas 内完成，保证同一图片的指纹唯一来源、结果一致。

const PH_SIZE = 32;
const PH_LOW = 8;

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

async function phLoadSource(src: Blob | string): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof src !== "string") return await createImageBitmap(src);
  return await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("image load failed"));
    img.src = src;
  });
}

// 计算 64 位感知哈希，返回 16 个 hex 字符；失败抛错（调用方自行兜底）
export async function computePhash(src: Blob | string): Promise<string> {
  const img = await phLoadSource(src);
  const cv = document.createElement("canvas");
  cv.width = PH_SIZE;
  cv.height = PH_SIZE;
  const ctx = cv.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("no canvas 2d");
  ctx.drawImage(img, 0, 0, PH_SIZE, PH_SIZE);
  if (img instanceof ImageBitmap) img.close();
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

const PH_POP = [0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4];

// 两个 hex 指纹的汉明距离（0~64，越小越像）；非法输入返回 65
export function phashHamming(a: string, b: string): number {
  if (!a || !b || a.length !== b.length) return 65;
  let d = 0;
  for (let i = 0; i < a.length; i++) {
    const x = parseInt(a[i], 16) ^ parseInt(b[i], 16);
    if (Number.isNaN(x)) return 65;
    d += PH_POP[x];
  }
  return d;
}
