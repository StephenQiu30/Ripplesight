# HotKey 项目与架构

HotKey 是 ToC 信息监控产品，覆盖主题与来源配置、信息获取与阅读、分析、事件、报告、分发、模型榜、公告和运营维护。本仓库维护 Python 后端与 Next.js Web；同级 `hotkey-app` 是尚未初始化的 Flutter 客户端。

产品要求见 [PRD001](docs/prd/001-热点舆情监控平台需求.md) 及 [完整业务需求](docs/prd/046-完整业务需求.md)；领域合同见 [Design001](docs/design/001-热点舆情监控平台总体设计.md) 及 [完整业务设计](docs/design/048-完整业务设计.md)。本文维护技术、目录、API 和数据库边界，[AGENTS](AGENTS.md) 维护工程检查，[BACKLOG](BACKLOG.md) 是总体进度入口，[PLAN007](docs/plan/007-公开信息免费采集执行计划.md) 维护本轮详细工作包和checklist，[Acceptance](docs/README.md) 记录证据。

## 技术与运行

| 范围 | 固定技术与入口 |
|---|---|
| 后端 | Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、psycopg 3；普通应用，不构建安装包 |
| 后端依赖 | uv、`pyproject.toml`、`uv.lock`；按 `uv sync --locked` 安装 |
| Web | Node.js 24.19.0、pnpm 12.3.4、Next.js 16.3.5、React 19.2.8、TypeScript、shadcn/Radix、Tailwind、Axios |
| 数据 | PostgreSQL 是业务事实源；Redis 只保存可重建缓存/限流；Kafka 传递持久任务事件；MinIO 保存证据及文件 |
| 外部客户端 | HTTPX、redis-py、confluent-kafka、minio；日志 structlog，CLI Typer |
| 质量 | Ruff、mypy、pytest；ESLint、Prettier、TypeScript、Vitest、生产构建、生成契约与浏览器检查 |
| API | 在 `backend/app/` 执行 `uvicorn main:create_app --factory --host 127.0.0.1 --port 8667` |
| Worker / 调度 / CLI | 在同目录分别执行 `python -m worker`、`python -m worker.scheduler`、`python -m cli` |
| Web | 在 `frontend/` 执行 `pnpm dev` 或 `pnpm start`，本机端口 `8666` |

本机 API 固定 `127.0.0.1:8667`、Web 固定 `127.0.0.1:8666`，API 文档为 `/docs`、`/scalar`，唯一契约为 `/openapi.json`。启动与维护命令见 [根 README](README.md)、[Backend README](backend/README.md)、[Web README](frontend/README.md)。

## 目录与领域所有权

```text
hotkey-server/
├── backend/
│   ├── app/main.py              # 应用工厂和进程资源装配
│   ├── app/api/                 # 路由、依赖、协议和异常映射
│   ├── app/core/                # 配置、日志、公共错误与 Schema
│   ├── app/db/                  # ORM 基类、连接池和模型注册
│   ├── app/<domain>/            # 领域模型、DTO、服务和按需适配器
│   ├── app/worker/              # Kafka、任务子进程与独立调度
│   ├── app/cli/                 # 维护入口
│   ├── database/schema.sql      # 唯一完整 DDL
│   └── tests/                   # unit、integration、architecture
├── frontend/
│   ├── src/app/                 # 路由及路由专属 components
│   ├── src/components/          # ui 及按领域划分的跨页组件
│   ├── src/layout/              # BasicLayout、头尾、容器和指南
│   ├── src/api/                 # Umi OpenAPI 生成客户端
│   ├── src/request.ts           # 唯一 Axios 传输层
│   ├── src/proxy.ts             # 会话门禁与 CSP
│   └── tests/                   # 独立前端测试
└── docs/                        # 现行 PRD、Design、PLAN007 和 Acceptance
```

领域按实际使用创建，不预建空包。领域持久化使用 `models.py`，契约使用 `schemas.py`，业务用例使用服务函数或类；复杂、复用查询才拆 Repository，外部系统差异才定义 Adapter/Protocol。禁止通用 BaseService/BaseRepository、全局 models/utils、无职责包装层或第二套后端/队列。

| 领域 | 唯一责任 |
|---|---|
| identity | 账户与基本资料、规范化用户头像、Argon2 密码、数据库会话、邮箱验证码、GitHub 状态与适配器 |
| monitors | 主题、不可变采集配置版本、调度投影与账号追踪 |
| jobs | Job、Outbox、预算、租约、执行状态、取消、恢复与到期事实 |
| connections | 来源连接版本、准入、授权、能力及状态证据 |
| sources | 来源契约、预设、外部采集与试抓适配器 |
| content | 内容身份、正文/媒体版本、发现关系、观察与评论父链 |
| evidence | 文件元数据、生命周期与 MinIO 适配器 |
| ai | 模型协议、适配器、唯一调用回执与成本账本 |
| analysis | 相关性、精选、结构化/中文写作/翻译、情感、观点与评测 |
| events | 候选、稳定事件、事实/进展、纠错、热度、人工修订及向量 |
| reports | 主题报告、日周月刊、固定输入、修订与存档 |
| notifications | 目标、订阅、投递、渠道与 unknown 人工处置 |
| knowledge | Obsidian 管理区导出、检索与问答 |
| publication | 许可版本、固定公开投影、阅读、分发和媒体引用 |
| leaderboard | 模型身份、来源快照、评分、排名与版本 |
| operations | 独立运营权限、反馈、站点设置、心跳、审计与维护编排 |
| audit / backups | 跨领域审计；备份候选与隔离恢复验证 |

Router 只处理 HTTP、身份/CSRF 和 DTO，经 API dependencies 注入服务，不直接访问 SQLAlchemy、构造 Service 或发布消息。Service 只能直接使用本领域 ORM，跨领域读取使用所属领域的函数/DTO；跨领域原子写由最外层用例传入同一 Session，内层不 commit。Schema 不依赖 ORM、Session 或 FastAPI；Adapter 不依赖 API、ORM、Worker 或任务状态机。Worker/CLI 装配同一服务，不复制规则。`core` 不反向依赖领域；`db/owners.py` 只校验或枚举真实账户分区。

Session 按请求或任务创建，不跨线程/任务共享。同步数据库使用同步路由，阻塞 SDK 不直接放入异步执行。Engine/客户端由所属进程创建关闭，导入模块不联网；API lifespan 不启动消费者。Worker 父进程独占 Kafka/offset 和任务终结，`spawn` 子进程自己建立资源，不继承 Session、Engine 或网络客户端。

## API 与身份

FastAPI 路由装饰器、类型注解和 Pydantic 是唯一可编辑契约。运行时 `/openapi.json` 供 Swagger、Scalar、契约检查、Umi 与 App 共用；禁止手写 OpenAPI JSON/YAML 或客户端 DTO。API 采用无版本 `/api/*` 路径；只有同时兼容不兼容公共契约时才另行设计版本。

每个操作声明稳定唯一 `operation_id`、中文 summary/tag、约束、成功模型和实际可达错误。成功使用资源 DTO、`PageView[T]`（`items/next_cursor`）或 `JobAcceptedView`，受理在持久提交后返回；204/304 无 body，文件/流沿媒体协议。错误统一 `ErrorView(code,message,request_id,details)`，应用错误不带 HTTP 状态，由 API 边界映射。422 details 仅保留安全字段位置/消息/类型；未知 5xx 不公开异常文本。请求 UUID 在响应头、错误体与日志一致；日志只记录方法、路由模板、状态与耗时，不记录原始 URL/query、正文、Cookie、Token 或连接字符串。

首页是公开信息入口，展示已许可发布的资讯、事件、专题与周报，并提供公开模型榜入口；公开阅读无需登录，创建个人关注、生成或发送报告及管理操作仍验证真实会话。匿名 publication 读取只使用 `HOTKEY_PUBLIC_PUBLICATION_OWNER_ID` 明确指定的发布分区；未指定返回 `publication_not_configured`，不推断账户或回退访问者资料。读前继续复验当前许可、固定版本与撤回。`/login`、`/workspace` 和个人业务始终 noindex，运营写入额外校验独立令牌；完整合同见 [Design001 §9.2](docs/design/001-热点舆情监控平台总体设计.md#92-公开欢迎页登录与个人数据访问)。

密码登录接受已验证邮箱或用户名，只登录已有账户；已验证 GitHub/邮箱首次登录创建个人账户，邮箱验证后缺少密码的账户进入首次设密流程，既有账户也可从账户设置完成。has_password由密码哈希是否存在计算；凭据更新须新近验证或当前密码/绑定邮箱证明，在同事务撤销全部旧会话并建立当前新会话。历史 UUID 只由维护 CLI 显式映射，首个注册者不能取得历史数据。会话固定12小时、可撤销、Cookie HttpOnly/SameSite=Lax、生产 Secure；业务写校验绑定 CSRF，公开登录校验同源 Origin/固定头。OTP 为6位、5分钟、单次、最多5次错误，发送冷却/频次受限；GitHub state 单次、浏览器绑定及 PKCE，验证主邮箱。GitHub/SMTP 配置缺失时明确不可用，认证邮件与报告通知开关独立。

## Web 合同

生成链为运行 OpenAPI → `@umijs/openapi` → `src/api/` → Axios `src/request.ts`。业务只调用生成函数，不导入 Axios/传输函数、不用 fetch/XHR 或手写下载 URL；可导入错误类和请求选项类型。请求选项不能覆盖生成方法、URL、数据或参数。浏览器同源 `/api/*`；SSR origin 统一由传输层解析，逐请求携带限定身份 Cookie，不在全局默认值保存凭据。透明代理只转发通用协议和 HotKey Cookie/Set-Cookie，拒绝伪造身份/转发头及任意 Authorization。

页面只组合正文与路由专属组件，稳定跨页复用后归 `components/<feature>`，基础组件归 `components/ui`；不建 features/common/patterns/shared 或 frontend/scripts。根布局装配独立 `src/layout/` 的 BasicLayout/BasicHeader/BasicFooter，头尾固定在动态视口两端，中间唯一 main 滚动；LayoutContainer 统一 `max-w-7xl`、`px-5 sm:px-8` 与正文 `py-10 sm:py-12`。内部表单/阅读尺度保留，加载/错误/404/全局恢复与打印一致，阅读进度使用 `useLayoutScrollContainer`。登录路由 `/login` 在同一外壳内省略顶部 Header，包含加载与恢复状态；保留唯一正文滚动区、页脚和全局通知。唯一视觉规范见 [Web DESIGN](frontend/DESIGN.md)。

CSP nonce 由 proxy 每请求生成，交互 HTML 按请求渲染，创建页使用 `connection()`；脚本 nonce 与响应一致且跨请求不复用，HTML private/no-store。生产 standalone、非 root、只读文件系统。测试统一 `frontend/tests`，Vitest 只发现此目录，生产类型和 Docker 上下文排除测试，独立测试类型仍检查。

## 数据、执行与恢复

`backend/database/schema.sql` 是唯一完整 DDL，按依赖顺序定义表/约束/索引，自带 BEGIN/COMMIT；应用启动不建表，不用 Alembic、独立 SQL、ORM 建表或 SQLite 业务表。SQLAlchemy 只映射结构，`datetime` 统一 TIMESTAMPTZ。SQL、Model 与结构断言同批更新，在全新 PostgreSQL 核对所有表、列、类型、可空性与主键；psql 文件、CI stdin、Compose entrypoint 均须保证失败无残留。

业务库统一 `hotkey`，宿主/Compose 配置一致；测试使用独立 `hotkey_test_<suffix>` 并在成功/失败后清理，恢复流程清理 `hotkey_restore_*`。完整 DDL 仅用于全新空库；保留数据先停写备份、实际恢复验证，再新空库建表/校验导入/切换，保留可回退源库。核对核心行数、整行摘要、身份/外键、版本、Job/Outbox/offset、覆盖/预算及对象哈希；同桶副本不是独立灾备或 WORM。详见 Design001 §6.3。

业务状态与 Outbox 同 PostgreSQL 事务，发布到 Kafka；消费者在业务提交后仅提交连续完成 offset，以消息ID、epoch、fencing、租约和唯一约束幂等。Kafka 事务不等于 PostgreSQL 跨系统原子性。持久重试由 jobs 管理，适配器只做有界安全重试；未知付费响应和通知不自动重发。

主题采集版本固定关键词、排序来源键和请求间隔；名称/报告偏好不升采集版本，旧 Job 不按当前投影重释。jobs 持有到期窗口及预算周期，人工重试仅下一成功领取开启新周期，累计/来源/全局预算不返还；content 只消费这些事实。评论分别保存作品、线程根、直接父节点、回复目标和未知/不可访问关系，不猜父链；可信页尾才确认覆盖。热榜合法空有观察时间与零条目快照，失败保留原到期桶。

四搜索、六榜属于 M1 正式验收范围；公开基础资讯和个人日/周报按所用来源、许可、持久读取及权限条件独立推进，不以完整 M1、模型润色、事件或渠道全部通过为统一前置。发布方原生 RSS/Atom 复用既有编辑来源类型并逐源准入，不增加默认来源枚举。原始固定版本复用原五分钟 publication.republish 与JSONB投影，编选run可空且明确未分析/摘要来源，不进入精选、事件或模型质量分母。个人 `report.weekly` 处理器与独立到期已实现，真实自然周到期和持续运行按 Design005/BACKLOG 独立验收，不把公开 weekly 刊物算作个人周报。

## 部署与外部启用

环境文件和唯一 `.env.example` 模板只在仓库根目录：本机所有入口共用根 `.env`，生产使用根 `.env.prod`；Settings 按源码位置解析根目录，进程注入优先。Web 配置仅加载 API/Web/OpenAPI/公开 metadata 字段，不加载后端秘密。根 `docker-compose.yml` 唯一维护应用定义；prod 文件通过 include 复用，生产命令显式 `--env-file .env.prod`；env 文件单独维护 PostgreSQL/Redis/Kafka，本机默认复用已有服务。外部环境不作为应用 depends_on；连接/密钥由环境注入。容器 Web/API 均8080，宿主映射8666/8667；Browser WS3000独立。不得删除用户库/卷或复制 RSSHub、SearXNG、Firecrawl、MinIO 编排。

RSSHub/SearXNG 主机只选 `127.0.0.1`（宿主）或 `host.docker.internal`（Compose），固定1200/8888、路由与引擎，冻结到连接版本；更改主机须重新应用预设。M1/M2 单宿主机 Worker，调度独立扫表；通用 Browser 固定 Playwright Python/Server1.63.0 原生 WS、私有令牌及独立 Squid 出口，初始仅 example.com 探针，真实平台业务仍未准入。

七平台扩围选择零供应商费用的本机路线，合同见 [Design007 §11](docs/design/007-扩展能力设计.md#11-免费本机采集顶层设计)。复用editorial来源、原Job及本机RSSHub1200/Firecrawl3002/SearXNG8888；目录、精确路由与服务端审批、主题持久匹配、同原身份正文阶段和ALL派生清理已进入实现/隔离验收。`content_topic_matches`、`content_version_inputs`由content持有，content/analysis/reports共用固定输入；正文响应不进入SourceRun缓存。导出复用原Job/MinIO/Evidence；告警复用notification.scan；`/public/`只读分发固定服务器发布者和原Redis计数，Cookie不改变归属。新增结构只应用新空测试库，业务库升级未执行。七平台各自的原生身份准入、稳定作者扫描及真实运行窗口仍未完成；Threads精确证明的受控合并合同见下一段。固定feed本地过滤不等于原生搜索；不启动第二AIHOT实例、正文库或队列。付费出口、通用Browser和MediaCrawler现有边界继续有效。

跨来源身份合同见 [Design007 §11.10](docs/design/007-扩展能力设计.md#1110-跨来源身份与独立观察输入实施合同)：content所属 `content_native_identities` / `content_observation_inputs` 已进入隔离实现，实际观察各有来源与固定输入，旧NULL保持严格原version图解释。仅当前获批Threads精确原XML主链接可证明threads_shortcode，须另有native字段用途，不能据外部自声明合并；Instagram匿名共享缓存已阻断。同owner重复RSSHub platform/route/target配置受理去重，编辑原profile。普通分析按整批帖子与评论冻结实际观察，输入签名区分同版本的独立来源；其DTO与签名归纯 `content.analysis_schemas`，查询/事务归 `content.analysis_inputs`，不使Schema间接加载数据库实现。旧摘要须能沿原成功AiCall证明完整原Job输入，缺失则停止展示。删除同时清理受影响原Job的prompt正文副本，保留身份、状态和计量审计；新B输入不能挽救旧A派生输出。完整作者scan handler及可信水位仍需实施和实际验证；受控结果记录于Acceptance002，不代替七平台真实准入。

MediaCrawler 仅本人 B站、个人非商业研究，固定宿主子进程、上游/补丁/适配器三版本与独立 CDP；资料权限700、文件600，拒绝符号链接/宽权限/超限，子进程仅最小环境。每帖同轮一级评论≤20，缺缓存不补网络；验证、登录失效或频繁访问立即停用，本人核查后人工恢复。具体版本/资料见 Design003。

真实 Codex/付费模型继续暂停；X 凭据/月度上限未确认前零真实请求。Reddit 仅考虑当前显式获批的官方 API 路径及 OAuth，商业用途另须书面批准；公共 Data API 迁移/退役及现行合同按 PRD007 官方依据重新核对，OAuth 不证明准入。来源预设、软件许可、平台/数据授权、能力、频次与预算分别核对，配置/probe 不算 persisted read 成功。报告SMTP默认关闭、飞书暂缓；知识库单向写 `HOTKEY_OBSIDIAN_VAULT_PATH` 的 HotKey 管理区，保留用户区块。不引入独立向量库或搜索引擎；向量仍在 PostgreSQL，由原 Job/AiCall/预算恢复。

## 文档维护

README 写使用方式，PROJECT 写技术边界，AGENTS 写检查，PRD 写需求/AC，Design 写现行合同，BACKLOG 写总体状态及未迁入PLAN的执行顺序，Acceptance 写实际证据及未通过条件。用户明确要求的 [PLAN007](docs/plan/007-公开信息免费采集执行计划.md) 唯一维护本轮详细工作包状态、依赖、验收步骤和checklist，BACKLOG只索引与汇总，不重复维护。完成步骤、临时运行快照、视觉研究和版本迁移过程不保留为另一套现行文档。文档/需求/证据编号不重用；清理文件不取消需求或改变验收结论。许可证、上游固定版本和资产归属保留于 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md) 及源码许可。

定时任务采用APScheduler 3.x内存进程时钟（30秒、单实例、合并错过tick），业务到期、幂等、重试、租约和投递仍由PostgreSQL/原Job/Outbox持久化，不使用数据库JobStore。根Compose worker profile配套Worker/Scheduler，API不运行计时器。用户经账户验证邮箱后自行订阅，普通会话/CSRF/CAS隔离，无需运营令牌；发送前复验当前邮箱与主题订阅。平台SMTP凭据保留根环境配置。
