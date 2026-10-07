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
    if new in s:
        skip(name)
        return
    if old not in s:
        fail(name, "锚点未找到（上游代码可能已变化，请人工更新补丁）")
        return
    open(path, "w", encoding="utf-8").write(s.replace(old, new, 1))
    done(name if not done_msg else f"{name} -> {done_msg}")


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
    j = s.find("--radius: 0.5rem;", i)
    if j < 0:
        fail("theme-colors", "未找到 radius 锚点")
        return
    end = j + len("--radius: 0.5rem;")
    if "222 47% 45%" in s[i:end]:
        skip("theme-colors")
        return
    new = """:root,.homebox {
    --background: 0 0% 100%;
    --background-accent: 220 20% 90%;
    --foreground: 222 30% 14%;
    --primary: 222 47% 45%;
    --primary-foreground: 210 40% 98%;
    --secondary: 222 26% 20%;
    --secondary-foreground: 210 30% 92%;
    --accent: 222 45% 95%;
    --accent-foreground: 222 40% 25%;
    --muted: 220 14% 94%;
    --muted-foreground: 220 10% 42%;
    --card: 0 0% 100%;
    --card-foreground: 222 30% 14%;
    --popover: 0 0% 100%;
    --popover-foreground: 222 30% 14%;
    --destructive: 0 72% 51%;
    --destructive-foreground: 0 0% 100%;
    --input: 220 13% 86%;
    --border: 220 13% 88%;
    --ring: 222 47% 45%;
    --sidebar-background: 220 20% 96%;
    --sidebar-foreground: 222 30% 14%;
    --sidebar-primary: 222 47% 45%;
    --sidebar-primary-foreground: 210 40% 98%;
    --sidebar-accent: 220 20% 90%;
    --sidebar-accent-foreground: 222 30% 14%;
    --sidebar-border: 220 13% 88%;
    --sidebar-ring: 222 47% 45%;
    --radius: 0.6rem;"""
    open(p, "w", encoding="utf-8").write(s[:i] + new + s[end:])
    done("theme-colors Groza 配色（靛蓝/石板风暴风）")


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
    if "prefers-color-scheme: dark" in s:
        skip("dark-mode")
        return
    dark = """

/* Groza 深色主题（跟随系统 prefers-color-scheme）。未放入 @layer base，优先级高于所有分层主题。*/
@media (prefers-color-scheme: dark) {
  :root {
    --background: 222 22% 11%;
    --background-accent: 222 18% 16%;
    --foreground: 210 30% 92%;
    --primary: 217 70% 60%;
    --primary-foreground: 222 47% 11%;
    --secondary: 222 25% 18%;
    --secondary-foreground: 210 30% 92%;
    --accent: 222 30% 22%;
    --accent-foreground: 210 30% 92%;
    --muted: 222 20% 20%;
    --muted-foreground: 215 20% 68%;
    --card: 222 22% 14%;
    --card-foreground: 210 30% 92%;
    --popover: 222 22% 14%;
    --popover-foreground: 210 30% 92%;
    --destructive: 0 62% 50%;
    --destructive-foreground: 0 0% 100%;
    --input: 222 18% 26%;
    --border: 222 18% 24%;
    --ring: 217 70% 60%;
    --sidebar-background: 222 25% 10%;
    --sidebar-foreground: 210 30% 90%;
    --sidebar-primary: 217 70% 60%;
    --sidebar-primary-foreground: 222 47% 11%;
    --sidebar-accent: 222 25% 18%;
    --sidebar-accent-foreground: 210 30% 92%;
    --sidebar-border: 222 18% 24%;
    --sidebar-ring: 217 70% 60%;
  }
}
"""
    open(p, "a", encoding="utf-8").write(dark)
    done("dark-mode 深色跟随系统")


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
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    done("menu-zh 菜单统一中文")

    # ---- 2c. 品牌与配色：Groza ----
    rep(f"{fe}/nuxt.config.ts",
        'name: "Homebox",\n      short_name: "Homebox",',
        'name: "Groza",\n      short_name: "Groza",',
        "pwa-name-groza")
    rep(f"{fe}/layouts/default.vue",
        '<AppHeaderText class="h-6" />',
        '<span class="text-xl font-bold tracking-tight text-secondary-foreground">Groza</span>',
        "brand-header-groza")
    rep(f"{fe}/pages/index.vue",
        'title: "HomeBox | " + t("index.title"),',
        'title: "Groza | " + t("index.title"),',
        "brand-login-title")
    patch_colors(fe)
    rebrand_locale(fe)
    patch_dark(fe)
    # 大字号：set-theme.js 启动即应用（跟随本地偏好）
    p_theme = f"{fe}/public/set-theme.js"
    try:
        ts = open(p_theme, encoding="utf-8").read()
        if "groza.bigfont" not in ts:
            ts += '\ntry { if (localStorage.getItem("groza.bigfont") === "1") { document.documentElement.style.fontSize = "18px"; } } catch (e) {}\n'
            open(p_theme, "w", encoding="utf-8").write(ts)
            done("bigfont-boot")
        else:
            skip("bigfont-boot")
    except OSError:
        fail("bigfont-boot", "set-theme.js 不可读")
    rep(f"{fe}/app.vue",
        '<Meta name="theme-color" content="#5b7f67" />',
        '<Meta name="theme-color" content="#2f3e7e" media="(prefers-color-scheme: light)" />\n      <Meta name="theme-color" content="#111725" media="(prefers-color-scheme: dark)" />',
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
    rep(f"{fe}/app.vue",
        '<Link rel="mask-icon" href="/mask-icon.svg" color="#5b7f67" />',
        '<Link rel="mask-icon" href="/mask-icon.svg" color="#2f3e7e" />',
        "mask-icon-color")

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

    # ---- 4. 侧边栏折叠样式两处 ----
    rep(dv,
        'class="flex size-12 items-center justify-center"',
        'class="flex size-12 items-center justify-center group-data-[collapsible=icon]:hidden"',
        "nav-collapsible-trigger-hidden")
    rep(dv,
        '<SidebarMenuItem class="flex gap-1">',
        '<SidebarMenuItem class="flex min-w-0 gap-1">',
        "nav-collapsible-row-minw")

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
                            '      label: "选项配置",\n'
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

    # 集合页「分类」tab（指向 /locations）
    rep(coll,
        '  import MdiTune from "~icons/mdi/tune";',
        '  import MdiTune from "~icons/mdi/tune";\n  import MdiFileTree from "~icons/mdi/file-tree";',
        "collection-locations-icon")
    rep(coll,
        '    {\n      id: "ui-options",\n      label: "选项配置",\n      to: "/collection/ui-options",\n      icon: MdiTune,\n    },',
        '    {\n      id: "ui-options",\n      label: "选项配置",\n      to: "/collection/ui-options",\n      icon: MdiTune,\n    },\n    {\n      id: "locations",\n      label: "分类",\n      to: "/locations",\n      icon: MdiFileTree,\n    },',
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
    rep(coll,
        '      id: "fields",\n      label: "字段",\n      to: "/templates",',
        '      id: "fields",\n      label: "配置",\n      to: "/collection/fields",',
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
                        "\t\tr.Post(\"/biz/outbound/rollback\", chain.ToHandlerFunc(a.handleBizOutboundRollback(), userMW...))")
        pub_anchor = 'r.Get("/qrcode", chain.ToHandlerFunc(v1Ctrl.HandleGenerateQRCode(), assetMW...))'
        pub_add = pub_anchor + '\n\t\tr.Get("/biz/images/{attachment}", chain.ToHandlerFunc(a.handleBizImage()))\n\t\tr.Get("/biz/images/{attachment}/{thumb}", chain.ToHandlerFunc(a.handleBizImage()))\n\t\tr.Get("/qr", chain.ToHandlerFunc(a.handleQRPublic()))'
        if anchor not in s or pub_anchor not in s:
            fail("routes-biz", "锚点未找到")
        else:
            s = s.replace(anchor, add, 1).replace(pub_anchor, pub_add, 1)
            open(p, "w", encoding="utf-8").write(s)
            done("routes-biz 入库路由 + 公开图片路由")

    # ---- 9. 侧边栏重构（以「库存维护」为中心，整段替换 nav 数组）----
    rep(dv,
        'import MdiCog from "~icons/mdi/cog";',
        'import MdiCog from "~icons/mdi/cog";\n  import MdiClipboardListOutline from "~icons/mdi/clipboard-list-outline";\n  import MdiTruckDeliveryOutline from "~icons/mdi/truck-delivery-outline";\n  import MdiTune from "~icons/mdi/tune";',
        "nav-restructure-icons")
    nav_body = (
        '    {\n'
        '      icon: MdiClipboardCheckOutline,\n'
        '      id: 900,\n'
        '      active: computed(() => route.path === "/tasks"),\n'
        '      name: computed(() => "待办"),\n'
        '      to: "/tasks",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiMagnify,\n'
        '      id: 3,\n'
        '      active: computed(() => route.path === "/ledger"),\n'
        '      name: computed(() => "物品"),\n'
        '      to: "/ledger",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiClipboardListOutline,\n'
        '      id: 905,\n'
        '      active: computed(() => route.path === "/ledger" && route.query.count === "1"),\n'
        '      name: computed(() => "盘点"),\n'
        '      to: "/ledger?count=1",\n'
        '    },\n'
        '    {\n'
        '      icon: MdiTruckDeliveryOutline,\n'
        '      id: 903,\n'
        '      active: computed(() => ["/intake", "/outbound", "/documents"].includes(route.path)),\n'
        '      name: computed(() => "进出"),\n'
        '      to: "/intake",\n'
        '      collapsible: [\n'
        '        { id: 901, active: computed(() => route.path === "/intake"), name: computed(() => "入库"), to: "/intake" },\n'
        '        { id: 902, active: computed(() => route.path === "/outbound"), name: computed(() => "出库"), to: "/outbound" },\n'
        '        { id: 904, active: computed(() => route.path === "/documents"), name: computed(() => "单据"), to: "/documents" },\n'
        '      ],\n'
        '    },\n'
        '    {\n'
        '      icon: MdiTune,\n'
        '      id: 907,\n'
        '      active: computed(() => ["/collection/fields", "/collection/ui-options", "/tags", "/collection/entity-types", "/collection/tools"].includes(route.path)),\n'
        '      name: computed(() => "库存配置"),\n'
        '      to: "/collection/fields",\n'
        '      collapsible: [\n'
        '        { id: 9061, active: computed(() => route.path === "/collection/fields"), name: computed(() => "字段 / 位置 / 媒体 / 组织"), to: "/collection/fields" },\n'
        '        { id: 9062, active: computed(() => route.path === "/collection/ui-options"), name: computed(() => "选项配置"), to: "/collection/ui-options" },\n'
        '        { id: 9063, active: computed(() => route.path === "/tags"), name: computed(() => "标签"), to: "/tags" },\n'
        '        { id: 9064, active: computed(() => route.path === "/collection/entity-types"), name: computed(() => "结构"), to: "/collection/entity-types" },\n'
        '        { id: 9065, active: computed(() => route.path === "/collection/tools"), name: computed(() => "工具"), to: "/collection/tools" },\n'
        '      ],\n'
        '    },\n'
        '    {\n'
        '      icon: MdiCog,\n'
        '      id: 7,\n'
        '      active: computed(() => ["/collection/members", "/collection/invites", "/collection/notifiers", "/collection/settings"].includes(route.path)),\n'
        '      name: computed(() => "设置"),\n'
        '      to: "/collection/members",\n'
        '      collapsible: [\n'
        '        { id: 61, active: computed(() => route.path === "/collection/members"), name: computed(() => t("collection.tabs.members")), to: "/collection/members" },\n'
        '        { id: 62, active: computed(() => route.path === "/collection/invites"), name: computed(() => t("collection.tabs.invites")), to: "/collection/invites" },\n'
        '        { id: 63, active: computed(() => route.path === "/collection/notifiers"), name: computed(() => t("collection.tabs.notifiers")), to: "/collection/notifiers" },\n'
        '        { id: 64, active: computed(() => route.path === "/collection/settings"), name: computed(() => t("collection.tabs.settings")), to: "/collection/settings" },\n'
        '      ],\n'
        '    },\n'
        '    {\n'
        '      icon: MdiAccount,\n'
        '      id: 6,\n'
        '      active: computed(() => route.path === "/profile"),\n'
        '      name: computed(() => t("menu.profile")),\n'
        '      to: "/profile",\n'
        '    },\n'
    )
    s_nav = open(dv, encoding="utf-8").read()
    if 'name: computed(() => "进出")' in s_nav:
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
                open(dv, "w", encoding="utf-8").write(s_nav)
                done("nav-restructure 库存维护为中心")

    # 默认落地页：/home -> /tasks（待办）
    rep(f"{fe}/pages/index.vue", 'return "/home";', 'return "/tasks";', "landing-home-to-tasks")
    rep(f"{fe}/pages/index.vue",
        'navigateTo(redirectTo.value || "/home");',
        'navigateTo(redirectTo.value || "/tasks");',
        "landing-redirect-to-tasks")

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
