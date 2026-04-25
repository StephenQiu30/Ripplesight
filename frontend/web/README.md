# AI Hotspot Console (Frontend)

该目录用于 Stage 5 运营控制台 MVP（仅读链路）。

## 技术栈

- Next.js 14 + App Router
- TypeScript
- Tailwind CSS
- OpenAPI 接口类型自动生成：`@umijs/openapi`（`generateService`）

## 快速开始

```bash
cd frontend/web
npm install
npm run api:gen
npm run dev
```

### 一键启动（联调主路径）

在仓库根目录执行：

```bash
cp infra/env/.env.example infra/env/.env && docker compose --profile app up -d --build
```

启动后访问：`http://127.0.0.1:3000/events`

对应容器环境已设置 `NEXT_PUBLIC_API_BASE_URL=http://api:8000`，前端会通过容器内 DNS 访问后端。

### 验收命令

```bash
curl -fsS http://127.0.0.1:8000/api/events?page=1&page_size=1
curl -fsS http://127.0.0.1:3000/events
curl -fsS http://127.0.0.1:3000/search
```

### 环境变量

- `NEXT_PUBLIC_API_BASE_URL`：服务端请求基地址，默认 `http://localhost:8000`
- 本地开发可直接访问 `http://localhost:3000/events`，页面会将 `/api/*` 走 Next 重写到后端。

## OpenAPI 生成链路

- `npm run api:gen`：基于 `contracts/openapi/openapi.yaml` 生成 `src/openapi/*`。
- `npm run api:check`：重新生成并检查文件是否落盘一致（防止接口文件未同步）。
- `npm run api:lint`：`api:gen + api:check` 的链路入口，建议每次 `openapi.yaml` 变更后执行。

## 页面结构

- `/events`：热点榜单（支持 `topic`、`source_type`、分页）
- `/events/[id]`：事件详情（展示证据链 + 反馈）
- `/search`：关键词搜索
- `/digest`：今日日报摘要
- `/config`：来源配置 / X 关键词 / X 账号（只读）
