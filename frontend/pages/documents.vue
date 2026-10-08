<script setup lang="ts">
  import { toast } from "@/components/ui/sonner";
  const $fetch = useNuxtApp().$gxFetch as typeof globalThis.$fetch;

  definePageMeta({ middleware: ["auth"] });
  useHead({ title: "Groza | 单据" });

  type Doc = {
    id: string; kind: "intake" | "outbound" | "adjust"; ts: string; party: string;
    note: string; status: string; rolledBack: boolean;
    items: Array<{ entityId: string; name: string; count: number; cost?: number }>;
    totalCost: number;
  };

  const KIND = [
    { v: "intake", label: "入库" },
    { v: "outbound", label: "出库" },
    { v: "adjust", label: "盘点调整" },
  ] as const;
  const kind = ref<"intake" | "outbound" | "adjust">("intake");
  const docs = ref<Doc[]>([]);
  const loading = ref(true);
  const err = ref("");
  const q = ref("");
  const showRolled = ref(true);
  const busy = ref("");
  const dFrom = ref("");
  const dTo = ref("");
  const fParty = ref("");
  const inputCls = "rounded-lg border bg-background px-2.5 py-1.5 text-sm outline-none transition focus:ring-2 focus:ring-ring/40";

  function flash(t: string) { try { toast(t); } catch (_e) { alert(t); } }
  function fmt(n: number | null | undefined): string { return n === null || n === undefined ? "0.00" : Number(n).toFixed(2); }
  function dt(ts: string): string { return String(ts || "").slice(5, 16).replace("T", " "); }

  const partyLabel = computed(() => kind.value === "intake" ? "供应商" : kind.value === "outbound" ? "去向 / 原因" : "备注");
  const parties = computed(() => [...new Set(docs.value.map(d => d.party).filter(Boolean))].sort());
  const matched = computed(() => {
    const kw = q.value.trim().toLowerCase();
    return docs.value.filter(d => {
      const day = String(d.ts || "").slice(0, 10);
      return (showRolled.value || !d.rolledBack) &&
        (!fParty.value || d.party === fParty.value) &&
        (!dFrom.value || day >= dFrom.value) &&
        (!dTo.value || day <= dTo.value) &&
        (!kw || (d.items || []).some(it => String(it.name || "").toLowerCase().includes(kw)) ||
          String(d.party || "").toLowerCase().includes(kw) || String(d.note || "").toLowerCase().includes(kw) || d.id.includes(kw));
    });
  });
  const totals = computed(() => {
    let cnt = 0, cost = 0;
    for (const d of matched.value) if (!d.rolledBack) { cnt += (d.items || []).reduce((a, it) => a + it.count, 0); cost += d.totalCost || 0; }
    return { cnt, cost };
  });
  watch(kind, () => { fParty.value = ""; load(); });

  async function load() {
    loading.value = true; err.value = "";
    try {
      const res = await $fetch<{ documents: Doc[] }>("/api/v1/gx/documents", { params: { kind: kind.value, limit: 500 } });
      docs.value = res.documents || [];
    } catch (e) { err.value = "加载失败：" + ((e as Error)?.message ?? String(e)); }
    finally { loading.value = false; }
  }
  onMounted(load);
  async function rollback(d: Doc) {
    if (!window.confirm(`回滚该${kind.value === "intake" ? "入库" : "出库"}单 ${d.id}？将把库存改回去。`)) return;
    busy.value = d.id;
    try {
      const path = d.kind === "intake" ? "/api/v1/biz/intake/rollback" : "/api/v1/biz/outbound/rollback";
      const body = d.kind === "intake" ? { intakeId: d.id } : { outboundId: d.id };
      await $fetch(path, { method: "POST", headers: { "Idempotency-Key": `rb-${d.id}` }, body });
      flash("已回滚");
      await load();
    } catch (e) { flash("回滚失败：" + ((e as Error)?.message ?? String(e))); }
    finally { busy.value = ""; }
  }

  function exportCSV() {
    const cols = ["时间", "类型", "单号", partyLabel.value, "款数", "件数", "明细", "金额", "状态"];
    const esc = (v: any) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [cols.join(",")];
    for (const d of matched.value) {
      const items = (d.items || []).map(it => `${it.name}×${it.count}`).join("; ");
      lines.push([d.ts, kind.value, d.id, d.party || "", (d.items || []).length, (d.items || []).reduce((a, it) => a + it.count, 0), items, d.totalCost || 0, d.rolledBack ? "已回滚" : ""].map(esc).join(","));
    }
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `单据-${kind.value}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
    flash(`已导出 ${matched.value.length} 单`);
  }
</script>

<template>
  <div class="min-h-[70vh] bg-background text-foreground">
    <div class="mx-auto max-w-5xl p-4 md:p-8" style="padding-bottom: calc(2rem + env(safe-area-inset-bottom))">
      <header class="mb-4 flex flex-wrap items-center gap-2">
        <h1 class="text-lg font-semibold tracking-tight md:text-xl">单据</h1>
        <span class="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary tabular-nums">{{ matched.length }} 单</span>
        <div class="ml-auto flex flex-wrap items-center gap-2">
          <NuxtLink to="/intake" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">入库</NuxtLink>
          <NuxtLink to="/outbound" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">出库</NuxtLink>
          <NuxtLink to="/ledger" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">台账</NuxtLink>
        </div>
      </header>

      <div class="mb-3 flex flex-wrap items-center gap-1 rounded-xl border bg-card p-1.5 shadow-sm">
        <button v-for="k in KIND" :key="k.v" class="rounded-lg px-3 py-1.5 text-sm font-medium transition" :class="kind === k.v ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'" @click="kind = k.v">{{ k.label }}</button>
      </div>

      <section class="mb-3 rounded-xl border bg-card p-2 shadow-sm">
        <div class="flex flex-wrap items-center gap-2">
          <input v-model="q" :class="[inputCls, 'h-10 min-w-0 flex-1 text-base']" placeholder="搜索：单号 / 明细 / 备注" />
          <select v-model="fParty" :class="[inputCls, 'h-10 max-w-40 text-base']">
            <option value="">全部{{ partyLabel }}</option>
            <option v-for="p in parties" :key="p" :value="p">{{ p }}</option>
          </select>
          <label class="inline-flex items-center gap-1 text-xs text-muted-foreground"><input v-model="showRolled" type="checkbox" class="accent-primary" /> 显示已回滚</label>
          <button class="rounded-lg border px-2.5 py-1.5 text-sm transition hover:bg-muted" @click="exportCSV">导出CSV</button>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <label>从 <input v-model="dFrom" type="date" :class="[inputCls, 'h-9']" /></label>
          <label>到 <input v-model="dTo" type="date" :class="[inputCls, 'h-9']" /></label>
          <span class="ml-auto">共 {{ matched.length }} 单 · {{ totals.cnt }} 件<template v-if="kind !== 'outbound'"> · 金额 ¥{{ fmt(totals.cost) }}</template>（不含已回滚）</span>
        </div>
      </section>

      <div v-if="loading" class="space-y-2">
        <div v-for="i in 5" :key="i" class="h-16 animate-pulse rounded-xl border bg-muted/40"></div>
      </div>
      <div v-else-if="err" class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-destructive">{{ err }}</div>
      <div v-else class="space-y-2">
        <div v-for="d in matched" :key="d.id" class="rounded-xl border bg-card px-3 py-2.5 text-sm" :class="d.rolledBack ? 'opacity-50' : ''">
          <div class="flex flex-wrap items-center gap-2">
            <span class="font-medium tabular-nums">{{ dt(d.ts) }}</span>
            <span v-if="d.party" class="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{{ d.party }}</span>
            <span class="text-xs text-muted-foreground">{{ (d.items || []).length }} 款 · {{ (d.items || []).reduce((a, it) => a + it.count, 0) }} 件</span>
            <span v-if="kind !== 'outbound'" class="font-medium tabular-nums">¥{{ fmt(d.totalCost) }}</span>
            <span class="text-xs text-muted-foreground">#{{ d.id }}</span>
            <button
              v-if="!d.rolledBack && kind !== 'adjust'"
              class="ml-auto rounded-lg px-2 py-1 text-xs text-destructive transition hover:bg-destructive/10 disabled:opacity-40"
              :disabled="busy === d.id"
              @click="rollback(d)"
            >回滚</button>
            <span v-else-if="d.rolledBack" class="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">已回滚</span>
          </div>
          <div v-if="d.note" class="mt-1 text-xs text-muted-foreground">备注：{{ d.note }}</div>
          <div class="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
            <span v-for="it in (d.items || [])" :key="it.entityId" class="rounded-md bg-muted px-1.5 py-0.5">{{ it.name || "（已删除）" }} ×{{ it.count }}</span>
          </div>
        </div>
        <div v-if="!matched.length" class="py-10 text-center text-sm text-muted-foreground">暂无单据</div>
      </div>
    </div>
  </div>
</template>
