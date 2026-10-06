package main

// 可观测指标：GET /api/v1/metrics（需登录）。用于监控项数、回收站、库大小、审计计数与 Go 运行时。

import (
	"encoding/json"
	"net/http"
	"os"
	"runtime"
	"strings"
	"time"

	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/data/repo"
)

var processStart = time.Now()

func (a *app) handleMetrics() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())

		items := 0
		if res, err := a.repos.Entities.QueryByGroup(ctx, ctx.GID, repo.EntityQuery{Page: -1, PageSize: -1}); err == nil {
			items = res.Total
		}

		var ms runtime.MemStats
		runtime.ReadMemStats(&ms)

		dbBytes := int64(0)
		if st, err := os.Stat("/data/homebox.db"); err == nil {
			dbBytes = st.Size()
		}

		trashCount := 0
		if data, err := os.ReadFile(trashPathV2); err == nil {
			var t trashShape
			if json.Unmarshal(data, &t) == nil {
				trashCount = len(t.Entries)
			}
		}

		auditCounts := map[string]int{}
		auditTotal := 0
		if data, err := os.ReadFile(auditPath); err == nil {
			for _, line := range strings.Split(strings.TrimRight(string(data), "\n"), "\n") {
				line = strings.TrimSpace(line)
				if line == "" {
					continue
				}
				var rec struct {
					Action string `json:"action"`
				}
				if json.Unmarshal([]byte(line), &rec) == nil && rec.Action != "" {
					auditCounts[rec.Action]++
					auditTotal++
				}
			}
		}

		return server.JSON(w, http.StatusOK, map[string]any{
			"uptimeSeconds": int64(time.Since(processStart).Seconds()),
			"items":         items,
			"trash":         trashCount,
			"dbBytes":       dbBytes,
			"auditTotal":    auditTotal,
			"auditCounts":   auditCounts,
			"go": map[string]any{
				"goroutines": runtime.NumGoroutine(),
				"heapMB":     ms.HeapAlloc / 1024 / 1024,
			},
		})
	}
}
