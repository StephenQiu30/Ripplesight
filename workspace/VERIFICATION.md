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

## 2026-10-07 需求 workspace 阅读验证

范围：按用户本轮要求，先搭需求阅读与核对 workspace，暂不实现业务代码；文档与执行以最小 POC/demo 为后续验证方式。基于 main 的 `5e098e86` 工作目录，修改未提交或推送。复用现有 Nextra 静态阅读工具，没有新增应用、接口、数据库结构、编辑器或同步实现。

新增原文：[需求与验证入口](content/product/reference/04-需求与验证入口.md)、[AI 任务协议](content/product/reference/05-AI任务协议.md)、[POC 验证卡](content/product/reference/06-POC验证卡.md)、[热点事件候选核对](content/research/2026-10-07-热点事件需求核对.md)。首页改为先读当前需求与验证方式；根 AGENTS/BACKLOG 记录当前阶段，workspace/AGENTS 指向最小阅读路径。已有 PRD、决策、能力和大计划原文保留，不自动废弃或派发。

| 检查 | 实际结果 |
|---|---|
| `pnpm index` | 退出 0；首页生成索引包含新增阅读页 |
| `pnpm check` | 退出 0；34 页元数据/链接/命名有效，19 个现有工具测试与 TypeScript 通过 |
| `pnpm build` | 退出 0；34 页静态正文、34 页 Pagefind 中文索引与原始 Markdown / AI 导出生成 |
| `pnpm preview` | 已启动；仅监听 127.0.0.1:8668，阅读入口为 `http://127.0.0.1:8668/hotkey-server/` |
| `pnpm verify` | 最终退出 0；34 页正文和原文、导航、根文件嵌入、链接与 AI 导出有效；舆情 13 条、评论 16 条、情感 10 条 |
| 实际浏览器 | 首页显示当前阶段；打开需求原话、AI 协议与热点候选；搜索 POC 后点击第一条打开验证卡；候选明确标为待核对、未执行，卡保留待执行结果 |
| 当前 Codex 原文读取 | 直接读取本机 `out/raw/` 的需求入口、AI 协议与候选；以下三项核对可回到作者原文 |

原文核对问题与答案：

1. 当前是否可以开始业务编码？不能；本轮阶段是 workspace 搭建与需求核对（需求入口“用户已经明确的要求”）。
2. 首个热点 POC 是否已被选定或跑通？没有；它是待核对的 AI 候选，尚无业务验证结果（候选页开头）。
3. 工程检查通过是否等于真实业务能力可用？不等于；证据等级与局限需要区分，验证卡通过不自动更新整项能力为可用（AI 协议“文档状态不能代替验证”“执行和交付”）。

首次 `pnpm verify` 因 PROJECT 缺少“文档预览”说明而失败；在 PROJECT §10 补上当前实际使用的本机入口、作者来源与边界后，重新构建并复验通过。未修改验证脚本或放宽断言。

首页截图保存于本机忽略目录 `.tools/requirements-workspace/2026-10-07-home.jpg`；浏览器阅读标签页保留。重启预览在 workspace 执行 `pnpm preview`，内容改动后先重新 build。

边界：本次只验证文档阅读、检索、原文导出与当前 AI 的三条事实核对，尚未取得本人阅读反馈；没有选择或执行业务 POC，没有真实在线采集或模型调用，没有启动正式 `/workspace/docs` 的专用来源与账号配置，也没有实际 Obsidian 双端验收。当前作者目录仍是开发 checkout 的 `workspace/content/`。`llms.txt` 中的绝对 URL 仍指向既有 GitHub Pages，本轮新内容仅在本机，AI 应读当前本机文件或 8668 原文。没有对外发布，也没有改动已有业务服务和自动化配置。


## 2026-10-07 产品参考英文目录修正

按用户要求，将 product 根层六份参考文档移入 `content/product/reference/`，与 `prd/`、`plan/` 并列；保留文件名和编号。更新相对链接、根文件 source、related、公开/内部清单、AI 入口与架构目录说明。现有文档工具只调整目录分组、导航与指针路径，并同步现有测试/验证脚本中的路径；没有业务实现。

`pnpm index`、`pnpm check`（34 页、19 个工具测试及 TypeScript）、`pnpm build`、`pnpm verify`（34 页正文/原文与 AI 导出）、`git diff --check` 均通过。浏览器重新加载首页，产品参考为独立分组，分类表显示 `product/reference/`；新页面与 raw 路径在 HTTP 验证中通过。旧编号历史文字保留，新原文导出使用迁移后的目录。截图：`.tools/requirements-workspace/2026-10-07-product-reference.jpg`。未提交、推送或对外发布。

## 2026-10-07 页脚与项目显示名称

核对 workspace/app/layout.tsx 及当前安装的 nextra-theme-docs 源码：全局 Footer 为 Nextra 内置组件，页脚文字由本项目配置，Layout 的 footer 参数为可选。本轮删除该组件的导入与配置。项目显示名沿用现有 frontend 的“知微见澜 Ripplesight”，统一文档导航、浏览器标题、首页、PRD、根目录说明与 AI 导出中的项目称呼。保留真实技术路径和标识，以及既有验证历史；需求、范围和业务实现未改变。

`pnpm index`、`pnpm check`（19 项现有测试及 TypeScript）、`pnpm build`、`pnpm verify` 均通过。另对 34 个生成页面检查：HTTP 200、无 footer 元素、正式名称存在、旧页脚品牌不存在。实际浏览器刷新后正式名称显示正确，footer 元素数量为 0；默认视口内容宽度与滚动宽度均为 831px，390px 窄屏覆盖下两者均为 375px（扣除滚动条），无整页横向溢出。检查后恢复默认视口；页面末尾保留文章导航与原文入口，没有全局页脚。

本机截图：`.tools/requirements-workspace/2026-10-07-footer-cleanup.jpg`、`.tools/requirements-workspace/2026-10-07-brand-mobile.jpg`。未新增测试、未提交、推送或对外部署。

## 2026-10-07 Ripplesight 仓库与项目改名

本人明确要求将 GitHub 仓库和当前项目名称统一为 `Ripplesight`。已通过 GitHub API 将 `StephenQiu30/hotkey-server` 改为 `StephenQiu30/Ripplesight`，仓库 ID 仍为 `1217852212`，默认分支仍为 main；description 同步当前产品定位。本机 origin 更新为 `https://github.com/StephenQiu30/Ripplesight.git`，`git ls-remote origin HEAD` 验证成功，远端 HEAD 仍为 `5e098e867543a7764891946eb93e5965d934c8a5`。

当前源码同步产品标识、网页和 PWA 元数据、登录邮件及通知、报告与公开分发的品牌、MCP serverInfo、CLI 说明、采集 User-Agent、下载文件名前缀、根文档与 workspace 链接。包名为 `ripplesight-backend`、`ripplesight-frontend`、`ripplesight-docs`；镜像默认使用 `ripplesight-` 前缀。`uv lock --offline` 只更新并重排根虚拟包，依赖版本未变。文档 basePath、canonical、导航、raw、AI 导出与验证脚本使用 `/Ripplesight`。

兼容边界：保留 `HOTKEY_*` 环境变量、数据库和数据卷、Compose 已有项目名、登录 Cookie/HTTP 协议、MCP 工具名、生成客户端类型名以及 Obsidian 默认 `HotKey/` 导出目录。本机共享 checkout 与既有 worktree 路径未移动；被冻结的 Flutter 项目未改动。未改业务能力、权限、数据库结构或自动化任务。

| 检查 | 结果 |
|---|---|
| backend Ruff、格式、mypy | 全部通过；435 个源码文件类型检查通过 |
| backend unit + architecture | 最终全量复测 1585 通过；首次 1584 通过、1 项 MediaCrawler 进程终止测试发生 OS `PermissionError`，该项单独复测通过后全量复测也通过；未修改采集进程逻辑 |
| frontend lint、typecheck、format、test、build | 全部通过；118 个测试文件、939 个测试通过 |
| workspace index、check、build、verify | 全部通过；34 页、19 个工具测试、TypeScript、逐页 HTTP/原文与 AI 导出有效；舆情/评论/情感查询分别命中 13/16/10 条 |
| 文档静态产物复核 | 34 页无 footer、旧 Pages 路径、旧仓库链接和旧中文品牌 |
| Compose 配置及 Git 差异 | `docker compose config --quiet`、`git diff --check` 通过；未重启既有 8666/8667 服务 |
| 本机浏览器 | 文档桌面与 390px 预览无整页横向溢出；文档标题、导航、canonical 和原文指向新名称，footer 数量为 0；手机菜单与 Ripplesight 搜索可用；8686 临时应用预览的首页和关于页显示新品牌 |

截图保存于本机忽略目录 `.tools/requirements-workspace/`：`2026-10-07-ripplesight-docs.jpg`、`2026-10-07-ripplesight-docs-mobile.jpg`、`2026-10-07-ripplesight-app-mobile.jpg`。测试后恢复默认视口；本机文档阅读入口为 <http://127.0.0.1:8668/Ripplesight/>。

待发布：GitHub Pages API 已报告新地址 <https://stephenqiu30.github.io/Ripplesight/>，但其当前 HTML 仍为旧构建，标题为 `HotKey 文档 · HotKey 文档`，样式资源 `/hotkey-server/_next/static/css/11c59cc40cabfed8.css` 返回 404。GitHub 官方说明仓库改名不重定向项目站点地址（[来源](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)）。需提交、推送并完成 workspace-site 部署后再验线上；本轮尚未获得 AGENTS §7 所要求的明确提交/推送授权，源码与既有 workspace 调整保留为未提交修改。本机验证不代替线上部署、数据库集成、真实采集或模型验收。

## 2026-10-07 父工作区、客户端与描述补齐

按本人补充要求，将实际父目录迁为 `/Users/stephenqiu/Desktop/StephenQiu/Ripplesight`，实际仓库目录为 `ripplesight-server/` 与 `ripplesight-app/`。迁移前后分别核对两个仓库的 Git diff 与未跟踪文件 hash，一致；所有既有修改原样保留。旧父目录和旧仓库名仅保留符号链接，供未迁移的会话访问。外部 worktree 的 `.git` 指针和主仓库登记路径改为新地址；已有缺失的 deploy worktree 仍标记 prunable，未清理或改变其状态。

Python 虚拟环境的 36 个启动/激活文件迁到新绝对路径，prompt 使用新包名。新路径执行锁文件同步后恢复了原有额外安装的 `tenacity==9.1.4`；未增加项目依赖。父目录新增 README/AGENTS 作为人和 AI 的入口；Claude 已有设计预览配置仅改显示名，保留真实的临时文件来源路径。

冻结客户端 GitHub 仓库由 `hotkey-app` 改为 [Ripplesight-app](https://github.com/StephenQiu30/Ripplesight-app)，ID 仍为 `1247949203`，main HEAD 为 `6697bd9fc71891e4f29510329e5c3408d1745284`，本机 origin 同步。纠正其旧 About 对“内容创作者 Web 工作台”的错误描述，明确“Flutter 客户端预留仓库；当前冻结，仅维护工程约定，尚无可运行应用”。App README、规范和 GitHub 模板使用新品牌与链接；未初始化 Flutter 工程。

主仓库 GitHub About、README、Web 标题与 description、PWA 描述、关于页、三个包与需求文档站描述统一当前定位：个人非商业使用的公开资讯阅读与舆情监控项目，围绕关键词连接来源材料、讨论与事件进展。关于页纠正首页用途为公开资讯阅读；描述不承诺已经完成真实业务验收。

新路径下 frontend 的 lint/typecheck/format、939 个测试及构建通过；backend Ruff/格式、435 源码的 mypy 与 76 个配置/提示词测试通过；workspace 的 19 个测试、TypeScript、34 页构建、HTTP/原文/AI 导出与搜索检查通过；App 公共文档和模板检查、两仓库 `git diff --check` 通过。已有 8666/8667 服务没有重启；文档预览使用新目录启动。

未完成的应用设置项：Codex `list_projects` 仍返回项目标签 `HotKey` 与旧路径，没有自动迁移。自动审批拒绝通过 `com.openai.codex` 界面改项目设置，理由是应用安全限制；当前没有可用的专用项目改名工具，未绕过限制编辑应用内部状态。需在 Codex 中将保存的项目目录切换为新父目录；兼容链接保证现有聊天仍能访问文件。源码尚未获明确提交/推送授权，GitHub README、Pages 与正式运行版本仍待发布。

浏览器复核补充：新目录 8686 临时预览的首页标题为 `Ripplesight · 公开资讯阅读与个人舆情监控`，PWA name/short_name 均为 Ripplesight，description 为当前项目定位；关于页的标题、品牌与正文说明正确。默认 1280px 与 390px 视口无整页横向溢出，测试后恢复默认视口并关闭临时应用预览；截图为 `.tools/requirements-workspace/2026-10-07-ripplesight-description.jpg`。新目录的 8668 文档预览继续保留。
