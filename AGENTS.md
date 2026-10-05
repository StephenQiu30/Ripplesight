# HotKey 工程规范

适用于整个仓库。技术与目录以 [PROJECT](PROJECT.md) 为准，产品和领域合同见 [docs](docs/README.md)，状态见 [BACKLOG](BACKLOG.md)。修改前阅读所属 PRD/Design 和相关测试；架构、目录或数据库变化先同步 PROJECT、所属 Design 与本规范。保留并行及无关修改，不依据共享工作区猜测归属。

## 实现边界

- 沿用 Python/FastAPI/SQLAlchemy2/PostgreSQL/Redis/Kafka 和 pnpm/Next/React/TypeScript/shadcn/Radix/Tailwind/Axios；App 独立 Flutter/Dart。已有选择不重复确认，有实质部署、费用、平台或框架影响的未决项先明确决定。
- 按真实业务切片创建文件，先明确主责、目标路径、接口/DTO、事务、依赖、任务恢复及验证范围。无使用方不建空模块，不建第二队列/账本/正文库，不用通用 BaseService/BaseRepository 或多层空接口。
- 后端源码仅 `backend/app`，入口 `main:create_app`；main 只装配生命周期，api/router 汇总路由。Router 不直接用 ORM、导入或构造 Service、发布消息；dependencies 只注入，不管理业务事务。
- 服务只直接导入本领域 ORM，跨领域经所属函数/DTO；跨领域原子写显式共用 Session，由最外层提交/回滚，内层只写或 flush。Schema 不依赖 ORM/Session/FastAPI，Adapter 不依赖 API/ORM/Worker/任务状态。
- core 只通用配置/错误/Schema/时间，db 只基类/连接池/模型注册；新增领域须在 PROJECT/Design 登记，并先用失败架构测试证明未登记代码被拒绝，不能预先白名单。
- 来源/MinIO/模型 SDK 分别归 sources/adapters、evidence/adapters、ai/adapters；持久业务状态归原领域。复用官方客户端与标准库，仅封装业务合同/生命周期/外部差异。
- Session 不跨线程/任务，DTO 在 Session 有效期内构造；同步数据库使用同步路由，阻塞 SDK 不直接运行在异步路由。资源按所属进程创建关闭，导入不联网；API lifespan 不启动 Worker。
- Worker 父进程独占 Kafka Consumer/offset/任务终结，spawn 子进程自行建立资源。取消、硬截止、未知退出均有界回收整个进程组，不能以协作截止或重建 Consumer 代替进程恢复。
- 状态与 Outbox 同事务；幂等业务提交后仅提交连续完成 offset。jobs 管持久重试、预算、租约和执行权；Redis 只可重建状态，适配器重试不持持久任务。重复消费、旧 lease/epoch、撤权与取消不能继续写。

## 数据与契约门禁

- 唯一 DDL 为 `backend/database/schema.sql`，完整结构自带 BEGIN/COMMIT，只用于新空库。禁止额外 SQL、Alembic、ORM/启动建表和 SQLite 业务持久化；datetime 统一 TIMESTAMPTZ。
- DDL、ORM 和数据库断言同批变更，先证明旧结构失败，再用全新真实 PostgreSQL 核对全部映射表/列/类型/可空性/主键。psql文件、CI stdin、Compose entrypoint 均验证失败无残留。
- 业务库固定 hotkey，宿主/Compose一致。测试只用独立 hotkey_test_<suffix>，执行者在成功或失败后清理；恢复流程清理 hotkey_restore_*。禁止业务库跑集成测试。
- 保留数据先按 Design001 §6.3 停写、备份、实际恢复、完整新库建表、校验导入再切换，核对整行JSON/对象哈希/关联/预算/offset并保留回退；旧库不能直接运行完整DDL，同桶副本不算独立灾备。
- HTTP唯一源为路由注解/Pydantic → `/openapi.json`；声明稳定operation_id、中文summary/tag、约束、成功模型、实际错误、认证与必要头。不手写OpenAPI、客户端DTO或生成文件。
- 成功为资源/`PageView[T]`/`JobAcceptedView`，错误统一 ErrorView，应用错误不携HTTP状态；禁止全局body改写或为所有路由统一声明所有错误。请求ID、5xx/422脱敏、必要头、运行/OpenAPI/客户端一致；204/304/文件/流按真实协议。
- Web/App按code/status分支，不按message判断；传输层不全局弹提示或自动重试写操作。核对HTTP、网络、超时、取消、非JSON、失败任务正常查询及请求ID头/body回退。
- 账户小型头像由 identity 管理规范化 PNG 与摘要，原图不持久化；资料写再次复验当前会话与绑定 CSRF，读取仅本人/当前摘要，Web 使用生成客户端和既有全局会话。存量结构按 Design001 §6.3 保留升级。
- 真实账户、12小时可撤销会话、CSRF、个人归属与历史映射按Design001 §9.2；禁止默认账号/会话或首个注册者取得旧分区。运营令牌、来源授权独立；GitHub/邮件未配置时明确不可用，受控认证不代替真实授权/收件。

## Web 目录与页面门禁

- 富文本阅读使用 `components/editor/Viewer`，支持块 JSON 与既有 Markdown/HTML/text，统一清洗正文与链接，不能执行原始 HTML；保留 SSR 阅读与报告引用。阅读页不提供本机笔记或编辑工具，阅读位置/原文译文模式仅保存于原本机阅读状态键。

- 业务请求只用 `frontend/src/api` Umi生成函数，接 `src/request.ts` 唯一Axios；业务不直接导入Axios/传输函数，不用fetch/XHR或手写下载URL。只允许导入错误类和请求选项类型，选项不能覆盖生成方法/地址/参数。
- SSR origin 在传输层统一解析，限定Cookie逐请求传递，不保存在全局defaults；透明同源代理只做基础设施转发。ESLint检查业务边界，生成漂移检查API，基础设施例外只按确切路径处理。
- 页面专属组件在app路由components，跨页稳定复用才迁components/<feature>，官方基础组件在ui。根布局装配独立layout目录的BasicLayout/Header/Footer/Container/UsageGuide；不建features/common/patterns/shared或scripts。
- 各页面只组合正文，不重复主导航、main、全屏高度、外侧宽度/边距。头尾固定、唯一main滚动、统一容器，加载/错误/404/global-error和打印一致；阅读位置使用真实main节点。
- `/login` 不显示顶部 Header；登录加载和恢复态沿用无 Header 的同一外壳，正文滚动、页脚和全局 Sonner 仍由 BasicLayout 管理。短请求只使用主按钮忙碌/禁用态，不追加中止 HTTP 请求的“取消”按钮；保留离页中止及真实任务取消、编辑/对话框退出。
- 视觉规范见frontend/DESIGN：黑白留白、语义令牌、无装饰边框、Tailwind命名尺度与标准断点；输入/错误/焦点/浮层保留必要轮廓。组件设计明确名称/领域/复用/路径/数据/加载空态部分错误权限。
- 操作失败/校验/成功/主动取消统一使用官方shadcn Sonner，BasicLayout仅挂载一个Toaster；禁止表单、菜单或内容底部的临时反馈块和自定义Toast。加载失败保留原生Empty/Alert恢复入口，持久业务错误事实仍作为内容展示；不在传输层自动通知，取消/失效响应不弹错误。
- 首页、说明页与许可阅读入口公开；资讯/专题/单篇/日周月刊只读取明确配置的公开发布分区，模型榜只读已发布轮次。未指定发布账号保持未发布，不按Cookie或首个账户选择。个人关注/报告/发送/管理的HTML含prefetch、API及认证出口验证真实会话并noindex。网络故障不能当退出或阻断公开阅读。公开索引逐项核准，元数据使用实际站点origin，无伪统计。
- CSP每请求nonce，交互HTML动态渲染、private/no-store；创建页connection()，脚本/响应nonce一致且不跨请求复用。生产standalone/非root/只读；浏览器验证冷进入及交互。
- 测试仅frontend/tests，Vitest只扫描此目录；src不放测试或导入测试框架，生产类型/Docker排除测试，独立测试类型仍检查。后端测试保持backend/tests。
- 本机Web8666/API8667，启动、映射、生成/转发、登录Origin、SEO及CI默认一致；Compose内部8080，Browser WS3000独立。pnpm唯一Web包管理器，提交pnpm-lock和packageManager。

## 来源、模型与安全

- 仅公开或获授权数据；逐来源校验许可/授权、能力、分页/尾段、频率、费用、版本和持久证据。配置/probe/空结果/诊断不算采集成功，未知保持null/partial，不造覆盖。
- 七平台新增接入按Design007 §11复用本机RSSHub/Firecrawl等，供应商费用硬上限零；收费或计价未知fallback、付费代理/云模型不得执行。RSSHub路由存在不等于准入，审查实际下游/Cookie/浏览器回退，访问风控不自动绕行。editorial profile材料进入个人主题须有固定规则/内容版本和原Job的持久关联合同；Firecrawl补正文绑定原身份，不直接复用webpage.collect制造副本。agent-browser用于产品验收，不作为生产爬虫或解除Browser冻结。
- 四搜索六榜是 M1 正式验收范围，不作为公开基础资讯、个人日/周报的统一前置；各切片须具备所用来源、许可、真实输入与持久读取/权限证据。原生 RSS/Atom 复用编辑来源类型、逐源准入，不增默认来源枚举；公开刊物 weekly 不证明个人 report.weekly 已有处理器，现行缺口见 BACKLOG。
- 来源预设冻结连接execution_policy，稳定预算按owner/source/metric/窗口计量；升版/人工重试不返还累计额度。主题不可变采集版本只含关键词/来源/请求间隔，名称/报告偏好不升版；旧Job不按当前投影重释。
- 评论保留原生不透明ID、作品/根/直接父/回复目标与关系缺口；无可信尾段不确认覆盖，HN整树/cache切页不算逐根远程分页，B站一级评论每帖≤20。
- HTTP适配器强制主机白名单并校验每跳重定向；GET读取、规则预览和本地样本不外采；已保存来源的远端试抓只经显式Job、许可与预算受理。RSSHub/SearXNG主机只127.0.0.1或host.docker.internal，固定1200/8888、路由与引擎，变更须重新应用预设。
- MediaCrawler仅本人B站个人非商业试点，固定宿主子进程、独立CDP及三版本校验。资料700/文件600、拒绝符号链接/宽权限/超限，子进程最小环境；验证码/登录失效/频繁访问立即停用，本人核查后人工恢复，缺同轮缓存不补网络。
- 通用Browser固定Playwright1.63.0原生WS、私有令牌和Squid出口；仅example.com探针，未准入真实平台。维护browser_state拒绝不可信路径且验证当前版本/身份/停用，文件存在不代表有效。
- 真实Codex/付费请求暂停；X凭据/月上限未定前零请求。Reddit须当前官方 API 显式批准及 OAuth，商业用途另须书面批准，公共 Data API 迁移/退役风险按PRD007官方依据复核；OAuth不代替准入。报告SMTP默认关闭，飞书暂缓，unknown发送/付费结果须人工处理，不自动重发。
- 模型输入为隔离不可信材料，输出严格结构化；数字/排序/引用由程序计算校验。AI各能力共用唯一调用/预算账本，embedding独立配置/准入，不借Codex组件许可。
- publication只持许可/投影/修订及原Job/Evidence引用，不存第二正文；读取/ETag/304/写入逐次复验ALL成员许可、固定版本及撤回。原始资讯run为空、标明未分析和摘要来源，不造精选/评分/事件；原五分钟republish扫描复用原始身份。GET不外采/付费，派生阅读/主题不制造事件事实。
- 站点设置、联系图/二维码、反馈、词典和维护归operations，审计复用原账本；评测事实归analysis。通知按固定subject/目标版本/当前许可/已有供应商回执恢复，不建第二投递队列。
- 环境文件只放仓库根目录，唯一模板为根 `.env.example`；本机共用根 `.env`，生产显式选择根 `.env.prod`，禁止子目录 `.env`、`.env.local` 或独立模板。Web 只加载所需公开/服务端 Web 字段，不加载后端秘密；显式注入环境优先。
- 配置用HOTKEY_前缀；秘密不入Git/日志/前端/模型输入，日志不含原URL/query/正文/Cookie/Token/连接串。公开异常稳定脱敏；供应商原始异常在边界转换。
- Compose应用只在根docker-compose定义，prod include复用并显式.env.prod；env文件独立，本机复用已有服务，不复制外部编排/删除库卷。知识库只写HotKey管理区，保留用户区块。

## 验证与交付

按变更影响执行必要检查；真实数据库/消息/对象恢复与受控样本分别判断，UI用浏览器验证。失败、skip、deselected、未执行或中断不计通过；旧代码/库/窗口证据不证明当前就绪，产品窗口不拼接。

在backend执行：

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
```

在frontend执行：

```sh
pnpm lint
pnpm typecheck
pnpm format:check
pnpm test
pnpm openapi:check
pnpm build
```

契约变更先启动同提交API，顺序生成/检查客户端，再跑前端，避免并行改写生成目录。数据库/消息改动验证事务回滚、重复消费、旧租约及进程重启；必要真实PostgreSQL/Redis/Kafka/MinIO集成不由mock替代。页面验证桌面/窄屏、键盘、焦点、空/加载/错误/权限及无障碍。纯文档检查本地链接、规则一致性与git diff --check。

文档分工与编号规则唯一见 [docs/README](docs/README.md#3-写在哪里)：PRD 写需求/AC，Design 写现行合同，BACKLOG 写总体进度，Acceptance 写实际证据；PLAN 只在用户明确要求时建立（现有 [PLAN007](docs/plan/007-公开信息免费采集执行计划.md)、[PLAN009](docs/plan/009-AIHOT参考对齐偏差计划.md)），其 WP 状态只在 PLAN 维护。普通整理不新建计划、审计流水或验收文件，不以删除文档关闭需求。编号不复用，EV 证据编号永不重编号；其余重编号须用户明确要求并在 docs/README 留对照表。许可证与署名完整保留。

未经用户明确授权，不提交、推送、创建/合并PR或删除远端引用。授权后检查差异、秘密和远端状态；标题唯一格式 `type(scope):中文动宾描述`，冒号后无空格，≤72字符。type限feat/fix/test/refactor/docs/chore/perf/build/ci/revert，scope用稳定小写英文。正文/脚注中文，说明变更、原因、实际验证；不兼容用!及BREAKING CHANGE中文说明，一个提交一个可独立验收目的，生成物与源同提交。

定时任务采用APScheduler 3.x内存进程时钟（30秒、单实例、合并错过tick），业务到期、幂等、重试、租约和投递仍由PostgreSQL/原Job/Outbox持久化，不使用数据库JobStore。根Compose worker profile配套Worker/Scheduler，API不运行计时器。用户经账户验证邮箱后自行订阅，普通会话/CSRF/CAS隔离，无需运营令牌；发送前复验当前邮箱与主题订阅。平台SMTP凭据保留根环境配置。
