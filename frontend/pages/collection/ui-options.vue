<script setup lang="ts">
  const $fetch = useNuxtApp().$gxFetch as typeof globalThis.$fetch;
  import { toast } from "@/components/ui/sonner";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({ title: "Groza | 选项配置" });

  const loading = ref(true);
  const saving = ref(false);
  const loadedOk = ref(false);
  const loadErr = ref("");
  const form = reactive({ sizes: "", specs: "", colors: "", materials: "", required: "" });
  const textareaCls = inputClsLg;

  function toText(arr: string[] | undefined): string {
    return (arr || []).join("\n");
  }
  function toArr(t: string): string[] {
    return t
      .split(/[\n,，、]/)
      .map(s => s.trim())
      .filter(Boolean);
  }

  async function load() {
    loading.value = true;
    loadErr.value = "";
    try {
      const d = await $fetch<Record<string, string[]>>("/api/v1/ui-options");
      form.sizes = toText(d.sizes);
      form.specs = toText(d.specs);
      form.colors = toText(d.colors);
      form.materials = toText(d.materials);
      form.required = toText(d.required);
      loadedOk.value = true;
    } catch (e) {
      loadErr.value = "加载失败：" + ((e as Error)?.message ?? String(e));
    } finally {
      loading.value = false;
    }
  }

  async function save() {
    if (!loadedOk.value || saving.value) return;
    saving.value = true;
    try {
      await $fetch("/api/v1/ui-options", {
        method: "PUT",
        body: {
          sizes: toArr(form.sizes),
          specs: toArr(form.specs),
          colors: toArr(form.colors),
          materials: toArr(form.materials),
          required: toArr(form.required),
        },
      });
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
  <div class="space-y-4">
    <Teleport to="#collection-header-actions" defer>
      <button :class="[btnPrimary, 'active:scale-95']" :disabled="saving || !loadedOk" @click="save">{{ saving ? "保存中…" : "保存" }}</button>
    </Teleport>
    <div class="rounded-xl border bg-card p-4">
      <p class="text-sm text-muted-foreground">配置全局选项（每行一个或用逗号分隔）；留空回退为按物品自动汇总。</p>
    </div>

    <div v-if="loading" class="space-y-3">
      <div v-for="i in 5" :key="i" :class="skeletonCls"></div>
    </div>
    <div v-else-if="loadErr" :class="[errorCls, 'flex items-center justify-between gap-3']">
      <span class="text-sm">{{ loadErr }}</span>
      <button :class="[btnGhost, 'active:scale-95']" @click="load">重试</button>
    </div>
    <div v-else class="grid gap-4 rounded-xl border bg-card p-4 md:grid-cols-2">
      <label class="block text-sm font-medium">
        尺寸
        <textarea v-model="form.sizes" rows="6" :class="textareaCls" placeholder="A4&#10;A5&#10;A5S&#10;B5"></textarea>
      </label>
      <label class="block text-sm font-medium">
        规格
        <textarea v-model="form.specs" rows="6" :class="textareaCls" placeholder="横线&#10;网格&#10;方格&#10;点阵"></textarea>
      </label>
      <label class="block text-sm font-medium">
        颜色
        <textarea v-model="form.colors" rows="6" :class="textareaCls" placeholder="黑色&#10;白色&#10;蓝色&#10;粉色"></textarea>
      </label>
      <label class="block text-sm font-medium">
        材质
        <textarea v-model="form.materials" rows="6" :class="textareaCls" placeholder="牛皮纸&#10;道林纸&#10;PP 封面"></textarea>
      </label>
      <label class="block text-sm font-medium md:col-span-2">
        必填字段
        <textarea v-model="form.required" rows="3" :class="textareaCls" placeholder="品牌&#10;进价&#10;（填字段名；台账将标注 * 并做必填校验）"></textarea>
      </label>
    </div>
  </div>
</template>
