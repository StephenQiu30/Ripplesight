# HotKey Server 项目与技术选型

更新日期：2026-10-02。本文固定仓库边界、技术栈、后端目录、API 契约和运行约束。产品需求见 [PRD 001](docs/prd/001-热点舆情监控平台需求.md)，设计见 [Design 001](docs/design/001-热点舆情监控平台总体设计.md) 及 Design 002—007，当前执行计划见 [Plan 索引](docs/plan/README.md)。用户2026-10-02决定公开首页作为SEO Welcome，业务页面登录后进入；账号密码、GitHub App与邮箱验证码共用真实会话，现行访问合同见 Design001 §9.2，实施见 Plan063。

## 1. 定位与仓库边界

HotKey 是 ToC 信息监控产品，帮助关注 AI 等专业方向的用户发现具体事件、观察升温和进展、阅读原文与讨论。公开欢迎页介绍产品；用户通过账号密码、GitHub App或邮箱验证码登录后进入主题、来源、内容和任务页面。身份与产品数据由服务端校验，第三方授权与真实邮件核收分别验收。公开资料调研、代码/受控测试、真实来源和产品验收分别记录。

HotKey 当前以**可信的信息获取**为核心：按主题持续取得可追溯的帖子、评论与六个公开热榜，显示来源 × 能力 × 时间窗的覆盖和缺口，并由本机 Codex 判断相关性。最终交付目标是整个核心链路的 POC；先按 Plan058 在一个主题、HN 搜索和一榜上完成最小演示，再扩为四关键词来源和六榜的 M1 短窗 Demo；范围以 PRD001 §1 为准。日报、周报、Obsidian、知识库检索/问答、报告导出和渠道投递属于非核心后续能力，飞书推送暂缓。当前来源验证仍使用本机基础设施，来源软件许可和平台授权范围不因 ToC 定位而扩大。本仓库同时维护 Python 后端与 Web 前端；同级 `hotkey-app`（Flutter）暂停。

```text
HotKey/
├── hotkey-server/
│   ├── PROJECT.md        # 本文：技术与架构约束
│   ├── AGENTS.md         # 实现门禁与验证命令
│   ├── BACKLOG.md        # 唯一进度看板（≤ 10 KB）
│   ├── HANDOVER.md       # 当前实现快照（≤ 5 KB）
│   ├── backend/          # Python API、Worker、CLI
│   ├── frontend/         # Next.js Web 工作台
│   └── docs/             # PRD、Design、当前执行 Plan、验收记录
└── hotkey-app/            # Flutter 客户端（暂停）
```

目录规划和测试目标不代表业务能力已经实现；能力是否可用以 BACKLOG 和验收记录为准。

### 1.1 用户与交付结果

公开 `/` 作为SEO Welcome，默认系统入口 `/topics`；未登录访问任何系统页面先进入 `/login`，成功后回到安全的站内原目标。报告接收方与平台采集账号仍分别归推送和来源连接管理。POC 成功标准是同一环境下配置、采集、持久化、分析状态、阅读、覆盖和失败恢复可操作且可追溯；真实来源与受控模型分别出结论。

### 1.2 能力里程碑

| 阶段 | 内容 |
|---|---|
| M1 | 一个主题、HN 与一榜先完成同库最小演示，再扩为四关键词来源、HN 评论、六榜、分析与阅读/覆盖/恢复闭环；产品阶段再做同窗连续 72 小时 |
| M2 | 本人账号 B 站 MediaCrawler 试点，真实低频采集、风控停止/人工恢复；72 小时后置 |
| M3 | 跨平台事件归并、热度与人工修订 |
| M4 | 分别验收分析质量、日报/周报、Obsidian 导出与问答 |
| M5 | SMTP 与暂缓的飞书按渠道分别验收 |
| M6 | 告警、指定账号、导出增强及后续来源逐项准入 |

### 1.3 当前实现边界（2026-10-02）

用户2026-10-02的新决定覆盖此前匿名Demo：公开首页和关于、隐私、条款、联系、变更说明保留公开，登录页不索引，其余工作区页面（含现有“更多”导航）必须验证真实数据库会话。API业务读写同样检查身份；运营令牌继续作为额外权限，不由普通登录替代。

`identity/`拥有账户、不可逆密码哈希、12小时固定有效且可撤销的数据库会话、GitHub授权状态及邮箱一次验证码。GitHub/邮箱首次验证成功创建个人账户；账号密码只登录已有账户。账户UUID作为业务owner_id，列表、详情、写入和任务保留原领域归属检查，不创建组织或租户框架。历史UUID不自动归给首个注册者；维护CLI必须显式指定原分区与账户映射，保留业务数据、复合外键、预算及幂等。后台调度按合法owner枚举或显式owner执行；不再把多用户当单分区拒绝。

会话Cookie为HttpOnly、SameSite=Lax，生产Secure；CSRF Cookie与header绑定当前会话，公开登录操作校验同源Origin及固定自定义头。代理仅转发HotKey身份Cookie和对应Set-Cookie，拒绝任意Authorization及伪造转发头；SSR通过生成API逐请求携带限定Cookie，不在全局Axios默认值保存用户凭据。GitHub状态绑定浏览器、单次使用并验证已验证主邮箱；OTP为6位、5分钟、单次使用、最多5次错误，发送有冷却和频率限制。GitHub/SMTP配置缺失时明确返回不可用，不伪造成功或创建默认会话。

完整 `schema.sql` 继续是唯一DDL源，启动不建表。现有hotkey库先备份并验证恢复，在新空库应用完整Schema及校验导入，再保留可回退旧库切换；不就地删业务数据或把完整DDL覆盖现有库。真实OAuth、邮件核收及历史账户映射不由受控测试代替。

原获取、标注、日报、通知和Obsidian任务保留；062新增六类编辑来源、分阶段精选/中文写作/全文翻译、事实纠错/热度、日周月刊、模型榜、Codex公告、公开投影/媒体与维护任务，复用原Job/Outbox/Kafka，全部领域API/Worker/页面已接。相应技术证据见Acceptance001，真实验收仍待完成。报告推送SMTP实现默认关闭，通知目标默认关闭，unknown只能人工确认。历史约四小时记录不证明M1连续72小时；B站修复后真实采集、真实三平台归并和产品AC仍未通过。当前状态以BACKLOG与逐卡Acceptance为准。


### 1.4 完整业务范围

完整范围包含信息获取、编辑分析、事件、报告、公开分发、模型榜、Codex 公告、分享海报和运营维护，采用 Python/FastAPI、Next.js、Kafka。范围见 [PRD046](docs/prd/046-AIHOT全量业务迁移需求.md)，所有权、版本和事务合同见 [Design048](docs/design/048-AIHOT全量迁移架构与兼容设计.md)。[Plan062](docs/plan/062-AIHOT全量业务迁移执行计划.md) 承接剩余真实验证；058/032/038/009/014 的专项验收与未通过条件继续保留。

analysis/events/content/reports/monitors/notifications 维护所属业务；publication 持有统一可发布投影与出口，leaderboard 持有模型身份/快照/排名，operations 持有独立运营认证、反馈与维护编排。以上领域均已注册架构验证。原 HotKey 主题、评论、原生榜单、覆盖、预算、证据、任务恢复与 Obsidian 保留。迁移不上 Node/Fastify/pg-boss 第二后端，不复制手写 OpenAPI；收费调用和状态接既有底座。业务用户会话与运营额外认证分别处理。真实来源/模型/渠道、数据库保留、预算及外部启用边界不自动放开。

publication已创建并登记架构门禁：持有来源公开许可版本、仅引用固定正文的投影、修订审计、精选epoch与分页重投；读取复核正文/人工版本/许可和撤回。原始内容及编辑分析分别由content与analysis经DTO提供，本域不另存正文，不建立第二个Job/投递队列。RSS、MCP、Markdown、SEO和海报使用同一准入投影。

## 2. 固定技术栈

### Web 前端

**pnpm + Next.js + shadcn/ui + Radix UI + Tailwind CSS + Axios + ESLint + Prettier。**

| 技术 | 职责 |
|---|---|
| pnpm | 唯一 Web 包管理器；提交 `pnpm-lock.yaml`，在 `package.json` 中固定 `packageManager` |
| Next.js App Router + React + TypeScript | 页面、布局、交互、服务端代理与类型约束 |
| shadcn/ui + Radix UI | shadcn/ui 采用 Radix primitives 的组件方案，不切换其他底层组件实现 |
| Tailwind CSS + CSS Variables | 样式与统一设计令牌 |
| Axios | 请求、固定写入头与错误；封装固定在 `frontend/src/request.ts` |
| `@umijs/openapi` | 从后端 OpenAPI 生成类型与端点函数至 `frontend/src/api/` |
| ESLint + Prettier | 代码检查与格式化 |

前端 API 文件和服务端类型统一由 `@umijs/openapi` 读取运行时 `/openapi.json`，生成至 `frontend/src/api/`；生成函数只接入 `frontend/src/request.ts` 的 Axios 封装。浏览器默认同源，SSR 的后端 origin 由该封装统一解析，页面不重复设置 baseURL；业务请求选项只提供头、取消、响应格式和超时，不覆盖生成操作的方法、地址和参数。业务页面、组件及工具不得手写请求、直接调用传输函数、创建 HTTP 客户端或修改生成物。ESLint 检查业务源码的请求边界；透明同源代理只负责通用转发，不承载业务端点。精选同步下载使用 `src/app/agent/components/selected-snapshot-download.tsx`，通过生成的 `getSelectedPublicationSnapshot` 取得数据后下载。

前端测试统一放 `frontend/tests/`，按 `app/`、`components/` 等对应业务目录组织；配置测试放 `tests/config/`，传输与 CSP 测试放测试目录根。`src/` 禁止放测试文件或导入测试框架/测试目录。Vitest 只发现独立测试目录；生产 TypeScript 与 Docker 构建排除测试，`tsconfig.test.json` 单独检查测试类型，`pnpm typecheck` 同时执行两套检查。后端继续使用既有 `backend/tests/`。独立 `hotkey-prototype` 的内存样例已由正式前端承接，停止维护并移出工作区；清理前保存源码、选定设计图和 QA 资料的离线恢复归档，不删除独立 server/app 项目。

页面归`src/app/`，专属组件放路由`components/`；跨页面按明确领域归`components/<feature>/`，shadcn归`components/ui/`，不建立features/common/patterns/shared层。用户于2026-10-02要求公共页面外壳集中在独立 `frontend/src/layout/`：`BasicLayout` 由根 App Router layout 接入，`BasicHeader`/`BasicFooter` 统一导航、品牌和站点信息。外壳占满动态视口，Header/Footer 不随正文滚动；唯一 main 滚动区及头尾通过 LayoutContainer 使用同一 `max-w-7xl` 和 `px-5 sm:px-8`，正文统一 `py-10 sm:py-12`。各路由只组合正文，不重复页面级 main、头尾、视口高度、容器最大宽度或外侧边距；文章、表单等内部阅读尺度保留。加载/错误/404使用同一外壳，global-error 独立恢复同一外壳；打印时恢复正常文档流并隐藏头尾。阅读进度通过 `useLayoutScrollContainer` 使用真实正文容器，保留现有本机存储结构，不再读取窗口滚动位置。浏览器调用同源`/api/*`，`HOTKEY_API_ORIGIN`仅供服务端代理；账户会话/CSRF与错误契约由后端维护。根DESIGN仅视觉参考，执行规范为frontend/DESIGN及对应切片Design。

身份认证实施同源校验、IP/账号频率限制、GitHub回调与邮箱验证码；认证邮件独立于报告投递启用状态。现有 API 代理的截止、脱敏错误、请求 ID 与必要安全头继续有效。

Web 设计固定为组件优先的无边框系统：App Router 页面只组合页面专属组件、按功能领域分类的复用组件与 shadcn/Radix 基础组件；默认信息表面通过留白、排版和语义背景分层。布局只使用 Tailwind 命名尺度和 `sm/md/lg/xl/2xl` 标准响应式层级，不使用原始像素值或任意布局尺寸。输入、焦点、错误与浮层保留必要轮廓；加载、路由错误、全局错误、404 与进程健康状态都有统一边界。组件归属、复用范围、目标路径、数据来源和状态覆盖必须在对应切片 Design 阶段明确。

当前 Web 页面以 FastAPI 生成的 OpenAPI 为准，保留 Vercel 黑白留白首页；关注、来源、内容、热榜、任务与已有报告读取使用生成客户端。`frontend/src/layout/basic-header.tsx` 区分公开站点与已登录工作区导航；不创建通用资源框架，未有接口的事件聚合占位和非核心报告/通知配置从当前界面移除。

Web的CSP nonce由`proxy.ts`每请求生成，交互HTML按请求渲染。主题创建page等待`connection()`，客户端只读取来源能力；生产脚本nonce须与响应CSP相同，不共享HTML缓存。runtime核对脚本/响应，浏览器冷进入验证交互，不能只检查健康。

### Python 后端与基础设施

业务数据库名统一为 `hotkey`，宿主机与 Compose 的 `HOTKEY_DATABASE_URL` 都指向该库。集成测试只使用本机独立 `hotkey_test_<suffix>` 库；执行者负责测试结束后的删除，不能把测试库、Demo 日期库或历史计划库作为业务配置。数据库初始化与保留数据的恢复继续遵守第 3 节，应用启动不执行 DDL。

架构固定为模块化单体，按业务领域分组；Router 处理 HTTP，Service 处理业务与事务，Pydantic Schema 定义契约，SQLAlchemy Model 定义持久化。Repository 按需引入。完整目录、文件职责、依赖方向和事务边界由本文固定；AGENTS.md 负责把这些决策转成实现门禁和验证命令。

**Python + SQLAlchemy 2 ORM + FastAPI + PostgreSQL（PGSQL）+ Redis + Kafka。**

| 技术 | 职责 |
|---|---|
| Python 3.12 | 语言基线；应用源码直接位于 `backend/app/`，不增加 `app/app`、`app/hotkey` 或 `<package_name>` 包装层 |
| FastAPI + Pydantic | API、验证、错误契约及唯一 OpenAPI 源；不预先创建未定义的 API 版本目录 |
| Uvicorn + pydantic-settings | ASGI 运行与类型化配置 |
| psycopg 3 | PostgreSQL 驱动，默认使用同步 SQLAlchemy Session |
| SQLAlchemy 2 | 运行时 ORM 映射与事务；不创建或修改数据库结构 |
| `database/schema.sql` | 唯一 PostgreSQL DDL 事实源；只用于初始化全新空库 |
| PostgreSQL | 业务事实、权限、任务、进度、幂等记录与 Outbox 的持久存储；M4 问答启用 `pg_trgm` 检索（不引入向量库） |
| Redis | 缓存、限流和可重建临时状态；关键权限、预算与任务状态仍有数据库依据 |
| Kafka | 任务事件与异步消息传输，由 Python Worker 消费 |
| MinIO | 复用既有对象存储，保存有权限与保留期约束的文件及证据 |
| Docker Compose | 根 `docker-compose.yml` 只编排 HotKey 应用，`docker-compose-prod.yml` 通过 include 复用相同服务定义；`docker-compose-env.yml` 单独编排 PostgreSQL/Redis/Kafka，本地开发默认复用已有环境、不启动该文件；开发与生产分别由未跟踪的 `.env`/`.env.prod` 注入连接信息与密钥；RSSHub、SearXNG 由同级 `Docker` 服务集合编排；Compose Worker 通过 `host.docker.internal` 访问宿主机 RSSHub 固定 1200 端口与 SearXNG 固定 8888 端口，宿主机 Worker 使用 `127.0.0.1`；`HOTKEY_RSSHUB_HOST/HOTKEY_SEARXNG_HOST` 仅选这两个主机并冻结到来源连接版本，路由和引擎保持固定；Firecrawl、MediaCrawler 各有本地入口 |
| Ruff + mypy + pytest | 格式/静态检查、类型、单元/集成/架构验证 |
| uv | 依赖、虚拟环境与 `uv.lock`，按锁文件安装 |
| HTTPX + Tenacity | HTTP 客户端与有界重试 |
| structlog + Typer | 结构化日志与命令行 |
| redis-py + confluent-kafka + minio | Redis、Kafka、MinIO 客户端 |
| Swagger UI | `/docs` 交互文档，读取唯一 `/openapi.json` |
| scalar-fastapi | `/scalar` 增强交互文档，与 Swagger UI 共用契约 |

### 后端目录、职责与唯一事实源

后端采用按业务领域分组的模块化单体。以下是实现目标结构，Python 包目录中的 `__init__.py` 在图中省略；没有明确使用方的领域文件不得提前创建。

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
│   │   ├── router.py              # 唯一 HTTP 路由汇总点
│   │   ├── dependencies.py        # DB Session、账户会话和Service注入
│   │   ├── docs.py                # Swagger/Scalar 文档注册
│   │   ├── middleware.py          # request ID、访问日志等 HTTP 横切逻辑
│   │   ├── exception_handlers.py  # 全局异常到 HTTP 错误响应的映射
│   │   └── routers/<resource>.py  # 资源接口，只处理 HTTP 协议
│   ├── core/
│   │   ├── config.py              # pydantic-settings 配置
│   │   ├── logging.py             # structlog 与标准 logging 配置
│   │   ├── errors.py              # 不依赖 FastAPI 的应用异常
│   │   └── schemas.py             # 公共输入、输出和 ErrorView
│   ├── db/
│   │   ├── base.py                # 唯一 DeclarativeBase
│   │   ├── session.py             # Engine 与 Session 工厂
│   │   └── metadata.py            # 模型注册，不负责建表
│   ├── <domain>/                  # 按业务领域命名，不建立全局 models/utils
│   │   ├── models.py              # SQLAlchemy 持久化映射
│   │   ├── schemas.py             # 领域输入、输出和服务 DTO
│   │   ├── services.py            # 业务规则、权限和事务边界
│   │   ├── repositories.py        # 仅复杂或复用查询需要时增加
│   │   └── adapters/              # 仅外部 SDK 或服务差异需要时增加
│   ├── worker/
│   │   ├── __main__.py            # python -m worker 入口
│   │   ├── app.py                 # Worker 生命周期和服务装配
│   │   ├── messaging.py           # Kafka 收发与位点提交
│   │   └── execution.py           # 单任务子进程监督与有界终止
│   └── cli/
│       ├── __main__.py            # python -m cli 入口
│       └── commands.py            # 管理命令
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── architecture/
```

图中的 `<domain>` 和 `<resource>` 只是目录职责的表示法，不是要创建的字面目录；每个实际名称必须在对应 Design 中明确登记。

目录规则如下：

- `main.py` 只创建 FastAPI 应用、注册 lifespan、路由、中间件和异常处理器；不放业务规则。
- `api/routers/`只处理HTTP参数、真实身份/CSRF依赖、状态码和响应模型；不导入SQLAlchemy、业务Service实现、Worker或消息客户端。
- 领域 Service 负责业务用例和事务；跨领域原子写入使用同一 Session，内层函数不得自行提交。
- Schema 不依赖 ORM、Session 或 FastAPI；Model 只负责持久化映射；Adapter 只封装外部系统差异。
- `worker/` 和 `cli/` 调用领域 Service，不复制 HTTP 层或业务规则。Worker 父进程独占 Kafka Consumer、offset 与任务终结；`worker/execution.py` 只监督单个 `spawn` 子进程，子进程自行创建数据库资源，不接收父进程 Session、Engine、Kafka Consumer 或网络连接。
- 不创建未定义的 API 版本目录、`app/app/`、`app/hotkey/` 或其他没有明确职责的包装目录。

### API 契约与版本策略

FastAPI 路由装饰器、类型注解和 Pydantic 模型是唯一可编辑的 API 契约事实源。运行时 `/openapi.json` 是由这套代码生成的唯一契约视图，Swagger UI、Scalar、Web 客户端、移动端客户端和契约测试都读取它。禁止手工维护第二份 OpenAPI/Swagger JSON 或 YAML。

当前 API 使用无版本路径，例如 `/api/topics`、`/api/jobs`、`/api/health` 和 `/api/ready`，不创建版本目录或版本前缀。OpenAPI 的 `openapi` 字段、`info.version` 和 URL 路径版本属于三个不同概念，不能互相替代。只有出现两个需要同时兼容的不兼容公共契约时，才可以先更新本文和 API 设计，再建立明确的版本策略。

每个 HTTP 操作必须声明唯一人工 `operation_id`、tag、成功状态、Pydantic 响应模型和实际可达的错误响应。生成的 OpenAPI、客户端代码和文档页面是派生物，不能反向成为第二个事实源。

### 全局异常与响应处理

现行统一决策如下；旧 Design 046 全局异常与响应契约已删除，见 Git 历史。HTTP 状态、稳定错误码、任务状态、页面状态分别建模；应用异常不携带 HTTP 状态，API 边界负责映射。成功响应统一为资源 DTO、`PageView[T]`、`JobAcceptedView` 三类，失败统一 `ErrorView`；不引入全接口 Result 外壳或成功 body 改写中间件。分页固定 `items/next_cursor`；异步受理必须先持久提交；204/304 无 body，文件与流按实际媒体协议处理。

`ErrorView` 的 code/message/request_id 必需，校验错误的 details 只含安全 location/message/type。公共消息来自登记表，自定义 HTTP 5xx detail 和 validator 原始消息不能直接公开。请求 UUID 保存到 scope/state，正常及异常响应头、错误 body 和日志一致，不能回退为 unknown；日志异常链也需脱敏。公开错误码、HTTP 映射、必要响应头、客户端本地传输错误分类按 046 统一登记并验证。

运行响应、OpenAPI 与生成客户端必须一致；有请求校验的路由显式声明 ErrorView 422。Web 统一读取 details 并支持请求 ID 的响应头/body 回退；网络、超时、取消、非 JSON 与业务错误区分。可控代理失败、Worker 和流发送后的失败有各自处理边界，不假定 FastAPI handler 能覆盖整个系统。新增接口持续通过同一契约检查。

全局异常处理由 `api/exception_handlers.py` 统一注册，`main.py` 只负责调用注册函数。处理范围固定为：

1. `core.errors.ApplicationError` 及其子类：映射为稳定错误码和明确 HTTP 状态。
2. FastAPI/Starlette HTTP 异常：保留必要状态和响应头，转换为统一错误模型。
3. `RequestValidationError`：返回字段级输入错误，不泄露内部文件路径或原始敏感请求体。
4. 数据库和外部服务异常：先在 Service/Adapter 边界转换为应用异常；不得把驱动异常直接返回客户端。
5. 未处理的 `Exception`：服务端记录异常类型和脱敏后的堆栈位置，客户端只返回稳定的 `internal_error` 与 `request_id`。

公共错误模型 `ErrorView` 位于 `core/schemas.py`，至少包含稳定 `code`、面向用户的 `message` 和 `request_id`。错误处理器不得把异常字符串、SQL、Token、Cookie、连接字符串或完整请求体写入响应。成功响应使用端点级 `response_model`；不使用中间件自动包装所有成功响应，以免破坏文件、流式和特殊状态响应。

本规范参考 [FastAPI 多文件应用指南](https://fastapi.tiangolo.com/tutorial/bigger-applications/)、[FastAPI 错误处理指南](https://fastapi.tiangolo.com/tutorial/handling-errors/)、[FastAPI Lifespan 指南](https://fastapi.tiangolo.com/advanced/events/)、[FastAPI 官方全栈模板](https://github.com/fastapi/full-stack-fastapi-template) 和 [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)。这些资料用于确认框架机制和通用协议；目录、事实源和版本策略以本文为准。

身份密码使用 `pwdlib[argon2]`，GitHub和SMTP适配器归 `identity/adapters/`，身份维护CLI复用现有cli，不引入通用认证框架。来源与模型服务凭据继续保存在服务端。Web 固定 Node.js 24.19.0、Next.js 16.3.5、React 19.2.8 与 pnpm 12.3.4。

## 3. 数据与任务执行边界

1. API路由负责HTTP、真实身份/CSRF与输入输出，经注入调用领域服务；服务管理事务，SQLAlchemy映射持久化。
2. 业务变更与 Outbox 写入同一 PostgreSQL 事务。独立发布器可靠地发送到 Kafka；消费者允许重复读取，以消息 ID、数据库唯一约束和业务状态保证幂等。
3. 消费者在业务事务提交后提交连续完成位置的 offset；处理并发时不得越过尚未完成的记录。Kafka 事务不能直接保证 PostgreSQL 副作用的原子性。[Kafka 消息交付语义](https://kafka.apache.org/41/design/design/)
4. Redis 的数据丢失不能导致任务或证据丢失。缓存设有效期与失效规则；限流故障时采用明确的保守策略。执行权、不可超额预算与撤权不能只依赖 Redis 锁或缓存。
5. `worker/` 维护 Kafka 客户端和消费者生命周期，`jobs/` 维护任务状态机；入口 `python -m worker`。已有 Outbox、手动 offset、inbox、租约/checkpoint、有限调度恢复和 `hotkey.jobs.accepted.v2` 消息；持久受理、内部分区读取、进度/取消、结构化失败、有限持久重试、到期 Outbox、重放防重及手动重试已有历史技术证据，不代表当前009正式验收已通过。032 的采集周期由 Job 领取事务拥有，周期请求数约束单轮上限，累计请求数与来源/全局账本持续增长；`content` 只消费 `jobs` 给出的周期事实。固定 `webpage.collect` 处理器已登记，历史 Kafka/Firecrawl 持久结果与恢复证据不代表其他平台接入；其他 kind 没有处理器时必须持久失败后确认，不能把排队记录或空 Worker 当作业务执行成功。
6. API、Worker 各自创建数据库连接池和消息客户端，Session 不跨线程/任务共享。同步数据库调用不直接放入异步路由。
7. FastAPI 从路由装饰器、类型注解和 Pydantic 模型自动生成 `/openapi.json`。它是唯一 API 契约视图；Swagger UI、Scalar、Umi OpenAPI 和 Flutter 客户端共用该地址，不维护独立契约文件。客户端由生成命令更新，CI 负责自动生成与差异检查。
8. 数据库结构只由 `backend/database/schema.sql` 定义，SQLAlchemy Model 必须与其同批更新。`schema.sql` 自身以 `BEGIN`/`COMMIT` 保证完整 DDL 原子性；CI 的 psql stdin 和 Compose 官方 entrypoint 挂载均依赖此事务，显式 `--single-transaction` 可额外使用。只对全新空库执行，失败后核对没有部分业务表。当前不支持存量库自动就地升级；保留数据时采用备份、全新建库、完整建表和校验后导入流程。
9. 热榜快照通过 owner/job 外键关联 `collection_due_windows` 的已受理到期事实，并以 owner/source/operation 唯一；合法空 Feed 是有观察时间的零条目快照，失败保留到期与 Job 原因，不由后续桶补写。
10. 评论的 `content_threads` 分别保存所属作品、线程根、直接父节点与回复目标的同 owner 内容身份；根或回复目标尚不可判定时使用空值，不把直接父节点猜作线程根。`parent_relation_status` 区分顶层、来源已观察、来源不可访问和待解析父节点，已知但未入库的节点以身份占位并保留缺口。以上列只通过完整 `schema.sql` 建于新库，旧库保留与重建沿用第 8 条。

## 4. 产品约束与未决事项

- 只采集公开或获授权的数据；遵守平台频率限制；凭据和登录态只存服务端，不进前端、日志和代码库。
- 本轮逐来源验收四个关键词来源（HN Algolia、Google News 搜索 RSS、本机 SearXNG 的 `duckduckgo news`、本机 RSSHub `/36kr/newsflashes`）、六个公开 RSSHub 热榜，以及本人账号 B 站试点。B 站使用宿主机 MediaCrawler 子进程和 `~/Desktop/Docker/mediacrawler-start-local/` 的固定补丁记录、独立 CDP 资料；微博等登录平台后续逐项准入。搜索、帖子、评论、热榜分别验收，不以公开热榜代替登录内容。
- 来源频次、请求与模型调用经来源预设及既有预算账本设置硬上限。预设执行策略按连接版本存于 `source_connection_versions.execution_policy` 非秘密 JSONB，来源预算按 owner/source/metric/窗口规则保持稳定身份；升版不返还已用额度。`schema.sql` 的新增列仅用于全新空库，保留库先满足 Design001 §6.3 同版本恢复合同。模型经既有 AiService 与按能力冻结的适配器，真实 Codex 及付费模型请求仍暂停。X 仅用官方 API，凭据与月度上限未确认前禁止真实请求。
- 模型适配器归 `ai/adapters/`，供应商可替换。报告中的数字一律由数据库计算，模型只负责判断和写作，正文的数字与链接须通过校验。
- 外部正文按不可信内容处理：进入模型时放入分隔的数据区，模型输出只接受结构化字段。
- 复用现有 MinIO。不更换 PostgreSQL 镜像，不引入向量库或搜索引擎（DEC-001-208）。
- 知识库是本地 Obsidian vault（`HOTKEY_OBSIDIAN_VAULT_PATH`，默认 `~/Desktop/Markdown/Obsidian`）的 `HotKey/` 子目录；HotKey 单向写入管理区块，原子写，不覆盖用户区块（[Design 005 第 3.3 节](docs/design/005-报告与知识库设计.md)）。
- 流水线由独立调度进程 `python -m worker.scheduler` 扫表驱动（DEC-001-203）；当前 M1/M2 只在宿主机运行一个 `python -m worker`，Compose 中的 worker 服务不启动（DEC-001-205）。
- 模型按原 Job 冻结的能力配置经 AiService 适配 Codex app-server 或明确启用的兼容接口，采用 override→环境配置→默认配置。凭据、模型兼容性及预算分别复核；embedding 使用独立配置。Codex 子进程只接最小环境变量（DEC-001-207）；配置成功不能代替真实模型验收。
- 推送秘密只从环境变量读取（DEC-001-210）；报告推送SMTP 已实现且默认关闭，飞书真实送达暂缓，渠道送达不阻断信息获取或报告生成。
- 冻结（保留代码，不再扩展、不作前置门禁）：032 备份 S03+、033 公平派发/熔断、028 S02+、029 S03、039 S02+、040、042 B0、010 历史回补、Flutter App。移出范围：044、045。

## 5. 实施与验证

当前排期且需要持续协调或独立验收的工作按 [Plan 索引](docs/plan/README.md) 推进；未来能力保留需求和设计，启动时再确定执行步骤。Plan 引用现行 Design，明确本轮差异、依赖与完成条件，不重复全量文件/接口/数据合同和多套 Checklist。小修复无需另建计划，仍先复现实际故障再实现、按影响范围回归并记录证据。核心契约未定不得列为实施就绪；真实账号/费用/渠道条件仅阻塞对应步骤。架构或数据库变化同步所属 Design、总 Design001 与本文。

持久化与任务合同见Design001 §4及子Design：到期窗口与采集周期归jobs，事件事实归events，原主题报告设置唯一读取/写入`monitor_topics.report_time`、`report_timezone`、`weekly_report_enabled`，冻结和导出归reports，不新增第二份主题设置；AIHOT公开刊期独立配置见Design048。原始导出归content，告警/投递审计归notifications，指定来源账号追踪归monitors，检索投影/回答归knowledge。实现与验收分别见BACKLOG和Acceptance。报告已统一为`/api/reports`并从运行OpenAPI重新生成原ribao客户端，不保留旧版本别名。生命周期、保留库恢复与真实依赖继续遵守现行门槛，不创建额外共享层、服务或存储桶。

`backend/app/monitors/runs.py` 专管主题手动采集的内部分区校验、幂等重放、来源逐项受理及 Job/Outbox 事务；`monitors/services.py` 保留主题和调度投影，`worker/scheduler.py` 负责到期领取与事实入账。前端主题页专属入口位于 `frontend/src/app/monitors/[topicId]/components/topic-run-actions.tsx`，只使用生成的 API 客户端。

主题采集版本在 `monitor_topic_versions` 固定关键词组、排序后的来源键和主题请求间隔；`monitor_topics` 与 `monitor_schedules` 保存当前投影，既有 Job 的配置版本不随更新重释。只改显示名称或报告/推送偏好不生成采集版本。来源保存须有已应用搜索预设及当前准入/运行策略；恢复还检查可用来源预算，真实采集可用性仍须逐来源验收。

`collection_due_windows` 属于 jobs 的持久到期事实，唯一键为 `(owner_id, schedule_key, due_at)`，允许未受理窗口没有 Job；`coverage_windows`、内容观察、资源尝试和预算账本仍分别保存执行事实。领域提供只读 DTO，调度受理在同一事务写入到期事实与 Job/Outbox，覆盖服务消费查询。

交付前执行后端 Ruff、mypy、pytest、OpenAPI 漂移与客户端生成检查，以及前端 ESLint、Prettier、类型检查、生产构建和浏览器验证。数据库和消息行为用隔离的真实 PostgreSQL/Redis/Kafka 验证。适配器用固定样本做契约测试，并以一次真实请求冒烟；模拟数据不能算采集成功。

## 6. 维护

PROJECT.md 是技术、架构、目录、API 契约和数据库约束的事实源；AGENTS.md 只补充实现门禁和命令，两者不得冲突。产品需求以总 PRD 001 和对应能力 PRD 为准；现行合同在 Design，当前排期的步骤在 Plan，证据与结论在 Acceptance。完成或合并的有效合同归入 Design，后置工作回归需求、设计和 BACKLOG，保留未通过条件后移除多余计划。历史原文由 Git 查阅；文档索引不复制版本、状态或验收矩阵。BACKLOG 是唯一进度看板（≤ 10 KB），HANDOVER 保持 ≤ 5 KB，均不追加流水账；小修复和普通文档整理不强制另建 Plan。

`operations` 是全量迁移实际维护领域，承接反馈、私有附件、操作审计、健康心跳和人工词典版本；只通过现有业务DTO编排任务/来源/预算/备份恢复，不建立第二任务或身份系统。运营token与用户会话分离，写入另核CSRF、actor/operation_id/版本；默认关闭，不能指定任意owner。选择评测事实归`analysis/evaluation_models.py`与`evaluation_services.py`，通过原AiService和预算，运营只读其DTO；真实模型仍暂停。

AI用途与供应商仍共用ai唯一调用账本；adapter显式component_key控制原ResourceComponentPolicy准入，embedding和未来兼容供应商不得借Codex组件许可。IndexNow保存已接收URL的资格位于原OperatorAuditOperation回执；每天按audit时间/ID/路径连续500项复验当前资格，变化才重新发送canonical，全部复验不加载供应商响应正文。没有额外模型、投递或SEO队列。

全量公开日周月刊的`report_edition_schedules`只保存每种完整刊期的有界扫描游标，不保存主题报告偏好；原`monitor_topics.report_time/report_timezone/weekly_report_enabled`仍是主题偏好的唯一来源。先检查最新完整刊期，再持续推进旧刊空洞，停机后不会被反复扫描最早旧刊阻塞。

全量阅读Web路径登记：`/discover`为资讯入口，`/items/[contentId]`为固定版本/许可正文，`/agent`为五工具与Markdown接入说明，`/feeds`为RSS订阅选择，`/publication/manage`为独立operator许可/投影维护；`/`为公开SEO Welcome，`/topics`为登录后工作区。路由专属组件在各页面components，明确跨页复用放`src/components/publication/`（卡片、读取错误、海报下载）；不复制网络客户端，唯一生成gongkaifabu/gongkaifenfa。所有入口覆盖加载/空/失败重试、partial/unknown、许可收紧与403/409，所有业务工作区页面始终noindex，公开Welcome和说明按Design001 §9.2索引。


本轮全量迁移补充边界见Design048：content/editorial_rendered_*持同ContentVersion正式格式与媒体事实；publication/media_mirror_*只持原Job/Evidence镜像引用，MinIO客户端归evidence/adapters/media_storage.py和进程生命周期；jobs/source_scopes.py只读真实任务收集范围DTO。新增Web `/discover/stories/[eventId]`是全成员许可通过的公开详情，`/editorial-sources`是六类源配置与运行，组件归其路由，全部接唯一运行OpenAPI。父进程续租、按启用handler计算Kafka窗口以及独立进程心跳/外部watchdog按Design048，不引入第二队列或事实源。

`publication/reading_groups.py`派生公开故事/事实/单件时间线，`publication/topics.py`与MIT静态行业定义派生行业主题目录、分页及索引准入；不新增材料或事件事实。Web `/discover/topics`与`/discover/topics/[slug]`使用唯一生成API，原`/topics`仍是监控主题。通知在生产结果事务内受理固定subject，原notification.scan/send任务复核所属领域typed DTO、目的地版本、当前许可和已保存供应商回执。

站点说明、联系信息和部署开关由operations站点设置持有同owner单例及修订，运营审计复用原表；联系二维码只接受限额且解码验证的图片，公共读取服从当前启用状态且禁止旧缓存。publication提供当前许可资料的统计DTO，禁止用数据库原总行数冒充公开可见数。Web `/about`、`/privacy`、`/terms`、`/changelog`、`/contact`、`/site/manage`分别为说明/公开联系/独立运营设置，专属组件接运行OpenAPI；`/discover/starred`是只存ID的本机收藏。

公开刊期`/reports/[kind]/[key]`仅日/周/月的最新完整稿，固定引用许可与索引授权取ALL相与；公开故事与专题采用同一实时indexable事实。IndexNow以原Job/预算/运营审计提交已准入的文章、刊期和事件canonical路径，三个领域分别使用连续有界游标；只记录接收/等待key验证，不冒充搜索引擎已收录。验证文件固定`/hotkey-indexnow-key.txt`且仅显式开启外部提交时提供。

`publication/share_images.py`从实时许可DTO生成1200×630分享PNG及1080×1440海报PNG，使用已锁定Pillow；`publication/assets/og-fonts/`是服务端唯一静态字体目录，复用固定AIHOT版本随附NotoSansSC子集并完整保留OFL声明。公开图片根路径固定/og/*，由公开分发路由和Next有限白名单装配；读取不触发外采/模型、不持久第二份正文。

海报二维码使用离线qrcode 8.2及Pillow编码当前许可canonical URL，固定纠错M和完整quiet zone；字体/OFL与移植MIT均保留。6h语义回溯以真实供应商/embeddings向量与同模型/维度cosine为依据，向量由events持有并沿原AiCall/Job/预算恢复，源码在ai/adapters/embeddings.py与events/embedding_execution.py，默认embeddings及AI均关闭。source.icons源图标只缓存已准入的源素材，复用Evidence/MinIO与原Jobs/预算，不在GET解析网站或请求头像。

来源试抓由sources/editorial_preview_*编排原Job/预算与OpsAudit，connections仅提供当前CAS/许可typed准入。离线样本、原来源异步试抓及未知人工核对使用唯一运行OpenAPI；不创建正式SourceRun或第二正文库。外部批次上限50，私有来源token与HMAC盐分开，滚动60秒同owner/真实peer共10次受理，由jobs/external_ingress.py读原Job并持advisory事务锁；connections持原SourceRun逐条回执与原内容Writer，GET不重新摄入。编辑来源写与人工重新分析也用独立operator+CSRF，分类/公开推荐理由与私有审计原因分开。

身份目录职责：`backend/app/identity/` 保存账户、会话、验证码、OAuth状态及身份服务/适配器；`api/routers/identity.py`只负责HTTP与Cookie，`db/metadata.py`登记模型。前端`src/components/auth/`保存跨页认证合同，`app/login/components/`保存登录组合；系统身份守卫使用生成客户端。欢迎页、登录及工作区共用BasicLayout、字体、语义颜色和官方组件。
