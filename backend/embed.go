package main

// Groza 多模态向量滤重（阿里云百炼 qwen3-vl-embedding，以图搜图）。
//   POST /api/v1/gx/embed-match              body=图片字节 → {"matches":[{"itemId":"...","score":0.93}...]}
//   POST /api/v1/gx/embed-register?item=&att= body=图片字节 → 登记该附件的向量
//   GET  /api/v1/gx/embed-status             {"total":N,"model":"...","updatedAt":"..."}
// 向量库：/data/biz/embeddings-<组ID>.json（base64(float32le) 按附件 ID 存，另存附件→物品映射）。
// 向量缓存：/data/ai-cache/emb-<模型>-<sha256>.json，同一张图重复计算不调模型、不计费；换模型缓存自动失效。

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
)

const embedEndpoint = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"
const embedDims = 1024

type embedLib struct {
	E         map[string]string `json:"e"` // 附件ID -> base64(float32le)
	O         map[string]string `json:"o"` // 附件ID -> 物品ID
	Model     string            `json:"model"`
	UpdatedAt string            `json:"updatedAt"`
}

var embedMu sync.Mutex

func embedModel() string {
	if m := os.Getenv("HBOX_AI_EMBED_MODEL"); m != "" {
		return m
	}
	return "qwen3-vl-embedding"
}

func embedPathFor(gid string) string { return bizDir + "/embeddings-" + gid + ".json" }

func embedLoad(gid string) *embedLib {
	var lib embedLib
	bizReadJSON(embedPathFor(gid), &lib)
	if lib.E == nil {
		lib.E = map[string]string{}
	}
	if lib.O == nil {
		lib.O = map[string]string{}
	}
	if lib.Model != "" && lib.Model != embedModel() {
		// 模型更换后旧向量不可比，视为空库（由引导流程重建）
		lib.E = map[string]string{}
		lib.O = map[string]string{}
	}
	lib.Model = embedModel()
	return &lib
}

// embedCompute 计算图片向量（带内容哈希+模型缓存）
func embedCompute(body []byte) ([]float32, error) {
	sum := sha256.Sum256(body)
	model := embedModel()
	cachePath := "/data/ai-cache/emb-" + aiSlug(model) + "-" + hex.EncodeToString(sum[:]) + ".json"
	if b, err := os.ReadFile(cachePath); err == nil {
		var v []float32
		if json.Unmarshal(b, &v) == nil && len(v) > 0 {
			return v, nil
		}
	}
	key := aiKey()
	if key == "" {
		return nil, errEmbedNoKey
	}
	dataURL := "data:" + imageMime(body) + ";base64," + base64.StdEncoding.EncodeToString(body)
	m := map[string]any{
		"model": model,
		"input": map[string]any{"contents": []any{map[string]string{"image": dataURL}}},
	}
	if strings.HasPrefix(model, "qwen") {
		// qwen 系支持 dimension；multimodal-embedding-v1 固定 1024 维，传参会 400
		m["parameters"] = map[string]any{"dimension": embedDims}
	}
	reqBody, _ := json.Marshal(m)
	req, err := http.NewRequest("POST", embedEndpoint, bytes.NewReader(reqBody))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")
	resp, err := (&http.Client{Timeout: 60 * time.Second}).Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	rb, _ := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if resp.StatusCode != http.StatusOK {
		return nil, &embedAPIError{status: resp.StatusCode, body: string(rb)}
	}
	vec := parseEmbeddingDash(rb)
	if len(vec) == 0 {
		return nil, &embedAPIError{status: resp.StatusCode, body: "no embedding: " + string(rb[:min(300, len(rb))])}
	}
	_ = os.MkdirAll("/data/ai-cache", 0o755)
	if b, err := json.Marshal(vec); err == nil {
		_ = os.WriteFile(cachePath, b, 0o644)
	}
	return vec, nil
}

// parseEmbeddingDash 解析百炼原生多模态向量响应（output.embeddings[0].embedding）
func parseEmbeddingDash(rb []byte) []float32 {
	var root struct {
		Output struct {
			Embeddings []struct {
				Embedding []float32 `json:"embedding"`
			} `json:"embeddings"`
		} `json:"output"`
	}
	if json.Unmarshal(rb, &root) != nil || len(root.Output.Embeddings) == 0 {
		return nil
	}
	return root.Output.Embeddings[0].Embedding
}

var errEmbedNoKey = &embedAPIError{status: 503, body: "AI 未配置（缺少 HBOX_AI_KEY）"}

type embedAPIError struct {
	status int
	body   string
}

func (e *embedAPIError) Error() string { return e.body }

func embedCosine(a, b []float32) float64 {
	if len(a) == 0 || len(a) != len(b) {
		return 0
	}
	var dot, na, nb float64
	for i := range a {
		x, y := float64(a[i]), float64(b[i])
		dot += x * y
		na += x * x
		nb += y * y
	}
	if na == 0 || nb == 0 {
		return 0
	}
	return dot / (math.Sqrt(na) * math.Sqrt(nb))
}

func embedDecode(s string) []float32 {
	raw, err := base64.StdEncoding.DecodeString(s)
	if err != nil || len(raw)%4 != 0 {
		return nil
	}
	v := make([]float32, len(raw)/4)
	for i := range v {
		v[i] = math.Float32frombits(binary.LittleEndian.Uint32(raw[i*4:]))
	}
	return v
}

func embedEncode(v []float32) string {
	raw := make([]byte, len(v)*4)
	for i, f := range v {
		binary.LittleEndian.PutUint32(raw[i*4:], math.Float32bits(f))
	}
	return base64.StdEncoding.EncodeToString(raw)
}

type embedMatch struct {
	ItemID string  `json:"itemId"`
	Score  float64 `json:"score"`
}

// embedScoreAll 全库打分取 Top-N。alive 非 nil 时只保留仍存在的物品（死物品在截 Top-N 前过滤）。
func embedScoreAll(lib *embedLib, vec []float32, limit int, alive map[string]bool) []embedMatch {
	best := map[string]float64{} // 同一物品多个附件取最高分
	for aid, b64 := range lib.E {
		s := embedCosine(vec, embedDecode(b64))
		item := lib.O[aid]
		if item == "" || s < 0.5 {
			continue
		}
		if alive != nil && !alive[item] {
			continue
		}
		if cur, ok := best[item]; !ok || s > cur {
			best[item] = s
		}
	}
	out := make([]embedMatch, 0, len(best))
	for id, s := range best {
		out = append(out, embedMatch{ItemID: id, Score: math.Round(s*1000) / 1000})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Score > out[j].Score })
	if len(out) > limit {
		out = out[:limit]
	}
	return out
}

// embedLiveItemIDs 查询库中映射的物品哪些仍存在（已删除物品的向量在截 Top-N 前过滤掉）。
// 查询失败返回 nil——调用方按「不过滤」降级，不阻断匹配。
func embedLiveItemIDs(gid string, lib *embedLib) map[string]bool {
	db, err := gxOpen()
	if err != nil {
		return nil
	}
	defer db.Close()
	set := map[string]bool{}
	for _, item := range lib.O {
		set[item] = true
	}
	list := make([]string, 0, len(set))
	for id := range set {
		list = append(list, id)
	}
	alive := map[string]bool{}
	const chunk = 200
	for i := 0; i < len(list); i += chunk {
		part := list[i:min(i+chunk, len(list))]
		q := `SELECT id FROM entities WHERE group_entities=? AND id IN (` + strings.TrimSuffix(strings.Repeat("?,", len(part)), ",") + `)`
		args := make([]any, 0, len(part)+1)
		args = append(args, gid)
		for _, id := range part {
			args = append(args, id)
		}
		rows, err := db.Query(q, args...)
		if err != nil {
			return nil
		}
		for rows.Next() {
			var id string
			if err := rows.Scan(&id); err == nil {
				alive[id] = true
			}
		}
		rows.Close()
	}
	return alive
}

// embedDeleteItem 物品被物理删除后同步清掉它的全部向量（按 O 映射反查附件）。
func embedDeleteItem(gid, itemID string) {
	embedMu.Lock()
	defer embedMu.Unlock()
	lib := embedLoad(gid)
	changed := false
	for aid, oid := range lib.O {
		if oid == itemID {
			delete(lib.O, aid)
			delete(lib.E, aid)
			changed = true
		}
	}
	if changed {
		lib.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
		_ = bizWriteJSON(embedPathFor(gid), lib)
	}
}

func (a *app) handleEmbedMatch() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())
		body, err := io.ReadAll(io.LimitReader(r.Body, 8<<20))
		if err != nil {
			return err
		}
		if len(body) == 0 {
			http.Error(w, "empty image", http.StatusBadRequest)
			return nil
		}
		vec, err := embedCompute(body)
		if err != nil {
			http.Error(w, "向量计算失败: "+err.Error(), http.StatusBadGateway)
			return nil
		}
		embedMu.Lock()
		gid := ctx.GID.String()
		lib := embedLoad(gid)
		matches := embedScoreAll(lib, vec, 5, embedLiveItemIDs(gid, lib))
		embedMu.Unlock()
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_ = json.NewEncoder(w).Encode(map[string]any{"matches": matches})
		return nil
	}
}

func (a *app) handleEmbedRegister() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())
		item := r.URL.Query().Get("item")
		att := r.URL.Query().Get("att")
		if item == "" || att == "" {
			http.Error(w, "need item & att", http.StatusBadRequest)
			return nil
		}
		itemID, err := uuid.Parse(item)
		if err != nil {
			http.Error(w, "bad item id", http.StatusBadRequest)
			return nil
		}
		if _, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, itemID); err != nil {
			http.Error(w, "物品不存在", http.StatusNotFound)
			return nil
		}
		body, err := io.ReadAll(io.LimitReader(r.Body, 8<<20))
		if err != nil {
			return err
		}
		if len(body) == 0 {
			http.Error(w, "empty image", http.StatusBadRequest)
			return nil
		}
		vec, err := embedCompute(body)
		if err != nil {
			http.Error(w, "向量计算失败: "+err.Error(), http.StatusBadGateway)
			return nil
		}
		embedMu.Lock()
		defer embedMu.Unlock()
		gid := ctx.GID.String()
		lib := embedLoad(gid)
		lib.E[att] = embedEncode(vec)
		lib.O[att] = item
		lib.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
		if err := bizWriteJSON(embedPathFor(gid), lib); err != nil {
			return err
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "total": len(lib.E)})
		return nil
	}
}

func (a *app) handleEmbedStatus() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())
		embedMu.Lock()
		lib := embedLoad(ctx.GID.String())
		embedMu.Unlock()
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_ = json.NewEncoder(w).Encode(map[string]any{"total": len(lib.E), "model": lib.Model, "updatedAt": lib.UpdatedAt})
		return nil
	}
}
