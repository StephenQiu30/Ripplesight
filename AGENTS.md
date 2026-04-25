# AGENTS

本文件定义本仓库文档、实现和协作约束。当前阶段以“从零重建轻量 MVP、开源自部署、可配置关键词的 AI 热点监控工具”为最高优先级。

## 1. 文档主事实源

- 产品需求与范围以 `docs/product/prd.md` 及其子文件为准。
- 执行计划以 `docs/product/plan.md` 为准。
- 技术约束以 `docs/engineering/tech-spec.md` 为准。
- API 契约由新 FastAPI 实现自动生成；旧 `contracts/openapi` 不再是实现约束。
- 验收口径以 `docs/engineering/acceptance.md` 为准。
- 具体执行任务以 `docs/plans/` 下的 PLAN 文件为准。
- 鱼皮 MVP 迁移范围以 `docs/plans/10-yupi-hot-monitor-mvp-plan.md` 为准。

## 2. 产品实现方向

- 第一阶段定位为“可自部署、可配置关键词的 AI 热点监控工具”，不是重型舆情平台。
- 功能实现优先参考鱼皮 `yupi-hot-monitor` 的 MVP 能力：关键词管理、多源抓取、AI 查询扩展、真假识别、相关性分析、热点列表、筛选排序、全网搜索、邮件通知、手动触发和定时触发。
- 参考鱼皮项目的功能闭环，不复制其技术栈；本仓库使用 `Next.js + TypeScript` 前端、`Python + FastAPI` 后端、`PostgreSQL` 数据库、`SQLAlchemy 2.0` ORM、`SMTP` 邮件。
- P0 必须围绕可运行闭环：配置关键词 -> 抓取多源内容 -> AI 查询扩展 -> AI 判断相关性/真实性 -> 生成热点 -> 阈值过滤 -> 事件邮件通知 -> AI 日报邮件。
- 鱼皮 MVP 迁移只迁移功能闭环，不迁移技术栈；继续使用 `Python + FastAPI + PostgreSQL + SQLAlchemy + Next.js`。
- 第一阶段数据源范围为 RSS、Hacker News、X/Twitter、Bing、Bilibili、Sogou-style；新增来源必须走统一 adapter 和 `Candidate` 输出。
- X/Twitter 必须使用官方 X API v2 Recent Search，通过 `X_API_BEARER_TOKEN` 注入凭据；不得引入页面爬取作为默认实现。
- 低于 `RELEVANCE_THRESHOLD` 的热点必须标记为 `filtered`，不得发送事件邮件，不得进入 AI 日报。
- 达到 `RELEVANCE_THRESHOLD` 的热点标记为 `active`，允许进入热点流、事件邮件和 AI 日报。
- P0 不做多租户、复杂权限、计费、复杂工作流、向量库、复杂队列治理和企业级数据平台。

## 3. 改动规范

- 新增需求必须先落 PRD 对应章节，再映射到技术文档和验收项。
- 不得在未更新 PRD 的情况下扩展新来源、规则或能力范围。
- 每次实现改动应可追踪到某个 PRD P0/P1 条目。
- 新增字段或新增 API 时，必须同步更新 OpenAPI、主技术文档和验收项，不得仅在代码层面变更。
- 当前旧实现、旧目录结构、旧数据库结构、旧 OpenAPI 契约、旧示例数据均不保留。
- 后续实现以 `docs/plans/` 为执行依据，不需要兼容旧代码、旧表结构或旧内存仓库。

## 4. 架构底线

- `apps/api` 承载 FastAPI 后端入口、路由、依赖注入、数据库访问和任务触发入口。
- `apps/web` 承载 Next.js 控制台。
- `packages/core` 承载跨应用共享的轻量类型、常量或文档化规则；不得重新引入旧 `backend/core` 分层。
- `sql/` 是数据库表结构事实源；`apps/api` 的 SQLAlchemy models 必须与 `sql/001_init_schema.sql` 保持一致。
- `migrations` 已废弃，不引入数据库迁移工具；数据库初始化优先执行 `sql/001_init_schema.sql`，重置时通过清空数据库重建。
- 外部平台、模型服务、邮件服务和数据库访问必须放在 infrastructure/adapter 层或等价隔离层中。
- 当前架构中不利于 MVP 落地的部分已允许删除，包括静态样例数据主链路、启动时隐式初始化业务数据、内存仓库作为生产默认实现。
- 不做旧 schema 迁移，不做旧数据迁移，不读取旧表、旧 bootstrap 数据或旧内存仓库。

## 5. 配置与运行约束

- 依赖与凭据仅允许通过环境变量注入。
- 环境变量只保留必要配置：PostgreSQL 连接、模型 API Key、可选 X/Twitter Key、SMTP 配置和服务端口。
- PostgreSQL 默认使用用户本机已有实例；不要为 P0 默认开发链路重新创建 Docker PostgreSQL 环境。
- 邮件未配置时系统仍必须可运行，只是不发送邮件。
- X/Twitter 未配置时系统仍必须可运行，只跳过该来源。
- Bing 未配置时系统仍必须可运行，只跳过该来源。
- 单个数据源失败不能中断整个热点检查任务。
- 手动触发和定时触发都必须走同一条业务编排链路。

## 6. 代码与测试

- 新增行为默认配套测试；核心流程至少覆盖正向主链路。
- 关键词管理、热点筛选、去重入库、AI 分析降级、邮件未配置降级必须有测试或可验收用例。
- 文档更新、API 更新、代码提交应同步进行，不出现“先写代码后补文档”。

## 7. 评审标准

- 评审时优先看“是否可运行、是否可配置、是否可回滚、失败是否可追踪”，其次看设计优雅性。
- 能用简单配置解决的问题，不引入复杂平台能力。
- 能参考鱼皮项目 MVP 功能闭环直接落地的问题，不提前抽象为企业级平台。
- 能通过 PostgreSQL + SQLAlchemy + FastAPI 直接完成的能力，不引入 Prisma、SQLite、Celery、Redis 或旧 OpenAPI 约束。
