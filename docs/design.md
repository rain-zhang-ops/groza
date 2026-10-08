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
