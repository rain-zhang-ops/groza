#!/usr/bin/env python3
"""homebox-cn 上游源码统一补丁脚本（集中管理，替代 rebuild.sh 里的散装补丁）。

用法: patch_upstream.py <frontend_dir> <backend_dir>
约定: 每个补丁独立函数；锚点找不到 => 打印 FAIL 并退出码 2（构建中止，防止静默失效）。
已应用的补丁会打印 OK；重复执行安全（幂等的补丁会 SKIP）。
"""
import json
import sys

FAILS = []

def done(name):
    print(f"OK   {name}")

def skip(name, why="已应用"):
    print(f"SKIP {name} ({why})")

def fail(name, why):
    FAILS.append(name)
    print(f"FAIL {name}: {why}", file=sys.stderr)

def rep(path, old, new, name, done_msg=None):
    s = open(path, encoding="utf-8").read()
    if new and new in s:
        skip(name)
        return
    if old not in s:
        if not new:
            skip(name, "已移除")
            return
        fail(name, "锚点未找到（上游代码可能已变化，请人工更新补丁）")
        return
    open(path, "w", encoding="utf-8").write(s.replace(old, new, 1))
    done(name if not done_msg else f"{name} -> {done_msg}")


def rep_any(path, olds, new, name, done_msg=None):
    """rep 的迁移版：olds 按优先级列出可替换锚点（含历史已应用的旧值），任一中招即替换。"""
    s = open(path, encoding="utf-8").read()
    if new in s:
        skip(name)
        return
    for old in olds:
        if old in s:
            open(path, "w", encoding="utf-8").write(s.replace(old, new, 1))
            done(name if not done_msg else f"{name} -> {done_msg}")
            return
    fail(name, "锚点未找到（上游代码可能已变化，请人工更新补丁）")


def patch_colors(fe):
    p = f"{fe}/assets/css/main.css"
    try:
        s = open(p, encoding="utf-8").read()
    except OSError:
        fail("theme-colors", "无法读取 main.css")
        return
    key = ":root,.homebox {"
    i = s.find(key)
    if i < 0:
        fail("theme-colors", "未找到 :root,.homebox")
        return
    j = s.find("--radius:", i)
    if j < 0:
        fail("theme-colors", "未找到 radius 锚点")
        return
    end = s.find(";", j)
    if end < 0:
        fail("theme-colors", "radius 锚点缺少分号")
        return
    end += 1
    if "--ring: 0 0% 5%;" in s[i:end]:
        skip("theme-colors")
        return
    new = """:root,.homebox {
    --background: 0 0% 100%;
    --background-accent: 0 0% 98%;
    --foreground: 0 0% 5%;
    --primary: 0 0% 5%;
    --primary-foreground: 0 0% 100%;
    --secondary: 0 0% 96%;
    --secondary-foreground: 0 0% 5%;
    --accent: 0 0% 96%;
    --accent-foreground: 0 0% 5%;
    --muted: 0 0% 96%;
    --muted-foreground: 0 0% 43%;
    --card: 0 0% 100%;
    --card-foreground: 0 0% 5%;
    --popover: 0 0% 100%;
    --popover-foreground: 0 0% 5%;
    --destructive: 358 84% 59%;
    --destructive-foreground: 0 0% 100%;
    --input: 0 0% 90%;
    --border: 0 0% 90%;
    --ring: 0 0% 5%;
    --sidebar-background: 0 0% 98%;
    --sidebar-foreground: 0 0% 5%;
    --sidebar-primary: 0 0% 5%;
    --sidebar-primary-foreground: 0 0% 100%;
    --sidebar-accent: 0 0% 94%;
    --sidebar-accent-foreground: 0 0% 5%;
    --sidebar-border: 0 0% 90%;
    --sidebar-ring: 0 0% 5%;
    --radius: 0.75rem;"""
    open(p, "w", encoding="utf-8").write(s[:i] + new + s[end:])
    done("theme-colors Groza 配色（Codex 式中性单色风）")


def rebrand_locale(fe):
    p = f"{fe}/locales/zh-CN.json"
    try:
        d = json.load(open(p, encoding="utf-8"))
    except OSError:
        return
    changed = [0]

    def walk(x):
        if isinstance(x, str):
            y = x.replace("HomeBox", "Groza").replace("Homebox", "Groza")
            if y != x:
                changed[0] += 1
            return y
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x

    d = walk(d)
    if changed[0]:
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        done(f"rebrand zh-CN（{changed[0]} 处 HomeBox→Groza）")
    else:
        skip("rebrand zh-CN")


def patch_dark(fe):
    p = f"{fe}/assets/css/main.css"
    try:
        s = open(p, encoding="utf-8").read()
    except OSError:
        fail("dark-mode", "无法读取 main.css")
        return
    dark_vars = """    --background: 0 0% 9%;
    --background-accent: 0 0% 13%;
    --foreground: 0 0% 93%;
    --primary: 0 0% 98%;
    --primary-foreground: 0 0% 5%;
    --secondary: 0 0% 15%;
    --secondary-foreground: 0 0% 93%;
    --accent: 0 0% 17%;
    --accent-foreground: 0 0% 93%;
    --muted: 0 0% 15%;
    --muted-foreground: 0 0% 63%;
    --card: 0 0% 13%;
    --card-foreground: 0 0% 93%;
    --popover: 0 0% 13%;
    --popover-foreground: 0 0% 93%;
    --destructive: 358 70% 55%;
    --destructive-foreground: 0 0% 100%;
    --input: 0 0% 22%;
    --border: 0 0% 22%;
    --ring: 0 0% 90%;
    --sidebar-background: 0 0% 7%;
    --sidebar-foreground: 0 0% 93%;
    --sidebar-primary: 0 0% 98%;
    --sidebar-primary-foreground: 0 0% 5%;
    --sidebar-accent: 0 0% 15%;
    --sidebar-accent-foreground: 0 0% 93%;
    --sidebar-border: 0 0% 22%;
    --sidebar-ring: 0 0% 90%;"""
    dark = (
        "\n\n/* Groza 深色主题：跟随系统 prefers-color-scheme；<html data-gx-theme> 可手动覆盖"
        "（light 强制浅色 / dark 强制深色，见 我的→主题设置）。未放入 @layer base，优先级高于所有分层主题。*/\n"
        "@media (prefers-color-scheme: dark) {\n"
        "  :root:not([data-gx-theme=\"light\"]) {\n" + dark_vars + "\n  }\n}\n\n"
        ":root[data-gx-theme=\"dark\"] {\n" + dark_vars + "\n}\n"
        "/* /Groza 深色主题 */\n"
    )
    marker = "\n\n/* Groza 深色主题"
    if marker in s:
        # 已追加过（历史版本）：替换深色块本身（不波及块后内容，如 groza-motion）
        i = s.find(marker)
        term = "/* /Groza 深色主题 */\n"
        if term in s[i:]:
            end = s.find(term, i) + len(term)
        else:
            # 旧块无终结标记：到媒体查询的收尾 "}\n" 为止
            end = s.find("\n}\n", i)
            if end < 0:
                fail("dark-mode", "深色块结尾未找到")
                return
            end += len("\n}\n")
        open(p, "w", encoding="utf-8").write(s[:i] + dark + s[end:])
        done("dark-mode 深色跟随系统+手动覆盖 -> Codex 中性深色")
        return
    if "prefers-color-scheme: dark" in s:
        skip("dark-mode")
        return
    open(p, "a", encoding="utf-8").write(dark)
    done("dark-mode 深色跟随系统+手动覆盖")


def patch_fonts(fe):
    p = f"{fe}/tailwind.config.js"
    try:
        s = open(p, encoding="utf-8").read()
    except OSError:
        fail("fonts", "无法读取 tailwind.config.js")
        return
    if "fontFamily" in s:
        skip("fonts")
        return
    anchor = "    extend: {\n      colors: {"
    new = '''    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "Noto Sans SC",
          "sans-serif",
        ],
        display: ["Georgia", "Times New Roman", "Songti SC", "STSong", "SimSun", "serif"],
        mono: ["ui-monospace", "SF Mono", "Menlo", "Consolas", "monospace"],
      },
      colors: {'''
    if anchor not in s:
        fail("fonts", "未找到 theme.extend.colors 锚点")
        return
    open(p, "w", encoding="utf-8").write(s.replace(anchor, new, 1))
    done("fonts 字体栈（sans 中文优化 / display 衬线 / mono）")


def patch_card_ring(fe):
    rep(f"{fe}/components/ui/card/Card.vue",
        "'rounded-lg bg-card text-card-foreground shadow',",
        "'rounded-lg border bg-card text-card-foreground',",
        "card-ring 卡片发丝边框替代投影")
    p = f"{fe}/components/ui/button/index.ts"
    rep(p,
        'default: "bg-primary text-primary-foreground shadow hover:bg-primary/90",',
        'default: "bg-primary text-primary-foreground hover:bg-primary/90",',
        "btn-default-shadow-rm")
    rep(p,
        'destructive: "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",',
        'destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",',
        "btn-destructive-shadow-rm")
    rep(p,
        'outline: "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",',
        'outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",',
        "btn-outline-shadow-rm")
    rep(p,
        'secondary: "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",',
        'secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",',
        "btn-secondary-shadow-rm")


def patch_motion(fe):
    """Codex 式交互基调：150ms 克制动效、细滚动条、墨色 selection。"""
    p = f"{fe}/assets/css/main.css"
    try:
        s = open(p, encoding="utf-8").read()
    except OSError:
        fail("motion", "无法读取 main.css")
        return
    if "groza-motion" in s:
        skip("motion")
        return
    css = """

/* groza-motion：克制动效 + 细滚动条 + 墨色 selection */
a, button, [role="button"], input, select, textarea {
  transition-property: background-color, border-color, color, box-shadow;
  transition-duration: 150ms;
  transition-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
}
::selection { background: hsl(var(--foreground) / 0.12); }
*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-thumb { background: hsl(var(--foreground) / 0.15); border-radius: 9999px; }
*::-webkit-scrollbar-thumb:hover { background: hsl(var(--foreground) / 0.28); }
*::-webkit-scrollbar-track { background: transparent; }
"""
    open(p, "a", encoding="utf-8").write(css)
    done("motion 交互基调（过渡/滚动条/selection）")


def main():
    fe, be = sys.argv[1], sys.argv[2]

    # ---- 1. 默认语言 zh-CN ----
    rep(f"{fe}/plugins/i18n.ts",
        'locale: preferences.value.language || checkDefaultLanguage() || "en",',
        'locale: preferences.value.language || "zh-CN",',
        "i18n-locale")
    rep(f"{fe}/plugins/i18n.ts",
        'fallbackLocale: "en",',
        'fallbackLocale: "zh-CN",',
        "i18n-fallback")

    # ---- 2. 中文菜单名 ----
    p = f"{fe}/locales/zh-CN.json"
    d = json.load(open(p, encoding="utf-8"))
    m = d.setdefault("menu", {})
    rename = {
        "home": "首页", "locations": "分类", "profile": "我的",
        "create_item": "物品", "create_location": "分类", "create_tag": "标签",
        "search": "物品", "templates": "模板", "maintenance": "维护",
        "collection": "集合", "scanner": "扫码",
    }
    m.update(rename)
    # 集合页签命名对齐侧栏（去行话、消解组项同名）
    tabs = d.setdefault("collection", {}).setdefault("tabs", {})
    tabs.update({"notifiers": "通知", "settings": "集合设置", "entity_types": "结构"})
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    done("menu-zh 菜单统一中文")

    # ---- 2c. 品牌与配色：Groza ----
    rep(f"{fe}/nuxt.config.ts",
        'name: "Homebox",\n      short_name: "Homebox",',
        'name: "Groza",\n      short_name: "Groza",',
        "pwa-name-groza")
    rep_any(f"{fe}/layouts/default.vue",
        ['<AppHeaderText class="h-6" />',
         '<span class="text-xl font-bold tracking-tight text-secondary-foreground">Groza</span>'],
        '<span class="font-display text-xl font-medium tracking-tight text-foreground">Groza</span>',
        "brand-header-groza")
    rep(f"{fe}/pages/index.vue",
        'title: "HomeBox | " + t("index.title"),',
        'title: "Groza | " + t("index.title"),',
        "brand-login-title")
    patch_colors(fe)
    patch_fonts(fe)
    rebrand_locale(fe)
    patch_dark(fe)
    # 大字号 + 手动主题：set-theme.js 启动即应用（跟随本地偏好）
    p_theme = f"{fe}/public/set-theme.js"
    try:
        ts = open(p_theme, encoding="utf-8").read()
        changed = False
        if "groza.bigfont" not in ts:
            ts += '\ntry { if (localStorage.getItem("groza.bigfont") === "1") { document.documentElement.style.fontSize = "18px"; } } catch (e) {}\n'
            changed = True
        if "groza.theme" not in ts:
            ts += '\ntry { var gxt = localStorage.getItem("groza.theme") || ""; if (gxt) { document.documentElement.setAttribute("data-gx-theme", gxt); } } catch (e) {}\n'
            changed = True
        if changed:
            open(p_theme, "w", encoding="utf-8").write(ts)
            done("theme-boot（bigfont + data-gx-theme）")
        else:
            skip("theme-boot")
    except OSError:
        fail("theme-boot", "set-theme.js 不可读")
    rep_any(f"{fe}/app.vue",
        ['<Meta name="theme-color" content="#5b7f67" />',
         '<Meta name="theme-color" content="#2f3e7e" media="(prefers-color-scheme: light)" />\n      <Meta name="theme-color" content="#111725" media="(prefers-color-scheme: dark)" />'],
        '<Meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)" />\n      <Meta name="theme-color" content="#171717" media="(prefers-color-scheme: dark)" />',
        "pwa-theme-color")

    # ---- 2d. 移动端/PWA 打磨：viewport-fit、iOS 独立应用元信息、品牌色 ----
    rep(f"{fe}/nuxt.config.ts",
        '  app: {\n    head: {\n      script: [{ src: "/set-theme.js" }],\n    },\n  },',
        '  app: {\n    head: {\n'
        '      viewport: "width=device-width, initial-scale=1, viewport-fit=cover",\n'
        '      meta: [\n'
        '        { name: "mobile-web-app-capable", content: "yes" },\n'
        '        { name: "apple-mobile-web-app-capable", content: "yes" },\n'
        '        { name: "apple-mobile-web-app-status-bar-style", content: "black-translucent" },\n'
        '        { name: "apple-mobile-web-app-title", content: "Groza" },\n'
        '      ],\n'
        '      script: [{ src: "/set-theme.js" }],\n    },\n  },',
        "mobile-head")
    rep_any(f"{fe}/app.vue",
        ['<Link rel="mask-icon" href="/mask-icon.svg" color="#5b7f67" />',
         '<Link rel="mask-icon" href="/mask-icon.svg" color="#2f3e7e" />'],
        '<Link rel="mask-icon" href="/mask-icon.svg" color="#0d0d0d" />',
        "mask-icon-color")
    patch_card_ring(fe)
    patch_motion(fe)

    # ---- 2b. PWA Service Worker 策略 ----
    #   /api        -> NetworkOnly（保证库存/流水实时，不被缓存落后）
    #   导航请求    -> NetworkFirst(3s)（新壳优先，离线回退缓存）
    #   哈希资源    -> CacheFirst（内容寻址，长缓存）
    rep(f"{fe}/nuxt.config.ts",
        '''      runtimeCaching: [
        {
          urlPattern: /^\\/api/,
          handler: "NetworkFirst",
          method: "GET",
          options: {
            cacheName: "api-cache",
            cacheableResponse: { statuses: [0, 200] },
            expiration: { maxAgeSeconds: 60 * 60 * 24 },
          },
        },
      ],''',
        '''      runtimeCaching: [
        { urlPattern: /^\\/api/, handler: "NetworkOnly", method: "GET" },
        {
          urlPattern: ({ request }) => request.mode === "navigate",
          handler: "NetworkFirst",
          options: { cacheName: "pages", networkTimeoutSeconds: 3, expiration: { maxEntries: 10 } },
        },
        {
          urlPattern: /\\/_nuxt\\/.*\\.(?:js|css|woff2?|png|jpg|jpeg|webp|svg)$/,
          handler: "CacheFirst",
          options: { cacheName: "assets", expiration: { maxEntries: 300, maxAgeSeconds: 60 * 60 * 24 * 30 } },
        },
      ],''',
        "pwa-sw-strategy")

    # ---- 3. 侧边栏：/items 菜单并入 /ledger ----
    dv = f"{fe}/layouts/default.vue"
    rep(dv,
        'import MdiMagnify from "~icons/mdi/magnify";',
        'import MdiMagnify from "~icons/mdi/magnify";\n  import MdiCashMultiple from "~icons/mdi/cash-multiple";',
        "nav-sell-icon-import")
    rep(dv,
        'navigateTo(`/items?q=${encodeURIComponent(search.value)}`);',
        'navigateTo(`/ledger?q=${encodeURIComponent(search.value)}`);',
        "nav-topsearch-to-ledger")

    # 侧栏移除「分类」入口（改到 集合 → 分类 tab）
    dv_s = open(dv, encoding="utf-8").read()
    loc_block = ('    {\n'
                 '      icon: MdiFileTree,\n'
                 '      id: 1,\n'
                 '      active: computed(() => route.path === "/locations"),\n'
                 '      name: computed(() => t("menu.locations")),\n'
                 '      to: "/locations",\n'
                 '    },\n')
    if loc_block in dv_s:
        open(dv, "w", encoding="utf-8").write(dv_s.replace(loc_block, "", 1))
        done("nav-hide-locations（分类移入设置 tab）")
    else:
        skip("nav-hide-locations")

    # ---- 4. （已废弃）侧栏 Collapsible 样式补丁：v2 分组扁平菜单无 Collapsible 标记 ----

    # ---- 5. 分类页默认隐藏物品 ----
    rep(f"{fe}/pages/locations.vue",
        'const showItems = ref(true);',
        'const showItems = ref(false);',
        "locations-hide-items-default")

    # ---- 6. 后端路由（含 ledger 聚合/字段PATCH/trash2）----
    p = f"{be}/app/api/routes.go"
    s = open(p, encoding="utf-8").read()
    if "/ledger/{" in s:
        skip("routes-ledger")
    else:
        anchor = ("\t\tuserMW := []errchain.Middleware{\n"
                  "\t\t\ta.mwAuthToken,\n"
                  "\t\t\ta.mwTenant,\n"
                  "\t\t\ta.mwRoles(RoleModeOr, authroles.RoleUser.String()),\n"
                  "\t\t}")
        add = anchor + ("\n\n"
                        "\t\tr.Get(\"/ledger\", chain.ToHandlerFunc(a.handleLedgerAggregate(), userMW...))\n"
                        "\t\tr.Patch(\"/ledger/{id}\", chain.ToHandlerFunc(a.handleLedgerFieldPatch(), userMW...))\n"
                        "\t\tr.Post(\"/ledger/sync-fields\", chain.ToHandlerFunc(a.handleLedgerSyncFields(), userMW...))\n"
                        "\t\tr.Get(\"/trash2\", chain.ToHandlerFunc(a.handleTrash2Get(), userMW...))\n"
                        "\t\tr.Put(\"/trash2\", chain.ToHandlerFunc(a.handleTrash2Put(), userMW...))\n"
                        "\t\tr.Post(\"/trash2/purge\", chain.ToHandlerFunc(a.handleTrash2Purge(), userMW...))\n"
                        "\t\tr.Get(\"/ui-options\", chain.ToHandlerFunc(a.handleUIOptionsGet(), userMW...))\n"
                        "\t\tr.Put(\"/ui-options\", chain.ToHandlerFunc(a.handleUIOptionsPut(), userMW...))\n"
                        "\t\tr.Post(\"/ai/recognize\", chain.ToHandlerFunc(a.handleAIRecognize(), userMW...))\n"
                        "\t\tr.Get(\"/trash\", chain.ToHandlerFunc(a.handleTrashGet(), userMW...))\n"
                        "\t\tr.Put(\"/trash\", chain.ToHandlerFunc(a.handleTrashPut(), userMW...))\n"
                        "\t\tr.Get(\"/audit\", chain.ToHandlerFunc(a.handleAuditGet(), userMW...))\n"
                        "\t\tr.Get(\"/metrics\", chain.ToHandlerFunc(a.handleMetrics(), userMW...))\n"
                        "\t\tr.Get(\"/gx/config\", chain.ToHandlerFunc(a.handleGxConfigGet(), userMW...))\n"
                        "\t\tr.Put(\"/gx/config\", chain.ToHandlerFunc(a.handleGxConfigPut(), userMW...))\n"
                        "\t\tr.Get(\"/gx/documents\", chain.ToHandlerFunc(a.handleGxDocuments(), userMW...))\n"
                        "\t\tr.Get(\"/gx/me\", chain.ToHandlerFunc(a.handleGxMe(), userMW...))\n"
                        "\t\tr.Post(\"/gx/adjust\", chain.ToHandlerFunc(a.handleGxAdjust(), userMW...))\n"
                        "\t\tr.Get(\"/gx/config/history\", chain.ToHandlerFunc(a.handleGxConfigHistory(), userMW...))\n"
                        "\t\tr.Post(\"/gx/config/restore\", chain.ToHandlerFunc(a.handleGxConfigRestore(), userMW...))")
        if anchor not in s:
            fail("routes-ledger", "userMW 锚点未找到")
        else:
            open(p, "w", encoding="utf-8").write(s.replace(anchor, add, 1))
            done("routes-ledger 注入 /ledger /ledger/{id} /trash2 /ui-options /ai/recognize /trash")

    # ---- 6b. 后端路由：embedding 以图搜图滤重（取代已废弃的 routes-phash）----
    s = open(p, encoding="utf-8").read()
    changed = False
    for dead in ('\n\t\tr.Get("/gx/phashes", chain.ToHandlerFunc(a.handlePhashesGet(), userMW...))',
                 '\n\t\tr.Put("/gx/phashes", chain.ToHandlerFunc(a.handlePhashesPut(), userMW...))'):
        if dead in s:
            s = s.replace(dead, "")
            changed = True
    if "/gx/embed-match" in s:
        if changed:
            open(p, "w", encoding="utf-8").write(s)
            done("routes-embed 清理废弃 phash 路由")
        else:
            skip("routes-embed")
    else:
        anchor = '\t\tr.Post("/gx/config/restore", chain.ToHandlerFunc(a.handleGxConfigRestore(), userMW...))'
        add = anchor + ("\n"
                        '\t\tr.Post("/gx/embed-match", chain.ToHandlerFunc(a.handleEmbedMatch(), userMW...))\n'
                        '\t\tr.Post("/gx/embed-register", chain.ToHandlerFunc(a.handleEmbedRegister(), userMW...))\n'
                        '\t\tr.Get("/gx/embed-status", chain.ToHandlerFunc(a.handleEmbedStatus(), userMW...))')
        if anchor not in s:
            fail("routes-embed", "gx/config/restore 锚点未找到")
        else:
            open(p, "w", encoding="utf-8").write(s.replace(anchor, add, 1))
            done("routes-embed 注入 /gx/embed-match /gx/embed-register /gx/embed-status")

    # ---- 7. 集合页「选项配置」tab ----
    coll = f"{fe}/pages/collection/index.vue"
    c = open(coll, encoding="utf-8").read()
    if 'to: "/collection/ui-options"' in c:
        skip("collection-ui-options-tab")
    else:
        changed = False
        if 'import MdiTune from "~icons/mdi/tune";' not in c:
            c2 = c.replace('  import MdiShape from "~icons/mdi/shape";',
                           '  import MdiShape from "~icons/mdi/shape";\n  import MdiTune from "~icons/mdi/tune";', 1)
            if c2 != c:
                c = c2; changed = True
        t_anchor = ('    {\n'
                    '      id: "entity-types",\n'
                    '      label: "collection.tabs.entity_types",\n'
                    '      to: "/collection/entity-types",\n'
                    '      icon: MdiShape,\n'
                    '    },')
        t_add = t_anchor + ('\n'
                            '    {\n'
                            '      id: "ui-options",\n'
                            '      label: "选项",\n'
                            '      to: "/collection/ui-options",\n'
                            '      icon: MdiTune,\n'
                            '    },')
        if t_anchor in c:
            c = c.replace(t_anchor, t_add, 1); changed = True
        else:
            fail("collection-ui-options-tab", "tabs 锚点未找到")
        if changed:
            open(coll, "w", encoding="utf-8").write(c)
            done("collection-ui-options-tab")

    # 历史注入的「选项配置」页签更名为「选项」（与侧栏一致）
    rep_any(coll,
        ['      id: "ui-options",\n      label: "选项配置",'],
        '      id: "ui-options",\n      label: "选项",',
        "tab-rename-ui-options")

    # 集合页「分类」tab（指向 /locations）
    rep(coll,
        '  import MdiTune from "~icons/mdi/tune";',
        '  import MdiTune from "~icons/mdi/tune";\n  import MdiFileTree from "~icons/mdi/file-tree";',
        "collection-locations-icon")
    rep(coll,
        '    {\n      id: "ui-options",\n      label: "选项",\n      to: "/collection/ui-options",\n      icon: MdiTune,\n    },',
        '    {\n      id: "ui-options",\n      label: "选项",\n      to: "/collection/ui-options",\n      icon: MdiTune,\n    },\n    {\n      id: "locations",\n      label: "分类",\n      to: "/locations",\n      icon: MdiFileTree,\n    },',
        "collection-locations-tab")

    # 集合页「字段」tab（指向 /templates），并隐藏侧栏「模板」入口
    rep(coll,
        '  import MdiFileTree from "~icons/mdi/file-tree";',
        '  import MdiFileTree from "~icons/mdi/file-tree";\n  import MdiFormTextbox from "~icons/mdi/form-textbox";',
        "collection-fields-icon")
    rep(coll,
        '    {\n      id: "locations",\n      label: "分类",\n      to: "/locations",\n      icon: MdiFileTree,\n    },',
        '    {\n      id: "locations",\n      label: "分类",\n      to: "/locations",\n      icon: MdiFileTree,\n    },\n    {\n      id: "fields",\n      label: "配置",\n      to: "/templates",\n      icon: MdiFormTextbox,\n    },',
        "collection-fields-tab")
    rep_any(coll,
        ['      id: "fields",\n      label: "库存架构",\n      to: "/collection/fields",',
         '      id: "fields",\n      label: "配置",\n      to: "/collection/fields",',
         '      id: "fields",\n      label: "配置",\n      to: "/templates",',
         '      id: "fields",\n      label: "字段",\n      to: "/templates",'],
        '      id: "fields",\n      label: "库存架构",\n      to: "/collection/fields",',
        "collection-fields-tab-target")
    dv_t = open(dv, encoding="utf-8").read()
    tpl_block = ('    {\n'
                 '      icon: MdiFileDocumentMultiple,\n'
                 '      id: 4,\n'
                 '      active: computed(() => route.path === "/templates"),\n'
                 '      name: computed(() => t("menu.templates")),\n'
                 '      to: "/templates",\n'
                 '    },\n')
    if tpl_block in dv_t:
        open(dv, "w", encoding="utf-8").write(dv_t.replace(tpl_block, "", 1))
        done("nav-hide-templates（模板并入 集合→字段）")
    else:
        skip("nav-hide-templates")

    # ---- 8. 进销存 biz 路由 ----
    p = f"{be}/app/api/routes.go"
    s = open(p, encoding="utf-8").read()
    if "/biz/intake" in s:
        skip("routes-biz")
    else:
        anchor = 'r.Put("/trash", chain.ToHandlerFunc(a.handleTrashPut(), userMW...))'
        add = anchor + ("\n\n"
                        "\t\tr.Get(\"/biz/intakes\", chain.ToHandlerFunc(a.handleBizIntakes(), userMW...))\n"
                        "\t\tr.Post(\"/biz/intake\", chain.ToHandlerFunc(a.handleBizIntakeCreate(), userMW...))\n"
                        "\t\tr.Post(\"/biz/intake/rollback\", chain.ToHandlerFunc(a.handleBizIntakeRollback(), userMW...))\n"
                        "\t\tr.Get(\"/biz/outbounds\", chain.ToHandlerFunc(a.handleBizOutbounds(), userMW...))\n"
                        "\t\tr.Post(\"/biz/outbound\", chain.ToHandlerFunc(a.handleBizOutboundCreate(), userMW...))\n"
                        "\t\tr.Post(\"/biz/outbound/rollback\", chain.ToHandlerFunc(a.handleBizOutboundRollback(), userMW...))\n"
                        "\t\tr.Get(\"/biz/shipments\", chain.ToHandlerFunc(a.handleBizShipments(), userMW...))\n"
                        "\t\tr.Post(\"/biz/shipments\", chain.ToHandlerFunc(a.handleBizShipmentCreate(), userMW...))\n"
                        "\t\tr.Post(\"/biz/shipments/ship\", chain.ToHandlerFunc(a.handleBizShipmentShip(), userMW...))\n"
                        "\t\tr.Post(\"/biz/shipments/cancel\", chain.ToHandlerFunc(a.handleBizShipmentCancel(), userMW...))\n"
                        "\t\tr.Post(\"/biz/shipments/undo\", chain.ToHandlerFunc(a.handleBizShipmentUndo(), userMW...))")
        pub_anchor = 'r.Get("/qrcode", chain.ToHandlerFunc(v1Ctrl.HandleGenerateQRCode(), assetMW...))'
        pub_add = pub_anchor + '\n\t\tr.Get("/biz/images/{attachment}", chain.ToHandlerFunc(a.handleBizImage()))\n\t\tr.Get("/biz/images/{attachment}/{thumb}", chain.ToHandlerFunc(a.handleBizImage()))\n\t\tr.Get("/qr", chain.ToHandlerFunc(a.handleQRPublic()))'
        if anchor not in s or pub_anchor not in s:
            fail("routes-biz", "锚点未找到")
        else:
            s = s.replace(anchor, add, 1).replace(pub_anchor, pub_add, 1)
            open(p, "w", encoding="utf-8").write(s)
            done("routes-biz 入库路由 + 公开图片路由")

    # ---- 9. 侧边栏重构（Codex 式分组扁平菜单，整段替换 nav 数组）----
    rep(dv,
        'import MdiCog from "~icons/mdi/cog";',
        'import MdiCog from "~icons/mdi/cog";\n  import MdiClipboardListOutline from "~icons/mdi/clipboard-list-outline";\n  import MdiTruckDeliveryOutline from "~icons/mdi/truck-delivery-outline";\n  import MdiTune from "~icons/mdi/tune";',
        "nav-restructure-icons")
    rep(dv,
        'import MdiTune from "~icons/mdi/tune";',
        'import MdiTune from "~icons/mdi/tune";\n  import MdiCogOutline from "~icons/mdi/cog-outline";',
        "nav-cogoutline-icon")
    rep_any(dv,
        ['import MdiCogOutline from "~icons/mdi/cog-outline";\n  import MdiInboxArrowDown from "~icons/mdi/inbox-arrow-down";\n  import MdiInboxArrowUp from "~icons/mdi/inbox-arrow-up";\n  import MdiAccountMultipleOutline from "~icons/mdi/account-multiple-outline";\n  import MdiEmailOutline from "~icons/mdi/email-outline";\n  import MdiBellOutline from "~icons/mdi/bell-outline";\n  import MdiFormatListBulleted from "~icons/mdi/format-list-bulleted";\n  import MdiPackageVariantClosed from "~icons/mdi/package-variant-closed";\n  import MdiClipboardCheckOutline from "~icons/mdi/clipboard-check-outline";',
         'import MdiCogOutline from "~icons/mdi/cog-outline";\n  import MdiInboxArrowDown from "~icons/mdi/inbox-arrow-down";\n  import MdiInboxArrowUp from "~icons/mdi/inbox-arrow-up";\n  import MdiAccountMultipleOutline from "~icons/mdi/account-multiple-outline";\n  import MdiEmailOutline from "~icons/mdi/email-outline";\n  import MdiBellOutline from "~icons/mdi/bell-outline";\n  import MdiFormatListBulleted from "~icons/mdi/format-list-bulleted";\n  import MdiPackageVariantClosed from "~icons/mdi/package-variant-closed";',
         'import MdiCogOutline from "~icons/mdi/cog-outline";\n  import MdiInboxArrowDown from "~icons/mdi/inbox-arrow-down";\n  import MdiInboxArrowUp from "~icons/mdi/inbox-arrow-up";\n  import MdiAccountMultipleOutline from "~icons/mdi/account-multiple-outline";\n  import MdiEmailOutline from "~icons/mdi/email-outline";\n  import MdiBellOutline from "~icons/mdi/bell-outline";\n  import MdiFormatListBulleted from "~icons/mdi/format-list-bulleted";',
         'import MdiCogOutline from "~icons/mdi/cog-outline";'],
        'import MdiCogOutline from "~icons/mdi/cog-outline";\n  import MdiInboxArrowDown from "~icons/mdi/inbox-arrow-down";\n  import MdiInboxArrowUp from "~icons/mdi/inbox-arrow-up";\n  import MdiAccountMultipleOutline from "~icons/mdi/account-multiple-outline";\n  import MdiEmailOutline from "~icons/mdi/email-outline";\n  import MdiBellOutline from "~icons/mdi/bell-outline";\n  import MdiFormatListBulleted from "~icons/mdi/format-list-bulleted";\n  import MdiPackageVariantClosed from "~icons/mdi/package-variant-closed";\n  import MdiClipboardCheckOutline from "~icons/mdi/clipboard-check-outline";',
        "nav-group-icons")
    rep(dv,
        '    }[];\n  }[] = [',
        '    }[];\n    group?: string;\n  }[] = [',
        "nav-type-group-field")
    nav_body = (
        '    {\n'
        '      icon: MdiClipboardCheckOutline,\n'
        '      id: 900, group: "概览",\n'
        '      active: computed(() => route.path === "/tasks"),\n'
        '      name: computed(() => "待办"),\n'
        '      to: "/tasks",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiMagnify,\n'
        '      id: 3, group: "库存",\n'
        '      active: computed(() => route.path === "/ledger" && route.query.count !== "1"),\n'
        '      name: computed(() => "物品"),\n'
        '      to: "/ledger",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiClipboardListOutline,\n'
        '      id: 905, group: "库存",\n'
        '      active: computed(() => route.path === "/ledger" && route.query.count === "1"),\n'
        '      name: computed(() => "盘点"),\n'
        '      to: "/ledger?count=1",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiInboxArrowDown,\n'
        '      id: 901, group: "进出",\n'
        '      active: computed(() => route.path === "/intake"),\n'
        '      name: computed(() => "入库"),\n'
        '      to: "/intake",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiInboxArrowUp,\n'
        '      id: 902, group: "进出",\n'
        '      active: computed(() => route.path === "/outbound"),\n'
        '      name: computed(() => "出库"),\n'
        '      to: "/outbound",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiPackageVariantClosed,\n'
        '      id: 904, group: "进出",\n'
        '      active: computed(() => route.path === "/ship"),\n'
        '      name: computed(() => "发货"),\n'
        '      to: "/ship",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiTune,\n'
        '      id: 9061, group: "配置",\n'
        '      active: computed(() => route.path === "/collection/fields"),\n'
        '      name: computed(() => "库存架构"),\n'
        '      to: "/collection/fields",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiFormatListBulleted,\n'
        '      id: 9062, group: "配置",\n'
        '      active: computed(() => route.path === "/collection/ui-options"),\n'
        '      name: computed(() => "选项"),\n'
        '      to: "/collection/ui-options",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiTagMultiple,\n'
        '      id: 9063, group: "配置",\n'
        '      active: computed(() => route.path === "/tags"),\n'
        '      name: computed(() => "标签"),\n'
        '      to: "/tags",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiFileTree,\n'
        '      id: 9081, group: "配置",\n'
        '      active: computed(() => route.path === "/collection/entity-types"),\n'
        '      name: computed(() => "结构"),\n'
        '      to: "/collection/entity-types",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiAccountMultipleOutline,\n'
        '      id: 61, group: "管理",\n'
        '      active: computed(() => route.path === "/collection/members"),\n'
        '      name: computed(() => t("collection.tabs.members")),\n'
        '      to: "/collection/members",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiEmailOutline,\n'
        '      id: 62, group: "管理",\n'
        '      active: computed(() => route.path === "/collection/invites"),\n'
        '      name: computed(() => t("collection.tabs.invites")),\n'
        '      to: "/collection/invites",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiBellOutline,\n'
        '      id: 63, group: "管理",\n'
        '      active: computed(() => route.path === "/collection/notifiers"),\n'
        '      name: computed(() => t("collection.tabs.notifiers")),\n'
        '      to: "/collection/notifiers",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiCog,\n'
        '      id: 64, group: "管理",\n'
        '      active: computed(() => route.path === "/collection/settings"),\n'
        '      name: computed(() => t("collection.tabs.settings")),\n'
        '      to: "/collection/settings",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiWrench,\n'
        '      id: 9082, group: "管理",\n'
        '      active: computed(() => route.path === "/collection/tools"),\n'
        '      name: computed(() => "工具"),\n'
        '      to: "/collection/tools",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiAccount,\n'
        '      id: 6, group: "",\n'
        '      active: computed(() => route.path === "/profile"),\n'
        '      name: computed(() => t("menu.profile")),\n'
        '      to: "/profile",\n'
        '    },\n'
    )
    navgroups_src = (
        '\n\n  const navGroups = computed(() => {\n'
        '    const out: { label: string; items: typeof nav }[] = [];\n'
        '    for (const n of nav) {\n'
        '      const g = n.group || "";\n'
        '      if (!out.length || out[out.length - 1].label !== g) out.push({ label: g, items: [] });\n'
        '      out[out.length - 1].items.push(n);\n'
        '    }\n'
        '    return out;\n'
        '  });'
    )
    sidebar_content_new = (
        '<SidebarContent>\n'
        '          <SidebarGroup v-for="g in navGroups" :key="g.label || \'ungrouped\'" class="py-0.5">\n'
        '            <SidebarGroupLabel\n'
        '              v-if="g.label"\n'
        '              class="px-2 pb-1 pt-3 text-xs font-medium tracking-wide text-muted-foreground group-data-[collapsible=icon]:hidden"\n'
        '            >\n'
        '              {{ g.label }}\n'
        '            </SidebarGroupLabel>\n'
        '            <SidebarMenu>\n'
        '              <SidebarMenuItem v-for="n in g.items" :key="n.id">\n'
        '                <SidebarMenuLink\n'
        '                  :href="n.to"\n'
        '                  :class="{\n'
        '                    \'bg-accent text-accent-foreground\': n.active?.value,\n'
        '                    \'text-nowrap\': typeof locale === \'string\' && locale.startsWith(\'zh-\'),\n'
        '                  }"\n'
        '                  :tooltip="n.name.value"\n'
        '                >\n'
        '                  <component :is="n.icon" v-if="n.icon" />\n'
        '                  <span>{{ n.name.value }}</span>\n'
        '                </SidebarMenuLink>\n'
        '              </SidebarMenuItem>\n'
        '            </SidebarMenu>\n'
        '          </SidebarGroup>\n'
        '\n'
        '          <!-- makes scanner accessible easily if using legacy header -->\n'
        '          <SidebarGroup v-if="preferences.displayLegacyHeader">\n'
        '            <SidebarMenu>\n'
        '              <SidebarMenuItem>\n'
        '                <SidebarMenuButton\n'
        '                  :class="{\n'
        '                    \'text-nowrap\': typeof locale === \'string\' && locale.startsWith(\'zh-\'),\n'
        '                  }"\n'
        '                  :tooltip="$t(\'menu.scanner\')"\n'
        '                  @click.prevent="openDialog(DialogID.Scanner)"\n'
        '                >\n'
        '                  <MdiQrcodeScan />\n'
        '                  <span>{{ $t("menu.scanner") }}</span>\n'
        '                </SidebarMenuButton>\n'
        '              </SidebarMenuItem>\n'
        '            </SidebarMenu>\n'
        '          </SidebarGroup>\n'
        '        </SidebarContent>'
    )
    s_nav = open(dv, encoding="utf-8").read()
    if '"库存架构"' in s_nav and "navGroups" in s_nav:
        skip("nav-restructure")
    else:
        marker = "  }[] = ["
        j = s_nav.find(marker)
        if j < 0:
            fail("nav-restructure", "未找到 nav 数组")
        else:
            arr_start = j + len(marker)
            arr_end = s_nav.find("\n  ];", arr_start)
            if arr_end < 0:
                fail("nav-restructure", "未找到 nav 数组结尾")
            else:
                s_nav = s_nav[:arr_start] + "\n" + nav_body.rstrip("\n") + "\n  ];" + s_nav[arr_end + len("\n  ];"):]
        sc_i = s_nav.find("<SidebarContent>")
        sc_j = s_nav.find("</SidebarContent>")
        if sc_i < 0 or sc_j < 0:
            fail("nav-restructure", "未找到 SidebarContent 块")
        else:
            s_nav = s_nav[:sc_i] + sidebar_content_new + s_nav[sc_j + len("</SidebarContent>"):]
        if "navGroups = computed" not in s_nav:
            # navGroups 插在 nav 数组之后（紧跟刚 splice 的数组结尾）
            insert_at = s_nav.find("\n  ];", s_nav.find('group: "概览"'))
            if insert_at < 0:
                fail("nav-restructure", "未找到 navGroups 注入点")
            else:
                s_nav = s_nav[:insert_at + len("\n  ];")] + navgroups_src + s_nav[insert_at + len("\n  ];"):]
        open(dv, "w", encoding="utf-8").write(s_nav)
        done("nav-restructure Codex 式分组扁平菜单")

    # ---- 9a. 侧栏头部瘦身（Codex 式：衬线字标 + 轻量创建按钮）----
    rep(dv,
        '          <SidebarGroupLabel class="text-base group-data-[collapsible=icon]:hidden">{{\n            $t("global.welcome", { username: username })\n          }}</SidebarGroupLabel>',
        '          <div class="w-full px-2 pb-1 pt-2 group-data-[collapsible=icon]:hidden">\n            <span class="font-display text-lg font-medium tracking-tight">Groza</span>\n          </div>',
        "sidebar-wordmark")
    rep(dv,
        '          <NuxtLink class="group-data-[collapsible=icon]:hidden" to="/home">\n            <div class="flex size-24 items-center justify-center rounded-full bg-background-accent p-4">\n              <AppLogo />\n            </div>\n          </NuxtLink>\n',
        '',
        "sidebar-logo-rm")
    rep(dv,
        'class="flex justify-center bg-primary text-primary-foreground drop-shadow-md hover:bg-primary/90 active:bg-primary/90 active:text-primary-foreground group-data-[collapsible=icon]:justify-start"',
        'class="h-9 w-full justify-start gap-2 border border-input bg-background hover:bg-accent"',
        "sidebar-create-btn")
    # 移动顶栏：去投影改发丝线
    rep(dv,
        'flex-col bg-secondary p-2 shadow-md sm:h-[var(--header-height)]',
        'flex-col border-b bg-background/95 p-2 backdrop-blur sm:h-[var(--header-height)]',
        "mobile-header-hairline")
    # 顶栏图标去黑块：SidebarTrigger 回退 ghost（图标色改 current），搜索/扫码改 outline
    rep(f"{fe}/components/ui/sidebar/SidebarTrigger.vue",
        '<MdiMenu class="text-primary-foreground" />',
        '<MdiMenu class="text-current" />',
        "trigger-icon-current")
    rep(dv,
        '<SidebarTrigger class="absolute left-2 top-2 hidden lg:flex" variant="default" />',
        '<SidebarTrigger class="absolute left-2 top-2 hidden lg:flex" />',
        "trigger-ghost-legacy")
    rep(dv,
        '<SidebarTrigger variant="default" />',
        '<SidebarTrigger />',
        "trigger-ghost-mobile")
    rep(dv,
        '<Button size="icon" @click="triggerSearch">',
        '<Button size="icon" variant="outline" @click="triggerSearch">',
        "header-search-outline")
    rep(dv,
        '<Button size="icon" @click="openScanner">',
        '<Button size="icon" variant="outline" @click="openScanner">',
        "header-scan-outline")
    # 移除页脚开发信息（版本号/构建号/API 链接）
    rep(dv,
        '          <footer v-if="status" class="bottom-0 w-full pb-4 text-center">\n            <p class="text-center text-sm">\n              <span\n                v-html="\n                  DOMPurify.sanitize(\n                    $t(\'global.footer.version_link\', {\n                      version: status.build.version.replace(/^v/, \'\'),\n                      build: status.build.commit,\n                    })\n                  )\n                "\n              />\n              ~\n              <span v-html="DOMPurify.sanitize($t(\'global.footer.api_link\'))" />\n            </p>\n          </footer>\n',
        '',
        "footer-dev-info-rm")
    rep(f"{fe}/pages/index.vue",
        '    <footer v-if="status" class="bottom-0 mt-auto w-full pb-4 text-center">\n      <p class="text-center text-sm">\n        {{ $t("global.version", { version: status.build.version }) }} ~\n        {{ $t("global.build", { build: status.build.commit }) }}\n      </p>\n    </footer>\n',
        '',
        "login-footer-dev-info-rm")
    # 我的页注入「最近变更」卡片（读 /api/v1/audit）；哨兵防重复注入（锚点注入后仍在文中）
    _prof = f"{fe}/pages/profile.vue"
    _prof_s = open(_prof, encoding="utf-8").read()
    if "recentChanges" in _prof_s:
        skip("profile-audit-script")
    else:
        rep(_prof,
            '  const { t } = useI18n();',
            '  const { t } = useI18n();\n  const $gx = useNuxtApp().$gxFetch as typeof globalThis.$fetch;\n  const recentChanges = ref<Array<Record<string, any>>>([]);\n  function actLabel(a: string): string {\n    const m: Record<string, string> = { "intake.create": "入库", "intake.rollback": "回滚入库", "outbound.create": "出库", "outbound.rollback": "回滚出库", "ledger.field_patch": "修改字段", "trash2.mark": "标记删除", "trash2.purge": "彻底删除", "gx.bulk_apply": "批量修改" };\n    return m[a] || a;\n  }\n  function dtGx(ts: string): string { return String(ts || "").slice(5, 16).replace("T", " "); }\n  onMounted(async () => {\n    try {\n      const a = await $gx<Array<Record<string, any>>>("/api/v1/audit", { params: { limit: 12 } });\n      recentChanges.value = Array.isArray(a) ? a : ((a as any).entries || []);\n    } catch (_e) { /* ignore */ }\n  });',
            "profile-audit-script")
    rep(f"{fe}/pages/profile.vue",
        '      <BaseCard>\n        <template #title>\n          <BaseSectionHeader>\n            <MdiDelete class="-mt-1 mr-2" />',
        '      <BaseCard>\n        <template #title>\n          <BaseSectionHeader>\n            <span> 最近变更 </span>\n            <template #description> 最近 12 条库存操作记录 </template>\n          </BaseSectionHeader>\n        </template>\n        <div class="px-4 pb-4">\n          <div v-if="!recentChanges.length" class="py-4 text-center text-sm text-muted-foreground">暂无记录</div>\n          <div v-else class="divide-y text-sm">\n            <div v-for="(r, i) in recentChanges" :key="i" class="flex items-center gap-2 py-1.5">\n              <span class="w-24 shrink-0 text-xs tabular-nums text-muted-foreground">{{ dtGx(r.ts) }}</span>\n              <span class="rounded bg-muted px-1.5 py-0.5 text-xs">{{ actLabel(r.action) }}</span>\n              <span class="min-w-0 flex-1 truncate text-muted-foreground">{{ r.name || r.supplier || r.entityId || r.intakeId || r.outboundId || "" }}</span>\n            </div>\n          </div>\n        </div>\n      </BaseCard>\n\n      <BaseCard>\n        <template #title>\n          <BaseSectionHeader>\n            <MdiDelete class="-mt-1 mr-2" />',
        "profile-audit-card")
    # 主题设置：ThemePicker（30+ daisyUI 主题会覆盖 Groza 配色）→ 外观/大字号开关
    _prof_s = open(_prof, encoding="utf-8").read()
    if "setGxTheme" in _prof_s:
        skip("profile-theme-toggles-script")
    else:
        rep(_prof,
            '  const { t } = useI18n();\n  const $gx = useNuxtApp().$gxFetch as typeof globalThis.$fetch;',
            '  const { t } = useI18n();\n  const gxTheme = ref("");\n  const bigfont = ref(false);\n  try {\n    gxTheme.value = localStorage.getItem("groza.theme") || "";\n    bigfont.value = localStorage.getItem("groza.bigfont") === "1";\n  } catch (_e) { /* ignore */ }\n  function setGxTheme(v: string) {\n    gxTheme.value = v;\n    try {\n      if (v) { localStorage.setItem("groza.theme", v); document.documentElement.setAttribute("data-gx-theme", v); }\n      else { localStorage.removeItem("groza.theme"); document.documentElement.removeAttribute("data-gx-theme"); }\n    } catch (_e) { /* ignore */ }\n  }\n  function toggleBigfont() {\n    bigfont.value = !bigfont.value;\n    try {\n      localStorage.setItem("groza.bigfont", bigfont.value ? "1" : "0");\n      document.documentElement.style.fontSize = bigfont.value ? "18px" : "";\n    } catch (_e) { /* ignore */ }\n  }\n  const $gx = useNuxtApp().$gxFetch as typeof globalThis.$fetch;',
            "profile-theme-toggles-script")
    rep(f"{fe}/pages/profile.vue",
        '          <ThemePicker />',
        '          <div class="flex flex-wrap items-center gap-x-4 gap-y-2">\n            <span class="text-sm text-muted-foreground">外观</span>\n            <div class="flex gap-1 rounded-xl border bg-card p-1">\n              <button\n                v-for="o in [[\'\', \'跟随系统\'], [\'light\', \'浅色\'], [\'dark\', \'深色\']]"\n                :key="o[0]"\n                class="rounded-lg px-2.5 py-1 text-sm transition"\n                :class="gxTheme === o[0] ? \'bg-primary text-primary-foreground\' : \'hover:bg-muted\'"\n                @click="setGxTheme(o[0])"\n              >\n                {{ o[1] }}\n              </button>\n            </div>\n            <span class="text-sm text-muted-foreground">大字号</span>\n            <button\n              class="rounded-lg border px-2.5 py-1 text-sm transition"\n              :class="bigfont ? \'bg-primary text-primary-foreground\' : \'hover:bg-muted\'"\n              @click="toggleBigfont"\n            >\n              {{ bigfont ? "已开启" : "已关闭" }}\n            </button>\n          </div>',
        "profile-theme-toggles-ui")

    # 默认落地页：/home -> /tasks（待办）
    rep(f"{fe}/pages/index.vue", 'return "/home";', 'return "/tasks";', "landing-home-to-tasks")
    rep(f"{fe}/pages/index.vue",
        'navigateTo(redirectTo.value || "/home");',
        'navigateTo(redirectTo.value || "/tasks");',
        "landing-redirect-to-tasks")

    # ---- 9b. 移动端底部 Dock：已移除（与汉堡抽屉菜单功能冗余）----
    # 历史版本曾注入 Dock；这里做反向补丁：无论目录里是 pristine 还是任何历史 Dock 变体，统一恢复为 pristine。
    rep_any(dv,
        ['<SidebarInset class="min-h-dvh max-w-full overflow-hidden bg-background-accent">\n        <div class="relative flex h-full flex-col justify-center pb-16 lg:pb-0">',
         '<SidebarInset class="min-h-dvh max-w-full overflow-hidden bg-background-accent">\n        <div class="relative flex h-full flex-col justify-center">'],
        '<SidebarInset class="min-h-dvh max-w-full overflow-hidden bg-background-accent">\n        <div class="relative flex h-full flex-col justify-center">',
        "mobile-dock-padding-remove")
    dock_old = '        </div>\n      </SidebarInset>'
    dock_v1 = (
        '        </div>\n'
        '        <nav class="fixed inset-x-0 bottom-0 z-40 flex items-stretch justify-around border-t bg-card/95 backdrop-blur lg:hidden" style="padding-bottom: env(safe-area-inset-bottom)">\n'
        '          <NuxtLink to="/tasks" class="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]" :class="route.path === \'/tasks\' ? \'text-primary\' : \'text-muted-foreground\'"><MdiClipboardCheckOutline class="h-5 w-5" /><span>待办</span></NuxtLink>\n'
        '          <NuxtLink to="/ledger" class="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]" :class="route.path === \'/ledger\' ? \'text-primary\' : \'text-muted-foreground\'"><MdiMagnify class="h-5 w-5" /><span>物品</span></NuxtLink>\n'
        '          <NuxtLink to="/intake" class="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]" :class="[\'/intake\', \'/outbound\', \'/documents\'].includes(route.path) ? \'text-primary\' : \'text-muted-foreground\'"><MdiTruckDeliveryOutline class="h-5 w-5" /><span>进出</span></NuxtLink>\n'
        '          <NuxtLink to="/collection/fields" class="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]" :class="(route.path.startsWith(\'/collection\') || route.path === \'/tags\') ? \'text-primary\' : \'text-muted-foreground\'"><MdiTune class="h-5 w-5" /><span>配置</span></NuxtLink>\n'
        '          <NuxtLink to="/profile" class="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]" :class="route.path === \'/profile\' ? \'text-primary\' : \'text-muted-foreground\'"><MdiAccount class="h-5 w-5" /><span>我的</span></NuxtLink>\n'
        '        </nav>\n'
        '      </SidebarInset>'
    )
    def dock_item(to, active_expr, icon, label):
        return (
            '          <NuxtLink to="' + to + '" class="flex flex-1 flex-col items-center gap-0.5 py-1.5 text-[11px] transition-colors" :class="'
            + active_expr + ' ? \'text-foreground\' : \'text-muted-foreground\'"><span class="rounded-full px-3 py-0.5 transition-colors" :class="'
            + active_expr + ' ? \'bg-accent\' : \'\'"><' + icon + ' class="h-5 w-5" /></span><span>' + label + '</span></NuxtLink>\n'
        )
    dock_head = (
        '        </div>\n'
        '        <nav class="fixed inset-x-0 bottom-0 z-40 flex items-stretch justify-around border-t bg-card/95 backdrop-blur lg:hidden" style="padding-bottom: env(safe-area-inset-bottom)">\n'
    )
    dock_tail = '        </nav>\n      </SidebarInset>'
    dock_v2 = (
        dock_head
        + dock_item("/tasks", "route.path === '/tasks'", "MdiClipboardCheckOutline", "待办")
        + dock_item("/ledger", "route.path === '/ledger'", "MdiMagnify", "物品")
        + dock_item("/intake", "['/intake', '/outbound', '/documents'].includes(route.path)", "MdiTruckDeliveryOutline", "进出")
        + dock_item("/collection/fields", "(route.path.startsWith('/collection') || route.path === '/tags')", "MdiTune", "配置")
        + dock_item("/profile", "route.path === '/profile'", "MdiAccount", "我的")
        + dock_tail
    )
    dock_prev = (  # 历史版本：单据页时代的 dock_new（发货台取代前的磁盘残留）
        dock_head
        + dock_item("/tasks", "route.path === '/tasks'", "MdiClipboardCheckOutline", "待办")
        + dock_item("/ledger", "route.path === '/ledger'", "MdiMagnify", "物品")
        + dock_item("/intake", "['/intake', '/outbound', '/documents'].includes(route.path)", "MdiTruckDeliveryOutline", "进出")
        + dock_item("/collection/fields", "(route.path.startsWith('/collection') || route.path === '/tags')", "MdiCogOutline", "管理")
        + dock_item("/profile", "route.path === '/profile'", "MdiAccount", "我的")
        + dock_tail
    )
    dock_new = (
        dock_head
        + dock_item("/tasks", "route.path === '/tasks'", "MdiClipboardCheckOutline", "待办")
        + dock_item("/ledger", "route.path === '/ledger'", "MdiMagnify", "物品")
        + dock_item("/intake", "['/intake', '/outbound', '/ship'].includes(route.path)", "MdiTruckDeliveryOutline", "进出")
        + dock_item("/collection/fields", "(route.path.startsWith('/collection') || route.path === '/tags')", "MdiCogOutline", "管理")
        + dock_item("/profile", "route.path === '/profile'", "MdiAccount", "我的")
        + dock_tail
    )
    rep_any(dv, [dock_new, dock_prev, dock_v2, dock_v1], dock_old, "mobile-dock-remove", "Dock 移除（导航统一走汉堡抽屉）")

    # ---- 9c. ⌘K 命令面板（Claude 式统一入口）----
    qm = f"{fe}/components/App/QuickMenuModal.vue"
    rep(qm,
        'useDialogHotkey(DialogID.QuickMenu, { code: "Backquote", ctrl: true });',
        'useDialogHotkey(DialogID.QuickMenu, { code: "KeyK", ctrl: true });',
        "cmdk-hotkey")
    rep(qm,
        ":placeholder=\"t('components.quick_menu.shortcut_hint')\"",
        ":placeholder=\"'搜索页面 / 执行操作…  Ctrl+K'\"",
        "cmdk-placeholder")
    rep(qm,
        ':value="`global.navigate_${i + 1}`"',
        ':value="navigate.text"',
        "cmdk-navigate-value")
    nav_old = (
        '    ...nav.map(v => ({\n'
        '      text: computed(() => v.name.value),\n'
        '      href: v.to,\n'
        '      type: "navigate" as const,\n'
        '    })),')
    nav_new = (
        '    ...nav.flatMap(v => [\n'
        '      { text: computed(() => v.name.value), href: v.to, type: "navigate" as const },\n'
        '      ...(v.collapsible || []).map(c => ({ text: computed(() => c.name.value), href: c.to, type: "navigate" as const })),\n'
        '    ]),')
    rep(dv, nav_old, nav_new, "cmdk-nav-children")

    # ---- 10. 模板模块：保留字段类型 + 可选类型 + 移动友好 + 并入集合 ----
    # (a) CreateModal：允许选类型，字段行移动友好
    rep(f"{fe}/components/Template/CreateModal.vue",
        '    fields: [] as Array<{ id: string; name: string; type: "text"; textValue: string }>,',
        '    fields: [] as Array<{ id: string; name: string; type: string; textValue: string }>,',
        "tpl-create-type-ts")
    cm_old = '''      <div v-if="form.fields.length > 0" class="flex flex-col gap-2">
        <div v-for="(field, idx) in form.fields" :key="idx" class="flex items-end gap-2">
          <FormTextField
            v-model="field.name"
            :label="$t('components.template.form.field_name')"
            :max-length="255"
            class="flex-1"
          />
          <FormTextField
            v-model="field.textValue"
            :label="$t('components.template.form.default_value')"
            class="flex-1"
          />
          <Button type="button" size="icon" variant="ghost" @click="form.fields.splice(idx, 1)">
            <MdiDelete class="size-4" />
          </Button>
        </div>
      </div>'''
    cm_new = '''      <div v-if="form.fields.length > 0" class="flex flex-col gap-2">
        <div v-for="(field, idx) in form.fields" :key="idx" class="flex flex-wrap items-end gap-2 rounded-lg border p-2">
          <FormTextField
            v-model="field.name"
            :label="$t('components.template.form.field_name')"
            :max-length="255"
            class="min-w-[8rem] flex-1"
          />
          <label class="flex flex-col gap-1 text-xs text-muted-foreground">类型
            <select v-model="field.type" class="h-9 rounded-lg border bg-background px-2 text-sm">
              <option value="text">文本</option>
              <option value="number">数字</option>
              <option value="boolean">开关</option>
            </select>
          </label>
          <FormTextField
            v-if="field.type === 'text'"
            v-model="field.textValue"
            :label="$t('components.template.form.default_value')"
            class="min-w-[8rem] flex-1"
          />
          <span v-else class="pb-2 text-xs text-muted-foreground">默认值暂仅支持文本</span>
          <Button type="button" size="icon" variant="ghost" @click="form.fields.splice(idx, 1)">
            <MdiDelete class="size-4" />
          </Button>
        </div>
      </div>'''
    rep(f"{fe}/components/Template/CreateModal.vue", cm_old, cm_new, "tpl-create-fields-mobile")

    # (b) 模板详情/编辑：保留类型（修 bug）+ 可选类型 + 移动友好
    rep(f"{fe}/pages/template/[id].vue",
        '    fields: [] as Array<{ id: string; name: string; type: "text"; textValue: string }>,',
        '    fields: [] as Array<{ id: string; name: string; type: string; textValue: string }>,',
        "tpl-edit-type-ts")
    rep(f"{fe}/pages/template/[id].vue",
        '''      fields: template.value.fields.map(f => ({
        id: f.id,
        name: f.name,
        type: "text" as const,
        textValue: f.textValue,
      })),''',
        '''      fields: template.value.fields.map(f => ({
        id: f.id,
        name: f.name,
        type: f.type || "text",
        textValue: f.textValue ?? "",
      })),''',
        "tpl-edit-preserve-type")
    id_old = '''        <div v-if="updateData.fields.length > 0" class="flex flex-col gap-2">
          <div v-for="(field, idx) in updateData.fields" :key="idx" class="flex items-end gap-2">
            <FormTextField
              v-model="field.name"
              :label="$t('components.template.form.field_name')"
              :max-length="255"
              class="flex-1"
            />
            <FormTextField
              v-model="field.textValue"
              :label="$t('components.template.form.default_value')"
              class="flex-1"
            />
            <Button type="button" size="icon" variant="ghost" @click="updateData.fields.splice(idx, 1)">
              <MdiDelete class="size-4" />
            </Button>
          </div>
        </div>'''
    id_new = '''        <div v-if="updateData.fields.length > 0" class="flex flex-col gap-2">
          <div v-for="(field, idx) in updateData.fields" :key="idx" class="flex flex-wrap items-end gap-2 rounded-lg border p-2">
            <FormTextField
              v-model="field.name"
              :label="$t('components.template.form.field_name')"
              :max-length="255"
              class="min-w-[8rem] flex-1"
            />
            <label class="flex flex-col gap-1 text-xs text-muted-foreground">类型
              <select v-model="field.type" class="h-9 rounded-lg border bg-background px-2 text-sm">
                <option value="text">文本</option>
                <option value="number">数字</option>
                <option value="boolean">开关</option>
              </select>
            </label>
            <FormTextField
              v-if="field.type === 'text'"
              v-model="field.textValue"
              :label="$t('components.template.form.default_value')"
              class="min-w-[8rem] flex-1"
            />
            <span v-else class="pb-2 text-xs text-muted-foreground">默认值暂仅支持文本</span>
            <Button type="button" size="icon" variant="ghost" @click="updateData.fields.splice(idx, 1)">
              <MdiDelete class="size-4" />
            </Button>
          </div>
        </div>'''
    rep(f"{fe}/pages/template/[id].vue", id_old, id_new, "tpl-edit-fields-mobile")
    rep(f"{fe}/pages/template/[id].vue",
        '    toast.success(t("components.template.toast.updated"));\n    template.value = data;',
        '    toast.success(t("components.template.toast.updated"));\n    try {\n      const _sr = await $fetch<Record<string, any>>("/api/v1/ledger/sync-fields", { method: "POST", body: {} });\n      if (_sr && typeof _sr.updated === "number") toast.success("已应用到 " + _sr.updated + " 件物品");\n    } catch (_e) { /* ignore */ }\n    template.value = data;',
        "tpl-sync-on-save")

    # ---- 12. 统一集合各 tab 布局 ----
    rep(f"{fe}/pages/collection/index/tools.vue",
        '    <BaseContainer class="m-0 flex flex-col gap-4 px-0">',
        '    <div class="flex flex-col gap-4">',
        "collection-tools-container-open")
    p_tools = f"{fe}/pages/collection/index/tools.vue"
    ts = open(p_tools, encoding="utf-8").read()
    if "    </BaseContainer>" in ts:
        open(p_tools, "w", encoding="utf-8").write(ts.replace("    </BaseContainer>", "    </div>", 1))
        done("collection-tools-container-close")
    else:
        skip("collection-tools-container-close")
    rep(f"{fe}/pages/collection/index/entity-types.vue",
        '<template>\n  <div>\n    <!-- Create Dialog -->',
        '<template>\n  <div class="space-y-4">\n    <!-- Create Dialog -->',
        "collection-entity-types-space")

    # ---- 11. 模板编辑去弹框：/templates 与 /template/{id} 重定向到字段页；集合 tab 手机显示文字 ----
    redir_old = '  definePageMeta({\n    middleware: ["auth"],\n  });'
    redir_new = '  definePageMeta({\n    middleware: ["auth", () => navigateTo("/collection/fields", { replace: true })],\n  });'
    rep(f"{fe}/pages/templates.vue", redir_old, redir_new, "tpl-list-redirect")
    rep(f"{fe}/pages/template/[id].vue", redir_old, redir_new, "tpl-detail-redirect")
    rep(f"{fe}/pages/collection/index.vue",
        '              <span class="hidden sm:block">{{ t(tab.label) }}</span>',
        '              <span class="block">{{ t(tab.label) }}</span>',
        "collection-tabs-label-mobile")

    if FAILS:
        print(f"\n共 {len(FAILS)} 个补丁失败: {', '.join(FAILS)}", file=sys.stderr)
        sys.exit(2)
    print("\n全部补丁完成")

if __name__ == "__main__":
    main()
