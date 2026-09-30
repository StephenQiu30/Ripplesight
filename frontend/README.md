# HotKey Web

技术栈：pnpm、Next.js App Router、React、TypeScript、shadcn/ui、Radix UI、Tailwind CSS、Axios、ESLint、Prettier。

## 运行

```bash
cp .env.example .env.local
pnpm install
pnpm dev
```

浏览器请求统一使用同源 `/api/*`，`src/app/api/[[...path]]/route.ts` 根据服务端 `HOTKEY_API_ORIGIN` 转发；`src/proxy.ts` 只负责 CSP nonce。

## 账户与登录

目标 Web 统一 `/login`，保留用户名和密码登录，与 GitHub App、邮箱验证码并存；GitHub 或邮箱首次成功验证可注册，已有用户进入自己的工作台。移除部署密钥、单账户限制与独立工作区身份包装；资源归属由后端从会话派生，页面不让用户填写 owner 标识。登录入口保持 `noindex`。

无感登录通过现有服务端 Cookie 校验实现：有效会话自动恢复，已登录用户进入工作台；过期、撤销或退出后返回登录验证。保留用户名/密码字段及必要状态，不新增 JWT refresh 框架。

当前页面和生成 API 客户端仍对应旧身份实现；GitHub App 与邮箱验证码尚不可用。本轮只更新设计和文档，运行和生成命令仍面向当前代码。组件、状态与账户合同见 [Design 001 §9.2](../docs/design/001-热点舆情监控平台总体设计.md)，替换工作由 [Plan 060](../docs/plan/060-GitHub与邮箱验证码登录执行计划.md) 承接；实现后从同版本后端 OpenAPI 重新生成客户端。

GitHub App 凭据、邮件发送凭据和验证码校验只在后端处理；Web 通过同源代理使用服务端会话 Cookie，写请求保留 CSRF 校验。邮件登录与后续报告邮件投递分别验证。

## 目录

```text
src/
├── app/                  # 路由；页面专属组件放对应路由的 components/
├── api/                  # Umi OpenAPI 生成文件
├── components/ui/        # shadcn 基础组件
├── components/<feature>/ # 跨页面复用组件
├── lib/                  # 纯工具
├── proxy.ts              # CSP nonce
└── request.ts            # Axios 请求封装
```

不创建 `features`、`common`、`patterns`、`shared` 或 `scripts` 目录。复用组件按功能领域分类；页面组件保留在所属路由中。组件归属、复用范围、目标路径、数据来源和状态覆盖必须在 Design 阶段确定。

## API

启动后端后，直接读取其自动生成的 `/openapi.json` 生成客户端：

```bash
pnpm openapi:generate
```

默认地址为 `http://127.0.0.1:8867/openapi.json`；其他环境使用 `HOTKEY_OPENAPI_URL=https://api.example.com/openapi.json pnpm openapi:generate`。该变量需传入命令环境，生成器不自动加载 Next.js 的 `.env.local`。

`@umijs/openapi` 1.14.1 只从 200/201 选择返回模型；配置会在生成器内存中把缺少 200/201 的 202 schema 暴露给其类型解析，运行时 OpenAPI 和真实 HTTP 202 语义保持不变。禁止为规避该限制手改生成文件或在服务端虚报 200。

生成结果直接写入 `src/api/`，统一调用 `src/request.ts`。请求封装负责凭据、超时、响应数据提取以及错误标准化。

## 检查

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```

生产镜像监听 `8080`，使用 standalone 输出、非 root 用户和只读文件系统。

仓库根 `docker-compose.yml` 是唯一完整运行入口；Web 默认绑定 `127.0.0.1:3000`，并在容器网络中代理至 API。端口可通过根 `.env` 调整。
