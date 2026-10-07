#!/usr/bin/env bash
#
# M0 就地迁移：给运行中的实例附加 gx_ 领域表（仅新增表，不改 Homebox 核心表）。
# 流程：停容器 -> 一致性备份 -> 容器内跑 migrate.py --in-place -> 校验 -> 启动。
# 幂等可重复；回滚 = 删除 gx_ 表 / 从 backups 恢复。
#
#   ops/migrate.sh            # 执行迁移
#   ops/migrate.sh --verify   # 只校验
#
set -euo pipefail

CONTAINER="${CONTAINER:-homebox}"
VOL="${VOL:-homebox-data}"
HELPER="${HELPER:-public.ecr.aws/docker/library/python:3-alpine}"
MIGDIR="$(cd "$(dirname "$0")/migrate" && pwd)"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

run_help() {   # $1 = migrate.py 参数
  docker run --rm -v "$VOL":/data -v "$MIGDIR":/mig:ro "$HELPER" \
    python /mig/migrate.py "$@"
}

if [ "${1:-}" = "--verify" ]; then
  log "校验 gx_ 表"
  run_help --verify --db /data/homebox.db --data /data --out /data/homebox.db
  exit $?
fi

WAS_RUNNING=0
if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo false)" = "true" ]; then
  WAS_RUNNING=1
  log "停止 $CONTAINER（迁移期间无写入）"
  docker stop "$CONTAINER" >/dev/null
fi

log "一致性备份（ops/backup.sh）"
bash "$(dirname "$0")/backup.sh" || die "备份失败，已中止"

log "执行就地迁移"
run_help --in-place --db /data/homebox.db --data /data

log "校验"
run_help --verify --db /data/homebox.db --data /data --out /data/homebox.db

if [ "$WAS_RUNNING" = 1 ]; then
  log "启动 $CONTAINER"
  docker start "$CONTAINER" >/dev/null
fi
log "M0 迁移完成（gx_ 表已就绪）"
