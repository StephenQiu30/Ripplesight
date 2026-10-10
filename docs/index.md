# Ripplesight 知识库

| 入口 | 职责 |
|---|---|
| [prd / PRD](prd/PRD.md) | 为什么做、为谁做、产品边界与验收标准 |
| [requirement / Requirement](requirement/REQUIREMENT.md) | 当前页面字段、数量、动作和关键业务约束 |
| [design / Design](design/DESIGN.md) | 现行视觉、组件、布局与交互规则 |
| [plan / Plan](plan/PLAN.md) | 当前执行顺序与交付门槛 |
| [文档视图](views/文档.base) | 在 Obsidian 中按目录浏览当前文档 |

## Obsidian 使用

打开本地仓库 `ripplesight-server/docs/`。四个主目录每类先维护一份原文，新增内容放到对应目录；确有独立主题才拆文件，不为每项任务生成成套文档。

使用搜索、图谱、反向链接、目录和 Templates 等核心功能，跨文档优先用标准 Markdown 相对链接。共享 `.obsidian/` 设置保留；个人布局、缓存和私密资料继续留本机。通过 Templates 从 `templates/` 插入对应模板，模板可选，编号和 frontmatter 不强制。

仓库根目录的 `BACKLOG.md`（进度）、`PROJECT.md`（技术架构）、`AGENTS.md`（工程规范）在代码编辑器中打开；它们位于本 vault 外，不作为 Obsidian 笔记链接。接口与数据库直接查代码和唯一 schema，不复制字段字典。当前知识库只保留有效需求、规范、计划与使用说明，不保留历史文档或归档副本。

## 检查

在 `frontend/` 执行 `pnpm docs:check` 检查本地链接和章节锚点，工具回归为 `pnpm test tests/docs/documents.test.ts`。入口手动维护，不生成索引，不运行文档站或发布流程。

业务报告的 Obsidian 导出独立于项目文档。
