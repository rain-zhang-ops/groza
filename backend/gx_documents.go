package main

// 统一单据（sidecar）：读写 gx_document / gx_document_line。
//   GET /api/v1/gx/documents?kind=intake|outbound&limit=200   统一单据列表（含明细与物品名）
// biz 的入库/出库在写入时同步落库（JSON 仍保留，回滚逻辑不变）。
// 仅访问 gx_ 表与只读 entities（取名称）。

import (
	"database/sql"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
)

type gxDocLine struct {
	ItemID   string
	Qty      float64
	UnitCost float64
	Before   float64
	After    float64
}

// gxRecordDocument 幂等写入一张单据（已存在同 group+kind+code 则跳过）。
// 失败返回 error——调用方必须记录日志并触发 gxRepairDocumentsFromBiz 对账，
// 单据页是唯一记录视图，不允许静默丢单。
func gxRecordDocument(gid, kind, code, party, note, status, ts string, lines []gxDocLine) error {
	db, err := gxOpen()
	if err != nil {
		return err
	}
	defer db.Close()
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	var n int
	if err = tx.QueryRow(`SELECT COUNT(*) FROM gx_document WHERE group_id=? AND kind=? AND code=?`, gid, kind, code).Scan(&n); err != nil {
		return err
	}
	if n > 0 {
		return nil
	}
	docID := uuid.NewString()
	posted := any(nil)
	if status == "posted" {
		posted = ts
	}
	if _, err = tx.Exec(`INSERT INTO gx_document (id,group_id,kind,code,party,note,status,created_at,posted_at,idem_key)
		VALUES (?,?,?,?,?,?,?,?,?,?)`, docID, gid, kind, code, party, note, status, ts, posted, gid+":"+kind+":"+code); err != nil {
		return err
	}
	for _, l := range lines {
		if _, err = tx.Exec(`INSERT INTO gx_document_line (id,group_id,document_id,item_id,qty,unit_cost,qty_before,qty_after)
			VALUES (?,?,?,?,?,?,?,?)`, uuid.NewString(), gid, docID, l.ItemID, l.Qty, l.UnitCost, l.Before, l.After); err != nil {
			return err
		}
	}
	return tx.Commit()
}

// gxRepairDocumentsFromBiz 以 biz JSON 权威存储为准，回填缺失的入/出库单据
// 并同步回滚状态（幂等）。盘点调整无 biz JSON 副本，不在对账范围内。
func gxRepairDocumentsFromBiz(gid string) {
	for _, ii := range loadIntakes() {
		lines := make([]gxDocLine, 0, len(ii.Items))
		for _, it := range ii.Items {
			lines = append(lines, gxDocLine{ItemID: it.EntityID, Qty: it.Count, UnitCost: it.Cost})
		}
		if err := gxRecordDocument(gid, "intake", ii.ID, ii.Supplier, ii.Note, "posted", ii.TS, lines); err == nil {
			if ii.RolledBack {
				gxMarkRolledBack(gid, "intake", ii.ID)
			}
		}
	}
	for _, ob := range loadOutbounds() {
		lines := make([]gxDocLine, 0, len(ob.Items))
		for _, it := range ob.Items {
			lines = append(lines, gxDocLine{ItemID: it.EntityID, Qty: -it.Count})
		}
		if err := gxRecordDocument(gid, "outbound", ob.ID, ob.Reason, ob.Note, "posted", ob.TS, lines); err == nil {
			if ob.RolledBack {
				gxMarkRolledBack(gid, "outbound", ob.ID)
			}
		}
	}
}

var gxRepairOnce sync.Once

// gxRecordDocumentLogged 落库并兜底：失败记日志（docker logs 可见）并异步触发对账回填。
func gxRecordDocumentLogged(gid, kind, code, party, note, status, ts string, lines []gxDocLine) {
	if err := gxRecordDocument(gid, kind, code, party, note, status, ts, lines); err != nil {
		log.Printf("[gx] 单据落库失败 kind=%s code=%s: %v（已触发对账回填）", kind, code, err)
		go gxRepairDocumentsFromBiz(gid)
	}
}

// gxMarkRolledBack 将单据标记为已回滚。best-effort。
func gxMarkRolledBack(gid, kind, code string) {
	db, err := gxOpen()
	if err != nil {
		return
	}
	defer db.Close()
	_, _ = db.Exec(`UPDATE gx_document SET status='rolled_back', rolled_back_at=? WHERE group_id=? AND kind=? AND code=?`,
		time.Now().UTC().Format(time.RFC3339), gid, kind, code)
}

func (a *app) handleGxDocuments() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())
		gid := ctx.GID.String()
		// 首次查询单据页时做一次对账回填（幂等、秒级），修复历史落库失败
		gxRepairOnce.Do(func() { go gxRepairDocumentsFromBiz(gid) })
		kind := r.URL.Query().Get("kind")
		limit := 200
		if v, err := strconv.Atoi(r.URL.Query().Get("limit")); err == nil && v > 0 && v <= 1000 {
			limit = v
		}
		db, err := gxOpen()
		if err != nil {
			return err
		}
		defer db.Close()

		q := `SELECT id,kind,code,party,note,status,created_at FROM gx_document WHERE group_id=?`
		args := []any{gid}
		if kind != "" {
			q += ` AND kind=?`
			args = append(args, kind)
		}
		q += ` ORDER BY created_at DESC LIMIT ?`
		args = append(args, limit)

		rows, err := db.Query(q, args...)
		if err != nil {
			return fmt.Errorf("查询单据失败: %w", err)
		}
		defer rows.Close()

		type docOut struct {
			ID         string           `json:"id"`
			DocID      string           `json:"docId"`
			Kind       string           `json:"kind"`
			TS         string           `json:"ts"`
			Party      string           `json:"party"`
			Note       string           `json:"note"`
			Status     string           `json:"status"`
			RolledBack bool             `json:"rolledBack"`
			Items      []map[string]any `json:"items"`
			TotalCost  float64          `json:"totalCost"`
		}
		type docRow struct {
			id, code, kindv string
			party, note     sql.NullString
			status          sql.NullString
			ts              string
		}
		// 先缓冲外层结果，避免单连接池下嵌套查询死锁
		var buffered []docRow
		for rows.Next() {
			var dr docRow
			if err = rows.Scan(&dr.id, &dr.kindv, &dr.code, &dr.party, &dr.note, &dr.status, &dr.ts); err != nil {
				return err
			}
			buffered = append(buffered, dr)
		}
		rows.Close()

		out := make([]docOut, 0, len(buffered))
		for _, dr := range buffered {
			d := docOut{
				ID: dr.code, DocID: dr.id, Kind: dr.kindv, TS: dr.ts,
				Party: dr.party.String, Note: dr.note.String, Status: dr.status.String,
				RolledBack: dr.status.String == "rolled_back", Items: []map[string]any{},
			}
			lines, err := db.Query(`SELECT l.item_id, l.qty, l.unit_cost, COALESCE(e.name,'')
				FROM gx_document_line l LEFT JOIN entities e ON e.id=l.item_id
				WHERE l.document_id=?`, dr.id)
			if err == nil {
				for lines.Next() {
					var itemID, name string
					var qty float64
					var cost sql.NullFloat64
					if err := lines.Scan(&itemID, &qty, &cost, &name); err != nil {
						continue
					}
					count := qty
					if count < 0 {
						count = -count
					}
					d.Items = append(d.Items, map[string]any{
						"entityId": itemID, "name": name, "count": count, "cost": cost.Float64,
					})
					d.TotalCost += count * cost.Float64
				}
				lines.Close()
			}
			out = append(out, d)
		}
		return server.JSON(w, http.StatusOK, map[string]any{"documents": out})
	}
}
