<script setup lang="ts">
  import { toast } from "@/components/ui/sonner";
  import MdiBarcodeScan from "~icons/mdi/barcode-scan";
  import MdiPlus from "~icons/mdi/plus";
  import MdiMinus from "~icons/mdi/minus";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({
    title: "Groza | 出货出库",
  });

  type Row = {
    id: string;
    name: string;
    brand: string;
    size: string;
    spec: string;
    color: string;
    qty: number;
    assetId?: string;
    serial?: string;
    thumb: string | null;
  };
  type OutboundItem = { entityId: string; name?: string; count: number };
  type Outbound = {
    id: string; ts: string; reason?: string; note?: string;
    items: OutboundItem[]; rolledBack?: boolean;
  };

  const isMobile = useMediaQuery("(max-width: 768px)");
  const tab = ref<"do" | "log">("do");

  const rows = ref<Row[]>([]);
  const outbounds = ref<Outbound[]>([]);
  const q = ref("");
  const hideSoldOut = ref(true);
  const fBrand = ref("");
  const sortMode = ref<"name" | "qtyDesc" | "qtyAsc">("name");
  const loading = ref(true);
  const err = ref("");
  const msg = ref("");
  const reason = ref("售出");
  const note = ref("");
  const items = reactive<Record<string, OutboundItem>>({});
  const saving = ref(false);
  const rollbackBusy = ref("");

  const REASONS = ["售出", "赠送", "自用", "损耗", "调拨", "其他"];

  const btnGhost = "inline-flex items-center gap-1 rounded-lg border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50";
  const btnPrimary = "inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50";
  const inputCls = "rounded-lg border bg-background px-2.5 py-1.5 text-sm outline-none transition focus:ring-2 focus:ring-ring/40";

  function buzz(ms = 15) { try { (navigator as any).vibrate?.(ms); } catch (_e) { /* ignore */ } }
  function fieldOf(e: Record<string, any>, name: string): any {
    for (const f of (e.fields as Array<Record<string, any>>) || []) {
      if (f.name === name) return f.type === "text" ? f.textValue : f.numberValue;
    }
    return "";
  }
  function imgUrl(r: Row): string { return r.thumb ? `/api/v1/entities/${r.id}/attachments/${r.thumb}` : ""; }

  async function load() {
    loading.value = true;
    err.value = "";
    try {
      const [agg, ob] = await Promise.all([
        $fetch<Record<string, any>>("/api/v1/ledger"),
        $fetch<Array<Record<string, any>>>("/api/v1/biz/outbounds").catch(() => []),
      ]);
      rows.value = ((agg.items as Array<Record<string, any>>) || []).map(e => ({
        id: e.id, name: e.name,
        brand: fieldOf(e, "品牌") || e.parent || "",
        size: fieldOf(e, "尺寸") || "", spec: fieldOf(e, "规格") || "", color: fieldOf(e, "颜色") || "",
        qty: e.quantity ?? 0, assetId: e.assetId || "", serial: e.serial || "", thumb: e.thumb || null,
      }));
      outbounds.value = (ob || []) as Outbound[];
    } catch (e) {
      err.value = "加载失败：" + ((e as Error)?.message ?? String(e));
    } finally {
      loading.value = false;
    }
  }
  onMounted(() => {
    load();
    syncOq();
    window.addEventListener("hb:offline-queue", syncOq);
  });
  onBeforeUnmount(() => {
    window.removeEventListener("hb:offline-queue", syncOq);
    closeScan();
  });

  const brandList = computed(() => {
    const s = new Set<string>();
    for (const r of rows.value) if (r.brand) s.add(r.brand);
    return [...s].sort((a, b) => a.localeCompare(b, "zh"));
  });
  const recentOut = computed(() => {
    const seen = new Set<string>(); const out: Row[] = [];
    for (const t of outbounds.value) {
      for (const it of (t.items || [])) {
        if (seen.has(it.entityId)) continue;
        seen.add(it.entityId);
        const r = rows.value.find(x => x.id === it.entityId);
        if (r) out.push(r);
        if (out.length >= 8) return out;
      }
    }
    return out;
  });
  const hiddenSoldOut = computed(() =>
    hideSoldOut.value ? rows.value.filter(r => r.qty <= 0 && (!fBrand.value || r.brand === fBrand.value)).length : 0);
  const matched = computed(() => {
    const kw = q.value.trim().toLowerCase();
    let list = rows.value.filter(r =>
      (!hideSoldOut.value || r.qty > 0) &&
      (!fBrand.value || r.brand === fBrand.value) &&
      (!kw ||
        r.name.toLowerCase().includes(kw) ||
        r.brand.toLowerCase().includes(kw) ||
        r.size.toLowerCase().includes(kw) ||
        r.color.toLowerCase().includes(kw) ||
        String(r.assetId || "").toLowerCase().includes(kw) ||
        String(r.serial || "").toLowerCase().includes(kw)));
    if (sortMode.value === "qtyDesc") list = [...list].sort((a, b) => b.qty - a.qty);
    else if (sortMode.value === "qtyAsc") list = [...list].sort((a, b) => a.qty - b.qty);
    return list;
  });
  const filtered = computed(() => matched.value.slice(0, q.value.trim() ? 200 : 60));
  const cartList = computed(() => Object.values(items));
  const cartCount = computed(() => cartList.value.reduce((s, l) => s + l.count, 0));
  function stock(r: Row): number { return rows.value.find(x => x.id === r.id)?.qty ?? r.qty; }

  function inc(r: Row) {
    const s = stock(r);
    if (s <= 0) { flash(`「${r.name}」库存为 0`); return; }
    if (!items[r.id]) items[r.id] = { entityId: r.id, name: r.name, count: 1 };
    else items[r.id].count = Math.min(s, items[r.id].count + 1);
    buzz();
  }
  function dec(r: Row) {
    if (!items[r.id]) return;
    items[r.id].count--;
    if (items[r.id].count <= 0) delete items[r.id];
    buzz();
  }
  function removeItem(id: string) { delete items[id]; }
  function clearItems() { for (const k of Object.keys(items)) delete items[k]; }

  function flash(t: string) {
    try { toast(t); } catch (_e) { msg.value = t; }
  }

  function overIssue(): string | null {
    for (const l of cartList.value) {
      const s = rows.value.find(x => x.id === l.entityId)?.qty ?? 0;
      if (l.count > s) return `「${l.name}」库存不足（现有 ${s}，出库 ${l.count}）`;
    }
    return null;
  }

  async function submit() {
    const list = cartList.value.map(l => ({ entityId: l.entityId, count: Math.round(l.count) || 0 }));
    if (!list.length || list.some(l => l.count <= 0)) { flash("先添加出库商品并填数量"); return; }
    const over = overIssue();
    if (over) { flash(over); return; }
    saving.value = true;
    const opId = (globalThis.crypto?.randomUUID?.() ?? (Date.now().toString(36) + Math.random().toString(36).slice(2)));
    const body = { reason: reason.value.trim(), note: note.value.trim(), items: list };
    try {
      const res = await $fetch<Record<string, any>>("/api/v1/biz/outbound", {
        method: "POST",
        headers: { "Idempotency-Key": opId },
        body,
      });
      const errs = (res.errors as string[]) || [];
      if (errs.length) flash("部分出库失败：" + errs.join("；"));
      else flash(`出库单已保存（${reason.value}）`);
      clearItems();
      note.value = "";
      buzz(25);
      await load();
    } catch (e: any) {
      const st = e?.statusCode || e?.response?.status || 0;
      if (!st || st >= 500) {
        oq.enqueue({ id: opId, path: "/api/v1/biz/outbound", method: "POST", body, label: `出库单 ${list.length} 款` });
        flash("离线：出库单已排队，联网后自动提交");
        clearItems();
        note.value = "";
      } else {
        flash("出库失败：" + ((e as Error)?.message ?? String(e)));
      }
    } finally {
      saving.value = false;
    }
  }

  async function rollback(t: Outbound) {
    if (!window.confirm(`回滚出库单 ${t.id}？将把 ${t.items.length} 款商品库存加回去。`)) return;
    rollbackBusy.value = t.id;
    try {
      await $fetch("/api/v1/biz/outbound/rollback", { method: "POST", headers: { "Idempotency-Key": `rb-${t.id}` }, body: { outboundId: t.id } });
      flash("出库单已回滚");
      await load();
    } catch (e) {
      flash("回滚失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      rollbackBusy.value = "";
    }
  }

  function dt(ts: string): string { return ts.length >= 16 ? ts.slice(5, 16).replace("T", " ") : ts; }

  // ---------- 扫码（连续加货） ----------
  const scanOpen = ref(false);
  const scanMsg = ref("");
  const videoEl = ref<HTMLVideoElement | null>(null);
  let stream: MediaStream | null = null;
  let scanRAF: number | undefined;
  let lastCode = "";
  let lastTs = 0;
  async function openScan() {
    const w = window as any;
    scanOpen.value = true;
    scanMsg.value = "对准商品二维码/条码（可连续扫描加入）";
    if (!("BarcodeDetector" in w)) { scanMsg.value = "本机不支持扫码，请用搜索框"; return; }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      await nextTick();
      if (videoEl.value) { videoEl.value.srcObject = stream; await videoEl.value.play(); }
      const det = new w.BarcodeDetector();
      const loop = async () => {
        if (!scanOpen.value || !videoEl.value) return;
        try {
          const codes = await det.detect(videoEl.value);
          if (codes && codes.length) onScan(codes[0].rawValue);
        } catch (_e) { /* ignore */ }
        scanRAF = window.requestAnimationFrame(loop);
      };
      loop();
    } catch (_e) {
      scanMsg.value = "无法打开摄像头，请用搜索框";
    }
  }
  function onScan(code: string) {
    const c = String(code || "").trim();
    if (!c) return;
    const now = Date.now();
    if (c === lastCode && now - lastTs < 1500) return;
    lastCode = c; lastTs = now;
    const hit = rows.value.find(r => String(r.assetId || "") === c || r.name.includes(c));
    if (!hit) { scanMsg.value = "未匹配：" + c; return; }
    inc(hit);
    scanMsg.value = "已加入：" + hit.name;
  }
  function closeScan() {
    scanOpen.value = false;
    if (scanRAF) window.cancelAnimationFrame(scanRAF);
    scanRAF = undefined;
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  }
  function onScanInput(e: Event) {
    const el = e.target as HTMLInputElement;
    const v = el.value;
    el.value = "";
    onScan(v);
  }

  // ---------- 离线队列 ----------
  const oq = useOfflineQueue();
  const offline = ref(false);
  const pendingN = ref(0);
  function syncOq() {
    offline.value = oq.isOffline();
    pendingN.value = oq.pending();
  }
</script>

<template>
  <div class="min-h-[70vh] bg-background text-foreground">
    <div class="mx-auto max-w-5xl p-3 md:p-6" style="padding-bottom: calc(6.5rem + env(safe-area-inset-bottom))">
      <header class="mb-3 flex items-center gap-2">
        <h1 class="text-lg font-semibold tracking-tight md:text-xl">出货出库</h1>
        <span v-if="offline" class="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-600">离线<template v-if="pendingN"> · {{ pendingN }}</template></span>
        <div class="ml-auto flex items-center gap-2">
          <NuxtLink to="/intake" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">进货</NuxtLink>
          <NuxtLink to="/ledger" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">台账</NuxtLink>
        </div>
      </header>

      <!-- 移动端：出库 / 记录 切换 -->
      <div v-if="isMobile" class="mb-3 grid grid-cols-2 gap-1 rounded-xl border bg-card p-1 text-sm">
        <button class="rounded-lg py-2 font-medium transition" :class="tab === 'do' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'" @click="tab = 'do'">出库</button>
        <button class="rounded-lg py-2 font-medium transition" :class="tab === 'log' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'" @click="tab = 'log'">记录 {{ outbounds.length }}</button>
      </div>

      <template v-if="!isMobile || tab === 'do'">
        <!-- 去向/原因 + 备注 -->
        <section class="mb-3 rounded-xl border bg-card p-3 shadow-sm">
          <div class="flex flex-wrap items-center gap-2">
            <label class="flex items-center gap-1 text-sm text-muted-foreground">去向/原因
              <select v-model="reason" :class="[inputCls, 'h-11 w-28 text-base']">
                <option v-for="r in REASONS" :key="r" :value="r">{{ r }}</option>
              </select>
            </label>
            <input v-model="note" :class="[inputCls, 'h-11 min-w-0 flex-1 text-base']" placeholder="备注（买家/日期/说明…）" />
          </div>
        </section>

        <!-- 搜索 + 扫码 -->
        <section class="mb-3 rounded-xl border bg-card p-2 shadow-sm">
          <div class="flex items-center gap-2">
            <input v-model="q" :class="[inputCls, 'h-12 min-w-0 flex-1 text-base']" placeholder="搜索（名称/品牌/编号/库位）" />
            <button class="grid h-12 w-12 shrink-0 place-items-center rounded-xl border bg-background transition active:scale-95" title="扫码加入" @click="openScan"><MdiBarcodeScan class="h-6 w-6" /></button>
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <select v-model="fBrand" :class="[inputCls, 'h-10 text-base']"><option value="">全部品牌</option><option v-for="b in brandList" :key="b" :value="b">{{ b }}</option></select>
            <select v-model="sortMode" :class="[inputCls, 'h-10 text-base']"><option value="name">按名称</option><option value="qtyDesc">库存多→少</option><option value="qtyAsc">库存少→多</option></select>
            <label class="inline-flex items-center gap-1 text-xs text-muted-foreground"><input v-model="hideSoldOut" type="checkbox" class="accent-primary" /> 隐藏无库存</label>
            <span class="ml-auto text-xs text-muted-foreground">{{ matched.length }} 款<template v-if="hiddenSoldOut"> · 隐藏 {{ hiddenSoldOut }}</template><template v-if="matched.length > filtered.length">（显示 {{ filtered.length }}）</template></span>
          </div>
          <div v-if="!q && recentOut.length" class="mt-2 flex flex-wrap items-center gap-1 text-xs">
            <span class="text-muted-foreground">最近出库</span>
            <button v-for="r in recentOut" :key="r.id" class="rounded-full border px-2 py-0.5 transition hover:bg-muted" @click="inc(r)">{{ r.name }}</button>
          </div>
          <div class="mt-2 max-h-[46vh] space-y-1 overflow-auto">
            <div
              v-for="r in filtered" :key="r.id"
              class="flex items-center gap-2 rounded-xl px-2 py-1.5"
              :class="r.qty <= 0 ? 'opacity-50' : 'hover:bg-muted/60'"
            >
              <img v-if="r.thumb" :src="imgUrl(r)" loading="lazy" class="h-11 w-11 shrink-0 rounded-lg border object-cover" alt="" />
              <span v-else class="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-dashed bg-muted/60 text-[10px] text-muted-foreground">无图</span>
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-medium">{{ r.name }}</div>
                <div class="truncate text-xs text-muted-foreground">{{ [r.brand, r.size, r.spec].filter(Boolean).join(" ") }} · 库存 {{ r.qty }}</div>
              </div>
              <div class="shrink-0">
                <button v-if="!items[r.id]" class="grid h-11 w-11 place-items-center rounded-full bg-primary text-xl text-primary-foreground transition active:scale-90 disabled:opacity-40" :disabled="r.qty <= 0" @click="inc(r)"><MdiPlus class="h-6 w-6" /></button>
                <div v-else class="flex items-center overflow-hidden rounded-full border">
                  <button class="grid h-11 w-11 place-items-center text-xl transition active:bg-muted" @click="dec(r)"><MdiMinus class="h-5 w-5" /></button>
                  <span class="w-8 text-center text-base font-semibold tabular-nums">{{ items[r.id].count }}</span>
                  <button class="grid h-11 w-11 place-items-center text-xl transition active:bg-muted disabled:opacity-40" :disabled="items[r.id].count >= r.qty" @click="inc(r)"><MdiPlus class="h-6 w-6" /></button>
                </div>
              </div>
            </div>
            <div v-if="!filtered.length" class="py-6 text-center text-sm text-muted-foreground">没有匹配的商品<template v-if="hideSoldOut && hiddenSoldOut">（已隐藏 {{ hiddenSoldOut }} 个无库存）</template></div>
          </div>
        </section>

        <!-- 已选清单 -->
        <section v-if="cartList.length" class="mb-3 rounded-xl border border-primary/30 bg-primary/5 p-3">
          <div class="mb-2 flex items-center gap-2 text-sm font-medium">
            已选（{{ cartList.length }} 款 · {{ cartCount }} 件）
            <span class="ml-auto rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{{ reason }}</span>
          </div>
          <div class="space-y-2">
            <div v-for="l in cartList" :key="l.entityId" class="flex flex-wrap items-center gap-2 rounded-lg bg-card px-3 py-2 text-sm shadow-sm">
              <span class="min-w-0 flex-1 truncate">{{ l.name }}</span>
              <span class="shrink-0 text-xs text-muted-foreground">库存 {{ rows.find(x => x.id === l.entityId)?.qty ?? "-" }}</span>
              <label class="flex items-center gap-1 text-xs text-muted-foreground">数量
                <input v-model.number="l.count" type="number" inputmode="numeric" min="1" :class="[inputCls, 'h-10 w-16 text-base']" />
              </label>
              <button class="rounded px-2 py-1 text-xs text-destructive transition hover:bg-destructive/10" @click="removeItem(l.entityId)">移除</button>
            </div>
          </div>
          <div v-if="!isMobile" class="mt-3 flex justify-end gap-2">
            <button :class="[btnGhost, 'active:scale-95']" @click="clearItems">清空</button>
            <button :class="[btnPrimary, 'active:scale-95']" :disabled="saving" @click="submit">{{ saving ? "保存中…" : "保存出库单" }}</button>
          </div>
        </section>
      </template>

      <!-- 出库记录 -->
      <template v-if="!isMobile || tab === 'log'">
        <section>
          <h2 class="mb-2 text-sm font-semibold text-muted-foreground">出库记录</h2>
          <div class="space-y-2">
            <div v-for="t in outbounds" :key="t.id" class="rounded-xl border bg-card px-3 py-2.5 text-sm" :class="t.rolledBack ? 'opacity-50' : ''">
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-medium tabular-nums">{{ dt(t.ts) }}</span>
                <span v-if="t.reason" class="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{{ t.reason }}</span>
                <span class="text-xs text-muted-foreground">{{ t.items.length }} 款</span>
                <button
                  v-if="!t.rolledBack"
                  class="ml-auto rounded-lg px-2 py-1 text-xs text-destructive transition hover:bg-destructive/10 disabled:opacity-40"
                  :disabled="rollbackBusy === t.id"
                  @click="rollback(t)"
                >回滚</button>
                <span v-else class="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">已回滚</span>
              </div>
              <div v-if="t.note" class="mt-1 text-xs text-muted-foreground">备注：{{ t.note }}</div>
              <div class="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                <span v-for="it in t.items" :key="it.entityId" class="rounded-md bg-muted px-1.5 py-0.5">{{ it.name }} ×{{ it.count }}</span>
              </div>
            </div>
            <div v-if="!outbounds.length" class="py-6 text-center text-sm text-muted-foreground">还没有出库单</div>
          </div>
        </section>
      </template>

      <p v-if="msg" class="mt-3 text-center text-xs text-muted-foreground">{{ msg }}</p>
    </div>

    <!-- 移动端：底部常驻保存条 -->
    <div
      v-if="isMobile && tab === 'do' && cartList.length"
      class="fixed inset-x-0 bottom-0 z-40 border-t bg-card/95 px-3 py-2 backdrop-blur-md"
      style="padding-bottom: calc(0.5rem + env(safe-area-inset-bottom))"
    >
      <div class="flex items-center gap-2">
        <span class="text-sm text-muted-foreground">已选 <b class="text-foreground">{{ cartList.length }}</b> 款 · {{ cartCount }} 件</span>
        <button class="ml-auto h-12 rounded-xl border px-3 text-sm transition active:scale-95" @click="clearItems">清空</button>
        <button class="h-12 rounded-xl bg-primary px-5 text-base font-medium text-primary-foreground transition active:scale-95 disabled:opacity-50" :disabled="saving" @click="submit">{{ saving ? "保存中…" : "保存出库单" }}</button>
      </div>
    </div>

    <!-- 扫码 -->
    <Transition name="fade">
      <div v-if="scanOpen" class="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/80 p-4 text-white" @click.self="closeScan">
        <p class="mb-2 text-center">{{ scanMsg }}</p>
        <video ref="videoEl" class="max-h-[60vh] w-full max-w-md rounded-xl" autoplay playsinline muted></video>
        <div class="mt-3 flex items-center gap-2">
          <input placeholder="或输入编号/名称后回车" class="rounded-lg px-3 py-2 text-black" @keyup.enter="onScanInput" />
          <button class="rounded-lg border border-white px-3 py-2 transition hover:bg-white/10" @click="closeScan">完成</button>
        </div>
      </div>
    </Transition>
  </div>
</template>
