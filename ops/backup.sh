#!/usr/bin/env bash
#
# 一致性备份：暂停 homebox 写入 → 打包整个数据卷 → 恢复写入
# 一致性说明：暂停容器后 SQLite 的 db/-wal/-shm 处于静止状态，打包结果可直接恢复。
#
# 用法:
#   ops/backup.sh                 # 备份并保留最近 30 份
#   KEEP=60 ops/backup.sh         # 自定义保留份数
#   RCLONE_REMOTE=oss:hb-backup ops/backup.sh   # 额外异地同步（需已配置 rclone）
#
set -euo pipefail

CONTAINER="${CONTAINER:-homebox}"
VOL="${VOL:-homebox-data}"
DEST="${DEST:-/home/zhang/homebox/backups}"
HELPER="${HELPER:-public.ecr.aws/docker/library/nginx:alpine}"   # 含 busybox tar/gzip
KEEP="${KEEP:-30}"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "缺少 docker"
docker volume inspect "$VOL" >/dev/null 2>&1 || die "数据卷 $VOL 不存在"
mkdir -p "$DEST"

STAMP="$(date +%Y%m%d-%H%M%S)"
NAME="homebox-$STAMP.tar.gz"
OUT="$DEST/$NAME"
PAUSED=0
resume() { if [ "$PAUSED" = 1 ]; then docker unpause "$CONTAINER" >/dev/null 2>&1 || true; PAUSED=0; fi; }
trap resume EXIT INT TERM

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  log "暂停 $CONTAINER（SQLite 一致性快照）"
  docker pause "$CONTAINER" >/dev/null && PAUSED=1
fi

log "打包数据卷 $VOL -> $OUT"
docker run --rm --entrypoint sh -v "$VOL":/data:ro -v "$DEST":/backup "$HELPER" \
  -c "tar czf /backup/$NAME -C /data ."
resume

log "校验归档"
[ -s "$OUT" ] || die "归档为空"
gzip -t "$OUT" || die "归档损坏（gzip 校验失败）"
TMPC="$(mktemp)"
tar tzf "$OUT" > "$TMPC"
grep -q 'homebox.db' "$TMPC" || { rm -f "$TMPC"; die "归档缺少 homebox.db"; }
tar xzf "$OUT" -O ./homebox.db > "$TMPC" 2>/dev/null || true
if grep -q 'SQLite format 3' "$TMPC"; then
  log "SQLite 头校验通过"
else
  rm -f "$TMPC"; die "homebox.db 不是有效 SQLite 文件（归档可能不一致）"
fi
rm -f "$TMPC"
log "生成成功：$OUT（$(du -h "$OUT" | cut -f1)）"

log "保留最近 $KEEP 份，清理更旧"
ls -1t "$DEST"/homebox-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

if command -v rclone >/dev/null 2>&1 && [ -n "${RCLONE_REMOTE:-}" ]; then
  log "异地同步 -> $RCLONE_REMOTE"
  rclone copy "$OUT" "$RCLONE_REMOTE" && log "异地同步完成"
else
  log "未启用异地：安装 rclone 并设 RCLONE_REMOTE=远端:路径 即生效"
fi

log "完成"
