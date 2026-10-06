#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Homebox 台账查询 / 筛选（支持按 品牌、尺寸、规格、颜色 多条件 AND 组合）

用法:
  ./homebox-query.py                          # 列出全部物品
  ./homebox-query.py --brand 英瑞克
  ./homebox-query.py --brand "Pukka Pad" --size A4
  ./homebox-query.py --spec "周计划 竖向 碟式活页"
  ./homebox-query.py --brand Happy --q 打孔器
  ./homebox-query.py --html /path/out.html     # 生成可离线筛选的 HTML 快照

API Key 读取顺序: 环境变量 HBOX_API_KEY -> ~/.config/homebox/api.key
地址: 默认 http://127.0.0.1:5036 ，可用 HBOX_URL 覆盖
"""
import argparse, json, os, sys, urllib.request, urllib.error, urllib.parse, html

BASE = os.environ.get("HBOX_URL", "http://127.0.0.1:5036") + "/api/v1"
def load_key():
    k = os.environ.get("HBOX_API_KEY")
    if k: return k.strip()
    p = os.path.expanduser("~/.config/homebox/api.key")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    sys.exit("缺少 API Key：设置 HBOX_API_KEY 或写入 ~/.config/homebox/api.key")

KEY = load_key()

def req(path, params=None):
    url = BASE + path
    if params:
        qs = urllib.parse.urlencode(params, doseq=True)
        url += ("&" if "?" in path else "?") + qs
    r = urllib.request.Request(url)
    r.add_header("Authorization", "Bearer " + KEY)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"请求失败 {path}: {e.code} {e.read().decode()[:200]}")

def list_entities(**params):
    return req("/entities", {"pageSize": 1000, **params}).get("items", [])

def get(eid):
    return req(f"/entities/{eid}")

def field_map(e):
    return {f["name"]: (f.get("textValue") if f["type"] == "text" else f.get("numberValue"))
            for f in e.get("fields", [])}

def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--brand"); ap.add_argument("--size"); ap.add_argument("--spec")
    ap.add_argument("--color"); ap.add_argument("--q", help="名称/关键字文本搜索")
    ap.add_argument("--tag", help="标签名（如品牌）")
    ap.add_argument("--html", help="输出离线可筛选 HTML 到指定文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    # 用后端 fields 过滤（单字段准确）求各条件命中集合，再取交集 => AND
    sets = []
    for name, val in (("品牌", a.brand), ("尺寸", a.size), ("规格", a.spec), ("颜色", a.color)):
        if val:
            ids = {i["id"] for i in list_entities(fields=f"{name}={val}")}
            sets.append(ids)
    if sets:
        match = set.intersection(*sets)
        rows = [get(i) for i in match]
    else:
        rows = [get(i["id"]) for i in list_entities()]

    if a.q:
        rows = [e for e in rows if a.q.lower() in e["name"].lower()]
    if a.tag:
        rows = [e for e in rows if any(t["name"] == a.tag for t in e.get("tags", []))]

    # 排序：品牌 -> 尺寸 -> 名称
    rows.sort(key=lambda e: (field_map(e).get("品牌") or "", field_map(e).get("尺寸") or "", e["name"]))

    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1)); return

    if a.html:
        write_html(rows, a.html); print(f"已生成 {a.html}（{len(rows)} 条）"); return

    # 终端表格
    print(f"命中 {len(rows)} 条\n")
    print(f"{'名称':<34}{'品牌':<10}{'尺寸':<20}{'规格':<30}{'数量':>4}  {'分类':<10}图  ID")
    print("-" * 140)
    for e in rows:
        f = field_map(e)
        img = "Y" if (e.get("imageId") or e.get("thumbnailId")) else "-"
        loc = (e.get("parent") or {}).get("name") or "-"
        print(f"{e['name']:<34}{str(f.get('品牌','')):<10}{str(f.get('尺寸',''))[:18]:<20}"
              f"{str(f.get('规格',''))[:28]:<30}{e['quantity']:>4}  {loc:<10}{img}  {e['id']}")

def write_html(rows, path):
    data = []
    for e in rows:
        f = field_map(e)
        data.append({
            "name": e["name"], "brand": f.get("品牌", ""), "size": f.get("尺寸", ""),
            "spec": f.get("规格", ""), "color": f.get("颜色", ""), "qty": e["quantity"],
            "loc": (e.get("parent") or {}).get("name", ""),
            "img": bool(e.get("imageId") or e.get("thumbnailId")), "id": e["id"],
        })
    payload = json.dumps(data, ensure_ascii=False)
    doc = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>本子台账</title>
<style>
 body{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:16px;color:#222}
 h1{font-size:18px} .bar{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin:12px 0}
 label{display:block;font-size:12px;color:#666} select,input{padding:6px;min-width:150px}
 table{border-collapse:collapse;width:100%;font-size:13px}
 th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}
 th{background:#f5f5f5;cursor:default} tr:hover{background:#fafafa}
 .n{color:#888;font-size:12px}
</style></head><body>
<h1>本子台账（离线快照，可筛选）</h1>
<div class="bar">
 <div><label>品牌</label><select id="brand"><option value="">全部</option></select></div>
 <div><label>尺寸</label><select id="size"><option value="">全部</option></select></div>
 <div><label>规格</label><select id="spec"><option value="">全部</option></select></div>
 <div><label>颜色</label><select id="color"><option value="">全部</option></select></div>
 <div><label>关键字</label><input id="q" placeholder="名称包含..."></div>
 <div><button onclick="reset()">重置</button></div>
</div>
<div class="n" id="cnt"></div>
<table><thead><tr><th>名称</th><th>品牌</th><th>尺寸</th><th>规格</th><th>颜色</th><th>数量</th><th>分类</th><th>图</th><th>ID</th></tr></thead>
<tbody id="tb"></tbody></table>
<script>
const DATA=__DATA__;
const F=["brand","size","spec","color"];
function uniq(k){return [...new Set(DATA.map(d=>d[k]).filter(Boolean))].sort()}
F.forEach(k=>{const s=document.getElementById(k);uniq(k).forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;s.appendChild(o)})});
function render(){
 const g=id=>document.getElementById(id).value;
 const q=g("q").toLowerCase();
 const rows=DATA.filter(d=>F.every(k=>!g(k)||d[k]===g(k)) && (!q||d.name.toLowerCase().includes(q)));
 document.getElementById("cnt").textContent="命中 "+rows.length+" / "+DATA.length+" 条";
 document.getElementById("tb").innerHTML=rows.map(d=>`<tr><td>${d.name}</td><td>${d.brand}</td><td>${d.size}</td><td>${d.spec}</td><td>${d.color||""}</td><td>${d.qty}</td><td>${d.loc}</td><td>${d.img?"Y":"-"}</td><td class="n">${d.id}</td></tr>`).join("");
}
F.concat(["q"]).forEach(k=>document.getElementById(k).addEventListener("input",render));
function reset(){F.concat(["q"]).forEach(k=>document.getElementById(k).value="");render()}
render();
</script></body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc.replace("__DATA__", payload))

if __name__ == "__main__":
    main()
