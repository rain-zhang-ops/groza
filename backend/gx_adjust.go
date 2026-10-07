package main

// 盘点调整（sidecar）：按实盘数量生成盘盈/盘亏调整单（gx_document kind=adjust）。
//   POST /api/v1/gx/adjust   body: { note, lines:[{itemId,counted}] }
// 逐件：diff = counted - 当前数量；更新库存；写审计与调整单；返回差异报告。

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"github.com/google/uuid"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
)

type gxAdjustLine struct {
	ItemID  string  `json:"itemId"`
	Counted float64 `json:"counted"`
}

type gxAdjustBody struct {
	Note  string         `json:"note"`
	Lines []gxAdjustLine `json:"lines"`
}

func (a *app) handleGxAdjust() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requirePerm(r, "editorCanAdjust", "无盘点权限"); err != nil {
			return err
		}
		var body gxAdjustBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		if len(body.Lines) == 0 {
			return validate.NewRequestError(fmt.Errorf("没有盘点明细"), http.StatusBadRequest)
		}
		ctx := services.NewContext(r.Context())

		type reportRow struct {
			ID       string  `json:"id"`
			Name     string  `json:"name"`
			Expected float64 `json:"expected"`
			Counted  float64 `json:"counted"`
			Diff     float64 `json:"diff"`
		}
		report := make([]reportRow, 0, len(body.Lines))
		docLines := make([]gxDocLine, 0, len(body.Lines))
		var errs []string
		var gain, loss float64

		for _, ln := range body.Lines {
			eid, err := uuid.Parse(ln.ItemID)
			if err != nil {
				errs = append(errs, "明细无效: "+ln.ItemID)
				continue
			}
			full, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, eid)
			if err != nil {
				errs = append(errs, "物品不存在: "+ln.ItemID)
				continue
			}
			expected := full.Quantity
			diff := ln.Counted - expected
			if diff == 0 {
				continue
			}
			upd := entityUpdateFromFull(full)
			upd.Quantity = ln.Counted
			if _, err := a.repos.Entities.UpdateByGroup(ctx, ctx.GID, upd); err != nil {
				errs = append(errs, "更新失败: "+full.Name)
				continue
			}
			if diff > 0 {
				gain += diff
			} else {
				loss += -diff
			}
			report = append(report, reportRow{ID: ln.ItemID, Name: full.Name, Expected: expected, Counted: ln.Counted, Diff: diff})
			docLines = append(docLines, gxDocLine{ItemID: ln.ItemID, Qty: diff, Before: expected, After: ln.Counted})
		}

		code := bizRandID()
		ts := bizNow()
		if len(docLines) > 0 {
			gxRecordDocument("adjust", code, "", body.Note, "posted", ts, docLines)
			auditLog("gx.adjust", map[string]any{"code": code, "items": len(docLines), "gain": gain, "loss": loss})
		}
		return server.JSON(w, http.StatusOK, map[string]any{
			"code": code, "ts": ts, "items": report, "gain": gain, "loss": loss, "errors": errs,
		})
	}
}
