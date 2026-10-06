#!/usr/bin/env bash
#
# 镜像回滚：把 homebox 容器切到指定版本标签（数据卷不变，仅换镜像）。
#   ops/rollback.sh              # 列出版本标签
#   ops/rollback.sh 0.26.2-e01dd73-20261006234500
#
set -euo pipefail

CONTAINER="${CONTAINER:-homebox}"
ENVFILE="${ENVFILE:-/home/zhang/.config/homebox/homebox.env}"
PORTMAP="${PORTMAP:-127.0.0.1:5037:7745}"
VOL="${VOL:-homebox-data}"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

TAG="${1:-}"
if [ -z "$TAG" ]; then
  echo "可用镜像标签（新→旧）："
  docker images "homebox-cn" --format '{{.Tag}}|{{.CreatedAt}}' \
    | grep -v '<none>' | sort -t'|' -k2 -r | awk -F'|' '{printf "  %-44s %s\n",$1,$2}'
  echo
  echo "用法: ops/rollback.sh <tag>"
  exit 0
fi

IMG="homebox-cn:$TAG"
docker image inspect "$IMG" >/dev/null 2>&1 || die "镜像不存在：$IMG"

cur="$(docker inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || true)"
log "切换：${cur:-无}  ->  $IMG"

docker stop "$CONTAINER" >/dev/null 2>&1 || true
docker rm   "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" --restart unless-stopped \
  --env-file "$ENVFILE" -p "$PORTMAP" -v "$VOL":/data "$IMG" >/dev/null

ok=0
for _ in $(seq 1 25); do
  docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null | grep -qx healthy && { ok=1; break; }
  sleep 3
done

if [ "$ok" = 1 ]; then
  docker tag "$IMG" "homebox-cn:latest"
  log "回滚成功，运行中：$IMG（并已将 :latest 指向它）"
  docker ps --filter "name=$CONTAINER" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
else
  die "切换后未健康；可执行 ops/rollback.sh <其他tag> 再试"
fi
