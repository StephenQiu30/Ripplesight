# Ripplesight 文档工作区

## 当前使用方式（2026-10-08）

从[页面PRD](content/product/prd/03-PRD-全站页面需求.md)进入具体页面，核对展示字段、数量、操作、接口与存储；[收敛方案](content/product/reference/14-页面驱动的收敛方案.md)替换无页面依据的扩展。进度只在根BACKLOG，历史调研/计划按需查证。

`content/product/prd/`维护目标，`pages/`维护逐页合同，`reference/`维护当前接口/数据与证据指针，`plan/`保留专项或历史计划。每目录独立编号，Markdown/Git是唯一需求原文，不建立数据库正文副本。

8668的Nextra静态预览读取公开允许清单，无需登录；8666的`/workspace/docs`读取单独初始化且已发布的内部快照，需要现有账号及独立读/写/发布允许清单。两者不是同一个数据源。仓库提交推送或8668热更新不代表内部副本已更新；已有副本先审查合并源码/清单并按[LOCAL](LOCAL.md)发布，不重新初始化覆盖草稿。

公开/内部阅读清单都登记当前页面需求及其依赖；内部清单保留已有内部资料，不反向发布到公开清单。只改文档登记不授予任何账号权限。本地和远端部署结果以[VERIFICATION](VERIFICATION.md)的具体提交证据为准，不能把历史CI或线上旧页面当当前源码。

在本目录执行：

```sh
pnpm install --frozen-lockfile
pnpm index
pnpm check
pnpm build
pnpm preview
```

预览服务器启动后，在另一个终端执行 `pnpm verify`，检查所有发布页面与原文、导航、嵌入与链接、AI 导出，以及 Pagefind 的“舆情 / 评论 / 情感”查询。可用 `DOCS_PREVIEW_URL` 指定其他预览地址（包含 `/Ripplesight` 前缀，不带结尾斜杠）。本次命令与结果见 [VERIFICATION.md](VERIFICATION.md)。

预览地址为 <http://127.0.0.1:8668/Ripplesight/>，可用 `PORT` 改端口。开发用 `pnpm dev`，搜索需在生产构建后通过静态预览检查。

GitHub Pages由既有工作流发布；每次应核对目标提交及运行结果。内部知识库仍需专用来源、宿主工具和账号允许清单，公开预览不承担内部权限。

`.md` 通过 Nextra 的 `compileMdx` / `evaluate` API 以 `format: 'md'` 编译；保留普通 Markdown 和 HTML 注释，不需要 MDX 写法。公开预览仅加载 `public-documents.json` 中的 `documents`，未登记文件默认不导出。登记私密文档、草稿、重复路径、越界或缺失文件时构建失败；新增页面需经过审查后登记。导航从 frontmatter 的 `title` 和文件名生成，PRD 与 PLAN 分组，空目录不显示。`templates/`、`views/`、`.obsidian/` 不进入路由、搜索或 AI 导出。清单中的 `references` 只允许明确登记的模板链接到其已有公开 Git 原文，不生成模板正文。

指针页的 `source:` 仅允许在构建时追加根目录 BACKLOG、PROJECT、AGENTS 原文，正文中的原文链接供 Obsidian 使用。Markdown AST 插件把已发布文档的链接改为站内地址，其他仓库路径改为 GitHub 链接，保留锚点。根文件不由脚本写入。

`pnpm index` 仅更新首页 HTML 注释之间的索引块。`pnpm check` 检查元数据、枚举、关联路径、正文长度、命名、编号唯一性、链接与锚点及索引是否最新；代码块和行内代码中的双链示例不算真实链接。`pnpm build` 也先执行文档校验，失败时不生成新的静态页面和导出。

构建生成 `llms.txt`、`llms-full.txt` 和 `/raw/<相对 content/ 的文件名>.md`。原始 Markdown 保留 frontmatter、作者正文与相对链接；指针页面另外追加其嵌入源全文。

Nextra/theme 4.6.1 的 Layout 校验存在[上游问题](https://github.com/shuding/nextra/issues/5036)。`patches/` 中的补丁把 `children` 传入原有校验，不改变字段要求；并翻译主题未提供配置项的跳转正文、菜单、首页、目录和主题切换标签。pnpm 安装会自动应用。升级 Nextra 时应重新核对并移除已被上游修复的补丁。署名见根目录 `THIRD_PARTY_NOTICES.md`。
