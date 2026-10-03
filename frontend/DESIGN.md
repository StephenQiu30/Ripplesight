# HotKey Web 设计规范

## 视觉

- 使用 Geist；Geist Mono 仅用于数据和技术标识。字体装配集中在 `src/layout/layout-fonts.ts`，根 HTML 和全局恢复页复用相同字体变量。
- 颜色、字体和圆角统一定义在 `src/app/globals.css`，业务组件只使用语义令牌。
- 页面通过留白、排版和表面明度建立层级，静态信息区不使用装饰性边框。
- 输入、选择、错误、键盘焦点和浮层保留必要轮廓。
- 布局只使用 Tailwind 命名尺度和 `sm`、`md`、`lg`、`xl`、`2xl`，禁止原始像素值和任意布局尺寸。

## 组件

- shadcn/Radix 基础组件放在 `src/components/ui/`。
- 全部页面的交互控件只组合官方 shadcn/ui + Radix：选择使用 Select/SelectGroup，布尔选项使用 Checkbox/Switch，折叠内容使用 Collapsible，数据表使用 Table，表单使用 FieldGroup/Field/FieldLabel，错误提示使用 Alert。业务源码不手写 button、input、select、textarea、details 或表格组件；ESLint 检查此边界。文档标题、段落、列表、页面结构、链接及音视频仍保留必要语义标签，不为它们增加包装组件。
- 组件使用原生 variant/size，className 只调整布局；避免额外卡片、阴影和装饰边框。表单窄屏单列、控件允许收缩、长选项在触发器中截断并在浮层中换行。Select 的“全部/清除覆盖”保留空值和原 FormData；Collapsible 关闭时保留内部已填状态。间距使用 flex/grid + gap，不使用 space-x/space-y。
- 跨页面复用组件按功能领域放在 `src/components/<feature>/`。
- 页面专属组件放在对应 `src/app/<route>/components/`；根页面使用 `src/app/components/`。
- 全站外壳统一在独立 `src/layout/`：BasicLayout 在根 App Router layout 装配，BasicHeader、BasicFooter 和共用 UsageGuide 在同目录。外壳使用 `h-dvh` 的 flex 布局，头尾不收缩，正文 main 独立滚动；所有页面的头尾及正文统一 `max-w-7xl`、`px-5 sm:px-8`，正文 `py-10 sm:py-12`。仅保留一个 main，页面组件不再设置全屏高度、页面级最大宽度和外侧内边距；内部表单、文章、表格按内容保留合理尺度。路由切换重置正文滚动，提供跳到正文的键盘入口；打印恢复正常流并隐藏头尾。
- LayoutContainer 是头尾和正文的唯一宽度定义；三处 region 同时预留对称的稳定滚动条槽，长页/短页切换不会产生容器宽度偏移。阅读进度通过布局提供的滚动节点保存与恢复，保留本机数据格式。
- 不创建 `features`、`common`、`patterns` 或 `shared` 目录。
- `page.tsx` 只处理页面入口、数据边界和组件组合。
- 组件至少被两个页面稳定复用后才能迁入 `src/components/<feature>/`。

每个切片在 Design 阶段记录组件名称、所属领域、复用范围、目标路径、数据来源及正常、空、加载、部分、错误和无权限状态。

## 首页

首页在本目录实现，使用 Vercel 黑白留白风格；不增加独立应用、业务状态层或额外配置流程。首页主入口通过 `/login` 进入系统，已登录后创建关注使用现有 `/monitors/new`。主题创建、修改、来源准入与保存使用当前 OpenAPI 生成 API；示例只用于说明，不显示为真实采集结果。

| 组件                                    | 领域与复用范围       | 路径                                  | 数据与状态                                                           |
| --------------------------------------- | -------------------- | ------------------------------------- | -------------------------------------------------------------------- |
| HomeContent                             | 首页专属组合         | src/app/components/home-content.tsx   | 静态内容与说明浮层开关；无业务 API                                   |
| BasicLayout / BasicHeader / BasicFooter | 全站页面骨架与导航   | src/layout/                           | 唯一正文滚动区、路由选中态、品牌、共用指南与真实站点链接；桌面及窄屏 |
| UsageGuide                              | 首页和导航复用的说明 | src/layout/usage-guide.tsx            | 静态指南/示例 Dialog，关闭后返回触发器焦点                           |
| HeroSection                             | 首页专属主视觉       | src/app/components/hero-section.tsx   | 选定文案、装饰品牌图、登录/系统入口与示例说明                        |
| BrandLockup / BrandMark                 | 跨页面品牌           | src/components/brand/brand-lockup.tsx | 复用 src/app/icon.png 母版；无 API 状态                              |
| Button / Dialog / DropdownMenu          | 跨页面官方基础组件   | src/components/ui/                    | 保留官方 Radix 语义和交互；必要的首页尺寸变体使用命名尺度            |

装饰主视觉位于 `public/brand/hero-brand-soft.png`，是既定品牌的阴影展示资产，不作为第二套品牌母版。布局使用现有 Tailwind 尺度与标准断点。首页无加载、空、部分或权限状态；业务页面保留当前加载、空、错误重试及成功状态。

## 公开Welcome与登录工作区

`/`保留既定黑白留白主视觉作为SEO Welcome，公开Header只显示站点说明/指南及登录入口，不显示工作区菜单；主操作“开始使用”进入 `/login`，登录后默认 `/topics` 或安全站内原目标。已登录工作区保留原“更多”导航、统一容器、固定头尾及唯一正文滚动区，显示账户和退出。公开说明仅about/privacy/terms/contact/changelog，公开文案不读取个人业务统计；login默认noindex，工作区始终noindex，robots/sitemap只列公开路径。

登录专属组件归 `src/app/login/components/`，跨页会话/账户与守卫归 `src/components/auth/`；全部类型和请求来自Umi生成的identity API。账号密码、GitHub App、邮箱验证码共用真实数据库会话，覆盖加载/不可用/字段错误/限流/取消/成功/网络重试。业务深链接和prefetch均先验证会话，网络失败不能当成已退出；SSR按请求转发限定Cookie，代理只转发HotKey身份Cookie/Set-Cookie。保持官方shadcn/Radix表单、按钮、菜单、无装饰边框、语义颜色及命名尺度。

登录页采用用户选定的 Product Design 方案 1：桌面左侧品牌短句与浅灰涟漪图片，右侧登录表单；窄屏优先表单，隐藏装饰故事区域。登录方式不使用 Tab，账号密码为默认表单，邮箱验证码与 GitHub 在主按钮下方作为同尺寸按钮；邮箱表单保留返回账号密码的按钮。不可用方式保留禁用按钮和明确说明，密码显示切换不改变认证合同。

密码表单接受邮箱或用户名，沿用生成接口的username字段。邮箱验证结果按has_password分支：已有密码继续原安全目标，缺密码进入账户首次设置。首次设置显示已验证邮箱、新密码与确认密码，内部保留原用户名；超过新近验证期限时切换至绑定邮箱验证码复核，保留已填信息和安全returnTo。已有密码账户保留用户名及当前密码/邮箱验证码维护。凭据保存成功返回轮换后的真实会话，首次设置继续工作区，常规修改留在账户设置显示成功；取消或晚到响应不能触发导航。

| 组件                              | 领域与复用范围       | 目标路径                                                             | 数据与状态                                                                      |
| --------------------------------- | -------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| LoginExperience / LoginBrandStory | 登录页专属组合与装饰 | src/app/login/components/login-experience.tsx；login-brand-story.tsx | 静态文案与 public/brand/login-ripple.png；桌面/窄屏，不读取业务统计             |
| LoginForm                         | 登录页专属认证组合   | src/app/login/components/login-form.tsx                              | 原生成 identity API；方式按钮、密码显示、验证码、加载/不可用/失败/取消/安全回跳 |

GitHub 按钮使用官方 GitHub-Mark 栅格素材 `public/brand/github-mark.png`；品牌母版继续为 `src/app/icon.png`。涟漪为独立装饰图，不作为另一份品牌母版；不添加新网络层、服务或页面外壳。

访问与数据隔离合同见 [Design001 §9.2](../docs/design/001-热点舆情监控平台总体设计.md#92-公开欢迎页登录与个人数据访问)；真实第三方授权/邮件核收不由受控测试代替。

| 组件                                  | 领域与复用范围       | 目标路径                                                               | 数据与状态                                                                                                                                   |
| ------------------------------------- | -------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| LoginForm                             | 登录页专属           | src/app/login/components/login-form.tsx                                | getLoginOptions、createIdentitySession、sendEmailLoginCode、verifyEmailLoginCode、startGithubLogin；读取/不可用/字段错误/限流/取消/成功/重试 |
| CredentialsForm                       | 账户设置专属         | src/app/account/components/credentials-form.tsx                        | 当前生成会话、has_password、updateIdentityCredentials、已验证邮箱验证码；首次设置/密码确认/当前密码或邮箱证明/期限/保存轮换/错误/安全回跳    |
| IdentitySessionProvider / AccountMenu | 全站会话与导航       | src/components/auth/                                                   | 消费proxy验证后的IdentitySessionView；退出真实会话后返回Welcome，失败保留当前账户                                                            |
| access / layout-session               | 路由和服务端会话读取 | src/components/auth/                                                   | 公开路径、安全站内回跳、限定内部已验证会话头；不保存会话秘密或自行发请求                                                                     |
| welcomeMetadata / robots / sitemap    | 公开SEO页面          | src/components/site/welcome-metadata.ts；src/app/robots.ts、sitemap.ts | 实际站点origin、canonical/OG；仅Welcome和公开说明入站点地图，工作区始终noindex                                                               |

公开站点origin使用`NEXT_PUBLIC_SITE_ORIGIN`或服务端`HOTKEY_WEB_ORIGIN`，本机固定Web8666/API8667，默认origin为`http://127.0.0.1:8666`；不调用私有业务API生成欢迎页元数据。登录页在上游会话验证故障时显示统一PageState和原安全目标重载操作，保持会话故障与未登录状态的区分。修改凭据成功200后撤销所有旧会话并建立当前新会话；已登录无密码账户访问登录页也进入设置步骤。验证码标识仅保存在组件内存中。

## API 与状态

- 公共协议遵循 PROJECT.md 与 AGENTS.md 的现行契约；运行 OpenAPI、类型化资源和 ErrorView 共同门禁已接入。本文件仅细化 Web 消费与展示，不另定义返回模型。
- 资源、分页、受理 DTO 和 ErrorView 来自同提交运行时 OpenAPI；错误读取 details，请求 ID 支持响应头/body 回退。HTTP、网络、超时、取消和协议失败分开；204 与文件不解析为 JSON，失败任务查询与合法空结果保持正常读取语义。
- 传输层不全局弹提示、不按 message 分支、不自动重试写操作。字段错误就地显示，页面失败保留恢复入口，操作结果使用适当短时反馈；旧数据刷新失败要标明过期。
- Umi OpenAPI 将端点和类型直接生成到 `src/api/`。
- 所有生成请求统一使用 `src/request.ts`，页面不得手写端点或创建第二套 HTTP 客户端。
- ESLint 拒绝业务源码直接导入传输函数/HTTP 客户端或调用网络原语；页面可使用生成函数、传输错误类和请求选项类型。透明同源代理只做通用转发，生成代码只由生成器更新。
- 浏览器同源与 SSR 后端 origin 由 `src/request.ts` 统一解析，业务请求选项只允许头、取消、响应格式和超时，生成的方法/URL/参数不能被覆盖。
- Agent 页专属 `SelectedSnapshotDownload` 位于 `src/app/agent/components/selected-snapshot-download.tsx`，使用生成的 `getSelectedPublicationSnapshot` 下载 JSON 快照，覆盖加载、错误和再次下载；不手写 API 地址。
- 测试统一在 `tests/`，按原业务路径组织 `app/`、`components/`，根配置测试归 `tests/config/`；`src/` 只放业务源码和生成客户端。Vitest 仅扫描 tests，生产类型检查及 Docker 构建排除测试；独立测试 TypeScript 配置继续检查所有测试，ESLint 拒绝业务目录中的测试或测试依赖。
- App Router 统一提供 loading、error、global-error 和 not-found 边界。
- `src/components/system/page-state.tsx` 中的 `PageState` 只处理正文错误、空态、无权限和恢复操作。加载、错误和404沿用根 BasicLayout，读取失败时主导航及页脚继续存在；global-error 替代根布局时独立装配 BasicLayout。不在状态组件内部请求业务数据。

## 可访问性与运行

- 交互支持键盘焦点，装饰图形使用 `aria-hidden`，状态区域提供语义名称。
- 动效遵循 `prefers-reduced-motion`。
- 页面必须完成桌面和窄屏浏览器检查。
- 本机开发页关闭 Next.js devIndicators，避免开发工具浮标覆盖固定页脚；终端与浏览器开发日志仍可用于诊断。
- 生产镜像使用 standalone、非 root、只读文件系统和 `/health` 健康检查。
- CSP nonce 由 `src/proxy.ts` 每请求生成；需要客户端交互的 HTML 入口必须按请求渲染。主题创建页在服务端入口等待 Next.js `connection()`，保持来源校验；生产脚本 nonce 必须与当前请求 CSP 一致，HTML 不使用共享缓存。生产镜像的 runtime 检查与浏览器冷进入均需通过。

## 业务页面

业务页面使用正式 Next.js、生成客户端、Axios 和 CSP。Swagger 的唯一源为 FastAPI 路由/Pydantic，临时导出的 OpenAPI 仅供生成校验，不成为手维护文件。页面只调用 `src/api/` 中的生成操作。

| 组件                                                                             | 领域与复用范围                   | 目标路径                                                                 | 数据来源与状态覆盖                                                                                                                       |
| -------------------------------------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| BasicHeader                                                                      | 全站主导航                       | src/layout/basic-header.tsx                                              | 静态真实会话与公开/工作区路由；统一桌面/手机导航、路由匹配与当前页语义，指南 Dialog                                                      |
| TopicsWorkspace / TopicList                                                      | 关注入口 / 列表                  | src/app/topics/components/；src/components/monitors/topic-list.tsx       | listMonitorTopics；加载、空、分页、归档筛选、错误重试                                                                                    |
| EventList / EventHotList                                                         | 已确认事件列表与关注热度         | src/app/events/components/                                               | listEvents / listHotEvents；主题、来源与搜索筛选、游标分页、真实热度、加载、空、权限和错误重试                                           |
| TopicForm / TopicEditor                                                          | 创建 / 编辑专属                  | src/app/monitors/new/components/；src/app/monitors/[topicId]/components/ | create/get/update/clone/pause/resume/archiveMonitorTopic；来源加载、字段422、版本冲突、重复提交、保存状态                                |
| KeywordGroupField / TopicSettingsFields / TopicRulePreview / TopicAdvancedFields | 创建与编辑复用                   | src/components/monitors/                                                 | generated MonitorTopic 输入与预览；关键词、可选进阶规则、来源准入、请求间隔；预览不采集                                                  |
| TopicRunActions                                                                  | 编辑页专属运行入口               | src/app/monitors/[topicId]/components/topic-run-actions.tsx              | runMonitorTopic；逐来源受理/拒绝、幂等、任务跳转，受理不表示完成                                                                         |
| SourcesWorkspace / SourceSettings / SourceConnectionActions                      | 来源配置专属                     | src/app/sources/components/                                              | listSourceCapabilities / updateSourceConnection；加载、禁用、凭据与准入理由、错误重试与写入反馈；预设仍由维护者CLI应用，没有网页写入端点 |
| SourceCoveragePanel / CoverageWindowTable / CoverageWindowDetail                 | 来源页二级覆盖信息               | src/app/sources/components/                                              | generated collection coverage；筛选、分页、空、部分、缺口、错误与详情；官方 Tabs/Sheet 渐进展示                                          |
| ContentList / WebpageCaptureForm / ContentDetail                                 | 内容列表与详情专属               | src/app/content/components/；src/app/content/[contentId]/components/     | list/getContentRecord / createCollectionJob；分页、空、错误、真实证据；网页受理不冒充已采集                                              |
| AnnotationPanel / CommentRefreshAction / CommentThreadList                       | 内容详情专属                     | src/app/content/[contentId]/components/                                  | 当前内容标注与评论/就绪/运行 API；缺失、部分、失败、读取与受理状态                                                                       |
| HotlistWorkspace / SnapshotSelector                                              | 热榜页专属                       | src/app/hotlists/components/                                             | listHotlistSources / list/get snapshots；来源选择、历史分页、合法空、错误和快照状态                                                      |
| JobHistory / JobHealthSummary / JobDetail                                        | 任务列表与详情专属               | src/app/jobs/components/；src/app/jobs/[jobId]/components/               | list/get/cancel/retryCollectionJob / listContinuousFailureIssues；筛选、分页、失败读取、取消重试与终态                                   |
| ReportList / ReportResults / ReportDetail / ReportDetailContent / ReportMarkdown | 已有报告读取专属，非核心二级入口 | src/app/reports/components/；src/app/reports/[reportId]/components/      | list/getReport；只读分页、空、错误和实际状态，无新生成/投递配置                                                                          |
| Collapsible / Empty / Item / Spinner                                             | 多页官方基础组件                 | src/components/ui/                                                       | 官方Radix折叠、空态、列表和加载组件；不承载业务状态                                                                                      |

配置第一层只呈现名称、关键词与来源，进阶规则/频率按需展开。编辑隐藏的既有报告偏好按原值传回，避免覆盖数据。来源主入口是配置，覆盖/技术字段二级展示。所有页面沿用语义颜色、命名尺度、官方表单/浮层/菜单；不新增数据状态框架。业务入口继续动态渲染、`noindex`，取消请求不显示为业务失败。

主导航归 `src/layout/basic-header.tsx`；任务路由内的 `job-presenters.ts` 复用时间/状态/能力展示，报告详情路由内的 `report-links.ts` 复用安全 HTTP URL 规则；两者均无请求与状态所有权。

## 日周月刊

`/editions`使用`src/app/editions/components/edition-list.tsx`，读取唯一生成客户端`rizhouyuekan.ts`，按日/周/月与刊期分页展示最新修订，接受有原因的补刊/新修订任务；加载、空、错误、409与unknown人工复核分别呈现。`/editions/[editionId]`使用专属edition-detail，按冻结条目与程序指标读正文，保留修订列表和历史标记，权限失效时整稿隐藏；不在页面触发模型。人工修订只允许已冻结引用，下载同一Markdown稿。旧`/reports`保留主题统计口径，通过导航区分。组件复用shadcn表单、按钮、空状态与根 BasicLayout，布局使用命名Tailwind尺度，无新共享层。

## 公开资讯与分发

`/discover`组合PublicItemCards、筛选和selected同步；`/items/[contentId]`组合ItemReader、引用、原译文/目录/许可状态；`/agent`说明真实五工具与Markdown；`/feeds`选择已核许可的摘要/全文/分类/刊期RSS；`/publication/manage`组合PublicationManager管理版本化来源许可、纠错和本地重建。PublicItemCards、PublicationFailure、PosterDownload跨页面复用归components/publication，其余归路由专属components；唯一数据来源为运行OpenAPI生成gongkaifabu/gongkaifenfa/quanwenfanyi。原/与品牌不改；正文/媒体默认安全原站链接，镜像独立任务未完成时不可标已缓存。覆盖加载、空、失败重试、部分译文/unknown、权限403与版本409、重建进度；operator令牌只用户会话内存，不内嵌源码或localStorage。

`/discover/stories/[eventId]`专属story-reader读取公开故事DTO及复用PublicItemCards，ALL成员撤回时整页隐藏，不用内部/events端点降级拼稿。`/editorial-sources`专属配置/运行组件读取bianjilaiyuan，按RSS、HTML、JSON、X、公众号和external区别显式字段、currentversion、reason/opid、运行unknown和人工动作；参与模式不自动扩大公开许可，令牌只在当前会话内存。

`/discover/topics`与`/discover/topics/[slug]`为行业主题目录和资料阅读，专属组件使用生成gongkaifabu的主题DTO、当前许可条目、相关主题与索引状态；不混入原`/topics`监控配置。资讯时间线按故事/事实/单件折叠，代表条目与进展的首次出现锚点分开，展开仍使用同一筛选和发布修订，覆盖空、分页、撤回和刷新冲突。

`/discover/starred`复用publication本机状态组件，500收藏/5000已读、ID导入导出、坏数据/存储失败与跨tab变更可见，不持久正文。`/about`、`/privacy`、`/terms`、`/changelog`是本地说明；`/contact`只读启用后的实际联系DTO；`/site/manage`专属配置组件以会话内运营令牌保存CAS/原因/图片，禁用后旧二维码不可读。所有业务数据仍经生成客户端，静态说明不显示伪统计。

`/reports/[reportId]/[key]`（reportId严格为kind）为公开刊期只读阅读页，kind仅daily/weekly/monthly，专属PublicEditionReader消费getPublicEdition及复用publication稿件组件。与原监控主题报告及/editions修订操作分离，公开稿只读最新完整修订且ALL引用当前许可有效；404撤回整稿、错误可重试、无生成或编辑控件。公开故事/刊期/专题Metadata按实际DTO.indexable决定noindex；故事和刊期要求所有固定叙事成员的当前索引许可。IndexNow根验证文件经固定Next rewrite及代理白名单，不开放任意文本文件代理。
