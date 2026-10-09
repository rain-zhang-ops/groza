<script setup lang="ts">
  const $fetch = useNuxtApp().$gxFetch as typeof globalThis.$fetch;
  import { toast } from "@/components/ui/sonner";
  import { useDialog } from "@/components/ui/dialog-provider";
  import { DialogID } from "@/components/ui/dialog-provider/utils";
  import MdiRefresh from "~icons/mdi/refresh";
  import MdiUndo from "~icons/mdi/undo";
  import MdiMagnify from "~icons/mdi/magnify";
  import MdiBarcodeScan from "~icons/mdi/barcode-scan";
  import MdiBellRing from "~icons/mdi/bell-ring";
  import MdiCellphoneArrowDown from "~icons/mdi/cellphone-arrow-down";
  import MdiFilterVariant from "~icons/mdi/filter-variant";
  import MdiPlus from "~icons/mdi/plus";
  import MdiMinus from "~icons/mdi/minus";
  import MdiCamera from "~icons/mdi/camera";
  import MdiOpenInNew from "~icons/mdi/open-in-new";
  import MdiImageSearch from "~icons/mdi/image-search";
  import MdiClose from "~icons/mdi/close";
  import MdiPackageVariantClosed from "~icons/mdi/package-variant-closed";
  import MdiAlertOutline from "~icons/mdi/alert-outline";
  import MdiClipboardCheckOutline from "~icons/mdi/clipboard-check-outline";
  import MdiFileImportOutline from "~icons/mdi/file-import-outline";
  import MdiQrcode from "~icons/mdi/qrcode";
  import MdiContentCopy from "~icons/mdi/content-copy";
  import MdiHistory from "~icons/mdi/history";
  import MdiDownload from "~icons/mdi/download";
  import MdiDeleteForever from "~icons/mdi/delete-forever";
  import MdiImageMultiple from "~icons/mdi/image-multiple";
  import MdiImage from "~icons/mdi/image";
  import MdiFormatSize from "~icons/mdi/format-size";
  import MdiViewGridOutline from "~icons/mdi/view-grid-outline";
  import MdiFormatListBulleted from "~icons/mdi/format-list-bulleted";
  import MdiContentPaste from "~icons/mdi/content-paste";
  import MdiFormTextbox from "~icons/mdi/form-textbox";
  import MdiDotsHorizontal from "~icons/mdi/dots-horizontal";
  import MdiEyeOutline from "~icons/mdi/eye-outline";
  import MdiEyeOffOutline from "~icons/mdi/eye-off-outline";
  definePageMeta({
    middleware: ["auth"],
  });

  const countMode = ref(false);

  useHead({
    title: () => (countMode.value ? "Groza | 盘点" : "Groza | 台账查询"),
  });

  type Row = {
    raw: Record<string, any>;
    id: string;
    name: string;
    brand: string;
    size: string;
    spec: string;
    color: string;
    material: string;
    paper: string;
    purchase: number | null;
    sell: number | null;
    pages: number | null;
    safety: number | null;
    qty: number;
    loc: string;
    serial: string;
    extra: Record<string, any>;
    thumb: string | null;
    updated: string;
  };
  type Field = "qty" | "purchase" | "sell" | "safety";
  type UndoItem = { row: Row; field: Field; prev: any };
  type AiTask = { id: string; label: string; search: boolean; status: "等待中" | "识别中" | "待确认" | "完成" | "失败" | "已取消"; msg: string };
  type AiConfirm = { id: string; blob: Blob; name: string; brand: string; size: string; spec: string; color: string; material: string; tag: string; search: boolean; url: string };

  const route = useRoute();
  const router = useRouter();
  const isMobile = useMediaQuery("(max-width: 768px)");
  // 卡片/列表切换：卡片=大图块（移动默认）；列表=桌面表格 / 移动紧凑行
  const viewMode = ref<"card" | "list">("card");
  watch(viewMode, v => { try { localStorage.setItem("hb.ledger.viewmode", v); } catch (_e) { /* ignore */ } });
  const { openDialog } = useDialog();
  const TPL_ID = "3873384e-3c86-4466-b3fd-42bbc4abd6e2";
  const TYPE_ID = "d5047042-cf61-42e9-bce3-29757ad2e6a9";
  const COLOR_WORDS = ["浅紫色", "深紫色", "紫色", "蓝色", "粉色", "黄色", "绿色", "白色", "橙色", "黑色", "金色", "银色"];
  const MATERIAL_WORDS = ["金属", "塑料"];
  const addOpen = ref(false);
  const addSaving = ref(false);
  const addForm = reactive({ name: "", size: "", color: "", spec: "", material: "塑料", qty: 0 as number, purchase: null as number | null, sell: null as number | null, loc: "", autoSplit: true, keep: false });
  const addNew = reactive({ size: false, color: false, spec: false, material: false });
  const uiOptions = ref<{ sizes: string[]; specs: string[]; colors: string[]; materials: string[]; required: string[] }>({ sizes: [], specs: [], colors: [], materials: [], required: [] });
  const mediaSlots = ref<Array<{ key: string; name: string; required?: boolean; multiple?: boolean }>>([
    { key: "front", name: "正面", required: true }, { key: "back", name: "反面" },
    { key: "detail", name: "细节", multiple: true }, { key: "package", name: "包装" },
  ]);
  const orgCfg = ref<{ tagGroup: { name: string; options: string[] }; series: { enabled: boolean; stripParentheses: boolean }; groupDims: string[] }>({
    tagGroup: { name: "品类", options: [] }, series: { enabled: true, stripParentheses: true }, groupDims: ["品牌", "尺寸", "规格", "系列"],
  });
  const DIM_KEYS: Record<string, string> = { 品牌: "brand", 尺寸: "size", 规格: "spec", 系列: "series", 颜色: "color", 材质: "material", 名称: "name", 分类: "loc" };
  const groupDims = computed(() => {
    const labels = orgCfg.value.groupDims?.length ? orgCfg.value.groupDims : ["品牌", "尺寸", "规格", "系列"];
    const opts = labels.map(l => ({ label: l, key: DIM_KEYS[l] || "" })).filter(d => d.key);
    return opts.length ? opts : [{ label: "品牌", key: "brand" }, { label: "系列", key: "series" }];
  });
  const isOwner = ref(true);
  function optionsFor(key: "size" | "color" | "spec" | "material", preset: string[]): string[] {
    const cfgMap: Record<string, string[]> = { size: uiOptions.value.sizes, color: uiOptions.value.colors, spec: uiOptions.value.specs, material: uiOptions.value.materials };
    const set = new Set([...(cfgMap[key] || []), ...preset]);
    for (const r of rows.value) { const v = String(r[key] || ""); if (v) set.add(v); }
    for (const v of [addForm.size, addForm.color, addForm.spec, addForm.material]) { if (v) set.add(v); }
    return [...set].sort((a, b) => a.localeCompare(b, "zh"));
  }
  const sizeOptions = computed(() => optionsFor("size", ["A4", "A5", "A5S", "A6", "A6L", "B5", "B6"]));
  const colorOptions = computed(() => optionsFor("color", ["黑色", "白色", "蓝色", "粉色", "黄色", "绿色", "橙色", "紫色", "浅紫色", "深紫色", "红色", "棕色", "灰色"]));
  const materialOptions = computed(() => optionsFor("material", ["塑料", "金属"]));
  const specOptions = computed(() => optionsFor("spec", ["网格", "点阵", "横线"]));
  function onSel(e: Event, field: "size" | "color" | "spec" | "material") {
    const v = (e.target as HTMLSelectElement).value;
    if (v === "__new__") { addNew[field] = true; addForm[field] = ""; }
    else { addNew[field] = false; addForm[field] = v; }
  }

  function splitName(raw: string) {
    let n = (raw || "").trim();
    let size = "", color = "", spec = "", material = "塑料";
    const lead = n.match(/^(A\d+L?S?|B\d+)/); if (lead) { size = lead[1]; n = n.slice(size.length); }
    const sp = n.match(/(横线|点阵|网格)$/); if (sp) { spec = sp[1]; n = n.slice(0, -spec.length); }
    const any = n.match(/(A\d+L?S?|B\d+)/); if (any && any.index !== undefined) n = n.slice(0, any.index);
    for (const m of MATERIAL_WORDS) { if (n.includes(m)) { material = m; n = n.replace(m, ""); break; } }
    for (const c of COLOR_WORDS) { if (n.includes(c)) { color = c; n = n.replace(c, ""); break; } }
    n = n.replace(/[（(]\s*[)）]/g, "").replace(/(横线|点阵|网格)+/g, "").replace(/\s+/g, "").trim();
    return { name: n || (raw || "").trim(), size, color, spec, material };
  }
  function onAddNameInput() {
    if (!addForm.autoSplit) return;
    const p = splitName(addForm.name);
    addForm.size = p.size; addForm.color = p.color; addForm.spec = p.spec; addForm.material = p.material;
  }
  function locName(id: string) { return (locations.value.find(l => l.id === id) || {}).name || ""; }

  function buzz(ms = 15) { try { (navigator as any).vibrate?.(ms); } catch (_e) { /* ignore */ } }

  // ---------- 变更历史 ----------
  const historyOpen = ref(false);
  const historyTitle = ref("");
  const historyLogs = ref<Array<Record<string, any>>>([]);
  const historyBusy = ref(false);
  async function showHistory(r: Row) {
    historyTitle.value = r.name;
    historyOpen.value = true; historyBusy.value = true; historyLogs.value = [];
    try {
      const arr = await $fetch<Array<Record<string, any>>>(`/api/v1/audit?entityId=${r.id}&limit=100`);
      historyLogs.value = (arr || []).slice().reverse();
    } catch (_e) { /* ignore */ }
    historyBusy.value = false;
  }
  function auditText(e: Record<string, any>): string {
    switch (e.action) {
      case "ledger.field_patch": return "修改字段：" + (Array.isArray(e.fields) ? e.fields.join("、") : "");
      case "intake.create": return `入库（单 ${e.intakeId}）`;
      case "intake.rollback": return `入库回滚（单 ${e.intakeId}）`;
      case "trash2.mark": return "标记删除";
      case "trash2.purge": return "回收站清除";
      default: return String(e.action || "");
    }
  }
  function fmtTs(ts: string): string {
    const d = new Date(ts); if (isNaN(d.getTime())) return ts || "";
    const z = (x: number) => String(x).padStart(2, "0");
    return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`;
  }

  // ---------- 导出 CSV（当前筛选） ----------
  function exportCSV() {
    const list = sorted.value;
    const cols = ["名称", "品牌", "尺寸", "规格", "颜色", "材质", "数量", "进价", "售价", "安全库存", "分类", "库位", "资产号"];
    const KNOWN = new Set(["品牌", "尺寸", "规格", "颜色", "材质", "进价", "售价", "安全库存"]);
    const extraSet = new Set<string>();
    for (const r of list) for (const f of ((r.raw.fields as Array<Record<string, any>>) || [])) if (!KNOWN.has(f.name)) extraSet.add(f.name);
    const extras = [...extraSet].sort();
    cols.push(...extras);
    const esc = (v: any) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [cols.join(",")];
    for (const r of list) {
      const fm = fieldMap(r.raw);
      const base: any[] = [r.name, r.brand, r.size, r.spec, r.color, r.material, r.qty ?? 0, r.purchase ?? "", r.sell ?? "", r.safety ?? "", r.loc, r.serial ?? "", r.raw.assetId ?? ""];
      for (const nm of extras) base.push(fm[nm] ?? "");
      lines.push(base.map(esc).join(","));
    }
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `台账-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    buzz(); flash(`已导出 ${list.length} 行`);
  }

  function shareText(): string {
    const list = sorted.value;
    const lines = [`Groza 清单 · ${new Date().toLocaleDateString()} · ${list.length} 款`];
    for (const r of list) lines.push(`· ${r.name}${r.serial ? "  @" + r.serial : ""}  ×${r.qty}${r.sell ? "  ¥" + r.sell : ""}`);
    return lines.join("\n");
  }
  async function copyList() {
    const t = shareText();
    try { await navigator.clipboard.writeText(t); flash("清单已复制，可直接粘贴"); }
    catch (_e) { window.prompt("复制清单：", t); }
    buzz();
  }
  function exportImage() {
    const list = sorted.value.slice(0, 300);
    if (!list.length) { flash("无可导出项"); return; }
    const rowH = 36, pad = 28, w = 760;
    const h = Math.min(pad * 2 + 44 + 34 + list.length * rowH, 16000);
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const ctx = c.getContext("2d"); if (!ctx) return;
    ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, c.width, c.height);
    ctx.fillStyle = "#1b1b1f"; ctx.font = "bold 30px -apple-system, PingFang SC, sans-serif";
    ctx.fillText("Groza 物品清单", pad, pad + 30);
    ctx.fillStyle = "#555"; ctx.font = "20px -apple-system, PingFang SC, sans-serif";
    ctx.fillText(`${new Date().toLocaleString()} · 共 ${list.length} 款`, pad, pad + 64);
    let y = pad + 104;
    ctx.font = "22px -apple-system, PingFang SC, sans-serif";
    for (const r of list) {
      ctx.fillStyle = "#1b1b1f";
      const label = (r.name + (r.serial ? "  @" + r.serial : "")).slice(0, 34);
      ctx.fillText(label, pad, y);
      ctx.fillStyle = "#555";
      ctx.fillText(`×${r.qty}`, w - pad - 70, y);
      y += rowH;
      if (y > c.height - pad) break;
    }
    c.toBlob((b) => {
      if (!b) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `Groza清单-${new Date().toISOString().slice(0, 10)}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
    buzz(); flash("已导出长图");
  }

  const pulling = ref(false);
  const refreshing = ref(false);
  let pullStartY = 0;
  function onPullStart(e: TouchEvent) { pullStartY = (import.meta.client && window.scrollY <= 0) ? e.touches[0].clientY : 0; }
  function onPullMove(e: TouchEvent) { if (pullStartY && e.touches[0].clientY - pullStartY > 56) pulling.value = true; }
  async function onPullEnd() {
    if (pulling.value && pullStartY) { refreshing.value = true; try { await load(); } finally { refreshing.value = false; } }
    pulling.value = false; pullStartY = 0;
  }

  // ---------- 复制一件 ----------
  async function duplicateRow(r: Row) {
    saving[r.id] = true;
    try {
      const created = await $fetch<Record<string, any>>(`/api/v1/entities/${r.id}/duplicate`, { method: "POST", body: {} });
      const nid = created?.id;
      const nm = r.name + "（副本）";
      if (nid) await $fetch(`/api/v1/entities/${nid}`, { method: "PATCH", body: { name: nm } }).catch(() => {});
      buzz(); flash("已复制：" + nm);
      await load();
    } catch (e) { flash("复制失败：" + ((e as Error)?.message ?? String(e))); }
    finally { saving[r.id] = false; }
  }

  // ---------- 重复名称（合并） ----------
  const dupGroups = computed(() => {
    const m: Record<string, Row[]> = {};
    for (const r of rows.value.filter(x => !isTrashed(x))) {
      const k = r.name.trim(); if (!k) continue;
      (m[k] = m[k] || []).push(r);
    }
    return Object.entries(m).filter(([, arr]) => arr.length > 1).map(([name, arr]) => ({ name, rows: arr }));
  });
  async function mergeDupSoft(g: { name: string; rows: Row[] }) {
    const sortedRows = [...g.rows].sort((a, b) => String(b.updated || "").localeCompare(String(a.updated || "")));
    const extras = sortedRows.slice(1);
    for (const r of extras) trashed[r.id] = true;
    try { await persistTrash(); buzz(20); flash(`「${g.name}」保留 1 条，标记删除 ${extras.length} 条`); }
    catch (e) { flash("操作失败：" + ((e as Error)?.message ?? String(e))); }
  }

  // ---------- 数据体检 ----------
  const qualityOpen = ref(false);
  const qualityStats = computed(() => {
    const list = rows.value.filter(r => !isTrashed(r));
    const dup: Record<string, number> = {};
    for (const r of list) { const k = r.name.trim().toLowerCase(); if (k) dup[k] = (dup[k] || 0) + 1; }
    const dupNames = Object.entries(dup).filter(([, c]) => c > 1).map(([k]) => k);
    return {
      total: list.length,
      noImg: list.filter(r => !r.thumb).length,
      noPurchase: list.filter(r => r.purchase === null || r.purchase === 0).length,
      noSell: list.filter(r => r.sell === null || r.sell === 0).length,
      noSafety: list.filter(r => !(r.safety && r.safety > 0)).length,
      noBrand: list.filter(r => !r.brand).length,
      noSize: list.filter(r => !r.size).length,
      noSpec: list.filter(r => !r.spec).length,
      dupCount: dupNames.reduce((a, k) => a + (dup[k] || 0), 0),
      dupNames,
      noRequired: (uiOptions.value.required || []).length ? list.filter(r => missingRequired(r).length > 0).length : 0,
    };
  });
  function applyQuality(kind: string) {
    onlyLow.value = false; showSummary.value = false;
    Object.assign(filter, { brand: "", size: "", spec: "", color: "", material: "", q: "" });
    if (kind === "dup") { filter.q = qualityStats.value.dupNames[0] || ""; dataFilter.value = ""; }
    else dataFilter.value = kind;
    qualityOpen.value = false;
    filterOpen.value = false;
  }

  // ---------- 批量导入 ----------
  const importOpen = ref(false);
  const importText = ref("");
  const importBusy = ref(false);
  const importMsg = ref("");
  const IMPORT_COLS = ["名称", "品牌", "尺寸", "规格", "颜色", "材质", "数量", "进价", "售价", "安全库存", "分类"];
  const importRows = computed(() => {
    const lines = importText.value.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    if (!lines.length) return [] as Array<Record<string, string>>;
    const sep = lines[0].includes("\t") ? "\t" : ",";
    let start = 0;
    const h = lines[0].split(sep).map(x => x.trim().toLowerCase());
    if (h.includes("名称") || h.includes("name")) start = 1;
    const out: Array<Record<string, string>> = [];
    for (let i = start; i < lines.length; i++) {
      const cells = lines[i].split(sep).map(x => x.trim());
      if (!cells[0]) continue;
      const o: Record<string, string> = {};
      IMPORT_COLS.forEach((c, idx) => { o[c] = cells[idx] || ""; });
      out.push(o);
    }
    return out;
  });
  async function importOne(row: Record<string, string>, fallbackLoc: string) {
    const name = (row["名称"] || "").trim();
    if (!name) throw new Error("无名称");
    const locName = (row["分类"] || "").trim();
    const loc = locName ? locations.value.find(l => l.name === locName) : undefined;
    const parentId = loc?.id || fallbackLoc;
    const qty = Number(row["数量"]) || 0;
    const created = await $fetch<Record<string, any>>(`/api/v1/templates/${TPL_ID}/create-item`, {
      method: "POST",
      body: { name, parentId, entityTypeId: TYPE_ID, quantity: qty, tagIds: [] },
    });
    const d = await $fetch<Record<string, any>>(`/api/v1/entities/${created.id}`);
    const brand = (row["品牌"] || loc?.name || "").trim();
    const fields = (d.fields || []).map((f: Record<string, any>) => {
      const x: Record<string, any> = { id: f.id, name: f.name, type: f.type };
      if (f.type === "text") x.textValue = f.textValue ?? ""; else x.numberValue = f.numberValue ?? 0;
      if (f.name === "品牌") x.textValue = brand;
      else if (f.name === "尺寸") x.textValue = row["尺寸"] || "";
      else if (f.name === "规格") x.textValue = row["规格"] || "";
      else if (f.name === "颜色") x.textValue = row["颜色"] || "";
      else if (f.name === "材质") x.textValue = row["材质"] || "";
      else if (f.name === "进价") x.numberValue = Number(row["进价"]) || 0;
      else if (f.name === "售价") x.numberValue = Number(row["售价"]) || 0;
      else if (f.name === "安全库存") x.numberValue = Number(row["安全库存"]) || 0;
      return x;
    });
    const tag = tags.value.find(t => t.name === brand);
    await $fetch(`/api/v1/entities/${created.id}`, {
      method: "PUT",
      body: { name, entityTypeId: d.entityType?.id ?? TYPE_ID, fields, notes: "", quantity: qty, parentId, tagIds: tag ? [tag.id] : [] },
    });
  }
  async function doImport() {
    const list = importRows.value;
    if (!list.length) { importMsg.value = "没有可导入的行"; return; }
    const fallbackLoc = addForm.loc || (locations.value[0] || {}).id || "";
    if (!fallbackLoc) { importMsg.value = "无可用分类"; return; }
    importBusy.value = true;
    let ok = 0, bad = 0;
    importMsg.value = `导入中… 0/${list.length}`;
    for (let i = 0; i < list.length; i++) {
      try { await importOne(list[i], fallbackLoc); ok++; } catch (_e) { bad++; }
      importMsg.value = `导入中… ${i + 1}/${list.length}（成功 ${ok} 失败 ${bad}）`;
    }
    importBusy.value = false;
    importMsg.value = `完成：成功 ${ok}，失败 ${bad}`;
    importText.value = "";
    await load();
  }

  // ---------- 二维码标签 ----------
  const qrOpen = ref(false);
  const qrData = ref("");
  const qrTitle = ref("");
  function qrSrcFor(v: string) { return `/api/v1/qr?data=${encodeURIComponent(v)}`; }
  function showQR(r: Row) {
    const a = String(r.raw.assetId || "");
    qrData.value = a || r.name;
    qrTitle.value = r.name + (a ? `（${a}）` : "");
    qrOpen.value = true;
  }
  function printQR(name: string, data: string) {
    const w = window.open("", "_blank", "width=420,height=600");
    if (!w) return;
    const img = `${location.origin}/api/v1/qr?data=${encodeURIComponent(data)}`;
    w.document.write(`<html><head><title>二维码</title></head><body style="text-align:center;font-family:sans-serif;padding:16px"><div style="font-size:16px;margin-bottom:12px">${name}</div><img style="width:320px" src="${img}" /><div style="margin-top:8px;color:#333">${data}</div></body></html>`);
    w.document.close();
    setTimeout(() => { try { w.focus(); w.print(); } catch (_e) { /* ignore */ } }, 600);
  }
  function printFiltered() {
    const list = sorted.value.filter(r => !isTrashed(r)).slice(0, 300);
    if (!list.length) { flash("无可打印项"); return; }
    const w = window.open("", "_blank");
    if (!w) return;
    const cards = list.map(r => {
      const a = String(r.raw.assetId || r.name);
      return `<div style="display:inline-block;width:190px;margin:6px;text-align:center;font-family:sans-serif;vertical-align:top"><div style="font-size:12px;height:32px;overflow:hidden">${r.name}</div><img style="width:150px" src="${location.origin}/api/v1/qr?data=${encodeURIComponent(a)}"/><div style="font-size:11px;color:#444">${a}</div></div>`;
    }).join("");
    w.document.write(`<html><head><title>二维码标签</title></head><body>${cards}</body></html>`);
    w.document.close();
    setTimeout(() => { try { w.focus(); w.print(); } catch (_e) { /* ignore */ } }, 800);
  }
  function addItem() {
    addForm.loc = addForm.loc || (locations.value[0] || {}).id || "";
    addOpen.value = true;
  }
  async function doAdd() {
    const p = addForm.autoSplit ? splitName(addForm.name) : { name: addForm.name, size: addForm.size, color: addForm.color, spec: addForm.spec, material: addForm.material };
    const name = (p.name || addForm.name).trim();
    if (!name) { flash("请填名称"); return; }
    if (!addForm.loc) { flash("请选分类"); return; }
    addSaving.value = true;
    try {
      const created = await $fetch<Record<string, any>>(`/api/v1/templates/${TPL_ID}/create-item`, {
        method: "POST",
        body: { name, parentId: addForm.loc, entityTypeId: TYPE_ID, quantity: Number(addForm.qty) || 0, tagIds: [] },
      });
      const d = await $fetch<Record<string, any>>(`/api/v1/entities/${created.id}`);
      const brand = locName(addForm.loc);
      const fields = (d.fields || []).map((f: Record<string, any>) => {
        const x: Record<string, any> = { id: f.id, name: f.name, type: f.type };
        if (f.type === "text") x.textValue = f.textValue ?? ""; else x.numberValue = f.numberValue ?? 0;
        if (f.name === "品牌") x.textValue = brand;
        else if (f.name === "尺寸") x.textValue = p.size;
        else if (f.name === "颜色") x.textValue = p.color;
        else if (f.name === "规格") x.textValue = p.spec;
        else if (f.name === "材质") x.textValue = p.material;
        else if (f.name === "进价") x.numberValue = Number(addForm.purchase) || 0;
        else if (f.name === "售价") x.numberValue = Number(addForm.sell) || 0;
        return x;
      });
      const tag = tags.value.find(t => t.name === brand);
      await $fetch(`/api/v1/entities/${created.id}`, {
        method: "PUT",
        body: { name, entityTypeId: d.entityType?.id ?? TYPE_ID, fields, notes: "", quantity: Number(addForm.qty) || 0, parentId: addForm.loc, tagIds: tag ? [tag.id] : [] },
      });
      buzz(); flash("已新增：" + name);
      if (addForm.keep) {
        Object.assign(addForm, { name: "", qty: 0, purchase: null, sell: null });
      } else {
        addOpen.value = false;
        Object.assign(addForm, { name: "", size: "", color: "", spec: "", material: "塑料", qty: 0, purchase: null, sell: null, loc: "", autoSplit: true, keep: false });
        Object.assign(addNew, { size: false, color: false, spec: false, material: false });
      }
      await load();
    } catch (e) {
      flash("新增失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      addSaving.value = false;
    }
  }
  const brandOptions = computed(() => {
    const set = new Set<string>(locations.value.map(l => l.name));
    for (const r of rows.value) { if (r.brand) set.add(r.brand); }
    return [...set].sort((a, b) => a.localeCompare(b, "zh"));
  });
  function optsWith(list: string[], cur: string): string[] {
    const arr = [...(list || [])];
    if (cur && !arr.includes(cur)) arr.unshift(cur);
    return arr;
  }
  function onInline(e: Event, r: Row, name: "品牌" | "尺寸" | "颜色" | "规格" | "材质", field: "brand" | "size" | "color" | "spec" | "material") {
    let v = (e.target as HTMLSelectElement).value;
    if (v === "__new__") {
      const nv = window.prompt("新增" + name, "");
      if (!nv || !nv.trim()) { (e.target as HTMLSelectElement).value = String(r[field] || ""); return; }
      v = nv.trim();
    }
    void setField(r, name, v);
  }
  async function setName(r: Row) {
    const nm = (r.name || "").trim();
    if (!nm) { flash("名称不能为空"); await load(); return; }
    saving[r.id] = true;
    try {
      const fresh = await $fetch<Record<string, any>>(`/api/v1/entities/${r.id}`, {
        method: "PUT",
        body: {
          name: nm, entityTypeId: r.raw.entityType.id, fields: buildFields(r, {}),
          notes: r.raw.notes || "", quantity: Number(r.qty),
          parentId: r.raw.parent?.id ?? null, tagIds: (r.raw.tags || []).map((t: Record<string, any>) => t.id),
        },
      });
      r.raw = { ...r.raw, ...fresh };
      r.raw.name = nm; r.updated = fresh.updatedAt || r.updated;
      markSaved(r.id); flash("已保存名称");
    } catch (e) {
      flash("保存失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      saving[r.id] = false;
    }
  }
  const aiInput = ref<HTMLInputElement | null>(null);
  const aiSearch = ref(false);
  const aiTasks = ref<AiTask[]>([]);
  const aiFiles = new Map<string, File>();
  const aiBlobs = new Map<string, Blob>();
  const aiConfirm = ref<AiConfirm | null>(null);
  const aiBusy = ref(false);
  const aiActive = computed(() => aiTasks.value.filter(t => t.status === "等待中" || t.status === "识别中").length);
  const aiDone = computed(() => aiTasks.value.filter(t => t.status === "完成").length);
  const aiFailed = computed(() => aiTasks.value.filter(t => t.status === "失败").length);
  const aiPending = computed(() => aiTasks.value.filter(t => t.status === "待确认").length);
  const AI_FIELDS = ["书写本", "无日期计划本", "有日期计划本", "贴纸", "笔", "套盒", "拼图"];
  const AI_BRANDS = ["英瑞克", "得力佳", "Pukka Pad", "Happy", "优品胜"];
  const AI_SIZES = ["A4", "A5", "A5S", "A6", "A6L", "B5", "B6", "Micro", "Skinny", "Classic", "Mini"];
  const AI_SPECS = ["横线", "网格", "方格", "点阵", "Notes笔记本", "无日期计划本", "有日期计划本"];
  const AI_MATERIALS = ["纸", "塑料", "金属", "布", "PU"];
  function pickAI() { aiInput.value?.click(); }
  function focusAppSearch() {
    const el = document.querySelector('input[type="search"]') as HTMLInputElement | null;
    el?.focus();
    el?.scrollIntoView({ block: "nearest" });
  }
  function onAIFile(e: Event) {
    const input = e.target as HTMLInputElement;
    const files = Array.from(input.files || []);
    input.value = "";
    if (!files.length) return;
    const search = aiSearch.value;
    for (const f of files) {
      const id = (globalThis.crypto?.randomUUID?.() ?? (Date.now().toString(36) + Math.random().toString(36).slice(2)));
      aiFiles.set(id, f);
      aiTasks.value.push({ id, label: f.name || "照片", search, status: "等待中", msg: "" });
    }
    flash(`已加入 AI 队列：${files.length} 张`);
    void runAIQueue();
  }
  function clampField(v: string, allowed: string[]): string {
    const s = (v || "").trim();
    if (!s) return "";
    return allowed.some(a => a === s || s.includes(a) || a.includes(s)) ? s : "";
  }
  async function runAIQueue() {
    if (aiBusy.value) return;
    aiBusy.value = true;
    try {
      for (;;) {
        const t = aiTasks.value.find(x => x.status === "等待中");
        if (!t) break;
        if (!aiFiles.has(t.id)) { t.status = "已取消"; continue; }
        t.status = "识别中";
        try {
          const f = aiFiles.get(t.id) as File;
          const blob = await compressImage(f);
          const res = await $fetch<Record<string, string>>(`/api/v1/ai/recognize${t.search ? "?search=1" : ""}`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob });
          aiBlobs.set(t.id, blob);
          aiFiles.delete(t.id);
          t.status = "待确认"; t.msg = (res.name || "").trim() || "识别完成";
          if (!aiConfirm.value) openAIConfirm(t, res, blob);
        } catch (err) {
          t.status = "失败"; t.msg = ((err as Error)?.message ?? String(err)).slice(0, 80);
        }
      }
    } finally {
      aiBusy.value = false;
    }
  }
  function openAIConfirm(t: AiTask, res: Record<string, string>, blob: Blob) {
    aiConfirm.value = {
      id: t.id,
      blob,
      name: (res.name || "").trim() || "未识别物品",
      brand: clampField(res.brand, AI_BRANDS),
      size: clampField(res.size, AI_SIZES),
      spec: clampField(res.spec, AI_SPECS),
      color: (res.color || "").trim(),
      material: clampField(res.material, AI_MATERIALS),
      tag: clampField(res.tag, AI_FIELDS),
      search: t.search,
      url: URL.createObjectURL(blob),
    };
  }
  function reopenAIConfirm(t: AiTask) {
    const blob = aiBlobs.get(t.id);
    if (!blob) { t.status = "失败"; t.msg = "识别数据已丢失，请重新拍照"; return; }
    if (aiConfirm.value) URL.revokeObjectURL(aiConfirm.value.url);
    openAIConfirm(t, {}, blob);
  }
  function aiConfirmNext() {
    if (!aiConfirm.value) return;
    URL.revokeObjectURL(aiConfirm.value.url);
    aiConfirm.value = null;
    const t = aiTasks.value.find(x => x.status === "待确认");
    if (t) {
      const blob = aiBlobs.get(t.id);
      if (blob) openAIConfirm(t, {}, blob);
    }
  }
  function aiReject() {
    const c = aiConfirm.value;
    if (!c) return;
    const t = aiTasks.value.find(x => x.id === c.id);
    if (t) { t.status = "已取消"; t.msg = "已拒绝"; }
    aiBlobs.delete(c.id);
    URL.revokeObjectURL(c.url);
    aiConfirm.value = null;
    const next = aiTasks.value.find(x => x.status === "待确认");
    if (next) {
      const blob = aiBlobs.get(next.id);
      if (blob) openAIConfirm(next, {}, blob);
    }
  }
  async function aiCreateOne() {
    const c = aiConfirm.value;
    if (!c) return;
    try {
      const row = await createFromAI(c);
      const t = aiTasks.value.find(x => x.id === c.id);
      if (t) { t.status = "完成"; t.msg = row.name; }
      rows.value.unshift(row);
      trashed[row.id] = false; delete trashEntries[row.id];
      markSaved(row.id);
    } catch (err) {
      const t = aiTasks.value.find(x => x.id === c.id);
      if (t) { t.status = "失败"; t.msg = ((err as Error)?.message ?? String(err)).slice(0, 80); }
      return;
    }
    aiBlobs.delete(c.id);
    URL.revokeObjectURL(c.url);
    aiConfirm.value = null;
    const next = aiTasks.value.find(x => x.status === "待确认");
    if (next) {
      const blob = aiBlobs.get(next.id);
      if (blob) openAIConfirm(next, {}, blob);
    }
  }
  async function aiCreateAll() {
    for (;;) {
      const before = aiConfirm.value?.id;
      await aiCreateOne();
      if (!aiConfirm.value || aiConfirm.value.id === before) break;
    }
  }
  function aiCancelTask(t: AiTask) {
    if (t.status === "等待中") {
      t.status = "已取消"; t.msg = "";
      aiFiles.delete(t.id);
      flash("已取消：" + t.label);
    } else if (t.status === "待确认") {
      if (aiConfirm.value?.id === t.id) aiReject();
      else {
        t.status = "已取消";
        aiBlobs.delete(t.id);
      }
    }
  }
  async function createFromAI(c: AiConfirm): Promise<Row> {
    const name = (c.name || "").trim() || "未识别物品";
    let loc = locations.value.find(l => l.name.toLowerCase() === c.brand.toLowerCase())
      || locations.value.find(l => c.brand && l.name.toLowerCase().includes(c.brand.toLowerCase()));
    if (!loc) loc = locations.value.find(l => l.name === "待分类") || locations.value[0];
    const parentId = loc?.id || "";
    if (!parentId) throw new Error("无可用分类");
    const tag = tags.value.find(t => t.name === c.tag);
    const created = await $fetch<Record<string, any>>(`/api/v1/templates/${TPL_ID}/create-item`, {
      method: "POST",
      body: { name, parentId, entityTypeId: TYPE_ID, quantity: 0, tagIds: tag ? [tag.id] : [] },
    });
    const d = await $fetch<Record<string, any>>(`/api/v1/entities/${created.id}`);
    const fields = (d.fields || []).map((fd: Record<string, any>) => {
      const x: Record<string, any> = { id: fd.id, name: fd.name, type: fd.type };
      if (fd.type === "text") x.textValue = fd.textValue ?? ""; else x.numberValue = fd.numberValue ?? 0;
      if (fd.name === "品牌") x.textValue = c.brand || loc?.name || "";
      else if (fd.name === "尺寸") x.textValue = c.size || "";
      else if (fd.name === "规格") x.textValue = c.spec || "";
      else if (fd.name === "颜色") x.textValue = c.color || "";
      else if (fd.name === "材质") x.textValue = c.material || "";
      return x;
    });
    await $fetch(`/api/v1/entities/${created.id}`, {
      method: "PUT",
      body: { name, entityTypeId: d.entityType?.id ?? TYPE_ID, fields, notes: "AI 识别新增", quantity: 0, parentId, tagIds: tag ? [tag.id] : [] },
    });
    const form = new FormData();
    form.append("file", c.blob, "ai.jpg");
    form.append("name", "ai.jpg");
    form.append("type", "photo");
    form.append("primary", "true");
    await $fetch(`/api/v1/entities/${created.id}/attachments`, { method: "POST", body: form });
    const full = await $fetch<Record<string, any>>(`/api/v1/entities/${created.id}`);
    return toRow(full);
  }
  function clearAIDone() {
    const removed = aiTasks.value.filter(t => t.status === "已取消" || t.status === "完成" || t.status === "失败");
    for (const t of removed) aiBlobs.delete(t.id);
    aiTasks.value = aiTasks.value.filter(t => t.status === "等待中" || t.status === "识别中" || t.status === "待确认");
  }
  async function setField(r: Row, name: "品牌" | "尺寸" | "颜色" | "规格" | "材质", val: string) {
    const ok = await putFields(r, { [name]: val });
    if (ok) {
      if (name === "尺寸") r.size = val; else if (name === "颜色") r.color = val; else if (name === "材质") r.material = val; else if (name === "品牌") r.brand = val; else r.spec = val;
      markSaved(r.id); flash("已保存" + name);
    }
  }

  const rows = ref<Row[]>([]);
  const tags = ref<Array<{ id: string; name: string }>>([]);
  const locations = ref<Array<{ id: string; name: string }>>([]);
  const loading = ref(true);
  const err = ref("");
  const msg = ref("");
  const onlyLow = ref(false);
  const hideSoldOut = ref(true);
  const dataFilter = ref("");
  const showSummary = ref(false);
  const summaryDim = ref<string>("brand");
  const preview = ref<string | null>(null);
  const undoLast = ref<{ label: string; items: UndoItem[] } | null>(null);
  const filterOpen = ref(false);
  const moreFilters = ref(false);
  const density = ref<"comfortable" | "compact">("comfortable");
  const page = ref(1);
  const pageSize = ref(50);

  const sel = reactive<Record<string, boolean>>({});
  const trashed = reactive<Record<string, boolean>>({});
  const trashEntries = reactive<Record<string, { deletedAt?: string; name?: string }>>({});
  const saving = reactive<Record<string, boolean>>({});
  const preEdit = reactive<Record<string, { qty: number; purchase: number | null; sell: number | null; safety: number | null }>>({});

  const filter = reactive({ brand: "", size: "", spec: "", color: "", material: "", q: "", series: "" });
  const extraFilters = reactive<Record<string, string>>({});
  const sort = reactive<{ key: string; dir: 1 | -1 }>({ key: "name", dir: 1 });
  const cols = reactive({
    size: true, spec: true, color: true, material: true, purchase: true, sell: true,
    safety: true, updated: true, shelf: true,
  });
  const batch = reactive<{ qty: number | null; purchase: number | null; sell: number | null; safety: number | null; tag: string; loc: string }>({
    qty: null, purchase: null, sell: null, safety: null, tag: "", loc: "",
  });
  const presets = ref<Array<{ name: string; view: Record<string, any> }>>([]);
  const presetName = ref("");

  const chip = "inline-flex cursor-pointer items-center gap-1.5 rounded-lg border bg-background px-3 py-1.5 text-sm transition-colors hover:bg-muted";
  const cellPad = computed(() => (density.value === "compact" ? "px-3 py-1" : "px-3 py-2"));

  function num(v: unknown): number | null {
    if (v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  function fieldMap(e: Record<string, any>): Record<string, any> {
    const m: Record<string, any> = {};
    for (const f of (e.fields as Array<Record<string, any>>) || []) {
      m[f.name] = f.type === "text" ? f.textValue : f.numberValue;
    }
    return m;
  }

  function toRow(e: Record<string, any>): Row {
    const f = fieldMap(e);
    const parent = e.parent as Record<string, any> | null | undefined;
    return {
      raw: e, id: e.id, name: e.name,
      brand: f["品牌"] || "", size: f["尺寸"] || "", spec: f["规格"] || "",
      color: f["颜色"] || "", material: f["材质"] || "", paper: f["纸张"] || "",
      purchase: num(f["进价"]), sell: num(f["售价"]), pages: num(f["页数"]), safety: num(f["安全库存"]),
      qty: e.quantity ?? 0,
      loc: typeof e.parent === "string" ? e.parent : (parent?.name || ""),
      thumb: e.thumb || e.imageId || e.thumbnailId || null,
      serial: String(e.serial ?? e.serialNumber ?? ""),
      extra: rowExtra(e),
      updated: e.updatedAt || "",
    } as Row;
  }
  function seriesKey(r: Row): string {
    const s = orgCfg.value.series;
    const nm = String(r.name || "");
    if (s && s.enabled === false) return nm;
    let x = nm;
    if (!s || s.stripParentheses !== false) x = x.replace(/[（(][^）)]*[)）]/g, "").trim();
    return x || nm;
  }
  const seriesOptions = computed(() => {
    const set = new Set<string>();
    for (const r of rows.value) { const k = seriesKey(r); if (k) set.add(k); }
    return [...set].sort((a, b) => a.localeCompare(b, "zh"));
  });
  function nq(x: string): string { return String(x || "").toLowerCase().replace(/\s+/g, ""); }

  // 搜索历史
  const searchHistory = ref<string[]>([]);
  try { searchHistory.value = JSON.parse(localStorage.getItem("groza.searchhist") || "[]"); } catch (_e) { searchHistory.value = []; }
  function pushSearch(v: string) {
    const t = v.trim();
    if (t.length < 2) return;
    searchHistory.value = [t, ...searchHistory.value.filter(x => x !== t)].slice(0, 10);
    try { localStorage.setItem("groza.searchhist", JSON.stringify(searchHistory.value)); } catch (_e) { /* ignore */ }
  }
  function hl(name: string): string {
    const q = (filter.q || "").trim();
    const esc = (x: string) => x.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    if (!q) return esc(name);
    const i = name.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return esc(name);
    return esc(name.slice(0, i)) + "<mark class=\"rounded bg-amber-200/70 px-0.5 text-foreground\">" + esc(name.slice(i, i + q.length)) + "</mark>" + esc(name.slice(i + q.length));
  }

  // 大字号
  const bigFont = ref(false);
  function applyBigFont() { if (import.meta.client) document.documentElement.style.fontSize = bigFont.value ? "18px" : ""; }
  function toggleBigFont() {
    bigFont.value = !bigFont.value;
    try { localStorage.setItem("groza.bigfont", bigFont.value ? "1" : "0"); } catch (_e) { /* ignore */ }
    applyBigFont(); buzz();
  }

  // 离线只读缓存
  const CACHE_KEY = "groza.ledger.cache";
  const offlineReadonly = ref(false);
  function applyAgg(agg: Record<string, any>): void {
    tags.value = agg.tags || [];
    locations.value = (agg.locations || []).map((x: Record<string, any>) => ({ id: x.id, name: x.name }));
    uiOptions.value = {
      sizes: agg.uiOptions?.sizes || [], specs: agg.uiOptions?.specs || [],
      colors: agg.uiOptions?.colors || [], materials: agg.uiOptions?.materials || [], required: agg.uiOptions?.required || [],
    };
    for (const k of Object.keys(trashEntries)) delete trashEntries[k];
    const ent = agg.trash?.entries || {};
    for (const id of Object.keys(ent)) { trashEntries[id] = ent[id]; trashed[id] = true; }
    rows.value = (agg.items as Array<Record<string, any>>).map(e => toRow({
      ...e,
      raw: {
        ...e,
        entityType: { id: TYPE_ID },
        parent: (agg.locations as Array<Record<string, any>> || []).find(l => l.name === e.parent) || null,
        notes: e.notes || "",
      },
    }));
  }

  // 配置驱动（gx/config）：必填与下拉选项按属性配置派生（名称匹配），失败回退原值
  async function applyGxConfig(): Promise<void> {
    try {
      try { const m = await $fetch<Record<string, any>>("/api/v1/gx/me"); isOwner.value = !!m.isOwner; } catch (_e) { /* ignore */ }
      const cfg = await $fetch<Record<string, any>>("/api/v1/gx/config");
      const slots = cfg?.media?.slots;
      if (Array.isArray(slots) && slots.length) mediaSlots.value = slots;
      if (cfg?.organization) {
        orgCfg.value = {
          tagGroup: { name: cfg.organization.tagGroup?.name || "品类", options: cfg.organization.tagGroup?.options || [] },
          series: { enabled: cfg.organization.series?.enabled !== false, stripParentheses: cfg.organization.series?.stripParentheses !== false },
          groupDims: Array.isArray(cfg.organization.groupDims) && cfg.organization.groupDims.length ? cfg.organization.groupDims : orgCfg.value.groupDims,
        };
        const keys = groupDims.value.map(d => d.key);
        if (!keys.includes(summaryDim.value)) summaryDim.value = keys[0] || "brand";
      }
      const attrs: Array<Record<string, any>> = Array.isArray(cfg?.attributes) ? cfg.attributes : [];
      if (!attrs.length) return;
      const opts = (n: string): string[] => (attrs.find(a => a.name === n)?.options) || [];
      uiOptions.value = {
        sizes: opts("尺寸").length ? opts("尺寸") : uiOptions.value.sizes,
        specs: opts("规格").length ? opts("规格") : uiOptions.value.specs,
        colors: opts("颜色").length ? opts("颜色") : uiOptions.value.colors,
        materials: opts("材质").length ? opts("材质") : uiOptions.value.materials,
        required: attrs.filter(a => a.required).map(a => a.name),
      };
    } catch (_e) { /* ignore */ }
  }

  async function load() {
    loading.value = true;
    err.value = "";
    try {
      let agg: Record<string, any> | null = null;
      try { agg = await $fetch<Record<string, any>>("/api/v1/ledger"); } catch (_e) { agg = null; }
      if (agg && Array.isArray(agg.items)) {
        try { localStorage.setItem(CACHE_KEY, JSON.stringify(agg)); } catch (_e) { /* ignore */ }
        offlineReadonly.value = false;
        applyAgg(agg);
        void applyGxConfig();
        loading.value = false;
        return;
      }
      // 离线：使用缓存（只读）
      try {
        const c = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
        if (c && Array.isArray(c.items)) { applyAgg(c); offlineReadonly.value = true; loading.value = false; return; }
      } catch (_e) { /* ignore */ }
      const [list, tagList, tree, opts, trashData] = await Promise.all([
        $fetch<{ items?: Array<Record<string, any>> }>("/api/v1/entities", { params: { pageSize: 1000 } }),
        $fetch<Array<{ id: string; name: string }>>("/api/v1/tags"),
        $fetch<Array<{ id: string; name: string }>>("/api/v1/entities/tree"),
        $fetch<Record<string, string[]>>("/api/v1/ui-options").catch(() => ({ sizes: [], specs: [], colors: [], materials: [] }) as Record<string, string[]>),
        $fetch<{ ids?: string[] }>("/api/v1/trash").catch(() => ({ ids: [] })),
      ]);
      tags.value = tagList || [];
      for (const k of Object.keys(trashed)) delete trashed[k];
      for (const id of (trashData.ids || [])) trashed[id] = true;
      locations.value = (tree || []).map(n => ({ id: n.id, name: n.name }));
      uiOptions.value = { sizes: opts.sizes || [], specs: opts.specs || [], colors: opts.colors || [], materials: opts.materials || [], required: (opts as any).required || [] };
      const items = list.items || [];
      rows.value = items.map(summaryToRow);
      loading.value = false;
      await hydrateRows(items.map(i => i.id));
    } catch (e) {
      err.value = "加载失败：" + ((e as Error)?.message ?? String(e));
      loading.value = false;
    }
  }
  function summaryToRow(e: Record<string, any>): Row {
    const parent = e.parent as Record<string, any> | null | undefined;
    return {
      raw: e, id: e.id, name: e.name,
      brand: "", size: "", spec: "", color: "", material: "", paper: "",
      purchase: null, sell: null, pages: null, safety: null,
      qty: e.quantity ?? 0, loc: parent?.name || "", serial: String(e.serial ?? e.serialNumber ?? ""), extra: {}, thumb: null, updated: e.updatedAt || "",
    } as Row;
  }
  async function hydrateRows(ids: string[], concurrency = 8) {
    let i = 0;
    const worker = async () => {
      while (i < ids.length) {
        const id = ids[i++];
        try {
          const d = await $fetch<Record<string, any>>(`/api/v1/entities/${id}`);
          const idx = rows.value.findIndex(r => r.id === id);
          if (idx >= 0) rows.value[idx] = toRow(d);
        } catch (_e) { /* 单条失败忽略 */ }
      }
    };
    await Promise.all(Array.from({ length: Math.min(concurrency, ids.length) }, worker));
  }

  // ---------- 视图状态 / URL / 记忆 ----------
  function view() {
    return {
      brand: filter.brand, size: filter.size, spec: filter.spec, color: filter.color, material: filter.material, q: filter.q, series: filter.series,
      onlyLow: onlyLow.value ? "1" : "", data: dataFilter.value, count: countMode.value ? "1" : "",
      hideSold: hideSoldOut.value ? "" : "0",
      sort: sort.key, dir: String(sort.dir),
    };
  }
  function applyView(v: Record<string, any>) {
    filter.brand = v.brand || ""; filter.size = v.size || ""; filter.spec = v.spec || "";
    filter.color = v.color || ""; filter.material = v.material || ""; filter.q = v.q || ""; filter.series = v.series || "";
    onlyLow.value = v.onlyLow === "1" || v.onlyLow === true;
    hideSoldOut.value = v.hideSold !== "0" && v.hideSold !== false;
    dataFilter.value = v.data || "";
    countMode.value = v.count === "1" || v.count === true;
    sort.key = v.sort || "name"; sort.dir = v.dir === "-1" || v.dir === -1 ? -1 : 1;
  }
  let syncTimer: number | undefined;
  function syncView() {
    window.clearTimeout(syncTimer);
    syncTimer = window.setTimeout(() => {
      const q: Record<string, string> = {};
      const v = view();
      for (const k of Object.keys(v)) if (v[k]) q[k] = String(v[k]);
      router.replace({ query: q });
      // 盘点是「任务模式」而非视图偏好：不落 localStorage，只能从菜单/页内开关进入
      localStorage.setItem("hb.ledger.view", JSON.stringify({ ...v, count: "" }));
    }, 200);
  }
  watch([filter, sort, onlyLow, hideSoldOut, countMode, dataFilter], syncView, { deep: true });
  watch([filter, sort, onlyLow, hideSoldOut, countMode, dataFilter, pageSize], () => { page.value = 1; shown.value = MOBILE_BATCH; }, { deep: true });
  // 侧栏「物品 / 盘点」是同页跳转（/ledger ↔ /ledger?count=1），组件不重挂载，需监听 query 同步盘点模式
  watch(() => route.query.count, (v) => { const want = v === "1"; if (want !== countMode.value) countMode.value = want; });
  watch(cols, () => localStorage.setItem("hb.ledger.cols", JSON.stringify(cols)), { deep: true });
  let histTimer: number | undefined;
  watch(() => filter.q, (v) => { window.clearTimeout(histTimer); histTimer = window.setTimeout(() => pushSearch(v || ""), 1500); });

  // ---------- PWA 安装 / 通知 ----------
  // 不拦截 beforeinstallprompt（preventDefault 会让浏览器控制台报 "Banner not shown"），
  // 安装走浏览器原生入口（Edge/Chrome 地址栏右侧安装图标；iOS Safari 分享菜单）。
  const canInstall = ref(false);
  const notifyOn = ref(false);
  let notifyTimer: number | undefined;
  function detectInstall() {
    const standalone = window.matchMedia?.("(display-mode: standalone)").matches || (navigator as any).standalone === true;
    canInstall.value = !standalone;
  }
  function install() {
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent || "");
    flash(ios ? "iOS：Safari「分享」→「添加到主屏幕」" : "点浏览器地址栏右侧的「安装」图标即可安装到桌面");
  }
  function checkLow() {
    const low = rows.value.filter(isLow);
    if (!low.length) return;
    const key = "hb.ledger.notified." + new Date().toISOString().slice(0, 10);
    if (localStorage.getItem(key)) return;
    localStorage.setItem(key, "1");
    new Notification("待补货提醒", {
      body: `有 ${low.length} 款低于安全库存：${low.slice(0, 5).map(r => r.name).join("、")}${low.length > 5 ? "…" : ""}`,
    });
  }
  async function toggleNotify() {
    if (!("Notification" in window)) { flash("本机不支持通知"); return; }
    if (notifyOn.value) {
      notifyOn.value = false;
      if (notifyTimer) window.clearInterval(notifyTimer);
      return;
    }
    const p = await Notification.requestPermission();
    if (p !== "granted") { flash("未授权通知"); return; }
    notifyOn.value = true;
    checkLow();
    notifyTimer = window.setInterval(checkLow, 30 * 60 * 1000);
    flash("已开启补货提醒（打开本页时）");
  }

  // ---------- 扫码 ----------
  const scanOpen = ref(false);
  const scanMsg = ref("");
  const videoEl = ref<HTMLVideoElement | null>(null);
  let stream: MediaStream | null = null;
  let scanRAF: number | undefined;
  function locate(code: string) {
    const c = code.trim();
    if (!c) return;
    const hit = rows.value.find(r =>
      String(r.raw.assetId || "") === c ||
      String(r.raw.serialNumber || "") === c ||
      r.name.includes(c));
    closeScan();
    if (!hit) { flash("未匹配到：" + c); return; }
    filter.q = hit.name;
    flash("已定位：" + hit.name);
  }
  async function openScan() {
    const w = window as any;
    if (!("BarcodeDetector" in w)) { flash("本机浏览器不支持扫码，可用下方输入编号"); scanOpen.value = true; return; }
    scanOpen.value = true;
    scanMsg.value = "对准条码 / 二维码";
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      await nextTick();
      if (videoEl.value) { videoEl.value.srcObject = stream; await videoEl.value.play(); }
      const det = new w.BarcodeDetector();
      const loop = async () => {
        if (!scanOpen.value || !videoEl.value) return;
        try {
          const codes = await det.detect(videoEl.value);
          if (codes && codes.length) { locate(codes[0].rawValue); return; }
        } catch (_e) { /* ignore */ }
        scanRAF = window.requestAnimationFrame(loop);
      };
      loop();
    } catch (_e) {
      scanMsg.value = "无法打开摄像头，可用下方输入编号";
    }
  }
  function onLocateInput(e: Event) {
    locate((e.target as HTMLInputElement).value);
  }
  function closeScan() {
    scanOpen.value = false;
    if (scanRAF) window.cancelAnimationFrame(scanRAF);
    scanRAF = undefined;
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  }

  // ---------- 拍照上传 ----------
  const fileInput = ref<HTMLInputElement | null>(null);
  let photoTarget: Row | null = null;
  function pickPhoto(r: Row) {
    photoTarget = r;
    fileInput.value?.click();
  }
  async function compressImage(file: File): Promise<Blob> {
    try {
      const img = await new Promise<HTMLImageElement>((res, rej) => {
        const i = new Image();
        i.onload = () => res(i);
        i.onerror = rej;
        i.src = URL.createObjectURL(file);
      });
      const max = 1600;
      let w = img.width, h = img.height;
      if (Math.max(w, h) > max) { const s = max / Math.max(w, h); w = Math.round(w * s); h = Math.round(h * s); }
      const c = document.createElement("canvas");
      c.width = w; c.height = h;
      const ctx = c.getContext("2d");
      if (ctx) ctx.drawImage(img, 0, 0, w, h);
      let q = 0.85, blob: Blob | null = null;
      for (let i = 0; i < 6; i++) {
        blob = await new Promise<Blob | null>(res => c.toBlob(b => res(b), "image/jpeg", q));
        if (blob && blob.size <= 400 * 1024) break;
        q -= 0.12;
      }
      URL.revokeObjectURL(img.src);
      return blob || file;
    } catch (_e) {
      return file;
    }
  }
  async function onFile(e: Event) {
    const input = e.target as HTMLInputElement;
    const f = input.files?.[0];
    input.value = "";
    const target = photoTarget;
    if (!f || !target) return;
    flash("压缩并上传中…");
    const blob = await compressImage(f);
    const form = new FormData();
    form.append("file", blob, "photo.jpg");
    form.append("name", "photo.jpg");
    form.append("type", "photo");
    form.append("primary", "true");
    try {
      await $fetch(`/api/v1/entities/${target.id}/attachments`, { method: "POST", body: form });
      const d = await $fetch<Record<string, any>>(`/api/v1/entities/${target.id}`);
      target.thumb = d.imageId || d.thumbnailId || target.thumb;
      flash("已上传封面");
    } catch (err2) {
      flash("上传失败：" + ((err2 as Error)?.message ?? String(err2)));
    }
  }

  // ---------- 左滑 ----------
  const swipe = reactive<Record<string, number>>({});
  let touchStartX = 0;
  let touchStartY = 0;
  let touchMoved = false;
  let lpTimer: number | undefined;
  function onTS(e: TouchEvent, r: Row) {
    if (countMode.value) return;
    touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; touchMoved = false; swipe[r.id] = 0;
    if (lpTimer) window.clearTimeout(lpTimer);
    lpTimer = window.setTimeout(() => {
      lpTimer = undefined;
      sel[r.id] = !sel[r.id];
      if (sel[r.id]) { swipe[r.id] = 0; buzz(20); }
    }, 550);
  }
  function onTM(e: TouchEvent, r: Row) {
    const dx = e.touches[0].clientX - touchStartX;
    const dy = e.touches[0].clientY - touchStartY;
    if (Math.abs(dx) > 10 || Math.abs(dy) > 10) { if (lpTimer) { window.clearTimeout(lpTimer); lpTimer = undefined; } }
    if (Math.abs(dy) > Math.abs(dx)) { swipe[r.id] = 0; return; }
    if (Math.abs(dx) > 8) touchMoved = true;
    swipe[r.id] = Math.max(-150, Math.min(0, dx));
  }
  function onTE(r: Row) {
    if (lpTimer) { window.clearTimeout(lpTimer); lpTimer = undefined; }
    swipe[r.id] = (swipe[r.id] || 0) < -60 ? -150 : 0;
  }
  function closeSwipe(r: Row) { swipe[r.id] = 0; }
  function cardStyle(r: Row) { return { transform: `translateX(${swipe[r.id] || 0}px)`, transition: touchMoved ? "none" : "transform .15s" }; }

  onMounted(async () => {
    detectInstall();
    syncOq();
    window.addEventListener("hb:offline-queue", syncOq);
    window.addEventListener("scroll", onScrollLoadMore, { passive: true });
    connectWS();
    window.addEventListener("pagehide", onWSPageHide);
    window.addEventListener("pageshow", onWSPageShow);
    document.addEventListener("visibilitychange", onWSVisChange);
    try { bigFont.value = localStorage.getItem("groza.bigfont") === "1"; applyBigFont(); } catch (_e) { /* ignore */ }
    const savedCols = localStorage.getItem("hb.ledger.cols");
    const savedVm = localStorage.getItem("hb.ledger.viewmode");
    viewMode.value = (savedVm === "card" || savedVm === "list") ? savedVm : (isMobile.value ? "card" : "list");
    if (savedCols) { try { Object.assign(cols, JSON.parse(savedCols)); } catch (_e) { /* ignore */ } }
    const savedPresets = localStorage.getItem("hb.ledger.presets");
    if (savedPresets) { try { presets.value = JSON.parse(savedPresets); } catch (_e) { /* ignore */ } }
    const hasQ = Object.keys(route.query).some(k => ["brand", "size", "spec", "color", "q", "series", "onlyLow", "hideSold", "count", "data", "sort", "dir"].includes(k));
    if (hasQ) applyView(route.query as Record<string, any>);
    else {
      const saved = localStorage.getItem("hb.ledger.view");
      if (saved) { try { applyView(JSON.parse(saved)); } catch (_e) { /* ignore */ } }
    }
    // 盘点模式只认当前 URL（兼容历史 localStorage 里残留的 count=1）
    countMode.value = route.query.count === "1";
    await load();
    await nextTick();
    onScrollLoadMore();
  });
  onBeforeUnmount(() => {
    window.removeEventListener("hb:offline-queue", syncOq);
    window.removeEventListener("scroll", onScrollLoadMore);
    window.removeEventListener("pagehide", onWSPageHide);
    window.removeEventListener("pageshow", onWSPageShow);
    document.removeEventListener("visibilitychange", onWSVisChange);
    closeScan();
    if (notifyTimer) window.clearInterval(notifyTimer);
    closeWSForFreeze();
    if (wsRefresh) window.clearTimeout(wsRefresh);
    if (aiConfirm.value) { URL.revokeObjectURL(aiConfirm.value.url); aiConfirm.value = null; }
  });

  function flash(t: string) {
    try { toast(t); } catch (_e) { msg.value = t; }
  }

  // ---------- 撤销 ----------
  function recordUndo(label: string, items: UndoItem[]) {
    undoLast.value = { label, items: items.filter(i => i.prev !== undefined) };
    if (!undoLast.value.items.length) undoLast.value = null;
  }
  async function undo() {
    const u = undoLast.value;
    if (!u) { flash("没有可撤销的操作"); return; }
    for (const it of u.items) {
      if (it.field === "qty") {
        it.row.qty = it.prev;
        await $fetch(`/api/v1/entities/${it.row.id}`, { method: "PATCH", body: { quantity: Number(it.prev) } });
      } else {
        const name = it.field === "purchase" ? "进价" : it.field === "sell" ? "售价" : "安全库存";
        it.row[it.field] = it.prev;
        await putFields(it.row, { [name]: it.prev ?? 0 });
      }
    }
    flash("已撤销：" + u.label);
    undoLast.value = null;
  }

  // ---------- 字段写入 ----------
  function buildFields(row: Row, changes: Record<string, any>): Array<Record<string, any>> {
    return (row.raw.fields as Array<Record<string, any>>).map(f => {
      const x: Record<string, any> = { id: f.id, name: f.name, type: f.type };
      if (f.type === "text") x.textValue = f.textValue ?? "";
      else if (f.type === "boolean") x.booleanValue = !!f.booleanValue;
      else x.numberValue = f.numberValue ?? 0;
      if (f.name in changes) {
        if (f.type === "text") x.textValue = String(changes[f.name]);
        else if (f.type === "boolean") x.booleanValue = !!changes[f.name];
        else x.numberValue = Number(changes[f.name]);
      }
      return x;
    });
  }
  const fieldsOpen = ref(false);
  const fieldsItem = ref<Row | null>(null);
  const fieldsDraft = ref<Array<Record<string, any>>>([]);
  const fieldsBusy = ref(false);
  function openFields(r: Row) {
    fieldsItem.value = r;
    fieldsDraft.value = ((r.raw.fields as Array<Record<string, any>>) || []).map(f => ({
      id: f.id, name: f.name, type: f.type || "text",
      value: f.type === "text" ? (f.textValue ?? "") : f.type === "boolean" ? !!f.booleanValue : (f.numberValue ?? 0),
    }));
    fieldsOpen.value = true;
  }
  async function saveFields() {
    const r = fieldsItem.value; if (!r) return;
    const miss = fieldsDraft.value.filter(f => requiredSet.value.has(f.name) && (f.value === "" || f.value === null || f.value === undefined)).map(f => f.name);
    if (miss.length && !window.confirm(`必填字段未填：${miss.join("、")}。仍要保存？`)) return;
    const changes: Record<string, any> = {};
    for (const f of fieldsDraft.value) changes[f.name] = f.value;
    fieldsBusy.value = true;
    const ok = await putFields(r, changes);
    fieldsBusy.value = false;
    if (ok) { fieldsOpen.value = false; buzz(); flash("字段已保存"); }
  }
  async function putFields(row: Row, changes: Record<string, any>): Promise<boolean> {
    const fields = buildFields(row, changes);
    saving[row.id] = true;
    try {
      const fresh = await $fetch<Record<string, any>>(`/api/v1/ledger/${row.id}`, {
        method: "PATCH",
        body: { fields: changes, updatedAt: row.updated || undefined },
      });
      row.raw = { ...row.raw, ...fresh };
      const f = fieldMap(fresh);
      row.brand = f["品牌"] || row.brand; row.size = f["尺寸"] || row.size;
      row.spec = f["规格"] || row.spec; row.color = f["颜色"] || row.color;
      row.material = f["材质"] || row.material;
      row.purchase = num(f["进价"]) ?? row.purchase; row.sell = num(f["售价"]) ?? row.sell;
      row.safety = num(f["安全库存"]) ?? row.safety;
      row.updated = fresh.updatedAt || row.updated;
      return true;
    } catch (e) {
      flash("保存失败：" + ((e as Error)?.message ?? String(e)));
      return false;
    } finally {
      saving[row.id] = false;
    }
  }

  function snapshot(r: Row) {
    preEdit[r.id] = { qty: r.qty, purchase: r.purchase, sell: r.sell, safety: r.safety };
  }
  async function patchQty(r: Row) {
    saving[r.id] = true;
    try {
      await $fetch(`/api/v1/entities/${r.id}`, { method: "PATCH", body: { quantity: Number(r.qty) } });
    } catch (e) {
      flash("保存失败：" + ((e as Error)?.message ?? String(e)));
    } finally {
      saving[r.id] = false;
    }
  }
  async function onQtyChange(r: Row) {
    const q = Number(r.qty);
    if (!Number.isFinite(q) || q < 0) { flash("数量无效"); return; }
    const prev = preEdit[r.id]?.qty;
    r.qty = q;
    recordUndo("数量", [{ row: r, field: "qty", prev }]);
    await patchQty(r);
    markSaved(r.id);
    flash(`已保存：${r.name} → ${q}`);
  }
  async function step(r: Row, d: number) {
    const prev = r.qty;
    r.qty = Math.max(0, Number(r.qty || 0) + d);
    recordUndo("数量", [{ row: r, field: "qty", prev }]);
    await patchQty(r);
    markSaved(r.id);
  }
  async function setPrice(r: Row, which: "purchase" | "sell") {
    const v = num(which === "purchase" ? r.purchase : r.sell);
    const prev = preEdit[r.id]?.[which];
    const ok = await putFields(r, { [which === "purchase" ? "进价" : "售价"]: v ?? 0 });
    if (ok) { r[which] = v; markSaved(r.id); recordUndo(which === "purchase" ? "进价" : "售价", [{ row: r, field: which, prev }]); flash("已保存价格"); }
  }
  async function setSafety(r: Row) {
    const v = num(r.safety) ?? 0;
    const prev = preEdit[r.id]?.safety;
    const ok = await putFields(r, { 安全库存: v });
    if (ok) { r.safety = v; markSaved(r.id); recordUndo("安全库存", [{ row: r, field: "safety", prev }]); flash("已保存安全库存"); }
  }
  const safetyEditing = reactive<Record<string, boolean>>({});
  function editSafety(r: Row) { snapshot(r); safetyEditing[r.id] = true; }
  async function doneSafetyEdit(r: Row) { await setSafety(r); safetyEditing[r.id] = false; }
  function focusEl(el: Element | null) { (el as HTMLInputElement | null)?.focus?.(); }

  // 手机卡片属性行：点分隔纯文本，只拼接有值的项
  function attrLine(r: Row): string {
    const parts = [r.brand, r.size, r.spec, r.color, r.material].filter(Boolean) as string[];
    for (const f of extraFields.value) {
      const v = r.extra[f.name];
      if (!v) continue;
      parts.push(f.type === "boolean" ? `${f.name} ✓` : `${f.name} ${v}`);
    }
    return parts.join(" · ");
  }

  // ---------- 计算 ----------
  const uniq = (key: keyof Row) => [...new Set(rows.value.map(r => String(r[key] ?? "")).filter(Boolean))].sort();
  const brands = computed(() => uniq("brand"));
  const sizes = computed(() => uniq("size"));
  const specs = computed(() => uniq("spec"));
  const colors = computed(() => uniq("color"));
  const materials = computed(() => uniq("material"));
  const activeFilterCount = computed(() => {
    let n = 0;
    if (filter.brand) n++; if (filter.size) n++; if (filter.spec) n++;
    if (filter.color) n++; if (filter.material) n++; if (filter.q) n++;
    if (dataFilter.value) n++; if (onlyLow.value) n++;
    return n;
  });

  function isSoldOut(r: Row): boolean { return (r.qty || 0) <= 0; }
  function isLow(r: Row): boolean { return (r.safety ?? 0) > 0 && (r.qty || 0) < (r.safety ?? 0); }
  function isTrashed(r: Row): boolean { return !!trashed[r.id]; }
  const trashedCount = computed(() => Object.keys(trashed).filter(k => trashed[k]).length);
  async function purgeOne(r: Row) {
    if (!isOwner.value) { flash("仅管理员可彻底删除"); return; }
    if (!isTrashed(r)) { flash("仅“待删除”的物品可彻底删除"); return; }
    if (!window.confirm(`彻底删除「${r.name}」？此操作不可恢复。`)) return;
    saving[r.id] = true;
    try {
      await $fetch("/api/v1/trash2/purge", { method: "POST", body: { confirm: true, ids: [r.id] } });
      delete trashed[r.id];
      buzz(30); flash("已彻底删除：" + r.name);
      await load();
    } catch (e) { flash("彻底删除失败：" + ((e as Error)?.message ?? String(e))); }
    finally { saving[r.id] = false; }
  }
  async function purgeSelected() {
    if (!isOwner.value) { flash("仅管理员可彻底删除"); return; }
    const ids = selectedRows.value.filter(r => isTrashed(r)).map(r => r.id);
    if (!ids.length) { flash("所选里没有“待删除”的物品"); return; }
    if (!window.confirm(`彻底删除所选 ${ids.length} 款？不可恢复。`)) return;
    try {
      await $fetch("/api/v1/trash2/purge", { method: "POST", body: { confirm: true, ids } });
      for (const id of ids) delete trashed[id];
      clearSel(); buzz(30); flash(`已彻底删除 ${ids.length} 款`);
      await load();
    } catch (e) { flash("彻底删除失败：" + ((e as Error)?.message ?? String(e))); }
  }
  function setSerial(r: Row) { void putSerial(r, r.serial); }
  async function putSerial(r: Row, val: string) {
    saving[r.id] = true;
    try {
      await $fetch(`/api/v1/ledger/${r.id}`, { method: "PATCH", body: { serial: val, updatedAt: r.updated, fields: {} } });
      r.raw.serial = val;
      r.updated = new Date().toISOString();
      markSaved(r.id); flash("已保存库位");
    } catch (e) { flash("保存库位失败：" + ((e as Error)?.message ?? String(e))); }
    finally { saving[r.id] = false; }
  }
  function promptSerial(r: Row) {
    const v = window.prompt("库位/货架位（如 A-3，留空清除）", r.serial || "");
    if (v === null) return;
    r.serial = v.trim();
    void putSerial(r, r.serial);
  }

  const galleryOpen = ref(false);
  const galleryId = ref("");
  const galleryTitle = ref("");
  const galleryImgs = ref<Array<Record<string, any>>>([]);
  const galleryBusy = ref(false);
  const galleryInput = ref<HTMLInputElement | null>(null);
  function pickGallery() { galleryInput.value?.click(); }
  function attUrl(aid: string) { return `/api/v1/entities/${galleryId.value}/attachments/${aid}`; }
  const gallerySlot = ref("detail");
  function slotName(key: string): string { return mediaSlots.value.find(s => s.key === key)?.name || key || "未分类"; }
  function slotKeyOf(a: Record<string, any>): string { const t = String(a.title || ""); return mediaSlots.value.some(s => s.key === t) ? t : ""; }
  async function setSlot(a: Record<string, any>, key: string) {
    galleryBusy.value = true;
    try {
      await $fetch(`/api/v1/entities/${galleryId.value}/attachments/${a.id}`, { method: "PUT", body: { type: a.type || "photo", title: key, primary: !!a.primary } });
      galleryImgs.value = galleryImgs.value.map(x => x.id === a.id ? { ...x, title: key } : x);
    } catch (e) { flash("设置槽位失败：" + ((e as Error)?.message ?? String(e))); }
    galleryBusy.value = false;
  }
  async function showGallery(r: Row) {
    galleryId.value = r.id; galleryTitle.value = r.name; galleryOpen.value = true; galleryBusy.value = true; galleryImgs.value = [];
    gallerySlot.value = mediaSlots.value.find(s => s.multiple)?.key || mediaSlots.value[0]?.key || "detail";
    try {
      const d = await $fetch<Record<string, any>>(`/api/v1/entities/${r.id}`);
      galleryImgs.value = (d.attachments || []).filter((a: any) => String(a.mimeType || "").startsWith("image/"));
    } catch (_e) { galleryImgs.value = []; }
    galleryBusy.value = false;
  }
  async function onGalleryFiles(e: Event) {
    const input = e.target as HTMLInputElement;
    const files = Array.from(input.files || []);
    input.value = "";
    if (!files.length) return;
    galleryBusy.value = true;
    let first = galleryImgs.value.length === 0;
    const slot = gallerySlot.value || "detail";
    for (const f of files) {
      try {
        const before = new Set(galleryImgs.value.map((x: any) => String(x.id)));
        const blob = await compressImage(f);
        const form = new FormData();
        form.append("file", blob, "photo.jpg");
        form.append("name", "photo.jpg");
        form.append("type", "photo");
        form.append("primary", first ? "true" : "false");
        first = false;
        const d = await $fetch<Record<string, any>>(`/api/v1/entities/${galleryId.value}/attachments`, { method: "POST", body: form });
        galleryImgs.value = (d.attachments || []).filter((a: any) => String(a.mimeType || "").startsWith("image/"));
        const fresh = galleryImgs.value.find((a: any) => !before.has(String(a.id)));
        if (fresh) await setSlot(fresh, slot);
      } catch (err) { flash("上传失败：" + ((err as Error)?.message ?? String(err))); }
    }
    galleryBusy.value = false;
  }
  async function delGalleryImg(a: Record<string, any>) {
    if (!window.confirm("删除这张图片？")) return;
    galleryBusy.value = true;
    try {
      await $fetch(`/api/v1/entities/${galleryId.value}/attachments/${a.id}`, { method: "DELETE" });
      galleryImgs.value = galleryImgs.value.filter(x => x.id !== a.id);
    } catch (e) { flash("删除失败：" + ((e as Error)?.message ?? String(e))); }
    galleryBusy.value = false;
  }
  async function setPrimaryImg(a: Record<string, any>) {
    galleryBusy.value = true;
    try {
      await $fetch(`/api/v1/entities/${galleryId.value}/attachments/${a.id}`, { method: "PUT", body: { type: a.type || "photo", title: a.title || "", primary: true } });
      galleryImgs.value = galleryImgs.value.map(x => ({ ...x, primary: x.id === a.id }));
    } catch (e) { flash("设置封面失败：" + ((e as Error)?.message ?? String(e))); }
    galleryBusy.value = false;
  }
  async function closeGallery() { galleryOpen.value = false; await load(); }

  async function purgeAll() {
    if (!isOwner.value) { flash("仅管理员可清空回收站"); return; }
    const n = trashedCount.value;
    if (!n) { flash("回收站为空"); return; }
    if (!window.confirm(`清空回收站（${n} 款）？此操作不可恢复。`)) return;
    try {
      await $fetch("/api/v1/trash2/purge", { method: "POST", body: { confirm: true } });
      for (const k of Object.keys(trashed)) delete trashed[k];
      buzz(30); flash(`回收站已清空（${n} 款）`);
      await load();
    } catch (e) { flash("清空失败：" + ((e as Error)?.message ?? String(e))); }
  }
  function trashAgeDays(r: Row): number | null {
    const e = trashEntries[r.id];
    if (!e?.deletedAt) return null;
    const t = new Date(e.deletedAt).getTime();
    if (isNaN(t)) return null;
    return Math.max(0, Math.floor((Date.now() - t) / 86400000));
  }
  async function persistTrash() {
    const entries: Record<string, { deletedAt: string; name?: string }> = {};
    for (const id of Object.keys(trashed).filter(k => trashed[k])) {
      const prev = trashEntries[id];
      entries[id] = {
        deletedAt: prev?.deletedAt || new Date().toISOString(),
        name: rows.value.find(r => r.id === id)?.name || prev?.name,
      };
      trashEntries[id] = entries[id];
    }
    await $fetch("/api/v1/trash2", { method: "PUT", body: { entries } });
  }
  async function toggleTrash(r: Row) {
    const mark = !trashed[r.id];
    if (mark) trashed[r.id] = true; else delete trashed[r.id];
    try {
      await persistTrash();
      flash((mark ? "已标记删除：" : "已恢复：") + r.name);
    } catch (e) {
      if (mark) delete trashed[r.id]; else trashed[r.id] = true;
      flash("操作失败：" + ((e as Error)?.message ?? String(e)));
    }
  }
  async function batchTrash() {
    const list = selectedRows.value;
    if (!list.length) return;
    for (const r of list) trashed[r.id] = true;
    try { await persistTrash(); flash(`已标记删除 ${list.length} 款`); clearSel(); }
    catch (e) { flash("操作失败：" + ((e as Error)?.message ?? String(e))); }
  }
  function dataMatch(r: Row): boolean {
    switch (dataFilter.value) {
      case "noSafety": return !(r.safety && r.safety > 0);
      case "noImg": return !r.thumb;
      case "noSerial": return !r.serial;
      case "noPrice": return r.purchase === null && r.sell === null;
      case "soldout": return isSoldOut(r);
      case "low": return isLow(r);
      case "trashed": return isTrashed(r);
      case "noBrand": return !r.brand;
      case "noSize": return !r.size;
      case "noSpec": return !r.spec;
      case "required": return missingRequired(r).length > 0;
      default: return true;
    }
  }
  const filteredBase = computed(() => rows.value.filter(r =>
    (!filter.brand || r.brand === filter.brand) &&
    (!filter.size || r.size === filter.size) &&
    (!filter.spec || r.spec === filter.spec) &&
    (!filter.color || r.color === filter.color) &&
    (!filter.material || r.material === filter.material) &&
    (!filter.series || seriesKey(r) === filter.series) &&
    Object.entries(extraFilters).every(([nm, v]) => !v || String(r.extra?.[nm] ?? "") === v) &&
    (!filter.q || nq(r.name).includes(nq(filter.q)) || nq(r.brand).includes(nq(filter.q)) || nq(r.size).includes(nq(filter.q)) || nq(r.serial).includes(nq(filter.q)) || nq(String(r.raw.assetId || "")).includes(nq(filter.q))) &&
    (!onlyLow.value || isLow(r)) &&
    dataMatch(r),
  ));
  // data=soldout 是专门查看售罄的视图，此时隐藏售罄不生效
  const filtered = computed(() => filteredBase.value.filter(r =>
    !hideSoldOut.value || dataFilter.value === "soldout" || !isSoldOut(r),
  ));
  const soldCount = computed(() => filteredBase.value.filter(isSoldOut).length);
  const sorted = computed(() => {
    const k = sort.key, dir = sort.dir;
    return [...filtered.value].sort((a, b) => {
      let va: any, vb: any;
      if (k === "low") { va = isLow(a) ? 1 : 0; vb = isLow(b) ? 1 : 0; }
      else {
        va = (a as Record<string, any>)[k]; vb = (b as Record<string, any>)[k];
        if (typeof va === "number" || typeof vb === "number") { va = Number(va ?? -Infinity); vb = Number(vb ?? -Infinity); }
        else { va = String(va ?? ""); vb = String(vb ?? ""); }
      }
      return va < vb ? -1 * dir : va > vb ? 1 * dir : 0;
    });
  });
  const totalPages = computed(() => Math.max(1, Math.ceil(sorted.value.length / pageSize.value)));
  const DEDICATED_FIELDS = new Set(["品牌", "尺寸", "规格", "颜色", "材质", "进价", "售价", "安全库存"]);
  const schemaFields = computed(() => {
    const seen = new Map<string, string>();
    for (const r of rows.value) {
      for (const f of ((r.raw.fields as Array<Record<string, any>>) || [])) {
        if (!f.name || seen.has(f.name)) continue;
        seen.set(f.name, f.type || "text");
      }
    }
    return [...seen.entries()].map(([name, type]) => ({ name, type }));
  });
  const extraFields = computed(() => {
    const list = schemaFields.value.filter(f => !DEDICATED_FIELDS.has(f.name));
    const ord = fieldOrder.value;
    if (!ord.length) return list;
    return [...list].sort((a, b) => {
      const ia = ord.indexOf(a.name), ib = ord.indexOf(b.name);
      if (ia < 0 && ib < 0) return 0;
      if (ia < 0) return 1;
      if (ib < 0) return -1;
      return ia - ib;
    });
  });
  const fieldOrder = ref<string[]>([]);
  try { fieldOrder.value = JSON.parse(localStorage.getItem("hb.ledger.fieldOrder") || "[]"); } catch (_e) { fieldOrder.value = []; }
  function moveField(name: string, dir: number) {
    const ord = [...fieldOrder.value];
    if (!ord.includes(name)) ord.push(name);
    const i = ord.indexOf(name), j = i + dir;
    if (j < 0 || j >= ord.length) return;
    [ord[i], ord[j]] = [ord[j], ord[i]];
    fieldOrder.value = ord;
    try { localStorage.setItem("hb.ledger.fieldOrder", JSON.stringify(ord)); } catch (_e) { /* ignore */ }
  }
  const requiredSet = computed(() => new Set(uiOptions.value.required || []));
  function missingRequired(r: Row): string[] {
    const miss: string[] = [];
    for (const name of (uiOptions.value.required || [])) {
      const v = r.extra?.[name];
      if (v === "" || v === null || v === undefined) miss.push(name);
    }
    return miss;
  }
  watch(extraFields, (list) => { for (const f of list) if (!(f.name in cols)) cols[f.name] = true; }, { immediate: true });
  const extraFilterOptions = computed(() => {
    const res: Array<{ name: string; options: string[] }> = [];
    for (const f of extraFields.value) {
      if (f.type !== "text") continue;
      const set = new Set<string>();
      for (const r of rows.value) { const v = r.extra?.[f.name]; if (v) set.add(String(v)); }
      if (set.size && set.size <= 30) res.push({ name: f.name, options: [...set].sort((a, b) => a.localeCompare(b, "zh")) });
    }
    return res;
  });
  function rowExtra(e: Record<string, any>): Record<string, any> {
    const o: Record<string, any> = {};
    for (const f of (e.fields || [])) {
      o[f.name] = f.type === "text" ? (f.textValue ?? "") : f.type === "boolean" ? !!f.booleanValue : (f.numberValue ?? 0);
    }
    return o;
  }
  async function setExtra(r: Row, name: string, type: string) {
    const val = r.extra[name];
    const payload = type === "boolean" ? !!val : type === "number" ? Number(val) : String(val ?? "");
    const ok = await putFields(r, { [name]: payload });
    if (ok) flash("已保存：" + name);
  }
  const paged = computed(() => {
    const start = (page.value - 1) * pageSize.value;
    return sorted.value.slice(start, start + pageSize.value);
  });
  // 移动端无限滚动：首批 30 条，哨兵接近视口即追加（scroll 监听，IO 对快速跳转不可靠）
  const MOBILE_BATCH = 30;
  const shown = ref(MOBILE_BATCH);
  const shownList = computed(() => sorted.value.slice(0, shown.value));
  const loadMoreEl = ref<HTMLElement | null>(null);
  function onScrollLoadMore() {
    const el = loadMoreEl.value;
    if (!el || shown.value >= sorted.value.length) return;
    if (el.getBoundingClientRect().top < window.innerHeight + 400) shown.value += MOBILE_BATCH;
  }
  function gotoPage(p: number) {
    page.value = Math.min(Math.max(1, p), totalPages.value);
    if (import.meta.client) window.scrollTo({ top: 0, behavior: "smooth" });
  }
  watch(totalPages, (tp) => { if (page.value > tp) page.value = tp; });
  const totals = computed(() => {
    let qty = 0, cost = 0, retail = 0, low = 0, sold = 0;
    for (const r of filtered.value) {
      qty += r.qty || 0; cost += (r.purchase ?? 0) * (r.qty || 0); retail += (r.sell ?? 0) * (r.qty || 0);
      if (isLow(r)) low += 1; if (isSoldOut(r)) sold += 1;
    }
    return { qty, cost, retail, low, sold };
  });

  // ---------- 动效 ----------
  const anim = reactive({ qty: 0, cost: 0, retail: 0 });
  let animRAF: number | undefined;
  watch(totals, () => {
    const from = { ...anim };
    const to = { qty: totals.value.qty, cost: totals.value.cost, retail: totals.value.retail };
    const start = performance.now();
    const dur = 500;
    if (animRAF) cancelAnimationFrame(animRAF);
    const stepAnim = (t: number) => {
      const k = Math.min(1, (t - start) / dur);
      const e = 1 - Math.pow(1 - k, 3);
      anim.qty = from.qty + (to.qty - from.qty) * e;
      anim.cost = from.cost + (to.cost - from.cost) * e;
      anim.retail = from.retail + (to.retail - from.retail) * e;
      if (k < 1) animRAF = requestAnimationFrame(stepAnim);
      else { anim.qty = to.qty; anim.cost = to.cost; anim.retail = to.retail; }
    };
    animRAF = requestAnimationFrame(stepAnim);
  });
  const saved = reactive<Record<string, number>>({});
  function markSaved(id: string) {
    buzz(12);
    saved[id] = Date.now();
    window.setTimeout(() => { if (saved[id] && Date.now() - saved[id] >= 900) delete saved[id]; }, 1000);
  }
  function isSaved(r: Row): boolean { return !!saved[r.id]; }
  const summaryGroups = computed(() => {
    const m: Record<string, { qty: number; cost: number }> = {};
    for (const r of filtered.value) {
      const k = summaryDim.value === "series" ? seriesKey(r) : String((r as Record<string, any>)[summaryDim.value] || "（未填）");
      if (!m[k]) m[k] = { qty: 0, cost: 0 };
      m[k].qty += r.qty || 0; m[k].cost += (r.purchase ?? 0) * (r.qty || 0);
    }
    const arr = Object.entries(m).map(([name, v]) => ({ name, ...v })).sort((a, b) => b.qty - a.qty);
    const max = Math.max(1, ...arr.map(a => a.qty));
    return arr.map(a => ({ ...a, pct: Math.round((a.qty / max) * 100) }));
  });

  // ---------- 盘点 ----------
  // 盘点 = 极简对账视图：只保留数量修改（即改即存），隐藏多选/操作列/其余编辑器
  watch(countMode, v => { if (v) { for (const k of Object.keys(sel)) delete sel[k]; } });

  function setSort(k: string) {
    if (sort.key === k) sort.dir = sort.dir === 1 ? -1 : 1;
    else { sort.key = k; sort.dir = 1; }
  }
  function fmt(n: number | null): string { return n === null || n === undefined ? "" : Number(n).toFixed(2); }
  function fmtDate(iso: string): string {
    if (!iso) return "-";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const p = (x: number) => String(x).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function imgUrl(r: Row): string { return r.thumb ? `/api/v1/entities/${r.id}/attachments/${r.thumb}` : ""; }
  function revealImg(e: Event) {
    const img = e.target as HTMLImageElement;
    const done = () => img.classList.remove("opacity-0");
    if (typeof img.decode === "function") img.decode().then(done, done);
    else done();
  }
  const arrow = (k: string) => (sort.key === k ? (sort.dir === 1 ? " ▲" : " ▼") : "");
  function rowClass(r: Row): string {
    if (isTrashed(r)) return "bg-destructive/10";
    if (isLow(r)) return "bg-amber-500/10";
    if (isSoldOut(r)) return "text-muted-foreground bg-muted/40";
    return "hover:bg-muted/50";
  }

  // ---------- 批量 ----------
  const selectedRows = computed(() => rows.value.filter(r => sel[r.id]));
  const selectedCount = computed(() => selectedRows.value.length);
  function toggleAll() {
    const all = paged.value.length > 0 && paged.value.every(r => sel[r.id]);
    for (const r of paged.value) sel[r.id] = !all;
  }
  function clearSel() { for (const k of Object.keys(sel)) sel[k] = false; }

  // 批量差异预览：先预览 → 确认 → 执行；执行后可用既有「撤销」回退
  const batchPreview = ref<{ label: string; rows: Array<{ name: string; from: string; to: string }>; total: number; run: () => Promise<void> } | null>(null);
  const batchRunning = ref(false);
  function openBatchPreview(label: string, rows: Array<{ name: string; from: string; to: string }>, run: () => Promise<void>) {
    batchPreview.value = { label, rows: rows.slice(0, 50), total: rows.length, run };
  }
  async function confirmBatch() {
    const bp = batchPreview.value;
    if (!bp) return;
    batchRunning.value = true;
    try { await bp.run(); } finally { batchRunning.value = false; batchPreview.value = null; }
  }
  function cancelBatch() { batchPreview.value = null; }

  function batchQty() {
    const v = Number(batch.qty);
    if (!Number.isFinite(v) || v < 0) { flash("填批量数量"); return; }
    const targets = selectedRows.value;
    openBatchPreview(`批量改数量 → ${v}`, targets.map(r => ({ name: r.name, from: String(r.qty), to: String(v) })), async () => {
      const items: UndoItem[] = targets.map(r => ({ row: r, field: "qty", prev: r.qty }));
      for (const r of targets) { await $fetch(`/api/v1/entities/${r.id}`, { method: "PATCH", body: { quantity: v } }); r.qty = v; }
      recordUndo("批量数量", items);
      flash(`批量改数量完成（${targets.length} 条）`);
    });
  }
  function batchPrice(which: "purchase" | "sell") {
    const v = num(which === "purchase" ? batch.purchase : batch.sell);
    if (v === null) { flash("填批量价格"); return; }
    const targets = selectedRows.value;
    const fld = which === "purchase" ? "进价" : "售价";
    openBatchPreview(`批量改${fld} → ${v}`, targets.map(r => ({ name: r.name, from: fmt(r[which]), to: fmt(v) })), async () => {
      const items: UndoItem[] = targets.map(r => ({ row: r, field: which, prev: r[which] }));
      for (const r of targets) {
        const ok = await putFields(r, { [fld]: v });
        if (ok) r[which] = v;
      }
      recordUndo(which === "purchase" ? "批量进价" : "批量售价", items);
      flash(`批量改${fld}完成（${targets.length} 条）`);
    });
  }
  function batchSafety() {
    const v = num(batch.safety);
    if (v === null) { flash("填批量安全库存"); return; }
    const targets = selectedRows.value;
    openBatchPreview(`批量设安全库存 → ${v}`, targets.map(r => ({ name: r.name, from: String(r.safety ?? ""), to: String(v) })), async () => {
      const items: UndoItem[] = targets.map(r => ({ row: r, field: "safety", prev: r.safety }));
      for (const r of targets) {
        const ok = await putFields(r, { 安全库存: v });
        if (ok) r.safety = v;
      }
      recordUndo("批量安全库存", items);
      flash(`批量设安全库存完成（${targets.length} 条）`);
    });
  }
  async function batchTag() {
    if (!batch.tag) { flash("选标签"); return; }
    const tag = tags.value.find(t => t.id === batch.tag);
    for (const r of selectedRows.value) {
      const cur = (r.raw.tags || []).map((t: Record<string, any>) => String(t.id));
      if (!cur.includes(batch.tag)) cur.push(batch.tag);
      await $fetch(`/api/v1/entities/${r.id}`, { method: "PATCH", body: { tagIds: cur } });
      r.raw.tags = [...(r.raw.tags || []), { id: batch.tag, name: tag?.name }];
    }
    flash(`批量加标签完成（${selectedCount.value} 条）`);
  }
  // ---------- 离线队列 / 实时刷新 ----------
  const oq = useOfflineQueue();
  const offline = ref(false);
  const pendingN = ref(0);
  const wsOk = ref(false);
  let ws: WebSocket | null = null;
  let wsRetry: number | undefined;
  let wsRefresh: number | undefined;
  function syncOq() {
    offline.value = oq.isOffline();
    pendingN.value = oq.pending();
  }
  function connectWS() {
    try {
      const scheme = location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(`${scheme}//${location.host}/api/v1/ws/events`);
      ws.onopen = () => { wsOk.value = true; };
      ws.onclose = () => {
        wsOk.value = false;
        wsRetry = window.setTimeout(connectWS, 5000);
      };
      ws.onmessage = (ev) => {
        let d: any;
        try { d = JSON.parse(String(ev.data)); } catch (_e) { return; }
        const type = String(d?.event || d?.type || "");
        if (type.includes("mutation")) {
          window.clearTimeout(wsRefresh);
          wsRefresh = window.setTimeout(() => { void load(); }, 1500);
        }
      };
      ws.onerror = () => { wsOk.value = false; };
    } catch (_e) { /* 忽略 */ }
  }
  function closeWSForFreeze() {
    // 页面进 bfcache/卸载前主动关闭，避免浏览器强杀并在控制台报错
    if (wsRetry) { window.clearTimeout(wsRetry); wsRetry = undefined; }
    if (ws) {
      ws.onopen = null; ws.onclose = null; ws.onerror = null; ws.onmessage = null;
      try { ws.close(); } catch (_e) { /* 忽略 */ }
      ws = null;
    }
    wsOk.value = false;
  }
  function resumeWS() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    ws = null;
    if (wsRetry) { window.clearTimeout(wsRetry); wsRetry = undefined; }
    connectWS();
  }
  function onWSPageHide() { closeWSForFreeze(); }
  function onWSPageShow(e: PageTransitionEvent) { if (e.persisted) resumeWS(); }
  function onWSVisChange() { if (document.visibilityState === "visible") resumeWS(); }

  async function batchLoc() {
    if (!batch.loc) { flash("选分类"); return; }
    const loc = locations.value.find(l => l.id === batch.loc);
    for (const r of selectedRows.value) {
      await $fetch(`/api/v1/entities/${r.id}`, { method: "PATCH", body: { parentId: batch.loc } });
      r.raw.parent = { id: batch.loc, name: loc?.name };
      r.loc = loc?.name || "";
    }
    flash(`批量改分类完成（${selectedCount.value} 条）`);
  }

  // ---------- 预设 ----------
  function savePreset() {
    const name = presetName.value.trim();
    if (!name) { flash("填预设名"); return; }
    presets.value = [...presets.value.filter(p => p.name !== name), { name, view: { ...view(), count: "" } }];
    localStorage.setItem("hb.ledger.presets", JSON.stringify(presets.value));
    presetName.value = "";
    flash("已保存预设：" + name);
  }
  function loadPreset(name: string) {
    const p = presets.value.find(x => x.name === name);
    if (p) applyView(p.view);
  }
  function onPresetChange(e: Event) {
    const name = (e.target as HTMLSelectElement).value;
    if (name) loadPreset(name);
  }
  function delPreset(name: string) {
    presets.value = presets.value.filter(p => p.name !== name);
    localStorage.setItem("hb.ledger.presets", JSON.stringify(presets.value));
  }
</script>

<template>
  <div class="overflow-x-clip bg-background text-foreground" @touchstart.passive="onPullStart" @touchmove.passive="onPullMove" @touchend="onPullEnd">
    <div v-if="offlineReadonly" class="bg-amber-500/15 px-3 py-1.5 text-center text-xs font-medium text-amber-600">离线只读：显示最近缓存，联网后自动更新</div>
    <div v-if="pulling" class="flex justify-center py-2"><span class="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">{{ refreshing ? "刷新中…" : "松开刷新" }}</span></div>
    <div class="mx-auto min-h-[70vh] max-w-[1700px] p-3 md:p-6" :style="safeBottom">
      <!-- 顶栏 -->
      <header class="mb-6">
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="font-display text-xl font-medium tracking-tight md:text-2xl">{{ countMode ? "盘点" : "物品台账" }}</h1>
          <span :class="badgeCls">{{ filtered.length }} 款</span>
          <span :class="badgeCls">共 {{ Math.round(anim.qty) }} 件</span>
          <button v-if="totals.low || onlyLow" class="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition active:scale-95" :class="onlyLow ? 'bg-amber-500 text-white' : 'bg-amber-500/15 text-amber-600'" @click="onlyLow = !onlyLow">
            <span class="h-1.5 w-1.5 rounded-full animate-pulse" :class="onlyLow ? 'bg-white' : 'bg-amber-500'"></span>待补货 {{ totals.low }}
          </button>
          <button v-if="soldCount" class="inline-flex items-center gap-1 transition active:scale-95 disabled:opacity-50" :class="hideSoldOut ? [badgeCls, 'py-1'] : 'rounded-full border border-primary bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary'" :disabled="dataFilter === 'soldout'" :title="dataFilter === 'soldout' ? '当前正在查看售罄物品' : ''" @click="hideSoldOut = !hideSoldOut"><MdiEyeOffOutline v-if="hideSoldOut" class="h-3.5 w-3.5" /><MdiEyeOutline v-else class="h-3.5 w-3.5" />售罄 {{ soldCount }}</button>
          <div class="ml-auto flex w-full flex-wrap items-center justify-end gap-2 md:w-auto md:flex-nowrap">
            <!-- 桌面完整操作 -->
            <div class="hidden items-center gap-2 md:flex">
              <button v-if="!isMobile" :class="[btnGhost, 'active:scale-95']" @click="openScan"><MdiBarcodeScan class="h-4 w-4" /> 扫码</button>
              <button v-if="canInstall" :class="[btnGhost, 'active:scale-95']" @click="install"><MdiCellphoneArrowDown class="h-4 w-4" /> 安装</button>
              <button :class="[btnGhost, 'active:scale-95']" @click="toggleNotify"><MdiBellRing class="h-4 w-4" /> {{ notifyOn ? "关闭提醒" : "补货提醒" }}</button>
              <button :class="[btnGhost, 'active:scale-95']" @click="qualityOpen = true"><MdiClipboardCheckOutline class="h-4 w-4" /> 数据体检</button>
              <button :class="[btnGhost, 'active:scale-95']" @click="importOpen = true"><MdiFileImportOutline class="h-4 w-4" /> 批量导入</button>
              <button :class="[btnGhost, 'active:scale-95']" @click="exportCSV"><MdiDownload class="h-4 w-4" /> 导出CSV</button>
              <button :class="[btnGhost, 'active:scale-95']" @click="copyList"><MdiContentPaste class="h-4 w-4" /> 复制清单</button>
              <button :class="[btnGhost, 'active:scale-95']" @click="exportImage"><MdiImage class="h-4 w-4" /> 长图</button>
              <button :class="[btnGhost, bigFont ? 'border-primary text-primary' : '', 'active:scale-95']" @click="toggleBigFont"><MdiFormatSize class="h-4 w-4" /> {{ bigFont ? "标准字号" : "大字号" }}</button>
              <Transition name="pop">
                <button v-if="undoLast" class="inline-flex items-center gap-1 rounded-lg border border-amber-400 bg-amber-500/10 px-3 py-1.5 text-sm font-medium text-amber-600 transition-all hover:bg-amber-500/20 active:scale-95" @click="undo"><MdiUndo class="h-4 w-4" /> 撤销</button>
              </Transition>
              <label class="flex items-center gap-1 rounded-lg border px-2 py-1.5 text-xs text-muted-foreground" title="联网搜索 1元/次，请省着用">
                <input v-model="aiSearch" type="checkbox" class="accent-primary" /> 联网
              </label>
              <span class="inline-block h-2 w-2 rounded-full" :class="wsOk ? 'bg-primary' : 'bg-muted-foreground/40'" :title="wsOk ? '实时同步已连接' : '实时同步未连接'"></span>
              <span v-if="offline" class="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-600">离线<template v-if="pendingN"> · {{ pendingN }}</template></span>
              <button v-if="trashedCount && isOwner" :class="[btnGhost, 'active:scale-95 border-destructive/40 text-destructive hover:bg-destructive/10']" @click="purgeAll"><MdiDeleteForever class="h-4 w-4" /> 清空回收站 {{ trashedCount }}</button>
              <button :class="[btnGhost, 'active:scale-95']" @click="load"><MdiRefresh class="h-4 w-4" /> 刷新</button>
            </div>
            <!-- 移动：更多菜单 -->
            <details class="relative md:hidden">
              <summary :class="[btnGhost, 'list-none active:scale-95']">更多 ⋯</summary>
              <div class="absolute right-0 z-40 mt-1 w-44 origin-top-right rounded-lg border bg-popover p-1.5 text-sm shadow-lg animate-pop">
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="toggleNotify"><MdiBellRing class="mr-1.5 inline h-4 w-4" />{{ notifyOn ? "关闭补货提醒" : "开启补货提醒" }}</button>
                <button v-if="canInstall" class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="install"><MdiCellphoneArrowDown class="mr-1.5 inline h-4 w-4" />安装到桌面</button>
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="qualityOpen = true"><MdiClipboardCheckOutline class="mr-1.5 inline h-4 w-4" />数据体检</button>
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="importOpen = true"><MdiFileImportOutline class="mr-1.5 inline h-4 w-4" />批量导入</button>
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="exportCSV"><MdiDownload class="mr-1.5 inline h-4 w-4" />导出CSV</button>
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="copyList"><MdiContentPaste class="mr-1.5 inline h-4 w-4" />复制清单</button>
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="exportImage"><MdiImage class="mr-1.5 inline h-4 w-4" />导出长图</button>
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="toggleBigFont"><MdiFormatSize class="mr-1.5 inline h-4 w-4" />{{ bigFont ? "标准字号" : "大字号" }}</button>
                <button v-if="trashedCount && isOwner" class="block w-full rounded px-2.5 py-2.5 text-left text-destructive transition hover:bg-destructive/10" @click="purgeAll"><MdiDeleteForever class="mr-1.5 inline h-4 w-4" />清空回收站（{{ trashedCount }}）</button>
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="openScan"><MdiBarcodeScan class="mr-1.5 inline h-4 w-4" />扫码</button>
                <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="load"><MdiRefresh class="mr-1.5 inline h-4 w-4" />刷新数据</button>
                <button v-if="undoLast" class="block w-full rounded border border-amber-400 bg-amber-500/10 px-2.5 py-2.5 text-left text-amber-600 transition hover:bg-amber-500/20" @click="undo"><MdiUndo class="mr-1.5 inline h-4 w-4" />撤销上一步</button>
                <label class="flex items-center gap-2 rounded px-2.5 py-2.5" title="联网搜索 1 元/次，请省着用"><input v-model="aiSearch" type="checkbox" class="accent-primary" /> 联网识别</label>
              </div>
            </details>
            <button :class="[btnGhost, 'shrink-0 active:scale-95']" @click="pickAI"><MdiImageSearch class="h-4 w-4" /> AI 新增<span v-if="aiActive" class="ml-1 rounded-full bg-primary/10 px-1.5 text-xs tabular-nums">{{ aiActive }}</span></button>
            <button :class="[btnPrimary, 'shrink-0 active:scale-95']" @click="addItem"><MdiPlus class="h-4 w-4" /> 新增物品</button>
          </div>
        </div>
      </header>

      <!-- AI 队列 -->
      <div v-if="aiTasks.length" class="mb-4 rounded-xl border bg-card p-3 text-sm">
        <div class="flex items-center gap-2">
          <span class="grid h-6 w-6 place-items-center rounded-md bg-muted text-muted-foreground"><MdiImageSearch class="h-3.5 w-3.5" /></span>
          <span class="font-medium">AI 队列</span>
          <span class="text-xs text-muted-foreground tabular-nums">处理中 {{ aiActive }} · 完成 {{ aiDone }} · 失败 {{ aiFailed }}</span>
          <button class="ml-auto rounded-lg border bg-background px-2.5 py-1 text-xs transition hover:bg-muted active:scale-95" @click="clearAIDone">清除已结束</button>
        </div>
        <div class="mt-2 max-h-44 space-y-1 overflow-auto">
          <div v-for="t in aiTasks" :key="t.id" class="flex items-center gap-2 rounded-lg bg-muted/40 px-2 py-1 text-xs">
            <span class="h-2 w-2 shrink-0 rounded-full" :class="{ 'bg-amber-500 animate-pulse': t.status === '识别中', 'bg-muted-foreground/40': t.status === '等待中', 'bg-primary': t.status === '待确认' || t.status === '完成', 'bg-destructive': t.status === '失败', 'bg-muted-foreground/60': t.status === '已取消' }"></span>
            <span class="truncate">{{ t.label }}</span>
            <span class="ml-auto shrink-0 text-muted-foreground">{{ t.status }}<template v-if="t.msg"> · {{ t.msg }}</template></span>
            <button v-if="t.status === '待确认'" class="shrink-0 rounded px-1.5 py-0.5 text-primary transition hover:bg-primary/10" @click="reopenAIConfirm(t)">确认</button>
            <button v-else-if="t.status === '等待中'" class="shrink-0 rounded px-1.5 py-0.5 text-destructive transition hover:bg-destructive/10" @click="aiCancelTask(t)">取消</button>
          </div>
        </div>
      </div>

      <!-- AI 识别确认卡片 -->
      <div v-if="aiConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="aiConfirmNext">
        <div class="w-full max-w-md rounded-2xl bg-card p-4 shadow-xl">
          <div class="mb-3 flex items-center gap-2">
            <span class="grid h-6 w-6 place-items-center rounded-md bg-muted text-muted-foreground"><MdiImageSearch class="h-3.5 w-3.5" /></span>
            <span class="font-medium">AI 识别结果确认</span>
            <span class="text-xs text-muted-foreground tabular-nums">待确认 {{ aiPending }}<template v-if="aiActive"> · 识别中 {{ aiActive }}</template></span>
          </div>
          <div class="flex gap-3">
            <img :src="aiConfirm.url" class="h-28 w-28 shrink-0 rounded-xl border object-cover" alt="识别图片" />
            <div class="grid flex-1 grid-cols-2 gap-2 text-sm">
              <label class="col-span-2 flex flex-col gap-1 text-xs text-muted-foreground">名称
                <input v-model="aiConfirm.name" :class="inputCls" />
              </label>
              <label class="flex flex-col gap-1 text-xs text-muted-foreground">品牌
                <select v-model="aiConfirm.brand" :class="inputCls">
                  <option value="">未识别</option><option v-for="b in AI_BRANDS" :key="b" :value="b">{{ b }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-1 text-xs text-muted-foreground">尺寸
                <select v-model="aiConfirm.size" :class="inputCls">
                  <option value="">未识别</option><option v-for="s in AI_SIZES" :key="s" :value="s">{{ s }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-1 text-xs text-muted-foreground">规格
                <select v-model="aiConfirm.spec" :class="inputCls">
                  <option value="">未识别</option><option v-for="s in AI_SPECS" :key="s" :value="s">{{ s }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-1 text-xs text-muted-foreground">材质
                <select v-model="aiConfirm.material" :class="inputCls">
                  <option value="">未识别</option><option v-for="m in AI_MATERIALS" :key="m" :value="m">{{ m }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-1 text-xs text-muted-foreground">颜色
                <input v-model="aiConfirm.color" :class="inputCls" />
              </label>
              <label class="flex flex-col gap-1 text-xs text-muted-foreground">标签
                <select v-model="aiConfirm.tag" :class="inputCls">
                  <option value="">未识别</option><option v-for="g in AI_FIELDS" :key="g" :value="g">{{ g }}</option>
                </select>
              </label>
            </div>
          </div>
          <div class="mt-4 flex flex-wrap justify-end gap-2">
            <button :class="[btnGhost, 'active:scale-95']" @click="aiConfirmNext">跳过 ›</button>
            <button class="inline-flex items-center gap-1 rounded-lg border border-destructive/40 px-3 py-1.5 text-sm font-medium text-destructive transition hover:bg-destructive/10 active:scale-95" @click="aiReject"><MdiClose class="h-4 w-4" /> 拒绝</button>
            <button v-if="aiPending > 1" :class="[btnGhost, 'active:scale-95']" @click="aiCreateAll">全部入库</button>
            <button :class="[btnPrimary, 'active:scale-95']" @click="aiCreateOne"><MdiPlus class="h-4 w-4" /> 确认入库</button>
          </div>
        </div>
      </div>

      <!-- 桌面筛选 -->
      <div v-if="!isMobile" class="mb-4 rounded-xl border bg-card p-3">
        <div class="flex flex-wrap items-end gap-3">
          <label class="flex flex-col gap-1 text-xs text-muted-foreground">品牌
            <select v-model="filter.brand" :class="inputCls">
              <option value="">全部</option><option v-for="v in brands" :key="v" :value="v">{{ v }}</option>
            </select>
          </label>
          <label class="flex flex-col gap-1 text-xs text-muted-foreground">尺寸
            <select v-model="filter.size" :class="inputCls">
              <option value="">全部</option><option v-for="v in sizes" :key="v" :value="v">{{ v }}</option>
            </select>
          </label>
          <label class="flex flex-col gap-1 text-xs text-muted-foreground">系列
            <select v-model="filter.series" :class="inputCls">
              <option value="">全部</option><option v-for="v in seriesOptions" :key="v" :value="v">{{ v }}</option>
            </select>
          </label>
          <label class="relative flex flex-col gap-1 text-xs text-muted-foreground">关键字
            <MdiMagnify class="pointer-events-none absolute bottom-2 left-2 h-4 w-4 text-muted-foreground" />
            <input v-model="filter.q" placeholder="名称/品牌/编号/库位…" :class="[inputCls, 'pl-7']" @keyup.enter="pushSearch(filter.q)" />
          </label>
          <div v-if="searchHistory.length" class="flex flex-wrap items-center gap-1">
            <span class="text-xs text-muted-foreground">常用</span>
            <button v-for="h in searchHistory.slice(0, 6)" :key="h" class="rounded-full border px-2 py-0.5 text-xs transition hover:bg-muted" @click="filter.q = h">{{ h }}</button>
          </div>
          <label class="flex flex-col gap-1 text-xs text-muted-foreground">数据完整性
            <select v-model="dataFilter" :class="inputCls">
              <option value="">全部</option>
              <option value="low">待补货</option>
              <option value="trashed">待删除（已标记）</option>
              <option value="soldout">售罄（数量0）</option>
              <option value="noSafety">未设安全库存</option>
              <option value="noImg">无图</option>
              <option value="noPrice">无价格</option>
              <option value="noBrand">无品牌</option>
              <option value="noSize">无尺寸</option>
              <option value="noSpec">无规格</option>
            </select>
          </label>
          <label :class="[chip, 'active:scale-95']"><input v-model="onlyLow" type="checkbox" class="accent-primary" /> 只看待补货</label>
          <label :class="[chip, 'active:scale-95']"><input v-model="countMode" type="checkbox" class="accent-primary" /> 盘点</label>
          <label :class="[chip, 'active:scale-95']"><input v-model="showSummary" type="checkbox" class="accent-primary" /> 汇总</label>
          <button :class="[btnGhost, 'active:scale-95']" @click="moreFilters = !moreFilters"><MdiFilterVariant class="h-4 w-4" /> 更多<span class="transition-transform" :class="moreFilters ? 'rotate-180' : ''">▾</span></button>
          <div class="ml-auto flex items-center gap-2">
            <button :class="[btnGhost, 'active:scale-95']" :title="viewMode === 'card' ? '切换到列表' : '切换到卡片'" @click="viewMode = viewMode === 'card' ? 'list' : 'card'"><MdiFormatListBulleted v-if="viewMode === 'card'" class="h-4 w-4" /><MdiViewGridOutline v-else class="h-4 w-4" /></button>
            <button :class="[btnGhost, 'active:scale-95']" @click="Object.assign(filter, { brand: '', size: '', spec: '', color: '', material: '', q: '' }); dataFilter = ''">重置</button>
            <details class="relative">
              <summary :class="[btnGhost, 'list-none active:scale-95']">列 ▾</summary>
              <div class="absolute right-0 z-40 mt-1 w-44 origin-top-right rounded-lg border bg-popover p-2 text-sm shadow-lg animate-pop">
                <label v-for="(val, key) in cols" :key="key" class="flex items-center gap-2 rounded px-1 py-1 hover:bg-muted">
                  <input v-model="cols[key]" type="checkbox" class="accent-primary" />
                  {{ {size:'尺寸',spec:'规格',color:'颜色',material:'材质',purchase:'进价',sell:'售价',safety:'安全库存',updated:'更新时间',shelf:'库位'}[key] || key }}
                  <template v-if="extraFields.some(f => f.name === key)">
                    <button type="button" class="ml-auto px-1 text-muted-foreground transition hover:text-foreground" title="上移" @click.stop.prevent="moveField(key, -1)">↑</button>
                    <button type="button" class="px-1 text-muted-foreground transition hover:text-foreground" title="下移" @click.stop.prevent="moveField(key, 1)">↓</button>
                  </template>
                </label>
              </div>
            </details>
          </div>
        </div>
        <Transition name="fold">
          <div v-if="moreFilters" class="mt-3 flex flex-wrap items-end gap-3 border-t pt-3">
            <template v-for="o in extraFilterOptions" :key="o.name">
              <label class="flex flex-col gap-1 text-xs text-muted-foreground">{{ o.name }}
                <select v-model="extraFilters[o.name]" :class="inputCls">
                  <option value="">全部</option><option v-for="v in o.options" :key="v" :value="v">{{ v }}</option>
                </select>
              </label>
            </template>
            <label class="flex flex-col gap-1 text-xs text-muted-foreground">规格
              <select v-model="filter.spec" :class="inputCls">
                <option value="">全部</option><option v-for="v in specs" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="flex flex-col gap-1 text-xs text-muted-foreground">颜色
              <select v-model="filter.color" :class="inputCls">
                <option value="">全部</option><option v-for="v in colors" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="flex flex-col gap-1 text-xs text-muted-foreground">材质
              <select v-model="filter.material" :class="inputCls">
                <option value="">全部</option><option v-for="v in materials" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="flex flex-col gap-1 text-xs text-muted-foreground">显示密度
              <select v-model="density" :class="inputCls">
                <option value="comfortable">舒适</option>
                <option value="compact">紧凑</option>
              </select>
            </label>
            <span class="ml-2 self-center text-xs text-muted-foreground">预设</span>
            <select :class="inputCls" @change="onPresetChange">
              <option value="">选择预设</option><option v-for="p in presets" :key="p.name" :value="p.name">{{ p.name }}</option>
            </select>
            <input v-model="presetName" placeholder="预设名" :class="[inputCls, 'w-28']" />
            <button :class="[btnGhost, 'active:scale-95']" @click="savePreset">保存当前视图</button>
            <button v-for="p in presets" :key="'d' + p.name" class="rounded-lg border px-2 py-1 text-xs text-destructive transition hover:bg-destructive/10" @click="delPreset(p.name)">删 {{ p.name }}</button>
          </div>
        </Transition>
      </div>

      <!-- 手机顶栏 -->
      <div v-else class="sticky top-[var(--header-height-mobile)] z-10 -mx-3 mb-3 flex items-center gap-2 border-b border-border/60 bg-background/90 px-3 py-2 backdrop-blur-md">
        <button class="grid h-10 w-10 shrink-0 place-items-center rounded-full border bg-background transition active:scale-95" title="搜索" @click="focusAppSearch"><MdiMagnify class="h-5 w-5" /></button>
        <button
          class="relative inline-flex h-10 shrink-0 items-center gap-1 rounded-full border px-3.5 text-sm font-medium transition active:scale-95"
          :class="activeFilterCount ? 'border-primary bg-primary/10 text-primary' : 'bg-background'"
          @click="filterOpen = true"
        ><MdiFilterVariant class="h-5 w-5" /> 筛选
          <span v-if="activeFilterCount" class="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1 text-xs font-semibold tabular-nums text-primary-foreground">{{ activeFilterCount }}</span>
        </button>
        <button
          class="grid h-10 w-10 shrink-0 place-items-center rounded-full border bg-background transition active:scale-95"
          :title="viewMode === 'card' ? '切换到列表' : '切换到卡片'"
          @click="viewMode = viewMode === 'card' ? 'list' : 'card'"
        ><MdiFormatListBulleted v-if="viewMode === 'card'" class="h-5 w-5" /><MdiViewGridOutline v-else class="h-5 w-5" /></button>
        <button
          class="inline-flex h-10 shrink-0 items-center rounded-full border px-3.5 text-sm font-medium transition-all active:scale-95"
          :class="onlyLow ? 'border-amber-400 bg-amber-500/15 text-amber-600' : 'bg-background'"
          @click="onlyLow = !onlyLow"
        >待补货</button>
        <button v-if="filter.q" class="inline-flex h-10 min-w-0 shrink items-center gap-1 rounded-full border border-primary bg-primary/10 px-3 text-sm text-primary transition active:scale-95" @click="filter.q = ''"><MdiClose class="h-4 w-4 shrink-0" /><span class="truncate">{{ filter.q }}</span></button>
        <span class="ml-auto shrink-0 text-xs text-muted-foreground tabular-nums">{{ filtered.length }} 款</span>
      </div>

      <!-- 汇总 -->
      <Transition name="fold">
        <div v-if="showSummary" class="mb-4 rounded-xl border bg-card p-4 text-sm">
          <div class="mb-3 flex items-center gap-2">
            <span class="font-semibold">汇总</span>
            <select v-model="summaryDim" :class="[inputCls, 'px-2 py-1']">
              <option v-for="d in groupDims" :key="d.key" :value="d.key">按{{ d.label }}</option>
            </select>
          </div>
          <div v-for="g in summaryGroups" :key="g.name" class="mb-1.5 flex items-center gap-3">
            <span class="w-24 shrink-0 truncate text-muted-foreground">{{ g.name }}</span>
            <span class="h-2.5 rounded-full bg-primary/80 transition-[width] duration-500 ease-out" :style="{ width: g.pct + '%', minWidth: '3px' }"></span>
            <span class="text-muted-foreground tabular-nums">{{ g.qty }} 件 · ¥{{ fmt(g.cost) }}</span>
          </div>
        </div>
      </Transition>

      <!-- 批量操作栏 -->
      <Transition name="fold">
        <div v-if="selectedCount" class="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-primary/30 bg-primary/5 p-3 text-sm">
          <span class="font-medium">已选 {{ selectedCount }} 款</span>
          <span class="flex items-center gap-1">数量<input v-model.number="batch.qty" inputmode="decimal" type="number" :class="[inputCls, 'w-16']" /><button :class="[btnGhost, 'active:scale-95']" @click="batchQty">应用</button></span>
          <span class="flex items-center gap-1">进价<input v-model.number="batch.purchase" inputmode="decimal" type="number" :class="[inputCls, 'w-16']" /><button :class="[btnGhost, 'active:scale-95']" @click="batchPrice('purchase')">应用</button></span>
          <span class="flex items-center gap-1">售价<input v-model.number="batch.sell" inputmode="decimal" type="number" :class="[inputCls, 'w-16']" /><button :class="[btnGhost, 'active:scale-95']" @click="batchPrice('sell')">应用</button></span>
          <span class="flex items-center gap-1">安全库存<input v-model.number="batch.safety" inputmode="decimal" type="number" :class="[inputCls, 'w-16']" /><button :class="[btnGhost, 'active:scale-95']" @click="batchSafety">应用</button></span>
          <span class="flex items-center gap-1">加{{ orgCfg.tagGroup.name }}<select v-model="batch.tag" :class="inputCls"><option value="">选择</option><option v-for="t in tags" :key="t.id" :value="t.id">{{ t.name }}</option></select><button :class="[btnGhost, 'active:scale-95']" @click="batchTag">应用</button></span>
          <span class="flex items-center gap-1">分类<select v-model="batch.loc" :class="inputCls"><option value="">选择</option><option v-for="l in locations" :key="l.id" :value="l.id">{{ l.name }}</option></select><button :class="[btnGhost, 'active:scale-95']" @click="batchLoc">应用</button></span>
          <button :class="[btnGhost, 'active:scale-95']" @click="batchTrash"><MdiTrashCanOutline class="h-4 w-4" /> 标记删除</button>
          <button v-if="isOwner" :class="[btnGhost, 'active:scale-95 border-destructive/40 text-destructive hover:bg-destructive/10']" @click="purgeSelected"><MdiDeleteForever class="h-4 w-4" /> 彻底删除</button>
          <button class="ml-auto rounded-lg px-3 py-1.5 text-muted-foreground transition hover:bg-muted" @click="clearSel"><MdiClose class="h-4 w-4" /></button>
        </div>
      </Transition>

      <!-- 批量差异预览 -->
      <Transition name="sheet">
        <div v-if="batchPreview" class="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center sm:p-4" @click.self="cancelBatch">
          <div class="sheet-panel max-h-[80vh] w-full overflow-auto rounded-t-2xl border bg-card p-4 shadow-xl sm:max-w-lg sm:rounded-2xl">
            <div class="mb-2 flex items-center gap-2">
              <span class="font-semibold">{{ batchPreview.label }}</span>
              <span class="text-xs text-muted-foreground">共 {{ batchPreview.total }} 条</span>
              <button class="ml-auto rounded-lg p-1 text-muted-foreground hover:bg-muted" @click="cancelBatch"><MdiClose class="h-5 w-5" /></button>
            </div>
            <p class="mb-2 text-xs text-muted-foreground">确认后执行；执行后可用顶部「撤销」回退。</p>
            <div class="divide-y rounded-lg border text-sm">
              <div v-for="(d, i) in batchPreview.rows" :key="i" class="flex items-center gap-2 p-2">
                <span class="min-w-0 flex-1 truncate">{{ d.name }}</span>
                <span class="text-muted-foreground line-through">{{ d.from }}</span>
                <span class="text-muted-foreground">→</span>
                <span class="font-medium text-primary">{{ d.to }}</span>
              </div>
              <div v-if="batchPreview.total > batchPreview.rows.length" class="p-2 text-center text-xs text-muted-foreground">…等 {{ batchPreview.total }} 条</div>
            </div>
            <div class="mt-4 flex items-center justify-end gap-2">
              <button :class="[btnGhost, 'active:scale-95']" :disabled="batchRunning" @click="cancelBatch">取消</button>
              <button :class="[btnPrimary, 'active:scale-95']" :disabled="batchRunning" @click="confirmBatch">{{ batchRunning ? "执行中…" : "确认执行" }}</button>
            </div>
          </div>
        </div>
      </Transition>
      <Transition name="fold">
        <div v-if="countMode" class="mb-4 flex items-center gap-3 rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-sm">
          <MdiAlertOutline class="h-5 w-5 shrink-0 text-amber-600" />
          <span class="min-w-0 flex-1">盘点模式：只保留数量修改，即改即存；其余编辑已锁定。</span>
        </div>
      </Transition>

      <!-- 加载骨架 -->
      <div v-if="loading" class="grid grid-cols-2 gap-3 md:grid-cols-3">
        <div v-for="i in 6" :key="i" :class="skeletonCls"></div>
      </div>
      <div v-else-if="err" :class="errorCls">{{ err }}</div>

      <!-- 卡片视图（移动单列 / 桌面网格） -->
      <TransitionGroup v-else-if="viewMode === 'card'" name="card" tag="div" :class="isMobile ? 'space-y-2.5' : 'grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-4'">
        <div v-for="r in shownList" :key="r.id" class="relative overflow-hidden rounded-2xl border bg-card">
          <div v-show="(swipe[r.id] || 0) < 0" class="absolute inset-y-0 right-0 flex items-center gap-2 bg-primary/5 px-2.5">
            <button class="grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-foreground transition active:scale-90" @click="step(r,-1); closeSwipe(r)"><MdiMinus class="h-5 w-5" /></button>
            <button class="grid h-12 w-12 place-items-center rounded-xl bg-primary text-primary-foreground transition active:scale-90" @click="step(r,1); closeSwipe(r)"><MdiPlus class="h-5 w-5" /></button>
            <button class="grid h-12 w-12 place-items-center rounded-xl bg-muted-foreground text-white transition active:scale-90" @click="pickPhoto(r); closeSwipe(r)"><MdiCamera class="h-5 w-5" /></button>
          </div>
          <div
            :class="[rowClass(r), isSaved(r) ? 'row-flash' : '', sel[r.id] ? 'ring-2 ring-inset ring-primary' : '', isTrashed(r) || isSoldOut(r) ? 'opacity-60' : '', !isTrashed(r) && !isSoldOut(r) && isLow(r) ? 'border-l-2 border-l-amber-400' : '']"
            :style="cardStyle(r)"
            class="relative bg-card p-3"
            style="touch-action: pan-y"
            @touchstart="onTS($event, r)"
            @touchmove="onTM($event, r)"
            @touchend="onTE(r)"
          >
            <div class="flex gap-3">
              <button v-if="r.thumb" class="shrink-0 self-start overflow-hidden rounded-xl border" @click="preview = imgUrl(r)"><img :src="imgUrl(r)" decoding="async" width="56" height="56" class="h-14 w-14 object-cover opacity-0 transition active:scale-95" @load="revealImg" /></button>
              <button v-else class="grid h-14 w-14 shrink-0 place-items-center self-start rounded-xl border border-dashed bg-muted/60 text-muted-foreground transition active:scale-95" @click="pickPhoto(r)"><MdiCamera class="h-5 w-5" /></button>
              <div class="min-w-0 flex-1">
                <div class="flex items-start gap-1.5">
                  <NuxtLink :to="`/item/${r.id}`" class="line-clamp-2 flex-1 text-base font-semibold leading-snug text-foreground"><span v-html="hl(r.name)"></span></NuxtLink>
                  <span v-if="isTrashed(r)" class="shrink-0 rounded-full bg-destructive/15 px-2.5 py-0.5 text-xs font-medium text-destructive">待删除{{ trashAgeDays(r) !== null ? " · " + trashAgeDays(r) + "天" : "" }}</span>
                  <span v-if="isLow(r)" class="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-600"><span class="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse"></span>待补货</span>
                  <span v-else-if="isSoldOut(r)" class="shrink-0 rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">售罄</span>
                </div>
                <div class="mt-1.5 text-xs text-muted-foreground">
                  <button class="rounded-md bg-muted px-2 py-1 text-muted-foreground transition active:scale-95 disabled:opacity-60" :disabled="countMode" @click="promptSerial(r)">库位 {{ r.serial || "＋" }}</button>
                </div>
                <div v-if="attrLine(r)" class="mt-1 truncate text-xs text-muted-foreground">{{ attrLine(r) }}</div>
                <div v-if="!countMode && ((r.purchase ?? 0) > 0 || (r.sell ?? 0) > 0)" class="mt-2 flex items-center gap-3 text-sm tabular-nums text-muted-foreground">
                  <span v-if="(r.purchase ?? 0) > 0">进 <b class="font-medium text-foreground">¥{{ fmt(r.purchase) }}</b></span>
                  <span v-if="(r.sell ?? 0) > 0">售 <b class="font-medium text-foreground">¥{{ fmt(r.sell) }}</b></span>
                </div>
              </div>
            </div>
            <div class="mt-3 flex items-center gap-2">
              <div class="flex shrink-0 items-center overflow-hidden rounded-xl border">
                <button class="grid h-11 w-12 place-items-center text-2xl transition active:bg-muted disabled:opacity-40" :disabled="saving[r.id]" @click="step(r,-1)">−</button>
                <input v-model.number="r.qty" inputmode="numeric" type="number" min="0" class="h-11 w-16 border-x bg-background text-center text-xl font-semibold tabular-nums outline-none focus:ring-2 focus:ring-inset focus:ring-ring/40" @focus="snapshot(r)" @change="onQtyChange(r)" />
                <button class="grid h-11 w-12 place-items-center text-2xl transition active:bg-muted disabled:opacity-40" :disabled="saving[r.id]" @click="step(r,1)">＋</button>
              </div>
              <template v-if="!countMode">
                <button v-if="!safetyEditing[r.id]" class="ml-auto px-2 py-2 text-xs text-muted-foreground transition active:scale-95" @click="editSafety(r)">安全 {{ r.safety ?? "＋" }}</button>
                <input v-else v-model.number="r.safety" inputmode="numeric" type="number" min="0" class="ml-auto h-11 w-16 rounded-xl border bg-background text-center text-base tabular-nums outline-none focus:ring-2 focus:ring-ring/40" :ref="focusEl" @blur="doneSafetyEdit(r)" @keyup.enter="($event.target as HTMLInputElement).blur()" />
              </template>
            </div>
            <div v-if="!countMode" class="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <button class="inline-flex h-9 items-center gap-1 rounded-lg border px-2.5 text-xs font-medium transition active:scale-95" @click="showGallery(r)"><MdiImageMultiple class="h-4 w-4" />图片</button>
              <button class="inline-flex h-9 items-center gap-1 rounded-lg border px-2.5 text-xs font-medium transition active:scale-95 disabled:opacity-40" :class="isTrashed(r) ? '' : 'border-destructive/40 text-destructive'" :disabled="saving[r.id]" @click="toggleTrash(r)">
                <MdiRestore v-if="isTrashed(r)" class="h-4 w-4" /><MdiTrashCanOutline v-else class="h-4 w-4" />{{ isTrashed(r) ? "恢复" : "标记删除" }}
              </button>
              <button v-if="isTrashed(r) && isOwner" class="inline-flex h-9 items-center gap-1 rounded-lg border border-destructive/40 px-2.5 text-xs font-medium text-destructive transition active:scale-95 disabled:opacity-40" :disabled="saving[r.id]" @click="purgeOne(r)"><MdiDeleteForever class="h-4 w-4" />彻底删除</button>
              <details class="relative">
                <summary class="inline-flex h-9 list-none items-center gap-1 rounded-lg border px-2.5 text-xs font-medium transition active:scale-95"><MdiDotsHorizontal class="h-4 w-4" /></summary>
                <div class="absolute bottom-full right-0 z-40 mb-1 w-44 origin-bottom-right rounded-lg border bg-popover p-1.5 text-sm shadow-lg animate-pop">
                  <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="showQR(r)"><MdiQrcode class="mr-1.5 inline h-4 w-4" />二维码</button>
                  <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted disabled:opacity-40" :disabled="saving[r.id]" @click="duplicateRow(r)"><MdiContentCopy class="mr-1.5 inline h-4 w-4" />复制</button>
                  <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="showHistory(r)"><MdiHistory class="mr-1.5 inline h-4 w-4" />历史</button>
                  <button class="block w-full rounded px-2.5 py-2.5 text-left transition hover:bg-muted" @click="openFields(r)"><MdiFormTextbox class="mr-1.5 inline h-4 w-4" />字段</button>
                </div>
              </details>
              <span class="ml-auto text-muted-foreground/70">更新 {{ fmtDate(r.updated) }}</span>
            </div>
          </div>
        </div>
        <div v-if="!sorted.length" key="__empty" class="rounded-2xl border border-dashed bg-card/50 p-10 text-center text-muted-foreground">
          <MdiPackageVariantClosed class="mx-auto mb-2 h-8 w-8 opacity-40" />
          没有匹配的物品
        </div>
      </TransitionGroup>

      <!-- 手机紧凑列表（列表模式） -->
      <div v-else-if="isMobile" class="divide-y overflow-hidden rounded-xl border bg-card">
        <div
          v-for="r in shownList" :key="r.id"
          class="flex items-center gap-2.5 px-3 py-2"
          :class="[isTrashed(r) || isSoldOut(r) ? 'opacity-60' : '', !isTrashed(r) && !isSoldOut(r) && isLow(r) ? 'border-l-2 border-l-amber-400' : '']"
        >
          <img v-if="r.thumb" :src="imgUrl(r)" decoding="async" width="40" height="40" class="h-10 w-10 shrink-0 cursor-zoom-in rounded-lg border object-cover opacity-0 transition" @load="revealImg" @click="preview = imgUrl(r)" />
          <span v-else class="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-dashed bg-muted/60 text-[10px] text-muted-foreground">无图</span>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <NuxtLink :to="`/item/${r.id}`" class="truncate text-sm font-medium text-foreground"><span v-html="hl(r.name)"></span></NuxtLink>
              <span v-if="isTrashed(r)" class="shrink-0 rounded-full bg-destructive/15 px-2 py-0.5 text-[10px] font-medium text-destructive">待删除</span>
              <span v-else-if="isLow(r)" class="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-600">待补货</span>
              <span v-else-if="isSoldOut(r)" class="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">售罄</span>
            </div>
            <div class="truncate text-xs text-muted-foreground">{{ [r.brand, r.size, r.spec].filter(Boolean).join(" · ") }}<template v-if="r.serial"> · 库位 {{ r.serial }}</template></div>
          </div>
          <div class="flex shrink-0 items-center overflow-hidden rounded-lg border">
            <button class="grid h-9 w-9 place-items-center text-lg transition active:bg-muted disabled:opacity-40" :disabled="saving[r.id]" @click="step(r,-1)">−</button>
            <input v-model.number="r.qty" inputmode="numeric" type="number" min="0" class="h-9 w-12 border-x bg-background text-center text-sm font-semibold tabular-nums outline-none focus:ring-2 focus:ring-inset focus:ring-ring/40" @focus="snapshot(r)" @change="onQtyChange(r)" />
            <button class="grid h-9 w-9 place-items-center text-lg transition active:bg-muted disabled:opacity-40" :disabled="saving[r.id]" @click="step(r,1)">＋</button>
          </div>
        </div>
        <div v-if="!sorted.length" :class="emptyCls">没有匹配的物品</div>
      </div>

      <!-- 桌面表格 -->
      <div v-else class="table-scroll overflow-x-auto rounded-xl border bg-card" :class="density === 'compact' ? 'text-[13px]' : ''">
        <table class="w-full border-collapse">
          <thead class="bg-card">
            <tr class="text-left text-xs text-muted-foreground">
              <th v-if="!countMode" class="border-b px-2 py-2"><input type="checkbox" class="accent-primary" :checked="sorted.length>0 && sorted.every(r=>sel[r.id])" @change="toggleAll" /></th>
              <th class="border-b px-2 py-2">图</th>
              <th class="cursor-pointer select-none border-b px-3 py-2 transition hover:text-foreground" @click="setSort('name')">名称<span v-if="requiredSet.has('名称')" class="text-destructive"> *</span>{{ arrow("name") }}</th>
              <th v-if="cols.updated" class="cursor-pointer select-none border-b px-3 py-2 whitespace-nowrap transition hover:text-foreground" @click="setSort('updated')">更新{{ arrow("updated") }}</th>
              <th v-if="cols.shelf" class="border-b px-3 py-2">库位</th>
              <th class="cursor-pointer select-none border-b px-3 py-2 transition hover:text-foreground" @click="setSort('brand')">品牌<span v-if="requiredSet.has('品牌')" class="text-destructive"> *</span>{{ arrow("brand") }}</th>
              <th v-if="cols.size" class="cursor-pointer select-none border-b px-3 py-2 transition hover:text-foreground" @click="setSort('size')">尺寸<span v-if="requiredSet.has('尺寸')" class="text-destructive"> *</span>{{ arrow("size") }}</th>
              <th v-if="cols.spec" class="border-b px-3 py-2">规格<span v-if="requiredSet.has('规格')" class="text-destructive"> *</span></th>
              <th v-if="cols.color" class="border-b px-3 py-2">颜色<span v-if="requiredSet.has('颜色')" class="text-destructive"> *</span></th>
              <th v-if="cols.material" class="border-b px-3 py-2">材质<span v-if="requiredSet.has('材质')" class="text-destructive"> *</span></th>
              <template v-for="f in extraFields" :key="'h' + f.name">
                <th v-if="cols[f.name]" class="border-b px-3 py-2 whitespace-nowrap">{{ f.name }}<span v-if="requiredSet.has(f.name)" class="text-destructive"> *</span></th>
              </template>
              <th v-if="cols.purchase" class="cursor-pointer select-none border-b px-3 py-2 text-right transition hover:text-foreground" @click="setSort('purchase')">进价<span v-if="requiredSet.has('进价')" class="text-destructive"> *</span>{{ arrow("purchase") }}</th>
              <th v-if="cols.sell" class="cursor-pointer select-none border-b px-3 py-2 text-right transition hover:text-foreground" @click="setSort('sell')">售价<span v-if="requiredSet.has('售价')" class="text-destructive"> *</span>{{ arrow("sell") }}</th>
              <th class="cursor-pointer select-none border-b px-3 py-2 text-center transition hover:text-foreground" @click="setSort('qty')">数量{{ arrow("qty") }}</th>
              <th v-if="cols.safety" class="cursor-pointer select-none border-b px-3 py-2 text-center transition hover:text-foreground" @click="setSort('safety')">安全库存<span v-if="requiredSet.has('安全库存')" class="text-destructive"> *</span>{{ arrow("safety") }}</th>
              <th v-if="!countMode" class="border-b px-2 py-2 text-center">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in paged" :key="r.id" class="border-b transition-colors last:border-0" :class="[rowClass(r), isSaved(r) ? 'row-flash' : '']">
              <td v-if="!countMode" :class="[cellPad, 'px-2!']"><input v-model="sel[r.id]" type="checkbox" class="accent-primary" /></td>
              <td :class="[cellPad, 'px-2!']">
                <div class="relative inline-block">
                  <img v-if="r.thumb" :src="imgUrl(r)" decoding="async" width="36" height="36" class="h-9 w-9 cursor-zoom-in rounded-md border object-cover opacity-0 transition hover:scale-110" @load="revealImg" @click="preview = imgUrl(r)" />
                  <button v-else-if="!countMode" class="grid h-9 w-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-muted" @click="pickPhoto(r)"><MdiCamera class="h-4 w-4" /></button>
                  <button v-if="r.thumb && !countMode" class="absolute -bottom-1 -right-1 grid h-4 w-4 place-items-center rounded-full bg-primary text-primary-foreground" title="换图" @click="pickPhoto(r)"><MdiCamera class="h-2.5 w-2.5" /></button>
                </div>
              </td>
              <td :class="cellPad">
                <div class="flex min-w-0 flex-wrap items-center gap-1.5">
                  <input v-model="r.name" class="w-40 min-w-0 flex-1 rounded-md border bg-background px-2 py-1 outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @change="setName(r)" />
                  <NuxtLink :to="`/item/${r.id}`" class="text-primary hover:underline" title="打开详情"><MdiOpenInNew class="h-3.5 w-3.5" /></NuxtLink>
                  <span v-if="isTrashed(r)" class="shrink-0 rounded-full bg-destructive/15 px-2.5 py-0.5 text-xs font-medium text-destructive">待删除{{ trashAgeDays(r) !== null ? " · " + trashAgeDays(r) + "天" : "" }}</span>
                  <span v-if="isLow(r)" class="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-600"><span class="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse"></span>待补货</span>
                  <span v-else-if="isSoldOut(r)" class="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">售罄</span>
                </div>
              </td>
              <td v-if="cols.updated" :class="[cellPad, 'whitespace-nowrap text-muted-foreground']" :title="r.updated">{{ fmtDate(r.updated) }}</td>
              <td v-if="cols.shelf" :class="cellPad">
                <input v-model="r.serial" class="w-20 rounded-md border bg-background px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-ring/40" placeholder="-" :disabled="countMode" @change="setSerial(r)" />
              </td>
              <td :class="cellPad"><select :value="r.brand" class="w-20 rounded-md border bg-background px-1 py-1 text-sm outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @change="onInline($event, r, '品牌', 'brand')"><option value="">-</option><option v-for="v in optsWith(brandOptions, r.brand)" :key="v" :value="v">{{ v }}</option><option value="__new__">＋ 新增…</option></select></td>
              <td v-if="cols.size" :class="cellPad"><select :value="r.size" class="w-20 rounded-md border bg-background px-1 py-1 text-sm outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @change="onInline($event, r, '尺寸', 'size')"><option value="">-</option><option v-for="v in optsWith(sizeOptions, r.size)" :key="v" :value="v">{{ v }}</option><option value="__new__">＋ 新增…</option></select></td>
              <td v-if="cols.spec" :class="cellPad"><select :value="r.spec" class="w-24 rounded-md border bg-background px-1 py-1 text-sm outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @change="onInline($event, r, '规格', 'spec')"><option value="">-</option><option v-for="v in optsWith(specOptions, r.spec)" :key="v" :value="v">{{ v }}</option><option value="__new__">＋ 新增…</option></select></td>
              <td v-if="cols.color" :class="cellPad"><select :value="r.color" class="w-20 rounded-md border bg-background px-1 py-1 text-sm outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @change="onInline($event, r, '颜色', 'color')"><option value="">-</option><option v-for="v in optsWith(colorOptions, r.color)" :key="v" :value="v">{{ v }}</option><option value="__new__">＋ 新增…</option></select></td>
              <td v-if="cols.material" :class="cellPad"><select :value="r.material" class="w-20 rounded-md border bg-background px-1 py-1 text-sm outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @change="onInline($event, r, '材质', 'material')"><option value="">-</option><option v-for="v in optsWith(materialOptions, r.material)" :key="v" :value="v">{{ v }}</option><option value="__new__">＋ 新增…</option></select></td>
              <template v-for="f in extraFields" :key="'c' + f.name">
                <td v-if="cols[f.name]" :class="cellPad">
                  <input v-if="f.type === 'text'" v-model="r.extra[f.name]" class="w-24 rounded-md border bg-background px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @change="setExtra(r, f.name, f.type)" />
                  <input v-else-if="f.type === 'number'" v-model.number="r.extra[f.name]" type="number" inputmode="decimal" class="w-20 rounded-md border bg-background px-2 py-1 text-right tabular-nums outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @change="setExtra(r, f.name, f.type)" />
                  <input v-else-if="f.type === 'boolean'" v-model="r.extra[f.name]" type="checkbox" class="accent-primary" :disabled="countMode" @change="setExtra(r, f.name, f.type)" />
                </td>
              </template>
              <td v-if="cols.purchase" :class="cellPad">
                <input v-model.number="r.purchase" inputmode="decimal" type="number" step="0.01" class="w-20 rounded-md border bg-background px-2 py-1 text-right tabular-nums outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @focus="snapshot(r)" @change="setPrice(r,'purchase')" />
              </td>
              <td v-if="cols.sell" :class="cellPad">
                <input v-model.number="r.sell" inputmode="decimal" type="number" step="0.01" class="w-20 rounded-md border bg-background px-2 py-1 text-right tabular-nums outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @focus="snapshot(r)" @change="setPrice(r,'sell')" />
              </td>
              <td :class="cellPad">
                <div class="flex items-center justify-center gap-1">
                  <button class="h-7 w-7 rounded-md border transition hover:bg-muted active:scale-90 disabled:opacity-40" :disabled="saving[r.id]" @click="step(r, -1)">−</button>
                  <input v-model.number="r.qty" inputmode="numeric" type="number" min="0" class="w-16 rounded-md border bg-background px-2 py-1 text-center tabular-nums outline-none focus:ring-2 focus:ring-ring/40" @focus="snapshot(r)" @change="onQtyChange(r)" />
                  <button class="h-7 w-7 rounded-md border transition hover:bg-muted active:scale-90 disabled:opacity-40" :disabled="saving[r.id]" @click="step(r, 1)">+</button>
                </div>
              </td>
              <td v-if="cols.safety" :class="cellPad">
                <input v-model.number="r.safety" inputmode="numeric" type="number" min="0" class="w-16 rounded-md border bg-background px-2 py-1 text-center tabular-nums outline-none focus:ring-2 focus:ring-ring/40" :disabled="countMode" @focus="snapshot(r)" @change="setSafety(r)" />
              </td>
              <td v-if="!countMode" :class="[cellPad, 'text-center']">
                <div class="flex items-center justify-center gap-1">
                  <button class="grid h-7 w-7 place-items-center rounded-md border transition hover:bg-muted active:scale-90" title="二维码标签" @click="showQR(r)"><MdiQrcode class="h-4 w-4" /></button>
                  <button class="grid h-7 w-7 place-items-center rounded-md border transition hover:bg-muted active:scale-90 disabled:opacity-40" :disabled="saving[r.id]" title="复制一件" @click="duplicateRow(r)"><MdiContentCopy class="h-4 w-4" /></button>
                  <button class="grid h-7 w-7 place-items-center rounded-md border transition hover:bg-muted active:scale-90" title="变更历史" @click="showHistory(r)"><MdiHistory class="h-4 w-4" /></button>
                  <button class="grid h-7 w-7 place-items-center rounded-md border transition hover:bg-muted active:scale-90" title="图片（多图）" @click="showGallery(r)"><MdiImageMultiple class="h-4 w-4" /></button>
                  <button class="grid h-7 w-7 place-items-center rounded-md border transition hover:bg-muted active:scale-90" title="自定义字段" @click="openFields(r)"><MdiFormTextbox class="h-4 w-4" /></button>
                  <button class="grid h-7 w-7 place-items-center rounded-md border transition hover:bg-muted active:scale-90 disabled:opacity-40" :disabled="saving[r.id]" :class="isTrashed(r) ? '' : 'border-destructive/40 text-destructive'" :title="isTrashed(r) ? '恢复（取消删除标记）' : '标记删除（不真正删除）'" @click="toggleTrash(r)">
                    <MdiRestore v-if="isTrashed(r)" class="h-4 w-4" /><MdiTrashCanOutline v-else class="h-4 w-4" />
                  </button>
                  <button v-if="isTrashed(r) && isOwner" class="grid h-7 w-7 place-items-center rounded-md border border-destructive/40 text-destructive transition hover:bg-destructive/10 active:scale-90 disabled:opacity-40" :disabled="saving[r.id]" title="彻底删除（不可恢复）" @click="purgeOne(r)"><MdiDeleteForever class="h-4 w-4" /></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!sorted.length" :class="emptyCls">
          <MdiPackageVariantClosed class="mx-auto mb-2 h-8 w-8 opacity-40" />
          没有匹配的物品
        </div>
      </div>

      <!-- 无限滚动哨兵 / 到底提示（卡片视图全端 + 移动列表；桌面表格用分页） -->
      <div v-if="(viewMode === 'card' || isMobile) && sorted.length" class="py-3 text-center text-xs tabular-nums text-muted-foreground">
        <span v-if="shownList.length < sorted.length" ref="loadMoreEl">下拉加载更多（{{ shownList.length }}/{{ sorted.length }}）</span>
        <span v-else>共 {{ sorted.length }} 条 · 到底了</span>
      </div>

      <!-- 分页（桌面表格；其余视图用无限滚动） -->
      <div v-if="sorted.length && viewMode === 'list'" class="mt-4 hidden flex-wrap items-center justify-center gap-2 rounded-xl border bg-card p-2 text-sm md:flex">
        <select v-model.number="pageSize" class="hidden rounded-lg border bg-background px-2 py-1.5 text-sm md:block" @change="gotoPage(1)">
          <option :value="20">20/页</option>
          <option :value="50">50/页</option>
          <option :value="100">100/页</option>
          <option v-if="!isMobile" :value="100000">全部</option>
        </select>
        <button class="hidden h-11 rounded-lg border px-3 font-medium transition active:scale-95 disabled:opacity-40 md:block" :disabled="page <= 1" @click="gotoPage(1)">首页</button>
        <button class="h-11 rounded-lg border px-3 font-medium transition active:scale-95 disabled:opacity-40" :disabled="page <= 1" @click="gotoPage(page - 1)">上一页</button>
        <span class="px-2 tabular-nums text-muted-foreground">{{ page }} / {{ totalPages }} · 共 {{ sorted.length }} 条</span>
        <button class="h-11 rounded-lg border px-3 font-medium transition active:scale-95 disabled:opacity-40" :disabled="page >= totalPages" @click="gotoPage(page + 1)">下一页</button>
        <button class="hidden h-11 rounded-lg border px-3 font-medium transition active:scale-95 disabled:opacity-40 md:block" :disabled="page >= totalPages" @click="gotoPage(totalPages)">末页</button>
      </div>
    </div>

    <!-- 手机筛选抽屉 -->
    <Transition name="sheet">
      <div v-if="filterOpen" class="fixed inset-0 z-50 flex items-end bg-black/40 backdrop-blur-[1px]" @click.self="filterOpen = false">
        <div class="sheet-panel flex max-h-[88vh] w-full flex-col overflow-hidden rounded-t-2xl border-t bg-card shadow-2xl">
          <div class="relative flex items-center justify-between border-b px-4 pb-3 pt-4">
            <span class="absolute left-1/2 top-2 h-1 w-10 -translate-x-1/2 rounded-full bg-muted-foreground/30"></span>
            <span class="mt-2 font-semibold">筛选<span v-if="activeFilterCount" class="ml-1.5 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">{{ activeFilterCount }}</span></span>
            <button :class="[btnPrimary, 'mt-2 active:scale-95']" @click="filterOpen = false">完成</button>
          </div>
          <div class="flex-1 space-y-4 overflow-auto p-4 text-base" :style="safeBottom">
            <label class="block text-xs text-muted-foreground">品牌
              <select v-model="filter.brand" :class="inputClsLg">
                <option value="">全部</option><option v-for="v in brands" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="block text-xs text-muted-foreground">尺寸
              <select v-model="filter.size" :class="inputClsLg">
                <option value="">全部</option><option v-for="v in sizes" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="block text-xs text-muted-foreground">规格
              <select v-model="filter.spec" :class="inputClsLg">
                <option value="">全部</option><option v-for="v in specs" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="block text-xs text-muted-foreground">颜色
              <select v-model="filter.color" :class="inputClsLg">
                <option value="">全部</option><option v-for="v in colors" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="block text-xs text-muted-foreground">材质
              <select v-model="filter.material" :class="inputClsLg">
                <option value="">全部</option><option v-for="v in materials" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="block text-xs text-muted-foreground">系列
              <select v-model="filter.series" :class="inputClsLg">
                <option value="">全部</option><option v-for="v in seriesOptions" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="block text-xs text-muted-foreground">数据完整性
              <select v-model="dataFilter" :class="inputClsLg">
                <option value="">全部</option>
                <option value="low">待补货</option>
                <option value="trashed">待删除（已标记）</option>
                <option value="soldout">售罄（数量0）</option>
                <option value="noSafety">未设安全库存</option>
                <option value="noImg">无图</option>
                <option value="noPrice">无价格</option>
                <option value="noBrand">无品牌</option>
                <option value="noSize">无尺寸</option>
                <option value="noSpec">无规格</option>
              </select>
            </label>
            <label v-for="o in extraFilterOptions" :key="o.name" class="block text-xs text-muted-foreground">{{ o.name }}
              <select v-model="extraFilters[o.name]" :class="inputClsLg">
                <option value="">全部</option><option v-for="v in o.options" :key="v" :value="v">{{ v }}</option>
              </select>
            </label>
            <label class="block text-xs text-muted-foreground">排序
              <span class="flex items-center gap-2">
                <select v-model="sort.key" :class="[inputClsLg, 'flex-1']">
                  <option value="name">名称</option>
                  <option value="qty">数量</option>
                  <option value="purchase">进价</option>
                  <option value="sell">售价</option>
                  <option value="safety">安全库存</option>
                  <option value="updated">更新时间</option>
                  <option value="brand">品牌</option>
                  <option value="size">尺寸</option>
                  <option value="low">低库存优先</option>
                </select>
                <button type="button" :class="[btnGhost, 'mt-1 shrink-0 justify-center px-3 py-2.5 text-base active:scale-95']" :title="sort.dir === 1 ? '升序' : '降序'" @click="setSort(sort.key)">{{ sort.dir === 1 ? "↑" : "↓" }}</button>
              </span>
            </label>
            <label class="flex items-center gap-2 text-base"><input v-model="countMode" type="checkbox" class="h-5 w-5 accent-primary" /> 盘点模式</label>
            <label class="flex items-center gap-2 text-base"><input v-model="showSummary" type="checkbox" class="h-5 w-5 accent-primary" /> 显示汇总</label>
            <div class="flex flex-wrap items-center gap-2 border-t pt-3">
              <span class="text-xs text-muted-foreground">预设</span>
              <select class="rounded-lg border bg-background px-2 py-1.5" @change="onPresetChange">
                <option value="">选择</option><option v-for="p in presets" :key="p.name" :value="p.name">{{ p.name }}</option>
              </select>
              <input v-model="presetName" placeholder="预设名" class="w-24 rounded-lg border bg-background px-2 py-1.5" />
              <button :class="[btnGhost, 'active:scale-95']" @click="savePreset">保存视图</button>
            </div>
            <button :class="[btnGhost, 'w-full justify-center py-2.5 text-base active:scale-95']" @click="Object.assign(filter, { brand: '', size: '', spec: '', color: '', material: '', q: '' }); dataFilter = ''">重置筛选</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 扫码 -->
    <Transition name="fade">
      <div v-if="scanOpen" class="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/80 p-4 text-white" @click.self="closeScan">
        <p class="mb-2">{{ scanMsg }}</p>
        <video ref="videoEl" class="max-h-[60vh] w-full max-w-md rounded-xl" autoplay playsinline muted></video>
        <div class="mt-3 flex items-center gap-2">
          <input placeholder="或输入编号/名称" class="rounded-lg px-3 py-2 text-black" @keyup.enter="onLocateInput" />
          <button class="rounded-lg border border-white px-3 py-2 transition hover:bg-white/10" @click="closeScan">关闭</button>
        </div>
      </div>
    </Transition>

    <!-- 新增物品 -->
    <Transition name="fade">
      <div v-if="addOpen" :class="drawerWrap" @click.self="addOpen = false">
        <div :class="drawerPanel" :style="safeBottom">
          <div class="mb-3 flex items-center justify-between">
            <span class="font-display text-lg font-medium">新增物品</span>
            <button class="rounded-lg p-1 hover:bg-muted" @click="addOpen = false"><MdiClose class="h-5 w-5" /></button>
          </div>
          <div class="space-y-3 text-sm">
            <label class="block">名称 / 系列
              <input v-model="addForm.name" :class="[inputCls, 'mt-1 w-full']" placeholder="如：A4小象紫色横线（会自动拆分）或 小象" @input="onAddNameInput" />
            </label>
            <label class="flex items-center gap-2"><input v-model="addForm.autoSplit" type="checkbox" class="accent-primary" /> 从名称自动拆分 尺寸 / 颜色 / 规格</label>
            <label class="flex items-center gap-2"><input v-model="addForm.keep" type="checkbox" class="accent-primary" /> 保存后继续新增（保留分类/规格）</label>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <label class="block text-xs text-muted-foreground">尺寸
                <select v-if="!addNew.size" :class="[inputCls, 'mt-1 w-full']" @change="onSel($event, 'size')">
                  <option value="">选择</option>
                  <option v-for="v in sizeOptions" :key="v" :value="v" :selected="v === addForm.size">{{ v }}</option>
                  <option value="__new__">＋ 新增…</option>
                </select>
                <span v-else class="mt-1 flex gap-1"><input v-model="addForm.size" :class="[inputCls, 'w-full']" placeholder="新尺寸" /><button class="rounded border px-2" @click="addNew.size = false">↩</button></span>
              </label>
              <label class="block text-xs text-muted-foreground">颜色
                <select v-if="!addNew.color" :class="[inputCls, 'mt-1 w-full']" @change="onSel($event, 'color')">
                  <option value="">选择</option>
                  <option v-for="v in colorOptions" :key="v" :value="v" :selected="v === addForm.color">{{ v }}</option>
                  <option value="__new__">＋ 新增…</option>
                </select>
                <span v-else class="mt-1 flex gap-1"><input v-model="addForm.color" :class="[inputCls, 'w-full']" placeholder="新颜色" /><button class="rounded border px-2" @click="addNew.color = false">↩</button></span>
              </label>
              <label class="block text-xs text-muted-foreground">规格
                <select v-if="!addNew.spec" :class="[inputCls, 'mt-1 w-full']" @change="onSel($event, 'spec')">
                  <option value="">选择</option>
                  <option v-for="v in specOptions" :key="v" :value="v" :selected="v === addForm.spec">{{ v }}</option>
                  <option value="__new__">＋ 新增…</option>
                </select>
                <span v-else class="mt-1 flex gap-1"><input v-model="addForm.spec" :class="[inputCls, 'w-full']" placeholder="新规格" /><button class="rounded border px-2" @click="addNew.spec = false">↩</button></span>
              </label>
              <label class="block text-xs text-muted-foreground">材质
                <select v-if="!addNew.material" :class="[inputCls, 'mt-1 w-full']" @change="onSel($event, 'material')">
                  <option value="">选择</option>
                  <option v-for="v in materialOptions" :key="v" :value="v" :selected="v === addForm.material">{{ v }}</option>
                  <option value="__new__">＋ 新增…</option>
                </select>
                <span v-else class="mt-1 flex gap-1"><input v-model="addForm.material" :class="[inputCls, 'w-full']" placeholder="新材质" /><button class="rounded border px-2" @click="addNew.material = false">↩</button></span>
              </label>
            </div>
            <div class="grid grid-cols-3 gap-2">
              <label class="block text-xs text-muted-foreground">数量<input v-model.number="addForm.qty" inputmode="numeric" type="number" :class="[inputCls, 'mt-1 w-full']" /></label>
              <label class="block text-xs text-muted-foreground">进价<input v-model.number="addForm.purchase" inputmode="decimal" type="number" :class="[inputCls, 'mt-1 w-full']" /></label>
              <label class="block text-xs text-muted-foreground">售价<input v-model.number="addForm.sell" inputmode="decimal" type="number" :class="[inputCls, 'mt-1 w-full']" /></label>
            </div>
            <label class="block text-xs text-muted-foreground">分类
              <select v-model="addForm.loc" :class="[inputCls, 'mt-1 w-full']">
                <option value="">选择分类</option>
                <option v-for="l in locations" :key="l.id" :value="l.id">{{ l.name }}</option>
              </select>
            </label>
          </div>
          <div class="mt-4 flex gap-2">
            <button :class="[btnGhost, 'flex-1 justify-center py-2.5 text-base sm:flex-none']" @click="addOpen = false">取消</button>
            <button :class="[btnPrimary, 'flex-1 justify-center py-2.5 text-base sm:flex-none']" :disabled="addSaving" @click="doAdd">{{ addSaving ? "保存中…" : "保存" }}</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 图片预览 -->
    <Transition name="fade">
      <div v-if="preview" class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" @click="preview = null">
        <img :src="preview" class="animate-pop max-h-[90vh] max-w-[90vw] rounded-xl shadow-2xl" />
      </div>
    </Transition>

    <!-- 数据体检 -->
    <Transition name="fade">
      <div v-if="qualityOpen" :class="drawerWrap" @click.self="qualityOpen = false">
        <div :class="drawerPanel" :style="safeBottom">
          <div class="mb-3 flex items-center justify-between">
            <span class="font-display text-lg font-medium">数据体检 · {{ qualityStats.total }} 款</span>
            <button class="rounded-lg p-1 hover:bg-muted" @click="qualityOpen = false"><MdiClose class="h-5 w-5" /></button>
          </div>
          <p class="mb-2 text-xs text-muted-foreground">点任意项以筛选出对应的物品，便于批量修正。</p>
          <div class="grid grid-cols-2 gap-2 text-sm">
            <button class="flex items-center justify-between rounded-lg border px-3 py-2.5 hover:bg-muted" @click="applyQuality('noPurchase')"><span>缺进价</span><b class="tabular-nums" :class="qualityStats.noPurchase ? 'text-amber-600' : 'text-muted-foreground'">{{ qualityStats.noPurchase }}</b></button>
            <button class="flex items-center justify-between rounded-lg border px-3 py-2.5 hover:bg-muted" @click="applyQuality('noImg')"><span>缺图</span><b class="tabular-nums" :class="qualityStats.noImg ? 'text-amber-600' : 'text-muted-foreground'">{{ qualityStats.noImg }}</b></button>
            <button class="flex items-center justify-between rounded-lg border px-3 py-2.5 hover:bg-muted" @click="applyQuality('noSafety')"><span>缺安全库存</span><b class="tabular-nums" :class="qualityStats.noSafety ? 'text-amber-600' : 'text-muted-foreground'">{{ qualityStats.noSafety }}</b></button>
            <button class="flex items-center justify-between rounded-lg border px-3 py-2.5 hover:bg-muted" @click="applyQuality('noBrand')"><span>缺品牌</span><b class="tabular-nums" :class="qualityStats.noBrand ? 'text-amber-600' : 'text-muted-foreground'">{{ qualityStats.noBrand }}</b></button>
            <button class="flex items-center justify-between rounded-lg border px-3 py-2.5 hover:bg-muted" @click="applyQuality('noSize')"><span>缺尺寸</span><b class="tabular-nums" :class="qualityStats.noSize ? 'text-amber-600' : 'text-muted-foreground'">{{ qualityStats.noSize }}</b></button>
            <button class="flex items-center justify-between rounded-lg border px-3 py-2.5 hover:bg-muted" @click="applyQuality('noSpec')"><span>缺规格</span><b class="tabular-nums" :class="qualityStats.noSpec ? 'text-amber-600' : 'text-muted-foreground'">{{ qualityStats.noSpec }}</b></button>
            <button v-if="(uiOptions.required || []).length" class="col-span-2 flex items-center justify-between rounded-lg border px-3 py-2.5 hover:bg-muted" @click="applyQuality('required')"><span>缺必填字段</span><b class="tabular-nums" :class="qualityStats.noRequired ? 'text-destructive' : 'text-muted-foreground'">{{ qualityStats.noRequired }}</b></button>
            <button class="col-span-2 flex items-center justify-between rounded-lg border px-3 py-2.5 hover:bg-muted" @click="applyQuality('dup')"><span>重复名称（涉及款数）</span><b class="tabular-nums" :class="qualityStats.dupCount ? 'text-destructive' : 'text-muted-foreground'">{{ qualityStats.dupCount }}</b></button>
          </div>
          <p v-if="qualityStats.dupNames.length" class="mt-2 truncate text-xs text-muted-foreground">重复示例：{{ qualityStats.dupNames.slice(0, 6).join("、") }}</p>
          <div v-if="dupGroups.length" class="mt-4 border-t pt-3">
            <div class="mb-1.5 text-sm font-medium text-destructive">重复名称（{{ dupGroups.length }} 组）· 可一键“保留最新、其余标记删除”</div>
            <div class="max-h-52 space-y-1 overflow-auto">
              <div v-for="g in dupGroups" :key="g.name" class="flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm">
                <span class="min-w-0 flex-1 truncate">{{ g.name }}</span>
                <span class="shrink-0 text-xs text-muted-foreground">{{ g.rows.length }} 条</span>
                <button class="shrink-0 rounded-md border border-destructive/40 px-2 py-1 text-xs text-destructive transition hover:bg-destructive/10 active:scale-95" @click="mergeDupSoft(g)">合并</button>
              </div>
            </div>
          </div>
          <button :class="[btnGhost, 'mt-3 w-full justify-center py-2.5 text-base']" @click="printFiltered">打印当前筛选二维码</button>
        </div>
      </div>
    </Transition>

    <!-- 批量导入 -->
    <Transition name="fade">
      <div v-if="importOpen" :class="drawerWrap" @click.self="importOpen = false">
        <div :class="drawerPanel" :style="safeBottom">
          <div class="mb-3 flex items-center justify-between">
            <span class="font-display text-lg font-medium">批量导入</span>
            <button class="rounded-lg p-1 hover:bg-muted" @click="importOpen = false"><MdiClose class="h-5 w-5" /></button>
          </div>
          <p class="mb-2 text-xs text-muted-foreground">每行一条，列用 Tab 或逗号分隔；顺序：名称,品牌,尺寸,规格,颜色,材质,数量,进价,售价,安全库存,分类。可含表头。分类填已有品牌名（否则用下方默认分类）。</p>
          <textarea v-model="importText" rows="7" class="w-full rounded-lg border bg-background p-2 font-mono text-xs outline-none focus:ring-2 focus:ring-ring/40" placeholder="名称	品牌	尺寸	规格	颜色	材质	数量	进价	售价	安全库存	分类"></textarea>
          <div class="mt-2 flex items-center gap-2">
            <label class="text-xs text-muted-foreground">默认分类
              <select v-model="addForm.loc" :class="[inputCls, 'ml-1']"><option v-for="l in locations" :key="l.id" :value="l.id">{{ l.name }}</option></select>
            </label>
            <span class="ml-auto text-xs text-muted-foreground">解析到 {{ importRows.length }} 行</span>
          </div>
          <div v-if="importMsg" class="mt-2 text-sm text-primary">{{ importMsg }}</div>
          <div class="mt-3 flex gap-2">
            <button :class="[btnGhost, 'flex-1 justify-center py-2.5 text-base']" @click="importOpen = false">关闭</button>
            <button :class="[btnPrimary, 'flex-1 justify-center py-2.5 text-base']" :disabled="importBusy || !importRows.length" @click="doImport">{{ importBusy ? "导入中…" : `导入 ${importRows.length} 行` }}</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 二维码 -->
    <Transition name="fade">
      <div v-if="qrOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="qrOpen = false">
        <div class="w-full max-w-xs rounded-2xl bg-card p-4 text-center shadow-2xl" :style="safeBottom">
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm font-semibold">二维码标签</span>
            <button class="rounded-lg p-1 hover:bg-muted" @click="qrOpen = false"><MdiClose class="h-5 w-5" /></button>
          </div>
          <img :src="qrSrcFor(qrData)" class="mx-auto h-56 w-56 rounded-lg border bg-white object-contain" alt="二维码" />
          <div class="mt-2 text-sm font-medium">{{ qrTitle }}</div>
          <div class="text-xs text-muted-foreground">{{ qrData }}</div>
          <div class="mt-3 flex gap-2">
            <button :class="[btnGhost, 'flex-1 justify-center']" @click="qrOpen = false">关闭</button>
            <button :class="[btnPrimary, 'flex-1 justify-center']" @click="printQR(qrTitle, qrData)">打印</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 变更历史 -->
    <Transition name="fade">
      <div v-if="historyOpen" :class="drawerWrap" @click.self="historyOpen = false">
        <div :class="drawerPanel" :style="safeBottom">
          <div class="mb-3 flex items-center justify-between">
            <span class="font-display text-lg font-medium">变更历史 · {{ historyTitle }}</span>
            <button class="rounded-lg p-1 hover:bg-muted" @click="historyOpen = false"><MdiClose class="h-5 w-5" /></button>
          </div>
          <div v-if="historyBusy" class="py-6 text-center text-sm text-muted-foreground">加载中…</div>
          <div v-else-if="!historyLogs.length" class="py-6 text-center text-sm text-muted-foreground">暂无记录</div>
          <div v-else class="space-y-1.5">
            <div v-for="(e, i) in historyLogs" :key="i" class="flex items-center gap-2 rounded-lg border px-2.5 py-2 text-sm">
              <span class="text-xs text-muted-foreground tabular-nums">{{ fmtTs(e.ts) }}</span>
              <span class="flex-1">{{ auditText(e) }}</span>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 多图 -->
    <Transition name="fade">
      <div v-if="galleryOpen" :class="drawerWrap" @click.self="closeGallery">
        <div :class="drawerPanel" :style="safeBottom">
          <div class="mb-3 flex items-center justify-between">
            <span class="font-display text-lg font-medium">图片 · {{ galleryTitle }}</span>
            <button class="rounded-lg p-1 hover:bg-muted" @click="closeGallery"><MdiClose class="h-5 w-5" /></button>
          </div>
          <div v-if="galleryBusy" class="py-6 text-center text-sm text-muted-foreground">处理中…</div>
          <div class="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
            上传到槽位
            <select v-model="gallerySlot" :class="inputCls">
              <option v-for="s in mediaSlots" :key="s.key" :value="s.key">{{ s.name }}</option>
            </select>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div v-for="a in galleryImgs" :key="a.id" class="relative overflow-hidden rounded-lg border">
              <img :src="attUrl(a.id)" class="h-28 w-full object-cover" alt="" />
              <button v-if="!a.primary" class="absolute left-1 top-1 rounded-md bg-black/60 px-1.5 py-0.5 text-xs text-white" @click="setPrimaryImg(a)">设封面</button>
              <span v-else class="absolute left-1 top-1 rounded-md bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">封面</span>
              <button class="absolute right-1 top-1 grid h-6 w-6 place-items-center rounded-full bg-black/60 text-white" @click="delGalleryImg(a)"><MdiDeleteForever class="h-3.5 w-3.5" /></button>
              <select :value="slotKeyOf(a)" class="absolute inset-x-1 bottom-1 rounded-md border-0 bg-black/70 px-1 py-0.5 text-xs text-white outline-none" @change="setSlot(a, ($event.target as HTMLSelectElement).value)">
                <option value="">未分类</option>
                <option v-for="s in mediaSlots" :key="s.key" :value="s.key">{{ s.name }}</option>
              </select>
            </div>
            <button class="grid h-28 place-items-center rounded-lg border border-dashed text-3xl text-muted-foreground transition hover:bg-muted" @click="pickGallery">＋</button>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">按槽位归档（{{ mediaSlots.map(s => s.name).join(" / ") }}）；第一张默认封面，可更换。</p>
        </div>
      </div>
    </Transition>

    <!-- 自定义字段 -->
    <Transition name="fade">
      <div v-if="fieldsOpen" :class="drawerWrap" @click.self="fieldsOpen = false">
        <div :class="drawerPanel" :style="safeBottom">
          <div class="mb-3 flex items-center justify-between">
            <span class="font-display text-lg font-medium">自定义字段 · {{ fieldsItem?.name }}</span>
            <button class="rounded-lg p-1 hover:bg-muted" @click="fieldsOpen = false"><MdiClose class="h-5 w-5" /></button>
          </div>
          <div class="space-y-2">
            <label v-for="(f, i) in fieldsDraft" :key="i" class="flex items-center gap-2 text-sm">
              <span class="w-20 shrink-0 truncate text-muted-foreground">{{ f.name }}<span v-if="requiredSet.has(f.name)" class="text-destructive">*</span></span>
              <input v-if="f.type === 'text'" v-model="f.value" :class="[inputCls, 'h-10 min-w-0 flex-1 text-base']" />
              <input v-else-if="f.type === 'number'" v-model.number="f.value" type="number" inputmode="decimal" :class="[inputCls, 'h-10 w-28 text-base']" />
              <input v-else-if="f.type === 'boolean'" v-model="f.value" type="checkbox" class="h-5 w-5 accent-primary" />
              <span v-else class="text-xs text-muted-foreground">{{ f.value }}</span>
            </label>
            <div v-if="!fieldsDraft.length" class="py-4 text-center text-sm text-muted-foreground">该物品暂无自定义字段（可在 集合→字段 添加）</div>
          </div>
          <div class="mt-3 flex gap-2">
            <button :class="[btnGhost, 'flex-1 justify-center py-2.5 text-base']" @click="fieldsOpen = false">取消</button>
            <button :class="[btnPrimary, 'flex-1 justify-center py-2.5 text-base']" :disabled="fieldsBusy" @click="saveFields">{{ fieldsBusy ? "保存中…" : "保存" }}</button>
          </div>
        </div>
      </div>
    </Transition>

    <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onFile" />
    <input ref="galleryInput" type="file" accept="image/*" multiple class="hidden" @change="onGalleryFiles" />
    <input ref="aiInput" type="file" accept="image/*" multiple class="hidden" @change="onAIFile" />
  </div>
</template>

<style scoped>
  @keyframes floatIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
  @keyframes popIn { 0% { opacity: .4; transform: scale(.94); } 60% { transform: scale(1.03); } 100% { opacity: 1; transform: scale(1); } }
  @keyframes rowFlash { 0% { background-color: hsl(var(--primary) / .22); } 100% { background-color: transparent; } }

  .animate-pop { animation: popIn .22s ease-out; }
  .row-flash { animation: rowFlash .9s ease-out; }

  .table-scroll { scrollbar-width: thin; scrollbar-color: hsl(var(--muted-foreground) / .5) transparent; }
  .table-scroll::-webkit-scrollbar { height: 10px; }
  .table-scroll::-webkit-scrollbar-track { background: transparent; }
  .table-scroll::-webkit-scrollbar-thumb { background: hsl(var(--muted-foreground) / .45); border-radius: 9999px; border: 2px solid transparent; background-clip: padding-box; }
  .table-scroll::-webkit-scrollbar-thumb:hover { background: hsl(var(--muted-foreground) / .7); background-clip: padding-box; }

  .card-enter-active { transition: opacity .28s ease, transform .28s ease; }
  .card-enter-from { opacity: 0; transform: translateY(6px); }
  .card-leave-active { transition: opacity .18s ease, transform .18s ease; position: absolute; width: 100%; }
  .card-leave-to { opacity: 0; }
  .card-move { transition: transform .28s ease; }

  .fold-enter-active, .fold-leave-active { transition: opacity .2s ease, transform .2s ease; }
  .fold-enter-from, .fold-leave-to { opacity: 0; transform: translateY(-6px); }

  .fade-enter-active, .fade-leave-active { transition: opacity .2s ease; }
  .fade-enter-from, .fade-leave-to { opacity: 0; }

  .sheet-enter-active, .sheet-leave-active { transition: opacity .22s ease; }
  .sheet-enter-from, .sheet-leave-to { opacity: 0; }
  .sheet-enter-active .sheet-panel { animation: sheetUp .28s cubic-bezier(.22,.61,.36,1); }
  .sheet-leave-active .sheet-panel { animation: sheetDown .2s ease forwards; }

  @keyframes sheetUp { from { transform: translateY(100%); } to { transform: none; } }
  @keyframes sheetDown { from { transform: none; } to { transform: translateY(100%); } }

  button, a, summary, label { -webkit-tap-highlight-color: transparent; }

  /* iPhone/Safari：输入控件小于 16px 会自动放大页面，统一放大 */
  @media (max-width: 768px) {
    input, select, textarea { font-size: 16px !important; }
    html { -webkit-text-size-adjust: 100%; }
  }

  @media (prefers-reduced-motion: reduce) {
    * { animation-duration: .001ms !important; transition-duration: .001ms !important; }
  }
</style>
