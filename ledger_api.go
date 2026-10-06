package main

// 台账自定义后端（追加式补丁，不改上游文件）：
//   GET   /api/v1/ledger          聚合接口：物品+字段+缩略图+分类树+标签+选项+回收站，一次返回
//   PATCH /api/v1/ledger/{id}     字段级更新（updatedAt 乐观锁，冲突返回 409）
//   GET   /api/v1/trash2          带删除时间的回收站
//   PUT   /api/v1/trash2          同上（兼容旧 {ids:[...]} 格式）

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/samber/lo"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/data/repo"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
)

// ---------------- 聚合接口 ----------------

type ledgerRowOut struct {
	ID        uuid.UUID              `json:"id"`
	Name      string                 `json:"name"`
	Quantity  float64                `json:"quantity"`
	UpdatedAt time.Time              `json:"updatedAt"`
	Parent    string                 `json:"parent"`
	Thumb     *uuid.UUID             `json:"thumb,omitempty"`
	Tags      []repo.TagSummary      `json:"tags"`
	Fields    []repo.EntityFieldData `json:"fields"`
	Notes     string                 `json:"notes"`
}

type ledgerLocation struct {
	ID   uuid.UUID `json:"id"`
	Name string    `json:"name"`
}

type ledgerUIOptions struct {
	Sizes     []string `json:"sizes"`
	Specs     []string `json:"specs"`
	Colors    []string `json:"colors"`
	Materials []string `json:"materials"`
}

type ledgerOut struct {
	Items      []ledgerRowOut    `json:"items"`
	Locations  []ledgerLocation  `json:"locations"`
	Tags       []repo.TagSummary `json:"tags"`
	UIOptions  ledgerUIOptions   `json:"uiOptions"`
	Trash      trashShape        `json:"trash"`
	TotalPrice float64           `json:"totalPrice"`
}

func (a *app) handleLedgerAggregate() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())

		items, err := a.repos.Entities.QueryByGroup(ctx, ctx.GID, repo.EntityQuery{
			Page:     -1,
			PageSize: -1,
			OrderBy:  "name",
		})
		if err != nil {
			return validate.NewRequestError(fmt.Errorf("查询物品失败: %w", err), http.StatusInternalServerError)
		}

		out := ledgerOut{
			Items:     make([]ledgerRowOut, 0, len(items.Items)),
			UIOptions: ledgerUIOptions{Sizes: []string{}, Specs: []string{}, Colors: []string{}, Materials: []string{}},
			Trash:     trashShape{Entries: map[string]trashEntry{}},
		}

		for _, s := range items.Items {
			row := ledgerRowOut{
				ID:        s.ID,
				Name:      s.Name,
				Quantity:  s.Quantity,
				UpdatedAt: s.UpdatedAt,
				Tags:      s.Tags,
				Fields:    []repo.EntityFieldData{},
			}
			if s.Parent != nil {
				row.Parent = s.Parent.Name
			}
			if s.ImageID != nil {
				row.Thumb = s.ImageID
			} else if s.ThumbnailId != nil {
				row.Thumb = s.ThumbnailId
			}

			full, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, s.ID)
			if err == nil {
				row.Fields = full.Fields
				row.Notes = full.Notes
				for _, att := range full.Attachments {
					if att.Primary {
						id := att.ID
						row.Thumb = &id
						break
					}
				}
			}
			out.Items = append(out.Items, row)
		}

		if tree, err := a.repos.Entities.Tree(ctx, ctx.GID, repo.TreeQuery{}); err == nil {
			var walk func(nodes []*repo.TreeItem)
			walk = func(nodes []*repo.TreeItem) {
				for _, n := range nodes {
					if n == nil {
						continue
					}
					out.Locations = append(out.Locations, ledgerLocation{ID: n.ID, Name: n.Name})
					walk(n.Children)
				}
			}
			walk(lo.Map(tree, func(t repo.TreeItem, _ int) *repo.TreeItem { return &t }))
		}

		if tags, err := a.repos.Tags.GetAll(ctx, ctx.GID); err == nil {
			out.Tags = tags
		}

		if data, err := os.ReadFile(uiOptionsPath); err == nil && json.Valid(data) {
			_ = json.Unmarshal(data, &out.UIOptions)
		}

		if data, err := os.ReadFile(trashPathV2); err == nil && json.Valid(data) {
			_ = json.Unmarshal(data, &out.Trash)
		}
		if out.Trash.Entries == nil {
			out.Trash.Entries = map[string]trashEntry{}
		}

		return server.JSON(w, http.StatusOK, out)
	}
}

// ---------------- 字段级 PATCH（乐观锁） ----------------

type ledgerFieldPatch struct {
	Fields    map[string]any `json:"fields"`
	UpdatedAt *time.Time     `json:"updatedAt,omitempty"`
}

func (a *app) handleLedgerFieldPatch() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		id, err := uuid.Parse(chi.URLParam(r, "id"))
		if err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}

		var body ledgerFieldPatch
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		if len(body.Fields) == 0 {
			return validate.NewRequestError(fmt.Errorf("fields 不能为空"), http.StatusBadRequest)
		}

		ctx := services.NewContext(r.Context())
		full, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, id)
		if err != nil {
			return err
		}

		if body.UpdatedAt != nil && full.UpdatedAt.After(body.UpdatedAt.Add(2*time.Second)) {
			return validate.NewRequestError(fmt.Errorf("该物品已被其他地方修改，请刷新后重试"), http.StatusConflict)
		}

		changed := false
		fields := make([]repo.EntityFieldData, 0, len(full.Fields))
		for _, f := range full.Fields {
			nf := f
			if v, ok := body.Fields[f.Name]; ok {
				switch f.Type {
				case "text":
					s := fmt.Sprintf("%v", v)
					if s != f.TextValue {
						changed = true
					}
					nf.TextValue = s
				case "number":
					n := ledgerToNumber(v)
					if n != f.NumberValue {
						changed = true
					}
					nf.NumberValue = n
				}
			}
			fields = append(fields, nf)
		}

		if !changed {
			return server.JSON(w, http.StatusOK, full)
		}

		upd := repo.EntityUpdate{
			ParentID:     full.Parent.ID,
			ID:           id,
			AssetID:      full.AssetID,
			Name:         full.Name,
			Description:  full.Description,
			Quantity:     full.Quantity,
			Insured:      full.Insured,
			Archived:     full.Archived,
			EntityTypeID: full.EntityType.ID,
			TagIDs:       tagIDsOf(full.Tags),
			Notes:        full.Notes,
			Fields:       fields,
		}
		upd.SyncChildEntityLocations = full.SyncChildEntityLocations

		out, err := a.repos.Entities.UpdateByGroup(ctx, ctx.GID, upd)
		if err != nil {
			return err
		}
		keys := make([]string, 0, len(body.Fields))
		for k := range body.Fields {
			keys = append(keys, k)
		}
		auditLog("ledger.field_patch", map[string]any{"entityId": id.String(), "name": full.Name, "fields": keys})
		return server.JSON(w, http.StatusOK, out)
	}
}

func tagIDsOf(tags []repo.TagSummary) []uuid.UUID {
	ids := make([]uuid.UUID, 0, len(tags))
	for _, t := range tags {
		ids = append(ids, t.ID)
	}
	return ids
}

func ledgerToNumber(v any) int {
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	case string:
		var f float64
		_, _ = fmt.Sscanf(n, "%g", &f)
		return int(f)
	}
	return 0
}

// ---------------- 带时间戳回收站 ----------------

type trashEntry struct {
	DeletedAt time.Time `json:"deletedAt"`
	Name      string    `json:"name,omitempty"`
}

type trashShape struct {
	Entries map[string]trashEntry `json:"entries"`
}

const trashPathV2 = "/data/trash2.json"

func (a *app) handleTrash2Get() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		data, err := os.ReadFile(trashPathV2)
		if err != nil || !json.Valid(data) || len(data) == 0 {
			data = []byte(`{"entries":{}}`)
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = w.Write(data)
		return nil
	}
}

func (a *app) handleTrash2Put() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		var in struct {
			Entries map[string]trashEntry `json:"entries"`
			IDs     []string              `json:"ids"`
		}
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&in); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		out := trashShape{Entries: map[string]trashEntry{}}
		for k, v := range in.Entries {
			if v.DeletedAt.IsZero() {
				v.DeletedAt = time.Now().UTC()
			}
			out.Entries[k] = v
		}
		for _, id := range in.IDs {
			if _, exists := out.Entries[id]; !exists {
				out.Entries[id] = trashEntry{DeletedAt: time.Now().UTC()}
			}
		}
		b, err := json.Marshal(out)
		if err != nil {
			return validate.NewRequestError(err, http.StatusInternalServerError)
		}
		tmp := trashPathV2 + ".tmp"
		if os.WriteFile(tmp, b, 0o644) == nil {
			_ = os.Rename(tmp, trashPathV2)
		} else {
			_ = os.WriteFile(trashPathV2, b, 0o644)
		}
		auditLog("trash2.mark", map[string]any{"marked": len(out.Entries)})
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = w.Write(b)
		return nil
	}
}

// ---------------- 回收站清除（物理删除；必须 confirm） ----------------
// POST /api/v1/trash2/purge
//   { "confirm": true, "ids": ["..."], "maxAgeDays": 30 }
//   只删除「回收站(trash2)」中的条目；可按 ID 显式指定，或按删除时间早于 maxAgeDays 天。
//   调用前应先做一致性快照（ops/purge.sh 已内置）。

func (a *app) handleTrash2Purge() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		var body struct {
			Confirm    bool     `json:"confirm"`
			IDs        []string `json:"ids"`
			MaxAgeDays int      `json:"maxAgeDays"`
		}
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		if !body.Confirm {
			return validate.NewRequestError(fmt.Errorf("需要 confirm:true 才能物理删除"), http.StatusBadRequest)
		}

		entries := trashShape{Entries: map[string]trashEntry{}}
		if data, err := os.ReadFile(trashPathV2); err == nil && json.Valid(data) {
			_ = json.Unmarshal(data, &entries)
			if entries.Entries == nil {
				entries.Entries = map[string]trashEntry{}
			}
		}

		ctx := services.NewContext(r.Context())
		want := map[string]bool{}
		for _, id := range body.IDs {
			want[id] = true
		}
		var cutoff time.Time
		if body.MaxAgeDays > 0 {
			cutoff = time.Now().UTC().AddDate(0, 0, -body.MaxAgeDays)
		}

		purged := []string{}
		errs := []string{}
		for idStr, e := range entries.Entries {
			if len(body.IDs) > 0 && !want[idStr] {
				continue
			}
			if !cutoff.IsZero() && e.DeletedAt.After(cutoff) {
				continue
			}
			id, err := uuid.Parse(idStr)
			if err != nil {
				delete(entries.Entries, idStr)
				errs = append(errs, idStr+": 非法ID")
				continue
			}
			if err := a.repos.Entities.DeleteByGroup(ctx, ctx.GID, id); err != nil {
				errs = append(errs, idStr+": "+err.Error())
				continue
			}
			delete(entries.Entries, idStr)
			purged = append(purged, idStr)
		}

		b, _ := json.MarshalIndent(entries, "", "  ")
		tmp := trashPathV2 + ".tmp"
		if os.WriteFile(tmp, b, 0o644) == nil {
			_ = os.Rename(tmp, trashPathV2)
		} else {
			_ = os.WriteFile(trashPathV2, b, 0o644)
		}

		auditLog("trash2.purge", map[string]any{
			"purged": len(purged), "errors": len(errs),
			"maxAgeDays": body.MaxAgeDays, "explicit": len(body.IDs) > 0,
		})
		return server.JSON(w, http.StatusOK, map[string]any{
			"purged": purged, "errors": errs, "remaining": len(entries.Entries),
		})
	}
}
