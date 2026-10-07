package main

// Groza 配置中心（sidecar）：读写 gx_config（库存架构配置：位置/属性/媒体/组织）。
//   GET /api/v1/gx/config   返回当前配置（缺省返回内置默认模板）
//   PUT /api/v1/gx/config   保存配置（版本 +1，并写入 gx_config_history）
// 仅访问 gx_ 表，不改动 Homebox 核心数据。

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"

	_ "modernc.org/sqlite"
)

const gxDBPath = "/data/homebox.db"

// 默认模板 = 现状（迁移时也会写入，这里作为兜底）
const defaultGxConfig = `{"version":1,"location":{"dim":"品牌","levels":["品牌"],"shelf":{"enabled":true,"name":"库位","pattern":"^[A-Z]-\\d{1,3}$","unique":false}},"attributes":[],"media":{"cover":"front","maxPerItem":8,"slots":[{"key":"front","name":"正面","required":true},{"key":"back","name":"反面"},{"key":"detail","name":"细节","multiple":true},{"key":"package","name":"包装"}]},"organization":{"tagGroup":{"name":"品类","options":[]},"series":{"enabled":true,"deriveFrom":["name"],"stripParentheses":true},"groupDims":["品牌","尺寸","规格","系列"]}}`

func gxOpen() (*sql.DB, error) {
	db, err := sql.Open("sqlite",
		"file:"+gxDBPath+"?_pragma=busy_timeout(5000)&_pragma=foreign_keys(1)")
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	return db, nil
}

func (a *app) handleGxConfigGet() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		db, err := gxOpen()
		if err != nil {
			return err
		}
		defer db.Close()

		var js string
		err = db.QueryRow(`SELECT json FROM gx_config WHERE id=1`).Scan(&js)
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		if err == sql.ErrNoRows || js == "" {
			_, _ = w.Write([]byte(defaultGxConfig))
			return nil
		}
		if err != nil {
			return validate.NewRequestError(fmt.Errorf("读取配置失败: %w", err), http.StatusInternalServerError)
		}
		_, _ = w.Write([]byte(js))
		return nil
	}
}

func (a *app) handleGxConfigPut() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requireOwner(r); err != nil {
			return err
		}
		body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if err != nil {
			return err
		}
		var probe map[string]json.RawMessage
		if err := json.Unmarshal(body, &probe); err != nil {
			return validate.NewRequestError(fmt.Errorf("配置不是合法 JSON"), http.StatusBadRequest)
		}
		if _, ok := probe["attributes"]; !ok {
			return validate.NewRequestError(fmt.Errorf("配置缺少 attributes"), http.StatusBadRequest)
		}

		db, err := gxOpen()
		if err != nil {
			return err
		}
		defer db.Close()
		tx, err := db.Begin()
		if err != nil {
			return err
		}
		defer func() { _ = tx.Rollback() }()

		var ver int
		_ = tx.QueryRow(`SELECT version FROM gx_config WHERE id=1`).Scan(&ver)
		ver++
		// 归一化：JSON 内嵌 version 以列为准
		var doc map[string]json.RawMessage
		_ = json.Unmarshal(body, &doc)
		if v, err := json.Marshal(ver); err == nil {
			doc["version"] = v
		}
		if norm, err := json.Marshal(doc); err == nil {
			body = norm
		}
		now := time.Now().UTC().Format(time.RFC3339)
		if _, err = tx.Exec(`INSERT INTO gx_config (id,version,json,updated_at) VALUES (1,?,?,?)
			ON CONFLICT(id) DO UPDATE SET version=excluded.version, json=excluded.json, updated_at=excluded.updated_at`,
			ver, string(body), now); err != nil {
			return err
		}
		if _, err = tx.Exec(`INSERT INTO gx_config_history (id,version,json,reason,created_at)
			VALUES (?,?,?,?,?)`, uuid.NewString(), ver, string(body), "api.put", now); err != nil {
			return err
		}
		if err = tx.Commit(); err != nil {
			return err
		}
		return server.JSON(w, http.StatusOK, map[string]any{"version": ver})
	}
}

func (a *app) handleGxConfigHistory() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		db, err := gxOpen()
		if err != nil {
			return err
		}
		defer db.Close()
		rows, err := db.Query(`SELECT version, COALESCE(reason,''), created_at FROM gx_config_history ORDER BY version DESC LIMIT 50`)
		if err != nil {
			return fmt.Errorf("读取配置历史失败: %w", err)
		}
		defer rows.Close()
		type row struct {
			Version   int    `json:"version"`
			Reason    string `json:"reason"`
			CreatedAt string `json:"createdAt"`
		}
		out := make([]row, 0, 16)
		for rows.Next() {
			var x row
			if err := rows.Scan(&x.Version, &x.Reason, &x.CreatedAt); err != nil {
				return err
			}
			out = append(out, x)
		}
		return server.JSON(w, http.StatusOK, map[string]any{"history": out})
	}
}

func (a *app) handleGxConfigRestore() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requireOwner(r); err != nil {
			return err
		}
		var body struct {
			Version int `json:"version"`
		}
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		db, err := gxOpen()
		if err != nil {
			return err
		}
		defer db.Close()
		tx, err := db.Begin()
		if err != nil {
			return err
		}
		defer func() { _ = tx.Rollback() }()

		var prev string
		if err := tx.QueryRow(`SELECT json FROM gx_config_history WHERE version=?`, body.Version).Scan(&prev); err != nil {
			return validate.NewRequestError(fmt.Errorf("版本不存在"), http.StatusNotFound)
		}
		var cur int
		_ = tx.QueryRow(`SELECT version FROM gx_config WHERE id=1`).Scan(&cur)
		newVer := cur + 1
		var doc map[string]json.RawMessage
		_ = json.Unmarshal([]byte(prev), &doc)
		if v, e := json.Marshal(newVer); e == nil {
			doc["version"] = v
		}
		norm, _ := json.Marshal(doc)
		now := time.Now().UTC().Format(time.RFC3339)
		if _, err = tx.Exec(`INSERT INTO gx_config (id,version,json,updated_at) VALUES (1,?,?,?)
			ON CONFLICT(id) DO UPDATE SET version=excluded.version, json=excluded.json, updated_at=excluded.updated_at`,
			newVer, string(norm), now); err != nil {
			return err
		}
		if _, err = tx.Exec(`INSERT INTO gx_config_history (id,version,json,reason,created_at) VALUES (?,?,?,?,?)`,
			uuid.NewString(), newVer, string(norm), fmt.Sprintf("restore v%d", body.Version), now); err != nil {
			return err
		}
		if err = tx.Commit(); err != nil {
			return err
		}
		return server.JSON(w, http.StatusOK, map[string]any{"version": newVer})
	}
}
