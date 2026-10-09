<script setup lang="ts">
  // 缩略图：加载中显示脉冲骨架 + 图标（避免误以为无图），decode 完成后淡入；失败显示占位图标。
  import MdiImageOutline from "~icons/mdi/image-outline";
  import MdiImageOffOutline from "~icons/mdi/image-off-outline";

  defineProps<{ src: string; boxClass?: string }>();
  const loaded = ref(false);
  const failed = ref(false);
  function onLoad(e: Event) {
    const img = e.target as HTMLImageElement;
    const done = () => { loaded.value = true; };
    if (typeof img.decode === "function") img.decode().then(done, done);
    else done();
  }
</script>

<template>
  <span class="relative inline-block shrink-0 overflow-hidden" :class="boxClass">
    <span v-if="!loaded" class="absolute inset-0 grid place-items-center bg-muted" :class="failed ? '' : 'animate-pulse'">
      <MdiImageOffOutline v-if="failed" class="h-1/3 w-1/3 text-muted-foreground/50" />
      <MdiImageOutline v-else class="h-1/3 w-1/3 text-muted-foreground/40" />
    </span>
    <img
      :src="src"
      decoding="async"
      class="absolute inset-0 h-full w-full object-cover transition-opacity duration-300"
      :class="loaded ? 'opacity-100' : 'opacity-0'"
      alt=""
      @load="onLoad"
      @error="failed = true"
    />
  </span>
</template>
