# HotKey 文档工作区

`content/` 是普通 Markdown 与 Obsidian 的作者来源，外层保留文档校验、索引与快照工具。项目知识库用于开发维护，目标是在 frontend 的 `/workspace/docs` 接入 Nextra 与 Editor.js 编辑视图，共用样式、权限和版本；不采用 GitBook，不另建文档网站。本机实现与启动步骤见 [LOCAL](LOCAL.md)，真实账号及双端验收仍待完成；Notion 主来源路线仅作替代评估。

继续使用 Nextra/theme 4.6.1、Next.js、React 与现有校验、公开预览工具。正式内部知识库接入 frontend 的 `/workspace/docs`，本期只需本机运行，不增加服务器部署。公开 Pages 预览不承担内部权限；现有公开发布清单继续隔离未登记资料。

产品文档按用途分层：`content/product/prd/` 保存目标、范围与验收需求，`content/product/plan/` 保存任务、容量与执行依赖；`content/product/` 根层保留进度、架构与工程规范指针。每个目录独立从 01 编号，目录内不可重复，需求和计划允许各自使用 01。需求与计划通过标准相对链接互相引用，文档入口按这三类展示；实际任务状态统一维护在仓库根目录 BACKLOG。

在本目录执行：

```sh
pnpm install --frozen-lockfile
pnpm index
pnpm check
pnpm build
pnpm preview
```

预览服务器启动后，在另一个终端执行 `pnpm verify`，检查所有发布页面与原文、导航、嵌入与链接、AI 导出，以及 Pagefind 的“舆情 / 评论 / 情感”查询。可用 `DOCS_PREVIEW_URL` 指定其他预览地址（包含 `/hotkey-server` 前缀，不带结尾斜杠）。本次命令与结果见 [VERIFICATION.md](VERIFICATION.md)。

预览地址为 <http://127.0.0.1:8668/hotkey-server/>，可用 `PORT` 改端口。开发用 `pnpm dev`，搜索需在生产构建后通过静态预览检查。

当前旧站支持本地静态预览，GitHub Pages 工作流的构建与部署任务已成功，见[运行记录](https://github.com/StephenQiu30/hotkey-server/actions/runs/37417404223)；线上页面尚无本轮浏览器验收。公开预览与本机内部入口分开管理。内部资料入口已按专项 PRD 接入 HotKey frontend 与授权 API，需先初始化专用来源并配置现有账号。VERIFICATION 中较早的未部署描述保留为历史记录。

`.md` 通过 Nextra 的 `compileMdx` / `evaluate` API 以 `format: 'md'` 编译；保留普通 Markdown 和 HTML 注释，不需要 MDX 写法。公开预览仅加载 `public-documents.json` 中的 `documents`，未登记文件默认不导出。登记私密文档、草稿、重复路径、越界或缺失文件时构建失败；新增页面需经过审查后登记。导航从 frontmatter 的 `title` 和文件名生成，PRD 与 PLAN 分组，空目录不显示。`templates/`、`views/`、`.obsidian/` 不进入路由、搜索或 AI 导出。清单中的 `references` 只允许明确登记的模板链接到其已有公开 Git 原文，不生成模板正文。

指针页的 `source:` 仅允许在构建时追加根目录 BACKLOG、PROJECT、AGENTS 原文，正文中的原文链接供 Obsidian 使用。Markdown AST 插件把已发布文档的链接改为站内地址，其他仓库路径改为 GitHub 链接，保留锚点。根文件不由脚本写入。

`pnpm index` 仅更新首页 HTML 注释之间的索引块。`pnpm check` 检查元数据、枚举、关联路径、正文长度、命名、编号唯一性、链接与锚点及索引是否最新；代码块和行内代码中的双链示例不算真实链接。`pnpm build` 也先执行文档校验，失败时不生成新的静态页面和导出。

构建生成 `llms.txt`、`llms-full.txt` 和 `/raw/<相对 content/ 的文件名>.md`。原始 Markdown 保留 frontmatter、作者正文与相对链接；指针页面另外追加其嵌入源全文。

Nextra/theme 4.6.1 的 Layout 校验存在[上游问题](https://github.com/shuding/nextra/issues/5036)。`patches/` 中的补丁把 `children` 传入原有校验，不改变字段要求；并翻译主题未提供配置项的跳转正文、菜单、首页、目录和主题切换标签。pnpm 安装会自动应用。升级 Nextra 时应重新核对并移除已被上游修复的补丁。署名见根目录 `THIRD_PARTY_NOTICES.md`。
