<script setup lang="ts">
  import { toast } from "@/components/ui/sonner";
  import { Button } from "@/components/ui/button";

  definePageMeta({
    middleware: ["auth"],
  });

  useHead({ title: "HomeBox | 选项配置" });

  const loading = ref(true);
  const saving = ref(false);
  const form = reactive({ sizes: "", specs: "", colors: "", materials: "" });

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
    try {
      const d = await $fetch<Record<string, string[]>>("/api/v1/ui-options");
      form.sizes = toText(d.sizes);
      form.specs = toText(d.specs);
      form.colors = toText(d.colors);
      form.materials = toText(d.materials);
    } catch (e) {
      toast.error("加载失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      loading.value = false;
    }
  }

  async function save() {
    saving.value = true;
    try {
      await $fetch("/api/v1/ui-options", {
        method: "PUT",
        body: {
          sizes: toArr(form.sizes),
          specs: toArr(form.specs),
          colors: toArr(form.colors),
          materials: toArr(form.materials),
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
    <div class="rounded-md border bg-card p-4">
      <h2 class="text-lg font-semibold">选项配置</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        配置后会作为「物品台账」新增表单和筛选下拉的全局选项（每行一个，或用逗号分隔）。留空的项会回退为按现有物品自动汇总。
      </p>
    </div>

    <div v-if="loading" class="rounded-md border bg-card p-4 text-sm text-muted-foreground">加载中…</div>
    <div v-else class="grid gap-4 rounded-md border bg-card p-4 md:grid-cols-2">
      <label class="block text-sm font-medium">
        尺寸
        <textarea v-model="form.sizes" rows="6" class="mt-1 w-full rounded-lg border bg-background p-2 text-sm outline-none focus:ring-2 focus:ring-ring/40" placeholder="A4&#10;A5&#10;A5S&#10;B5"></textarea>
      </label>
      <label class="block text-sm font-medium">
        规格
        <textarea v-model="form.specs" rows="6" class="mt-1 w-full rounded-lg border bg-background p-2 text-sm outline-none focus:ring-2 focus:ring-ring/40" placeholder="横线&#10;网格&#10;方格&#10;点阵"></textarea>
      </label>
      <label class="block text-sm font-medium">
        颜色
        <textarea v-model="form.colors" rows="6" class="mt-1 w-full rounded-lg border bg-background p-2 text-sm outline-none focus:ring-2 focus:ring-ring/40" placeholder="黑色&#10;白色&#10;蓝色&#10;粉色"></textarea>
      </label>
      <label class="block text-sm font-medium">
        材质
        <textarea v-model="form.materials" rows="6" class="mt-1 w-full rounded-lg border bg-background p-2 text-sm outline-none focus:ring-2 focus:ring-ring/40" placeholder="牛皮纸&#10;道林纸&#10;PP 封面"></textarea>
      </label>
      <div class="md:col-span-2">
        <Button :disabled="saving" @click="save">{{ saving ? "保存中…" : "保存" }}</Button>
      </div>
    </div>
  </div>
</template>
