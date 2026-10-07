<script setup lang="ts">
  import { toast } from "@/components/ui/sonner";
  import { Button } from "@/components/ui/button";
  import MdiPlus from "~icons/mdi/plus";
  import MdiDelete from "~icons/mdi/delete";
  import MdiArrowUp from "~icons/mdi/arrow-up";
  import MdiArrowDown from "~icons/mdi/arrow-down";
  import MdiRestore from "~icons/mdi/restore";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({ title: "Groza | 库存配置" });

  const TYPES = [
    { v: "text", label: "文本" },
    { v: "number", label: "数字" },
    { v: "boolean", label: "开关" },
    { v: "date", label: "日期" },
    { v: "select", label: "单选" },
    { v: "multiselect", label: "多选" },
  ];

  const DEFAULT = {
    version: 1,
    location: { dim: "品牌", levels: ["品牌"], shelf: { enabled: true, name: "库位", pattern: "^[A-Z]-\\d{1,3}$", unique: false } },
    attributes: [
      { key: "brand", name: "品牌", type: "text", required: true, show_column: true, filterable: true, sortable: false, unit: null, options: [], options_source: "locations" },
      { key: "size", name: "尺寸", type: "select", required: true, show_column: true, filterable: true, sortable: false, unit: null, options: ["A4", "A5", "A5S", "B5"] },
      { key: "spec", name: "规格", type: "select", required: false, show_column: true, filterable: true, sortable: false, unit: null, options: ["横线", "网格", "方格", "点阵"] },
      { key: "color", name: "颜色", type: "select", required: false, show_column: true, filterable: true, sortable: false, unit: null, options: ["黑", "白", "蓝", "粉"] },
      { key: "material", name: "材质", type: "select", required: false, show_column: true, filterable: true, sortable: false, unit: null, options: ["纸", "塑料", "金属", "布", "PU"] },
      { key: "purchase", name: "进价", type: "number", required: true, show_column: true, filterable: true, sortable: true, unit: "元", options: [] },
      { key: "sell", name: "售价", type: "number", required: false, show_column: true, filterable: true, sortable: true, unit: "元", options: [] },
      { key: "pages", name: "页数", type: "number", required: false, show_column: true, filterable: false, sortable: false, unit: null, options: [] },
      { key: "paper", name: "纸张", type: "text", required: false, show_column: true, filterable: true, sortable: false, unit: null, options: [] },
      { key: "safety", name: "安全库存", type: "number", required: false, show_column: true, filterable: false, sortable: false, unit: null, options: [] },
    ],
    media: { cover: "front", maxPerItem: 8, slots: [
      { key: "front", name: "正面", required: true, multiple: false },
      { key: "back", name: "反面", required: false, multiple: false },
      { key: "detail", name: "细节", required: false, multiple: true },
      { key: "package", name: "包装", required: false, multiple: false },
    ] },
    organization: { tagGroup: { name: "品类", options: [] }, series: { enabled: true, deriveFrom: ["name"], stripParentheses: true }, groupDims: ["品牌", "尺寸", "规格", "系列"] },
    permissions: { editorCanIntake: true, editorCanOutbound: true, editorCanAdjust: true },
  };

  const cfg = reactive<any>(JSON.parse(JSON.stringify(DEFAULT)));
  const loading = ref(true);
  const saving = ref(false);
  const err = ref("");
  const isOwner = ref(true);
  const inputCls = "rounded-lg border bg-background px-2.5 py-2 text-sm outline-none focus:ring-2 focus:ring-ring/40";

  async function loadMe() {
    try { const m = await $fetch<Record<string, any>>("/api/v1/gx/me"); isOwner.value = !!m.isOwner; } catch (_e) { /* ignore */ }
  }
  const history = ref<Array<{ version: number; reason: string; createdAt: string }>>([]);
  const restoring = ref(0);
  async function loadHistory() {
    try { const h = await $fetch<Record<string, any>>("/api/v1/gx/config/history"); history.value = h.history || []; } catch (_e) { /* ignore */ }
  }
  async function restoreVersion(v: number) {
    if (!isOwner.value) { toast.error("仅管理员可回滚配置"); return; }
    if (!window.confirm(`恢复到配置 v${v}？（将生成新版本，可再次回滚）`)) return;
    restoring.value = v;
    try {
      const r = await $fetch<Record<string, any>>("/api/v1/gx/config/restore", { method: "POST", body: { version: v } });
      toast.success("已恢复（新版本 " + (r?.version ?? "?") + "）");
      await load(); await loadHistory();
    } catch (e) { toast.error("恢复失败：" + ((e as Error)?.message ?? String(e))); }
    finally { restoring.value = 0; }
  }

  function genKey() { return "k" + Date.now().toString(36) + Math.floor(Math.random() * 100); }

  async function load() {
    loading.value = true; err.value = "";
    try {
      const c = await $fetch<any>("/api/v1/gx/config");
      // 深合并默认，保证结构完整
      Object.assign(cfg, JSON.parse(JSON.stringify(DEFAULT)), c);
      cfg.attributes = (cfg.attributes || []).map((a: any) => ({ options: [], ...a }));
      cfg.media = { ...JSON.parse(JSON.stringify(DEFAULT.media)), ...(cfg.media || {}) };
      cfg.organization = { ...JSON.parse(JSON.stringify(DEFAULT.organization)), ...(cfg.organization || {}) };
      cfg.location = { ...JSON.parse(JSON.stringify(DEFAULT.location)), ...(cfg.location || {}), shelf: { ...DEFAULT.location.shelf, ...((cfg.location || {}).shelf || {}) } };
    } catch (e) { err.value = "加载失败：" + ((e as Error)?.message ?? String(e)); }
    finally { loading.value = false; }
  }

  function addAttr() { cfg.attributes.push({ key: genKey(), name: "", type: "text", required: false, show_column: true, filterable: true, sortable: false, unit: null, options: [] }); }
  function delAttr(i: number) { cfg.attributes.splice(i, 1); }
  function moveAttr(i: number, d: number) {
    const j = i + d; if (j < 0 || j >= cfg.attributes.length) return;
    [cfg.attributes[i], cfg.attributes[j]] = [cfg.attributes[j], cfg.attributes[i]];
    cfg.attributes = [...cfg.attributes];
  }
  function addSlot() { cfg.media.slots.push({ key: genKey(), name: "", required: false, multiple: false }); }
  function delSlot(i: number) { cfg.media.slots.splice(i, 1); }
  function moveSlot(i: number, d: number) {
    const j = i + d; if (j < 0 || j >= cfg.media.slots.length) return;
    [cfg.media.slots[i], cfg.media.slots[j]] = [cfg.media.slots[j], cfg.media.slots[i]];
  }
  function addTag() { if (cfg.organization.tagGroup.options.length < 60) cfg.organization.tagGroup.options.push(""); }
  function delTag(i: number) { cfg.organization.tagGroup.options.splice(i, 1); }

  function resetDefault() {
    Object.assign(cfg, JSON.parse(JSON.stringify(DEFAULT)));
    toast.success("已载入默认模板（未保存，请点右上保存生效）");
  }

  async function save() {
    saving.value = true;
    try {
      const clean = JSON.parse(JSON.stringify(cfg));
      clean.attributes = clean.attributes
        .filter((a: any) => (a.name || "").trim())
        .map((a: any) => ({
          ...a,
          name: a.name.trim(),
          key: (a.key || "").trim() || genKey(),
          options: Array.isArray(a.options) ? a.options.filter((o: any) => String(o).trim() !== "") : [],
        }));
      clean.media.slots = clean.media.slots.filter((s: any) => (s.name || "").trim()).map((s: any) => ({ ...s, name: s.name.trim(), key: (s.key || "").trim() || genKey() }));
      clean.organization.tagGroup.options = clean.organization.tagGroup.options.map((t: string) => String(t).trim()).filter(Boolean);
      const r = await $fetch<any>("/api/v1/gx/config", { method: "PUT", body: clean });
      Object.assign(cfg, clean); cfg.version = r?.version ?? cfg.version;
      toast.success("配置已保存（版本 " + (r?.version ?? "?") + "）");
    } catch (e) { toast.error("保存失败：" + ((e as Error)?.message ?? String(e))); }
    finally { saving.value = false; }
  }

  onMounted(() => { void loadMe(); void loadHistory(); void load(); });
</script>

<template>
  <div class="space-y-4">
    <Teleport to="#collection-header-actions" defer>
      <Button size="sm" variant="outline" :disabled="saving || !isOwner" @click="resetDefault"><MdiRestore class="mr-1 size-4" /> 默认</Button>
      <Button size="sm" :loading="saving" :disabled="!isOwner" @click="save">{{ saving ? "保存中…" : "保存" }}</Button>
    </Teleport>

    <div v-if="!isOwner" class="rounded-md border border-amber-400/40 bg-amber-500/10 p-3 text-sm text-amber-700">仅管理员（owner）可修改库存配置。</div>

    <div v-if="err" class="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-destructive">{{ err }}</div>
    <div v-else-if="loading" class="space-y-2">
      <div v-for="i in 5" :key="i" class="h-16 animate-pulse rounded-md border bg-muted/40"></div>
    </div>
    <template v-else>
      <details class="rounded-md border bg-card p-4 text-sm" open>
        <summary class="cursor-pointer font-medium">说明（点开/收起）</summary>
        <ul class="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
          <li>这里配置库存的<b>四维信息模型</b>：属性 / 位置 / 媒体 / 组织。台账与 AI 会按此渲染。</li>
          <li><b>属性</b>：物品的字段，可自定义 名称 / 类型 / 必填 / 列 / 筛选 / 单位 / 选项。<b>键</b>是稳定标识，建成后别改。</li>
          <li><b>位置</b>：分类维度名（如 品牌）与库位规则（可重复，不做唯一约束）。</li>
          <li><b>媒体</b>：图片槽位（正面/反面/细节/包装），封面槽用于列表缩略图。</li>
          <li><b>组织</b>：品类标签体系、系列派生规则、分组维度。</li>
        </ul>
      </details>

      <!-- 属性 -->
      <section class="space-y-3 rounded-md border bg-card p-4">
        <div class="flex items-center justify-between">
          <span class="text-sm font-semibold">属性（{{ cfg.attributes.length }}）</span>
          <Button size="sm" variant="outline" @click="addAttr"><MdiPlus class="mr-1 size-4" /> 添加属性</Button>
        </div>
        <div class="flex flex-col gap-3">
          <div v-for="(a, i) in cfg.attributes" :key="i" class="rounded-lg border p-3">
            <div class="flex items-center gap-2">
              <input v-model="a.name" :class="[inputCls, 'min-w-0 flex-1 text-base']" placeholder="名称（如 品牌）" />
              <select v-model="a.type" :class="[inputCls, 'h-10 w-24 text-base']">
                <option v-for="t in TYPES" :key="t.v" :value="t.v">{{ t.label }}</option>
              </select>
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <label class="flex items-center gap-1.5"><input v-model="a.required" type="checkbox" class="size-4 accent-primary" /> 必填</label>
              <label class="flex items-center gap-1.5"><input v-model="a.show_column" type="checkbox" class="size-4 accent-primary" /> 显示列</label>
              <label class="flex items-center gap-1.5"><input v-model="a.filterable" type="checkbox" class="size-4 accent-primary" /> 可筛选</label>
              <label class="flex items-center gap-1.5"><input v-model="a.sortable" type="checkbox" class="size-4 accent-primary" /> 可排序</label>
              <label class="flex items-center gap-1.5 text-muted-foreground">单位 <input v-model="a.unit" :class="[inputCls, 'h-9 w-16 text-base']" placeholder="元" /></label>
              <div class="ml-auto flex items-center gap-1">
                <button class="grid h-9 w-9 place-items-center rounded-lg border text-muted-foreground transition hover:bg-muted active:scale-95 disabled:opacity-40" :disabled="i === 0" title="上移" @click="moveAttr(i, -1)"><MdiArrowUp class="h-4 w-4" /></button>
                <button class="grid h-9 w-9 place-items-center rounded-lg border text-muted-foreground transition hover:bg-muted active:scale-95 disabled:opacity-40" :disabled="i === cfg.attributes.length - 1" title="下移" @click="moveAttr(i, 1)"><MdiArrowDown class="h-4 w-4" /></button>
                <button class="grid h-9 w-9 place-items-center rounded-lg border border-destructive/40 text-destructive transition hover:bg-destructive/10 active:scale-95" title="删除" @click="delAttr(i)"><MdiDelete class="h-4 w-4" /></button>
              </div>
            </div>
            <div v-if="a.type === 'select' || a.type === 'multiselect'" class="mt-2 flex items-center gap-2">
              <span class="shrink-0 text-xs text-muted-foreground">选项</span>
              <input :value="(a.options || []).join(' / ')" :class="[inputCls, 'h-10 min-w-0 flex-1 text-base']" placeholder="用 / 分隔，如 A4 / A5 / B5" @input="a.options = ($event.target as HTMLInputElement).value.split('/').map(s => s.trim())" />
            </div>
            <div class="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <span>键</span>
              <input v-model="a.key" :class="[inputCls, 'h-8 w-40 font-mono text-xs']" />
            </div>
          </div>
          <div v-if="!cfg.attributes.length" class="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">还没有属性，点「添加属性」。</div>
        </div>
      </section>

      <!-- 位置 -->
      <section class="space-y-3 rounded-md border bg-card p-4">
        <span class="text-sm font-semibold">位置</span>
        <label class="block text-sm">分类维度名
          <input v-model="cfg.location.dim" :class="[inputCls, 'mt-1 w-full text-base']" placeholder="品牌" />
        </label>
        <label class="flex items-center gap-2 text-sm"><input v-model="cfg.location.shelf.enabled" type="checkbox" class="size-4 accent-primary" /> 启用库位</label>
        <div v-if="cfg.location.shelf.enabled" class="grid gap-3 sm:grid-cols-2">
          <label class="block text-sm">库位名
            <input v-model="cfg.location.shelf.name" :class="[inputCls, 'mt-1 w-full text-base']" placeholder="库位" />
          </label>
          <label class="block text-sm">格式（正则，可选）
            <input v-model="cfg.location.shelf.pattern" :class="[inputCls, 'mt-1 w-full font-mono text-xs']" placeholder="^[A-Z]-\\d{1,3}$" />
          </label>
        </div>
        <p class="text-xs text-muted-foreground">库位可重复（同一货架位可放多款）；唯一性只对资产号/二维码。</p>
      </section>

      <!-- 媒体 -->
      <section class="space-y-3 rounded-md border bg-card p-4">
        <div class="flex items-center justify-between">
          <span class="text-sm font-semibold">媒体槽位（{{ cfg.media.slots.length }}）</span>
          <Button size="sm" variant="outline" @click="addSlot"><MdiPlus class="mr-1 size-4" /> 添加槽位</Button>
        </div>
        <div class="flex flex-col gap-2">
          <div v-for="(s, i) in cfg.media.slots" :key="i" class="flex flex-wrap items-center gap-2 rounded-lg border p-3">
            <input v-model="s.name" :class="[inputCls, 'h-10 min-w-0 flex-1 text-base']" placeholder="槽位名（如 正面）" />
            <label class="flex items-center gap-1.5 text-sm"><input v-model="s.required" type="checkbox" class="size-4 accent-primary" /> 必填</label>
            <label class="flex items-center gap-1.5 text-sm"><input v-model="s.multiple" type="checkbox" class="size-4 accent-primary" /> 多张</label>
            <label class="flex items-center gap-1.5 text-sm text-muted-foreground">封面 <input type="radio" name="cover" :value="s.key" v-model="cfg.media.cover" class="size-4 accent-primary" /></label>
            <div class="ml-auto flex items-center gap-1">
              <button class="grid h-9 w-9 place-items-center rounded-lg border text-muted-foreground transition hover:bg-muted active:scale-95 disabled:opacity-40" :disabled="i === 0" @click="moveSlot(i, -1)"><MdiArrowUp class="h-4 w-4" /></button>
              <button class="grid h-9 w-9 place-items-center rounded-lg border text-muted-foreground transition hover:bg-muted active:scale-95 disabled:opacity-40" :disabled="i === cfg.media.slots.length - 1" @click="moveSlot(i, 1)"><MdiArrowDown class="h-4 w-4" /></button>
              <button class="grid h-9 w-9 place-items-center rounded-lg border border-destructive/40 text-destructive transition hover:bg-destructive/10 active:scale-95" @click="delSlot(i)"><MdiDelete class="h-4 w-4" /></button>
            </div>
          </div>
        </div>
        <label class="block text-sm">每件最多图片数
          <input v-model.number="cfg.media.maxPerItem" type="number" inputmode="numeric" :class="[inputCls, 'mt-1 w-24 text-base']" />
        </label>
      </section>

      <!-- 组织 -->
      <section class="space-y-3 rounded-md border bg-card p-4">
        <span class="text-sm font-semibold">组织</span>
        <label class="block text-sm">标签体系名
          <input v-model="cfg.organization.tagGroup.name" :class="[inputCls, 'mt-1 w-full text-base']" placeholder="品类" />
        </label>
        <div>
          <div class="mb-1 flex items-center justify-between">
            <span class="text-sm">标签选项（{{ cfg.organization.tagGroup.options.length }}）</span>
            <Button size="sm" variant="outline" @click="addTag"><MdiPlus class="mr-1 size-4" /> 添加</Button>
          </div>
          <div class="flex flex-wrap gap-2">
            <div v-for="(t, i) in cfg.organization.tagGroup.options" :key="i" class="flex items-center gap-1 rounded-full border pl-2">
              <input v-model="cfg.organization.tagGroup.options[i]" class="w-20 bg-transparent py-1 text-sm outline-none" placeholder="标签" />
              <button class="grid size-6 place-items-center text-muted-foreground hover:text-destructive" @click="delTag(i)"><MdiDelete class="h-4 w-4" /></button>
            </div>
          </div>
        </div>
        <label class="flex items-center gap-2 text-sm"><input v-model="cfg.organization.series.enabled" type="checkbox" class="size-4 accent-primary" /> 启用系列（按名称去括号派生）</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="cfg.organization.series.stripParentheses" type="checkbox" class="size-4 accent-primary" /> 去除名称中的括号内容</label>
      </section>

      <!-- 权限 -->
      <section class="space-y-2 rounded-md border bg-card p-4">
        <span class="text-sm font-semibold">权限</span>
        <p class="text-xs text-muted-foreground">管理员（owner）始终可用；以下控制普通成员（editor）可执行的操作。</p>
        <label class="flex items-center gap-2 text-sm"><input v-model="cfg.permissions.editorCanIntake" type="checkbox" class="size-4 accent-primary" /> 允许入库</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="cfg.permissions.editorCanOutbound" type="checkbox" class="size-4 accent-primary" /> 允许出库</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="cfg.permissions.editorCanAdjust" type="checkbox" class="size-4 accent-primary" /> 允许盘点</label>
      </section>

      <!-- 版本历史 -->
      <section class="space-y-2 rounded-md border bg-card p-4">
        <div class="flex items-center justify-between">
          <span class="text-sm font-semibold">版本历史（最近 {{ history.length }}）</span>
          <span class="text-xs text-muted-foreground">当前 v{{ cfg.version }}</span>
        </div>
        <p class="text-xs text-muted-foreground">每次保存都会生成一个版本；可恢复到任意历史版本（生成新版本，不丢失后续记录）。</p>
        <div v-if="!history.length" class="py-3 text-center text-sm text-muted-foreground">暂无历史</div>
        <div v-else class="divide-y rounded-lg border text-sm">
          <div v-for="h in history" :key="h.version" class="flex items-center gap-2 p-2">
            <span class="w-12 shrink-0 font-mono text-xs">v{{ h.version }}</span>
            <span class="min-w-0 flex-1 truncate text-muted-foreground">{{ h.reason || "保存" }}</span>
            <span class="shrink-0 text-xs tabular-nums text-muted-foreground">{{ (h.createdAt || "").slice(0, 16).replace("T", " ") }}</span>
            <button class="shrink-0 rounded-lg border px-2 py-1 text-xs transition hover:bg-muted active:scale-95 disabled:opacity-40" :disabled="!isOwner || restoring === h.version || h.version === cfg.version" @click="restoreVersion(h.version)">{{ restoring === h.version ? "恢复中…" : "恢复" }}</button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
