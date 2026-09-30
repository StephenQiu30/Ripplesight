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

## Demo 访问

当前 Demo 直接进入 `/events`，删除 `/login`、`/register`、独占 auth 组件和身份先行请求；页面不显示账户信息或退出入口。`EventsWorkspace` 使用主题API，`TopicForm` 使用来源能力API，覆盖加载、空、错误重试与业务成功。来源授权/凭据和内容原生身份保留。

`request.ts` 写请求固定 `X-HotKey-CSRF: 1`；代理不转发 Cookie/Authorization 或 Set-Cookie，业务失败就地显示并支持重试，不跳登录。CSP nonce、动态交互入口和 `noindex` 保持。

访问规则见 [Design001 §9.2](../docs/design/001-热点舆情监控平台总体设计.md)，文件和验证见 [Plan061](../docs/plan/061-Demo用户体系与历史依赖清理执行计划.md)。未来 ToC 登录需求后置，不保留组件或配置骨架。

## API 与状态

- 公共协议遵循 PROJECT.md 与 AGENTS.md 的现行契约；旧 Design 046 全局异常与响应契约已删除，见 Git 历史。046 S03 是后续实施的共同前置；本文件仅细化 Web 消费与展示，不另定义返回模型。
- 资源、分页、受理 DTO 和 ErrorView 来自同提交运行时 OpenAPI；错误读取 details，请求 ID 支持响应头/body 回退。HTTP、网络、超时、取消和协议失败分开；204 与文件不解析为 JSON，失败任务查询与合法空结果保持正常读取语义。
- 传输层不全局弹提示、不按 message 分支、不自动重试写操作。字段错误就地显示，页面失败保留恢复入口，操作结果使用适当短时反馈；旧数据刷新失败要标明过期。
- Umi OpenAPI 将端点和类型直接生成到 `src/api/`。
- 所有生成请求统一使用 `src/request.ts`，页面不得手写端点或创建第二套 HTTP 客户端。
- App Router 统一提供 loading、error、global-error 和 not-found 边界。
- `src/components/system/page-state.tsx` 中的 `PageState` 处理页面错误、空态、无权限和恢复操作。

## 可访问性与运行

- 交互支持键盘焦点，装饰图形使用 `aria-hidden`，状态区域提供语义名称。
- 动效遵循 `prefers-reduced-motion`。
- 页面必须完成桌面和窄屏浏览器检查。
- 生产镜像使用 standalone、非 root、只读文件系统和 `/health` 健康检查。
- CSP nonce 由 `src/proxy.ts` 每请求生成；需要客户端交互的 HTML 入口必须按请求渲染。主题创建页在服务端入口等待 Next.js `connection()`，保持来源校验；生产脚本 nonce 必须与本次 CSP 一致，HTML 不使用共享缓存。生产镜像的 runtime 检查与浏览器冷进入均需通过。
