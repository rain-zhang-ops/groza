<script setup lang="ts">
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
  const showRolled = ref(true);
  const rollbackBusy = ref("");

  const inputCls = "rounded-lg border bg-background px-2.5 py-1.5 text-sm outline-none transition focus:ring-2 focus:ring-ring/40";

  function flash(t: string) {
    try { toast(t); } catch (_e) { msg.value = t; }
  }

  async function load() {
    loading.value = true; err.value = "";
    try {
      const ob = await $fetch<Array<Record<string, any>>>("/api/v1/biz/outbounds");
      outbounds.value = (ob || []) as Outbound[];
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
    return outbounds.value.filter(t =>
      (showRolled.value || !t.rolledBack) &&
      (!fReason.value || t.reason === fReason.value) &&
      (!kw || (t.items || []).some(it => String(it.name || "").toLowerCase().includes(kw)) || String(t.note || "").toLowerCase().includes(kw) || t.id.includes(kw)));
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
