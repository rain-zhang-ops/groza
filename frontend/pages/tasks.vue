<script setup lang="ts">
  const $fetch = useNuxtApp().$gxFetch as typeof globalThis.$fetch;
  import MdiImageOffOutline from "~icons/mdi/image-off-outline";
  import MdiCurrencyUsdOff from "~icons/mdi/currency-usd-off";
  import MdiMapMarkerOff from "~icons/mdi/map-marker-off";
  import MdiShieldAlertOutline from "~icons/mdi/shield-alert-outline";
  import MdiAlertOutline from "~icons/mdi/alert-outline";
  import MdiContentDuplicate from "~icons/mdi/content-duplicate";
  import MdiPackageVariantClosedRemove from "~icons/mdi/package-variant-closed-remove";
  import MdiTrashCanOutline from "~icons/mdi/trash-can-outline";
  import MdiRefresh from "~icons/mdi/refresh";

  definePageMeta({ middleware: ["auth"] });
  useHead({ title: "Groza | 待办" });

  type Item = Record<string, any>;
  const loading = ref(true);
  const err = ref("");
  const items = ref<Item[]>([]);
  const required = ref<string[]>([]);
  const trashCount = ref(0);

  function fv(it: Item, name: string): any {
    const f = (it.fields || []).find((x: Record<string, any>) => x.name === name);
    if (!f) return undefined;
    if (f.type === "number") return f.numberValue;
    if (f.type === "boolean") return f.booleanValue;
    return f.textValue;
  }
  function num(v: any): number | null { const n = Number(v); return Number.isFinite(n) && v !== "" && v !== null && v !== undefined ? n : null; }

  async function load() {
    loading.value = true; err.value = "";
    try {
      const [agg, cfg, trash] = await Promise.all([
        $fetch<Record<string, any>>("/api/v1/ledger"),
        $fetch<Record<string, any>>("/api/v1/gx/config").catch(() => ({ attributes: [] })),
        $fetch<Record<string, any>>("/api/v1/trash2").catch(() => ({ entries: {} })),
      ]);
      items.value = agg.items || [];
      required.value = (cfg.attributes || []).filter((a: Record<string, any>) => a.required).map((a: Record<string, any>) => a.name);
      trashCount.value = Object.keys(trash.entries || {}).length;
    } catch (e) { err.value = "加载失败：" + ((e as Error)?.message ?? String(e)); }
    finally { loading.value = false; }
  }
  onMounted(load);

  const dupNames = computed(() => {
    const m: Record<string, number> = {};
    for (const it of items.value) { const n = String(it.name || "").trim(); if (n) m[n] = (m[n] || 0) + 1; }
    return Object.entries(m).filter(([, c]) => c > 1).sort((a, b) => b[1] - a[1]);
  });

  const queues = computed(() => {
    const list = items.value;
    return [
      { key: "noImg", label: "缺图", icon: MdiImageOffOutline, filter: "noImg", count: list.filter(it => !it.thumb).length },
      { key: "noPrice", label: "缺价格", icon: MdiCurrencyUsdOff, filter: "noPrice", count: list.filter(it => num(fv(it, "进价")) === null && num(fv(it, "售价")) === null).length },
      { key: "noSerial", label: "缺库位", icon: MdiMapMarkerOff, filter: "noSerial", count: list.filter(it => !it.serial).length },
      { key: "noSafety", label: "缺安全库存", icon: MdiShieldAlertOutline, filter: "noSafety", count: list.filter(it => (num(fv(it, "安全库存")) || 0) <= 0).length },
      { key: "low", label: "低库存（待补货）", icon: MdiAlertOutline, filter: "low", count: list.filter(it => { const s = num(fv(it, "安全库存")) || 0; return s > 0 && Number(it.quantity || 0) <= s; }).length },
      { key: "required", label: "缺必填字段", icon: MdiShieldAlertOutline, filter: "required", count: required.value.length ? list.filter(it => required.value.some(nm => { const v = fv(it, nm); return v === "" || v === null || v === undefined; })).length : 0 },
      { key: "dup", label: "重复名称", icon: MdiContentDuplicate, filter: "", count: dupNames.value.reduce((a, [, c]) => a + c, 0), q: dupNames.value[0]?.[0] || "" },
      { key: "soldout", label: "售罄", icon: MdiPackageVariantClosedRemove, filter: "soldout", count: list.filter(it => Number(it.quantity || 0) <= 0).length },
      { key: "trashed", label: "待删除", icon: MdiTrashCanOutline, filter: "trashed", count: trashCount.value },
    ];
  });
  const total = computed(() => queues.value.reduce((a, q) => a + q.count, 0));

  const hideEmpty = ref(true);
  try { hideEmpty.value = localStorage.getItem("groza.tasks.hideEmpty") !== "0"; } catch (_e) { /* ignore */ }
  function toggleHideEmpty() {
    hideEmpty.value = !hideEmpty.value;
    try { localStorage.setItem("groza.tasks.hideEmpty", hideEmpty.value ? "1" : "0"); } catch (_e) { /* ignore */ }
  }
  const visibleQueues = computed(() => (hideEmpty.value ? queues.value.filter(q => q.count > 0) : queues.value));
  const hiddenCount = computed(() => queues.value.length - visibleQueues.value.length);

  function go(q: { filter: string; q?: string }) {
    const params: Record<string, string> = {};
    if (q.filter) params.data = q.filter;
    if (q.q) params.q = q.q;
    navigateTo({ path: "/ledger", query: params });
  }
</script>

<template>
  <div class="min-h-[70vh] bg-background text-foreground">
    <div class="mx-auto max-w-5xl p-4 md:p-8" style="padding-bottom: calc(2rem + env(safe-area-inset-bottom))">
      <header class="mb-6 flex flex-wrap items-center gap-2">
        <h1 class="font-display text-xl font-medium tracking-tight md:text-2xl">待办</h1>
        <span :class="badgeCls">共 {{ total }} 项</span>
        <div class="ml-auto flex flex-wrap items-center gap-2">
          <button
            role="switch"
            :aria-checked="hideEmpty"
            :class="btnGhost"
            @click="toggleHideEmpty"
          >
            <span class="relative h-4 w-7 shrink-0 rounded-full transition-colors" :class="hideEmpty ? 'bg-primary' : 'bg-muted-foreground/30'">
              <span class="absolute left-0.5 top-0.5 h-3 w-3 rounded-full bg-primary-foreground transition-transform" :class="hideEmpty ? 'translate-x-3' : ''"></span>
            </span>
            隐藏 0 项
          </button>
          <button :class="btnGhost" @click="load"><MdiRefresh class="h-4 w-4" /> 刷新</button>
          <NuxtLink to="/ledger" :class="btnPrimary">台账</NuxtLink>
        </div>
      </header>

      <div v-if="loading" class="grid grid-cols-2 gap-3 md:grid-cols-3">
        <div v-for="i in 6" :key="i" :class="skeletonCls"></div>
      </div>
      <div v-else-if="err" :class="errorCls">{{ err }}</div>
      <template v-else>
        <div v-if="!visibleQueues.length" :class="emptyCls">没有待办事项，库存数据很健康</div>
        <section v-else class="grid grid-cols-2 gap-3 md:grid-cols-3">
          <button
            v-for="q in visibleQueues"
            :key="q.key"
            class="flex flex-col gap-1 rounded-2xl border bg-card p-4 text-left transition hover:border-foreground/25 active:scale-[0.98]"
            @click="go(q)"
          >
            <component :is="q.icon" class="h-6 w-6" :class="q.count ? 'text-amber-600' : 'text-muted-foreground'" />
            <span class="mt-1 text-sm font-medium">{{ q.label }}</span>
            <span class="text-2xl font-semibold tabular-nums" :class="q.count ? 'text-foreground' : 'text-muted-foreground'">{{ q.count }}</span>
          </button>
        </section>
        <p class="mt-2 text-xs text-muted-foreground">
          点卡片直达台账对应筛选，可批量处理（差异预览→确认）并可撤销。
          <template v-if="hiddenCount > 0">已隐藏 {{ hiddenCount }} 个无待办分类。</template>
        </p>
      </template>
    </div>
  </div>
</template>
