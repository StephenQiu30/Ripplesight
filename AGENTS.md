# HotKey 工程规范

本文件适用于整个仓库。后端固定 Python、SQLAlchemy 2、FastAPI、PostgreSQL、Redis、Kafka；前端固定 pnpm、Next.js、shadcn/ui、Radix UI、Tailwind CSS、Axios、ESLint、Prettier。

`PROJECT.md` 是项目技术、架构、目录、API 契约和数据库事实源；本文件负责实现执行门禁、工具命令和验证要求。发生冲突时以 PROJECT.md 的架构决策为准。模块 README 记录使用方式，HANDOVER 记录实现状态；这些文件不得定义冲突的架构规则。变更架构或目录时必须先更新 PROJECT.md、对应 Design 和本文件，再修改代码。

总设计为 [Design 001](docs/design/001-热点舆情监控平台总体设计.md)，M1—M6 的 Design 002—007 定义各能力合同；需求为 [PRD 001](docs/prd/001-热点舆情监控平台需求.md) 与 PRD 002—007。只有当前已排期、需要持续协调、恢复或独立验收的工作保留 [Plan](docs/plan/README.md)；未来能力留在 PRD/Design/BACKLOG，启动时再写必要步骤。小修复沿用现行合同和适用检查，不强制新建计划。Plan 引用 Design，只写本轮差异、步骤、真实依赖与完成条件，不复制整份设计或重复 SPEC、Checklist、阶段门禁。关键契约未定不得声称实施就绪，技术依赖与真实授权条件分别列明。架构/数据库变化同步对应 Design 及总 Design001；实际证据写 Acceptance，未通过项如实保留。文档编号见 `docs/README.md`，历史编号不复用；计划逐项人工编写和审核，不用脚本生成或重编号。

## 完整业务维护边界

完整范围与领域合同见 PRD046、Design048；Plan062 只保留真实验证与缺陷修复。现有 Python/Next.js/Kafka、唯一状态和回执账本继续使用；真实验收及付费、来源、渠道启用条件保持有效。publication、leaderboard、operations 均已实现并登记架构检查，后续修改按所属领域门禁执行。

本轮publication实际实现已以未登记包的失败测试登记：只持许可/公开投影/修订与精选epoch，使用content/analysis/events领域DTO复核固定材料，所有异步重投复用jobs；禁止跨域ORM与重复原文/模型账本。出口必须逐次服从相同许可与撤回状态。

## 任务开始前的目录与选型门禁

- 统一异常、响应和状态契约按本文件与 PROJECT.md 的现行规则执行；旧 046 的实现与通过证据从 Git 和 Acceptance 查阅。每次相关变更按影响范围验证现行 HTTP/OpenAPI/客户端合同，不为每份计划重复建立历史前置卡或阶段表。真实依赖未验证时不得声称通过，此门禁不额外要求逐项用户批准普通实现细节。
- API 层映射无 HTTP 状态的应用错误；统一 ErrorView、类型化成功/分页/受理响应，禁止全局 body 改写。检查请求 ID、5xx/校验脱敏、必要头、运行响应与 OpenAPI 422 一致、生成客户端和非 JSON/网络/取消路径。不得用所有路由统一声明所有错误码、手改生成代码或宽泛测试忽略绕过检查。
- Web/App 不手写服务端 DTO，不按 message 判断状态，不在传输拦截器全局弹提示或自动重试写请求。Worker 的持久状态、重试和连续 offset 按 Design001/002 实现，真实恢复由当前 Demo 和正式验收验证，HTTP 契约通过不能替代。

- 每个实现切片开始前先明确技术选择与目录职责，列明新增、修改、移动和生成文件；不先写文件后找目录。
- 技术选择已有用户决定的直接沿用；影响本片的部署、费用、平台范围或新框架等未决项，先给出选项和影响询问用户，未答复不执行依赖该决定的工作。普通实现细节按已定规范处理，不重复确认已确定的技术栈。
- 用户最新决定（2026-10-01）：当前 Demo 不需要登录、注册或用户体系，现行访问合同见 Design001 §9.2，身份代码、页面、配置和业务登录依赖已清理。此前用户名密码、GitHub App、邮箱验证码、无感登录保留为未来 ToC 需求，不保留实现骨架，不阻塞 Demo。业务 `owner_id`/`created_by` 是内部历史分区 UUID；新 Schema 无身份表与身份外键，已有库不就地删表。API/CLI 使用 `db/demo.py` 的单分区解析，不创建假用户或会话；读取无 Cookie，写入固定 `X-HotKey-CSRF: 1`，多个分区明确拒绝。来源登录态、采集授权、预算与任务幂等照常保留。
- 用户已明确（2026-09-30）：最终目标是整个核心链路的 POC 验证，当前先收尾 M1；范围与退出条件以 PRD001 §1“当前核心链路 POC 边界”为准。先按 Plan058 在一个主题、HN 公开搜索和一榜上完成首次可演示的同库最小闭环，再逐项扩至四关键词来源、HN 评论和六榜的完整 M1 短窗 Demo；相关性分析状态、阅读、覆盖和任务恢复均须有可核对证据。最小闭环不代替扩围或产品验收；M1/M2 真实 72 小时及正式指标后置。日报、周报、Obsidian、知识库检索/问答、报告导出与报告渠道投递保留为非核心后续能力，不进入当前排期或阻塞核心链路。MediaCrawler 本人 B 站试点仍限个人/非商业研究，采用宿主机子进程，补丁和独立 CDP 资料记录在 `~/Desktop/Docker/mediacrawler-start-local/`；这是该来源许可/试点边界，不是 ToC 产品账户限制。遇验证、登录失效或访问频繁立即停用并由本人核查后人工恢复。复用现有 MinIO、本地 Firecrawl+Playwright、RSSHub、SearXNG；真实 Codex 请求仍暂停，模型不发起付费请求。飞书暂缓，报告 SMTP 待实现，未来登录验证码邮件独立于报告渠道；X 在凭据与月度上限未确认前禁止真实请求。来源频次与模型调用经来源预设及既有预算账本设置硬上限。
- 新后端模块、前端功能目录必须登记职责并纳入全源码/依赖检查；门禁重新实现并验证前，不得声称已覆盖新模块。
- 按业务切片创建目录，不提前创建空模块。来源适配器放sources/adapters，MinIO适配器放evidence/adapters，模型SDK适配器放ai/adapters；业务状态仍由业务模块持有。前端页面使用 `frontend/src/app`，页面专属组件放对应路由的 `components/`，跨页面复用组件按明确功能领域放 `frontend/src/components/<feature>/`，shadcn 基础组件放 `components/ui/`；`components/navigation/` 仅承载多个业务路由实际共用的导航。不创建 `features`、`common`、`patterns` 或 `shared` 层；生成客户端固定在 `src/api`，Axios 封装固定在 `src/request.ts`。

- `backend/` 是唯一后端：Python 3.12、FastAPI、Pydantic、SQLAlchemy 2、PostgreSQL、Redis、Kafka。禁止恢复 Go 后端、独立旧 Agent 或兼容旧接口。
- `frontend/`是唯一Web，采用pnpm/Next/React/TypeScript/Tailwind/shadcn/Radix/Axios/ESLint/Prettier；业务页面归`src/app/`且使用`noindex`不加入sitemap。公开页/SEO仅基于真实可公开内容。
- 品牌资产只保留唯一母版，页面图标通过 Next.js Metadata API 引用。
- Next 配置位于 `frontend/next.config.ts`，页面 CSP 使用 `frontend/src/proxy.ts` 的逐请求 nonce。浏览器对 `/api/*` 的请求保持同源，Compose 服务环境将 `HOTKEY_API_ORIGIN` 指向 `http://backend:8080`，本机开发默认 `http://127.0.0.1:8867`；容器内 Web 端口固定为 `8080`。生产镜像使用 standalone 输出和非 root 用户，生产文件系统保持只读。
- 交互HTML按请求渲染，主题创建page用`connection()`注入本次nonce。生产HTML不共享缓存、不放宽CSP。runtime核对脚本/响应nonce一致且跨请求不复用，浏览器无需会话检查即可冷进入并交互。
- 独立客户端仓库固定为同级 `hotkey-app`，使用 Flutter + Dart；Web 只在本仓库 `frontend/` 实现。两个仓库各自维护根 PROJECT.md 与 HANDOVER.md。
- Web 依赖统一由 pnpm 管理，提交 pnpm-lock.yaml 并在 package.json 声明 packageManager；不混用 npm/yarn 锁文件。
- Web 设计固定为组件优先的无边框系统：路由组合页面组件、按功能领域分类的复用组件与 ui 组件，默认信息表面不用装饰性边框；输入、焦点、错误与浮层保留必要轮廓。布局只使用 Tailwind 命名尺度和 `sm/md/lg/xl/2xl` 响应式层级，禁止原始像素值和任意布局尺寸。前端不建立独立 `scripts/` 目录，使用 ESLint、TypeScript、Prettier、生产构建和代码审查维护这些约束。
- 用户最新首页决定（2026-10-01）：方案 1 直接落在 `frontend/`，采用 Vercel 官网的黑白留白风格，不过度设计。复用现有首页组件、主题创建与 API，不增加第二套前端或复制原型内存业务；最新业务页要求按同一 FastAPI/OpenAPI 契约重建旧页面，保留已选首页；移除无接口占位与非核心偏好表单，不增加第二套状态或请求层。
- 每个前端切片必须在 Design 阶段列出组件名称、所属 feature、复用范围、目标路径、数据来源和状态覆盖。页面专属组件不得提前放入公共目录；只有至少两个页面存在稳定复用时才迁移到 `components/<feature>/`。
- 唯一 HTTP 契约由 FastAPI 路由装饰器、类型注解和 Pydantic 模型自动生成，通过 `/openapi.json` 提供；前端端点函数与类型全部由 `@umijs/openapi` 读取该地址生成。禁止手写契约 JSON/YAML、端点请求及生成类型。
- 用户最新决定（2026-10-02）：所有前端业务请求必须调用 `frontend/src/api/` 内的 Umi OpenAPI 生成函数，统一接入 Axios 封装 `frontend/src/request.ts`。业务源码不得直接导入 Axios、调用 fetch/XHR 或传输 request，也不得手写下载 API URL；仅可从 request 导入错误类和请求选项类型。ESLint 执行该边界，生成目录以 OpenAPI 漂移检查验证。透明同源代理和传输层只承担基础设施职责，其测试按确切路径检查，不给业务目录放宽规则。
- `docs/` 保留现行需求、设计、当前排期的执行计划和证据摘要。完成或合并 Plan 的有效合同进入 Design；后置工作回到 PRD/Design/BACKLOG，未通过条件保留，再删除多余执行文档。历史调研、迁移过程和截图从 Git 查询，编号不复用。`docs/README.md` 只维护入口与简短承接关系，状态只写 BACKLOG，证据只写 Acceptance；普通文档整理不新增 Plan 或验收文档。删除计划不表示需求取消或功能完成。
- 修改前阅读相关设计和测试。行为变化先验证失败，再实现；修复需针对实际故障验证。
- API路由负责协议、Demo分区/写入头和验证；业务服务负责事务，SQLAlchemy模型负责持久化。禁止路由直接SQL或发布消息。
- Session 不跨线程或任务共享。同步数据库端点使用同步路由；各 API/Worker 进程独立拥有连接池和消息客户端，禁止跨进程继承连接。
- 业务服务只能直接导入本领域ORM模型；跨领域读取使用所属模块提供的函数/DTO，跨领域原子写显式传入同一Session。禁止为绕过边界建立全局repository或共享models目录。
- 顶层模块只在当前切片真实创建时登记；architecture测试不得预先白名单未来模块。新增模块必须先以失败测试证明未登记代码会被拒绝。
- `backend/database/schema.sql` 是唯一数据库 DDL 事实源；SQLAlchemy Model 只负责运行时映射。禁止 Alembic、revision 目录、`metadata.create_all`、应用启动建表和第二份 DDL。
- 业务数据库统一为 `hotkey`；宿主机与 Compose 的连接配置必须一致。集成测试使用本机独立 `hotkey_test_<suffix>`，由执行者在成功或失败后删除，禁止使用业务库或长期遗留测试库。恢复验证的 `hotkey_restore_*` 由所属恢复流程清理。
- Plan 001 的 `monitor_topic_versions` 是关键词组、来源选择和主题请求间隔的不可变采集配置快照；名称与报告/推送偏好不升采集版本。主题恢复前核对已应用搜索预设、当前来源准入/执行策略和预算，旧 Job 不按当前主题投影重释。
- `schema.sql` 只用于全新空库，文件自身以 `BEGIN`/`COMMIT` 包住完整 DDL；直接 `psql -X --set ON_ERROR_STOP=on -f backend/database/schema.sql`、CI stdin 导入和 Compose 官方 entrypoint 挂载均依赖该文件内事务保证原子性，也可额外使用 `--single-transaction`，但不得以其代替文件内事务。三种入口均须在空库执行并在失败后确认无部分业务表。当前不支持存量库自动就地演进；需要保留数据时先验证备份，再新建数据库、应用完整 Schema 并导入校验后的数据。禁止对旧系统库直接执行。
- 业务状态与 Outbox 同事务提交。Outbox 发布到 Kafka，消费者在业务事务提交后提交连续完成位置的 offset，允许重投并通过消息 ID、epoch、fencing、租约和唯一约束保证幂等。Kafka 事务不等于与 PostgreSQL 的跨系统原子提交。Redis 只承担缓存、限流及可重建临时状态，不保存唯一业务事实；关键执行权以 PostgreSQL 为准。不再采用 RabbitMQ/Celery，不以 Redis 另建任务队列。
- HotKey 应用服务定义只维护在根 `docker-compose.yml`；`docker-compose-prod.yml` 通过 include 复用全部应用服务、profile、网络与安全限制，生产命令必须显式指定 `--env-file .env.prod`。`docker-compose-env.yml` 单独维护 PostgreSQL/Redis/Kafka，本地开发复用已有环境，不默认启动环境编排。应用不得 depends_on 这些外部依赖；连接地址和密钥由环境注入。RSSHub、SearXNG 由同级 `Docker/rsshub-start-local`、`Docker/searxng-start-local` 的 `docker-compose.yml` 管理；Firecrawl 独立编排，`~/Desktop/Docker/mediacrawler-start-local/` 保存 MediaCrawler 固定补丁、独立 CDP 资料与按需容器构建记录，但 HotKey 的 B 站调用固定为宿主机子进程，不走该容器。不得在 HotKey 根编排复制这些服务或删除用户持久卷。开发与生产不维护两套服务定义，仅分开注入连接信息与密钥。
- RSSHub/SearXNG 本机入口的主机设置 `HOTKEY_RSSHUB_HOST/HOTKEY_SEARXNG_HOST` 仅接受 `127.0.0.1` 或 `host.docker.internal`；宿主机默认前者，Compose 默认后者。固定端口 1200/8888、路由和引擎不得随主机设置扩展；来源预设将所选主机及单项白名单冻结到连接版本，已有版本须显式重新应用预设才变更。
- 认证信息不入日志或 Git；配置使用 `HOTKEY_` 前缀。公开错误只含稳定错误码、面向用户的消息和请求 ID；输入校验可附带脱敏字段详情，不回显敏感请求体。
- HTTP完成日志只记录request_id、方法、路由模板、状态码和耗时；禁止记录原始URL/query、请求/响应正文、Cookie、Token或连接字符串。未处理异常记录类型与堆栈，但不回显给客户端。
- 锁定依赖；运行 Ruff、mypy、pytest、OpenAPI 漂移检查及前端类型检查/构建。数据库和消息行为必须用真实 PostgreSQL/Redis/Kafka 验证，UI 必须用浏览器验证。
- 只采集公开或获授权数据；平台连接器必须明确能力、分页、限流和失败状态。禁止把模拟数据、空结果或诊断任务当成采集成功。
- 不擅自提交、推送或删除远端引用；用户明确授权后，先检查差异、敏感信息和远端状态，再按下列 Git 规范提交。

## Git 提交规范与交付

- 提交标题唯一格式为 `type(scope):中文描述`，冒号后不加空格。`type` 限用 `feat`、`fix`、`test`、`refactor`、`docs`、`chore`、`perf`、`build`、`ci`、`revert`；`scope` 必填，使用稳定的小写英文模块名（如 `api`、`jobs`、`docs`、`ci`、`repo`）；描述必须是具体的简体中文动宾短语，不得省略 `scope` 或使用英文描述。产品名、协议名和必要的代码标识符可保留原文。标题不超过 72 个字符。示例：`feat(api):新增任务状态查询`。
- 提交正文和脚注使用简体中文；正文说明变更摘要、原因和实际验证结果。避免“更新代码”“修复问题”等无具体信息的描述。
- 不兼容变更使用 `<type>(<scope>)!:`，并在脚注用 `BREAKING CHANGE: <中文迁移说明>` 记录影响和迁移方式。
- 一个提交只包含一个可独立验收的任务；生成物与对应源文件同提交，不混入无关格式化、重构或文档。
- 未经用户明确授权，不创建提交、推送、创建或合并 Pull Request。

## FastAPI 目录与命名（必须执行）

- 后端固定为模块化单体，按业务领域分组，采用 Router、Service、Schema、Model 分层。Repository 仅在查询复杂或需复用时增加，不创建通用 BaseRepository、ServiceImpl 或每层一套空接口。
- 后端切片在 Design 阶段明确领域归属、变更路径、路由与 DTO、服务入口、事务所有者、跨领域依赖及消息恢复行为；业务和目录规范确定后再创建模块。
- 最外层业务用例提交或回滚事务；依赖注入只管理 Session 创建与释放。跨领域原子写共用 Session，内层函数不自行提交。HTTP 和 Worker 各自装配服务，业务服务不依赖 HTTP 上下文。
- 后端工程及 Compose HTTP 服务均为 `backend`，作为普通应用运行，不构建独立安装包；禁止恢复 `server/` 别名。部署入口为 `main:create_app`。
- 应用代码统一放在 `backend/app/`；禁止在 app 下增加 hotkey 或 app 包装层；`main.py` 只做应用工厂和 lifespan 装配；`api/router.py` 汇总路由，`api/routers/*.py` 按资源组织，依赖和 HTTP 横切逻辑分别在 dependencies.py、middleware.py、exception_handlers.py。
- 已登记的 `monitors/`、`jobs/`、`connections/`、`content/` 领域在对应切片落地时拥有各自 models.py、schemas.py、services.py。`db/demo.py` 只解析内部历史数据分区，不导入业务 ORM、建表或提供通用仓储；`identity/` 从 Demo 登记中删除。禁止预先创建空领域包，也禁止用通用 Workspace/BaseService 聚合无关领域。
- `core/` 只放配置、通用错误、输入输出基类和时间函数，不反向依赖业务模块。`db/` 拥有 DeclarativeBase、连接池及元数据注册；`audit/` 承载跨领域审计。`jobs/execution.py` 维护执行状态机，`worker/messaging.py` 对接 Kafka，`worker/execution.py` 监督单个任务子进程的总截止与有界终止；`worker/app.py` 装配消费者和父进程数据库终结，Kafka Consumer/offset 仅属于父进程。任务子进程使用 multiprocessing `spawn` 并自行创建数据库资源，禁止传入父进程的 Session、Engine、Kafka Consumer 或网络连接。运行目录为 backend/app，Worker 入口为 `python -m worker`（由 `worker/__main__.py` 承接）；不得沿用 Celery 启动命令。
- 路由禁止导入 SQLAlchemy、业务 models、services 实现、执行器或消息组件；只能通过 `api/dependencies.py` 注入服务。禁止经 request.app.state 在路由中绕过业务服务读写数据库或发布任务。服务、模型、Schema 不导入 FastAPI/Starlette/HTTP 路由；Schema 不导入 ORM 或数据库资源。
- 每个HTTP操作必须有唯一人工`operation_id`、tag、成功状态和Pydantic响应模型；错误响应按操作显式声明，不在应用级虚报所有状态码。输入继承严格Input并给集合、字符串、页大小和正文设置上限。游标不得泄漏内部数据，应有明确的校验和分页边界。
- Python 文件、目录、函数使用 snake_case，类使用 PascalCase，常量使用 UPPER_SNAKE_CASE；同类职责文件统一使用 models.py / schemas.py / services.py。绝对导入；`__init__.py` 仅标识包或说明包，不放业务代码和重导出别名。
- 用户最新决定（2026-10-02）：测试与业务代码分离。前端测试统一放 `frontend/tests/`，镜像业务目录，配置测试放 `tests/config/`；不得在 `frontend/src/` 或前端根散放测试、从业务代码导入测试框架/测试目录。Vitest 只发现 tests；生产类型检查/镜像排除测试，`tsconfig.test.json` 单独检查测试类型，`pnpm typecheck` 覆盖两者。后端测试仍放 `backend/tests/unit/`、`backend/tests/integration/`、`backend/tests/architecture/`，公共 fixture 放 tests/conftest.py。
- 独立 `hotkey-prototype` 已由正式前端承接，可以退役；因无 Git 历史，清理前保存源码、选定设计图与 QA 资料的可恢复归档，server/app 独立项目照常保留。
- 不新增项目 `scripts/` 目录或一次性 `.sh` 文件，容器与部署验证复用 pytest、领域 CLI、Compose、依赖官方 CLI 和 CI 工作流。组件文件使用 kebab-case.tsx，导出组件使用 PascalCase；生成客户端固定在 `frontend/src/api/`，Axios 传输封装固定在 `frontend/src/request.ts`，不创建 features/patterns/shared 层，英文 README 为 README.en.md。
- 后端结构与依赖方向由 architecture 测试强制检查；前端 Next 层登记与依赖方向遵循本文件及 `frontend/DESIGN.md`，并通过 ESLint、TypeScript、生产构建和代码审查验证。Ruff 检查命名/绝对导入，mypy 严格检查后端应用与工具；锁文件、`schema.sql`、ORM 映射、HTTP 和消息契约必须在目录重构中保持可验证。增加架构例外需同步 Design，禁止添加宽泛忽略绕过标准检查。
- 不因“异步更先进”将同步psycopg调用放进`async def`路由。只有整条调用链非阻塞且有独立并发/连接池验证时才引入AsyncSession，并保证每个并发task独立Session。

- `sources/` 的适配器不依赖 API、ORM、Worker 或 CLI；业务来源契约不导入 HTTP 客户端。来源探测只经独立 CLI 显式执行，查询预览不发送网络请求。未通过持久化采集验收前，来源连接状态保持 not_connected。
- X 官方 API 适配器 `sources/adapters/x_api.py` 只处理官方端点、只读映射、分页和错误翻译；业务预算/连接执行权由调用方装配。凭据与月度上限未确认前不启用真实请求。新 HTTP 适配器继承 `sources/adapters/http_source.py`，必须接收主机白名单并校验每一跳重定向。
- 本地网页/浏览器采集遵守下述边界；旧 Design 047 本地网页与浏览器采集已删除，见 Git 历史（原 047 Plan 曾并入拆分前的旧总 Plan 001）。S00/S01 与 S02 公开网页业务闭环、S03 浏览器基础，以及 S03-T03 Worker 单任务硬截止/取消回收/未知退出重放共享边界已有实现和技术验证。不得把公开网页闭环或运行时探针当作平台接入成功；通用 Browser 业务处理器仍未接入 Worker，G4-002 的凭据隔离/换版旧写端到端验证仍待完成。本人账号 B 站采用 [Design 003 第 3 节](docs/design/003-本人账号B站试点设计.md)的宿主机 MediaCrawler 与独立 CDP 资料，其真实修复后采集仍未验收；其他登录平台不得据此称已接入。Firecrawl 内置渲染器不等于完整交互服务。`connections/adapters/local_secrets.py` 只管理受控浏览器状态文件，运行时不得接收不可信文件路径；本地 CLI 捕获文件也需拒绝符号链接、宽权限及超限内容。`browser_state` 引用必须与版本行身份一致，执行前由 `connections` 服务判定当前版本、停用及认证失效，不由文件存在性代替；无适配器时不在目录新增假来源。外采适配器保持无 ORM，业务编排归 content，执行权和预算归 jobs；不新增第二套队列或任务数据库。跨仓库 Firecrawl 修复单独检查差异，不混入 HotKey 提交。
- S03 通用浏览器服务固定 Playwright Python/Server `1.63.0` 原生 WS；browser 构建 target、必要的 `server.js` 入口与 seccomp 置于 `backend/`。browser 只接 Worker 共享的 WS 内网及专用代理内网，只有 HotKey 自有 Squid 代理接公网桥接网；初始代理仅放行 `example.com` 探针，不放行真实平台。控制面 WS 路径使用本机私有配置的不可猜测 `/ws/` 令牌，browser 与调用方必须一致，禁用公开根路径及日志回显。适配器管理器启动、建连、context 与交互共用协作式截止；各关闭步骤有界请求清理，但不能冒充业务任务硬截止。CLI 的无网络探针和代理通路仅证明运行基础，不得据此声明平台能力；真实平台出口/请求计量须经后续专门验证。不得为通用服务安装 Scrapling、第二套依赖栈或把浏览器二进制加入 API 镜像；本人账号 B 站的宿主机独立 CDP 资料按 [Design 003 第 3 节](docs/design/003-本人账号B站试点设计.md)执行。
- 评论与回复按 [Design 002 第 3.4 节](docs/design/002-信息获取主链路设计.md)与[Design 003 第 3 节](docs/design/003-本人账号B站试点设计.md)存入 `content_threads`；旧 Design 008 评论与回复采集已删除，见 Git 历史。评论 ID 保留原生不透明字符串，作品、线程根、直接父节点和回复目标分别记录；`parent_relation_status` 与身份占位保留未知/不可访问父节点缺口，不猜测父链。新增关系列与 ORM、来源准入字段同批更新，只在全新空库应用完整 `schema.sql`；旧库保留与重建按 Design001 §6.3。HN 验证一级/楼中楼分页和旧帖新回复，B 站本轮只验同轮缓存的一级评论每帖 ≤20 条，不宣称楼中楼覆盖。候选爬虫先核对固定源码/许可/运行边界，不能照 README 的“全量”或单页结果声明完整；评论不依赖 X 先就绪。
- 010 增量范围遵守下述现行规则；旧 Design 010 增量更新与历史回补已删除，见 Git 历史。Job 检查点不充当跨轮次确认水位，`SourcePage.COMPLETE/EMPTY` 不单独证明有界时间窗覆盖；半批失败和未知尾段保留缺口。S01 的持久范围表、ORM、服务与受控测试已同批进入；S02 时间标记要求范围 Job 显式固定 `scan_kind`，旧任务缺失类型时不默认为追新。现有开发库未就地迁移、无真实多页处理器；内部样本不标记真实来源可用。逐来源重叠/旧帖周期须有真实样本后才固定，不创建无处理器的回补路由或页面。

### 固定技术与运行入口

| 项目 | 固定要求 |
|---|---|
| HTTP 服务 | Python 3.12、FastAPI、Uvicorn |
| 契约与配置 | Pydantic 2、pydantic-settings；配置使用 `HOTKEY_` 前缀 |
| 数据访问 | SQLAlchemy 2、psycopg 3、PostgreSQL；默认同步 Session |
| 数据库结构 | `database/schema.sql`；唯一 DDL 事实源，只初始化全新空库 |
| 缓存与事件 | Redis 负责可重建状态；Kafka 负责持久任务事件 |
| 对象存储 | MinIO，适配器归 `evidence/adapters/` |
| 工具 | Ruff、mypy、pytest、HTTPX；依赖精确版本随锁文件提交 |
| API 入口 | 在 `backend/app/` 执行 `uvicorn main:create_app --factory` |
| Worker 入口 | 在 `backend/app/` 执行 `python -m worker`（当前 M1/M2 只在宿主机运行一个） |
| 调度入口 | 在 `backend/app/` 执行 `python -m worker.scheduler`（扫表创建 Job） |
| CLI 入口 | 在 `backend/app/` 执行 `python -m cli` |

后端依赖统一使用 uv、`pyproject.toml` 和 `uv.lock`，作为普通应用管理，不构建安装包。CI 和镜像使用 `uv sync --locked`；精确版本在底座初始化时解析、验证并提交，不手工编辑锁文件。

### 通用工具与复用边界

| 能力 | 固定工具 | 放置与使用规则 |
|---|---|---|
| 配置校验 | `pydantic-settings` | `core/config.py`；禁止手写环境变量解析框架 |
| HTTP 请求 | `httpx` | 领域 adapters 使用复用的 Client/AsyncClient；明确连接、读取、写入和连接池超时 |
| 结构化日志 | `structlog` + 标准 logging | `core/logging.py` 统一配置，输出结构化日志，按请求绑定并清理 request_id |
| 有限重试 | `tenacity` | 只用于适配器中可安全重试的调用；明确异常类型、次数、时间预算和退避 |
| 命令行 | `typer` | `cli/commands.py` 定义命令，`cli/__main__.py` 启动；不自行解析 argv |
| Redis | `redis`（redis-py） | 复用官方连接池，设置超时与资源释放；业务缓存规则留在所属领域 |
| Kafka | `confluent-kafka` | `worker/messaging.py` 适配；确认投递结果，业务提交后提交 offset |
| 对象存储 | `minio` | `evidence/adapters/minio.py`；复用官方签名、上传和下载能力 |
| 标准通用能力 | `datetime`、`zoneinfo`、`uuid`、`pathlib`、`contextlib` | 标准库能完成的功能直接使用，不建立重复工具类 |

- 工具选型固定，依赖随真实使用方加入；禁止为凑工具清单安装未使用的框架。
- 仅为业务契约、生命周期和外部服务差异做薄封装，不创建通用 HttpUtils、RedisUtils、BaseService 或万能工具包。
- 直接复用 FastAPI/Starlette 的依赖注入、异常处理、中间件、表单解析和响应序列化能力；不另造 Web 框架。
- Tenacity 不承担持久任务调度或消费重试状态；不得无条件重试写操作，避免 SDK 重试与应用重试叠加。
- 同步 SDK 不直接运行在异步路由中；连接池、HTTP Client 和消息客户端由所属进程生命周期统一创建与关闭。
- 日志禁止输出原始请求、响应、Token、Cookie 和连接字符串；外部异常先映射为业务错误，再交由 API 输出。

### 接口文档

- FastAPI 路由与 Pydantic Schema 是唯一契约源；运行时统一提供 `/openapi.json`，Swagger UI 使用 `/docs`。
- 增强交互文档默认使用 `scalar-fastapi`，入口 `/scalar`，与 Swagger UI 共用 `/openapi.json`；不额外开启 ReDoc。
- Knife4j 只有在明确要求该产品时作为替代 UI 接入，不能安装 Spring Boot starter 到 Python 后端。接入前验证实际 OpenAPI 版本、nullable、联合类型、认证与调试兼容性；不得只修改 Schema 版本号冒充兼容。
- 不手写第二份 Swagger JSON，不另用注解体系生成契约；文档 UI 和 Umi OpenAPI 客户端读取同一份契约。
- 接口变更只修改路由装饰器、参数类型、`Field`/`Query`/`Path` 声明和 Pydantic 模型。后端重载或重启后，FastAPI 自动更新 `/openapi.json`，Swagger UI 和增强文档刷新后展示新契约；不逐接口维护文档页面。
- Umi OpenAPI 的 `schemaPath` 直接指向后端 `/openapi.json`，通过命令环境变量 `HOTKEY_OPENAPI_URL` 覆盖。生成客户端需要执行 `pnpm openapi:generate`，不宣称后端变更会自动热更新 TypeScript 文件。
- 后端底座 CI 必须启动同一提交的应用，自动执行客户端生成和类型检查，并检查生成差异；契约不可读取或生成失败时构建失败。需要归档的 JSON 仅由程序导出为 CI 产物，不作为手工维护的源文件。
- `api/docs.py` 负责文档 UI 注册，由 `main.py` 装配；文档页面使用 `include_in_schema=False`，不得进入生成客户端。
- 端点必须填写中文 summary、必要 description、tag、operation_id、参数约束、成功和错误模型、适用示例及认证方式。
- Swagger UI 与增强文档的静态资源固定版本；生产文档在受控入口开放或关闭，调试功能沿用真实 API 权限。
- 文档验收包含 Schema 加载、分组、认证、参数输入、实际调试、错误展示和 Umi OpenAPI 生成；页面能打开不等于契约兼容。

### 后端目录标准

以下为目标结构；按实际切片创建文件。领域模块无持久化需求时不创建 models.py，无查询复用需求时不创建 repositories.py。Python 包必须有 `__init__.py`，图中省略。

```text
backend/
├── pyproject.toml                 # 依赖、Python 版本、检查和测试配置
├── uv.lock                        # uv 生成的唯一依赖锁文件
├── Dockerfile
├── database/
│   └── schema.sql                 # 唯一 PostgreSQL DDL 事实源
├── app/
│   ├── main.py                    # 唯一 create_app 与 lifespan 装配
│   ├── api/
│   │   ├── router.py              # 注册所有 HTTP 路由
│   │   ├── dependencies.py        # DB Session、Demo分区和服务注入
│   │   ├── docs.py                # 接口文档 UI 注册
│   │   ├── middleware.py          # 请求 ID 和访问日志
│   │   ├── exception_handlers.py  # 业务异常转 HTTP 响应
│   │   └── routers/<resource>.py  # 资源接口，不含业务实现
│   ├── core/
│   │   ├── config.py              # pydantic-settings
│   │   ├── logging.py             # structlog 与标准 logging 配置
│   │   ├── errors.py              # 与 HTTP 无关的异常
│   │   └── schemas.py             # 公共输入输出基类
│   ├── db/
│   │   ├── base.py                # 唯一 DeclarativeBase
│   │   ├── session.py             # Engine 与 Session 工厂
│   │   └── metadata.py            # 仅用于模型注册
│   ├── <domain>/                  # 按业务领域命名
│   │   ├── models.py              # 表、关系、索引和约束
│   │   ├── schemas.py             # 输入、输出和服务 DTO
│   │   ├── services.py            # 业务规则、资源权限、事务
│   │   ├── repositories.py        # 按需拆出的查询与持久化
│   │   └── adapters/              # 按需隔离外部 SDK
│   ├── worker/
│   │   ├── __main__.py
│   │   ├── app.py                 # 生命周期和服务装配
│   │   └── messaging.py           # Kafka 收发与提交位点
│   └── cli/
│       ├── __main__.py
│       └── commands.py
└── tests/
    ├── conftest.py                # 隔离环境与公共 fixture
    ├── unit/
    ├── integration/
    └── architecture/
```

| 领域目录 | 唯一业务主责 |
|---|---|
| `monitors/` | 监控配置与规则 |
| `jobs/` | 任务、Outbox、执行状态机、取消与恢复 |
| `connections/` | 平台连接版本、能力证据与可用状态投影 |
| `content/` | 作品身份、发现关系、内容版本与观察投影 |
| `sources/` | 来源契约、来源适配器与采集能力 |
| `evidence/` | 证据元数据、文件与 MinIO 适配器 |
| `ai/` | 模型调用契约、SDK 适配器、调用记录与成本结算 |
| `analysis/` | 相关性、摘要、情感与观点标注（已有代码；M1 相关性、M4 质量验收） |
| `events/` | 候选、稳定身份、事实/纠错、热度、人工合并/拆分与事件阅读；M3 真实产品验收独立保留 |
| `reports/` | 主题报告及公开日周月刊的生成、输入复验、修订与存档；M4 真实质量独立验收 |
| `notifications/` | 推送渠道、订阅、发送记录与未知结果人工恢复；SMTP 已实现默认关闭，飞书真实送达暂缓 |
| `knowledge/` | Obsidian 日报导出已有代码；M4 独立验收及 `pg_trgm` 检索与问答 |
| `audit/` | 跨领域审计记录 |
| `publication/` | 公开许可、固定内容投影、公开阅读与分发出口 |
| `leaderboard/` | 模型身份、来源快照、评分与排名 |
| `operations/` | 独立运营认证、反馈、站点设置、心跳与维护编排 |

新增领域必须先在切片 Design 登记主责、依赖和目标目录，再更新本表；不得把业务代码堆入 `core/`、全局 `utils/` 或全局 `models/`。

### 依赖、事务与资源边界

| 层 | 允许依赖 | 禁止事项 |
|---|---|---|
| Router | Schema、API 依赖别名 | SQLAlchemy、直接导入或构造 Service、发布消息 |
| API dependencies | Session 工厂、Service、Demo分区与写入头 | 业务编排、自动提交事务 |
| Service | 本领域 ORM/Repository、Schema、显式领域服务、适配器契约 | HTTP 上下文、直接访问其他领域 ORM、循环依赖 |
| Schema | Pydantic、标准类型、公共 Schema | ORM、Session、FastAPI |
| Model/Repository | SQLAlchemy、db 基类、本领域数据结构 | HTTP、调用上层 Service、独立 commit |
| Adapter | 外部 SDK、所属领域契约 | HTTP 路由、任务状态机、修改其他领域数据 |
| Worker/CLI | 业务服务、运行资源与装配 | 复制业务规则、调用 HTTP 路由实现 |

- 服务简单时使用函数；需要持有注入依赖时使用类。只为实际可替换边界定义 Protocol，不要求每个服务都配接口与实现类。
- 最外层用例显式开启并结束事务；跨领域写入由编排方传入同一 Session，内层只读写或 flush。独立任务重新取得 Session。
- Session 按请求或任务创建，不跨并发执行单元共享；请求依赖清理时仅释放或回滚未完成事务。响应 DTO 在 Session 有效期内构造，禁止响应序列化触发隐式数据库访问。
- Engine、连接池和外部客户端按进程初始化，由 API lifespan 或 Worker 生命周期释放；导入模块时不建立网络连接。
- 同步数据库使用 `def` 路由；异步 Worker 调用同步业务时，整个用例及 Session 生命周期在同一个受控执行单元内完成。不得在事件循环中直接调用阻塞数据库或 SDK。
- API 与 Worker 独立运行；FastAPI lifespan 不启动业务消费者。存活检查验证进程，就绪检查验证必需依赖；必需资源初始化失败必须阻止服务就绪。
- 数据写入和 Outbox 原子提交；Worker 幂等完成业务事务后再提交 offset。失败重投、死信、取消和恢复策略必须在任务 Design 中明确。

### 前后端契约与目录标准

```text
frontend/src/
├── app/
│   ├── page.tsx
│   ├── components/               # 根页面专属组件
│   └── <route>/
│       ├── page.tsx
│       └── components/           # 对应页面或路由树专属组件
├── components/
│   ├── ui/                       # shadcn/Radix 基础组件
│   └── <feature>/                # 按功能分类的跨页面复用组件
├── api/                          # Umi OpenAPI 生成文件
├── lib/                          # 无业务语义的纯工具
├── request.ts                    # 唯一 Axios 传输层
└── proxy.ts                      # 同源代理与 CSP
```

- HTTP 契约链固定为路由装饰器/类型注解/Pydantic → 运行时 `/openapi.json` → Umi OpenAPI → `frontend/src/api/` → `src/request.ts`。后端输入、输出 Schema 分离；响应不得暴露敏感字段。
- 每个端点显式声明稳定的 `operation_id`、tag、成功状态、响应模型和适用错误响应。客户端生成物与对应契约变更同批交付。
- 页面专属组件不得被所属路由树外部导入；需要跨页面复用时迁移至对应 `components/<feature>/`。不创建 `src/features`、`common`、`patterns`、`shared` 或前端 `scripts` 目录。

### 任务说明必须覆盖的内容

需要保留 Plan 的当前任务只记录本轮变化和必要完成条件；小修复可直接在任务说明中记录。下列决策若已有现行 Design 合同，引用即可，不要求在 Plan 再写一遍；与本轮无关的行省略。

| 内容 | 必须明确 |
|---|---|
| 文件清单 | 新增、修改、移动、生成文件的确切路径及职责 |
| 领域边界 | 主责模块、服务入口、允许依赖及跨领域调用 |
| 数据 | `schema.sql`、ORM、Schema、约束、事务所有者、重建与数据导入行为 |
| HTTP | 方法、路径、身份和资源权限、operation_id、响应与错误 |
| 任务 | 消息契约、幂等、offset、超时、重试、取消与恢复 |
| 前端 | 组件名称、分类、复用范围、路径、数据来源和各状态 |
| 验收 | 必要场景、验证命令、隔离依赖、完成条件及证据位置 |

无明确职责或没有当前使用方的文件不得提前创建。实现改变以上决策时，同步更新 Design 和本规范。

### 实施验收要求

- 后端初始化时配置 Ruff、严格 mypy、pytest 及 `app` 导入路径；建立架构测试约束实际模块和依赖方向。
- 单元测试验证业务规则；集成测试在全新隔离 PostgreSQL 中执行完整 `schema.sql`，验证 ORM 映射、HTTP/OpenAPI、事务、依赖释放及 Redis/Kafka 行为。
- 每次 DDL 变更必须以失败验证证明旧 `schema.sql` 不满足新结构，再在同一提交更新 SQLAlchemy Model、完整 SQL 和数据库断言。CI 从空库建表并验证，不读取开发机旧库，不接受仅靠 mock 或 SQLite 的结果。
- 数据库或消息改动必须验证回滚、重复消费和进程重启恢复；不能用 mock 通过代替真实集成验收。
- 前端运行 ESLint、TypeScript、Prettier 和生产构建；页面变更完成桌面与窄屏浏览器检查。
- 文档变更检查路径、命名和规则一致性。规划目录不代表代码已经存在，测试目标不代表已经通过。

全量迁移维护切片新增`operations/`实际领域，主责/事务/鉴权见Design048：反馈及冷却、私有附件、审计、心跳和词典版本；模型注册与canonical schema同一窗口核对。`analysis/evaluation_*`归分析领域，运营通过DTO调用；付费评测关闭。运营读写使用独立token，不恢复ToC登录。全量公开刊期的scan游标只负责补刊，不替代主题报告配置。

全量阅读Web路径登记：`/discover`为资讯入口，`/items/[contentId]`为固定版本/许可正文，`/agent`为五工具与Markdown接入说明，`/feeds`为RSS订阅选择，`/publication/manage`为独立operator许可/投影维护；保留已有`/`监控首页。路由专属组件在各页面components，明确跨页复用放`src/components/publication/`（卡片、读取错误、海报下载）；不复制网络客户端，唯一生成gongkaifabu/gongkaifenfa。所有入口覆盖加载/空/失败重试、partial/unknown、许可收紧与403/409，公开Demo仍noindex。

本轮已登记content/editorial_rendered_*、publication/media_mirror_*及jobs/source_scopes.py职责见PROJECT/Design048；同版本格式和媒体事实要同事务且纳入内容指纹，跨域只用typed读取，禁止来源receipt复制正文。新公开详情`/discover/stories/[eventId]`须ALL成员许可成立；`/editorial-sources`沿用唯一客户端和独立运营写入。MinIO客户端纯构造并在所属进程关闭，GET禁止外采。长任务监督续租只改当前执行权，不能续取消或伪造请求；Kafka显式轮询窗口不足要拒绝。

行业主题目录`/discover/topics`与`/discover/topics/[slug]`归publication，使用固定MIT主题定义和已许可主体信号，不替代原监控`/topics`。`publication/reading_groups.py`只派生公开故事/事实/单件阅读分组，`topics.py`只派生主题计数、分页与索引准入；不增加原始材料、事件事实或HTTP客户端。通知扫描与发送沿用原Job，跨域只能调用所属领域typed读取与同事务受理。

站点设置operations/site_*仅持同owner联系/二维码、版本与显式开关；沿用运营audit和鉴权，不生成第二套账号。公开统计归publication且逐次核许可，说明/联系/设置路径见PROJECT；本机收藏`/discover/starred`只存ID，导入需限额/合法ID/版本校验，跨tab修改不得覆盖其他条目。

公开刊期`/reports/[kind]/[key]`是publication读模型，禁止拼接内部历史稿或在GET执行付费生成；公开故事/刊期/专题的indexable服从当前ALL来源许可。IndexNow发送固定canonical引用，使用原Job、预算与运营审计；固定根验证路径只经既有公开分发路由及Next严格白名单转发。

publication/share_images.py仅消费实时许可DTO生成固定尺寸PNG；assets/og-fonts唯一承载有完整OFL许可的NotoSansSC固定子集，不重复品牌资产或引入远程字体请求。分享图片和海报在ETag/304前仍复验全部正文权限，撤回返回404。

真实embedding仅走ai/adapters/embeddings.py的/embeddings合同；events向量不复制付费回执账本，冻结模型/维度/输入版本并经原Job+AiCall恢复，unknown不重发。source.icons缓存仅源图标素材，当前source准入、公开权、Evidence可读性在网络提交/写入/GET均重新核对，真实外采默认关闭；沿已有media fetch/codec/storage和预算实现，不复制队列。
