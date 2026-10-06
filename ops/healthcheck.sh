#!/usr/bin/env bash
#
# 轻量健康检查：状态接口 + 容器健康 + 数据库文件 + 磁盘水位。失败非 0 退出；
# 可选 HEALTH_WEBHOOK（POST {"text": "..."}，适配钉钉/飞书/Slack 机器人）。
#
set -euo pipefail
BASE="${HB_URL:-http://127.0.0.1:5037}"
CONTAINER="${CONTAINER:-homebox}"
WARN_DISK="${WARN_DISK:-85}"

fail=0; msg=""
code="$(curl -s -o /dev/null -w '%{http_code}' -m 8 "$BASE/api/v1/status" || echo 000)"
[ "$code" = "200" ] || { fail=1; msg="status=$code"; }
hs="$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo unknown)"
[ "$hs" = "healthy" ] || { fail=1; msg="$msg container=$hs"; }
docker exec "$CONTAINER" sh -c 'test -f /data/homebox.db' >/dev/null 2>&1 || { fail=1; msg="$msg db-missing"; }
disk="$(df -P / | awk 'NR==2{print $5}' | tr -d '%')"
[ "${disk:-0}" -lt "$WARN_DISK" ] || { fail=1; msg="$msg disk=${disk}%"; }

ts="$(date '+%F %T')"
if [ "$fail" = 0 ]; then
  echo "$ts OK status=$code container=$hs disk=${disk}%"
  exit 0
fi
line="$ts FAIL$msg"
echo "$line" >&2
if [ -n "${HEALTH_WEBHOOK:-}" ]; then
  curl -s -m 8 -X POST -H 'Content-Type: application/json' \
    -d "{\"text\":\"homebox $line\"}" "$HEALTH_WEBHOOK" >/dev/null 2>&1 || true
fi
exit 1
