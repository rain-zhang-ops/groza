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
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
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

// auditLogG 带集合标记的审计（多集合隔离用）。
func auditLogG(gid, action string, fields map[string]any) {
	if fields == nil {
		fields = map[string]any{}
	}
	if gid != "" {
		fields["group"] = gid
	}
	auditLog(action, fields)
}

// auditGroupOK：记录带 group 时必须与当前集合一致；无 group（历史）放行。
func auditGroupOK(line, gid string) bool {
	var rec map[string]any
	if json.Unmarshal([]byte(line), &rec) != nil {
		return true
	}
	if s, ok := rec["group"].(string); ok && s != "" {
		return s == gid
	}
	return true
}

func (a *app) handleAuditGet() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())
		gid := ctx.GID.String()
		limit := 200
		if v := r.URL.Query().Get("limit"); v != "" {
			if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 5000 {
				limit = n
			}
		}
		want := r.URL.Query().Get("entityId")
		var all []string
		if data, err := os.ReadFile(auditPath); err == nil {
			for _, ln := range strings.Split(strings.TrimRight(string(data), "\n"), "\n") {
				ln = strings.TrimSpace(ln)
				if ln == "" || !json.Valid([]byte(ln)) {
					continue
				}
				if !auditGroupOK(ln, gid) {
					continue
				}
				if want != "" && !auditMatches(ln, want) {
					continue
				}
				all = append(all, ln)
			}
		}
		if len(all) > limit {
			all = all[len(all)-limit:]
		}
		out := make([]json.RawMessage, 0, len(all))
		for _, ln := range all {
			out = append(out, json.RawMessage(ln))
		}
		return server.JSON(w, http.StatusOK, out)
	}
}

// auditMatches 判断一条审计记录是否与某实体相关（entityId 字段或 ids/entityIds 数组包含）。
func auditMatches(line, id string) bool {
	var rec map[string]any
	if json.Unmarshal([]byte(line), &rec) != nil {
		return false
	}
	if s, ok := rec["entityId"].(string); ok && s == id {
		return true
	}
	for _, key := range []string{"ids", "entityIds"} {
		if arr, ok := rec[key].([]any); ok {
			for _, v := range arr {
				if s, ok := v.(string); ok && s == id {
					return true
				}
			}
		}
	}
	return false
}
