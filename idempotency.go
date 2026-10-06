package main

// 幂等键支持：客户端（尤其离线队列重放）可为变更请求带 Idempotency-Key 头，
// 服务端记录响应（/data/idem.json，TTL 7 天），重复到达时直接回放，避免重复入库/回滚。

import (
	"encoding/json"
	"net/http"
	"os"
	"sync"
	"time"
)

const idemPath = "/data/idem.json"

var idemTTL = 7 * 24 * time.Hour

type idemEntry struct {
	TS   time.Time       `json:"ts"`
	Body json.RawMessage `json:"body"`
}

var idemMu sync.Mutex

func idemLoad() map[string]idemEntry {
	var m map[string]idemEntry
	if data, err := os.ReadFile(idemPath); err == nil {
		_ = json.Unmarshal(data, &m)
	}
	if m == nil {
		m = map[string]idemEntry{}
	}
	return m
}

func idemSave(m map[string]idemEntry) {
	b, err := json.Marshal(m)
	if err != nil {
		return
	}
	tmp := idemPath + ".tmp"
	if os.WriteFile(tmp, b, 0o644) == nil {
		_ = os.Rename(tmp, idemPath)
	} else {
		_ = os.WriteFile(idemPath, b, 0o644)
	}
}

func idemKey(r *http.Request) string { return r.Header.Get("Idempotency-Key") }

func idemLookup(key string) (json.RawMessage, bool) {
	if key == "" {
		return nil, false
	}
	idemMu.Lock()
	defer idemMu.Unlock()
	e, ok := idemLoad()[key]
	if !ok || time.Since(e.TS) > idemTTL {
		return nil, false
	}
	return e.Body, true
}

func idemStore(key string, v any) {
	if key == "" {
		return
	}
	b, err := json.Marshal(v)
	if err != nil {
		return
	}
	idemMu.Lock()
	defer idemMu.Unlock()
	m := idemLoad()
	now := time.Now()
	for k, e := range m {
		if now.Sub(e.TS) > idemTTL {
			delete(m, k)
		}
	}
	m[key] = idemEntry{TS: now, Body: b}
	idemSave(m)
}

func idemServe(w http.ResponseWriter, body json.RawMessage) error {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Idempotent-Replay", "true")
	_, _ = w.Write(body)
	return nil
}
