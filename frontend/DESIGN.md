# Ripplesight Web 设计规范

本文规定 Web 端的视觉、组件、布局和状态处理。数据请求与目录约定见 [README](README.md) 和 [AGENTS](../AGENTS.md)。

2026-10 重新设计的高保真稿见 [Claude 画布](https://claude.ai/artifact/ERFs389e9sFhhp11U5cviY) 与 [Figma](https://www.figma.com/design/DfWRfnw965ocH6lmlSYGgs)，任务拆分见[前端重新设计计划](../docs/product/plan/02-PLAN-前端重新设计.md)。设计稿是视觉与结构的依据，其中的示例数据不进产品代码。本人最新要求清理旧实现并按稿重建；与本文旧版视觉规则冲突时，以本轮 Figma 原稿为准，数据真实性、权限和可访问性要求继续适用。

本轮用户要求按上述 Figma 还原，并严格遵守 shadcn 与 Vercel React Best Practices。验收分为组件规范和视觉比对：前者核查组件组合、语义令牌、表单反馈、键盘访问与 React 实现；后者以 Figma 桌面端导出的 10 页原稿（1440px 桌面与 390px 移动）为依据，在同尺寸浏览器下比对布局、排版和资产。原稿已成功读取；MCP 额度限制不再阻止视觉实现。接口未提供的历史曲线、情感比例、趋势不能用设计样本冒充；个人备注按本机输入保存，保留真实空态并单独记录能力缺口。

## 1. 视觉

- 风格：黑白、留白、克制。层级靠排版、间距和表面明度区分，不靠装饰边框、阴影或卡片堆叠。
- 品牌：项目与 GitHub 仓库使用 `Ripplesight`；界面主品牌按稿显示“知微见澜”，副标题使用 `Ripplesight · AI 热点监测`，标识只用 `components/brand` 的 `BrandLockup` / `BrandMark`（`src/app/icon.png`）。
- 字体：Geist；Geist Mono 只用于数据和技术标识（计数、热度、时间、百分比、错误码），数字用等宽数字。字体集中在 `src/layout/layout-fonts.ts` 中装配。
- 颜色、字体、圆角统一定义在 `src/app/globals.css` 的语义令牌中，业务组件只使用这些令牌。
- 输入框、选择器、错误提示、键盘焦点和浮层保留必要的轮廓；信息流允许使用结构分隔线。
- 概览指标采用上方标签、下方等宽数字；桌面四列、移动两列，不可用显示“—”，上下用分隔线收边，不做成卡片。需要强调的提醒或侧栏分组用 `muted` 表面区分，不加阴影。
- `destructive` 只表示错误、负面情感和负面突增，不用作装饰或品牌色。情感三分类固定为正面 `foreground`、中性 `muted-foreground` 一档的浅灰、负面 `destructive`；图形旁必须同时给出文字或数值，不能只靠颜色区分。
- 尺寸只用 Tailwind 的命名尺度，断点只用 `sm`、`md`、`lg`、`xl`、`2xl`；不写像素值，也不用任意值尺寸。间距用 flex/grid 配合 gap，不用 `space-x` / `space-y`。
- 动效使用 GSAP 官方 React `useGSAP`，通过组件 ref 限定目标并在卸载时清理。侧栏折叠／展开以 220ms 过渡实际布局，拖动实时跟手；移动监控主题列表用 180ms 高度过渡，桌面始终显示；页面切换用 180ms、4px 的轻微入场，不等待退场、不重挂表单。重复操作从当前进度接续，不排队；`prefers-reduced-motion` 下立即完成，运行中切换该偏好也停止动效。

## 2. 组件

- 基础组件用官方 shadcn CLI 引入到 `src/components/ui/`，不另写包装层来替代它们。
- 交互控件只用 shadcn/Radix 组件：Button、Select、Checkbox、Switch、ToggleGroup、Collapsible、Table、Calendar、Tooltip、表单（FieldGroup / Field / FieldLabel）。站点外壳用 Sidebar 系列组件。
- 缺少的组件先用 `pnpm exec shadcn add <组件>` 引入；CLI 要覆盖 `components/ui` 中已有文件时一律拒绝，保留项目定制的版本。不得用原生 HTML 标签自行拼组件。
- 标题、段落、列表、链接、原生表单、音视频，统一使用 `ui/content.tsx` 中的 Heading / Text / ContentList / TextLink / Form / AudioPlayer / VideoPlayer。
- 信息列表使用 Item 系列组件；持久提示用 Alert，空状态用 Empty，分隔用 Separator，导航用 NavigationMenu。
- 业务代码中不出现小写的原生 JSX 标签，这类标签只能写在 `components/ui` 中（由 ESLint 检查）。
- 组件只用自带的 variant / size；`className` 只用来调整布局。
- `pnpm lint` 的 `design-system/conventions` 检查业务调用处的间距、颜色、动态类名、可见容器内的选择器/菜单/页签分组与按钮图标。UI 基础组件保留自身样式；跨文件组合、字体与布局是否符合原稿仍需人工和浏览器审查，lint 通过不等于全量设计验收。
- 富文本阅读统一用 `components/editor/Viewer`：支持块 JSON 和 markdown / html / text，服务端渲染，对内容和链接做白名单清洗，不执行原始 HTML，不带编辑工具。

## 3. 组件放在哪里

| 类型                      | 位置                                                             |
| ------------------------- | ---------------------------------------------------------------- |
| 只有一个页面用            | `src/app/<路由>/components/`（首页的放在 `src/app/components/`） |
| 至少两个页面稳定复用      | `src/components/<功能>/`                                         |
| 全站外壳                  | `src/layout/`                                                    |
| shadcn 基础组件与语义组件 | `src/components/ui/`                                             |

`page.tsx` 只负责页面入口、数据边界和组件组合。

## 4. 布局

- 全站外壳是 `BasicLayout`：固定侧栏与移动导航，`PageContainer` 提供唯一正文滚动区。公开阅读页删除旧版固定面包屑条和全局页脚；面包屑仅在详情页内容中展示。`main` 是整体内容地标，`#page-content` 是可聚焦的滚动节点。
- 正文由 `LayoutContainer` 控制，桌面外侧留白 48px、移动 16px。md 及以上使用官方 shadcn `Sidebar` 与 `Resizable`：默认宽度 240px（`site-sidebar` 令牌），展开时可在 224–320px 拖动调整，折叠为 48px 图标栏；导航占满侧栏可用宽度、行高 40px。标题旁提供折叠按钮，拖动边界支持方向键、Home/End 与双击恢复默认宽度；展开宽度和折叠状态保存在本机，刷新与切换路由后恢复。编辑控件中的 Ctrl/Cmd+B 不被侧栏拦截。2026-10-08 本人最新侧栏优化指令覆盖原稿固定宽度规则。
- 侧栏按稿分“阅读”和“工作台”：今日热点、探索、事件、榜单、日报，以及监控主题、告警、收藏。个人入口公开可发现，权限由目标路由处理；未登录时不伪装登录状态。管理、报告等既有入口收进“更多”，不移除可用能力。服务就绪状态仅使用 `getReadiness` 的真实响应。
- md 以下显示 56px 顶部品牌／搜索／告警导航及 64px 底栏，正文位于两者之间。类别筛选横向滚动；列表标题缩为 16px，隐藏桌面序号与事件长摘要。
- 首页、探索、事件、收藏与榜单使用 `reading-columns`：1440px 原稿对应主栏 666px、间隔 20px、辅栏 357px；窄屏转单列，辅栏位于正文后。首页删除旧版额外标题、内层容器留白与重复位置栏。
- 日报专用 edition-columns：主栏约696px、间隔48px、余下辅栏；报头元信息紧凑同排，正文为要点、社媒表、事件双栏和舆情。
- 页面标题 32/40px（移动 26/34px），章节标题 20px，辅栏标题 14px，正文 14/24px，元信息 12px；特殊登录标题通过 Heading 的 appearance 变体定义，避免响应式字号覆盖。
- 页内类别、立场、维度等单选筛选用 ToggleGroup，状态写进 URL 查询参数，刷新和分享后保持；窄屏时横向滚动，不换成下拉。
- `/login` 使用 64px 品牌顶栏、1040px 双栏内容区（左侧 556px、间隔 64px、表单 420px）与底部版权区。使用原有涟漪品牌资产；移动隐藏品牌插图，表单单列。账号、邮箱和 GitHub 流程保持真实服务配置。
- 打印时隐藏侧栏，恢复正常文档流。

### 监控主题工作区

- 主视图按稿连续展示主题标题、关键词、小时命中、采集平台、规则和最近告警，删除旧版默认四页签。结果和设置作为次级展开区；编辑、手动运行和错误恢复仍可访问。
- 桌面主题列表使用固定窄列，详情占剩余宽度；移动端主题列表可收起，深链接主题保持可访问。
- `active` 显示为“定时已启用”，不代表任务正在执行。只展示接口返回的帖子与时间，不把最近列表长度当总量，不提供没有数据支持的相关度或定时历史。

## 5. 状态与反馈

- 每个页面都要处理五种状态：正常、空、加载、错误、无权限。路由级统一提供 loading、error、global-error、not-found 边界；正文状态使用 `components/system/page-state.tsx` 中的 `PageState`。
- 操作反馈只用 Sonner：失败用 `toast.error`，成功用 `toast.success`，主动取消用 `toast.info`。Toaster 只在 BasicLayout 挂载一次。不要在表单底部放消息块，也不要自定义 Toast。
- 字段错误保留 `aria-invalid` 和纠错焦点。加载失败时显示 Empty 或 Alert，并提供重试入口。旧数据刷新失败时要标明“已过期”。
- 短请求只让主按钮显示忙碌并禁止重复点击，不额外放“取消”按钮。
- 网络故障不能当作“已退出登录”；公开阅读在会话服务故障时仍然可用。

## 6. 访问与安全

- 公开页面（首页、`/discover`、`/items`、`/events`、`/leaderboard`、公开日报/周报/月报）不需要登录；个人页面和管理页面需要会话，并设置 `noindex`。
- 每个请求生成独立的 CSP nonce（`src/proxy.ts`）；需要交互的 HTML 按请求渲染，不使用共享缓存。
- 生产环境 CSP 的 `style-src` 只放行 nonce 与哈希，服务端渲染出的 `style` 属性会被丢弃：组件不得依赖 `style` 设置布局或 CSS 变量，静态值写成类名（如 `site-sidebar-width`），动态值在客户端经 CSSOM 设置；图表等依赖内联样式的第三方组件只在客户端渲染。开发环境放行 `unsafe-inline`，这类问题只会在生产构建中暴露，由 `tests/layout/csp-inline-style.test.tsx` 把关。
- 交互元素可以用键盘访问；装饰图形加 `aria-hidden`；状态区域有语义名称。
- 每次改动 UI，都要在桌面和 390px 宽的窄屏下分别用浏览器检查。
