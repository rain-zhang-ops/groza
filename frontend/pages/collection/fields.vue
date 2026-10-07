<script setup lang="ts">
  import { toast } from "@/components/ui/sonner";
  import { Button } from "@/components/ui/button";
  import MdiPlus from "~icons/mdi/plus";
  import MdiDelete from "~icons/mdi/delete";
  import MdiArrowUp from "~icons/mdi/arrow-up";
  import MdiArrowDown from "~icons/mdi/arrow-down";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({ title: "Groza | 字段设置" });

  const NIL = "00000000-0000-0000-0000-000000000000";
  const TYPES = [
    { v: "text", label: "文本" },
    { v: "number", label: "数字" },
    { v: "boolean", label: "开关" },
  ];

  const templates = ref<Array<{ id: string; name: string }>>([]);
  const tplId = ref("");
  const loading = ref(true);
  const saving = ref(false);
  const err = ref("");

  const form = reactive({
    name: "",
    description: "",
    raw: {} as Record<string, any>,
    fields: [] as Array<Record<string, any>>,
  });

  const inputCls = "rounded-lg border bg-background px-2.5 py-2 text-sm outline-none focus:ring-2 focus:ring-ring/40";

  function toDraft(fields: Array<Record<string, any>>) {
    return (fields || []).map(f => ({
      id: f.id || NIL,
      name: f.name || "",
      type: f.type || "text",
      value: f.type === "text" ? (f.textValue ?? "") : f.type === "boolean" ? !!f.booleanValue : (f.numberValue ?? 0),
      timeValue: f.timeValue,
    }));
  }

  async function loadTemplate(id: string) {
    loading.value = true; err.value = "";
    try {
      const t = await $fetch<Record<string, any>>(`/api/v1/templates/${id}`);
      form.name = t.name || "";
      form.description = t.description || "";
      form.raw = t;
      form.fields = toDraft(t.fields || []);
    } catch (e) { err.value = "加载失败：" + ((e as Error)?.message ?? String(e)); }
    finally { loading.value = false; }
  }
  async function loadAll() {
    loading.value = true;
    try {
      const list = await $fetch<Array<Record<string, any>>>("/api/v1/templates");
      templates.value = (list || []).map(t => ({ id: t.id, name: t.name }));
      if (templates.value.length) {
        tplId.value = templateId.value || templates.value[0].id;
        await loadTemplate(tplId.value);
      }
    } catch (e) { err.value = "加载失败：" + ((e as Error).message ?? String(e)); loading.value = false; }
  }
  const route = useRoute();
  const templateId = computed(() => (route.params.id as string) || "");

  const QUICK: Array<{ name: string; type: string }> = [
    { name: "品牌", type: "text" }, { name: "尺寸", type: "text" }, { name: "规格", type: "text" },
    { name: "颜色", type: "text" }, { name: "材质", type: "text" }, { name: "进价", type: "number" },
    { name: "售价", type: "number" }, { name: "页数", type: "number" }, { name: "纸张", type: "text" },
    { name: "安全库存", type: "number" },
  ];
  const quickPending = computed(() => QUICK.filter(q => !form.fields.some(f => f.name.trim() === q.name)));
  function quickAdd(q: { name: string; type: string }) {
    form.fields.push({ id: NIL, name: q.name, type: q.type, value: q.type === "number" ? 0 : "" });
  }
  function addField() { form.fields.push({ id: NIL, name: "", type: "text", value: "" }); }
  function delField(i: number) { form.fields.splice(i, 1); }
  function moveField(i: number, d: number) {
    const j = i + d; if (j < 0 || j >= form.fields.length) return;
    [form.fields[i], form.fields[j]] = [form.fields[j], form.fields[i]];
    form.fields = [...form.fields];
  }

  async function save() {
    if (!form.name.trim()) { toast.error("模板名不能为空"); return; }
    saving.value = true;
    try {
      const fields = form.fields.filter(f => f.name.trim()).map(f => ({
        id: f.id === NIL ? NIL : f.id,
        type: f.type,
        name: f.name.trim(),
        textValue: f.type === "text" ? String(f.value ?? "") : "",
        numberValue: f.type === "number" ? (Number(f.value) || 0) : 0,
        booleanValue: f.type === "boolean" ? !!f.value : false,
        timeValue: f.timeValue || "0001-01-01T00:00:00Z",
      }));
      const payload = {
        name: form.name.trim(),
        description: form.description,
        notes: form.raw.notes || "",
        defaultQuantity: form.raw.defaultQuantity ?? 1,
        defaultInsured: !!form.raw.defaultInsured,
        defaultName: form.raw.defaultName ?? null,
        defaultDescription: form.raw.defaultDescription ?? null,
        defaultManufacturer: form.raw.defaultManufacturer ?? null,
        defaultModelNumber: form.raw.defaultModelNumber ?? null,
        defaultLifetimeWarranty: !!form.raw.defaultLifetimeWarranty,
        defaultWarrantyDetails: form.raw.defaultWarrantyDetails ?? null,
        defaultLocationId: form.raw.defaultLocation?.id ?? null,
        defaultTagIds: (form.raw.defaultTags || []).map((t: Record<string, any>) => t.id),
        includeWarrantyFields: !!form.raw.includeWarrantyFields,
        includePurchaseFields: !!form.raw.includePurchaseFields,
        includeSoldFields: !!form.raw.includeSoldFields,
        fields,
      };
      await $fetch(`/api/v1/templates/${tplId.value}`, { method: "PUT", body: payload });
      let applied = 0;
      try { const r = await $fetch<Record<string, any>>("/api/v1/ledger/sync-fields", { method: "POST", body: {} }); applied = r?.updated ?? 0; } catch (_e) { /* ignore */ }
      toast.success(`已保存${applied ? "，并应用到 " + applied + " 件物品" : ""}`);
      await loadTemplate(tplId.value);
    } catch (e) { toast.error("保存失败：" + ((e as Error)?.message ?? String(e))); }
    finally { saving.value = false; }
  }

  onMounted(loadAll);
</script>

<template>
  <div class="min-h-[70vh] bg-background text-foreground">
    <div class="mx-auto max-w-3xl p-3 md:p-6" style="padding-bottom: calc(6rem + env(safe-area-inset-bottom))">
      <header class="mb-3 flex items-center gap-2">
        <h1 class="text-lg font-semibold tracking-tight md:text-xl">字段设置</h1>
        <span class="text-xs text-muted-foreground">这些字段会出现在每个物品上（台账可编辑/筛选/导出）</span>
        <div class="ml-auto flex items-center gap-2">
          <NuxtLink to="/ledger" class="rounded-lg border bg-background px-3 py-1.5 text-sm transition hover:bg-muted">台账</NuxtLink>
        </div>
      </header>

      <div v-if="err" class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-destructive">{{ err }}</div>
      <div v-else-if="loading" class="space-y-2">
        <div v-for="i in 5" :key="i" class="h-16 animate-pulse rounded-xl border bg-muted/40"></div>
      </div>

      <template v-else>
        <details class="mb-3 rounded-xl border bg-card p-3 text-sm" open>
          <summary class="cursor-pointer font-medium">说明（点开/收起）</summary>
          <ul class="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
            <li>这些字段会出现在<b>每个物品</b>上，并在「物品台账」中<b>显示为列</b>（可编辑 / 筛选 / 导出）。</li>
            <li>类型：<b>文本</b> 如 品牌/规格；<b>数字</b> 如 进价/页数（可参与货值、排序）；<b>开关</b> 是/否。</li>
            <li>保存后会<b>自动应用到所有物品</b>（只补齐缺失字段与类型，<b>不会删除</b>已有数据）。</li>
            <li>“必填”在 <b>集合 → 选项配置</b> 里设置，台账会标 <span class="text-destructive">*</span> 并做校验。</li>
            <li>列表里的 <b>↑ ↓</b> 调整的是台账<b>列顺序</b>。</li>
          </ul>
        </details>

        <section class="mb-3 rounded-xl border bg-card p-3 shadow-sm">
          <label v-if="templates.length > 1" class="mb-2 block text-xs text-muted-foreground">模板
            <select v-model="tplId" :class="[inputCls, 'mt-1 w-full text-base']" @change="loadTemplate(tplId)">
              <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </label>
          <label class="block text-xs text-muted-foreground">名称
            <input v-model="form.name" :class="[inputCls, 'mt-1 w-full text-base']" />
          </label>
          <label class="mt-2 block text-xs text-muted-foreground">描述
            <input v-model="form.description" :class="[inputCls, 'mt-1 w-full text-base']" placeholder="可选" />
          </label>
        </section>

        <section class="mb-3 rounded-xl border bg-card p-3 shadow-sm">
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm font-medium">字段（{{ form.fields.length }}）</span>
            <Button size="sm" variant="outline" @click="addField"><MdiPlus class="mr-1 size-4" /> 添加字段</Button>
          </div>
          <div v-if="quickPending.length" class="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>常用：</span>
            <button v-for="q in quickPending" :key="q.name" class="rounded-full border px-2 py-0.5 transition hover:bg-muted active:scale-95" @click="quickAdd(q)">＋ {{ q.name }}</button>
          </div>
          <div class="flex flex-col gap-2">
            <div v-for="(f, i) in form.fields" :key="i" class="rounded-xl border p-2">
              <div class="flex items-center gap-2">
                <input v-model="f.name" :class="[inputCls, 'min-w-0 flex-1 text-base']" placeholder="字段名（如 品牌）" />
                <select v-model="f.type" :class="[inputCls, 'h-10 w-24 text-base']">
                  <option v-for="t in TYPES" :key="t.v" :value="t.v">{{ t.label }}</option>
                </select>
              </div>
              <div class="mt-2 flex items-center gap-2">
                <span class="w-16 shrink-0 text-xs text-muted-foreground">默认值</span>
                <input v-if="f.type === 'text'" v-model="f.value" :class="[inputCls, 'h-10 min-w-0 flex-1 text-base']" placeholder="默认值（可选）" />
                <input v-else-if="f.type === 'number'" v-model.number="f.value" type="number" inputmode="decimal" :class="[inputCls, 'h-10 w-28 text-base']" />
                <input v-else-if="f.type === 'boolean'" v-model="f.value" type="checkbox" class="h-5 w-5 accent-primary" />
                <div class="ml-auto flex items-center gap-1">
                  <button class="grid h-9 w-9 place-items-center rounded-lg border text-muted-foreground transition hover:bg-muted active:scale-95 disabled:opacity-40" :disabled="i === 0" title="上移" @click="moveField(i, -1)"><MdiArrowUp class="h-4 w-4" /></button>
                  <button class="grid h-9 w-9 place-items-center rounded-lg border text-muted-foreground transition hover:bg-muted active:scale-95 disabled:opacity-40" :disabled="i === form.fields.length - 1" title="下移" @click="moveField(i, 1)"><MdiArrowDown class="h-4 w-4" /></button>
                  <button class="grid h-9 w-9 place-items-center rounded-lg border border-destructive/40 text-destructive transition hover:bg-destructive/10 active:scale-95" title="删除" @click="delField(i)"><MdiDelete class="h-4 w-4" /></button>
                </div>
              </div>
            </div>
            <div v-if="!form.fields.length" class="rounded-xl border border-dashed p-4 text-center">
              <p class="text-sm text-muted-foreground">还没有字段。点右上「添加字段」，或一键添加常用字段：</p>
              <div class="mt-2 flex flex-wrap justify-center gap-2">
                <button v-for="q in quickPending" :key="q.name" class="rounded-full border px-3 py-1.5 text-sm transition hover:bg-muted active:scale-95" @click="quickAdd(q)">＋ {{ q.name }}</button>
              </div>
            </div>
          </div>
        </section>
      </template>
    </div>

    <!-- 移动端底部保存条 -->
    <div v-if="!loading && !err" class="fixed inset-x-0 bottom-0 z-40 border-t bg-card/95 px-3 py-2 backdrop-blur-md" style="padding-bottom: calc(0.5rem + env(safe-area-inset-bottom))">
      <div class="mx-auto flex max-w-3xl items-center gap-2">
        <span class="text-xs text-muted-foreground">保存后自动应用到所有物品</span>
        <Button class="ml-auto" :loading="saving" @click="save">{{ saving ? "保存中…" : "保存" }}</Button>
      </div>
    </div>
  </div>
</template>
