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
| knowledge | Obsidian 业务导出、检索与问答；项目文档切片规划见 §11 |
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
- **项目知识库（规划，尚未接入）**：frontend 的 `/workspace/docs` 将提供正式阅读与编辑入口；具体来源、接口、权限、快照和写入位置见 §11。现有 Nextra 工程保留作预览，工程结果不代表统一入口、权限或双端编辑已实现。
- 环境文件只放在仓库根目录：本机用 `.env`，生产用 `.env.prod`，模板是 `.env.example`。所有进程都读这一份，进程注入的环境变量优先。
- `docker-compose.yml` 定义应用（API、Web，以及按需启用的 Worker / Scheduler / CLI）；`docker-compose-env.yml` 只在需要全新的 PostgreSQL/Redis/Kafka 时使用；`docker-compose-prod.yml` 通过 include 复用应用定义。
- Web 生产构建为 standalone，以非 root 用户和只读文件系统运行；每个请求生成独立的 CSP nonce。

## 11. 项目文档知识库接入方案（待审查）

对应[专项 PRD](workspace/content/product/prd/02-PRD-workspace项目知识库.md)与[项目知识库能力](workspace/content/capabilities/07-项目文档知识库.md)。以下是后续实现约定，接口、配置项、快照和草稿功能尚未实现；派发状态与环境缺口只维护在 BACKLOG §7。

### 现有代码与复用边界

| 已核对的来源 | 可复用 | 本专项需要补齐 |
|---|---|---|
| [工作台页面](frontend/src/app/workspace/page.tsx)、[BasicLayout](frontend/src/layout/basic-layout.tsx) | 站内入口、全局侧栏、主题、滚动容器与语义 UI | `/workspace/docs` 目录、详情、章节导航和五种页面状态 |
| [身份 DTO](backend/app/identity/schemas.py)、[身份依赖](backend/app/api/dependencies.py) | 已验证会话的用户 UUID、同源与 CSRF 校验 | 用户只有身份，没有项目文档权限；增加明确的读取、修改和发布允许清单 |
| [Web 门禁](frontend/src/proxy.ts)、[会话上下文](frontend/src/components/auth/session-context.tsx) | 页面登录门禁、CSP、`private, no-store`、站内会话展示 | 文档 API 独立授权；页面会话不能证明文档访问已获允许 |
| [阅读器](frontend/src/components/editor/viewer.tsx)、[内容渲染](frontend/src/components/editor/content.ts) | 已有 marked、sanitize-html 和 rich-content 样式 | 当前 Markdown 先转成块数据，存在格式损失；文档直接解析 Markdown，生成稳定目录与锚点，清理 HTML 与链接 |
| [knowledge 服务](backend/app/knowledge/services.py) | 现有知识库领域归属 | 当前处理日报业务导出；项目文档以独立切片组织，不复用业务导出对象、作业或公开索引 |
| [后端镜像](backend/Dockerfile)、[Compose](docker-compose.yml) | API 进程、非 root 用户、只读容器 | 镜像只复制 backend；不能假定运行目录能访问 workspace，需明确挂载经过验证的快照 |

读取服务放在 `backend/app/knowledge/` 的项目文档切片，DTO 不依赖 ORM；HTTP 路由位于 `api/routers`，由 `api/dependencies.py` 装配。出现实际使用方时再创建模块，不新建顶层领域或空包。frontend 继续只调用同版本 OpenAPI 生成的 `src/api` 函数。

### 来源与快照

作者来源保留普通 Markdown。现有仓库内容使用 `workspace/content/`；公开预览仍只接受 `workspace/public-documents.json`。内部应用清单与公开预览清单分别校验：已有公开资料可以进入内部读取快照；新增私密资料的作者目录或 Git 工作副本必须位于受保护存储，不进入当前公开仓库或静态产物。首期没有私密来源时不自动扫描其他目录。

应用清单登记文档路径、分类、源路径、指针路径（如有）、原文 SHA-256、阅读正文 SHA-256、附件及其 hash、来源 Git revision。元数据沿用作者 frontmatter；生成字段不回写作者原文。允许的根文件映射如下：

| 阅读路径 | 唯一作者原文 |
|---|---|
| `product/01-进度与优先级.md` | 根目录 `BACKLOG.md` |
| `product/02-技术架构.md` | 根目录 `PROJECT.md` |
| `product/03-工程规范.md` | 根目录 `AGENTS.md` |

指针说明和根文件正文一起参与页面快照；根文件保留自己的原文 hash，后续编辑与保存只定位到这个源文件。页面快照不是第二份可编辑文档。普通页面的原文读取保留作者文件字节；指针的原文入口返回根文件，另附来源映射。

构建完整的不可变快照目录，包含清单、原文、阅读正文、附件和同版本检索产物。`snapshot_id` 对排序后的清单内容、文件 hash 和来源 revision 求 SHA-256，排除构建时间、绝对主机路径等易变信息；同一来源重建应得到相同标识。登记文件与来源 revision 的字节不一致时标为工作草稿，发布读取拒绝冒充已发布版本；无关业务代码改动不混入文档快照。

只接受清单登记的规范化路径，构建与读取均核对真实路径；越界、符号链接逃逸、缺失附件、损坏 hash 或本地链接失败时拒绝快照。模板、看板、本机配置与未发布草稿不进入读取清单；废弃资料只有显式历史模式可见。运行服务读取快照，不临时扫描开发目录，也不在请求期间混合旧正文与新索引。

首期参考环境使用现有 Compose 的 backend，显式配置 `HOTKEY_WORKSPACE_DOCUMENT_SNAPSHOT_ROOT`，将单个已验证快照挂载到容器绝对目录并设为只读；frontend 镜像不携带正文。目标部署环境和路径由 Stephen 确认，实际冷启动、重启与上一快照恢复在目标环境任务验收。缺失或损坏快照返回明确的暂不可用错误，不降级到公共静态目录。

### 权限、接口与缓存

规划新增 `HOTKEY_WORKSPACE_DOCUMENT_READ_USER_IDS`、`HOTKEY_WORKSPACE_DOCUMENT_WRITE_USER_IDS`、`HOTKEY_WORKSPACE_DOCUMENT_PUBLISH_USER_IDS` 三组 UUID 允许清单；读取默认空，修改和发布还必须具有读取权限。身份 UUID 来自现有已验证会话，不从用户名、客户端字段或公开发布账号推断；配置留在本机或部署环境，不写入文档或示例真实值。

认证后统一校验权限，再读取目录、标题、摘要、正文、检索片段、附件、下载和 AI 原文。匿名与过期会话按现有身份错误拒绝；已登录但未允许返回 403；允许身份遇到缺配置、身份服务故障或坏快照时返回 503；允许身份请求未登记路径返回 404。所有错误使用稳定 `code`，不得包含未授权的资料信息或服务器绝对路径。修改和发布在对应允许清单之外还复用同源与 CSRF 校验，不能用读取授权替代写授权。

读取路由集中于 `/api/workspace/documents`：目录返回元数据与快照标识；详情和原文接受登记路径及快照标识；附件接受登记附件标识；检索返回同快照的命中与章节。最终路径、DTO 和错误映射以实现生成的 OpenAPI 为准，不手写客户端。frontend 相对文档链接定位到 `/workspace/docs/[...path]`，附件走受保护 API；不把受保护正文复制到 `public/`、静态 raw、公开业务 `/llms.txt` 或 `/mcp`。

目录、正文和附件响应与授权错误统一 `Cache-Control: private, no-store`，不依赖共享 CDN 缓存。可重建的服务端检索索引按快照隔离，每次请求仍先授权；详情指定旧快照时不得静默返回新正文。浏览器在退出、身份变化或权限拒绝时清除文档状态，不缓存已获授权的正文用于后续未授权展示。需要覆盖退出后回看、失败响应与附件出口，不能仅以成功响应的会话依赖头证明缓存安全。

### 原文编辑的宿主位置

后续编辑在同一 backend 的项目文档切片提供草稿与发布接口，复用现有身份和 CSRF。草稿保存在明确的受保护持久位置，携带 source hash、base revision、操作标识；不写只读镜像或临时容器层。写入存储和源仓库位置尚待确认，阅读阶段不开放这些配置和写操作。

Git 校验、差异、确认发布和恢复由宿主机上的维护流程执行，使用文档专用工作副本及登记路径；不直接操作当前开发 checkout。网页与 Obsidian 的修改进入同一作者来源，指针编辑映射到根文件。批准后生成完整快照，再整体切换服务读取版本；失败保留上一快照和草稿。保存、发布两次检查来源版本，重复操作与结果未知先核对操作记录，不能静默覆盖或盲目重推。具体持久化、锁与操作恢复在编辑设计任务审查后实现。
