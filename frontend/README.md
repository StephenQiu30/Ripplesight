# HotKey Web

技术栈：pnpm、Next.js App Router、React、TypeScript、shadcn/ui、Radix UI、Tailwind CSS、Axios、ESLint、Prettier。

首页实现在 `src/app/components/`，沿用 [DESIGN](DESIGN.md) 的黑白留白、语义令牌和统一 BasicLayout，展示真实公开资讯、事件、专题和周刊。主入口“浏览资讯”进入 `/discover`，个人关注入口按真实会话进入 `/workspace` 或 `/login?returnTo=%2Fworkspace`；通用登录默认仍为 `/topics`。来源能力、主题配置及保存复用生成 API。

业务页面按当前 Swagger 重建：关注的基础设置包含名称、关键词和来源，进阶规则与频率按需展开；来源页优先配置，覆盖信息放在二级页签。相关内容、热榜、采集记录及已有报告只呈现真实接口结果。共用外壳位于 `src/layout/`，固定头尾与正文滚动区，各页面共享宽度、边距、字体与语义颜色。

## 运行

```bash
# 首次配置只在仓库根目录执行：cp .env.example .env
# 在 frontend/ 执行：
pnpm install
pnpm dev
```

Next 配置与 OpenAPI 生成器从根 `.env` 仅加载 `HOTKEY_API_ORIGIN`、`HOTKEY_WEB_ORIGIN`、`HOTKEY_OPENAPI_URL` 和 `NEXT_PUBLIC_SITE_ORIGIN`；已注入的环境变量优先，GitHub、SMTP、数据库等秘密不加载到 Web 进程。容器只使用 Compose 注入的 Web 字段，不复制环境文件。

本机前端固定监听 `http://127.0.0.1:8666`，后端固定使用 `http://127.0.0.1:8667`；`pnpm dev` 和 `pnpm start` 均使用该前端地址。

浏览器请求统一使用同源 `/api/*`，`src/app/api/[[...path]]/route.ts` 根据服务端 `HOTKEY_API_ORIGIN` 转发；`src/proxy.ts` 负责 CSP nonce 与真实会话验证，包含深链接与预取。私有 SSR 请求统一由 Axios 封装转发限定 Cookie。

## 公开页面与登录工作区

本机页面统一使用 `HOTKEY_WEB_ORIGIN` 指定的地址（默认 `http://127.0.0.1:8666`）。同协议、同端口的 `localhost` / `127.0.0.1` / `[::1]` 页面访问先跳转到该地址，避免登录 Origin、会话 Cookie 和 OAuth 回调使用不同主机；API 写入仍严格校验原 Origin，不重写来源或重放跨源提交。GitHub OAuth App 需配置 `HOTKEY_GITHUB_CLIENT_ID`、`HOTKEY_GITHUB_CLIENT_SECRET`，Callback URL 为 `${HOTKEY_WEB_ORIGIN}/api/identity/github/callback`，OAuth App 的授权仅请求 `user:email`；密钥只放本机未跟踪 `.env`。

公开页面包含首页和说明、`/discover`及专题/故事、`/items/[contentId]`、公共日周月刊目录和合法刊期、已发布模型榜。资讯和刊物固定读取明确的公共发布分区并复核当前许可，未配置时显示未发布，各块读取失败独立保留恢复入口；不混用个人采集分区。`/login` 提供账号密码、GitHub、邮箱验证码，第三方与邮件可用性读取实际配置。

个人主题、报告生成/发送、来源和管理工作区需要真实登录并始终 noindex，账户菜单支持退出及 `/account` 凭据设置；首页个人入口安全回跳 `/workspace`，通用登录默认 `/topics`。来源授权与凭据独立。公共刊物不代表个人主题周报执行已完成；个人周报和无模型基础公开阅读的实现缺口见 [BACKLOG](../BACKLOG.md)。个人入口文案引导配置关注和阅读已有报告，完整周期生成按对应验收成立后再承诺。

账户会话由后端验证并通过 HttpOnly Cookie 保存；同源代理仅转发 HotKey 身份 Cookie 与对应 Set-Cookie，写入使用现行 CSRF 合同。登录服务故障显示可恢复状态，不将网络失败当成退出。所有登录、邮箱验证、OAuth 开始、退出和凭据设置调用 Umi 生成的 identity API，不手写请求。

页面访问合同见 [Design001 §9.2](../docs/design/001-热点舆情监控平台总体设计.md#92-公开欢迎页登录与个人数据访问)，验证边界见 [共享验收](../docs/acceptance/001-共享运行门槛验收.md)。

公开 metadata 的 origin 使用 `NEXT_PUBLIC_SITE_ORIGIN` 或服务端 `HOTKEY_WEB_ORIGIN`，本机默认为 `http://127.0.0.1:8666`；部署时设置实际站点地址。sitemap 列公开说明和阅读目录，排除 `/login` 与无列表语义的 `/items`；单篇/故事/刊期 metadata 按真实 DTO 的索引许可决定 noindex。robots 声明公开阅读入口，私人工作区保持认证与 noindex；robots 不是权限控制。交互 HTML 保持逐请求 CSP nonce。

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

所有测试统一放独立 `tests/`，其中 `app/`、`components/` 对应业务目录，`config/` 放 ESLint/OpenAPI 配置测试；传输与 CSP 测试放测试目录根。`src/` 和前端根不放测试文件，业务代码不导入测试框架或测试目录。`pnpm test` 只发现 tests，`pnpm typecheck` 同时检查生产和测试配置；生产构建及 Docker 上下文排除测试。

## API

启动后端后，直接读取其自动生成的 `/openapi.json` 生成客户端：

```bash
pnpm openapi:generate
```

默认地址为 `http://127.0.0.1:8667/openapi.json`；其他环境使用 `HOTKEY_OPENAPI_URL=https://api.example.com/openapi.json pnpm openapi:generate`。该变量统一写入根 `.env`，也可通过命令环境显式覆盖。

`@umijs/openapi` 1.14.1 只从 200/201 选择返回模型；配置会在生成器内存中把缺少 200/201 的 202 schema 暴露给其类型解析，运行时 OpenAPI 和真实 HTTP 202 语义保持不变。禁止为规避该限制手改生成文件或在服务端虚报 200。

生成结果直接写入 `src/api/`，统一调用 `src/request.ts`。请求封装负责凭据、超时、响应数据提取以及错误标准化。

业务代码只能调用 `src/api/` 中的生成函数，禁止手写请求、直接导入 Axios 或传输 `request`、调用 `fetch`/XHR、复制服务端 DTO，以及手工修改生成文件。错误类和请求选项类型可以从 `src/request.ts` 导入。`pnpm lint` 检查请求边界，`pnpm openapi:check` 检查生成漂移；同源透明代理只转发通用协议，不定义业务请求。

来源配置 API 仅支持已有连接的状态更新；来源预设由维护者使用后端 CLI 应用。网页不会模拟预设设置或将任务受理显示为采集完成。API 不可用时就地显示错误和重试，创建页保留可填写的草稿。

## 富文本 Editor / Viewer

通用组件统一从 `@/components/editor` 导入。`Editor` 只在浏览器动态加载 Editor.js，
受控 `value` 和 `onChange` 使用官方 OutputData；提交时等待 `ref.save()`，
避免依赖尚未完成的 onChange。`Viewer` 在服务端也可读取相同 JSON，
支持显式 `format="markdown" | "html" | "text"` 的旧字符串，统一清洗后展示。
默认字符串格式为 Markdown，`citations` 可绑定报告冻结引用，`headingOffset` 避免重复页面主标题。

```tsx
import { useRef, useState } from "react";
import {
  Editor,
  Viewer,
  type EditorDocument,
  type EditorHandle,
} from "@/components/editor";

function ContentEditor() {
  const [document, setDocument] = useState<EditorDocument>({ blocks: [] });
  const editorRef = useRef<EditorHandle>(null);
  // 在提交处理函数中：const current = await editorRef.current!.save();
  return (
    <>
      <Editor
        ref={editorRef}
        value={document}
        onChange={setDocument}
        aria-label="正文"
      />
      <Viewer value={document} />
    </>
  );
}
```

支持段落、标题、嵌套/任务列表、引用、代码、表格、分隔线及粘贴图片 URL。
图片不上传。报告/API/导出继续使用原 Markdown；阅读笔记在原本机存储键增加
`noteDocument`，保留兼容的 `note`、阅读模式和位置，旧文字自动恢复。
组件状态、主题和安全边界见 [DESIGN](DESIGN.md)。

## 检查

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```

生产镜像监听 `8080`，使用 standalone 输出、非 root 用户和只读文件系统。

仓库根 `docker-compose.yml` 启动应用，默认复用已有环境；`docker-compose-prod.yml` 复用相同应用定义，通过显式 `--env-file .env.prod` 启动生产服务。环境依赖单独归 `docker-compose-env.yml`，本地开发默认不启动；宿主 Web/API 入口分别固定为 `127.0.0.1:8666` 与 `127.0.0.1:8667`，Web 在容器网络中代理至 API 的内部 `8080` 端口。
