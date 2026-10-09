package main

// 入库后端 v2（已移除「销售/流水/报表/补货预测」等经营与收银相关接口）：
//   GET  /api/v1/biz/intakes             入库单列表（倒序）
//   POST /api/v1/biz/intake              创建入库单（建单 + 加库存 + 更新进价/售价）
//   POST /api/v1/biz/intake/rollback     回滚入库单（减回库存并清空本次改过的价格，单据标记已回滚）
//   GET  /api/v1/biz/images/{attachment} 无鉴权图片（<img> 用，16位hex附件ID + 可选 /thumb）
// 存储：/data/biz/intakes.json /img_index.json（tmp+rename 原子写）

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/data/repo"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
)

// ---------------- 类型 ----------------

const (
	bizDir        = "/data/biz"
	intakesPath   = bizDir + "/intakes.json"
	outboundsPath = bizDir + "/outbounds.json"
	imgIndexPath  = bizDir + "/img_index.json"
	bizTimeLayout = "2006-01-02T15:04:05.000000"
)

type intakeItem struct {
	EntityID string  `json:"entityId"`
	Name     string  `json:"name,omitempty"`
	Count    float64 `json:"count"`
	Cost     float64 `json:"cost,omitempty"`
	Sell     float64 `json:"sell,omitempty"`
	PrevCost int     `json:"prevCost,omitempty"`
	HadCost  bool    `json:"hadCost,omitempty"`
	PrevSell int     `json:"prevSell,omitempty"`
	HadSell  bool    `json:"hadSell,omitempty"`
}

type intake struct {
	ID         string       `json:"id"`
	TS         string       `json:"ts"`
	Supplier   string       `json:"supplier,omitempty"`
	Note       string       `json:"note,omitempty"`
	Items      []intakeItem `json:"items"`
	TotalCost  float64      `json:"totalCost"`
	RolledBack bool         `json:"rolledBack,omitempty"`
}

// ---------------- 存储 ----------------

func bizNow() string { return time.Now().Format(bizTimeLayout) }

func bizRandID() string {
	const cs = "abcdefghijklmnopqrstuvwxyz0123456789"
	b := make([]byte, 10)
	for i := range b {
		b[i] = cs[rand.Intn(len(cs))]
	}
	return string(b)
}

func bizReadJSON(path string, v any) bool {
	data, err := os.ReadFile(path)
	if err != nil || len(data) == 0 {
		return false
	}
	return json.Unmarshal(data, v) == nil
}

func bizWriteJSON(path string, v any) error {
	b, err := json.Marshal(v)
	if err != nil {
		return err
	}
	_ = os.MkdirAll(filepath.Dir(path), 0o755)
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, 0o644); err == nil {
		if err := os.Rename(tmp, path); err == nil {
			return nil
		}
	}
	return os.WriteFile(path, b, 0o644)
}

func loadIntakes() []intake {
	var is []intake
	bizReadJSON(intakesPath, &is)
	return is
}

func saveIntakes(is []intake) error { return bizWriteJSON(intakesPath, is) }

// ---------------- 工具 ----------------

func uuidToHex(id uuid.UUID) string { return hex.EncodeToString(id[:]) }

// imgFromAttachments 记录物品主图到图片索引，返回可用的公开图片 URL（供 <img> 使用）。
func (a *app) imgFromAttachments(ctx context.Context, gid, eid uuid.UUID) string {
	full, err := a.repos.Entities.GetOneByGroup(ctx, gid, eid)
	if err != nil {
		return ""
	}
	var chosen *repo.ItemAttachment
	for i := range full.Attachments {
		if full.Attachments[i].Primary {
			chosen = &full.Attachments[i]
			break
		}
	}
	if chosen == nil && len(full.Attachments) > 0 {
		chosen = &full.Attachments[0]
	}
	if chosen == nil {
		return ""
	}
	rel := strings.TrimPrefix(strings.TrimPrefix(filepath.ToSlash(chosen.Path), "file:///"), "/")
	_ = os.MkdirAll(filepath.Dir(imgIndexPath), 0o755)
	var idx map[string]string
	bizReadJSON(imgIndexPath, &idx)
	if idx == nil {
		idx = map[string]string{}
	}
	idx[uuidToHex(chosen.ID)] = rel
	_ = bizWriteJSON(imgIndexPath, idx)
	return "/api/v1/biz/images/" + uuidToHex(chosen.ID)
}

func entityUpdateFromFull(full repo.EntityOut) repo.EntityUpdate {
	upd := repo.EntityUpdate{
		ParentID:     full.Parent.ID,
		ID:           full.ID,
		AssetID:      full.AssetID,
		Name:         full.Name,
		Description:  full.Description,
		Quantity:     full.Quantity,
		Insured:      full.Insured,
		Archived:     full.Archived,
		EntityTypeID: full.EntityType.ID,
		TagIDs:       tagIDsOf(full.Tags),
		Notes:        full.Notes,
		Fields:       full.Fields,
	}
	upd.SyncChildEntityLocations = full.SyncChildEntityLocations
	return upd
}

// ---------------- 入库单列表 ----------------

func (a *app) handleBizIntakes() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		is := loadIntakes()
		if is == nil {
			is = []intake{}
		}
		return server.JSON(w, http.StatusOK, is)
	}
}

// ---------------- 入库单创建 ----------------

type intakeBody struct {
	Supplier string       `json:"supplier"`
	Note     string       `json:"note"`
	Items    []intakeItem `json:"items"`
}

func (a *app) handleBizIntakeCreate() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requirePerm(r, "editorCanIntake", "无入库权限"); err != nil {
			return err
		}
		var body intakeBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		if len(body.Items) == 0 {
			return validate.NewRequestError(fmt.Errorf("没有入库明细"), http.StatusBadRequest)
		}
		key := idemKey(r)
		if cached, ok := idemLookup(key); ok {
			return idemServe(w, cached)
		}

		ctx := services.NewContext(r.Context())
		ii := &intake{
			ID:       bizRandID(),
			TS:       bizNow(),
			Supplier: strings.TrimSpace(body.Supplier),
			Note:     strings.TrimSpace(body.Note),
		}
		var errs []string

		for _, it := range body.Items {
			eid, err := uuid.Parse(it.EntityID)
			if err != nil || it.Count <= 0 {
				errs = append(errs, "明细无效: "+it.EntityID)
				continue
			}
			full, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, eid)
			if err != nil {
				errs = append(errs, "物品不存在: "+it.EntityID)
				continue
			}
			newQty := full.Quantity + it.Count
			upd := entityUpdateFromFull(full)
			upd.Quantity = newQty
			prevCost, prevSell := 0, 0
			hadCost, hadSell := false, false
			if it.Cost > 0 || it.Sell > 0 {
				nf := make([]repo.EntityFieldData, 0, len(full.Fields))
				for _, f := range full.Fields {
					if f.Type == "number" {
						if f.Name == "进价" && it.Cost > 0 {
							prevCost, hadCost = f.NumberValue, true
							f.NumberValue = int(it.Cost)
						} else if f.Name == "售价" && it.Sell > 0 {
							prevSell, hadSell = f.NumberValue, true
							f.NumberValue = int(it.Sell)
						}
					}
					nf = append(nf, f)
				}
				upd.Fields = nf
			}
			if _, err := a.repos.Entities.UpdateByGroup(ctx, ctx.GID, upd); err != nil {
				errs = append(errs, "更新失败: "+full.Name)
				continue
			}
			ii.Items = append(ii.Items, intakeItem{
				EntityID: it.EntityID, Name: full.Name, Count: it.Count, Cost: it.Cost, Sell: it.Sell,
				PrevCost: prevCost, HadCost: hadCost, PrevSell: prevSell, HadSell: hadSell,
			})
			ii.TotalCost += it.Cost * it.Count
		}

		if len(ii.Items) == 0 {
			return validate.NewRequestError(fmt.Errorf("没有成功入库的明细：%s", strings.Join(errs, "；")), http.StatusBadRequest)
		}

		is := loadIntakes()
		is = append([]intake{*ii}, is...)
		if err := saveIntakes(is); err != nil {
			return validate.NewRequestError(err, http.StatusInternalServerError)
		}
		eids := make([]string, 0, len(ii.Items))
		for _, it := range ii.Items {
			eids = append(eids, it.EntityID)
		}
		auditLogG(ctx.GID.String(), "intake.create", map[string]any{"intakeId": ii.ID, "items": len(ii.Items), "supplier": ii.Supplier, "entityIds": eids})
		{
			lines := make([]gxDocLine, 0, len(ii.Items))
			for _, it := range ii.Items {
				lines = append(lines, gxDocLine{ItemID: it.EntityID, Qty: float64(it.Count), UnitCost: float64(it.Cost)})
			}
			gxRecordDocumentLogged(ctx.GID.String(), "intake", ii.ID, ii.Supplier, ii.Note, "posted", ii.TS, lines)
		}
		resp := map[string]any{"intake": ii, "errors": errs}
		idemStore(key, resp)
		return server.JSON(w, http.StatusOK, resp)
	}
}

// ---------------- 入库单回滚 ----------------

type intakeRollbackBody struct {
	IntakeID string `json:"intakeId"`
}

func (a *app) handleBizIntakeRollback() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requireOwner(r); err != nil {
			return err
		}
		var body intakeRollbackBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		key := idemKey(r)
		if cached, ok := idemLookup(key); ok {
			return idemServe(w, cached)
		}
		is := loadIntakes()
		idx := -1
		for i, v := range is {
			if v.ID == body.IntakeID {
				idx = i
				break
			}
		}
		if idx < 0 {
			return validate.NewRequestError(fmt.Errorf("入库单不存在"), http.StatusNotFound)
		}
		t := is[idx]
		if t.RolledBack {
			return validate.NewRequestError(fmt.Errorf("该入库单已回滚"), http.StatusConflict)
		}

		ctx := services.NewContext(r.Context())
		var errs []string
		for _, it := range t.Items {
			eid, err := uuid.Parse(it.EntityID)
			if err != nil {
				continue
			}
			full, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, eid)
			if err != nil {
				errs = append(errs, "物品不存在，跳过: "+it.Name)
				continue
			}
			newQty := full.Quantity - it.Count
			if newQty < 0 {
				newQty = 0
			}
			upd := entityUpdateFromFull(full)
			upd.Quantity = newQty
			if it.HadCost || it.HadSell {
				nf := make([]repo.EntityFieldData, 0, len(full.Fields))
				for _, f := range full.Fields {
					if f.Type == "number" {
						if f.Name == "进价" && it.HadCost {
							f.NumberValue = it.PrevCost
						} else if f.Name == "售价" && it.HadSell {
							f.NumberValue = it.PrevSell
						}
					}
					nf = append(nf, f)
				}
				upd.Fields = nf
			}
			if _, err := a.repos.Entities.UpdateByGroup(ctx, ctx.GID, upd); err != nil {
				errs = append(errs, "更新失败: "+it.Name)
				continue
			}
		}
		t.RolledBack = true
		is[idx] = t
		if err := saveIntakes(is); err != nil {
			return validate.NewRequestError(err, http.StatusInternalServerError)
		}
		eids := make([]string, 0, len(t.Items))
		for _, it := range t.Items {
			eids = append(eids, it.EntityID)
		}
		auditLogG(ctx.GID.String(), "intake.rollback", map[string]any{"intakeId": t.ID, "items": len(t.Items), "entityIds": eids})
		gxMarkRolledBack(ctx.GID.String(), "intake", t.ID)
		resp := map[string]any{"intake": t, "errors": errs}
		idemStore(key, resp)
		return server.JSON(w, http.StatusOK, resp)
	}
}

// ---------------- 无鉴权图片（<img> 用）----------------

func streamAttachmentFile(w http.ResponseWriter, r *http.Request, fullPath string) error {
	f, err := os.Open(fullPath)
	if err != nil {
		return validate.NewRequestError(err, http.StatusNotFound)
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return validate.NewRequestError(err, http.StatusNotFound)
	}
	if strings.HasSuffix(fullPath, ".webp") {
		w.Header().Set("Content-Type", "image/webp")
	} else if strings.HasSuffix(fullPath, ".png") {
		w.Header().Set("Content-Type", "image/png")
	} else {
		w.Header().Set("Content-Type", "image/jpeg")
	}
	w.Header().Set("Cache-Control", "public, max-age=604800")
	w.Header().Set("Content-Length", fmt.Sprint(st.Size()))
	_, _ = io.Copy(w, f)
	return nil
}

func (a *app) handleBizImage() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		hexID := chi.URLParam(r, "attachment")
		wantThumb := chi.URLParam(r, "thumb") == "thumb"

		var idx map[string]string
		if !bizReadJSON(imgIndexPath, &idx) {
			return validate.NewRequestError(fmt.Errorf("no index"), http.StatusNotFound)
		}
		rel, ok := idx[hexID]
		if !ok {
			return validate.NewRequestError(fmt.Errorf("not found"), http.StatusNotFound)
		}
		rel = strings.TrimPrefix(rel, "/")
		base := "/data"

		var candidate string
		if wantThumb {
			ext := filepath.Ext(rel)
			withoutExt := strings.TrimSuffix(rel, ext)
			for _, t := range []string{".webp", ".thumb.webp", ".thumb.jpg", ".thumb.png"} {
				p := filepath.Join(base, withoutExt+t)
				if _, err := os.Stat(p); err == nil {
					candidate = p
					break
				}
			}
		}
		if candidate == "" {
			candidate = filepath.Join(base, rel)
		}
		cleaned := filepath.Clean(candidate)
		if !strings.HasPrefix(cleaned, base) {
			return validate.NewRequestError(fmt.Errorf("bad path"), http.StatusBadRequest)
		}
		return streamAttachmentFile(w, r, cleaned)
	}
}

// ---------------- 出库单（纯库存：扣减，无收银/报表） ----------------

type outboundItem struct {
	EntityID string  `json:"entityId"`
	Name     string  `json:"name,omitempty"`
	Count    float64 `json:"count"`
}

type outbound struct {
	ID         string         `json:"id"`
	TS         string         `json:"ts"`
	Reason     string         `json:"reason,omitempty"`
	Note       string         `json:"note,omitempty"`
	Items      []outboundItem `json:"items"`
	RolledBack bool           `json:"rolledBack,omitempty"`
}

func loadOutbounds() []outbound {
	var os_ []outbound
	bizReadJSON(outboundsPath, &os_)
	return os_
}

func saveOutbounds(os_ []outbound) error { return bizWriteJSON(outboundsPath, os_) }

func (a *app) handleBizOutbounds() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		os_ := loadOutbounds()
		if os_ == nil {
			os_ = []outbound{}
		}
		return server.JSON(w, http.StatusOK, os_)
	}
}

type outboundBody struct {
	Reason string         `json:"reason"`
	Note   string         `json:"note"`
	Items  []outboundItem `json:"items"`
}

// applyOutbound 出库核心：扣库存、落出库单、审计、单据同步。
// 发货确认与原出库创建共用。status 为建议 HTTP 状态码（400 明细全败 / 500 落盘失败）。
func (a *app) applyOutbound(ctx services.Context, reason, note string, items []outboundItem) (*outbound, []string, int, error) {
	ob := &outbound{ID: bizRandID(), TS: bizNow(), Reason: strings.TrimSpace(reason), Note: strings.TrimSpace(note)}
	var errs []string

	for _, it := range items {
		eid, err := uuid.Parse(it.EntityID)
		if err != nil || it.Count <= 0 {
			errs = append(errs, "明细无效: "+it.EntityID)
			continue
		}
		full, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, eid)
		if err != nil {
			errs = append(errs, "物品不存在: "+it.EntityID)
			continue
		}
		newQty := full.Quantity - it.Count
		if newQty < 0 {
			errs = append(errs, fmt.Sprintf("库存不足(%g)：%s", full.Quantity, full.Name))
			continue
		}
		upd := entityUpdateFromFull(full)
		upd.Quantity = newQty
		if _, err := a.repos.Entities.UpdateByGroup(ctx, ctx.GID, upd); err != nil {
			errs = append(errs, "更新失败: "+full.Name)
			continue
		}
		ob.Items = append(ob.Items, outboundItem{EntityID: it.EntityID, Name: full.Name, Count: it.Count})
	}

	if len(ob.Items) == 0 {
		return nil, errs, http.StatusBadRequest, fmt.Errorf("没有成功出库的明细：%s", strings.Join(errs, "；"))
	}

	os_ := loadOutbounds()
	os_ = append([]outbound{*ob}, os_...)
	if err := saveOutbounds(os_); err != nil {
		return nil, errs, http.StatusInternalServerError, err
	}
	eids := make([]string, 0, len(ob.Items))
	for _, it := range ob.Items {
		eids = append(eids, it.EntityID)
	}
	auditLogG(ctx.GID.String(), "outbound.create", map[string]any{"outboundId": ob.ID, "items": len(ob.Items), "reason": ob.Reason, "entityIds": eids})
	{
		lines := make([]gxDocLine, 0, len(ob.Items))
		for _, it := range ob.Items {
			lines = append(lines, gxDocLine{ItemID: it.EntityID, Qty: -float64(it.Count)})
		}
		gxRecordDocumentLogged(ctx.GID.String(), "outbound", ob.ID, ob.Reason, ob.Note, "posted", ob.TS, lines)
	}
	return ob, errs, http.StatusOK, nil
}

func (a *app) handleBizOutboundCreate() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requirePerm(r, "editorCanOutbound", "无出库权限"); err != nil {
			return err
		}
		var body outboundBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		if len(body.Items) == 0 {
			return validate.NewRequestError(fmt.Errorf("没有出库明细"), http.StatusBadRequest)
		}
		key := idemKey(r)
		if cached, ok := idemLookup(key); ok {
			return idemServe(w, cached)
		}

		ctx := services.NewContext(r.Context())
		ob, errs, status, err := a.applyOutbound(ctx, body.Reason, body.Note, body.Items)
		if err != nil {
			return validate.NewRequestError(err, status)
		}
		resp := map[string]any{"outbound": ob, "errors": errs}
		idemStore(key, resp)
		return server.JSON(w, http.StatusOK, resp)
	}
}

type outboundRollbackBody struct {
	OutboundID string `json:"outboundId"`
}

// applyOutboundRollback 回滚核心：库存加回、标记已回滚、审计、单据同步。
// 出库回滚与发货撤销共用。
func (a *app) applyOutboundRollback(ctx services.Context, outboundID string) (*outbound, []string, int, error) {
	os_ := loadOutbounds()
	idx := -1
	for i, v := range os_ {
		if v.ID == outboundID {
			idx = i
			break
		}
	}
	if idx < 0 {
		return nil, nil, http.StatusNotFound, fmt.Errorf("出库单不存在")
	}
	t := os_[idx]
	if t.RolledBack {
		return nil, nil, http.StatusConflict, fmt.Errorf("该出库单已回滚")
	}

	var errs []string
	for _, it := range t.Items {
		eid, err := uuid.Parse(it.EntityID)
		if err != nil {
			continue
		}
		full, err := a.repos.Entities.GetOneByGroup(ctx, ctx.GID, eid)
		if err != nil {
			errs = append(errs, "物品不存在，跳过: "+it.Name)
			continue
		}
		upd := entityUpdateFromFull(full)
		upd.Quantity = full.Quantity + it.Count
		if _, err := a.repos.Entities.UpdateByGroup(ctx, ctx.GID, upd); err != nil {
			errs = append(errs, "更新失败: "+it.Name)
			continue
		}
	}
	t.RolledBack = true
	os_[idx] = t
	if err := saveOutbounds(os_); err != nil {
		return nil, errs, http.StatusInternalServerError, err
	}
	eids := make([]string, 0, len(t.Items))
	for _, it := range t.Items {
		eids = append(eids, it.EntityID)
	}
	auditLogG(ctx.GID.String(), "outbound.rollback", map[string]any{"outboundId": t.ID, "items": len(t.Items), "entityIds": eids})
	gxMarkRolledBack(ctx.GID.String(), "outbound", t.ID)
	return &t, errs, http.StatusOK, nil
}

func (a *app) handleBizOutboundRollback() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requireOwner(r); err != nil {
			return err
		}
		var body outboundRollbackBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		key := idemKey(r)
		if cached, ok := idemLookup(key); ok {
			return idemServe(w, cached)
		}

		ctx := services.NewContext(r.Context())
		t, errs, status, err := a.applyOutboundRollback(ctx, body.OutboundID)
		if err != nil {
			return validate.NewRequestError(err, status)
		}
		resp := map[string]any{"outbound": t, "errors": errs}
		idemStore(key, resp)
		return server.JSON(w, http.StatusOK, resp)
	}
}

var _ = context.Background
