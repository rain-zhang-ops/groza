// Groza 共享 UI 类名常量（设计标准 docs/ui-standard.md §4/§6）。
// Nuxt 自动导入，页面直接使用，不再页内重复定义。

export const btnGhost =
  "inline-flex items-center gap-1 rounded-lg border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50";

export const btnPrimary =
  "inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50";

export const inputCls =
  "rounded-lg border bg-background px-2.5 py-1.5 text-sm outline-none transition focus:ring-2 focus:ring-ring/40";

export const badgeCls =
  "rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground tabular-nums";

export const skeletonCls = "h-16 animate-pulse rounded-xl border bg-muted/40";

export const errorCls = "rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-destructive";

export const emptyCls = "py-10 text-center text-sm text-muted-foreground";

export const drawerWrap = "fixed inset-0 z-50 flex justify-end bg-black/40";

export const drawerPanel = "h-full w-full max-w-md overflow-auto bg-card p-5 shadow-2xl sm:max-w-lg";

export const inputClsLg =
  "mt-1 w-full rounded-lg border bg-background px-3 py-2.5 text-base outline-none transition focus:ring-2 focus:ring-ring/40";

export const safeBottom = "padding-bottom: calc(1rem + env(safe-area-inset-bottom))";
