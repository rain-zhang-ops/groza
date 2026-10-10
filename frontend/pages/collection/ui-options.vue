<script setup lang="ts">
  const $fetch = useNuxtApp().$gxFetch as typeof globalThis.$fetch;
  import { toast } from "@/components/ui/sonner";
  import MdiClose from "~icons/mdi/close";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({ title: "Groza | 选项" });

  const DIMS = [
    { key: "sizes", label: "尺寸", ph: "A4" },
    { key: "specs", label: "规格", ph: "横线" },
    { key: "colors", label: "颜色", ph: "黑色" },
    { key: "materials", label: "材质", ph: "纸" },
    { key: "required", label: "必填字段", ph: "品牌", hint: "填字段名；台账将标注 * 并做必填校验" },
  ];

  const loading = ref(true);
  const saving = ref(false);
  const loadedOk = ref(false);
  const loadErr = ref("");
  const form = reactive<Record<string, string[]>>({ sizes: [], specs: [], colors: [], materials: [], required: [] });
  const drafts = reactive<Record<string, string>>({ sizes: "", specs: "", colors: "", materials: "", required: "" });
  const lastSaved = ref("");
  const dirty = computed(() => lastSaved.value !== "" && JSON.stringify(form) !== lastSaved.value);

  function commit(key: string) {
    const parts = (drafts[key] || "").split(/[\n,，、/]/).map(s => s.trim()).filter(Boolean);
    if (!parts.length) { drafts[key] = ""; return; }
    for (const p of parts) if (!form[key].includes(p)) form[key].push(p);
    drafts[key] = "";
  }
  function removeAt(key: string, i: number) { form[key].splice(i, 1); }

  async function load() {
    loading.value = true;
    loadErr.value = "";
    try {
      const d = await $fetch<Record<string, string[]>>("/api/v1/ui-options");
      for (const k of Object.keys(form)) form[k] = Array.isArray(d[k]) ? [...d[k]] : [];
      loadedOk.value = true;
      lastSaved.value = JSON.stringify(form);
    } catch (e) {
      loadErr.value = "加载失败：" + ((e as Error)?.message ?? String(e));
    } finally {
      loading.value = false;
    }
  }

  async function save() {
    if (!loadedOk.value || saving.value) return;
    for (const k of Object.keys(drafts)) commit(k);
    saving.value = true;
    try {
      await $fetch("/api/v1/ui-options", { method: "PUT", body: JSON.parse(JSON.stringify(form)) });
      lastSaved.value = JSON.stringify(form);
      toast.success("已保存");
    } catch (e) {
      toast.error("保存失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      saving.value = false;
    }
  }

  onMounted(load);
</script>

<template>
  <div class="space-y-3">
    <Teleport to="#collection-header-actions" defer>
      <button :class="[btnPrimary, 'active:scale-95']" :disabled="saving || !loadedOk" @click="save">{{ saving ? "保存中…" : "保存" }}<span v-if="dirty" class="ml-1 inline-block size-1.5 rounded-full bg-amber-400 align-middle" title="有未保存修改"></span></button>
    </Teleport>
    <p class="px-1 text-xs text-muted-foreground">全局选项：输入后回车添加，点 × 删除；留空的分区回退为按物品自动汇总。</p>

    <div v-if="loading" class="space-y-3">
      <div v-for="i in 5" :key="i" :class="skeletonCls"></div>
    </div>
    <div v-else-if="loadErr" :class="[errorCls, 'flex items-center justify-between gap-3']">
      <span class="text-sm">{{ loadErr }}</span>
      <button :class="[btnGhost, 'active:scale-95']" @click="load">重试</button>
    </div>
    <template v-else>
      <section v-for="d in DIMS" :key="d.key" class="rounded-xl border bg-card p-3.5">
        <div class="mb-2 flex items-baseline gap-2">
          <span class="text-sm font-semibold">{{ d.label }}</span>
          <span class="text-xs tabular-nums text-muted-foreground">{{ form[d.key].length }}</span>
        </div>
        <div class="flex flex-wrap items-center gap-1.5">
          <span v-for="(o, i) in form[d.key]" :key="o + i" class="flex items-center gap-0.5 rounded-full border bg-background py-1 pl-3 pr-1 text-sm">
            {{ o }}
            <button type="button" class="grid h-6 w-6 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground active:scale-90" :title="`删除 ${o}`" @click="removeAt(d.key, i)"><MdiClose class="size-3.5" /></button>
          </span>
          <input
            v-model="drafts[d.key]"
            class="h-8 min-w-24 flex-1 bg-transparent text-base outline-none"
            :placeholder="form[d.key].length ? '回车添加' : `如 ${d.ph}（回车添加）`"
            @keydown.enter.prevent="commit(d.key)"
            @blur="commit(d.key)"
          />
        </div>
        <p v-if="d.hint" class="mt-1.5 text-xs text-muted-foreground">{{ d.hint }}</p>
      </section>
    </template>
  </div>
</template>
