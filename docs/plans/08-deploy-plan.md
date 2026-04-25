# 08 Deploy Plan

## 目标

提供自部署运行说明和 Docker Compose 环境。

## 范围

- API、Web、PostgreSQL 三个服务。
- 环境变量模板。
- 数据库初始化步骤。
- 数据库初始化与清理步骤。
- 可选 seed 默认来源和设置。

## 部署步骤

1. 复制 `infra/env/.env.example` 为 `infra/env/.env`。
2. 填写 PostgreSQL、模型 API、SMTP 配置。
3. 执行 Docker Compose 启动。
4. 启动后检测并初始化表结构；如需重置数据库，可清空 `postgres_data` 数据卷后重启。
5. 打开控制台配置关键词。

## 验收标准

- 空 PostgreSQL 可以完成首次结构初始化。
- API 健康检查可访问。
- Web 控制台可访问。
- SMTP 未配置时系统仍可运行。

## 非目标

- 不提供云厂商一键部署。
- 不做旧数据导入。
