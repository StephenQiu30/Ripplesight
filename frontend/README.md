# HotKey Web

技术栈：pnpm、Next.js App Router、React、TypeScript、shadcn/ui、Radix UI、Tailwind CSS、Axios、ESLint、Prettier。

首页方案 1 直接实现在 `src/app/components/`，采用 Vercel 黑白留白风格。“创建关注”进入现有 `/monitors/new`，“我的关注”进入 `/events`；来源能力、主题配置及保存复用现有生成 API。指南和示例只提供简短说明。

业务页面按当前 Swagger 重建：关注的基础设置包含名称、关键词和来源，进阶规则与频率按需展开；来源页优先配置，覆盖信息放在二级页签。相关内容、热榜、采集记录及已有报告只呈现真实接口结果，移除没有接口的事件聚合占位与非核心偏好表单。共用导航位于 `src/components/navigation/`，不增加第二套页面或请求层。

## 运行

```bash
cp .env.example .env.local
pnpm install
pnpm dev
```

浏览器请求统一使用同源 `/api/*`，`src/app/api/[[...path]]/route.ts` 根据服务端 `HOTKEY_API_ORIGIN` 转发；`src/proxy.ts` 只负责 CSP nonce。

## Demo 业务入口

当前 Demo 直接访问 `/events`，登录、注册及用户体系删除。业务页面不读取身份、不显示账户/退出操作，也不因错误跳往登录页。来源授权和凭据状态仍由来源页面显示。

写请求由 `src/request.ts` 设置固定 `X-HotKey-CSRF: 1`，无需 Cookie/token。Next 同源代理不转发旧 Cookie/Authorization，也不向浏览器透传 Set-Cookie；加载、空、错误/重试、草稿冲突及请求编号继续有效。

页面访问合同见 [Design001 §9.2](../docs/design/001-热点舆情监控平台总体设计.md#92-当前-demo-的访问与数据分区)，验证边界见 [共享验收](../docs/acceptance/001-共享运行门槛验收.md)；API 从同版本后端 OpenAPI 生成，不手写端点。

未来 ToC 的用户名密码、GitHub App、邮箱验证码和无感登录需求后置。当前 Demo 保持 `noindex`、生产 CSP nonce 和动态交互入口。

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
