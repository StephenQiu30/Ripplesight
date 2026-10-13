# Ripplesight 工程规范

适用于整个仓库，对人和 AI 代理都有效。`CLAUDE.md` 通过导入加载本文件，规则只在这里修改。技术架构见 [PROJECT](PROJECT.md)，产品能力见[文档工作区](docs/index.md)，进度见 [BACKLOG](BACKLOG.md)。

## 当前约定

项目文档仅在 docs/ 维护 Markdown/Git，Obsidian 直接打开 docs。只保留当前需求与规范，不保留历史文档、归档副本或按日期追加的授权记录。

视觉以 Figma 桌面稿 DfWRfnw965ocH6lmlSYGgs 和 [编号设计](docs/index.md#设计主题) 的现行要求为准。已有页面用于核对接口、会话和权限依赖；缺失数据保留设计区块与真实空态，不编造样本。物理删表先验证消费者、备份恢复与迁移。提交与推送遵守 §7。

## 1. 分工

| 角色 | 负责 |
|---|---|
| 需求提出者 | 确定方向与优先级；提供账号、凭据和模型名；授权提交与推送 |
| 实施代理 | 按当前需求实现代码与测试，完成 §5 的检查并更新 BACKLOG |
| 独立审查代理 | 只读核查需求、改动与验证结果，由实施代理修复；不能用自检替代独立审查 |

## 2. 开始改动前

1. 先读 [docs/index.md](docs/index.md#需求驱动的交付规范)、本次任务对应的详细需求、开发PRD、目标设计、包含SPEC开发合同的agent PLAN与当前 BACKLOG，再按实际需要查代码和测试。
2. 按 [SDD开发规范](docs/index.md#plan内嵌specsdd) 和所属PLAN组织实施，确认本切片的US/FR/AC、输入合同、评审基线及就绪门槛，再按同文件任务开发。如果对应不上或规格冲突，先修所属文档并评审；具体切片和基线记录方式由PLAN说明，不在工程入口统一强制额外提交或固定工作流。提交与推送仍遵守§7，不能为了兼容旧实现保留错误方案。
3. 架构、目录或数据库有变化时，先更新 PROJECT。
4. 工作区里不属于本次任务的修改原样保留，不要覆盖或回退。

## 3. 代码规则

**后端**
- 遵守 PROJECT §5 的分层规则，以及 §6 的数据库规则。
- 按真实的业务切片建文件；没有使用方就不建模块，不预留空包。
- 外部系统的差异才定义 Adapter；复杂且需要复用的查询才拆出 Repository。
- 优先使用官方客户端和标准库；开源项目的复用按 [产品边界](docs/requirement/00-产品目标与边界.md#已确认边界) 处理，改编代码须保留原许可证和作者署名。

### Python 规范与自动检查

后端以 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) 为团队规范基础，结合 [PEP 8](https://peps.python.org/pep-0008/) 和 [PEP 257](https://peps.python.org/pep-0257/)。适用于 `backend/` 中的业务代码、测试与工具脚本；配置以 `backend/pyproject.toml` 为准，依赖版本由 `backend/uv.lock` 固定。

- **格式与命名**：4 空格缩进，函数、变量与模块用 `snake_case`，类用 `CapWords`，常量用 `UPPER_SNAKE_CASE`，内部实现用单下划线前缀。避免遮蔽内置名称。格式交给 Ruff，不手工维护另一套格式。
- **导入**：按标准库、第三方、项目模块分组并排序，使用完整绝对路径，禁止星号和相对导入。通常在文件顶部导入；为解决依赖环或可选依赖而局部导入时说明原因。新增代码优先导入模块，使调用来源清晰。
- **类型**：业务函数的参数与返回值必须标注，使用 Python 3.12 类型语法；可空值明确为 `T | None`，容器说明元素类型，优先 `collections.abc` 中的接口。外部不可信数据先校验再进入业务层，不用 `Any`、`cast` 或 `type: ignore` 掩盖实际错误。生产源码全量执行 mypy strict；测试由 Ruff 和 pytest 检查，暂不纳入 mypy。
- **文档**：新增或修改的公共模块、类和函数须有说明职责与合同的 docstring；明显简单的成员、重写方法和测试函数可省略重复说明。复杂函数使用 Google 风格的 `Args:`、`Returns:` / `Yields:`、`Raises:`，写清副作用、边界与调用者需要处理的异常，不复述类型标注。注释解释原因与约束，避免逐行翻译代码。
- **异常与断言**：捕获可预期的具体异常，转换异常用 `raise ... from ...` 保留原因，不吞掉失败。只有任务、请求或资源清理等明确边界可以捕获 `Exception`，并负责记录、恢复或重新抛出；不能捕获 `BaseException` 干扰退出。`assert` 仅用于内部不变量和测试，用户输入、权限与配置校验必须显式判断并抛错。
- **状态与资源**：禁止可变默认参数，避免可变全局业务状态；文件、锁、连接和事务用上下文管理器或可靠的 `try/finally` 收尾。属性访问避免隐藏 I/O；推导式保持简单，复杂分支、嵌套和副作用改为明确循环。线程和异步共享状态须明确同步与生命周期，异步函数内不直接执行阻塞 I/O。
- **日志**：沿用 structlog 的固定事件名与结构化字段，不在日志调用中用 f-string、拼接或提前格式化字符串；捕获后需要堆栈时用 `logger.exception`。遵守 §4 的敏感信息限制，不重复记录同一失败。
- **例外管理**：`noqa` 和 `type: ignore` 必须指明规则或错误码，非显然的例外写明原因；除本节明确列出的迁移边界外，不得添加全局忽略、排除业务目录或降低 strict 来通过检查。新增无类型第三方依赖只允许针对该外部模块配置 `ignore_missing_imports`，并说明边界；优先使用官方类型或类型存根。

本项目对 Google 原文的明确调整：保留现有 **100 字符行宽、Ruff 默认双引号格式**；允许直接导入 FastAPI、Pydantic、SQLAlchemy、类型及项目领域类/函数，避免无业务收益的导入改写；日志使用 structlog。Google 原文要求 Pylint，本项目使用 Ruff 与 mypy 落实可自动化的规则，人工审查补充其余要求，不声称工具覆盖全部 Google 规则。

| 检查方式 | 强制范围 |
|---|---|
| Ruff lint | 原有 `E/F/I/N/UP/B/SIM/RUF`，补充 `W`、Google 风格 `D`、日志 `G/LOG`、禁止相对导入 `TID252`、Pylint 错误 `PLE` 和 `PLW0127/PLW1509`、禁止无错误码的忽略 `PGH003/PGH004` |
| Ruff format | `backend/` 中发现的 Python 文件，100 字符行宽、空格缩进、双引号 |
| mypy | `backend/app` 全量 strict、不可达代码、忽略项错误码、未使用的 awaitable 与无用忽略检查；缺失类型的第三方模块例外须逐项列明 |
| 独立审查 | 导入来源与局部导入原因、公共接口文档完整性、异常边界、全局状态、资源/并发、日志内容及分层；不能由 lint 通过替代 |

现有代码缺失 docstring 的 `D100–D107` 暂不作为全仓自动门禁，避免批量生成无意义文档；已有 docstring 的 Google 风格由 Ruff 检查，新增/修改公共接口的文档要求由独立审查核对。此迁移边界不允许通过新增忽略来隐藏已有格式问题。

本地在 `backend/` 执行 `uv sync --locked --group dev`，然后运行 §5 的检查；可用 `uv run --locked ruff check --fix .` 和 `uv run --locked ruff format .` 修复可自动处理的问题，修复后检查差异。CI 的 `backend / quality` 独立运行 lint、格式和类型检查，无需数据库、Kafka 或 MinIO；失败时该任务失败，不允许 `continue-on-error`。是否阻止合并取决于远端分支保护，不能仅凭工作流文件声称已强制阻止。当前后端工作流保留路径过滤；管理员将 quality 设为全 PR 必需状态前，须先调整触发或条件化任务，使纯 Web/文档 PR 也能产生所需状态，避免等待未触发的检查。

**Web**
- 业务请求只调用 `src/api` 里生成的函数，经由 `src/request.ts`；业务代码不直接导入 Axios，也不用 fetch / XHR。（ESLint 强制）
- 业务页面、复用组件和布局只组合 shadcn/Radix 组件和 `components/ui` 中的语义组件；原生小写 JSX 标签只能出现在 `components/ui`。（ESLint 强制）
- 测试只放在 `frontend/tests`，`src` 不导入测试库。（ESLint 强制）
- 视觉与交互规则见 [编号设计](docs/index.md#设计主题)。
- 不建 `features`、`common`、`patterns`、`shared` 目录。

**接口契约**
- 修改接口时，先启动同一提交的 API，再生成客户端（`pnpm openapi:generate`），最后改前端。生成的文件不要手改。
- Web 按错误的 `code` 和 HTTP 状态分支处理，不靠匹配 `message` 文本；传输层不全局弹提示，也不自动重试写请求。

## 4. 数据、凭据与外部请求

- 测试只用独立的 `hotkey_test_<后缀>` 库，成功或失败后都要删除；绝不能连业务库 `hotkey` 跑测试。
- Token、Cookie、密码、连接字符串不进代码、日志、数据库明文、测试快照或提交；只放在本机 `.env` 或独立的浏览器配置目录里。
- 只采公开内容或本人账号能看到的内容；遇到验证码或风控就停下，不绕过。不调用任何收费接口。（完整边界见 [产品边界](docs/requirement/00-产品目标与边界.md#已确认边界)）
- 测试中的外部请求一律用固定样本代替；真实请求只在验收时由本人授权后进行。

## 5. 完成前必须通过的检查

| 范围 | 命令（在对应目录执行） |
|---|---|
| 后端 | 在 `backend/` 执行 `uv sync --locked --group dev`，然后 `uv run --locked ruff check .`、`uv run --locked ruff format --check .`、`uv run --locked mypy`、`uv run --locked pytest`（集成测试需设置 `HOTKEY_TEST_DATABASE_URL`，指向独立的测试库） |
| Web | `pnpm lint`、`pnpm typecheck`、`pnpm format:check`、`pnpm test`、`pnpm build` |
| 契约 | 修改了接口时，`pnpm openapi:check` 无差异 |
| 数据库 | 修改了结构时，在全新库上执行 `schema.sql`，并跑结构断言 |
| 页面 | 修改了 UI 时，在桌面和 390px 宽的窄屏下分别检查正常、空、加载、错误、无权限五种状态，以及键盘操作 |
| 文档 | 在 frontend/ 下执行 `pnpm docs:check`；详细需求、开发PRD、目标设计和agent PLAN逐项使用同编号、同名称文件维护；职责与交接门槛遵守docs/index.md；普通 Markdown 即可，不强制 frontmatter 或生成索引 |

检查失败就照实报告，不能把跳过当作通过。

## 6. 什么算“完成”

- **代码完成**：§5 的检查全部通过，并经独立审查。
- **能力可用**：用本机真实数据跑通对应编号需求的验收标准，在 BACKLOG 记录结果、证据和仍未验证的范围。模板按需使用，不要求为每项任务新建能力、决策或验收文件。
- 单元测试、模拟数据或健康检查通过，只能算代码完成，不能算可用。

## 7. 提交与推送

- 未经本人明确授权，不提交、不推送、不创建或合并 PR、不删除远端分支。
- 提交信息格式：`type(scope):中文动宾描述`（冒号后不加空格，≤72 字符）。type 只能是 feat/fix/test/refactor/docs/chore/perf/build/ci/revert；scope 用稳定的小写英文；正文用中文写清改了什么、为什么改、怎么验证的。
- 一个提交只做一件可以独立验收的事；生成物和它的源文件放在同一个提交里。
