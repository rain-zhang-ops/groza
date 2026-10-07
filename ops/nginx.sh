#!/usr/bin/env bash
#
# 启动/重建 HTTPS 反向代理容器（homebox-https）。
# 使用 deploy/nginx.conf（80→301、5036/443 HTTPS 反代 127.0.0.1:5037）与证书目录。
#   ops/nginx.sh
#
set -euo pipefail

NAME="${NAME:-homebox-https}"
CONF="${CONF:-/home/zhang/homebox/deploy/nginx.conf}"
CERTS="${CERTS:-/home/zhang/.certs/loomweave}"
IMG="${IMG:-public.ecr.aws/docker/library/nginx:alpine}"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
[ -f "$CONF" ] || { echo "缺少配置 $CONF" >&2; exit 1; }
[ -d "$CERTS" ] || { echo "缺少证书目录 $CERTS" >&2; exit 1; }

log "重建容器 $NAME"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --restart unless-stopped --network host \
  -v "$CONF":/etc/nginx/nginx.conf:ro \
  -v "$CERTS":/etc/nginx/certs:ro \
  "$IMG" >/dev/null
sleep 1
docker exec "$NAME" nginx -t
log "$NAME 已启动"
docker ps --filter "name=$NAME" --format 'table {{.Names}}\t{{.Status}}'
