package main

import (
	"encoding/json"
	"io"
	"net/http"
	"os"

	"github.com/hay-kot/httpkit/errchain"
)

// 软删除（仅标记，不真正删除）：把被标记的物品 ID 存到 /data/trash.json
const trashPath = "/data/trash.json"

var defaultTrash = []byte(`{"ids":[]}`)

func (a *app) handleTrashGet() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		data, err := os.ReadFile(trashPath)
		if err != nil || !json.Valid(data) || len(data) == 0 {
			data = defaultTrash
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = w.Write(data)
		return nil
	}
}

func (a *app) handleTrashPut() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if err != nil {
			return err
		}
		var parsed struct {
			IDs []string `json:"ids"`
		}
		if err := json.Unmarshal(body, &parsed); err != nil {
			http.Error(w, "invalid json", http.StatusBadRequest)
			return nil
		}
		out, err := json.Marshal(struct {
			IDs []string `json:"ids"`
		}{IDs: parsed.IDs})
		if err != nil {
			return err
		}
		if err := os.WriteFile(trashPath, out, 0o644); err != nil {
			return err
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = w.Write(out)
		return nil
	}
}
