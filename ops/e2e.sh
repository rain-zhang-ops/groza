#!/usr/bin/env bash
#
# 端到端测试运行器：准备 Playwright(含无头 Chromium 与缺失系统库，无需 root) 后执行 tests/e2e.py。
#   ops/e2e.sh            # 只读 e2e
#   E2E_WRITE=1 ops/e2e.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${E2E_WORK:-$ROOT/build/e2e}"
VENV="$WORK/venv"
SYSROOT="$WORK/sysroot"
LIBS="libatk1.0-0t64 libatk-bridge2.0-0t64 libatspi2.0-0t64 libxdamage1 libxkbcommon0"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
mkdir -p "$WORK"

if [ ! -x "$VENV/bin/playwright" ]; then
  log "创建 venv 并安装 playwright"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q playwright
fi

export PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://cdn.npmmirror.com/binaries/playwright}"
if [ ! -d "$HOME/.cache/ms-playwright"/chromium_headless_shell-* ]; then
  log "下载无头 Chromium（npmmirror）"
  "$VENV/bin/playwright" install chromium-headless-shell
fi

if [ ! -e "$SYSROOT/usr/lib/x86_64-linux-gnu/libatk-1.0.so.0" ]; then
  log "本地解包系统库（无 root）"
  mkdir -p "$WORK/debs"
  ( cd "$WORK/debs"
    for p in $LIBS; do apt-get download "$p" >/dev/null 2>&1 || true; done
    for d in *.deb; do dpkg -x "$d" "$SYSROOT"; done )
fi

export LD_LIBRARY_PATH="$SYSROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
log "运行 tests/e2e.py"
exec "$VENV/bin/python" "$ROOT/tests/e2e.py"
