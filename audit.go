package main

// 追加式审计日志：/data/audit.log（每行一条 JSON）。用于追溯关键变更（改字段/入库/标记删除/清除）。
// 设计为“只追加、不修改”，写失败不影响主流程。
//   GET /api/v1/audit?limit=200   查看最近若干条

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
)

const auditPath = "/data/audit.log"

var auditMu sync.Mutex

func auditLog(action string, fields map[string]any) {
	rec := map[string]any{
		"ts":     time.Now().UTC().Format(time.RFC3339Nano),
		"action": action,
	}
	for k, v := range fields {
		rec[k] = v
	}
	b, err := json.Marshal(rec)
	if err != nil {
		return
	}
	b = append(b, '\n')

	auditMu.Lock()
	defer auditMu.Unlock()
	f, err := os.OpenFile(auditPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return
	}
	_, _ = f.Write(b)
	_ = f.Close()
}

func (a *app) handleAuditGet() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		limit := 200
		if v := r.URL.Query().Get("limit"); v != "" {
			if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 5000 {
				limit = n
			}
		}
		out := []json.RawMessage{}
		if data, err := os.ReadFile(auditPath); err == nil {
			lines := strings.Split(strings.TrimRight(string(data), "\n"), "\n")
			if len(lines) > limit {
				lines = lines[len(lines)-limit:]
			}
			for _, ln := range lines {
				ln = strings.TrimSpace(ln)
				if ln == "" || !json.Valid([]byte(ln)) {
					continue
				}
				out = append(out, json.RawMessage(ln))
			}
		}
		return server.JSON(w, http.StatusOK, out)
	}
}
