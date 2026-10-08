# Ripplesight 技术架构

本文说明 Ripplesight 由哪些部分组成、各部分负责什么、必须遵守哪些技术约定。产品能力与验收标准见[文档工作区](workspace/content/index.md)，工程流程见 [AGENTS](AGENTS.md)，进度见 [BACKLOG](BACKLOG.md)。

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
| 知识库阅读预览 | Compose `workspace`；Nextra 静态构建由 Nginx 提供 | 8668（`/Ripplesight/`） |

API 进程不跑定时器，也不消费消息。同一时间只运行一个 Worker，并且它运行在宿主机上，因为 Codex 登录状态和 MediaCrawler 浏览器都在宿主机。Compose 中容器内的端口统一为 8080，映射到宿主机的 8666/8667。

本机前端、API 与知识库阅读预览统一由 `docker-compose.yml` 的 `frontend`、`backend`、`workspace` 服务启动，三个端口只绑定 localhost。知识库镜像在构建时执行现有文档校验、Nextra 导出与 Pagefind 索引，运行时只包含公开阅读清单的静态产物；它不挂载作者目录或 `.tools/workspace`，也不初始化正式内部知识库。构建使用仓库根目录作为上下文以核对原文链接，专用忽略清单排除凭据、本机状态与依赖缓存。

Compose 本机项目名为 `ripplesight`，生产项目名为 `ripplesight-prod`，容器、网络和自有镜像使用 `ripplesight` 前缀；后端容器用户也使用 `ripplesight`，UID 保持 10001。应用继续使用本机已有数据库及 `HOTKEY_*` 配置。可选环境栈的新数据卷跟随当前 Compose 项目名，已有卷可通过 `HOTKEY_POSTGRES_VOLUME_NAME`、`HOTKEY_REDIS_VOLUME_NAME`、`HOTKEY_KAFKA_VOLUME_NAME` 显式复用；改名不复制、删除或初始化已有数据。

本机默认加载 `docker-compose.override.yml` 开启热更新：API 只读挂载 `backend/app`，由 Uvicorn 重载；Web 只读挂载 `frontend/src`、`public` 与开发配置，使用 Next.js 默认 Turbopack 开发服务器。知识库容器只读读取当前 checkout，将筛选后的文档及链接校验来源复制到容器构建目录；监听变化后自动执行原有校验、静态导出和 Pagefind 索引。构建只读捕获的来源副本，成功后整体切换预览目录并通知浏览器刷新；构建期间的新修改排入下一轮，失败保留上一版。依赖和生成物留在容器内，不回写作者文件，不自动发布内部知识库。验收标准是保存代码或已登记文档后无需人工重建，HTTP 可读到更新，文档正文、检索与 AI 导出保持同版。Web 开发缓存使用独立命名卷，不放入计入容器内存的 tmpfs；开发容器上限 3GiB、Node 堆上限 1536MiB、2 CPU，配合 Turbopack 避免 webpack 持续累积编译内存导致开发子进程重启。更新依赖或 Next.js 版本时可单独清理该缓存卷，业务数据卷不受影响。生产和 CI 显式选择基础 Compose 文件，继续使用只读的生产镜像；环境变量、依赖及数据库结构变化仍按原流程处理。

## 3. 目录

本机父工作区为 `Ripplesight/`，其中 `ripplesight-server/` 是下方的主仓库，`ripplesight-app/` 是尚未初始化的冻结客户端仓库。目录已按新名称迁移；旧名称的符号链接仅为已有工具与会话保留，新配置应使用新路径。

```text
ripplesight-server/
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
└── workspace/                 # 文档与校验工具；保留 Nextra 公开预览及本机文档工具
    └── content/               # Obsidian 知识库
        ├── product/           # 产品文档，按用途使用英文子目录
        │   ├── prd/           # 产品需求：目标、范围与验收要求
        │   ├── plan/          # 历史或专项执行计划，当前任务看BACKLOG
        │   ├── pages/         # 当前页面字段、数量、接口与存储取舍
        │   └── reference/     # 产品参考：核对入口、AI 约定、验证卡及根文件指针
        ├── capabilities/      # 各项能力规格与可用状态
        ├── decisions/         # 生效与历史决策
        ├── records/           # 真实验收记录
        ├── research/          # 调研依据
        ├── templates/         # 文档模板，不发布
        └── views/             # Obsidian 看板，不发布
```

Web 外壳使用 `BasicLayout → PageContainer`：前者管理侧栏、移动导航和会话，后者统一有限高度的正文滚动区与宽度，页脚仅登录页使用；页内标题由页面提供。`LayoutContainer` 只负责横向对齐。滚动引用指向 `PageContainer` 的正文区，路由切换、阅读定位和跳到正文共用该节点；打印恢复自然文档流。全站只保留一个 main，业务页面不另建全屏滚动容器。

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

- RSSHub/SearXNG 聚合服务只连接本机实例，主机只能是 `127.0.0.1`（宿主机）或 `host.docker.internal`（Compose）。平台直连和聚合服务是不同路径；各 HTTP 适配器均强制目标主机白名单，并校验每一次重定向。
- MediaCrawler 作为宿主机子进程运行，使用独立的浏览器和本人账号；浏览器资料目录权限为 700、文件权限为 600；遇到验证码、登录失效或限流就停用。
- 模型只走本机 Codex app-server：每个分析任务启动一个子进程，只读、不需要审批、只传最小环境变量、使用空的工作目录。模型输入一律视为不可信文本，输出必须是结构化结果并经过校验；数字、排序和引用由程序计算。
- 费用、账号、许可等产品边界见 [决策](workspace/content/index.md#决策)。

## 9. API 与身份

- FastAPI 路由注解加 Pydantic 是唯一的接口契约，运行时生成 `/openapi.json`；Web 客户端由它生成，不手写 OpenAPI 或客户端 DTO。
- 每个接口声明唯一的 `operation_id`、中文 summary 和 tag、成功响应模型和实际可能返回的错误。成功时返回资源 DTO、`PageView[T]`（`items` / `next_cursor`）或 `JobAcceptedView`；失败时统一返回 `ErrorView(code, message, request_id, details)`。
- 路径统一是 `/api/*`，不带版本号。日志只记录方法、路由模板、状态码和耗时，不记录 URL 参数、正文、Cookie 或 Token。
- 登录方式有三种：密码（邮箱或用户名）、邮箱验证码、GitHub OAuth。注册仅通过邮箱或 GitHub 验证身份，首次必须设置自选用户名和密码再进入工作台；密码入口只用于已有账号。GitHub 回调与邮箱验证统一导向账户设置，私有页面对未设置密码的会话继续引导设置，业务读写 API 返回 `account_setup_required`，身份验证与凭据设置接口仍可使用。会话存在数据库里，有效期 12 小时，可撤销；Cookie 为 HttpOnly + SameSite=Lax，生产环境加 Secure。写请求校验与会话绑定的 CSRF。修改密码会撤销全部旧会话。
- 公开页面不需要登录，只读取 `HOTKEY_PUBLIC_PUBLICATION_OWNER_ID` 指定的发布账号；未配置时返回 `publication_not_configured`。个人数据按 owner 隔离，跨账户访问返回 404。

## 10. 配置与部署

- **文档预览（当前需求核对入口）**：在 `workspace/` 执行 `pnpm build`、`pnpm preview`，浏览 <http://127.0.0.1:8668/Ripplesight/>。2026-10-07 本轮复用这条已有路径阅读非敏感需求文档，不新增服务实现；作者来源是当前 checkout 的 `workspace/content/`，AI 按需读本机 `workspace/out/raw/`。预览只监听回环地址，不替代内部知识库权限或正式验收。
- **文档工作区**：`workspace/content/` 是普通 Markdown 与 Obsidian 的作者来源，外层保留校验、索引与快照工具。现有 Nextra 静态站及 GitHub Pages 工作流继续保留，按 `workspace/public-documents.json` 控制公开产物，未登记文件、私密资料、草稿、模板、看板和本机配置不生成页面、搜索或 AI 导出。内部知识库独立使用授权快照，既有公开站与 CI 不承载内部权限。
- **项目知识库（本机实现，待真实验收）**：用于项目开发维护，frontend 的 `/workspace/docs` 是内部网页入口，采用 Nextra 文档框架并复用现有布局、身份与访问规则；Editor.js 提供网页编辑视图。具体接口、权限、快照和写入位置见 §11。不采用 GitBook，不另建文档网站；Notion 主来源路线仅作替代方案评估，尚未采用。工程与受控浏览器结果不代表真实账号、Obsidian 或 AI 验收已通过。
- 环境文件只放在仓库根目录：本机用 `.env`，生产用 `.env.prod`，模板是 `.env.example`。所有进程都读这一份，进程注入的环境变量优先。
- `docker-compose.yml` 定义应用（API、Web，以及按需启用的 Worker / Scheduler / CLI）；`docker-compose-env.yml` 只在需要全新的 PostgreSQL/Redis/Kafka 时使用；`docker-compose-prod.yml` 通过 include 复用应用定义。
- Web 生产构建为 standalone，以非 root 用户和只读文件系统运行；每个请求生成独立的 CSP nonce。

## 11. 项目文档知识库接入方案（待审查）

对应[专项 PRD](workspace/content/product/prd/02-PRD-workspace项目知识库.md)与[项目知识库能力](workspace/content/capabilities/07-项目文档知识库.md)。已实现授权接口、Nextra 工作台、Editor.js、持久草稿和本地发布工具；工程与真实验收分别记录，派发状态与环境缺口只维护在 BACKLOG §7。

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

文档框架继续采用 Nextra 4.6.1；frontend 内通过 `compileMdx` / `evaluate` 按普通 Markdown 模式渲染授权原文，使用应用语义组件及主题，不重复挂载全站 Layout。目录、搜索、正文、附件和编辑都调用生成客户端，不把受保护资料编入前端产物。Nextra 公开静态预览与其 Pagefind、AI 导出仍只处理公开清单，不能充当内部访问入口。

仅在本机运行。knowledge 项目文档切片复用会话、UUID 允许清单、同源与 CSRF；通过固定的 Node 文档工具调用现有解析与校验能力。工具根、文档专用 Git 工作副本、持久快照与草稿目录由本机配置明确指定，默认不启用。初始化只创建独立副本，不修改当前开发 checkout；网页与 Obsidian 使用该副本中的 Markdown，原有作者目录不搬迁。发布只提交选择的文档及必要内部清单到本地历史，不推送远端。

Editor.js 与 Markdown 原文视图编辑同一草稿。适配器保留原始块及 frontmatter，支持段落和标题的富文本修改；表格、代码、Mermaid、注释和未知格式保留原文块，不经过既有有损 `markdownToDocument()`。未编辑内容保持原字节。保存携带来源 hash、草稿版本及操作 UUID；发布再检查来源，执行文档校验、固定范围本地 Git 历史与完整快照切换，失败保留草稿和上一快照。结果未知时先读取同一操作记录，禁止自动重试写请求。

### 文档类型与生效规则

一个项目对应一份明确的作者来源、文档清单和版本快照；当前只实现 Ripplesight，不扩展多租户平台。PRD 定义目标与验收，决策记录背景、取舍和影响，PROJECT/AGENTS 保留技术与工程约定，PLAN 组织任务与依赖，BACKLOG 是实际进度唯一来源，records 保留真实验收。关联使用现有相对链接与 `related`，页面按同一快照展示可核对的上下游；不复制进度或另起编号体系。

页面编辑与文档生效分开。PRD/PLAN 普通修订保留 Git 历史；生效决策按现有写作规则生成修订草稿，由本人同意后把旧决策标为废弃并新建替代记录，相关引用和快照一起校验。决策草稿存入受保护草稿层，不擅自扩展作者文件的状态枚举。AI 默认读取已发布的生效规则，明确区分草稿、废弃规则和任务完成状态。

### 来源与快照

作者来源保留普通 Markdown。现有仓库内容使用 `workspace/content/`；公开预览只接受 `workspace/public-documents.json`。内部应用使用 `workspace/internal-documents.json`，与公开清单分别校验：已有公开资料可以进入内部读取快照；新增私密资料的作者目录或 Git 工作副本必须位于受保护存储，不进入当前公开仓库或静态产物。首期没有私密来源时不自动扫描其他目录。

应用清单登记文档路径、分类、源路径、指针路径（如有）、原文 SHA-256、阅读正文 SHA-256、附件及其 hash、来源 Git revision。元数据沿用作者 frontmatter；生成字段不回写作者原文。允许的根文件映射如下：

| 阅读路径 | 唯一作者原文 |
|---|---|
| `product/reference/01-进度与优先级.md` | 根目录 `BACKLOG.md` |
| `product/reference/02-技术架构.md` | 根目录 `PROJECT.md` |
| `product/reference/03-工程规范.md` | 根目录 `AGENTS.md` |

指针说明和根文件正文一起参与页面快照；根文件保留自己的原文 hash，后续编辑与保存只定位到这个源文件。页面快照不是第二份可编辑文档。普通页面的原文读取保留作者文件字节；指针的原文入口返回根文件，另附来源映射。

构建完整的不可变快照目录，包含清单、原文、阅读正文、附件和同版本检索产物。`snapshot_id` 对排序后的清单内容、文件 hash 和来源 revision 求 SHA-256，排除构建时间、绝对主机路径等易变信息；同一来源重建应得到相同标识。登记文件与来源 revision 的字节不一致时标为工作草稿，发布读取拒绝冒充已发布版本；无关业务代码改动不混入文档快照。

只接受清单登记的规范化路径，构建与读取均核对真实路径；越界、符号链接逃逸、缺失附件、损坏 hash 或本地链接失败时拒绝快照。模板、看板、本机配置与未发布草稿不进入读取清单；废弃资料只有显式历史模式可见。运行服务读取快照，不临时扫描开发目录，也不在请求期间混合旧正文与新索引。

首期直接在宿主机运行 API 和 frontend，使用 `workspace/scripts/local.mjs` 初始化独立工作副本与持久目录；配置工具根、来源根及快照根三个绝对路径。目标环境仅为本机，持久状态位于独立本地目录，实际冷启动、重启与上一快照恢复在目标环境任务验收。缺失或损坏快照返回明确的暂不可用错误，不降级到公共静态目录。

### 权限、接口与缓存

已新增 `HOTKEY_WORKSPACE_DOCUMENT_READ_USER_IDS`、`HOTKEY_WORKSPACE_DOCUMENT_WRITE_USER_IDS`、`HOTKEY_WORKSPACE_DOCUMENT_PUBLISH_USER_IDS` 三组 UUID 允许清单；读取默认空，修改和发布还必须具有读取权限。身份 UUID 来自现有已验证会话，不从用户名、客户端字段或公开发布账号推断；配置留在本机，不写入文档或示例真实值。

认证后统一校验权限，再读取目录、标题、摘要、正文、检索片段、附件、下载和 AI 原文。匿名与过期会话按现有身份错误拒绝；已登录但未允许返回 403；允许身份遇到缺配置、身份服务故障或坏快照时返回 503；允许身份请求未登记路径返回 404。所有错误使用稳定 `code`，不得包含未授权的资料信息或服务器绝对路径。修改和发布在对应允许清单之外还复用同源与 CSRF 校验，不能用读取授权替代写授权。

读取路由集中于 `/api/workspace/documents`：目录返回元数据与快照标识；详情和原文接受登记路径及快照标识；附件接受登记附件标识；检索返回同快照的命中与章节。最终路径、DTO 和错误映射以实现生成的 OpenAPI 为准，不手写客户端。frontend 相对文档链接定位到 `/workspace/docs/[...path]`，附件走受保护 API；不把受保护正文复制到 `public/`、静态 raw、公开业务 `/llms.txt` 或 `/mcp`。

目录、正文和附件响应与授权错误统一 `Cache-Control: private, no-store`，不依赖共享 CDN 缓存。可重建的服务端检索索引按快照隔离，每次请求仍先授权；详情指定旧快照时不得静默返回新正文。浏览器在退出、身份变化或权限拒绝时清除文档状态，不缓存已获授权的正文用于后续未授权展示。需要覆盖退出后回看、失败响应与附件出口，不能仅以成功响应的会话依赖头证明缓存安全。

### 原文编辑的宿主位置

网页编辑在同一 backend 的项目文档切片提供草稿与发布接口，复用现有身份和 CSRF。草稿保存在明确的受保护持久位置，携带 source hash、base revision、操作标识；不写只读镜像或临时容器层。本机初始化默认将来源与存储设在被忽略的 `.tools/workspace/`，没有初始化与明确账号配置时全部文档访问关闭。

Git 校验、差异、确认发布和恢复由本机文档工具执行，使用文档专用工作副本及登记路径；不直接操作当前开发 checkout。网页与 Obsidian 的修改进入同一作者来源，指针编辑映射到根文件。批准后生成完整快照，再整体切换服务读取版本；失败保留上一快照和草稿。保存、发布两次检查来源版本，重复操作与结果未知先核对操作记录，不能静默覆盖或盲目重推。文件原子替换、PID 锁、操作 UUID 与准备快照支持重启核对；Git 使用独立索引，快照只从已提交树与本次修改生成。决策替代同时更新旧状态、新记录与内部清单。启动与权限说明见 [本机知识库](workspace/LOCAL.md)。


## 12. 关键词监控工程设计（提案）

本节只保留当前运行链与历史demo接入证据。此前通用候选、四档相关性、扩展适配器和完整分析平台的详细提案已由[页面驱动的收敛方案](workspace/content/product/reference/14-页面驱动的收敛方案.md)替换，不作为当前实施前置。

| 当前链路 | 复用职责 |
|---|---|
| 主题/来源配置 | 现有monitor_topics/versions、source_connections/versions，编辑比较版本，准入由服务校验 |
| 运行/调度 | 原jobs/outbox、租约、预算、到期窗口；页面读取回执和任务，不重建批次平台 |
| 材料/评论 | content身份、正文版本、观察、threads；原文时间和抓取时间分离 |
| 分析/展示 | 当前annotations合同、公开许可投影、事件热度与报告引用；没有数据不编造统计 |

字段、键与查询见[页面数据库设计](workspace/content/product/reference/09-全站页面数据库设计.md)，接口见[当前页面合同](workspace/content/product/reference/08-全站页面接口设计.md)。独立库验证、真实平台和自然小时运行仍分别验收。

### 12.7 Chrome 登录复用的首个可运行 demo

最新用户授权启动真实定时 POC。为隔离既有积压 Job，首轮采用宿主 `cli.keyword_demo` 有界运行器，复用 sources 契约输出；不启动全局 Worker，不修改业务数据库结构。来源适配器只访问 B 站固定 HTTPS 端点，登录来自已部署的本机 Framefetch cookie-source（127.0.0.1），每轮重新获取、只驻留内存、不打印或落盘。桥接 token 仅保存在本机私有 .env 中。桥接断开、登录失效、验证码或限流停止并记录原因，不自动换身份或代理。

POC 数据存于 git 忽略的私有 `.tools/keyword-demo`，原子写入 JSON 状态、按平台 ID 去重并输出转义后的本机 HTML 阅读报告；它是独立验收产物，不是第三份 PRD 或正式业务数据库。首次即运行，此后默认每小时轮询一次，每日最多 60 次来源请求、单轮最多 4 次（登录、搜索、最多两个帖的评论），一次只取一页、窗口 72 小时，结果明确标注抽样与关键词基线。持久化下一次时间、请求预算和停止原因，进程重启不补发密集积压；文件锁防止并行运行。正式账号下的 monitor/Job 集成、语义四档及其他平台不据此标为完成。


### 12.8 Chrome demo 接入现有工作台（2026-10-07 授权实施）

用户要求 demo 跑通后接入真实前后端。本切片保留 `bilibili` 来源键，通过连接版本的固定 API 地址 `https://api.bilibili.com` 区分旧 MediaCrawler 网页入口。Chrome 适配器实现现有 SourceAdapter，搜索与新鲜根评论分别进入 keyword.search / source.comments；继续用 PostgreSQL 的主题、任务、内容、预算与覆盖表，无新表、无第二份正文库。原生适配器版本写入既有 `jobs.scope.source_adapter_version`，由服务端按当次组件政策冻结；旧 MediaCrawler SHA 字段与约束保持不变，不需要 DDL 或业务库迁移。仅按本机显式绑定的 owner UUID 使用 Chrome，会话只在宿主进程内存中短暂存在。

来源设置页提供当前账号应用 Chrome 预设的受保护写接口；未绑定账号拒绝执行。预设每小时、每日 60 次网络请求、单页两帖与每帖最多 20 根评论、00–08 点静默、30 天保留；搜索和评论共用来源预算。实际抓取受取消、连接版本、登录和风控停止约束；小样本始终报告部分覆盖。

单机接管可限定 owner + bilibili，仅扫描该账号的主题日程和评论候选，并从现有 jobs/outbox 执行对应任务，复用 JobExecutionService 的租约、幂等、预算和完成流程，不启动其他账号历史任务。标准 Kafka Worker 保持兼容。原独立 demo 调度在真实链路接管时停止，旧 JSON/页面只保留验收证据。


## 13. 全站页面需求与契约设计（2026-10-08）

本人最新纠正：当前前端视觉实现属于历史冗余，必须从 layout、组件和页面按 Figma 桌面稿重新复现；已有页面文档仅作为接口与数据依赖清单。文档数量、接口数量和表数量均不是交付目标。[页面专项 PRD](workspace/content/product/prd/03-PRD-全站页面需求.md)及单页需求是当前实施入口，旧设计中的扩展不能自动进入实施范围。

[接口设计](workspace/content/product/reference/08-全站页面接口设计.md)按页面读取和提交路径组织；[数据库设计](workspace/content/product/reference/09-全站页面数据库设计.md)逐项说明哪些字段持久化、哪些由查询计算、哪些仅为浏览器状态。撤销上一版预设云收藏、事件关注、独立阅读回执、运行批次、情感快照和告警已读等新表的实施建议。当前 UI 可以使用既有存储，不为每个路由、卡片或计数建表。

阅读主流程、监控闭环、辅助管理与冻结功能分别维护；保留当前调用需要的历史存储，不以“页面不直接读表”为由删除任务、权限、许可、版本或审计。物理删表必须先验证服务、任务、外键与历史数据迁移，按§6在独立库恢复和验证。§12中的四档相关性、候选关联等尚未实现的扩展只作为历史讨论，不是本轮默认前置。

现有 `/topics`、`/monitors/[topicId]`、`/workspace` 共享 TopicsWorkspace，保持一套主题数据和编辑流程。Figma 外壳只由 PageContainer 管理正文滚动和登录页脚，删除无调用者的旧固定 header 插槽；不重新引入全局位置栏。具体取舍、删除证据与后续清理门槛见[页面驱动的收敛方案](workspace/content/product/reference/14-页面驱动的收敛方案.md)。
