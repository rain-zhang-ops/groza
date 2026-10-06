<script setup lang="ts">
  import { toast } from "@/components/ui/sonner";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({
    title: "HomeBox | 进货入库",
  });

  type Row = {
    id: string;
    name: string;
    brand: string;
    size: string;
    spec: string;
    color: string;
    sell: number | null;
    purchase: number | null;
    qty: number;
    thumb: string | null;
  };
  type IntakeItem = { entityId: string; name?: string; count: number; cost: number; sell: number };
  type Intake = {
    id: string; ts: string; supplier?: string; note?: string;
    items: IntakeItem[]; totalCost: number; rolledBack?: boolean;
  };

  const rows = ref<Row[]>([]);
  const intakes = ref<Intake[]>([]);
  const q = ref("");
  const loading = ref(true);
  const err = ref("");
  const msg = ref("");
  const supplier = ref("");
  const note = ref("");
  const items = reactive<Record<string, IntakeItem>>({});
  const saving = ref(false);
  const rollbackBusy = ref("");

  const SUP_KEY = "hb.intake.suppliers";
  const suppliers = ref<string[]>([]);
  try { suppliers.value = JSON.parse(localStorage.getItem(SUP_KEY) || "[]"); } catch (_e) { suppliers.value = []; }

  const btnGhost = "inline-flex items-center gap-1 rounded-lg border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50";
  const btnPrimary = "inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50";
  const inputCls = "rounded-lg border bg-background px-2.5 py-1.5 text-sm outline-none transition focus:ring-2 focus:ring-ring/40";

  function num(v: unknown): number | null {
    if (v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
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
      const [agg, fl] = await Promise.all([
        $fetch<Record<string, any>>("/api/v1/ledger"),
        $fetch<Array<Record<string, any>>>("/api/v1/biz/intakes").catch(() => []),
      ]);
      rows.value = ((agg.items as Array<Record<string, any>>) || []).map(e => ({
        id: e.id, name: e.name,
        brand: fieldOf(e, "品牌") || e.parent || "",
        size: fieldOf(e, "尺寸") || "", spec: fieldOf(e, "规格") || "", color: fieldOf(e, "颜色") || "",
        sell: num(fieldOf(e, "售价")), purchase: num(fieldOf(e, "进价")),
        qty: e.quantity ?? 0, thumb: e.thumb || null,
      }));
      intakes.value = (fl || []) as Intake[];
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
  });

  const filtered = computed(() => {
    const kw = q.value.trim().toLowerCase();
    const list = rows.value.filter(r =>
      !kw ||
      r.name.toLowerCase().includes(kw) ||
      r.brand.toLowerCase().includes(kw) ||
      r.size.toLowerCase().includes(kw) ||
      r.color.toLowerCase().includes(kw));
    if (!kw) return list.slice(0, 80);
    return list.slice(0, 200);
  });
  const cartList = computed(() => Object.values(items));
  const cartCount = computed(() => cartList.value.reduce((s, l) => s + l.count, 0));
  const totalCost = computed(() => cartList.value.reduce((s, l) => s + l.count * (l.cost || 0), 0));

  function addItem(r: Row) {
    if (!items[r.id]) items[r.id] = { entityId: r.id, name: r.name, count: 10, cost: r.purchase || 0, sell: r.sell || 0 };
  }
  function removeItem(id: string) { delete items[id]; }

  function flash(t: string) {
    try { toast(t); } catch (_e) { msg.value = t; }
  }

  function saveSupplier() {
    const s = supplier.value.trim();
    if (!s) return;
    suppliers.value = [s, ...suppliers.value.filter(x => x !== s)].slice(0, 20);
    localStorage.setItem(SUP_KEY, JSON.stringify(suppliers.value));
  }

  function clearItems() {
    for (const k of Object.keys(items)) delete items[k];
  }

  async function submit() {
    saveSupplier();
    const list = cartList.value.map(l => ({ entityId: l.entityId, count: Math.round(l.count) || 0, cost: l.cost || 0, sell: l.sell || 0 }));
    if (!list.length || list.some(l => l.count <= 0)) { flash("先添加入库商品并填数量"); return; }
    saving.value = true;
    try {
      const res = await $fetch<Record<string, any>>("/api/v1/biz/intake", {
        method: "POST",
        body: { supplier: supplier.value.trim(), note: note.value.trim(), items: list },
      });
      const errs = (res.errors as string[]) || [];
      if (errs.length) flash("部分入库失败：" + errs.join("；"));
      else flash(`入库单已保存 ¥${totalCost.value.toFixed(2)}`);
      for (const k of Object.keys(items)) delete items[k];
      note.value = "";
      await load();
    } catch (e: any) {
      const st = e?.statusCode || e?.response?.status || 0;
      if (!st || st >= 500) {
        oq.enqueue({ path: "/api/v1/biz/intake", method: "POST", body: { supplier: supplier.value.trim(), note: note.value.trim(), items: list }, label: `入库单 ${list.length} 款` });
        flash("离线：入库单已排队，联网后自动提交");
        for (const k of Object.keys(items)) delete items[k];
        note.value = "";
      } else {
        flash("入库失败：" + ((e as Error)?.message ?? String(e)));
      }
    } finally {
      saving.value = false;
    }
  }

  async function rollback(t: Intake) {
    if (!window.confirm(`回滚入库单 ${t.id}？将把 ${t.items.length} 款商品库存减回去。`)) return;
    rollbackBusy.value = t.id;
    try {
      await $fetch("/api/v1/biz/intake/rollback", { method: "POST", body: { intakeId: t.id } });
      flash("入库单已回滚");
      await load();
    } catch (e) {
      flash("回滚失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      rollbackBusy.value = "";
    }
  }

  function fmt(n: number | null | undefined): string { return n === null || n === undefined ? "" : Number(n).toFixed(2); }
  function dt(ts: string): string { return ts.length >= 16 ? ts.slice(5, 16).replace("T", " ") : ts; }

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
    <div class="mx-auto max-w-5xl p-3 md:p-6" style="padding-bottom: calc(2rem + env(safe-area-inset-bottom))">
      <header class="mb-4 flex items-center gap-2">
        <h1 class="text-lg font-semibold tracking-tight md:text-xl">进货入库</h1>
        <span v-if="offline" class="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-600">离线<template v-if="pendingN"> · {{ pendingN }}</template></span>
        <div class="ml-auto flex items-center gap-2">
          <NuxtLink to="/ledger" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">台账</NuxtLink>
        </div>
      </header>

      <!-- 入库单表单 -->
      <section class="mb-5 rounded-xl border bg-card p-3 shadow-sm">
        <div class="flex flex-wrap items-center gap-2">
          <input v-model="supplier" :class="[inputCls, 'w-full md:w-56']" list="sup-list" placeholder="供应商（自由填写）" @change="saveSupplier" />
          <datalist id="sup-list">
            <option v-for="s in suppliers" :key="s" :value="s"></option>
          </datalist>
          <input v-model="note" :class="[inputCls, 'min-w-0 flex-1']" placeholder="备注（档口/日期/特殊约定…）" />
        </div>
        <div class="mt-2 flex items-center gap-2">
          <input v-model="q" :class="[inputCls, 'h-11 min-w-0 flex-1 text-base']" placeholder="搜索商品加入入库单" />
        </div>
        <div class="mt-2 max-h-56 space-y-1 overflow-auto">
          <button
            v-for="r in filtered" :key="r.id"
            class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition hover:bg-muted/60 active:scale-[0.99]"
            @click="addItem(r)"
          >
            <img v-if="r.thumb" :src="imgUrl(r)" loading="lazy" class="h-9 w-9 shrink-0 rounded-md border object-cover" alt="" />
            <span class="min-w-0 flex-1 truncate">{{ r.name }}</span>
            <span class="shrink-0 text-xs text-muted-foreground">{{ [r.brand, r.size, r.spec].filter(Boolean).join(" ") }}</span>
            <span class="shrink-0 text-xs tabular-nums text-muted-foreground">库存 {{ r.qty }}</span>
            <span class="shrink-0 text-xs font-medium text-primary">＋加入</span>
          </button>
          <div v-if="!filtered.length" class="py-4 text-center text-sm text-muted-foreground">没有匹配的商品（先到台账新增）</div>
        </div>
      </section>

      <!-- 入库明细 -->
      <section v-if="cartList.length" class="mb-5 rounded-xl border border-primary/30 bg-primary/5 p-3">
        <div class="mb-2 flex items-center gap-2 text-sm font-medium">
          入库明细（{{ cartCount }} 件）
          <span class="ml-auto font-semibold tabular-nums">总成本 ¥{{ fmt(totalCost) }}</span>
        </div>
        <div class="space-y-2">
          <div v-for="l in cartList" :key="l.entityId" class="flex flex-wrap items-center gap-2 rounded-lg bg-card px-3 py-2 text-sm shadow-sm">
            <span class="min-w-0 flex-1 truncate">{{ l.name }}</span>
            <label class="flex items-center gap-1 text-xs text-muted-foreground">数量
              <input v-model.number="l.count" type="number" inputmode="numeric" :class="[inputCls, 'w-16']" />
            </label>
            <label class="flex items-center gap-1 text-xs text-muted-foreground">成本
              <input v-model.number="l.cost" type="number" inputmode="decimal" :class="[inputCls, 'w-16']" />
            </label>
            <label class="flex items-center gap-1 text-xs text-muted-foreground">售价
              <input v-model.number="l.sell" type="number" inputmode="decimal" :class="[inputCls, 'w-16']" />
            </label>
            <button class="rounded px-2 py-1 text-xs text-destructive transition hover:bg-destructive/10" @click="removeItem(l.entityId)">移除</button>
          </div>
        </div>
        <div class="mt-3 flex justify-end gap-2">
          <button :class="[btnGhost, 'active:scale-95']" @click="clearItems">清空</button>
          <button :class="[btnPrimary, 'active:scale-95']" :disabled="saving" @click="submit">{{ saving ? "保存中…" : "保存入库单" }}</button>
        </div>
      </section>

      <!-- 入库单历史 -->
      <section>
        <h2 class="mb-2 text-sm font-semibold text-muted-foreground">入库单</h2>
        <div class="space-y-2">
          <div v-for="t in intakes" :key="t.id" class="rounded-xl border bg-card px-3 py-2.5 text-sm" :class="t.rolledBack ? 'opacity-50' : ''">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-medium tabular-nums">{{ dt(t.ts) }}</span>
              <span v-if="t.supplier" class="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{{ t.supplier }}</span>
              <span class="text-xs text-muted-foreground">{{ t.items.length }} 款</span>
              <span class="ml-auto font-medium tabular-nums">¥{{ fmt(t.totalCost) }}</span>
              <button
                v-if="!t.rolledBack"
                class="rounded-lg px-2 py-1 text-xs text-destructive transition hover:bg-destructive/10 disabled:opacity-40"
                :disabled="rollbackBusy === t.id"
                @click="rollback(t)"
              >回滚</button>
              <span v-else class="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">已回滚</span>
            </div>
            <div v-if="t.note" class="mt-1 text-xs text-muted-foreground">备注：{{ t.note }}</div>
            <div class="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
              <span v-for="it in t.items" :key="it.entityId" class="rounded-md bg-muted px-1.5 py-0.5">{{ it.name }} ×{{ it.count }}</span>
            </div>
          </div>
          <div v-if="!intakes.length" class="py-6 text-center text-sm text-muted-foreground">还没有入库单</div>
        </div>
      </section>

      <p v-if="msg" class="mt-3 text-center text-xs text-muted-foreground">{{ msg }}</p>
    </div>
  </div>
</template>
