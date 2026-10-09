package main

// Groza 图片指纹库（pHash）：指纹由浏览器 canvas 算法统一计算后上传，全设备共享，
// 避免每个浏览器各自扫描建索引。
//   GET /api/v1/gx/phashes   当前集合指纹库 {"h":{附件ID:指纹},"o":{附件ID:物品ID},"updatedAt":...}
//   PUT /api/v1/gx/phashes   合并写入（同键保留服务端已有值——同一算法产物；仅追加新键）
// 存储：/data/biz/phashes-<组ID>.json（biz JSON 模式）。

import (
	"encoding/json"
	"io"
	"net/http"
	"sync"
	"time"

	"github.com/hay-kot/httpkit/errchain"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
)

type phashLib struct {
	H         map[string]string `json:"h"`
	O         map[string]string `json:"o"`
	UpdatedAt string            `json:"updatedAt"`
}

var phashMu sync.Mutex

func phashPathFor(gid string) string { return bizDir + "/phashes-" + gid + ".json" }

func phashValidHex(s string) bool {
	if len(s) != 16 && len(s) != 48 {
		return false
	}
	for _, c := range s {
		if (c < '0' || c > '9') && (c < 'a' || c > 'f') {
			return false
		}
	}
	return true
}

func (a *app) handlePhashesGet() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())
		phashMu.Lock()
		var lib phashLib
		bizReadJSON(phashPathFor(ctx.GID.String()), &lib)
		phashMu.Unlock()
		if lib.H == nil {
			lib.H = map[string]string{}
		}
		if lib.O == nil {
			lib.O = map[string]string{}
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		b, _ := json.Marshal(lib)
		_, _ = w.Write(b)
		return nil
	}
}

func (a *app) handlePhashesPut() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())
		var in phashLib
		if err := json.NewDecoder(io.LimitReader(r.Body, 8<<20)).Decode(&in); err != nil {
			http.Error(w, "bad json", http.StatusBadRequest)
			return nil
		}
		phashMu.Lock()
		defer phashMu.Unlock()
		path := phashPathFor(ctx.GID.String())
		var lib phashLib
		bizReadJSON(path, &lib)
		if lib.H == nil {
			lib.H = map[string]string{}
		}
		if lib.O == nil {
			lib.O = map[string]string{}
		}
		added := 0
		for k, v := range in.H {
			if k == "" || !phashValidHex(v) {
				continue
			}
			if _, ok := lib.H[k]; ok {
				continue
			}
			lib.H[k] = v
			if ov := in.O[k]; ov != "" {
				lib.O[k] = ov
			}
			added++
		}
		if added > 0 {
			lib.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
			if err := bizWriteJSON(path, &lib); err != nil {
				return err
			}
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "added": added, "total": len(lib.H)})
		return nil
	}
}
