# Ripplesight 技术架构

本文说明 Ripplesight 由哪些部分组成、各部分负责什么、必须遵守哪些技术约定。产品能力与验收标准见[文档工作区](docs/index.md)，工程流程见 [AGENTS](AGENTS.md)，进度见 [BACKLOG](BACKLOG.md)。

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

本机前端与 API 由 Compose 的 frontend、backend 服务启动，仅绑定 localhost。项目文档回归 docs/ 下的 Markdown/Git 管理，由 Obsidian 或编辑器直接阅读和修改，不运行文档网站。

Compose 本机项目名为 `ripplesight`，生产项目名为 `ripplesight-prod`，容器、网络和自有镜像使用 `ripplesight` 前缀；后端容器用户也使用 `ripplesight`，UID 保持 10001。应用继续使用本机已有数据库及 `HOTKEY_*` 配置。可选环境栈的新数据卷跟随当前 Compose 项目名，已有卷可通过 `HOTKEY_POSTGRES_VOLUME_NAME`、`HOTKEY_REDIS_VOLUME_NAME`、`HOTKEY_KAFKA_VOLUME_NAME` 显式复用；改名不复制、删除或初始化已有数据。

本机默认加载 `docker-compose.override.yml` 开启热更新：API 只读挂载 `backend/app`，由 Uvicorn 重载；Web 只读挂载 `frontend/src`、`public` 与开发配置，使用 Next.js 默认 Turbopack 开发服务器。Web 开发缓存使用独立命名卷，不放入计入容器内存的 tmpfs；开发容器上限 3GiB、Node 堆上限 1536MiB、2 CPU，配合 Turbopack 避免 webpack 持续累积编译内存导致开发子进程重启。更新依赖或 Next.js 版本时可单独清理该缓存卷，业务数据卷不受影响。生产和 CI 显式选择基础 Compose 文件，继续使用只读的生产镜像；环境变量、依赖及数据库结构变化仍按原流程处理。

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
├── scripts/docs/             # 本机 Markdown 索引与链接校验工具
└── docs/                     # 唯一项目文档目录，也是 Obsidian vault
    ├── .obsidian/            # 共享链接、模板与核心插件配置
    ├── product/              # prd / plan / pages / reference
    ├── capabilities/         # 能力规格与状态
    ├── decisions/            # 生效与历史决策
    ├── records/              # 验收记录
    ├── research/             # 调研依据
    ├── templates/            # 文档模板
    ├── views/                # Obsidian Bases 看板
    └── designs/              # 设计参考
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
- 费用、账号、许可等产品边界见 [决策](docs/index.md#决策)。

## 9. API 与身份

- FastAPI 路由注解加 Pydantic 是唯一的接口契约，运行时生成 `/openapi.json`；Web 客户端由它生成，不手写 OpenAPI 或客户端 DTO。
- 每个接口声明唯一的 `operation_id`、中文 summary 和 tag、成功响应模型和实际可能返回的错误。成功时返回资源 DTO、`PageView[T]`（`items` / `next_cursor`）或 `JobAcceptedView`；失败时统一返回 `ErrorView(code, message, request_id, details)`。
- 路径统一是 `/api/*`，不带版本号。日志只记录方法、路由模板、状态码和耗时，不记录 URL 参数、正文、Cookie 或 Token。
- 登录方式有三种：密码（邮箱或用户名）、邮箱验证码、GitHub OAuth。注册仅通过邮箱或 GitHub 验证身份，首次必须设置自选用户名和密码再进入工作台；密码入口只用于已有账号。GitHub 回调与邮箱验证统一导向账户设置，私有页面对未设置密码的会话继续引导设置，业务读写 API 返回 `account_setup_required`，身份验证与凭据设置接口仍可使用。会话存在数据库里，有效期 12 小时，可撤销；Cookie 为 HttpOnly + SameSite=Lax，生产环境加 Secure。写请求校验与会话绑定的 CSRF。修改密码会撤销全部旧会话。
- 公开页面不需要登录，只读取 `HOTKEY_PUBLIC_PUBLICATION_OWNER_ID` 指定的发布账号；未配置时返回 `publication_not_configured`。个人数据按 owner 隔离，跨账户访问返回 404。

## 10. 配置与部署

- **项目文档**：普通 Markdown 唯一原文在 docs/，Obsidian 直接打开 docs；BACKLOG、PROJECT、AGENTS 保持仓库根文件原文。索引与链接校验在 scripts/docs/，不生成网页或数据库正文副本。业务报告的 Obsidian 导出继续使用 knowledge/obsidian.py。
- 环境文件只放在仓库根目录：本机用 `.env`，生产用 `.env.prod`，模板是 `.env.example`。所有进程都读这一份，进程注入的环境变量优先。
- `docker-compose.yml` 定义应用（API、Web，以及按需启用的 Worker / Scheduler / CLI）；`docker-compose-env.yml` 只在需要全新的 PostgreSQL/Redis/Kafka 时使用；`docker-compose-prod.yml` 通过 include 复用应用定义。
- Web 生产构建为 standalone，以非 root 用户和只读文件系统运行；每个请求生成独立的 CSP nonce。

## 11. 项目文档知识库接入方案（待审查）

2026-10-08 用户撤销在线项目知识库，恢复 docs 下的 Markdown/Git 管理并保留 Obsidian。原 Nextra 文档站、Pagefind/AI 站点导出、Editor.js 网页编辑、项目文档 API、专用副本与快照发布工具退役；不再新增账号或发布流程。旧专项 PRD 与 PLAN 标为废弃，历史证据保留供追溯。

Obsidian 直接编辑 docs 中的原文，保留 frontmatter、标准 Markdown 相对链接、templates、views 与共享 .obsidian 配置。根文件只保留指针，仍在仓库根目录修改；不另存可编辑正文副本。index.md 由本机索引脚本更新，Git diff 负责审阅变化。索引和检查命令见 docs/README.md。

业务报告、资讯和评论的 Obsidian 导出属于产品能力，与项目文档网站分离，保留现有 knowledge/obsidian.py、配置、CLI 与测试。已有 .tools/workspace 的私密来源、草稿和本机历史不自动迁入公开 docs，也不删除；如有本机状态，按 docs/README 的说明手工审阅。

## 12. 关键词监控工程设计（提案）

本节只保留当前运行链与历史demo接入证据。此前通用候选、四档相关性、扩展适配器和完整分析平台的详细提案已由[页面驱动的收敛方案](docs/product/reference/14-页面驱动的收敛方案.md)替换，不作为当前实施前置。

| 当前链路 | 复用职责 |
|---|---|
| 主题/来源配置 | 现有monitor_topics/versions、source_connections/versions，编辑比较版本，准入由服务校验 |
| 运行/调度 | 原jobs/outbox、租约、预算、到期窗口；页面读取回执和任务，不重建批次平台 |
| 材料/评论 | content身份、正文版本、观察、threads；原文时间和抓取时间分离 |
| 分析/展示 | 当前annotations合同、公开许可投影、事件热度与报告引用；没有数据不编造统计 |

字段、键与查询见[页面数据库设计](docs/product/reference/09-全站页面数据库设计.md)，接口见[当前页面合同](docs/product/reference/08-全站页面接口设计.md)。独立库验证、真实平台和自然小时运行仍分别验收。

### 12.7 Chrome 登录复用的首个可运行 demo

最新用户授权启动真实定时 POC。为隔离既有积压 Job，首轮采用宿主 `cli.keyword_demo` 有界运行器，复用 sources 契约输出；不启动全局 Worker，不修改业务数据库结构。来源适配器只访问 B 站固定 HTTPS 端点，登录来自已部署的本机 Framefetch cookie-source（127.0.0.1），每轮重新获取、只驻留内存、不打印或落盘。桥接 token 仅保存在本机私有 .env 中。桥接断开、登录失效、验证码或限流停止并记录原因，不自动换身份或代理。

POC 数据存于 git 忽略的私有 `.tools/keyword-demo`，原子写入 JSON 状态、按平台 ID 去重并输出转义后的本机 HTML 阅读报告；它是独立验收产物，不是第三份 PRD 或正式业务数据库。首次即运行，此后默认每小时轮询一次，每日最多 60 次来源请求、单轮最多 4 次（登录、搜索、最多两个帖的评论），一次只取一页、窗口 72 小时，结果明确标注抽样与关键词基线。持久化下一次时间、请求预算和停止原因，进程重启不补发密集积压；文件锁防止并行运行。正式账号下的 monitor/Job 集成、语义四档及其他平台不据此标为完成。


### 12.8 Chrome demo 接入现有工作台（2026-10-07 授权实施）

用户要求 demo 跑通后接入真实前后端。本切片保留 `bilibili` 来源键，通过连接版本的固定 API 地址 `https://api.bilibili.com` 区分旧 MediaCrawler 网页入口。Chrome 适配器实现现有 SourceAdapter，搜索与新鲜根评论分别进入 keyword.search / source.comments；继续用 PostgreSQL 的主题、任务、内容、预算与覆盖表，无新表、无第二份正文库。原生适配器版本写入既有 `jobs.scope.source_adapter_version`，由服务端按当次组件政策冻结；旧 MediaCrawler SHA 字段与约束保持不变，不需要 DDL 或业务库迁移。仅按本机显式绑定的 owner UUID 使用 Chrome，会话只在宿主进程内存中短暂存在。

来源设置页提供当前账号应用 Chrome 预设的受保护写接口；未绑定账号拒绝执行。预设每小时、每日 60 次网络请求、单页两帖与每帖最多 20 根评论、00–08 点静默、30 天保留；搜索和评论共用来源预算。实际抓取受取消、连接版本、登录和风控停止约束；小样本始终报告部分覆盖。

单机接管可限定 owner + bilibili，仅扫描该账号的主题日程和评论候选，并从现有 jobs/outbox 执行对应任务，复用 JobExecutionService 的租约、幂等、预算和完成流程，不启动其他账号历史任务。标准 Kafka Worker 保持兼容。原独立 demo 调度在真实链路接管时停止，旧 JSON/页面只保留验收证据。


## 13. 全站页面需求与契约设计（2026-10-08）

本人最新纠正：当前前端视觉实现属于历史冗余，必须从 layout、组件和页面按 Figma 桌面稿重新复现；已有页面文档仅作为接口与数据依赖清单。文档数量、接口数量和表数量均不是交付目标。[页面专项 PRD](docs/product/prd/03-PRD-全站页面需求.md)及单页需求是当前实施入口，旧设计中的扩展不能自动进入实施范围。

[接口设计](docs/product/reference/08-全站页面接口设计.md)按页面读取和提交路径组织；[数据库设计](docs/product/reference/09-全站页面数据库设计.md)逐项说明哪些字段持久化、哪些由查询计算、哪些仅为浏览器状态。撤销上一版预设云收藏、事件关注、独立阅读回执、运行批次、情感快照和告警已读等新表的实施建议。当前 UI 可以使用既有存储，不为每个路由、卡片或计数建表。

阅读主流程、监控闭环、辅助管理与冻结功能分别维护；保留当前调用需要的历史存储，不以“页面不直接读表”为由删除任务、权限、许可、版本或审计。物理删表必须先验证服务、任务、外键与历史数据迁移，按§6在独立库恢复和验证。§12中的四档相关性、候选关联等尚未实现的扩展只作为历史讨论，不是本轮默认前置。

现有 `/topics`、`/monitors/[topicId]`、`/workspace` 共享 TopicsWorkspace，保持一套主题数据和编辑流程。Figma 外壳只由 PageContainer 管理正文滚动和登录页脚，删除无调用者的旧固定 header 插槽；不重新引入全局位置栏。具体取舍、删除证据与后续清理门槛见[页面驱动的收敛方案](docs/product/reference/14-页面驱动的收敛方案.md)。

### CI生产底线（2026-10-08）

CI只验证当前锁定运行栈，不扩展旧版本、旧卷名或多系统兼容矩阵。frontend执行完整静态检查、交互回归与构建；contract仅执行同提交运行API的生成客户端漂移及传输层专项，不重复全套Web测试；backend使用隔离hotkey_test_*库、唯一schema和实际Redis/Kafka/MinIO做全量回归；runtime使用生产镜像验证依赖、HTTP代理、会话/CSRF、动态CSP、Worker及非root只读边界。公开文档保留内容校验、工具测试、构建与发布，镜像测试使用隔离Git夹具而不依赖Docker上下文携带仓库元数据。CI成功不替代Figma视觉、真实提供方和长期服务验收。
