-- =============================================================
-- Groza 领域层 schema v2（Sidecar：仅 gx_ 前缀新表，Homebox 核心表不动）
-- SQLite；执行前先确保：PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;
-- 由 ops/migrate/migrate.py 负责执行与数据搬运。
-- =============================================================

PRAGMA foreign_keys = ON;

-- 迁移版本（幂等升级依据）
CREATE TABLE IF NOT EXISTS gx_schema_version (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

-- ---------- 物品元数据（A1 混合模型：JSON 全量 + 高频字段冗余列） ----------
-- 冗余列随配置动态增删（ALTER TABLE）；下列为「默认模板=现状」的初始集。
CREATE TABLE IF NOT EXISTS gx_item_meta (
  item_id     TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
  shelf       TEXT,                                    -- 库位（可重复，非唯一）
  status      TEXT NOT NULL DEFAULT 'normal'
              CHECK(status IN ('normal','low','soldout','paused','pending_delete')),
  version     INTEGER NOT NULL DEFAULT 1,              -- 乐观锁
  attributes  TEXT NOT NULL DEFAULT '{}',              -- 全量属性 JSON（key=稳定键）
  -- 冗余列（由 gx_config 的 attributes 生成）：
  attr_brand    TEXT,
  attr_size     TEXT,
  attr_spec     TEXT,
  attr_color    TEXT,
  attr_material TEXT,
  attr_purchase REAL,
  attr_sell     REAL,
  attr_pages    REAL,
  attr_paper    TEXT,
  attr_safety   REAL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_gx_meta_shelf   ON gx_item_meta(shelf);
CREATE INDEX IF NOT EXISTS ix_gx_meta_status  ON gx_item_meta(status);
CREATE INDEX IF NOT EXISTS ix_meta_attr_purchase ON gx_item_meta(attr_purchase);
CREATE INDEX IF NOT EXISTS ix_meta_attr_brand    ON gx_item_meta(attr_brand);

-- ---------- 单据（库存变更唯一入口） ----------
CREATE TABLE IF NOT EXISTS gx_document (
  id              TEXT PRIMARY KEY,
  kind            TEXT NOT NULL CHECK(kind IN ('intake','outbound','adjust')),
  code            TEXT,                                -- 单号（原 id 保留）
  party           TEXT,                                -- 供应商 / 去向 / 原因
  note            TEXT,
  status          TEXT NOT NULL DEFAULT 'draft'
                  CHECK(status IN ('draft','posted','rolled_back')),
  created_by      TEXT,
  created_at      TEXT NOT NULL,
  posted_at       TEXT,
  rolled_back_at  TEXT,
  idem_key        TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS gx_document_line (
  id                TEXT PRIMARY KEY,
  document_id       TEXT NOT NULL REFERENCES gx_document(id) ON DELETE CASCADE,
  item_id           TEXT NOT NULL,                     -- 无外键：单据历史须在物品删除后仍可查
  qty               REAL NOT NULL,                     -- intake 正 / outbound 负 / adjust 正负
  unit_cost         REAL,
  unit_price        REAL,
  qty_before        REAL NOT NULL,
  qty_after         REAL NOT NULL,
  price_cost_before REAL, price_cost_after REAL,
  price_sell_before REAL, price_sell_after REAL
);
CREATE INDEX IF NOT EXISTS ix_docline_doc   ON gx_document_line(document_id);
CREATE INDEX IF NOT EXISTS ix_doc_kind_ts   ON gx_document(kind, created_at);

-- ---------- 配置（按集合，v3 起）：group_id 为主键 ----------
CREATE TABLE IF NOT EXISTS gx_group_config (
  group_id   TEXT PRIMARY KEY,
  version    INTEGER NOT NULL,
  json       TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gx_group_config_history (
  id         TEXT PRIMARY KEY,
  group_id   TEXT NOT NULL,
  version    INTEGER NOT NULL,
  json       TEXT NOT NULL,
  reason     TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_gxcfg_hist_grp ON gx_group_config_history(group_id, version DESC);

-- ---------- 审计 / 幂等 / AI 缓存 ----------
CREATE TABLE IF NOT EXISTS gx_audit_log (
  id           TEXT PRIMARY KEY,
  ts           TEXT NOT NULL,
  actor        TEXT,
  action       TEXT NOT NULL,
  item_id      TEXT,
  document_id  TEXT,
  changes_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_item ON gx_audit_log(item_id, ts);
CREATE INDEX IF NOT EXISTS ix_audit_ts   ON gx_audit_log(ts);

CREATE TABLE IF NOT EXISTS gx_idempotency (
  key           TEXT PRIMARY KEY,
  ts            TEXT NOT NULL,
  response_json TEXT
);

CREATE TABLE IF NOT EXISTS gx_ai_cache (
  hash        TEXT PRIMARY KEY,
  ts          TEXT NOT NULL,
  result_json TEXT
);
