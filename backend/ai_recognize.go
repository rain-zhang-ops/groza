package main

// Groza AI 识别（阿里云百炼 DashScope，qwen-vl 视觉模型，OpenAI 兼容模式）。
// 结果按 图片内容哈希+模型 缓存到 /data/ai-cache/，重复识别不调模型、不计费；换模型缓存自动失效。

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

const aiEndpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

const aiPrompt = `你是文具/笔记本库存录入助手。看这张图片，先用联网搜索尽力匹配出这是哪款商品（品牌/系列/官方名称），再只输出一个 JSON（不要任何多余文字、不要 markdown 代码块）：
{"name":"中文简短名称，优先用图案/系列简称，如 蓝蝴蝶、猫与咖啡、小象","brand":"英瑞克/得力佳/Pukka Pad/Happy/优品胜 之一，否则空","size":"从 A4/A5/A5S/A6/A6L/B5/B6/Micro/Skinny/Classic/Mini 里选，否则空","spec":"从 横线/网格/方格/点阵/Notes笔记本/无日期计划本/有日期计划本 里选，否则空","color":"主要颜色，如 蓝色/粉色，否则空","material":"从 纸/塑料/金属/布/PU 里选，否则空","tag":"书写本/无日期计划本/有日期计划本/贴纸/笔/套盒/拼图 之一，否则空"}
只输出 JSON。`

func aiKey() string { return os.Getenv("HBOX_AI_KEY") }

func aiModel() string {
	if m := os.Getenv("HBOX_AI_MODEL"); m != "" {
		return m
	}
	return "qwen-vl-max"
}

// aiSlug 模型名转文件名安全串
func aiSlug(model string) string {
	return strings.NewReplacer("/", "_", ":", "_", ".", "_").Replace(model)
}

// imageMime 按魔数嗅探格式：data URI 的 format 段必须与实际编码一致
func imageMime(b []byte) string {
	switch {
	case len(b) >= 8 && bytes.Equal(b[:8], []byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}):
		return "image/png"
	case len(b) >= 12 && bytes.Equal(b[:4], []byte("RIFF")) && bytes.Equal(b[8:12], []byte("WEBP")):
		return "image/webp"
	default:
		return "image/jpeg"
	}
}

// aiContentText 兼容 content 为字符串或分段数组两种形态
func aiContentText(raw json.RawMessage) string {
	var s string
	if json.Unmarshal(raw, &s) == nil {
		return s
	}
	var parts []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	}
	if json.Unmarshal(raw, &parts) != nil {
		return ""
	}
	var sb strings.Builder
	for _, p := range parts {
		sb.WriteString(p.Text)
	}
	return sb.String()
}

func (a *app) handleAIRecognize() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		key := aiKey()
		if key == "" {
			http.Error(w, "AI 未配置（缺少 HBOX_AI_KEY）", http.StatusServiceUnavailable)
			return nil
		}
		model := aiModel()
		body, err := io.ReadAll(io.LimitReader(r.Body, 8<<20))
		if err != nil {
			return err
		}
		if len(body) == 0 {
			http.Error(w, "empty image", http.StatusBadRequest)
			return nil
		}
		search := r.URL.Query().Get("search") == "1" || r.URL.Query().Get("search") == "true"
		sum := sha256.Sum256(body)
		cachePath := "/data/ai-cache/ai-" + aiSlug(model) + "-" + hex.EncodeToString(sum[:]) + ".json"
		if b, err := os.ReadFile(cachePath); err == nil && json.Valid(b) {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			_, _ = w.Write(b)
			return nil
		}
		dataURL := "data:" + imageMime(body) + ";base64," + base64.StdEncoding.EncodeToString(body)

		mk := func(withSearch bool) []byte {
			m := map[string]any{
				"model": model,
				"messages": []any{map[string]any{"role": "user", "content": []any{
					map[string]any{"type": "text", "text": aiPrompt},
					map[string]any{"type": "image_url", "image_url": map[string]string{"url": dataURL}},
				}}},
			}
			if withSearch {
				m["enable_search"] = true
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
		if search && status != http.StatusOK {
			// 模型/参数不支持联网搜索时降级为纯识别重试
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
		var pr struct {
			Choices []struct {
				Message struct {
					Content json.RawMessage `json:"content"`
				} `json:"message"`
			} `json:"choices"`
		}
		if err := json.Unmarshal(rb, &pr); err != nil {
			http.Error(w, "AI 响应解析失败", http.StatusBadGateway)
			return nil
		}
		text := ""
		if len(pr.Choices) > 0 {
			text = aiContentText(pr.Choices[0].Message.Content)
		}
		start := strings.Index(text, "{")
		end := strings.LastIndex(text, "}")
		out := []byte("{}")
		cacheable := false
		if start >= 0 && end > start {
			cand := text[start : end+1]
			if json.Valid([]byte(cand)) {
				var probe map[string]any
				if json.Unmarshal([]byte(cand), &probe) == nil && len(probe) > 0 {
					out = []byte(cand)
					cacheable = true
				}
			}
		}
		if cacheable {
			_ = os.MkdirAll("/data/ai-cache", 0o755)
			_ = os.WriteFile(cachePath, out, 0o644)
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = w.Write(out)
		return nil
	}
}
