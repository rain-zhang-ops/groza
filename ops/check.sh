#!/usr/bin/env bash
#
# 本地静态检查（CI 用）：语法 + gofmt + 补丁可解析。失败返回非 0。
#
set -euo pipefail
cd "$(dirname "$0")/.."
fail=0

echo "== bash -n =="
for f in rebuild.sh ops/*.sh; do
  if bash -n "$f"; then echo "  ok  $f"; else echo "  ERR $f"; fail=1; fi
done

echo "== python 语法 =="
if python3 -m py_compile patches/patch_upstream.py tests/smoke.py; then echo "  ok"; else fail=1; fi

echo "== gofmt =="
bad="$(gofmt -l ./*.go 2>/dev/null || true)"
if [ -n "$bad" ]; then echo "  需格式化: $bad"; fail=1; else echo "  ok"; fi
for f in ./*.go; do gofmt -e "$f" >/dev/null 2>/dev/null || { echo "  语法错误: $f"; fail=1; }; done

echo "== node --check =="
if node --check lib/offline-queue.js; then echo "  ok"; else fail=1; fi

echo "== 定制文件齐全 =="
for f in ledger.vue ui-options.vue intake.vue lib/offline-queue.js ledger_api.go biz.go audit.go idempotency.go metrics.go qr.go ai_recognize.go ui_options.go trash.go patches/patch_upstream.py tests/smoke.py tests/e2e.py; do
  [ -f "$f" ] && echo "  ok  $f" || { echo "  缺失 $f"; fail=1; }
done

if [ "$fail" = 0 ]; then echo "静态检查通过"; else echo "静态检查有失败项" >&2; fi
exit $fail
