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
if python3 -m py_compile patches/patch_upstream.py tests/smoke.py tests/e2e.py ops/migrate/migrate.py; then echo "  ok"; else fail=1; fi

echo "== gofmt =="
bad="$(gofmt -l ./backend/*.go 2>/dev/null || true)"
if [ -n "$bad" ]; then echo "  需格式化: $bad"; fail=1; else echo "  ok"; fi
for f in ./backend/*.go; do gofmt -e "$f" >/dev/null 2>/dev/null || { echo "  语法错误: $f"; fail=1; }; done

echo "== 离线队列 =="
if grep -q "export function useOfflineQueue" frontend/composables/useOfflineQueue.ts; then echo "  ok"; else echo "  ERR useOfflineQueue"; fail=1; fi

echo "== 定制文件齐全 =="
for f in frontend/pages/ledger.vue frontend/pages/intake.vue frontend/pages/intake-records.vue frontend/pages/outbound.vue frontend/pages/outbound-records.vue frontend/pages/tasks.vue frontend/pages/documents.vue frontend/pages/collection/ui-options.vue frontend/pages/collection/fields.vue frontend/composables/useOfflineQueue.ts backend/ledger_api.go backend/biz.go backend/audit.go backend/idempotency.go backend/metrics.go backend/qr.go backend/ai_recognize.go backend/ui_options.go backend/gx_config.go backend/gx_documents.go backend/gx_perms.go backend/gx_adjust.go backend/trash.go frontend/plugins/gx-fetch.client.ts patches/patch_upstream.py tests/smoke.py tests/e2e.py; do
  [ -f "$f" ] && echo "  ok  $f" || { echo "  缺失 $f"; fail=1; }
done

if [ "$fail" = 0 ]; then echo "静态检查通过"; else echo "静态检查有失败项" >&2; fi
exit $fail
