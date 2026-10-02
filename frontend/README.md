# HotKey Web

技术栈：pnpm、Next.js App Router、React、TypeScript、shadcn/ui、Radix UI、Tailwind CSS、Axios、ESLint、Prettier。

首页方案 1 实现在 `src/app/components/`，采用 Vercel 黑白留白风格，作为公开 SEO Welcome。主入口“开始使用”进入 `/login`，登录后默认进入 `/topics`；来源能力、主题配置及保存复用生成 API。指南和示例只提供简短说明。

业务页面按当前 Swagger 重建：关注的基础设置包含名称、关键词和来源，进阶规则与频率按需展开；来源页优先配置，覆盖信息放在二级页签。相关内容、热榜、采集记录及已有报告只呈现真实接口结果。共用外壳位于 `src/layout/`，固定头尾与正文滚动区，各页面共享宽度、边距、字体与语义颜色。

## 运行

```bash
cp .env.example .env.local
pnpm install
pnpm dev
```

浏览器请求统一使用同源 `/api/*`，`src/app/api/[[...path]]/route.ts` 根据服务端 `HOTKEY_API_ORIGIN` 转发；`src/proxy.ts` 负责 CSP nonce 与真实会话验证，包含深链接与预取。私有 SSR 请求统一由 Axios 封装转发限定 Cookie。

## 公开页面与登录工作区

公开页面为首页、关于、隐私、条款、联系与变更说明，保留 SEO metadata、robots 和 sitemap。`/login` 提供账号密码、GitHub、邮箱验证码三种方式；第三方与邮件可用性读取实际服务配置。登录后才能访问原“更多”中的工作区页面，默认进入 `/topics` 或安全站内原目标。工作区始终 noindex，沿用原导航与统一 BasicLayout；账户菜单支持退出及 `/account` 凭据设置。来源授权与凭据仍独立处理。

账户会话由后端验证并通过 HttpOnly Cookie 保存；同源代理仅转发 HotKey 身份 Cookie 与对应 Set-Cookie，写入使用现行 CSRF 合同。登录服务故障显示可恢复状态，不将网络失败当成退出。所有登录、邮箱验证、OAuth 开始、退出和凭据设置调用 Umi 生成的 identity API，不手写请求。

页面访问合同见 [Design001 §9.2](../docs/design/001-热点舆情监控平台总体设计.md#92-公开欢迎页登录与个人数据访问)，实施见 [Plan063](../docs/plan/063-公开欢迎页与三种登录执行计划.md)，验证边界见 [共享验收](../docs/acceptance/001-共享运行门槛验收.md)。

公开 metadata 的 origin 使用 `NEXT_PUBLIC_SITE_ORIGIN` 或服务端 `HOTKEY_WEB_ORIGIN`，本机默认为 `http://127.0.0.1:3001`；部署时设置实际站点地址。robots 与 sitemap 不列出登录或业务路由。交互 HTML 保持逐请求 CSP nonce。

## 目录

```text
src/
├── app/                  # 路由；页面专属组件放对应路由的 components/
├── api/                  # Umi OpenAPI 生成文件
├── components/ui/        # shadcn 基础组件
├── components/<feature>/ # 跨页面复用组件
├── layout/               # BasicLayout、统一 Header/Footer、容器和共用指南
├── lib/                  # 纯工具
├── proxy.ts              # 真实会话门禁与 CSP nonce
└── request.ts            # Axios 请求封装
```

不创建 `features`、`common`、`patterns`、`shared` 或 `scripts` 目录。复用组件按功能领域分类；页面组件保留在所属路由中。组件归属、复用范围、目标路径、数据来源和状态覆盖必须在 Design 阶段确定。

根路由统一使用 `layout/BasicLayout`，Header/Footer 固定在视口两端，正文在唯一 main 内滚动，头尾和正文使用相同容器宽度及边距。页面不再重复导航、main 或全屏尺寸。正文滚动容器通过 `useLayoutScrollContainer` 提供给阅读进度功能，保存与恢复保留原本机存储格式；打印恢复自然文档流。

所有测试统一放独立 `tests/`，其中 `app/`、`components/` 对应业务目录，`config/` 放 ESLint/OpenAPI 配置测试；传输与 CSP 测试放测试目录根。`src/` 和前端根不放测试文件，业务代码不导入测试框架或测试目录。`pnpm test` 只发现 tests，`pnpm typecheck` 同时检查生产和测试配置；生产构建及 Docker 上下文排除测试。独立内存 prototype 已由正式前端承接并退役。

## API

启动后端后，直接读取其自动生成的 `/openapi.json` 生成客户端：

```bash
pnpm openapi:generate
```

默认地址为 `http://127.0.0.1:8867/openapi.json`；其他环境使用 `HOTKEY_OPENAPI_URL=https://api.example.com/openapi.json pnpm openapi:generate`。该变量需传入命令环境，生成器不自动加载 Next.js 的 `.env.local`。

`@umijs/openapi` 1.14.1 只从 200/201 选择返回模型；配置会在生成器内存中把缺少 200/201 的 202 schema 暴露给其类型解析，运行时 OpenAPI 和真实 HTTP 202 语义保持不变。禁止为规避该限制手改生成文件或在服务端虚报 200。

生成结果直接写入 `src/api/`，统一调用 `src/request.ts`。请求封装负责凭据、超时、响应数据提取以及错误标准化。

业务代码只能调用 `src/api/` 中的生成函数，禁止手写请求、直接导入 Axios 或传输 `request`、调用 `fetch`/XHR、复制服务端 DTO，以及手工修改生成文件。错误类和请求选项类型可以从 `src/request.ts` 导入。`pnpm lint` 检查请求边界，`pnpm openapi:check` 检查生成漂移；同源透明代理只转发通用协议，不定义业务请求。

来源配置 API 仅支持已有连接的状态更新；来源预设由维护者使用后端 CLI 应用。网页不会模拟预设设置或将任务受理显示为采集完成。API 不可用时就地显示错误和重试，创建页保留可填写的草稿。

## 检查

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```

生产镜像监听 `8080`，使用 standalone 输出、非 root 用户和只读文件系统。

仓库根 `docker-compose.yml` 启动应用，默认复用已有环境；`docker-compose-prod.yml` 复用相同应用定义，通过显式 `--env-file .env.prod` 启动生产服务。环境依赖单独归 `docker-compose-env.yml`，本地开发默认不启动；Web 默认绑定 `127.0.0.1:3000`，并在容器网络中代理至 API。端口可通过根 `.env` 调整。
