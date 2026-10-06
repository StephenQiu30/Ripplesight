# 文档网站验证记录

以下原始记录保留历史上下文，不作为当前 checkout 或线上部署的证明。本轮重新执行的结果见文末。

## 原始记录

核验日期：2026-10-06。仓库 HEAD 仍为 `b8b76234`；未提交、未推送，未设置 GitHub Pages。`backend/`、`frontend/` 和既有 `.codex/` 删除不在本次修改范围。

环境：Node `v24.19.0`，运行脚本的 pnpm `12.3.4`。安装了 npm registry 当前稳定版本 Nextra/theme `4.6.1`、Next `16.3.8`、React/React DOM `19.3.0`；TypeScript `5.9.3` 与前端保持同一主版本。

下列命令在 `workspace/` 执行。沙箱不允许写入用户级包管理器缓存，因此命令使用 `PNPM_HOME=/private/tmp/hotkey-docs-pnpm`；首次安装同时使用 `npm_config_cache=/private/tmp/hotkey-docs-npm`。未覆盖 HTTP(S)_PROXY。

| 命令 | 结果 |
|---|---|
| `npm_config_cache=/private/tmp/hotkey-docs-npm PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm install --store-dir /private/tmp/hotkey-docs-store` | 成功，pnpm 12.3.4；生成独立锁文件 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm install --frozen-lockfile --store-dir /private/tmp/hotkey-docs-store` | 退出 0；锁文件验证 495 项，无需解析更新 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm index` | 退出 0；“索引已是最新，无改动。” |
| `git diff --exit-code -- content/index.md` | 退出 0，无输出 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm check` | 退出 0；24 个发布页面；8 个回归用例通过；TypeScript 通过 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm build` | 退出 0；24 个文档静态页面；Pagefind 索引 24 页、1559 个词、zh 单语言 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm preview` | 启动 `http://127.0.0.1:8668/hotkey-server/` |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm verify` | 退出 0；24 个页面与原文均返回 200；导航、元数据、全文嵌入、改写链接和 AI 导出断言通过 |

`pnpm verify` 使用导出的 `out/_pagefind/pagefind.js` API，在 Node 中经 HTTP 加载真实索引。采用与 Nextra Search 相同的 `baseUrl: '/'`，验证结果链接挂载到 `/hotkey-server` 后能返回 200。

| 查询 | 结果数 | 首条结果 |
|---|---|---|
| 舆情 | 12 | 舆情监控开源方案调研 |
| 评论 | 14 | 04 评论舆情 |
| 情感 | 8 | 04 评论舆情 |

显式 curl 命令如下，四条均退出 0、返回 HTTP 200：

```sh
curl --noproxy '*' -fsS -o /private/tmp/hotkey-docs-home.html -w 'home HTTP %{http_code}\n' http://127.0.0.1:8668/hotkey-server/
curl --noproxy '*' -fsS -o /private/tmp/hotkey-docs-capability.html -w '评论舆情 HTTP %{http_code}\n' 'http://127.0.0.1:8668/hotkey-server/capabilities/04-%E8%AF%84%E8%AE%BA%E8%88%86%E6%83%85/'
curl --noproxy '*' -fsS -o /private/tmp/hotkey-docs-progress.html -w '进度 HTTP %{http_code}\n' 'http://127.0.0.1:8668/hotkey-server/product/02-%E8%BF%9B%E5%BA%A6%E4%B8%8E%E4%BC%98%E5%85%88%E7%BA%A7/'
curl --noproxy '*' -fsS -o /private/tmp/hotkey-docs-llms.txt -w 'llms.txt HTTP %{http_code}\n' http://127.0.0.1:8668/hotkey-server/llms.txt
```

进度页 HTML 包含 `HotKey BACKLOG` 到“由 Claude 写任务卡并派给 Codex 开发”的末节正文。能力链接为 `/hotkey-server/capabilities/04-评论舆情/`（编码形式也可访问），工程规范链接为 `https://github.com/StephenQiu30/hotkey-server/blob/main/AGENTS.md`。技术架构页包含 PROJECT 的技术栈、数据库、配置与部署等章节。回归用例还核对了 `backend/README.md` 和 `PROJECT.md#6-数据库` 的 GitHub 改写与锚点保留。

已列出和核对的产物：

```text
out/llms.txt                                8597 bytes
out/llms-full.txt                          62299 bytes
out/_pagefind/
out/_pagefind/pagefind.js                  45555 bytes
out/capabilities/04-评论舆情/index.html
out/raw/capabilities/04-评论舆情.md           3413 bytes
```

HTML 使用 Markdown 模式编译，保留首页 HTML 注释标记，首页与写作规则不需要改动。模板、看板和 `.obsidian` 没有生成路由或 AI 原文；Pagefind 只索引发布正文。Nextra 的 Layout 校验缺陷通过持久 pnpm 补丁修复，补丁同时翻译主题无法配置的五处 UI/无障碍标签；详见 README 与 THIRD_PARTY_NOTICES。

在仓库根目录执行 `git diff --check` 通过；`git diff --exit-code -- workspace/content/index.md BACKLOG.md` 无输出；`git diff --summary -- workspace/content` 无输出，未重命名或移动内容文件。工作流 YAML 的事件和 Pages 权限已解析验证。

新增文件：

- `.github/workflows/workspace-site.yml`
- `workspace/.node-version`、`.npmrc`、`package.json`、`pnpm-lock.yaml`、`pnpm-workspace.yaml`、`tsconfig.json`、`next.config.mjs`
- `workspace/app/layout.tsx`、`app/[[...slug]]/page.tsx`、`app/not-found.tsx`、`app/style.css`、`mdx-components.tsx`
- `workspace/scripts/content.mjs`、`content.d.mts`、`navigation.mjs`、`index.mjs`、`check.mjs`、`export.mjs`、`preview.mjs`、`verify.mjs`
- `workspace/tests/docs.test.mjs`、`patches/nextra-theme-docs@4.6.1.patch`、`README.md`、`VERIFICATION.md`

修改文件：`.gitignore`、`AGENTS.md`、根 `README.md`、`PROJECT.md`、`THIRD_PARTY_NOTICES.md`，以及 `workspace/content/product/02-进度与优先级.md`、`03-技术架构.md`（只移除旧 include 注释，保留 source 和 Obsidian 原文链接）。生成的 node_modules、.next、out、next-env.d.ts 不纳入版本控制。

尚未验证：桌面、390px 窄屏、键盘和浏览器搜索交互，以及真实 GitHub Actions/Pages 部署。浏览器工具对 `http://127.0.0.1:8668` 的访问被自动审批拒绝，工具理由为该地址未获用户授权；未绕过该拒绝。Node 查询和静态 HTTP 验证不等同于浏览器交互验收。仓库所有者仍需在 Settings → Pages → Source 选择 GitHub Actions。


## 本轮工具修复与编号复核

日期：2026-10-06。文档分类与编号修正已在 main 的 `286e4dbe` 提交并推送；以下检查针对其后的工作目录实现，包含本轮未提交修改，不冒充已发布快照。恢复缺失的脚本、测试与主题补丁后，重新执行当前检查；原始记录中的旧路径和浏览器审批结果不代表本轮状态。

产品编号按目录独立：`product/` 的进度、架构、工程规范依次为 01、02、03；`product/prd/` 的总 PRD、专项 PRD 为 01、02；`product/plan/` 的专项 PLAN 为 01。同目录重复编号、00、非英文目录及 PRD/PLAN 放错目录会拒绝。索引、导航、原文导出使用当前路径。

| 本轮检查 | 结果 |
|---|---|
| 冻结锁文件安装 | 退出 0；恢复并应用已登记的 Nextra/theme 4.6.1 补丁 |
| `pnpm index` | 生成 27 页清单的分类索引；二次生成无改动 |
| `pnpm check` | 27 个公开页面；13 个回归测试通过；TypeScript 通过 |
| `pnpm build` | 退出 0；27 个文档页面、中文 Pagefind 索引、逐页原文与 AI 导出生成 |
| `pnpm preview` + `pnpm verify` | 退出 0；27 页正文与原文 HTTP 200，导航、PLAN 元数据、根文件嵌入、链接及 AI 导出通过 |
| 中文查询 | 舆情 12 条、评论 14 条、情感 8 条；属于预览冒烟检查，不等于专项 KR3/KR4 |
| 桌面浏览器 | 分类导航、PLAN 元数据、中文搜索、无结果反馈、搜索加载反馈、方向键和回车打开命中章节、Escape 收起结果通过；专项 PRD 的 Mermaid 图完成渲染，未捕获浏览器 error/warn |
| 390px 窄屏浏览器 | 菜单可打开分类与 PLAN，正文和表格可读；页面宽度未超过可用视口；检查后恢复默认视口 |
| 公开内容边界 | 只导出显式清单；未登记私密/草稿样本不进入目录、原文或 AI 全文；错误登记、重复路径、缺失文件与符号链接越界拒绝；移除旧 raw 导出；模板引用不导出模板正文 |

预览地址为 `http://127.0.0.1:8668/hotkey-server/`。截图保存在当前 Codex 任务附件目录，不作为知识库作者原文。当前浏览器正常读取本地预览；本轮未发生原始记录所述的审批拒绝。

本轮没有启用或验收 GitHub Pages；没有接入 frontend `/workspace/docs`、服务端文档权限、真实 Obsidian 双端同步或 AI 问题集。静态预览无应用登录权限状态，不能据此声称通过专项 KR2。Claude 审查仍待进行，工具任务未标记为“代码完成”或“能力可用”。


## 接入方案草案复核

同日，工具实现已在 `8d562ced` 推送 main。随后根据当前源码整理 PROJECT §11，并新增 `capabilities/07-项目文档知识库.md`，明确专项 KR 的归属；以下是新增文档后的工作目录检查，不构成权限或业务功能验收。

- `pnpm index` 更新能力清单，二次生成无改动。
- `pnpm check` 退出 0：28 个公开预览页面，13 个测试与 TypeScript 通过。
- `pnpm build` 退出 0：28 个文档页面、28 页中文索引（2150 个词）与 Markdown/AI 导出生成。
- `pnpm verify` 退出 0：28 页正文与原文、根文件嵌入、链接、导航、元数据和中文查询通过。
- 最终构建后重新加载浏览器首页并保存分类预览截图；此次增加方案文档，没有修改应用 UI 或接口。

本轮公开预览文件增加的是方案与规格，不含账号 UUID、凭据或私密正文。正式环境与本人账号已请求确认；Claude 审查仍待进行，后续快照、接口与页面按 PLAN 准入。没有取得工具提交对应的 GitHub Actions 运行证据，以上结论限于本地工程和浏览器检查。

## 本机知识库接入验证

日期：2026-10-06。用户确认保留 Nextra，并仅在本机启动。本轮实现尚未提交或推送；既有 frontend 重设计的并行修改原样保留。以下结论针对当前工作目录，不能作为 main、CI 或真实使用验收的证明。

| 检查 | 结果与边界 |
|---|---|
| 后端 Ruff、格式、mypy | 全部退出 0；713 个文件格式通过，435 个源文件类型检查通过 |
| 后端 pytest | 1613 通过、948 跳过；未提供独立 PostgreSQL 测试库，跳过项不算通过，没有修改数据库结构 |
| frontend lint、typecheck、format:check | 全部退出 0 |
| frontend test | 92 个文件、607 项通过；包含真实 Editor.js ESM 加载、保存与未知 Markdown 字节保留，以及 Nextra 编译、章节和安全渲染 |
| frontend build | 退出 0；目录和详情为动态授权路由，不把内部正文编入公开产物 |
| OpenAPI | 同一工作目录的 API 在独立本机端口运行，重新生成客户端；openapi:check 退出 0，生成前后文件指纹一致 |
| workspace check、build | 29 个公开页面、19 个测试与 TypeScript 通过；Nextra/theme、Pagefind 中文索引、逐页 Markdown 和 AI 导出仍仅来自公开清单 |
| 独立 Git 工具测试 | 确定性、根文件映射、正文及章节 hash、快照损坏拒绝、重复保存、草稿恢复、冲突合并、限定提交、失败保留、决策替代、历史附件、路径及符号链接校验、提交后结果恢复均通过 |
| 本机初始化与只读 CLI | local:init 使用隔离目录创建专用副本与 30 篇内部文档快照，副本无 origin，配置和状态文件 0600、目录 0700；list/search/read 能读取已发布版本 |
| Git 工作目录检查 | git diff --check 退出 0；没有移动或重命名作者内容，没有向当前开发 checkout 提交或推送 |

浏览器使用现有前端生产构建和真实文档服务、Node 发布工具，但身份由仓库外的受控样本提供；来源、草稿与操作均在独立临时 Git 副本。没有使用本人真实登录，也没有向业务数据库写测试数据。测试端口为 Web 18866、API 18768，仅监听本机；产品仍使用约定的 8666/8667。

- 桌面与 390px 均检查正常、空、加载、错误、无权限状态。窄屏目录和正文宽度为 390px，没有整页横向溢出；表格自行横向滚动。Tab 到检索按钮、Enter 检索及打开命中章节通过，章节进入应用滚动容器并获得焦点。
- 富文本修改切换到原文视图、保存草稿、确认发布通过。隔离副本首个发布的 Git 差异只有预期段落的一处修改，来源干净，目录、详情与读取快照整体切换。
- 浏览器编辑期间从文件侧改变来源，保存返回版本冲突，网页未保存内容与本地来源分别保留。明确合并后再次保存和发布，正文同时包含两侧修改。
- 决策替代只在隔离副本执行。默认目录隐藏旧决策；启用历史模式可读取其废弃状态，编辑入口隐藏，关联新决策和原文链接保留 snapshot/history。发布工具测试另核对旧附件默认隐藏、历史模式可读。
- 浏览器检查期间发现并修复中文路由解码、重复章节提取、Editor.js 的 LogLevels 仅类型导出及保存器原文清理、跨路由章节定位问题。最终受控页面未捕获 error/warn。中文输入采用受控填充，不能替代实际输入法组合输入验收。

截图保存在当前任务附件目录。受控身份、假数据入口及临时发布内容都没有加入产品代码或公开清单，验证结束关闭本轮临时进程，保留原本运行的服务。

未完成门槛：真实账号 UUID 与正式本机初始化、真实 Obsidian 的五类十次往返、实际输入法、固定 20 条检索与 20 个本机 Codex 问题、目标环境完整冷启动与恢复。已尝试本机 Claude 只读审查，CLI 返回登录过期，审查没有执行。按 AGENTS §6，当前不标记“代码完成”或“能力可用”；没有本轮远端 CI 证据。Mermaid 内部页面显示可编辑源码，公开 Nextra 预览的图表渲染继续保留。
