#!/usr/bin/env bash
#
# 清除回收站（物理删除）。安全默认：先做一致性快照，再调用 /api/v1/trash2/purge。
#
# 用法:
#   ops/purge.sh                # 清除回收站全部条目（先快照）
#   ops/purge.sh --days 30      # 只清除“标记删除”超过 30 天的
#   ops/purge.sh --ids a,b,c    # 只清除指定 id
#   ops/purge.sh --dry-run      # 只统计将删除多少，不做任何写操作
#
set -euo pipefail

BASE="${HB_URL:-http://127.0.0.1:5037}"
KEYFILE="${HB_KEYFILE:-/home/zhang/.config/homebox/api.key}"
TOKEN="${HB_TOKEN:-$(head -c 300 "$KEYFILE" 2>/dev/null | tr -d '\n\r' || true)}"
DIR="$(cd "$(dirname "$0")" && pwd)"

DAYS=0; IDS=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --days) DAYS="${2:-0}"; shift 2 ;;
    --ids) IDS="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "未知参数 $1" >&2; exit 2 ;;
  esac
done

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m错误:\033[0m %s\n' "$*" >&2; exit 1; }
[ -n "$TOKEN" ] || die "缺少 API token（$KEYFILE 或 HB_TOKEN）"

run_py() { python3 - "$BASE" "$TOKEN" "$DAYS" "$IDS" "$1" <<'PY'
import json, sys, urllib.request, urllib.error, datetime
base, token, days, ids, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
H = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, headers=H, method=method, data=data)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
st, d = call("/api/v1/trash2")
entries = (d.get("entries") or {}) if isinstance(d, dict) else {}
id_list = [x for x in ids.split(",") if x]
cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days) if days > 0 else None
sel = 0
for k, v in entries.items():
    if id_list and k not in id_list:
        continue
    if cutoff:
        ts = (v or {}).get("deletedAt")
        try:
            t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            t = None
        if t and t > cutoff:
            continue
    sel += 1
print(f"  回收站条目: {len(entries)}  将清除: {sel}" + (f"（--days {days}）" if days else ""))
if mode == "dry":
    sys.exit(0)
st, d = call("/api/v1/trash2/purge", "POST", {"confirm": True, "maxAgeDays": days, "ids": id_list})
if st != 200:
    print(f"  清除失败 HTTP {st}: {d}")
    sys.exit(1)
print(f"  已清除: {len(d.get('purged', []))}  剩余: {d.get('remaining')}  错误: {len(d.get('errors', []))}")
for e in (d.get("errors") or [])[:5]:
    print("    -", e)
PY
}

if [ "$DRY" = 1 ]; then
  log "预览（dry-run，不写任何数据）"
  run_py dry
  exit 0
fi

log "清除前先做一致性快照"
"$DIR/backup.sh" || die "快照失败，已中止清除"

log "执行清除"
run_py purge

log "最近审计"
docker exec "${CONTAINER:-homebox}" tail -n 5 /data/audit.log 2>/dev/null || true
log "完成"
