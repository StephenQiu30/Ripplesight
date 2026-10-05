# HotKey Web 设计规范

## 视觉

- 使用 Geist；Geist Mono 仅用于数据和技术标识。字体装配集中在 `src/layout/layout-fonts.ts`，根 HTML 和全局恢复页复用相同字体变量。
- 颜色、字体和圆角统一定义在 `src/app/globals.css`，业务组件只使用语义令牌。
- 页面通过留白、排版和表面明度建立层级，静态信息区不使用装饰性边框；信息流外侧可使用结构分隔线，区分固定导航、阅读正文与发现区域。
- 输入、选择、错误、键盘焦点和浮层保留必要轮廓。
- 布局只使用 Tailwind 命名尺度和 `sm`、`md`、`lg`、`xl`、`2xl`，禁止原始像素值和任意布局尺寸。

## 组件

- 富文本阅读统一使用 `src/components/editor/Viewer`（经目录入口导出），接收块 JSON 或显式 markdown/html/text，SSR 可读、空内容为空、无编辑工具栏，所有内容和 URL 白名单清洗。段落/标题/嵌套列表/任务列表/引用/代码/表格/分隔符/图片共用块合同，报告引用只绑定当前报告给定 URL，未知引用保留文字。通用 Viewer 用于私人报告、公开刊期和资讯正文；阅读页不提供本机笔记，不装载 Editor.js 编辑器及块工具。原本机阅读状态键只保存 mode/scroll，忽略旧 note/noteDocument，后续保存不携带笔记字段，不新增业务 API。

- shadcn/Radix 基础组件放在 `src/components/ui/`。
- 全部页面的交互控件只组合官方 shadcn/ui + Radix：选择使用 Select/SelectGroup，布尔选项使用 Checkbox/Switch，折叠内容使用 Collapsible，数据表使用 Table，表单使用 FieldGroup/Field/FieldLabel。业务源码不手写 button、input、select、textarea、details 或表格组件；ESLint 检查此边界。标题、段落、列表、结构、链接、原生表单和音视频统一经 `ui/content.tsx` 的 Heading/Text/Content/ContentList/TextLink/Form/AudioPlayer/VideoPlayer 组合；该层补齐官方注册表未提供的语义能力，不伪称额外组件来自官方注册表。原生 JSX 仅留在 UI 层，业务页面、复用组件和布局不直接写原生标签；ESLint 拒绝全部小写 JSX 标签。DocumentRoot/DocumentBody保留Next文档根，Form保留原生提交/校验，媒体保留原生控件；不改变回调、ref、URL或正文清洗合同。
- 信息面板和数据列表组合 Item/ItemContent/ItemTitle/ItemDescription/ItemGroup，持久提示使用 Alert，空状态使用 Empty，分隔线使用 Separator，导航使用 NavigationMenu。业务页面不再用原生容器绘制圆角面板、提示和分隔线；ESLint 对手写控件及这些视觉容器统一检查。
- 日期组件使用官方 Calendar（React Day Picker），公告单日选择和刊期只读日历均保持北京时间、真实数据及真实刊期链接。互斥范围、状态和刊期类型使用 ToggleGroup；业务逻辑保留已有筛选和分页重置。基础组件通过官方 shadcn CLI 引入，不建立替代基础组件的自定义包装层。
- 全站操作反馈使用官方 shadcn Sonner：失败和提交校验使用 `toast.error`，成功使用 `toast.success`，主动取消使用 `toast.info`。BasicLayout 唯一挂载 Toaster，统一右上角、可关闭、语义颜色和无障碍通知；业务组件直接调用 `sonner`，传输层不自动弹提示。不在表单、菜单或内容底部保留错误/成功消息块，不创建自定义 Toast 或通知包装层。字段可保留 `data-invalid`/`aria-invalid` 和纠错焦点；加载失败只保留原生 Empty/Alert 的恢复入口及稳定说明，具体请求错误由 Sonner 提示。持久任务失败事实、权限/覆盖状态和全局恢复页面仍使用原生 shadcn 组件；请求取消、失效响应和重新渲染不得重复通知。
- 组件使用原生 variant/size，className 只调整布局；避免额外卡片、阴影和装饰边框。表单窄屏单列、控件允许收缩、长选项在触发器中截断并在浮层中换行。Select 的“全部/清除覆盖”保留空值和原 FormData；Collapsible 关闭时保留内部已填状态。间距使用 flex/grid + gap，不使用 space-x/space-y。
- 跨页面复用组件按功能领域放在 `src/components/<feature>/`。
- 页面专属组件放在对应 `src/app/<route>/components/`；根页面使用 `src/app/components/`。
- 全站外壳统一在独立 `src/layout/`：BasicLayout 在根 App Router 装配 BasicSidebar；全站移除顶部 Header。外壳使用 `h-dvh`，唯一宽度源 LayoutContainer 定义 `max-w-7xl`；侧栏固定在正文滚动区之外，md 为图标栏 `w-20`，lg 为 `w-60`，xl 为 `w-64`。正文只有一个 main，沿用真实滚动节点、路由重置、阅读位置与跳到正文入口；首页正文没有外侧内边距，其他页面统一 `px-5 sm:px-8`、`py-8 sm:py-10`。站点 Footer 位于正文结束处，不占用固定底部视口；打印隐藏侧栏并恢复正常文档流。
- md 以下使用固定底部导航，提供首页、探索资讯、本机收藏、个人工作台与更多；正文预留 `pb-16`，不遮挡最后的操作。更多菜单提供专题、刊物、模型榜、说明和登录/账户入口，手机主题选择在同一菜单内。桌面侧栏的导航、定制关注按钮和真实账户/主题入口保持键盘可达；较矮视口允许导航区域滚动。
- `/login` 在 BasicLayout 内省略侧栏与底部导航；加载、错误恢复和正常表单使用同一外壳，保留正文滚动、Footer 与 Sonner。短请求只显示主按钮忙碌并禁重复，不追加 HTTP 取消按钮。
- 主题偏好仍由全局 ThemeProvider 管理，桌面切换入口位于侧栏账户旁；手机通过更多菜单的 RadioGroup 切换浅色、深色和跟随系统。沿用既有存储键、导入导出、系统变化与跨标签同步；存储失败由 Sonner 提示。
- 不创建 `features`、`common`、`patterns` 或 `shared` 目录。
- `page.tsx` 只处理页面入口、数据边界和组件组合。
- 组件至少被两个页面稳定复用后才能迁入 `src/components/<feature>/`。

每个切片在 Design 阶段记录组件名称、所属领域、复用范围、目标路径、数据来源及正常、空、加载、部分、错误和无权限状态。

## 公开信息首页与个人工作台

首页使用 X 式阅读布局：全局侧栏承担导航，ReadingLayout 只组合信息流与发现区。lg 以上主内容采用三等份网格，帖子流跨两份、右侧发现区占一份；在 `max-w-7xl` 和 xl 侧栏下约为导航 256、帖子流 672、发现区 336 CSS px（浏览器滚动条占用另计）。低于 lg 发现区后置，低于 md 使用底部导航。首页首屏直接阅读，不展示宣传 Hero 或重复页面导航。

信息流顶部使用 sticky timeline Tabs、单行横向滚动分类和 Separator；桌面搜索位于右侧，手机搜索位于信息流顶部，支持回车、空白拦截和输入法组合态。HomePosts 使用 Item/Avatar、Card 标题/摘要和真实 Badge：头像在左、来源与时间在上、标题及摘要对齐内容列；标题采用 post 字号、摘要最多三行。没有来源图标时使用图标库 RSS 回退，不造人像；提供站内阅读、来源原文、已有事件和本机收藏，不造互动计数。右侧使用 muted Card 呈现关注入口、专题、事件与刊物，长于视口时随唯一正文滚动区滚动，避免固定后无法阅读底部内容。

首页全部/精选、已有分类与真实游标分页沿用 SSR 和生成客户端；搜索进入既有资讯检索，不触发采集或模型。公开发布分区、许可、无摘要、未分析、历史导入、加载/空/部分错误和真实会话合同保持。个人工作台仍集中关注、报告与管理；资讯、专题、刊物、单篇及发布辅助页移除重复 PublicationNavigation，模型榜的评测来源/计算规则保留为领域子导航。

| 组件                                         | 领域与复用范围     | 目标路径                                            | 数据与状态                                                                         |
| -------------------------------------------- | ------------------ | --------------------------------------------------- | ---------------------------------------------------------------------------------- |
| BasicLayout / BasicSidebar                   | 全站外壳与导航     | src/layout/basic-layout.tsx；basic-sidebar.tsx      | 真实全局会话；路由最长匹配、桌面/图标栏/手机、账户与主题、键盘焦点；登录页省略导航 |
| ReadingLayout                                | 首页阅读布局       | src/layout/reading-layout.tsx                       | children/aside；lg 2:1、窄屏辅助区后置，不创建 main 或业务滚动节点                 |
| HomeContent / HomePosts                      | 首页专属           | src/app/components/home-content.tsx；home-posts.tsx | 原公开 DTO；真实筛选/游标/来源/摘要/空态/部分错误；复用 SaveItem 本机收藏          |
| SaveItem                                     | 收藏与阅读跨页复用 | src/components/publication/local-reading.tsx        | 沿用原收藏 ID 存储键和跨标签同步；compact 图标/pressed 状态；失败 Sonner           |
| ThemeProvider / ThemeToggle / ThemeMenuItems | 全站主题           | src/layout/theme-toggle.tsx                         | 原本机偏好；桌面入口、手机菜单、系统/导入/跨标签同步                               |

`/discover`（含专题、事件与本机收藏）、`/items`、`/leaderboard`、`/reports/daily|weekly|monthly`及合法刊期阅读公开；`/reports`个人列表、UUID详情与archive、`/editions`编选、个人关注/内容/任务、公告监控及全部管理页面仍经会话守卫。公开publication、刊物目录、正文媒体、来源图标与分享图只使用明确的`HOTKEY_PUBLIC_PUBLICATION_OWNER_ID`，不回退访问者或遍历全部账户；未配置返回503 `publication_not_configured`。RSS、Markdown、MCP及精选同步仍保持原会话边界。

公开首页与说明保留SEO；阅读元数据仅在站点允许索引且当前材料许可满足时索引。login和工作台始终noindex，robots对公开阅读路径提供具体allow而私有路径仍disallow，sitemap只列公开入口。会话验证网络故障不清Cookie；公开阅读继续可用，私有页和登录页保留503恢复状态。CSP按请求nonce、private/no-store与SSR逐请求Cookie保持。

登录专属组件归 `src/app/login/components/`，跨页会话/账户与守卫归 `src/components/auth/`；全部类型和请求来自Umi生成的identity API。账号密码、GitHub OAuth App、邮箱验证码共用真实数据库会话，覆盖加载/不可用/字段错误/限流/取消/成功/网络重试。业务深链接和prefetch均先验证会话，网络失败不能当成已退出；SSR按请求转发限定Cookie，代理只转发HotKey身份Cookie/Set-Cookie。保持官方shadcn/Radix表单、按钮、菜单、无装饰边框、语义颜色及命名尺度。

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
| welcomeMetadata / robots / sitemap    | 公开SEO页面          | src/components/site/welcome-metadata.ts；src/app/robots.ts、sitemap.ts | 实际站点origin、canonical/OG；公开首页、说明与阅读入口入站点地图，工作区始终noindex                                                          |

公开站点origin使用`NEXT_PUBLIC_SITE_ORIGIN`或服务端`HOTKEY_WEB_ORIGIN`，本机固定Web8666/API8667，默认origin为`http://127.0.0.1:8666`；不调用私有业务API生成欢迎页元数据。登录页在上游会话验证故障时显示统一PageState和原安全目标重载操作，保持会话故障与未登录状态的区分。修改凭据成功200后撤销所有旧会话并建立当前新会话；已登录无密码账户访问登录页也进入设置步骤。验证码标识仅保存在组件内存中。

## API 与状态

- 公共协议遵循 PROJECT.md 与 AGENTS.md 的现行契约；运行 OpenAPI、类型化资源和 ErrorView 共同门禁已接入。本文件仅细化 Web 消费与展示，不另定义返回模型。
- 资源、分页、受理 DTO 和 ErrorView 来自同提交运行时 OpenAPI；错误读取 details，请求 ID 支持响应头/body 回退。HTTP、网络、超时、取消和协议失败分开；204 与文件不解析为 JSON，失败任务查询与合法空结果保持正常读取语义。
- 传输层不全局弹提示、不按 message 分支、不自动重试写操作。提交与字段校验错误由业务组件使用 Sonner，字段保留 `aria-invalid`/`data-invalid` 和纠错焦点；读取失败保留 Empty/Alert 的恢复入口，持久任务失败和权限/覆盖缺口仍作为内容。旧数据刷新失败要标明过期。
- Umi OpenAPI 将端点和类型直接生成到 `src/api/`。
- 所有生成请求统一使用 `src/request.ts`，页面不得手写端点或创建第二套 HTTP 客户端。
- ESLint 拒绝业务源码直接导入传输函数/HTTP 客户端或调用网络原语；页面可使用生成函数、传输错误类和请求选项类型。透明同源代理只做通用转发，生成代码只由生成器更新。
- 浏览器同源与 SSR 后端 origin 由 `src/request.ts` 统一解析，业务请求选项只允许头、取消、响应格式和超时，生成的方法/URL/参数不能被覆盖。
- Agent 页专属 `SelectedSnapshotDownload` 位于 `src/app/agent/components/selected-snapshot-download.tsx`，使用生成的 `getSelectedPublicationSnapshot` 下载 JSON 快照，覆盖加载、错误和再次下载；不手写 API 地址。
- 测试统一在 `tests/`，按原业务路径组织 `app/`、`components/`，根配置测试归 `tests/config/`；`src/` 只放业务源码和生成客户端。Vitest 仅扫描 tests，生产类型检查及 Docker 构建排除测试；独立测试 TypeScript 配置继续检查所有测试，ESLint 拒绝业务目录中的测试或测试依赖。
- App Router 统一提供 loading、error、global-error 和 not-found 边界。
- 全局 loading 在既有外壳内提供可访问的加载状态，页面有专属布局时使用对应路由骨架。登录页的路由等待、登录方式请求和失败重试复用同一 LoginExperience / LoginFormLayout，使用原生 Skeleton 并预留表单高度；标题、品牌和条款不随方式加载而跳位，窄屏与减少动效模式沿用同一布局。业务提交继续保留当前内容和按钮忙碌状态。
- `src/components/system/page-state.tsx` 中的 `PageState` 只处理正文错误、空态、无权限和恢复操作。加载、错误和404沿用根 BasicLayout，读取失败时主导航及页脚继续存在；global-error 替代根布局时独立装配 BasicLayout。不在状态组件内部请求业务数据。

## 可访问性与运行

- 配置只在仓库根 `.env` / `.env.prod` 维护，模板仅根 `.env.example`。Next 和 OpenAPI 配置按 Web 字段白名单读取根 `.env`，保留显式进程注入，后端认证/来源/模型秘密不加载到 Web 进程；容器继续按需注入，不复制环境文件。

- 本机 loopback 页面别名在读取会话前按 `HOTKEY_WEB_ORIGIN` 规范化，仅同协议同端口的 GET/HEAD 跳转并保留原路径和查询。API Origin/CSRF 校验保持严格；缺少会话的孤立 CSRF Cookie 在页面入口清除，有效账户的凭据验证码仍使用绑定 CSRF。OAuth 回调、Cookie 和本机页面使用同一主机。

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
| BasicHeader                                                                      | 全站主导航                       | src/layout/basic-header.tsx                                              | 静态真实会话与公开/工作区路由；统一桌面/手机分组导航、路由匹配与当前页语义；指南 Dialog 由 BasicFooter 打开                              |
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
| ReportList / ReportResults / ReportDetail / ReportDetailContent                  | 已有报告读取专属，非核心二级入口 | src/app/reports/components/；src/app/reports/[reportId]/components/      | list/getReport；只读分页、空、错误和实际状态，无新生成/投递配置                                                                          |
| Collapsible / Empty / Item / Spinner                                             | 多页官方基础组件                 | src/components/ui/                                                       | 官方Radix折叠、空态、列表和加载组件；不承载业务状态                                                                                      |

配置第一层只呈现名称、关键词与来源，进阶规则/频率及报告设置按需展开。报告设置提供日报时间、周报与个人邮件发送，未修改的既有偏好及其他目标按原值传回，避免覆盖数据。来源主入口是配置，覆盖/技术字段二级展示。所有页面沿用语义颜色、命名尺度、官方表单/浮层/菜单；不新增数据状态框架。业务入口继续动态渲染、`noindex`，取消请求不显示为业务失败。

主导航归 `src/layout/basic-header.tsx`；任务路由内的 `job-presenters.ts` 复用时间/状态/能力展示，报告详情路由内的 `report-links.ts` 复用安全 HTTP URL 规则；两者均无请求与状态所有权。

## 日周月刊

`/editions`使用`src/app/editions/components/edition-list.tsx`，读取唯一生成客户端`rizhouyuekan.ts`，按日/周/月与刊期分页展示最新修订，接受有原因的补刊/新修订任务；加载、空、错误、409与unknown人工复核分别呈现。`/editions/[editionId]`使用专属edition-detail，按冻结条目与程序指标读正文，保留修订列表和历史标记，权限失效时整稿隐藏；不在页面触发模型。人工修订只允许已冻结引用，下载同一Markdown稿。旧`/reports`保留主题统计口径，通过导航区分。组件复用shadcn表单、按钮、空状态与根 BasicLayout，布局使用命名Tailwind尺度，无新共享层。

## 公开资讯与分发

`/discover`组合PublicItemCards、筛选和selected同步；`/items/[contentId]`组合ItemReader、引用、原译文/目录/许可状态；`/agent`说明真实五工具与Markdown；`/feeds`选择已核许可的摘要/全文/分类/刊期RSS；`/publication/manage`组合PublicationManager管理版本化来源许可、纠错和本地重建。PublicItemCards与PublicationFailure在`src/components/publication/reading-parts.tsx`，PosterDownload在`src/components/publication/poster-download.tsx`，跨页面复用；其余归路由专属components。唯一数据来源为运行OpenAPI生成gongkaifabu/gongkaifenfa/quanwenfanyi。正文/媒体默认安全原站链接，镜像独立任务未完成时不可标已缓存。覆盖加载、空、失败重试、部分译文/unknown、权限403与版本409、重建进度；operator令牌只用户会话内存，不内嵌源码或localStorage。

`/discover/stories/[eventId]`专属story-reader读取公开故事DTO及复用PublicItemCards，ALL成员撤回时整页隐藏，不用内部/events端点降级拼稿。`/editorial-sources`专属配置/运行组件读取bianjilaiyuan，按RSS、HTML、JSON、X、公众号和external区别显式字段、currentversion、reason/opid、运行unknown和人工动作；参与模式不自动扩大公开许可，令牌只在当前会话内存。

`/discover/topics`与`/discover/topics/[slug]`为行业主题目录和资料阅读，专属组件使用生成gongkaifabu的主题DTO、当前许可条目、相关主题与索引状态；不混入原`/topics`监控配置。资讯时间线按故事/事实/单件折叠，代表条目与进展的首次出现锚点分开，展开仍使用同一筛选和发布修订，覆盖空、分页、撤回和刷新冲突。

`/discover/starred`复用publication本机状态组件，500收藏/5000已读、ID导入导出、坏数据/存储失败与跨tab变更可见，不持久正文。`/about`、`/privacy`、`/terms`、`/changelog`是本地说明；`/contact`只读启用后的实际联系DTO；`/site/manage`专属配置组件以会话内运营令牌保存CAS/原因/图片，禁用后旧二维码不可读。所有业务数据仍经生成客户端，静态说明不显示伪统计。

`/reports/[reportId]/[key]`（reportId严格为kind）为公开刊期只读阅读页，kind仅daily/weekly/monthly；`/reports/{kind}/archive`为对应公开历史目录，守卫只放行这三个精确路径及合法刊期，不放行UUID报告或archive下任意路径。专属PublicEditionReader消费getPublicEdition，历史目录消费listPublicEditionCatalogue并复用publication稿件组件。与原监控主题报告及/editions修订操作分离，公开稿只读最新完整修订且ALL引用当前许可有效；404撤回整稿、错误可重试、无生成或编辑控件。公开故事/刊期/专题Metadata按实际DTO.indexable决定noindex；故事和刊期要求所有固定叙事成员的当前索引许可。IndexNow根验证文件经固定Next rewrite及代理白名单，不开放任意文本文件代理。

账户设置在密码表单下展示“登录方式”：当前邮箱及绑定/更换按钮、GitHub连接状态及连接按钮。邮箱验证使用原生Dialog、FieldGroup和Input，验证码限时且发送有冷却；GitHub复用OAuth App回调，成功/失败用Sonner反馈。加载时按钮禁用，离页/关闭邮箱Dialog中止短请求并忽略失效响应，不追加HTTP取消按钮。页面随轮换后的会话更新，旧邮箱凭据表单不继续使用旧挑战。专属组件为 `src/app/account/components/identity-connections.tsx`，请求仅用同提交生成的getLoginOptions、sendEmailLinkCode、linkIdentityEmail、startGithubLink。

## 账户设置

`AccountSettings`（src/app/account/components/account-settings.tsx）复现选定方案3：左侧浅灰资料摘要展示头像、用户名、绑定邮箱和验证状态，右侧使用官方line Tabs切换基本资料与登录安全；lg以上1:2双列，窄屏顺序堆叠。用户名独立保存不要求填密码，头像上传独立于密码操作；两者通过生成的updateIdentityProfile/uploadIdentityAvatar返回真实会话后刷新导航。文件类型/2 MiB在客户端预检，服务端重新解码校验并规范化；上传中禁重复，失败保留旧头像，成功统一Sonner。未上传使用用户图标，读取失败允许在资料栏重试；无伪造人像或默认账户。`UserAvatar`跨页复用在components/auth，经getIdentityAvatar读Blob，只显示当前哈希，离页/换图中止读取并释放object URL。密码表单复用CredentialsForm嵌入模式，保留当前密码/绑定邮箱验证码、首次设置和安全回跳合同。分类切换保留输入草稿，短提交期间限制其他账户修改。并行已有IdentityConnections继续在右侧登录安全下展示真实绑定能力。

ReportEmailSubscription为账户页专属组件（app/account/components/report-email-subscription.tsx），使用生成的个人邮件订阅GET/PUT，展示本人已验证邮箱、订阅及平台SMTP就绪；缺绑定引导登录安全，未配置发信保留偏好并说明暂不能发送。TopicReportFields创建/编辑复用，新增个人订阅读取与主题发送开关，保留其他目标偏好。正常、未绑定、未订阅、未就绪、加载失败重试、冲突与取消依真实响应和Sonner/Empty呈现。新主题默认每小时、08:00日报及周一08:00周报，既有自定义值保持。

### 探索与公共阅读列表

首页、探索、专题和刊物的资讯列表统一使用 `PublicItemFeed`，保留真实来源、发布时间或发现时间、来源摘要、许可内的站内阅读与本机收藏。摘要最多显示三行，完整内容由阅读页承接。探索页优先展示搜索与范围、时间、分类，其他条件进入可展开的高级筛选；收起时保留表单值，有已用高级条件时默认展开。
