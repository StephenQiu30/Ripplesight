# 00 Foundation Plan

## 目标

从零建立新项目基础结构，不保留旧实现、旧数据库结构和旧 OpenAPI 契约。

## 范围

- 建立 `apps/api` FastAPI 后端。
- 建立 `apps/web` Next.js 控制台。
- 建立 PostgreSQL 与 SQLAlchemy 基础（无迁移）。
- 建立 Docker Compose 和环境变量模板。
- 确认空数据库启动初始化路径可创建必要表结构。

## 实现步骤

1. 初始化 FastAPI 应用入口和健康检查接口。
2. 初始化 Next.js 应用入口。
3. 配置 PostgreSQL 连接环境变量。
4. 配置 SQLAlchemy Base 并定义无迁移初始化入口（`create_all`）。
5. 配置 Docker Compose 启动 API、Web、PostgreSQL。
6. 删除或忽略旧实现路径，不做兼容层。

## 验收标准

- `GET /api/health` 返回 `{"status":"ok"}`。
- 空 PostgreSQL 可以连接。
- 能从空 PostgreSQL 直接完成首轮表结构初始化。
- 项目不依赖旧 `backend/core`、`services/api`、`services/worker`。

## 非目标

- 不实现业务表。
- 不迁移旧数据。
- 不实现关键词、热点、通知业务。
