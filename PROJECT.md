# HotKey 技术架构

本文说明 HotKey 由哪些部分组成、各部分负责什么、必须遵守哪些技术约定。产品能力与验收标准见[文档工作区](workspace/content/index.md)，工程流程见 [AGENTS](AGENTS.md)，进度见 [BACKLOG](BACKLOG.md)。

## 1. 技术栈

| 部分 | 技术 |
|---|---|
| 后端 | Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、psycopg 3；依赖用 uv 管理（`pyproject.toml` + `uv.lock`） |
| Web | Node.js 24、pnpm 12、Next.js 16（App Router）、React 19、TypeScript、Tailwind、shadcn/ui + Radix、Axios |
| 数据 | PostgreSQL（业务数据唯一来源）、Redis（只放可重建的缓存和限流）、Kafka（持久任务消息）、MinIO（证据与文件） |
| 后台任务 | 独立 Worker 进程消费 Kafka；独立 Scheduler 进程用 APScheduler 每 30 秒扫描到期任务 |
| 本机外部服务 | RSSHub（1200）、SearXNG（8888）、Firecrawl（3002）、MediaCrawler（宿主子进程）、Codex app-server（宿主子进程） |
| 质量工具 | 后端 Ruff、mypy、pytest；Web 端 ESLint、Prettier、tsc、Vitest、生产构建 |

## 2. 进程与端口

| 进程 | 启动方式（在 `backend/app` 或 `frontend`） | 本机端口 |
|---|---|---|
| API | `uvicorn main:create_app --factory` | 8667（文档 `/docs`、`/scalar`，契约 `/openapi.json`） |
| Worker | `python -m worker` | — |
| Scheduler | `python -m worker.scheduler` | — |
| CLI | `python -m cli` | — |
| Web | `pnpm dev` / `pnpm start` | 8666 |

API 进程不跑定时器，也不消费消息。同一时间只运行一个 Worker，并且它运行在宿主机上，因为 Codex 登录状态和 MediaCrawler 浏览器都在宿主机。Compose 中容器内的端口统一为 8080，映射到宿主机的 8666/8667。

## 3. 目录

```text
hotkey-server/
├── backend/
│   ├── app/main.py            # 应用工厂，只负责装配
│   ├── app/api/               # 路由汇总、依赖注入、错误映射
│   ├── app/core/              # 配置、日志、公共错误、通用 Schema、时间
│   ├── app/db/                # ORM 基类、连接池、模型注册
│   ├── app/<领域>/            # 各业务领域，见 §4
│   ├── app/worker/            # Kafka 消费、任务子进程、Scheduler
│   ├── app/cli/               # 维护命令
│   ├── database/schema.sql    # 唯一的完整建表脚本
│   └── tests/                 # unit / integration / architecture
├── frontend/
│   ├── src/app/               # 路由；页面专属组件放在路由下的 components/
│   ├── src/components/        # ui/（shadcn 基础组件）及按功能划分的复用组件
│   ├── src/layout/            # 全站外壳
│   ├── src/api/               # 由 OpenAPI 生成的客户端（不要手改）
│   ├── src/request.ts         # 唯一的 HTTP 传输层
│   ├── src/proxy.ts           # 会话门禁与 CSP
│   └── tests/                 # 前端测试
└── workspace/                 # 文档工作区，外层为 Nextra 网站
    └── content/               # Obsidian 知识库
        ├── product/           # 产品文档，根层保留进度、架构与工程规范指针
        │   ├── prd/           # 产品需求：目标、范围与验收要求
        │   └── plan/          # 执行计划：任务、容量与依赖
        ├── capabilities/      # 各项能力规格与可用状态
        ├── decisions/         # 生效与历史决策
        ├── records/           # 真实验收记录
        ├── research/          # 调研依据
        ├── templates/         # 文档模板，不发布
        └── views/             # Obsidian 看板，不发布
```

## 4. 业务领域

后端只允许下列顶层包，架构测试（`tests/architecture/test_structure.py`）会拒绝未登记的包。新增领域需要先修改本表和该测试。

| 领域 | 负责 |
|---|---|
| identity | 账户、密码、会话、邮箱验证码、GitHub 登录、头像 |
| monitors | 主题与关键词、采集版本、调度 |
| jobs | 任务、Outbox、预算、租约、重试、取消、到期 |
| connections | 来源连接、授权与状态 |
| sources | 来源定义与外部采集适配器（`sources/adapters/`） |
| content | 内容身份、正文版本、评论父链、观察记录、主题匹配 |
| evidence | 文件元数据与 MinIO 适配器 |
| ai | 模型调用、Codex app-server 适配器、调用回执与用量账本 |
| analysis | 相关性、精选、结构化、写作、翻译、情感、观点、评测 |
| events | 事件归并、事实与进展、热度、向量 |
| reports | 个人日报/周报、公开刊物、导出 |
| notifications | 订阅、投递、告警 |
| knowledge | Obsidian 导出、检索与问答 |
| publication | 公开内容的许可、投影与撤回（对外分发部分已冻结） |
| leaderboard | 模型榜 |
| operations | 运营权限、站点设置、反馈、心跳、维护 |
| backups | 备份与恢复验证 |
| api / core / db / worker / cli | 见 §3 |

## 5. 分层规则

以下规则由架构测试和 ESLint 强制执行：

- **Router** 只处理 HTTP、身份校验、CSRF 和 DTO；通过 `api` 的依赖注入调用服务，不直接用 ORM，不构造 Service，也不发布消息。
- **Service** 只直接使用本领域的 ORM 模型；读取其他领域的数据要通过对方提供的函数或 DTO。跨领域的原子写入共用同一个 Session，由最外层负责提交。
- **Schema**（`schemas.py`）不依赖 ORM、Session 或 FastAPI。
- **Adapter**（`*/adapters/`）不依赖 API、ORM、Worker 或任务状态。
- `core` 不反向依赖业务领域；Worker 不依赖 HTTP 协议层。
- 应用错误不携带 HTTP 状态码，由 API 边界统一映射成 `ErrorView`。
- 不建通用的 BaseService / BaseRepository、全局 utils，也不建第二套队列、账本或正文库。
- Session 按请求或任务创建，不跨线程共享；资源由所属进程创建和关闭，模块导入时不联网。

## 6. 数据库

- `backend/database/schema.sql` 是唯一的建表来源，自带 `BEGIN/COMMIT`，只用于全新的空库。不用 Alembic，不用 ORM 建表，也不用 SQLite 存业务数据。所有时间字段使用 `TIMESTAMPTZ`。
- 改表结构时，SQL、ORM 模型和结构断言要在同一次提交里更新，并在一个全新的 PostgreSQL 上核对所有表的列、类型、可空性和主键。
- 业务库名固定为 `hotkey`。测试只用独立的 `hotkey_test_<后缀>` 库，用完删除；绝不能在业务库上跑测试。
- **升级有数据的库**：先停写并备份，在新库上实际恢复一遍，确认能读；再建一个全新空库、执行完整的 `schema.sql`、导入并核对数据（各表行数、外键、任务和预算等）；全部核对无误后才切换，旧库保留作回退。禁止直接在旧库上执行 `schema.sql`。

## 7. 任务与可靠性

- 业务状态和 Outbox 写在同一个 PostgreSQL 事务里，由 Outbox 发布到 Kafka。Worker 在业务提交后才提交 offset，通过消息 ID、租约和唯一约束保证重复消费也不会重复写入。
- Worker 父进程独占 Kafka 消费和任务的最终状态；每个任务在 `spawn` 出的子进程里执行，子进程自己建立数据库连接。任务取消、超时或进程异常退出时，回收整个进程组。
- 持久的重试和预算由 `jobs` 管理；适配器内部只做有限次数的安全重试。状态不明的外部发送不会自动重发。

## 8. 外部来源与模型

- 来源采集只走本机服务：RSSHub/SearXNG 的主机只能是 `127.0.0.1`（宿主机）或 `host.docker.internal`（Compose）。HTTP 适配器强制主机白名单，并校验每一次重定向。
- MediaCrawler 作为宿主机子进程运行，使用独立的浏览器和本人账号；浏览器资料目录权限为 700、文件权限为 600；遇到验证码、登录失效或限流就停用。
- 模型只走本机 Codex app-server：每个分析任务启动一个子进程，只读、不需要审批、只传最小环境变量、使用空的工作目录。模型输入一律视为不可信文本，输出必须是结构化结果并经过校验；数字、排序和引用由程序计算。
- 费用、账号、许可等产品边界见 [决策](workspace/content/index.md#决策)。

## 9. API 与身份

- FastAPI 路由注解加 Pydantic 是唯一的接口契约，运行时生成 `/openapi.json`；Web 客户端由它生成，不手写 OpenAPI 或客户端 DTO。
- 每个接口声明唯一的 `operation_id`、中文 summary 和 tag、成功响应模型和实际可能返回的错误。成功时返回资源 DTO、`PageView[T]`（`items` / `next_cursor`）或 `JobAcceptedView`；失败时统一返回 `ErrorView(code, message, request_id, details)`。
- 路径统一是 `/api/*`，不带版本号。日志只记录方法、路由模板、状态码和耗时，不记录 URL 参数、正文、Cookie 或 Token。
- 登录方式有三种：密码（邮箱或用户名）、邮箱验证码、GitHub OAuth。会话存在数据库里，有效期 12 小时，可撤销；Cookie 为 HttpOnly + SameSite=Lax，生产环境加 Secure。写请求校验与会话绑定的 CSRF。修改密码会撤销全部旧会话。
- 公开页面不需要登录，只读取 `HOTKEY_PUBLIC_PUBLICATION_OWNER_ID` 指定的发布账号；未配置时返回 `publication_not_configured`。个人数据按 owner 隔离，跨账户访问返回 404。

## 10. 配置与部署

- **文档预览**：`workspace/` 是独立的 Nextra 静态预览工程，使用 Next.js App Router、React 19 和 Node.js 24；`workspace/content/` 是 Obsidian 知识库。`workspace/public-documents.json` 明确登记可进入公开预览的文档，未登记文件、私密资料、草稿、模板、看板和本机配置不生成页面、搜索或 AI 导出；清单路径及真实路径需校验。私密项目资料由应用后端授权读取，不靠静态站提供权限。GitHub Pages 发布需单独配置和验证。
- **项目知识库（规划，尚未接入）**：按[专项 PRD](workspace/content/product/prd/02-PRD-workspace项目知识库.md)，frontend 的 `/workspace/docs` 将提供正式阅读与编辑入口，复用现有布局和身份；backend 负责文档清单、正文、检索、访问校验与草稿。Markdown/Git 保持内容来源，部署快照显式打包或挂载，Obsidian 使用文档工作副本。现有 Nextra 工程保留作预览；本次 PRD 不代表统一入口、权限或发布已实现。
- 环境文件只放在仓库根目录：本机用 `.env`，生产用 `.env.prod`，模板是 `.env.example`。所有进程都读这一份，进程注入的环境变量优先。
- `docker-compose.yml` 定义应用（API、Web，以及按需启用的 Worker / Scheduler / CLI）；`docker-compose-env.yml` 只在需要全新的 PostgreSQL/Redis/Kafka 时使用；`docker-compose-prod.yml` 通过 include 复用应用定义。
- Web 生产构建为 standalone，以非 root 用户和只读文件系统运行；每个请求生成独立的 CSP nonce。
