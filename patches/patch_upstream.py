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
    if new in s and old not in s:
        skip(name)
        return
    if old not in s:
        fail(name, "锚点未找到（上游代码可能已变化，请人工更新补丁）")
        return
    open(path, "w", encoding="utf-8").write(s.replace(old, new, 1))
    done(name if not done_msg else f"{name} -> {done_msg}")

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

    # ---- 3. 侧边栏：/items 菜单并入 /ledger ----
    dv = f"{fe}/layouts/default.vue"
    rep(dv,
        'import MdiMagnify from "~icons/mdi/magnify";',
        'import MdiMagnify from "~icons/mdi/magnify";\n  import MdiCashMultiple from "~icons/mdi/cash-multiple";',
        "nav-sell-icon-import")
    old_items = ('    {\n'
                 '      icon: MdiMagnify,\n'
                 '      id: 3,\n'
                 '      active: computed(() => route.path === "/items"),\n'
                 '      name: computed(() => t("menu.search")),\n'
                 '      to: "/items",\n'
                 '    },')
    new_items = ('    {\n'
                 '      icon: MdiMagnify,\n'
                 '      id: 3,\n'
                 '      active: computed(() => route.path === "/ledger"),\n'
                 '      name: computed(() => "物品"),\n'
                 '      to: "/ledger",\n'
                 '    },')
    rep(dv, old_items, new_items, "nav-items-to-ledger")
    rep(dv,
        'navigateTo(`/items?q=${encodeURIComponent(search.value)}`);',
        'navigateTo(`/ledger?q=${encodeURIComponent(search.value)}`);',
        "nav-topsearch-to-ledger")

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
                        "\t\tr.Get(\"/trash2\", chain.ToHandlerFunc(a.handleTrash2Get(), userMW...))\n"
                        "\t\tr.Put(\"/trash2\", chain.ToHandlerFunc(a.handleTrash2Put(), userMW...))\n"
                        "\t\tr.Post(\"/trash2/purge\", chain.ToHandlerFunc(a.handleTrash2Purge(), userMW...))\n"
                        "\t\tr.Get(\"/ui-options\", chain.ToHandlerFunc(a.handleUIOptionsGet(), userMW...))\n"
                        "\t\tr.Put(\"/ui-options\", chain.ToHandlerFunc(a.handleUIOptionsPut(), userMW...))\n"
                        "\t\tr.Post(\"/ai/recognize\", chain.ToHandlerFunc(a.handleAIRecognize(), userMW...))\n"
                        "\t\tr.Get(\"/trash\", chain.ToHandlerFunc(a.handleTrashGet(), userMW...))\n"
                        "\t\tr.Put(\"/trash\", chain.ToHandlerFunc(a.handleTrashPut(), userMW...))\n"
                        "\t\tr.Get(\"/audit\", chain.ToHandlerFunc(a.handleAuditGet(), userMW...))")
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
                        "\t\tr.Post(\"/biz/intake/rollback\", chain.ToHandlerFunc(a.handleBizIntakeRollback(), userMW...))")
        pub_anchor = 'r.Get("/qrcode", chain.ToHandlerFunc(v1Ctrl.HandleGenerateQRCode(), assetMW...))'
        pub_add = pub_anchor + '\n\t\tr.Get("/biz/images/{attachment}", chain.ToHandlerFunc(a.handleBizImage()))\n\t\tr.Get("/biz/images/{attachment}/{thumb}", chain.ToHandlerFunc(a.handleBizImage()))'
        if anchor not in s or pub_anchor not in s:
            fail("routes-biz", "锚点未找到")
        else:
            s = s.replace(anchor, add, 1).replace(pub_anchor, pub_add, 1)
            open(p, "w", encoding="utf-8").write(s)
            done("routes-biz 入库路由 + 公开图片路由")

    # ---- 9. 侧边栏「进货」入口（物品 之后；用 MdiCashMultiple 图标）----
    rep(dv,
        '      active: computed(() => route.path === "/ledger"),\n      name: computed(() => "物品"),\n      to: "/ledger",\n    },',
        '      active: computed(() => route.path === "/ledger"),\n      name: computed(() => "物品"),\n      to: "/ledger",\n    },\n    {\n      icon: MdiCashMultiple,\n      id: 901,\n      active: computed(() => route.path === "/intake"),\n      name: computed(() => "进货"),\n      to: "/intake",\n    },',
        "nav-intake-entry")

    if FAILS:
        print(f"\n共 {len(FAILS)} 个补丁失败: {', '.join(FAILS)}", file=sys.stderr)
        sys.exit(2)
    print("\n全部补丁完成")

if __name__ == "__main__":
    main()
