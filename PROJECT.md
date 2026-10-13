# Ripplesight 技术架构

本文说明 Ripplesight 由哪些部分组成、各部分负责什么、必须遵守哪些技术约定。产品能力与验收标准见[文档工作区](docs/index.md)，工程流程见 [AGENTS](AGENTS.md)，进度见 [BACKLOG](BACKLOG.md)。

## 1. 技术栈

逐评论analysis.comment.v1复用analysis.annotate Job与content_annotations。content领域负责已采评论分页、原帖/直接父链冻结及版本复核，analysis只消费纯DTO。观察manifest的post_observations记录实际原帖，comment_observations记录目标与可得祖先；评论独立状态含insufficient/unknown/deferred，非有效结论保持relevant=null。canonical schema只用于全新独立测试库，本次不升级业务库。帖子事件、报告、告警保持帖子提示版本范围。analysis_comment_scan_cursors只保存主题规则、原帖版本/评论分页游标与invalid补偿轮转位置，每轮最多50个原帖版本、500个评论节点、20个新任务，循环扫描上下文变更，不保存正文。

| 部分 | 技术 |
|---|---|
| 后端 | Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、psycopg 3；依赖用 uv 管理（`pyproject.toml` + `uv.lock`） |
| Web | Node.js 24、pnpm 12、Next.js 16（App Router）、React 19、TypeScript、Tailwind、shadcn/ui + Radix、Axios |
| 数据 | PostgreSQL（业务数据唯一来源）、Redis（可重建缓存、限流及待单独评审的短期OAuth流程状态）、Kafka（持久任务消息）、MinIO（证据与文件） |
| 后台任务 | 独立 Worker 进程消费 Kafka；独立 Scheduler 进程用 APScheduler 每 30 秒扫描到期任务 |
| 本机外部服务 | RSSHub（1200）、SearXNG（8888）、Firecrawl（3002）、MediaCrawler（宿主子进程）、Codex app-server（宿主子进程） |
| 质量工具 | 后端 Ruff、mypy、pytest；Web 端 ESLint、Prettier、tsc、Vitest、生产构建 |

关键词定时整来源跳过的逐查询受理计划保存在既有collection_due_windows.query_plan可空JSONB，包含本轮最新准入判定时已领取的主题版本、完整候选与来源原因；历史无快照与恢复中的较早跳过/漏轮保持未知，不创建假Job或第二套采集账本。仅规范SQL全新独立测试库执行新增列与约束，业务库升级仍按§6。

手动全部来源跳过的操作证据由monitors领域monitor_topic_run_skips保存，主键为owner与operation_id，外键绑定所属主题及冻结版本，JSONB保存完整只读回执。仅实际全部跳过时写入；已受理/部分受理仍以既有Job scope为依据，不复制任务或预算账本。沿用原操作事务锁保证首次判定与重放，旧失败不倒填；同操作不能因改词或来源恢复而发起新任务。首次全跳过返回200，实际新任务受理返回202，重放返回200；再次尝试须显式使用新操作编号。结构升级仍按§6。

原帖v2逐维校验复用content_annotations.dimension_results可空JSONB，与当前相关性平面投影同事务写入；各维首个有效值及调用出处独立保留，旧无逐维记录不倒填。调用须匹配本人同冻结任务输入，资料标注面板只读展示状态；规范SQL仅用于全新独立测试库，业务库升级仍按§6。

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

Compose 使用 `docker-compose.yml` 中的构建镜像。修改源码或依赖后重新构建对应服务；需要热更新时，按 backend/README.md 或 frontend/README.md 在宿主机启动开发服务。环境变量和数据库结构变化分别按配置与数据库流程处理。

## 3. 目录

本机父工作区为 `Ripplesight/`，其中 `ripplesight-server/` 是下方的主仓库，`ripplesight-app/` 是尚未初始化的冻结客户端仓库。工具和配置统一使用这两个仓库路径。

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
│   ├── sql/schema.sql         # 唯一的完整建表脚本
│   └── tests/                 # unit / integration / architecture
├── frontend/
│   ├── src/app/               # 路由；页面专属组件放在路由下的 components/
│   ├── src/components/        # ui/（shadcn 基础组件）及按功能划分的复用组件
│   ├── src/layout/            # 全站外壳
│   ├── src/api/               # 由 OpenAPI 生成的客户端（不要手改）
│   ├── src/request.ts         # 唯一的 HTTP 传输层
│   ├── src/proxy.ts           # 会话门禁与 CSP
│   └── tests/                 # 前端测试
└── docs/                     # 唯一项目文档目录，也是 Obsidian vault
    ├── index.md              # 知识库入口与使用说明
    ├── requirement/          # 原始意图、详细业务要求与验收依据
    ├── design/               # 目标架构、数据/接口/事务及交互设计
    ├── prd/                  # 面向开发人员的产品交接：价值、流程、故事和验收
    ├── plan/                 # 面向 agent 的任务、依赖、验证及停止条件
    ├── research/             # 调研证据与限制；不代替需求或开发交接
    ├── templates/            # 四类可选模板
    ├── views/文档.base       # Obsidian 文档视图
    └── .obsidian/            # 共享配置；个人布局与缓存继续忽略
```

Web 外壳使用 `BasicLayout → PageContainer`：前者管理侧栏、移动导航和会话，后者统一有限高度的正文滚动区与宽度，页脚仅登录页使用；页内标题由页面提供。`LayoutContainer` 只负责横向对齐。滚动引用指向 `PageContainer` 的正文区，路由切换、阅读定位和跳到正文共用该节点；打印恢复自然文档流。全站只保留一个 main，业务页面不另建全屏滚动容器。

采集身份计量由content服务基于保留观察历史计算，jobs仅投影DTO；Web复用`components/collection/identity-counts.tsx`供覆盖详情与关键词/评论任务详情消费，不复制统计账本。

单轮执行差分复用job_attempts的job+lease_epoch边界，新领取标记collection_counts_tracked，并以可空collection_observed_count保存已原子提交页面的上游增量。content_observations.execution_epoch可空外键绑定实际执行；重放不改原归属，旧记录不回填。content一次历史查询按明确归属投影最近20轮身份计量，jobs只读输出，Web与整个任务累计分别展示。规范SQL仅用于全新独立测试库，业务库升级遵守§6。

列表逐轮摘要复用`components/collection/job-collection-counts.tsx`的显式GET与取消/失权边界，单轮展示统一在`components/collection/execution-counts.tsx`，任务详情消费同一组件。任务记录、覆盖窗口、受理任务及发现关系只用明确任务引用；不新增采集、计量查询或账本。

报告列表与详情共用全部冻结输入许可检查，导出状态与下载同样复核当前许可；事件成员列表与计数只包含当前可读集合，partial不携带受限成员引用或数量。

事件修订差分由events领域在既有分组评估记录的可空JSONB结果中原子冻结，关联实际事件修订、此前修订及新成员/事实身份；不建立第二份材料或事实账本。事实读取在当前许可下投影差分，统计由程序从冻结分类计算。旧记录无结果不倒填；模型补证/重复判断及实际可读证据分别核对。

普通页头复用 `components/system/page-header.tsx` 的 `PageHeader`，统一标题、可选说明、操作与详情面包屑；面包屑直接组合现有 shadcn 基础组件。空状态由 `PageState` 组合 `Empty`，说明与操作均按当前场景提供，不自动添加无关跳转或技术诊断。刊物报头与登录表单保留专用排版。

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
| knowledge | Obsidian 业务报告导出、检索与问答 |
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

CORE-01恢复目标按设计10分为独立账本、隔离重放、身份/对象及全入口屏障、最终追赶与切换。R1提供版本化完整资源拒读交换合同及随机新临时库复演，evidence提供调用者事务内重放接口，成功仍固定不允许开放服务。R2按PLAN-10内嵌SPEC先落实独立账本事务及只读重放消费者，再接通全部在线写入/读取/副作用；不把交换样本或部分接入当线上权威。账本目标为独立PG实例/专库、凭据和备份生命周期；实际故障域、身份/对象恢复及最终切换仍需验收。

这是完整账本/恢复方案内的依赖，不是核心业务的统一开工顺序；排期见BACKLOG。正常owner/当前许可/完整依赖、删除决定可靠保存与独立最小记录、停止及副作用幂等仍是业务硬门槛。未部署完整恢复能力时，恢复目标不得进入业务身份、API/Worker/Scheduler、队列及对象外发；只有该操作范围的当前限制/身份和副作用复核通过才可评审开放。已接入独立reader的路径强制配置和故障拒绝保持不变，不借排期后置恢复旧allow。

- `backend/sql/schema.sql` 是唯一的建表来源，自带 `BEGIN/COMMIT`，只用于全新的空库。不用 Alembic，不用 ORM 建表，也不用 SQLite 存业务数据。所有时间字段使用 `TIMESTAMPTZ`。
- 独立拒绝账本由evidence持有，唯一DDL为`backend/sql/journal.sql`，只用于另一个全新空账本库；不导入业务schema、不进入业务metadata/dump、没有业务FK。R2-A交付最小head/events、受限原子追加函数及R1只读消费者；共用交换合同归evidence，删除backups的重复归属文件。业务库唯一schema规则保持不变。运行角色不能改历史/重建epoch，缺独立pin/head必须拒绝；R2-B全部在线消费者未就绪前不接管业务删除，不提供双写/失败回退。具体合同见PLAN-10内嵌SPEC；同机独立测试库不证明生产故障域或历史覆盖。
- 独立账本唯一性损坏反例需要在已验证的自有测试库临时移除唯一约束；架构门禁仅允许`tests/integration/test_independent_journal.py`的`test_online_rejects_duplicate_owner_operation_even_with_valid_chain`中一次确切的`ALTER TABLE restriction_journal.events DROP CONSTRAINT events_owner_id_operation_id_key`。其他文件、函数或DDL仍拒绝，并以反例验证边界。这是受控故障注入，不是建表来源或业务迁移；测试库结束后删除。
- 改表结构时，SQL、ORM 模型和结构断言要在同一次提交里更新，并在一个全新的 PostgreSQL 上核对所有表的列、类型、可空性和主键。
- 业务库名固定为 `hotkey`。测试只用独立的 `hotkey_test_<后缀>` 库，用完删除；绝不能在业务库上跑测试。
- 备份恢复验证从`hotkey_test_`源库恢复时，自动创建`hotkey_test_restore_<随机编号>`目标，用后删除；其他源库保留`hotkey_restore_`命名。测试环境的维护恢复配置仅接受本机独立测试源和独立`hotkey_test_restore_`入口，正常环境保留既有恢复入口限制。入口与真正恢复目标分别核对，不能只检查主测试库；既存恢复库不得作为测试清理对象。
- **升级有数据的库**：先停写并备份，在新库上实际隔离恢复一遍，确认结构与数据；再建一个全新空库、执行完整的 `schema.sql`、导入并核对数据（各表行数、外键、任务和预算等）；全部核对无误，且当前删除/撤权、身份和副作用围栏均通过才切换。旧库可保留为隔离回退候选，不可直接恢复旧授权/任务；回退也须复核切换后新增的限制。禁止直接在旧库上执行 `schema.sql`，不能借灾备排期后置跳过该操作范围的恢复验证。

## 7. 任务与可靠性

- 业务状态和 Outbox 写在同一个 PostgreSQL 事务里，由 Outbox 发布到 Kafka。Worker 在业务提交后才提交 offset，通过消息 ID、租约和唯一约束保证重复消费也不会重复写入。
- Worker 父进程独占 Kafka 消费和任务的最终状态；每个任务在 `spawn` 出的子进程里执行，子进程自己建立数据库连接。任务取消、超时或进程异常退出时，回收整个进程组。
- 持久的重试和预算由 `jobs` 管理；适配器内部只做有限次数的安全重试。状态不明的外部发送不会自动重发。

## 8. 外部来源与模型

- RSSHub/SearXNG 聚合服务只连接本机实例，主机只能是 `127.0.0.1`（宿主机）或 `host.docker.internal`（Compose）。平台直连和聚合服务是不同路径；各 HTTP 适配器均强制目标主机白名单，并校验每一次重定向。
- MediaCrawler 桥保留固定版本核验和本地已保存样本/评论读取。其搜索子进程目前只有整批预算预扣与轮询终止，缺逐 HTTP 请求准入，线上搜索工厂在启动前拒绝；补齐逐请求保护并验证后才恢复。B站实时采集使用具备逐请求回调的本人本机 Chrome 方式；浏览器资料目录权限为 700、文件权限为 600，遇到验证码、登录失效或限流就停用。
- 模型只走本机 Codex app-server：每个分析任务启动一个子进程，只读、不需要审批、只传最小环境变量、使用空的工作目录。模型输入一律视为不可信文本，输出必须是结构化结果并经过校验；数字、排序和引用由程序计算。
- 费用、账号、许可等产品边界见 [产品边界](docs/requirement/00-产品目标与边界.md#已确认边界)。

## 9. API 与身份

来源能力API的search_contract是connections领域派生的当前路径说明，包含预设/连接依据、查询种子方式、三组词/语言/窗口的处理与范围限制；不保存为新账本、不改变任务请求或倒填旧Job。主题新建/编辑与来源页复用此合同，准入及真实完成仍由原能力状态与任务回执证明。

- FastAPI 路由注解加 Pydantic 是唯一的接口契约，运行时生成 `/openapi.json`；Web 客户端由它生成，不手写 OpenAPI 或客户端 DTO。
- 每个接口声明唯一的 `operation_id`、中文 summary 和 tag、成功响应模型和实际可能返回的错误。成功时返回资源 DTO、`PageView[T]`（`items` / `next_cursor`）或 `JobAcceptedView`；失败时统一返回 `ErrorView(code, message, request_id, details)`。
- 路径统一是 `/api/*`，不带版本号。日志只记录方法、路由模板、状态码和耗时，不记录 URL 参数、正文、Cookie 或 Token。
- 登录方式有三种：密码（邮箱或用户名）、邮箱验证码、GitHub OAuth。注册仅通过邮箱或 GitHub 验证身份，首次必须设置自选用户名和密码再进入工作台；密码入口只用于已有账号。GitHub 回调与邮箱验证统一导向账户设置，私有页面对未设置密码的会话继续引导设置，业务读写 API 返回 `account_setup_required`，身份验证与凭据设置接口仍可使用。会话存在数据库里，有效期 12 小时，可撤销；Cookie 为 HttpOnly + SameSite=Lax，生产环境加 Secure。写请求校验与会话绑定的 CSRF。修改密码会撤销全部旧会话。
- 公开页面不需要登录，只读取 `HOTKEY_PUBLIC_PUBLICATION_OWNER_ID` 指定的发布账号；未配置时返回 `publication_not_configured`。个人数据按 owner 隔离，跨账户访问返回 404。

## 10. 配置与部署

- **项目文档**：docs/ 是 Markdown 唯一原文和 Obsidian vault；requirement、design、prd、plan 四目录同编号同名称，职责与交接门槛统一见 docs/index.md。进度和技术约定仍在根目录 BACKLOG、PROJECT、AGENTS；research 只保留与当前决策相关的调研依据。链接、锚点和四目录结构检查复用 frontend/tests/docs/ 的 pnpm docs:check，不强制元数据或生成索引。业务报告的 Obsidian 导出继续使用 knowledge/obsidian.py。
- 环境文件只放在仓库根目录：本机用 `.env`，生产用 `.env.prod`，模板是 `.env.example`。所有进程都读这一份，进程注入的环境变量优先。
- `docker-compose.yml` 定义应用（API、Web，以及按需启用的 Worker / Scheduler / CLI）；`docker-compose-env.yml` 只在需要全新的 PostgreSQL/Redis/Kafka 时使用；`docker-compose-prod.yml` 通过 include 复用应用定义。
- 浏览器采集由宿主机来源适配器执行；报告导出使用 Playwright，不部署独立的远程 browser 服务。
- Web 生产构建为 standalone，以非 root 用户和只读文件系统运行；每个请求生成独立的 CSP nonce。

## 11. 项目文档

[文档入口](docs/index.md#需求驱动的交付规范) 按 pm-execution 统一需求拆解与交接：原始意图先形成详细 requirement，产品经理据此组织面向开发人员的 PRD；设计人员从需求和 PRD 推导目标设计，开发交接时 PRD 引用已评审设计；agent 再据同一规格拆 PLAN。四目录从 00 开始连续编号，文件名与 H1 一致，编号是追踪键，不规定页面、服务、表或开发任务的数量。用户故事只维护在 PRD，任务只维护在 PLAN，业务 AC 只维护在 requirement；不用重复正文制造多份规则。

Obsidian 直接打开 docs，共享配置、Templates 与文档视图保留；进度仅在根目录 BACKLOG，工程约定仅在 PROJECT 和 AGENTS。API 与数据库直接查代码和唯一 schema。当前文档只维护有效要求与使用说明，不保存历史文档、归档副本或已完成事项流水。业务报告的 Obsidian 导出独立于项目文档。

## 12. 关键词监控运行链

| 当前链路 | 职责 |
|---|---|
| 主题与来源配置 | monitor_topics/versions、source_connections/versions；编辑比较版本，来源准入由服务校验 |
| 运行与调度 | jobs/outbox、租约、预算和到期窗口；页面读取任务与回执 |
| 材料与评论 | content 身份、正文版本、观察记录和 threads；来源发布时间与采集时间分离 |
| 分析与展示 | annotations、公开许可投影、事件热度和报告引用；缺失数据使用真实空态 |

B 站 Chrome 来源使用 `bilibili` 来源键与固定 API 地址 `https://api.bilibili.com`，通过 SourceAdapter 接入 `keyword.search` 和 `source.comments`。适配器版本写入任务冻结的 `jobs.scope.source_adapter_version`，主题、任务、内容、预算与覆盖复用业务数据库。登录由本机 cookie-source 提供，仅对显式绑定的 owner 生效；凭据只驻留宿主进程内存，验证码、登录失效或限流时停止。

来源预设为每小时一轮、每日 60 次请求、单页两帖、每帖最多 20 条根评论、00–08 点静默、保留 30 天；搜索与评论共用预算。有界单机执行器按 owner 与来源限定任务，复用 JobExecutionService 的租约、幂等和完成流程。抽样始终标为部分覆盖，真实增量、自然持续运行和模型质量分别验收。

字段与约束见唯一 [schema](backend/sql/schema.sql)，接口以 [生成客户端](frontend/src/api) 与 [后端路由](backend/app/api/routers) 为准。


关键词查询受理复用 jobs.scope，`query_plan` 保存版本化 JSON 文本，包含有序候选、来源查询上限和逐项受理/跳过原因。手动与定时运行使用同一规划函数，未受理候选不创建任务、Outbox 或预算用量；任务详情和手动运行重放读取冻结快照，历史任务缺少快照时返回未知。它描述受理范围，不代表实际请求、命中或覆盖完成；不新增采集表或账本。

主题关键词采集的语言、搜索窗口、查询/候选/实际请求上限保存在 `monitor_topic_versions` 的显式列；改变配置生成不可变新版本。运行的有效配置连同UTC边界冻结在既有 `jobs.scope.query_plan`，执行读取该快照；候选跨页累计复用 checkpoint，实际请求复用逐请求准入。结构升级仍遵守 §6，不直接修改业务库。

普通关键词分析默认使用相关性优先的 `analysis.annotate.v2`；冻结v1任务仍按原提示词/校验执行，已有效旧结果不因切版自动重算。`content_annotations_output_status_check`允许相关且情感未分析，未知保留NULL；事件不以情感作为准入条件，报告与告警各自说明情感覆盖。数据库约束升级仍按 §6 在新库恢复核对，不直接修改业务库。

## 13. 页面与服务的边界

页面需求与视觉规范分别在 [编号需求](docs/index.md#需求目录) 和 [编号设计](docs/index.md#设计主题) 中逐项维护。页面需要的字段由现有客户端和后端合同核对；查询派生值、本机状态与持久业务事实分开。每个新增结构必须有实际读写方，不能为路由、卡片或计数复制一套数据。

`/topics`、`/monitors/[topicId]` 和 `/workspace` 共用 TopicsWorkspace。权限、公开许可、版本、任务租约与 outbox 等现有运行职责保留；物理删表须先核对消费者、历史数据和外键，再按 §6 在独立库完成恢复与迁移验证。

## 14. CI 检查

CI 验证当前锁定运行栈。frontend执行完整静态检查、交互回归与构建；contract仅执行同提交运行API的生成客户端漂移及传输层专项，不重复全套Web测试；backend使用隔离hotkey_test_*库、唯一schema和实际Redis/Kafka/MinIO做全量回归；runtime使用生产镜像验证依赖、HTTP代理、会话/CSRF、动态CSP、Worker及非root只读边界。项目文档仅保留本地链接与锚点校验、检查工具测试，镜像测试使用隔离Git夹具而不依赖Docker上下文携带仓库元数据。CI成功不替代Figma视觉、真实提供方和长期服务验收。

## 15. 页面路由约定

页面的静态路径用斜线表达层级，不使用连字符拼接多个层级：来源维护为 `/sources/editorial`。动态标识和日期仍保留其业务格式。公开来源由发布账号配置，个人配置继续按会话账号隔离；不得把个人来源自动公开。

个人 RSS/网页/JSON 来源复用 `editorial_source_profiles` 及其不可变版本、连接与审计，不建第二套来源表。服务端生成 `ed_personal_` 命名空间的 source_key，个人接口只访问会话 owner 下此命名空间；站点运营列表读取原 `ed_` 来源。个人命名空间拒绝配置公开发布策略，即使该用户也是发布账号也不能自动进入公开页面。创建默认关闭，不发起外部请求；启用继续核验原来源许可和保留策略。个人配置接口位于 `/api/sources/personal`，页面位于 `/sources/personal`。


## 13. 需求驱动的目标设计评审

本轮文档按用户要求从核心闭环重新推导；当前实现和旧设计可能有误，不能据现状限制需求。requirement 维护原始意图/功能/非功能/业务规则/验收，PRD 面向开发人员交接用户价值、流程、故事与范围，design 维护目标架构、ER、字段/键/索引/生命周期、接口/事务与体验，PLAN 面向 agent 维护执行输入、专属工作包、依赖、验证及停止条件。具体门槛见[需求驱动的交付规范](docs/index.md#需求驱动的交付规范)。

这些是待评审目标方案，不是本架构文件所述运行系统已经变更。新增候选表不自动授权替换现有schema、启动服务或升级业务库；结构实施前须按§6核对消费者、DDL/ORM/结构断言及恢复回退。旧“必须复用某表/队列/组件”等实施选择可以重评，安全、费用及授权边界仍按现行规范执行。


评论身份与关系分离：`content_threads`允许父、根及回复目标均为空且状态为`unresolved`，表示尚无关系证据；仅显式`root`表示来源确认根评论。未知关系可同事务补成根或回复，保持对象/版本/观察身份；已知父或根冲突拒绝，迟到未知不降级。关系补齐串行化于原帖身份锁，校验同owner、同帖及祖先无环。冻结分析输入不因后来补链而改写；新分析遇到未知祖先保留`unresolved`。结构升级遵守§6。


可靠首次计量使用content领域的`content_identity_history`：仅真实新建账户同事务登记完整起点，FK账户并随账户删除；缺登记/旧账户一律未知。该表仅保留owner、complete/unknown与登记/失效时间，不含对象ID、原生键、URL或哈希。任一完整对象清理使owner级历史标记永久变unknown，覆盖跨profile强原生别名，配置/连接变化不得复位。写观察与清理先取相同owner事务锁，再取原生身份锁；`content_records.last_collection_observation_id`记录精确前序，即使前序删除也不回退到更早观察。观察冻结计量依据版本、首次身份状态和前序ID，重放保持原始回执。结构升级遵守§6，不能把缺历史默认为首次。

采集持久化、正文请求计量和精确观察清理均先取owner历史事务锁，再锁Job/run、来源准入及原生身份；owner锁不跨网络请求持有。采集计量合同为`frozen_receipt_identity_v2`，仅输出原始观察、唯一身份及四类互斥计数，删除旧“观察数减新增”兼容字段。


### CORE-01 在线依赖证明

PLAN-10 R2-B先修实际observation来源/ALL依赖，再接每次新读的独立权威，全部消费者就绪后才接管删除。B1a由content持有source_v1/observations_v1证明，未知旧basis拒读不回填，不从同版本推测依赖。所有新post/comment/document固定来源shadow；编辑来源才要求guid/url_fallback，普通原生ID/网页沿既有身份，source_identity_basis为空在明确basis下表示该判定不适用。唯一schema/ORM同步约束，规范SQL仅用于全新隔离库，不自动迁移业务库。ContentVersionInput真实依赖和清理消费者保留，不作为未知观察的授权替代。

B1b按[PLAN-10锁外权威合同](docs/plan/10-权限与数据生命周期.md#b1b-锁外权威与完整复核-spec)分片：先交付流式独立读取、配置/故障传播和完整资料详情，再迁移三条基础路径与持锁写方。受保护拥有事务入口拒绝活动Session事务；新只读业务快照冻结DTO及完整依赖，结束后读独立J，再开新快照完整复核，变化有限重做。写方只能在J后重取业务锁复核，变化释放锁重准入；禁止给旧锁内helper偷偷注入网络I/O或rollback调用者。Evidence持有基础资源key，content/analysis持有各自真实闭包，避免递归。只读URL/pin为受保护动作强制输入，每动作reader在finally释放；独立权威故障不继承ApplicationError，API与两类Worker明确传播。尚无证明的详情可见性/热榜等段按unknown拒绝，不借同content补许可。无DDL变更、无业务库升级或生产者开关；具体接入进度只在BACKLOG。

### CORE-01 邮件验证事务方案

邮件挑战真源迁至PostgreSQL的`identity_email_challenges`，与账户、绑定、凭据变更及新会话同事务消费。Redis邮件数据仅为发送/验证限流；OAuth状态/PKCE仍沿用独立存储，不能据此声称OAuth事务完成。领域实现位于identity/email_challenges.py，Router仅传入浏览器绑定，ORM及唯一DDL同步维护。匿名绑定HttpOnly nonce，认证操作绑定owner/session/credential_version；统一锁序挑战→账户→会话，SMTP不跨事务持锁。重发UPSERT、错误计数提交及业务失败回滚合同见[切片SPEC](docs/plan/29-登录与验证注册.md#spec-开发合同)。过期行操作时有界清理，定期清理与保留期运行验收仍待完成。旧Redis邮件挑战切换后失效，不双写真源；业务库部署与升级仍遵守§6，当前仅改唯一schema和独立测试库。

开发追踪由各PLAN内嵌SPEC：先独立评审并按所属PLAN记录可复核规格基线，再按同文件工程任务实施。职责与模板以[文档入口](docs/index.md#plan内嵌specsdd)为唯一规范。

首页公开聚合由publication应用层在同一只读快照内扫描当前许可集合，事件时间依据由events提供；`/api/publication/home`返回全站计数和有界列表，不从Web列表估算，不新增统计表或读取时回填。

公开报道情感由analysis读取独立维度及固定观察证明，monitors提供当前规则版本；publication仅在完整事件公开许可通过后消费DTO并汇总同一快照的全站材料分母。首页/详情共用样本合同，不跨域查询分析ORM，不新增情感表或读取时触发分析，未经校准不生成突增/通知。

首页负面突增只读规则由publication在home同一快照内全站逐事件判定；core/publication_config.py持有严格配置类型，HOTKEY_PUBLIC_NEGATIVE_SURGE_POLICY无业务默认阈值。公开响应不含校准引用，不持久化、不创建个人通知；判定及不足合同见设计12与HOME-SURGE-04。

### 首页事件历史领域读取

events/public_history.py负责固定快照的散列、公开三元组/闭包、来源口径、逐点可用性及6小时趋势；publication在完整公开许可后消费DTO，不访问events ORM。热度writer新增manifest provenance，无DDL。该历史是延迟计算记录，旧依据/补算/采集不完整不连线。首页仅为最终50项读取历史，全站统计保持独立。

平台榜单由content保留固定原始条目及可空provenance，evidence分别登记整榜/条目资源和postgres_hotlist_snapshot清理目标；任一条删除保守清除整榜及派生观察，CLI/维护共用handler。publication复用版本化来源配置中的独立hotlist_publication授权，不继承正文再发布或组件许可；首页只消费纯DTO及当前许可，原生未知与RSSHub源序号分开。升级仅新空库按§6验证，旧无依据数据不回填授权。

热榜技术预设不授平台采集/留存或组件运行权：首次仅pending来源档案与技术连接，重应用不覆盖已有审核/留存/组件预算；显式审核就绪后才运行。真实来源及升级准备合同见PLAN40 HOME-NATIVE-LIVE-07和DESIGN10隔离迁移准备。
