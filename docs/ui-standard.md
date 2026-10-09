# Groza 页面设计标准（UI Standard）

> 目标：所有自研页「看起来像同一个产品」。新页面按本文档落地；旧页面逐步向标准收敛。
> 哲学来源：Codex/OpenAI 近单色中性系 + Claude 衬线/无衬线分工。核心气质：**克制、发丝边界、衬线标题、无重投影**。

## 1. 设计原则

1. **单色克制**：界面只有中性灰阶 + 墨色主按钮；彩色仅用于语义（amber=警告、destructive=危险、绿=成功）。
2. **边框即层次**：用 1px `border` 表达容器边界，不用投影；投影只留给浮层（抽屉/弹窗/FAB）。
3. **衬线管标题，黑体管功能**：标题 `font-display` + `font-medium`（衬线不用粗体）；正文/按钮/数字一律 sans；数字加 `tabular-nums`。
4. **少弹窗**：内容编辑进右侧抽屉；只有「确认类」才用居中弹窗。
5. **移动优先**：iPhone Safari 是第一公民，所有固定元素必须处理 `env(safe-area-inset-bottom)`。

## 2. 设计 Token

色板（`patches/patch_upstream.py` `patch_colors`，shadcn HSL 变量）：

| 用途 | token | 浅色值 |
|---|---|---|
| 页面底 | `bg-background` | #fff |
| 画布/侧栏底 | `bg-background-accent` / `bg-sidebar` | #fafafa |
| 卡片/弹层底 | `bg-card` | #fff |
| 次级面/徽章底 | `bg-muted` | #f5f5f5 |
| hover 面 | `bg-accent` | #f5f5f5 |
| 正文 | `text-foreground` | #0d0d0d |
| 次级文字 | `text-muted-foreground` | #6e6e6e |
| 边框/输入框边 | `border` / `border-input` | #e5e5e5 |
| 主按钮/焦点环 | `bg-primary` / `ring-ring` | #0d0d0d |
| 危险 | `text-destructive` / `border-destructive/40` / `bg-destructive/10` | #ef4146 |
| 警告（唯一允许的非 token 色） | `bg-amber-500/15 text-amber-600` | — |

字体：`font-display`（Georgia/Songti SC 衬线，仅标题）/ `font-sans`（默认）/ `font-mono`（编码、版本号）。
圆角：`--radius: 0.75rem`。分级：徽章/小chip `rounded-full|rounded-md`，按钮/输入框 `rounded-lg`，卡片/区块 `rounded-xl`，大卡片/弹窗 `rounded-2xl`。
动效：150ms `cubic-bezier(0.16,1,0.3,1)`，属性限 `background-color, border-color, color, box-shadow`（main.css `groza-motion` 全局注入，页面内写 `transition` 即可）。

## 3. 页面骨架（标准模板）

```html
<div class="min-h-[70vh] bg-background text-foreground">
  <div class="mx-auto max-w-5xl p-4 md:p-8" style="padding-bottom: calc(2rem + env(safe-area-inset-bottom))">
    <header class="mb-6 flex flex-wrap items-center gap-2">
      <h1 class="font-display text-xl font-medium tracking-tight md:text-2xl">页面名</h1>
      <span class="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground tabular-nums">共 N 项</span>
      <div class="ml-auto flex flex-wrap items-center gap-2">
        <!-- 次操作：border 按钮；当前页的主流程入口：primary 黑按钮 -->
      </div>
    </header>
    <!-- 内容 -->
  </div>
</div>
```

- **容器**：统一 `max-w-5xl p-4 md:p-8`；仅数据密集页（台账）允许例外：`max-w-[1700px] p-3 md:p-6`。
- **padding-bottom**：标准页 `calc(2rem + env(safe-area-inset-bottom))`（移动端 Dock 已移除，无抬高需求）；台账 `calc(1rem + env(...))`。
- **页头**：`mb-6`；h1 前不加装饰图标块。页头按钮顺序：主流程入口（primary）在最右，互跳链接（border）在左；每屏主按钮至多 1 个。
- **互跳集合**：进出/记录/单据页头部固定含「入库 · 出库 · 单据 · 台账」。

## 4. 组件标准

**按钮**（三级，共享常量定义在 `frontend/composables/uiClasses.ts`，Nuxt 自动导入，禁止页内重定义）：
```js
btnPrimary = "inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50";
btnGhost   = "inline-flex items-center gap-1 rounded-lg border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50";
```
- 主按钮（黑）：每屏至多 1-2 个，只给当前页主流程。
- 危险操作：文字型 `text-destructive hover:bg-destructive/10`（轻量，列表行内）或描边型 `border-destructive/40 text-destructive`（表单内）；**禁止** `red-*` 裸色值。
- 图标按钮：`grid h-9 w-9 place-items-center rounded-lg border hover:bg-muted`。

**徽章**：页头计数 `rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground tabular-nums`；行内 chip 同式可省略 `font-medium tabular-nums`；警告徽章 `bg-amber-500/15 text-amber-600`；统一 `text-xs`，不用 `text-[11px]`。

**卡片**：`rounded-xl border bg-card p-3`（紧凑列表卡）/ `p-4`（内容卡）；手机端物品大卡 `rounded-2xl`。**一律不带 shadow**。

**输入框**（统一常量）：
```js
const inputCls = "rounded-lg border bg-background px-2.5 py-1.5 text-sm outline-none transition focus:ring-2 focus:ring-ring/40";
// 移动端 sheet/表单用 inputClsLg：mt-1 w-full ... px-3 py-2.5 text-base（16px 防 iOS 自动缩放）
```

**抽屉**（共享常量 `drawerWrap`/`drawerPanel`，配合 `:style="safeBottom"` 处理底部安全区，禁止页内重写）。

**列表**：行卡 `rounded-xl border bg-card px-3 py-2.5 text-sm`，列表 `space-y-2`；表格用 `rounded-xl border bg-card` 包裹 + 行 `border-b last:border-0`。

**Tab 条**：`flex gap-1 rounded-xl border bg-card p-1.5`，激活项 `bg-primary text-primary-foreground`。

## 5. 弹层标准

| 场景 | 形态 | 规格 |
|---|---|---|
| 内容编辑/详情（默认） | 右侧抽屉 | `fixed inset-0 z-50 flex justify-end bg-black/40`，面板 `h-full w-full max-w-md overflow-auto bg-card p-5 shadow-2xl sm:max-w-lg`，标题 `font-display text-lg font-medium`，Transition `fade` |
| 移动端筛选/报告 | 底部 sheet | `items-end`，面板 `max-h-[88vh] rounded-t-2xl border-t bg-card shadow-2xl` + 抓手条，桌面端退化为居中 |
| 确认类（删除/回滚/AI 结果确认） | 居中弹窗 | `bg-black/50`，卡 `w-full max-w-md rounded-2xl bg-card p-4 shadow-xl` |
| 扫码/图片预览 | 全屏 | `bg-black/80` |

- z-index 规范：内容浮层一律 `z-50`；常驻 chrome（底部保存条/移动筛选 sheet）`z-40`。
- 新建弹层从右侧抽屉开始想，禁止新增居中表单弹窗。

## 6. 状态标准

- **loading**：骨架屏 `h-16 animate-pulse rounded-xl border bg-muted/40`，按内容形态重复 5-6 个；禁用「加载中…」纯文字（collection 两页待改）。
- **empty**：`py-10 text-center text-sm text-muted-foreground`；重要空态可用 `rounded-xl border border-dashed p-10 text-center`。
- **error**：`rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-destructive`。
- **离线**：顶栏徽章 `bg-amber-500/15 text-amber-600`；台账的离线只读横幅为全宽条。
- **操作反馈**：页内轻提示 `mt-3 text-center text-xs text-muted-foreground`；collection 体系用 toast。二者选一并按页体系固定（见 §8）。

## 7. 移动端标准

- 触控目标 ≥ 40px（计数器/步进按钮 `h-11 w-11` 是标杆）。
- 固定底部元素（保存条）必须 `padding-bottom: env(safe-area-inset-bottom)`。
- 手机卡片 + 桌面表格双形态（台账模式）；下拉刷新仅限台账。
- 顶部 AppBar：ghost 汉堡 + 衬线字标 + outline 图标按钮；禁止 `bg-primary` 黑块图标。

## 8. 两套页面体系（现状，收敛方向）

- **主流体系**（tasks/ledger/intake/outbound/documents）：手写 class、`rounded-xl/2xl`、页内常量、msg 轻提示。（records×2 已删除，功能并入 documents，见 design.md 第 10 节）
- **collection 体系**（fields/ui-options）：shadcn `<Button>`、`rounded-md`、toast、Teleport 页头按钮。
- **收敛方向**：collection 两页并入主流体系（圆角升 `rounded-xl`、加骨架屏、`inputCls` 统一）；`btnPrimary/btnGhost/inputCls/chip` 四个常量抽为共享模块 `frontend/composables/uiClasses.ts`，消灭 6+ 份重复定义。

## 9. 文案标准

- 术语：入库/出库/单据/台账/待办/盘点（禁用「进货/出货/物品管理」）。
- 导航分组：概览(待办) / 库存(物品·盘点) / 进出(入库·出库·发货) / 配置(库存架构·选项·标签·分类·结构) / 管理(成员·邀请·通知·集合设置·工具) / 我的。规则：**配置=库存建模，管理=团队与系统**；禁用「高级/其他」式模糊分组；组内不出现与组同名的项（旧「设置」组含「设置」项即反例）；菜单项 ≤4 字，禁止多词堆叠（旧「字段 / 位置 / 媒体 / 组织」即反例）；去行话（通知器→通知）。集合页（/collection/*）不设页内 tab 条——导航唯一入口是侧栏/抽屉，页头只出当前页标题（布局按路由自动映射），避免「一页看到全部组」的不纯粹。
- 计数单位：物品=款、库存=件、单据=单。
- 空态文案给动作指引（「暂无记录，去入库 →」式）。

## 10. Do / Don't

**Do**：用 token 色值；`tabular-nums` 管数字；hover 只改底色；新页从 §3 模板复制。
**Don't**：不用 `shadow` 于静态卡片；不用 `red-*`/`blue-*` 裸色；衬线不加粗；不新增居中表单弹窗；不在页头放超过 5 个按钮。

## 11. 交互标准（Interaction）

> 来源：Nielsen 响应三阈值、Linear（乐观更新/安静表格）、Notion（hover 渐进披露）、Apple HIG（44pt 触控）、Material（Snackbar 规范）、A List Apart（undo 优于警告）。

1. **即时反馈**：任何点击 100ms 内有视觉反馈（`active:scale-95`/局部 loading）；>1s 的操作必须出状态文案。
2. **乐观更新**：可逆操作先写本地、后台同步、失败回滚+提示；界面速度不依赖网络。
3. **撤销优于确认**：删除/作废 = 立即执行 + 撤销入口；仅不可恢复操作允许确认弹窗。
4. **安静表格**（台账桌面）：单元格控件默认透明无边（`cellCtrl`），hover 显边、focus 显环；行操作按钮与复选框 `opacity-0 group-hover:opacity-100`（有选中态时复选框常显）；读时像文档，写时是表单。
5. **Esc 逐层关闭**：所有抽屉/弹层/预览必须可被 Esc 关闭（`useEscStack`，弹层栈顶优先）；点击遮罩（`@click.self`）关闭同样必须。
6. **菜单外点收起**：`<details>` 菜单点击页面任意处自动关闭（`useDetailsAutoClose`，capture 阶段）。
7. **键盘流**：高频录入页桌面端落地聚焦首字段（移动端不弹键盘）；Enter 前进/提交。
8. **触控下限**：可点目标 ≥44px；主操作在拇指热区（屏幕下半部）。
9. **加载态**：已知布局用骨架屏；不用裸 spinner。
10. **空态**：每页必有设计过的空态（说明 + 引导动作）。

## 附：现状差距清单（按优先级）

| # | 差距 | 涉及文件 | 标准条款 |
|---|---|---|---|
| ~~1~~ | ~~按钮/输入框常量 6+ 处重复定义~~ ✅ 已抽 `frontend/composables/uiClasses.ts`（btnGhost/btnPrimary/inputCls/badgeCls/skeletonCls/errorCls/emptyCls） | 全部主流页 | §8 |
| ~~2~~ | ~~collection 两页体系不同~~ ✅ 圆角升 rounded-xl、ui-options 加骨架屏、inputCls 统一（保留 Teleport 页头与 toast） | fields.vue、ui-options.vue | §8 |
| ~~3~~ | ~~ledger 页头 mb-4 + 图标块、根容器无 min-h~~ ✅ 图标块已删、mb-6、min-h-[70vh] | ledger.vue | §3 |
| ~~4~~ | ~~danger 按钮三种写法（含 red-* 裸色）~~ ✅ 全量改 destructive token（含数据体检抽屉 3 处） | ledger.vue | §4 |
| ~~5~~ | ~~amber 写法剩余不统一~~ ✅ 撤销按钮统一 border-amber-400/bg-amber-500/10；盘点提交按钮改 btnPrimary | ledger.vue | §2 |
| ~~6~~ | ~~骨架/error/empty 圆角与高度不统一~~ ✅ 换 skeletonCls/errorCls/emptyCls，删 animate-shimmer | ledger.vue | §6 |
| ~~7~~ | ~~弹层 Transition 名不一致~~ ✅ 底部弹层统一 sheet（差异预览/盘点报告 fold→sheet）；fold 只留行内展开 | ledger.vue | §5 |
| ~~8~~ | ~~records 页导出/复制按钮缺 text-sm~~ ✅ 已换 btnGhost | intake/outbound-records.vue | §4 |
| ~~9~~ | ~~徽章规格混用（text-[11px]、px-2）~~ ✅ 全量 text-xs / px-2.5 | ledger.vue、records 页 | §4 |
| ~~10~~ | ~~z-index 混用（筛选 sheet z-40 与 FAB 同级）~~ ✅ sheet 升 z-50；移动 FAB 已删除（入口收敛到页头） | ledger.vue | §5 |
