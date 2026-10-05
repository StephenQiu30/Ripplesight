# HotKey 工程规范

适用于整个仓库，对人和 AI 代理都有效。`CLAUDE.md` 通过导入加载本文件，规则只在这里修改。技术架构见 [PROJECT](PROJECT.md)，产品能力见[文档工作区](workspace/content/index.md)，进度见 [BACKLOG](BACKLOG.md)。

## 1. 分工

| 角色 | 负责 |
|---|---|
| 本人（需求提出者） | 定方向与优先级；提供账号登录、凭据和模型名；授权提交与推送 |
| Claude | 维护 docs 与 BACKLOG；写任务卡并派给 Codex；审查代码；做真实运行验收并记录结果。不写实现代码 |
| Codex | 按任务卡实现代码和测试，并跑完 §5 的检查 |

## 2. 开始改动前

1. 先读 [workspace/content/index.md](workspace/content/index.md)，按其中的阅读顺序读 [PRD](workspace/content/product/01-PRD.md)、对应的能力文档（`workspace/content/capabilities/`）、相关决策（`workspace/content/decisions/`）和相关代码、测试。
2. 确认这次改动对应哪一条验收标准。如果对应不上，先改文档，再动代码。
3. 架构、目录或数据库有变化时，先更新 PROJECT。
4. 工作区里不属于本次任务的修改原样保留，不要覆盖或回退。

## 3. 代码规则

**后端**
- 遵守 PROJECT §5 的分层规则，以及 §6 的数据库规则。
- 按真实的业务切片建文件；没有使用方就不建模块，不预留空包。
- 外部系统的差异才定义 Adapter；复杂且需要复用的查询才拆出 Repository。
- 优先使用官方客户端和标准库；开源项目的复用按 [优先复用开源项目](workspace/content/decisions/08-优先复用开源项目.md) 处理，改编代码要在 THIRD_PARTY_NOTICES 署名。

**Web**
- 业务请求只调用 `src/api` 里生成的函数，经由 `src/request.ts`；业务代码不直接导入 Axios，也不用 fetch / XHR。（ESLint 强制）
- 业务页面、复用组件和布局只组合 shadcn/Radix 组件和 `components/ui` 中的语义组件；原生小写 JSX 标签只能出现在 `components/ui`。（ESLint 强制）
- 测试只放在 `frontend/tests`，`src` 不导入测试库。（ESLint 强制）
- 视觉与交互规则见 [frontend/DESIGN](frontend/DESIGN.md)。
- 不建 `features`、`common`、`patterns`、`shared` 目录。

**接口契约**
- 修改接口时，先启动同一提交的 API，再生成客户端（`pnpm openapi:generate`），最后改前端。生成的文件不要手改。
- Web 按错误的 `code` 和 HTTP 状态分支处理，不靠匹配 `message` 文本；传输层不全局弹提示，也不自动重试写请求。

## 4. 数据、凭据与外部请求

- 测试只用独立的 `hotkey_test_<后缀>` 库，成功或失败后都要删除；绝不能连业务库 `hotkey` 跑测试。
- Token、Cookie、密码、连接字符串不进代码、日志、数据库明文、测试快照或提交；只放在本机 `.env` 或独立的浏览器配置目录里。
- 只采公开内容或本人账号能看到的内容；遇到验证码或风控就停下，不绕过。不调用任何收费接口。（完整边界见 [决策](workspace/content/index.md#决策)）
- 测试中的外部请求一律用固定样本代替；真实请求只在验收时由本人授权后进行。

## 5. 完成前必须通过的检查

| 范围 | 命令（在对应目录执行） |
|---|---|
| 后端 | `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`、`uv run pytest`（集成测试需设置 `HOTKEY_TEST_DATABASE_URL`，指向独立的测试库） |
| Web | `pnpm lint`、`pnpm typecheck`、`pnpm format:check`、`pnpm test`、`pnpm build` |
| 契约 | 修改了接口时，`pnpm openapi:check` 无差异 |
| 数据库 | 修改了结构时，在全新库上执行 `schema.sql`，并跑结构断言 |
| 页面 | 修改了 UI 时，在桌面和 390px 宽的窄屏下分别检查正常、空、加载、错误、无权限五种状态，以及键盘操作 |
| 文档 | 本地链接有效，`git diff --check` 通过 |

检查失败就照实报告，不能把跳过当作通过。

## 6. 什么算“完成”

- **代码完成**：§5 的检查全部通过，并经 Claude 审查。
- **能力可用**：用本机真实数据跑通对应的验收标准，并在 `workspace/content/records/` 新建一份验收记录（用 `workspace/content/templates/03-验收记录.md`），同步更新能力文档的 `status`。
- 单元测试、模拟数据或健康检查通过，只能算代码完成，不能算可用。

## 7. 提交与推送

- 未经本人明确授权，不提交、不推送、不创建或合并 PR、不删除远端分支。
- 提交信息格式：`type(scope):中文动宾描述`（冒号后不加空格，≤72 字符）。type 只能是 feat/fix/test/refactor/docs/chore/perf/build/ci/revert；scope 用稳定的小写英文；正文用中文写清改了什么、为什么改、怎么验证的。
- 一个提交只做一件可以独立验收的事；生成物和它的源文件放在同一个提交里。
