<script setup lang="ts">
  const $fetch = useNuxtApp().$gxFetch as typeof globalThis.$fetch;
  import { toast } from "@/components/ui/sonner";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({
    title: "Groza | 出库记录",
  });

  type OutboundItem = { entityId: string; name?: string; count: number };
  type Outbound = {
    id: string; ts: string; reason?: string; note?: string;
    items: OutboundItem[]; rolledBack?: boolean;
  };

  const outbounds = ref<Outbound[]>([]);
  const loading = ref(true);
  const err = ref("");
  const msg = ref("");
  const q = ref("");
  const fReason = ref("");
  const dFrom = ref("");
  const dTo = ref("");
  const showRolled = ref(true);
  const rollbackBusy = ref("");

  const inputCls = "rounded-lg border bg-background px-2.5 py-1.5 text-sm outline-none transition focus:ring-2 focus:ring-ring/40";

  function flash(t: string) {
    try { toast(t); } catch (_e) { msg.value = t; }
  }

  async function load() {
    loading.value = true; err.value = "";
    try {
      const res = await $fetch<{ documents: Array<Record<string, any>> }>("/api/v1/gx/documents", { params: { kind: "outbound", limit: 500 } });
      outbounds.value = (res.documents || []).map(d => ({
        id: d.id, ts: d.ts, reason: d.party, note: d.note,
        items: (d.items || []).map((it: Record<string, any>) => ({ entityId: it.entityId, name: it.name, count: it.count })),
        rolledBack: d.rolledBack,
      })) as Outbound[];
    } catch (e) { err.value = "加载失败：" + ((e as Error)?.message ?? String(e)); }
    finally { loading.value = false; }
  }
  onMounted(load);

  const reasons = computed(() => {
    const s = new Set<string>();
    for (const t of outbounds.value) if (t.reason) s.add(t.reason);
    return [...s];
  });
  const matched = computed(() => {
    const kw = q.value.trim().toLowerCase();
    return outbounds.value.filter(t => {
      const d = t.ts.slice(0, 10);
      return (showRolled.value || !t.rolledBack) &&
        (!fReason.value || t.reason === fReason.value) &&
        (!dFrom.value || d >= dFrom.value) &&
        (!dTo.value || d <= dTo.value) &&
        (!kw || (t.items || []).some(it => String(it.name || "").toLowerCase().includes(kw)) || String(t.note || "").toLowerCase().includes(kw) || t.id.includes(kw));
    });
  });
  const totalOut = computed(() => matched.value.reduce((s, t) => s + (t.rolledBack ? 0 : (t.items || []).reduce((a, it) => a + it.count, 0)), 0));

  async function rollback(t: Outbound) {
    if (!window.confirm(`回滚出库单 ${t.id}？将把 ${t.items.length} 款商品库存加回去。`)) return;
    rollbackBusy.value = t.id;
    try {
      await $fetch("/api/v1/biz/outbound/rollback", { method: "POST", headers: { "Idempotency-Key": `rb-${t.id}` }, body: { outboundId: t.id } });
      flash("出库单已回滚");
      await load();
    } catch (e) { flash("回滚失败：" + ((e as Error)?.message ?? String(e))); }
    finally { rollbackBusy.value = ""; }
  }

  function exportCSV() {
    const cols = ["时间", "单号", "去向", "款数", "件数", "商品明细", "状态"];
    const esc = (v: any) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [cols.join(",")];
    for (const t of matched.value) {
      const items = (t.items || []).map(it => `${it.name}×${it.count}`).join("; ");
      lines.push([t.ts, t.id, t.reason || "", (t.items || []).length, (t.items || []).reduce((a, it) => a + it.count, 0), items, t.rolledBack ? "已回滚" : ""].map(esc).join(","));
    }
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `出库记录-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
    flash(`已导出 ${matched.value.length} 单`);
  }
  function copyText() {
    const lines = [`Groza 出库记录 · ${new Date().toLocaleDateString()} · ${matched.value.length} 单`];
    for (const t of matched.value) lines.push(`· ${t.ts.slice(0, 16).replace("T", " ")}  ${t.reason || ""}  ${(t.items || []).map(it => it.name + "×" + it.count).join("、")}`);
    const txt = lines.join("\n");
    navigator.clipboard?.writeText(txt).then(() => flash("已复制到剪贴板")).catch(() => window.prompt("复制：", txt));
  }
  function dt(ts: string): string { return ts.length >= 16 ? ts.slice(5, 16).replace("T", " ") : ts; }
</script>

<template>
  <div class="min-h-[70vh] bg-background text-foreground">
    <div class="mx-auto max-w-5xl p-3 md:p-6" style="padding-bottom: calc(2rem + env(safe-area-inset-bottom))">
      <header class="mb-3 flex items-center gap-2">
        <h1 class="text-lg font-semibold tracking-tight md:text-xl">出库记录</h1>
        <span class="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary tabular-nums">{{ matched.length }} 单</span>
        <div class="ml-auto flex items-center gap-2">
          <NuxtLink to="/outbound" class="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90">去出库</NuxtLink>
          <NuxtLink to="/ledger" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">台账</NuxtLink>
        </div>
      </header>

      <!-- 筛选 -->
      <section class="mb-3 rounded-xl border bg-card p-2 shadow-sm">
        <div class="flex flex-wrap items-center gap-2">
          <input v-model="q" :class="[inputCls, 'h-10 min-w-0 flex-1 text-base']" placeholder="搜索：商品名 / 备注 / 单号" />
          <select v-model="fReason" :class="[inputCls, 'h-10 text-base']"><option value="">全部去向</option><option v-for="r in reasons" :key="r" :value="r">{{ r }}</option></select>
          <label class="inline-flex items-center gap-1 text-xs text-muted-foreground"><input v-model="showRolled" type="checkbox" class="accent-primary" /> 显示已回滚</label>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <label>从 <input v-model="dFrom" type="date" :class="[inputCls, 'h-9']" /></label>
          <label>到 <input v-model="dTo" type="date" :class="[inputCls, 'h-9']" /></label>
          <button class="rounded-lg border px-2.5 py-1.5 transition hover:bg-muted" @click="exportCSV">导出CSV</button>
          <button class="rounded-lg border px-2.5 py-1.5 transition hover:bg-muted" @click="copyText">复制文本</button>
        </div>
        <div class="mt-1.5 text-xs text-muted-foreground">共 {{ matched.length }} 单 · 出库 {{ totalOut }} 件（不含已回滚）</div>
      </section>

      <div v-if="loading" class="space-y-2">
        <div v-for="i in 5" :key="i" class="h-16 animate-pulse rounded-xl border bg-muted/40"></div>
      </div>
      <div v-else-if="err" class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-destructive">{{ err }}</div>
      <div v-else class="space-y-2">
        <div v-for="t in matched" :key="t.id" class="rounded-xl border bg-card px-3 py-2.5 text-sm" :class="t.rolledBack ? 'opacity-50' : ''">
          <div class="flex flex-wrap items-center gap-2">
            <span class="font-medium tabular-nums">{{ dt(t.ts) }}</span>
            <span v-if="t.reason" class="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{{ t.reason }}</span>
            <span class="text-xs text-muted-foreground">{{ t.items.length }} 款 · {{ t.items.reduce((a, it) => a + it.count, 0) }} 件</span>
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
        <div v-if="!matched.length" class="py-10 text-center text-sm text-muted-foreground">没有匹配的出库单</div>
      </div>

      <p v-if="msg" class="mt-3 text-center text-xs text-muted-foreground">{{ msg }}</p>
    </div>
  </div>
</template>
