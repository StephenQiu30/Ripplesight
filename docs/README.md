# Ripplesight 项目文档

2026-10-08 起回归 `docs/` 下的 Markdown/Git 管理。文档原文只有这一份，AI、编辑器和 Obsidian 直接读取它。需求从 [index](index.md) 开始，任务状态只在根目录 [BACKLOG](../BACKLOG.md)。

## Obsidian

选择“打开本地仓库”，打开 `ripplesight-server/docs/`。保留 `.obsidian/app.json` 的标准 Markdown 相对链接与自动更新链接设置、`templates.json` 的模板目录及 `core-plugins.json` 的图谱、反向链接、属性、Templates 和 Bases；模板在 `templates/`，三个看板在 `views/`。个人布局、插件缓存等继续忽略，不提交。

直接修改这里的 Markdown，再通过 Git diff 审阅。PRD、PLAN、能力、决策与记录继续使用 frontmatter；新增文档按所在目录编号，记录与调研可用日期命名。根目录 BACKLOG、PROJECT、AGENTS 仍是唯一原文，`product/reference/` 中的指针链接到根文件；它们位于 vault 外，可在编辑器中打开，不复制成第二份可编辑原文。

## 索引与校验

无需文档网站、账号、快照或发布流程。在 `scripts/docs/` 执行：

```sh
pnpm install --frozen-lockfile
pnpm index
pnpm check
```

工具仅更新 `docs/index.md` 的生成索引，并检查元数据、编号、关联、相对链接和章节锚点；不生成网页、Pagefind、raw 或 llms 导出。Obsidian 的检索、图谱和 Bases 直接使用原文件。模板、看板、设计参考与本 README 不进入需求索引。

## 旧资料

旧 Nextra 站、网页编辑及 GitHub Pages 发布工作流已从当前项目移除。专项 PRD 与 PLAN 标为废弃，旧验证记录保留在 [VERIFICATION](VERIFICATION.md)，其中站点命令和结论仅为历史证据。旧实现链接固定到迁移前提交，不表示仍可运行。

本机旧站点与生成物归档在 Git 忽略的 `.tools/retired-workspace-2026-10-08/`。若曾使用 `.tools/workspace/source`、`store` 或其他私密副本，其内容仍保留原处；先审阅来源、草稿和冲突，不能把私密内容自动拷入公开 docs，也不要重新初始化覆盖它们。

项目文档迁移不影响业务报告的 Obsidian 导出：`backend/app/knowledge/obsidian.py`、导出配置、CLI、API 和测试继续保留。文件检查不代表已完成真实 Obsidian 操作验收。
