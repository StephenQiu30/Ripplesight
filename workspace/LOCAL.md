# 本机项目知识库

2026-10-07 本轮先搭需求阅读 workspace，直接维护当前 checkout 的 `workspace/content/`，使用已有静态预览 <http://127.0.0.1:8668/Ripplesight/> 与逐页原文读取；没有执行以下内部知识库初始化。当前阅读与 AI 使用方式见 [README](README.md)。下方保留正式知识库的账号、独立来源和双端编辑流程，需要启用时再明确切换作者来源。

内部入口是 <http://127.0.0.1:8666/workspace/docs>，沿用 Ripplesight 的登录、布局和主题。使用 Nextra 4.6.1 编译普通 Markdown，Editor.js 提供段落、标题的富文本编辑；代码、Mermaid、表格、frontmatter、注释及未知语法保留为原文块。Mermaid 目前显示源码，不加载需要宽松 HTML 或样式策略的渲染器。

## 初始化与启动

先按项目 README 配好本机 `.env`、数据库与现有 Ripplesight 账号，并在 backend、frontend 和 workspace 安装锁定依赖。本机 API 需要 Node.js、Git、uv，Web 和文档工具使用 pnpm。没有新增数据库表或独立知识库账号。

在 `workspace/` 执行：

```sh
pnpm local:init -- --user <现有账号的 UUID>
pnpm local:start
```

账号 UUID 来自登录后的 `/api/identity/session` 的 `user.id`，不使用用户名或公开发布账号推断。初始化生成被 Git 忽略的 `.tools/workspace/config.json`，默认只允许这个账号读、改和发布。配置中三组允许清单可分别调整；发布还需具备读写权限。未初始化、未配置账号或坏快照均不开放读取。启动不会终止其他进程，8666/8667 已占用时先正常停止现有 Web/API。

初始化创建 `.tools/workspace/source/` 专用 Git 副本，复制当前文档及 BACKLOG、PROJECT、AGENTS，并保存初始本地文档历史；不提交或修改开发 checkout，也没有远端推送。`.tools/workspace/store/` 保存不可变快照、本人草稿和操作记录，重启复用这些目录，不重复执行初始化。配置目录权限为 0700，状态文件为 0600。备份时一起保留 source、store 与 config；不要只备份 `.next` 或公开静态导出。

## 网页和 Obsidian 编辑

用 Obsidian 打开 `.tools/workspace/source/workspace/content/`。初始化后它是网页与本机编辑共用的来源；原开发 checkout 的 `workspace/content/` 是初始化种子和公开资料，网页不会回写它。根文件位于专用副本根目录，指针页面显示实际来源，网页编辑直接修改该唯一原文。

网页依次“编辑文档 → 保存草稿 → 对比差异 → 确认发布”。保存草稿不改变当前读取版本，发布后保存本地 Git 历史并切换整个快照，目录、搜索、正文、附件和原文使用相同标识。历史版本可加载为新草稿，再审阅、保存和发布；不会改写已有 Git 历史。

Obsidian 修改现有文档后，在对应网页进入编辑并使用“发布本地来源修改”。网页草稿与本地来源同时变化时，页面展示来源、当前修改与已保存草稿；先合并，再明确选择“已对比并合并来源”，保存并发布。来源 hash 和草稿 revision 会在保存、发布时再次核对，禁止强制覆盖。未保存修改离开页面会提示；网络结果未知时使用“核对操作结果”，不要盲目重发。

生效决策不能直接覆盖。网页修改其草稿，填写新标题、日期和替代原因，保存后输入新的 `decisions/两位编号-名称.md` 路径，选择“发布替代决策”。确认后旧记录标为废弃、新记录保持生效并建立双方关联，内部清单登记新记录；不会自动扩展公开清单。普通的新文档仍需在专用副本维护元数据、索引和内部清单，并完成文档审查；网页目前只新增替代决策。

## AI 阅读与权限

AI 应先取目录的 `snapshot_id`，再将它带入搜索、详情或原文请求，避免跨版本引用。路径以返回的 `path` 为准；正文和章节原文带 SHA-256 响应头。引用使用 `/workspace/docs/<path>?snapshot=<id>#<anchor>`。默认排除废弃资料，历史模式须显式设置 `history=true`。

认证接口均位于 `/api/workspace/documents`：目录、`/search`、`/document`、`/raw`、`/attachment`；写入包括 `/draft`、`/publish`，结果查询为 `/operations/<UUID>`。所有读取使用现有会话，写入还核对 Origin 和 CSRF。目录的“查看历史资料（含废弃）”明确启用历史模式；旧决策显示废弃状态并只读，关联链接保留版本和历史标记。不能把登录 Cookie 放进文档、命令示例或 AI 上下文。远程 MCP 不是本期前提，没有新增公共全文出口。

本机 Codex 可通过下面的只读工具按需读取已发布快照，不需要复制浏览器凭据：

```sh
pnpm local:read -- list
pnpm local:read -- search --query 权限
pnpm local:read -- read --path product/prd/02-PRD-workspace项目知识库.md --snapshot <目录返回的标识>
```

该工具依赖当前系统用户已拥有配置目录的文件访问权，不能替代远程 API 授权；它只允许目录、搜索、详情和原文读取。直接读取 source 中尚未发布的内容时必须标为工作草稿。规格、生效决策、进度和验收证据分别引用；资料不足或冲突时说明依据，不能按日期自动选择规则。

## 公开预览与验收

原 Nextra/theme、Pagefind、公开 AI 导出、补丁及 Pages 工作流继续保留，只读取 `public-documents.json`。本机内部清单为 `internal-documents.json`，新增私密资料留在专用副本，不进入公开仓库或静态产物。

工程测试覆盖权限、Markdown 往返、隔离 Git、冲突、失败和操作恢复。能力可用仍须按 PRD 验证真实账号、桌面与 390px、实际 Obsidian、固定中文查询和本机 Codex，并由 Claude 审查与记录；受控样本不替代这些验收。
