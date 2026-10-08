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
  import MdiHistory from "~icons/mdi/history";
  import MdiRefresh from "~icons/mdi/refresh";

  definePageMeta({ middleware: ["auth"] });
  useHead({ title: "Groza | 待办中心" });

  type Item = Record<string, any>;
  const loading = ref(true);
  const err = ref("");
  const items = ref<Item[]>([]);
  const required = ref<string[]>([]);
  const trashCount = ref(0);
  const recent = ref<Array<Record<string, any>>>([]);

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
      const [agg, cfg, trash, audit] = await Promise.all([
        $fetch<Record<string, any>>("/api/v1/ledger"),
        $fetch<Record<string, any>>("/api/v1/gx/config").catch(() => ({ attributes: [] })),
        $fetch<Record<string, any>>("/api/v1/trash2").catch(() => ({ entries: {} })),
        $fetch<Array<Record<string, any>>>("/api/v1/audit", { params: { limit: 12 } }).catch(() => []),
      ]);
      items.value = agg.items || [];
      required.value = (cfg.attributes || []).filter((a: Record<string, any>) => a.required).map((a: Record<string, any>) => a.name);
      trashCount.value = Object.keys(trash.entries || {}).length;
      recent.value = Array.isArray(audit) ? audit : ((audit as any).entries || []);
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
      { key: "noImg", label: "缺图片", icon: MdiImageOffOutline, filter: "noImg", count: list.filter(it => !it.thumb).length },
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

  const lowStock = computed(() => items.value
    .map(it => { const s = num(fv(it, "安全库存")) || 0; const q = Number(it.quantity || 0); return { id: it.id, name: it.name, q, s, suggest: Math.max(1, s - q) }; })
    .filter(x => x.s > 0 && x.q <= x.s)
    .sort((a, b) => (a.q - a.s) - (b.q - b.s)));

  function copyRestock() {
    const lines = [`补货清单 ${new Date().toLocaleDateString()}`, ...lowStock.value.map(x => `· ${x.name}  当前 ${x.q}/安全 ${x.s}  建议补 ${x.suggest}`)];
    const txt = lines.join("\n");
    navigator.clipboard?.writeText(txt).then(() => alert("已复制补货清单")).catch(() => window.prompt("复制：", txt));
  }

  function go(q: { filter: string; q?: string }) {
    const params: Record<string, string> = {};
    if (q.filter) params.data = q.filter;
    if (q.q) params.q = q.q;
    navigateTo({ path: "/ledger", query: params });
  }
  function actLabel(a: string): string {
    const m: Record<string, string> = { "intake.create": "入库", "intake.rollback": "回滚入库", "outbound.create": "出库", "outbound.rollback": "回滚出库", "ledger.field_patch": "修改字段", "trash2.mark": "标记删除", "trash2.purge": "彻底删除", "gx.bulk_apply": "批量修改" };
    return m[a] || a;
  }
  function dt(ts: string): string { return String(ts || "").slice(5, 16).replace("T", " "); }
</script>

<template>
  <div class="min-h-[70vh] bg-background text-foreground">
    <div class="mx-auto max-w-5xl p-4 md:p-8" style="padding-bottom: calc(2rem + env(safe-area-inset-bottom))">
      <header class="mb-4 flex flex-wrap items-center gap-2">
        <h1 class="text-lg font-semibold tracking-tight md:text-xl">待办</h1>
        <span class="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary tabular-nums">共 {{ total }} 项</span>
        <div class="ml-auto flex flex-wrap items-center gap-2">
          <button class="inline-flex items-center gap-1 rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted active:scale-95" @click="load"><MdiRefresh class="h-4 w-4" /> 刷新</button>
          <NuxtLink to="/ledger" class="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90">台账</NuxtLink>
        </div>
      </header>

      <div v-if="loading" class="grid grid-cols-2 gap-3 md:grid-cols-3">
        <div v-for="i in 6" :key="i" class="h-16 animate-pulse rounded-xl border bg-muted/40"></div>
      </div>
      <div v-else-if="err" class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-destructive">{{ err }}</div>
      <template v-else>
        <section class="grid grid-cols-2 gap-3 md:grid-cols-3">
          <button
            v-for="q in queues"
            :key="q.key"
            class="flex flex-col gap-1 rounded-2xl border bg-card p-4 text-left shadow-sm transition hover:border-primary/40 active:scale-[0.98]"
            @click="go(q)"
          >
            <component :is="q.icon" class="h-6 w-6" :class="q.count ? 'text-amber-600' : 'text-muted-foreground'" />
            <span class="mt-1 text-sm font-medium">{{ q.label }}</span>
            <span class="text-2xl font-semibold tabular-nums" :class="q.count ? 'text-foreground' : 'text-muted-foreground'">{{ q.count }}</span>
          </button>
        </section>
        <p class="mt-2 text-xs text-muted-foreground">点卡片直达台账对应筛选，可批量处理（差异预览→确认）并可撤销。</p>

        <section class="mt-5 rounded-2xl border bg-card p-4 shadow-sm">
          <div class="mb-2 flex items-center gap-2">
            <MdiAlertOutline class="h-5 w-5 text-amber-600" />
            <span class="text-sm font-semibold">补货草稿</span>
            <span class="text-xs text-muted-foreground">低库存 {{ lowStock.length }} 款</span>
            <div class="ml-auto flex items-center gap-2">
              <button class="rounded-lg border bg-background px-2.5 py-1.5 text-xs transition hover:bg-muted active:scale-95" @click="copyRestock">复制清单</button>
              <NuxtLink to="/intake" class="rounded-lg bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground transition hover:bg-primary/90">去入库</NuxtLink>
            </div>
          </div>
          <div v-if="!lowStock.length" class="py-4 text-center text-sm text-muted-foreground">暂无低库存</div>
          <div v-else class="divide-y text-sm">
            <div v-for="x in lowStock" :key="x.id" class="flex items-center gap-2 py-1.5">
              <span class="min-w-0 flex-1 truncate">{{ x.name }}</span>
              <span class="shrink-0 text-xs tabular-nums text-muted-foreground">当前 {{ x.q }} / 安全 {{ x.s }}</span>
              <span class="shrink-0 rounded bg-amber-500/15 px-1.5 py-0.5 text-xs tabular-nums text-amber-600">建议补 {{ x.suggest }}</span>
            </div>
          </div>
        </section>

        <section class="mt-5 rounded-2xl border bg-card p-4 shadow-sm">
          <div class="mb-2 flex items-center gap-2">
            <MdiHistory class="h-5 w-5 text-muted-foreground" />
            <span class="text-sm font-semibold">最近变更</span>
          </div>
          <div v-if="!recent.length" class="py-4 text-center text-sm text-muted-foreground">暂无记录</div>
          <div v-else class="divide-y text-sm">
            <div v-for="(r, i) in recent" :key="i" class="flex items-center gap-2 py-1.5">
              <span class="w-24 shrink-0 text-xs text-muted-foreground tabular-nums">{{ dt(r.ts) }}</span>
              <span class="rounded bg-muted px-1.5 py-0.5 text-xs">{{ actLabel(r.action) }}</span>
              <span class="min-w-0 flex-1 truncate text-muted-foreground">{{ r.name || r.supplier || r.entityId || r.intakeId || r.outboundId || "" }}</span>
            </div>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>
