package main

import (
	"encoding/json"
	"io"
	"net/http"
	"os"

	"github.com/hay-kot/httpkit/errchain"
)

const uiOptionsPath = "/data/ui-options.json"

var defaultUIOptions = []byte(`{"sizes":[],"specs":[],"colors":[],"materials":[]}`)

func (a *app) handleUIOptionsGet() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		data, err := os.ReadFile(uiOptionsPath)
		if err != nil || !json.Valid(data) || len(data) == 0 {
			data = defaultUIOptions
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = w.Write(data)
		return nil
	}
}

func (a *app) handleUIOptionsPut() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requireOwner(r); err != nil {
			return err
		}
		body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if err != nil {
			return err
		}
		if !json.Valid(body) {
			http.Error(w, "invalid json", http.StatusBadRequest)
			return nil
		}
		tmp := uiOptionsPath + ".tmp"
		if err := os.WriteFile(tmp, body, 0o644); err == nil {
			if err := os.Rename(tmp, uiOptionsPath); err == nil {
				w.WriteHeader(http.StatusNoContent)
				return nil
			}
		}
		if err := os.WriteFile(uiOptionsPath, body, 0o644); err != nil {
			return err
		}
		w.WriteHeader(http.StatusNoContent)
		return nil
	}
}
