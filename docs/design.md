# Groza 库存维护系统设计方案 v2（评审修订版）

- 定位：**库存维护台**（持续维护与更新库存信息），AI 是维护加速器，不是主界面。
- 原则：批量改、可追溯、可回退、多端一致、配置驱动、不越界（不做收银/报表）。
- 版本：v2 —— 已吸收评审意见（A1/A2/A3/A5 修订、B1 顺序调整、迁移保留 Homebox 核心）。

## 0. v1→v2 修订摘要

| # | 问题 | 修订 |
|---|---|---|
| A1 | 纯 EAV 与台账查询矛盾 | 改「JSON 主存 + 高频字段冗余列」混合模型（§4） |
| A2 | 重构内核 → 死 fork | 改 sidecar 分层，Homebox 核心零改动（§3） |
| A3 | 「库位唯一」业务性错误 | 删除硬约束，一格多款；唯一性仅限定位码（§5） |
| A4 | 迁移映射缺媒体/回滚/回收站原因 | 映射表补齐（§10.2） |
| A5 | reset 覆盖用户自定义 | 配置版本快照，reset=切版本（§9.5） |
| A6 | 「按时间点回滚」承诺过重 | 改为「快照恢复 + 审计重放（粒度=每日快照）」 |
| B1 | 迁移与 P0 顺序矛盾 | **迁移先行**，功能随后（§13） |
| B2/B4 | API 缺现有功能端点、价格历史查询 | 契约补齐（§8）、审计索引（§4.5） |
| B5 | 媒体槽位落地方式 | 复用 `attachments.title` 存槽位名，`primary`=封面（§4.5） |
| B6 | 权限未定义 | 角色枚举 + 检查点（§6.8） |
| B7/B8/B9 | 备份适配、SW 版本、故障用例 | §10.5、§8.1、§11 |

## 1. 定位与设计原则

- 库存是活的：进货/出货/盘点/纠错/改价持续改变它，核心不是「录入一次」而是「持续维护」。
- 主界面 = **维护工作台（待办中心）**，不是表单页或聊天页。
- 四条主线：**批量改、可追溯、可回退、多端一致**；模型本身**可自定义**（位置/属性/媒体/组织四维）。
- AI 定位：拍照建档、整箱识别、单据识别、找相似款——服务于维护，不喧宾夺主。
- 边界：不做收银台/找零/日结、不做毛利/动销/ABC 报表；保持单模板 + 动态字段。

## 2. 信息模型（四维可配置，默认模板=现状）

全部由**库存架构配置**（`gx_config.json`）驱动，台账/AI/导入导出/校验从它派生。默认即当前状态。

```json
{
  "version": 3,
  "location": {
    "dim": "品牌",
    "levels": ["品牌"],
    "shelf": { "enabled": true, "name": "库位", "pattern": "^[A-Z]-\\d{1,3}$", "unique": false }
  },
  "attributes": [
    {"key":"brand","name":"品牌","type":"text","required":true,"column":true,"filter":true,"optionsFrom":"locations"},
    {"key":"size","name":"尺寸","type":"select","required":true,"column":true,"filter":true,"options":["A4","A5","A5S","B5"]},
    {"key":"spec","name":"规格","type":"select","column":true,"filter":true,"options":["横线","网格","方格","点阵"]},
    {"key":"color","name":"颜色","type":"select","column":true,"filter":true,"options":["黑","白","蓝","粉"]},
    {"key":"material","name":"材质","type":"text","column":true,"filter":true},
    {"key":"purchase","name":"进价","type":"number","required":true,"column":true,"filter":true,"unit":"元"},
    {"key":"sell","name":"售价","type":"number","column":true,"filter":true,"unit":"元"},
    {"key":"pages","name":"页数","type":"number","column":true},
    {"key":"paper","name":"纸张","type":"text","column":true},
    {"key":"safety","name":"安全库存","type":"number","column":true}
  ],
  "media": {
    "cover": "front",
    "maxPerItem": 8,
    "slots": [
      {"key":"front","name":"正面","required":true},
      {"key":"back","name":"反面"},
      {"key":"detail","name":"细节","multiple":true},
      {"key":"package","name":"包装"}
    ]
  },
  "organization": {
    "tagGroup": { "name": "品类", "options": ["书写本","无日期计划本","有日期计划本","贴纸","笔","套盒","拼图"] },
    "series": { "enabled": true, "deriveFrom": ["name"], "stripParentheses": true },
    "groupDims": ["品牌","尺寸","规格","系列"]
  }
}
```

- **属性**：`key` 是稳定键（不可改，仅显示名可改）；`type` = text/number/boolean/date/select/multiselect；`optionsFrom` = manual | locations | tags。
- **位置**：品牌分类 + 可选的库位（§5 规则）。
- **媒体**：图片槽位（正面/反面/细节/包装），`attachment.title` 存槽位名，`primary` 存封面。
- **组织**：标签体系（品类）、系列派生（名称去括号）、分组/汇总维度。

## 3. 总体架构（A2：Sidecar 分层，可升级）

```
┌─────────────────────────────────────────────┐
│ 自有 API /api/v1/*（业务唯一入口）            │
│  items / documents / config / audit / ai     │
├─────────────────────────────────────────────┤
│ 领域层（外挂表，gx_ 前缀，独立迁移）           │
│  gx_item_meta · gx_attribute_def ·           │
│  gx_document(_line) · gx_config(+history) ·  │
│  gx_audit_log · gx_idempotency · gx_ai_cache │
├─────────────────────────────────────────────┤
│ Homebox 核心（零 schema 改动，可随上游升级）   │
│  groups/users/entities/entity_types/         │
│  attachments/tags/api_keys + 原路由           │
└─────────────────────────────────────────────┘
```

**边界规则**
1. Homebox 核心表**不加列、不改语义**；仅保留品牌/导航/配色等外观 patch。
2. 所有新表 `gx_` 前缀 + 独立迁移版本表 `gx_schema_version`，与上游表名零冲突。
3. **数量唯一事实源 = `entities.quantity`**；单据 post/rollback 在事务内更新它；其它领域元数据走 gx 层，不做双写。
4. 业务读写只走自有 API；Homebox 原路由继续可用（上游 UI 兼容），不承接新功能。
5. **升级流程**：上游 release → 对比 fork patch 集（核心未改 → 冲突极小）→ 升级 → 跑 `gx_schema_version` 校验 + smoke + 表一致性体检 → 通过才对外。
6. 媒体槽位复用 `attachments.title`；封面用 `attachments.primary`（非侵入）。

## 4. 数据存储（A1：JSON 主存 + 冗余列混合模型）

### 4.1 设计原则
- `gx_item_meta.attributes`（JSON）存**全量属性值**（key 为稳定键），详情/编辑/导出/AI 回填直连它。
- 对 `column/filterable/sortable` 的属性生成**类型化冗余列** `attr_<key>`；台账列表筛选/排序走冗余列（可索引、可导出）。
- **单一写路径**：backend service 同事务写 JSON + 冗余列；配置变更在事务内 `ALTER TABLE ADD COLUMN` + 回填。
- 数据量（数千条）下该模型最简单可靠；体检脚本校验 JSON 与冗余列一致。

### 4.2 DDL（SQLite，`PRAGMA journal_mode=WAL; foreign_keys=ON;`）

```sql
-- 迁移版本
CREATE TABLE gx_schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);

-- 属性定义（配置）
CREATE TABLE gx_attribute_def (
  id TEXT PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('text','number','boolean','date','select','multiselect')),
  required INTEGER NOT NULL DEFAULT 0,
  show_column INTEGER NOT NULL DEFAULT 1,
  filterable INTEGER NOT NULL DEFAULT 1,
  sortable INTEGER NOT NULL DEFAULT 0,
  unit TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  default_value TEXT,
  options_source TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE gx_attribute_option (
  id TEXT PRIMARY KEY,
  def_id TEXT NOT NULL REFERENCES gx_attribute_def(id) ON DELETE CASCADE,
  value TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE(def_id, value)
);

-- 物品元数据（侧车，A1 混合模型）
CREATE TABLE gx_item_meta (
  item_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
  shelf TEXT,
  status TEXT NOT NULL DEFAULT 'normal'
    CHECK(status IN ('normal','low','soldout','paused','pending_delete')),
  version INTEGER NOT NULL DEFAULT 1,          -- 乐观锁
  attributes TEXT NOT NULL DEFAULT '{}',       -- 全量 JSON
  -- 冗余列（由配置生成，示例为默认模板）：
  attr_brand TEXT, attr_size TEXT, attr_spec TEXT, attr_color TEXT,
  attr_material TEXT, attr_purchase REAL, attr_sell REAL,
  attr_pages REAL, attr_paper TEXT, attr_safety REAL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_gx_meta_shelf ON gx_item_meta(shelf);
CREATE INDEX ix_gx_meta_status ON gx_item_meta(status);
-- 冗余列索引随配置动态增删（如 ix_meta_attr_purchase）

-- 单据（库存变更唯一入口）
CREATE TABLE gx_document (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('intake','outbound','adjust')),
  code TEXT, party TEXT, note TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK(status IN ('draft','posted','rolled_back')),
  created_by TEXT, created_at TEXT NOT NULL,
  posted_at TEXT, rolled_back_at TEXT,
  idem_key TEXT UNIQUE
);
CREATE TABLE gx_document_line (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES gx_document(id) ON DELETE CASCADE,
  item_id TEXT NOT NULL REFERENCES entities(id),
  qty REAL NOT NULL,                          -- intake 正 / outbound 负 / adjust 正负
  unit_cost REAL, unit_price REAL,
  qty_before REAL NOT NULL, qty_after REAL NOT NULL,
  price_cost_before REAL, price_cost_after REAL,
  price_sell_before REAL, price_sell_after REAL
);
CREATE INDEX ix_docline_doc ON gx_document_line(document_id);
CREATE INDEX ix_doc_kind_ts ON gx_document(kind, created_at);

-- 配置（单行 JSON + 历史快照）
CREATE TABLE gx_config (
  id INTEGER PRIMARY KEY CHECK(id = 1),
  version INTEGER NOT NULL,
  json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE gx_config_history (
  id TEXT PRIMARY KEY,
  version INTEGER NOT NULL,
  json TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL
);

-- 审计 / 幂等 / AI 缓存
CREATE TABLE gx_audit_log (
  id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  actor TEXT,
  action TEXT NOT NULL,                        -- field_patch|intake|outbound|adjust|trash|purge|config|sync_attrs
  item_id TEXT, document_id TEXT,
  changes_json TEXT                            -- {"进价":{"old":12,"new":18}}
);
CREATE INDEX ix_audit_item ON gx_audit_log(item_id, ts);  -- 价格历史等字段级查询
CREATE INDEX ix_audit_ts ON gx_audit_log(ts);

CREATE TABLE gx_idempotency (key TEXT PRIMARY KEY, ts TEXT NOT NULL, response_json TEXT);
CREATE TABLE gx_ai_cache (hash TEXT PRIMARY KEY, ts TEXT NOT NULL, result_json TEXT);
```

### 4.3 台账查询形态
```sql
SELECT e.id, e.name, e.quantity, m.shelf, m.status,
       m.attr_brand, m.attr_size, m.attr_purchase, m.attr_sell
FROM entities e JOIN gx_item_meta m ON m.item_id = e.id
WHERE e.entity_type_id = :itemType
  AND m.attr_brand = :brand
  AND m.attr_purchase BETWEEN :lo AND :hi
ORDER BY m.attr_purchase DESC
LIMIT 20 OFFSET 40;
```
- 列表一次 JOIN；动态列/筛选 = 按配置选择冗余列；无冗余列的属性只进详情/导出。

### 4.4 一致性保障
- 写路径唯一（service 层事务）；体检项新增「JSON ↔ 冗余列一致性」与「quantity ↔ 单据行累计」校验；迁移后必跑。

### 4.5 与 Homebox 表的边界映射
| 概念 | 落点 |
|---|---|
| 物品 | `entities`（quantity/name/type/parent 唯一事实源） + `gx_item_meta`（shelf/status/attributes/version） |
| 位置 | `entities`(is_location) 树；库位 = `gx_item_meta.shelf` |
| 属性定义/选项 | `gx_attribute_def` / `gx_attribute_option` |
| 属性值 | `gx_item_meta.attributes` + 冗余列 |
| 媒体 | `attachments`（`title`=槽位名，`primary`=封面） |
| 组织 | `tags` + `gx_config.json.organization` |

## 5. 库位与定位（A3）

- **一格多款是常态**：库位是**可重复**的物理位置标识，不是唯一键。
- 规则：可选格式校验（`pattern`，默认 `^[A-Z]-\d{1,3}$`）；**无唯一冲突报错**；重复库位仅给「占用提示」软提示（该位已有 N 件）。
- 唯一性只保留给**定位码/资产号**：QR 数据 = item id（天然唯一）；未来可加自定义资产码（加唯一索引）。
- UI：库位列/筛选/分组；「同库位」一键查看该格全部物品。

## 6. 功能设计

### 6.1 维护工作台（待办中心）
把需维护的库存聚成可批处理队列：缺价 / 缺图 / 缺库位 / 缺安全库存 / 缺属性 / 重复 / 久未更新 / 低库存 / 数量异常 / 价格为0 / 待删除。点入→筛选态→批量修正。目标：每天清空待办。

### 6.2 批量维护（关键能力）
对当前筛选/勾选执行，**先出差异预览（原→新）→ 确认 → 可回滚**：
- 数量：设值 / +N / −N / ×系数；
- 价格：设值 / 加价率(×1.8) / 百分比 ±%；
- 库位/分类/标签/属性：统一设值或新增。

### 6.3 专项
- **改价**：按品牌/系列/区间批量；**价格历史**（`GET /items/{id}/history?field=purchase`，走 `gx_audit_log`）。
- **数量**：进/出自动更新；盘盈亏调整单；批量加减。
- **库位**：批量设/移；编码规则；占用提示。
- **媒体**：按槽位补图、设封面、清理冗余图。
- **去重合并**：同名/近名合并（合并数量、迁移图/标签）。
- **生命周期**：停售/归档；待删除→回收站→彻底删除。

### 6.4 单据与盘点
- 入库/出库/盘盈亏统一走 `gx_document`：`draft → posted`（事务内改 `entities.quantity` + 记 before/after）→ `rolled_back` 冲回；幂等键防重。
- 盘点会话：`count` 走 document(kind=adjust) + 差异报告（账 vs 实）→ 一次提交。会话 UI 可后置（先做报告）。

### 6.5 变更历史 / 撤销
- 字段级历史（谁/何时/旧→新）来自 `gx_audit_log`；单条撤销、**批量事务回滚**、**快照恢复 + 审计重放**（粒度=每日快照）。
- 审计导出：按日期/操作人/字段。

### 6.6 查找
扫码 / 定位码 / 库位 / 拼音首字母 / 品牌筛选 / 图片找相似 / 最近修改 / 待办；批量多选。

### 6.7 数据质量校验
必填（`*` + 拦截）、格式（库位 pattern、价格≥0）、异常值（0 价/负数量/超阈值提醒）、一致性（§4.4）。

### 6.8 权限与协作
`user_groups.role` 枚举：`viewer`（只读）/ `editor`（录入/盘点）/ `manager`（改价/删除/配置）。检查点：批量改价、删除、配置变更仅 manager；全部动作留痕。

## 7. 双端交互设计

### 7.1 移动 Shell（现场维护）
- **底部 Dock**（56px + safe-area）：台账 / 进出 / **助手(中央)** / 记录 / 我的；右下 FAB=拍照建档/扫码。
- **助手=底部抽屉**（三档 peek 20% / half 60% / full 100%）：把手 → 状态条 → 对话/步骤 → 结果卡（左右滑跳过）→ 输入区（📷主按钮，贴键盘）。
- **表单=整页**（不弹框）+ 底部常驻保存条；输入 16px 防放大。
- **手势**：左滑操作 / 长按多选 / 下拉刷新 / 抽屉拖拽 / 双击放大；**连续扫码**（巡店/盘点逐件 +1）。
- iOS 细节：`env(safe-area-inset-*)`、`100dvh`、`viewport-fit=cover`、PWA standalone、明暗 theme-color。
- 离线：只读缓存 + 写入队列（幂等）+ 离线横幅。

### 7.2 桌面 Shell（批量整理）
- 左侧栏（可折叠）+ 列表↔详情双栏 + 结果/审批 Panel 三栏。
- **⌘K 指令面板** + 快捷键（`/` 搜索、`n` 新增、`g t/i/o/r`、`↑↓↵`、`e` 编辑、`a/r` 接受/拒绝、`Esc` 关闭）。
- 表格密度（舒适/紧凑）、行内编辑、悬浮预览图。

### 7.3 组件两端自适应
| 组件 | 手机 | 桌面 |
|---|---|---|
| 助手 | 底部抽屉 | 右侧 Panel |
| 结果/审批卡 | 全宽卡片 | Panel 内卡片 |
| 表单 | 整页+底部保存条 | 居中整页 |
| 表格 | 卡片 | 数据表 |
| 主操作 | FAB+底部按钮 | 顶部按钮+快捷键 |
| Toast | Dock 上方 | 右下角 |

## 8. API 契约（自有层）

### 8.1 约定
- `/api/v1`；认证沿用；写操作支持 `Idempotency-Key`；乐观锁 `version`，冲突 409；分页 `page/pageSize`。
- **版本头**：响应带 `X-Api-Version`；前端 SW 检测版本变化**强刷**（配合 B8）。

### 8.2 端点
```
物品     GET/POST /items · GET/PATCH/DELETE /items/{id}
批量     POST /items/bulk（预览） · POST /items/bulk/apply（确认）
历史     GET /items/{id}/history?field=&from=&to=
媒体     POST /items/{id}/attachments?slot= · PATCH /attachments/{id}
配置     GET/PUT /config/schema · POST /config/schema/reset（=切默认版本）
属性     CRUD /config/attributes[/{id}] · CRUD /config/attributes/{id}/options
单据     POST /documents · POST /documents/{id}/post · POST /documents/{id}/rollback · GET /documents
盘点     POST /count-sessions[/{id}/lines|/close]（差异→adjust 单据）
审计     GET /audit?itemId&action&from&to
AI       POST /ai/recognize（按 attributes 定义抽取）· POST /ai/parse-document
现有     GET /metrics · GET /healthz · 二维码 /qr · CSV 导出 /items/export
```

### 8.3 示例
```json
PATCH /items/{id}  { "version": 7, "attributes": { "purchase": 18, "color": "蓝" }, "shelf": "A-3" }
200 { "id": "...", "version": 8, "attributes": { "purchase": 18, "color": "蓝" }, "shelf": "A-3", "auditId": "..." }
409 { "error": { "code": "version_conflict", "details": { "currentVersion": 9 } } }
```

## 9. 配置中心

- **属性**（原字段页升级）：名称/类型/必填/列/筛选/排序/单位/默认值/选项来源；key 创建后不可改。
- **位置**：分类维度名、库位启用/名/格式（`unique` 已废，见 §5）。
- **媒体**：槽位增删/命名/必填/多张/封面/每件上限。
- **组织**：品类选项、系列规则、分组维度。
- **reset = 版本切换（A5）**：保存自动入 `gx_config_history`；恢复默认=切回默认版本快照，用户自定义仍可切回，不丢数据。
- 属性变更沿用 sync-fields 回填思路（改冗余列 + JSON），并提示影响件数。

## 10. 迁移方案（一次性重构 + Sidecar）

### 10.1 原则
一次性完成「JSON 文件→表 + 新表落地 + 自有 API 上线」，但 **Homebox 核心表不动**；维护窗口、可回滚、副本演练。

### 10.2 映射（已补齐 A4）
| 旧 | 新 |
|---|---|
| groups/users/user_groups/api_keys/entity_types/entities/attachments/tags | **不变** |
| template_fields | `gx_attribute_def`（类型/必填/排序/单位；修复历史类型覆盖） |
| /data/ui-options.json | `gx_attribute_option` + `required` |
| /data/biz/intakes.json / outbounds.json（含**进货单据照片、历史回滚记录**） | `gx_document` + `gx_document_line` |
| /data/audit.log | `gx_audit_log` |
| /data/idem.json | `gx_idempotency` |
| /data/ai-cache/ | `gx_ai_cache` |
| /data/trash2.json（含**删除原因**） | `gx_item_meta.status='pending_delete'` + audit |
| 库位(serial_number) | `gx_item_meta.shelf`（去唯一约束） |
| /data/ui-options 的 required | `gx_attribute_def.required` |

### 10.3 步骤
1. 冻结：停止写入 → `wal_checkpoint(TRUNCATE)` → `ops/backup.sh` 快照（含 /data 全部 JSON）。
2. 建新表：`ops/migrate/schema_v2.sql`（gx_* + 版本表）。
3. 搬运：`ops/migrate/migrate`（`--dry-run` 出统计；幂等可重跑）。
4. 校验：条目数、抽样比对（价格/数量/类型/图片可访问/JSON↔冗余列一致）；不通过**中止不切换**。
5. 切换：旧库保留为 `homebox.db.v1`；`DB_PATH` 切换；重启容器。
6. 冒烟：smoke + e2e + 8 页巡检。
7. 回滚：`DB_PATH` 指回 `homebox.db.v1` 重启（秒级）。

### 10.4 演练
复制数据卷在副本上跑全流程 + 计时；生产窗口预留 5–10 分钟。

### 10.5 运维适配（B7）
- `backup.sh`：新数据源 = db（含 gx_ 表）+ 数据卷图片 + `gx_config_history` 导出。
- `metrics`：新增 gx 表慢查询、迁移校验结果、审计量。
- `check.sh`：把 `ops/migrate/`（DDL+脚本）纳入静态检查。

## 11. 验收用例

**迁移**：条目/标签/位置数一致；10 属性类型不变；ui-options 进下拉且 required 生效；intakes/outbounds → document 带照片与回滚记录；审计可查；图片可开、封面正确。
**配置**：进价必填→列头 `*`+保存拦截；新增属性→自动成列/筛选/编辑；reset→切回默认且可切回用户版本；库位格式校验、同格多款不报错仅提示。
**功能**：批量改价（差异预览→确认→回滚）；价格历史端点；入库→数量+，回滚→复原，重复提交幂等；盘点→差异→adjust→库存更新。
**双端**：移动 Dock/抽屉/整页表单/键盘避让/离线队列；桌面 ⌘K/快捷键/密度。
**故障（B9）**：断网回放、版本冲突 409、迁移中断重跑（幂等）。
**回归**：收银/报表不回归；单模板保持；SW 版本强刷生效。

## 12. 风险与回退
| 风险 | 缓解 |
|---|---|
| 数据丢失 | 快照 + 校验门禁 + 旧库保留（秒级回滚） |
| 死 fork | sidecar 边界（§3）；升级流程校验 |
| 停机超时 | 副本演练 + dry-run 计时 |
| 冗余列与 JSON 不一致 | 单一写路径 + 体检校验 |
| 配置误改 | 版本快照 + reset=切版本 + 审计 |
| 前端不兼容 | X-Api-Version + SW 强刷；同版本发布 |

## 13. 路线图（迁移先行）

1. **M0 迁移**：sidecar schema + JSON→表迁移 + 校验/回滚 + 演练。
2. **P0**：属性+位置配置（JSON 属性 + 冗余列同步 + 维护工作台「缺X」队列）。
3. **P1**：媒体槽位、单据/盘点、审计/历史 UI、批量维护（改价/数量/库位）。
4. **P2**：组织配置、权限、自动化（低库存→进货草稿）、图片找相似。
- 全程：移动优先、默认不联网（AI 费用护栏）、可回退。

---

## 附录：实现落地记录（截至 main 7e93035）

### 已交付
- **M0 迁移**：`ops/migrate/{schema_v2.sql,migrate.py,migrate.sh}`；构建时 `--ensure` 幂等建表/补列/回填；生产已附加 `gx_` 表并回填。
- **P0 配置**：`/api/v1/gx/config`(+history/restore)；前端「集合 → 配置」四维（属性/位置/媒体/组织/权限）；台账按配置派生必填与选项。
- **P1**：批量「差异预览→确认」；媒体槽位（title=槽位、primary=封面）；统一单据 `GET /gx/documents`（biz 写入同步 gx_document）。
- **P2**：组织配置生效（系列/分组维度/标签体系名）；权限检查点（危险操作 owner，editor 入库/出库/盘点可配）。
- **待办中心** `/tasks`：缺图/缺价/缺库位/缺安全库存/低库存/缺必填/重复/售罄/待删除 + 补货草稿 + 最近变更。
- **盘点**：差异报告 → `POST /gx/adjust` 生成调整单。
- **配置版本历史/回滚** UI。
- **PWA/移动端**：viewport-fit=cover、iOS 独立应用元信息、主题色。
- **多集合**：`gx_group_config` + 单据/审计 `group_id` 隔离；前端 `gx-fetch` 插件注入 `X-Tenant`。

### 已知限制 / 待办
- `gx_item_meta` 以物品 ID 为键（天然按集合正确）；配置/单据/审计已按集合隔离。
- 内部表 `gx_idempotency`、`gx_ai_cache` 应用并未使用（实际用 `/data/idem.json` 与 `ai-cache/` 文件），已**清理**（`--ensure` 会 `DROP`）。
- 迁移期遗留的 `gx_config`/`gx_config_history`/`gx_attribute_def`/`gx_attribute_option` 已确认无独有数据（配置以 `gx_group_config` 为准）并**已清理**（`--ensure` 会 `DROP`）。
- 移动端集合选择器若在折叠菜单内，需先选择集合后自研请求才带 `X-Tenant`；未选择时后端回退默认集合。
- 上游 Homebox 内核未改；未来升级仅需重跑补丁 + `--ensure` + 校验。

### 导航结构（重构后）
以「库存维护」为中心（整段替换上游 nav）：
- **待办** `/tasks`（默认落地页，吸收原「首页」）
- **物品** `/ledger`
- **盘点** `/ledger?count=1`
- **进出** ▾：入库 `/intake` · 出库 `/outbound` · 单据 `/documents`（统一读 `gx_document`）
- **库存配置** ▾：字段/位置/媒体/组织 `/collection/fields` · 选项配置 `/collection/ui-options` · 标签 `/tags` · 结构 `/collection/entity-types` · 工具 `/collection/tools`
- **设置** ▾：成员 / 邀请 / 通知 / 集合设置
- **我的** `/profile`
隐藏/降级：首页、维护、顶级标签、旧的 物品/分类/模板 页。

### 移动端底部 Dock（3）
`lg` 以下显示底部固定导航：待办 / 物品 / 进出 / 配置 / 我的（抽屉仍保留）；内容区加底部避让。

### 交互/跳转规范统一（4）
- 标题统一：待办 / 单据 / 入库 / 出库 / 入库记录 / 出库记录（原“进货/出货”全部改为“入库/出库”）。
- 头部统一：`flex-wrap` + 标题 + 计数徽章 + 右侧操作区；次要入口用 border 按钮，主动作用 primary 按钮。
- 互跳集合统一：进出/记录/单据页均含「入库 · 出库 · 单据 · 台账」（记录页前置主动作「去入库/去出库」）。
- 空/加载/错误态统一：`h-16 animate-pulse` 骨架、`rounded-xl border border-destructive/40 …` 错误、`py-10 text-center text-sm text-muted-foreground` 空态。

### Claude 式交互（分步）
1. **⌘K 命令面板**：快捷键改 `Ctrl+K`；面板纳入所有导航（含子项）+ 新建项；搜索按文本过滤；统一入口。

2. **视觉/留白**：更浅画布(`--background-accent 96%`)、更柔边框(`--border 91%`)、更圆角(`--radius .75rem`)、更柔次要文字；自研页容器留白加大(`p-4 md:p-8`、`mb-4`)。

3. **少弹窗（右侧抽屉）**：台账的新增/数据体检/批量导入/变更历史/图片/自定义字段 由居中弹窗改为**右侧抽屉**（desktop 右栏、mobile 全宽），减少打断感。

### Codex 式中性配色 + 衬线标题（5）
设计参照 OpenAI/Codex 的近单色中性系，叠加 Claude 的「衬线标题/无衬线正文」分工。

- **配色**（`patches/patch_upstream.py` `patch_colors`，浅色）：画布纯白 `#fff` + Mist `#fafafa`、正文 Ink `#0d0d0d`、主按钮墨黑（Codex 式黑底白字，弃用靛蓝）、次要/静音面 `#f5f5f5`、次级文字 `#6e6e6e`、发丝边框 `#e5e5e5`、焦点环墨色、`--destructive: #ef4146`、sidebar-* 全套同步（修掉历史微调漏改侧栏的问题）。
- **深色**（`patch_dark`）：`#171717` 底、`#212121` 卡片、主按钮反转为白底黑字、边框 `0 0% 22%`；与浅色同为中性零色相。
- **字体**（`patch_fonts` 注入 tailwind.config）：`font-display` 衬线栈 `Georgia, Times New Roman, Songti SC, STSong, SimSun, serif`（iOS/macOS 自带宋体，零字体加载）；`font-sans` 中文优化栈；`font-mono` 系统等宽。标题一律衬线 + `font-medium`（500，衬线不用粗体）。
- **应用面**：侧栏「Groza」字标、各自研页 h1（待办/物品台账/入库/出库/入库记录/出库记录/单据）、台账 6 个右侧抽屉标题。
- **组件层次**：Card 改发丝边框替代投影；Button default/destructive/outline/secondary 去掉 shadow——深度靠边框与背景色差表达。
- **PWA**：theme-color 改 `#ffffff`(light)/`#171717`(dark)，mask-icon `#0d0d0d`。
- **迁移兼容**：`rep_any()` 支持把历史已应用的旧值（靛蓝字标/旧 theme-color）迁移到新值；`patch_colors` 锚点改为任意 `--radius:` 值，重复构建安全。

### 菜单/布局/交互 Codex 化（6）
- **侧栏分组扁平菜单**：nav 数组改扁平 + `group` 字段，`navGroups` computed 切段渲染；分组：概览(待办) / 库存(物品·盘点) / 进出(入库·出库·单据) / 库存配置(字段·选项·标签) / 设置(成员·邀请·通知·集合) / 高级(结构·工具) / 我的。组标签为小号 muted 字，去掉 Collapsible 层级与折叠箭头（⌘K 扁平 nav 天然兼容）。
- **侧栏头部瘦身**：welcome 文案 → 衬线「Groza」字标；删除大圆 logo；「创建」改全宽发丝边框白底按钮（Codex "New thread" 式）。
- **移动顶栏**：去 `shadow-md` 投影改 `border-b` 发丝线 + `bg-background/95 backdrop-blur`。
- **移动 Dock**：选中态改灰底 pill（`bg-accent rounded-full` 包裹图标）+ 墨色文字，不再用主色变色。
- **自研页统一**：计数徽章/信息 chip 一律 `bg-muted text-muted-foreground`（原 `bg-primary/10`）；页头 `mb-4`→`mb-6`；所有带边框容器去 `shadow-sm`（无边框的购物车行补 `border`）；tasks 队列卡片 hover 改 `border-foreground/25`。
- **交互基调**（`patch_motion` 追加 main.css，哨兵 `groza-motion`）：全局 a/button/input 150ms `cubic-bezier(0.16,1,0.3,1)` 过渡、8px 细滚动条（hover 加深）、`::selection` 墨色 12%。
- **清理**：废弃 nav-collapsible-trigger-hidden / nav-collapsible-row-minw 两个失效补丁（v2 模板已无 Collapsible）；`rep()` 支持 `new=""` 的删除型替换（sidebar-logo-rm）。

### 台账页信息层级重排（7）
- **卡片瘦身**：操作行 6 按钮收至「图片/标记删除/⋯」（二维码/复制/历史/字段进 ⋯ 上弹菜单）；「合计数量」统计卡删除并入页头徽章（N 款/共 N 件/售罄 N）；双 primary 收敛为「新增物品」唯一主按钮，「AI 新增」降 ghost；移动 FAB 删除（与页头重复且遮挡内容）。
- **内容主角化**：数量为卡片视觉焦点（步进器中间 text-xl font-semibold，−/+ 加宽 w-12 text-2xl）；进售价格双 0 时整行不渲染；属性 chip 行改点分隔纯文本（库位保留可点 chip）；安全库存低频化——默认「安全 N」小字按钮，点开才变输入框（blur/Enter 保存收回，:ref 函数聚焦替代 autofocus）。
- **状态驱动视觉**：待删除/售罄整卡 opacity-60 退到背景层；低库存卡左缘 border-l-2 border-l-amber-400 边条（优先级 待删除 > 售罄 > 低库存）；页头「待补货」徽章可点击切换 onlyLow 筛选（激活实心 amber）。
- **标准化销项**（ui-standard.md 差距 #3–#10）：裸色全量 token 化（destructive/foreground）、徽章统一 text-xs/px-2.5、抽屉抽 drawerWrap/drawerPanel/safeBottom 常量、筛选 sheet 下拉换 inputClsLg（text-base 防 iOS 缩放）、骨架/error/empty 换共享常量、底部弹层 Transition 统一 sheet、筛选 sheet z-40→z-50。
- **交互补全**：移动筛选 sheet 新增排序区块（9 键 + ↑↓ 方向，复用桌面 sort 状态）；分页条移动端只留 上一页/x/y/下一页，「全部=100000」仅桌面。
- **深色巡检**：tasks 开关滑块 bg-white 改 bg-primary-foreground（随主题反色，修深色下滑块隐形）。
- **隐藏售罄开关**（补充）：页头「售罄 N」徽章变开关按钮（eye-off/eye 图标），默认隐藏售罄；接入 view/applyView 视图同步（URL `hideSold=0` + localStorage，absent 回落默认 true）；计数改用过滤前的 soldCount 避免徽章死锁；`data=soldout` 视图（待办页跳转）下开关自动失效并置灰。

### 全 tab 页面标准化统一（8）
- **进出页**（intake/outbound）：补 loading 骨架/error 重试/empty 空态三态；表单与明细输入全量 text-base 防 iOS 缩放；页头互跳链接换 btnGhost；触控目标 ≥36px；出库保存条抬高 `calc(3.75rem+safe-area)` 修被 Dock 遮挡（根容器 padding-bottom 同步升 8rem）；删除 rollback/dt 等死代码。
- **记录/单据页**（intake-records/outbound-records/documents）：primary 主入口统一最右（去入库/去出库）；日期输入 h-11 text-base；回滚确认 window.confirm → 居中确认弹窗；flash 去 toast/alert 双轨改页内 msg；筛选区加「重置」；徽章/骨架/错误/空态全量换 badgeCls/skeletonCls/errorCls/emptyCls；chip px-2 残留清为 px-2.5；documents 补 primary「去入库」、切 kind Tab 重置全部筛选。
- **配置页**（collection/fields、ui-options）：shadcn Button 全换 btnPrimary/btnGhost 原生按钮（32px 触控问题解决）；保存中 disabled 防重复提交；ui-options 加载失败禁用保存 + errorCls 重试（防空白表单清空线上配置）；textarea/键/正则/标签输入全量 text-base；删属性/槽位/恢复默认/回滚版本全部走确认弹窗；已建成字段键输入锁定。

### WebSocket 与 bfcache 共处（9）
- **问题**：页面被浏览器收进前进/后退缓存（bfcache）时，浏览器强杀挂着的 WebSocket 并在控制台刷 `WebSocket connection ... failed: Page entered Back-Forward Cache` + `websocket error Event`；恢复后旧代码也不会立即重连，实时事件断流。台账页同时存在两条连接（全局 `use-server-events` 带 tenant 参数 + ledger.vue 自带裸连接），报错翻倍。
- **方案**：注入定制 `frontend/composables/use-server-events.ts` 覆盖上游同名文件（rebuild.sh CUSTOM_FILES/cp 已登记）；ledger.vue 自带连接同步处理。
- **生命周期**：`pagehide` 主动关闭连接并清空回调（浏览器无需代杀，控制台从此干净）；`pageshow(persisted)` / `visibilitychange=visible` / `online` 时检测 readyState，死连接立即重连并重置退避（不等 backoff）；`onerror` 降为 debug（错误后必有 close，重连统一由 onclose 安排）。
- **防重复**：connect 前检查 OPEN/CONNECTING；恢复路径复用既有 `scheduleReconnect` 指数退避（1s→30s 封顶）。
- **验证**：/tmp/bfcache-test.py（Playwright + init_script 打 docId/pageshow 标记）；测试环境因自签证书 SW 等因素不进 bfcache，降级判定通过——离开再返回零 bfcache/WS 报错、WS 自动重连成功。

### 记录页收敛进单据（10）
- **删除 /intake-records、/outbound-records**：与单据页功能重叠 90% 且不在菜单（仅入/出库页头链接可达）。入库页头去掉「入库记录」；出库页「单据」链接带 `?kind=outbound` 直达出库 Tab。旧路由 404，rebuild.sh/check.sh 同步除名（含清理前端复用目录残留 `rm -f`）。
- **单据页 kind 参数化**：`?kind=` 初始化 Tab、切 Tab `router.replace` 同步 URL、监听 query 变化（页内跳转也生效）。
- **落库不再静默**：gxRecordDocument 改返回 error；gxRecordDocumentLogged 统一兜底（log.Printf 进 docker logs + 异步触发对账）；gxRepairDocumentsFromBiz 以 biz JSON 权威存储为准幂等回填缺失单据并同步回滚状态；单据页首次查询 sync.Once 自动对账一次。上线即回填 12 条历史遗漏（150→162 条），当前 0 缺失。盘点调整无 biz JSON 副本，不在对账范围（失败仅日志）。

### 发货台取代单据页（11）
- **业务流**：买家下单 → 新建发货单（拣货/打包，**不动库存**）→ 发货前买家退款则「取消」（库存无影响）→ 打包完成「确认发货」才真正扣库存并生成出库单。解决发货前退款的库存污染问题。
- **后端** `backend/ship.go`：`/biz/shipments` GET/POST + `/ship` `/cancel` `/undo` 五个接口，shipments.json 存储（biz JSON 模式），全接口幂等键；确认发货复用重构出的 `applyOutbound` 核心（库存不足明细跳过并报错、全败 400、部分成功返回 errors）；撤销发货复用 `applyOutboundRollback`（owner 权限，库存加回+出库单回滚）；审计 shipment.create/ship/cancel/undo。
- **biz.go 重构**：applyOutbound/applyOutboundRollback 抽公共核心（行为不变，原 handler 变薄壳），发货与出库共用。
- **前端** `frontend/pages/ship.vue`：待发货/已发货/已取消三 Tab（带计数）、待发徽章、卡片明细+合计、待发货卡实时库存不足预警（ amber）、确认/取消/撤销均走居中确认弹窗；新建发货单右侧抽屉（drawerWrap/drawerPanel）：买家/备注 + 商品搜索拣选（库存上限步进器）。
- **单据页下线**：documents.vue 删除（用户判定无价值），侧栏「进出」组 入库/出库/**发货**（MdiPackageVariantClosed），Dock 进出项覆盖 /ship；入/出库页头 单据 链接换 发货。gx_document 表与 /gx/documents API 保留（后台审计用，不对用户暴露）。
- **补丁教训**：rep_any/rep 的历史锚点是匹配复用目录里旧构建产物的，改 nav/dock 内容时旧变体必须冻结保留（本次新增 dock_prev、nav-group-icons 改 rep_any 三变体）。

### 盘点模式沉浸式区分（12）
- **问题**：盘点与物品同页差异太隐晦（仅横幅+输入框），且盘点开关被视图持久化（localStorage count=1）污染——点菜单「物品」也停在盘点模式，两入口体感完全一样。
- **URL 是盘点唯一来源**：syncView/savePreset 落 localStorage 时剥离 count；onMounted 强制 `countMode = route.query.count === "1"`（兼容历史残留）；页内开关仍可用（经 syncView 写回 URL）。
- **沉浸式盘点界面**：h1/title 动态「盘点 ↔ 物品台账」（countMode 声明上移到 useHead 前，避开 TDZ）；页头 amber 进度徽章「已盘 N/M」；卡片精简——隐藏价格行/操作行/左滑手势/长按多选（进入盘点自动清空选择）；实盘输入放大 h-12 w-24 text-xl；差异徽章化（盘盈墨色/盘亏红/持平灰）；移动端底部固定提交条（已盘 N/M · 差异 X + 提交盘点，避开 Dock），桌面保留横幅按钮（无差异时禁用）。

### 台账移动端无限滚动（13）
- **问题**：列表长（120+ 条）时翻页按钮沉在 50 张卡片底下，移动端「显示不下、翻页困难」。
- **方案**：移动端改无限滚动——首批 30 条，滚动接近底部哨兵（innerHeight+400px 提前量）自动追加 30 条，到底显示「共 N 条 · 到底了」；筛选/排序/视图切换重置回首批。桌面保留翻页条（移动端隐藏）。
- **实现教训**：IntersectionObserver 对「瞬移式滚动越过哨元」（下方不可见→上方不可见，交集状态不变）不会回调，快速甩动/跳转会卡死加载——改用 passive scroll 监听 + getBoundingClientRect 判定，简单可靠。

### 盘点模式精简为「只改数量」（14，覆盖 12 的实盘/差异方案）
- 用户判定实盘/差异/提交调整单流程过重。盘点模式改为极简对账视图：只保留数量步进器（即改即存），其余全部锁定或隐藏。
- **移动端卡片**：实盘输入/差异徽章/底部提交条删除，换回数量步进器；安全库存、库位编辑、价格行、操作行在盘点时隐藏/禁用。
- **桌面表格**：盘点时隐藏多选列、操作列、实盘/差异列；名称/库位/品牌/规格/价格/安全库存等编辑器全部 disabled，仅数量可编辑。
- **删除机制**：盘点差异报告弹窗、submitCount/confirmCount/diff 系列函数、Row.count 字段；gx/adjust 后端接口保留（暂无 UI 入口）。
- 保留：h1/title 动态「盘点」、amber 提示横幅（文案改「只保留数量修改，即改即存；其余编辑已锁定」）、URL 唯一来源（12 的机制不变）。

### 卡片/列表切换 + 移动端 Dock 移除（15）
- **卡片/列表切换**（ledger 物品/盘点共用）：`viewMode`（card/list，localStorage `hb.ledger.viewmode`，默认移动=卡片、桌面=表格）。卡片视图桌面端变 2/3/4 列网格（复用移动卡片）；移动列表模式为新增紧凑行（40px 图 + 名称/徽标 + 属性行 + 小步进器，无操作列——盘点/普通都只改数量）。切换按钮：移动顶栏筛选旁 + 桌面筛选条「重置」旁（MdiFormatListBulleted/MdiViewGridOutline）。无限滚动哨兵扩展到卡片视图全端+移动列表；分页条仅桌面列表模式。
- **Dock 移除**：移动端底部 Dock（待办/物品/进出/管理/我的）与汉堡抽屉冗余，patch 反向化——mobile-dock 改 rep_any 四变体→pristine 尾巴，mobile-dock-padding 改 rep_any 回退 pb-16。出库保存条 bottom 3.75rem+safe → bottom-0 + safe-area；出库/发货容器 padding-bottom 8rem → 2rem；ui-standard §底部留白/z-index 条款同步。
- **结构教训**：哨兵 div 曾夹在 TransitionGroup 与表格 v-else 之间，表格 v-else 实际配对的是哨兵的 v-if（碰巧可用）——条件链必须相邻，本次已把哨兵移出链条。

### 图片加载占位动画 GxThumb（16）
- 新增共享组件 `frontend/components/GxThumb.vue`：加载中显示 muted 脉冲骨架 + 图片图标（替代 opacity-0 空白，用户不再以为没图）；`img.decode()` 完成后 300ms 淡入；加载失败显示 image-off 占位图标（不再空转脉冲）。
- 替换点：台账卡片/紧凑列表/桌面表格缩略图、发货台拣选、出库拣选（顺带去掉了出库残留的 loading="lazy"）。ledger 的 revealImg 死代码删除。
- **坑**：上游 nuxt.config `components: { dirs: [] }` 关闭了自动扫描——组件必须显式 `import GxThumb from "~/components/GxThumb.vue"`（生产构建把 resolveComponent 失败静默降级，页面零报错零图片，极难排查）；rebuild.sh 构建前固定清 `.nuxt` 与 `node_modules/.cache/nuxt`（复用目录的扫描缓存会让新组件/composable 不进注册表）。

### 图片加载动画补齐（16 补）
- 覆盖扩展到：图片抽屉（多图，GxThumb h-28 w-full）、大图预览（居中 spinner，@load 淡入，preview 切换重置 previewLoaded）、入库页拣选（残留 loading=lazy 一并去除）。
- 说明：已缓存图片瞬时显示不出动画是预期行为；动画只在真实慢加载时出现。验证用请求拦截（abort/延迟）确定性复现。

### AI 拍照滤重：图片指纹 pHash（17）
- **需求**：AI 新增时通过照片直接判定「这物品已经有了」，起滤重作用；只做第一层（近似重复检测），不做文本/embedding 层。
- **实现路径选择**：全前端 canvas 计算（`frontend/composables/usePhash.ts`），不建后端哈希接口——浏览器与 Go 分别缩放+哈希会因插值差异产生两套对不上的指纹，单一实现保证一致性；指纹索引存 localStorage `hb.phash.v1`（附件 id → 指纹 + 物品 id 映射），台账加载后后台逐张补齐（40ms 间隔防卡顿，失败单张跳过）。
- **算法**：32×32 灰度 → DCT → 低频 8×8 与中位数比较 → 64 位指纹（16 hex）。汉明距离 ≤8 强命中、9~14 弱提示。拍照压缩后与 AI 识别 `Promise.all` 并行，不拖慢原流程。
- **命中交互**（确认框内嵌，不自动裁决）：强命中出琥珀色拦截条（缩略图+「疑似已有物品 · 相似度 N%」+库存），主按钮变「并入库存 +1」（复用 step() 含撤销记录）与「定位查看」（设 filter.q），「仍要新增」降级为次按钮；弱命中灰条提示+定位；队列内互查（距离 ≤6）提示同批重复。
- **指纹沉淀**：AI 新增成功、并入已有（照片作为该物品额外附件，一物多指纹）、手动换封面，三处都会自动登记指纹。
- **清理**：aiReject/aiCreateOne/aiAdvance/clearAIDone 同步清理 aiHashes；测试脚本 tests/test_phash_dedup.py（端到端：索引→同款重拍→拦截条→并入→库存+1），副作用清理 tests/cleanup_phash_test.py。

### 服务端共享指纹库（17 补）
- **问题**：指纹索引存 localStorage，每台设备各自扫描全量图片建库，iPhone 首次要等几十秒。
- **方案**：新增 `backend/phash.go`（GET/PUT `/api/v1/gx/phashes`，按集合存 `/data/biz/phashes-<组ID>.json`，biz JSON 模式，PUT 增量合并+16 位 hex 格式校验，同键以服务端已有为准——同一浏览器算法产物必然一致）。前端：onMounted 先 pull 共享库再 buildPhashIndex（只补算缺的）；本地新增指纹（建索引/AI 新增/并入/换封面）防抖 2.5s 回推。
- **补丁**：routes-phash 独立块，锚点复用 routes-ledger 注入的 gx/config/restore 行（新树由 6 号块先注入、复用树已有该行，两种路径都适用；独立 marker 避免 rep_any 锚点冻结问题）。
- **验证**：tests/test_phash_sync.py——全量 117 张建库 → 服务端写入 117 → 全新浏览器上下文（模拟新设备）直接拉到 117/117 零重算。

### 定向刷新：消灭「改一条、刷全表」（18）
- **问题**：WS mutation 事件（上游只广播组级 GroupMutationEvent，无实体 ID）触发防抖整表 load()——自己改一个数量，1.5s 后全表骨架屏闪烁、无限滚动与滚动位置被重置。
- **本页回声抑制**：$fetch 包一层，任何非 GET 请求写入 lastLocalEdit 时间戳（覆盖数量/字段/名称/价格/批量/上传等全部写路径，不只数量）；WS 事件落在 6s 窗口内直接跳过——本地保存函数已就地更新行，无需刷新。
- **静默增量刷新**：窗口外的 mutation（他人/其他设备编辑）改走 refreshSilent()——重拉 /api/v1/ledger 按 id 合并 applyAgg，不碰 loading 骨架屏、shown 已加载条数与滚动位置（keyed v-for 复用 DOM）。
- **显式 load() 收敛**：新增物品/复制一件/关闭图片抽屉改 refreshRow(id) 单行定向拉取（不存在则 unshift）；彻底删除（单个/批量/清空）改本地 filter 剔除。保留下拉刷新与批量导入的整表 load()（用户主动/大批量场景）。
- **测试教训**：抑制窗口会误伤「紧随其后」的外部编辑断言——测试须先越过 6s 窗口再模拟外部编辑。tests/test_targeted_refresh.py 8 项全过。

### 多尺度指纹 v2：重拍取景差异召回（17 再补）
- **问题**（用户实测：两次拍鼠标没触发滤重）：单段全图 pHash 对平移/裁剪/旋转极敏感——实验实测裁 10% 边缘距离 18、旋转 8° 距离 24，全部漏网；亮度变化稳（4~6）。真实重拍几乎必有取景差异，单段指纹形同虚设。
- **方案**：每张图算 3 段指纹（全图 + 中心 80% + 中心 60%，共 48 hex），比对取两两最小距离。实测：裁 25% 距离 0、裁 10% 10、提亮 2、旋转 8° 14（弱提示），误报对照（鼠标 vs 鼠标垫）保持 26 安全距离。旋转 20°+ 仍漏（预期，拦截定位是提醒而非裁决）。
- **兼容**：phashHamming 分段处理——等长多段取最小，新旧（16/48）混比只比全图段；后端校验放行 16/48 位 hex。localStorage 键升级 hb.phash.v2，服务端旧库清空后由引导脚本全量重建（119 张）。
- **验证**：tests/test_phash_sensitivity.py（单段灵敏度基线）、tests/test_phash_multiscale.py（多尺度召回+误报对照）、tests/test_phash_recrop.py（真实链路回归：鼠标主图裁 15% 走 AI 新增 → 强拦截 88% 指向鼠标，拒绝不留副作用）。

### 滤重方案替换：Embedding 以图搜图（19，取代 17 的 pHash 方案）
- **决策**：pHash（含多尺度 v2）对真实重拍的取景差异召回不足，用户拍板改用 doubao-embedding-vision 多模态向量。pHash 代码全量移除（usePhash.ts / backend/phash.go / routes-phash 补丁块，补丁会自动清理已注入的旧路由）。
- **架构**（向量全程服务端，前端零计算零存储）：新增 `backend/embed.go`——`POST /gx/embed-match`（图片字节→向量→对全库余弦→Top5 {itemId,score}）、`POST /gx/embed-register?item=&att=`（登记向量，按附件 ID 存）、`GET /gx/embed-status`。向量库 `/data/biz/embeddings-<gid>.json`（base64 float32le，1024 维约 5.5KB/张）；向量按内容 sha256 缓存（`/data/ai-cache/emb-*.json`），同图重复算不调模型不计费；模型更换自动视为空库。
- **模型坑**：账号只开通了 `doubao-embedding-vision-251215`（250615/250328/241215 均 404 NotFound）；可用 `GET /api/v3/models` 查目录，status=None 才是已开通（Retiring 不可用）。默认模型可用 HBOX_AI_EMBED_MODEL 覆盖。
- **阈值标定**（tests/test_embed_calibrate.py 实测）：同物变体（裁 15%/旋转 8°/提亮 30%）余弦 0.958~0.991，跨物品最高 0.711 → EMBED_STRONG=0.90 / EMBED_WEAK=0.80，间隔带宽阔。
- **前端**：runAIQueue 里 embed-match 与 AI 识别并行；确认框拦截条/弱提示/并入/定位交互不变（相似度 = score×100%）；登记三入口不变（新增/并入/换封面）。pHash 时代的队列内互查移除（同图经缓存得同向量，建完即被 1.0 拦截）。
- **验证**：引导 tests/test_embed_bootstrap.py 全量 119/119 登记成功；回归 tests/test_embed_recrop.py 鼠标裁 15% → 强拦截 97% 指向鼠标 ✓。

### AI 供应商切换：火山方舟豆包 → 阿里云百炼 Qwen（20）
- **决策**：用户改用阿里云百炼（DashScope）key。AI 识别与向量滤重两条链路整体迁移，接口路径、请求/响应形态对前端完全透明（无前端改动，仅注释更新）。
- **识别链路**：`ai_recognize.go` 改走 OpenAI 兼容模式 `POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，模型 `HBOX_AI_MODEL`（默认 `qwen-vl-max`）；联网搜索用 `enable_search:true`（VL 实测支持），非 200 自动降级纯识别重试；响应兼容 content 字符串/分段数组两种形态。
- **向量链路**：`embed.go` 改走百炼原生接口 `POST .../api/v1/services/embeddings/multimodal-embedding/multimodal-embedding`，模型 `HBOX_AI_EMBED_MODEL`（默认 `qwen3-vl-embedding`，`parameters.dimension=1024` 保持维度不变；multimodal-embedding-v1 固定 1024 维不支持 dimension 参数，传参会 400，故仅 qwen 前缀模型附带）。请求体为 `input.contents:[{image:dataURL}]`，响应取 `output.embeddings[0].embedding`（旧 `data` 形态解析删除）。
- **环境变量**：`HBOX_AI_ARK_KEY/HBOX_AI_ARK_MODEL` 废弃 → `HBOX_AI_KEY/HBOX_AI_MODEL/HBOX_AI_EMBED_MODEL`（env.example 与线上 env 同步更换，旧 key 已移除）。
- **两个配套修正**：① 缓存键加模型 slug（`ai-<模型>-<sha>.json` / `emb-<模型>-<sha>.json`）——否则换模型后旧缓存向量/识别结果会被错误复用；② data URI 的 format 段改为魔数嗅探（png/webp/jpeg）——前端固定发 image/jpeg 头，PNG 图会被错标，百炼对格式与实际编码一致性更严格。
- **阈值复标定**（test_embed_calibrate.py，换模型后必做）：同物变体（裁15%/旋转8°/提亮30%）余弦 0.989~0.995、原图 0.997；真实跨物品最高 0.685 → EMBED_STRONG=0.90 / EMBED_WEAK=0.80 维持不变，间隔带比豆包更宽。标定中「未识别物品」对鼠标变体 0.975 高分，排查确认该物品封面就是用户第二次实拍的鼠标照片（pHash 时代的重复数据残留），属正确命中而非误报——也实证了「拍两次鼠标」场景现在会被强拦截。
- **验证**：全量向量引导 119/119（qwen3-vl-embedding）；recrop 回归（裁 15% → 强拦截指向鼠标）✓；/api/v1/ai/recognize 实测返回结构化 JSON ✓。

### 导航分组重组：配置 = 建模、管理 = 团队与系统（21）
- **问题**：「库存配置 / 设置 / 高级」三个配置类分组边界模糊——「设置」组里又有一个「设置」子项（组项同名）；「结构」（实体类型）明明是库存建模却在「高级」；菜单项「字段 / 位置 / 媒体 / 组织」四词堆叠；「通知器」行话。9 个低频配置项分散三组，占侧栏一半。
- **新结构**（5 组 + 我的）：概览(待办) / 库存(物品·盘点) / 进出(入库·出库·发货) / **配置**(库存架构·选项·标签·结构) / **管理**(成员·邀请·通知·集合设置·工具)。心智模型：配置 = 库存怎么建模（低频一次性），管理 = 团队与系统维护。
- **改名**：「字段 / 位置 / 媒体 / 组织」→「库存架构」，「选项配置」→「选项」，「通知器」→「通知」，「设置」(集合设置页)→「集合设置」；结构从高级移入配置，工具从高级移入管理，「高级」组取消。
- **实现**：nav_body 重写（组序=数组首现序）；nav-restructure 幂等守卫改认新标记「库存架构」（旧树含「概览」会跳过，必须换标记才能重打）；zh-CN locale 补 `collection.tabs` 改名（页签条与侧栏同源一致）；集合页 tab 历史注入值迁移（选项配置→选项走 rep_any 更名块；fields tab-target 的 new 直接收敛为「库存架构」，olds 冻结全部历史变体）。fields.vue 页标题同步「库存架构」。
- **教训**：tab 更名要注意下游补丁锚点连锁——collection-locations-tab 锚定在 ui-options 页签文本上，改名前必须先插迁移块，否则第二轮构建 FAIL；所有更名均已验证二次构建幂等。
- **验证**：桌面 1280px 侧栏全量渲染（15 项 + 5 组标，内容区 overflow-auto 可滚到底见管理组与「我的」）；iPhone 390px 抽屉完整分组 ✓；集合页 tab 条命名一致 ✓。

### 集合页纯粹化：去页内 tab 条，布局按路由出标题（22）
- **问题**：库存架构等集合页顶部挂一条混合全部组的 tab 条（成员/邀请/通知/集合设置/结构…），与侧栏分组矛盾、不纯粹；且历史补丁链叠出了两个 fields 重复 tab（配置→/templates 与 库存架构→/collection/fields 并存）。
- **方案**：导航唯一入口收口到侧栏/抽屉。collection/index.vue 删「管理集合 - {name}」卡与 ButtonGroup tab 条；页头只剩 衬线 h1（新增 `currentTabLabel` computed：按 route.path 命中 tabs 数组得当前页名）+ 右侧动作区（保留 `#collection-header-actions` teleport 目标与退出/删除集合按钮）。tabs 数组退化为路由→标题映射表。fields/ui-options 的 Teleport 页头按钮不受影响。
- **入口兜底**：/locations（分类）此前唯一入口就是被删的 tab——侧栏「配置」组补「分类」项（MdiFileTree；「结构」改 MdiShapeOutline 避让，与旧 tab 图标语义一致）。
- **tab 数组收敛**：fields tab 改为幂等 unify 块（正则清掉全部 id:"fields" 历史条目 → 注入唯一最终形态），取代脆弱的「锚定追加 + rep_any 收敛」两段式——后者在收敛态上会重复追加（重复 tab 就是这么来的）。
- **补丁教训（重要）**：同一串上「先 replace 再按旧偏移 splice」必错位——本轮因此切坏构建树的 collection/index.vue（吃掉 `</script>/<template>/<BaseContainer>/<Title>` 并复制了按钮残片），手工修复树文件后纠正补丁顺序（先脚本替换、再在新串上算模板位置）。失效块 `collection-tabs-label-mobile`（锚定已删的 tab 标记）随之一并废弃——**删除 HTML 结构类补丁时，必须 grep 下游锚定该结构的补丁块一并处理**。
- **验证**：/collection/fields 无 tab 条/无管理集合卡/标题=库存架构/teleport 保存按钮存活；/collection/members 标题=成员；抽屉含「分类」且 /locations 可达；补丁二次执行全 SKIP 无 FAIL。8 项断言全过。

### 中文化清扫 + 台账工具条收敛（23）
- **中英混杂根因分两类**：UI 壳残留（登录页 HomeB[logo]x 大字标、GitHub/Mastodon/Discord/文档社交图标、语言下拉「中文（简体）（中文（简体）」重复、Toggle Sidebar 无障碍文案、18 个页面 useHead 标题「HomeBox |」）与**数据残留**（集合名「狗砸的宝藏's Home」是注册时上游自动命名，经 PUT /api/v1/groups 改名「狗砸的宝藏」，currency 保留）。
- **登录页**：字标改「盒子 logo + Groza」；社交图标整段移除（保留语言选择器）；LanguageSelector 只显示母语名（不再 当前语言名+括号母语名 重复）。
- **台账工具条（丑陋重灾区）**：桌面 11+ 按钮在 flex-nowrap 下被压缩竖排换行（补货提/醒、导出 CS/V）——根因是按钮无 `whitespace-nowrap` 且数量超设计标准 §10「页头 ≤5 按钮」。收敛：桌面可见 = 扫码/刷新/撤销(瞬时)/联网开关/同步状态点 + 更多⋯ + AI 新增 + 新增物品；低频动作（补货提醒/安装/数据体检/批量导入/导出CSV/复制清单/导出长图/大字号/清空回收站）全部收进「更多」菜单，菜单从 `md:hidden` 改为移动/桌面统一。btnGhost/btnPrimary 共享常量补 `whitespace-nowrap shrink-0`。
- **实现**：登录页字标/社交图标为补丁块（login-wordmark-groza / login-social-rm 段替换）；标题清扫为 glob 巡检替换（`HomeBox |` → `Groza |`，幂等）；LanguageSelector/侧栏 sr 文案为 rep 块。
- **验证**：登录页 Groza 字标+无社交图标+语言下拉不重复；台账工具条无竖排按钮、更多菜单含全部低频动作；6 页控件英文残留扫描零命中（允许 Groza/AI/CSV 等专有名词）。

### 交互统一改造：安静表格 + Esc/外点 + 键盘流（24）
- **调研**（子代理，8 个一手来源）：Nielsen 响应三阈值（0.1s 直接操纵感上限）、Linear（乐观更新是架构、动画只动 transform/opacity）、Notion（hover 渐进披露 checkbox/拖柄）、Apple HIG（44pt 触控下限）、Material（Snackbar 4-6s 至多一个动作）、A List Apart（Never use a warning when you mean undo；失焦校验优于边输边报）。产出 20 条统一交互标准，精选 10 条落地为 ui-standard.md §11。
- **台账桌面「安静表格」**（本轮最大痛点：每格都是带框控件、每行 6 个图标按钮常显）：单元格控件统一 `cellCtrl/cellInput/cellSelect` 常量——默认透明无边（读时如文档），hover 显边、focus 显环；行操作 6 按钮与复选框 `opacity-0 group-hover:opacity-100 focus-within:opacity-100`（有选中态时复选框常显）；数量步进保持常显（主操作不藏）；功能零删减。
- **全局弹层卫生**：新增 `frontend/composables/useEscStack.ts`（Nuxt 自动导入）——useEscStack（Esc 按栈顶优先逐层关闭：图片预览→扫码→AI 确认→筛选/新增/体检/导入/历史/图库/字段/二维码/批量预览抽屉）+ useDetailsAutoClose（`<details>` 菜单外点收起，原生无此行为）。接线：ledger（12 层）、outbound（扫码）、fields（确认框）；ship 既有手写 Esc 保持。
- **表单键盘流**：入库页桌面落地自动聚焦搜索框（`qInput.focus()`，移动端不弹键盘避免打扰）。
- **注意**：与 rebuild 链路一致——新 composable 三处登记（rebuild.sh cp + CUSTOM_FILES + check.sh）。
- **验证**：静默表格默认态/hover 态截图对比；Esc 关二维码抽屉 ✓；更多菜单外点收起 ✓；入库自动聚焦 ✓；复选框选中态常显 ✓。

### 易用性三件套：连续滚动 / ⌘K 命令面板 / 手势盘点（25）
- **连续滚动替代翻页**（Linear/Notion 式）：删除桌面分页机制（page/pageSize/totalPages/gotoPage/分页条），台账桌面表格与移动端共用 shown/shownList 渐进揭示（首批 30，哨兵近视口 +30）；全选范围从「当前页」改为「已加载」。翻页相关 query 不再产生，书签语义不变（筛选仍在 URL）。
- **⌘K 命令面板**（上游 QuickMenuModal 改造）：① Ctrl 热键补 `|| (key.ctrl && event.metaKey)` —— Mac ⌘K 之前无效；② quickMenuActions 整段重写贴合 Groza IA：置顶「新增物品 →/ledger?add=1」「AI 新增（拍照识别）→/ledger?ai=1」直达动作（ledger 新增 applyActionQuery：消费参数开抽屉后 router.replace 清 URL），导航项由新 nav 数组自动派生（含配置/管理全组）；③ 创建组空时隐藏分组标题；④ 废弃历史块 cmdk-nav-children（锚点被整段替换覆盖）。ledger.vue 侧实现 ?add/?ai 消费逻辑。
- **手势盘点**（存量功能回归验证）：移动端卡片左滑吸附揭示 −/+/拍照（touch 方向锁，snap -150px）、长按 550ms 进多选（震动反馈）、卡片按钮为同名可见入口（HIG：手势必须有可见替代）。
- **验证**：桌面首批 30 行→滚底 60 行、无分页条；Ctrl+K 与 ⌘K 均开面板、面板直达新增抽屉；左滑吸附/滑出 +1（20→21，测后恢复）/长按多选全过。

### 侧栏收敛：配置+管理合并「系统」+ 页脚用户条（26）
- **合并**：配置（库存架构/选项/标签/分类/结构）与管理（成员/邀请/通知/集合设置/工具）合并为单组「系统」（10 项，数据形态在前、组织管理居中、集合设置/工具殿后）。组序列：概览（1)/库存（2)/进出（3)/系统（10)。
- **「我的」入口下沉**：nav 末尾的「我的」项移除，由页脚用户条承接（用户名即 /profile 链接，当前页高亮 bg-accent）——导航区只留业务，账号区固定底部，消除同目的地双入口。
- **登出按钮换位**：SidebarFooter 的全宽大按钮（折叠态甚至是 destructive 红块）改为 Claude/Codex 式安静页脚——`[头像图标+用户名(→/profile)] [32px 登出小图标]`，登出默认 muted、hover 才显 destructive 色；tooltip/aria 保留（data-testid 不变，旧测试兼容）。
- **实现**：patch_upstream.py nav_body 组名 replace_all（配置/管理→系统）+ 删 profile 项；nav-restructure 幂等 skip 条件改 `group: "系统"`（splice 路径对 pristine 与旧补丁态均成立）；sidebar-footer-user-chip rep 块替换整段 SidebarFooter。
- **验证**：桌面/iPhone 抽屉组标签=[概览,库存,进出,系统]、无「我的」nav 项、系统组 10 项齐、页脚文本=用户名、登出按钮 32×32、点用户条 →/profile。
