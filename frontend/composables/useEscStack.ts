// Groza 全局交互基元（设计标准 docs/ui-standard.md §11）。
// useEscStack：Esc 逐层关闭弹层（closer 返回 true 表示「我关了」，停止下传）。
// useDetailsAutoClose：<details> 菜单点击页面任意处自动收起（原生 details 不会）。

export function useEscStack(closers: Array<() => boolean>) {
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "Escape") return;
    for (const c of closers) {
      if (c()) {
        e.preventDefault();
        break;
      }
    }
  };
  onMounted(() => window.addEventListener("keydown", onKey));
  onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
}

export function useDetailsAutoClose() {
  const onClick = (e: MouseEvent) => {
    const t = e.target as Node;
    document.querySelectorAll("details[open]").forEach(d => {
      if (!d.contains(t)) (d as HTMLDetailsElement).open = false;
    });
  };
  // capture 阶段处理：summary 点击先走原生 toggle，外点兜底
  onMounted(() => document.addEventListener("click", onClick, true));
  onBeforeUnmount(() => document.removeEventListener("click", onClick, true));
}
