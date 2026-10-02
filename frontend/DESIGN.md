# HotKey Web 设计规范

## 视觉

- 使用 Geist；Geist Mono 仅用于数据和技术标识。
- 颜色、字体和圆角统一定义在 `src/app/globals.css`，业务组件只使用语义令牌。
- 页面通过留白、排版和表面明度建立层级，静态信息区不使用装饰性边框。
- 输入、选择、错误、键盘焦点和浮层保留必要轮廓。
- 布局只使用 Tailwind 命名尺度和 `sm`、`md`、`lg`、`xl`、`2xl`，禁止原始像素值和任意布局尺寸。

## 组件

- shadcn/Radix 基础组件放在 `src/components/ui/`。
- 跨页面复用组件按功能领域放在 `src/components/<feature>/`。
- 页面专属组件放在对应 `src/app/<route>/components/`；根页面使用 `src/app/components/`。
- 不创建 `features`、`common`、`patterns` 或 `shared` 目录。
- `page.tsx` 只处理页面入口、数据边界和组件组合。
- 组件至少被两个页面稳定复用后才能迁入 `src/components/<feature>/`。

每个切片在 Design 阶段记录组件名称、所属领域、复用范围、目标路径、数据来源及正常、空、加载、部分、错误和无权限状态。

## 当前首页切片

方案 1 在本目录实现，使用 Vercel 黑白留白风格；不增加独立应用、业务状态层或额外配置流程。首页的“创建关注”进入现有 `/monitors/new`，“我的关注”进入 `/topics`。主题创建、修改、来源准入与保存使用当前 OpenAPI 生成 API；示例只用于说明，不显示为真实采集结果。

| 组件                           | 领域与复用范围        | 路径                                       | 数据与状态                                                |
| ------------------------------ | --------------------- | ------------------------------------------ | --------------------------------------------------------- |
| HomeContent                    | 首页专属组合          | src/app/components/home-content.tsx        | 静态内容与说明浮层开关；无业务 API                        |
| SiteHeader                     | 首页专属导航          | src/app/components/site-header.tsx         | 品牌、官方菜单、现有路由链接与指南入口                    |
| HeroSection                    | 首页专属主视觉        | src/app/components/hero-section.tsx        | 选定文案、装饰品牌图、创建链接与示例入口                  |
| CapabilityOverview             | 首页专属指南/示例说明 | src/app/components/capability-overview.tsx | 静态说明；官方 Dialog 打开、关闭及键盘焦点                |
| BrandLockup / BrandMark        | 跨页面品牌            | src/components/brand/brand-lockup.tsx      | 复用 src/app/icon.png 母版；无 API 状态                   |
| Button / Dialog / DropdownMenu | 跨页面官方基础组件    | src/components/ui/                         | 保留官方 Radix 语义和交互；必要的首页尺寸变体使用命名尺度 |

装饰主视觉位于 `public/brand/hero-brand-soft.png`，是既定品牌的阴影展示资产，不作为第二套品牌母版。布局使用现有 Tailwind 尺度与标准断点。首页无加载、空、部分或权限状态；业务页面保留当前加载、空、错误重试及成功状态。

## Demo 访问规则

当前 Demo 直接进入 `/topics`，删除 `/login`、`/register`、独占 auth 组件和身份先行请求；页面不显示账户信息或退出入口。`TopicsWorkspace` 使用主题API，`TopicForm` 使用来源能力API，覆盖加载、空、错误重试与业务成功。来源授权/凭据和内容原生身份保留。

`request.ts` 写请求固定 `X-HotKey-CSRF: 1`；代理不转发 Cookie/Authorization 或 Set-Cookie，业务失败就地显示并支持重试，不跳登录。CSP nonce、动态交互入口和 `noindex` 保持。

访问规则见 [Design001 §9.2](../docs/design/001-热点舆情监控平台总体设计.md#92-当前-demo-的访问与数据分区)，验证边界见 [共享验收](../docs/acceptance/001-共享运行门槛验收.md)。未来 ToC 登录需求后置，不保留组件或配置骨架。

## API 与状态

- 公共协议遵循 PROJECT.md 与 AGENTS.md 的现行契约；运行 OpenAPI、类型化资源和 ErrorView 共同门禁已接入。旧 Design 046 全局异常与响应契约已删除，046 S03 历史证据保留于 Git 和共享验收；本文件仅细化 Web 消费与展示，不另定义返回模型。
- 资源、分页、受理 DTO 和 ErrorView 来自同提交运行时 OpenAPI；错误读取 details，请求 ID 支持响应头/body 回退。HTTP、网络、超时、取消和协议失败分开；204 与文件不解析为 JSON，失败任务查询与合法空结果保持正常读取语义。
- 传输层不全局弹提示、不按 message 分支、不自动重试写操作。字段错误就地显示，页面失败保留恢复入口，操作结果使用适当短时反馈；旧数据刷新失败要标明过期。
- Umi OpenAPI 将端点和类型直接生成到 `src/api/`。
- 所有生成请求统一使用 `src/request.ts`，页面不得手写端点或创建第二套 HTTP 客户端。
- ESLint 拒绝业务源码直接导入传输函数/HTTP 客户端或调用网络原语；页面可使用生成函数、传输错误类和请求选项类型。透明同源代理只做通用转发，生成代码只由生成器更新。
- 浏览器同源与 SSR 后端 origin 由 `src/request.ts` 统一解析，移除页面重复 baseURL 和 `publicationApiOptions`；业务请求选项只允许头、取消、响应格式和超时，生成的方法/URL/参数不能被覆盖。
- Agent 页专属 `SelectedSnapshotDownload` 位于 `src/app/agent/components/selected-snapshot-download.tsx`，使用生成的 `getSelectedPublicationSnapshot` 下载 JSON 快照，覆盖加载、错误和再次下载；不手写 API 地址。
- 测试统一在 `tests/`，按原业务路径组织 `app/`、`components/`，根配置测试归 `tests/config/`；`src/` 只放业务源码和生成客户端。Vitest 仅扫描 tests，生产类型检查及 Docker 构建排除测试；独立测试 TypeScript 配置继续检查所有测试，ESLint 拒绝业务目录中的测试或测试依赖。
- App Router 统一提供 loading、error、global-error 和 not-found 边界。
- `src/components/system/page-state.tsx` 中的 `PageState` 处理页面错误、空态、无权限和恢复操作。业务页通过 `navigation` 保留 `WorkspaceHeader`，读取失败时仍可切换页面；不在状态组件内部请求业务数据。

## 可访问性与运行

- 交互支持键盘焦点，装饰图形使用 `aria-hidden`，状态区域提供语义名称。
- 动效遵循 `prefers-reduced-motion`。
- 页面必须完成桌面和窄屏浏览器检查。
- 生产镜像使用 standalone、非 root、只读文件系统和 `/health` 健康检查。
- CSP nonce 由 `src/proxy.ts` 每请求生成；需要客户端交互的 HTML 入口必须按请求渲染。主题创建页在服务端入口等待 Next.js `connection()`，保持来源校验；生产脚本 nonce 必须与本次 CSP 一致，HTML 不使用共享缓存。生产镜像的 runtime 检查与浏览器冷进入均需通过。

## 当前业务页面重建

清理旧业务页的密集布局、无接口的事件脉络占位与报告/通知偏好表单。保留正式 Next.js 脚手架、首页、生成客户端、Axios 传输和 CSP；不复制原型。Swagger 的唯一源为 FastAPI 路由/Pydantic，临时导出的 OpenAPI 仅供生成校验，不成为手维护文件。页面只调用 `src/api/` 中的生成操作。

| 组件                                                                             | 领域与复用范围                   | 目标路径                                                                 | 数据来源与状态覆盖                                                                                                                       |
| -------------------------------------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| WorkspaceHeader                                                                  | 多个业务页的导航                 | src/components/navigation/workspace-header.tsx                           | 静态真实路由；桌面导航、移动官方菜单与当前页语义                                                                                         |
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

本片新增导航为 `src/components/navigation/workspace-header.tsx`；来源组合与设置分别为 `src/app/sources/components/sources-workspace.tsx`、`source-settings.tsx`，替代并删除旧 `source-capability-matrix.tsx`。`TopicAdvancedFields` 导出在既有 `src/components/monitors/topic-settings-fields.tsx`；报告查询/详情局部组合留在各自原文件中，不放到公共层。官方基础组件新增 `collapsible.tsx`、`empty.tsx`、`item.tsx`、`spinner.tsx`，只提供实际使用的交互原语。

## 日周月刊

`/editions`使用`src/app/editions/components/edition-list.tsx`，读取唯一生成客户端`rizhouyuekan.ts`，按日/周/月与刊期分页展示最新修订，接受有原因的补刊/新修订任务；加载、空、错误、409与unknown人工复核分别呈现。`/editions/[editionId]`使用专属edition-detail，按冻结条目与程序指标读正文，保留修订列表和历史标记，权限失效时整稿隐藏；不在页面触发模型。人工修订只允许已冻结引用，下载同一Markdown稿。旧`/reports`保留主题统计口径，通过导航区分。组件复用shadcn表单、按钮、空状态与原WorkspaceHeader，布局使用命名Tailwind尺度，无新共享层。

## 公开资讯与分发

`/discover`组合PublicItemCards、筛选和selected同步；`/items/[contentId]`组合ItemReader、引用、原译文/目录/许可状态；`/agent`说明真实五工具与Markdown；`/feeds`选择已核许可的摘要/全文/分类/刊期RSS；`/publication/manage`组合PublicationManager管理版本化来源许可、纠错和本地重建。PublicItemCards、PublicationFailure、PosterDownload跨页面复用归components/publication，其余归路由专属components；唯一数据来源为运行OpenAPI生成gongkaifabu/gongkaifenfa/quanwenfanyi。原/与品牌不改；正文/媒体默认安全原站链接，镜像独立任务未完成时不可标已缓存。覆盖加载、空、失败重试、部分译文/unknown、权限403与版本409、重建进度；operator令牌只用户会话内存，不内嵌源码或localStorage。

`/discover/stories/[eventId]`专属story-reader读取公开故事DTO及复用PublicItemCards，ALL成员撤回时整页隐藏，不用内部/events端点降级拼稿。`/editorial-sources`专属配置/运行组件读取bianjilaiyuan，按RSS、HTML、JSON、X、公众号和external区别显式字段、currentversion、reason/opid、运行unknown和人工动作；参与模式不自动扩大公开许可，令牌只在当前会话内存。

`/discover/topics`与`/discover/topics/[slug]`为行业主题目录和资料阅读，专属组件使用生成gongkaifabu的主题DTO、当前许可条目、相关主题与索引状态；不混入原`/topics`监控配置。资讯时间线按故事/事实/单件折叠，代表条目与进展的首次出现锚点分开，展开仍使用同一筛选和发布修订，覆盖空、分页、撤回和刷新冲突。

`/discover/starred`复用publication本机状态组件，500收藏/5000已读、ID导入导出、坏数据/存储失败与跨tab变更可见，不持久正文。`/about`、`/privacy`、`/terms`、`/changelog`是本地说明；`/contact`只读启用后的实际联系DTO；`/site/manage`专属配置组件以会话内运营令牌保存CAS/原因/图片，禁用后旧二维码不可读。所有业务数据仍经生成客户端，静态说明不显示伪统计。

`/reports/[reportId]/[key]`（reportId严格为kind）为公开刊期只读阅读页，kind仅daily/weekly/monthly，专属PublicEditionReader消费getPublicEdition及复用publication稿件组件。与原监控主题报告及/editions修订操作分离，公开稿只读最新完整修订且ALL引用当前许可有效；404撤回整稿、错误可重试、无生成或编辑控件。公开故事/刊期/专题Metadata按实际DTO.indexable决定noindex；故事和刊期要求所有固定叙事成员的当前索引许可。IndexNow根验证文件经固定Next rewrite及代理白名单，不开放任意文本文件代理。
