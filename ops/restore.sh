#!/usr/bin/env bash
#
# 从备份恢复数据卷；支持“演练模式”（恢复到临时卷并启动临时容器验证，不动生产）。
#
# 用法:
#   ops/restore.sh --drill [备份文件]     # 演练：默认取最新备份
#   ops/restore.sh [备份文件] --yes       # 真正恢复（会先自动快照当前数据）
#
set -euo pipefail

CONTAINER="${CONTAINER:-homebox}"
VOL="${VOL:-homebox-data}"
DEST="${DEST:-/home/zhang/homebox/backups}"
HELPER="${HELPER:-public.ecr.aws/docker/library/nginx:alpine}"
IMAGE="${IMAGE:-homebox-cn:latest}"
ENVFILE="${ENVFILE:-/home/zhang/.config/homebox/homebox.env}"
PORTMAP="${PORTMAP:-127.0.0.1:5037:7745}"
DRILL_PORT="${DRILL_PORT:-127.0.0.1:5057:7745}"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

FILE=""; DRILL=0; YES=0
for a in "$@"; do
  case "$a" in
    --drill) DRILL=1 ;;
    --yes|-y) YES=1 ;;
    -*) die "未知参数 $a" ;;
    *) FILE="$a" ;;
  esac
done
[ -n "$FILE" ] || FILE="$(ls -1t "$DEST"/homebox-*.tar.gz 2>/dev/null | head -1 || true)"
[ -n "$FILE" ] && [ -f "$FILE" ] || die "找不到备份文件（默认目录 $DEST）"

log "备份文件：$FILE"
gzip -t "$FILE" || die "归档损坏"
TMPC="$(mktemp)"
tar tzf "$FILE" > "$TMPC"
grep -q 'homebox.db' "$TMPC" || { rm -f "$TMPC"; die "归档缺少 homebox.db"; }
tar xzf "$FILE" -O ./homebox.db > "$TMPC" 2>/dev/null || true
grep -q 'SQLite format 3' "$TMPC" || { rm -f "$TMPC"; die "homebox.db 非法"; }
rm -f "$TMPC"

name="$(basename "$FILE")"
dir="$(cd "$(dirname "$FILE")" && pwd)"

if [ "$DRILL" = 1 ]; then
  TV="hb-drill-vol-$$"; TC="hb-drill-$$"
  log "演练：恢复到临时卷 $TV 并启动临时容器验证"
  docker volume create "$TV" >/dev/null
  cleanup() { docker rm -f "$TC" >/dev/null 2>&1 || true; docker volume rm -f "$TV" >/dev/null 2>&1 || true; }
  trap cleanup EXIT
  docker run --rm -v "$TV":/data -v "$dir":/b:ro "$HELPER" sh -c "tar xzf /b/$name -C /data"
  docker run -d --name "$TC" --env-file "$ENVFILE" -p "$DRILL_PORT" -v "$TV":/data "$IMAGE" >/dev/null
  ok=0
  for _ in $(seq 1 30); do
    if docker inspect -f '{{.State.Health.Status}}' "$TC" 2>/dev/null | grep -qx healthy; then ok=1; break; fi
    sleep 3
  done
  if [ "$ok" = 1 ]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5057/api/v1/status || true)"
    log "演练成功：临时实例健康，/api/v1/status -> $code"
    docker exec "$TC" wget -qO- http://localhost:7745/api/v1/status 2>/dev/null | head -c 200 || true
    echo
  else
    die "演练失败：临时实例未健康（备份可能不可用）"
  fi
  exit 0
fi

[ "$YES" = 1 ] || die "真正恢复需显式加 --yes（会覆盖生产数据卷）"
log "先快照当前数据（安全兜底）"
( cd "$(dirname "$0")" && KEEP=90 ./backup.sh ) || die "当前快照失败，已中止"

log "停止并移除容器 $CONTAINER"
docker stop "$CONTAINER" >/dev/null 2>&1 || true
docker rm "$CONTAINER" >/dev/null 2>&1 || true

log "重建数据卷 $VOL 并解包备份"
docker volume rm -f "$VOL" >/dev/null 2>&1 || true
docker volume create "$VOL" >/dev/null
docker run --rm -v "$VOL":/data -v "$dir":/b:ro "$HELPER" sh -c "tar xzf /b/$name -C /data"

log "启动容器 $CONTAINER"
docker run -d --name "$CONTAINER" --restart unless-stopped \
  --env-file "$ENVFILE" -p "$PORTMAP" -v "$VOL":/data "$IMAGE" >/dev/null
for _ in $(seq 1 25); do
  docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null | grep -qx healthy && break
  sleep 3
done
docker ps --filter "name=$CONTAINER" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -sS -o /dev/null -w 'status=%{http_code}\n' -m 8 http://127.0.0.1:5037/api/v1/status || true
log "恢复完成"
