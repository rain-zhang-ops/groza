package main

// 发货台（预出库）：拣货/打包环节的发货单缓存。
//   买家下单先建发货单（不动库存）；发货前退款则取消（库存无影响）；
//   确认发货才真正扣库存并生成出库单（复用 applyOutbound，库存不足的明细跳过并报错）。
// 存储：/data/biz/shipments.json（与 intakes/outbounds 同一 JSON 模式）。
//
//   GET  /api/v1/biz/shipments          发货单列表（新→旧）
//   POST /api/v1/biz/shipments          新建 {party, note, items:[{entityId, count}]}
//   POST /api/v1/biz/shipments/ship     确认发货 {id}
//   POST /api/v1/biz/shipments/cancel   取消（退款/误建）{id}——仅待发货
//   POST /api/v1/biz/shipments/undo     撤销发货 {id}——已发货回滚出库，库存加回

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
)

const shipmentsPath = bizDir + "/shipments.json"

type shipmentItem struct {
	EntityID string  `json:"entityId"`
	Name     string  `json:"name,omitempty"`
	Count    float64 `json:"count"`
}

type shipment struct {
	ID         string         `json:"id"`
	TS         string         `json:"ts"`
	Party      string         `json:"party,omitempty"` // 买家 / 去向
	Note       string         `json:"note,omitempty"`
	Items      []shipmentItem `json:"items"`
	Status     string         `json:"status"` // pending | shipped | cancelled
	ShippedTS  string         `json:"shippedTs,omitempty"`
	OutboundID string         `json:"outboundId,omitempty"`
}

func loadShipments() []shipment {
	var ss []shipment
	bizReadJSON(shipmentsPath, &ss)
	return ss
}

func saveShipments(ss []shipment) error { return bizWriteJSON(shipmentsPath, ss) }

func (a *app) handleBizShipments() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ss := loadShipments()
		if ss == nil {
			ss = []shipment{}
		}
		return server.JSON(w, http.StatusOK, ss)
	}
}

type shipmentBody struct {
	Party string         `json:"party"`
	Note  string         `json:"note"`
	Items []shipmentItem `json:"items"`
}

func (a *app) handleBizShipmentCreate() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requirePerm(r, "editorCanOutbound", "无发货权限"); err != nil {
			return err
		}
		var body shipmentBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		if len(body.Items) == 0 {
			return validate.NewRequestError(fmt.Errorf("没有发货明细"), http.StatusBadRequest)
		}
		key := idemKey(r)
		if cached, ok := idemLookup(key); ok {
			return idemServe(w, cached)
		}

		ctx := services.NewContext(r.Context())
		sh := &shipment{
			ID: bizRandID(), TS: bizNow(), Status: "pending",
			Party: strings.TrimSpace(body.Party), Note: strings.TrimSpace(body.Note),
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
			sh.Items = append(sh.Items, shipmentItem{EntityID: it.EntityID, Name: full.Name, Count: it.Count})
			if full.Quantity < it.Count {
				errs = append(errs, fmt.Sprintf("库存不足(现%g)：%s", full.Quantity, full.Name))
			}
		}
		if len(sh.Items) == 0 {
			return validate.NewRequestError(fmt.Errorf("没有有效明细：%s", strings.Join(errs, "；")), http.StatusBadRequest)
		}

		ss := loadShipments()
		ss = append([]shipment{*sh}, ss...)
		if err := saveShipments(ss); err != nil {
			return validate.NewRequestError(err, http.StatusInternalServerError)
		}
		auditLogG(ctx.GID.String(), "shipment.create", map[string]any{"shipmentId": sh.ID, "items": len(sh.Items), "party": sh.Party})
		resp := map[string]any{"shipment": sh, "errors": errs}
		idemStore(key, resp)
		return server.JSON(w, http.StatusOK, resp)
	}
}

type shipmentIDBody struct {
	ID string `json:"id"`
}

// findShipment 定位待操作的发货单（按 id）。
func findShipment(ss []shipment, id string) int {
	for i, s := range ss {
		if s.ID == id {
			return i
		}
	}
	return -1
}

func (a *app) handleBizShipmentShip() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requirePerm(r, "editorCanOutbound", "无发货权限"); err != nil {
			return err
		}
		var body shipmentIDBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		key := idemKey(r)
		if cached, ok := idemLookup(key); ok {
			return idemServe(w, cached)
		}

		ss := loadShipments()
		idx := findShipment(ss, body.ID)
		if idx < 0 {
			return validate.NewRequestError(fmt.Errorf("发货单不存在"), http.StatusNotFound)
		}
		sh := ss[idx]
		if sh.Status != "pending" {
			return validate.NewRequestError(fmt.Errorf("该发货单已%s", map[string]string{"shipped": "发货", "cancelled": "取消"}[sh.Status]), http.StatusConflict)
		}

		ctx := services.NewContext(r.Context())
		items := make([]outboundItem, 0, len(sh.Items))
		for _, it := range sh.Items {
			items = append(items, outboundItem{EntityID: it.EntityID, Name: it.Name, Count: it.Count})
		}
		ob, errs, status, err := a.applyOutbound(ctx, sh.Party, sh.Note, items)
		if err != nil {
			return validate.NewRequestError(err, status)
		}

		sh.Status = "shipped"
		sh.ShippedTS = bizNow()
		sh.OutboundID = ob.ID
		ss[idx] = sh
		if err := saveShipments(ss); err != nil {
			return validate.NewRequestError(err, http.StatusInternalServerError)
		}
		auditLogG(ctx.GID.String(), "shipment.ship", map[string]any{"shipmentId": sh.ID, "outboundId": ob.ID, "items": len(ob.Items)})
		resp := map[string]any{"shipment": sh, "outbound": ob, "errors": errs}
		idemStore(key, resp)
		return server.JSON(w, http.StatusOK, resp)
	}
}

func (a *app) handleBizShipmentCancel() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requirePerm(r, "editorCanOutbound", "无发货权限"); err != nil {
			return err
		}
		var body shipmentIDBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		key := idemKey(r)
		if cached, ok := idemLookup(key); ok {
			return idemServe(w, cached)
		}

		ss := loadShipments()
		idx := findShipment(ss, body.ID)
		if idx < 0 {
			return validate.NewRequestError(fmt.Errorf("发货单不存在"), http.StatusNotFound)
		}
		sh := ss[idx]
		if sh.Status != "pending" {
			return validate.NewRequestError(fmt.Errorf("只有待发货单可以取消"), http.StatusConflict)
		}
		sh.Status = "cancelled"
		ss[idx] = sh
		if err := saveShipments(ss); err != nil {
			return validate.NewRequestError(err, http.StatusInternalServerError)
		}
		ctx := services.NewContext(r.Context())
		auditLogG(ctx.GID.String(), "shipment.cancel", map[string]any{"shipmentId": sh.ID, "party": sh.Party})
		resp := map[string]any{"shipment": sh}
		idemStore(key, resp)
		return server.JSON(w, http.StatusOK, resp)
	}
}

func (a *app) handleBizShipmentUndo() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		if err := a.requireOwner(r); err != nil {
			return err
		}
		var body shipmentIDBody
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
			return validate.NewRequestError(err, http.StatusBadRequest)
		}
		key := idemKey(r)
		if cached, ok := idemLookup(key); ok {
			return idemServe(w, cached)
		}

		ss := loadShipments()
		idx := findShipment(ss, body.ID)
		if idx < 0 {
			return validate.NewRequestError(fmt.Errorf("发货单不存在"), http.StatusNotFound)
		}
		sh := ss[idx]
		if sh.Status != "shipped" || sh.OutboundID == "" {
			return validate.NewRequestError(fmt.Errorf("只有已发货单可以撤销"), http.StatusConflict)
		}

		ctx := services.NewContext(r.Context())
		ob, errs, status, err := a.applyOutboundRollback(ctx, sh.OutboundID)
		if err != nil {
			return validate.NewRequestError(err, status)
		}
		sh.Status = "cancelled"
		ss[idx] = sh
		if err := saveShipments(ss); err != nil {
			return validate.NewRequestError(err, http.StatusInternalServerError)
		}
		auditLogG(ctx.GID.String(), "shipment.undo", map[string]any{"shipmentId": sh.ID, "outboundId": sh.OutboundID})
		resp := map[string]any{"shipment": sh, "outbound": ob, "errors": errs}
		idemStore(key, resp)
		return server.JSON(w, http.StatusOK, resp)
	}
}
