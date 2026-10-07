package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/hay-kot/httpkit/errchain"
)

const aiEndpoint = "https://ark.cn-beijing.volces.com/api/v3/responses"

const aiPrompt = `你是文具/笔记本库存录入助手。看这张图片，先用联网搜索尽力匹配出这是哪款商品（品牌/系列/官方名称），再只输出一个 JSON（不要任何多余文字、不要 markdown 代码块）：
{"name":"中文简短名称，优先用图案/系列简称，如 蓝蝴蝶、猫与咖啡、小象","brand":"英瑞克/得力佳/Pukka Pad/Happy/优品胜 之一，否则空","size":"从 A4/A5/A5S/A6/A6L/B5/B6/Micro/Skinny/Classic/Mini 里选，否则空","spec":"从 横线/网格/方格/点阵/Notes笔记本/无日期计划本/有日期计划本 里选，否则空","color":"主要颜色，如 蓝色/粉色，否则空","material":"从 纸/塑料/金属/布/PU 里选，否则空","tag":"书写本/无日期计划本/有日期计划本/贴纸/笔/套盒/拼图 之一，否则空"}
只输出 JSON。`

type aiResp struct {
	Output []struct {
		Type    string `json:"type"`
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
	} `json:"output"`
	OutputText string          `json:"output_text"`
	Error      json.RawMessage `json:"error"`
}

func (a *app) handleAIRecognize() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		key := os.Getenv("HBOX_AI_ARK_KEY")
		model := os.Getenv("HBOX_AI_ARK_MODEL")
		if model == "" {
			model = "doubao-seed-2-1-pro-260628"
		}
		if key == "" {
			http.Error(w, "AI 未配置（缺少 HBOX_AI_ARK_KEY）", http.StatusServiceUnavailable)
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
		search := r.URL.Query().Get("search") == "1" || r.URL.Query().Get("search") == "true"
		// 结果缓存（按图片内容哈希），重复识别不再调用模型/不计费
		sum := sha256.Sum256(body)
		cachePath := "/data/ai-cache/" + hex.EncodeToString(sum[:]) + ".json"
		if b, err := os.ReadFile(cachePath); err == nil && json.Valid(b) {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			_, _ = w.Write(b)
			return nil
		}
		mime := r.Header.Get("Content-Type")
		if mime == "" || !strings.HasPrefix(mime, "image/") {
			mime = "image/jpeg"
		}
		dataURL := "data:" + mime + ";base64," + base64.StdEncoding.EncodeToString(body)

		mk := func(withSearch bool) []byte {
			m := map[string]any{
				"model":    model,
				"thinking": map[string]any{"type": "disabled"},
				"input": []any{map[string]any{"role": "user", "content": []any{
					map[string]any{"type": "input_text", "text": aiPrompt},
					map[string]any{"type": "input_image", "image_url": dataURL},
				}}},
			}
			if withSearch {
				m["tools"] = []any{map[string]any{"type": "web_search"}}
			}
			b, _ := json.Marshal(m)
			return b
		}
		call := func(b []byte) (int, []byte, error) {
			req, err := http.NewRequest("POST", aiEndpoint, bytes.NewReader(b))
			if err != nil {
				return 0, nil, err
			}
			req.Header.Set("Authorization", "Bearer "+key)
			req.Header.Set("Content-Type", "application/json")
			resp, err := (&http.Client{Timeout: 120 * time.Second}).Do(req)
			if err != nil {
				return 0, nil, err
			}
			defer resp.Body.Close()
			rb, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
			return resp.StatusCode, rb, nil
		}
		status, rb, err := call(mk(search))
		if err != nil {
			http.Error(w, "AI 请求失败: "+err.Error(), http.StatusBadGateway)
			return nil
		}
		if search && status != http.StatusOK && bytes.Contains(rb, []byte("ToolNotOpen")) {
			status, rb, err = call(mk(false))
			if err != nil {
				http.Error(w, "AI 请求失败: "+err.Error(), http.StatusBadGateway)
				return nil
			}
		}
		if status != http.StatusOK {
			http.Error(w, "AI 返回错误: "+string(rb), http.StatusBadGateway)
			return nil
		}
		var pr aiResp
		if err := json.Unmarshal(rb, &pr); err != nil {
			http.Error(w, "AI 响应解析失败", http.StatusBadGateway)
			return nil
		}
		text := pr.OutputText
		if text == "" {
			var sb strings.Builder
			for _, o := range pr.Output {
				if o.Type == "message" {
					for _, c := range o.Content {
						sb.WriteString(c.Text)
					}
				}
			}
			text = sb.String()
		}
		start := strings.Index(text, "{")
		end := strings.LastIndex(text, "}")
		out := []byte("{}")
		if start >= 0 && end > start {
			cand := text[start : end+1]
			if json.Valid([]byte(cand)) {
				out = []byte(cand)
			}
		}
		_ = os.MkdirAll("/data/ai-cache", 0o755)
		_ = os.WriteFile(cachePath, out, 0o644)
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = w.Write(out)
		return nil
	}
}
