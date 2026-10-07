package main

// 权限检查点（复用 Homebox 角色）：危险操作要求 group 的 owner。
//   GET /api/v1/gx/me   返回当前用户在所属 group 的角色（owner|user）
// 仅用于 gx_ 侧车与部分危险端点；不改动 Homebox 核心鉴权。

import (
	"fmt"
	"net/http"

	"github.com/hay-kot/httpkit/errchain"
	"github.com/hay-kot/httpkit/server"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
)

// isOwner 判断当前请求用户是否为所属 group 的 owner。
func (a *app) isOwner(r *http.Request) (bool, error) {
	ctx := services.NewContext(r.Context())
	return a.repos.Groups.IsOwnerOf(ctx, ctx.UID, ctx.GID)
}

// requireOwner 危险操作守卫：非 owner 返回 403。
func (a *app) requireOwner(r *http.Request) error {
	ok, err := a.isOwner(r)
	if err != nil {
		return err
	}
	if !ok {
		return validate.NewRequestError(fmt.Errorf("需要管理员(owner)权限"), http.StatusForbidden)
	}
	return nil
}

func (a *app) handleGxMe() errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		ctx := services.NewContext(r.Context())
		owner, err := a.isOwner(r)
		if err != nil {
			return err
		}
		role := "user"
		if owner {
			role = "owner"
		}
		return server.JSON(w, http.StatusOK, map[string]any{
			"userId":  ctx.UID.String(),
			"role":    role,
			"isOwner": owner,
		})
	}
}
