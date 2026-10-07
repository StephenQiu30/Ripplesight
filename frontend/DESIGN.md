# Ripplesight Web 设计规范

本文规定 Web 端的视觉、组件、布局和状态处理。数据请求与目录约定见 [README](README.md) 和 [AGENTS](../AGENTS.md)。

2026-10 重新设计的高保真稿见 [Claude 画布](https://claude.ai/artifact/ERFs389e9sFhhp11U5cviY) 与 [Figma](https://www.figma.com/design/DfWRfnw965ocH6lmlSYGgs)，任务拆分见[前端重新设计计划](../workspace/content/product/plan/02-PLAN-前端重新设计.md)。设计稿只定视觉与结构，其中的示例数据不进代码；与本文冲突时以本文为准。

## 1. 视觉

- 风格：黑白、留白、克制。层级靠排版、间距和表面明度区分，不靠装饰边框、阴影或卡片堆叠。
- 品牌：项目、GitHub 仓库和界面上的产品名统一使用 `Ripplesight`，标识只用 `components/brand` 的 `BrandLockup` / `BrandMark`（`src/app/icon.png`）。
- 字体：Geist；Geist Mono 只用于数据和技术标识（计数、热度、时间、百分比、错误码），数字用等宽数字。字体集中在 `src/layout/layout-fonts.ts` 中装配。
- 颜色、字体、圆角统一定义在 `src/app/globals.css` 的语义令牌中，业务组件只使用这些令牌。
- 输入框、选择器、错误提示、键盘焦点和浮层保留必要的轮廓；信息流允许使用结构分隔线。
- 概览指标排成一行“标签 + 等宽数字”，上下用分隔线收边，不做成卡片。需要强调的提醒或侧栏分组用 `muted` 表面区分，不加阴影。
- `destructive` 只表示错误、负面情感和负面突增，不用作装饰或品牌色。情感三分类固定为正面 `foreground`、中性 `muted-foreground` 一档的浅灰、负面 `destructive`；图形旁必须同时给出文字或数值，不能只靠颜色区分。
- 尺寸只用 Tailwind 的命名尺度，断点只用 `sm`、`md`、`lg`、`xl`、`2xl`；不写像素值，也不用任意值尺寸。间距用 flex/grid 配合 gap，不用 `space-x` / `space-y`。
- 动效遵循 `prefers-reduced-motion`。

## 2. 组件

- 基础组件用官方 shadcn CLI 引入到 `src/components/ui/`，不另写包装层来替代它们。
- 交互控件只用 shadcn/Radix 组件：Button、Select、Checkbox、Switch、ToggleGroup、Collapsible、Table、Calendar、Tooltip、表单（FieldGroup / Field / FieldLabel）。站点外壳用 Sidebar 系列组件。
- 缺少的组件先用 `pnpm exec shadcn add <组件>` 引入；CLI 要覆盖 `components/ui` 中已有文件时一律拒绝，保留项目定制的版本。不得用原生 HTML 标签自行拼组件。
- 标题、段落、列表、链接、原生表单、音视频，统一使用 `ui/content.tsx` 中的 Heading / Text / ContentList / TextLink / Form / AudioPlayer / VideoPlayer。
- 信息列表使用 Item 系列组件；持久提示用 Alert，空状态用 Empty，分隔用 Separator，导航用 NavigationMenu。
- 业务代码中不出现小写的原生 JSX 标签，这类标签只能写在 `components/ui` 中（由 ESLint 检查）。
- 组件只用自带的 variant / size；`className` 只用来调整布局。
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

- 全站外壳是 `BasicLayout`：固定侧栏与移动导航，内部统一挂载 `PageContainer`。后者提供固定位置栏、占满剩余高度的唯一正文滚动区，以及跟在正文后的页脚。`main` 是整体内容地标，`#page-content` 是键盘与阅读定位的滚动节点；页面不重复写导航、`main`、全屏高度或外侧边距。
- `PageContainer` 使用 header / children / footer 插槽；正文自动约束宽度、最小尺寸及响应式留白。位置栏和正文共用 `LayoutContainer` 对齐，正文变化不推动位置栏；加载、空、错误与无权限仍由页面原有 `PageState` 表达。打印恢复自然文档流。
- 正文宽度由 `LayoutContainer`（`max-w-7xl`）统一控制。md 及以上的站点侧栏用 shadcn `Sidebar`（`collapsible="icon"`）：展开 16rem，收起为 3rem 图标栏，收起时用 Tooltip 显示入口名；用侧栏顶部按钮或 Ctrl/⌘ + B 切换，状态记在 `sidebar_state` cookie，根布局读出后首屏不闪动。
- 侧栏分“阅读”和“工作台”两组：阅读组公开可见；工作台组只在有会话时显示；接口能给出待处理告警数时才用 Badge 标在告警入口上。侧栏底部放服务状态（取自 `getReadiness`，取不到时整块不显示，不显示假状态）和账号菜单。
- md 以下改用固定底部导航（首页、探索、收藏、工作台、更多），正文底部预留 `pb-16`。
- 首页使用 `ReadingLayout`：lg 及以上为“信息流 2 : 发现区 1”，窄屏时发现区排到后面。首屏直接是内容，不放宣传 Hero。详情页沿用同样的 2 : 1 分栏：左侧正文、时间线和来源，右侧舆情与关联信息。
- 页内类别、立场、维度等单选筛选用 ToggleGroup，状态写进 URL 查询参数，刷新和分享后保持；窄屏时横向滚动，不换成下拉。
- `/login` 不显示侧栏和底部导航，其他部分仍沿用 BasicLayout。
- 打印时隐藏侧栏，恢复正常文档流。

## 5. 状态与反馈

- 每个页面都要处理五种状态：正常、空、加载、错误、无权限。路由级统一提供 loading、error、global-error、not-found 边界；正文状态使用 `components/system/page-state.tsx` 中的 `PageState`。
- 操作反馈只用 Sonner：失败用 `toast.error`，成功用 `toast.success`，主动取消用 `toast.info`。Toaster 只在 BasicLayout 挂载一次。不要在表单底部放消息块，也不要自定义 Toast。
- 字段错误保留 `aria-invalid` 和纠错焦点。加载失败时显示 Empty 或 Alert，并提供重试入口。旧数据刷新失败时要标明“已过期”。
- 短请求只让主按钮显示忙碌并禁止重复点击，不额外放“取消”按钮。
- 网络故障不能当作“已退出登录”；公开阅读在会话服务故障时仍然可用。

## 6. 访问与安全

- 公开页面（首页、`/discover`、`/items`、`/events`、`/leaderboard`、公开日报/周报/月报）不需要登录；个人页面和管理页面需要会话，并设置 `noindex`。
- 每个请求生成独立的 CSP nonce（`src/proxy.ts`）；需要交互的 HTML 按请求渲染，不使用共享缓存。
- 生产环境 CSP 的 `style-src` 只放行 nonce 与哈希，服务端渲染出的 `style` 属性会被丢弃：组件不得依赖 `style` 设置布局或 CSS 变量，静态值写成类名（如 `[--sidebar-width:16rem]`），动态值在客户端经 CSSOM 设置；图表等依赖内联样式的第三方组件只在客户端渲染。开发环境放行 `unsafe-inline`，这类问题只会在生产构建中暴露，由 `tests/layout/csp-inline-style.test.tsx` 把关。
- 交互元素可以用键盘访问；装饰图形加 `aria-hidden`；状态区域有语义名称。
- 每次改动 UI，都要在桌面和 390px 宽的窄屏下分别用浏览器检查。
