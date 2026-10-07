package main

// 公开二维码接口（供 <img> 直接引用，无需鉴权）：GET /api/v1/qr?data=...
// 用于给物品 assetId 生成可扫描的二维码标签。

import (
	"io"
	"net/http"

	"github.com/hay-kot/httpkit/errchain"
	"github.com/yeqown/go-qrcode/v2"
	"github.com/yeqown/go-qrcode/writer/standard"
)

func (a *app) handleQRPublic() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		data := r.URL.Query().Get("data")
		if data == "" {
			http.Error(w, "data required", http.StatusBadRequest)
			return nil
		}
		if len(data) > 1000 {
			data = data[:1000]
		}
		qrc, err := qrcode.New(data)
		if err != nil {
			http.Error(w, "qr error", http.StatusBadRequest)
			return nil
		}
		w.Header().Set("Content-Type", "image/png")
		w.Header().Set("Cache-Control", "public, max-age=604800")
		writer := standard.NewWithWriter(struct {
			io.Writer
			io.Closer
		}{w, io.NopCloser(nil)})
		return qrc.Save(writer)
	}
}
