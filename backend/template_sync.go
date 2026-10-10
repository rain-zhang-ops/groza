package main

// 模板字段回填：把模板中的字段（新增/类型）同步到所有物品。
// 仅“补齐缺失字段 + 同步类型”，不删除物品已有字段（避免丢数据）。
// POST /api/v1/ledger/sync-fields

import (
	"net/http"

	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/data/repo"
)

func (a *app) handleLedgerSyncFields() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requireOwner(r); err != nil {
			return err
		}
		ctx := services.NewContext(r.Context())

		type def struct {
			Type string
			Text string
			Num  int
			Bool bool
		}
		defs := map[string]def{}
		var order []string

		tpls, err := a.repos.EntityTemplates.GetAll(ctx, ctx.GID)
		if err != nil {
			return server.JSON(w, http.StatusOK, map[string]any{"updated": 0, "error": err.Error()})
		}
		for _, t := range tpls {
			full, err := a.repos.EntityTemplates.GetOne(ctx, ctx.GID, t.ID)
			if err != nil {
				continue
			}
			for _, f := range full.Fields {
				if f.Name == "" {
					continue
				}
				if _, ok := defs[f.Name]; !ok {
					order = append(order, f.Name)
				}
				defs[f.Name] = def{Type: f.Type, Text: f.TextValue, Num: f.NumberValue, Bool: f.BooleanValue}
			}
		}
		if len(order) == 0 {
			return server.JSON(w, http.StatusOK, map[string]any{"updated": 0, "fields": []string{}})
		}

		items, err := a.repos.Entities.QueryByGroup(ctx, ctx.GID, repo.EntityQuery{Page: -1, PageSize: -1})
		if err != nil {
			return server.JSON(w, http.StatusOK, map[string]any{"updated": 0, "error": err.Error()})
		}

		updated := 0
		for _, s := range items.Items {
			func() { // 闭包 + defer：panic 时实体锁也能释放
				defer lockEntityQty(s.ID)()
				full, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, s.ID)
				if err != nil {
					return
				}
				changed := false
				fields := make([]repo.EntityFieldData, 0, len(full.Fields)+len(order))
				have := map[string]bool{}
				for _, f := range full.Fields {
					have[f.Name] = true
					if d, ok := defs[f.Name]; ok && d.Type != "" && f.Type != d.Type {
						f.Type = d.Type
						changed = true
					}
					fields = append(fields, f)
				}
				for _, name := range order {
					if have[name] {
						continue
					}
					d := defs[name]
					nf := repo.EntityFieldData{Name: name, Type: d.Type}
					switch d.Type {
					case "number":
						nf.NumberValue = d.Num
					case "boolean":
						nf.BooleanValue = d.Bool
					default:
						nf.TextValue = d.Text
					}
					fields = append(fields, nf)
					changed = true
				}
				if !changed {
					return
				}
				upd := entityUpdateFromFull(full)
				upd.Fields = fields
				if _, err := a.repos.Entities.UpdateByGroup(ctx, ctx.GID, upd); err == nil {
					updated++
				}
			}()
		}

		auditLogG(ctx.GID.String(), "ledger.sync_fields", map[string]any{"updated": updated, "fields": len(order)})
		return server.JSON(w, http.StatusOK, map[string]any{"updated": updated, "fields": order})
	}
}
