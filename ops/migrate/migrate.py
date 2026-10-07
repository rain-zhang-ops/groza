#!/usr/bin/env python3
"""
Groza 一次性迁移：Homebox 旧库 + /data JSON -> 新库（Homebox 核心不动，仅加 gx_ 表）

用法:
  migrate.py --db /data/homebox.db --data /data --dry-run   # 预演（不改任何文件）
  migrate.py --db /data/homebox.db --data /data             # 产出 <db>.v2 新库
  migrate.py --verify --db /data/homebox.db --data /data --out <新库>  # 校验新库

原则:
  - 绝不修改源库；目标库 = 源库副本 + gx_* 表（可秒级回滚：保留旧库即可）。
  - 幂等：可重复执行（gx_ 表先清空再重建）。
  - 默认模板 = 现状（template_fields + ui-options + tags）。
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

# 属性名 -> 稳定键（默认模板=现状）
NAME2KEY = {
    "品牌": "brand", "尺寸": "size", "颜色": "color", "规格": "spec",
    "进价": "purchase", "售价": "sell", "页数": "pages", "纸张": "paper",
    "安全库存": "safety", "材质": "material",
}
KEY2TYPE = {  # 冗余列类型（供 ALTER 时使用）
    "brand": "TEXT", "size": "TEXT", "color": "TEXT", "spec": "TEXT",
    "material": "TEXT", "purchase": "REAL", "sell": "REAL",
    "pages": "REAL", "paper": "TEXT", "safety": "REAL",
}
UIOPT_MAP = {"sizes": "尺寸", "specs": "规格", "colors": "颜色", "materials": "材质"}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def die(msg):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# ---------------------------------------------------------------- schema
def apply_schema(t):
    sql_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_v2.sql")
    with open(sql_path, encoding="utf-8") as f:
        t.executescript(f.read())
    # 清空 gx_ 数据表（幂等重跑）
    for tbl in ["gx_audit_log", "gx_document_line", "gx_document",
                "gx_group_config_history", "gx_group_config",
                "gx_idempotency", "gx_ai_cache", "gx_schema_version"]:
        t.execute(f"DELETE FROM {tbl}")
    t.commit()

# 需要按需补充的列（多集合 v3）
NEEDED_COLUMNS = {
    "gx_audit_log": ["group_id"],
    "gx_document": ["group_id"],
    "gx_document_line": ["group_id"],
}

def ensure_schema(t):
    """仅建表/补列（不动数据），用于每次构建幂等确保。"""
    sql_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_v2.sql")
    with open(sql_path, encoding="utf-8") as f:
        t.executescript(f.read())
    for tbl, cols in NEEDED_COLUMNS.items():
        have = {r[1] for r in t.execute(f"PRAGMA table_info({tbl})")}
        for col in cols:
            if col not in have:
                t.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} TEXT")
    # 清理已被取代的陈旧表（数据已在 gx_group_config / 源头，冗余）
    for tbl in ["gx_attribute_option", "gx_attribute_def", "gx_config_history", "gx_config"]:
        t.execute(f"DROP TABLE IF EXISTS {tbl}")
    t.commit()

def backfill_groups(t):
    """把历史 gx 数据归属到当前唯一集合；并（首次）补齐集合配置。"""
    try:
        row = t.execute("SELECT id FROM groups LIMIT 1").fetchone()
        gid = row[0] if row else None
    except Exception:
        gid = None
    if not gid:
        return
    for tbl in ["gx_audit_log", "gx_document", "gx_document_line"]:
        t.execute(f"UPDATE {tbl} SET group_id=? WHERE group_id IS NULL", (gid,))
    t.execute("INSERT OR IGNORE INTO gx_schema_version (version,applied_at) VALUES (3,?)", (now_iso(),))
    t.commit()

# ---------------------------------------------------------------- 属性配置
def build_attr_defs(s, data_dir):
    """template_fields + ui-options -> defs/options/required/冗余列集合"""
    rows = s.execute("SELECT name, type, text_value, number_value, boolean_value "
                     "FROM template_fields ORDER BY created_at, rowid").fetchall()
    if not rows:
        return [], {}, [], []
    uo_path = os.path.join(data_dir, "ui-options.json")
    uo = load_json(uo_path) if os.path.exists(uo_path) else {}
    required = set(uo.get("required", []))
    defs, options, red_keys = [], {}, []
    used = {}
    for i, (name, typ, tv, nv, bv) in enumerate(rows):
        key = NAME2KEY.get(name)
        if key is None or key in used:
            key = next(k for k in [f"f{j}" for j in range(1, 100)] if k not in used)
        used[key] = True
        gtype = {"text": "text", "number": "number", "boolean": "boolean",
                 "date": "date"}.get(typ, "text")
        if gtype == "text" and name in UIOPT_MAP.values():
            gtype = "select"
        defs.append({
            "key": key, "name": name, "type": gtype,
            "required": 1 if name in required else 0,
            "show_column": 1, "filterable": 1, "sortable": 0,
            "unit": "元" if name in ("进价", "售价") else None,
            "sort_order": i, "default_value": tv or None,
            "options_source": "manual",
        })
        if key in KEY2TYPE:
            red_keys.append(key)
        for ukey, uname in UIOPT_MAP.items():
            if uname == name:
                options[key] = [str(v) for v in uo.get(ukey, [])]
    return defs, options, required, red_keys

def build_config_json(defs, options, tags):
    defs_simple = []
    for d in defs:
        item = {k: v for k, v in d.items()}
        item["options"] = options.get(d["key"], [])
        item["required"] = bool(item["required"])
        item["show_column"] = bool(item["show_column"])
        item["filterable"] = bool(item["filterable"])
        item["sortable"] = bool(item["sortable"])
        defs_simple.append(item)
    return {
        "version": 1,
        "location": {"dim": "品牌", "levels": ["品牌"],
                     "shelf": {"enabled": True, "name": "库位",
                               "pattern": "^[A-Z]-\\d{1,3}$", "unique": False}},
        "attributes": defs_simple,
        "media": {"cover": "front", "maxPerItem": 8,
                  "slots": [
                      {"key": "front", "name": "正面", "required": True},
                      {"key": "back", "name": "反面"},
                      {"key": "detail", "name": "细节", "multiple": True},
                      {"key": "package", "name": "包装"}]},
        "organization": {
            "tagGroup": {"name": "品类", "options": tags},
            "series": {"enabled": True, "deriveFrom": ["name"], "stripParentheses": True},
            "groupDims": ["品牌", "尺寸", "规格", "系列"]},
    }

def migrate_config(s, t, data_dir):
    defs, options, required, red_keys = build_attr_defs(s, data_dir)
    tags = [r[0] for r in s.execute("SELECT name FROM tags ORDER BY name")]
    cfg = build_config_json(defs, options, tags)
    row = t.execute("SELECT id FROM groups LIMIT 1").fetchone()
    gid = row[0] if row else ""
    js = json.dumps(cfg, ensure_ascii=False)
    t.execute("INSERT OR REPLACE INTO gx_group_config (group_id,version,json,updated_at)"
              " VALUES (?,1,?,?)", (gid, js, now_iso()))
    t.execute("INSERT INTO gx_group_config_history (id,group_id,version,json,reason,created_at)"
              " VALUES (?,?,1,?,?,?)",
              (str(uuid.uuid4()), gid, js, "migration: 默认模板=现状", now_iso()))
    return defs, red_keys

# ---------------------------------------------------------------- 物品
TYPE_COL = {"text": "text_value", "number": "number_value",
            "boolean": "boolean_value", "date": "time_value"}

def migrate_items(s, t, defs, red_keys, trash_entries):
    meta_cols = [r[1] for r in t.execute("PRAGMA table_info(gx_item_meta)")]
    red_map = {d["name"]: d["key"] for d in defs if d["key"] in red_keys}
    items = s.execute(
        "SELECT e.id, e.serial_number, e.archived, e.updated_at FROM entities e"
        " JOIN entity_types et ON e.entity_type_entities = et.id"
        " WHERE et.is_location = 0").fetchall()
    for eid, serial, archived, updated in items:
        vals, row_attrs = {}, {}
        for name, typ, tv, nv, bv, tm in s.execute(
                "SELECT name,type,text_value,number_value,boolean_value,time_value"
                " FROM entity_fields WHERE entity_fields = ?", (eid,)):
            col = TYPE_COL.get(typ, "text_value")
            raw = {"text_value": tv, "number_value": nv,
                   "boolean_value": bv, "time_value": tm}[col]
            if typ == "boolean":
                raw = bool(raw)
            vals[name] = raw
        for d in defs:
            key = d["key"]
            if d["name"] in vals:
                row_attrs[key] = vals[d["name"]]
        status = "pending_delete" if eid in trash_entries else \
                 ("paused" if archived else "normal")
        t.execute(
            "INSERT INTO gx_item_meta (item_id,shelf,status,version,attributes,updated_at)"
            " VALUES (?,?,?,1,?,?)",
            (eid, serial or None, status, json.dumps(row_attrs, ensure_ascii=False),
             updated or now_iso()))
        upd = {}
        for name, key in red_map.items():
            if key in row_attrs:
                colname = f"attr_{key}"
                if colname in meta_cols:
                    upd[colname] = row_attrs[key]
        if upd:
            t.execute(f"UPDATE gx_item_meta SET {', '.join(f'{k}=?' for k in upd)}"
                      f" WHERE item_id=?", (*upd.values(), eid))
    return len(items)

# ---------------------------------------------------------------- 媒体槽位
def migrate_media(s, t):
    """photos: primary -> 正面(front)，其余 -> 细节(detail)；thumbnails 不动"""
    n_front = n_detail = 0
    for aid, ent, prim in s.execute(
            'SELECT id, entity_attachments, "primary" FROM attachments WHERE type="photo"'):
        slot = "front" if prim else "detail"
        t.execute("UPDATE attachments SET title=? WHERE id=?", (slot, aid))
        if prim:
            n_front += 1
        else:
            n_detail += 1
    return n_front, n_detail

# ---------------------------------------------------------------- 单据
def migrate_documents(s, t, data_dir):
    intakes = load_json(os.path.join(data_dir, "biz", "intakes.json")) \
        if os.path.exists(os.path.join(data_dir, "biz", "intakes.json")) else []
    outbounds = load_json(os.path.join(data_dir, "biz", "outbounds.json")) \
        if os.path.exists(os.path.join(data_dir, "biz", "outbounds.json")) else []
    flows = load_json(os.path.join(data_dir, "biz", "flows.json")) \
        if os.path.exists(os.path.join(data_dir, "biz", "flows.json")) else []
    flow_map = {}
    for f in flows:
        flow_map.setdefault((f.get("intakeId"), f.get("entityId")), []).append(f)

    def flow_for(intake_id, entity_id, positive=True):
        for f in flow_map.get((intake_id, entity_id), []):
            if positive and (f.get("delta") or 0) > 0:
                return f
            if not positive and (f.get("delta") or 0) < 0:
                return f
        return None

    def insert_doc(kind, code, party, note, status, ts, lines, idem):
        doc_id = str(uuid.uuid4())
        t.execute("INSERT INTO gx_document (id,kind,code,party,note,status,created_at,"
                  "posted_at,rolled_back_at,idem_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (doc_id, kind, code, party, note, status, ts,
                   ts if status == "posted" else None,
                   ts if status == "rolled_back" else None, idem))
        for ln in lines:
            t.execute(
                "INSERT INTO gx_document_line (id,document_id,item_id,qty,unit_cost,"
                "unit_price,qty_before,qty_after) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), doc_id, ln["item_id"], ln["qty"], ln.get("cost"),
                 None, ln["before"], ln["after"]))

    n_doc = n_line = 0
    for d in intakes:
        lines = []
        for it in d.get("items", []):
            f = flow_for(d["id"], it["entityId"], positive=True)
            before = f["qtyBefore"] if f else None
            after = f["qtyAfter"] if f else None
            qty = it.get("count", 0) or 0
            if before is None:
                before, after = 0, qty
            lines.append({"item_id": it["entityId"], "qty": qty,
                          "cost": it.get("cost"), "before": before, "after": after})
        insert_doc("intake", d["id"], d.get("supplier"), d.get("note"),
                   "rolled_back" if d.get("rolledBack") else "posted",
                   d.get("ts", now_iso()), lines, f"intake:{d['id']}")
        n_doc += 1; n_line += len(lines)
    for d in outbounds:
        lines = []
        for it in d.get("items", []):
            qty = it.get("count", 0) or 0
            lines.append({"item_id": it["entityId"], "qty": -qty,
                          "before": qty, "after": 0})
        insert_doc("outbound", d["id"], d.get("reason"), None,
                   "rolled_back" if d.get("rolledBack") else "posted",
                   d.get("ts", now_iso()), lines, f"outbound:{d['id']}")
        n_doc += 1; n_line += len(lines)
    for f in flows:  # 收银历史（已废弃功能）→ outbound 历史单据
        if f.get("kind") != "sale":
            continue
        insert_doc("outbound", f.get("id"), "销售",
                   f"遗留收银流水 {f.get('id')}",
                   "rolled_back" if f.get("reversed") else "posted",
                   f.get("ts", now_iso()),
                   [{"item_id": f["entityId"], "qty": -(abs(f.get("delta", 0))),
                     "before": f.get("qtyBefore", 0), "after": f.get("qtyAfter", 0)}],
                   f"outbound:{f.get('id')}")
        n_doc += 1; n_line += 1
    return n_doc, n_line

# ---------------------------------------------------------------- 审计/幂等/缓存/回收站
def migrate_audit(s, t, data_dir):
    path = os.path.join(data_dir, "audit.log")
    n = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                t.execute(
                    "INSERT INTO gx_audit_log (id,ts,actor,action,item_id,document_id,"
                    "changes_json) VALUES (?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), e.get("ts", now_iso()), e.get("actor", ""),
                     e.get("action", ""), e.get("entityId"),
                     e.get("intakeId") or e.get("outboundId"),
                     json.dumps(e, ensure_ascii=False)))
                n += 1
    return n

def migrate_idem(t, data_dir):
    path = os.path.join(data_dir, "idem.json")
    n = 0
    if os.path.exists(path):
        d = load_json(path)
        for k, v in (d.items() if isinstance(d, dict) else []):
            t.execute("INSERT OR IGNORE INTO gx_idempotency (key,ts,response_json)"
                      " VALUES (?,?,?)", (k, now_iso(), json.dumps(v, ensure_ascii=False)))
            n += 1
    return n

def migrate_ai_cache(t, data_dir):
    cache_dir = os.path.join(data_dir, "ai-cache")
    n = 0
    if os.path.isdir(cache_dir):
        for fn in os.listdir(cache_dir):
            if not fn.endswith(".json"):
                continue
            with open(os.path.join(cache_dir, fn), encoding="utf-8", errors="ignore") as f:
                content = f.read()
            t.execute("INSERT OR IGNORE INTO gx_ai_cache (hash,ts,result_json) VALUES (?,?,?)",
                      (fn[:-5], now_iso(), content))
            n += 1
    return n

def migrate_trash(s, t, data_dir):
    path = os.path.join(data_dir, "trash2.json")
    entries = {}
    if os.path.exists(path):
        try:
            entries = load_json(path).get("entries", {})
        except Exception:
            entries = {}
    for eid, info in entries.items():
        t.execute("UPDATE gx_item_meta SET status='pending_delete' WHERE item_id=?", (eid,))
        t.execute("INSERT INTO gx_audit_log (id,ts,actor,action,item_id,changes_json)"
                  " VALUES (?,?,?,?,?,?)",
                  (str(uuid.uuid4()), now_iso(), "", "trash2.mark", eid,
                   json.dumps({"entry": info}, ensure_ascii=False)))
    return len(entries)

# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="源 homebox.db 路径")
    ap.add_argument("--data", help="/data 目录（含 biz/、ui-options.json 等）")
    ap.add_argument("--out", help="目标新库路径（默认 <db>.v2）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--in-place", dest="in_place", action="store_true",
                    help="就地附加迁移到源库（仅新增 gx_ 表）")
    ap.add_argument("--ensure", action="store_true",
                    help="仅建表/补列（不动数据），用于构建时幂等确保")
    a = ap.parse_args()
    if not a.db or not a.data:
        die("需要 --db 与 --data")

    if getattr(a, "ensure", False):
        t = sqlite3.connect(a.db, timeout=30)
        try:
            t.execute("PRAGMA busy_timeout=30000")
            ensure_schema(t)
            backfill_groups(t)
            print("ensure 完成（建表/补列/回填集合）")
        finally:
            t.close()
        return

    if a.verify:
        verify(a)
        return

    # 附加式就地迁移（仅新增 gx_ 表，不改 Homebox 核心表，可回滚=删 gx_ 表）
    if getattr(a, "in_place", False):
        t = sqlite3.connect(a.db, timeout=30)
        t.row_factory = sqlite3.Row
        try:
            t.execute("PRAGMA busy_timeout=30000")
            apply_schema(t)
            defs, red_keys = migrate_config(t, t, a.data)
            trash_entries = {}
            tp = os.path.join(a.data, "trash2.json")
            if os.path.exists(tp):
                try:
                    trash_entries = load_json(tp).get("entries", {})
                except Exception:
                    pass
            rep = {
                "属性定义": len(defs),
                "物品(gx_item_meta)": migrate_items(t, t, defs, red_keys, trash_entries),
                "媒体槽位(front/detail)": migrate_media(t, t),
                "单据/行": migrate_documents(t, t, a.data),
                "审计": migrate_audit(t, t, a.data),
                "幂等": migrate_idem(t, a.data),
                "AI缓存": migrate_ai_cache(t, a.data),
                "回收站": migrate_trash(t, t, a.data),
            }
            t.execute("INSERT INTO gx_schema_version (version,applied_at) VALUES (2,?)",
                      (now_iso(),))
            t.commit()
            backfill_groups(t)
            print(f"就地迁移完成 -> {a.db}")
            for k, v in rep.items():
                print(f"  {k}: {v}")
        finally:
            t.close()
        return

    out = a.out or a.db + ".v2"
    if a.dry_run:
        out = a.db + ".v2.dryrun"
        if os.path.exists(out):
            os.remove(out)
        real_out = a.db + ".v2"
        if os.path.exists(real_out):
            real_out = None
        target = real_out or out
    else:
        target = out

    # 目标 = 源库副本（源库只读、绝不动）
    src = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()

    s = sqlite3.connect(target)
    t = sqlite3.connect(target)
    t.row_factory = sqlite3.Row
    report = {}

    try:
        apply_schema(t)
        defs, red_keys = migrate_config(s, t, a.data)
        report["属性定义"] = len(defs)
        trash_path = os.path.join(a.data, "trash2.json")
        trash_entries = {}
        if os.path.exists(trash_path):
            try:
                trash_entries = load_json(trash_path).get("entries", {})
            except Exception:
                pass
        report["物品(gx_item_meta)"] = migrate_items(s, t, defs, red_keys, trash_entries)
        report["媒体槽位(front/detail)"] = migrate_media(s, t)
        report["单据/行"] = migrate_documents(s, t, a.data)
        report["审计"] = migrate_audit(s, t, a.data)
        report["幂等"] = migrate_idem(t, a.data)
        report["AI缓存"] = migrate_ai_cache(t, a.data)
        report["回收站"] = migrate_trash(s, t, a.data)
        t.execute("INSERT INTO gx_schema_version (version,applied_at) VALUES (2,?)",
                  (now_iso(),))
        t.commit()
        print(f"迁移{'预演' if a.dry_run else '完成'} -> {target}")
        for k, v in report.items():
            print(f"  {k}: {v}")
        if a.dry_run:
            print("提示: dry-run 未保留文件" + ("（目标已存在，未覆盖）" if real_out is None else ""))
    finally:
        t.close(); s.close()
        if a.dry_run:
            try:
                os.remove(target)
            except OSError:
                pass

def verify(a):
    """校验新库（不修改）"""
    out = a.out or a.db + ".v2"
    src = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    t = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
    t.row_factory = sqlite3.Row
    errs = []
    def cmp(what, got, want):
        ok = got == want
        print(f"  [{'OK' if ok else 'FAIL'}] {what}: {got} (期望 {want})")
        if not ok:
            errs.append(what)

    n_items = src.execute("SELECT COUNT(*) FROM entities e JOIN entity_types et"
                          " ON e.entity_type_entities=et.id WHERE et.is_location=0").fetchone()[0]
    cmp("物品数", t.execute("SELECT COUNT(*) FROM gx_item_meta").fetchone()[0], n_items)
    n_photos = src.execute("SELECT COUNT(*) FROM attachments WHERE type='photo'").fetchone()[0]
    n_slot = t.execute("SELECT COUNT(*) FROM attachments WHERE title IN ('front','detail')").fetchone()[0]
    cmp("照片槽位标注", n_slot, n_photos)
    bad = t.execute("SELECT COUNT(*) FROM gx_item_meta WHERE attributes IS NULL OR attributes=''").fetchone()[0]
    cmp("属性 JSON 缺失", bad, 0)
    # JSON 与冗余列抽样一致性
    sample = t.execute("SELECT item_id, attributes, attr_purchase, attr_brand"
                       " FROM gx_item_meta LIMIT 5").fetchall()
    for r in sample:
        attrs = json.loads(r["attributes"])
        if attrs.get("purchase") is not None and abs((attrs["purchase"] or 0) - (r["attr_purchase"] or 0)) > 1e-6:
            errs.append(f"冗余列不一致 {r['item_id']} purchase")
    print(f"  抽样一致性: {'OK' if not any('冗余列' in e for e in errs) else 'FAIL'}")
    if os.path.exists(os.path.join(a.data, "biz", "intakes.json")):
        want = len(load_json(os.path.join(a.data, "biz", "intakes.json"))) + \
               len(load_json(os.path.join(a.data, "biz", "outbounds.json"))) + \
               sum(1 for f in load_json(os.path.join(a.data, "biz", "flows.json"))
                   if f.get("kind") == "sale")
        cmp("单据数", t.execute("SELECT COUNT(*) FROM gx_document").fetchone()[0], want)
    print("  结果:", "全部通过" if not errs else f"失败项: {errs}")
    t.close(); src.close()
    sys.exit(1 if errs else 0)

if __name__ == "__main__":
    main()
