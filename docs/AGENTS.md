# docs 文档维护

继承根目录 [AGENTS](../AGENTS.md)。本目录是项目文档唯一作者来源，也是 Obsidian vault；不再运行在线知识库。

1. 从 [需求入口](index.md)、[需求与验证入口](product/reference/04-需求与验证入口.md)和根目录 [BACKLOG](../BACKLOG.md)开始，按任务选择相关文档。
2. 保留标准 Markdown 相对链接、frontmatter、templates、views 和共享 Obsidian 设置。私密资料不自动迁入公开仓库。
3. PRD 定需求、PLAN 定执行建议，实际进度只在 BACKLOG；区分用户要求、提案、实现事实和运行证据。
4. 在线知识库 PRD/PLAN 已废弃，不再扩建网页阅读、编辑、快照或发布设施。业务 Obsidian 导出仍有效。
5. 修改后在 frontend 执行 pnpm docs:index、pnpm docs:check，结果记录在 VERIFICATION.md。不再运行文档站 build/preview。
6. 原位更新文档并保留其他任务的未提交修改。提交和推送按根工程规范及用户当前授权执行。
