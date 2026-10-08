#!/usr/bin/env bash
#
# 重新构建「默认简体中文 + 台账增强」的 Homebox 镜像 homebox-cn:latest
#
# v2: 所有上游源码补丁集中在 patches/patch_upstream.py，锚点失配即中止构建（防静默失效）。
#     后端自定义代码（ledger_api.go / ai_recognize.go / ui_options.go / trash.go）
#     与前端页面（ledger.vue / ui-options.vue）都放在 ~/homebox 下，由本脚本注入。
#
# 用法：
#   ./rebuild.sh                      # 按当前运行容器版本重建
#   ./rebuild.sh v0.27.0              # 指定版本（自动探测对应 commit）
#   ./rebuild.sh v0.27.0 <commit>     # 指定版本和 commit
#
# 依赖：docker、go、node/pnpm(corepack)、curl、unzip、python3
# 说明：GitHub 不可达，源码走腾讯 Go 代理，镜像走南京大学 ghcr 镜像源。
#
set -euo pipefail

# ---------------- 配置 ----------------
HOME_DIR="/home/zhang/homebox"
WORK="$HOME_DIR/build"                 # 构建目录（放在大磁盘，勿用 /tmp）
ENVFILE="/home/zhang/.config/homebox/homebox.env"  # 含 pepper 等环境变量（600 权限）
IMAGE="homebox-cn:latest"
CONTAINER="homebox"
PORTMAP="127.0.0.1:5037:7745"          # Homebox 只对本机开放；对外由 Nginx(5036/443) 提供 HTTPS
HEALTH_URL="http://127.0.0.1:5037"
DATA_VOL="homebox-data"
MIRROR="ghcr.nju.edu.cn"               # 官方镜像国内镜像
GOPROXY_TENCENT="https://mirrors.tencent.com/go"
NPM_REGISTRY="https://registry.npmmirror.com"
GOIMG="public.ecr.aws/docker/library/golang:alpine"

VERSION="${1:-}"
COMMIT="${2:-}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m错误: %s\033[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "缺少 docker"
command -v go     >/dev/null || die "缺少 go"
command -v python3>/dev/null || die "缺少 python3"
export PATH="$HOME/.local/bin:$PATH"
[ -f "$ENVFILE" ] || die "找不到环境变量文件 $ENVFILE"
CUSTOM_FILES="backend/ledger_api.go backend/biz.go backend/audit.go backend/idempotency.go backend/metrics.go backend/qr.go backend/template_sync.go backend/ai_recognize.go backend/ui_options.go backend/gx_config.go backend/gx_documents.go backend/gx_perms.go backend/gx_adjust.go backend/trash.go frontend/pages/ledger.vue frontend/pages/tasks.vue frontend/pages/documents.vue frontend/pages/intake.vue frontend/pages/intake-records.vue frontend/pages/outbound.vue frontend/pages/outbound-records.vue frontend/pages/collection/ui-options.vue frontend/pages/collection/fields.vue frontend/composables/useOfflineQueue.ts frontend/composables/uiClasses.ts frontend/plugins/gx-fetch.client.ts patches/patch_upstream.py"
for f in $CUSTOM_FILES; do
  [ -f "$HOME_DIR/$f" ] || die "缺少定制文件 $HOME_DIR/$f"
done

status_field() { # $1=容器名 $2=字段
  docker exec "$1" wget -qO- http://localhost:7745/api/v1/status 2>/dev/null \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['build']['$2'])" 2>/dev/null || true
}

# ---------------- 备份当前定制文件 ----------------
log "备份定制文件到 backups/"
mkdir -p "$HOME_DIR/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
BK="$HOME_DIR/backups/custom-$STAMP"
mkdir -p "$BK"
for f in $CUSTOM_FILES rebuild.sh; do
  cp -a "$HOME_DIR/$f" "$BK/$(basename $f)" 2>/dev/null || true
done
log "备份完成: $BK"

# ---------------- 版本 / commit ----------------
if [ -z "$VERSION" ]; then
  VERSION="$(docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" && status_field "$CONTAINER" version || true)"
  [ -n "$VERSION" ] || die "无法探测当前版本，请显式传入版本号，例如: $0 v0.26.2"
fi
IMG_TAG="${VERSION#v}"
log "目标版本: $VERSION (镜像 tag: $IMG_TAG)"

if [ -z "$COMMIT" ] && docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  cur="$(status_field "$CONTAINER" version || true)"
  [ "$cur" = "$VERSION" ] && COMMIT="$(status_field "$CONTAINER" commit || true)"
fi

if [ -z "$COMMIT" ]; then
  log "启动官方镜像临时容器以解析 commit"
  docker pull "$MIRROR/sysadminsmedia/homebox:$IMG_TAG" >/dev/null
  docker rm -f hb-commit-probe >/dev/null 2>&1 || true
  docker volume create hb-commit-probe-data >/dev/null
  docker run -d --name hb-commit-probe --env-file "$ENVFILE" \
    -v hb-commit-probe-data:/data "$MIRROR/sysadminsmedia/homebox:$IMG_TAG" >/dev/null
  for _ in $(seq 1 20); do COMMIT="$(status_field hb-commit-probe commit || true)"; [ -n "$COMMIT" ] && break; sleep 2; done
  docker rm -f hb-commit-probe >/dev/null 2>&1 || true
  docker volume rm hb-commit-probe-data >/dev/null 2>&1 || true
fi
[ -n "$COMMIT" ] || die "无法解析 commit，请作为第二个参数传入"
log "commit: $COMMIT"

# ---------------- 源码（后端始终重注入；前端可复用；FRESH=1 全量重下）----------------
export GOPROXY="$GOPROXY_TENCENT" GOTOOLCHAIN=auto GOFLAGS=-mod=mod
mkdir -p "$WORK/gocache" "$WORK/tmp"
cd "$WORK"
REUSE_FE="$WORK/github.com/sysadminsmedia/homebox@$VERSION/frontend"

# 后端：从模块缓存重新取干净源码（保证自定义路由补丁每次都完整应用）
log "注入后端源码（模块缓存）"
mkdir -p resolve && ( cd resolve && go mod init tmp >/dev/null 2>&1 || true )
BE_DIR="$( cd resolve && go mod download -json "github.com/sysadminsmedia/homebox/backend@$COMMIT" )"
BE_DIR="$( printf '%s' "$BE_DIR" | python3 -c 'import sys,json;print(json.load(sys.stdin)["Dir"])' )"
rm -rf backend && cp -r "$BE_DIR" backend && chmod -R u+w backend

# 前端：可复用（含 node_modules）以加速
if [ "${FRESH:-0}" != "1" ] && [ -d "$REUSE_FE" ]; then
  log "复用前端源码与依赖（加速）"
  FE_DIR="$REUSE_FE"
  chmod -R u+w "$FE_DIR" 2>/dev/null || true
else
  log "下载前端源码"
  rm -rf "$WORK/github.com" "$WORK/hb-src.zip" "$WORK/.src-$VERSION-$COMMIT" 2>/dev/null || true
  curl -fsSL "https://mirrors.tencent.com/go/github.com/sysadminsmedia/homebox/@v/$VERSION.zip" -o hb-src.zip
  unzip -q hb-src.zip
  FE_DIR="github.com/sysadminsmedia/homebox@$VERSION/frontend"
  [ -d "$FE_DIR" ] || FE_DIR="$(find . -maxdepth 4 -type d -name frontend | head -1)"
  [ -n "$FE_DIR" ] && [ -d "$FE_DIR" ] || die "未找到 frontend 源码"
  FE_DIR="$PWD/$FE_DIR"
fi

# ---------------- 注入定制文件 ----------------
log "注入定制文件"
cp "$HOME_DIR/backend/ledger_api.go"   "$WORK/backend/app/api/ledger.go"
cp "$HOME_DIR/backend/audit.go"        "$WORK/backend/app/api/audit.go"
cp "$HOME_DIR/backend/idempotency.go"  "$WORK/backend/app/api/idempotency.go"
cp "$HOME_DIR/backend/metrics.go"      "$WORK/backend/app/api/metrics.go"
cp "$HOME_DIR/backend/qr.go"           "$WORK/backend/app/api/qr.go"
cp "$HOME_DIR/backend/template_sync.go" "$WORK/backend/app/api/template_sync.go"
cp "$HOME_DIR/backend/biz.go"          "$WORK/backend/app/api/biz.go"
cp "$HOME_DIR/backend/ai_recognize.go" "$WORK/backend/app/api/ai_recognize.go"
cp "$HOME_DIR/backend/ui_options.go"   "$WORK/backend/app/api/ui_options.go"
cp "$HOME_DIR/backend/gx_config.go"    "$WORK/backend/app/api/gx_config.go"
cp "$HOME_DIR/backend/gx_documents.go" "$WORK/backend/app/api/gx_documents.go"
cp "$HOME_DIR/backend/gx_perms.go"    "$WORK/backend/app/api/gx_perms.go"
cp "$HOME_DIR/backend/gx_adjust.go"   "$WORK/backend/app/api/gx_adjust.go"
cp "$HOME_DIR/backend/trash.go"        "$WORK/backend/app/api/trash.go"
cp "$HOME_DIR/frontend/pages/ledger.vue" "$FE_DIR/pages/ledger.vue"
cp "$HOME_DIR/frontend/pages/intake.vue" "$FE_DIR/pages/intake.vue"
cp "$HOME_DIR/frontend/pages/intake-records.vue" "$FE_DIR/pages/intake-records.vue"
cp "$HOME_DIR/frontend/pages/outbound.vue" "$FE_DIR/pages/outbound.vue"
cp "$HOME_DIR/frontend/pages/outbound-records.vue" "$FE_DIR/pages/outbound-records.vue"
cp "$HOME_DIR/frontend/pages/tasks.vue" "$FE_DIR/pages/tasks.vue"
cp "$HOME_DIR/frontend/pages/documents.vue" "$FE_DIR/pages/documents.vue"
mkdir -p "$FE_DIR/composables"
cp "$HOME_DIR/frontend/composables/useOfflineQueue.ts" "$FE_DIR/composables/useOfflineQueue.ts"
cp "$HOME_DIR/frontend/composables/uiClasses.ts" "$FE_DIR/composables/uiClasses.ts"
cp "$HOME_DIR/frontend/plugins/gx-fetch.client.ts" "$FE_DIR/plugins/gx-fetch.client.ts"
mkdir -p "$FE_DIR/pages/collection/index"
cp "$HOME_DIR/frontend/pages/collection/ui-options.vue" "$FE_DIR/pages/collection/index/ui-options.vue"
rm -f "$FE_DIR/pages/collection/fields.vue"
cp "$HOME_DIR/frontend/pages/collection/fields.vue" "$FE_DIR/pages/collection/index/fields.vue"

# ---------------- 统一补丁（锚点失配即中止）----------------
log "应用统一补丁 patches/patch_upstream.py"
python3 "$HOME_DIR/patches/patch_upstream.py" "$FE_DIR" "$WORK/backend"

# ---------------- 构建前端 ----------------
log "构建前端 (pnpm install + build)"
export npm_config_registry="$NPM_REGISTRY" COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NODE_OPTIONS=--max-old-space-size=2048
( cd "$FE_DIR" && pnpm install --frozen-lockfile )

# Nuxt 4.2.2 app manifest 竞态修复（node_modules 内部补丁，版本升级可能失效 -> 中止）
python3 - "$FE_DIR" <<'PYEOF'
import sys, os, glob, stat
root = sys.argv[1]
cands = []
cands += glob.glob(os.path.join(root, "node_modules/nuxt/dist/app/composables/manifest.js"))
cands += glob.glob(os.path.join(root, "node_modules/.pnpm/nuxt@*/node_modules/nuxt/dist/app/composables/manifest.js"))
if not cands:
    cands = glob.glob(os.path.join(root, "node_modules/**/nuxt/dist/app/composables/manifest.js"), recursive=True)
old = """  manifest.then((m) => {
    matcher = createMatcherFromExport(m.matcher);
  }).catch((e) => {"""
new = """  manifest = manifest.then((m) => {
    matcher = createMatcherFromExport(m.matcher);
    return m;
  }).catch((e) => {"""
hits = 0
for p in cands:
    try:
        s = open(p, encoding="utf-8").read()
    except OSError:
        continue
    if new in s and old not in s:
        hits += 1
        print("already patched:", p)
        continue
    if old in s:
        os.chmod(p, os.stat(p).st_mode | stat.S_IWUSR)
        open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
        hits += 1
        print("patched:", p)
if hits == 0:
    sys.exit("[rebuild] 未找到 nuxt manifest.js 竞态代码，构建中止（版本可能已变）")
PYEOF

( cd "$FE_DIR" && pnpm build )
rm -rf backend/app/api/static/public
cp -r "$FE_DIR/.output/public" backend/app/api/static/public

# ---------------- 编译后端 ----------------
log "编译后端 (Alpine, CGO_ENABLED=0)"
GOMODCACHE="$(go env GOMODCACHE)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$WORK/backend":/src \
  -v "$GOMODCACHE":/go/pkg/mod \
  -v "$WORK/gocache":/cache \
  -v "$WORK/tmp":/tmp \
  -w /src \
  -e HOME=/tmp -e GOCACHE=/cache \
  -e GOPROXY="$GOPROXY_TENCENT" -e GOSUMDB=sum.golang.org \
  -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH=amd64 \
  "$GOIMG" sh -c "go build -ldflags '-s -w -X main.commit=$COMMIT -X main.buildTime=$BUILD_TIME -X main.version=$VERSION' -o /src/api ./app/api/*.go"
[ -x backend/api ] || die "后端编译失败"

# ---------------- 构建镜像（版本化标签，便于回滚）----------------
REL="${VERSION#v}-${COMMIT:0:7}-$(date +%Y%m%d%H%M%S)"
log "构建镜像 $IMAGE（版本标签 homebox-cn:$REL）"
BASE_REF="$MIRROR/sysadminsmedia/homebox:$IMG_TAG"
docker pull "$BASE_REF" >/dev/null 2>&1 || { BASE_REF="$MIRROR/sysadminsmedia/homebox:latest"; docker pull "$BASE_REF" >/dev/null; }
rm -rf img; mkdir -p img; cp backend/api img/api
printf 'FROM %s\nCOPY api /app/api\n' "$BASE_REF" > img/Dockerfile
docker build -t "$IMAGE" -t "homebox-cn:$REL" img
printf '%s\n' "$REL" > "$WORK/.last-release"

# ---------------- 切换容器 ----------------
log "切换容器 $CONTAINER"
docker stop "$CONTAINER" >/dev/null 2>&1 || true
docker rm   "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" --restart unless-stopped \
  --env-file "$ENVFILE" -p "$PORTMAP" -v "$DATA_VOL":/data "$IMAGE"
for _ in $(seq 1 25); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null)" = healthy ] && break
  sleep 3
done
docker ps --filter "name=$CONTAINER" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -sS -I -m 8 "$HEALTH_URL" | head -1

# ---------------- gx_ 领域表（幂等：只建表，不动数据）----------------
if [ -f "$HOME_DIR/ops/migrate/schema_v2.sql" ]; then
  log "确保 gx_ 领域表就绪（建表/补列/回填集合）"
  docker run --rm -v "$DATA_VOL":/data -v "$HOME_DIR/ops/migrate":/mig:ro \
    public.ecr.aws/docker/library/python:3-alpine \
    python /mig/migrate.py --ensure --db /data/homebox.db --data /data \
    || log "警告：gx_ 建表/补列失败（可稍后运行 ops/migrate.sh）"
fi

# ---------------- 冒烟测试（可选）----------------
if [ "${SMOKE:-1}" = "1" ] && [ -x "$HOME_DIR/tests/smoke.py" ]; then
  log "运行冒烟测试 tests/smoke.py"
  python3 "$HOME_DIR/tests/smoke.py" || die "冒烟测试失败（容器保持运行，可手动排查）"
fi

# ---------------- 清理（SMOKE=0 时保留源码目录便于调试）----------------
if [ "${SMOKE:-1}" = "1" ]; then
  log "清理临时文件（保留源码与 node_modules 以加速下次构建；FRESH=1 强制重下）"
  docker rmi "$BASE_REF" >/dev/null 2>&1 || true
  rm -rf "$WORK/resolve" "$WORK/hb-src.zip" "$WORK/img" "$WORK/_wip" 2>/dev/null || true
else
  log "SMOKE=0：保留源码目录不清理"
fi
# 仅保留最近 5 个版本标签镜像（latest 始终保留）
docker images "homebox-cn" --format '{{.Tag}}|{{.CreatedAt}}' \
  | grep -vE '^(latest|<none>)\|' | sort -t'|' -k2 -r \
  | awk -F'|' 'NR>5{print $1}' | while read -r t; do [ -n "$t" ] && docker rmi "homebox-cn:$t" >/dev/null 2>&1 || true; done
docker image prune -f >/dev/null 2>&1 || true

log "完成。镜像 $IMAGE 已上线；版本标签 homebox-cn:$REL（可用 ops/rollback.sh 回滚）。"
