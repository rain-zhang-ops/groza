SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help check build deploy backup drill restore purge rollback e2e health nginx ps logs

help: ## 显示可用命令
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

check: ## 本地静态检查（bash/python/gofmt/文件齐全）
	./ops/check.sh

build: ## 构建并部署（下载上游→注入→打补丁→构建→切换容器→冒烟测试）
	bash rebuild.sh

deploy: build ## 别名：build

backup: ## 一致性备份（暂停→打包→校验→保留N份→可选异地）
	./ops/backup.sh

drill: ## 恢复演练（临时卷启动验证，不影响生产）
	./ops/restore.sh --drill

restore: ## 真实恢复：make restore FILE=/path/to/backup.tar.gz
	@test -n "$(FILE)" || { echo "用法: make restore FILE=/path.tar.gz"; exit 1; }
	./ops/restore.sh "$(FILE)" --yes

purge: ## 回收站清除（先快照）：make purge [DAYS=30] [IDS=a,b]
	./ops/purge.sh $(if $(DAYS),--days $(DAYS),) $(if $(IDS),--ids $(IDS),)

rollback: ## 镜像回滚：make rollback TAG=0.26.2-xxxx / 无 TAG 列出
	./ops/rollback.sh $(TAG)

e2e: ## 端到端测试（Playwright，登录→台账）
	./ops/e2e.sh

health: ## 健康检查（状态+容器+DB+磁盘）
	./ops/healthcheck.sh

nginx: ## 重建 HTTPS 反向代理容器
	./ops/nginx.sh

ps: ## 查看容器状态
	docker ps --filter name=homebox --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

logs: ## 查看 homebox 最近日志
	docker logs --tail=100 homebox
