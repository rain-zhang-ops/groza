<script setup lang="ts">
  const $fetch = useNuxtApp().$gxFetch as typeof globalThis.$fetch;
  import { toast } from "@/components/ui/sonner";
  import MdiPlus from "~icons/mdi/plus";
  import MdiMinus from "~icons/mdi/minus";
  import MdiPackageVariantClosed from "~icons/mdi/package-variant-closed";

  definePageMeta({ middleware: ["auth"] });
  useHead({ title: "Groza | 发货" });

  type ShipItem = { entityId: string; name?: string; count: number };
  type Shipment = {
    id: string; ts: string; party?: string; note?: string;
    items: ShipItem[]; status: "pending" | "shipped" | "cancelled";
    shippedTs?: string; outboundId?: string;
  };
  type Row = { id: string; name: string; brand: string; qty: number; thumb: string | null };

  const TABS = [
    { v: "pending", label: "待发货" },
    { v: "shipped", label: "已发货" },
    { v: "cancelled", label: "已取消" },
  ] as const;
  type Tab = (typeof TABS)[number]["v"];

  const shipments = ref<Shipment[]>([]);
  const rows = ref<Row[]>([]);
  const loading = ref(true);
  const err = ref("");
  const msg = ref("");
  const busy = ref("");
  const tab = ref<Tab>("pending");
  const confirmAct = ref<{ type: "ship" | "cancel" | "undo"; sh: Shipment } | null>(null);

  function flash(t: string) { try { toast(t); } catch (_e) { msg.value = t; } }
  function dt(ts: string): string { return String(ts || "").slice(5, 16).replace("T", " "); }
  function totalOf(sh: Shipment): number { return (sh.items || []).reduce((a, it) => a + it.count, 0); }
  function opId(): string { return globalThis.crypto?.randomUUID?.() ?? (Date.now().toString(36) + Math.random().toString(36).slice(2)); }

  const counts = computed(() => {
    const c: Record<Tab, number> = { pending: 0, shipped: 0, cancelled: 0 };
    for (const s of shipments.value) if (c[s.status] !== undefined) c[s.status]++;
    return c;
  });
  const filtered = computed(() => shipments.value.filter(s => s.status === tab.value));

  // 待发货单的库存预警（确认发货时会因不足而失败）
  function shortages(sh: Shipment): string[] {
    const out: string[] = [];
    for (const it of sh.items || []) {
      const r = rows.value.find(x => x.id === it.entityId);
      if (r && r.qty < it.count) out.push(`${it.name} 现 ${r.qty}`);
    }
    return out;
  }

  function fieldOf(e: Record<string, any>, name: string): any {
    for (const f of (e.fields as Array<Record<string, any>>) || []) {
      if (f.name === name) return f.type === "text" ? f.textValue : f.numberValue;
    }
    return "";
  }
  function imgUrl(r: Row): string { return r.thumb ? `/api/v1/entities/${r.id}/attachments/${r.thumb}` : ""; }

  async function load() {
    loading.value = true; err.value = "";
    try {
      const [ss, agg] = await Promise.all([
        $fetch<Shipment[]>("/api/v1/biz/shipments"),
        $fetch<Record<string, any>>("/api/v1/ledger"),
      ]);
      shipments.value = (ss || []) as Shipment[];
      rows.value = ((agg.items as Array<Record<string, any>>) || []).map(e => ({
        id: e.id, name: e.name, brand: fieldOf(e, "品牌") || e.parent || "",
        qty: e.quantity ?? 0, thumb: e.thumb || null,
      }));
    } catch (e) {
      err.value = "加载失败：" + ((e as Error)?.message ?? String(e));
    } finally {
      loading.value = false;
    }
  }
  function onKey(e: KeyboardEvent) {
    if (e.key !== "Escape") return;
    if (confirmAct.value) confirmAct.value = null;
    else if (createOpen.value) closeCreate();
  }
  onMounted(() => {
    load();
    window.addEventListener("keydown", onKey);
  });
  onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

  // ---------- 新建发货单 ----------
  const createOpen = ref(false);
  const party = ref("");
  const note = ref("");
  const q = ref("");
  const items = reactive<Record<string, ShipItem>>({});
  const saving = ref(false);

  const matched = computed(() => {
    const kw = q.value.trim().toLowerCase();
    return rows.value.filter(r =>
      r.qty > 0 &&
      (!kw || r.name.toLowerCase().includes(kw) || r.brand.toLowerCase().includes(kw)));
  });
  const pickerList = computed(() => matched.value.slice(0, q.value.trim() ? 200 : 60));
  const cartList = computed(() => Object.values(items));
  const cartCount = computed(() => cartList.value.reduce((s, l) => s + l.count, 0));

  function stock(id: string): number { return rows.value.find(x => x.id === id)?.qty ?? 0; }
  function inc(r: Row) {
    if (r.qty <= 0) return;
    if (!items[r.id]) items[r.id] = { entityId: r.id, name: r.name, count: 1 };
    else items[r.id].count = Math.min(r.qty, items[r.id].count + 1);
  }
  function dec(r: Row) {
    if (!items[r.id]) return;
    items[r.id].count--;
    if (items[r.id].count <= 0) delete items[r.id];
  }
  function openCreate() { createOpen.value = true; }
  function closeCreate() {
    createOpen.value = false;
    party.value = ""; note.value = ""; q.value = "";
    for (const k of Object.keys(items)) delete items[k];
  }

  async function submitCreate() {
    const list = cartList.value.map(l => ({ entityId: l.entityId, count: Math.round(l.count) || 0 }));
    if (!list.length || list.some(l => l.count <= 0)) { flash("先添加发货商品并填数量"); return; }
    saving.value = true;
    try {
      const res = await $fetch<Record<string, any>>("/api/v1/biz/shipments", {
        method: "POST",
        headers: { "Idempotency-Key": opId() },
        body: { party: party.value.trim(), note: note.value.trim(), items: list },
      });
      const errs = (res.errors as string[]) || [];
      flash(errs.length ? "已建单，注意：" + errs.join("；") : `发货单已建立（${list.length} 款）`);
      closeCreate();
      tab.value = "pending";
      await load();
    } catch (e) {
      flash("建单失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      saving.value = false;
    }
  }

  // ---------- 发货 / 取消 / 撤销 ----------
  const CONFIRM_TEXT = {
    ship: { title: "确认发货", body: (sh: Shipment) => `将扣减 ${sh.items.length} 款商品库存并生成出库单（共 ${totalOf(sh)} 件）。`, ok: "确认发货" },
    cancel: { title: "取消发货单", body: (sh: Shipment) => `买家退款或误建？取消后库存不受影响（${sh.items.length} 款 · ${totalOf(sh)} 件）。`, ok: "确认取消" },
    undo: { title: "撤销发货", body: (sh: Shipment) => `将回滚对应出库单，${sh.items.length} 款商品库存加回。`, ok: "确认撤销" },
  } as const;

  async function runAction() {
    const act = confirmAct.value;
    if (!act) return;
    confirmAct.value = null;
    busy.value = act.sh.id;
    const path = act.type === "ship" ? "/api/v1/biz/shipments/ship" : act.type === "cancel" ? "/api/v1/biz/shipments/cancel" : "/api/v1/biz/shipments/undo";
    try {
      const res = await $fetch<Record<string, any>>(path, {
        method: "POST",
        headers: { "Idempotency-Key": opId() },
        body: { id: act.sh.id },
      });
      const errs = (res.errors as string[]) || [];
      const okMsg = act.type === "ship" ? "已发货，库存已扣减" : act.type === "cancel" ? "已取消" : "已撤销，库存已加回";
      flash(errs.length ? okMsg + "，部分明细异常：" + errs.join("；") : okMsg);
      await load();
    } catch (e) {
      flash("操作失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      busy.value = "";
    }
  }
</script>

<template>
  <div class="min-h-[70vh] bg-background text-foreground">
    <div class="mx-auto max-w-5xl p-4 md:p-8" style="padding-bottom: calc(8rem + env(safe-area-inset-bottom))">
      <header class="mb-6 flex flex-wrap items-center gap-2">
        <h1 class="font-display text-xl font-medium tracking-tight md:text-2xl">发货</h1>
        <span v-if="counts.pending" class="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium tabular-nums text-amber-600">待发 {{ counts.pending }}</span>
        <div class="ml-auto flex flex-wrap items-center gap-2">
          <NuxtLink to="/outbound" :class="btnGhost">出库</NuxtLink>
          <NuxtLink to="/ledger" :class="btnGhost">台账</NuxtLink>
          <button :class="btnPrimary" @click="openCreate">新建发货单</button>
        </div>
      </header>

      <!-- 状态 Tab -->
      <div class="mb-3 flex items-center gap-1.5">
        <button
          v-for="t in TABS" :key="t.v"
          class="rounded-lg px-3 py-1.5 text-sm font-medium transition"
          :class="tab === t.v ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'"
          @click="tab = t.v"
        >{{ t.label }}<template v-if="counts[t.v]"> · {{ counts[t.v] }}</template></button>
      </div>

      <!-- 三态 -->
      <div v-if="loading" class="space-y-2">
        <div v-for="i in 4" :key="i" :class="skeletonCls"></div>
      </div>
      <div v-else-if="err" :class="[errorCls, 'flex items-center gap-2']">
        <span class="min-w-0 flex-1 text-sm">{{ err }}</span>
        <button :class="[btnGhost, 'shrink-0 active:scale-95']" @click="load">重试</button>
      </div>
      <div v-else-if="!filtered.length" :class="emptyCls">
        <MdiPackageVariantClosed class="mx-auto mb-2 h-8 w-8 opacity-40" />
        <template v-if="tab === 'pending'">暂无待发货单，点右上角「新建发货单」开始拣货打包</template>
        <template v-else-if="tab === 'shipped'">暂无已发货记录</template>
        <template v-else>暂无已取消记录</template>
      </div>

      <!-- 单据卡片 -->
      <div v-else class="space-y-2">
        <div
          v-for="sh in filtered" :key="sh.id"
          class="rounded-xl border bg-card p-3 transition-opacity"
          :class="sh.status === 'cancelled' ? 'opacity-60' : ''"
        >
          <div class="flex items-center gap-2">
            <span class="min-w-0 flex-1 truncate font-medium">{{ sh.party || "未填买家/去向" }}</span>
            <span class="shrink-0 text-xs tabular-nums text-muted-foreground">{{ dt(sh.status === "shipped" && sh.shippedTs ? sh.shippedTs : sh.ts) }}</span>
            <span
              :class="[badgeCls, 'shrink-0']"
              :style="sh.status === 'pending' ? 'background: rgb(245 158 11 / 0.15); color: rgb(217 119 6)' : ''"
            >{{ sh.status === "pending" ? "待发货" : sh.status === "shipped" ? "已发货" : "已取消" }}</span>
          </div>
          <div class="mt-2 space-y-1 text-sm">
            <div v-for="it in sh.items" :key="it.entityId" class="flex items-center justify-between gap-2">
              <span class="min-w-0 truncate">{{ it.name }}</span>
              <span class="shrink-0 tabular-nums text-muted-foreground">×{{ it.count }}</span>
            </div>
          </div>
          <div v-if="sh.note" class="mt-1.5 text-xs text-muted-foreground">{{ sh.note }}</div>
          <div v-if="sh.status === 'pending' && shortages(sh).length" class="mt-1.5 text-xs text-amber-600">库存不足：{{ shortages(sh).join("、") }}</div>
          <div class="mt-3 flex items-center gap-2">
            <span class="text-xs tabular-nums text-muted-foreground">合计 {{ totalOf(sh) }} 件</span>
            <div class="ml-auto flex items-center gap-2">
              <template v-if="sh.status === 'pending'">
                <button :class="[btnGhost, 'text-destructive active:scale-95']" :disabled="busy === sh.id" @click="confirmAct = { type: 'cancel', sh }">取消</button>
                <button :class="[btnPrimary, 'active:scale-95']" :disabled="busy === sh.id" @click="confirmAct = { type: 'ship', sh }">{{ busy === sh.id ? "处理中…" : "确认发货" }}</button>
              </template>
              <button v-else-if="sh.status === 'shipped'" :class="[btnGhost, 'active:scale-95']" :disabled="busy === sh.id" @click="confirmAct = { type: 'undo', sh }">撤销发货</button>
            </div>
          </div>
        </div>
      </div>

      <p v-if="msg" class="mt-3 text-center text-xs text-muted-foreground">{{ msg }}</p>
    </div>

    <!-- 新建发货单抽屉 -->
    <Transition name="fade">
      <div v-if="createOpen" :class="drawerWrap" @click.self="closeCreate">
        <div :class="drawerPanel" :style="safeBottom">
          <div class="mb-4 flex items-center gap-2">
            <h2 class="font-display text-lg font-medium">新建发货单</h2>
            <button :class="[btnGhost, 'ml-auto active:scale-95']" @click="closeCreate">关闭</button>
          </div>

          <div class="mb-3 space-y-2">
            <input v-model="party" :class="inputClsLg" placeholder="买家 / 去向（必填建议填）" />
            <input v-model="note" :class="inputClsLg" placeholder="备注（订单号 / 快递 / 说明…）" />
          </div>

          <input v-model="q" :class="[inputClsLg, 'mb-2']" placeholder="搜索商品（名称/品牌）" />
          <div class="max-h-[38vh] space-y-1 overflow-auto">
            <div v-for="r in pickerList" :key="r.id" class="flex items-center gap-2 rounded-xl px-2 py-1.5 hover:bg-muted/60">
              <img v-if="r.thumb" :src="imgUrl(r)" class="h-11 w-11 shrink-0 rounded-lg border object-cover" alt="" />
              <span v-else class="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-dashed bg-muted/60 text-[10px] text-muted-foreground">无图</span>
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-medium">{{ r.name }}</div>
                <div class="truncate text-xs text-muted-foreground">{{ r.brand }} · 库存 {{ r.qty }}</div>
              </div>
              <div class="shrink-0">
                <button v-if="!items[r.id]" class="grid h-11 w-11 place-items-center rounded-full bg-primary text-xl text-primary-foreground transition active:scale-90" @click="inc(r)"><MdiPlus class="h-6 w-6" /></button>
                <div v-else class="flex items-center overflow-hidden rounded-full border">
                  <button class="grid h-11 w-11 place-items-center text-xl transition active:bg-muted" @click="dec(r)"><MdiMinus class="h-5 w-5" /></button>
                  <span class="w-8 text-center text-base font-semibold tabular-nums">{{ items[r.id].count }}</span>
                  <button class="grid h-11 w-11 place-items-center text-xl transition active:bg-muted disabled:opacity-40" :disabled="items[r.id].count >= r.qty" @click="inc(r)"><MdiPlus class="h-6 w-6" /></button>
                </div>
              </div>
            </div>
            <div v-if="!pickerList.length" :class="emptyCls">没有匹配的有库存商品</div>
          </div>

          <div v-if="cartList.length" class="mt-3 rounded-xl border border-primary/30 bg-primary/5 p-3">
            <div class="mb-2 text-sm font-medium">已选（{{ cartList.length }} 款 · {{ cartCount }} 件）</div>
            <div class="space-y-2">
              <div v-for="l in cartList" :key="l.entityId" class="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm">
                <span class="min-w-0 flex-1 truncate">{{ l.name }}</span>
                <label class="flex items-center gap-1 text-xs text-muted-foreground">数量
                  <input v-model.number="l.count" type="number" inputmode="numeric" min="1" :max="stock(l.entityId)" :class="[inputCls, 'h-10 w-16 text-base']" />
                </label>
                <button class="h-9 rounded-lg px-3 text-xs text-destructive transition hover:bg-destructive/10 active:scale-95" @click="delete items[l.entityId]">移除</button>
              </div>
            </div>
          </div>

          <div class="mt-4 flex justify-end gap-2">
            <button :class="[btnGhost, 'active:scale-95']" @click="closeCreate">取消</button>
            <button :class="[btnPrimary, 'active:scale-95']" :disabled="saving || !cartList.length" @click="submitCreate">{{ saving ? "保存中…" : "保存发货单" }}</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 居中确认弹窗 -->
    <Transition name="fade">
      <div v-if="confirmAct" class="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" @click.self="confirmAct = null">
        <div class="w-full max-w-sm rounded-xl border bg-card p-5">
          <h3 class="font-display text-lg font-medium">{{ CONFIRM_TEXT[confirmAct.type].title }}</h3>
          <p class="mt-2 text-sm text-muted-foreground">{{ CONFIRM_TEXT[confirmAct.type].body(confirmAct.sh) }}</p>
          <div class="mt-4 flex justify-end gap-2">
            <button :class="[btnGhost, 'active:scale-95']" @click="confirmAct = null">再想想</button>
            <button :class="[btnPrimary, 'active:scale-95']" @click="runAction">{{ CONFIRM_TEXT[confirmAct.type].ok }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
