# HotKey Web 设计规范

本文规定 Web 端的视觉、组件、布局和状态处理。数据请求与目录约定见 [README](README.md) 和 [AGENTS](../AGENTS.md)。

## 1. 视觉

- 风格：黑白、留白、克制。层级靠排版、间距和表面明度区分，不靠装饰边框、阴影或卡片堆叠。
- 字体：Geist；Geist Mono 只用于数据和技术标识。字体集中在 `src/layout/layout-fonts.ts` 中装配。
- 颜色、字体、圆角统一定义在 `src/app/globals.css` 的语义令牌中，业务组件只使用这些令牌。
- 输入框、选择器、错误提示、键盘焦点和浮层保留必要的轮廓；信息流允许使用结构分隔线。
- 尺寸只用 Tailwind 的命名尺度，断点只用 `sm`、`md`、`lg`、`xl`、`2xl`；不写像素值，也不用任意值尺寸。间距用 flex/grid 配合 gap，不用 `space-x` / `space-y`。
- 动效遵循 `prefers-reduced-motion`。

## 2. 组件

- 基础组件用官方 shadcn CLI 引入到 `src/components/ui/`，不另写包装层来替代它们。
- 交互控件只用 shadcn/Radix 组件：Button、Select、Checkbox、Switch、ToggleGroup、Collapsible、Table、Calendar、表单（FieldGroup / Field / FieldLabel）。
- 标题、段落、列表、链接、原生表单、音视频，统一使用 `ui/content.tsx` 中的 Heading / Text / ContentList / TextLink / Form / AudioPlayer / VideoPlayer。
- 信息列表使用 Item 系列组件；持久提示用 Alert，空状态用 Empty，分隔用 Separator，导航用 NavigationMenu。
- 业务代码中不出现小写的原生 JSX 标签，这类标签只能写在 `components/ui` 中（由 ESLint 检查）。
- 组件只用自带的 variant / size；`className` 只用来调整布局。
- 富文本阅读统一用 `components/editor/Viewer`：支持块 JSON 和 markdown / html / text，服务端渲染，对内容和链接做白名单清洗，不执行原始 HTML，不带编辑工具。

## 3. 组件放在哪里

| 类型 | 位置 |
|---|---|
| 只有一个页面用 | `src/app/<路由>/components/`（首页的放在 `src/app/components/`） |
| 至少两个页面稳定复用 | `src/components/<功能>/` |
| 全站外壳 | `src/layout/` |
| shadcn 基础组件与语义组件 | `src/components/ui/` |

`page.tsx` 只负责页面入口、数据边界和组件组合。

## 4. 布局

- 全站外壳是 `BasicLayout`：固定侧栏 + 唯一的 `main` 滚动区 + 跟在正文后面的页脚。页面只写正文，不要重复写导航、`main`、全屏高度或外侧边距。
- 宽度由 `LayoutContainer`（`max-w-7xl`）统一控制。侧栏宽度：md 为图标栏 `w-20`，lg 为 `w-60`，xl 为 `w-64`。
- md 以下改用固定底部导航（首页、探索、收藏、工作台、更多），正文底部预留 `pb-16`。
- 首页使用 `ReadingLayout`：lg 及以上为“信息流 2 : 发现区 1”，窄屏时发现区排到后面。首屏直接是内容，不放宣传 Hero。
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
- 交互元素可以用键盘访问；装饰图形加 `aria-hidden`；状态区域有语义名称。
- 每次改动 UI，都要在桌面和 390px 宽的窄屏下分别用浏览器检查。
