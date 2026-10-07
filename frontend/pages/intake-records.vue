<script setup lang="ts">
  const $fetch = useNuxtApp().$gxFetch as typeof globalThis.$fetch;
  import { toast } from "@/components/ui/sonner";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({
    title: "Groza | 进货记录",
  });

  type IntakeItem = { entityId: string; name?: string; count: number; cost?: number; sell?: number };
  type Intake = {
    id: string; ts: string; supplier?: string; note?: string;
    items: IntakeItem[]; totalCost: number; rolledBack?: boolean;
  };

  const intakes = ref<Intake[]>([]);
  const loading = ref(true);
  const err = ref("");
  const msg = ref("");
  const q = ref("");
  const fSupplier = ref("");
  const showRolled = ref(true);
  const dFrom = ref("");
  const dTo = ref("");
  const rollbackBusy = ref("");

  const inputCls = "rounded-lg border bg-background px-2.5 py-1.5 text-sm outline-none transition focus:ring-2 focus:ring-ring/40";

  function flash(t: string) {
    try { toast(t); } catch (_e) { msg.value = t; }
  }
  function fmt(n: number | null | undefined): string { return n === null || n === undefined ? "0.00" : Number(n).toFixed(2); }

  async function load() {
    loading.value = true; err.value = "";
    try {
      const res = await $fetch<{ documents: Array<Record<string, any>> }>("/api/v1/gx/documents", { params: { kind: "intake", limit: 500 } });
      intakes.value = (res.documents || []).map(d => ({
        id: d.id, ts: d.ts, supplier: d.party, note: d.note,
        items: (d.items || []).map((it: Record<string, any>) => ({ entityId: it.entityId, name: it.name, count: it.count, cost: it.cost })),
        totalCost: d.totalCost, rolledBack: d.rolledBack,
      })) as Intake[];
    } catch (e) { err.value = "加载失败：" + ((e as Error)?.message ?? String(e)); }
    finally { loading.value = false; }
  }
  onMounted(load);

  const suppliers = computed(() => {
    const s = new Set<string>();
    for (const t of intakes.value) if (t.supplier) s.add(t.supplier);
    return [...s];
  });
  const matched = computed(() => {
    const kw = q.value.trim().toLowerCase();
    return intakes.value.filter(t => {
      const d = t.ts.slice(0, 10);
      return (showRolled.value || !t.rolledBack) &&
        (!fSupplier.value || t.supplier === fSupplier.value) &&
        (!dFrom.value || d >= dFrom.value) &&
        (!dTo.value || d <= dTo.value) &&
        (!kw || (t.items || []).some(it => String(it.name || "").toLowerCase().includes(kw)) || String(t.supplier || "").toLowerCase().includes(kw) || String(t.note || "").toLowerCase().includes(kw) || t.id.includes(kw));
    });
  });
  const totals = computed(() => {
    let cnt = 0, cost = 0;
    for (const t of matched.value) if (!t.rolledBack) { cnt += (t.items || []).reduce((a, it) => a + it.count, 0); cost += t.totalCost || 0; }
    return { cnt, cost };
  });

  async function rollback(t: Intake) {
    if (!window.confirm(`回滚入库单 ${t.id}？将把 ${t.items.length} 款商品库存减回去。`)) return;
    rollbackBusy.value = t.id;
    try {
      await $fetch("/api/v1/biz/intake/rollback", { method: "POST", headers: { "Idempotency-Key": `rb-${t.id}` }, body: { intakeId: t.id } });
      flash("入库单已回滚");
      await load();
    } catch (e) { flash("回滚失败：" + ((e as Error)?.message ?? String(e))); }
    finally { rollbackBusy.value = ""; }
  }

  function exportCSV() {
    const cols = ["时间", "单号", "供应商", "款数", "件数", "商品明细", "总成本", "状态"];
    const esc = (v: any) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [cols.join(",")];
    for (const t of matched.value) {
      const items = (t.items || []).map(it => `${it.name}×${it.count}`).join("; ");
      lines.push([t.ts, t.id, t.supplier || "", (t.items || []).length, (t.items || []).reduce((a, it) => a + it.count, 0), items, t.totalCost || 0, t.rolledBack ? "已回滚" : ""].map(esc).join(","));
    }
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `进货记录-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
    flash(`已导出 ${matched.value.length} 单`);
  }
  function copyText() {
    const lines = [`Groza 进货记录 · ${new Date().toLocaleDateString()} · ${matched.value.length} 单`];
    for (const t of matched.value) lines.push(`· ${t.ts.slice(0, 16).replace("T", " ")}  ${t.supplier || ""}  ${(t.items || []).map(it => it.name + "×" + it.count).join("、")}  ¥${fmt(t.totalCost)}`);
    const txt = lines.join("\n");
    navigator.clipboard?.writeText(txt).then(() => flash("已复制到剪贴板")).catch(() => window.prompt("复制：", txt));
  }

  function dt(ts: string): string { return ts.length >= 16 ? ts.slice(5, 16).replace("T", " ") : ts; }
</script>

<template>
  <div class="min-h-[70vh] bg-background text-foreground">
    <div class="mx-auto max-w-5xl p-3 md:p-6" style="padding-bottom: calc(2rem + env(safe-area-inset-bottom))">
      <header class="mb-3 flex items-center gap-2">
        <h1 class="text-lg font-semibold tracking-tight md:text-xl">进货记录</h1>
        <span class="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary tabular-nums">{{ matched.length }} 单</span>
        <div class="ml-auto flex items-center gap-2">
          <NuxtLink to="/intake" class="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90">去进货</NuxtLink>
          <NuxtLink to="/ledger" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">台账</NuxtLink>
        </div>
      </header>

      <section class="mb-3 rounded-xl border bg-card p-2 shadow-sm">
        <div class="flex flex-wrap items-center gap-2">
          <input v-model="q" :class="[inputCls, 'h-10 min-w-0 flex-1 text-base']" placeholder="搜索：商品名 / 供应商 / 备注 / 单号" />
          <select v-model="fSupplier" :class="[inputCls, 'h-10 text-base']"><option value="">全部供应商</option><option v-for="s in suppliers" :key="s" :value="s">{{ s }}</option></select>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <label>从 <input v-model="dFrom" type="date" :class="[inputCls, 'h-9']" /></label>
          <label>到 <input v-model="dTo" type="date" :class="[inputCls, 'h-9']" /></label>
          <label class="inline-flex items-center gap-1"><input v-model="showRolled" type="checkbox" class="accent-primary" /> 显示已回滚</label>
          <button class="rounded-lg border px-2.5 py-1.5 transition hover:bg-muted" @click="exportCSV">导出CSV</button>
          <button class="rounded-lg border px-2.5 py-1.5 transition hover:bg-muted" @click="copyText">复制文本</button>
        </div>
        <div class="mt-1.5 text-xs text-muted-foreground">共 {{ matched.length }} 单 · 入库 {{ totals.cnt }} 件 · 总成本 ¥{{ fmt(totals.cost) }}（不含已回滚）</div>
      </section>

      <div v-if="loading" class="space-y-2">
        <div v-for="i in 5" :key="i" class="h-16 animate-pulse rounded-xl border bg-muted/40"></div>
      </div>
      <div v-else-if="err" class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-destructive">{{ err }}</div>
      <div v-else class="space-y-2">
        <div v-for="t in matched" :key="t.id" class="rounded-xl border bg-card px-3 py-2.5 text-sm" :class="t.rolledBack ? 'opacity-50' : ''">
          <div class="flex flex-wrap items-center gap-2">
            <span class="font-medium tabular-nums">{{ dt(t.ts) }}</span>
            <span v-if="t.supplier" class="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{{ t.supplier }}</span>
            <span class="text-xs text-muted-foreground">{{ t.items.length }} 款 · {{ t.items.reduce((a, it) => a + it.count, 0) }} 件</span>
            <span class="font-medium tabular-nums">¥{{ fmt(t.totalCost) }}</span>
            <span class="text-xs text-muted-foreground">#{{ t.id }}</span>
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
        <div v-if="!matched.length" class="py-10 text-center text-sm text-muted-foreground">没有匹配的入库单</div>
      </div>

      <p v-if="msg" class="mt-3 text-center text-xs text-muted-foreground">{{ msg }}</p>
    </div>
  </div>
</template>
