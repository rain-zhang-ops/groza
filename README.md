# Groza

基于 [Homebox](https://github.com/sysadminsmedia/homebox) v0.26.2 的**中文进销存/台账**定制版，面向手机端使用（iPhone Safari）。
在保留 Homebox 的基础上，注入自定义后端接口与前端页面，并配套一套可复现的构建与运维脚本。

## 功能

- **物品台账**：品牌/尺寸/规格/颜色/材质等字段、行内编辑、批量操作、筛选/排序、客户端分页、手机卡片 + 桌面表格双形态。
- **AI 拍照建档**：调用豆包/火山方舟识别图片，支持联网搜索（未开通自动退回），多图队列、结果确认、按图哈希缓存。
- **入库管理**：入库单（建单/加库存/改进价售价）、入库单回滚、离线队列 + 幂等键（`Idempotency-Key`）。
- **数据质量护栏**：数据体检（缺价/缺图/缺品牌/…/重复名称），一键筛选定位、重复名称合并（软删除）。
- **二维码标签**：按资产号生成可扫码二维码（公开 `/api/v1/qr`），单个/批量打印，扫码定位。
- **回收站 + 审计**：软删除（带删除时间）、清除（需确认、先快照）、按实体的变更历史、只追加审计日志。
- **批量导入/导出**：粘贴 TSV/CSV 批量建档；按当前筛选导出 CSV。
- **现代 UI**：Groza 靛蓝石板配色、移动 FAB、长按多选、触觉反馈。

## 目录结构

```
.
├── rebuild.sh                 # 主构建/部署脚本（下载上游→注入→补丁→构建→切换容器→冒烟）
├── Makefile                   # 便捷入口（make help）
├── backend/                   # 自定义后端（注入到 upstream app/api/，package main）
│   ├── ledger_api.go          # /ledger 聚合、字段级 PATCH（乐观锁）、trash2
│   ├── biz.go                 # 入库（intake / rollback / intakes）
│   ├── ai_recognize.go        # AI 识别（豆包 responses API）
│   ├── audit.go               # 审计日志 + 查询
│   ├── idempotency.go         # 幂等键
│   ├── metrics.go             # /metrics
│   ├── qr.go                  # 公开二维码 /qr
│   ├── trash.go / ui_options.go
├── frontend/                  # 自定义前端页面（注入到 upstream frontend/pages|composables）
│   ├── pages/ledger.vue       # 台账
│   ├── pages/intake.vue       # 进货入库
│   ├── pages/collection/ui-options.vue
│   └── composables/useOfflineQueue.ts
├── patches/patch_upstream.py  # 上游源码统一补丁（默认中文、导航、PWA、路由、Groza 品牌/配色）
├── deploy/
│   ├── nginx.conf             # HTTPS 反代（80→301、5036/443 → 127.0.0.1:5037）
│   └── homebox.env.example    # 环境变量示例
├── ops/                       # 运维脚本（备份/恢复/清除/回滚/健康/nginx/检查/e2e）
├── tests/                     # smoke.py（API 冒烟）、e2e.py（Playwright）
└── tools/                     # 离线查询小工具
```

## 架构与端口

- `homebox` 容器：应用本体，镜像 `homebox-cn:latest`，仅监听 `127.0.0.1:5037`，数据卷 `homebox-data`（SQLite）。
- `homebox-https` 容器：Nginx，`--network host`，对外 `https://<域名>:5036`（80 → 301 跳转；443 备用），反代到 `127.0.0.1:5037`。

## 快速开始

前置：docker、go、node/pnpm(corepack)、python3。

```bash
# 1) 环境变量
cp deploy/homebox.env.example ~/.config/homebox/homebox.env   # 填入真实值，chmod 600

# 2) 构建并部署（会自动跑冒烟测试）
make build            # 等价 ./rebuild.sh

# 3) HTTPS 反代（首次或更换配置时）
make nginx

# 4) 健康检查
make health
```

`rebuild.sh` 参数：
- `bash rebuild.sh [版本] [commit]`：指定目标版本/提交（默认按当前运行容器探测）。
- `FRESH=1 bash rebuild.sh`：强制重新下载源码（默认复用前端源码与 `node_modules` 加速）。
- `SMOKE=0 bash rebuild.sh`：跳过冒烟测试（保留源码目录便于调试）。

## 运维

```bash
make check                 # 静态检查（bash/python/gofmt/文件齐全）
make backup                # 一致性备份（暂停→打包→校验→保留N份；KEEP=30）
make drill                 # 恢复演练（临时卷，不动生产）
make restore FILE=...      # 真实恢复（先自动快照，再覆盖数据卷）
make purge DAYS=30         # 回收站清除（先快照；默认只清超期）
make rollback              # 列出版本标签；make rollback TAG=... 回滚
make e2e                   # 端到端测试
```

- **备份/异地**：`ops/backup.sh` 支持 `RCLONE_REMOTE=远端:路径` 异地同步（需安装 rclone）。
- **定时任务**建议：每日 `backup`、每周 `restore --drill`、每周 `e2e`、每 5 分钟 `healthcheck`。
- **审计**：`GET /api/v1/audit?limit=&entityId=`；**指标**：`GET /api/v1/metrics`。

## 测试

- `tests/smoke.py`：构建后自动运行，覆盖聚合接口、乐观锁、入库/回滚、回收站清除、审计、幂等重放、指标。
- `tests/e2e.py`：Playwright 登录 → 台账渲染（`ops/e2e.sh` 自动准备无头浏览器与依赖，无需 root）。

凭据来自环境变量或 `tests/smoke.env`（已被忽略，见 `tests/smoke.env.example`）。

## 致谢与许可

本项目是 [Homebox](https://github.com/sysadminsmedia/homebox)（MIT）的定制分支，`rebuild.sh` 在构建时下载上游源码并注入本仓库的定制文件与补丁；上游版权归其原作者所有。
